import difflib
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.auth import require_admin
from app.api.errors import api_error
from app.api.schemas import (
    DiffResponse,
    ProductSummary,
    ProviderSummary,
    SourceSummary,
    VersionDetail,
    VersionSummary,
)
from app.core.db import get_db
from app.models.document_version import DocumentVersion
from app.models.product import Product
from app.models.provider import Provider
from app.models.source import Source
from app.tracker.run import freshness_state
from app.tracker.scoring import compute_eu_alignment_score

router = APIRouter()

# Worse-first ordering for picking a single "worst" freshness state to
# summarize a provider's sources with.
_FRESHNESS_SEVERITY = {"stale": 0, "blocked": 1, "due": 2, "checking": 2, "fresh": 3, "disabled": 4}


@router.get("/providers", response_model=list[ProviderSummary], dependencies=[Depends(require_admin)])
def list_providers(db: Session = Depends(get_db)) -> list[ProviderSummary]:
    providers = db.execute(select(Provider).order_by(Provider.display_name)).scalars().all()
    now = datetime.now(timezone.utc)
    results = []
    for provider in providers:
        sources = db.execute(select(Source).where(Source.provider_id == provider.id)).scalars().all()
        enabled_sources = [s for s in sources if s.enabled]
        states = [freshness_state(s, now) for s in enabled_sources] or ["disabled"]
        worst = min(states, key=lambda s: _FRESHNESS_SEVERITY.get(s, 99))

        domicile_evidence_source_key = None
        if provider.eu_domicile_evidence_source_id is not None:
            evidence_source = db.get(Source, provider.eu_domicile_evidence_source_id)
            domicile_evidence_source_key = evidence_source.source_key if evidence_source else None

        conflicting_source_key = None
        if provider.eu_domicile_conflicting_source_id is not None:
            conflicting_source = db.get(Source, provider.eu_domicile_conflicting_source_id)
            conflicting_source_key = conflicting_source.source_key if conflicting_source else None

        results.append(
            ProviderSummary(
                id=provider.id,
                slug=provider.slug,
                display_name=provider.display_name,
                website_url=provider.website_url,
                source_count=len(sources),
                enabled_source_count=len(enabled_sources),
                worst_freshness_state=worst,
                eu_domicile_status=provider.eu_domicile_status,
                eu_domicile_evidence_quote=provider.eu_domicile_evidence_quote,
                eu_domicile_evidence_source_key=domicile_evidence_source_key,
                eu_domicile_evidence_char_start=provider.eu_domicile_evidence_char_start,
                eu_domicile_evidence_char_end=provider.eu_domicile_evidence_char_end,
                eu_domicile_evaluated_at=provider.eu_domicile_evaluated_at,
                eu_domicile_conflicting_quote=provider.eu_domicile_conflicting_quote,
                eu_domicile_conflicting_source_key=conflicting_source_key,
                registry_verified_country=provider.registry_verified_country,
                registry_source=provider.registry_source,
                registry_checked_at=provider.registry_checked_at,
            )
        )
    return results


@router.get(
    "/providers/{provider_id}/products",
    response_model=list[ProductSummary],
    dependencies=[Depends(require_admin)],
)
def list_provider_products(provider_id: UUID, db: Session = Depends(get_db)) -> list[ProductSummary]:
    """The actual answer this tool exists to give: per product, is it
    EU/EEA resident (or not, or customer-selectable), with the evidence
    that produced that answer. See app/tracker/residency_classifier.py."""
    provider = db.get(Provider, provider_id)
    if provider is None:
        raise api_error(404, "provider_not_found", "no such provider")

    products = (
        db.execute(select(Product).where(Product.provider_id == provider_id).order_by(Product.display_name))
        .scalars()
        .all()
    )
    results = []
    for product in products:
        evidence_source_key = None
        if product.eu_eea_evidence_source_id is not None:
            evidence_source = db.get(Source, product.eu_eea_evidence_source_id)
            evidence_source_key = evidence_source.source_key if evidence_source else None

        score, tier = compute_eu_alignment_score(provider.eu_domicile_status, product.eu_eea_status)

        results.append(
            ProductSummary(
                id=product.id,
                slug=product.slug,
                display_name=product.display_name,
                product_type=product.product_type,
                eu_eea_status=product.eu_eea_status,
                eu_eea_evidence_quote=product.eu_eea_evidence_quote,
                eu_eea_evidence_source_key=evidence_source_key,
                eu_eea_evidence_char_start=product.eu_eea_evidence_char_start,
                eu_eea_evidence_char_end=product.eu_eea_evidence_char_end,
                eu_eea_evaluated_at=product.eu_eea_evaluated_at,
                eu_alignment_score=score,
                eu_alignment_tier=tier,
            )
        )
    return results


@router.get(
    "/providers/{provider_id}/sources",
    response_model=list[SourceSummary],
    dependencies=[Depends(require_admin)],
)
def list_provider_sources(provider_id: UUID, db: Session = Depends(get_db)) -> list[SourceSummary]:
    provider = db.get(Provider, provider_id)
    if provider is None:
        raise api_error(404, "provider_not_found", "no such provider")

    sources = (
        db.execute(select(Source).where(Source.provider_id == provider_id).order_by(Source.source_key))
        .scalars()
        .all()
    )
    now = datetime.now(timezone.utc)
    results = []
    for source in sources:
        product = db.get(Product, source.product_id) if source.product_id else None
        results.append(
            SourceSummary(
                id=source.id,
                source_key=source.source_key,
                canonical_url=source.canonical_url,
                authority=source.authority,
                source_class=source.source_class,
                enabled=source.enabled,
                product_display_name=product.display_name if product else "",
                freshness_state=freshness_state(source, now),
                last_success_at=source.last_success_at,
                last_change_at=source.last_change_at,
                failure_count=source.failure_count,
            )
        )
    return results


@router.get(
    "/sources/{source_id}/versions",
    response_model=list[VersionSummary],
    dependencies=[Depends(require_admin)],
)
def list_source_versions(source_id: UUID, db: Session = Depends(get_db)) -> list[VersionSummary]:
    source = db.get(Source, source_id)
    if source is None:
        raise api_error(404, "source_not_found", "no such source")

    versions = (
        db.execute(
            select(DocumentVersion)
            .where(DocumentVersion.source_id == source_id)
            .order_by(DocumentVersion.created_at.desc())
        )
        .scalars()
        .all()
    )
    return [
        VersionSummary(
            id=v.id,
            created_at=v.created_at,
            title=v.title,
            predecessor_id=v.predecessor_id,
        )
        for v in versions
    ]


@router.get("/versions/{version_id}", response_model=VersionDetail, dependencies=[Depends(require_admin)])
def get_version(version_id: UUID, db: Session = Depends(get_db)) -> VersionDetail:
    version = db.get(DocumentVersion, version_id)
    if version is None:
        raise api_error(404, "version_not_found", "no such document version")
    return VersionDetail(
        id=version.id,
        source_id=version.source_id,
        created_at=version.created_at,
        title=version.title,
        predecessor_id=version.predecessor_id,
        normalized_content=version.normalized_content,
    )


@router.get(
    "/versions/{version_id}/diff", response_model=DiffResponse, dependencies=[Depends(require_admin)]
)
def get_version_diff(version_id: UUID, db: Session = Depends(get_db)) -> DiffResponse:
    version = db.get(DocumentVersion, version_id)
    if version is None:
        raise api_error(404, "version_not_found", "no such document version")

    if version.predecessor_id is None:
        return DiffResponse(
            version_id=version.id,
            predecessor_id=None,
            is_first_version=True,
            diff_lines=list(version.normalized_content.splitlines()),
        )

    predecessor = db.get(DocumentVersion, version.predecessor_id)
    diff = difflib.unified_diff(
        predecessor.normalized_content.splitlines() if predecessor else [],
        version.normalized_content.splitlines(),
        lineterm="",
        fromfile="previous",
        tofile="current",
    )
    return DiffResponse(
        version_id=version.id,
        predecessor_id=version.predecessor_id,
        is_first_version=False,
        diff_lines=list(diff),
    )
