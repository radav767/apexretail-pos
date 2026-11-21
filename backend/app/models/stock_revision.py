from sqlalchemy import Column,BigInteger
from sqlalchemy.dialects.postgresql import UUID
from app.db.base import Base
class StockRevision(Base):
    __tablename__='stock_revisions'
    company_id=Column(UUID(as_uuid=True),primary_key=True)
    branch_id=Column(UUID(as_uuid=True),primary_key=True)
    product_id=Column(UUID(as_uuid=True),primary_key=True)
    revision=Column(BigInteger,nullable=False,server_default='0')
