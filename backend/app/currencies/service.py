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

    async def ensure_base(self, company_id):
        base = await self.repo.base(company_id)
        if base is not None:
            return base
        settings = await self.repo.settings(company_id, for_update=True)
        code = str(getattr(settings, "currency_code", None) or "USD").strip().upper()
        symbol = str(getattr(settings, "currency_symbol", None) or "$").strip() or "$"
        places = min(max(int(getattr(settings, "decimal_places", 2) or 2), 0), 2)
        base = CompanyCurrency(
            company_id=company_id, code=code, display_name=code, symbol=symbol,
            decimal_places=places, active=True, is_base=True,
            cash_accepted=True, card_accepted=True, mobile_accepted=True, display_order=0,
        )
        self.repo.db.add(base)
        await self.repo.db.flush()
        if settings is not None:
            settings.base_currency_id = base.id
        return base

    async def serialize(self, currency, *, at=None):
        rate = None if currency.is_base else await self.repo.current_rate(
            currency.company_id, currency.id, at or datetime.now(timezone.utc)
        )
        values = {column.name: getattr(currency, column.name) for column in currency.__table__.columns}
        values.update({
            "current_rate": Decimal("1") if currency.is_base else (rate.foreign_units_per_base if rate else None),
            "current_rate_id": rate.id if rate else None,
            "rate_effective_at": rate.effective_at if rate else None,
        })
        return values

    async def list(self, company_id, actor, *, active=None, at=None):
        enforce_actor_company(actor, company_id)
        return [await self.serialize(row, at=at) for row in await self.repo.list(company_id, active=active)]

    async def pos_config(self, company_id, actor):
        enforce_actor_company(actor, company_id)
        generated_at = datetime.now(timezone.utc)
        base = await self.repo.base(company_id)
        settings = await self.repo.settings(company_id)
        if base is None or settings is None:
            raise HTTPException(409, "Company currency configuration is incomplete")
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
        settings = await self.repo.settings(data.company_id, for_update=True)
        if settings is None:
            raise HTTPException(404, "Company settings not found")
        if data.is_base:
            if await self.repo.base(data.company_id):
                raise HTTPException(409, "A base currency already exists")
            if data.decimal_places > 2:
                raise HTTPException(409, "Base accounting currency currently supports at most two decimal places")
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

    async def update(self, company_id, currency_id, data: CurrencyUpdate, actor):
        enforce_actor_company(actor, company_id)
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

    async def create_rate(self, data: ExchangeRateCreate, actor):
        enforce_actor_company(actor, data.company_id)
        if data.effective_at.tzinfo is None or data.effective_at.utcoffset() is None:
            raise HTTPException(400, "effective_at must include a timezone")
        currency = await self.repo.get(data.company_id, data.currency_id, for_update=True)
        settings = await self.repo.settings(data.company_id, for_update=True)
        if currency is None or settings is None:
            raise HTTPException(404, "Currency not found")
        if currency.is_base:
            raise HTTPException(409, "The base currency always has an exchange rate of 1")
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
            details={"currency": currency.code, "rate": str(rate.foreign_units_per_base), "effective_at": rate.effective_at.isoformat()},
        )
        try:
            return await self.repo.save(rate, settings, audit)
        except IntegrityError as exc:
            raise HTTPException(409, "An exchange rate already exists at that effective time") from exc

    async def rates(self, company_id, actor, *, currency_id=None, limit=100):
        enforce_actor_company(actor, company_id)
        return await self.repo.rates(company_id, currency_id, limit)

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
