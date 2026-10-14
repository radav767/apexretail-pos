"""store immutable tender and change snapshots for credit settlements

Revision ID: p5e_settlement_tender_change
Revises: p5d_shift_cash_movements
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "p5e_settlement_tender_change"
down_revision: Union[str, None] = "p5d_shift_cash_movements"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "credit_settlements",
        sa.Column("tendered_amount_original", sa.Numeric(18, 4), nullable=True),
    )
    op.add_column(
        "credit_settlements",
        sa.Column("change_amount_original", sa.Numeric(18, 4), nullable=True),
    )
    op.create_check_constraint(
        "ck_credit_settlements_tender_change_consistent",
        "credit_settlements",
        "(tendered_amount_original IS NULL AND change_amount_original IS NULL) OR "
        "(tendered_amount_original IS NOT NULL AND change_amount_original IS NOT NULL "
        "AND original_amount IS NOT NULL AND tendered_amount_original >= original_amount "
        "AND tendered_amount_original - original_amount = change_amount_original)",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_credit_settlements_tender_change_consistent",
        "credit_settlements",
        type_="check",
    )
    op.drop_column("credit_settlements", "change_amount_original")
    op.drop_column("credit_settlements", "tendered_amount_original")
