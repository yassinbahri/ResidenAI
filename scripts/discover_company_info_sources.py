"""Backfill: for every provider without a company-info/imprint source, run
automatic discovery (app/tracker/discovery.py::discover_company_info_source)
against its website and add one if a candidate is found. Also re-checks
providers that already have one, in case it was created before the
confidence gate existed (2026-07-29) - see below.

This closes the evidence gap identified while root-causing why no provider
in the registry had ever resolved eu_domiciled: privacy/security pages
(what seed_sources.py originally tracked) rarely state a company's legal
domicile; an imprint/legal-notice page almost always does. This script is
the one-time catch-up for the providers seeded before that discovery
function existed - app/tracker/onboarding.py already does this
automatically for every provider onboarded from now on.

    python scripts/discover_company_info_sources.py

Idempotent - same discipline as seed_sources.py: matches by source_key
(f"{slug}-company-info"), so re-running is a no-op for providers whose
existing source already passes the confidence check.

Reclassification pass (added 2026-07-29): the first run of this script
accepted any content-bearing page as domicile evidence, which is exactly
how Salesforce's "be a trailblazer" marketing page, a Hugging Face org
profile, and a GitHub security-features doc ended up tagged
source_class="legal_notice" - none of them actually state a legal entity's
domicile. This script now re-fetches each existing company-info source's
current URL and re-tags source_class based on whether the page actually
contains a domicile-relevant marker (app/tracker/discovery.py::
looks_like_legal_notice), downgrading weak ones to "other" so they stop
counting as domicile evidence (app/tracker/run.py::
reevaluate_provider_domicile only reads legal_notice/trust_center sources).
"""

from __future__ import annotations

from sqlalchemy import select

from app.core.db import SessionLocal
from app.models.provider import Provider
from app.models.source import Source
from app.tracker.discovery import discover_company_info_source, looks_like_legal_notice
from app.tracker.fetch import FetchRequest, HttpFetcher
from app.tracker.normalize import normalize_html


def _reclassify_existing(source: Source, fetcher: HttpFetcher) -> str:
    """Re-fetches an existing company-info source's URL and returns a
    one-line status string. Never raises - a fetch failure just leaves the
    existing source_class untouched."""
    try:
        result = fetcher.fetch(FetchRequest(url=source.canonical_url))
    except Exception as exc:
        return f"could not re-check ({type(exc).__name__}), left as {source.source_class}"
    if not result.body:
        return f"empty response on re-check, left as {source.source_class}"

    text = normalize_html(result.body).text
    confident = looks_like_legal_notice(text)
    new_class = "legal_notice" if confident else "other"
    if new_class == source.source_class:
        return f"unchanged ({source.source_class})"

    old_class = source.source_class
    source.source_class = new_class
    return f"reclassified {old_class} -> {new_class}"


def main() -> None:
    with SessionLocal() as db:
        providers = list(db.execute(select(Provider)).scalars())
        fetcher = HttpFetcher()

        found = 0
        reclassified = 0
        not_found = 0

        try:
            for provider in providers:
                source_key = f"{provider.slug}-company-info"
                existing = db.execute(
                    select(Source).where(
                        Source.provider_id == provider.id, Source.source_key == source_key
                    )
                ).scalar_one_or_none()

                if existing is not None:
                    status = _reclassify_existing(existing, fetcher)
                    print(f"  {provider.slug}: {status}")
                    if status.startswith("reclassified"):
                        reclassified += 1
                        db.commit()
                    continue

                if not provider.website_url:
                    print(f"  {provider.slug}: no website_url on record, skipping")
                    not_found += 1
                    continue

                candidate = discover_company_info_source(provider.website_url, fetcher=fetcher)
                if candidate is None:
                    print(f"  {provider.slug}: no company-info source found automatically")
                    not_found += 1
                    continue

                db.add(
                    Source(
                        provider_id=provider.id,
                        product_id=None,
                        source_key=source_key,
                        canonical_url=candidate.url,
                        authority="official_legal",
                        source_class="legal_notice" if candidate.confident else "other",
                        enabled=True,
                    )
                )
                db.commit()
                confidence_note = "" if candidate.confident else " (weak candidate, not domicile-authoritative)"
                print(f"  {provider.slug}: found {candidate.url}{confidence_note}")
                found += 1
        finally:
            fetcher.close()

    print(
        f"\nDone. {found} newly discovered, {reclassified} reclassified, "
        f"{not_found} need a source added manually."
    )


if __name__ == "__main__":
    main()
