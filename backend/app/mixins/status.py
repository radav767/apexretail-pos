from sqlalchemy import Boolean
from sqlalchemy.orm import Mapped, mapped_column

class StatusMixin:
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    deleted: Mapped[bool] = mapped_column(Boolean, default=False)
