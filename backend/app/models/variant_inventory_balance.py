import uuid
from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Numeric, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from app.db.base import Base
class VariantInventoryBalance(Base):
    __tablename__="variant_inventory_balances"
    __table_args__=(UniqueConstraint("company_id","branch_id","variant_id",name="uq_variant_balance_branch_variant"),)
    id=Column(UUID(as_uuid=True),primary_key=True,default=uuid.uuid4)
    company_id=Column(UUID(as_uuid=True),ForeignKey("companies.id",ondelete="CASCADE"),nullable=False,index=True)
    shop_id=Column(UUID(as_uuid=True),ForeignKey("shops.id",ondelete="CASCADE"),nullable=False,index=True)
    branch_id=Column(UUID(as_uuid=True),ForeignKey("branches.id",ondelete="CASCADE"),nullable=False,index=True)
    product_id=Column(UUID(as_uuid=True),ForeignKey("products.id",ondelete="CASCADE"),nullable=False,index=True)
    variant_id=Column(UUID(as_uuid=True),ForeignKey("product_variants.id",ondelete="CASCADE"),nullable=False,index=True)
    quantity=Column(Numeric(12,3),nullable=False,default=0); reorder_level=Column(Numeric(12,3),nullable=False,default=0)
    active=Column(Boolean,nullable=False,default=True); deleted=Column(Boolean,nullable=False,default=False)
    created_at=Column(DateTime(timezone=True),nullable=False,server_default=func.now()); updated_at=Column(DateTime(timezone=True),nullable=False,server_default=func.now(),onupdate=func.now())
