"""add branch links to sales and inventory

Revision ID: d42f8a9c1b70
Revises: b31a9f4c7e20
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "d42f8a9c1b70"
down_revision = "b31a9f4c7e20"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "sales",
        sa.Column(
            "shop_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
    )
    op.add_column(
        "sales",
        sa.Column(
            "branch_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
    )

    op.create_foreign_key(
        "fk_sales_shop_id",
        "sales",
        "shops",
        ["shop_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_sales_branch_id",
        "sales",
        "branches",
        ["branch_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.create_index(
        "ix_sales_shop_id",
        "sales",
        ["shop_id"],
    )
    op.create_index(
        "ix_sales_branch_id",
        "sales",
        ["branch_id"],
    )

    op.add_column(
        "inventory_movements",
        sa.Column(
            "shop_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
    )
    op.add_column(
        "inventory_movements",
        sa.Column(
            "branch_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
    )

    op.create_foreign_key(
        "fk_inventory_movements_shop_id",
        "inventory_movements",
        "shops",
        ["shop_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_inventory_movements_branch_id",
        "inventory_movements",
        "branches",
        ["branch_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.create_index(
        "ix_inventory_movements_shop_id",
        "inventory_movements",
        ["shop_id"],
    )
    op.create_index(
        "ix_inventory_movements_branch_id",
        "inventory_movements",
        ["branch_id"],
    )

    connection = op.get_bind()

    connection.execute(
        sa.text(
            """
            UPDATE sales AS s
            SET
                branch_id = (
                    SELECT b.id
                    FROM branches AS b
                    JOIN shops AS sh ON sh.id = b.shop_id
                    WHERE b.company_id = s.company_id
                      AND b.active = true
                      AND b.deleted = false
                      AND sh.active = true
                      AND sh.deleted = false
                    ORDER BY b.created_at
                    LIMIT 1
                ),
                shop_id = (
                    SELECT b.shop_id
                    FROM branches AS b
                    JOIN shops AS sh ON sh.id = b.shop_id
                    WHERE b.company_id = s.company_id
                      AND b.active = true
                      AND b.deleted = false
                      AND sh.active = true
                      AND sh.deleted = false
                    ORDER BY b.created_at
                    LIMIT 1
                )
            WHERE s.branch_id IS NULL
            """
        )
    )

    connection.execute(
        sa.text(
            """
            UPDATE inventory_movements AS movement
            SET
                branch_id = (
                    SELECT b.id
                    FROM branches AS b
                    JOIN shops AS sh ON sh.id = b.shop_id
                    WHERE b.company_id = movement.company_id
                      AND b.active = true
                      AND b.deleted = false
                      AND sh.active = true
                      AND sh.deleted = false
                    ORDER BY b.created_at
                    LIMIT 1
                ),
                shop_id = (
                    SELECT b.shop_id
                    FROM branches AS b
                    JOIN shops AS sh ON sh.id = b.shop_id
                    WHERE b.company_id = movement.company_id
                      AND b.active = true
                      AND b.deleted = false
                      AND sh.active = true
                      AND sh.deleted = false
                    ORDER BY b.created_at
                    LIMIT 1
                )
            WHERE movement.branch_id IS NULL
            """
        )
    )


def downgrade():
    op.drop_index(
        "ix_inventory_movements_branch_id",
        table_name="inventory_movements",
    )
    op.drop_index(
        "ix_inventory_movements_shop_id",
        table_name="inventory_movements",
    )
    op.drop_constraint(
        "fk_inventory_movements_branch_id",
        "inventory_movements",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_inventory_movements_shop_id",
        "inventory_movements",
        type_="foreignkey",
    )
    op.drop_column("inventory_movements", "branch_id")
    op.drop_column("inventory_movements", "shop_id")

    op.drop_index(
        "ix_sales_branch_id",
        table_name="sales",
    )
    op.drop_index(
        "ix_sales_shop_id",
        table_name="sales",
    )
    op.drop_constraint(
        "fk_sales_branch_id",
        "sales",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_sales_shop_id",
        "sales",
        type_="foreignkey",
    )
    op.drop_column("sales", "branch_id")
    op.drop_column("sales", "shop_id")
