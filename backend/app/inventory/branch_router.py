from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import (
    AuthActor,
    get_auth_actor,
    ensure_company_access,
    require_billable_body_company,
    require_body_permission,
)
from app.db.session import get_db
from app.inventory.branch_repository import (
    BranchInventoryRepository,
)
from app.inventory.branch_schema import (
    BranchCreate,
    BranchInventoryOut,
    InventoryBranchOut,
)
from app.inventory.branch_service import (
    BranchInventoryService,
)
from app.financial_access import enforce_actor_branch
from app.employees.permissions import has_permission


router = APIRouter(
    prefix="/inventory",
    tags=["Branch Inventory"],
)


def get_service(
    db: AsyncSession = Depends(get_db),
):
    return BranchInventoryService(
        BranchInventoryRepository(db)
    )


@router.post(
    "/branches",
    response_model=InventoryBranchOut,
)
async def create_inventory_branch(
    data: BranchCreate,
    service: BranchInventoryService = Depends(get_service),
    _actor: AuthActor = Depends(
        require_body_permission("branches_manage")
    ),
    _entitlement: None = Depends(
        require_billable_body_company
    ),
):
    return await service.create_branch(data, actor=_actor)


@router.get(
    "/branches/{company_id}",
    response_model=list[InventoryBranchOut],
)
async def list_inventory_branches(
    company_id: UUID,
    service: BranchInventoryService = Depends(get_service),
    actor: AuthActor = Depends(get_auth_actor),
):
    ensure_company_access(actor, company_id)
    rows = await service.branches(company_id)
    if actor.actor_type == "employee" and actor.role not in {"owner", "administrator"}:
        rows = [row for row in rows if row["id"] == actor.employee.branch_id]
    return rows


@router.get(
    "/branch-overview/{company_id}",
    response_model=list[BranchInventoryOut],
)
async def branch_inventory_overview(
    company_id: UUID,
    branch_id: UUID | None = Query(default=None),
    service: BranchInventoryService = Depends(get_service),
    actor: AuthActor = Depends(get_auth_actor),
):
    ensure_company_access(actor, company_id)
    if actor.actor_type == "employee" and actor.role not in {"owner", "administrator"}:
        branch_id = branch_id or actor.employee.branch_id
        enforce_actor_branch(actor, branch_id)
    rows = await service.overview(
        company_id,
        branch_id,
    )
    if actor.actor_type == "employee" and not has_permission(actor.permissions, "product_costs_view"):
        rows = [{**row, "cost_price": None, "stock_value": None} for row in rows]
    return rows
