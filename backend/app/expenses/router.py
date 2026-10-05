from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import AuthActor, require_billable_body_company, require_body_permission, require_path_permission
from app.db.session import get_db
from app.expenses.repository import ExpenseRepository
from app.expenses.schema import ExpenseCategoryCreate, ExpenseCategoryOut, ExpenseCategoryUpdate, ExpenseCreate, ExpenseOut
from app.expenses.service import ExpenseService
from app.pagination import Page, page_response


router = APIRouter(prefix="/expenses", tags=["Expenses"])


def get_service(db: AsyncSession = Depends(get_db)):
    return ExpenseService(ExpenseRepository(db))


@router.post("/categories", response_model=ExpenseCategoryOut)
async def create_category(data: ExpenseCategoryCreate, service: ExpenseService = Depends(get_service), actor: AuthActor = Depends(require_body_permission("expenses_manage")), _entitlement: None = Depends(require_billable_body_company)):
    return await service.create_category(data, actor)


@router.get("/categories/{company_id}", response_model=list[ExpenseCategoryOut])
async def list_categories(company_id: UUID, active: bool | None = None, service: ExpenseService = Depends(get_service), actor: AuthActor = Depends(require_path_permission("expenses_create"))):
    return await service.list_categories(company_id, actor, active)


@router.patch("/categories/{company_id}/{category_id}", response_model=ExpenseCategoryOut)
async def update_category(company_id: UUID, category_id: UUID, data: ExpenseCategoryUpdate, service: ExpenseService = Depends(get_service), actor: AuthActor = Depends(require_path_permission("expenses_manage"))):
    return await service.update_category(company_id, category_id, data, actor)


@router.delete("/categories/{company_id}/{category_id}", status_code=204)
async def delete_category(company_id: UUID, category_id: UUID, service: ExpenseService = Depends(get_service), actor: AuthActor = Depends(require_path_permission("expenses_manage"))):
    await service.delete_category(company_id, category_id, actor)
    return Response(status_code=204)


@router.post("", response_model=ExpenseOut)
async def create_expense(data: ExpenseCreate, service: ExpenseService = Depends(get_service), actor: AuthActor = Depends(require_body_permission("expenses_create")), _entitlement: None = Depends(require_billable_body_company)):
    return await service.create_expense(data, actor)


@router.get("/{company_id}", response_model=list[ExpenseOut] | Page[ExpenseOut])
async def list_expenses(company_id: UUID, start_at: datetime | None = None, end_at: datetime | None = None, branch_id: UUID | None = None, category_id: UUID | None = None, payment_method: str | None = Query(default=None, pattern="^(cash|card|mobile)$"), employee_id: UUID | None = None, actor_user_id: UUID | None = None, actor_id: UUID | None = None, search: str | None = Query(default=None, max_length=160), page: int | None = Query(default=None, ge=1), page_size: int | None = Query(default=None, ge=1, le=100), limit: int = Query(100, ge=1, le=100), offset: int = Query(0, ge=0), service: ExpenseService = Depends(get_service), actor: AuthActor = Depends(require_path_permission("expenses_create"))):
    filters = dict(start_at=start_at, end_at=end_at, branch_id=branch_id, category_id=category_id, payment_method=payment_method, employee_id=employee_id, actor_user_id=actor_user_id, actor_id=actor_id, search=search)
    if page is None and page_size is None: return await service.list_expenses(company_id, actor, **filters, limit=limit, offset=offset)
    page, page_size = page or 1, page_size or 25
    items, total, summary = await service.list_expenses(company_id, actor, **filters, limit=page_size, offset=(page-1)*page_size, with_total=True)
    return page_response(items, page, page_size, total, summary=summary)
