import uuid
from sqlalchemy import Column, String, Boolean, Numeric, Integer, ForeignKey
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
    unit = Column(String(20), default="each")
    cost_price = Column(Numeric(12, 2), default=0)
    selling_price = Column(Numeric(12, 2), default=0)
    stock_qty = Column(Numeric(12, 3), default=0)
    reorder_level = Column(Numeric(12, 3), default=0)
    active = Column(Boolean, default=True)
    deleted = Column(Boolean, default=False)
