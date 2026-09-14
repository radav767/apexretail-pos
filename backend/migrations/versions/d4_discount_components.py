"""separate line and sale-wide discount snapshots

Revision ID: d4discountcomponents
Revises: d3phase2discount
"""

from alembic import op
import sqlalchemy as sa


revision = "d4discountcomponents"
down_revision = "d3phase2discount"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Existing aggregate discounts cannot be split reliably, so both new
    # component fields deliberately remain NULL for historical receipts.
    op.add_column(
        "sales",
        sa.Column("sale_discount_amount", sa.Numeric(12, 2), nullable=True),
    )
    op.add_column(
        "sale_items",
        sa.Column("line_discount_amount", sa.Numeric(12, 2), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("sale_items", "line_discount_amount")
    op.drop_column("sales", "sale_discount_amount")
