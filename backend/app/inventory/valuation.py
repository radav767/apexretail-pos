"""Read-only current stock positions. Lots attribute these balances, not extra stock.

Variant price/cost overrides use the same parent fallback as checkout. Historical
sale snapshots are never used as current stock prices or rewritten here.
"""
from sqlalchemy import text


def positions_sql(*, legacy=False):
    parent = """SELECT p.id product_id, NULL::uuid variant_id,p.name product_name,p.sku,
        p.category_id,p.selling_price,p.cost_price,ib.quantity,ib.reorder_level,
        ib.branch_id,ib.shop_id,p.company_id
        FROM inventory_balances ib JOIN products p ON p.id=ib.product_id AND p.company_id=ib.company_id
        WHERE ib.company_id=:company_id AND ib.active AND NOT ib.deleted AND p.active AND NOT p.deleted"""
    variant = """SELECT p.id,v.id,p.name || ' — ' || v.name,coalesce(v.sku,p.sku),
        p.category_id,coalesce(v.selling_price,p.selling_price),coalesce(v.cost_price,p.cost_price),
        ib.quantity,ib.reorder_level,ib.branch_id,ib.shop_id,p.company_id
        FROM variant_inventory_balances ib
        JOIN products p ON p.id=ib.product_id AND p.company_id=ib.company_id
        JOIN product_variants v ON v.id=ib.variant_id AND v.product_id=p.id AND v.company_id=p.company_id
        WHERE ib.company_id=:company_id AND ib.active AND NOT ib.deleted AND p.active AND NOT p.deleted"""
    fallback = """SELECT p.id,NULL::uuid,p.name,p.sku,p.category_id,p.selling_price,p.cost_price,
        p.stock_qty,p.reorder_level,NULL::uuid,NULL::uuid,p.company_id FROM products p
        WHERE p.company_id=:company_id AND p.active AND NOT p.deleted
        AND NOT EXISTS(SELECT FROM inventory_balances ib WHERE ib.product_id=p.id AND ib.company_id=p.company_id)"""
    return parent + " UNION ALL " + variant + (" UNION ALL " + fallback if legacy else "")


async def stock_summary(db, company_id, branch_id=None):
    sql = positions_sql(legacy=branch_id is None)
    result = await db.execute(text(f"""SELECT count(DISTINCT product_id) total_products,
        coalesce(sum(quantity),0) total_quantity,
        CASE WHEN bool_and(cost_price IS NOT NULL OR quantity=0) THEN coalesce(sum(quantity*cost_price),0)
             WHEN count(*)=0 THEN 0 ELSE NULL END stock_value,
        count(DISTINCT product_id) FILTER(WHERE quantity<=reorder_level) low_stock_products
        FROM ({sql}) positions WHERE CAST(:branch_id AS uuid) IS NULL OR branch_id=CAST(:branch_id AS uuid)"""),
        {"company_id": company_id, "branch_id": branch_id})
    return dict(result.mappings().one())
