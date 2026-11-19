from sqlalchemy import Column,String,Integer,ForeignKey,DateTime,func
from sqlalchemy.dialects.postgresql import UUID
from app.db.base import Base


class QuotationCommand(Base):
    __tablename__='quotation_commands'
    request_id=Column(UUID(as_uuid=True),primary_key=True)
    company_id=Column(UUID(as_uuid=True),ForeignKey('companies.id'),nullable=False)
    order_id=Column(UUID(as_uuid=True),ForeignKey('commerce_orders.id'),nullable=False)
    actor_type=Column(String(10),nullable=False)
    actor_id=Column(UUID(as_uuid=True),nullable=False)
    payload_hash=Column(String(64),nullable=False)
    device_id=Column(UUID(as_uuid=True),ForeignKey('devices.id'),nullable=False)
    assignment_revision=Column(Integer,nullable=False)
    action=Column(String(20),nullable=False)
    created_at=Column(DateTime(timezone=True),server_default=func.now(),nullable=False)
