import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base, BaseModel


class Device(Base, BaseModel):
    __tablename__ = "devices"
    __table_args__ = (
        Index(
            "uq_devices_branch_pos_number_active",
            "branch_id",
            "pos_number",
            unique=True,
            postgresql_where=text(
                "pos_number IS NOT NULL AND removed_at IS NULL"
            ),
        ),
    )

    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False)
    shop_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("shops.id"), nullable=False)
    branch_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("branches.id"), nullable=False)

    name: Mapped[str] = mapped_column(String, nullable=False)
    friendly_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    pos_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    device_key: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    platform: Mapped[str] = mapped_column(String, default="Android")
    app_version: Mapped[str] = mapped_column(String, default="1.0.0")
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_seen_platform: Mapped[str | None] = mapped_column(String(50), nullable=True)
    last_seen_app_version: Mapped[str | None] = mapped_column(String(50), nullable=True)
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="active",
        server_default="active",
    )
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deactivated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deactivation_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    removed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    activation_code_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    activation_code_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    device_fingerprint: Mapped[str | None] = mapped_column(String(255), nullable=True)
    pending_shop_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("shops.id"),
        nullable=True,
    )
    pending_branch_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("branches.id"),
        nullable=True,
    )
