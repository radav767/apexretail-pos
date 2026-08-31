"""phase 1 pos onboarding settings snapshots

Revision ID: 6c7fd2a9c1ab
Revises: 1e4c9f7b2a6d
Create Date: 2026-08-18 00:30:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "6c7fd2a9c1ab"
down_revision: Union[str, None] = "1e4c9f7b2a6d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "devices",
        sa.Column("pos_number", sa.Integer(), nullable=True),
    )
    op.add_column(
        "devices",
        sa.Column("friendly_name", sa.String(length=120), nullable=True),
    )
    op.add_column(
        "devices",
        sa.Column(
            "last_seen_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.add_column(
        "devices",
        sa.Column(
            "last_seen_platform",
            sa.String(length=50),
            nullable=True,
        ),
    )
    op.add_column(
        "devices",
        sa.Column(
            "last_seen_app_version",
            sa.String(length=50),
            nullable=True,
        ),
    )
    op.add_column(
        "devices",
        sa.Column(
            "status",
            sa.String(length=20),
            nullable=False,
            server_default="active",
        ),
    )
    op.add_column(
        "devices",
        sa.Column(
            "claimed_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.add_column(
        "devices",
        sa.Column(
            "deactivated_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.add_column(
        "devices",
        sa.Column(
            "deactivation_reason",
            sa.Text(),
            nullable=True,
        ),
    )
    op.add_column(
        "devices",
        sa.Column(
            "removed_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.add_column(
        "devices",
        sa.Column(
            "activation_code_hash",
            sa.String(length=128),
            nullable=True,
        ),
    )
    op.add_column(
        "devices",
        sa.Column(
            "activation_code_expires_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.add_column(
        "devices",
        sa.Column(
            "device_fingerprint",
            sa.String(length=255),
            nullable=True,
        ),
    )
    op.add_column(
        "devices",
        sa.Column(
            "pending_shop_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
    )
    op.add_column(
        "devices",
        sa.Column(
            "pending_branch_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
    )
    op.create_foreign_key(
        "fk_devices_pending_shop_id_shops",
        "devices",
        "shops",
        ["pending_shop_id"],
        ["id"],
    )
    op.create_foreign_key(
        "fk_devices_pending_branch_id_branches",
        "devices",
        "branches",
        ["pending_branch_id"],
        ["id"],
    )
    op.create_index(
        "uq_devices_branch_pos_number_active",
        "devices",
        ["branch_id", "pos_number"],
        unique=True,
        postgresql_where=sa.text(
            "pos_number IS NOT NULL AND removed_at IS NULL"
        ),
    )

    op.execute(
        """
        UPDATE devices
        SET
            friendly_name = COALESCE(NULLIF(BTRIM(name), ''), friendly_name),
            last_seen_platform = platform,
            last_seen_app_version = app_version,
            status = CASE
                WHEN active = false THEN 'deactivated'
                ELSE 'active'
            END,
            claimed_at = COALESCE(claimed_at, created_at),
            pending_shop_id = COALESCE(pending_shop_id, shop_id),
            pending_branch_id = COALESCE(pending_branch_id, branch_id)
        """
    )

    op.alter_column(
        "devices",
        "status",
        server_default=None,
    )

    op.add_column(
        "shops",
        sa.Column(
            "address_line_1",
            sa.String(length=255),
            nullable=True,
        ),
    )
    op.add_column(
        "shops",
        sa.Column(
            "address_line_2",
            sa.String(length=255),
            nullable=True,
        ),
    )
    op.add_column(
        "shops",
        sa.Column(
            "city",
            sa.String(length=120),
            nullable=True,
        ),
    )
    op.add_column(
        "shops",
        sa.Column(
            "state_province",
            sa.String(length=120),
            nullable=True,
        ),
    )
    op.add_column(
        "shops",
        sa.Column(
            "country",
            sa.String(length=120),
            nullable=True,
        ),
    )
    op.add_column(
        "shops",
        sa.Column(
            "phone",
            sa.String(length=80),
            nullable=True,
        ),
    )
    op.add_column(
        "shops",
        sa.Column(
            "tax_vat_number",
            sa.String(length=120),
            nullable=True,
        ),
    )

    op.add_column(
        "sales",
        sa.Column(
            "shop_name_snapshot",
            sa.String(length=160),
            nullable=True,
        ),
    )
    op.add_column(
        "sales",
        sa.Column(
            "shop_address_snapshot",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )
    op.add_column(
        "sales",
        sa.Column(
            "branch_name_snapshot",
            sa.String(length=160),
            nullable=True,
        ),
    )
    op.add_column(
        "sales",
        sa.Column(
            "device_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
    )
    op.add_column(
        "sales",
        sa.Column(
            "pos_name_snapshot",
            sa.String(length=160),
            nullable=True,
        ),
    )
    op.add_column(
        "sales",
        sa.Column(
            "pos_number_snapshot",
            sa.String(length=40),
            nullable=True,
        ),
    )
    op.add_column(
        "sales",
        sa.Column(
            "receipt_footer_snapshot",
            sa.Text(),
            nullable=True,
        ),
    )
    op.create_foreign_key(
        "fk_sales_device_id_devices",
        "sales",
        "devices",
        ["device_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_sales_device_id",
        "sales",
        ["device_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_sales_device_id", table_name="sales")
    op.drop_constraint(
        "fk_sales_device_id_devices",
        "sales",
        type_="foreignkey",
    )
    op.drop_column("sales", "receipt_footer_snapshot")
    op.drop_column("sales", "pos_number_snapshot")
    op.drop_column("sales", "pos_name_snapshot")
    op.drop_column("sales", "device_id")
    op.drop_column("sales", "branch_name_snapshot")
    op.drop_column("sales", "shop_address_snapshot")
    op.drop_column("sales", "shop_name_snapshot")

    op.drop_column("shops", "tax_vat_number")
    op.drop_column("shops", "phone")
    op.drop_column("shops", "country")
    op.drop_column("shops", "state_province")
    op.drop_column("shops", "city")
    op.drop_column("shops", "address_line_2")
    op.drop_column("shops", "address_line_1")

    op.drop_index(
        "uq_devices_branch_pos_number_active",
        table_name="devices",
    )
    op.drop_constraint(
        "fk_devices_pending_branch_id_branches",
        "devices",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_devices_pending_shop_id_shops",
        "devices",
        type_="foreignkey",
    )
    op.drop_column("devices", "pending_branch_id")
    op.drop_column("devices", "pending_shop_id")
    op.drop_column("devices", "device_fingerprint")
    op.drop_column("devices", "activation_code_expires_at")
    op.drop_column("devices", "activation_code_hash")
    op.drop_column("devices", "removed_at")
    op.drop_column("devices", "deactivation_reason")
    op.drop_column("devices", "deactivated_at")
    op.drop_column("devices", "claimed_at")
    op.drop_column("devices", "status")
    op.drop_column("devices", "last_seen_app_version")
    op.drop_column("devices", "last_seen_platform")
    op.drop_column("devices", "last_seen_at")
    op.drop_column("devices", "friendly_name")
    op.drop_column("devices", "pos_number")
