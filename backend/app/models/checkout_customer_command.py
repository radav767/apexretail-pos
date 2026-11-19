from sqlalchemy import Column,String,ForeignKey,DateTime,func
from sqlalchemy.dialects.postgresql import UUID
from app.db.base import Base


class CheckoutCustomerCommand(Base):
    __tablename__='checkout_customer_commands'
    request_id=Column(UUID(as_uuid=True),primary_key=True)
    company_id=Column(UUID(as_uuid=True),ForeignKey('companies.id'),nullable=False)
    customer_id=Column(UUID(as_uuid=True),ForeignKey('customers.id'),nullable=False,unique=True)
    actor_type=Column(String(10),nullable=False)
    actor_id=Column(UUID(as_uuid=True),nullable=False)
    payload_hash=Column(String(64),nullable=False)
    created_at=Column(DateTime(timezone=True),server_default=func.now(),nullable=False)
