import uuid
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from app.mixins import AuditMixin, StatusMixin, BusinessMixin

class Base(DeclarativeBase):
    pass

class BaseModel(AuditMixin, StatusMixin):
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

class BaseBusinessModel(BaseModel, BusinessMixin):
    pass
