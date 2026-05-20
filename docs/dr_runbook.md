# Disaster Recovery (DR) Runbook — Perennia AI

> **Scope** — PostgreSQL on Railway (primary data store), file storage
> (Railway volume / S3-backed object store), and the FastAPI control
> plane. Frontend (Vercel) and landing page (Vercel) are stateless and
> rebuild from `git` automatically.

## Recovery Objectives

| Objective | Target | Mechanism |
|-----------|--------|-----------|
| **RPO** (max data loss) | **1 hour** | Continuous WAL archiving + hourly logical backups |
| **RTO** (max downtime) | **4 hours** | Documented restore procedure + quarterly drill |
| **Backup retention** | 35 days rolling + monthly snapshots for 7 years (SOC 2 financial controls) | Railway managed backups + off-platform archive |

## Drill Cadence

DR drills are run **quarterly** (Mar/Jun/Sep/Dec) and **before any major
release**. Each drill must:

1. Exercise the full backup → drop → restore → verify loop.
2. Measure the wall-clock RTO.
3. Confirm row-count parity across every table.
4. File a JSON report in `dr_drills/<UTC_timestamp>.json`.
5. Be reviewed by the on-call engineer and recorded in the SOC 2
   evidence binder.

The automated driver is `backend/scripts/dr_drill.py`:

```bash
# CI-safe (SQLite). Always runs as part of the integration suite.
python3 -m backend.scripts.dr_drill --target sqlite --report-dir dr_drills/

# Production-shaped against a real Postgres instance.
TEST_DATABASE_URL="postgresql://..." \
  python3 -m backend.scripts.dr_drill --target postgres --report-dir dr_drills/
```

A non-zero exit code MUST page the on-call engineer.

## Manual DR Procedure

If the automated tooling is unavailable, follow this procedure.

### 1. Declare incident and freeze writes

1. Trigger PagerDuty incident `DR-RESTORE`.
2. Put the API in maintenance mode (Railway dashboard → environment
   variable `MAINTENANCE_MODE=1` and redeploy).
3. Notify customers via status page.

### 2. Identify recovery point

1. Decide between **PITR** (point-in-time recovery via WAL) and
   **snapshot** restore.
2. The chosen recovery target must satisfy the 1-hour RPO. Confirm the
   most recent backup timestamp from Railway → Backups.

### 3. Restore the database

```bash
# 1) Provision a fresh Postgres instance.
railway up --service postgres --env recovery

# 2) Restore the most recent base backup.
pg_restore --no-owner --no-acl -d "$RECOVERY_DATABASE_URL" backup.dump

# 3) Replay WAL up to the chosen recovery target time.
#    (Railway exposes this as `restore_target_time` in the dashboard.)
```

### 4. Verify integrity

1. Row-count parity vs. last known-good snapshot — use the queries in
   `backend/scripts/dr_drill.py`.
2. Application smoke tests — `python3 -m pytest backend/tests/smoke -q`.
3. Audit chain integrity — call `loan_state_audit_service.verify_chain()`
   on a representative sample of loans.

### 5. Cut over

1. Point `DATABASE_URL` at the recovered instance.
2. Remove maintenance mode.
3. Watch error rates for the next 60 minutes.
4. Post-incident review within 72 hours.

## Audit-table Special Handling

The audit tables (`loan_state_change_audit`, `audit_events`,
`consent_audit_log`, etc.) are protected by the
`audit_immutability_guard()` trigger. After a restore, the trigger must
exist — `alembic upgrade head` will reinstall it if missing.

Each row in `loan_state_change_audit` carries a SHA-256 hash chain
(`prev_hash`, `entry_hash`). After restore, run:

```python
from services.loan_state_audit_service import verify_chain
for loan_id in sample_loans:
    assert verify_chain(db, loan_id), f"Chain broken for {loan_id}"
```

Any failure indicates either tampering or an incomplete restore.

## References

* `backend/scripts/dr_drill.py` — automated drill driver.
* `backend/alembic/versions/2026_05_19_audit_immutability.py` — DB-level
  immutability + hash chain migration.
* `backend/services/loan_state_audit_service.py` — `verify_chain()`.
