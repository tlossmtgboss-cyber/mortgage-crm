"""
Rate Watch worker entrypoint — FREE-TIER PRODUCTION CONFIG.

Modes:
  python -m app.workers.rate_watch_worker            # forever
  python -m app.workers.rate_watch_worker --once     # single cycle (Railway cron)

Default cadence: every 60 minutes is plenty. The PMMS anchor only refreshes
weekly on Thursday at 12pm ET; DGS10 refreshes daily after market close
(~5pm ET on business days). Polling more often costs API calls for no signal.

Source configuration:
  - PRIMARY: fred_composite (production)
  - SANITY:  none on free tier (composite covers everything)
  - DEV ONLY: mnd_html (manual invocation in staging for parser regression tests)

Required env:
  - DATABASE_URL          (Postgres connection string)
  - REDIS_URL             (Redis connection string)
  - FRED_API_KEY          (FREE — get at https://fred.stlouisfed.org/docs/api/api_key.html)

Optional env:
  - RATE_WATCH_PRIMARY_SOURCE         (default: fred_composite)
  - RATE_WATCH_POLL_INTERVAL_SECONDS  (default: 3600 = 1h)
  - RATE_WATCH_USER_AGENT             (used by all HTTP sources)
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys

import asyncpg
from redis.asyncio import Redis

from services.rate_watch.evaluator import RefiOpportunityEvaluator
from services.rate_watch.ingestion import RateIngestionWorker
from services.rate_watch.models import SourceName
from services.rate_watch.sources.base import RateSource, SourceConfig
from services.rate_watch.sources.fred_composite import FredCompositeSource
from services.rate_watch.sources.mnd_html import MNDHtmlSource

# Event bus — stub until Aria event bus is wired
class _StubBus:
    async def publish(self, event):
        logging.getLogger("rate_watch.events").info("event: %s", event)
event_bus = _StubBus()

# TCPA checker — stub until compliance module is wired
from types import SimpleNamespace
class _StubTcpa:
    async def check_consent(self, borrower_id):
        return SimpleNamespace(granted=True, consent_id=None)
    async def quiet_hours_ok(self, borrower_id):
        return True
tcpa_checker = _StubTcpa()

logger = logging.getLogger(__name__)


# Production source registry — fred_composite is the only blessed primary.
SOURCE_REGISTRY: dict[str, type[RateSource]] = {
    "fred_composite": FredCompositeSource,
    "mnd_html": MNDHtmlSource,             # dev-only, see DEV_ONLY_SOURCES
}

ALLOWED_PRIMARY_SOURCES = {"fred_composite"}
DEV_ONLY_SOURCES = {"mnd_html"}


def _build_source(name: str) -> RateSource:
    if name not in SOURCE_REGISTRY:
        raise ValueError(f"unknown source: {name}. registered: {list(SOURCE_REGISTRY)}")

    cls = SOURCE_REGISTRY[name]
    config = SourceConfig(
        name=SourceName(name) if name in {s.value for s in SourceName} else SourceName.FRED,
        user_agent=os.getenv(
            "RATE_WATCH_USER_AGENT",
            "PerenniaAI-RateWatch/1.0 (+https://perennia.ai; ops@perennia.ai)",
        ),
        timeout_seconds=float(os.getenv("RATE_WATCH_TIMEOUT_SECONDS", "20")),
        max_retries=int(os.getenv("RATE_WATCH_MAX_RETRIES", "3")),
        base_backoff_seconds=float(os.getenv("RATE_WATCH_BASE_BACKOFF", "2.0")),
        api_key=os.getenv(f"{name.upper()}_API_KEY") or os.getenv("FRED_API_KEY"),
        endpoint=os.getenv(f"{name.upper()}_ENDPOINT"),
    )
    return cls(config)


def _validate_primary(name: str) -> None:
    if name in DEV_ONLY_SOURCES:
        if os.getenv("RATE_WATCH_ALLOW_DEV_SOURCE_AS_PRIMARY") != "i-understand-the-risks":
            raise RuntimeError(
                f"Source '{name}' is dev-only and cannot be used as primary in production. "
                "If you're certain (and you should not be), set "
                "RATE_WATCH_ALLOW_DEV_SOURCE_AS_PRIMARY=i-understand-the-risks. "
                "The team strongly recommends using 'fred_composite' instead."
            )
    elif name not in ALLOWED_PRIMARY_SOURCES:
        raise RuntimeError(
            f"Source '{name}' is not in the allow-list of production primaries: "
            f"{ALLOWED_PRIMARY_SOURCES}"
        )


async def _build_worker_and_evaluator():
    db_url = os.environ["DATABASE_URL"]
    redis_url = os.environ["REDIS_URL"]

    db_pool = await asyncpg.create_pool(db_url, min_size=1, max_size=5)
    redis = Redis.from_url(redis_url, decode_responses=True)

    primary_name = os.getenv("RATE_WATCH_PRIMARY_SOURCE", "fred_composite")
    _validate_primary(primary_name)

    sanity_names_raw = os.getenv("RATE_WATCH_SANITY_SOURCES", "").strip()
    sanity_names = [
        s.strip() for s in sanity_names_raw.split(",")
        if s.strip() and s.strip() != primary_name
    ]

    primary = _build_source(primary_name)
    sanity = [_build_source(n) for n in sanity_names]

    logger.info(
        "rate-watch worker starting: primary=%s sanity=%s",
        primary_name, sanity_names or "(none)",
    )

    worker = RateIngestionWorker(
        primary_source=primary,
        sanity_sources=sanity,
        redis=redis,
        db_pool=db_pool,
        event_bus=event_bus,
    )
    evaluator = RefiOpportunityEvaluator(
        db_pool=db_pool,
        redis=redis,
        event_bus=event_bus,
        tcpa_checker=tcpa_checker,
    )
    return worker, evaluator, db_pool, redis


async def run_once() -> int:
    worker, evaluator, db_pool, redis = await _build_worker_and_evaluator()
    try:
        ok = await worker.run_once()
        if ok:
            opportunities = await evaluator.evaluate_book()
            logger.info("evaluator created %d opportunities", len(opportunities))
        return 0 if ok else 1
    finally:
        await db_pool.close()
        await redis.aclose()


async def run_forever() -> int:
    worker, evaluator, db_pool, redis = await _build_worker_and_evaluator()
    interval = int(os.getenv("RATE_WATCH_POLL_INTERVAL_SECONDS", "3600"))
    try:
        while True:
            try:
                ok = await worker.run_once()
                if ok:
                    await evaluator.evaluate_book()
            except Exception:                       # noqa: BLE001 — keep the loop alive
                logger.exception("ingest cycle failed; sleeping then retrying")
            await asyncio.sleep(interval)
    finally:
        await db_pool.close()
        await redis.aclose()


def main() -> int:
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true", help="Single ingest cycle then exit")
    args = parser.parse_args()
    return asyncio.run(run_once() if args.once else run_forever())


if __name__ == "__main__":
    sys.exit(main())
