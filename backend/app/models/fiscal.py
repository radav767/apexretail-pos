"""Preparatory fiscal records; these are NOT accepted FDMS receipts."""
import uuid
from sqlalchemy import Column, DateTime, ForeignKey, Integer, JSON, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from app.db.base import Base


class FiscalConfiguration(Base):
    __tablename__ = 'fiscal_configurations'
    company_id = Column(UUID(as_uuid=True), ForeignKey('companies.id'), primary_key=True)
    version = Column(Integer, nullable=False)
    settings = Column(JSON, nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())


class FiscalPreparation(Base):
    __tablename__ = 'fiscal_preparations'
    __table_args__ = (UniqueConstraint('company_id', 'sale_id', name='uq_fiscal_preparation_sale'),)
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(UUID(as_uuid=True), ForeignKey('companies.id'), nullable=False, index=True)
    sale_id = Column(UUID(as_uuid=True), ForeignKey('sales.id'), nullable=False)
    snapshot = Column(JSON, nullable=False)
    snapshot_hash = Column(String(64), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())


class FiscalAudit(Base):
    __tablename__ = 'fiscal_audit'
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(UUID(as_uuid=True), ForeignKey('companies.id'), nullable=False, index=True)
    actor_user_id = Column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=False)
    action = Column(String(80), nullable=False)
    details = Column(JSON, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
