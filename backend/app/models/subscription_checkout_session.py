import uuid

from sqlalchemy import Column, DateTime, ForeignKey, Integer, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.db.base import Base


class SubscriptionCheckoutSession(Base):
    __tablename__ = "subscription_checkout_sessions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    company_subscription_id = Column(
        UUID(as_uuid=True),
        ForeignKey("company_subscriptions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    plan = Column(String(20), nullable=False)
    provider = Column(String(80), nullable=False)
    session_reference = Column(String(160), nullable=False, unique=True)
    status = Column(String(40), nullable=False, default="pending")
    checkout_url = Column(Text, nullable=True)
    billing_period = Column(String(20), nullable=True)
    billing_currency = Column(String(8), nullable=True)
    unit_price = Column(Numeric(12, 2), nullable=True)
    terminal_count = Column(Integer, nullable=True)
    total_amount = Column(Numeric(12, 2), nullable=True)
    included_device_ids = Column(JSONB, nullable=True)
    paynow_reference = Column(String(160), nullable=True)
    poll_url = Column(Text, nullable=True)
    payment_status = Column(String(40), nullable=True)
    payload = Column(JSONB, nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=True)
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
