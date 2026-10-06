"""add cashier shifts and per-currency drawer snapshots

Revision ID: p5b_cashier_shifts
Revises: p5a_company_currencies
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "p5b_cashier_shifts"
down_revision: Union[str, None] = "p5a_company_currencies"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


SUMMARY_COLUMNS = (
    "gross_sales_base", "net_sales_base", "cost_of_sales_base", "gross_profit_base",
    "discounts_base", "cash_sales_base", "card_sales_base", "mobile_sales_base",
    "credit_sales_base", "cash_settlements_base", "card_settlements_base",
    "mobile_settlements_base", "cash_expenses_base", "noncash_expenses_base",
)


def upgrade() -> None:
    op.add_column("company_settings", sa.Column("shift_enforcement_enabled", sa.Boolean(), server_default=sa.false(), nullable=False))
    op.add_column("company_settings", sa.Column("shift_required_from", sa.DateTime(timezone=True), nullable=True))
    columns = [
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("shift_number", sa.String(50), nullable=False),
        sa.Column("company_id", sa.UUID(), nullable=False),
        sa.Column("shop_id", sa.UUID(), nullable=False),
        sa.Column("branch_id", sa.UUID(), nullable=False),
        sa.Column("device_id", sa.UUID(), nullable=False),
        sa.Column("employee_id", sa.UUID(), nullable=False),
        sa.Column("opened_pos_session_id", sa.UUID(), nullable=False),
        sa.Column("status", sa.String(20), server_default="open", nullable=False),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("opening_note", sa.Text(), nullable=True),
        sa.Column("closing_note", sa.Text(), nullable=True),
        sa.Column("open_idempotency_key", sa.String(100), nullable=False),
        sa.Column("close_idempotency_key", sa.String(100), nullable=True),
    ]
    columns.extend(sa.Column(name, sa.Numeric(14, 2), nullable=True) for name in SUMMARY_COLUMNS)
    columns.extend([
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("status IN ('open','closed')", name="ck_cashier_shifts_status"),
        sa.CheckConstraint("(status='open' AND closed_at IS NULL) OR (status='closed' AND closed_at IS NOT NULL)", name="ck_cashier_shifts_closed_state"),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"]),
        sa.ForeignKeyConstraint(["shop_id"], ["shops.id"]),
        sa.ForeignKeyConstraint(["branch_id"], ["branches.id"]),
        sa.ForeignKeyConstraint(["device_id"], ["devices.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["employee_id"], ["employees.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["opened_pos_session_id"], ["pos_sessions.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("shift_number"),
        sa.UniqueConstraint("company_id", "open_idempotency_key", name="uq_cashier_shifts_open_key"),
        sa.UniqueConstraint("company_id", "close_idempotency_key", name="uq_cashier_shifts_close_key"),
    ])
    op.create_table("cashier_shifts", *columns)
    op.execute("CREATE UNIQUE INDEX uq_cashier_shifts_open_employee ON cashier_shifts (employee_id) WHERE status = 'open'")
    op.execute("CREATE UNIQUE INDEX uq_cashier_shifts_open_device ON cashier_shifts (device_id) WHERE status = 'open'")
    op.create_index("ix_cashier_shifts_company_opened", "cashier_shifts", ["company_id", "opened_at"])
    op.create_index("ix_cashier_shifts_company_branch_opened", "cashier_shifts", ["company_id", "branch_id", "opened_at"])

    op.create_table(
        "cashier_shift_currency_snapshots",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("shift_id", sa.UUID(), nullable=False),
        sa.Column("company_id", sa.UUID(), nullable=False),
        sa.Column("company_currency_id", sa.UUID(), nullable=False),
        sa.Column("currency_code", sa.String(8), nullable=False),
        sa.Column("currency_name_snapshot", sa.String(80), nullable=False),
        sa.Column("currency_symbol_snapshot", sa.String(10), nullable=False),
        sa.Column("decimal_places_snapshot", sa.Integer(), nullable=False),
        sa.Column("cash_accepted_snapshot", sa.Boolean(), nullable=False),
        sa.Column("card_accepted_snapshot", sa.Boolean(), nullable=False),
        sa.Column("mobile_accepted_snapshot", sa.Boolean(), nullable=False),
        sa.Column("opening_float", sa.Numeric(18, 4), nullable=False),
        sa.Column("cash_sales", sa.Numeric(18, 4), nullable=True),
        sa.Column("cash_refunds", sa.Numeric(18, 4), nullable=True),
        sa.Column("cash_settlements", sa.Numeric(18, 4), nullable=True),
        sa.Column("cash_expenses", sa.Numeric(18, 4), nullable=True),
        sa.Column("expected_cash", sa.Numeric(18, 4), nullable=True),
        sa.Column("counted_cash", sa.Numeric(18, 4), nullable=True),
        sa.Column("variance", sa.Numeric(18, 4), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("opening_float >= 0", name="ck_shift_currency_opening_nonnegative"),
        sa.CheckConstraint("counted_cash IS NULL OR counted_cash >= 0", name="ck_shift_currency_counted_nonnegative"),
        sa.ForeignKeyConstraint(["shift_id"], ["cashier_shifts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"]),
        sa.ForeignKeyConstraint(["company_currency_id"], ["company_currencies.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("shift_id", "currency_code", name="uq_shift_currency_code"),
    )
    op.create_index("ix_shift_currency_company_code", "cashier_shift_currency_snapshots", ["company_id", "currency_code"])

    op.execute("""
        CREATE FUNCTION protect_cashier_shift_mutation()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF TG_OP = 'DELETE' THEN
                RAISE EXCEPTION 'cashier shifts cannot be deleted';
            END IF;
            IF OLD.status = 'closed' THEN
                RAISE EXCEPTION 'closed cashier shifts are immutable';
            END IF;
            IF NEW.id <> OLD.id OR NEW.company_id <> OLD.company_id OR
               NEW.shop_id <> OLD.shop_id OR NEW.branch_id <> OLD.branch_id OR
               NEW.device_id <> OLD.device_id OR NEW.employee_id <> OLD.employee_id OR
               NEW.opened_pos_session_id <> OLD.opened_pos_session_id OR
               NEW.opened_at <> OLD.opened_at OR NEW.open_idempotency_key <> OLD.open_idempotency_key THEN
                RAISE EXCEPTION 'cashier shift identity is immutable';
            END IF;
            RETURN NEW;
        END;
        $$
    """)
    op.execute("CREATE TRIGGER trg_cashier_shifts_protect BEFORE UPDATE OR DELETE ON cashier_shifts FOR EACH ROW EXECUTE FUNCTION protect_cashier_shift_mutation()")
    op.execute("""
        CREATE FUNCTION protect_shift_currency_snapshot_mutation()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF TG_OP = 'DELETE' THEN
                RAISE EXCEPTION 'shift currency snapshots cannot be deleted';
            END IF;
            IF EXISTS (SELECT 1 FROM cashier_shifts s WHERE s.id=OLD.shift_id AND s.status='closed') THEN
                RAISE EXCEPTION 'closed shift currency snapshots are immutable';
            END IF;
            IF NEW.shift_id <> OLD.shift_id OR NEW.company_id <> OLD.company_id OR
               NEW.company_currency_id <> OLD.company_currency_id OR NEW.currency_code <> OLD.currency_code OR
               NEW.currency_name_snapshot <> OLD.currency_name_snapshot OR
               NEW.currency_symbol_snapshot <> OLD.currency_symbol_snapshot OR
               NEW.decimal_places_snapshot <> OLD.decimal_places_snapshot OR
               NEW.opening_float <> OLD.opening_float THEN
                RAISE EXCEPTION 'shift opening currency snapshot is immutable';
            END IF;
            RETURN NEW;
        END;
        $$
    """)
    op.execute("CREATE TRIGGER trg_shift_currency_snapshots_protect BEFORE UPDATE OR DELETE ON cashier_shift_currency_snapshots FOR EACH ROW EXECUTE FUNCTION protect_shift_currency_snapshot_mutation()")


def downgrade() -> None:
    op.execute("DROP TRIGGER trg_shift_currency_snapshots_protect ON cashier_shift_currency_snapshots")
    op.execute("DROP FUNCTION protect_shift_currency_snapshot_mutation()")
    op.execute("DROP TRIGGER trg_cashier_shifts_protect ON cashier_shifts")
    op.execute("DROP FUNCTION protect_cashier_shift_mutation()")
    op.drop_table("cashier_shift_currency_snapshots")
    op.drop_table("cashier_shifts")
    op.drop_column("company_settings", "shift_required_from")
    op.drop_column("company_settings", "shift_enforcement_enabled")
