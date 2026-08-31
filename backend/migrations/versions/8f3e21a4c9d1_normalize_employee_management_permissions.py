"""normalize employee management permissions

Revision ID: 8f3e21a4c9d1
Revises: b31280e1f5ad
Create Date: 2026-08-18 00:00:00.000000
"""

from alembic import op


# revision identifiers, used by Alembic.
revision = "8f3e21a4c9d1"
down_revision = "e8b4d0c721aa"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE employees
        SET permissions = jsonb_strip_nulls(
            COALESCE(permissions, '{}'::jsonb)
            || jsonb_build_object(
                'manage_inventory',
                COALESCE(
                    (permissions ->> 'manage_inventory')::boolean,
                    (permissions ->> 'inventory')::boolean,
                    false
                ),
                'manage_products',
                COALESCE(
                    (permissions ->> 'manage_products')::boolean,
                    (permissions ->> 'products')::boolean,
                    false
                )
            )
        )
        """
    )


def downgrade() -> None:
    op.execute(
        """
        UPDATE employees
        SET permissions = jsonb_strip_nulls(
            COALESCE(permissions, '{}'::jsonb)
            || jsonb_build_object(
                'inventory',
                COALESCE(
                    (permissions ->> 'inventory')::boolean,
                    (permissions ->> 'manage_inventory')::boolean,
                    false
                ),
                'products',
                COALESCE(
                    (permissions ->> 'products')::boolean,
                    (permissions ->> 'manage_products')::boolean,
                    false
                )
            )
        )
        """
    )
