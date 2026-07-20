import uuid
from sqlalchemy import Column, String, Numeric, DateTime, ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID
from app.db.base import Base

class Sale(Base):
    __tablename__ = "sales"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(UUID(as_uuid=True), nullable=False)
    total_amount = Column(Numeric(12, 2), default=0)
    payment_method = Column(String(40), default="cash")
    status = Column(String(40), default="completed")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
