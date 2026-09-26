from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import AuthActor, require_billable_body_company, require_body_permission, require_path_permission
from app.credit.repository import CreditRepository
from app.credit.schema import ReceivableOut, SettlementCreate, SettlementOut
from app.credit.service import CreditService
from app.db.session import get_db


router = APIRouter(prefix="/credit", tags=["Credit"])


def get_service(db: AsyncSession = Depends(get_db)):
    return CreditService(CreditRepository(db))


@router.get("/{company_id}/receivables", response_model=list[ReceivableOut])
async def list_receivables(company_id: UUID, customer_id: UUID | None = None, branch_id: UUID | None = None, status: str | None = None, limit: int = Query(100, ge=1, le=500), offset: int = Query(0, ge=0), service: CreditService = Depends(get_service), actor: AuthActor = Depends(require_path_permission("customers_view"))):
    return await service.list_receivables(company_id, actor, customer_id=customer_id, branch_id=branch_id, status=status, limit=limit, offset=offset)


@router.get("/{company_id}/receivables/{receivable_id}", response_model=ReceivableOut)
async def get_receivable(company_id: UUID, receivable_id: UUID, service: CreditService = Depends(get_service), actor: AuthActor = Depends(require_path_permission("customers_view"))):
    return await service.get_receivable(company_id, receivable_id, actor)


@router.post("/settlements", response_model=SettlementOut)
async def create_settlement(data: SettlementCreate, service: CreditService = Depends(get_service), actor: AuthActor = Depends(require_body_permission("credit_settlements")), _entitlement: None = Depends(require_billable_body_company)):
    return await service.create_settlement(data, actor)


@router.get("/{company_id}/settlements", response_model=list[SettlementOut])
async def list_settlements(company_id: UUID, receivable_id: UUID | None = None, customer_id: UUID | None = None, branch_id: UUID | None = None, limit: int = Query(100, ge=1, le=500), offset: int = Query(0, ge=0), service: CreditService = Depends(get_service), actor: AuthActor = Depends(require_path_permission("credit_settlements"))):
    return await service.list_settlements(company_id, actor, receivable_id=receivable_id, customer_id=customer_id, branch_id=branch_id, limit=limit, offset=offset)
