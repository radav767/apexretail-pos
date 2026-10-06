import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, String, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class CompanyCurrency(Base):
    __tablename__ = "company_currencies"
    __table_args__ = (
        CheckConstraint("decimal_places >= 0 AND decimal_places <= 4", name="ck_company_currencies_decimal_places"),
        CheckConstraint("code = upper(btrim(code)) AND btrim(code) <> ''", name="ck_company_currencies_normalized_code"),
        CheckConstraint("NOT is_base OR active", name="ck_company_currencies_base_active"),
        Index("uq_company_currencies_company_code", "company_id", "code", unique=True),
        Index(
            "uq_company_currencies_one_base",
            "company_id",
            unique=True,
            postgresql_where=text("is_base IS TRUE"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)
    code: Mapped[str] = mapped_column(String(8), nullable=False)
    display_name: Mapped[str] = mapped_column(String(80), nullable=False)
    symbol: Mapped[str] = mapped_column(String(10), nullable=False)
    decimal_places: Mapped[int] = mapped_column(Integer, nullable=False, default=2)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_base: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    cash_accepted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    card_accepted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    mobile_accepted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
