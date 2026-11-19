from datetime import datetime

from sqlalchemy import func, select

from app.models import (
    AuditEvent, CashierShift, CompanyCurrency, CompanySetting,
    CreditReceivable, CreditSettlement, CurrencyExchangeRate, Employee,
    Expense, Sale, User,
)


class CurrencyRepository:
    def __init__(self, db):
        self.db = db

    async def settings(self, company_id, *, for_update=False):
        query = select(CompanySetting).execution_options(populate_existing=True).where(
            CompanySetting.company_id == company_id,
            CompanySetting.deleted.is_(False),
        )
        if for_update:
            query = query.with_for_update()
        return (await self.db.execute(query)).scalar_one_or_none()

    async def list(self, company_id, *, active=None, for_update=False):
        query = select(CompanyCurrency).where(CompanyCurrency.company_id == company_id)
        if active is not None:
            query = query.where(CompanyCurrency.active == active)
        if for_update:
            query = query.with_for_update()
        return list((await self.db.execute(query.order_by(CompanyCurrency.display_order, CompanyCurrency.code))).scalars())

    async def get(self, company_id, currency_id, *, for_update=False):
        query = select(CompanyCurrency).where(
            CompanyCurrency.company_id == company_id,
            CompanyCurrency.id == currency_id,
        )
        if for_update:
            query = query.with_for_update()
        return (await self.db.execute(query)).scalar_one_or_none()

    async def by_code(self, company_id, code, *, active=True):
        query = select(CompanyCurrency).where(
            CompanyCurrency.company_id == company_id,
            CompanyCurrency.code == code,
        )
        if active:
            query = query.where(CompanyCurrency.active.is_(True))
        return (await self.db.execute(query)).scalar_one_or_none()

    async def base(self, company_id):
        return (await self.db.execute(select(CompanyCurrency).where(
            CompanyCurrency.company_id == company_id,
            CompanyCurrency.is_base.is_(True),
            CompanyCurrency.active.is_(True),
        ))).scalar_one_or_none()

    async def current_rate(self, company_id, currency_id, at: datetime):
        return (await self.db.execute(select(CurrencyExchangeRate).where(
            CurrencyExchangeRate.company_id == company_id,
            CurrencyExchangeRate.currency_id == currency_id,
            CurrencyExchangeRate.effective_at <= at,
        ).order_by(CurrencyExchangeRate.effective_at.desc(), CurrencyExchangeRate.created_at.desc()).limit(1))).scalar_one_or_none()

    async def recent_effective_rates(self, company_id, currency_id, at: datetime, limit=2):
        return list((await self.db.execute(select(CurrencyExchangeRate).where(
            CurrencyExchangeRate.company_id == company_id,
            CurrencyExchangeRate.currency_id == currency_id,
            CurrencyExchangeRate.effective_at <= at,
        ).order_by(
            CurrencyExchangeRate.effective_at.desc(),
            CurrencyExchangeRate.created_at.desc(),
            CurrencyExchangeRate.id.desc(),
        ).limit(limit))).scalars())

    async def rates(self, company_id, currency_id=None, limit=25, offset=0):
        query = select(CurrencyExchangeRate).where(CurrencyExchangeRate.company_id == company_id)
        if currency_id is not None:
            query = query.where(CurrencyExchangeRate.currency_id == currency_id)
        total = int((await self.db.execute(
            select(func.count()).select_from(query.order_by(None).subquery())
        )).scalar_one())
        rows = list((await self.db.execute(
            query.order_by(
                CurrencyExchangeRate.effective_at.desc(),
                CurrencyExchangeRate.created_at.desc(),
                CurrencyExchangeRate.id.desc(),
            ).limit(limit).offset(offset)
        )).scalars())
        return rows, total

    async def rate_actor(self, rate):
        direct_user = (await self.db.execute(select(User.email).where(
            User.id == rate.created_by_user_id,
            User.company_id == rate.company_id,
        ))).scalar_one_or_none() if rate.created_by_user_id else None
        if direct_user:
            return rate.created_by_user_id, direct_user
        audit = (await self.db.execute(select(AuditEvent).where(
            AuditEvent.company_id == rate.company_id,
            AuditEvent.action == "exchange_rate_created",
            AuditEvent.details["rate_id"].as_string() == str(rate.id),
        ).order_by(AuditEvent.created_at.desc()).limit(1))).scalar_one_or_none()
        if audit is None:
            return None, "Unknown"
        if audit.actor_employee_id:
            name = (await self.db.execute(select(Employee.name).where(
                Employee.id == audit.actor_employee_id,
                Employee.company_id == rate.company_id,
            ))).scalar_one_or_none()
            return audit.actor_employee_id, name or str(audit.actor_employee_id)
        if audit.actor_user_id:
            email = (await self.db.execute(select(User.email).where(
                User.id == audit.actor_user_id,
                User.company_id == rate.company_id,
            ))).scalar_one_or_none()
            return audit.actor_user_id, email or str(audit.actor_user_id)
        return None, "Unknown"

    async def financial_activity_count(self, company_id):
        total = 0
        for model in (Sale, CreditReceivable, CreditSettlement, Expense, CashierShift):
            total += int((await self.db.execute(
                select(func.count(model.id)).where(model.company_id == company_id)
            )).scalar_one())
        total += int((await self.db.execute(
            select(func.count(CurrencyExchangeRate.id)).where(
                CurrencyExchangeRate.company_id == company_id
            )
        )).scalar_one())
        return total

    async def save(self, *objects):
        self.db.add_all(objects)
        try:
            await self.db.commit()
            await self.db.refresh(objects[0])
            return objects[0]
        except Exception:
            await self.db.rollback()
            raise
