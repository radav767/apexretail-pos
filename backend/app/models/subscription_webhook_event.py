import uuid

from sqlalchemy import Boolean, Column, DateTime, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.db.base import Base


class SubscriptionWebhookEvent(Base):
    __tablename__ = "subscription_webhook_events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    provider = Column(String(80), nullable=False, index=True)
    provider_event_id = Column(String(160), nullable=False, unique=True)
    event_type = Column(String(120), nullable=False)
    company_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    payload = Column(JSONB, nullable=True)
    processed = Column(Boolean, nullable=False, default=False)
    processed_at = Column(DateTime(timezone=True), nullable=True)
    processing_error = Column(Text, nullable=True)
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
