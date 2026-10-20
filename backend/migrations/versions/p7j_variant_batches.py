"""Scope new lots to variants. Never assign historical lots to a variant."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "p7j_variant_batches"
down_revision = "p7i_pharmacy_return_holds"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("product_batches", sa.Column("variant_id", UUID(as_uuid=True), nullable=True))
    op.create_foreign_key("fk_batch_variant", "product_batches", "product_variants", ["variant_id"], ["id"])
    op.drop_constraint("uq_product_batch", "product_batches", type_="unique")
    op.create_index("uq_product_batch_standard", "product_batches", ["company_id", "branch_id", "product_id", "code"], unique=True, postgresql_where=sa.text("variant_id IS NULL"))
    op.create_index("uq_product_batch_variant", "product_batches", ["company_id", "branch_id", "product_id", "variant_id", "code"], unique=True, postgresql_where=sa.text("variant_id IS NOT NULL"))


def downgrade():
    if op.get_bind().execute(sa.text("SELECT EXISTS(SELECT FROM product_batches WHERE variant_id IS NOT NULL)")).scalar():
        raise RuntimeError("Variant batches exist; use forward recovery")
    op.drop_index("uq_product_batch_variant", table_name="product_batches")
    op.drop_index("uq_product_batch_standard", table_name="product_batches")
    op.create_unique_constraint("uq_product_batch", "product_batches", ["company_id", "branch_id", "product_id", "code"])
    op.drop_constraint("fk_batch_variant", "product_batches", type_="foreignkey")
    op.drop_column("product_batches", "variant_id")
