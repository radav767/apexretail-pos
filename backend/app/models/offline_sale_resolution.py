import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, JSON, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class OfflineSaleResolution(Base):
    """Append-only evidence for a manager-reviewed quarantined POS sale."""

    __tablename__ = "offline_sale_resolutions"
    __table_args__ = (
        UniqueConstraint("company_id", "client_sale_id", name="uq_offline_resolution_client_sale"),
        UniqueConstraint("company_id", "idempotency_key", name="uq_offline_resolution_key"),
        Index("ix_offline_resolutions_company_created", "company_id", "created_at"),
        Index("ix_offline_resolutions_shift", "original_shift_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False)
    client_sale_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    original_shift_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("cashier_shifts.id", ondelete="RESTRICT"), nullable=False)
    original_employee_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("employees.id", ondelete="RESTRICT"), nullable=False)
    original_device_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("devices.id", ondelete="RESTRICT"), nullable=False)
    sale_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("sales.id", ondelete="RESTRICT"), nullable=True)
    action: Mapped[str] = mapped_column(String(40), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    payload_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    payload_snapshot: Mapped[dict] = mapped_column(JSON, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(100), nullable=False)
    resolved_by_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=True)
    resolved_by_employee_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("employees.id", ondelete="RESTRICT"), nullable=True)
    resolver_name_snapshot: Mapped[str] = mapped_column(String(160), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
