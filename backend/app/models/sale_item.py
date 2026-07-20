import uuid
from sqlalchemy import Column, String, Numeric, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from app.db.base import Base

class SaleItem(Base):
    __tablename__ = "sale_items"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    sale_id = Column(UUID(as_uuid=True), ForeignKey("sales.id"), nullable=False)
    product_id = Column(UUID(as_uuid=True), nullable=False)
    product_name = Column(String(160), nullable=False)
    quantity = Column(Numeric(12, 3), default=1)
    unit_price = Column(Numeric(12, 2), default=0)
    line_total = Column(Numeric(12, 2), default=0)
