from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import AuthActor, require_billable_body_company, require_body_permission, require_path_permission
from app.db.session import get_db
from app.expenses.repository import ExpenseRepository
from app.expenses.schema import ExpenseCategoryCreate, ExpenseCategoryOut, ExpenseCreate, ExpenseOut
from app.expenses.service import ExpenseService


router = APIRouter(prefix="/expenses", tags=["Expenses"])


def get_service(db: AsyncSession = Depends(get_db)):
    return ExpenseService(ExpenseRepository(db))


@router.post("/categories", response_model=ExpenseCategoryOut)
async def create_category(data: ExpenseCategoryCreate, service: ExpenseService = Depends(get_service), actor: AuthActor = Depends(require_body_permission("expenses_manage")), _entitlement: None = Depends(require_billable_body_company)):
    return await service.create_category(data, actor)


@router.get("/categories/{company_id}", response_model=list[ExpenseCategoryOut])
async def list_categories(company_id: UUID, active: bool | None = None, service: ExpenseService = Depends(get_service), actor: AuthActor = Depends(require_path_permission("expenses_manage"))):
    return await service.list_categories(company_id, actor, active)


@router.post("", response_model=ExpenseOut)
async def create_expense(data: ExpenseCreate, service: ExpenseService = Depends(get_service), actor: AuthActor = Depends(require_body_permission("expenses_manage")), _entitlement: None = Depends(require_billable_body_company)):
    return await service.create_expense(data, actor)


@router.get("/{company_id}", response_model=list[ExpenseOut])
async def list_expenses(company_id: UUID, start_at: datetime | None = None, end_at: datetime | None = None, branch_id: UUID | None = None, category_id: UUID | None = None, payment_method: str | None = Query(default=None, pattern="^(cash|card|mobile)$"), employee_id: UUID | None = None, limit: int = Query(100, ge=1, le=500), offset: int = Query(0, ge=0), service: ExpenseService = Depends(get_service), actor: AuthActor = Depends(require_path_permission("expense_reports"))):
    return await service.list_expenses(company_id, actor, start_at=start_at, end_at=end_at, branch_id=branch_id, category_id=category_id, payment_method=payment_method, employee_id=employee_id, limit=limit, offset=offset)
