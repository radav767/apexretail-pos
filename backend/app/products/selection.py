"""Bounded read model for shared product selection; never exposes cost prices."""
from fastapi import HTTPException
from sqlalchemy import select,func,case,or_
from app.models import Product,Category,Branch,InventoryBalance,VariantInventoryBalance
from app.pagination import page_response


async def selection(db,company_id,branch_id,*,search='',category_id=None,page=1,page_size=25):
    branch=(await db.execute(select(Branch.id).where(Branch.id==branch_id,Branch.company_id==company_id,
        Branch.active.is_(True),Branch.deleted.is_(False)))).scalar_one_or_none()
    if not branch:raise HTTPException(404,'Branch not found')
    if category_id and not (await db.execute(select(Category.id).where(Category.id==category_id,Category.company_id==company_id,Category.deleted.is_(False)))).scalar_one_or_none():
        raise HTTPException(404,'Category not found')
    query=select(Product).where(Product.company_id==company_id,Product.active.is_(True),Product.deleted.is_(False))
    term=search.strip()
    if term:
        escaped=term.replace('\\','\\\\').replace('%','\\%').replace('_','\\_')
        query=query.where(or_(*[field.ilike('%'+escaped+'%',escape='\\') for field in (Product.name,Product.sku,Product.barcode)]))
    if category_id:query=query.where(Product.category_id==category_id)
    total=(await db.execute(select(func.count()).select_from(query.subquery()))).scalar_one()
    base=select(func.sum(InventoryBalance.quantity)).where(InventoryBalance.company_id==company_id,
        InventoryBalance.branch_id==branch_id,InventoryBalance.product_id==Product.id,
        InventoryBalance.active.is_(True),InventoryBalance.deleted.is_(False)).correlate(Product).scalar_subquery()
    variants=select(func.sum(VariantInventoryBalance.quantity)).where(VariantInventoryBalance.company_id==company_id,
        VariantInventoryBalance.branch_id==branch_id,VariantInventoryBalance.product_id==Product.id).correlate(Product).scalar_subquery()
    rows=(await db.execute(query.with_only_columns(Product.id,Product.name,Product.sku,Product.barcode,Product.unit,Product.product_type,
        Product.selling_price,Product.track_inventory,Category.name.label('category_name'),
        (func.coalesce(base,0)+func.coalesce(variants,0)).label('branch_stock_qty'))
        .outerjoin(Category,(Category.id==Product.category_id)&(Category.company_id==company_id))
        .order_by(case((Product.barcode==term,0),else_=1),func.lower(Product.name),Product.id)
        .offset((page-1)*page_size).limit(page_size))).mappings().all()
    items=[{**row,'branch_stock_qty':row['branch_stock_qty'] if row['track_inventory'] else None} for row in rows]
    return page_response(items,page,page_size,total)
