"""Immutable exact request proofs, separate from frozen shift snapshots."""
from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID
from app.db.base import Base


class ShiftCommandReceipt(Base):
    __tablename__ = 'shift_command_receipts'
    company_id = Column(UUID(as_uuid=True), ForeignKey('companies.id'), primary_key=True)
    kind = Column(String(24), primary_key=True)
    command_key = Column(String(100), primary_key=True)
    shift_id = Column(UUID(as_uuid=True), ForeignKey('cashier_shifts.id', ondelete='RESTRICT'), nullable=False)
    movement_id = Column(UUID(as_uuid=True), ForeignKey('cashier_shift_cash_movements.id', ondelete='RESTRICT'))
    resolution_id = Column(UUID(as_uuid=True), ForeignKey('offline_sale_resolutions.id', ondelete='RESTRICT'))
    payload_hash = Column(String(64), nullable=False)
    actor_type = Column(String(10), nullable=False)
    actor_id = Column(UUID(as_uuid=True), nullable=False)
    device_id = Column(UUID(as_uuid=True))
    assignment_revision = Column(Integer)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
