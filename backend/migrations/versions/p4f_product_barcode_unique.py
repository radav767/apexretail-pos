"""add company-scoped normalized product barcode uniqueness

Revision ID: p4f_product_barcode_unique
Revises: p4e_expenses
"""
from typing import Sequence, Union

from alembic import op
from sqlalchemy import text


revision: str = "p4f_product_barcode_unique"
down_revision: Union[str, None] = "p4e_expenses"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    connection = op.get_bind()
    collisions = connection.execute(
        text(
            """
            SELECT company_id, btrim(barcode) AS normalized_barcode,
                   count(*) AS product_count
            FROM products
            WHERE deleted IS FALSE
              AND barcode IS NOT NULL
              AND btrim(barcode) <> ''
            GROUP BY company_id, btrim(barcode)
            HAVING count(*) > 1
            LIMIT 10
            """
        )
    ).mappings().all()
    if collisions:
        evidence = "; ".join(
            f"company={row['company_id']} barcode={row['normalized_barcode']!r} "
            f"count={row['product_count']}"
            for row in collisions
        )
        raise RuntimeError(
            "Cannot create product barcode unique index; "
            f"trim-normalized collisions exist: {evidence}"
        )

    op.execute(
        """
        CREATE UNIQUE INDEX uq_products_company_barcode_trimmed
        ON products (company_id, btrim(barcode))
        WHERE barcode IS NOT NULL
          AND btrim(barcode) <> ''
          AND deleted IS FALSE
        """
    )


def downgrade() -> None:
    op.drop_index(
        "uq_products_company_barcode_trimmed",
        table_name="products",
    )
