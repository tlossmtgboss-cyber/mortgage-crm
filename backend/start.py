#!/usr/bin/env python3
"""
Start script for Railway deployment.
Handles PORT environment variable properly and runs migrations first.
"""

import os
import subprocess
import sys

def cleanup_idle_connections():
    """Terminate idle database connections to prevent 'too many clients' errors.

    On Railway redeploys, previous deployment connections may linger.
    This cleanup runs BEFORE anything else to free up connection slots.
    """
    database_url = os.environ.get("DATABASE_URL", "")
    if not database_url or "sqlite" in database_url:
        return

    # Fix postgres:// to postgresql:// for psycopg2
    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql://", 1)

    try:
        import psycopg2
        conn = psycopg2.connect(database_url, connect_timeout=5)
        conn.autocommit = True
        cur = conn.cursor()

        # Check current connection count
        cur.execute("SELECT count(*) FROM pg_stat_activity WHERE datname = current_database()")
        total = cur.fetchone()[0]
        cur.execute("SHOW max_connections")
        max_conn = cur.fetchone()[0]
        print(f"START.PY: DB connections: {total}/{max_conn}", flush=True)

        # If connections are over 80% of max, aggressively clean up
        if total > int(max_conn) * 0.8:
            print(f"START.PY: Connection usage HIGH ({total}/{max_conn}) - terminating idle connections", flush=True)
            # First pass: terminate idle connections older than 5 seconds
            cur.execute("""
                SELECT pg_terminate_backend(pid)
                FROM pg_stat_activity
                WHERE datname = current_database()
                  AND pid != pg_backend_pid()
                  AND state = 'idle'
                  AND state_change < NOW() - INTERVAL '5 seconds'
            """)
            terminated = cur.rowcount
            print(f"START.PY: Terminated {terminated} idle connections (>5s)", flush=True)

            # Re-check
            cur.execute("SELECT count(*) FROM pg_stat_activity WHERE datname = current_database()")
            total = cur.fetchone()[0]

            # Second pass: if still over 80%, terminate ALL idle connections
            if total > int(max_conn) * 0.8:
                cur.execute("""
                    SELECT pg_terminate_backend(pid)
                    FROM pg_stat_activity
                    WHERE datname = current_database()
                      AND pid != pg_backend_pid()
                      AND state = 'idle'
                """)
                terminated2 = cur.rowcount
                print(f"START.PY: Terminated {terminated2} more idle connections", flush=True)

            # Third pass: if STILL over 90%, terminate idle-in-transaction too
            cur.execute("SELECT count(*) FROM pg_stat_activity WHERE datname = current_database()")
            total = cur.fetchone()[0]
            if total > int(max_conn) * 0.9:
                cur.execute("""
                    SELECT pg_terminate_backend(pid)
                    FROM pg_stat_activity
                    WHERE datname = current_database()
                      AND pid != pg_backend_pid()
                      AND state IN ('idle', 'idle in transaction')
                """)
                terminated3 = cur.rowcount
                print(f"START.PY: Terminated {terminated3} idle-in-transaction connections", flush=True)
        else:
            # Normal cleanup: just terminate long-idle connections
            cur.execute("""
                SELECT pg_terminate_backend(pid)
                FROM pg_stat_activity
                WHERE datname = current_database()
                  AND pid != pg_backend_pid()
                  AND state = 'idle'
                  AND state_change < NOW() - INTERVAL '30 seconds'
            """)
            terminated = cur.rowcount
            if terminated > 0:
                print(f"START.PY: Terminated {terminated} idle connections (>30s)", flush=True)

        # Final count
        cur.execute("SELECT count(*) FROM pg_stat_activity WHERE datname = current_database()")
        remaining = cur.fetchone()[0]
        print(f"START.PY: DB connections after cleanup: {remaining}/{max_conn}", flush=True)

        cur.close()
        conn.close()
    except Exception as e:
        print(f"START.PY: Connection cleanup warning: {e}", flush=True)

def _ensure_new_tables(database_url: str):
    """Verify that tables managed by Alembic migrations 014/015 exist.

    DDL was moved to Alembic migration 015_inline_ddl_consolidation.
    This function now only performs a startup health check — if any
    expected table is missing, it logs a warning directing operators
    to run ``alembic upgrade head``.
    """
    if not database_url or "sqlite" in database_url:
        return

    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql://", 1)

    import psycopg2
    conn = psycopg2.connect(database_url, connect_timeout=10)
    conn.autocommit = True
    cur = conn.cursor()

    expected_tables = (
        "client_files", "client_file_collaborators",
        "team_chat_channels", "team_chat_messages",
        "team_chat_reactions", "team_chat_reads",
        "audit_events", "ai_cost_records",
    )

    present = []
    missing = []
    for tbl in expected_tables:
        cur.execute(
            "SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = %s)",
            (tbl,),
        )
        if cur.fetchone()[0]:
            present.append(tbl)
        else:
            missing.append(tbl)

    if missing:
        print(
            f"START.PY: WARNING — missing tables: {', '.join(missing)}. "
            f"Run 'alembic upgrade head' to create them "
            f"(see migration 015_inline_ddl_consolidation).",
            flush=True,
        )
    else:
        print(f"START.PY: All {len(present)} expected tables verified.", flush=True)

    cur.close()
    conn.close()


def main():
    # Clean up stale database connections FIRST
    print("=" * 50, flush=True)
    print("START.PY: Cleaning up idle database connections...", flush=True)
    cleanup_idle_connections()

    # Run migrations first (with advisory lock to prevent concurrent execution across replicas)
    script_dir = os.path.dirname(os.path.abspath(__file__))
    print("=" * 50, flush=True)
    print("START.PY: Running migrations...", flush=True)

    database_url = os.environ.get("DATABASE_URL", "")
    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql://", 1)

    got_lock = False
    lock_conn = None
    try:
        if database_url and "sqlite" not in database_url:
            import psycopg2
            lock_conn = psycopg2.connect(database_url, connect_timeout=10)
            lock_conn.autocommit = True
            lock_cursor = lock_conn.cursor()
            lock_cursor.execute("SELECT pg_try_advisory_lock(728371)")
            got_lock = lock_cursor.fetchone()[0]
            lock_cursor.close()
            if not got_lock:
                print("START.PY: Another replica is running migrations, skipping...", flush=True)
        else:
            got_lock = True

        if got_lock:
            try:
                result = subprocess.run(
                    [sys.executable, os.path.join(script_dir, "run_migrations.py")],
                    check=False,
                    timeout=120
                )
                if result.returncode != 0:
                    print(f"START.PY: Migration exited with code {result.returncode} — continuing startup", flush=True)
            except subprocess.TimeoutExpired:
                print("START.PY: Migrations timed out after 120s — continuing startup", flush=True)
    except Exception as e:
        print(f"START.PY: Migration step failed ({e}) — continuing startup without migrations", flush=True)
    finally:
        if lock_conn:
            if got_lock:
                try:
                    release_cursor = lock_conn.cursor()
                    release_cursor.execute("SELECT pg_advisory_unlock(728371)")
                    release_cursor.close()
                except Exception:
                    pass
            try:
                lock_conn.close()
            except Exception:
                pass

    # Verify schema is at Alembic head revision
    print("=" * 50, flush=True)
    print("START.PY: Checking Alembic schema version...", flush=True)
    try:
        from alembic.config import Config as _AlembicConfig
        from alembic.runtime.migration import MigrationContext as _MigCtx
        from alembic.script import ScriptDirectory as _ScriptDir
        from sqlalchemy import create_engine as _create_engine

        _alembic_cfg = _AlembicConfig(os.path.join(script_dir, "alembic.ini"))
        _alembic_cfg.set_main_option(
            "script_location", os.path.join(script_dir, "alembic")
        )
        _script = _ScriptDir.from_config(_alembic_cfg)
        _head = _script.get_current_head()

        if database_url and "sqlite" not in database_url:
            _engine = _create_engine(database_url)
            with _engine.connect() as _conn:
                _current = _MigCtx.configure(_conn).get_current_revision()
            _engine.dispose()

            if _current == _head:
                print(f"START.PY: Schema at head ({_head})", flush=True)
            else:
                print(
                    f"START.PY: WARNING — schema at {_current!r}, "
                    f"head is {_head!r}. Run 'alembic upgrade head'.",
                    flush=True,
                )
    except Exception as e:
        print(f"START.PY: Schema version check warning: {e}", flush=True)

    # Verify tables from Alembic migrations 014/015 exist.
    # DDL is now managed exclusively by Alembic — this is just a health check.
    print("=" * 50, flush=True)
    print("START.PY: Verifying schema tables exist...", flush=True)
    try:
        _ensure_new_tables(database_url)
    except Exception as e:
        print(f"START.PY: Table verification warning: {e}", flush=True)

    # Backfill client_files from existing leads (idempotent — skips existing)
    print("START.PY: Backfilling client_files from leads...", flush=True)
    try:
        from migrations.backfill_client_files import backfill
        backfill()
        print("START.PY: Client file backfill complete", flush=True)
    except Exception as e:
        print(f"START.PY: Client file backfill warning: {e}", flush=True)

    # Run multi-tenant organization_id migration
    print("=" * 50, flush=True)
    print("START.PY: Running multi-tenant migration...", flush=True)
    try:
        from migrations.add_multi_tenant_organization_id import run_migration
        success = run_migration()
        if success:
            print("START.PY: Multi-tenant migration completed successfully!", flush=True)
        else:
            print("START.PY: Multi-tenant migration completed with warnings", flush=True)
    except Exception as e:
        print(f"START.PY: Multi-tenant migration error: {e}", flush=True)

    # Get port from environment or default to 8080
    port = os.environ.get("PORT", "8080")
    print(f"START.PY: PORT env var = {os.environ.get('PORT', 'NOT SET')}", flush=True)
    print(f"START.PY: Starting uvicorn on port {port}...", flush=True)
    print("=" * 50, flush=True)

    # Single worker — numReplicas=1 with pool_size=5 + max_overflow=1 = 6 connections.
    # Adding --workers would multiply connection usage beyond safe limits.
    os.execvp("uvicorn", [
        "uvicorn",
        "main:app",
        "--host", "0.0.0.0",
        "--port", port
    ])

ALLOWED_WORKERS = {"team_chat_bot", "voice_agent"}

if __name__ == "__main__":
    worker_mode = os.environ.get("WORKER_MODE", "")
    if worker_mode:
        if worker_mode not in ALLOWED_WORKERS:
            print(f"START.PY: ERROR: unknown WORKER_MODE={worker_mode!r}, "
                  f"allowed: {ALLOWED_WORKERS}", flush=True)
            sys.exit(1)
        print(f"START.PY: WORKER_MODE={worker_mode}", flush=True)
        if worker_mode == "voice_agent":
            script_dir = os.path.dirname(os.path.abspath(__file__))
            aria_dir = os.path.join(script_dir, "aria")
            os.chdir(aria_dir)
            os.execvp(sys.executable, [sys.executable, "voice_agent.py", "start"])
        else:
            os.execvp(sys.executable, [sys.executable, "-m", f"workers.{worker_mode}"])
    else:
        main()
