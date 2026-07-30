import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Integer, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class Provider(Base):
    """An AI provider tracked by the internal data-residency/compliance
    tracker. Not exposed to ShadowAI tenants - operator-only reference data
    that eventually informs ShadowAI's own CatalogEntry.data_residency
    review, never written automatically."""

    __tablename__ = "providers"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    slug: Mapped[str] = mapped_column(String(100), unique=True)
    display_name: Mapped[str] = mapped_column(String(255))
    website_url: Mapped[str | None] = mapped_column(String(500), default=None)
    status: Mapped[str] = mapped_column(String(20), default="active")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    # Company-level signal, independent of any one product's processing
    # location - see app/tracker/domicile_classifier.py. Recomputed
    # automatically from all of this provider's enabled sources whenever
    # any of them changes (app/tracker/run.py::reevaluate_provider_domicile).
    eu_domicile_status: Mapped[str] = mapped_column(String(20), default="unclear")
    eu_domicile_evidence_quote: Mapped[str | None] = mapped_column(String(500), default=None)
    # Not a ForeignKey - same circular-dependency reasoning as
    # Product.eu_eea_evidence_source_id; advisory metadata only.
    eu_domicile_evidence_source_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(), default=None)
    eu_domicile_evaluated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    # Offsets of the matched evidence within that source's normalized text -
    # lets the frontend jump to/highlight the exact match in the existing
    # version-diff viewer instead of only showing a quote string.
    eu_domicile_evidence_char_start: Mapped[int | None] = mapped_column(Integer, default=None)
    eu_domicile_evidence_char_end: Mapped[int | None] = mapped_column(Integer, default=None)

    # Populated only when eu_domicile_status == "conflicting": one enabled
    # source made a self-referential EU claim, another made a
    # self-referential non-EU claim. eu_domicile_evidence_quote/source_id
    # above hold the EU-claiming side; these hold the non-EU-claiming side.
    # See app/tracker/domicile_classifier.py.
    eu_domicile_conflicting_quote: Mapped[str | None] = mapped_column(String(500), default=None)
    eu_domicile_conflicting_source_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(), default=None)

    # Best-effort corroboration against an authoritative company registry
    # (GLEIF / Brønnøysundregistrene) - see app/tracker/registries.py. A
    # separate signal from the page-scraped eu_domicile_status above; never
    # silently overrides it, only surfaced alongside it for a human to
    # weigh - a registry disagreement is a real, interesting finding, not
    # grounds to auto-correct the page-scraped verdict.
    registry_verified_country: Mapped[str | None] = mapped_column(String(2), default=None)
    registry_source: Mapped[str | None] = mapped_column(String(20), default=None)
    registry_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
