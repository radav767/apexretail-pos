import uuid

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, BaseModel


class ProductCreationRequest(Base, BaseModel):
    __tablename__ = "product_creation_requests"

    __table_args__ = (
        UniqueConstraint(
            "company_id",
            "idempotency_key",
            name="uq_product_creation_requests_company_key",
        ),
    )

    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
    )

    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("products.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )

    idempotency_key: Mapped[str] = mapped_column(
        String(120),
        nullable=False,
    )
