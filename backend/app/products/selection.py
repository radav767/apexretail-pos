"""Bounded read model for shared product selection; never exposes cost prices."""
from fastapi import HTTPException
from sqlalchemy import select,func,case,or_
from app.models import Product,Category,Branch,InventoryBalance,VariantInventoryBalance
from app.pagination import page_response
from app.products.access import ensure_catalog_access
from app.workflows.core import WorkflowService
from app.printing.service import permit


async def selection(db,company_id,branch_id,*,actor=None,search='',category_id=None,purpose='general',selected_id=None,page=1,page_size=25,status='active'):
    if purpose not in ('general','charge','management') or status not in ('active','inactive','all') or (purpose!='management' and status!='active') or not isinstance(search,str) or len(search)>160 or not isinstance(page,int) or not isinstance(page_size,int) or page<1 or not 1<=page_size<=100 or (page-1)*page_size>2147483647:
        raise HTTPException(422,'Use a supported selection purpose and bounded search/page')
    await WorkflowService(db,actor).current_context(company_id,branch_id)
    if purpose=='management':
        if actor.actor_type!='user' or actor.role not in ('owner','administrator') or actor.pos_session:
            raise HTTPException(403,'Catalogue management selection requires an authorized Backoffice user')
        permit(actor,'products_edit')
    elif purpose=='charge':permit(actor,'business_settings_manage')
    else:ensure_catalog_access(actor,company_id)
    branch=(await db.execute(select(Branch.id).where(Branch.id==branch_id,Branch.company_id==company_id,
        Branch.active.is_(True),Branch.deleted.is_(False)))).scalar_one_or_none()
    if not branch:raise HTTPException(404,'Branch not found')
    if category_id and not (await db.execute(select(Category.id).where(Category.id==category_id,Category.company_id==company_id,Category.deleted.is_(False)))).scalar_one_or_none():
        raise HTTPException(404,'Category not found')
    query=select(Product).where(Product.company_id==company_id,Product.deleted.is_(False))
    if purpose!='management' or status!='all':query=query.where(Product.active.is_(status!='inactive'))
    if purpose=='charge':query=query.where(Product.product_type.in_(('service','non_stock')),Product.track_inventory.is_(False))
    if selected_id:query=query.where(Product.id==selected_id)
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
        Product.selling_price,Product.track_inventory,*([Product.active] if purpose=='management' else []),Category.name.label('category_name'),
        (func.coalesce(base,0)+func.coalesce(variants,0)).label('branch_stock_qty'))
        .outerjoin(Category,(Category.id==Product.category_id)&(Category.company_id==company_id))
        .order_by(case((Product.barcode==term,0),else_=1),func.lower(Product.name),Product.id)
        .offset((page-1)*page_size).limit(page_size))).mappings().all()
    items=[{**row,'branch_stock_qty':row['branch_stock_qty'] if row['track_inventory'] else None} for row in rows]
    if purpose=='management':return {**page_response(items,page,page_size,total),'selection_contract':'product-selection-management-v1','purpose':purpose,'status':status}
    return {**page_response(items,page,page_size,total),'selection_contract':'product-selection-v2','purpose':purpose}
