"""Permission-scoped physical count positions. Never exposes product costs."""
from sqlalchemy import select
from app.models import Product, ProductVariant, InventoryBalance, VariantInventoryBalance, ProductBatch
from .stock_repository import BranchStockRepository


async def count_catalog(db, company_id, branch_id):
    branch=await BranchStockRepository(db).resolve_branch(company_id,branch_id)
    products=(await db.execute(select(Product).where(Product.company_id==company_id,
        Product.active==True,Product.deleted==False,Product.track_inventory==True,
        Product.product_type.in_(["standard","variable_weight"])).order_by(Product.name))).scalars().all()
    parents={row.product_id:row for row in (await db.execute(select(InventoryBalance).where(
        InventoryBalance.company_id==company_id,InventoryBalance.branch_id==branch.id,
        InventoryBalance.active==True,InventoryBalance.deleted==False))).scalars()}
    variants=(await db.execute(select(ProductVariant).where(ProductVariant.company_id==company_id,
        ProductVariant.deleted==False))).scalars().all()
    balances={row.variant_id:row for row in (await db.execute(select(VariantInventoryBalance).where(
        VariantInventoryBalance.company_id==company_id,VariantInventoryBalance.branch_id==branch.id,
        VariantInventoryBalance.active==True,VariantInventoryBalance.deleted==False))).scalars()}
    batches=(await db.execute(select(ProductBatch).where(ProductBatch.company_id==company_id,
        ProductBatch.branch_id==branch.id).order_by(ProductBatch.expires_on,ProductBatch.code))).scalars().all()
    result=[]
    for product in products:
        options=[v for v in variants if v.product_id==product.id]
        dimensions=[(None,parents.get(product.id))] if not options or parents.get(product.id) and parents[product.id].quantity else []
        dimensions += [(v,balances.get(v.id)) for v in options if v.active or balances.get(v.id) and balances[v.id].quantity]
        for variant,balance in dimensions:
            variant_id=variant.id if variant else None
            result.append({"key":f"{product.id}:{variant_id or 'parent'}","product_id":product.id,"variant_id":variant_id,
                "name":f"{product.name} — {variant.name}" if variant else product.name,
                "sku":variant.sku if variant and variant.sku else product.sku,"unit":product.unit,
                "stock_qty":balance.quantity if balance else 0,"active":variant.active if variant else True,
                "batches":[{"id":lot.id,"code":lot.code,"expires_on":lot.expires_on,"quantity":lot.quantity}
                    for lot in batches if lot.product_id==product.id and lot.variant_id==variant_id]})
    return result
