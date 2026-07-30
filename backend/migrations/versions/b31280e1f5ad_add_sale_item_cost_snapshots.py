"""add sale item cost snapshots

Revision ID: b31280e1f5ad
Revises: e7b1c5a9d240
Create Date: 2026-07-30 22:02:26.092698

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b31280e1f5ad'
down_revision: Union[str, None] = 'e7b1c5a9d240'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "sale_items",
        sa.Column(
            "unit_cost",
            sa.Numeric(12, 2),
            nullable=False,
            server_default="0",
        ),
    )

    op.add_column(
        "sale_items",
        sa.Column(
            "line_cost",
            sa.Numeric(12, 2),
            nullable=False,
            server_default="0",
        ),
    )

    op.execute(
        """
        UPDATE sale_items AS si
        SET
            unit_cost = COALESCE(p.cost_price, 0),
            line_cost = ROUND(
                si.quantity * COALESCE(p.cost_price, 0),
                2
            )
        FROM products AS p
        WHERE p.id = si.product_id
        """
    )


def downgrade() -> None:
    op.drop_column("sale_items", "line_cost")
    op.drop_column("sale_items", "unit_cost")
