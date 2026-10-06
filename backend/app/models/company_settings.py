import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, BaseModel


class CompanySetting(Base, BaseModel):
    __tablename__ = "company_settings"

    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )

    base_currency_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company_currencies.id", ondelete="RESTRICT"), nullable=True
    )
    currency_config_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    multi_currency_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=text("false"))
    shift_enforcement_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=text("false"))
    shift_required_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reporting_timezone: Mapped[str] = mapped_column(String(80), nullable=False, default="Africa/Harare", server_default="Africa/Harare")

    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    contact_email: Mapped[str | None] = mapped_column(String(255), nullable=True)

    currency_code: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        default="USD",
        server_default="USD",
    )
    currency_symbol: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        default="$",
        server_default="$",
    )
    decimal_places: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=2,
        server_default="2",
    )

    tax_name: Mapped[str] = mapped_column(
        String(40),
        nullable=False,
        default="VAT",
        server_default="VAT",
    )
    tax_rate: Mapped[float] = mapped_column(
        Numeric(6, 3),
        nullable=False,
        default=0,
        server_default="0",
    )
    tax_inclusive: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("false"),
    )

    receipt_header: Mapped[str | None] = mapped_column(Text, nullable=True)
    receipt_footer: Mapped[str | None] = mapped_column(Text, nullable=True)

    paper_size: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        default="80mm",
        server_default="80mm",
    )
    auto_print: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("false"),
    )

    payment_methods: Mapped[list] = mapped_column(
        JSONB,
        nullable=False,
        default=lambda: ["cash", "card", "mobile", "credit"],
        server_default=text(
            """'["cash", "card", "mobile", "credit"]'::jsonb"""
        ),
    )
