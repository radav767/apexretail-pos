from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import AuthActor, require_billable_body_company, require_body_permission, require_path_permission
from app.customers.repository import CustomerRepository
from app.customers.schema import CustomerCreate, CustomerOut, CustomerTransactionOut, CustomerUpdate
from app.customers.service import CustomerService
from app.db.session import get_db
from app.pagination import Page, page_response


router = APIRouter(prefix="/customers", tags=["Customers"])


def get_service(db: AsyncSession = Depends(get_db)):
    return CustomerService(CustomerRepository(db))


@router.post("", response_model=CustomerOut)
async def create_customer(data: CustomerCreate, service: CustomerService = Depends(get_service), actor: AuthActor = Depends(require_body_permission("customers_view")), _entitlement: None = Depends(require_billable_body_company)):
    return await service.create(data, actor)


@router.get("/{company_id}", response_model=list[CustomerOut] | Page[CustomerOut])
async def list_customers(company_id: UUID, search: str | None = Query(default=None, max_length=160), active: bool | None = None, credit_enabled: bool | None = None, page: int | None = Query(default=None, ge=1), page_size: int | None = Query(default=None, ge=1, le=100), limit: int = Query(100, ge=1, le=100), offset: int = Query(0, ge=0), service: CustomerService = Depends(get_service), _actor: AuthActor = Depends(require_path_permission("customers_view"))):
    if page is None and page_size is None:
        return await service.list(company_id, search=search, active=active, credit_enabled=credit_enabled, limit=limit, offset=offset)
    page, page_size = page or 1, page_size or 25
    items, total = await service.list(company_id, search=search, active=active, credit_enabled=credit_enabled, limit=page_size, offset=(page - 1) * page_size, with_total=True)
    return page_response(items, page, page_size, total)


@router.get("/{company_id}/{customer_id}", response_model=CustomerOut)
async def get_customer(company_id: UUID, customer_id: UUID, service: CustomerService = Depends(get_service), _actor: AuthActor = Depends(require_path_permission("customers_view"))):
    return await service.get(company_id, customer_id)


@router.patch("/{company_id}/{customer_id}", response_model=CustomerOut)
async def update_customer(company_id: UUID, customer_id: UUID, data: CustomerUpdate, service: CustomerService = Depends(get_service), actor: AuthActor = Depends(require_path_permission("customers_view"))):
    return await service.update(company_id, customer_id, data, actor)


@router.get("/{company_id}/{customer_id}/transactions", response_model=list[CustomerTransactionOut] | Page[CustomerTransactionOut])
async def customer_transactions(company_id: UUID, customer_id: UUID, transaction_type: str | None = Query(default=None, pattern="^(credit_sale|settlement)$"), start_at: datetime | None = None, end_at: datetime | None = None, page: int | None = Query(default=None, ge=1), page_size: int | None = Query(default=None, ge=1, le=100), limit: int = Query(100, ge=1, le=100), offset: int = Query(0, ge=0), service: CustomerService = Depends(get_service), _actor: AuthActor = Depends(require_path_permission("customers_view"))):
    filters = dict(transaction_type=transaction_type, start_at=start_at, end_at=end_at)
    if page is None and page_size is None:
        return await service.history(company_id, customer_id, **filters, limit=limit, offset=offset)
    page, page_size = page or 1, page_size or 25
    items, total = await service.history(company_id, customer_id, **filters, limit=page_size, offset=(page - 1) * page_size, with_total=True)
    return page_response(items, page, page_size, total)
