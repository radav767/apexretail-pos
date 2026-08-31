"""add device activation attempt lockouts

Revision ID: 9a6b3d4e5f01
Revises: 6c7fd2a9c1ab
Create Date: 2026-08-18 15:10:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "9a6b3d4e5f01"
down_revision: Union[str, None] = "6c7fd2a9c1ab"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "device_activation_attempts",
        sa.Column(
            "company_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "device_fingerprint",
            sa.String(length=255),
            nullable=False,
        ),
        sa.Column(
            "failed_attempts",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "locked_until",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "last_failed_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
        sa.Column(
            "deleted",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
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
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "company_id",
            "device_fingerprint",
            name="uq_device_activation_attempts_company_fingerprint",
        ),
    )
    op.create_index(
        "ix_device_activation_attempts_company_id",
        "device_activation_attempts",
        ["company_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_device_activation_attempts_company_id",
        table_name="device_activation_attempts",
    )
    op.drop_table("device_activation_attempts")
