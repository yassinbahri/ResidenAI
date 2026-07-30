"""CLI: recompute every product's EU/EEA residency status and every
provider's EU domicile status from whatever content is already captured,
without waiting for the next scheduled check.

    python scripts/reevaluate_residency.py

Useful right after seeding new sources, or after a change to
app/tracker/residency_classifier.py's or domicile_classifier.py's patterns -
ongoing checks already trigger this automatically when a source's content
changes.
"""

from app.core.db import SessionLocal
from app.tracker.run import reevaluate_all_products


def main() -> None:
    with SessionLocal() as db:
        count = reevaluate_all_products(db)
    print(f"re-evaluated {count} product(s) and their providers' domicile status")


if __name__ == "__main__":
    main()
