"""Platform billing is separate from tenants' sales and cash ledgers."""
import uuid
from sqlalchemy import Column, String, Integer, Boolean, DateTime, Numeric, ForeignKey, UniqueConstraint, JSON, func
from sqlalchemy.dialects.postgresql import UUID
from app.db.base import Base

def uid(**kwargs):return Column(UUID(as_uuid=True),default=uuid.uuid4,**kwargs)

class PlatformAdmin(Base):
    __tablename__='platform_admins'
    id=uid(primary_key=True)
    email=Column(String(160),nullable=False,unique=True)
    password_hash=Column(String(160),nullable=False)
    role=Column(String(20),nullable=False)
    active=Column(Boolean,nullable=False,default=True)
    failed_attempts=Column(Integer,nullable=False,default=0)
    locked_until=Column(DateTime(timezone=True))

class PlatformSession(Base):
    __tablename__='platform_sessions'
    id=uid(primary_key=True)
    admin_id=Column(UUID(as_uuid=True),ForeignKey('platform_admins.id'),nullable=False)
    token_hash=Column(String(64),nullable=False,unique=True)
    expires_at=Column(DateTime(timezone=True),nullable=False)
    revoked_at=Column(DateTime(timezone=True))

class PlatformAudit(Base):
    __tablename__='platform_audit'
    id=uid(primary_key=True)
    admin_id=Column(UUID(as_uuid=True),ForeignKey('platform_admins.id'))
    company_id=Column(UUID(as_uuid=True),ForeignKey('companies.id'))
    action=Column(String(80),nullable=False)
    details=Column(JSON,nullable=False)
    created_at=Column(DateTime(timezone=True),nullable=False,server_default=func.now())

class BillingPlan(Base):
    __tablename__='billing_plans'
    id=uid(primary_key=True)
    name=Column(String(80),nullable=False)
    version=Column(Integer,nullable=False,default=1)
    active=Column(Boolean,nullable=False,default=True)
    terms=Column(JSON,nullable=False)

class BillingInvoice(Base):
    __tablename__='billing_invoices'
    __table_args__=(UniqueConstraint('company_id','request_id',name='uq_billing_invoice_request'),)
    id=uid(primary_key=True)
    company_id=Column(UUID(as_uuid=True),ForeignKey('companies.id'),nullable=False,index=True)
    request_id=Column(UUID(as_uuid=True),nullable=False)
    payload_hash=Column(String(64),nullable=False)
    plan_id=Column(UUID(as_uuid=True),ForeignKey('billing_plans.id'),nullable=False)
    snapshot=Column(JSON,nullable=False)
    amount=Column(Numeric(18,4),nullable=False)
    currency=Column(String(8),nullable=False)
    decimal_places=Column(Integer,nullable=False)
    due_at=Column(DateTime(timezone=True),nullable=False)
    fulfilled_at=Column(DateTime(timezone=True))
    created_at=Column(DateTime(timezone=True),nullable=False,server_default=func.now())

class BillingPayment(Base):
    __tablename__='billing_payments'
    __table_args__=(UniqueConstraint('company_id','request_id',name='uq_billing_payment_request'),
        UniqueConstraint('company_id','reference',name='uq_billing_payment_reference'))
    id=uid(primary_key=True)
    company_id=Column(UUID(as_uuid=True),ForeignKey('companies.id'),nullable=False,index=True)
    invoice_id=Column(UUID(as_uuid=True),ForeignKey('billing_invoices.id'),nullable=False,index=True)
    request_id=Column(UUID(as_uuid=True),nullable=False)
    admin_id=Column(UUID(as_uuid=True),ForeignKey('platform_admins.id'),nullable=False)
    amount=Column(Numeric(18,4),nullable=False)
    method=Column(String(20),nullable=False)
    reference=Column(String(160),nullable=False)
    created_at=Column(DateTime(timezone=True),nullable=False,server_default=func.now())

class BillingNotice(Base):
    __tablename__='billing_notices'
    id=uid(primary_key=True)
    company_id=Column(UUID(as_uuid=True),ForeignKey('companies.id'),nullable=False,index=True)
    event_key=Column(String(200),nullable=False,unique=True)
    kind=Column(String(40),nullable=False)
    message=Column(String(500),nullable=False)
    created_at=Column(DateTime(timezone=True),nullable=False,server_default=func.now())
