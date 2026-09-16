import uuid
from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class DeviceTombstone(Base):
    """Permanent security/audit evidence for a physically deleted terminal."""

    __tablename__ = "device_tombstones"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    terminal_name: Mapped[str] = mapped_column(String(120), nullable=False)
    pos_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    previous_shop_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    previous_branch_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    device_key_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    fingerprint_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, unique=True)
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    actor_employee_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    action: Mapped[str] = mapped_column(String(80), nullable=False, default="terminal_delete")
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    assignment_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    historical_sales_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    deleted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
