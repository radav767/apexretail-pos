from sqlalchemy import func, select

from app.models import CashierShift, CashierShiftCurrencySnapshot, CompanyCurrency


class ShiftRepository:
    def __init__(self, db):
        self.db = db

    async def current(self, employee_id, device_id, *, for_update=False):
        query = select(CashierShift).where(
            CashierShift.employee_id == employee_id,
            CashierShift.device_id == device_id,
            CashierShift.status == "open",
        )
        if for_update:
            query = query.with_for_update()
        return (await self.db.execute(query)).scalar_one_or_none()

    async def by_id(self, company_id, shift_id, *, for_update=False):
        query = select(CashierShift).where(
            CashierShift.company_id == company_id,
            CashierShift.id == shift_id,
        )
        if for_update:
            query = query.with_for_update()
        return (await self.db.execute(query)).scalar_one_or_none()

    async def by_open_key(self, company_id, key):
        return (await self.db.execute(select(CashierShift).where(
            CashierShift.company_id == company_id,
            CashierShift.open_idempotency_key == key,
        ))).scalar_one_or_none()

    async def active_currencies(self, company_id):
        return list((await self.db.execute(select(CompanyCurrency).where(
            CompanyCurrency.company_id == company_id,
            CompanyCurrency.active.is_(True),
        ).order_by(CompanyCurrency.display_order, CompanyCurrency.code))).scalars())

    async def snapshots(self, shift_id, *, for_update=False):
        query = select(CashierShiftCurrencySnapshot).where(
            CashierShiftCurrencySnapshot.shift_id == shift_id
        ).order_by(CashierShiftCurrencySnapshot.currency_code)
        if for_update:
            query = query.with_for_update()
        return list((await self.db.execute(query)).scalars())

    async def list(self, company_id, *, branch_id=None, employee_id=None, device_id=None, status=None, start_at=None, end_at=None, limit=25, offset=0):
        query = select(CashierShift).where(CashierShift.company_id == company_id)
        for value, column in (
            (branch_id, CashierShift.branch_id), (employee_id, CashierShift.employee_id),
            (device_id, CashierShift.device_id), (status, CashierShift.status),
        ):
            if value is not None:
                query = query.where(column == value)
        if start_at is not None:
            query = query.where(CashierShift.opened_at >= start_at)
        if end_at is not None:
            query = query.where(CashierShift.opened_at < end_at)
        total = int((await self.db.execute(select(func.count()).select_from(query.order_by(None).subquery()))).scalar_one())
        rows = list((await self.db.execute(query.order_by(CashierShift.opened_at.desc(), CashierShift.id.desc()).limit(limit).offset(offset))).scalars())
        return rows, total

    async def has_open_device_shift(self, company_id, device_id):
        return (await self.db.execute(select(CashierShift.id).where(
            CashierShift.company_id == company_id,
            CashierShift.device_id == device_id,
            CashierShift.status == "open",
        ))).scalar_one_or_none() is not None
