from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from hashlib import sha256

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.document_version import DocumentVersion
from app.models.product import Product
from app.models.provider import Provider
from app.models.source import Source
from app.models.source_observation import SourceObservation
from app.tracker.domicile_classifier import classify_eu_domicile
from app.tracker.fetch import FetchRequest, HttpFetcher
from app.tracker.normalize import normalize_html
from app.tracker.residency_classifier import classify_eu_eea_residency

_BACKOFF_BASE_SECONDS = 300
_BACKOFF_MAX_SECONDS = 6 * 3600


def due_sources(db: Session, limit: int = 1000) -> list[Source]:
    now = datetime.now(timezone.utc)
    stmt = (
        select(Source)
        .where(Source.enabled.is_(True))
        .where(Source.next_check_at <= now)
        .where((Source.backoff_until.is_(None)) | (Source.backoff_until <= now))
        .order_by(Source.next_check_at.asc())
        .limit(limit)
    )
    return list(db.execute(stmt).scalars())


def freshness_state(source: Source, now: datetime | None = None) -> str:
    """Derived, not stored - avoids a state machine that can drift out of
    sync with last_success_at/backoff_until.

    Staleness is checked before backoff, deliberately. Backoff caps at six
    hours, so a source that has been failing for months is *always* sitting in
    a backoff window when this is called - reporting it as merely "blocked"
    hid the thing that actually matters, which is that the captured content is
    ancient and the verdict resting on it can no longer be trusted. A
    permanent 404 used to show the same amber dot as a source that failed once
    an hour ago, forever.
    """
    now = now or datetime.now(timezone.utc)
    if not source.enabled:
        return "disabled"
    if source.last_success_at is None or (
        (now - source.last_success_at).total_seconds() > source.max_healthy_age_seconds
    ):
        return "stale"
    if source.backoff_until and source.backoff_until > now:
        return "blocked"
    if source.next_check_at <= now:
        return "due"
    return "fresh"


def _latest_document_version(db: Session, source_id) -> DocumentVersion | None:
    stmt = (
        select(DocumentVersion)
        .where(DocumentVersion.source_id == source_id)
        # created_at alone can tie (two versions captured in the same
        # instant), and which row wins here decides a product's residency
        # verdict - so break the tie on the id for a stable answer.
        .order_by(DocumentVersion.created_at.desc(), DocumentVersion.id.desc())
        .limit(1)
    )
    return db.execute(stmt).scalars().first()


def reevaluate_product_residency(db: Session, product_id) -> None:
    """Recompute a product's EU/EEA status from the latest captured content
    of each of its *enabled* sources (disabled sources may hold stale or
    known-unreliable content - see Source.enabled). Cheap enough to run on
    every successful check, so the answer is never more than one check
    cycle stale and never requires a human to update it."""
    product = db.get(Product, product_id)
    if product is None:
        return

    sources = db.execute(
        select(Source).where(Source.product_id == product_id, Source.enabled.is_(True))
    ).scalars().all()

    texts_by_source_key: dict[str, str] = {}
    source_id_by_key: dict[str, object] = {}
    for source in sources:
        latest = _latest_document_version(db, source.id)
        if latest is not None:
            texts_by_source_key[source.source_key] = latest.normalized_content
            source_id_by_key[source.source_key] = source.id

    assessment = classify_eu_eea_residency(texts_by_source_key)
    product.eu_eea_status = assessment.status
    product.eu_eea_evidence_quote = assessment.evidence_quote
    product.eu_eea_evidence_source_id = (
        source_id_by_key.get(assessment.evidence_source_key) if assessment.evidence_source_key else None
    )
    product.eu_eea_evidence_char_start = assessment.evidence_char_start
    product.eu_eea_evidence_char_end = assessment.evidence_char_end
    product.eu_eea_evaluated_at = datetime.now(timezone.utc)


def reevaluate_provider_domicile(db: Session, provider_id) -> None:
    """Recompute a provider's company-domicile status from the latest
    captured content of each of its *enabled* sources - same automatic,
    no-human-input pattern as reevaluate_product_residency, but for the
    company itself rather than any one product's processing location.

    Only sources classed "legal_notice"/"trust_center" are fed to the
    classifier - a privacy or security page almost never states legal
    domicile, and letting one supply a verdict is exactly how a marketing
    page or generic doc page could accidentally produce a false domicile
    claim (see app/models/source.py::SourceClass). Everything else (e.g. a
    weak, unconfident company-info candidate tagged "other" by
    discovery.py) is tracked and checked like any other source, just not
    trusted for this specific verdict."""
    provider = db.get(Provider, provider_id)
    if provider is None:
        return

    sources = (
        db.execute(
            select(Source).where(
                Source.provider_id == provider_id,
                Source.enabled.is_(True),
                Source.source_class.in_(["legal_notice", "trust_center"]),
            )
        )
        .scalars()
        .all()
    )

    texts_by_source_key: dict[str, str] = {}
    source_id_by_key: dict[str, object] = {}
    for source in sources:
        latest = _latest_document_version(db, source.id)
        if latest is not None:
            texts_by_source_key[source.source_key] = latest.normalized_content
            source_id_by_key[source.source_key] = source.id

    assessment = classify_eu_domicile(texts_by_source_key, provider_name=provider.display_name)
    provider.eu_domicile_status = assessment.status
    provider.eu_domicile_evidence_quote = assessment.evidence_quote
    provider.eu_domicile_evidence_source_id = (
        source_id_by_key.get(assessment.evidence_source_key) if assessment.evidence_source_key else None
    )
    provider.eu_domicile_evidence_char_start = assessment.evidence_char_start
    provider.eu_domicile_evidence_char_end = assessment.evidence_char_end
    provider.eu_domicile_conflicting_quote = assessment.conflicting_quote
    provider.eu_domicile_conflicting_source_id = (
        source_id_by_key.get(assessment.conflicting_source_key) if assessment.conflicting_source_key else None
    )
    provider.eu_domicile_evaluated_at = datetime.now(timezone.utc)


def reevaluate_all_products(db: Session) -> int:
    """Backfill/repair helper - recomputes every product's status and its
    provider's domicile status from whatever content is already captured,
    without waiting for the next scheduled check to touch each source.
    Returns the number of products evaluated."""
    provider_ids = db.execute(select(Provider.id)).scalars().all()
    for provider_id in provider_ids:
        reevaluate_provider_domicile(db, provider_id)

    product_ids = db.execute(select(Product.id)).scalars().all()
    for product_id in product_ids:
        reevaluate_product_residency(db, product_id)
    db.commit()
    return len(product_ids)


def _next_backoff(failure_count: int) -> datetime:
    delay = min(_BACKOFF_BASE_SECONDS * (2**failure_count), _BACKOFF_MAX_SECONDS)
    delay += random.uniform(0, delay * 0.1)
    return datetime.now(timezone.utc) + timedelta(seconds=delay)


@dataclass(frozen=True)
class CheckOutcome:
    source: Source
    observation: SourceObservation
    new_document_version: DocumentVersion | None


def check_source(db: Session, source: Source, fetcher: HttpFetcher) -> CheckOutcome:
    now = datetime.now(timezone.utc)
    request = FetchRequest(
        url=source.canonical_url, etag=source.etag, last_modified=source.last_modified
    )

    try:
        result = fetcher.fetch(request)
    except httpx.HTTPStatusError as exc:
        return _record_failure(
            db, source, now, "http_status", str(exc), exc.response.status_code
        )
    except httpx.HTTPError as exc:
        return _record_failure(db, source, now, type(exc).__name__, str(exc), None)

    if result.not_modified:
        observation = SourceObservation(
            source_id=source.id,
            checked_at=now,
            status="not_modified",
            http_status=304,
        )
        db.add(observation)
        _mark_success(source, now, result.etag, result.last_modified)
        db.commit()
        return CheckOutcome(source=source, observation=observation, new_document_version=None)

    assert result.body is not None
    normalized = normalize_html(result.body)

    observation = SourceObservation(
        source_id=source.id,
        checked_at=now,
        status="success",
        http_status=result.status_code,
        raw_sha256=sha256(result.body.encode("utf-8")).hexdigest(),
        normalized_sha256=normalized.text_sha256,
    )
    db.add(observation)
    db.flush()

    new_version = None
    latest = _latest_document_version(db, source.id)
    if latest is None or latest.normalized_sha256 != normalized.text_sha256:
        new_version = DocumentVersion(
            source_id=source.id,
            observation_id=observation.id,
            normalized_sha256=normalized.text_sha256,
            title=normalized.title,
            raw_content=result.body,
            normalized_content=normalized.text,
            predecessor_id=latest.id if latest else None,
        )
        db.add(new_version)
        db.flush()
        source.last_change_at = now
        if source.product_id is not None:
            reevaluate_product_residency(db, source.product_id)
        reevaluate_provider_domicile(db, source.provider_id)

    _mark_success(source, now, result.etag, result.last_modified)
    db.commit()
    return CheckOutcome(source=source, observation=observation, new_document_version=new_version)


def _mark_success(
    source: Source, now: datetime, etag: str | None, last_modified: str | None
) -> None:
    source.etag = etag
    source.last_modified = last_modified
    source.last_success_at = now
    source.next_check_at = now + timedelta(seconds=source.poll_interval_seconds)
    source.failure_count = 0
    source.backoff_until = None


def _record_failure(
    db: Session,
    source: Source,
    now: datetime,
    error_class: str,
    error_message: str,
    http_status: int | None,
) -> CheckOutcome:
    observation = SourceObservation(
        source_id=source.id,
        checked_at=now,
        status="failed",
        http_status=http_status,
        error_class=error_class,
        error_message=error_message[:2000],
    )
    db.add(observation)
    source.failure_count += 1
    source.backoff_until = _next_backoff(source.failure_count)
    db.commit()
    return CheckOutcome(source=source, observation=observation, new_document_version=None)


def run_due_checks(db: Session, fetcher: HttpFetcher | None = None, limit: int = 1000) -> list[CheckOutcome]:
    """Checks every due source, isolating each one.

    check_source already handles the *expected* failures (HTTP errors become
    observations with backoff). This guards the unexpected ones - a parser
    blowing up, a constraint violation, a classifier raising on pathological
    content. Previously a single such source aborted the whole tick, so the
    sources queued behind it were never fetched at all; and because
    _mark_success never ran, the offending source stayed due and killed every
    subsequent tick the same way. One bad page silently froze the tracker.
    """
    owns_fetcher = fetcher is None
    fetcher = fetcher or HttpFetcher()
    outcomes: list[CheckOutcome] = []
    try:
        for source in due_sources(db, limit=limit):
            try:
                outcomes.append(check_source(db, source, fetcher))
            except Exception as exc:  # noqa: BLE001 - deliberately broad, see docstring
                # The session is likely dirty (mid-flush IntegrityError), so
                # reset it before touching the next source.
                db.rollback()
                _record_unexpected_failure(db, source, exc)
    finally:
        if owns_fetcher:
            fetcher.close()
    return outcomes


def _record_unexpected_failure(db: Session, source: Source, exc: Exception) -> None:
    """Applies the same backoff an HTTP failure gets, so a source that raises
    is visible in the observation log and stops being retried every tick
    instead of wedging the scheduler. Failing to even record this must not
    itself abort the run, hence the inner guard."""
    try:
        _record_failure(
            db,
            source,
            datetime.now(timezone.utc),
            f"unexpected:{type(exc).__name__}",
            str(exc),
            None,
        )
    except Exception:  # noqa: BLE001
        db.rollback()
