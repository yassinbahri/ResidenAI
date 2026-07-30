import uuid
from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy import delete, select

from app.core.db import SessionLocal
from app.models.document_version import DocumentVersion
from app.models.product import Product
from app.models.provider import Provider
from app.models.source import Source
from app.models.source_observation import SourceObservation
from app.tracker.fetch import FetchResult
from app.tracker.run import check_source, due_sources, freshness_state, reevaluate_product_residency
from app.tracker.seed_sources import upsert_seed_registry


class FakeFetcher:
    """Duck-typed stand-in for HttpFetcher.fetch(); results are consumed
    from the queue in order."""

    def __init__(self, results: list[FetchResult]) -> None:
        self._results = list(results)

    def fetch(self, request) -> FetchResult:
        return self._results.pop(0)


def _success_result(body: str) -> FetchResult:
    from hashlib import sha256

    return FetchResult(
        url="https://example.test/docs",
        status_code=200,
        fetched_at=datetime.now(timezone.utc),
        body=body,
        body_sha256=sha256(body.encode()).hexdigest(),
        etag='"v1"',
        last_modified="Mon, 01 Jan 2026 00:00:00 GMT",
        not_modified=False,
    )


def _not_modified_result() -> FetchResult:
    return FetchResult(
        url="https://example.test/docs",
        status_code=304,
        fetched_at=datetime.now(timezone.utc),
        body=None,
        body_sha256=None,
        etag='"v1"',
        last_modified="Mon, 01 Jan 2026 00:00:00 GMT",
        not_modified=True,
    )


def _make_provider_source(db) -> Source:
    provider = Provider(slug=f"test-{uuid.uuid4()}", display_name="Test Provider")
    db.add(provider)
    db.flush()
    product = Product(provider_id=provider.id, slug="api", display_name="Test API", product_type="direct_api")
    db.add(product)
    db.flush()
    source = Source(
        provider_id=provider.id,
        product_id=product.id,
        source_key="docs",
        canonical_url="https://example.test/docs",
        authority="official_product_documentation",
    )
    db.add(source)
    db.flush()
    return source


def _cleanup(db, provider_id) -> None:
    source_ids = [s.id for s in db.execute(select(Source).where(Source.provider_id == provider_id)).scalars()]
    for source_id in source_ids:
        db.execute(delete(DocumentVersion).where(DocumentVersion.source_id == source_id))
        db.execute(delete(SourceObservation).where(SourceObservation.source_id == source_id))
    db.execute(delete(Source).where(Source.provider_id == provider_id))
    db.execute(delete(Product).where(Product.provider_id == provider_id))
    db.execute(delete(Provider).where(Provider.id == provider_id))
    db.commit()


def test_check_source_creates_document_version_on_first_success() -> None:
    with SessionLocal() as db:
        source = _make_provider_source(db)
        db.commit()
        provider_id = source.provider_id

        try:
            fetcher = FakeFetcher([_success_result("<main><p>EU only</p></main>")])
            outcome = check_source(db, source, fetcher)

            assert outcome.observation.status == "success"
            assert outcome.new_document_version is not None
            assert "EU only" in outcome.new_document_version.normalized_content
            assert source.failure_count == 0
            assert source.last_success_at is not None
            assert source.next_check_at > datetime.now(timezone.utc)
        finally:
            _cleanup(db, provider_id)


def test_check_source_no_new_version_when_content_unchanged() -> None:
    with SessionLocal() as db:
        source = _make_provider_source(db)
        db.commit()
        provider_id = source.provider_id

        try:
            fetcher = FakeFetcher(
                [
                    _success_result("<main><p>EU only</p></main>"),
                    _success_result("<main><p>EU only</p></main>"),
                ]
            )
            check_source(db, source, fetcher)
            second = check_source(db, source, fetcher)

            assert second.observation.status == "success"
            assert second.new_document_version is None

            versions = db.execute(
                select(DocumentVersion).where(DocumentVersion.source_id == source.id)
            ).scalars().all()
            assert len(versions) == 1
        finally:
            _cleanup(db, provider_id)


def test_check_source_creates_new_version_when_content_changes() -> None:
    with SessionLocal() as db:
        source = _make_provider_source(db)
        db.commit()
        provider_id = source.provider_id

        try:
            fetcher = FakeFetcher(
                [
                    _success_result("<main><p>EU only</p></main>"),
                    _success_result("<main><p>Global infrastructure</p></main>"),
                ]
            )
            first = check_source(db, source, fetcher)
            second = check_source(db, source, fetcher)

            assert second.new_document_version is not None
            assert second.new_document_version.predecessor_id == first.new_document_version.id
            assert source.last_change_at is not None
        finally:
            _cleanup(db, provider_id)


def test_check_source_not_modified_records_observation_without_new_version() -> None:
    with SessionLocal() as db:
        source = _make_provider_source(db)
        db.commit()
        provider_id = source.provider_id

        try:
            fetcher = FakeFetcher([_success_result("<main><p>EU only</p></main>"), _not_modified_result()])
            check_source(db, source, fetcher)
            second = check_source(db, source, fetcher)

            assert second.observation.status == "not_modified"
            assert second.new_document_version is None
        finally:
            _cleanup(db, provider_id)


def test_check_source_failure_sets_backoff_and_increments_failure_count() -> None:
    with SessionLocal() as db:
        source = _make_provider_source(db)
        db.commit()
        provider_id = source.provider_id

        try:

            class FailingFetcher:
                def fetch(self, request):
                    raise httpx.ConnectTimeout("timed out")

            outcome = check_source(db, source, FailingFetcher())

            assert outcome.observation.status == "failed"
            assert outcome.observation.error_class == "ConnectTimeout"
            assert source.failure_count == 1
            assert source.backoff_until is not None
            assert source.backoff_until > datetime.now(timezone.utc)
        finally:
            _cleanup(db, provider_id)


def test_due_sources_excludes_disabled_and_not_yet_due() -> None:
    with SessionLocal() as db:
        source = _make_provider_source(db)
        source.next_check_at = datetime.now(timezone.utc) - timedelta(minutes=1)
        db.commit()
        provider_id = source.provider_id

        try:
            due_ids = {s.id for s in due_sources(db)}
            assert source.id in due_ids

            source.enabled = False
            db.commit()
            due_ids = {s.id for s in due_sources(db)}
            assert source.id not in due_ids
        finally:
            _cleanup(db, provider_id)


def test_freshness_state_transitions() -> None:
    with SessionLocal() as db:
        source = _make_provider_source(db)
        db.commit()
        provider_id = source.provider_id

        try:
            now = datetime.now(timezone.utc)
            assert freshness_state(source, now) == "stale"  # never checked

            source.last_success_at = now
            source.next_check_at = now + timedelta(days=7)
            assert freshness_state(source, now) == "fresh"

            source.next_check_at = now - timedelta(minutes=1)
            assert freshness_state(source, now) == "due"

            source.max_healthy_age_seconds = 60
            source.last_success_at = now - timedelta(minutes=5)
            assert freshness_state(source, now) == "stale"

            source.backoff_until = now + timedelta(minutes=5)
            assert freshness_state(source, now) == "blocked"

            source.enabled = False
            assert freshness_state(source, now) == "disabled"
        finally:
            _cleanup(db, provider_id)


def test_check_source_automatically_updates_product_residency_status() -> None:
    """The whole point of this tool: a source change must update its
    product's EU/EEA verdict without any human action, in the same
    transaction as the check itself."""
    with SessionLocal() as db:
        source = _make_provider_source(db)
        db.commit()
        provider_id = source.provider_id

        try:
            product = db.get(Product, source.product_id)
            assert product.eu_eea_status == "unclear"  # default, nothing captured yet

            fetcher = FakeFetcher(
                [_success_result("<main><p>We offer data residency in Europe for all customers.</p></main>")]
            )
            check_source(db, source, fetcher)

            db.refresh(product)
            assert product.eu_eea_status == "available"
            assert product.eu_eea_evidence_quote is not None
            assert product.eu_eea_evidence_source_id == source.id
            assert product.eu_eea_evaluated_at is not None
        finally:
            _cleanup(db, provider_id)


def test_check_source_does_not_reevaluate_residency_when_content_unchanged() -> None:
    with SessionLocal() as db:
        source = _make_provider_source(db)
        db.commit()
        provider_id = source.provider_id

        try:
            fetcher = FakeFetcher(
                [
                    _success_result("<main><p>We offer data residency in Europe.</p></main>"),
                    _not_modified_result(),
                ]
            )
            check_source(db, source, fetcher)
            product = db.get(Product, source.product_id)
            first_evaluated_at = product.eu_eea_evaluated_at

            check_source(db, source, fetcher)
            db.refresh(product)
            assert product.eu_eea_evaluated_at == first_evaluated_at
        finally:
            _cleanup(db, provider_id)


def test_domicile_evaluation_ignores_privacy_security_sources() -> None:
    # source_class gate (2026-07-29): a privacy/security page almost never
    # states legal domicile, so it must not be able to supply a domicile
    # verdict even if its text happens to contain a self-referential EU
    # claim - only legal_notice/trust_center-classed sources count.
    with SessionLocal() as db:
        source = _make_provider_source(db)
        source.source_class = "privacy_security"
        db.commit()
        provider_id = source.provider_id

        try:
            fetcher = FakeFetcher(
                [_success_result("<main><p>We are headquartered in Germany and comply with the GDPR.</p></main>")]
            )
            check_source(db, source, fetcher)

            provider = db.get(Provider, provider_id)
            assert provider.eu_domicile_status == "unclear"
        finally:
            _cleanup(db, provider_id)


def test_domicile_evaluation_uses_legal_notice_sources() -> None:
    with SessionLocal() as db:
        source = _make_provider_source(db)
        source.source_class = "legal_notice"
        db.commit()
        provider_id = source.provider_id

        try:
            fetcher = FakeFetcher(
                [_success_result("<main><p>We are headquartered in Germany and comply with the GDPR.</p></main>")]
            )
            check_source(db, source, fetcher)

            provider = db.get(Provider, provider_id)
            assert provider.eu_domicile_status == "eu_domiciled"
            assert provider.eu_domicile_evidence_char_start is not None
        finally:
            _cleanup(db, provider_id)


def test_residency_evidence_attribution_is_deterministic_across_sources() -> None:
    """Two sources both stating a residency claim must always credit the same
    one. The classifier takes the first match across sources, so without an
    ORDER BY the evidence quote and linked source could flip between identical
    runs on whatever order Postgres returned - phantom churn in the audit
    trail this tool exists to provide. Lowest source_key wins."""
    with SessionLocal() as db:
        source_a = _make_provider_source(db)
        provider_id = source_a.provider_id
        source_a.source_key = "a-docs"
        source_z = Source(
            provider_id=provider_id,
            product_id=source_a.product_id,
            source_key="z-docs",
            canonical_url="https://example.test/z-docs",
            authority="official_product_documentation",
        )
        db.add(source_z)
        db.commit()

        try:
            body = "<main><p>Data is processed in the EU for all customers.</p></main>"
            check_source(db, source_z, FakeFetcher([_success_result(body)]))
            check_source(db, source_a, FakeFetcher([_success_result(body)]))

            product = db.get(Product, source_a.product_id)
            db.refresh(product)
            assert product.eu_eea_status == "available"
            assert product.eu_eea_evidence_source_id == source_a.id

            # Re-running from already-captured content must not move it.
            reevaluate_product_residency(db, product.id)
            db.commit()
            db.refresh(product)
            assert product.eu_eea_evidence_source_id == source_a.id
        finally:
            _cleanup(db, provider_id)


def test_seed_registry_upsert_is_idempotent() -> None:
    with SessionLocal() as db:
        upsert_seed_registry(db)
        first_count = len(db.execute(select(Provider)).scalars().all())

        upsert_seed_registry(db)
        provider_rows = db.execute(select(Provider)).scalars().all()

        assert len(provider_rows) == first_count
        assert first_count >= 7  # openai, anthropic, azure, bedrock, google, mistral, cohere

        slugs = {p.slug for p in provider_rows}
        assert "openai" in slugs
        assert "anthropic" in slugs
