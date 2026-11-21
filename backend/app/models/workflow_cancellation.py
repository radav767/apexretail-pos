from sqlalchemy import Column,String,ForeignKey,DateTime,func
from sqlalchemy.dialects.postgresql import UUID
from app.db.base import Base
class WorkflowCancellation(Base):
    __tablename__='workflow_cancellations'
    request_id=Column(UUID(as_uuid=True),primary_key=True)
    company_id=Column(UUID(as_uuid=True),ForeignKey('companies.id'),primary_key=True)
    actor_type=Column(String(10),primary_key=True)
    actor_id=Column(UUID(as_uuid=True),primary_key=True)
    reason=Column(String(500),nullable=False)
    created_at=Column(DateTime(timezone=True),server_default=func.now(),nullable=False)
