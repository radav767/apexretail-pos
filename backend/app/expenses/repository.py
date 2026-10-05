from sqlalchemy import String, and_, case, cast, func, literal, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Branch, CompanySetting, Employee, Expense, ExpenseCategory, User


class ExpenseRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_branch(self, company_id, branch_id):
        return (await self.db.execute(select(Branch).where(Branch.company_id == company_id, Branch.id == branch_id, Branch.active.is_(True), Branch.deleted.is_(False)))).scalar_one_or_none()

    async def get_category(self, company_id, category_id, active_only=True):
        query = select(ExpenseCategory).where(ExpenseCategory.company_id == company_id, ExpenseCategory.id == category_id, ExpenseCategory.deleted.is_(False))
        if active_only:
            query = query.where(ExpenseCategory.active.is_(True))
        return (await self.db.execute(query)).scalar_one_or_none()

    async def find_category_name(self, company_id, name, excluding_id=None):
        query = select(ExpenseCategory.id).where(ExpenseCategory.company_id == company_id, ExpenseCategory.name == name, ExpenseCategory.deleted.is_(False))
        if excluding_id is not None:
            query = query.where(ExpenseCategory.id != excluding_id)
        return (await self.db.execute(query)).scalar_one_or_none()

    async def category_expense_count(self, company_id, category_id):
        return (await self.db.execute(select(func.count(Expense.id)).where(Expense.company_id == company_id, Expense.category_id == category_id))).scalar_one()

    async def delete_category(self, category, audit):
        self.db.add(audit)
        await self.db.delete(category)
        try:
            await self.db.commit()
        except Exception:
            await self.db.rollback()
            raise

    async def currency_code(self, company_id):
        value = (await self.db.execute(select(CompanySetting.currency_code).where(CompanySetting.company_id == company_id, CompanySetting.deleted.is_(False)))).scalar_one_or_none()
        return value or "USD"

    async def get_by_key(self, company_id, key):
        return (await self.db.execute(select(Expense).where(Expense.company_id == company_id, Expense.idempotency_key == key))).scalar_one_or_none()

    async def save(self, *objects):
        self.db.add_all(objects)
        try:
            await self.db.commit()
            await self.db.refresh(objects[0])
            return objects[0]
        except Exception:
            await self.db.rollback()
            raise

    async def list_categories(self, company_id, active=None):
        query = select(ExpenseCategory).where(ExpenseCategory.company_id == company_id, ExpenseCategory.deleted.is_(False))
        if active is not None:
            query = query.where(ExpenseCategory.active == active)
        return list((await self.db.execute(query.order_by(ExpenseCategory.name))).scalars().all())

    async def list_expenses(self, company_id, *, start_at=None, end_at=None, branch_id=None, category_id=None, payment_method=None, employee_id=None, actor_user_id=None, actor_id=None, search=None, limit=100, offset=0, with_total=False):
        actor_filter = actor_id
        resolved_actor_id = func.coalesce(Expense.employee_id, Expense.actor_user_id).label("actor_id")
        actor_name = func.coalesce(
            Employee.name,
            User.email,
            cast(resolved_actor_id, String),
            literal("Unknown"),
        ).label("actor_name")
        query = select(Expense, ExpenseCategory.name.label("category_name"), resolved_actor_id, actor_name).join(
            ExpenseCategory,
            (ExpenseCategory.id == Expense.category_id) & (ExpenseCategory.company_id == Expense.company_id),
        ).outerjoin(
            Employee,
            and_(
                Employee.id == Expense.employee_id,
                Employee.company_id == Expense.company_id,
                Employee.active.is_(True),
                Employee.deleted.is_(False),
            ),
        ).outerjoin(
            User,
            and_(
                User.id == Expense.actor_user_id,
                User.company_id == Expense.company_id,
                User.active.is_(True),
                User.deleted.is_(False),
            ),
        ).where(Expense.company_id == company_id)
        for value, column, operator in (
            (start_at, Expense.occurred_at, "ge"), (end_at, Expense.occurred_at, "lt"),
            (branch_id, Expense.branch_id, "eq"), (category_id, Expense.category_id, "eq"),
            (payment_method, Expense.payment_method, "eq"), (employee_id, Expense.employee_id, "eq"),
            (actor_user_id, Expense.actor_user_id, "eq"),
        ):
            if value is not None:
                query = query.where(getattr(column, f"__{operator}__")(value))
        if search:
            value = f"%{search.strip()}%"
            query = query.where(or_(Expense.reference.ilike(value), Expense.description.ilike(value)))
        if actor_filter is not None:
            query = query.where(or_(Expense.employee_id == actor_filter, Expense.actor_user_id == actor_filter))
        total = None
        summary = None
        if with_total:
            matching = query.with_only_columns(Expense.id, maintain_column_froms=True).order_by(None).subquery()
            total = int((await self.db.execute(select(func.count()).select_from(matching))).scalar_one())
            values = (await self.db.execute(select(
                func.coalesce(func.sum(Expense.amount), 0),
                func.coalesce(func.sum(case((Expense.payment_method == "cash", Expense.amount), else_=0)), 0),
                func.coalesce(func.sum(case((Expense.payment_method == "card", Expense.amount), else_=0)), 0),
                func.coalesce(func.sum(case((Expense.payment_method == "mobile", Expense.amount), else_=0)), 0),
            ).where(Expense.id.in_(select(matching.c.id))))).one()
            summary = dict(zip(("total", "cash", "card", "mobile"), values))
        rows = (await self.db.execute(query.order_by(Expense.occurred_at.desc(), Expense.id.desc()).limit(limit).offset(offset))).all()
        return (rows, total, summary) if with_total else rows

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
