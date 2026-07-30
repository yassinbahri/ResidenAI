import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class SourceObservation(Base):
    """One check attempt against a source, success or failure - the daily
    freshness proof is computed from these plus Source.last_success_at,
    never inferred from document versions alone (an unchanged page must
    still count as a fresh check)."""

    __tablename__ = "source_observations"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    source_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sources.id"))
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(20))  # success | not_modified | failed
    http_status: Mapped[int | None] = mapped_column(Integer, default=None)
    raw_sha256: Mapped[str | None] = mapped_column(String(64), default=None)
    normalized_sha256: Mapped[str | None] = mapped_column(String(64), default=None)
    error_class: Mapped[str | None] = mapped_column(String(100), default=None)
    error_message: Mapped[str | None] = mapped_column(String(2000), default=None)
    duration_ms: Mapped[int | None] = mapped_column(Integer, default=None)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
