"""Durable test-only protocol state, separate from financial records."""
import uuid
from sqlalchemy import Column, Integer, BigInteger, ForeignKey, JSON, String, UniqueConstraint, DateTime, func
from sqlalchemy.dialects.postgresql import UUID
from app.db.base import Base


class FiscalProtocolState(Base):
    __tablename__ = 'fiscal_protocol_states'
    company_id = Column(UUID(as_uuid=True), ForeignKey('companies.id'), primary_key=True)
    data = Column(JSON, nullable=False)


class FiscalDocument(Base):
    __tablename__ = 'fiscal_documents'
    __table_args__ = (UniqueConstraint('company_id', 'preparation_id', name='uq_fiscal_document_preparation'),
                      UniqueConstraint('company_id', 'global_no', name='uq_fiscal_document_global'))
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(UUID(as_uuid=True), ForeignKey('companies.id'), nullable=False, index=True)
    preparation_id = Column(UUID(as_uuid=True), ForeignKey('fiscal_preparations.id'), nullable=False)
    day_no = Column(Integer, nullable=False)
    global_no = Column(Integer, nullable=False)
    payload = Column(JSON, nullable=False)
    payload_hash = Column(String(64), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())


class FiscalProtocolEvent(Base):
    __tablename__ = 'fiscal_protocol_events'
    __table_args__ = (UniqueConstraint('company_id', 'sequence', name='uq_fiscal_event_sequence'),)
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(UUID(as_uuid=True), ForeignKey('companies.id'), nullable=False, index=True)
    document_id = Column(UUID(as_uuid=True), ForeignKey('fiscal_documents.id'))
    sequence = Column(BigInteger, nullable=False)
    kind = Column(String(50), nullable=False)
    details = Column(JSON, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
