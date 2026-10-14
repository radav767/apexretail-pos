import uuid
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError

from app.currencies.repository import CurrencyRepository
from app.currencies.schema import CurrencyCreate, CurrencyUpdate, ExchangeRateCreate
from app.financial_access import enforce_actor_company
from app.models import AuditEvent, CompanyCurrency, CurrencyExchangeRate


def money_quantum(decimal_places: int) -> Decimal:
    return Decimal(1).scaleb(-decimal_places)


def quantize_currency(value: Decimal, decimal_places: int) -> Decimal:
    return Decimal(value).quantize(money_quantum(decimal_places), rounding=ROUND_HALF_UP)


class CurrencyService:
    def __init__(self, repo: CurrencyRepository):
        self.repo = repo

    @staticmethod
    def actor_user_id(actor):
        return actor.user.id if actor.actor_type == "user" and actor.user else None

    @staticmethod
    def enforce_currency_admin(actor):
        if actor.role not in {"owner", "administrator", "manager"}:
            raise HTTPException(403, "Currency administration permission required")
        if actor.actor_type == "employee" and not (actor.permissions or {}).get("currencies_manage"):
            raise HTTPException(403, "Currency administration permission required")

    async def ensure_base(self, company_id):
        settings = await self.repo.settings(company_id)
        base = await self.repo.base(company_id)
        if settings is None or base is None:
            raise HTTPException(409, "Company base currency configuration is incomplete")

        configured_code = str(getattr(settings, "currency_code", "") or "").strip().upper()
        configured_symbol = str(getattr(settings, "currency_symbol", "") or "").strip()
        base_code = str(getattr(base, "code", "") or "").strip().upper()
        base_symbol = str(getattr(base, "symbol", "") or "").strip()
        try:
            configured_places = int(settings.decimal_places)
            base_places = int(base.decimal_places)
        except (AttributeError, TypeError, ValueError):
            raise HTTPException(409, "Company base currency configuration is invalid")

        if (
            getattr(settings, "base_currency_id", None) != base.id
            or configured_code != base_code
            or configured_symbol != base_symbol
            or configured_places != base_places
            or not base_code.isascii()
            or not base_code.isalnum()
            or not 3 <= len(base_code) <= 8
            or not getattr(base, "active", False)
            or not getattr(base, "is_base", False)
            or not 0 <= base_places <= 4
        ):
            raise HTTPException(409, "Company base currency configuration is inconsistent")
        return base

    async def serialize(self, currency, *, at=None):
        effective_at = at or datetime.now(timezone.utc)
        recent = [] if currency.is_base else await self.repo.recent_effective_rates(
            currency.company_id, currency.id, effective_at, 2
        )
        rate = recent[0] if recent else None
        previous = recent[1] if len(recent) > 1 else None
        values = {column.name: getattr(currency, column.name) for column in currency.__table__.columns}
        values.update({
            "current_rate": Decimal("1") if currency.is_base else (rate.foreign_units_per_base if rate else None),
            "current_rate_id": rate.id if rate else None,
            "rate_effective_at": rate.effective_at if rate else None,
            "previous_rate": previous.foreign_units_per_base if previous else None,
            "previous_rate_effective_at": previous.effective_at if previous else None,
        })
        return values

    async def list(self, company_id, actor, *, active=None, at=None):
        enforce_actor_company(actor, company_id)
        self.enforce_currency_admin(actor)
        return [await self.serialize(row, at=at) for row in await self.repo.list(company_id, active=active)]

    async def pos_config(self, company_id, actor):
        enforce_actor_company(actor, company_id)
        generated_at = datetime.now(timezone.utc)
        base = await self.ensure_base(company_id)
        settings = await self.repo.settings(company_id)
        currencies = [
            await self.serialize(row, at=generated_at)
            for row in await self.repo.list(company_id, active=True)
        ]
        return {
            "company_id": company_id,
            "version": int(getattr(settings, "currency_config_version", 1) or 1),
            "generated_at": generated_at,
            "multi_currency_enabled": bool(getattr(settings, "multi_currency_enabled", False)),
            "base_currency_code": base.code,
            "currencies": currencies,
        }

    async def create(self, data: CurrencyCreate, actor):
        enforce_actor_company(actor, data.company_id)
        self.enforce_currency_admin(actor)
        settings = await self.repo.settings(data.company_id, for_update=True)
        if settings is None:
            raise HTTPException(404, "Company settings not found")
        if data.is_base:
            raise HTTPException(409, "Create the currency first, then use the protected base-currency action")
        currency = CompanyCurrency(
            **data.model_dump(), created_by_user_id=self.actor_user_id(actor)
        )
        settings.currency_config_version = int(settings.currency_config_version or 0) + 1
        audit = AuditEvent(
            company_id=data.company_id,
            actor_user_id=self.actor_user_id(actor),
            actor_employee_id=actor.employee.id if actor.actor_type == "employee" else None,
            action="currency_created",
            details={"code": currency.code, "is_base": currency.is_base},
        )
        try:
            await self.repo.save(currency, settings, audit)
        except IntegrityError as exc:
            raise HTTPException(409, "Currency code already exists for this company") from exc
        return await self.serialize(currency)

    async def set_multi_currency(self, company_id, enabled, actor):
        enforce_actor_company(actor, company_id)
        self.enforce_currency_admin(actor)
        settings = await self.repo.settings(company_id, for_update=True)
        if settings is None:
            raise HTTPException(404, "Company settings not found")
        settings.multi_currency_enabled = bool(enabled)
        settings.currency_config_version = int(settings.currency_config_version or 0) + 1
        audit = AuditEvent(
            company_id=company_id,
            actor_user_id=self.actor_user_id(actor),
            actor_employee_id=actor.employee.id if actor.actor_type == "employee" else None,
            action="multi_currency_configuration_updated",
            details={"enabled": bool(enabled)},
        )
        await self.repo.save(settings, audit)
        return await self.pos_config(company_id, actor)

    async def update(self, company_id, currency_id, data: CurrencyUpdate, actor):
        enforce_actor_company(actor, company_id)
        self.enforce_currency_admin(actor)
        currency = await self.repo.get(company_id, currency_id, for_update=True)
        settings = await self.repo.settings(company_id, for_update=True)
        if currency is None or settings is None:
            raise HTTPException(404, "Currency not found")
        values = data.model_dump(exclude_unset=True)
        if currency.is_base:
            if values.get("active") is False:
                raise HTTPException(409, "The base currency cannot be deactivated")
            if values.get("decimal_places", currency.decimal_places) > 2:
                raise HTTPException(409, "Base accounting currency currently supports at most two decimal places")
        for key, value in values.items():
            setattr(currency, key, value.strip() if isinstance(value, str) else value)
        if currency.is_base:
            settings.currency_code = currency.code
            settings.currency_symbol = currency.symbol
            settings.decimal_places = currency.decimal_places
        settings.currency_config_version = int(settings.currency_config_version or 0) + 1
        audit = AuditEvent(
            company_id=company_id,
            actor_user_id=self.actor_user_id(actor),
            actor_employee_id=actor.employee.id if actor.actor_type == "employee" else None,
            action="currency_updated",
            details={"currency_id": str(currency.id), "changes": sorted(values)},
        )
        await self.repo.save(currency, settings, audit)
        return await self.serialize(currency)

    async def set_base(self, company_id, currency_id, actor):
        enforce_actor_company(actor, company_id)
        self.enforce_currency_admin(actor)
        settings = await self.repo.settings(company_id, for_update=True)
        currencies = await self.repo.list(company_id, for_update=True)
        selected = next((row for row in currencies if row.id == currency_id), None)
        if selected is None or settings is None:
            raise HTTPException(404, "Currency not found")
        current = next((row for row in currencies if row.is_base), None)
        if current and current.id == selected.id:
            return await self.serialize(selected)
        if not selected.active:
            raise HTTPException(409, "Activate the currency before making it the base currency")
        if selected.decimal_places > 2:
            raise HTTPException(409, "Base accounting currency currently supports at most two decimal places")
        if await self.repo.financial_activity_count(company_id):
            raise HTTPException(
                409,
                "Base currency cannot be changed after financial activity, shifts, or exchange-rate history exists",
            )
        try:
            if current is not None:
                current.is_base = False
                await self.repo.db.flush([current])
            selected.is_base = True
            selected.active = True
            await self.repo.db.flush([selected])
            settings.base_currency_id = selected.id
            settings.currency_code = selected.code
            settings.currency_symbol = selected.symbol
            settings.decimal_places = selected.decimal_places
            settings.currency_config_version = int(settings.currency_config_version or 0) + 1
            self.repo.db.add(AuditEvent(
                company_id=company_id,
                actor_user_id=self.actor_user_id(actor),
                actor_employee_id=actor.employee.id if actor.actor_type == "employee" else None,
                action="base_currency_changed",
                details={
                    "previous_currency": current.code if current else None,
                    "base_currency": selected.code,
                    "currency_id": str(selected.id),
                },
            ))
            await self.repo.db.commit()
            await self.repo.db.refresh(selected)
        except Exception:
            await self.repo.db.rollback()
            raise
        return await self.serialize(selected)

    async def create_rate(self, data: ExchangeRateCreate, actor):
        enforce_actor_company(actor, data.company_id)
        self.enforce_currency_admin(actor)
        if data.effective_at.tzinfo is None or data.effective_at.utcoffset() is None:
            raise HTTPException(400, "effective_at must include a timezone")
        currency = await self.repo.get(data.company_id, data.currency_id, for_update=True)
        settings = await self.repo.settings(data.company_id, for_update=True)
        if currency is None or settings is None:
            raise HTTPException(404, "Currency not found")
        if currency.is_base:
            raise HTTPException(409, "The base currency always has an exchange rate of 1")
        if not currency.active:
            raise HTTPException(409, "Activate the currency before setting an exchange rate")
        base = await self.repo.base(data.company_id)
        if base is None:
            raise HTTPException(409, "Company base currency is not configured")
        rate = CurrencyExchangeRate(
            id=uuid.uuid4(), company_id=data.company_id, currency_id=currency.id,
            currency_code=currency.code,
            foreign_units_per_base=Decimal(data.foreign_units_per_base),
            effective_at=data.effective_at,
            created_by_user_id=self.actor_user_id(actor),
            note=(data.note or "").strip() or None,
        )
        settings.currency_config_version = int(settings.currency_config_version or 0) + 1
        audit = AuditEvent(
            company_id=data.company_id,
            actor_user_id=self.actor_user_id(actor),
            actor_employee_id=actor.employee.id if actor.actor_type == "employee" else None,
            action="exchange_rate_created",
            details={"rate_id": str(rate.id), "base_currency": base.code, "currency": currency.code, "rate": str(rate.foreign_units_per_base), "effective_at": rate.effective_at.isoformat()},
        )
        try:
            saved = await self.repo.save(rate, settings, audit)
            actor_id, actor_name = await self.repo.rate_actor(saved)
            saved.base_currency_code = base.code
            saved.actor_id = actor_id
            saved.actor_name = actor_name
            return saved
        except IntegrityError as exc:
            raise HTTPException(409, "An exchange rate already exists at that effective time") from exc

    async def serialize_rate(self, rate, base_currency_code):
        actor_id, actor_name = await self.repo.rate_actor(rate)
        return {
            **{column.name: getattr(rate, column.name) for column in rate.__table__.columns},
            "base_currency_code": base_currency_code,
            "actor_id": actor_id,
            "actor_name": actor_name,
        }

    async def rates(self, company_id, actor, *, currency_id=None, limit=25, offset=0):
        enforce_actor_company(actor, company_id)
        self.enforce_currency_admin(actor)
        base = await self.repo.base(company_id)
        if base is None:
            raise HTTPException(409, "Company base currency is not configured")
        rows, total = await self.repo.rates(company_id, currency_id, limit, offset)
        return [await self.serialize_rate(row, base.code) for row in rows], total

    async def resolve_snapshot(self, company_id, payment_method, currency_code, original_amount, *, at=None):
        at = at or datetime.now(timezone.utc)
        base = await self.ensure_base(company_id)
        code = (currency_code or base.code).strip().upper()
        currency = await self.repo.by_code(company_id, code)
        if currency is None:
            raise HTTPException(409, "Payment currency is not enabled")
        accepted = {
            "cash": currency.cash_accepted,
            "card": currency.card_accepted,
            "mobile": currency.mobile_accepted,
        }.get(payment_method, currency.is_base)
        if not accepted:
            raise HTTPException(409, f"{currency.code} is not accepted for {payment_method}")
        settings = await self.repo.settings(company_id)
        if not currency.is_base and not (settings and settings.multi_currency_enabled):
            raise HTTPException(409, "Multi-currency payments are not enabled")
        if currency.is_base:
            rate, rate_id = Decimal("1"), None
        else:
            row = await self.repo.current_rate(company_id, currency.id, at)
            if row is None:
                raise HTTPException(409, f"No effective exchange rate is configured for {currency.code}")
            rate, rate_id = Decimal(row.foreign_units_per_base), row.id
        original = quantize_currency(Decimal(original_amount), currency.decimal_places)
        base_amount = quantize_currency(original / rate, base.decimal_places)
        return {
            "base_currency": base,
            "currency": currency,
            "exchange_rate_id": rate_id,
            "exchange_rate_snapshot": rate,
            "original_amount": original,
            "base_amount": base_amount,
        }

    async def resolve_from_base(self, company_id, payment_method, currency_code, base_amount, *, at=None):
        at = at or datetime.now(timezone.utc)
        base = await self.ensure_base(company_id)
        code = (currency_code or base.code).strip().upper()
        currency = await self.repo.by_code(company_id, code)
        if currency is None:
            raise HTTPException(409, "Payment currency is not enabled")
        accepted = {
            "cash": currency.cash_accepted,
            "card": currency.card_accepted,
            "mobile": currency.mobile_accepted,
        }.get(payment_method, currency.is_base)
        if not accepted:
            raise HTTPException(409, f"{currency.code} is not accepted for {payment_method}")
        settings = await self.repo.settings(company_id)
        if not currency.is_base and not (settings and settings.multi_currency_enabled):
            raise HTTPException(409, "Multi-currency payments are not enabled")
        if currency.is_base:
            rate, rate_id = Decimal("1"), None
        else:
            row = await self.repo.current_rate(company_id, currency.id, at)
            if row is None:
                raise HTTPException(409, f"No effective exchange rate is configured for {currency.code}")
            rate, rate_id = Decimal(row.foreign_units_per_base), row.id
        base_value = quantize_currency(Decimal(base_amount), base.decimal_places)
        original = quantize_currency(base_value * rate, currency.decimal_places)
        return {
            "base_currency": base, "currency": currency,
            "exchange_rate_id": rate_id, "exchange_rate_snapshot": rate,
            "original_amount": original, "base_amount": base_value,
        }
