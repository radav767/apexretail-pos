import hmac
import hashlib
import json
import secrets
import uuid
from datetime import datetime, timezone, timedelta
from uuid import UUID

from fastapi import HTTPException

from app.auth.security import (
    create_employee_access_token,
    hash_password,
    verify_password,
    create_session_token,
    hash_session_token,
)
from app.employees.repository import EmployeeRepository
from app.employees.schema import (
    EmployeeCreate,
    EmployeeUpdate,
    PinLoginRequest,
)
from app.employees.permissions import PERMISSION_KEYS, ROLE_TEMPLATES, has_permission, normalize_permissions
from app.models import (
    AuditEvent,
    Device,
    Employee,
    EmployeeShopAccess,
    EmployeeDeviceAccess,
    EmployeeRole,
    ManagerAuthorization,
    PosSession,
    Shop,
)
from app.devices.authority import (
    TERMINAL_IDENTITY_REVOKED,
    hash_device_identity,
    terminal_authority_error,
)
from sqlalchemy import delete, select, text


class EmployeeService:
    def __init__(
        self,
        repo: EmployeeRepository,
    ):
        self.repo = repo

    @staticmethod
    def clean_optional(
        value: str | None,
    ):
        if value is None:
            return None

        cleaned = value.strip()

        return cleaned or None

    @staticmethod
    def build_permissions(
        role: str,
        supplied: dict[str, bool] | None,
    ):
        supplied = dict(supplied or {})
        if "inventory" in supplied and "manage_inventory" not in supplied:
            supplied["manage_inventory"] = supplied["inventory"]
        if "products" in supplied and "manage_products" not in supplied:
            supplied["manage_products"] = supplied["products"]
        return normalize_permissions(role, supplied)

    @staticmethod
    async def effective_permissions(employee: Employee, db) -> dict[str, bool]:
        if not getattr(employee, "role_id", None):
            return EmployeeService.build_permissions(employee.role, employee.permissions)
        role = (await db.execute(select(EmployeeRole).where(
            EmployeeRole.id == employee.role_id,
            EmployeeRole.company_id == employee.company_id,
            EmployeeRole.active == True,
            EmployeeRole.deleted == False,
        ))).scalar_one_or_none()
        if role is None:
            return normalize_permissions("denied", {})
        return normalize_permissions("denied", {
            **role.permissions, **(employee.role_overrides or {}),
        })

    @staticmethod
    def custom_overrides(role_permissions: dict, supplied: dict | None) -> dict:
        supplied = supplied or {}
        return {key: bool(value) for key, value in supplied.items()
                if key in PERMISSION_KEYS and bool(value) != bool(role_permissions.get(key))}

    @staticmethod
    def ensure_grantable(actor, role: str, permissions: dict[str, bool]):
        if actor is None or (actor.actor_type == "user" and actor.role in {"owner", "administrator"}):
            return
        if role in {"owner", "administrator"}:
            raise HTTPException(403, "Only a business owner may assign this role")
        for key, value in permissions.items():
            if value and not has_permission(actor.permissions, key):
                raise HTTPException(403, f"Cannot grant permission: {key}")

    @staticmethod
    def ensure_branch_access(actor, branch_id):
        if actor is not None and actor.actor_type == "employee" and actor.role not in {"owner", "administrator"}:
            if actor.employee is None or actor.employee.branch_id != branch_id:
                raise HTTPException(403, "Branch access denied")

    def normalize_employee_view(
        self,
        row,
    ):
        if not row:
            return row

        return {
            **row,
            "role_name": row.get("role_name") or row["role"],
            "device_ids": row.get("device_ids") or [],
            "permissions": self.build_permissions(
                row["role"],
                row["permissions"],
            ),
        }

    @staticmethod
    def verify_pin_value(
        entered_pin: str,
        stored_pin: str,
    ):
        if stored_pin.startswith("$2"):
            try:
                return verify_password(
                    entered_pin,
                    stored_pin,
                )
            except ValueError:
                return False

        return hmac.compare_digest(
            entered_pin,
            stored_pin,
        )

    async def ensure_unique_pin(
        self,
        company_id: UUID,
        pin: str,
        excluding_employee_id: UUID | None = None,
    ):
        employees = await self.repo.active_pin_candidates(
            company_id,
        )

        for employee in employees:
            if (
                excluding_employee_id is not None
                and employee.id == excluding_employee_id
            ):
                continue

            if self.verify_pin_value(
                pin,
                employee.pin,
            ):
                raise HTTPException(
                    409,
                    "This PIN is already used by another employee",
                )

    async def validate_location(
        self,
        company_id: UUID,
        shop_id: UUID,
        branch_id: UUID,
    ):
        location = await self.repo.get_location(
            company_id,
            shop_id,
            branch_id,
        )

        if not location:
            raise HTTPException(
                400,
                "The selected branch does not belong to the selected shop",
            )

    async def create(
        self,
        data: EmployeeCreate,
        actor=None,
    ):
        if hasattr(self.repo, 'authorize_actor'):
            await self.repo.authorize_actor(data.company_id, actor)
            from app.subscriptions.write_policy import require_new_write
            await require_new_write(self.repo.db, data.company_id)
        if hasattr(self.repo,'db'):
            from app.subscriptions.commercial import enforce_capacity
            await enforce_capacity(self.repo.db,data.company_id,'employee')
        self.ensure_branch_access(actor, data.branch_id)
        await self.validate_location(
            data.company_id,
            data.shop_id,
            data.branch_id,
        )

        await self.ensure_unique_pin(
            data.company_id,
            data.pin,
        )

        if data.role not in ROLE_TEMPLATES and data.role != "manager" and not data.role_id:
            raise HTTPException(400, "Unknown employee role")
        role_permissions = data.permissions
        role_name = data.role
        role_overrides = {}
        if data.role_id:
            custom_role = await self.repo.get_role(data.company_id, data.role_id)
            if custom_role is None:
                raise HTTPException(400, "The selected role is unavailable")
            role_name = custom_role.name
            role_overrides = self.custom_overrides(custom_role.permissions, data.permissions)
            role_permissions = {**custom_role.permissions, **role_overrides}
        normalized_permissions = self.build_permissions(
            "kitchen_staff" if data.role_id else role_name, role_permissions
        )
        self.ensure_grantable(actor, role_name, normalized_permissions)
        devices = await self.repo.validate_devices(data.company_id, data.device_ids)
        if devices is None:
            raise HTTPException(400, "One or more selected devices are unavailable")

        employee = Employee(
            company_id=data.company_id,
            shop_id=data.shop_id,
            branch_id=data.branch_id,
            name=data.name.strip(),
            email=self.clean_optional(data.email),
            phone=self.clean_optional(data.phone),
            pin=hash_password(data.pin),
            role="custom" if data.role_id else role_name,
            role_id=data.role_id,
            role_overrides=role_overrides,
            device_restricted=data.device_restricted,
            permissions=normalized_permissions,
            active=True,
            deleted=False,
        )

        try:
            self.repo.db.add(employee)
            await self.repo.db.flush()
            await self.repo.set_devices(employee, devices)
            self.repo.db.add(AuditEvent(
                company_id=data.company_id,
                actor_employee_id=actor.employee.id if actor and actor.actor_type == "employee" else None,
                actor_user_id=actor.user.id if actor and actor.actor_type == "user" else None,
                action="employee_created",
                details={"employee_id": str(employee.id), "role": role_name},
            ))
            await self.repo.db.commit()
            await self.repo.db.refresh(employee)
        except Exception:
            await self.repo.db.rollback()
            raise

        row = dict(await self.repo.get_view(data.company_id, employee.id))
        row["device_ids"] = await self.repo.device_ids(employee.id)
        return self.normalize_employee_view(row)

    async def list_employees(
        self,
        company_id: UUID,
        actor=None,
    ):
        rows = await self.repo.list_employees(
            company_id,
        )
        result = []
        for row in rows:
            if actor and actor.actor_type == "employee" and actor.role not in {"owner", "administrator"} and row["branch_id"] != actor.employee.branch_id:
                continue
            view = dict(row)
            view["device_ids"] = await self.repo.device_ids(row["id"])
            result.append(self.normalize_employee_view(view))
        return result

    async def update(
        self,
        company_id: UUID,
        employee_id: UUID,
        data: EmployeeUpdate,
        actor=None,
    ):
        if hasattr(self.repo, 'authorize_actor'):
            await self.repo.authorize_actor(company_id, actor)
        employee = await self.repo.get_employee(
            company_id,
            employee_id,
        )

        if not employee:
            raise HTTPException(
                404,
                "Employee not found",
            )

        security_before = None
        if hasattr(self.repo, 'authorize_actor'):
            old_permissions = await self.effective_permissions(employee, self.repo.db)
            old_devices = set(await self.repo.device_ids(employee.id))
            security_before = (employee.pin, employee.shop_id, employee.branch_id, employee.role, employee.role_id,
                               dict(employee.permissions or {}), dict(employee.role_overrides or {}), employee.active,
                               employee.device_restricted, old_devices)
            fields = {key for key,value in data.model_dump(exclude_unset=True).items() if value is not None}
            security_only = bool(fields) and fields <= {'pin','permissions','active','device_restricted','device_ids'}
            preview = old_permissions
            if data.permissions is not None:
                if employee.role_id:
                    custom = await self.repo.get_role(company_id, employee.role_id)
                    if custom is None: raise HTTPException(400, 'The selected role is unavailable')
                    preview = self.build_permissions('kitchen_staff', {**custom.permissions, **self.custom_overrides(custom.permissions, data.permissions)})
                else: preview = self.build_permissions(employee.role, data.permissions)
            adds_rights = any(enabled and not has_permission(old_permissions,key) for key,enabled in preview.items())
            new_restricted = employee.device_restricted if data.device_restricted is None else data.device_restricted
            device_reduction = (data.device_ids is None or new_restricted and
                (not employee.device_restricted or set(data.device_ids) <= old_devices))
            security_only = (security_only and not adds_rights and device_reduction and
                not (data.active is True and not employee.active) and
                not (employee.device_restricted and not new_restricted))
            if not security_only:
                from app.subscriptions.write_policy import require_new_write
                await require_new_write(self.repo.db, company_id)

        if data.active is True and not employee.active and hasattr(self.repo,'db'):
            from app.subscriptions.commercial import enforce_capacity
            await enforce_capacity(self.repo.db,company_id,'employee',employee.id)

        before = {
            "name": employee.name,
            "role": employee.role,
            "role_id": str(employee.role_id) if employee.role_id else None,
            "branch_id": str(employee.branch_id),
            "active": employee.active,
        }
        self.ensure_branch_access(actor, employee.branch_id)

        shop_id = data.shop_id or employee.shop_id
        branch_id = data.branch_id or employee.branch_id
        self.ensure_branch_access(actor, branch_id)

        await self.validate_location(
            company_id,
            shop_id,
            branch_id,
        )

        if data.pin is not None:
            await self.ensure_unique_pin(
                company_id,
                data.pin,
                employee.id,
            )

            employee.pin = hash_password(
                data.pin,
            )

        if data.name is not None:
            employee.name = data.name.strip()

        if data.email is not None:
            employee.email = self.clean_optional(
                data.email,
            )

        if data.phone is not None:
            employee.phone = self.clean_optional(
                data.phone,
            )

        employee.shop_id = shop_id
        employee.branch_id = branch_id

        role_changed = (
            data.role is not None
            and data.role != employee.role
        )

        if data.role_id is not None:
            custom_role = await self.repo.get_role(company_id, data.role_id)
            if custom_role is None:
                raise HTTPException(400, "The selected role is unavailable")
            employee.role_id = custom_role.id
            employee.role = "custom"
            employee.role_overrides = self.custom_overrides(custom_role.permissions, data.permissions)
            employee.permissions = self.build_permissions("kitchen_staff", {**custom_role.permissions, **employee.role_overrides})
            role_changed = True
        elif data.role is not None:
            if data.role not in ROLE_TEMPLATES and data.role != "manager":
                raise HTTPException(400, "Unknown employee role")
            employee.role_id = None
            employee.role_overrides = {}
            employee.role = data.role

        if data.role_id is None and employee.role_id is not None and data.permissions is not None:
            custom_role = await self.repo.get_role(company_id, employee.role_id)
            if custom_role is None:
                raise HTTPException(400, "The selected role is unavailable")
            employee.role_overrides = self.custom_overrides(custom_role.permissions, data.permissions)
            employee.permissions = self.build_permissions("kitchen_staff", {**custom_role.permissions, **employee.role_overrides})
        elif data.role_id is None and (
            data.permissions is not None
            or role_changed
        ):
            employee.permissions = self.build_permissions(
                employee.role,
                data.permissions,
            )
        self.ensure_grantable(actor, employee.role, employee.permissions)

        if data.active is not None:
            employee.active = data.active

        if data.device_restricted is not None:
            employee.device_restricted = data.device_restricted
        if data.device_ids is not None:
            devices = await self.repo.validate_devices(company_id, data.device_ids)
            if devices is None:
                raise HTTPException(400, "One or more selected devices are unavailable")
            await self.repo.set_devices(employee, devices)

        sessions_revoked = False
        if security_before is not None:
            security_after = (employee.pin, employee.shop_id, employee.branch_id, employee.role, employee.role_id,
                              dict(employee.permissions or {}), dict(employee.role_overrides or {}), employee.active,
                              employee.device_restricted, set(await self.repo.device_ids(employee.id)))
            sessions_revoked = security_after != security_before
            if sessions_revoked: await self.repo.revoke_sessions(employee, 'employee_security_changed')

        self.repo.db.add(AuditEvent(
            company_id=company_id,
            actor_employee_id=actor.employee.id if actor and actor.actor_type == "employee" else None,
            actor_user_id=actor.user.id if actor and actor.actor_type == "user" else None,
            action="employee_deactivated" if data.active is False else "employee_updated",
            details={"employee_id": str(employee.id), "before": before, "pin_changed": data.pin is not None, "sessions_revoked": sessions_revoked},
        ))

        await self.repo.save(employee)

        row = dict(await self.repo.get_view(company_id, employee.id))
        row["device_ids"] = await self.repo.device_ids(employee.id)
        return self.normalize_employee_view(row)

    async def delete(
        self,
        company_id: UUID,
        employee_id: UUID,
        actor=None,
    ):
        if hasattr(self.repo, 'authorize_actor'):
            await self.repo.authorize_actor(company_id, actor)
        employee = await self.repo.get_employee(
            company_id,
            employee_id,
        )

        if not employee:
            raise HTTPException(
                404,
                "Employee not found",
            )

        if employee.role == "owner":
            raise HTTPException(
                400,
                "The owner employee cannot be deleted",
            )

        self.ensure_branch_access(actor, employee.branch_id)
        self.ensure_grantable(actor, employee.role, employee.permissions)

        self.repo.db.add(AuditEvent(
            company_id=company_id,
            actor_employee_id=actor.employee.id if actor and actor.actor_type == "employee" else None,
            actor_user_id=actor.user.id if actor and actor.actor_type == "user" else None,
            action="employee_deactivated",
            details={"employee_id": str(employee.id), "name": employee.name},
        ))
        if hasattr(self.repo, 'revoke_sessions'):
            await self.repo.revoke_sessions(employee, 'employee_deleted')
        await self.repo.soft_delete(employee)

        return {
            "ok": True,
            "message": "Employee deleted",
        }

    async def pin_login(
        self,
        data: PinLoginRequest,
    ):
        deleted_identity_checker = getattr(
            self.repo,
            "is_deleted_device_identity",
            None,
        )
        if deleted_identity_checker is not None:
            deleted_identity = await deleted_identity_checker(
                data.company_id,
                device_id=data.device_id,
                device_key_hash=(
                    hash_device_identity(data.device_key.strip())
                    if data.device_key
                    else None
                ),
            )
            if deleted_identity:
                raise terminal_authority_error(
                    403,
                    TERMINAL_IDENTITY_REVOKED,
                    "This terminal identity was permanently deleted",
                )

        employees = await self.repo.active_pin_candidates(data.company_id, data.branch_id)

        for employee in employees:
            if self.verify_pin_value(
                data.pin,
                employee.pin,
            ):
                if data.takeover and (data.device_id is None or not data.device_key):
                    raise HTTPException(
                        400,
                        "Explicit takeover requires a terminal and device identity",
                    )
                if data.takeover:
                    # Serialize identity transfers for this tenant before taking
                    # row locks. This prevents concurrent swaps/replays from
                    # committing conflicting terminal keys or sessions.
                    await self.repo.db.execute(
                        text(
                            "SELECT pg_advisory_xact_lock("
                            "hashtextextended(:company_id, 0))"
                        ),
                        {"company_id": str(data.company_id)},
                    )
                    # The device key is globally unique, so serialize its
                    # ownership independently of the tenant lock. Concurrent
                    # cross-tenant claims then observe the committed owner and
                    # return a controlled conflict instead of a uniqueness
                    # failure at commit time.
                    await self.repo.db.execute(
                        text(
                            "SELECT pg_advisory_xact_lock("
                            "hashtextextended(:device_key, 1))"
                        ),
                        {"device_key": data.device_key.strip()},
                    )
                permissions = await self.effective_permissions(employee, self.repo.db)
                shop_id = data.shop_id or employee.shop_id
                if employee.role == "owner":
                    shops = (await self.repo.db.execute(select(Shop.id).where(Shop.company_id == data.company_id, Shop.active == True, Shop.deleted == False))).scalars().all()
                else:
                    shops = (await self.repo.db.execute(select(EmployeeShopAccess.shop_id).where(EmployeeShopAccess.employee_id == employee.id))).scalars().all() or [employee.shop_id]
                if shop_id not in shops:
                    raise HTTPException(403, "Employee is not authorised for this shop")
                shop_rows = (await self.repo.db.execute(select(Shop).where(Shop.id.in_(shops), Shop.company_id == data.company_id, Shop.active == True, Shop.deleted == False).order_by(Shop.name.asc()))).scalars().all()
                terminal_rows = (await self.repo.db.execute(select(Device).where(Device.company_id == data.company_id, Device.shop_id.in_(shops), Device.active == True, Device.deleted == False, Device.removed_at.is_(None), Device.deactivated_at.is_(None)).order_by(Device.shop_id, Device.pos_number.asc().nullslast()))).scalars().all()
                if getattr(employee, "device_restricted", False):
                    allowed_device_ids = set(await self.repo.device_ids(employee.id))
                    terminal_rows = [row for row in terminal_rows if row.id in allowed_device_ids]
                if employee.role not in {"owner", "administrator"}:
                    terminal_rows = [row for row in terminal_rows if row.branch_id == employee.branch_id]
                if data.shop_id is None and data.device_id is None:
                    return {"id": employee.id, "company_id": employee.company_id, "shop_id": None, "branch_id": None, "name": employee.name, "role": employee.role, "permissions": permissions, "access_token": "", "selection_required": True, "shops": [{"id": str(s.id), "name": s.name} for s in shop_rows], "terminals": [{"id": str(d.id), "shop_id": str(d.shop_id), "branch_id": str(d.branch_id), "name": d.friendly_name or d.name, "pos_number": d.pos_number} for d in terminal_rows]}
                q = select(Device).where(Device.company_id == data.company_id, Device.shop_id == shop_id, Device.active == True, Device.deleted == False, Device.removed_at.is_(None), Device.deactivated_at.is_(None))
                if data.device_id:
                    q = q.where(Device.id == data.device_id)
                device = (await self.repo.db.execute(q.order_by(Device.pos_number.asc().nullslast()).with_for_update())).scalars().first()
                if not device:
                    raise HTTPException(409, "No active POS terminal is available for this shop")
                if employee.role not in {"owner", "administrator"} and device.branch_id != employee.branch_id:
                    raise HTTPException(403, "Employee is not authorized for this branch")
                if getattr(employee, "device_restricted", False) and not await self.repo.device_allowed(employee.id, device.id):
                    raise HTTPException(403, "This employee is not authorized for this POS device")
                now = datetime.now(timezone.utc)
                existing = (await self.repo.db.execute(select(PosSession).where(PosSession.employee_id == employee.id, PosSession.session_version == employee.session_version, PosSession.revoked_at.is_(None), PosSession.expires_at > now).with_for_update())).scalars().first()
                terminal_existing = (await self.repo.db.execute(select(PosSession).join(Employee, Employee.id == PosSession.employee_id).where(PosSession.device_id == device.id, PosSession.session_version == Employee.session_version, PosSession.revoked_at.is_(None), PosSession.expires_at > now).with_for_update(of=PosSession))).scalars().first()
                same_device_identity = bool(
                    data.device_key
                    and hmac.compare_digest(
                        data.device_key.strip(),
                        str(device.device_key),
                    )
                )
                resumable = None
                if (
                    existing
                    and existing.device_id == device.id
                    and same_device_identity
                ):
                    resumable = existing
                elif not existing and same_device_identity:
                    resumable = (
                        await self.repo.db.execute(
                            select(PosSession)
                            .where(
                                PosSession.employee_id == employee.id,
                                PosSession.session_version == employee.session_version,
                                PosSession.device_id == device.id,
                                PosSession.revoked_at.is_(None),
                            )
                            .order_by(PosSession.created_at.desc())
                            .with_for_update()
                        )
                    ).scalars().first()

                if resumable is not None:
                    supplied_token = (data.session_token or "").strip()
                    token_matches = bool(
                        supplied_token
                        and hmac.compare_digest(
                            hash_session_token(supplied_token),
                            resumable.token_hash,
                        )
                    )
                    token = supplied_token if token_matches else create_session_token()
                    if not token_matches:
                        resumable.token_hash = hash_session_token(token)
                    resumable.expires_at = now + timedelta(hours=12)
                    resumable.last_authenticated_at = now
                    self.repo.db.add(AuditEvent(
                        company_id=data.company_id, actor_employee_id=employee.id,
                        device_id=device.id, action="employee_login",
                        details={"resumed": True},
                    ))
                    response = {
                        "id": employee.id,
                        "company_id": employee.company_id,
                        "shop_id": device.shop_id,
                        "branch_id": device.branch_id,
                        "name": employee.name,
                        "role": employee.role,
                        "permissions": permissions,
                        "access_token": token,
                        "device_id": device.id,
                        "device_key": device.device_key,
                        "assignment_revision": getattr(device, "assignment_revision", 1),
                    }
                    await self.repo.db.commit()
                    return response
                if existing and not data.takeover:
                    raise HTTPException(409, "You are already signed in on another device. Choose Cancel or Take over this session.")
                if terminal_existing and terminal_existing.id != (existing.id if existing else None) and not data.takeover:
                    raise HTTPException(409, "This POS terminal is already in use. Choose another terminal or take over the session.")
                previous_device_key = str(device.device_key)
                prior_key_owner = None
                source_terminal_existing = None
                if data.takeover:
                    requested_device_key = data.device_key.strip()
                    prior_key_owner = (
                        await self.repo.db.execute(
                            select(Device)
                            .where(
                                Device.device_key == requested_device_key,
                                Device.deleted == False,
                            )
                            .with_for_update()
                        )
                    ).scalars().first()
                    if (
                        prior_key_owner
                        and prior_key_owner.company_id != data.company_id
                    ):
                        raise HTTPException(
                            409,
                            "This device identity belongs to another company",
                        )
                    if prior_key_owner and prior_key_owner.id != device.id:
                        source_terminal_existing = (
                            await self.repo.db.execute(
                                select(PosSession).join(Employee, Employee.id == PosSession.employee_id).where(
                                    PosSession.session_version == Employee.session_version,
                                    PosSession.device_id == prior_key_owner.id,
                                    PosSession.revoked_at.is_(None),
                                    PosSession.expires_at > now,
                                ).with_for_update(of=PosSession)
                            )
                        ).scalars().first()
                        prior_key_owner.device_key = f"released-{uuid.uuid4()}"
                        await self.repo.db.flush()
                    device.device_key = requested_device_key
                if existing:
                    existing.revoked_at = now; existing.revoke_reason = "takeover"
                    self.repo.db.add(AuditEvent(company_id=data.company_id, actor_employee_id=employee.id, device_id=device.id, action="session_takeover", details={"old_device_id": str(existing.device_id), "new_device_id": str(device.id)}))
                if terminal_existing and terminal_existing.id != (existing.id if existing else None):
                    terminal_existing.revoked_at = now; terminal_existing.revoke_reason = "terminal_takeover"
                    self.repo.db.add(AuditEvent(company_id=data.company_id, actor_employee_id=employee.id, device_id=device.id, action="session_takeover", details={"old_device_id": str(device.id), "old_employee_id": str(terminal_existing.employee_id), "reason": "terminal_takeover"}))
                if (
                    source_terminal_existing
                    and source_terminal_existing.id
                    not in {
                        existing.id if existing else None,
                        terminal_existing.id if terminal_existing else None,
                    }
                ):
                    source_terminal_existing.revoked_at = now
                    source_terminal_existing.revoke_reason = "device_identity_transfer"
                    self.repo.db.add(AuditEvent(
                        company_id=data.company_id,
                        actor_employee_id=employee.id,
                        device_id=prior_key_owner.id,
                        action="session_takeover",
                        details={
                            "old_device_id": str(prior_key_owner.id),
                            "old_employee_id": str(source_terminal_existing.employee_id),
                            "reason": "device_identity_transfer",
                        },
                    ))
                if data.takeover and not hmac.compare_digest(
                    previous_device_key,
                    str(device.device_key),
                ):
                    self.repo.db.add(AuditEvent(
                        company_id=data.company_id,
                        actor_employee_id=employee.id,
                        device_id=device.id,
                        action="device_identity_transfer",
                        details={
                            "source_device_id": (
                                str(prior_key_owner.id)
                                if prior_key_owner
                                and prior_key_owner.id != device.id
                                else None
                            ),
                            "terminal_id": str(device.id),
                        },
                    ))
                token = create_session_token()
                self.repo.db.add(PosSession(id=uuid.uuid4(), session_version=employee.session_version, company_id=data.company_id, employee_id=employee.id, device_id=device.id, shop_id=device.shop_id, branch_id=device.branch_id, token_hash=hash_session_token(token), expires_at=now + timedelta(hours=12), last_authenticated_at=now))
                self.repo.db.add(AuditEvent(
                    company_id=data.company_id, actor_employee_id=employee.id,
                    device_id=device.id, action="employee_login",
                    details={"resumed": False},
                ))
                response = {
                    "id": employee.id,
                    "company_id": employee.company_id,
                    "shop_id": device.shop_id,
                    "branch_id": device.branch_id,
                    "name": employee.name,
                    "role": employee.role,
                    "permissions": permissions,
                    "access_token": token,
                    "device_id": device.id,
                    "device_key": device.device_key,
                    "assignment_revision": getattr(device, "assignment_revision", 1),
                }
                try:
                    await self.repo.db.commit()
                except Exception:
                    await self.repo.db.rollback()
                    raise
                return response

        raise HTTPException(
            401,
            "Invalid employee PIN",
        )
