"""CLI: idempotently sync the registry to the seed list in
app/tracker/seed_sources.py.

    python scripts/seed_sources.py
"""

from app.core.db import SessionLocal
from app.tracker.seed_sources import upsert_seed_registry


def main() -> None:
    with SessionLocal() as db:
        upsert_seed_registry(db)
    print("source registry synced")


if __name__ == "__main__":
    main()
