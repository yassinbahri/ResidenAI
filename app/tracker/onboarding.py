"""Onboard a brand-new provider given just a name and homepage. This is the
one part of "handling new companies automatically" that genuinely can be
fully automatic without an AI or human research step - see discovery.py for
the honest limits of the URL-finding part.

Idempotent like seed_sources.py::upsert_seed_registry - re-running with the
same slug is a no-op, never a duplicate.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.product import Product
from app.models.provider import Provider
from app.models.source import Source
from app.tracker.discovery import discover_company_info_source, discover_privacy_source
from app.tracker.fetch import HttpFetcher


@dataclass(frozen=True)
class OnboardingResult:
    provider: Provider
    already_existed: bool
    source_auto_discovered: bool
    discovered_url: str | None
    company_info_source_auto_discovered: bool
    discovered_company_info_url: str | None
    # False whenever discovered_company_info_url is None. When it's set,
    # True means the page itself contained a domicile-relevant marker
    # (source_class="legal_notice", counts as domicile evidence); False
    # means only a plausible-looking page was found with no such marker
    # (source_class="other" - tracked, but not trusted for a domicile
    # verdict until a human confirms it). See discovery.py.
    company_info_source_confident: bool


def onboard_new_provider(
    db: Session,
    slug: str,
    display_name: str,
    website_url: str,
    product_slug: str = "primary",
    product_display_name: str | None = None,
    product_type: str = "unclassified",
    fetcher: HttpFetcher | None = None,
) -> OnboardingResult:
    """Creates the provider/product records and attempts automatic source
    discovery. If discovery fails, the provider/product still get created
    (visible in the registry) but with a disabled source pointing at the
    bare homepage - a clear "needs a source added" signal rather than a
    silently missing company or a fabricated URL."""
    existing = db.execute(select(Provider).where(Provider.slug == slug)).scalar_one_or_none()
    if existing is not None:
        return OnboardingResult(existing, True, False, None, False, None, False)

    provider = Provider(slug=slug, display_name=display_name, website_url=website_url)
    db.add(provider)
    db.flush()

    product = Product(
        provider_id=provider.id,
        slug=product_slug,
        display_name=product_display_name or display_name,
        product_type=product_type,
    )
    db.add(product)
    db.flush()

    discovered_url = discover_privacy_source(website_url, fetcher=fetcher)
    found = discovered_url is not None
    db.add(
        Source(
            provider_id=provider.id,
            product_id=product.id,
            source_key=f"{slug}-auto-discovered",
            canonical_url=discovered_url or website_url,
            authority="official_product_documentation",
            source_class="privacy_security",
            enabled=found,
        )
    )

    # Company-info/imprint source: provider-level, not product-level -
    # states legal domicile, which the privacy source above almost never
    # does. See discovery.py's module docstring for why this was added.
    company_info_candidate = discover_company_info_source(website_url, fetcher=fetcher)
    company_info_found = company_info_candidate is not None
    discovered_company_info_url = company_info_candidate.url if company_info_candidate else None
    company_info_confident = company_info_candidate.confident if company_info_candidate else False
    if company_info_candidate is not None:
        db.add(
            Source(
                provider_id=provider.id,
                product_id=None,
                source_key=f"{slug}-company-info",
                canonical_url=company_info_candidate.url,
                authority="official_legal",
                # Only a confident candidate counts as domicile evidence -
                # see app/tracker/run.py::reevaluate_provider_domicile.
                source_class="legal_notice" if company_info_candidate.confident else "other",
                enabled=True,
            )
        )

    db.commit()
    return OnboardingResult(
        provider,
        False,
        found,
        discovered_url,
        company_info_found,
        discovered_company_info_url,
        company_info_confident,
    )
