"""add Phase 4A nullable reporting evidence

Revision ID: p4a_sales_inventory
Revises: d4discountcomponents
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "p4a_sales_inventory"
down_revision: Union[str, None] = "d4discountcomponents"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "sale_items",
        sa.Column("category_id_snapshot", sa.UUID(), nullable=True),
    )
    op.add_column(
        "sale_items",
        sa.Column("category_name_snapshot", sa.String(120), nullable=True),
    )
    op.add_column(
        "sale_items",
        sa.Column("cost_snapshot_available", sa.Boolean(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("sale_items", "cost_snapshot_available")
    op.drop_column("sale_items", "category_name_snapshot")
    op.drop_column("sale_items", "category_id_snapshot")
