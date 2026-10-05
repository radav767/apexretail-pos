from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import AuthActor, require_billable_body_company, require_body_permission, require_path_permission
from app.credit.repository import CreditRepository
from app.credit.schema import ReceivableOut, SettlementCreate, SettlementOut
from app.credit.service import CreditService
from app.db.session import get_db
from app.pagination import Page, page_response


router = APIRouter(prefix="/credit", tags=["Credit"])


def get_service(db: AsyncSession = Depends(get_db)):
    return CreditService(CreditRepository(db))


@router.get("/{company_id}/receivables", response_model=list[ReceivableOut] | Page[ReceivableOut])
async def list_receivables(company_id: UUID, customer_id: UUID | None = None, branch_id: UUID | None = None, status: str | None = Query(default=None, pattern="^(unpaid|open|outstanding|partially_paid|paid|overdue)$"), start_at: datetime | None = None, end_at: datetime | None = None, search: str | None = Query(default=None, max_length=160), page: int | None = Query(default=None, ge=1), page_size: int | None = Query(default=None, ge=1, le=100), limit: int = Query(100, ge=1, le=100), offset: int = Query(0, ge=0), service: CreditService = Depends(get_service), actor: AuthActor = Depends(require_path_permission("customers_view"))):
    filters = dict(customer_id=customer_id, branch_id=branch_id, status=status, start_at=start_at, end_at=end_at, search=search)
    if page is None and page_size is None: return await service.list_receivables(company_id, actor, **filters, limit=limit, offset=offset)
    page, page_size = page or 1, page_size or 25
    items, total = await service.list_receivables(company_id, actor, **filters, limit=page_size, offset=(page-1)*page_size, with_total=True)
    return page_response(items, page, page_size, total)


@router.get("/{company_id}/receivables/{receivable_id}", response_model=ReceivableOut)
async def get_receivable(company_id: UUID, receivable_id: UUID, service: CreditService = Depends(get_service), actor: AuthActor = Depends(require_path_permission("customers_view"))):
    return await service.get_receivable(company_id, receivable_id, actor)


@router.post("/settlements", response_model=SettlementOut)
async def create_settlement(data: SettlementCreate, service: CreditService = Depends(get_service), actor: AuthActor = Depends(require_body_permission("credit_settlements")), _entitlement: None = Depends(require_billable_body_company)):
    return await service.create_settlement(data, actor)


@router.get("/{company_id}/settlements", response_model=list[SettlementOut] | Page[SettlementOut])
async def list_settlements(company_id: UUID, receivable_id: UUID | None = None, customer_id: UUID | None = None, branch_id: UUID | None = None, status: str | None = Query(default=None, pattern="^(unpaid|open|outstanding|partially_paid|paid|overdue)$"), payment_method: str | None = Query(default=None, pattern="^(cash|card|mobile)$"), start_at: datetime | None = None, end_at: datetime | None = None, search: str | None = Query(default=None, max_length=160), page: int | None = Query(default=None, ge=1), page_size: int | None = Query(default=None, ge=1, le=100), limit: int = Query(100, ge=1, le=100), offset: int = Query(0, ge=0), service: CreditService = Depends(get_service), actor: AuthActor = Depends(require_path_permission("credit_settlements"))):
    filters = dict(receivable_id=receivable_id, customer_id=customer_id, branch_id=branch_id, status=status, payment_method=payment_method, start_at=start_at, end_at=end_at, search=search)
    if page is None and page_size is None: return await service.list_settlements(company_id, actor, **filters, limit=limit, offset=offset)
    page, page_size = page or 1, page_size or 25
    items, total = await service.list_settlements(company_id, actor, **filters, limit=page_size, offset=(page-1)*page_size, with_total=True)
    return page_response(items, page, page_size, total)
