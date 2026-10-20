import uuid
from sqlalchemy import Column, String, Numeric, DateTime, ForeignKey, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from app.db.base import Base


class BatchReturnHold(Base):
    __tablename__ = "batch_return_holds"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False)
    branch_id = Column(UUID(as_uuid=True), ForeignKey("branches.id"), nullable=False)
    product_id = Column(UUID(as_uuid=True), ForeignKey("products.id"), nullable=False)
    movement_id = Column(UUID(as_uuid=True), ForeignKey("inventory_movements.id"), nullable=False, unique=True)
    quantity = Column(Numeric(12,3), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())


class BatchReturnInspection(Base):
    __tablename__ = "batch_return_inspections"
    __table_args__ = (UniqueConstraint("company_id", "request_id", name="uq_batch_return_request"),)
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False)
    hold_id = Column(UUID(as_uuid=True), ForeignKey("batch_return_holds.id"), nullable=False, unique=True)
    batch_id = Column(UUID(as_uuid=True), ForeignKey("product_batches.id"), nullable=False)
    request_id = Column(UUID(as_uuid=True), nullable=False)
    payload_hash = Column(String(64), nullable=False)
    disposition = Column(String(16), nullable=False)
    reason = Column(String(500), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())


class BatchInspectionDisposal(Base):
    __tablename__ = "batch_inspection_disposals"
    inspection_id = Column(UUID(as_uuid=True), ForeignKey("batch_return_inspections.id"), primary_key=True)
    movement_id = Column(UUID(as_uuid=True), ForeignKey("inventory_movements.id"), nullable=False, unique=True)
