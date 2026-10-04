from sqlalchemy import func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import CreditReceivable, Customer


class CustomerRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def code_exists(self, company_id, code, excluding_id=None):
        query = select(Customer.id).where(Customer.company_id == company_id, Customer.customer_code == code, Customer.deleted.is_(False))
        if excluding_id is not None:
            query = query.where(Customer.id != excluding_id)
        return (await self.db.execute(query)).scalar_one_or_none() is not None

    async def get(self, company_id, customer_id, *, for_update=False, active_only=False):
        query = select(Customer).where(Customer.company_id == company_id, Customer.id == customer_id, Customer.deleted.is_(False))
        if active_only:
            query = query.where(Customer.active.is_(True))
        if for_update:
            query = query.with_for_update()
        return (await self.db.execute(query)).scalar_one_or_none()

    async def balance(self, company_id, customer_id):
        result = await self.db.execute(select(func.coalesce(func.sum(CreditReceivable.outstanding_balance), 0)).where(CreditReceivable.company_id == company_id, CreditReceivable.customer_id == customer_id))
        return result.scalar_one()

    async def list(self, company_id, *, search=None, active=None, limit=100, offset=0):
        balance = func.coalesce(func.sum(CreditReceivable.outstanding_balance), 0).label("outstanding_balance")
        query = select(Customer, balance).outerjoin(
            CreditReceivable,
            (CreditReceivable.customer_id == Customer.id) & (CreditReceivable.company_id == Customer.company_id),
        ).where(Customer.company_id == company_id, Customer.deleted.is_(False))
        if search:
            value = f"%{search.strip()}%"
            query = query.where(or_(Customer.name.ilike(value), Customer.customer_code.ilike(value), Customer.phone.ilike(value)))
        if active is not None:
            query = query.where(Customer.active == active)
        query = query.group_by(Customer.id).order_by(Customer.name, Customer.id).limit(limit).offset(offset)
        return (await self.db.execute(query)).all()

    async def save(self, customer):
        self.db.add(customer)
        await self.db.commit()
        await self.db.refresh(customer)
        return customer

    async def history(self, company_id, customer_id):
        result = await self.db.execute(text("""
            SELECT 'credit_sale' transaction_type, cr.id transaction_id,
                   cr.sale_id, s.receipt_number, cr.original_amount amount,
                   'credit' payment_method, cr.branch_id, cr.created_at occurred_at,
                   cr.due_date, NULL::varchar reference,
                   cr.cashier_employee_id actor_id,
                   COALESCE(emp.name, cr.cashier_employee_id::text, 'Unknown') actor_name
              FROM credit_receivables cr
              JOIN sales s ON s.id=cr.sale_id AND s.company_id=cr.company_id
              LEFT JOIN employees emp ON emp.id=cr.cashier_employee_id
               AND emp.company_id=cr.company_id AND emp.active=true AND emp.deleted=false
             WHERE cr.company_id=:company_id AND cr.customer_id=:customer_id
            UNION ALL
            SELECT 'settlement', cs.id, cr.sale_id, cs.receipt_number,
                   -cs.amount, cs.payment_method, cs.branch_id, cs.received_at,
                   NULL::date, cs.reference,
                   COALESCE(cs.cashier_employee_id, cs.actor_user_id) actor_id,
                   COALESCE(settle_emp.name, settle_user.email,
                            cs.cashier_employee_id::text, cs.actor_user_id::text, 'Unknown') actor_name
              FROM credit_settlements cs
              JOIN credit_receivables cr ON cr.id=cs.receivable_id AND cr.company_id=cs.company_id
              LEFT JOIN employees settle_emp ON settle_emp.id=cs.cashier_employee_id
               AND settle_emp.company_id=cs.company_id AND settle_emp.active=true AND settle_emp.deleted=false
              LEFT JOIN users settle_user ON settle_user.id=cs.actor_user_id
               AND settle_user.company_id=cs.company_id AND settle_user.active=true AND settle_user.deleted=false
             WHERE cs.company_id=:company_id AND cs.customer_id=:customer_id
            ORDER BY occurred_at, transaction_id
        """), {"company_id": company_id, "customer_id": customer_id})
        return [dict(row) for row in result.mappings().all()]
