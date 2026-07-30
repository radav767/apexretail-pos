"""add company settings

Revision ID: c4f6a1b28d90
Revises: b31280e1f5ad
Create Date: 2026-07-31
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "c4f6a1b28d90"
down_revision: Union[str, None] = "b31280e1f5ad"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "company_settings",
        sa.Column(
            "company_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column("address", sa.Text(), nullable=True),
        sa.Column(
            "contact_email",
            sa.String(length=255),
            nullable=True,
        ),
        sa.Column(
            "currency_code",
            sa.String(length=10),
            server_default="USD",
            nullable=False,
        ),
        sa.Column(
            "currency_symbol",
            sa.String(length=10),
            server_default="$",
            nullable=False,
        ),
        sa.Column(
            "decimal_places",
            sa.Integer(),
            server_default="2",
            nullable=False,
        ),
        sa.Column(
            "tax_name",
            sa.String(length=40),
            server_default="VAT",
            nullable=False,
        ),
        sa.Column(
            "tax_rate",
            sa.Numeric(precision=6, scale=3),
            server_default="0",
            nullable=False,
        ),
        sa.Column(
            "tax_inclusive",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column("receipt_header", sa.Text(), nullable=True),
        sa.Column("receipt_footer", sa.Text(), nullable=True),
        sa.Column(
            "paper_size",
            sa.String(length=10),
            server_default="80mm",
            nullable=False,
        ),
        sa.Column(
            "auto_print",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column(
            "payment_methods",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text(
                """'["cash", "card", "mobile", "credit"]'::jsonb"""
            ),
            nullable=False,
        ),
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "active",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
        sa.Column(
            "deleted",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "company_id",
            name="uq_company_settings_company_id",
        ),
    )


def downgrade() -> None:
    op.drop_table("company_settings")
