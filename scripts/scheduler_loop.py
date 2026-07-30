"""Long-running loop: check due sources every `scheduler_interval_seconds`,
forever. This is the "automatic checks" process - runs in its own container
(see docker/docker-compose.yml's `scheduler` service), not on anyone's local
machine, and not tied to the API process being up.

No Celery/Redis: at this scale (dozens of sources, checked at most daily)
a sleep loop is simpler to operate and easier to reason about than a task
queue, and it's still fully containerized/restart-safe under Docker.
"""

import logging
import time
from datetime import datetime, timezone

from sqlalchemy import select

from app.core.config import get_settings
from app.core.db import SessionLocal
from app.models.source import Source
from app.tracker.run import freshness_state, run_due_checks

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("scheduler")


def _log_staleness_summary(db) -> None:
    """One line of visibility into source freshness per run - no
    Prometheus/Grafana needed at this scale, just something that shows up
    in `docker compose logs scheduler` without having to open the frontend."""
    now = datetime.now(timezone.utc)
    sources = db.execute(select(Source).where(Source.enabled.is_(True))).scalars().all()
    counts: dict[str, int] = {}
    for source in sources:
        state = freshness_state(source, now)
        counts[state] = counts.get(state, 0) + 1
    stale = counts.get("stale", 0)
    blocked = counts.get("blocked", 0)
    if stale or blocked:
        logger.warning(
            "staleness: %d enabled source(s), %d stale, %d blocked (of %d total)",
            len(sources),
            stale,
            blocked,
            len(sources),
        )
    else:
        logger.info("staleness: %d enabled source(s), none stale or blocked", len(sources))


def run_once() -> None:
    with SessionLocal() as db:
        outcomes = run_due_checks(db)
        _log_staleness_summary(db)
    if not outcomes:
        logger.info("no sources were due")
        return
    changed = sum(1 for o in outcomes if o.new_document_version is not None)
    failed = sum(1 for o in outcomes if o.observation.status == "failed")
    logger.info("checked=%d changed=%d failed=%d", len(outcomes), changed, failed)
    for outcome in outcomes:
        if outcome.observation.status == "failed":
            logger.warning(
                "%s failed: %s %s",
                outcome.source.source_key,
                outcome.observation.error_class,
                outcome.observation.error_message,
            )
        elif outcome.new_document_version is not None:
            logger.info("%s changed -> new document version", outcome.source.source_key)


def main() -> None:
    interval = get_settings().scheduler_interval_seconds
    logger.info("scheduler starting, interval=%ds", interval)
    while True:
        try:
            run_once()
        except Exception:
            logger.exception("scheduler tick failed")
        time.sleep(interval)


if __name__ == "__main__":
    main()
