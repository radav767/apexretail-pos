"""add immutable cashier shift cash movements

Revision ID: p5d_shift_cash_movements
Revises: p5c_transaction_currency
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "p5d_shift_cash_movements"
down_revision: Union[str, None] = "p5c_transaction_currency"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("cashier_shift_currency_snapshots", sa.Column("cash_in", sa.Numeric(18, 4), nullable=True))
    op.add_column("cashier_shift_currency_snapshots", sa.Column("cash_out", sa.Numeric(18, 4), nullable=True))
    op.create_table(
        "cashier_shift_cash_movements",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("company_id", sa.UUID(), nullable=False),
        sa.Column("shift_id", sa.UUID(), nullable=False),
        sa.Column("branch_id", sa.UUID(), nullable=False),
        sa.Column("device_id", sa.UUID(), nullable=False),
        sa.Column("employee_id", sa.UUID(), nullable=False),
        sa.Column("movement_type", sa.String(20), nullable=False),
        sa.Column("currency_code", sa.String(8), nullable=False),
        sa.Column("amount", sa.Numeric(18, 4), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("idempotency_key", sa.String(100), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("movement_type IN ('cash_in','cash_out')", name="ck_shift_cash_movement_type"),
        sa.CheckConstraint("amount > 0", name="ck_shift_cash_movement_positive_amount"),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"]),
        sa.ForeignKeyConstraint(["shift_id"], ["cashier_shifts.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["branch_id"], ["branches.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["device_id"], ["devices.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["employee_id"], ["employees.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("company_id", "idempotency_key", name="uq_shift_cash_movement_idempotency"),
    )
    op.create_index("ix_shift_cash_movements_shift_created", "cashier_shift_cash_movements", ["shift_id", "created_at"])
    op.execute("""
        CREATE FUNCTION protect_shift_cash_movement()
        RETURNS trigger LANGUAGE plpgsql AS $$
        DECLARE shift_row cashier_shifts%ROWTYPE;
        BEGIN
            IF TG_OP <> 'INSERT' THEN
                RAISE EXCEPTION 'cash shift movements are immutable';
            END IF;
            SELECT * INTO shift_row FROM cashier_shifts WHERE id=NEW.shift_id FOR UPDATE;
            IF NOT FOUND OR shift_row.status <> 'open' OR
               shift_row.company_id <> NEW.company_id OR shift_row.branch_id <> NEW.branch_id OR
               shift_row.device_id <> NEW.device_id OR shift_row.employee_id <> NEW.employee_id THEN
                RAISE EXCEPTION 'cash movement must belong to the active cashier shift';
            END IF;
            RETURN NEW;
        END;
        $$
    """)
    op.execute("CREATE TRIGGER trg_shift_cash_movement_protect BEFORE INSERT OR UPDATE OR DELETE ON cashier_shift_cash_movements FOR EACH ROW EXECUTE FUNCTION protect_shift_cash_movement()")


def downgrade() -> None:
    op.execute("DROP TRIGGER trg_shift_cash_movement_protect ON cashier_shift_cash_movements")
    op.execute("DROP FUNCTION protect_shift_cash_movement()")
    op.drop_index("ix_shift_cash_movements_shift_created", table_name="cashier_shift_cash_movements")
    op.drop_table("cashier_shift_cash_movements")
    op.drop_column("cashier_shift_currency_snapshots", "cash_out")
    op.drop_column("cashier_shift_currency_snapshots", "cash_in")
