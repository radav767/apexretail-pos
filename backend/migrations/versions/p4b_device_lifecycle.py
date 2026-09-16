"""add Phase 4B terminal deletion tombstones

Revision ID: p4b_device_lifecycle
Revises: p4a_sales_inventory
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "p4b_device_lifecycle"
down_revision: Union[str, None] = "p4a_sales_inventory"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "devices",
        sa.Column("assignment_revision", sa.Integer(), server_default="1", nullable=False),
    )
    op.create_table(
        "device_tombstones",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("company_id", sa.UUID(), nullable=False),
        sa.Column("terminal_name", sa.String(120), nullable=False),
        sa.Column("pos_number", sa.Integer(), nullable=True),
        sa.Column("previous_shop_id", sa.UUID(), nullable=False),
        sa.Column("previous_branch_id", sa.UUID(), nullable=False),
        sa.Column("device_key_hash", sa.String(64), nullable=False),
        sa.Column("fingerprint_hash", sa.String(64), nullable=True),
        sa.Column("actor_user_id", sa.UUID(), nullable=True),
        sa.Column("actor_employee_id", sa.UUID(), nullable=True),
        sa.Column("action", sa.String(80), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("assignment_revision", sa.Integer(), nullable=False),
        sa.Column("historical_sales_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("historical_sales_count >= 0", name="ck_device_tombstones_sales_count"),
        sa.UniqueConstraint("device_key_hash"),
        sa.UniqueConstraint("fingerprint_hash"),
    )
    op.create_index("ix_device_tombstones_company_id", "device_tombstones", ["company_id"])
    op.execute("""
        CREATE FUNCTION reject_device_tombstone_mutation()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'device tombstones are immutable';
        END;
        $$
    """)
    op.execute("""
        CREATE TRIGGER trg_device_tombstones_immutable
        BEFORE UPDATE OR DELETE ON device_tombstones
        FOR EACH ROW EXECUTE FUNCTION reject_device_tombstone_mutation()
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER trg_device_tombstones_immutable ON device_tombstones")
    op.execute("DROP FUNCTION reject_device_tombstone_mutation()")
    op.drop_index("ix_device_tombstones_company_id", table_name="device_tombstones")
    op.drop_table("device_tombstones")
    op.drop_column("devices", "assignment_revision")
