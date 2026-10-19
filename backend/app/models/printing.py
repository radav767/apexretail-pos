"""Printing is an independent side effect; these tables never own stock/payments."""
import uuid
from sqlalchemy import Column, String, Boolean, Integer, DateTime, ForeignKey, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID, JSONB
from app.db.base import Base


class PrinterStation(Base):
    __tablename__ = "printer_stations"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    shop_id = Column(UUID(as_uuid=True), ForeignKey("shops.id"), nullable=False)
    branch_id = Column(UUID(as_uuid=True), ForeignKey("branches.id"), nullable=False)
    device_id = Column(UUID(as_uuid=True), ForeignKey("devices.id", ondelete="RESTRICT"), nullable=False)
    name = Column(String(80), nullable=False)
    purpose = Column(String(16), nullable=False)
    transport = Column(String(16), nullable=False)
    address = Column(String(180), nullable=False, default="")
    paper_width = Column(String(4), nullable=False, default="80mm")
    auto_print = Column(Boolean, nullable=False, default=False)
    active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())


class PrinterRoute(Base):
    __tablename__ = "printer_routes"
    __table_args__ = (UniqueConstraint("station_id", "target_type", "target_id", name="uq_printer_route"),)
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    station_id = Column(UUID(as_uuid=True), ForeignKey("printer_stations.id"), nullable=False, index=True)
    target_type = Column(String(16), nullable=False)
    target_id = Column(UUID(as_uuid=True), nullable=False)


class PrintJob(Base):
    __tablename__ = "print_jobs"
    __table_args__ = (UniqueConstraint("station_id", "request_key", name="uq_print_job_request"),)
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    station_id = Column(UUID(as_uuid=True), ForeignKey("printer_stations.id"), nullable=False, index=True)
    sale_id = Column(UUID(as_uuid=True), ForeignKey("sales.id"), nullable=True)
    order_id = Column(UUID(as_uuid=True), ForeignKey("commerce_orders.id", ondelete="RESTRICT"), nullable=True)
    requested_employee_id = Column(UUID(as_uuid=True), ForeignKey("employees.id", ondelete="RESTRICT"), nullable=True)
    request_key = Column(String(160), nullable=False)
    kind = Column(String(16), nullable=False)
    payload = Column(JSONB, nullable=False)
    payload_hash = Column(String(64), nullable=False)
    status = Column(String(16), nullable=False, default="pending")
    attempts = Column(Integer, nullable=False, default=0)
    claim_hash = Column(String(64), nullable=True)
    claimed_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    last_error = Column(String(240), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
