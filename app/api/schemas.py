from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class ProviderSummary(BaseModel):
    id: UUID
    slug: str
    display_name: str
    website_url: str | None
    source_count: int
    enabled_source_count: int
    worst_freshness_state: str
    eu_domicile_status: str
    eu_domicile_evidence_quote: str | None
    eu_domicile_evidence_source_key: str | None
    eu_domicile_evidence_char_start: int | None
    eu_domicile_evidence_char_end: int | None
    eu_domicile_evaluated_at: datetime | None
    # Populated only when eu_domicile_status == "conflicting" - a second,
    # contradictory self-referential match. See domicile_classifier.py.
    eu_domicile_conflicting_quote: str | None
    eu_domicile_conflicting_source_key: str | None
    # Best-effort registry corroboration (GLEIF/Brreg) - a separate signal
    # from the page-scraped status above, never overrides it. None if never
    # checked or no match found. See app/tracker/registries.py.
    registry_verified_country: str | None
    registry_source: str | None
    registry_checked_at: datetime | None


class ProductSummary(BaseModel):
    id: UUID
    slug: str
    display_name: str
    product_type: str
    eu_eea_status: str
    eu_eea_evidence_quote: str | None
    eu_eea_evidence_source_key: str | None
    eu_eea_evidence_char_start: int | None
    eu_eea_evidence_char_end: int | None
    eu_eea_evaluated_at: datetime | None
    # Combines this product's eu_eea_status with its provider's
    # eu_domicile_status - see app/tracker/scoring.py.
    eu_alignment_score: int
    eu_alignment_tier: str


class SourceSummary(BaseModel):
    id: UUID
    source_key: str
    canonical_url: str
    authority: str
    source_class: str
    enabled: bool
    product_display_name: str
    freshness_state: str
    last_success_at: datetime | None
    last_change_at: datetime | None
    failure_count: int


class VersionSummary(BaseModel):
    id: UUID
    created_at: datetime
    title: str | None
    predecessor_id: UUID | None


class VersionDetail(VersionSummary):
    source_id: UUID
    normalized_content: str


class DiffResponse(BaseModel):
    version_id: UUID
    predecessor_id: UUID | None
    is_first_version: bool
    diff_lines: list[str]
