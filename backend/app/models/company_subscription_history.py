import uuid

from sqlalchemy import Column, DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.db.base import Base


class CompanySubscriptionHistory(Base):
    __tablename__ = "company_subscription_history"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_subscription_id = Column(
        UUID(as_uuid=True),
        ForeignKey("company_subscriptions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    action = Column(String(80), nullable=False)
    plan = Column(String(20), nullable=True)
    status = Column(String(40), nullable=False)
    provider = Column(String(80), nullable=True)
    provider_reference = Column(String(160), nullable=True)
    payload = Column(JSONB, nullable=True)
    note = Column(Text, nullable=True)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
