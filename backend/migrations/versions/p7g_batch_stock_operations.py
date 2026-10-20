"""Append-only idempotency records for lot-specific existing-ledger movements."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "p7g_batch_stock_operations"
down_revision = "p7f_offline_order_receipts"
branch_labels = None
depends_on = None


def upgrade():
    uid = postgresql.UUID(as_uuid=True)
    op.create_table("batch_stock_operations",
        sa.Column("id", uid, primary_key=True),
        sa.Column("company_id", uid, sa.ForeignKey("companies.id"), nullable=False),
        sa.Column("request_id", uid, nullable=False),
        sa.Column("payload_hash", sa.String(64), nullable=False),
        sa.Column("batch_id", uid, sa.ForeignKey("product_batches.id"), nullable=False),
        sa.Column("movement_id", uid, sa.ForeignKey("inventory_movements.id"), nullable=False, unique=True),
        sa.Column("operation", sa.String(24), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("company_id", "request_id", name="uq_batch_stock_request"))
    op.execute("DO $$ BEGIN IF EXISTS (SELECT FROM pg_roles WHERE rolname='apex_user') THEN GRANT SELECT, INSERT ON batch_stock_operations TO apex_user; END IF; END $$")


def downgrade():
    if op.get_bind().execute(sa.text("SELECT EXISTS(SELECT FROM batch_stock_operations)")).scalar():
        raise RuntimeError("Batch operation history exists; use forward recovery")
    op.drop_table("batch_stock_operations")
