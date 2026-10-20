"""Separate, append-only tip accounting. Never product revenue or stock."""
import uuid
from sqlalchemy import Column, String, Numeric, Boolean, DateTime, ForeignKey, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID, JSONB
from app.db.base import Base


class TipSettings(Base):
    __tablename__ = "tip_settings"
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id"), primary_key=True)
    enabled = Column(Boolean, nullable=False, default=False)
    policy = Column(String(16), nullable=False, default="staff")
    weights = Column(JSONB, nullable=False, default=dict)
    business_retention_confirmed = Column(Boolean, nullable=False, default=False)
    service_product_id = Column(UUID(as_uuid=True), ForeignKey("products.id"))


class TipEntry(Base):
    __tablename__ = "tip_entries"
    __table_args__ = (UniqueConstraint("company_id", "request_id", name="uq_tip_entry_request"),)
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False)
    branch_id = Column(UUID(as_uuid=True), ForeignKey("branches.id"), nullable=False)
    shift_id = Column(UUID(as_uuid=True), ForeignKey("cashier_shifts.id"), nullable=False)
    sale_id = Column(UUID(as_uuid=True), ForeignKey("sales.id"))
    original_id = Column(UUID(as_uuid=True), ForeignKey("tip_entries.id"))
    request_id = Column(UUID(as_uuid=True), nullable=False)
    payload_hash = Column(String(64), nullable=False)
    kind = Column(String(16), nullable=False)
    policy = Column(String(16), nullable=False)
    payment_method = Column(String(16), nullable=False)
    currency_code = Column(String(8), nullable=False)
    decimal_places = Column(Numeric(1, 0), nullable=False)
    amount = Column(Numeric(18, 4), nullable=False)
    reason = Column(String(500), nullable=False)
    reference = Column(String(120), nullable=False, default="")
    cash_movement_id = Column(UUID(as_uuid=True), ForeignKey("cashier_shift_cash_movements.id"), unique=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())


class TipEntitlement(Base):
    __tablename__ = "tip_entitlements"
    __table_args__ = (UniqueConstraint("entry_id", "employee_id", name="uq_tip_entry_employee"),)
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    entry_id = Column(UUID(as_uuid=True), ForeignKey("tip_entries.id"), nullable=False)
    employee_id = Column(UUID(as_uuid=True), ForeignKey("employees.id"), nullable=False)
    amount = Column(Numeric(18, 4), nullable=False)
