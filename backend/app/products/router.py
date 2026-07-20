from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.products.repository import ProductRepository
from app.products.schema import (
    CategoryCreate,
    CategoryOut,
    CategoryUpdate,
    ProductCreate,
    ProductOut,
    ProductUpdate,
)
from app.products.service import ProductService


router = APIRouter(prefix="/products", tags=["Products"])


def get_service(db: AsyncSession = Depends(get_db)):
    return ProductService(ProductRepository(db))


@router.post("/categories", response_model=CategoryOut)
async def create_category(
    data: CategoryCreate,
    service: ProductService = Depends(get_service),
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
):
    return await service.delete_category(company_id, category_id)


@router.post("", response_model=ProductOut)
async def create_product(
    data: ProductCreate,
    service: ProductService = Depends(get_service),
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
):
    return await service.delete_product(company_id, product_id)
