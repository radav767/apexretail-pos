import uuid

from sqlalchemy import Boolean, Column, ForeignKey, Numeric, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID

from app.db.base import Base


class ProductPriceLevel(Base):
    __tablename__ = "product_price_levels"
    __table_args__ = (
        UniqueConstraint("product_id", "name", name="uq_product_price_levels_name"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    product_id = Column(
        UUID(as_uuid=True),
        ForeignKey("products.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name = Column(String(80), nullable=False)
    price = Column(Numeric(12, 2), nullable=False)
    minimum_quantity = Column(Numeric(12, 3), nullable=False, default=1)
    active = Column(Boolean, nullable=False, default=True)
    deleted = Column(Boolean, nullable=False, default=False)

