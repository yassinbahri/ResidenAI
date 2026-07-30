import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, Uuid, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base

# Deterministic, keyword-derived signal (app/tracker/residency_classifier.py)
# - not a legal conclusion. "not_available" beats "available" in priority
# when both match, since a false "available" claim is more harmful than
# missing a subtler positive statement.
EU_EEA_STATUSES = ("available", "selectable", "not_available", "unclear")


class Product(Base):
    """A distinct offering of a provider (e.g. "direct API" vs. "Azure OpenAI
    Data Zone deployment") - residency/retention/training facts attach here,
    never to the provider as a whole, since those properties differ by
    product."""

    __tablename__ = "products"
    __table_args__ = (UniqueConstraint("provider_id", "slug"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    provider_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("providers.id"))
    slug: Mapped[str] = mapped_column(String(100))
    display_name: Mapped[str] = mapped_column(String(255))
    product_type: Mapped[str] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(20), default="active")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    # The actual "is this EU/EEA resident" answer this whole tool exists to
    # surface - recomputed automatically every time any of this product's
    # sources gets a new document version (app/tracker/run.py). Never set by
    # hand; a bad automatic answer with visible evidence is more useful and
    # more honest than a fresher-looking blank field.
    eu_eea_status: Mapped[str] = mapped_column(String(20), default="unclear")
    eu_eea_evidence_quote: Mapped[str | None] = mapped_column(String(500), default=None)
    # Deliberately not a ForeignKey - products and sources already reference
    # each other (source.product_id), and a second cross-reference here
    # would create a circular FK dependency between the two tables. This is
    # advisory metadata for display only, not a data-integrity requirement.
    eu_eea_evidence_source_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(), default=None)
    eu_eea_evaluated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    # Offsets of the matched evidence within that source's normalized text -
    # lets the frontend jump to/highlight the exact match instead of only
    # showing a quote string.
    eu_eea_evidence_char_start: Mapped[int | None] = mapped_column(Integer, default=None)
    eu_eea_evidence_char_end: Mapped[int | None] = mapped_column(Integer, default=None)
