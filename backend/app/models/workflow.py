"""Scoped workflow projections and append-only full command acknowledgements."""
import uuid
from sqlalchemy import Column,String,Integer,ForeignKey,DateTime,func
from sqlalchemy.dialects.postgresql import UUID,JSONB
from app.db.base import Base

class WorkflowRecord(Base):
    __tablename__='workflow_records'
    id=Column(UUID(as_uuid=True),primary_key=True,default=uuid.uuid4)
    company_id=Column(UUID(as_uuid=True),ForeignKey('companies.id'),nullable=False,index=True)
    branch_id=Column(UUID(as_uuid=True),ForeignKey('branches.id'),index=True)
    kind=Column(String(24),nullable=False)
    state=Column(String(24),nullable=False)
    version=Column(Integer,nullable=False,default=1)
    payload=Column(JSONB,nullable=False)
    created_at=Column(DateTime(timezone=True),server_default=func.now(),nullable=False)

class WorkflowCommand(Base):
    __tablename__='workflow_commands'
    request_id=Column(UUID(as_uuid=True),primary_key=True)
    company_id=Column(UUID(as_uuid=True),ForeignKey('companies.id'),nullable=False,index=True)
    record_id=Column(UUID(as_uuid=True),ForeignKey('workflow_records.id'),nullable=False,index=True)
    kind=Column(String(40),nullable=False)
    actor_type=Column(String(10),nullable=False)
    actor_id=Column(UUID(as_uuid=True),nullable=False)
    device_id=Column(UUID(as_uuid=True),ForeignKey('devices.id'))
    assignment_revision=Column(Integer)
    payload_hash=Column(String(64),nullable=False)
    result=Column(JSONB,nullable=False)
    created_at=Column(DateTime(timezone=True),server_default=func.now(),nullable=False)
