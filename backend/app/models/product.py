import uuid
from sqlalchemy import Column, String, Boolean, Numeric, Integer, ForeignKey, DateTime
from sqlalchemy.dialects.postgresql import UUID
from app.db.base import Base

class Product(Base):
    __tablename__ = "products"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(UUID(as_uuid=True), nullable=False)
    category_id = Column(UUID(as_uuid=True), nullable=True)
    name = Column(String(160), nullable=False)
    sku = Column(String(80), nullable=True)
    barcode = Column(String(80), nullable=True)
    product_type = Column(String(24), nullable=False, default="standard")
    image_url = Column(String(500), nullable=True)
    unit = Column(String(20), default="each")
    purchase_unit = Column(String(20), nullable=True)
    units_per_purchase = Column(Numeric(12, 3), nullable=False, default=1)
    track_inventory = Column(Boolean, nullable=False, default=True)
    tax_rate = Column(Numeric(7, 4), nullable=True)
    tax_exempt = Column(Boolean, nullable=False, default=False)
    cost_price = Column(Numeric(12, 2), nullable=True)
    selling_price = Column(Numeric(12, 2), nullable=True)
    stock_qty = Column(Numeric(12, 3), default=0)
    reorder_level = Column(Numeric(12, 3), default=0)
    create_request_key = Column(String(120), nullable=True)
    active = Column(Boolean, default=True)
    deleted = Column(Boolean, default=False)
    archived_at = Column(DateTime(timezone=True), nullable=True)
