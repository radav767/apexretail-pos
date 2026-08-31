"""add weighted product snapshots and subscriptions

Revision ID: 3c2a6f4b8d11
Revises: 9a6b3d4e5f01
Create Date: 2026-08-19 09:10:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "3c2a6f4b8d11"
down_revision: Union[str, None] = "9a6b3d4e5f01"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
    op.execute(
        "UPDATE products SET unit = 'each' WHERE unit IS NULL OR BTRIM(unit) = ''"
    )
    op.add_column(
        "sale_items",
        sa.Column(
            "selling_unit",
            sa.String(length=20),
            nullable=False,
            server_default="each",
        ),
    )
    op.add_column(
        "sales",
        sa.Column(
            "original_sale_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
    )
    op.create_foreign_key(
        "fk_sales_original_sale_id_sales",
        "sales",
        "sales",
        ["original_sale_id"],
        ["id"],
    )
    op.add_column(
        "sale_items",
        sa.Column(
            "original_sale_item_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
    )
    op.create_foreign_key(
        "fk_sale_items_original_sale_item_id_sale_items",
        "sale_items",
        "sale_items",
        ["original_sale_item_id"],
        ["id"],
    )
    op.execute(
        "UPDATE sale_items SET selling_unit = 'each' WHERE selling_unit IS NULL OR BTRIM(selling_unit) = ''"
    )
    op.alter_column("sale_items", "selling_unit", server_default=None)

    op.create_table(
        "company_subscriptions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "company_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column("plan", sa.String(length=20), nullable=True),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("trial_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("trial_ends_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "current_period_started_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "current_period_ends_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column("grace_ends_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("provider", sa.String(length=80), nullable=True),
        sa.Column("provider_reference", sa.String(length=160), nullable=True),
        sa.Column("status_reason", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("company_id"),
    )
    op.create_index(
        "ix_company_subscriptions_company_id",
        "company_subscriptions",
        ["company_id"],
    )
    op.create_index(
        "ix_company_subscriptions_status",
        "company_subscriptions",
        ["status"],
    )

    op.create_table(
        "company_subscription_history",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "company_subscription_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "company_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column("action", sa.String(length=80), nullable=False),
        sa.Column("plan", sa.String(length=20), nullable=True),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("provider", sa.String(length=80), nullable=True),
        sa.Column("provider_reference", sa.String(length=160), nullable=True),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["company_subscription_id"],
            ["company_subscriptions.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_company_subscription_history_company_id",
        "company_subscription_history",
        ["company_id"],
    )

    op.create_table(
        "subscription_webhook_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider", sa.String(length=80), nullable=False),
        sa.Column("provider_event_id", sa.String(length=160), nullable=False),
        sa.Column("event_type", sa.String(length=120), nullable=False),
        sa.Column(
            "company_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "processed",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("processing_error", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("provider_event_id"),
    )
    op.create_index(
        "ix_subscription_webhook_events_provider",
        "subscription_webhook_events",
        ["provider"],
    )
    op.create_index(
        "ix_subscription_webhook_events_company_id",
        "subscription_webhook_events",
        ["company_id"],
    )

    op.create_table(
        "subscription_checkout_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "company_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "company_subscription_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column("plan", sa.String(length=20), nullable=False),
        sa.Column("provider", sa.String(length=80), nullable=False),
        sa.Column(
            "session_reference",
            sa.String(length=160),
            nullable=False,
        ),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("checkout_url", sa.Text(), nullable=True),
        sa.Column(
            "payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["company_subscription_id"],
            ["company_subscriptions.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("session_reference"),
    )
    op.create_index(
        "ix_subscription_checkout_sessions_company_id",
        "subscription_checkout_sessions",
        ["company_id"],
    )

    op.execute(
        """
        INSERT INTO company_subscriptions (
            id,
            company_id,
            plan,
            status,
            trial_started_at,
            trial_ends_at,
            current_period_started_at,
            current_period_ends_at,
            grace_ends_at,
            provider,
            provider_reference,
            status_reason
        )
        SELECT
            gen_random_uuid(),
            companies.id,
            NULL,
            'active',
            NULL,
            NULL,
            NOW(),
            NULL,
            NULL,
            'system',
            'grandfathered',
            'Grandfathered active during subscription rollout'
        FROM companies
        WHERE NOT EXISTS (
            SELECT 1
            FROM company_subscriptions
            WHERE company_subscriptions.company_id = companies.id
        )
        """
    )

    op.execute(
        """
        INSERT INTO company_subscription_history (
            id,
            company_subscription_id,
            company_id,
            action,
            plan,
            status,
            provider,
            provider_reference,
            payload,
            note
        )
        SELECT
            gen_random_uuid(),
            company_subscriptions.id,
            company_subscriptions.company_id,
            'grandfathered',
            company_subscriptions.plan,
            company_subscriptions.status,
            company_subscriptions.provider,
            company_subscriptions.provider_reference,
            NULL,
            company_subscriptions.status_reason
        FROM company_subscriptions
        WHERE company_subscriptions.provider_reference = 'grandfathered'
        """
    )


def downgrade() -> None:
    op.drop_index(
        "ix_subscription_checkout_sessions_company_id",
        table_name="subscription_checkout_sessions",
    )
    op.drop_table("subscription_checkout_sessions")

    op.drop_index(
        "ix_subscription_webhook_events_company_id",
        table_name="subscription_webhook_events",
    )
    op.drop_index(
        "ix_subscription_webhook_events_provider",
        table_name="subscription_webhook_events",
    )
    op.drop_table("subscription_webhook_events")

    op.drop_index(
        "ix_company_subscription_history_company_id",
        table_name="company_subscription_history",
    )
    op.drop_table("company_subscription_history")

    op.drop_index(
        "ix_company_subscriptions_status",
        table_name="company_subscriptions",
    )
    op.drop_index(
        "ix_company_subscriptions_company_id",
        table_name="company_subscriptions",
    )
    op.drop_table("company_subscriptions")

    op.drop_constraint(
        "fk_sale_items_original_sale_item_id_sale_items",
        "sale_items",
        type_="foreignkey",
    )
    op.drop_column("sale_items", "original_sale_item_id")
    op.drop_constraint(
        "fk_sales_original_sale_id_sales",
        "sales",
        type_="foreignkey",
    )
    op.drop_column("sales", "original_sale_id")
    op.drop_column("sale_items", "selling_unit")
