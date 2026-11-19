from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID
from app.db.base import Base


class RefundCommandReceipt(Base):
    __tablename__ = 'refund_command_receipts'
    request_id = Column(UUID(as_uuid=True), primary_key=True)
    company_id = Column(UUID(as_uuid=True), ForeignKey('companies.id'), nullable=False, index=True)
    sale_id = Column(UUID(as_uuid=True), ForeignKey('sales.id'), nullable=False, unique=True)
    actor_type = Column(String(10), nullable=False)
    actor_id = Column(UUID(as_uuid=True), nullable=False)
    payload_hash = Column(String(64), nullable=False)
    branch_id = Column(UUID(as_uuid=True), ForeignKey('branches.id'), nullable=False)
    device_id = Column(UUID(as_uuid=True), ForeignKey('devices.id'))
    assignment_revision = Column(Integer)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
