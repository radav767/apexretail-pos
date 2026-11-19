import uuid
from sqlalchemy import Column, ForeignKey, Numeric, DateTime, CheckConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from app.db.base import Base


class CreditRefundAdjustment(Base):
    __tablename__ = 'credit_refund_adjustments'
    __table_args__ = (CheckConstraint('amount > 0', name='ck_credit_refund_amount_positive'),)
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(UUID(as_uuid=True), ForeignKey('companies.id'), nullable=False)
    receivable_id = Column(UUID(as_uuid=True), ForeignKey('credit_receivables.id'), nullable=False)
    refund_sale_id = Column(UUID(as_uuid=True), ForeignKey('sales.id'), nullable=False, unique=True)
    amount = Column(Numeric(12,2), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
