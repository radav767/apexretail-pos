"""add offline sale identity

Revision ID: e8b4d0c721aa
Revises: d7a4b1c92e65
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "e8b4d0c721aa"
down_revision = "d7a4b1c92e65"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "sales",
        sa.Column(
            "client_sale_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
    )

    op.add_column(
        "sales",
        sa.Column(
            "client_created_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )

    op.create_index(
        "uq_sales_client_sale_id",
        "sales",
        ["client_sale_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(
        "uq_sales_client_sale_id",
        table_name="sales",
    )
    op.drop_column("sales", "client_created_at")
    op.drop_column("sales", "client_sale_id")
