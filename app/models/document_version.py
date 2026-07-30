import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class DocumentVersion(Base):
    """An immutable snapshot of a source's content, created only when the
    normalized content actually changed. Raw and normalized content are
    stored inline as text rather than in object storage - at this scale
    (dozens of sources, weekly checks) a few hundred rows a year is trivial
    for Postgres, and it avoids standing up S3/MinIO for a solo-operator
    tool. Revisit only if volume or a contractual-evidence retention
    requirement demands it."""

    __tablename__ = "document_versions"
    __table_args__ = (UniqueConstraint("source_id", "normalized_sha256"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    source_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sources.id"))
    observation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("source_observations.id"))
    normalized_sha256: Mapped[str] = mapped_column(String(64))
    title: Mapped[str | None] = mapped_column(String(500), default=None)
    raw_content: Mapped[str] = mapped_column()
    normalized_content: Mapped[str] = mapped_column()
    predecessor_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("document_versions.id"), default=None
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
