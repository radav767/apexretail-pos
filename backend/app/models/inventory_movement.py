from sqlalchemy import ForeignKey
import uuid

from sqlalchemy import Column, DateTime, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import UUID

from app.db.base import Base


class InventoryMovement(Base):
    __tablename__ = "inventory_movements"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    company_id = Column(
        UUID(as_uuid=True),
        nullable=False,
        index=True,
    )


    shop_id = Column(
        UUID(as_uuid=True),
        ForeignKey("shops.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    branch_id = Column(
        UUID(as_uuid=True),
        ForeignKey("branches.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    product_id = Column(
        UUID(as_uuid=True),
        nullable=False,
        index=True,
    )
    variant_id = Column(UUID(as_uuid=True), ForeignKey("product_variants.id", ondelete="SET NULL"), nullable=True, index=True)

    product_name = Column(
        String(160),
        nullable=False,
    )

    movement_type = Column(
        String(40),
        nullable=False,
        index=True,
    )

    quantity = Column(
        Numeric(12, 3),
        nullable=False,
        default=0,
    )

    before_qty = Column(
        Numeric(12, 3),
        nullable=False,
        default=0,
    )

    after_qty = Column(
        Numeric(12, 3),
        nullable=False,
        default=0,
    )

    unit_cost = Column(
        Numeric(12, 2),
        nullable=False,
        default=0,
    )

    reference = Column(
        String(80),
        nullable=True,
    )

    supplier = Column(
        String(160),
        nullable=True,
    )

    reason = Column(
        String(160),
        nullable=True,
    )

    notes = Column(
        Text,
        nullable=True,
    )

    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
