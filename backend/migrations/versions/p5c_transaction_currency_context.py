"""add shift links and immutable transaction currency snapshots

Revision ID: p5c_transaction_currency
Revises: p5b_cashier_shifts
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "p5c_transaction_currency"
down_revision: Union[str, None] = "p5b_cashier_shifts"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    for table in ("sales", "credit_settlements", "expenses"):
        op.add_column(table, sa.Column("shift_id", sa.UUID(), nullable=True))
        op.create_foreign_key(f"fk_{table}_shift", table, "cashier_shifts", ["shift_id"], ["id"], ondelete="RESTRICT")
        op.create_index(f"ix_{table}_shift_id", table, ["shift_id"])

    op.add_column("credit_receivables", sa.Column("shift_id", sa.UUID(), nullable=True))
    op.create_foreign_key("fk_credit_receivables_shift", "credit_receivables", "cashier_shifts", ["shift_id"], ["id"], ondelete="RESTRICT")
    op.create_index("ix_credit_receivables_shift_id", "credit_receivables", ["shift_id"])

    for table in ("sales", "credit_settlements"):
        op.add_column(table, sa.Column("base_currency_code", sa.String(8), nullable=True))
        op.add_column(table, sa.Column("payment_currency_code", sa.String(8), nullable=True))
        op.add_column(table, sa.Column("exchange_rate_id", sa.UUID(), nullable=True))
        op.add_column(table, sa.Column("exchange_rate_snapshot", sa.Numeric(20, 10), nullable=True))
        op.create_foreign_key(f"fk_{table}_exchange_rate", table, "currency_exchange_rates", ["exchange_rate_id"], ["id"], ondelete="RESTRICT")

    op.add_column("sales", sa.Column("payment_amount_original", sa.Numeric(18, 4), nullable=True))
    op.add_column("sales", sa.Column("tendered_amount_original", sa.Numeric(18, 4), nullable=True))
    op.add_column("sales", sa.Column("change_amount_original", sa.Numeric(18, 4), nullable=True))
    op.add_column("credit_settlements", sa.Column("original_amount", sa.Numeric(18, 4), nullable=True))

    op.add_column("expenses", sa.Column("device_id", sa.UUID(), nullable=True))
    op.add_column("expenses", sa.Column("base_currency_code", sa.String(8), nullable=True))
    op.add_column("expenses", sa.Column("exchange_rate_id", sa.UUID(), nullable=True))
    op.add_column("expenses", sa.Column("exchange_rate_snapshot", sa.Numeric(20, 10), nullable=True))
    op.add_column("expenses", sa.Column("original_amount", sa.Numeric(18, 4), nullable=True))
    op.create_foreign_key("fk_expenses_device", "expenses", "devices", ["device_id"], ["id"], ondelete="SET NULL")
    op.create_foreign_key("fk_expenses_exchange_rate", "expenses", "currency_exchange_rates", ["exchange_rate_id"], ["id"], ondelete="RESTRICT")

    # Historical rows deliberately remain NULL. Only new snapshot-bearing sales
    # are protected; existing status/reprint/refund maintenance stays valid.
    op.execute("""
        CREATE FUNCTION protect_sale_financial_context()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF OLD.shift_id IS DISTINCT FROM NEW.shift_id OR
               OLD.base_currency_code IS DISTINCT FROM NEW.base_currency_code OR
               OLD.payment_currency_code IS DISTINCT FROM NEW.payment_currency_code OR
               OLD.exchange_rate_id IS DISTINCT FROM NEW.exchange_rate_id OR
               OLD.exchange_rate_snapshot IS DISTINCT FROM NEW.exchange_rate_snapshot OR
               OLD.payment_amount_original IS DISTINCT FROM NEW.payment_amount_original OR
               OLD.tendered_amount_original IS DISTINCT FROM NEW.tendered_amount_original OR
               OLD.change_amount_original IS DISTINCT FROM NEW.change_amount_original THEN
                RAISE EXCEPTION 'sale shift and currency snapshots are immutable';
            END IF;
            RETURN NEW;
        END;
        $$
    """)
    op.execute("CREATE TRIGGER trg_sales_financial_context_immutable BEFORE UPDATE ON sales FOR EACH ROW EXECUTE FUNCTION protect_sale_financial_context()")


def downgrade() -> None:
    op.execute("DROP TRIGGER trg_sales_financial_context_immutable ON sales")
    op.execute("DROP FUNCTION protect_sale_financial_context()")
    op.drop_constraint("fk_expenses_exchange_rate", "expenses", type_="foreignkey")
    op.drop_constraint("fk_expenses_device", "expenses", type_="foreignkey")
    for column in ("original_amount", "exchange_rate_snapshot", "exchange_rate_id", "base_currency_code", "device_id"):
        op.drop_column("expenses", column)
    op.drop_column("credit_settlements", "original_amount")
    for column in ("change_amount_original", "tendered_amount_original", "payment_amount_original"):
        op.drop_column("sales", column)
    for table in ("credit_settlements", "sales"):
        op.drop_constraint(f"fk_{table}_exchange_rate", table, type_="foreignkey")
        for column in ("exchange_rate_snapshot", "exchange_rate_id", "payment_currency_code", "base_currency_code"):
            op.drop_column(table, column)
    op.drop_index("ix_credit_receivables_shift_id", table_name="credit_receivables")
    op.drop_constraint("fk_credit_receivables_shift", "credit_receivables", type_="foreignkey")
    op.drop_column("credit_receivables", "shift_id")
    for table in ("expenses", "credit_settlements", "sales"):
        op.drop_index(f"ix_{table}_shift_id", table_name=table)
        op.drop_constraint(f"fk_{table}_shift", table, type_="foreignkey")
        op.drop_column(table, "shift_id")
