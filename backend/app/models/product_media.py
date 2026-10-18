import uuid
from sqlalchemy import Column,DateTime,ForeignKey,Integer,String,func
from sqlalchemy.dialects.postgresql import UUID
from app.db.base import Base
class ProductMedia(Base):
    __tablename__="product_media"
    id=Column(UUID(as_uuid=True),primary_key=True,default=uuid.uuid4); company_id=Column(UUID(as_uuid=True),ForeignKey("companies.id",ondelete="CASCADE"),nullable=False,index=True); product_id=Column(UUID(as_uuid=True),ForeignKey("products.id",ondelete="CASCADE"),nullable=False,index=True)
    storage_name=Column(String(120),nullable=False,unique=True); original_name=Column(String(255),nullable=False); content_type=Column(String(40),nullable=False); size_bytes=Column(Integer,nullable=False); sha256=Column(String(64),nullable=False); created_at=Column(DateTime(timezone=True),nullable=False,server_default=func.now())
