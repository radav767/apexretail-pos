from sqlalchemy import String, and_, cast, func, literal, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Branch, CreditReceivable, CreditSettlement, Customer, Employee, Sale, Shop, User


class CreditRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_branch(self, company_id, branch_id):
        result = await self.db.execute(select(Branch).where(Branch.company_id == company_id, Branch.id == branch_id, Branch.active.is_(True), Branch.deleted.is_(False)))
        return result.scalar_one_or_none()

    async def get_receivable(self, company_id, receivable_id, *, for_update=False):
        query = select(CreditReceivable).where(CreditReceivable.company_id == company_id, CreditReceivable.id == receivable_id)
        if for_update:
            query = query.with_for_update().execution_options(populate_existing=True)
        return (await self.db.execute(query)).scalar_one_or_none()

    async def get_settlement_by_key(self, company_id, key):
        result = await self.db.execute(select(CreditSettlement).where(CreditSettlement.company_id == company_id, CreditSettlement.idempotency_key == key))
        return result.scalar_one_or_none()

    async def list_receivables(self, company_id, *, customer_id=None, branch_id=None, status=None, start_at=None, end_at=None, search=None, limit=100, offset=0, with_total=False):
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
            if status == "overdue":
                query = query.where(CreditReceivable.outstanding_balance > 0, CreditReceivable.due_date < func.current_date())
            elif status == "outstanding":
                query = query.where(CreditReceivable.status.in_(("unpaid", "partially_paid")))
            elif status == "open":
                query = query.where(CreditReceivable.status == "unpaid")
            else:
                query = query.where(CreditReceivable.status == status)
        if start_at is not None: query = query.where(CreditReceivable.created_at >= start_at)
        if end_at is not None: query = query.where(CreditReceivable.created_at < end_at)
        if search:
            value = f"%{search.strip()}%"
            query = query.where(Sale.receipt_number.ilike(value))
        total = int((await self.db.execute(select(func.count()).select_from(query.order_by(None).subquery()))).scalar_one()) if with_total else None
        rows = (await self.db.execute(query.order_by(CreditReceivable.created_at.desc(), CreditReceivable.id.desc()).limit(limit).offset(offset))).all()
        return (rows, total) if with_total else rows

    async def list_settlements(self, company_id, *, receivable_id=None, customer_id=None, branch_id=None, status=None, payment_method=None, start_at=None, end_at=None, search=None, limit=100, offset=0, with_total=False):
        actor_id = func.coalesce(CreditSettlement.cashier_employee_id, CreditSettlement.actor_user_id).label("actor_id")
        actor_name = func.coalesce(
            Employee.name,
            User.email,
            cast(actor_id, String),
            literal("Unknown"),
        ).label("actor_name")
        query = select(
            CreditSettlement, actor_id, actor_name,
            Customer.name.label("customer_name"), Customer.customer_code.label("customer_code"),
            Sale.receipt_number.label("sale_receipt_number"),
        ).outerjoin(
            Employee,
            and_(
                Employee.id == CreditSettlement.cashier_employee_id,
                Employee.company_id == CreditSettlement.company_id,
                Employee.active.is_(True),
                Employee.deleted.is_(False),
            ),
        ).outerjoin(
            User,
            and_(
                User.id == CreditSettlement.actor_user_id,
                User.company_id == CreditSettlement.company_id,
                User.active.is_(True),
                User.deleted.is_(False),
            ),
        ).join(CreditReceivable, and_(CreditReceivable.id == CreditSettlement.receivable_id, CreditReceivable.company_id == CreditSettlement.company_id)).join(Customer, and_(Customer.id == CreditSettlement.customer_id, Customer.company_id == CreditSettlement.company_id)).join(Sale, and_(Sale.id == CreditReceivable.sale_id, Sale.company_id == CreditSettlement.company_id)).where(CreditSettlement.company_id == company_id)
        if receivable_id is not None:
            query = query.where(CreditSettlement.receivable_id == receivable_id)
        if customer_id is not None:
            query = query.where(CreditSettlement.customer_id == customer_id)
        if branch_id is not None:
            query = query.where(CreditSettlement.branch_id == branch_id)
        if status is not None:
            if status == "overdue": query = query.where(CreditReceivable.outstanding_balance > 0, CreditReceivable.due_date < func.current_date())
            elif status == "outstanding": query = query.where(CreditReceivable.status.in_(("unpaid", "partially_paid")))
            elif status == "open": query = query.where(CreditReceivable.status == "unpaid")
            else: query = query.where(CreditReceivable.status == status)
        if payment_method is not None: query = query.where(CreditSettlement.payment_method == payment_method)
        if start_at is not None: query = query.where(CreditSettlement.received_at >= start_at)
        if end_at is not None: query = query.where(CreditSettlement.received_at < end_at)
        if search:
            value = f"%{search.strip()}%"
            query = query.where(CreditSettlement.reference.ilike(value) | CreditSettlement.receipt_number.ilike(value) | Sale.receipt_number.ilike(value))
        total = int((await self.db.execute(select(func.count()).select_from(query.order_by(None).subquery()))).scalar_one()) if with_total else None
        rows = (await self.db.execute(query.order_by(CreditSettlement.received_at.desc(), CreditSettlement.id.desc()).limit(limit).offset(offset))).all()
        return (rows, total) if with_total else rows

    async def actor_identity(self, company_id, employee_id=None, user_id=None):
        actor_id = employee_id or user_id
        name = None
        if employee_id is not None:
            name = (await self.db.execute(select(Employee.name).where(
                Employee.id == employee_id, Employee.company_id == company_id,
                Employee.active.is_(True), Employee.deleted.is_(False),
            ))).scalar_one_or_none()
        elif user_id is not None:
            name = (await self.db.execute(select(User.email).where(
                User.id == user_id, User.company_id == company_id,
                User.active.is_(True), User.deleted.is_(False),
            ))).scalar_one_or_none()
        return actor_id, name or (str(actor_id) if actor_id else "Unknown")

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
