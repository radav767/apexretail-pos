"""Resolve inventory dimensions without creating a second balance writer."""
from fastapi import HTTPException
from sqlalchemy import select
from app.models import ProductVariant
from app.sales.repository import SalesRepository


async def variant_for_stock(db, company_id, product_id, variant_id, *, include_inactive=False):
    if variant_id is None:
        return None
    query=select(ProductVariant).where(
        ProductVariant.id == variant_id, ProductVariant.company_id == company_id,
        ProductVariant.product_id == product_id, ProductVariant.deleted == False)
    if not include_inactive:query=query.where(ProductVariant.active == True)
    row = (await db.execute(query.with_for_update())).scalar_one_or_none()
    if row is None:
        raise HTTPException(404, "Variant not found or inactive for this product")
    return row


async def dimension_balance(db, stock, company_id, branch, product, variant):
    if variant is None:
        return await stock.get_balance_for_update(company_id, branch, product)
    return await SalesRepository(db).get_variant_balance(company_id, branch, product.id, variant.id)
