from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import (
    AuthActor,
    ensure_company_access,
    get_auth_actor,
    require_billable_body_company,
    require_billable_path_company,
    require_body_permission,
    require_path_permission,
)
from app.db.session import get_db
from app.products.repository import ProductRepository
from app.products.schema import (
    CategoryCreate,
    CategoryOut,
    CategoryUpdate,
    ProductCreate,
    ProductBarcodeLookupOut,
    ProductOut,
    ProductUpdate,
)
from app.products.service import ProductService


router = APIRouter(prefix="/products", tags=["Products"])


def get_service(db: AsyncSession = Depends(get_db)):
    return ProductService(ProductRepository(db))


@router.get(
    "/{company_id}/barcode-lookup",
    response_model=ProductBarcodeLookupOut,
)
async def lookup_product_by_barcode(
    company_id: UUID,
    barcode: str = Query(min_length=1, max_length=80),
    branch_id: UUID = Query(...),
    service: ProductService = Depends(get_service),
    actor: AuthActor = Depends(get_auth_actor),
):
    ensure_company_access(actor, company_id)
    if actor.actor_type == "employee":
        permissions = actor.permissions or {}
        if not any(
            permissions.get(key)
            for key in ("sales", "manage_products", "manage_inventory")
        ):
            raise HTTPException(403, "Permission denied")
        if actor.employee is not None and actor.employee.branch_id != branch_id:
            raise HTTPException(403, "Branch access denied")
    return await service.lookup_barcode(company_id, branch_id, barcode)


@router.post("/categories", response_model=CategoryOut)
async def create_category(
    data: CategoryCreate,
    service: ProductService = Depends(get_service),
    _actor: AuthActor = Depends(
        require_body_permission("manage_products")
    ),
    _entitlement: None = Depends(
        require_billable_body_company
    ),
):
    return await service.create_category(data)


@router.get(
    "/categories/{company_id}",
    response_model=list[CategoryOut],
)
async def list_categories(
    company_id: UUID,
    service: ProductService = Depends(get_service),
):
    return await service.list_categories(company_id)


@router.patch(
    "/categories/{company_id}/{category_id}",
    response_model=CategoryOut,
)
async def update_category(
    company_id: UUID,
    category_id: UUID,
    data: CategoryUpdate,
    service: ProductService = Depends(get_service),
    _actor: AuthActor = Depends(
        require_path_permission("manage_products")
    ),
    _entitlement: None = Depends(
        require_billable_path_company
    ),
):
    return await service.update_category(
        company_id,
        category_id,
        data,
    )


@router.delete("/categories/{company_id}/{category_id}")
async def delete_category(
    company_id: UUID,
    category_id: UUID,
    service: ProductService = Depends(get_service),
    _actor: AuthActor = Depends(
        require_path_permission("manage_products")
    ),
    _entitlement: None = Depends(
        require_billable_path_company
    ),
):
    return await service.delete_category(company_id, category_id)


@router.post("", response_model=ProductOut)
async def create_product(
    data: ProductCreate,
    service: ProductService = Depends(get_service),
    _actor: AuthActor = Depends(
        require_body_permission("manage_products")
    ),
):
    return await service.create_product(data)


@router.get("/{company_id}", response_model=list[ProductOut])
async def list_products(
    company_id: UUID,
    service: ProductService = Depends(get_service),
):
    return await service.list_products(company_id)


@router.patch(
    "/{company_id}/{product_id}",
    response_model=ProductOut,
)
async def update_product(
    company_id: UUID,
    product_id: UUID,
    data: ProductUpdate,
    service: ProductService = Depends(get_service),
    _actor: AuthActor = Depends(
        require_path_permission("manage_products")
    ),
):
    return await service.update_product(
        company_id,
        product_id,
        data,
    )


@router.delete("/{company_id}/{product_id}")
async def delete_product(
    company_id: UUID,
    product_id: UUID,
    service: ProductService = Depends(get_service),
    _actor: AuthActor = Depends(
        require_path_permission("manage_products")
    ),
):
    return await service.delete_product(company_id, product_id, actor=_actor)

@router.post("/{company_id}/{product_id}/archive", response_model=ProductOut)
async def archive_product(company_id: UUID, product_id: UUID, service: ProductService = Depends(get_service), _actor: AuthActor = Depends(require_path_permission("manage_products"))):
    return await service.archive_product(company_id, product_id, actor=_actor)
