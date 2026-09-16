import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import HTTPException

from app.devices.repository import DeviceRepository
from app.devices.schema import (
    DeviceActivationClaim,
    DeviceActivationRequest,
    DeviceHeartbeat,
    DeviceRegister,
    DeviceUpdate,
    DeviceAssignmentRequest,
    DeviceDecommissionRequest,
    DeviceDeleteRequest,
)
from app.auth.security import SECRET_KEY, verify_password
from app.devices.authority import (
    TERMINAL_IDENTITY_REVOKED,
    hash_device_identity,
    terminal_authority_error,
)
from app.core.config import get_settings
from app.inventory.stock_repository import BranchStockRepository
from app.subscriptions.service import SubscriptionService
from app.models import AuditEvent, DeviceTombstone


UTC = timezone.utc
ACTIVATION_CODE_TTL = timedelta(minutes=10)
MAX_ACTIVATION_ATTEMPTS = 5
ACTIVATION_LOCKOUT = timedelta(minutes=15)


def utcnow() -> datetime:
    return datetime.now(UTC)


def hash_activation_code(code: str) -> str:
    return hashlib.sha256(
        f"{SECRET_KEY}:{code}".encode("utf-8")
    ).hexdigest()


def normalize_status(device) -> str:
    if device.removed_at is not None:
        return "removed"
    if device.deactivated_at is not None or device.active is False:
        return "deactivated"
    return device.status or "active"


class DeviceService:
    def __init__(self, repo: DeviceRepository):
        self.repo = repo
        self.stock = BranchStockRepository(repo.db)

    def subscription_service(self) -> SubscriptionService:
        settings = get_settings()
        return SubscriptionService(
            self.repo.db,
            offline_grace_hours=settings.subscription_offline_grace_hours,
            provider_name=settings.subscription_provider_name,
            checkout_base_url=settings.subscription_provider_checkout_base_url,
            webhook_secret=settings.subscription_provider_webhook_secret,
            webhook_signature_header=settings.subscription_webhook_signature_header,
            paynow_integration_id=settings.paynow_integration_id,
            paynow_integration_key=settings.paynow_integration_key,
            paynow_return_url=settings.paynow_return_url,
            paynow_result_url=settings.paynow_result_url,
        )

    async def _identity_is_tombstoned(self, device_key: str, fingerprint: str | None = None) -> bool:
        checker = getattr(self.repo, "identity_is_tombstoned", None)
        if checker is None:
            return False
        return await checker(
            hash_device_identity(device_key),
            hash_device_identity(fingerprint) if fingerprint else None,
        )

    async def _get_device(self, company_id: UUID, device_id: UUID, *, for_update: bool = False):
        try:
            return await self.repo.get_by_id(company_id, device_id, for_update=for_update)
        except TypeError:
            return await self.repo.get_by_id(company_id, device_id)

    @staticmethod
    def _clean_optional(value: str | None) -> str | None:
        if value is None:
            return None

        cleaned = value.strip()
        return cleaned or None

    async def _enforce_attempt_limit(
        self,
        company_id: UUID,
        device_fingerprint: str,
    ):
        now = utcnow()
        attempt = await self.repo.get_activation_attempt(
            company_id,
            device_fingerprint,
            for_update=True,
        )

        if (
            attempt is not None
            and attempt.locked_until is not None
            and attempt.locked_until > now
            and attempt.failed_attempts >= MAX_ACTIVATION_ATTEMPTS
        ):
            raise HTTPException(
                429,
                "Too many activation attempts. Try again later.",
            )

        if (
            attempt is not None
            and attempt.locked_until is not None
            and attempt.locked_until <= now
        ):
            attempt.failed_attempts = 0
            attempt.locked_until = None

    async def _record_failed_attempt(
        self,
        company_id: UUID,
        device_fingerprint: str,
    ):
        now = utcnow()
        await self.repo.ensure_activation_attempt(
            company_id,
            device_fingerprint,
        )
        attempt = await self.repo.get_activation_attempt(
            company_id,
            device_fingerprint,
            for_update=True,
        )
        if attempt is None:
            return

        if (
            attempt.locked_until is not None
            and attempt.locked_until <= now
        ):
            attempt.failed_attempts = 0
            attempt.locked_until = None

        attempt.failed_attempts += 1
        attempt.last_failed_at = now
        if attempt.failed_attempts >= MAX_ACTIVATION_ATTEMPTS:
            attempt.locked_until = now + ACTIVATION_LOCKOUT

    async def _clear_attempts(
        self,
        company_id: UUID,
        device_fingerprint: str,
    ):
        await self.repo.delete_activation_attempt(
            company_id,
            device_fingerprint,
        )

    async def _ensure_pos_number_available(
        self,
        company_id: UUID,
        branch_id: UUID,
        pos_number: int | None,
        *,
        exclude_device_id: UUID | None = None,
    ):
        if pos_number is None:
            return

        existing = await self.repo.find_branch_pos_number_device(
            company_id,
            branch_id,
            pos_number,
            exclude_device_id=exclude_device_id,
        )

        if existing is not None:
            raise HTTPException(
                409,
                "This POS number is already assigned in the selected branch",
            )

    async def _validate_location(
        self,
        company_id: UUID,
        shop_id: UUID,
        branch_id: UUID,
    ):
        shop = await self.repo.get_shop(
            company_id,
            shop_id,
        )

        if not shop:
            raise HTTPException(
                404,
                "Shop not found or inactive",
            )

        branch = await self.repo.get_branch(
            company_id,
            branch_id,
        )

        if not branch:
            raise HTTPException(
                404,
                "Branch not found or inactive",
            )

        if branch.shop_id != shop.id:
            raise HTTPException(
                400,
                "The selected branch does not belong to the selected shop",
            )

        return shop, branch

    async def register(self, data: DeviceRegister):
        now = utcnow()
        device_key = data.device_key.strip()
        name = data.name.strip()
        platform = data.platform.strip() or "web"
        app_version = data.app_version.strip() or "1.0.0"
        device_fingerprint = self._clean_optional(
            data.device_fingerprint
        )

        if await self._identity_is_tombstoned(device_key, device_fingerprint):
            raise terminal_authority_error(
                403,
                TERMINAL_IDENTITY_REVOKED,
                "This terminal identity was permanently deleted",
            )

        existing = await self.repo.get_by_key(
            data.company_id,
            device_key,
        )

        if existing:
            if normalize_status(existing) in {"deactivated", "removed"}:
                raise HTTPException(403, "Device access has been disabled")
            await self.repo.update_registration(
                existing,
                name=name,
                device_fingerprint=device_fingerprint,
                platform=platform,
                app_version=app_version,
                last_seen_at=now,
            )

            return await self.repo.get_view(
                data.company_id,
                existing.id,
            )

        default_branch = await self.stock.resolve_branch(
            data.company_id,
            None,
        )

        device = await self.repo.create_device(
            company_id=data.company_id,
            shop_id=default_branch.shop_id,
            branch_id=default_branch.id,
            device_key=device_key,
            name=name,
            friendly_name=name,
            pos_number=None,
            platform=platform,
            app_version=app_version,
            status="active",
            active=True,
            claimed_at=now,
            device_fingerprint=device_fingerprint,
            pending_shop_id=default_branch.shop_id,
            pending_branch_id=default_branch.id,
            last_seen_at=now,
        )

        return await self.repo.get_view(
            data.company_id,
            device.id,
        )

    async def request_activation(
        self,
        data: DeviceActivationRequest,
    ):
        friendly_name = data.friendly_name.strip()
        if not friendly_name:
            raise HTTPException(400, "Friendly name is required")

        shop, branch = await self._validate_location(
            data.company_id,
            data.shop_id,
            data.branch_id,
        )
        await self._ensure_pos_number_available(
            data.company_id,
            branch.id,
            data.pos_number,
            exclude_device_id=data.device_id,
        )
        await self.subscription_service().enforce_device_activation_allowed(
            data.company_id,
            exclude_device_id=data.device_id,
        )

        device = None
        if data.device_id is not None:
            device = await self.repo.get_by_id(
                data.company_id,
                data.device_id,
            )
            if not device:
                raise HTTPException(404, "Device not found")

        now = utcnow()
        activation_code = secrets.token_urlsafe(9).upper()[:10]
        activation_hash = hash_activation_code(activation_code)
        expires_at = now + ACTIVATION_CODE_TTL

        if device is None:
            placeholder_key = f"pending-{UUID(int=secrets.randbits(128))}"
            device = await self.repo.create_device(
                company_id=data.company_id,
                shop_id=shop.id,
                branch_id=branch.id,
                device_key=placeholder_key,
                name=friendly_name,
                friendly_name=friendly_name,
                pos_number=data.pos_number,
                platform="pending",
                app_version="pending",
                status="pending",
                active=False,
                claimed_at=None,
                activation_code_hash=activation_hash,
                activation_code_expires_at=expires_at,
                device_fingerprint=None,
                pending_shop_id=shop.id,
                pending_branch_id=branch.id,
                last_seen_at=None,
            )
        else:
            device.friendly_name = friendly_name
            device.name = friendly_name
            device.pos_number = data.pos_number
            device.shop_id = shop.id
            device.branch_id = branch.id
            device.pending_shop_id = shop.id
            device.pending_branch_id = branch.id
            device.activation_code_hash = activation_hash
            device.activation_code_expires_at = expires_at
            if normalize_status(device) == "removed":
                device.removed_at = None
            if normalize_status(device) == "deactivated":
                device.deactivated_at = None
                device.deactivation_reason = None
            device.status = "pending"
            device.active = False
            await self.repo.save(device)

        view = await self.repo.get_view(
            data.company_id,
            device.id,
        )

        return {
            "device": view,
            "activation_code": activation_code,
            "activation_code_expires_at": expires_at,
        }

    async def claim_activation(
        self,
        data: DeviceActivationClaim,
    ):
        now = utcnow()
        device_key = data.device_key.strip()
        device_fingerprint = data.device_fingerprint.strip()
        claimed_device_id = None

        try:
            # The request-scoped session may already have an autobegun
            # transaction because the billable-company dependency reads the
            # subscription before this service is called. This service owns
            # completion of that transaction; starting another one here would
            # raise InvalidRequestError and could strand a pending terminal.
            if await self._identity_is_tombstoned(device_key, device_fingerprint):
                raise terminal_authority_error(
                    403,
                    TERMINAL_IDENTITY_REVOKED,
                    "This terminal identity was permanently deleted",
                )
            await self._enforce_attempt_limit(
                data.company_id,
                device_fingerprint,
            )

            existing_global = await self.repo.get_by_global_key(
                device_key,
                for_update=True,
            )
            if (
                existing_global
                and existing_global.company_id != data.company_id
            ):
                raise HTTPException(
                    409,
                    "This device is already claimed by another company",
                )

            if (
                existing_global
                and existing_global.company_id == data.company_id
                and existing_global.device_fingerprint
                == device_fingerprint
                and existing_global.claimed_at is not None
                and existing_global.status == "active"
            ):
                await self._clear_attempts(
                    data.company_id,
                    device_fingerprint,
                )
                claimed_device_id = existing_global.id
            else:
                device = await self.repo.get_pending_activation(
                    data.company_id,
                    hash_activation_code(
                        data.activation_code.strip().upper()
                    ),
                    now,
                    for_update=True,
                )

                if device is None:
                    await self._record_failed_attempt(
                        data.company_id,
                        device_fingerprint,
                    )
                    # Failed credential attempts are security state and must
                    # survive the 400 response. No terminal fields have been
                    # changed on this path.
                    await self.repo.db.commit()
                    raise HTTPException(
                        400,
                        "Invalid or expired activation code",
                    )

                if (
                    existing_global
                    and existing_global.id != device.id
                ):
                    raise HTTPException(
                        409,
                        "This device key is already registered",
                    )

                await self.subscription_service().enforce_device_activation_allowed(
                    data.company_id,
                    exclude_device_id=device.id,
                )

                device.device_key = device_key
                device.device_fingerprint = device_fingerprint
                device.name = data.name.strip()
                device.friendly_name = (
                    device.friendly_name or device.name
                )
                device.platform = (
                    data.platform.strip() or "android"
                )
                device.app_version = (
                    data.app_version.strip() or "1.0.0"
                )
                device.last_seen_at = now
                device.last_seen_platform = device.platform
                device.last_seen_app_version = device.app_version
                device.claimed_at = device.claimed_at or now
                device.activation_code_hash = None
                device.activation_code_expires_at = None
                device.pending_shop_id = device.shop_id
                device.pending_branch_id = device.branch_id
                device.status = "active"
                device.active = True
                await self.repo.flush(device)
                await self._clear_attempts(
                    data.company_id,
                    device_fingerprint,
                )
                claimed_device_id = device.id

            await self.repo.db.commit()
        except Exception:
            if self.repo.db.in_transaction():
                await self.repo.db.rollback()
            raise

        return await self.repo.get_view(
            data.company_id,
            claimed_device_id,
        )

    async def list_devices(self, company_id: UUID):
        return await self.repo.list_devices(company_id)

    async def heartbeat(
        self,
        data: DeviceHeartbeat,
    ):
        device = None

        if data.device_id is not None:
            device = await self.repo.get_by_id(
                data.company_id,
                data.device_id,
            )
        elif data.device_key:
            device = await self.repo.get_by_key(
                data.company_id,
                data.device_key.strip(),
            )

        if not device:
            raise HTTPException(404, "Device not found")

        if normalize_status(device) in {"deactivated", "removed"}:
            raise HTTPException(
                403,
                "Device access has been disabled",
            )

        device.last_seen_at = utcnow()
        if data.platform:
            device.last_seen_platform = data.platform.strip()
            device.platform = data.platform.strip()
        if data.app_version:
            device.last_seen_app_version = data.app_version.strip()
            device.app_version = data.app_version.strip()

        await self.repo.save(device)
        return await self.repo.get_view(
            data.company_id,
            device.id,
        )

    async def update(
        self,
        company_id: UUID,
        device_id: UUID,
        data: DeviceUpdate,
        actor=None,
    ):
        device = await self._get_device(company_id, device_id, for_update=True)

        if not device:
            raise HTTPException(404, "Device not found")

        if data.friendly_name is not None:
            cleaned = data.friendly_name.strip()
            if not cleaned:
                raise HTTPException(
                    400,
                    "Friendly name cannot be empty",
                )
            device.friendly_name = cleaned

        if "pos_number" in data.model_fields_set:
            device.pos_number = data.pos_number

        await self._ensure_pos_number_available(
            company_id,
            device.branch_id,
            device.pos_number,
            exclude_device_id=device.id,
        )

        # Retain direct-service compatibility for legacy tests and internal
        # callers. Authenticated API callers must use the audited lifecycle
        # endpoints, which require explicit client-state confirmations.
        if data.status is not None and actor is not None:
            raise HTTPException(
                400,
                "Use the terminal decommission lifecycle endpoint",
            )

        before_state = {
            "active": bool(device.active),
            "status": device.status,
            "deactivated_at": (
                str(device.deactivated_at) if device.deactivated_at else None
            ),
            "shop_id": str(device.shop_id) if device.shop_id else None,
        }
        if data.status == "deactivated":
            device.active = False
            device.status = "deactivated"
            device.deactivated_at = utcnow()
            device.deactivation_reason = self._clean_optional(
                data.deactivation_reason
            )
            if hasattr(self.repo.db, "add"):
                self.repo.db.add(AuditEvent(
                    company_id=company_id,
                    device_id=device.id,
                    action="terminal_archive",
                    reason=device.deactivation_reason,
                    details={
                        "record_id": str(device.id),
                        "shop_id": str(device.shop_id),
                        "before": before_state,
                        "after": {"active": False, "status": "deactivated"},
                    },
                ))
        elif data.status == "active":
            device.active = True
            device.status = "active"
            device.deactivated_at = None
            device.deactivation_reason = None
            device.removed_at = None
        elif data.status == "removed":
            device.active = False
            device.status = "removed"
            device.removed_at = utcnow()

        await self.repo.save(device)

        return await self.repo.get_view(company_id, device.id)

    @staticmethod
    def _require_client_state_confirmation(data):
        if not data.offline_queue_resolved or not data.active_checkout_closed:
            raise HTTPException(
                409,
                "Resolve the terminal's offline queue and close its active checkout before continuing",
            )

    @staticmethod
    def _actor_ids(actor):
        return (
            actor.user.id if actor and actor.actor_type == "user" else None,
            actor.employee.id if actor and actor.actor_type == "employee" else None,
        )

    async def reassign(
        self,
        company_id: UUID,
        device_id: UUID,
        data: DeviceAssignmentRequest,
        actor,
    ):
        self._require_client_state_confirmation(data)
        device = await self._get_device(company_id, device_id, for_update=True)
        if not device:
            raise HTTPException(404, "Device not found")
        if normalize_status(device) != "active":
            raise HTTPException(409, "Only an active terminal can be reassigned")
        if device.assignment_revision != data.expected_assignment_revision:
            raise HTTPException(409, "Terminal assignment changed; reload before retrying")

        _, branch = await self._validate_location(company_id, data.shop_id, data.branch_id)
        await self._ensure_pos_number_available(
            company_id, branch.id, data.pos_number, exclude_device_id=device.id
        )
        previous_shop_id = device.shop_id
        previous_branch_id = device.branch_id
        if branch.id == previous_branch_id and data.shop_id == previous_shop_id:
            raise HTTPException(409, "Select another branch for reassignment")

        now = utcnow()
        next_revision = device.assignment_revision + 1
        user_id, employee_id = self._actor_ids(actor)
        try:
            await self.repo.revoke_sessions(device.id, now, "terminal_reassigned")
            device.shop_id = data.shop_id
            device.branch_id = branch.id
            device.pending_shop_id = data.shop_id
            device.pending_branch_id = branch.id
            device.pos_number = data.pos_number
            device.assignment_revision = next_revision
            device.activation_code_hash = None
            device.activation_code_expires_at = None
            self.repo.db.add(AuditEvent(
                company_id=company_id,
                actor_employee_id=employee_id,
                actor_user_id=user_id,
                device_id=device.id,
                action="terminal_reassign",
                reason=data.reason.strip(),
                details={
                    "terminal_id": str(device.id),
                    "previous_shop_id": str(previous_shop_id),
                    "previous_branch_id": str(previous_branch_id),
                    "new_shop_id": str(device.shop_id),
                    "new_branch_id": str(device.branch_id),
                    "previous_assignment_revision": next_revision - 1,
                    "assignment_revision": next_revision,
                    "sessions_revoked": True,
                    "offline_queue_resolved": True,
                    "active_checkout_closed": True,
                    "effective_at": now.isoformat(),
                },
            ))
            await self.repo.save(device)
        except Exception:
            await self.repo.db.rollback()
            raise
        return await self.repo.get_view(company_id, device.id)

    async def decommission(
        self,
        company_id: UUID,
        device_id: UUID,
        data: DeviceDecommissionRequest,
        actor,
    ):
        self._require_client_state_confirmation(data)
        device = await self._get_device(company_id, device_id, for_update=True)
        if not device:
            raise HTTPException(404, "Device not found")
        if normalize_status(device) == "deactivated":
            return await self.repo.get_view(company_id, device.id)

        now = utcnow()
        user_id, employee_id = self._actor_ids(actor)
        try:
            await self.repo.revoke_sessions(device.id, now, "terminal_decommissioned")
            device.active = False
            device.status = "deactivated"
            device.deactivated_at = now
            device.deactivation_reason = data.reason.strip()
            device.activation_code_hash = None
            device.activation_code_expires_at = None
            device.assignment_revision += 1
            self.repo.db.add(AuditEvent(
                company_id=company_id,
                actor_employee_id=employee_id,
                actor_user_id=user_id,
                device_id=device.id,
                action="terminal_decommission",
                reason=device.deactivation_reason,
                details={
                    "terminal_id": str(device.id),
                    "shop_id": str(device.shop_id),
                    "branch_id": str(device.branch_id),
                    "assignment_revision": device.assignment_revision,
                    "sessions_revoked": True,
                    "offline_queue_resolved": True,
                    "active_checkout_closed": True,
                    "effective_at": now.isoformat(),
                },
            ))
            await self.repo.save(device)
        except Exception:
            await self.repo.db.rollback()
            raise
        return await self.repo.get_view(company_id, device.id)

    async def deletion_impact(self, company_id: UUID, device_id: UUID):
        device = await self.repo.get_by_id(company_id, device_id)
        if not device:
            tombstone = await self.repo.get_tombstone(company_id, device_id)
            if tombstone:
                return {
                    "device_id": device_id,
                    "terminal_name": tombstone.terminal_name,
                    "can_delete": True,
                    "dependencies": {"active_sessions": 0, "pending_activation_credential": False, "pending_offline_transactions": "client_only_unknown", "active_checkout_state": "client_only_unknown"},
                    "historical_sales": tombstone.historical_sales_count,
                    "policy": "already_deleted",
                }
            raise HTTPException(404, "Device not found")
        active_sessions, historical_sales = await self.repo.deletion_dependencies(device.id)
        return {
            "device_id": device.id,
            "terminal_name": device.friendly_name or device.name,
            "can_delete": active_sessions == 0,
            "dependencies": {
                "active_sessions": active_sessions,
                "pending_activation_credential": bool(device.activation_code_hash),
                "pending_offline_transactions": "client_only_unknown",
                "active_checkout_state": "client_only_unknown",
            },
            "historical_sales": historical_sales,
            "policy": "Unsynchronized client-only sales cannot be recovered after deletion; synchronize them before decommissioning. Historical server sales are preserved.",
        }

    @staticmethod
    def _verify_reauthentication(actor, secret: str):
        encoded = actor.user.password_hash if actor.actor_type == "user" else actor.employee.pin
        try:
            valid = verify_password(secret, encoded)
        except ValueError:
            valid = False
        if not valid:
            raise HTTPException(401, "Reauthentication failed")

    async def delete_permanently(self, company_id: UUID, device_id: UUID, data: DeviceDeleteRequest, actor):
        self._verify_reauthentication(actor, data.reauthentication_secret)
        self._require_client_state_confirmation(data)
        device = await self._get_device(company_id, device_id, for_update=True)
        if not device:
            tombstone = await self.repo.get_tombstone(company_id, device_id)
            if not tombstone:
                raise HTTPException(404, "Device not found")
            if not hmac.compare_digest(data.confirmation_name.strip(), tombstone.terminal_name):
                raise HTTPException(400, "Terminal name confirmation does not match exactly")
            return {"device_id": device_id, "deleted": True, "already_deleted": True, "deleted_at": tombstone.deleted_at}

        terminal_name = device.friendly_name or device.name
        if not hmac.compare_digest(data.confirmation_name.strip(), terminal_name):
            raise HTTPException(400, "Terminal name confirmation does not match exactly")
        active_sessions, historical_sales = await self.repo.deletion_dependencies(device.id)
        if active_sessions:
            raise HTTPException(409, f"Deletion blocked: {active_sessions} active POS session(s). Use Decommission first, then retry deletion.")

        now = utcnow()
        tombstone = DeviceTombstone(
            id=device.id,
            company_id=device.company_id,
            terminal_name=terminal_name,
            pos_number=device.pos_number,
            previous_shop_id=device.shop_id,
            previous_branch_id=device.branch_id,
            device_key_hash=hash_device_identity(device.device_key),
            fingerprint_hash=hash_device_identity(device.device_fingerprint) if device.device_fingerprint else None,
            actor_user_id=actor.user.id if actor.actor_type == "user" else None,
            actor_employee_id=actor.employee.id if actor.actor_type == "employee" else None,
            action="terminal_delete",
            reason=self._clean_optional(data.reason),
            assignment_revision=device.assignment_revision,
            historical_sales_count=historical_sales,
            deleted_at=now,
        )
        try:
            await self.repo.revoke_sessions(device.id, now, "terminal_deleted")
            if device.device_fingerprint:
                await self.repo.delete_activation_attempt(company_id, device.device_fingerprint)
            self.repo.db.add(tombstone)
            self.repo.db.add(AuditEvent(
                company_id=company_id,
                actor_employee_id=tombstone.actor_employee_id,
                actor_user_id=tombstone.actor_user_id,
                device_id=device.id,
                action="terminal_delete",
                reason=tombstone.reason,
                details={"terminal_id": str(device.id), "terminal_name": terminal_name, "previous_branch_id": str(device.branch_id), "timestamp": now.isoformat()},
            ))
            await self.repo.db.flush()
            await self.repo.delete_device_row(device.id)
            await self.repo.db.commit()
        except Exception:
            await self.repo.db.rollback()
            raise
        return {"device_id": device_id, "deleted": True, "already_deleted": False, "deleted_at": now}
