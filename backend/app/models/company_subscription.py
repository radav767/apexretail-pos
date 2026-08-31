import uuid

from sqlalchemy import Column, DateTime, ForeignKey, Integer, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import UUID

from app.db.base import Base


class CompanySubscription(Base):
    __tablename__ = "company_subscriptions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    plan = Column(String(20), nullable=True)
    status = Column(String(40), nullable=False, index=True)
    trial_started_at = Column(DateTime(timezone=True), nullable=True)
    trial_ends_at = Column(DateTime(timezone=True), nullable=True)
    current_period_started_at = Column(
        DateTime(timezone=True),
        nullable=True,
    )
    current_period_ends_at = Column(
        DateTime(timezone=True),
        nullable=True,
    )
    grace_ends_at = Column(DateTime(timezone=True), nullable=True)
    provider = Column(String(80), nullable=True)
    provider_reference = Column(String(160), nullable=True)
    billing_currency = Column(String(8), nullable=True)
    licensed_terminal_count = Column(Integer, nullable=True)
    unit_price = Column(Numeric(12, 2), nullable=True)
    total_amount = Column(Numeric(12, 2), nullable=True)
    status_reason = Column(Text, nullable=True)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
