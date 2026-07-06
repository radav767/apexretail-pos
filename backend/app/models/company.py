from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base, BaseModel

class Company(Base, BaseModel):
    __tablename__ = "companies"

    name: Mapped[str] = mapped_column(String, nullable=False)
    owner_name: Mapped[str | None] = mapped_column(String, nullable=True)
    owner_email: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    business_type: Mapped[str] = mapped_column(String, default="Retail")
    country: Mapped[str | None] = mapped_column(String, nullable=True)
    phone: Mapped[str | None] = mapped_column(String, nullable=True)
