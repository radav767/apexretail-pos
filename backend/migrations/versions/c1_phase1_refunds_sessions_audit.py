"""phase 1 refunds, sessions, authorizations and audit"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "c1phase1refunds"
down_revision = "b8e51d8f4a21"
branch_labels = None
depends_on = None

def upgrade():
    op.add_column("sales", sa.Column("refund_reason", sa.String(500), nullable=True))
    op.add_column("sales", sa.Column("refund_method", sa.String(40), nullable=True))
    op.add_column("sales", sa.Column("reprint_count", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("sales", sa.Column("last_reprinted_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("products", sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True))
    op.create_table("employee_shop_access",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("employee_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("employees.id", ondelete="CASCADE"), nullable=False),
        sa.Column("shop_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("shops.id", ondelete="CASCADE"), nullable=False),
        sa.UniqueConstraint("employee_id", "shop_id", name="uq_employee_shop_access"))
    op.execute("""INSERT INTO employee_shop_access (id, employee_id, shop_id)
        SELECT gen_random_uuid(), id, shop_id FROM employees
        ON CONFLICT (employee_id, shop_id) DO NOTHING""")
    op.create_table("pos_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("employee_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("employees.id", ondelete="CASCADE"), nullable=False),
        sa.Column("device_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("devices.id", ondelete="CASCADE"), nullable=False),
        sa.Column("shop_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("shops.id", ondelete="CASCADE"), nullable=False),
        sa.Column("branch_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("branches.id", ondelete="CASCADE"), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("last_authenticated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoke_reason", sa.String(120), nullable=True))
    op.create_index("ix_pos_sessions_employee_active", "pos_sessions", ["employee_id", "revoked_at"])
    op.create_index("ix_pos_sessions_device_active", "pos_sessions", ["device_id", "revoked_at"])
    op.create_table("audit_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("actor_employee_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("employees.id", ondelete="SET NULL"), nullable=True),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("device_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("devices.id", ondelete="SET NULL"), nullable=True),
        sa.Column("action", sa.String(80), nullable=False), sa.Column("reason", sa.String(500), nullable=True),
        sa.Column("details", sa.JSON(), nullable=True), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False))

def downgrade():
    op.drop_table("audit_events"); op.drop_index("ix_pos_sessions_device_active", table_name="pos_sessions"); op.drop_index("ix_pos_sessions_employee_active", table_name="pos_sessions"); op.drop_table("pos_sessions"); op.drop_table("employee_shop_access")
    op.drop_column("products", "archived_at"); op.drop_column("sales", "last_reprinted_at"); op.drop_column("sales", "reprint_count"); op.drop_column("sales", "refund_method"); op.drop_column("sales", "refund_reason")
