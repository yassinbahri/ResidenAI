"""CLI: check every due source and record any content changes as new
document versions.

    python scripts/run_checks.py

Run this on whatever schedule you like (cron, Windows Task Scheduler, a
manual run) - there is no Celery/queue here by design, since a few dozen
sources checked at most daily doesn't need one.
"""

from app.core.db import SessionLocal
from app.tracker.run import run_due_checks


def main() -> None:
    with SessionLocal() as db:
        outcomes = run_due_checks(db)

        if not outcomes:
            print("no sources were due")
            return

        for outcome in outcomes:
            source = outcome.source
            obs = outcome.observation
            change_note = " -> NEW VERSION" if outcome.new_document_version else ""
            detail = f": {obs.error_class} {obs.error_message}" if obs.status == "failed" else ""
            print(f"{source.source_key} ({source.canonical_url}): {obs.status}{change_note}{detail}")

        changed = sum(1 for o in outcomes if o.new_document_version is not None)
        failed = sum(1 for o in outcomes if o.observation.status == "failed")
        print(f"\n{len(outcomes)} checked, {changed} changed, {failed} failed")


if __name__ == "__main__":
    main()
