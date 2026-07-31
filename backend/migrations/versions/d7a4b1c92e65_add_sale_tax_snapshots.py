"""add sale tax snapshots

Revision ID: d7a4b1c92e65
Revises: c4f6a1b28d90
"""

from alembic import op
import sqlalchemy as sa


revision = "d7a4b1c92e65"
down_revision = "c4f6a1b28d90"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "sales",
        sa.Column(
            "subtotal_amount",
            sa.Numeric(12, 2),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )

    op.add_column(
        "sales",
        sa.Column(
            "tax_name",
            sa.String(40),
            nullable=True,
        ),
    )

    op.add_column(
        "sales",
        sa.Column(
            "tax_rate",
            sa.Numeric(7, 3),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )

    op.add_column(
        "sales",
        sa.Column(
            "tax_amount",
            sa.Numeric(12, 2),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )

    op.add_column(
        "sales",
        sa.Column(
            "tax_inclusive",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )

    # Existing transactions were completed before tax snapshots existed.
    op.execute(
        """
        UPDATE sales
        SET subtotal_amount = total_amount,
            tax_rate = 0,
            tax_amount = 0,
            tax_inclusive = false
        """
    )


def downgrade() -> None:
    op.drop_column("sales", "tax_inclusive")
    op.drop_column("sales", "tax_amount")
    op.drop_column("sales", "tax_rate")
    op.drop_column("sales", "tax_name")
    op.drop_column("sales", "subtotal_amount")
