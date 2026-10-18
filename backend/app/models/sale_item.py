import uuid
from sqlalchemy import Boolean, Column, String, Numeric, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from app.db.base import Base

class SaleItem(Base):
    __tablename__ = "sale_items"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    sale_id = Column(UUID(as_uuid=True), ForeignKey("sales.id"), nullable=False)
    product_id = Column(UUID(as_uuid=True), nullable=False)
    variant_id = Column(UUID(as_uuid=True), ForeignKey("product_variants.id", ondelete="RESTRICT"), nullable=True)
    variant_name_snapshot = Column(String(120), nullable=True)
    original_sale_item_id = Column(
        UUID(as_uuid=True),
        ForeignKey("sale_items.id", ondelete="SET NULL"),
        nullable=True,
    )
    product_name = Column(String(160), nullable=False)
    category_id_snapshot = Column(UUID(as_uuid=True), nullable=True)
    category_name_snapshot = Column(String(120), nullable=True)
    quantity = Column(Numeric(12, 3), default=1)
    selling_unit = Column(String(20), nullable=False, default="each")
    unit_price = Column(Numeric(12, 2), default=0)
    line_total = Column(Numeric(12, 2), default=0)
    # The entered line-level component, separate from any sale-wide amount
    # allocated into line_total. Nullable for pre-fix receipts.
    line_discount_amount = Column(Numeric(12, 2), nullable=True)

    unit_cost = Column(Numeric(12, 2), default=0)
    line_cost = Column(Numeric(12, 2), default=0)
    # NULL means the historical row predates explicit cost-availability
    # persistence. False means the cost was known to be unavailable.
    cost_snapshot_available = Column(Boolean, nullable=True)
    tax_rate_snapshot = Column(Numeric(7,4), nullable=True)
    tax_amount = Column(Numeric(12,2), nullable=True)
    tax_exempt_snapshot = Column(Boolean, nullable=True)
    price_level_name_snapshot = Column(String(80), nullable=True)
