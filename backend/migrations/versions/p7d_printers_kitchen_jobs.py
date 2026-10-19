"""Add isolated printer stations, routing and delivery queue (no financial rewrites)."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = "p7d_printers_kitchen_jobs"
down_revision = "p7c_employee_roles_permissions"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("printer_stations",
        sa.Column("id", UUID(), primary_key=True),
        sa.Column("company_id", UUID(), sa.ForeignKey("companies.id"), nullable=False),
        sa.Column("shop_id", UUID(), sa.ForeignKey("shops.id"), nullable=False),
        sa.Column("branch_id", UUID(), sa.ForeignKey("branches.id"), nullable=False),
        sa.Column("device_id", UUID(), sa.ForeignKey("devices.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("purpose", sa.String(16), nullable=False),
        sa.Column("transport", sa.String(16), nullable=False),
        sa.Column("address", sa.String(180), nullable=False),
        sa.Column("paper_width", sa.String(4), nullable=False),
        sa.Column("auto_print", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("purpose IN ('receipt','kitchen','bar')", name="ck_printer_purpose"),
        sa.CheckConstraint("transport IN ('bluetooth','usb','network','system')", name="ck_printer_transport"),
        sa.CheckConstraint("paper_width IN ('58mm','80mm')", name="ck_printer_width"))
    op.create_index("ix_printer_stations_company_id", "printer_stations", ["company_id"])
    op.create_table("printer_routes",
        sa.Column("id", UUID(), primary_key=True),
        sa.Column("station_id", UUID(), sa.ForeignKey("printer_stations.id"), nullable=False),
        sa.Column("target_type", sa.String(16), nullable=False),
        sa.Column("target_id", UUID(), nullable=False),
        sa.UniqueConstraint("station_id", "target_type", "target_id", name="uq_printer_route"),
        sa.CheckConstraint("target_type IN ('product','category')", name="ck_printer_route_type"))
    op.create_index("ix_printer_routes_station_id", "printer_routes", ["station_id"])
    op.create_table("print_jobs",
        sa.Column("id", UUID(), primary_key=True),
        sa.Column("company_id", UUID(), sa.ForeignKey("companies.id"), nullable=False),
        sa.Column("station_id", UUID(), sa.ForeignKey("printer_stations.id"), nullable=False),
        sa.Column("sale_id", UUID(), sa.ForeignKey("sales.id")),
        sa.Column("requested_employee_id", UUID(), sa.ForeignKey("employees.id", ondelete="RESTRICT")),
        sa.Column("request_key", sa.String(160), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("payload", JSONB(), nullable=False),
        sa.Column("payload_hash", sa.String(64), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("claim_hash", sa.String(64)),
        sa.Column("claimed_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("last_error", sa.String(240)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("station_id", "request_key", name="uq_print_job_request"),
        sa.CheckConstraint("status IN ('pending','sending','submitted','uncertain','cancelled')", name="ck_print_job_status"))
    for column in ("company_id", "station_id"):
        op.create_index(f"ix_print_jobs_{column}", "print_jobs", [column])
    # Do not grant DDL or change owners. Immutable snapshots cannot be updated
    # by the runtime role; only delivery state columns may change.
    op.execute("""DO $$ BEGIN IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname='apex_user') THEN
        GRANT SELECT,INSERT,UPDATE ON printer_stations TO apex_user;
        GRANT SELECT,INSERT,DELETE ON printer_routes TO apex_user;
        GRANT SELECT,INSERT ON print_jobs TO apex_user;
        GRANT UPDATE(status,attempts,claim_hash,claimed_at,completed_at,last_error) ON print_jobs TO apex_user;
    END IF; END $$""")


def downgrade():
    # Operational use requires queue archival/review before removing this data.
    for table in ("print_jobs", "printer_routes", "printer_stations"):
        op.drop_table(table)
