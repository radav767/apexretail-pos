"""add nullable sale discount snapshots for Dashboard Phase 2

Revision ID: d3phase2discount
Revises: c2phase1inventory
"""

from alembic import op
import sqlalchemy as sa


revision = "d3phase2discount"
down_revision = "c2phase1inventory"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # No default and no backfill: historical prices cannot prove that a
    # discount occurred, so existing records must remain unknown.
    op.add_column(
        "sales",
        sa.Column(
            "discount_amount",
            sa.Numeric(12, 2),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("sales", "discount_amount")
