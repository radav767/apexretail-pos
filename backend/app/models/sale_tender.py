"""Immutable original split allocations; no provider success is represented."""
from sqlalchemy import Column,String,Numeric,Integer,ForeignKey,DateTime,func
from sqlalchemy.dialects.postgresql import UUID
from app.db.base import Base
class SaleTender(Base):
    __tablename__='sale_tenders'
    id=Column(UUID(as_uuid=True),primary_key=True)
    company_id=Column(UUID(as_uuid=True),ForeignKey('companies.id'),nullable=False)
    sale_id=Column(UUID(as_uuid=True),ForeignKey('sales.id'),nullable=False,index=True)
    method=Column(String(16),nullable=False)
    currency_code=Column(String(8),nullable=False)
    currency_places=Column(Integer,nullable=False)
    applied_original=Column(Numeric(18,4),nullable=False)
    tendered_original=Column(Numeric(18,4),nullable=False)
    change_original=Column(Numeric(18,4),nullable=False)
    applied_base=Column(Numeric(12,2),nullable=False)
    exchange_rate_id=Column(UUID(as_uuid=True),ForeignKey('currency_exchange_rates.id'))
    exchange_rate_snapshot=Column(Numeric(20,10),nullable=False)
    currency_config_version=Column(Integer,nullable=False)
    created_at=Column(DateTime(timezone=True),nullable=False,server_default=func.now())
