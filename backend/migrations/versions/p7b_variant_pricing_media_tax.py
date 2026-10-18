"""variant stock, customer pricing, media and item tax snapshots
Revision ID: p7b_variant_pricing_tax
Revises: p7a_product_composites
"""
from typing import Sequence,Union
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql
revision="p7b_variant_pricing_tax"; down_revision="p7a_product_composites"; branch_labels=None; depends_on=None
def upgrade():
    op.add_column("customers",sa.Column("price_level_name",sa.String(80)))
    op.add_column("sales",sa.Column("price_level_name_snapshot",sa.String(80)))
    for column in [sa.Column("variant_id",postgresql.UUID(as_uuid=True)),sa.Column("variant_name_snapshot",sa.String(120)),sa.Column("tax_rate_snapshot",sa.Numeric(7,4)),sa.Column("tax_amount",sa.Numeric(12,2)),sa.Column("tax_exempt_snapshot",sa.Boolean()),sa.Column("price_level_name_snapshot",sa.String(80))]: op.add_column("sale_items",column)
    op.create_foreign_key("fk_sale_items_variant_id","sale_items","product_variants",["variant_id"],["id"],ondelete="RESTRICT"); op.create_index("ix_sale_items_variant_id","sale_items",["variant_id"])
    op.add_column("inventory_movements",sa.Column("variant_id",postgresql.UUID(as_uuid=True))); op.create_foreign_key("fk_inventory_movements_variant_id","inventory_movements","product_variants",["variant_id"],["id"],ondelete="SET NULL"); op.create_index("ix_inventory_movements_variant_id","inventory_movements",["variant_id"])
    op.create_table("variant_inventory_balances",sa.Column("id",postgresql.UUID(as_uuid=True),primary_key=True),sa.Column("company_id",postgresql.UUID(as_uuid=True),sa.ForeignKey("companies.id",ondelete="CASCADE"),nullable=False),sa.Column("shop_id",postgresql.UUID(as_uuid=True),sa.ForeignKey("shops.id",ondelete="CASCADE"),nullable=False),sa.Column("branch_id",postgresql.UUID(as_uuid=True),sa.ForeignKey("branches.id",ondelete="CASCADE"),nullable=False),sa.Column("product_id",postgresql.UUID(as_uuid=True),sa.ForeignKey("products.id",ondelete="CASCADE"),nullable=False),sa.Column("variant_id",postgresql.UUID(as_uuid=True),sa.ForeignKey("product_variants.id",ondelete="CASCADE"),nullable=False),sa.Column("quantity",sa.Numeric(12,3),nullable=False,server_default="0"),sa.Column("reorder_level",sa.Numeric(12,3),nullable=False,server_default="0"),sa.Column("active",sa.Boolean(),nullable=False,server_default=sa.true()),sa.Column("deleted",sa.Boolean(),nullable=False,server_default=sa.false()),sa.Column("created_at",sa.DateTime(timezone=True),server_default=sa.func.now(),nullable=False),sa.Column("updated_at",sa.DateTime(timezone=True),server_default=sa.func.now(),nullable=False),sa.CheckConstraint("quantity>=0",name="ck_variant_balance_quantity"),sa.UniqueConstraint("company_id","branch_id","variant_id",name="uq_variant_balance_branch_variant"))
    for c in ("company_id","branch_id","product_id","variant_id"): op.create_index(f"ix_variant_inventory_balances_{c}","variant_inventory_balances",[c])
    op.create_table("product_media",sa.Column("id",postgresql.UUID(as_uuid=True),primary_key=True),sa.Column("company_id",postgresql.UUID(as_uuid=True),sa.ForeignKey("companies.id",ondelete="CASCADE"),nullable=False),sa.Column("product_id",postgresql.UUID(as_uuid=True),sa.ForeignKey("products.id",ondelete="CASCADE"),nullable=False),sa.Column("storage_name",sa.String(120),nullable=False,unique=True),sa.Column("original_name",sa.String(255),nullable=False),sa.Column("content_type",sa.String(40),nullable=False),sa.Column("size_bytes",sa.Integer(),nullable=False),sa.Column("sha256",sa.String(64),nullable=False),sa.Column("created_at",sa.DateTime(timezone=True),server_default=sa.func.now(),nullable=False),sa.CheckConstraint("size_bytes>0 AND size_bytes<=5242880",name="ck_product_media_size"))
    op.create_index("ix_product_media_company_id","product_media",["company_id"]); op.create_index("ix_product_media_product_id","product_media",["product_id"])
    op.execute("DO $$ BEGIN IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname='apex_user') THEN GRANT SELECT,INSERT,UPDATE,DELETE ON variant_inventory_balances,product_media TO apex_user; END IF; END $$")
def downgrade():
    op.drop_index("ix_product_media_product_id",table_name="product_media"); op.drop_index("ix_product_media_company_id",table_name="product_media"); op.drop_table("product_media")
    for c in reversed(("company_id","branch_id","product_id","variant_id")): op.drop_index(f"ix_variant_inventory_balances_{c}",table_name="variant_inventory_balances")
    op.drop_table("variant_inventory_balances"); op.drop_index("ix_inventory_movements_variant_id",table_name="inventory_movements"); op.drop_constraint("fk_inventory_movements_variant_id","inventory_movements",type_="foreignkey"); op.drop_column("inventory_movements","variant_id"); op.drop_index("ix_sale_items_variant_id",table_name="sale_items"); op.drop_constraint("fk_sale_items_variant_id","sale_items",type_="foreignkey")
    for c in ("price_level_name_snapshot","tax_exempt_snapshot","tax_amount","tax_rate_snapshot","variant_name_snapshot","variant_id"): op.drop_column("sale_items",c)
    op.drop_column("sales","price_level_name_snapshot"); op.drop_column("customers","price_level_name")
