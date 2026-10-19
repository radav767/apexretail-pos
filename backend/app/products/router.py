from uuid import UUID

import csv
import io

from fastapi import APIRouter, Depends, File, HTTPException, Query, Response, UploadFile
from fastapi.responses import FileResponse
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
    ProductComponentOut,
    ProductComponentWrite,
    ProductImportRequest,
    ProductBarcodeLookupOut,
    ProductOut,
    ProductPriceLevelCreate,
    ProductPriceLevelOut,
    ProductPriceLevelUpdate,
    ProductUpdate,
    ProductVariantCreate,
    ProductVariantOut,
    ProductVariantUpdate,
)
from app.products.service import ProductService
from app.products.media import store,path_for
from app.products.import_preview import preview
from app.employees.permissions import has_permission
from app.financial_access import enforce_actor_branch


router = APIRouter(prefix="/products", tags=["Products"])


def get_service(db: AsyncSession = Depends(get_db)):
    return ProductService(ProductRepository(db))

@router.post("/images/{company_id}/{product_id}")
async def upload_image(company_id:UUID,product_id:UUID,image:UploadFile=File(...),db:AsyncSession=Depends(get_db),_actor:AuthActor=Depends(require_path_permission("products_edit")),_entitlement:None=Depends(require_billable_path_company)):
    return await store(ProductRepository(db),company_id,product_id,image)
@router.get("/images/{company_id}/{media_id}")
async def read_image(company_id:UUID,media_id:UUID,db:AsyncSession=Depends(get_db),actor:AuthActor=Depends(get_auth_actor)):
    ensure_catalog_access(actor,company_id); media=await ProductRepository(db).get_media(company_id,media_id)
    if not media: raise HTTPException(404,"Product image not found")
    return FileResponse(path_for(media),media_type=media.content_type,headers={"Cache-Control":"private,max-age=3600"})


def ensure_catalog_access(actor: AuthActor, company_id: UUID) -> None:
    ensure_company_access(actor, company_id)
    if actor.actor_type == "employee" and actor.role not in {
        "owner", "manager", "administrator"
    }:
        permissions = actor.permissions or {}
        if not any(
            permissions.get(key)
            for key in ("sales", "manage_products", "manage_inventory")
        ):
            raise HTTPException(403, "Permission denied")


def can_view_product_cost(actor: AuthActor) -> bool:
    if actor.actor_type == "user" or actor.role in {"owner", "administrator"}:
        return True
    permissions = actor.permissions or {}
    return has_permission(permissions, "product_costs_view")


def product_response(product, actor):
    if can_view_product_cost(actor):
        return product
    return ProductOut.model_validate(product).model_copy(update={"cost_price": None})


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
    result = await service.lookup_barcode(company_id, branch_id, barcode)
    if not can_view_product_cost(actor):
        result["cost_price"] = None
    return result


@router.post("/categories", response_model=CategoryOut)
async def create_category(
    data: CategoryCreate,
    service: ProductService = Depends(get_service),
    _actor: AuthActor = Depends(
        require_body_permission("categories_manage")
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
    actor: AuthActor = Depends(get_auth_actor),
):
    ensure_catalog_access(actor, company_id)
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
        require_path_permission("categories_manage")
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
        require_path_permission("categories_manage")
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
    actor: AuthActor = Depends(
        require_body_permission("products_add")
    ),
    _entitlement: None = Depends(require_billable_body_company),
):
    if (
        actor.actor_type == "employee"
        and data.branch_id is not None
        and actor.employee is not None
        and actor.employee.branch_id != data.branch_id
    ):
        raise HTTPException(403, "Branch access denied")
    if isinstance(service, ProductService):
        product = await service.create_product(data, actor=actor)
    else:
        product = await service.create_product(data)
    return product_response(product, actor)


@router.get("/components/{company_id}/{product_id}", response_model=list[ProductComponentOut])
async def list_product_components(
    company_id: UUID,
    product_id: UUID,
    service: ProductService = Depends(get_service),
    actor: AuthActor = Depends(get_auth_actor),
):
    ensure_catalog_access(actor, company_id)
    rows = await service.list_components(company_id, product_id)
    if not can_view_product_cost(actor):
        rows = [{**row, "component_cost": None, "total_cost": None} for row in rows]
    return rows


@router.put("/components/{company_id}/{product_id}", response_model=list[ProductComponentOut])
async def replace_product_components(
    company_id: UUID,
    product_id: UUID,
    data: list[ProductComponentWrite],
    service: ProductService = Depends(get_service),
    _actor: AuthActor = Depends(require_path_permission("composites_manage")),
    _entitlement: None = Depends(require_billable_path_company),
):
    rows = await service.replace_components(company_id, product_id, data)
    if not can_view_product_cost(_actor):
        rows = [{**row, "component_cost": None, "total_cost": None} for row in rows]
    return rows


@router.get("/variants/{company_id}", response_model=list[ProductVariantOut])
async def list_product_variants(
    company_id: UUID,
    product_id: UUID | None = Query(default=None),
    branch_id: UUID | None = Query(default=None),
    service: ProductService = Depends(get_service),
    actor: AuthActor = Depends(get_auth_actor),
):
    ensure_catalog_access(actor, company_id)
    if actor.actor_type == "employee" and actor.role not in {"owner", "administrator"}:
        branch_id = branch_id or actor.employee.branch_id
        enforce_actor_branch(actor, branch_id)
    rows = await service.list_variants(company_id, product_id, branch_id)
    if not can_view_product_cost(actor):
        rows = [{**row, "cost_price": None} for row in rows]
    return rows


@router.post("/variants/{company_id}/{product_id}", response_model=ProductVariantOut)
async def create_product_variant(
    company_id: UUID,
    product_id: UUID,
    data: ProductVariantCreate,
    service: ProductService = Depends(get_service),
    _actor: AuthActor = Depends(require_path_permission("variants_manage")),
    _entitlement: None = Depends(require_billable_path_company),
):
    if _actor.actor_type == "employee":
        data.branch_id = data.branch_id or _actor.employee.branch_id
        enforce_actor_branch(_actor, data.branch_id)
    result = await service.create_variant(company_id, product_id, data)
    if not can_view_product_cost(_actor):
        result = {**result, "cost_price": None}
    return result


@router.patch("/variants/{company_id}/item/{variant_id}", response_model=ProductVariantOut)
async def update_product_variant(
    company_id: UUID,
    variant_id: UUID,
    data: ProductVariantUpdate,
    service: ProductService = Depends(get_service),
    _actor: AuthActor = Depends(require_path_permission("variants_manage")),
    _entitlement: None = Depends(require_billable_path_company),
):
    if _actor.actor_type == "employee" and data.branch_id is not None:
        enforce_actor_branch(_actor, data.branch_id)
    result = await service.update_variant(company_id, variant_id, data)
    if not can_view_product_cost(_actor):
        result = {**result, "cost_price": None}
    return result


@router.delete("/variants/{company_id}/item/{variant_id}")
async def delete_product_variant(
    company_id: UUID,
    variant_id: UUID,
    service: ProductService = Depends(get_service),
    _actor: AuthActor = Depends(require_path_permission("variants_manage")),
    _entitlement: None = Depends(require_billable_path_company),
):
    return await service.delete_variant(company_id, variant_id)


@router.get("/price-levels/{company_id}", response_model=list[ProductPriceLevelOut])
async def list_product_price_levels(
    company_id: UUID,
    product_id: UUID | None = Query(default=None),
    service: ProductService = Depends(get_service),
    actor: AuthActor = Depends(get_auth_actor),
):
    ensure_catalog_access(actor, company_id)
    return await service.list_price_levels(company_id, product_id)


@router.post("/price-levels/{company_id}/{product_id}", response_model=ProductPriceLevelOut)
async def create_product_price_level(
    company_id: UUID,
    product_id: UUID,
    data: ProductPriceLevelCreate,
    service: ProductService = Depends(get_service),
    _actor: AuthActor = Depends(require_path_permission("products_edit")),
    _entitlement: None = Depends(require_billable_path_company),
):
    return await service.create_price_level(company_id, product_id, data)


@router.patch("/price-levels/{company_id}/item/{price_level_id}", response_model=ProductPriceLevelOut)
async def update_product_price_level(
    company_id: UUID,
    price_level_id: UUID,
    data: ProductPriceLevelUpdate,
    service: ProductService = Depends(get_service),
    _actor: AuthActor = Depends(require_path_permission("products_edit")),
    _entitlement: None = Depends(require_billable_path_company),
):
    return await service.update_price_level(company_id, price_level_id, data)


@router.delete("/price-levels/{company_id}/item/{price_level_id}")
async def delete_product_price_level(
    company_id: UUID,
    price_level_id: UUID,
    service: ProductService = Depends(get_service),
    _actor: AuthActor = Depends(require_path_permission("products_edit")),
    _entitlement: None = Depends(require_billable_path_company),
):
    return await service.delete_price_level(company_id, price_level_id)


@router.post("/import", response_model=list[ProductOut])
async def import_products(
    data: ProductImportRequest,
    service: ProductService = Depends(get_service),
    actor: AuthActor = Depends(require_body_permission("products_add")),
    _entitlement: None = Depends(require_billable_body_company),
):
    if actor.actor_type == "employee":
        data.branch_id = data.branch_id or actor.employee.branch_id
        enforce_actor_branch(actor, data.branch_id)
        if any(row.variant_name for row in data.rows) and not has_permission(actor.permissions, "variants_manage"):
            raise HTTPException(403, "Variant management permission denied")
        if any(row.category_name for row in data.rows) and not has_permission(actor.permissions, "categories_manage"):
            raise HTTPException(403, "Category management permission denied")
    return [product_response(product, actor) for product in await service.import_products(data, actor=actor)]

@router.post("/import/preview/{company_id}")
async def preview_import(company_id:UUID,file:UploadFile=File(...),_actor:AuthActor=Depends(require_path_permission("manage_products")),_entitlement:None=Depends(require_billable_path_company)):
    return await preview(file)


@router.get("/export/{company_id}")
async def export_products(
    company_id: UUID,
    service: ProductService = Depends(get_service),
    _actor: AuthActor = Depends(require_path_permission("product_costs_view")),
):
    products = await service.list_products(company_id, include_cost=True)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "name", "sku", "barcode", "product_type", "unit", "purchase_unit",
        "units_per_purchase", "cost_price", "selling_price", "stock_qty",
        "reorder_level", "active",
    ])
    for product in products:
        writer.writerow([
            product.name, product.sku, product.barcode, product.product_type,
            product.unit, product.purchase_unit, product.units_per_purchase,
            product.cost_price, product.selling_price, product.stock_qty,
            product.reorder_level, product.active,
        ])
    return Response(
        output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=products.csv"},
    )


@router.get("/units/{company_id}")
async def list_product_units(
    company_id: UUID,
    actor: AuthActor = Depends(get_auth_actor),
):
    ensure_catalog_access(actor, company_id)
    return [
        {"code": "each", "name": "Each"},
        {"code": "kg", "name": "Kilogram"},
        {"code": "g", "name": "Gram"},
        {"code": "litre", "name": "Litre"},
        {"code": "ml", "name": "Millilitre"},
        {"code": "carton", "name": "Carton"},
        {"code": "case", "name": "Case"},
        {"code": "pack", "name": "Pack"},
    ]


@router.get("/{company_id}", response_model=list[ProductOut])
async def list_products(
    company_id: UUID,
    search: str | None = Query(default=None, max_length=160),
    category_id: UUID | None = Query(default=None),
    product_type: str | None = Query(default=None, max_length=24),
    service: ProductService = Depends(get_service),
    actor: AuthActor = Depends(get_auth_actor),
):
    ensure_catalog_access(actor, company_id)
    return await service.list_products(
        company_id,
        search=search,
        category_id=category_id,
        product_type=product_type,
        include_cost=can_view_product_cost(actor),
    )


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
        require_path_permission("products_edit")
    ),
):
    product = await service.update_product(
        company_id,
        product_id,
        data,
        actor=_actor,
    )
    return product_response(product, _actor)


@router.delete("/{company_id}/{product_id}")
async def delete_product(
    company_id: UUID,
    product_id: UUID,
    service: ProductService = Depends(get_service),
    _actor: AuthActor = Depends(
        require_path_permission("products_delete")
    ),
):
    return await service.delete_product(company_id, product_id, actor=_actor)

@router.post("/{company_id}/{product_id}/archive", response_model=ProductOut)
async def archive_product(company_id: UUID, product_id: UUID, service: ProductService = Depends(get_service), _actor: AuthActor = Depends(require_path_permission("products_delete"))):
    return await service.archive_product(company_id, product_id, actor=_actor)
