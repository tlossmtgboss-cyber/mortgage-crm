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
    """Create tables that Alembic migration 014 should have created.

    run_migrations.py stamps at head when core tables already exist,
    so newer migrations (client_files, team_chat, audit_events) may
    never have actually run.  This is idempotent (IF NOT EXISTS).
    """
    if not database_url or "sqlite" in database_url:
        return

    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql://", 1)

    import psycopg2
    conn = psycopg2.connect(database_url, connect_timeout=10)
    conn.autocommit = True
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS client_files (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            organization_id INTEGER NOT NULL REFERENCES organizations(id),
            lead_id INTEGER UNIQUE REFERENCES leads(id),
            first_name VARCHAR,
            last_name VARCHAR,
            primary_email VARCHAR,
            primary_phone VARCHAR,
            lifecycle_stage VARCHAR NOT NULL DEFAULT 'new_lead',
            source VARCHAR,
            preferred_channel VARCHAR,
            sticky_note TEXT,
            assigned_loan_officer_id INTEGER REFERENCES users(id),
            assigned_loan_assistant_id INTEGER REFERENCES users(id),
            assigned_processor_id INTEGER REFERENCES users(id),
            assigned_underwriter_id INTEGER REFERENCES users(id),
            property_address JSONB,
            active_loan_program VARCHAR,
            active_loan_purpose VARCHAR,
            active_loan_amount NUMERIC(18,2),
            active_loan_fico INTEGER,
            active_loan_ltv NUMERIC(8,4),
            active_loan_lock_expires_at TIMESTAMPTZ,
            active_loan_projected_close_date TIMESTAMPTZ,
            tags JSONB NOT NULL DEFAULT '[]',
            last_contact_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            created_by_user_id INTEGER REFERENCES users(id)
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS client_file_collaborators (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            organization_id INTEGER NOT NULL REFERENCES organizations(id),
            client_file_id UUID NOT NULL REFERENCES client_files(id) ON DELETE CASCADE,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            role VARCHAR NOT NULL DEFAULT 'viewer',
            notify_on_inbound BOOLEAN NOT NULL DEFAULT FALSE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE(client_file_id, user_id)
        )
    """)

    cur.execute("""
        DO $$ BEGIN
            CREATE TYPE team_chat_author_kind AS ENUM ('human', 'system');
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$
    """)
    cur.execute("""
        DO $$ BEGIN
            CREATE TYPE team_chat_agent_slug AS ENUM (
                'cadence', 'aria', 'avery', 'insight',
                'ops_manager', 'document', 'milestone', 'lifecycle'
            );
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$
    """)
    cur.execute("""
        DO $$ BEGIN
            CREATE TYPE team_chat_reaction_emoji AS ENUM (
                'thumbs_up', 'check', 'fire', 'question'
            );
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS team_chat_channels (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            organization_id INTEGER NOT NULL,
            client_file_id UUID NOT NULL REFERENCES client_files(id) ON DELETE CASCADE,
            pinned_message_id UUID,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE(client_file_id)
        )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS ix_team_chat_channels_org ON team_chat_channels(organization_id)")

    cur.execute("""
        CREATE TABLE IF NOT EXISTS team_chat_messages (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            organization_id INTEGER NOT NULL,
            channel_id UUID NOT NULL REFERENCES team_chat_channels(id) ON DELETE CASCADE,
            client_file_id UUID NOT NULL REFERENCES client_files(id) ON DELETE CASCADE,
            author_kind team_chat_author_kind NOT NULL,
            author_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
            system_agent_slug team_chat_agent_slug,
            system_display_name VARCHAR(80),
            system_source_event_kind VARCHAR(80),
            system_source_object_id UUID,
            system_source_object_label VARCHAR(200),
            body TEXT NOT NULL,
            mentioned_user_ids INTEGER[] NOT NULL DEFAULT '{}',
            attachments JSONB NOT NULL DEFAULT '[]',
            is_pinned BOOLEAN NOT NULL DEFAULT FALSE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            edited_at TIMESTAMPTZ,
            deleted_at TIMESTAMPTZ
        )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS ix_tc_messages_channel_time ON team_chat_messages(channel_id, created_at)")
    cur.execute("CREATE INDEX IF NOT EXISTS ix_tc_messages_org ON team_chat_messages(organization_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS ix_tc_messages_client_file ON team_chat_messages(client_file_id)")

    cur.execute("""
        DO $$ BEGIN
            ALTER TABLE team_chat_channels
                ADD CONSTRAINT fk_tc_channels_pinned
                FOREIGN KEY (pinned_message_id) REFERENCES team_chat_messages(id)
                ON DELETE SET NULL;
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS team_chat_reactions (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            organization_id INTEGER NOT NULL,
            message_id UUID NOT NULL REFERENCES team_chat_messages(id) ON DELETE CASCADE,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            emoji team_chat_reaction_emoji NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE(message_id, user_id, emoji)
        )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS ix_tc_reactions_message ON team_chat_reactions(message_id)")

    cur.execute("""
        CREATE TABLE IF NOT EXISTS team_chat_reads (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            organization_id INTEGER NOT NULL,
            channel_id UUID NOT NULL REFERENCES team_chat_channels(id) ON DELETE CASCADE,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            last_read_message_id UUID NOT NULL,
            last_read_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE(channel_id, user_id)
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS audit_events (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            occurred_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            event_type VARCHAR(64) NOT NULL,
            outcome VARCHAR(16) NOT NULL DEFAULT 'success',
            actor_id UUID,
            actor_email VARCHAR(320),
            actor_role VARCHAR(32),
            org_id UUID,
            resource_type VARCHAR(64),
            resource_id VARCHAR(128),
            ip INET,
            user_agent TEXT,
            request_id VARCHAR(64),
            metadata JSONB NOT NULL DEFAULT '{}'
        )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS ix_audit_events_occurred ON audit_events(occurred_at)")
    cur.execute("CREATE INDEX IF NOT EXISTS ix_audit_events_event_type ON audit_events(event_type)")
    cur.execute("CREATE INDEX IF NOT EXISTS ix_audit_events_actor ON audit_events(actor_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS ix_audit_events_resource ON audit_events(resource_id)")

    tables_created = []
    for tbl in ("client_files", "client_file_collaborators",
                "team_chat_channels", "team_chat_messages",
                "team_chat_reactions", "team_chat_reads", "audit_events"):
        cur.execute("SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = %s)", (tbl,))
        if cur.fetchone()[0]:
            tables_created.append(tbl)

    print(f"START.PY: Tables verified: {', '.join(tables_created)}", flush=True)

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

    # Ensure tables from Alembic migration 014 exist.
    # run_migrations.py stamps at head when core tables pre-exist, so these
    # tables may never have been created despite the migration being "applied".
    print("=" * 50, flush=True)
    print("START.PY: Ensuring client_files and team_chat tables exist...", flush=True)
    try:
        _ensure_new_tables(database_url)
    except Exception as e:
        print(f"START.PY: Table creation warning: {e}", flush=True)

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
