import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class DocumentVersion(Base):
    """An immutable snapshot of a source's content, created only when the
    normalized content actually changed. Raw and normalized content are
    stored inline as text rather than in object storage - at this scale
    (dozens of sources, weekly checks) a few hundred rows a year is trivial
    for Postgres, and it avoids standing up S3/MinIO for a solo-operator
    tool. Revisit only if volume or a contractual-evidence retention
    requirement demands it.

    Deliberately *not* unique on (source_id, normalized_sha256). Vendors
    revert wording all the time - a residency claim is added, pulled, then
    reinstated - and a content-addressed uniqueness rule cannot express that
    timeline: the reappearing hash collides with its own earlier row. This is
    a version history ordered by created_at and linked by predecessor_id, not
    a content-addressed store, so A -> B -> A is three legitimate rows. What
    prevents duplicates is check_source comparing against the *latest*
    version, which is also the only comparison that means anything here."""

    __tablename__ = "document_versions"
    __table_args__ = (
        # Every read is "latest version for this source" (_latest_document_version).
        Index("ix_document_versions_source_created", "source_id", "created_at"),
    )

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
