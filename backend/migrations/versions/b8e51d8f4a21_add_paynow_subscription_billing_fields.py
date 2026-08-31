"""add paynow subscription billing fields

Revision ID: b8e51d8f4a21
Revises: 3c2a6f4b8d11
Create Date: 2026-08-31 12:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "b8e51d8f4a21"
down_revision: Union[str, None] = "3c2a6f4b8d11"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "company_subscriptions",
        sa.Column("billing_currency", sa.String(length=8), nullable=True),
    )
    op.add_column(
        "company_subscriptions",
        sa.Column("licensed_terminal_count", sa.Integer(), nullable=True),
    )
    op.add_column(
        "company_subscriptions",
        sa.Column("unit_price", sa.Numeric(12, 2), nullable=True),
    )
    op.add_column(
        "company_subscriptions",
        sa.Column("total_amount", sa.Numeric(12, 2), nullable=True),
    )

    op.add_column(
        "subscription_checkout_sessions",
        sa.Column("billing_period", sa.String(length=20), nullable=True),
    )
    op.add_column(
        "subscription_checkout_sessions",
        sa.Column("billing_currency", sa.String(length=8), nullable=True),
    )
    op.add_column(
        "subscription_checkout_sessions",
        sa.Column("unit_price", sa.Numeric(12, 2), nullable=True),
    )
    op.add_column(
        "subscription_checkout_sessions",
        sa.Column("terminal_count", sa.Integer(), nullable=True),
    )
    op.add_column(
        "subscription_checkout_sessions",
        sa.Column("total_amount", sa.Numeric(12, 2), nullable=True),
    )
    op.add_column(
        "subscription_checkout_sessions",
        sa.Column(
            "included_device_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )
    op.add_column(
        "subscription_checkout_sessions",
        sa.Column("paynow_reference", sa.String(length=160), nullable=True),
    )
    op.add_column(
        "subscription_checkout_sessions",
        sa.Column("poll_url", sa.Text(), nullable=True),
    )
    op.add_column(
        "subscription_checkout_sessions",
        sa.Column("payment_status", sa.String(length=40), nullable=True),
    )

    op.execute(
        """
        UPDATE company_subscriptions
        SET billing_currency = 'USD'
        WHERE billing_currency IS NULL
        """
    )


def downgrade() -> None:
    op.drop_column("subscription_checkout_sessions", "payment_status")
    op.drop_column("subscription_checkout_sessions", "poll_url")
    op.drop_column("subscription_checkout_sessions", "paynow_reference")
    op.drop_column("subscription_checkout_sessions", "included_device_ids")
    op.drop_column("subscription_checkout_sessions", "total_amount")
    op.drop_column("subscription_checkout_sessions", "terminal_count")
    op.drop_column("subscription_checkout_sessions", "unit_price")
    op.drop_column("subscription_checkout_sessions", "billing_currency")
    op.drop_column("subscription_checkout_sessions", "billing_period")

    op.drop_column("company_subscriptions", "total_amount")
    op.drop_column("company_subscriptions", "unit_price")
    op.drop_column("company_subscriptions", "licensed_terminal_count")
    op.drop_column("company_subscriptions", "billing_currency")
