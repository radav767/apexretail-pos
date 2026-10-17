import uuid

from sqlalchemy import Column, ForeignKey, Numeric, String
from sqlalchemy.dialects.postgresql import UUID

from app.db.base import Base


class SaleItemComponent(Base):
    """Immutable inventory recipe snapshot for a sold composite line."""

    __tablename__ = "sale_item_components"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    sale_item_id = Column(
        UUID(as_uuid=True),
        ForeignKey("sale_items.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    component_product_id = Column(
        UUID(as_uuid=True),
        ForeignKey("products.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    component_name = Column(String(160), nullable=False)
    quantity = Column(Numeric(12, 3), nullable=False)
    unit = Column(String(20), nullable=False)
    unit_cost = Column(Numeric(12, 2), nullable=False, default=0)

