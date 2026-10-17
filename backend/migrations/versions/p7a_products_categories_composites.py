"""add professional product, category, variant and composite support

Revision ID: p7a_product_composites
Revises: p5h_runtime_write_permissions
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "p7a_product_composites"
down_revision: Union[str, None] = "p5h_runtime_write_permissions"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("categories", sa.Column("parent_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("categories", sa.Column("image_url", sa.String(length=500), nullable=True))
    op.create_foreign_key(
        "fk_categories_parent_id",
        "categories",
        "categories",
        ["parent_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index("ix_categories_parent_id", "categories", ["parent_id"])

    op.add_column(
        "products",
        sa.Column("product_type", sa.String(length=24), nullable=False, server_default="standard"),
    )
    op.add_column("products", sa.Column("image_url", sa.String(length=500), nullable=True))
    op.add_column("products", sa.Column("purchase_unit", sa.String(length=20), nullable=True))
    op.add_column(
        "products",
        sa.Column("units_per_purchase", sa.Numeric(12, 3), nullable=False, server_default="1"),
    )
    op.add_column(
        "products",
        sa.Column("track_inventory", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.add_column("products", sa.Column("tax_rate", sa.Numeric(7, 4), nullable=True))
    op.add_column(
        "products",
        sa.Column("tax_exempt", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_check_constraint(
        "ck_products_product_type",
        "products",
        "product_type IN ('standard', 'non_stock', 'service', 'composite', 'bundle', 'variable_weight')",
    )
    op.create_check_constraint(
        "ck_products_units_per_purchase_positive",
        "products",
        "units_per_purchase > 0",
    )

    op.create_table(
        "product_components",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("composite_product_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("component_product_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("quantity", sa.Numeric(12, 3), nullable=False),
        sa.Column("unit", sa.String(length=20), nullable=False, server_default="each"),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("deleted", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.CheckConstraint("quantity > 0", name="ck_product_components_quantity_positive"),
        sa.CheckConstraint("composite_product_id <> component_product_id", name="ck_product_components_not_self"),
        sa.ForeignKeyConstraint(["composite_product_id"], ["products.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["component_product_id"], ["products.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("composite_product_id", "component_product_id", name="uq_product_components_recipe_pair"),
    )
    op.create_index("ix_product_components_company_id", "product_components", ["company_id"])
    op.create_index("ix_product_components_composite_product_id", "product_components", ["composite_product_id"])
    op.create_index("ix_product_components_component_product_id", "product_components", ["component_product_id"])

    op.create_table(
        "product_variants",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("product_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("sku", sa.String(length=80), nullable=True),
        sa.Column("barcode", sa.String(length=80), nullable=True),
        sa.Column("attributes", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("cost_price", sa.Numeric(12, 2), nullable=True),
        sa.Column("selling_price", sa.Numeric(12, 2), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("deleted", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("company_id", "sku", name="uq_product_variants_company_sku"),
        sa.UniqueConstraint("company_id", "barcode", name="uq_product_variants_company_barcode"),
    )
    op.create_index("ix_product_variants_company_id", "product_variants", ["company_id"])
    op.create_index("ix_product_variants_product_id", "product_variants", ["product_id"])

    op.create_table(
        "product_price_levels",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("product_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("price", sa.Numeric(12, 2), nullable=False),
        sa.Column("minimum_quantity", sa.Numeric(12, 3), nullable=False, server_default="1"),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("deleted", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.CheckConstraint("price >= 0", name="ck_product_price_levels_price_nonnegative"),
        sa.CheckConstraint("minimum_quantity > 0", name="ck_product_price_levels_minimum_positive"),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("product_id", "name", name="uq_product_price_levels_name"),
    )
    op.create_index("ix_product_price_levels_company_id", "product_price_levels", ["company_id"])
    op.create_index("ix_product_price_levels_product_id", "product_price_levels", ["product_id"])

    op.create_table(
        "sale_item_components",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("sale_item_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("component_product_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("component_name", sa.String(length=160), nullable=False),
        sa.Column("quantity", sa.Numeric(12, 3), nullable=False),
        sa.Column("unit", sa.String(length=20), nullable=False),
        sa.Column("unit_cost", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.CheckConstraint("quantity > 0", name="ck_sale_item_components_quantity_positive"),
        sa.ForeignKeyConstraint(["sale_item_id"], ["sale_items.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["component_product_id"], ["products.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_sale_item_components_company_id", "sale_item_components", ["company_id"])
    op.create_index("ix_sale_item_components_sale_item_id", "sale_item_components", ["sale_item_id"])
    op.create_index("ix_sale_item_components_component_product_id", "sale_item_components", ["component_product_id"])

    # Runtime DML only. Ownership and schema-level DDL privileges are unchanged.
    op.execute(
        """
        DO $$
        BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'apex_user') THEN
            GRANT SELECT, INSERT, UPDATE, DELETE ON
              product_components, product_variants, product_price_levels,
              sale_item_components TO apex_user;
          END IF;
        END
        $$
        """
    )


def downgrade() -> None:
    op.drop_index("ix_sale_item_components_component_product_id", table_name="sale_item_components")
    op.drop_index("ix_sale_item_components_sale_item_id", table_name="sale_item_components")
    op.drop_index("ix_sale_item_components_company_id", table_name="sale_item_components")
    op.drop_table("sale_item_components")
    op.drop_index("ix_product_price_levels_product_id", table_name="product_price_levels")
    op.drop_index("ix_product_price_levels_company_id", table_name="product_price_levels")
    op.drop_table("product_price_levels")
    op.drop_index("ix_product_variants_product_id", table_name="product_variants")
    op.drop_index("ix_product_variants_company_id", table_name="product_variants")
    op.drop_table("product_variants")
    op.drop_index("ix_product_components_component_product_id", table_name="product_components")
    op.drop_index("ix_product_components_composite_product_id", table_name="product_components")
    op.drop_index("ix_product_components_company_id", table_name="product_components")
    op.drop_table("product_components")
    op.drop_constraint("ck_products_units_per_purchase_positive", "products", type_="check")
    op.drop_constraint("ck_products_product_type", "products", type_="check")
    op.drop_column("products", "tax_exempt")
    op.drop_column("products", "tax_rate")
    op.drop_column("products", "track_inventory")
    op.drop_column("products", "units_per_purchase")
    op.drop_column("products", "purchase_unit")
    op.drop_column("products", "image_url")
    op.drop_column("products", "product_type")
    op.drop_index("ix_categories_parent_id", table_name="categories")
    op.drop_constraint("fk_categories_parent_id", "categories", type_="foreignkey")
    op.drop_column("categories", "image_url")
    op.drop_column("categories", "parent_id")
