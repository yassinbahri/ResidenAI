"""Best-effort corroboration pass: for every provider, look up its display
name in GLEIF (and, as a fallback, Brønnøysundregistrene) and record
whether an authoritative registry agrees with the page-scraped
eu_domicile_status. A disagreement is surfaced, never auto-corrected - see
app/tracker/registries.py for why this stays advisory.

    python scripts/verify_domicile_registries.py

Re-running just re-checks and overwrites the stored
registry_verified_country/registry_source/registry_checked_at fields on
Provider; it never touches eu_domicile_status itself.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select

from app.core.db import SessionLocal
from app.models.provider import Provider
from app.tracker.registries import lookup_brreg, lookup_gleif

_EU_EEA_COUNTRY_CODES = {
    "AT", "BE", "BG", "HR", "CY", "CZ", "DE", "DK", "EE", "ES", "FI", "FR", "GR",
    "HU", "IE", "IT", "LT", "LU", "LV", "MT", "NL", "PL", "PT", "RO", "SE", "SI",
    "SK", "NO", "IS", "LI",
}


def main() -> None:
    with SessionLocal() as db:
        providers = list(db.execute(select(Provider)).scalars())

        checked = 0
        matched = 0
        agreements = 0
        disagreements = 0

        for provider in providers:
            checked += 1
            match = lookup_gleif(provider.display_name) or lookup_brreg(provider.display_name)
            if match is None:
                print(f"  {provider.slug}: no registry match found")
                continue

            matched += 1
            provider.registry_verified_country = match.country_code
            provider.registry_source = match.source
            provider.registry_checked_at = datetime.now(timezone.utc)
            db.commit()

            registry_says_eu = match.country_code in _EU_EEA_COUNTRY_CODES
            page_says_eu = provider.eu_domicile_status == "eu_domiciled"
            page_says_non_eu = provider.eu_domicile_status == "non_eu_domiciled"

            if page_says_eu and not registry_says_eu:
                disagreements += 1
                print(
                    f"  {provider.slug}: DISAGREEMENT - page says eu_domiciled, "
                    f"{match.source} says {match.country_code} ({match.matched_name})"
                )
            elif page_says_non_eu and registry_says_eu:
                disagreements += 1
                print(
                    f"  {provider.slug}: DISAGREEMENT - page says non_eu_domiciled, "
                    f"{match.source} says {match.country_code} ({match.matched_name})"
                )
            else:
                agreements += 1
                print(f"  {provider.slug}: {match.source} confirms {match.country_code} ({match.matched_name})")

    print(
        f"\nDone. {checked} checked, {matched} matched, {agreements} consistent, "
        f"{disagreements} disagree with the page-scraped status."
    )


if __name__ == "__main__":
    main()
