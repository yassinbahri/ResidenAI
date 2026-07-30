"""CLI: onboard a brand-new provider automatically - no manual source
research required for the common case.

    python scripts/onboard_provider.py <slug> "<Display Name>" <website_url>

Attempts automatic discovery of a privacy/security documentation source by
scanning the homepage's own links (app/tracker/discovery.py). If that
fails, the provider is still created (visible in the tracker) with a
disabled placeholder source - check the frontend for providers needing a
source added by hand, rather than assuming every company onboards cleanly.
"""

import sys

from app.core.db import SessionLocal
from app.tracker.onboarding import onboard_new_provider


def main() -> None:
    if len(sys.argv) != 4:
        print("usage: onboard_provider.py <slug> <display_name> <website_url>", file=sys.stderr)
        raise SystemExit(1)

    slug, display_name, website_url = sys.argv[1], sys.argv[2], sys.argv[3]

    with SessionLocal() as db:
        result = onboard_new_provider(db, slug=slug, display_name=display_name, website_url=website_url)

    if result.already_existed:
        print(f"'{slug}' already exists - nothing to do")
        return

    if result.source_auto_discovered:
        print(f"onboarded '{display_name}' - auto-discovered privacy source: {result.discovered_url}")
    else:
        print(
            f"onboarded '{display_name}' - could NOT auto-discover a privacy source. "
            f"Created with a disabled placeholder pointing at {website_url}; "
            "add a real source manually via the frontend or seed_sources.py."
        )

    if result.company_info_source_auto_discovered:
        confidence_note = "" if result.company_info_source_confident else " (weak candidate, not domicile-authoritative - verify by hand)"
        print(f"  auto-discovered company-info source: {result.discovered_company_info_url}{confidence_note}")
    else:
        print("  could NOT auto-discover a company-info/imprint source - add one manually if needed.")


if __name__ == "__main__":
    main()
