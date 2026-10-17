import uuid

from sqlalchemy import Boolean, Column, ForeignKey, Numeric, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID

from app.db.base import Base


class ProductComponent(Base):
    __tablename__ = "product_components"
    __table_args__ = (
        UniqueConstraint(
            "composite_product_id",
            "component_product_id",
            name="uq_product_components_recipe_pair",
        ),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    composite_product_id = Column(
        UUID(as_uuid=True),
        ForeignKey("products.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    component_product_id = Column(
        UUID(as_uuid=True),
        ForeignKey("products.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    quantity = Column(Numeric(12, 3), nullable=False)
    unit = Column(String(20), nullable=False, default="each")
    active = Column(Boolean, nullable=False, default=True)
    deleted = Column(Boolean, nullable=False, default=False)

