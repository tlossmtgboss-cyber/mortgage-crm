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
            # Advisory lock key 728371 — arbitrary but unique to migrations
            lock_cursor.execute("SELECT pg_try_advisory_lock(728371)")
            got_lock = lock_cursor.fetchone()[0]
            lock_cursor.close()
            if not got_lock:
                print("START.PY: Another replica is running migrations, skipping...", flush=True)
        else:
            got_lock = True  # SQLite — no concurrency concern

        if got_lock:
            try:
                result = subprocess.run(
                    [sys.executable, os.path.join(script_dir, "run_migrations.py")],
                    check=False,
                    timeout=120  # 2 minute timeout — don't let migrations block startup
                )
                if result.returncode != 0:
                    print(f"FATAL: Migration failed with exit code {result.returncode}", flush=True)
                    sys.exit(1)
            except subprocess.TimeoutExpired:
                print("FATAL: Migrations timed out after 120s", flush=True)
                sys.exit(1)
    finally:
        if lock_conn:
            if got_lock:
                try:
                    release_cursor = lock_conn.cursor()
                    release_cursor.execute("SELECT pg_advisory_unlock(728371)")
                    release_cursor.close()
                except Exception:
                    pass
            lock_conn.close()

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

    # Start uvicorn — single worker per replica is intentional.
    # With numReplicas=2 in railway.toml and pool_size=2 + max_overflow=5 = 7 per process,
    # 2 replicas × 1 worker × 7 = 14 connections, leaving headroom within Railway's ~20 limit.
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
            os.chdir(script_dir)
            env = os.environ.copy()
            env["PYTHONPATH"] = script_dir + os.pathsep + env.get("PYTHONPATH", "")
            os.execvpe(sys.executable, [sys.executable, "-m", "aria.voice_agent", "start"], env)
        else:
            os.execvp(sys.executable, [sys.executable, "-m", f"workers.{worker_mode}"])
    else:
        main()
