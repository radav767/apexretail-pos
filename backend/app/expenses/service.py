from fastapi import HTTPException

from app.expenses.repository import ExpenseRepository
from app.expenses.schema import ExpenseCategoryCreate, ExpenseCategoryUpdate, ExpenseCreate
from app.financial_access import enforce_actor_branch, enforce_actor_company
from app.models import AuditEvent, Expense, ExpenseCategory


class ExpenseService:
    def __init__(self, repo: ExpenseRepository):
        self.repo = repo

    async def create_category(self, data: ExpenseCategoryCreate, actor):
        enforce_actor_company(actor, data.company_id)
        name = data.name.strip()
        if await self.repo.find_category_name(data.company_id, name):
            raise HTTPException(409, "Expense category already exists")
        category = ExpenseCategory(company_id=data.company_id, name=name, description=(data.description or "").strip() or None, active=True, deleted=False)
        audit = AuditEvent(company_id=data.company_id, actor_user_id=actor.user.id if actor.actor_type == "user" else None, actor_employee_id=actor.employee.id if actor.actor_type == "employee" else None, action="expense_category_created", details={"name": name})
        return await self.repo.save(category, audit)

    async def list_categories(self, company_id, actor, active=None):
        enforce_actor_company(actor, company_id)
        return await self.repo.list_categories(company_id, active)

    async def update_category(self, company_id, category_id, data: ExpenseCategoryUpdate, actor):
        enforce_actor_company(actor, company_id)
        category = await self.repo.get_category(company_id, category_id, active_only=False)
        if not category:
            raise HTTPException(404, "Expense category not found")
        values = data.model_dump(exclude_unset=True)
        if "name" in values:
            name = values["name"].strip()
            if await self.repo.find_category_name(company_id, name, category.id):
                raise HTTPException(409, "Expense category already exists")
            values["name"] = name
        if "description" in values:
            values["description"] = (values["description"] or "").strip() or None
        for key, value in values.items():
            setattr(category, key, value)
        audit = AuditEvent(company_id=company_id, actor_user_id=actor.user.id if actor.actor_type == "user" else None, actor_employee_id=actor.employee.id if actor.actor_type == "employee" else None, action="expense_category_updated", details={"category_id": str(category.id), "changes": sorted(values)})
        return await self.repo.save(category, audit)

    async def delete_category(self, company_id, category_id, actor):
        enforce_actor_company(actor, company_id)
        category = await self.repo.get_category(company_id, category_id, active_only=False)
        if not category:
            raise HTTPException(404, "Expense category not found")
        if await self.repo.category_expense_count(company_id, category.id):
            raise HTTPException(409, "Expense categories used by posted expenses cannot be deleted; deactivate the category instead")
        audit = AuditEvent(company_id=company_id, actor_user_id=actor.user.id if actor.actor_type == "user" else None, actor_employee_id=actor.employee.id if actor.actor_type == "employee" else None, action="expense_category_deleted", details={"category_id": str(category.id), "name": category.name})
        await self.repo.delete_category(category, audit)

    async def create_expense(self, data: ExpenseCreate, actor):
        enforce_actor_company(actor, data.company_id)
        enforce_actor_branch(actor, data.branch_id)
        existing = await self.repo.get_by_key(data.company_id, data.idempotency_key)
        if existing:
            if (
                existing.category_id != data.category_id
                or existing.branch_id != data.branch_id
                or existing.amount != data.amount
                or existing.payment_method != data.payment_method
            ):
                raise HTTPException(409, "Idempotency key was already used for a different expense")
            return existing
        branch = await self.repo.get_branch(data.company_id, data.branch_id)
        if not branch:
            raise HTTPException(404, "Branch not found")
        category = await self.repo.get_category(data.company_id, data.category_id)
        if not category:
            raise HTTPException(404, "Expense category not found")
        if data.occurred_at.tzinfo is None or data.occurred_at.utcoffset() is None:
            raise HTTPException(400, "occurred_at must include a timezone")
        expense = Expense(
            company_id=data.company_id, category_id=category.id, shop_id=branch.shop_id,
            branch_id=branch.id, actor_user_id=actor.user.id if actor.actor_type == "user" else None,
            employee_id=actor.employee.id if actor.actor_type == "employee" else None,
            amount=data.amount, currency_code=await self.repo.currency_code(data.company_id),
            occurred_at=data.occurred_at, payment_method=data.payment_method,
            description=data.description.strip(), reference=(data.reference or "").strip() or None,
            idempotency_key=data.idempotency_key.strip(),
        )
        audit = AuditEvent(company_id=data.company_id, actor_user_id=expense.actor_user_id, actor_employee_id=expense.employee_id, action="expense_posted", details={"amount": str(data.amount), "payment_method": data.payment_method, "category_id": str(category.id)})
        return await self.repo.save(expense, audit)

    async def list_expenses(self, company_id, actor, **filters):
        enforce_actor_company(actor, company_id)
        branch_id = filters.get("branch_id")
        if actor.actor_type == "employee" and actor.role not in {"owner", "administrator"}:
            if branch_id is not None:
                enforce_actor_branch(actor, branch_id)
            filters["branch_id"] = actor.employee.branch_id
        rows = await self.repo.list_expenses(company_id, **filters)
        return [{**{column.name: getattr(expense, column.name) for column in expense.__table__.columns}, "category_name": category_name} for expense, category_name in rows]
