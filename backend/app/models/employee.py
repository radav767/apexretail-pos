import uuid

from sqlalchemy import ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, BaseModel


class Employee(Base, BaseModel):
    __tablename__ = "employees"

    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("companies.id"),
        nullable=False,
    )

    shop_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("shops.id"),
        nullable=False,
    )

    branch_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("branches.id"),
        nullable=False,
    )

    name: Mapped[str] = mapped_column(
        String(160),
        nullable=False,
    )

    email: Mapped[str | None] = mapped_column(
        String(160),
        nullable=True,
    )

    phone: Mapped[str | None] = mapped_column(
        String(60),
        nullable=True,
    )

    # Stores a bcrypt hash, never the plain four-digit PIN.
    pin: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    role: Mapped[str] = mapped_column(
        String(40),
        default="cashier",
        nullable=False,
    )

    permissions: Mapped[dict] = mapped_column(
        JSONB,
        default=dict,
        nullable=False,
    )
