import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Numeric, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class CurrencyExchangeRate(Base):
    __tablename__ = "currency_exchange_rates"
    __table_args__ = (
        CheckConstraint("foreign_units_per_base > 0", name="ck_currency_rates_positive"),
        UniqueConstraint("company_id", "currency_id", "effective_at", name="uq_currency_rates_effective_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)
    currency_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("company_currencies.id", ondelete="RESTRICT"), nullable=False)
    currency_code: Mapped[str] = mapped_column(String(8), nullable=False)
    foreign_units_per_base: Mapped[Decimal] = mapped_column(Numeric(20, 10), nullable=False)
    effective_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
