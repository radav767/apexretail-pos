"""Business identity credentials; never shared with platform authentication."""
import uuid
from sqlalchemy import Column, String, Integer, Boolean, DateTime, ForeignKey, LargeBinary, func
from sqlalchemy.dialects.postgresql import UUID
from app.db.base import Base


class BusinessSession(Base):
    __tablename__ = 'business_sessions'
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=False, index=True)
    company_id = Column(UUID(as_uuid=True), ForeignKey('companies.id'), nullable=False, index=True)
    session_version = Column(Integer, nullable=False)
    remembered = Column(Boolean, nullable=False, default=False)
    audience = Column(String(30), nullable=False, default='backoffice')
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    expires_at = Column(DateTime(timezone=True), nullable=False)
    revoked_at = Column(DateTime(timezone=True))


class BusinessRefreshCredential(Base):
    __tablename__ = 'business_refresh_credentials'
    token_hash = Column(String(64), primary_key=True)
    session_id = Column(UUID(as_uuid=True), ForeignKey('business_sessions.id'), nullable=False, index=True)
    consumed_at = Column(DateTime(timezone=True))
    expires_at = Column(DateTime(timezone=True), nullable=False)
