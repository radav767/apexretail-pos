"""add product create idempotency

Revision ID: 1e4c9f7b2a6d
Revises: 8f3e21a4c9d1
Create Date: 2026-08-18 00:00:01.000000
"""

import uuid

from alembic import op, context
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "1e4c9f7b2a6d"
down_revision = "8f3e21a4c9d1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "products",
        sa.Column(
            "create_request_key",
            sa.String(length=120),
            nullable=True,
        ),
    )

    op.create_table(
        "product_creation_requests",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "company_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "product_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "idempotency_key",
            sa.String(length=120),
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
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["product_id"],
            ["products.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "company_id",
            "idempotency_key",
            name="uq_product_creation_requests_company_key",
        ),
        sa.UniqueConstraint(
            "product_id",
            name="uq_product_creation_requests_product_id",
        ),
    )

    op.create_index(
        "ix_product_creation_requests_company_id",
        "product_creation_requests",
        ["company_id"],
    )
    op.create_index(
        "ix_product_creation_requests_product_id",
        "product_creation_requests",
        ["product_id"],
    )

    connection = op.get_bind()

    if context.is_offline_mode():
        return

    rows = connection.execute(
        sa.text(
            """
            SELECT company_id, id AS product_id, create_request_key
            FROM products
            WHERE create_request_key IS NOT NULL
              AND btrim(create_request_key) <> ''
            """
        )
    ).mappings().all()

    for row in rows:
        connection.execute(
            sa.text(
                """
                INSERT INTO product_creation_requests (
                    id,
                    company_id,
                    product_id,
                    idempotency_key,
                    active,
                    deleted,
                    created_at,
                    updated_at
                )
                VALUES (
                    CAST(:id AS uuid),
                    CAST(:company_id AS uuid),
                    CAST(:product_id AS uuid),
                    :idempotency_key,
                    true,
                    false,
                    CURRENT_TIMESTAMP,
                    CURRENT_TIMESTAMP
                )
                ON CONFLICT (
                    company_id,
                    idempotency_key
                )
                DO NOTHING
                """
            ),
            {
                "id": str(uuid.uuid4()),
                "company_id": str(row["company_id"]),
                "product_id": str(row["product_id"]),
                "idempotency_key": row["create_request_key"],
            },
        )


def downgrade() -> None:
    op.drop_index(
        "ix_product_creation_requests_product_id",
        table_name="product_creation_requests",
    )
    op.drop_index(
        "ix_product_creation_requests_company_id",
        table_name="product_creation_requests",
    )
    op.drop_table("product_creation_requests")
    op.drop_column("products", "create_request_key")
