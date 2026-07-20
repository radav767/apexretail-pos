import uuid

from sqlalchemy import Column, String, Numeric, DateTime, func
from sqlalchemy.dialects.postgresql import UUID

from app.db.base import Base


class Sale(Base):
    __tablename__ = "sales"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(UUID(as_uuid=True), nullable=False)

    receipt_number = Column(String(40), unique=True, nullable=False)

    total_amount = Column(Numeric(12, 2), nullable=False, default=0)
    amount_received = Column(Numeric(12, 2), nullable=False, default=0)
    change_due = Column(Numeric(12, 2), nullable=False, default=0)

    payment_method = Column(String(40), nullable=False, default="cash")
    status = Column(String(40), nullable=False, default="completed")

    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
