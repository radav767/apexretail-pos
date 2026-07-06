from datetime import datetime
from sqlalchemy import String, DateTime
from sqlalchemy.orm import Mapped, mapped_column

class SyncMixin:
    sync_status: Mapped[str] = mapped_column(String, default="synced")
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    device_created_by: Mapped[str | None] = mapped_column(String, nullable=True)
