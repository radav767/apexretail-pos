"""Separate tip liabilities, business tips and immutable shift summaries."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB
revision = "p7h_tips_accounting"
down_revision = "p7g_batch_stock_operations"
branch_labels = None
depends_on = None


def uid(name, target=None, **kwargs):
    return sa.Column(name, UUID(as_uuid=True), *([sa.ForeignKey(target)] if target else []), **kwargs)


def upgrade():
    op.create_table("tip_settings", uid("company_id", "companies.id", primary_key=True),
        sa.Column("enabled", sa.Boolean(), nullable=False), sa.Column("policy", sa.String(16), nullable=False),
        sa.Column("weights", JSONB(), nullable=False), sa.Column("business_retention_confirmed", sa.Boolean(), nullable=False),
        uid("service_product_id", "products.id"), sa.CheckConstraint("policy IN ('staff','shared','business')", name="ck_tip_settings_policy"))
    op.create_table("tip_entries", uid("id", primary_key=True), uid("company_id", "companies.id", nullable=False),
        uid("branch_id", "branches.id", nullable=False), uid("shift_id", "cashier_shifts.id", nullable=False),
        uid("sale_id", "sales.id"), uid("original_id", "tip_entries.id"), uid("request_id", nullable=False),
        sa.Column("payload_hash", sa.String(64), nullable=False), sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("policy", sa.String(16), nullable=False), sa.Column("payment_method", sa.String(16), nullable=False),
        sa.Column("currency_code", sa.String(8), nullable=False), sa.Column("decimal_places", sa.Numeric(1,0), nullable=False),
        sa.Column("amount", sa.Numeric(18,4), nullable=False), sa.Column("reason", sa.String(500), nullable=False),
        sa.Column("reference", sa.String(120), nullable=False), uid("cash_movement_id", "cashier_shift_cash_movements.id", unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("company_id", "request_id", name="uq_tip_entry_request"),
        sa.CheckConstraint("amount > 0 AND decimal_places BETWEEN 0 AND 4", name="ck_tip_amount"),
        sa.CheckConstraint("kind IN ('collect','reverse','payout') AND payment_method IN ('cash','card','mobile') AND policy IN ('staff','shared','business')", name="ck_tip_kind"))
    op.create_table("tip_entitlements", uid("id", primary_key=True), uid("entry_id", "tip_entries.id", nullable=False),
        uid("employee_id", "employees.id", nullable=False), sa.Column("amount", sa.Numeric(18,4), nullable=False),
        sa.UniqueConstraint("entry_id", "employee_id", name="uq_tip_entry_employee"))
    op.add_column("cashier_shifts", sa.Column("tips_snapshot", JSONB(), nullable=True))
    op.create_index("ix_tip_entries_shift", "tip_entries", ["shift_id"])
    op.create_index("ix_tip_entries_company_date", "tip_entries", ["company_id", "created_at"])
    op.create_index("ix_tip_entitlements_employee", "tip_entitlements", ["employee_id"])
    op.execute("""DO $$ BEGIN IF EXISTS(SELECT FROM pg_roles WHERE rolname='apex_user') THEN
        GRANT SELECT,INSERT,UPDATE ON tip_settings TO apex_user;
        GRANT SELECT,INSERT ON tip_entries,tip_entitlements TO apex_user;
        GRANT UPDATE(tips_snapshot) ON cashier_shifts TO apex_user;
    END IF; END $$""")
    # Protect financial tip records even from accidental ORM/owner mutation.
    op.execute("""CREATE FUNCTION reject_tip_mutation() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN RAISE EXCEPTION 'Tip ledger is append-only; post an audited reversal'; END $$""")
    for table in ("tip_entries", "tip_entitlements"):
        op.execute(f"CREATE TRIGGER {table}_immutable BEFORE UPDATE OR DELETE ON {table} FOR EACH ROW EXECUTE FUNCTION reject_tip_mutation()")
    op.execute("""CREATE FUNCTION protect_closed_tip_snapshot() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN IF OLD.status='closed' AND NEW.tips_snapshot IS DISTINCT FROM OLD.tips_snapshot THEN
        RAISE EXCEPTION 'Closed tip snapshot is immutable'; END IF; RETURN NEW; END $$""")
    op.execute("CREATE TRIGGER closed_tip_snapshot BEFORE UPDATE OF tips_snapshot ON cashier_shifts FOR EACH ROW EXECUTE FUNCTION protect_closed_tip_snapshot()")


def downgrade():
    if op.get_bind().execute(sa.text("SELECT EXISTS(SELECT FROM tip_entries) OR EXISTS(SELECT FROM tip_settings)")).scalar():
        raise RuntimeError("Tip records/settings exist; use reviewed forward recovery")
    for table in ("tip_entitlements", "tip_entries"):
        op.drop_table(table)
    op.execute("DROP FUNCTION reject_tip_mutation()")
    op.execute("DROP TRIGGER closed_tip_snapshot ON cashier_shifts")
    op.execute("DROP FUNCTION protect_closed_tip_snapshot()")
    op.drop_column("cashier_shifts", "tips_snapshot")
    op.drop_table("tip_settings")
