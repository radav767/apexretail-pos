from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import hashlib
import hmac
from secrets import token_urlsafe
from urllib.parse import urlencode
from uuid import UUID

import httpx
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.security import create_entitlement_snapshot_token
from app.models.company import Company
from app.models.company_subscription import CompanySubscription
from app.models.company_subscription_history import CompanySubscriptionHistory
from app.models.device import Device
from app.models.subscription_checkout_session import SubscriptionCheckoutSession
from app.models.subscription_webhook_event import SubscriptionWebhookEvent
from app.subscriptions.paynow import (
    PAYNOW_INITIATE_URL,
    PaynowCredentials,
    PaynowError,
    build_hash,
    fields_from_pairs,
    normalize_payment_status,
    parse_form_body,
    parse_initiation_response,
    quantize_amount,
    validate_hash,
)


UTC = timezone.utc
TRIAL_DAYS = 30
PAYNOW_TIMEOUT_SECONDS = 15
SUBSCRIPTION_STATUSES = {
    "trial",
    "active",
    "grace_period",
    "expired",
    "suspended",
    "cancelled",
    "canceled",
}
WRITE_ALLOWED_STATUSES = {"trial", "active", "grace_period"}
PLAN_DURATIONS = {
    "monthly": timedelta(days=30),
    "yearly": timedelta(days=365),
}
PLAN_PRICING = {
    "monthly": Decimal("8.00"),
    "yearly": Decimal("96.00"),
}
PAYNOW_SUCCESS_STATUSES = {"paid"}


@dataclass
class SubscriptionPolicy:
    offline_grace_hours: int
    provider_name: str | None
    checkout_base_url: str | None
    webhook_secret: str | None
    webhook_signature_header: str
    paynow_integration_id: str | None
    paynow_integration_key: str | None
    paynow_return_url: str | None
    paynow_result_url: str | None

    @property
    def normalized_provider_name(self) -> str | None:
        provider_name = str(self.provider_name or "").strip().lower()
        return provider_name or None

    @property
    def paynow_credentials(self) -> PaynowCredentials:
        return PaynowCredentials(
            integration_id=str(self.paynow_integration_id or "").strip(),
            integration_key=str(self.paynow_integration_key or "").strip(),
            return_url=str(self.paynow_return_url or "").strip(),
            result_url=str(self.paynow_result_url or "").strip(),
        )

    @property
    def activation_available(self) -> bool:
        if self.normalized_provider_name == "paynow":
            return self.paynow_credentials.configured
        return bool(
            self.normalized_provider_name
            and self.checkout_base_url
        )


class SubscriptionService:
    def __init__(
        self,
        db: AsyncSession,
        *,
        offline_grace_hours: int = 72,
        provider_name: str | None = None,
        checkout_base_url: str | None = None,
        webhook_secret: str | None = None,
        webhook_signature_header: str = "x-apex-signature",
        paynow_integration_id: str | None = None,
        paynow_integration_key: str | None = None,
        paynow_return_url: str | None = None,
        paynow_result_url: str | None = None,
    ):
        self.db = db
        self.policy = SubscriptionPolicy(
            offline_grace_hours=offline_grace_hours,
            provider_name=provider_name,
            checkout_base_url=checkout_base_url,
            webhook_secret=webhook_secret,
            webhook_signature_header=webhook_signature_header,
            paynow_integration_id=paynow_integration_id,
            paynow_integration_key=paynow_integration_key,
            paynow_return_url=paynow_return_url,
            paynow_result_url=paynow_result_url,
        )

    def provider_name(self) -> str | None:
        return self.policy.normalized_provider_name

    def display_status(self, subscription: CompanySubscription) -> str:
        status = str(subscription.status or "").strip().lower()
        if status == "grace_period":
            return "past_due"
        if status in {"suspended", "cancelled", "canceled"}:
            return "cancelled"
        if status in {"trial", "active", "expired"}:
            return status
        return "expired"

    def display_status_label(self, subscription: CompanySubscription) -> str:
        labels = {
            "trial": "Trial",
            "active": "Active",
            "past_due": "Past due",
            "expired": "Expired",
            "cancelled": "Cancelled",
        }
        return labels[self.display_status(subscription)]

    def plan_label(self, plan: str | None) -> str:
        labels = {
            "monthly": "Monthly",
            "yearly": "Yearly",
        }
        return labels.get(str(plan or "").strip().lower(), "Not set")

    def trial_days_remaining(
        self,
        subscription: CompanySubscription,
    ) -> int | None:
        if subscription.trial_ends_at is None:
            return None
        remaining_seconds = (
            subscription.trial_ends_at - datetime.now(UTC)
        ).total_seconds()
        if remaining_seconds <= 0:
            return 0
        return int((remaining_seconds + 86399) // 86400)

    def subscription_started_at(
        self,
        subscription: CompanySubscription,
    ) -> datetime | None:
        return (
            subscription.current_period_started_at
            or subscription.trial_started_at
        )

    def renewal_or_expiry_at(
        self,
        subscription: CompanySubscription,
    ) -> datetime | None:
        display_status = self.display_status(subscription)
        if display_status == "trial":
            return subscription.trial_ends_at
        if display_status == "past_due":
            return subscription.grace_ends_at
        if display_status in {"expired", "cancelled"}:
            return (
                subscription.current_period_ends_at
                or subscription.trial_ends_at
            )
        return subscription.current_period_ends_at

    def payment_configuration_required(self) -> list[str]:
        provider_name = self.provider_name()
        if not provider_name:
            return [
                "Set SUBSCRIPTION_PROVIDER_NAME=paynow to enable hosted subscription checkout.",
                "Set PAYNOW_INTEGRATION_ID with the Paynow integration ID.",
                "Set PAYNOW_INTEGRATION_KEY with the Paynow integration key.",
                "Set PAYNOW_RETURN_URL to the Backoffice return URL.",
                "Set PAYNOW_RESULT_URL to the API callback URL.",
            ]

        if provider_name == "paynow":
            requirements: list[str] = []
            credentials = self.policy.paynow_credentials
            if not credentials.integration_id:
                requirements.append(
                    "Set PAYNOW_INTEGRATION_ID with the Paynow integration ID."
                )
            if not credentials.integration_key:
                requirements.append(
                    "Set PAYNOW_INTEGRATION_KEY with the Paynow integration key."
                )
            if not credentials.return_url:
                requirements.append(
                    "Set PAYNOW_RETURN_URL to the Backoffice return URL."
                )
            if not credentials.result_url:
                requirements.append(
                    "Set PAYNOW_RESULT_URL to the API callback URL."
                )
            return requirements

        requirements: list[str] = []
        if not self.policy.checkout_base_url:
            requirements.append(
                "Set SUBSCRIPTION_PROVIDER_CHECKOUT_BASE_URL for the selected payment provider."
            )
        if not self.policy.webhook_secret:
            requirements.append(
                "Set SUBSCRIPTION_PROVIDER_WEBHOOK_SECRET and connect the provider webhook to /api/subscriptions/webhooks."
            )
        return requirements

    def payment_configuration_message(self) -> str:
        requirements = self.payment_configuration_required()
        if not requirements:
            if self.provider_name() == "paynow":
                return "Paynow checkout is ready. Access will change only after a verified Paynow payment result is received."
            return "Subscription checkout is ready. Access will change only after the payment provider confirms the payment."
        return "Real payment activation is not fully configured yet. " + " ".join(
            requirements
        )

    async def get_company(self, company_id: UUID) -> Company:
        result = await self.db.execute(
            select(Company).where(Company.id == company_id)
        )
        company = result.scalar_one_or_none()
        if company is None:
            raise HTTPException(404, "Company not found")
        return company

    async def get_or_create_trial(
        self,
        company_id: UUID,
        *,
        commit: bool = True,
    ) -> CompanySubscription:
        existing = await self.get_current(company_id)
        if existing is not None:
            return self.apply_status_windows(existing)

        now = datetime.now(UTC)
        trial_ends_at = now + timedelta(days=TRIAL_DAYS)
        subscription = CompanySubscription(
            company_id=company_id,
            plan=None,
            status="trial",
            trial_started_at=now,
            trial_ends_at=trial_ends_at,
            grace_ends_at=trial_ends_at
            + timedelta(hours=self.policy.offline_grace_hours),
            provider=None,
            provider_reference=None,
            billing_currency="USD",
            licensed_terminal_count=None,
            unit_price=None,
            total_amount=None,
            status_reason="Initial 30-day free trial",
        )
        self.db.add(subscription)
        await self.db.flush()
        self.db.add(
            CompanySubscriptionHistory(
                company_subscription_id=subscription.id,
                company_id=company_id,
                action="trial_started",
                plan=None,
                status="trial",
                provider=None,
                provider_reference=None,
                payload=None,
                note="Free trial created by server",
            )
        )
        if commit:
            await self.db.commit()
            await self.db.refresh(subscription)
        return self.apply_status_windows(subscription)

    async def get_current(
        self,
        company_id: UUID,
    ) -> CompanySubscription | None:
        result = await self.db.execute(
            select(CompanySubscription).where(
                CompanySubscription.company_id == company_id
            )
        )
        subscription = result.scalar_one_or_none()
        if subscription is None:
            return None
        return self.apply_status_windows(subscription)

    async def ensure_current(
        self,
        company_id: UUID,
    ) -> CompanySubscription:
        await self.get_company(company_id)
        return await self.get_or_create_trial(company_id)

    def apply_status_windows(
        self,
        subscription: CompanySubscription,
    ) -> CompanySubscription:
        now = datetime.now(UTC)
        effective_until = self.effective_until(subscription)
        if (
            subscription.status == "trial"
            and subscription.trial_ends_at
            and now > subscription.trial_ends_at
        ):
            subscription.status = (
                "grace_period"
                if subscription.grace_ends_at
                and now <= subscription.grace_ends_at
                else "expired"
            )
        elif (
            subscription.status == "active"
            and effective_until
            and now > effective_until
        ):
            subscription.status = (
                "grace_period"
                if subscription.grace_ends_at
                and now <= subscription.grace_ends_at
                else "expired"
            )
        elif (
            subscription.status == "grace_period"
            and subscription.grace_ends_at
            and now > subscription.grace_ends_at
        ):
            subscription.status = "expired"
        return subscription

    def effective_until(
        self,
        subscription: CompanySubscription,
    ) -> datetime | None:
        if subscription.status == "trial":
            return subscription.trial_ends_at
        return subscription.current_period_ends_at

    def snapshot_for(
        self,
        subscription: CompanySubscription,
    ) -> dict:
        # JWT NumericDate claims have whole-second precision. Derive every
        # entitlement boundary from that same aligned instant so the ISO grace
        # deadline cannot exceed the signed maximum by a fractional second.
        issued_at = datetime.now(UTC).replace(microsecond=0)
        offline_grace_expires_at = issued_at + timedelta(
            hours=self.policy.offline_grace_hours
        )
        snapshot_expires_at = issued_at + timedelta(
            hours=min(self.policy.offline_grace_hours, 12)
        )
        terms=getattr(subscription,'commercial_terms',None)
        signed_status=subscription.status
        if terms is not None:
            hours=min(self.policy.offline_grace_hours,int(terms['offline_grace_hours']))
            offline_grace_expires_at=issued_at+timedelta(hours=hours)
            if subscription.grace_ends_at:
                boundary=subscription.grace_ends_at.replace(microsecond=0)
                if boundary<=issued_at:
                    # NumericDate cannot represent the last fractional second.
                    # Sign a non-writable result instead of extending a license
                    # or raising an authentication-time 500.
                    signed_status='expired'
                    offline_grace_expires_at=issued_at+timedelta(seconds=1)
                else:offline_grace_expires_at=min(offline_grace_expires_at,boundary)
            snapshot_expires_at=min(snapshot_expires_at,offline_grace_expires_at)
        token = create_entitlement_snapshot_token(
            company_id=str(subscription.company_id),
            status=signed_status,
            plan=subscription.plan,
            offline_grace_expires_at=offline_grace_expires_at,
            snapshot_expires_at=snapshot_expires_at,
            issued_at=issued_at,
            **({'features':terms.get('features',{}),'limits':{kind:terms.get(kind+'_limit') for kind in ('branch','device','employee')}} if terms is not None else {}),
        )
        writes_allowed = signed_status in WRITE_ALLOWED_STATUSES
        return {
            "status": signed_status,
            "display_status": self.display_status(subscription) if signed_status==subscription.status else 'expired',
            "display_status_label": self.display_status_label(subscription) if signed_status==subscription.status else 'Expired',
            "plan": subscription.plan,
            "effective_until": self.effective_until(subscription),
            "offline_grace_expires_at": offline_grace_expires_at,
            "snapshot_token": token,
            "snapshot_expires_at": snapshot_expires_at,
            "writes_allowed": writes_allowed,
            "message": None
            if writes_allowed
            else "Your subscription has expired. Renew it to continue creating new sales and updating billable records.",
        }

    async def get_billable_device_ids(
        self,
        company_id: UUID,
        *,
        exclude_device_id: UUID | None = None,
    ) -> list[UUID]:
        statement = select(Device.id).where(
            Device.company_id == company_id,
            Device.deleted == False,
            Device.active == True,
            Device.status == "active",
            Device.claimed_at.is_not(None),
            Device.removed_at.is_(None),
            Device.deactivated_at.is_(None),
        )
        if exclude_device_id is not None:
            statement = statement.where(
                Device.id != exclude_device_id
            )
        result = await self.db.execute(statement)
        return list(result.scalars().all())

    async def build_billing_summary(
        self,
        company_id: UUID,
        plan: str,
        *,
        allow_zero: bool = False,
    ) -> dict:
        normalized_plan = str(plan or "").strip().lower()
        if normalized_plan not in PLAN_PRICING:
            raise HTTPException(
                400,
                "Subscription plan must be monthly or yearly.",
            )
        included_device_ids = await self.get_billable_device_ids(
            company_id
        )
        terminal_count = len(included_device_ids)
        if terminal_count <= 0 and not allow_zero:
            raise HTTPException(
                400,
                "At least one active claimed POS terminal is required before starting a subscription payment.",
            )
        unit_price = quantize_amount(
            PLAN_PRICING[normalized_plan]
        )
        total_amount = quantize_amount(
            unit_price * terminal_count
        )
        return {
            "billing_period": normalized_plan,
            "currency": "USD",
            "unit_price": unit_price,
            "terminal_count": terminal_count,
            "total_amount": total_amount,
            "included_device_ids": included_device_ids,
        }

    async def billing_options(
        self,
        company_id: UUID,
    ) -> list[dict]:
        included_device_ids = await self.get_billable_device_ids(
            company_id
        )
        terminal_count = len(included_device_ids)
        options: list[dict] = []
        for billing_period, unit_price in PLAN_PRICING.items():
            price = quantize_amount(unit_price)
            options.append(
                {
                    "billing_period": billing_period,
                    "currency": "USD",
                    "unit_price": price,
                    "terminal_count": terminal_count,
                    "total_amount": quantize_amount(
                        price * terminal_count
                    ),
                }
            )
        return options

    def usage_summary(
        self,
        subscription: CompanySubscription,
        active_terminals: int,
    ) -> dict:
        allowance = subscription.licensed_terminal_count
        allowance_enforced = allowance is not None
        available_slots = (
            max(allowance - active_terminals, 0)
            if allowance is not None
            else None
        )
        return {
            "active_terminals": active_terminals,
            "billable_terminals": active_terminals,
            "licensed_terminal_allowance": allowance,
            "available_terminal_slots": available_slots,
            "allowance_enforced": allowance_enforced,
        }

    async def get_latest_checkout_session(
        self,
        company_id: UUID,
    ) -> SubscriptionCheckoutSession | None:
        result = await self.db.execute(
            select(SubscriptionCheckoutSession)
            .where(
                SubscriptionCheckoutSession.company_id == company_id
            )
            .order_by(
                SubscriptionCheckoutSession.created_at.desc()
            )
        )
        return result.scalars().first()

    async def get_checkout_session_by_reference(
        self,
        reference: str,
        *,
        for_update: bool = False,
    ) -> SubscriptionCheckoutSession | None:
        statement = select(SubscriptionCheckoutSession).where(
            SubscriptionCheckoutSession.session_reference
            == reference
        )
        if for_update:
            statement = statement.with_for_update()
        result = await self.db.execute(statement)
        return result.scalar_one_or_none()

    def serialize_checkout_session(
        self,
        session: SubscriptionCheckoutSession | None,
    ) -> dict | None:
        if session is None:
            return None
        return {
            "id": session.id,
            "session_reference": session.session_reference,
            "provider": session.provider,
            "status": session.status,
            "billing_period": session.billing_period,
            "billing_currency": session.billing_currency,
            "unit_price": session.unit_price,
            "terminal_count": session.terminal_count,
            "total_amount": session.total_amount,
            "paynow_reference": session.paynow_reference,
            "checkout_url": session.checkout_url,
            "poll_url": session.poll_url,
            "payment_status": session.payment_status,
            "expires_at": session.expires_at,
            "created_at": session.created_at,
            "updated_at": session.updated_at,
        }

    def merge_payload(
        self,
        session: SubscriptionCheckoutSession,
        updates: dict,
    ) -> dict:
        payload = dict(session.payload or {})
        payload.update(updates)
        return payload

    async def maybe_refresh_latest_paynow_session(
        self,
        latest_session: SubscriptionCheckoutSession | None,
    ) -> SubscriptionCheckoutSession | None:
        if latest_session is None:
            return None
        if latest_session.provider != "paynow":
            return latest_session
        if latest_session.status in {"paid", "cancelled", "failed", "expired"}:
            return latest_session
        if not latest_session.poll_url:
            return latest_session
        try:
            return await self.refresh_paynow_checkout_from_poll(
                latest_session.session_reference
            )
        except HTTPException:
            return latest_session

    async def page(
        self,
        company_id: UUID,
    ) -> dict:
        subscription = await self.ensure_current(company_id)
        commercial=getattr(subscription,'commercial_terms',None)
        billing_preview = await self.build_billing_summary(
            company_id,
            subscription.plan if subscription.plan in PLAN_PRICING else "monthly",
            allow_zero=True,
        )
        active_terminals = billing_preview["terminal_count"]
        latest_session = await self.get_latest_checkout_session(
            company_id
        )
        if not commercial:
            latest_session = await self.maybe_refresh_latest_paynow_session(latest_session)
        else:
            billing_preview={**billing_preview,'billing_period':'commercial','currency':commercial['currency'],
                'unit_price':Decimal(commercial['price']),'total_amount':Decimal(commercial['price'])}
        history_result = await self.db.execute(
            select(CompanySubscriptionHistory)
            .where(
                CompanySubscriptionHistory.company_id
                == company_id
            )
            .order_by(
                CompanySubscriptionHistory.created_at.desc()
            )
        )
        return {
            "current": {
                "company_id": company_id,
                "commercial_terms": commercial,
                "plan": subscription.plan,
                "status": subscription.status,
                "display_status": self.display_status(subscription),
                "display_status_label": self.display_status_label(
                    subscription
                ),
                "plan_label": commercial['plan_name'] if commercial else self.plan_label(subscription.plan),
                "trial_started_at": subscription.trial_started_at,
                "trial_ends_at": subscription.trial_ends_at,
                "trial_days_remaining": self.trial_days_remaining(
                    subscription
                ),
                "current_period_started_at": subscription.current_period_started_at,
                "current_period_ends_at": subscription.current_period_ends_at,
                "grace_ends_at": subscription.grace_ends_at,
                "subscription_started_at": self.subscription_started_at(
                    subscription
                ),
                "renewal_or_expiry_at": self.renewal_or_expiry_at(
                    subscription
                ),
                "provider": subscription.provider,
                "provider_reference": subscription.provider_reference,
                "status_reason": subscription.status_reason,
                "snapshot": self.snapshot_for(subscription),
            },
            "usage": self.usage_summary(
                subscription,
                active_terminals,
            ),
            "billing_preview": billing_preview,
            "billing_options": [] if commercial else await self.billing_options(company_id),
            "latest_checkout": self.serialize_checkout_session(
                latest_session
            ),
            "history": history_result.scalars().all(),
            "activation_available": False if commercial else self.policy.activation_available,
            "activation_message": 'Renew through your commercial subscription invoice.' if commercial else self.payment_configuration_message(),
            "provider_name": self.provider_name(),
            "checkout_configured": self.policy.activation_available,
            "webhook_configured": self.provider_name() == "paynow"
            and bool(
                self.policy.paynow_credentials.integration_key
                and self.policy.paynow_credentials.result_url
            ),
            "payment_configuration_required": self.payment_configuration_required(),
            "available_plans": [] if commercial else ["monthly", "yearly"],
        }

    async def enforce_writes_allowed(
        self,
        company_id: UUID,
    ):
        subscription = await self.ensure_current(company_id)
        if subscription.status not in WRITE_ALLOWED_STATUSES:
            raise HTTPException(
                402,
                "This subscription is no longer active. Renew it to continue creating new sales or changing billable records.",
            )

    async def enforce_device_activation_allowed(
        self,
        company_id: UUID,
        *,
        exclude_device_id: UUID | None = None,
    ):
        if not hasattr(self.db, "execute"):
            return
        subscription = await self.ensure_current(company_id)
        if subscription.status == "trial":
            if getattr(subscription,'commercial_terms',None) is None:return
        from app.subscriptions.commercial import enforce_capacity
        await enforce_capacity(self.db,company_id,'device',exclude_device_id)
        allowance = subscription.licensed_terminal_count
        if allowance is None:
            return
        active_devices = await self.get_billable_device_ids(
            company_id,
            exclude_device_id=exclude_device_id,
        )
        if len(active_devices) >= allowance:
            raise HTTPException(
                402,
                "All licensed POS terminal slots are already in use. Upgrade the subscription before activating another terminal.",
            )

    def record_history(
        self,
        subscription: CompanySubscription,
        *,
        action: str,
        plan: str | None,
        status: str,
        provider: str | None,
        provider_reference: str | None,
        payload: dict | None,
        note: str,
    ) -> None:
        self.db.add(
            CompanySubscriptionHistory(
                company_subscription_id=subscription.id,
                company_id=subscription.company_id,
                action=action,
                plan=plan,
                status=status,
                provider=provider,
                provider_reference=provider_reference,
                payload=payload,
                note=note,
            )
        )

    async def send_paynow_request(
        self,
        pairs: list[tuple[str, str]],
    ) -> bytes:
        try:
            async with httpx.AsyncClient(
                transport=httpx.AsyncHTTPTransport(),
                timeout=PAYNOW_TIMEOUT_SECONDS
            ) as client:
                response = await client.post(
                    PAYNOW_INITIATE_URL,
                    content=urlencode(pairs).encode("utf-8"),
                    headers={
                        "Content-Type": "application/x-www-form-urlencoded"
                    },
                )
                response.raise_for_status()
                return response.content
        except httpx.TimeoutException as exc:
            raise HTTPException(
                504,
                "Paynow did not respond in time. Please try again.",
            ) from exc
        except httpx.TransportError as exc:
            raise HTTPException(
                502,
                "The payment service is temporarily unavailable. Please try again.",
            ) from exc
        except httpx.HTTPError as exc:
            raise HTTPException(
                502,
                "Unable to start the Paynow checkout right now.",
            ) from exc

    async def fetch_paynow_poll(
        self,
        poll_url: str,
    ) -> bytes:
        try:
            async with httpx.AsyncClient(
                timeout=PAYNOW_TIMEOUT_SECONDS
            ) as client:
                response = await client.get(poll_url)
                response.raise_for_status()
                return response.content
        except httpx.TimeoutException as exc:
            raise HTTPException(
                504,
                "Paynow status verification timed out. Please refresh again shortly.",
            ) from exc
        except httpx.HTTPError as exc:
            raise HTTPException(
                502,
                "Unable to verify the Paynow payment status right now.",
            ) from exc

    def create_session_reference(self) -> str:
        return f"APR-SUB-{token_urlsafe(12).upper()}"

    async def activate_or_renew(
        self,
        company_id: UUID,
        plan: str,
    ) -> dict:
        current=await self.get_current(company_id)
        if current is not None and getattr(current,'commercial_terms',None) is not None:
            raise HTTPException(409,'This business uses commercial invoices; renew through platform billing')
        normalized_plan = str(plan or "").strip().lower()
        if normalized_plan not in PLAN_DURATIONS:
            raise HTTPException(
                400,
                "Subscription plan must be monthly or yearly.",
            )
        if self.provider_name() == "paynow":
            return await self.activate_or_renew_with_paynow(
                company_id,
                normalized_plan,
            )

        subscription = await self.ensure_current(company_id)
        if not self.policy.activation_available:
            return {
                "activation_available": False,
                "provider": None,
                "checkout_url": None,
                "checkout_session_id": None,
                "checkout_session_reference": None,
                "message": self.payment_configuration_message(),
            }

        session_reference = self.create_session_reference()
        checkout_url = (
            f"{self.policy.checkout_base_url}"
            f"?session_reference={session_reference}"
            f"&company_id={company_id}"
            f"&plan={normalized_plan}"
        )
        checkout_session = SubscriptionCheckoutSession(
            company_id=company_id,
            company_subscription_id=subscription.id,
            plan=normalized_plan,
            provider=self.provider_name() or "unknown",
            session_reference=session_reference,
            status="pending",
            checkout_url=checkout_url,
            billing_period=normalized_plan,
            billing_currency="USD",
            payment_status="pending",
            payload={"plan": normalized_plan},
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
        self.db.add(checkout_session)
        await self.db.flush()

        self.record_history(
            subscription,
            action="checkout_session_created",
            plan=normalized_plan,
            status=subscription.status,
            provider=self.provider_name(),
            provider_reference=session_reference,
            payload={"checkout_url": checkout_url},
            note="Awaiting payment provider confirmation",
        )
        await self.db.commit()
        return {
            "activation_available": True,
            "provider": self.provider_name(),
            "checkout_url": checkout_url,
            "checkout_session_id": str(checkout_session.id),
            "checkout_session_reference": session_reference,
            "message": (
                "Checkout session created. Subscription access will update only after the payment provider confirms payment. "
                f"{self.payment_configuration_message()}"
            ),
        }

    async def activate_or_renew_with_paynow(
        self,
        company_id: UUID,
        plan: str,
    ) -> dict:
        subscription = await self.ensure_current(company_id)
        if not self.policy.activation_available:
            return {
                "activation_available": False,
                "provider": "paynow",
                "checkout_url": None,
                "checkout_session_id": None,
                "checkout_session_reference": None,
                "message": self.payment_configuration_message(),
            }
        company = await self.get_company(company_id)

        billing = await self.build_billing_summary(
            company_id,
            plan,
        )
        session_reference = self.create_session_reference()
        checkout_session = SubscriptionCheckoutSession(
            company_id=company_id,
            company_subscription_id=subscription.id,
            plan=plan,
            provider="paynow",
            session_reference=session_reference,
            status="pending",
            billing_period=plan,
            billing_currency=billing["currency"],
            unit_price=billing["unit_price"],
            terminal_count=billing["terminal_count"],
            total_amount=billing["total_amount"],
            included_device_ids=[
                str(device_id)
                for device_id in billing["included_device_ids"]
            ],
            payment_status="pending",
            payload={
                "billing_period": plan,
                "currency": billing["currency"],
                "unit_price": str(billing["unit_price"]),
                "terminal_count": billing["terminal_count"],
                "total_amount": str(billing["total_amount"]),
                "included_device_ids": [
                    str(device_id)
                    for device_id in billing["included_device_ids"]
                ],
                "internal_reference": session_reference,
            },
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
        self.db.add(checkout_session)
        await self.db.flush()

        credentials = self.policy.paynow_credentials
        additional_info = (
            f"ApexRetail {self.plan_label(plan)} subscription for "
            f"{billing['terminal_count']} POS terminal(s)"
        )
        request_pairs: list[tuple[str, str]] = [
            ("id", credentials.integration_id),
            ("reference", session_reference),
            ("amount", f"{billing['total_amount']:.2f}"),
            ("additionalinfo", additional_info),
            ("returnurl", credentials.return_url),
            ("resulturl", credentials.result_url),
            ("authemail", company.owner_email),
            ("status", "Message"),
        ]
        request_pairs.append(
            (
                "hash",
                build_hash(
                    request_pairs,
                    credentials.integration_key,
                ),
            )
        )

        response_body = await self.send_paynow_request(
            request_pairs
        )
        try:
            response = parse_initiation_response(
                response_body,
                credentials.integration_key,
            )
        except PaynowError as exc:
            raise HTTPException(
                502,
                str(exc),
            ) from exc

        checkout_session.checkout_url = response.browser_url
        checkout_session.poll_url = response.poll_url
        checkout_session.paynow_reference = response.paynow_reference
        checkout_session.payment_status = normalize_payment_status(
            response.status
        )
        checkout_session.status = normalize_payment_status(
            response.status
        )
        checkout_session.payload = self.merge_payload(
            checkout_session,
            {
                "paynow_reference": response.paynow_reference,
                "poll_url": response.poll_url,
                "browser_url": response.browser_url,
                "initiation_status": response.status,
                "initiation_response": response.raw_fields,
            },
        )

        self.record_history(
            subscription,
            action="paynow_checkout_created",
            plan=plan,
            status=subscription.status,
            provider="paynow",
            provider_reference=response.paynow_reference,
            payload=checkout_session.payload,
            note="Awaiting verified Paynow payment result",
        )
        await self.db.commit()

        return {
            "activation_available": True,
            "provider": "paynow",
            "checkout_url": response.browser_url,
            "checkout_session_id": str(checkout_session.id),
            "checkout_session_reference": session_reference,
            "message": "Paynow checkout opened. Subscription access will change only after a verified payment result is received.",
        }

    async def apply_confirmed_payment(
        self,
        *,
        company_id: UUID,
        provider: str,
        provider_reference: str,
        plan: str,
        billing_snapshot: dict,
        payload: dict | None,
        status_reason: str,
    ) -> CompanySubscription:
        subscription = await self.ensure_current(company_id)
        if getattr(subscription,'commercial_terms',None) is not None:
            # A late, verified legacy callback is money received, not permission
            # to overwrite the commercial contract. Retain it for reconciliation.
            self.record_history(subscription,action='legacy_payment_needs_review',plan=plan,status=subscription.status,
                provider=provider,provider_reference=provider_reference,payload={'payment':payload,'billing_snapshot':{k:str(v) if isinstance(v,Decimal) else v for k,v in billing_snapshot.items()}},note='Verified legacy payment retained; commercial license unchanged')
            from app.models.commercial import PlatformAudit
            self.db.add(PlatformAudit(company_id=company_id,action='legacy_payment_needs_review',details={'provider':provider,'provider_reference':provider_reference}))
            await self.db.commit()
            return subscription
        now = datetime.now(UTC)
        duration = PLAN_DURATIONS[plan]
        period_start = now
        if (
            subscription.current_period_ends_at
            and subscription.current_period_ends_at > now
        ):
            period_start = subscription.current_period_ends_at
        period_end = period_start + duration
        subscription.plan = plan
        subscription.status = "active"
        subscription.current_period_started_at = period_start
        subscription.current_period_ends_at = period_end
        subscription.grace_ends_at = period_end + timedelta(
            hours=self.policy.offline_grace_hours
        )
        subscription.provider = provider
        subscription.provider_reference = provider_reference
        subscription.billing_currency = str(
            billing_snapshot["currency"]
        )
        subscription.licensed_terminal_count = int(
            billing_snapshot["terminal_count"]
        )
        subscription.unit_price = billing_snapshot["unit_price"]
        subscription.total_amount = billing_snapshot["total_amount"]
        subscription.status_reason = status_reason
        self.db.add(subscription)
        await self.db.flush()
        self.record_history(
            subscription,
            action="payment_confirmed",
            plan=plan,
            status=subscription.status,
            provider=provider,
            provider_reference=provider_reference,
            payload=payload,
            note="Renewal applied from verified payment confirmation",
        )
        await self.db.commit()
        await self.db.refresh(subscription)
        return self.apply_status_windows(subscription)

    def paynow_event_id(
        self,
        *,
        source: str,
        reference: str,
        paynow_reference: str,
        status: str,
        amount: str,
    ) -> str:
        digest = hashlib.sha256(
            f"{source}|{reference}|{paynow_reference}|{status}|{amount}".encode(
                "utf-8"
            )
        ).hexdigest()
        return f"paynow:{source}:{digest}"

    def validate_checkout_snapshot(
        self,
        session: SubscriptionCheckoutSession,
        fields: dict[str, str],
    ) -> dict:
        reference = str(fields.get("reference", "")).strip()
        amount = quantize_amount(
            fields.get("amount", "0")
        )
        paynow_reference = str(
            fields.get("paynowreference", "")
        ).strip()
        if reference != session.session_reference:
            raise HTTPException(
                400,
                "Payment reference did not match the pending subscription checkout.",
            )
        if session.expires_at and datetime.now(UTC) > session.expires_at:
            session.status = "expired"
            session.payment_status = "expired"
            raise HTTPException(
                410,
                "This subscription checkout session has expired. Start a new payment.",
            )
        if (
            quantize_amount(session.total_amount or Decimal("0"))
            != amount
        ):
            raise HTTPException(
                400,
                "The payment amount did not match the pending subscription checkout.",
            )
        if str(session.billing_currency or "").upper() != "USD":
            raise HTTPException(
                400,
                "The pending subscription checkout currency is invalid.",
            )
        if not session.terminal_count or session.terminal_count <= 0:
            raise HTTPException(
                400,
                "The pending subscription checkout does not have a valid terminal count.",
            )
        if (
            session.paynow_reference
            and paynow_reference
            and paynow_reference != session.paynow_reference
        ):
            raise HTTPException(
                400,
                "The Paynow reference did not match the pending subscription checkout.",
            )
        return {
            "reference": reference,
            "amount": amount,
            "paynow_reference": paynow_reference
            or session.paynow_reference,
            "terminal_count": session.terminal_count,
            "currency": "USD",
            "billing_period": session.billing_period or session.plan,
            "unit_price": quantize_amount(
                session.unit_price or Decimal("0")
            ),
            "total_amount": quantize_amount(
                session.total_amount or Decimal("0")
            ),
            "included_device_ids": [
                UUID(str(device_id))
                for device_id in (session.included_device_ids or [])
            ],
        }

    async def apply_paynow_payment_update(
        self,
        session: SubscriptionCheckoutSession,
        fields: dict[str, str],
        *,
        source: str,
    ) -> str:
        normalized_status = normalize_payment_status(
            fields.get("status")
        )
        already_paid = (
            session.status == "paid"
            or session.payment_status == "paid"
        )
        session.payment_status = normalized_status
        session.status = normalized_status
        session.payload = self.merge_payload(
            session,
            {
                f"{source}_response": fields,
                "paynow_reference": fields.get(
                    "paynowreference"
                )
                or session.paynow_reference,
                "poll_url": fields.get("pollurl")
                or session.poll_url,
                "payment_status": normalized_status,
            },
        )
        if fields.get("paynowreference"):
            session.paynow_reference = fields["paynowreference"]
        if fields.get("pollurl"):
            session.poll_url = fields["pollurl"]

        if normalized_status not in PAYNOW_SUCCESS_STATUSES:
            return normalized_status

        if already_paid:
            return "paid"

        billing_snapshot = self.validate_checkout_snapshot(
            session,
            fields,
        )
        subscription = await self.apply_confirmed_payment(
            company_id=session.company_id,
            provider="paynow",
            provider_reference=str(
                billing_snapshot["paynow_reference"]
                or session.session_reference
            ),
            plan=str(
                billing_snapshot["billing_period"]
                or session.plan
            ),
            billing_snapshot=billing_snapshot,
            payload=self.merge_payload(
                session,
                {
                    "verified_source": source,
                    "verified_at": datetime.now(UTC).isoformat(),
                },
            ),
            status_reason="Payment confirmed by Paynow",
        )
        session.status = "paid"
        session.payment_status = "paid"
        session.payload = self.merge_payload(
            session,
            {
                "subscription_status": subscription.status,
                "licensed_terminal_count": subscription.licensed_terminal_count,
            },
        )
        return "paid"

    async def refresh_paynow_checkout_from_poll(
        self,
        session_reference: str,
    ) -> SubscriptionCheckoutSession:
        if self.provider_name() != "paynow":
            raise HTTPException(
                400,
                "Paynow polling is not enabled.",
            )
        session = await self.get_checkout_session_by_reference(
            session_reference,
            for_update=True,
        )
        if session is None:
            raise HTTPException(
                404,
                "Subscription checkout session not found.",
            )
        if not session.poll_url:
            return session
        response_body = await self.fetch_paynow_poll(
            session.poll_url
        )
        pairs = parse_form_body(response_body)
        if not validate_hash(
            pairs,
            self.policy.paynow_credentials.integration_key,
        ):
            raise HTTPException(
                403,
                "Paynow returned an invalid verification signature.",
            )
        fields = fields_from_pairs(pairs)
        self.validate_checkout_snapshot(
            session,
            fields,
        )

        event_id = self.paynow_event_id(
            source="poll",
            reference=str(fields.get("reference", "")),
            paynow_reference=str(
                fields.get("paynowreference", "")
            ),
            status=str(fields.get("status", "")),
            amount=str(fields.get("amount", "")),
        )
        existing_result = await self.db.execute(
            select(SubscriptionWebhookEvent).where(
                SubscriptionWebhookEvent.provider_event_id
                == event_id
            )
        )
        if existing_result.scalar_one_or_none() is None:
            self.db.add(
                SubscriptionWebhookEvent(
                    provider="paynow",
                    provider_event_id=event_id,
                    event_type="subscription.poll",
                    company_id=session.company_id,
                    payload=fields,
                    processed=True,
                    processed_at=datetime.now(UTC),
                    processing_error=None,
                )
            )
        await self.apply_paynow_payment_update(
            session,
            fields,
            source="poll",
        )
        await self.db.commit()
        await self.db.refresh(session)
        return session

    async def process_paynow_result(
        self,
        body: bytes,
    ) -> dict:
        if self.provider_name() != "paynow":
            raise HTTPException(
                503,
                "Paynow is not configured on this server.",
            )
        pairs = parse_form_body(body)
        if not pairs:
            raise HTTPException(
                400,
                "Paynow callback body is empty.",
            )
        if not validate_hash(
            pairs,
            self.policy.paynow_credentials.integration_key,
        ):
            raise HTTPException(
                403,
                "Paynow callback signature is invalid.",
            )
        fields = fields_from_pairs(pairs)
        reference = str(fields.get("reference", "")).strip()
        if not reference:
            raise HTTPException(
                400,
                "Paynow callback reference is missing.",
            )
        session = await self.get_checkout_session_by_reference(
            reference,
            for_update=True,
        )
        if session is None:
            raise HTTPException(
                404,
                "The payment reference was not recognised.",
            )

        event_id = self.paynow_event_id(
            source="result",
            reference=reference,
            paynow_reference=str(
                fields.get("paynowreference", "")
            ),
            status=str(fields.get("status", "")),
            amount=str(fields.get("amount", "")),
        )
        existing_result = await self.db.execute(
            select(SubscriptionWebhookEvent).where(
                SubscriptionWebhookEvent.provider_event_id
                == event_id
            )
        )
        existing = existing_result.scalar_one_or_none()
        if existing is not None:
            return {
                "processed": bool(existing.processed),
                "duplicate": True,
                "company_id": existing.company_id,
                "status": session.status,
            }

        self.validate_checkout_snapshot(
            session,
            fields,
        )

        self.db.add(
            SubscriptionWebhookEvent(
                provider="paynow",
                provider_event_id=event_id,
                event_type="subscription.result",
                company_id=session.company_id,
                payload=fields,
                processed=False,
                processed_at=None,
                processing_error=None,
            )
        )

        status = await self.apply_paynow_payment_update(
            session,
            fields,
            source="result",
        )
        event = (
            await self.db.execute(
                select(SubscriptionWebhookEvent).where(
                    SubscriptionWebhookEvent.provider_event_id
                    == event_id
                )
            )
        ).scalar_one()
        event.processed = True
        event.processed_at = datetime.now(UTC)
        event.processing_error = None
        self.db.add(event)
        await self.db.commit()
        return {
            "processed": True,
            "duplicate": False,
            "company_id": session.company_id,
            "status": status,
        }

    async def record_webhook(
        self,
        data,
    ) -> dict:
        existing_result = await self.db.execute(
            select(SubscriptionWebhookEvent).where(
                SubscriptionWebhookEvent.provider_event_id
                == data.provider_event_id
            )
        )
        existing = existing_result.scalar_one_or_none()
        if existing is not None:
            return {
                "processed": bool(existing.processed),
                "duplicate": True,
                "company_id": existing.company_id,
                "status": None,
            }

        event = SubscriptionWebhookEvent(
            provider=data.provider,
            provider_event_id=data.provider_event_id,
            event_type=data.event_type,
            company_id=data.company_id,
            payload=data.payload,
            processed=False,
            processed_at=None,
            processing_error=None,
        )
        self.db.add(event)
        await self.db.flush()

        status = None
        if data.event_type == "subscription.payment_confirmed":
            if data.company_id is None:
                raise HTTPException(
                    400,
                    "company_id is required for payment confirmation",
                )
            plan = str(
                (data.payload or {}).get("plan") or ""
            ).strip().lower()
            provider_reference = str(
                (data.payload or {}).get("provider_reference")
                or data.provider_event_id
            ).strip()
            if plan not in PLAN_DURATIONS:
                raise HTTPException(
                    400,
                    "Webhook payload plan must be monthly or yearly",
                )
            billing_snapshot = {
                "currency": str(
                    (data.payload or {}).get("currency")
                    or "USD"
                ),
                "terminal_count": int(
                    (data.payload or {}).get("terminal_count")
                    or 1
                ),
                "unit_price": quantize_amount(
                    (data.payload or {}).get("unit_price")
                    or PLAN_PRICING[plan]
                ),
                "total_amount": quantize_amount(
                    (data.payload or {}).get("total_amount")
                    or PLAN_PRICING[plan]
                ),
            }
            subscription = await self.apply_confirmed_payment(
                company_id=data.company_id,
                provider=data.provider,
                provider_reference=provider_reference,
                plan=plan,
                billing_snapshot=billing_snapshot,
                payload=data.payload,
                status_reason="Payment confirmed by provider",
            )
            status = subscription.status
            event.processed = True
            event.processed_at = datetime.now(UTC)
            event.processing_error = None
            self.db.add(event)
            await self.db.commit()
        else:
            event.processed = True
            event.processed_at = datetime.now(UTC)
            self.db.add(event)
            await self.db.commit()

        return {
            "processed": True,
            "duplicate": False,
            "company_id": data.company_id,
            "status": status,
        }

    def build_webhook_signature(
        self,
        body: bytes,
    ) -> str:
        if not self.policy.webhook_secret:
            raise RuntimeError(
                "Webhook secret is not configured"
            )
        digest = hmac.new(
            self.policy.webhook_secret.encode("utf-8"),
            body,
            hashlib.sha256,
        ).hexdigest()
        return f"sha256={digest}"

    def verify_webhook_signature(
        self,
        *,
        body: bytes,
        provided_signature: str | None,
    ) -> None:
        if not self.policy.webhook_secret:
            raise HTTPException(
                503,
                "Webhook secret is not configured",
            )
        if not provided_signature:
            raise HTTPException(
                403,
                "Webhook signature is required",
            )
        expected = self.build_webhook_signature(body)
        if not hmac.compare_digest(
            provided_signature.strip(),
            expected,
        ):
            raise HTTPException(
                403,
                "Invalid webhook signature",
            )
