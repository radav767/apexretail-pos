"""Append-only offline unpaid-order acknowledgements; no financial backfill."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "p7f_offline_order_receipts"
down_revision = "p7e_business_orders_batches"
branch_labels = None
depends_on = None


def upgrade():
    uid = postgresql.UUID(as_uuid=True)
    op.create_table("order_sync_receipts",
        sa.Column("id", uid, primary_key=True),
        sa.Column("company_id", uid, sa.ForeignKey("companies.id"), nullable=False),
        sa.Column("employee_id", uid, sa.ForeignKey("employees.id"), nullable=False),
        sa.Column("device_id", uid, sa.ForeignKey("devices.id"), nullable=False),
        sa.Column("request_id", uid, nullable=False),
        sa.Column("payload_hash", sa.String(64), nullable=False),
        sa.Column("result", postgresql.JSONB(), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("synchronized_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("company_id", "request_id", name="uq_order_sync_request"))
    # Preserve ownership and existing schema permissions. Runtime may append
    # acknowledgements but cannot alter or erase them.
    op.execute("DO $$ BEGIN IF EXISTS (SELECT FROM pg_roles WHERE rolname='apex_user') THEN GRANT SELECT, INSERT ON order_sync_receipts TO apex_user; END IF; END $$")


def downgrade():
    if op.get_bind().execute(sa.text("SELECT EXISTS(SELECT FROM order_sync_receipts)")).scalar():
        raise RuntimeError("Offline acknowledgements exist; use reviewed forward recovery, not destructive downgrade")
    op.drop_table("order_sync_receipts")
