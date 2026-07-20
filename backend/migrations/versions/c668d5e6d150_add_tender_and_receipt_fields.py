"""add tender and receipt fields

Revision ID: c668d5e6d150
Revises: 02d0c8e6367e
Create Date: 2026-07-20 08:23:13.807786

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'c668d5e6d150'
down_revision: Union[str, None] = '02d0c8e6367e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add the fields as nullable first because historical sales already exist.
    op.add_column(
        "sales",
        sa.Column("receipt_number", sa.String(length=40), nullable=True),
    )
    op.add_column(
        "sales",
        sa.Column("amount_received", sa.Numeric(12, 2), nullable=True),
    )
    op.add_column(
        "sales",
        sa.Column("change_due", sa.Numeric(12, 2), nullable=True),
    )

    # Backfill all historical sales.
    # "LEG-" plus the UUID is exactly 40 characters and remains unique.
    op.execute(
        """
        UPDATE sales
        SET
            receipt_number = 'LEG-' || id::text,
            amount_received = COALESCE(total_amount, 0),
            change_due = 0
        """
    )

    # Enforce the final production constraints after backfilling.
    op.alter_column(
        "sales",
        "receipt_number",
        existing_type=sa.String(length=40),
        nullable=False,
    )
    op.alter_column(
        "sales",
        "amount_received",
        existing_type=sa.Numeric(12, 2),
        nullable=False,
    )
    op.alter_column(
        "sales",
        "change_due",
        existing_type=sa.Numeric(12, 2),
        nullable=False,
    )

    op.create_unique_constraint(
        "uq_sales_receipt_number",
        "sales",
        ["receipt_number"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_sales_receipt_number",
        "sales",
        type_="unique",
    )
    op.drop_column("sales", "change_due")
    op.drop_column("sales", "amount_received")
    op.drop_column("sales", "receipt_number")

