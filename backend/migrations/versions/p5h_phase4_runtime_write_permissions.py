"""grant least-privilege Phase 4 runtime shift updates

Revision ID: p5h_runtime_write_permissions
Revises: p5g_offline_resolution
"""
from typing import Sequence, Union

from alembic import op


revision: str = "p5h_runtime_write_permissions"
down_revision: Union[str, None] = "p5g_offline_resolution"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # The production schema is owned by the protected migration role.  The
    # application role needs UPDATE DML on the fields written during closing;
    # any column-level UPDATE grant also permits PostgreSQL row locks.  Existing
    # triggers keep identity fields, opening snapshots, and every closed
    # snapshot immutable.  No ownership, CREATE, ALTER, DROP, TRIGGER, broad
    # table UPDATE, or other DDL privilege is granted.
    op.execute(
        """
        DO $$
        BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'apex_user') THEN
            GRANT UPDATE (
              gross_sales_base, net_sales_base, cost_of_sales_base,
              gross_profit_base, discounts_base, cash_sales_base,
              card_sales_base, mobile_sales_base, credit_sales_base,
              cash_settlements_base, card_settlements_base,
              mobile_settlements_base, cash_expenses_base,
              noncash_expenses_base, cash_refunds_base, refunds_base,
              cash_in_base, cash_out_base, status, closed_at, closing_note,
              close_idempotency_key, closed_by_user_id,
              closed_by_employee_id, closing_user_name_snapshot,
              report_generated_at
            ) ON cashier_shifts TO apex_user;

            GRANT UPDATE (
              cash_sales, cash_refunds, cash_settlements, cash_expenses,
              cash_in, cash_out, expected_cash, counted_cash, variance
            ) ON cashier_shift_currency_snapshots TO apex_user;
          END IF;
        END
        $$
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'apex_user') THEN
            REVOKE UPDATE (
              gross_sales_base, net_sales_base, cost_of_sales_base,
              gross_profit_base, discounts_base, cash_sales_base,
              card_sales_base, mobile_sales_base, credit_sales_base,
              cash_settlements_base, card_settlements_base,
              mobile_settlements_base, cash_expenses_base,
              noncash_expenses_base, cash_refunds_base, refunds_base,
              cash_in_base, cash_out_base, status, closed_at, closing_note,
              close_idempotency_key, closed_by_user_id,
              closed_by_employee_id, closing_user_name_snapshot,
              report_generated_at
            ) ON cashier_shifts FROM apex_user;

            REVOKE UPDATE (
              cash_sales, cash_refunds, cash_settlements, cash_expenses,
              cash_in, cash_out, expected_cash, counted_cash, variance
            ) ON cashier_shift_currency_snapshots FROM apex_user;
          END IF;
        END
        $$
        """
    )
