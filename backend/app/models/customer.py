import uuid
from decimal import Decimal

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, BaseModel


class Customer(Base, BaseModel):
    __tablename__ = "customers"
    __table_args__ = (
        UniqueConstraint("company_id", "customer_code", name="uq_customers_company_code"),
        CheckConstraint("credit_limit IS NULL OR credit_limit >= 0", name="ck_customers_credit_limit_nonnegative"),
        CheckConstraint("credit_terms_days >= 0", name="ck_customers_credit_terms_nonnegative"),
        CheckConstraint("NOT unlimited_credit OR credit_enabled", name="ck_customers_unlimited_requires_enabled"),
        CheckConstraint("NOT unlimited_credit OR credit_limit IS NULL", name="ck_customers_unlimited_has_no_limit"),
        CheckConstraint("NOT credit_enabled OR unlimited_credit OR credit_limit IS NOT NULL", name="ck_customers_enabled_has_policy"),
    )

    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False)
    customer_code: Mapped[str] = mapped_column(String(40), nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    phone: Mapped[str | None] = mapped_column(String(60), nullable=True)
    email: Mapped[str | None] = mapped_column(String(160), nullable=True)
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    credit_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    unlimited_credit: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    credit_limit: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    credit_terms_days: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
