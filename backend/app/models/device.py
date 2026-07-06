import uuid
from sqlalchemy import String, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base, BaseModel

class Device(Base, BaseModel):
    __tablename__ = "devices"

    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False)
    shop_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("shops.id"), nullable=False)
    branch_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("branches.id"), nullable=False)

    name: Mapped[str] = mapped_column(String, nullable=False)
    device_key: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    platform: Mapped[str] = mapped_column(String, default="Android")
    app_version: Mapped[str] = mapped_column(String, default="1.0.0")
