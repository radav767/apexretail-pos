"""add branch inventory balances

Revision ID: b31a9f4c7e20
Revises: 126d0a13fddb
"""

import uuid

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "b31a9f4c7e20"
down_revision = "126d0a13fddb"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "inventory_balances",
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
            "shop_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "branch_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "product_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "quantity",
            sa.Numeric(12, 3),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "reorder_level",
            sa.Numeric(12, 3),
            nullable=False,
            server_default="0",
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
            ["shop_id"],
            ["shops.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["branch_id"],
            ["branches.id"],
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
            "branch_id",
            "product_id",
            name="uq_inventory_balance_branch_product",
        ),
    )

    op.create_index(
        "ix_inventory_balances_company_id",
        "inventory_balances",
        ["company_id"],
    )
    op.create_index(
        "ix_inventory_balances_shop_id",
        "inventory_balances",
        ["shop_id"],
    )
    op.create_index(
        "ix_inventory_balances_branch_id",
        "inventory_balances",
        ["branch_id"],
    )
    op.create_index(
        "ix_inventory_balances_product_id",
        "inventory_balances",
        ["product_id"],
    )

    connection = op.get_bind()

    companies = connection.execute(
        sa.text(
            """
            SELECT id
            FROM companies
            WHERE deleted = false
            ORDER BY created_at
            """
        )
    ).mappings().all()

    for company in companies:
        company_id = str(company["id"])

        branch = connection.execute(
            sa.text(
                """
                SELECT
                    b.id AS branch_id,
                    b.shop_id
                FROM branches b
                JOIN shops s ON s.id = b.shop_id
                WHERE b.company_id = CAST(:company_id AS uuid)
                  AND b.active = true
                  AND b.deleted = false
                  AND s.active = true
                  AND s.deleted = false
                ORDER BY b.created_at
                LIMIT 1
                """
            ),
            {"company_id": company_id},
        ).mappings().first()

        if branch:
            shop_id = str(branch["shop_id"])
            branch_id = str(branch["branch_id"])
        else:
            shop = connection.execute(
                sa.text(
                    """
                    SELECT id
                    FROM shops
                    WHERE company_id = CAST(:company_id AS uuid)
                      AND deleted = false
                    ORDER BY created_at
                    LIMIT 1
                    """
                ),
                {"company_id": company_id},
            ).mappings().first()

            if shop:
                shop_id = str(shop["id"])
            else:
                shop_id = str(uuid.uuid4())

                connection.execute(
                    sa.text(
                        """
                        INSERT INTO shops (
                            id,
                            company_id,
                            name,
                            created_at,
                            updated_at,
                            active,
                            deleted
                        )
                        VALUES (
                            CAST(:id AS uuid),
                            CAST(:company_id AS uuid),
                            'Main Shop',
                            CURRENT_TIMESTAMP,
                            CURRENT_TIMESTAMP,
                            true,
                            false
                        )
                        """
                    ),
                    {
                        "id": shop_id,
                        "company_id": company_id,
                    },
                )

            branch_id = str(uuid.uuid4())

            connection.execute(
                sa.text(
                    """
                    INSERT INTO branches (
                        id,
                        company_id,
                        shop_id,
                        name,
                        created_at,
                        updated_at,
                        active,
                        deleted
                    )
                    VALUES (
                        CAST(:id AS uuid),
                        CAST(:company_id AS uuid),
                        CAST(:shop_id AS uuid),
                        'Main Branch',
                        CURRENT_TIMESTAMP,
                        CURRENT_TIMESTAMP,
                        true,
                        false
                    )
                    """
                ),
                {
                    "id": branch_id,
                    "company_id": company_id,
                    "shop_id": shop_id,
                },
            )

        products = connection.execute(
            sa.text(
                """
                SELECT
                    id,
                    COALESCE(stock_qty, 0) AS stock_qty,
                    COALESCE(reorder_level, 0) AS reorder_level
                FROM products
                WHERE company_id = CAST(:company_id AS uuid)
                  AND deleted = false
                """
            ),
            {"company_id": company_id},
        ).mappings().all()

        for product in products:
            connection.execute(
                sa.text(
                    """
                    INSERT INTO inventory_balances (
                        id,
                        company_id,
                        shop_id,
                        branch_id,
                        product_id,
                        quantity,
                        reorder_level,
                        active,
                        deleted,
                        created_at,
                        updated_at
                    )
                    VALUES (
                        CAST(:id AS uuid),
                        CAST(:company_id AS uuid),
                        CAST(:shop_id AS uuid),
                        CAST(:branch_id AS uuid),
                        CAST(:product_id AS uuid),
                        :quantity,
                        :reorder_level,
                        true,
                        false,
                        CURRENT_TIMESTAMP,
                        CURRENT_TIMESTAMP
                    )
                    ON CONFLICT (
                        company_id,
                        branch_id,
                        product_id
                    )
                    DO NOTHING
                    """
                ),
                {
                    "id": str(uuid.uuid4()),
                    "company_id": company_id,
                    "shop_id": shop_id,
                    "branch_id": branch_id,
                    "product_id": str(product["id"]),
                    "quantity": product["stock_qty"],
                    "reorder_level": product["reorder_level"],
                },
            )


def downgrade():
    op.drop_index(
        "ix_inventory_balances_product_id",
        table_name="inventory_balances",
    )
    op.drop_index(
        "ix_inventory_balances_branch_id",
        table_name="inventory_balances",
    )
    op.drop_index(
        "ix_inventory_balances_shop_id",
        table_name="inventory_balances",
    )
    op.drop_index(
        "ix_inventory_balances_company_id",
        table_name="inventory_balances",
    )
    op.drop_table("inventory_balances")
