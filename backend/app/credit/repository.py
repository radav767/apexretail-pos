from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Branch, CreditReceivable, CreditSettlement, Customer, Sale, Shop


class CreditRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_branch(self, company_id, branch_id):
        result = await self.db.execute(select(Branch).where(Branch.company_id == company_id, Branch.id == branch_id, Branch.active.is_(True), Branch.deleted.is_(False)))
        return result.scalar_one_or_none()

    async def get_receivable(self, company_id, receivable_id, *, for_update=False):
        query = select(CreditReceivable).where(CreditReceivable.company_id == company_id, CreditReceivable.id == receivable_id)
        if for_update:
            query = query.with_for_update()
        return (await self.db.execute(query)).scalar_one_or_none()

    async def get_settlement_by_key(self, company_id, key):
        result = await self.db.execute(select(CreditSettlement).where(CreditSettlement.company_id == company_id, CreditSettlement.idempotency_key == key))
        return result.scalar_one_or_none()

    async def list_receivables(self, company_id, *, customer_id=None, branch_id=None, status=None, limit=100, offset=0):
        query = select(
            CreditReceivable,
            Customer.name.label("customer_name"), Customer.customer_code.label("customer_code"),
            Sale.receipt_number.label("sale_receipt_number"),
        ).join(Customer, (Customer.id == CreditReceivable.customer_id) & (Customer.company_id == CreditReceivable.company_id)).join(Sale, (Sale.id == CreditReceivable.sale_id) & (Sale.company_id == CreditReceivable.company_id)).where(CreditReceivable.company_id == company_id)
        if customer_id is not None:
            query = query.where(CreditReceivable.customer_id == customer_id)
        if branch_id is not None:
            query = query.where(CreditReceivable.branch_id == branch_id)
        if status is not None:
            query = query.where(CreditReceivable.status == status)
        return (await self.db.execute(query.order_by(CreditReceivable.created_at.desc(), CreditReceivable.id).limit(limit).offset(offset))).all()

    async def list_settlements(self, company_id, *, receivable_id=None, customer_id=None, branch_id=None, limit=100, offset=0):
        query = select(CreditSettlement).where(CreditSettlement.company_id == company_id)
        if receivable_id is not None:
            query = query.where(CreditSettlement.receivable_id == receivable_id)
        if customer_id is not None:
            query = query.where(CreditSettlement.customer_id == customer_id)
        if branch_id is not None:
            query = query.where(CreditSettlement.branch_id == branch_id)
        return list((await self.db.execute(query.order_by(CreditSettlement.received_at.desc(), CreditSettlement.id).limit(limit).offset(offset))).scalars().all())

    async def save_settlement(self, receivable, settlement, audit):
        self.db.add(receivable)
        self.db.add(settlement)
        self.db.add(audit)
        try:
            await self.db.commit()
            await self.db.refresh(settlement)
            return settlement
        except Exception:
            await self.db.rollback()
            raise
