"""repair inventory balance backfill for online and offline upgrades"""
from alembic import op, context
import sqlalchemy as sa

revision = "c2phase1inventory"
down_revision = "c1phase1refunds"
branch_labels = None
depends_on = None

def upgrade():
    bind = op.get_bind()
    if context.is_offline_mode() or bind is None:
        return
    rows = bind.execute(sa.text("""
        SELECT p.company_id, p.id AS product_id, p.stock_qty, p.reorder_level,
               b.id AS branch_id, b.shop_id
        FROM products p
        JOIN LATERAL (
          SELECT b.id, b.shop_id FROM branches b
          JOIN shops s ON s.id=b.shop_id
          WHERE b.company_id=p.company_id AND b.active=true AND b.deleted=false
            AND s.active=true AND s.deleted=false
          ORDER BY b.created_at LIMIT 1
        ) b ON true
        WHERE p.deleted=false
    """)).mappings().all()
    for row in rows:
        bind.execute(sa.text("""
          INSERT INTO inventory_balances
            (id, company_id, shop_id, branch_id, product_id, quantity,
             reorder_level, active, deleted, created_at, updated_at)
          VALUES (gen_random_uuid(), :company_id, :shop_id, :branch_id,
                  :product_id, COALESCE(:quantity,0), COALESCE(:reorder,0),
                  true, false, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
          ON CONFLICT (company_id, branch_id, product_id) DO NOTHING
        """), {"company_id": row["company_id"], "shop_id": row["shop_id"], "branch_id": row["branch_id"], "product_id": row["product_id"], "quantity": row["stock_qty"], "reorder": row["reorder_level"]})

def downgrade():
    # Deliberately non-destructive: inventory balances may have received live
    # movements after upgrade and must not be deleted by downgrade.
    pass
