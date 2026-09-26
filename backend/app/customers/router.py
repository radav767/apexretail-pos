from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import AuthActor, require_billable_body_company, require_body_permission, require_path_permission
from app.customers.repository import CustomerRepository
from app.customers.schema import CustomerCreate, CustomerOut, CustomerTransactionOut, CustomerUpdate
from app.customers.service import CustomerService
from app.db.session import get_db


router = APIRouter(prefix="/customers", tags=["Customers"])


def get_service(db: AsyncSession = Depends(get_db)):
    return CustomerService(CustomerRepository(db))


@router.post("", response_model=CustomerOut)
async def create_customer(data: CustomerCreate, service: CustomerService = Depends(get_service), actor: AuthActor = Depends(require_body_permission("customers_manage")), _entitlement: None = Depends(require_billable_body_company)):
    return await service.create(data, actor)


@router.get("/{company_id}", response_model=list[CustomerOut])
async def list_customers(company_id: UUID, search: str | None = Query(default=None, max_length=160), active: bool | None = None, limit: int = Query(100, ge=1, le=500), offset: int = Query(0, ge=0), service: CustomerService = Depends(get_service), _actor: AuthActor = Depends(require_path_permission("customers_view"))):
    return await service.list(company_id, search=search, active=active, limit=limit, offset=offset)


@router.get("/{company_id}/{customer_id}", response_model=CustomerOut)
async def get_customer(company_id: UUID, customer_id: UUID, service: CustomerService = Depends(get_service), _actor: AuthActor = Depends(require_path_permission("customers_view"))):
    return await service.get(company_id, customer_id)


@router.patch("/{company_id}/{customer_id}", response_model=CustomerOut)
async def update_customer(company_id: UUID, customer_id: UUID, data: CustomerUpdate, service: CustomerService = Depends(get_service), actor: AuthActor = Depends(require_path_permission("customers_manage"))):
    return await service.update(company_id, customer_id, data, actor)


@router.get("/{company_id}/{customer_id}/transactions", response_model=list[CustomerTransactionOut])
async def customer_transactions(company_id: UUID, customer_id: UUID, service: CustomerService = Depends(get_service), _actor: AuthActor = Depends(require_path_permission("customers_view"))):
    return await service.history(company_id, customer_id)
