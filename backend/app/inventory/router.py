from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import (
    AuthActor,
    ensure_company_access,
    get_auth_actor,
    require_billable_body_company,
    require_body_permission,
    require_path_permission,
)
from app.db.session import get_db
from app.inventory.repository import InventoryRepository
from app.inventory.schema import (
    GRNCreate,
    InventoryMovementOut,
    InventoryProductOut,
    InventoryValuationOut,
    StockAdjustmentCreate,
    StockTakeCreate,
)
from app.inventory.service import InventoryService
from app.financial_access import enforce_actor_branch
from app.employees.permissions import has_permission


router = APIRouter(
    prefix="/inventory",
    tags=["Inventory"],
)


def get_service(
    db: AsyncSession = Depends(get_db),
):
    return InventoryService(InventoryRepository(db))


def movement_response(movement, actor):
    if actor.actor_type == "user" or actor.role in {"owner", "administrator"} or has_permission(actor.permissions, "product_costs_view"):
        return movement
    return InventoryMovementOut.model_validate(movement).model_copy(update={"unit_cost": None})


@router.get(
    "/overview/{company_id}",
    response_model=list[InventoryProductOut],
)
async def inventory_overview(
    company_id: UUID,
    service: InventoryService = Depends(get_service),
    _actor: AuthActor = Depends(require_path_permission("manage_inventory")),
):
    if _actor.actor_type == "employee" and _actor.role not in {"owner", "administrator"}:
        raise HTTPException(403, "Use the branch-scoped inventory overview")
    return await service.overview(company_id)


@router.get(
    "/valuation/{company_id}",
    response_model=InventoryValuationOut,
)
async def inventory_valuation(
    company_id: UUID,
    service: InventoryService = Depends(get_service),
    _actor: AuthActor = Depends(require_path_permission("inventory_valuation")),
):
    if _actor.actor_type == "employee" and _actor.role not in {"owner", "administrator"}:
        raise HTTPException(403, "Use the branch-scoped inventory valuation report")
    return await service.valuation(company_id)


@router.get(
    "/history/{company_id}",
    response_model=list[InventoryMovementOut],
)
async def inventory_history(
    company_id: UUID,
    limit: int = Query(default=100, ge=1, le=500),
    service: InventoryService = Depends(get_service),
    _actor: AuthActor = Depends(get_auth_actor),
):
    ensure_company_access(_actor, company_id)
    if _actor.actor_type == "employee" and not any(has_permission(_actor.permissions, key) for key in ("sales_process", "manage_inventory")):
        raise HTTPException(403, "Inventory history permission denied")
    return [movement_response(row, _actor) for row in await service.history(company_id, limit, actor=_actor)]


@router.post(
    "/grn",
    response_model=InventoryMovementOut,
)
async def receive_stock(
    data: GRNCreate,
    service: InventoryService = Depends(get_service),
    _actor: AuthActor = Depends(
        require_body_permission("inventory_receive")
    ),
    _entitlement: None = Depends(
        require_billable_body_company
    ),
):
    if _actor.actor_type == "employee":
        enforce_actor_branch(_actor, data.branch_id or _actor.employee.branch_id)
        data.branch_id = data.branch_id or _actor.employee.branch_id
    return movement_response(await service.receive_stock(data), _actor)


@router.post(
    "/adjustments",
    response_model=InventoryMovementOut,
)
async def adjust_stock(
    data: StockAdjustmentCreate,
    service: InventoryService = Depends(get_service),
    _actor: AuthActor = Depends(get_auth_actor),
    _entitlement: None = Depends(
        require_billable_body_company
    ),
):
    if _actor.company_id != data.company_id:
        raise HTTPException(403, "Forbidden")
    if _actor.actor_type == "employee":
        enforce_actor_branch(_actor, data.branch_id or _actor.employee.branch_id)
        data.branch_id = data.branch_id or _actor.employee.branch_id
    return movement_response(await service.adjust_stock(data, _actor), _actor)


@router.post(
    "/stock-take",
    response_model=list[InventoryMovementOut],
)
async def stock_take(
    data: StockTakeCreate,
    service: InventoryService = Depends(get_service),
    _actor: AuthActor = Depends(
        require_body_permission("inventory_count")
    ),
    _entitlement: None = Depends(
        require_billable_body_company
    ),
):
    if _actor.actor_type == "employee":
        enforce_actor_branch(_actor, data.branch_id or _actor.employee.branch_id)
        data.branch_id = data.branch_id or _actor.employee.branch_id
    rows=await service.stock_take(data, actor=_actor) if isinstance(service,InventoryService) else await service.stock_take(data)
    return [movement_response(row, _actor) for row in rows]


@router.get("/stock-take/capabilities")
async def count_capabilities(actor: AuthActor = Depends(get_auth_actor)):
    from app.auth.dependencies import require_permission
    await require_permission("inventory_count")(actor)
    return {"idempotency":"audit-v1", "variant_counts":True, "expected_quantity":True}


@router.get("/count-catalog/{company_id}")
async def physical_count_catalog(company_id: UUID, branch_id: UUID,
    actor: AuthActor = Depends(get_auth_actor), db: AsyncSession = Depends(get_db)):
    from app.auth.dependencies import require_permission
    from .count_catalog import count_catalog
    ensure_company_access(actor, company_id)
    await require_permission("inventory_count")(actor)
    enforce_actor_branch(actor,branch_id)
    return await count_catalog(db,company_id,branch_id)
