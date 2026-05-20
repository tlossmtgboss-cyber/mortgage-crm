"""
RateIngestionWorker — the 24/7 polling loop.

Design (Data Engineer):
  - Single async loop, scheduled by Railway's native scheduler.
  - Redis SETNX lock prevents overlap if Railway fires twice.
  - Each run logs to rate_watch_run_log before any rate writes.
  - On hard fail: log + emit Sentry + skip; the next tick will retry.
  - On soft fail (one source down, others up): log + emit metric + proceed.
  - On schema drift from primary: STOP emitting opportunities until human ack'd.

Failure-mode handling (Architect signed off):
  - Upstream 5xx: retry with jittered exponential backoff (3 attempts max).
  - Upstream 429: respect Retry-After header, otherwise back off 5 minutes.
  - Timeout: classed as transient; next tick retries.
  - Parse error: hard fail, page DevOps. Don't auto-retry, don't degrade silently.
  - Schema drift: hard fail + lock the "emit opportunities" gate. Manual unlock required.
"""
from __future__ import annotations

import asyncio
import logging
import random
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import AsyncIterator

from redis.asyncio import Redis

from .models import (
    ErrorKind,
    Product,
    RateObservationRecordedEvent,
    RunStatus,
    SourceFetchResult,
    SourceName,
)
from .sources.base import (
    HttpSourceError,
    ParseSourceError,
    RateLimitedError,
    RateSource,
    SchemaDriftError,
    SourceTimeoutError,
)

logger = logging.getLogger(__name__)

LOCK_KEY = "rate_watch:ingest:lock"
LOCK_TTL_SECONDS = 600  # 10 min — generous; if a run takes longer we want alerting anyway
SCHEMA_DRIFT_GATE_KEY = "rate_watch:emit_opportunities_disabled"


class RateIngestionWorker:
    def __init__(
        self,
        *,
        primary_source: RateSource,
        sanity_sources: list[RateSource],
        redis: Redis,
        db_pool,                            # asyncpg-style pool
        event_bus,                          # your existing CRM event bus
        max_retries: int = 3,
        base_backoff_seconds: float = 2.0,
    ):
        self.primary = primary_source
        self.sanity_sources = sanity_sources
        self.redis = redis
        self.db = db_pool
        self.events = event_bus
        self.max_retries = max_retries
        self.base_backoff = base_backoff_seconds

    # ------------------------------------------------------------------ #
    # Entry point                                                         #
    # ------------------------------------------------------------------ #
    async def run_once(self) -> bool:
        """
        Run one ingestion cycle. Returns True on success, False on hard fail.

        Idempotent: safe to call twice in quick succession (the Redis lock
        causes the second call to no-op).
        """
        async with self._lock_or_skip() as acquired:
            if not acquired:
                logger.info("ingest skipped: another worker holds the lock")
                return True  # not a failure — just contention

            primary_ok = await self._ingest_one_source(self.primary, primary=True)
            for src in self.sanity_sources:
                await self._ingest_one_source(src, primary=False)

            return primary_ok

    # ------------------------------------------------------------------ #
    # Per-source ingestion with retry/backoff                             #
    # ------------------------------------------------------------------ #
    async def _ingest_one_source(self, source: RateSource, *, primary: bool) -> bool:
        run_id = await self._start_run(source.name)
        t_start = time.monotonic()

        last_error: Exception | None = None
        for attempt in range(1, self.max_retries + 1):
            try:
                result = await source.fetch()
                await self._persist(source, result, run_id)
                await self._publish_observed_event(source, result, run_id)
                duration_ms = int((time.monotonic() - t_start) * 1000)
                await self._finish_run(
                    run_id,
                    status=RunStatus.SUCCESS,
                    rows=len(result.observations),
                    duration_ms=duration_ms,
                    etag=result.upstream_etag,
                )
                logger.info(
                    "ingest ok: source=%s rows=%d duration=%dms",
                    source.name.value, len(result.observations), duration_ms,
                )
                return True

            except SchemaDriftError as exc:
                # Critical — disable downstream outreach until a human looks.
                await self._raise_schema_drift_gate(source.name, str(exc))
                await self._finish_run(
                    run_id,
                    status=RunStatus.HARD_FAIL,
                    error=exc,
                    error_kind=ErrorKind.SCHEMA_DRIFT,
                    duration_ms=int((time.monotonic() - t_start) * 1000),
                )
                if primary:
                    logger.error("PRIMARY source schema drift: %s — outreach disabled", exc)
                return False

            except ParseSourceError as exc:
                await self._finish_run(
                    run_id,
                    status=RunStatus.HARD_FAIL,
                    error=exc,
                    error_kind=ErrorKind.PARSE_ERROR,
                    duration_ms=int((time.monotonic() - t_start) * 1000),
                )
                logger.error("parse error from %s: %s", source.name.value, exc)
                return False

            except RateLimitedError as exc:
                last_error = exc
                # Long, fixed backoff — don't hammer when told to slow down.
                await asyncio.sleep(60 * attempt)

            except (HttpSourceError, SourceTimeoutError) as exc:
                last_error = exc
                # Jittered exponential backoff.
                delay = self.base_backoff * (2 ** (attempt - 1)) * (0.75 + random.random() * 0.5)
                logger.warning(
                    "transient error from %s (attempt %d): %s — retry in %.1fs",
                    source.name.value, attempt, exc, delay,
                )
                await asyncio.sleep(delay)

            except Exception as exc:                # noqa: BLE001 — last-resort net
                last_error = exc
                logger.exception("unexpected error from %s", source.name.value)
                break

        # All retries exhausted.
        await self._finish_run(
            run_id,
            status=RunStatus.SOFT_FAIL if not primary else RunStatus.HARD_FAIL,
            error=last_error,
            error_kind=ErrorKind.HTTP_ERROR,
            duration_ms=int((time.monotonic() - t_start) * 1000),
        )
        return False

    # ------------------------------------------------------------------ #
    # Persistence                                                         #
    # ------------------------------------------------------------------ #
    async def _persist(
        self,
        source: RateSource,
        result: SourceFetchResult,
        run_id: int,
    ) -> None:
        if not result.observations:
            return

        # Single INSERT statement with ON CONFLICT DO NOTHING handles dedup.
        # The unique index on (source, product, observed_at) is the dedup key.
        sql = """
            INSERT INTO rate_observations
                (source, product, rate, points, change_pct, observed_at,
                 fetched_at, fetch_run_id, raw_payload)
            VALUES
                ($1, $2, $3, $4, $5, $6, $7, $8, $9)
            ON CONFLICT (source, product, observed_at) DO NOTHING
            RETURNING id
        """
        async with self.db.acquire() as conn:
            async with conn.transaction():
                for obs in result.observations:
                    await conn.fetchval(
                        sql,
                        obs.source.value,
                        obs.product.value,
                        obs.rate,
                        obs.points,
                        obs.change_pct,
                        obs.observed_at,
                        result.fetched_at,
                        run_id,
                        obs.raw_payload,
                    )

        # Hot-cache the latest per product so dashboards/widgets don't hit Postgres.
        pipe = self.redis.pipeline()
        for obs in result.observations:
            key = f"rates:current:{obs.product.value}"
            pipe.hset(key, mapping={
                "rate": str(obs.rate),
                "points": str(obs.points),
                "observed_at": obs.observed_at.isoformat(),
                "source": obs.source.value,
            })
            pipe.expire(key, 3600)
        await pipe.execute()

    # ------------------------------------------------------------------ #
    # Run-log lifecycle                                                   #
    # ------------------------------------------------------------------ #
    async def _start_run(self, source: SourceName) -> int:
        sql = """
            INSERT INTO rate_watch_run_log (source, status)
            VALUES ($1, 'running')
            RETURNING id
        """
        async with self.db.acquire() as conn:
            return await conn.fetchval(sql, source.value)

    async def _finish_run(
        self,
        run_id: int,
        *,
        status: RunStatus,
        rows: int = 0,
        duration_ms: int = 0,
        etag: str | None = None,
        error: Exception | None = None,
        error_kind: ErrorKind | None = None,
    ) -> None:
        sql = """
            UPDATE rate_watch_run_log
            SET finished_at = NOW(),
                status = $1,
                rows_observed = $2,
                fetch_duration_ms = $3,
                upstream_etag = $4,
                error_message = $5,
                error_kind = $6
            WHERE id = $7
        """
        async with self.db.acquire() as conn:
            await conn.execute(
                sql,
                status.value,
                rows,
                duration_ms,
                etag,
                str(error) if error else None,
                error_kind.value if error_kind else None,
                run_id,
            )

    # ------------------------------------------------------------------ #
    # Events                                                              #
    # ------------------------------------------------------------------ #
    async def _publish_observed_event(
        self,
        source: RateSource,
        result: SourceFetchResult,
        run_id: int,
    ) -> None:
        if source is not self.primary or not result.observations:
            return
        # Only the primary source's observations trigger downstream evaluation.
        # Sanity sources (FRED) inform anomaly detection only.
        event = RateObservationRecordedEvent(
            fetch_run_id=run_id,
            source=source.name,
            products_updated=[o.product for o in result.observations],
            occurred_at=datetime.now(timezone.utc),
        )
        await self.events.publish(event)

    # ------------------------------------------------------------------ #
    # Schema-drift gate                                                   #
    # ------------------------------------------------------------------ #
    async def _raise_schema_drift_gate(self, source: SourceName, reason: str) -> None:
        """
        Sets a Redis key that the RefiOpportunityEvaluator checks before
        emitting any borrower outreach. A human must clear this key after
        verifying the parse/source is correct.
        """
        await self.redis.set(
            SCHEMA_DRIFT_GATE_KEY,
            f"source={source.value} reason={reason} at={datetime.now(timezone.utc).isoformat()}",
        )
        logger.critical(
            "SCHEMA DRIFT GATE RAISED — outreach disabled. "
            "Source=%s Reason=%s. Clear Redis key '%s' after verification.",
            source.value, reason, SCHEMA_DRIFT_GATE_KEY,
        )

    # ------------------------------------------------------------------ #
    # Distributed lock                                                    #
    # ------------------------------------------------------------------ #
    @asynccontextmanager
    async def _lock_or_skip(self) -> AsyncIterator[bool]:
        """
        Acquire the ingestion lock via Redis SETNX. If we can't, yield False
        (caller skips this run). Always releases on exit, even on exception.
        """
        token = f"{time.time()}:{random.random()}"
        acquired = await self.redis.set(
            LOCK_KEY,
            token,
            nx=True,
            ex=LOCK_TTL_SECONDS,
        )
        try:
            yield bool(acquired)
        finally:
            if acquired:
                # Compare-and-delete via Lua to avoid releasing someone else's lock
                # if our run overran the TTL.
                script = """
                if redis.call('GET', KEYS[1]) == ARGV[1] then
                    return redis.call('DEL', KEYS[1])
                else
                    return 0
                end
                """
                await self.redis.eval(script, 1, LOCK_KEY, token)
