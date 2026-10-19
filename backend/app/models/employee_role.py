import uuid

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, BaseModel


class EmployeeRole(Base, BaseModel):
    __tablename__ = "employee_roles"
    __table_args__ = (UniqueConstraint("company_id", "name", name="uq_employee_roles_company_name"),)

    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    description: Mapped[str | None] = mapped_column(String(240), nullable=True)
    permissions: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

