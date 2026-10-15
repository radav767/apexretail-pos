"""add immutable audited offline sale resolutions

Revision ID: p5g_offline_resolution
Revises: p5f_phase4_shift_z
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "p5g_offline_resolution"
down_revision: Union[str, None] = "p5f_phase4_shift_z"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "offline_sale_resolutions",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("company_id", sa.UUID(), nullable=False),
        sa.Column("client_sale_id", sa.UUID(), nullable=False),
        sa.Column("original_shift_id", sa.UUID(), nullable=False),
        sa.Column("original_employee_id", sa.UUID(), nullable=False),
        sa.Column("original_device_id", sa.UUID(), nullable=False),
        sa.Column("sale_id", sa.UUID(), nullable=True),
        sa.Column("action", sa.String(40), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("payload_sha256", sa.String(64), nullable=False),
        sa.Column("payload_snapshot", sa.JSON(), nullable=False),
        sa.Column("idempotency_key", sa.String(100), nullable=False),
        sa.Column("resolved_by_user_id", sa.UUID(), nullable=True),
        sa.Column("resolved_by_employee_id", sa.UUID(), nullable=True),
        sa.Column("resolver_name_snapshot", sa.String(160), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("action IN ('post_to_original_shift','retain_quarantined')", name="ck_offline_resolution_action"),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"]),
        sa.ForeignKeyConstraint(["original_shift_id"], ["cashier_shifts.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["original_employee_id"], ["employees.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["original_device_id"], ["devices.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["sale_id"], ["sales.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["resolved_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["resolved_by_employee_id"], ["employees.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("company_id", "client_sale_id", name="uq_offline_resolution_client_sale"),
        sa.UniqueConstraint("company_id", "idempotency_key", name="uq_offline_resolution_key"),
    )
    op.create_index("ix_offline_resolutions_company_created", "offline_sale_resolutions", ["company_id", "created_at"])
    op.create_index("ix_offline_resolutions_shift", "offline_sale_resolutions", ["original_shift_id"])
    op.execute("""
        CREATE FUNCTION protect_offline_sale_resolution_mutation()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          RAISE EXCEPTION 'offline sale resolution evidence is immutable';
        END; $$
    """)
    op.execute("CREATE TRIGGER trg_offline_sale_resolutions_immutable BEFORE UPDATE OR DELETE ON offline_sale_resolutions FOR EACH ROW EXECUTE FUNCTION protect_offline_sale_resolution_mutation()")


def downgrade() -> None:
    op.execute("DROP TRIGGER trg_offline_sale_resolutions_immutable ON offline_sale_resolutions")
    op.execute("DROP FUNCTION protect_offline_sale_resolution_mutation()")
    op.drop_table("offline_sale_resolutions")
