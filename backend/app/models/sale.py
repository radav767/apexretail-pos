from sqlalchemy import Boolean
from sqlalchemy import ForeignKey
import uuid

from sqlalchemy import Column, String, Numeric, DateTime, func
from sqlalchemy.dialects.postgresql import UUID

from app.db.base import Base


class Sale(Base):
    __tablename__ = "sales"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(UUID(as_uuid=True), nullable=False)


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


    employee_id = Column(
        UUID(as_uuid=True),
        ForeignKey("employees.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    cashier_name = Column(
        String(160),
        nullable=True,
    )

    receipt_number = Column(String(40), unique=True, nullable=False)

    subtotal_amount = Column(

        Numeric(12, 2),

        nullable=False,

        default=0,

    )

    tax_name = Column(String(40), nullable=True)

    tax_rate = Column(

        Numeric(7, 3),

        nullable=False,

        default=0,

    )

    tax_amount = Column(

        Numeric(12, 2),

        nullable=False,

        default=0,

    )

    tax_inclusive = Column(

        Boolean,

        nullable=False,

        default=False,

    )


    total_amount = Column(Numeric(12, 2), nullable=False, default=0)
    amount_received = Column(Numeric(12, 2), nullable=False, default=0)
    change_due = Column(Numeric(12, 2), nullable=False, default=0)

    payment_method = Column(String(40), nullable=False, default="cash")
    status = Column(String(40), nullable=False, default="completed")

    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
