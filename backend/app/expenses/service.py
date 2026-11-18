from datetime import datetime, timezone
from decimal import Decimal

from fastapi import HTTPException
from app.printing.service import permit
from app import financial_commands
from app.subscriptions.write_policy import require_new_write

from app.expenses.repository import ExpenseRepository
from app.expenses.schema import ExpenseCategoryCreate, ExpenseCategoryUpdate, ExpenseCreate
from app.financial_access import enforce_actor_branch, enforce_actor_company
from app.models import AuditEvent, Expense, ExpenseCategory
from app.currencies.repository import CurrencyRepository
from app.currencies.service import CurrencyService
from app.financial_context import resolve_shift_for_write


class ExpenseService:
    def __init__(self, repo: ExpenseRepository):
        self.repo = repo

    @staticmethod
    def validate_currency_quote(data, snapshot, current_version):
        if data.currency_config_version is not None and current_version is not None and current_version != data.currency_config_version:
            raise HTTPException(409, "Payment currency configuration changed. Refresh the expense quote and try again.")
        if data.exchange_rate_id is not None and data.exchange_rate_id != snapshot["exchange_rate_id"]:
            raise HTTPException(409, "Exchange rate changed. Refresh the expense quote and try again.")
        if data.exchange_rate_snapshot is not None and Decimal(data.exchange_rate_snapshot) != Decimal(snapshot["exchange_rate_snapshot"]):
            raise HTTPException(409, "Exchange rate snapshot changed. Refresh the expense quote and try again.")

    async def attach_actor(self, expense):
        actor_id, actor_name = await self.repo.actor_identity(
            expense.company_id, expense.employee_id, expense.actor_user_id,
        )
        expense.actor_id = actor_id
        expense.actor_name = actor_name
        return expense

    async def create_category(self, data: ExpenseCategoryCreate, actor):
        permit(actor, "expenses_manage")
        enforce_actor_company(actor, data.company_id)
        await require_new_write(self.repo.db, data.company_id)
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
        permit(actor, "expenses_manage")
        enforce_actor_company(actor, company_id)
        await require_new_write(self.repo.db, company_id)
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
        permit(actor, "expenses_manage")
        enforce_actor_company(actor, company_id)
        await require_new_write(self.repo.db, company_id)
        category = await self.repo.get_category(company_id, category_id, active_only=False)
        if not category:
            raise HTTPException(404, "Expense category not found")
        if await self.repo.category_expense_count(company_id, category.id):
            raise HTTPException(409, "Expense categories used by posted expenses cannot be deleted; deactivate the category instead")
        audit = AuditEvent(company_id=company_id, actor_user_id=actor.user.id if actor.actor_type == "user" else None, actor_employee_id=actor.employee.id if actor.actor_type == "employee" else None, action="expense_category_deleted", details={"category_id": str(category.id), "name": category.name})
        await self.repo.delete_category(category, audit)

    async def create_expense(self, data: ExpenseCreate, actor):
        permit(actor, "expenses_create")
        enforce_actor_company(actor, data.company_id)
        enforce_actor_branch(actor, data.branch_id)
        data = data.model_copy()
        command_hash = await financial_commands.lock_command(self.repo.db, "expenses", data, actor)
        existing = await self.repo.get_by_key(data.company_id, data.idempotency_key)
        if existing:
            await financial_commands.verify_replay(self.repo.db, existing, data, actor, command_hash)
            return await self.attach_actor(existing)
        await require_new_write(self.repo.db, data.company_id)

        branch = await self.repo.get_branch(data.company_id, data.branch_id)
        if not branch:
            raise HTTPException(404, "Branch not found")
        category = await self.repo.get_category(data.company_id, data.category_id)
        if not category:
            raise HTTPException(404, "Expense category not found")
        if data.occurred_at.tzinfo is None or data.occurred_at.utcoffset() is None:
            raise HTTPException(400, "occurred_at must include a timezone")
        shift = await resolve_shift_for_write(
            self.repo.db, actor, data.company_id, branch.id, data.shift_id,
            attach_active=True,
        )
        original_input = data.original_amount if data.original_amount is not None else data.amount
        if original_input is None:
            raise HTTPException(400, "Expense amount is required")
        currency_repository = CurrencyRepository(self.repo.db)
        settings = await currency_repository.settings(data.company_id, for_update=True)
        current_version = int(getattr(settings, "currency_config_version", 0) or 0) if settings is not None else None
        snapshot = await CurrencyService(currency_repository).resolve_snapshot(
            data.company_id, data.payment_method, data.currency_code,
            original_input, at=datetime.now(timezone.utc),
        )
        self.validate_currency_quote(data, snapshot, current_version)
        if Decimal(original_input) != Decimal(snapshot["original_amount"]):
            raise HTTPException(400, "Expense amount exceeds the selected currency precision")
        base_amount = Decimal(snapshot["base_amount"]).quantize(Decimal("0.01"))
        if data.amount is not None and data.original_amount is not None and Decimal(data.amount).quantize(Decimal("0.01")) != base_amount:
            raise HTTPException(409, "Expense base amount does not match the authoritative currency conversion")
        expense = Expense(
            company_id=data.company_id, category_id=category.id, shop_id=branch.shop_id,
            branch_id=branch.id, actor_user_id=actor.user.id if actor.actor_type == "user" else None,
            employee_id=actor.employee.id if actor.actor_type == "employee" else None,
            device_id=shift.device_id if shift else (actor.pos_session.device_id if actor.actor_type == "employee" and actor.pos_session else None),
            shift_id=shift.id if shift else None,
            amount=base_amount, currency_code=snapshot["currency"].code,
            base_currency_code=snapshot["base_currency"].code,
            exchange_rate_id=snapshot["exchange_rate_id"],
            exchange_rate_snapshot=snapshot["exchange_rate_snapshot"],
            original_amount=snapshot["original_amount"],
            occurred_at=data.occurred_at, payment_method=data.payment_method,
            description=data.description.strip(), reference=(data.reference or "").strip() or None,
            idempotency_key=data.idempotency_key.strip(),
        )
        audit = AuditEvent(company_id=data.company_id, actor_user_id=expense.actor_user_id, actor_employee_id=expense.employee_id, device_id=expense.device_id, action="expense_posted", details={"amount": str(base_amount), "original_amount": str(expense.original_amount), "currency": expense.currency_code, "rate": str(expense.exchange_rate_snapshot), "payment_method": data.payment_method, "category_id": str(category.id), "shift_id": str(expense.shift_id) if expense.shift_id else None})
        await financial_commands.stamp(self.repo.db, expense, actor, command_hash)
        return await self.attach_actor(await self.repo.save(expense, audit))

    async def list_expenses(self, company_id, actor, **filters):
        enforce_actor_company(actor, company_id)
        branch_id = filters.get("branch_id")
        if actor.actor_type == "employee" and actor.role not in {"owner", "administrator"}:
            if branch_id is not None:
                enforce_actor_branch(actor, branch_id)
            filters["branch_id"] = actor.employee.branch_id
        rows = await self.repo.list_expenses(company_id, **filters)
        total = None
        summary = None
        if filters.get("with_total"):
            rows, total, summary = rows
        items = [{
            **{column.name: getattr(expense, column.name) for column in expense.__table__.columns},
            "category_name": category_name, "actor_id": actor_id, "actor_name": actor_name,
        } for expense, category_name, actor_id, actor_name in rows]
        return (items, total, summary) if total is not None else items
