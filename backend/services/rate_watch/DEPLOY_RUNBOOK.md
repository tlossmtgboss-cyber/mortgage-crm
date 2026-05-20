# Rate Watch — Free-Tier Deployment Runbook

**Owner:** DevOps + Data Engineer
**Last reviewed:** 2026-05-17
**Audience:** Tim, and any future engineer touching this system

---

## What this system does (one line)

Polls free public mortgage-rate data daily, computes your Perennia rate
(market − margin), scans loans under management against per-borrower
target rates, and emits `refi.opportunity.detected` events to the existing
Aria + Smart Calendar pipeline when a target is hit.

---

## What it costs to run

| Item | Cost |
|---|---|
| FRED API key | $0 (free registration) |
| Railway compute (worker, hourly cron) | ~$1–3/mo (within existing plan) |
| Postgres rows | negligible (~24 KB/year of rate observations) |
| Redis keys | 8 hot-cache keys, ~1 KB |
| Total marginal cost | **$0** |

---

## Pre-deploy checklist

- [ ] Get a FREE FRED API key
      → https://fred.stlouisfed.org/docs/api/api_key.html
      → ~60 seconds, no credit card, just an email
- [ ] Add `FRED_API_KEY=<your-key>` to Railway env vars (project secrets)
- [ ] Run migration `20260517_01_rate_watch.sql` on staging Postgres
- [ ] Verify migration: `\dt rate_*` and `\dt borrower_target_rates` show tables
- [ ] Confirm `current_rates` view exists: `SELECT * FROM current_rates;`
      (will return 0 rows until first ingest — that's fine)
- [ ] Backfill `rate_margins` if migration's seed insert was skipped
- [ ] Confirm existing Aria event bus has a handler subscribed to
      `refi.opportunity.detected` (or stub one for the first deploy)
- [ ] Confirm `tcpa_checker` module is importable in your repo

## Deploy sequence

```bash
# 1. Apply migration on staging first.
psql "$STAGING_DATABASE_URL" -f backend/app/db/migrations/20260517_01_rate_watch.sql

# 2. Deploy the new worker code to Railway.
git push railway main   # or your normal deploy path

# 3. Smoke test ONCE in staging, watching logs.
railway run --service rate-watch-worker python -m app.workers.rate_watch_worker --once

# Expected log lines:
#   rate-watch worker starting: primary=fred_composite sanity=(none)
#   ingest ok: source=fred rows=6 duration=<N>ms
#   evaluator pass complete: 0 opportunities created   # 0 is fine on first run

# 4. Verify rates landed in Postgres:
psql "$STAGING_DATABASE_URL" -c "SELECT product, market_rate, perennia_rate FROM current_rates;"

# Expected output (numbers will differ — these are illustrative):
#    product       | market_rate | perennia_rate
#   --------------+-------------+----------------
#    15_fixed     |     5.8205  |        5.5705
#    30_fha       |     6.0100  |        5.7600
#    30_fixed     |     6.4900  |        6.2400
#    30_jumbo     |     6.5300  |        6.2800
#    30_va        |     6.0300  |        5.7800
#    7_6_sofr_arm |     6.3300  |        6.0800

# 5. Repeat on production.
psql "$PROD_DATABASE_URL" -f backend/app/db/migrations/20260517_01_rate_watch.sql
railway run --service rate-watch-worker python -m app.workers.rate_watch_worker --once

# 6. Enable Railway scheduled job:
#    Service: rate-watch-worker
#    Schedule: "0 * * * *"   (top of every hour)
#    Command:  python -m app.workers.rate_watch_worker --once
```

## Verification (post-deploy)

Within 1 hour after enabling the cron:

```sql
-- Should show a SUCCESS row in the last hour
SELECT * FROM rate_watch_run_log
ORDER BY started_at DESC LIMIT 5;

-- Should show 6 rows, all from source='fred', observed_at within last 24h
SELECT product, source, rate, observed_at
FROM rate_observations
WHERE observed_at > NOW() - INTERVAL '24 hours'
ORDER BY product;
```

Within 24 hours: spot-check that the 30-yr-fixed market_rate on `current_rates`
agrees with [Freddie Mac PMMS](https://www.freddiemac.com/pmms) to within
~15 bps (the Treasury-model adjustment between Thursdays).

## Monitoring + alerting

Wire these into your existing Sentry / monitoring:

| Metric | Threshold | Severity | Action |
|---|---|---|---|
| `rate_watch_run_log.status='hard_fail'` in last hour | any | High | Page DevOps |
| No `status='success'` run in last 2 hours | true | High | Page DevOps |
| Redis key `rate_watch:emit_opportunities_disabled` present | true | Critical | Page on-call; verify parser, then `POST /api/rate-watch/admin/clear-drift-gate` |
| 30-yr `perennia_rate` < 2.0% OR > 12% on `current_rates` | true | High | Page on-call; likely parse bug |
| `refi_opportunities` insert rate > 50/hour | true | Medium | Investigate; possibly a stuck pipeline replay |

## Rollback procedure

If anything's wrong:

1. **Pause the cron in Railway** (does not delete data, just stops new ingests).
2. **Block outreach** by setting the schema-drift gate manually:
   ```bash
   redis-cli SET rate_watch:emit_opportunities_disabled "manual:rollback:$(date)"
   ```
   This stops the evaluator from emitting new `refi.opportunity.detected` events
   immediately. Existing in-flight opportunities are unaffected (they're already
   queued through Aria).
3. **Revert the deploy** if needed.
4. **No data deletion is required** — `rate_observations` is append-only and
   safe to keep even if you roll back the worker.

The `current_rates` view goes stale automatically (latest observation just gets
older). No corrupting state to clean up.

## Decision criteria

- LOs calling borrowers with rates that don't match BytePro pricing → expected,
  but if differences > 25 bps consistently for one product, recalibrate that
  product's spread in `DEFAULT_DERIVED_SPREADS_BPS` (or have the LO set an
  override via `POST /api/rate-watch/margins`).
- 30-yr rates moving > 50 bps in one fetch cycle → investigate; usually means
  PMMS just refreshed (Thursday) so re-anchoring caused the jump.
- DGS10 missing observation for a given day → fine; the source falls back to
  the previous business day automatically.

## Upgrade path (when you can pay for data later)

When you sign with Optimal Blue (or Polly, or another licensed feed):

1. Implement `OptimalBlueSource.fetch()` per the docstring in
   `sources/optimal_blue.py`.
2. Add `optimal_blue` to `ALLOWED_PRIMARY_SOURCES` in the worker.
3. Set `RATE_WATCH_PRIMARY_SOURCE=optimal_blue` in prod env.
4. Set `RATE_WATCH_SANITY_SOURCES=fred_composite` — keep FRED running in
   parallel as the cross-check.
5. Bump `RATE_WATCH_POLL_INTERVAL_SECONDS` down to 900 (15 min) to take
   advantage of intraday data.
6. Redeploy. No schema migration, no code changes elsewhere. The whole
   downstream pipeline picks up the better data automatically.

That's the payoff for the source-abstraction work — you don't redesign the
system to upgrade the data; you swap a config value.

## Incident contacts

- DevOps lead: Tim
- Security: Tim
- Data Engineer: Tim
- (Yes, all of these are Tim — solo founder. The system is built so the
  hot paths self-heal and the dangerous paths fail closed. If anything
  pages you at 3am, it's the schema-drift gate, and clearing it is a
  ~5-minute investigation: spot-check the current FRED values vs your
  ingest, decide if the parser is right, clear the Redis key via the
  admin endpoint or `redis-cli DEL`.)
