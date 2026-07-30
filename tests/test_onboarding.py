import uuid

import httpx
from sqlalchemy import delete, select

from app.core.db import SessionLocal
from app.models.product import Product
from app.models.provider import Provider
from app.models.source import Source
from app.tracker.fetch import HttpFetcher
from app.tracker.onboarding import onboard_new_provider

REAL_PRIVACY_PAGE = "<main>" + ("Real privacy policy content about data handling. " * 20) + "</main>"
REAL_IMPRINT_PAGE = "<main>" + ("Example GmbH, registered in Berlin, Germany. Handelsregister HRB 12345. " * 10) + "</main>"


def _cleanup(db, provider_id) -> None:
    source_ids = [s.id for s in db.execute(select(Source).where(Source.provider_id == provider_id)).scalars()]
    for source_id in source_ids:
        db.execute(delete(Source).where(Source.id == source_id))
    db.execute(delete(Product).where(Product.provider_id == provider_id))
    db.execute(delete(Provider).where(Provider.id == provider_id))
    db.commit()


def test_onboard_new_provider_with_successful_discovery() -> None:
    slug = f"test-vendor-{uuid.uuid4().hex[:8]}"

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/":
            return httpx.Response(200, text="<html><body><a href='/privacy'>Privacy</a></body></html>")
        return httpx.Response(200, text=REAL_PRIVACY_PAGE)

    fetcher = HttpFetcher(http_client=httpx.Client(transport=httpx.MockTransport(handler)))

    with SessionLocal() as db:
        result = onboard_new_provider(
            db, slug=slug, display_name="Test Vendor", website_url="https://example.test/", fetcher=fetcher
        )
        try:
            assert result.already_existed is False
            assert result.source_auto_discovered is True
            assert result.discovered_url == "https://example.test/privacy"

            source = db.execute(select(Source).where(Source.provider_id == result.provider.id)).scalar_one()
            assert source.enabled is True
            assert source.canonical_url == "https://example.test/privacy"
        finally:
            _cleanup(db, result.provider.id)


def test_onboard_new_provider_when_discovery_fails_still_creates_a_visible_placeholder() -> None:
    slug = f"test-vendor-{uuid.uuid4().hex[:8]}"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="<html><body><a href='/pricing'>Pricing</a></body></html>")

    fetcher = HttpFetcher(http_client=httpx.Client(transport=httpx.MockTransport(handler)))

    with SessionLocal() as db:
        result = onboard_new_provider(
            db, slug=slug, display_name="Test Vendor", website_url="https://example.test/", fetcher=fetcher
        )
        try:
            assert result.source_auto_discovered is False
            assert result.discovered_url is None

            # Still visible in the registry - not silently skipped.
            provider = db.get(Provider, result.provider.id)
            assert provider is not None
            source = db.execute(select(Source).where(Source.provider_id == result.provider.id)).scalar_one()
            assert source.enabled is False  # flagged as needing manual attention
            assert source.canonical_url == "https://example.test/"
        finally:
            _cleanup(db, result.provider.id)


def test_onboard_new_provider_also_discovers_a_confident_company_info_source() -> None:
    slug = f"test-vendor-{uuid.uuid4().hex[:8]}"

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/":
            return httpx.Response(
                200,
                text="<html><body><a href='/privacy'>Privacy</a><a href='/imprint'>Imprint</a></body></html>",
            )
        if request.url.path == "/imprint":
            return httpx.Response(200, text=REAL_IMPRINT_PAGE)
        return httpx.Response(200, text=REAL_PRIVACY_PAGE)

    fetcher = HttpFetcher(http_client=httpx.Client(transport=httpx.MockTransport(handler)))

    with SessionLocal() as db:
        result = onboard_new_provider(
            db, slug=slug, display_name="Test Vendor", website_url="https://example.test/", fetcher=fetcher
        )
        try:
            assert result.company_info_source_auto_discovered is True
            assert result.company_info_source_confident is True
            assert result.discovered_company_info_url == "https://example.test/imprint"

            sources = db.execute(select(Source).where(Source.provider_id == result.provider.id)).scalars().all()
            source_keys = {s.source_key for s in sources}
            assert source_keys == {f"{slug}-auto-discovered", f"{slug}-company-info"}

            privacy_source = next(s for s in sources if s.source_key == f"{slug}-auto-discovered")
            assert privacy_source.source_class == "privacy_security"

            company_info_source = next(s for s in sources if s.source_key == f"{slug}-company-info")
            assert company_info_source.product_id is None
            assert company_info_source.enabled is True
            assert company_info_source.source_class == "legal_notice"
        finally:
            _cleanup(db, result.provider.id)


def test_onboard_new_provider_tags_an_unconfident_company_info_source_as_other() -> None:
    # The company-info candidate is real content but has no domicile
    # marker (mirrors the real Salesforce/Hugging Face/GitHub false
    # positives found while backfilling the registry) - it's still tracked
    # as a source, just not trusted for a domicile verdict.
    slug = f"test-vendor-{uuid.uuid4().hex[:8]}"

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/":
            return httpx.Response(
                200,
                text="<html><body><a href='/privacy'>Privacy</a><a href='/imprint'>Imprint</a></body></html>",
            )
        return httpx.Response(200, text=REAL_PRIVACY_PAGE)  # no domicile marker anywhere

    fetcher = HttpFetcher(http_client=httpx.Client(transport=httpx.MockTransport(handler)))

    with SessionLocal() as db:
        result = onboard_new_provider(
            db, slug=slug, display_name="Test Vendor", website_url="https://example.test/", fetcher=fetcher
        )
        try:
            assert result.company_info_source_auto_discovered is True
            assert result.company_info_source_confident is False

            company_info_source = db.execute(
                select(Source).where(Source.provider_id == result.provider.id, Source.source_key == f"{slug}-company-info")
            ).scalar_one()
            assert company_info_source.source_class == "other"
        finally:
            _cleanup(db, result.provider.id)


def test_onboard_new_provider_is_idempotent() -> None:
    slug = f"test-vendor-{uuid.uuid4().hex[:8]}"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="<html><body></body></html>")

    fetcher = HttpFetcher(http_client=httpx.Client(transport=httpx.MockTransport(handler)))

    with SessionLocal() as db:
        first = onboard_new_provider(
            db, slug=slug, display_name="Test Vendor", website_url="https://example.test/", fetcher=fetcher
        )
        try:
            second = onboard_new_provider(
                db, slug=slug, display_name="Test Vendor", website_url="https://example.test/", fetcher=fetcher
            )
            assert second.already_existed is True
            assert second.provider.id == first.provider.id

            providers = db.execute(select(Provider).where(Provider.slug == slug)).scalars().all()
            assert len(providers) == 1
        finally:
            _cleanup(db, first.provider.id)
