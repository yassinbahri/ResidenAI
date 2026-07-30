import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base

# Ordered roughly by decreasing authority - lower-tier sources should never
# silently override a higher-tier one during review.
SourceAuthority = Enum(
    "contractual",
    "official_legal",
    "official_product_documentation",
    "official_trust_center",
    "official_release_notes",
    "official_api",
    "official_blog",
    "official_support",
    "official_forum_staff",
    "secondary_reputable",
    "community",
    name="source_authority",
)

# What kind of page this is, independent of how much we trust it
# (SourceAuthority above). Added so a domicile verdict can require a page
# that actually states legal-entity facts (legal_notice/trust_center)
# instead of accepting any page that merely matched a keyword and had
# enough text - see app/tracker/run.py::reevaluate_provider_domicile.
SourceClass = Enum(
    "legal_notice",
    "privacy_security",
    "trust_center",
    "region_matrix",
    "changelog",
    "other",
    name="source_class",
)


class Source(Base):
    """One monitored document. Freshness state is derived at query time
    from last_success_at/max_healthy_age_seconds rather than stored - see
    app/tracker/run.py::freshness_state - so there is no separate state
    machine to keep in sync."""

    __tablename__ = "sources"
    __table_args__ = (UniqueConstraint("provider_id", "source_key"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    provider_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("providers.id"))
    product_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("products.id"), default=None)
    source_key: Mapped[str] = mapped_column(String(200))
    canonical_url: Mapped[str] = mapped_column(String(1000))
    source_type: Mapped[str] = mapped_column(String(50), default="html_document")
    authority: Mapped[str] = mapped_column(SourceAuthority)
    source_class: Mapped[str] = mapped_column(SourceClass, default="other")
    enabled: Mapped[bool] = mapped_column(default=True)

    # Solo-operator cadence: weekly checks / two-week healthy age - a
    # vendor's residency policy doesn't change hourly, and this is
    # reference data for one internal catalogue, not a paid SLA.
    poll_interval_seconds: Mapped[int] = mapped_column(Integer, default=7 * 24 * 3600)
    max_healthy_age_seconds: Mapped[int] = mapped_column(Integer, default=14 * 24 * 3600)

    etag: Mapped[str | None] = mapped_column(String(500), default=None)
    last_modified: Mapped[str | None] = mapped_column(String(200), default=None)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    last_change_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    next_check_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    failure_count: Mapped[int] = mapped_column(Integer, default=0)
    backoff_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
