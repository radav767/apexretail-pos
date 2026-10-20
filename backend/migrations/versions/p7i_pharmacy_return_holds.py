"""Hold newly refunded lot stock pending audited inspection. No backfill."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID
revision = "p7i_pharmacy_return_holds"
down_revision = "p7h_tips_accounting"
branch_labels = None
depends_on = None


def uid(name, target=None, **kwargs):
    return sa.Column(name, UUID(as_uuid=True), *([sa.ForeignKey(target)] if target else []), **kwargs)


def upgrade():
    op.create_table("batch_return_holds", uid("id", primary_key=True), uid("company_id", "companies.id", nullable=False),
        uid("branch_id", "branches.id", nullable=False), uid("product_id", "products.id", nullable=False),
        uid("movement_id", "inventory_movements.id", nullable=False, unique=True), sa.Column("quantity", sa.Numeric(12,3), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("quantity > 0", name="ck_batch_return_quantity"))
    op.create_index("ix_batch_hold_scope", "batch_return_holds", ["company_id", "branch_id", "product_id"])
    op.create_table("batch_return_inspections", uid("id", primary_key=True), uid("company_id", "companies.id", nullable=False),
        uid("hold_id", "batch_return_holds.id", nullable=False, unique=True), uid("batch_id", "product_batches.id", nullable=False),
        uid("request_id", nullable=False), sa.Column("payload_hash", sa.String(64), nullable=False),
        sa.Column("disposition", sa.String(16), nullable=False),
        sa.Column("reason", sa.String(500), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("company_id", "request_id", name="uq_batch_return_request"),
        sa.CheckConstraint("disposition IN ('restock','dispose')", name="ck_return_disposition"))
    op.create_table("batch_inspection_disposals", uid("inspection_id", "batch_return_inspections.id", primary_key=True),
        uid("movement_id", "inventory_movements.id", nullable=False, unique=True))
    op.execute("""DO $$ BEGIN IF EXISTS(SELECT FROM pg_roles WHERE rolname='apex_user') THEN
        GRANT SELECT,INSERT ON batch_return_holds,batch_return_inspections,batch_inspection_disposals TO apex_user;
    END IF; END $$""")
    for table in ("batch_return_holds", "batch_return_inspections", "batch_inspection_disposals"):
        op.execute(f"CREATE TRIGGER {table}_immutable BEFORE UPDATE OR DELETE ON {table} FOR EACH ROW EXECUTE FUNCTION reject_tip_mutation()")


def downgrade():
    if op.get_bind().execute(sa.text("SELECT EXISTS(SELECT FROM batch_return_holds)")).scalar():
        raise RuntimeError("Pharmacy return holds exist; use forward recovery")
    op.drop_table("batch_inspection_disposals")
    op.drop_table("batch_return_inspections")
    op.drop_table("batch_return_holds")
