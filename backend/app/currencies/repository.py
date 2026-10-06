from datetime import datetime

from sqlalchemy import and_, select

from app.models import CompanyCurrency, CompanySetting, CurrencyExchangeRate


class CurrencyRepository:
    def __init__(self, db):
        self.db = db

    async def settings(self, company_id, *, for_update=False):
        query = select(CompanySetting).where(
            CompanySetting.company_id == company_id,
            CompanySetting.deleted.is_(False),
        )
        if for_update:
            query = query.with_for_update()
        return (await self.db.execute(query)).scalar_one_or_none()

    async def list(self, company_id, *, active=None):
        query = select(CompanyCurrency).where(CompanyCurrency.company_id == company_id)
        if active is not None:
            query = query.where(CompanyCurrency.active == active)
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

    async def rates(self, company_id, currency_id=None, limit=100):
        query = select(CurrencyExchangeRate).where(CurrencyExchangeRate.company_id == company_id)
        if currency_id is not None:
            query = query.where(CurrencyExchangeRate.currency_id == currency_id)
        return list((await self.db.execute(query.order_by(CurrencyExchangeRate.effective_at.desc()).limit(limit))).scalars())

    async def save(self, *objects):
        self.db.add_all(objects)
        try:
            await self.db.commit()
            await self.db.refresh(objects[0])
            return objects[0]
        except Exception:
            await self.db.rollback()
            raise
