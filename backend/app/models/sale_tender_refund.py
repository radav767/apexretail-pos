"""Immutable original-leg allocations for synthetic split refund accounting."""
from sqlalchemy import Column,String,Numeric,ForeignKey,DateTime,func,UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from app.db.base import Base
class SaleTenderRefund(Base):
    __tablename__='sale_tender_refunds'
    __table_args__=(UniqueConstraint('refund_sale_id','tender_id',name='uq_refund_original_tender'),)
    id=Column(UUID(as_uuid=True),primary_key=True)
    company_id=Column(UUID(as_uuid=True),ForeignKey('companies.id'),nullable=False)
    refund_sale_id=Column(UUID(as_uuid=True),ForeignKey('sales.id'),nullable=False)
    tender_id=Column(UUID(as_uuid=True),ForeignKey('sale_tenders.id'),nullable=False)
    kind=Column(String(24),nullable=False)
    amount_base=Column(Numeric(12,2),nullable=False)
    amount_original=Column(Numeric(18,4),nullable=False)
    created_at=Column(DateTime(timezone=True),nullable=False,server_default=func.now())
