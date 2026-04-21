# 08 — Infrastructure

**Findings addressed:**
- Questionable decision: no PgBouncer despite comments saying otherwise
- Business q#11: 20 DB connection limit ≈ 15 concurrent users max
- Enterprise gap: no database backup verification

## Scope

1. **Connection pooling** — Supavisor (PgBouncer-compatible) in front of Postgres
2. **SQLAlchemy async engine config** — sized for pooler, not raw DB
3. **Health checks** — Railway health endpoint that actually exercises DB + Redis
4. **Backup verification** — nightly job that restores into scratch DB and asserts
5. **Connection-limit monitoring** — alerts before exhaustion

## 1. Add Supavisor (Railway)

Railway supports Supavisor natively. In the Postgres service settings:

1. Open the Postgres plugin in your Railway project.
2. Enable **Connection Pooler** (Supavisor). Railway provisions it automatically.
3. Copy the pooled URL — typically the same host with port `6543` and `?pgbouncer=true`.
4. Set a new env var `DATABASE_POOLED_URL` on the backend service.
5. Keep `DATABASE_URL` pointing at direct connection for migrations (Alembic needs session-mode, not transaction-mode).

## 2. App uses pooled URL for runtime, direct URL for migrations

See `db.py` — it reads `DATABASE_POOLED_URL` for the app engine and `DATABASE_URL` only for Alembic.

## 3. Pool sizing math

Supavisor gives you effectively unlimited logical connections. Real physical connection pool to Postgres is typically 15 on Railway Hobby / 40 on Pro.

SQLAlchemy pool per backend replica:
- `pool_size=20` (steady-state)
- `max_overflow=10` (burst)
- `pool_pre_ping=True` (catch stale conns from pooler)
- `pool_recycle=1800` (30 min, prevents idle drops)

With 3 backend replicas that's 90 logical conns via Supavisor → ~15 physical to Postgres. Fine on Hobby, great headroom on Pro.

## 4. Health checks

`/health` — liveness: just returns 200 if app is up.
`/health/ready` — readiness: exercises DB, Redis, and encryption. Railway readiness probe points here. If it fails, Railway stops routing traffic to that instance.

## 5. Backup verification

`backup-verify-nightly.sh` runs via Railway Cron (or GitHub Actions on schedule). It:
1. Triggers a fresh logical dump
2. Restores into an ephemeral scratch DB
3. Runs sanity queries (user count, loan count, latest audit event)
4. Tears down the scratch DB
5. Posts success/failure to Slack via webhook

If a dump can't restore cleanly, SOC 2 requires you to know within 24 hours.

## 6. Connection monitoring

`pg-connection-monitor.sql` runs every minute via Railway cron / pg_cron. Writes to a `connection_stats` table. Grafana dashboard alerts at 70% saturation.
