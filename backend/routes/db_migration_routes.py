"""
Database Migration Routes

Migration endpoints for database schema changes.
Extracted from inline_legacy_routes.py.

All endpoints with URL pattern /api/v1/migrations/* plus admin migration
endpoints (/api/v1/admin/run-migration, /api/v1/public/migrations/*, etc.).

Uses function-registration pattern (NOT APIRouter) since these endpoints
depend on closure variables (get_db, get_current_user) passed through
the registration function.
"""
from fastapi import Depends, HTTPException, Header
from sqlalchemy.orm import Session
from sqlalchemy import text
from datetime import datetime, timezone
import logging
import os

from database.models import (
    User, VerifiedCallerId, AgentTelephonySettings,
)
from database import engine

logger = logging.getLogger(__name__)


def register_migration_routes(app, get_db, get_current_user, **kwargs):
    """Register database migration routes."""

    # ========================================================================
    # /api/v1/migrations/* ENDPOINTS
    # ========================================================================

    # PURL System Migration Endpoint
    @app.post("/api/v1/migrations/add-purl-system")
    async def add_purl_system_migration(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
        """Run migration to add PURL (Persistent URL) borrower portal tables"""
        try:
            from sqlalchemy import text as sql_text

            sql_commands = [
                "CREATE EXTENSION IF NOT EXISTS pgcrypto",
                "CREATE EXTENSION IF NOT EXISTS citext",
                """CREATE TABLE IF NOT EXISTS purl_workspaces (
                    id SERIAL PRIMARY KEY,
                    organization_id INTEGER REFERENCES organizations(id) ON DELETE CASCADE,
                    slug VARCHAR(255) NOT NULL,
                    status VARCHAR(50) NOT NULL DEFAULT 'lead',
                    display_name VARCHAR(500) NOT NULL,
                    source VARCHAR(255),
                    owner_user_id INTEGER REFERENCES users(id),
                    lead_at TIMESTAMP WITH TIME ZONE,
                    application_at TIMESTAMP WITH TIME ZONE,
                    active_loan_at TIMESTAMP WITH TIME ZONE,
                    closing_at TIMESTAMP WITH TIME ZONE,
                    post_close_at TIMESTAMP WITH TIME ZONE,
                    meta_data JSONB NOT NULL DEFAULT '{}'::jsonb,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(organization_id, slug)
                )""",
                "CREATE INDEX IF NOT EXISTS idx_purl_workspaces_org_status ON purl_workspaces(organization_id, status)",
                "CREATE INDEX IF NOT EXISTS idx_purl_workspaces_slug ON purl_workspaces(slug)",
                """CREATE TABLE IF NOT EXISTS purl_contacts (
                    id SERIAL PRIMARY KEY,
                    organization_id INTEGER NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
                    workspace_id INTEGER NOT NULL REFERENCES purl_workspaces(id) ON DELETE CASCADE,
                    contact_type VARCHAR(50) NOT NULL,
                    first_name VARCHAR(255) NOT NULL,
                    last_name VARCHAR(255) NOT NULL,
                    email VARCHAR(255),
                    phone VARCHAR(50),
                    auth_user_id INTEGER REFERENCES users(id),
                    meta_data JSONB NOT NULL DEFAULT '{}'::jsonb,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                )""",
                "CREATE INDEX IF NOT EXISTS idx_purl_contacts_workspace ON purl_contacts(workspace_id)",
                """CREATE TABLE IF NOT EXISTS purl_access_tokens (
                    id SERIAL PRIMARY KEY,
                    organization_id INTEGER NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
                    workspace_id INTEGER NOT NULL REFERENCES purl_workspaces(id) ON DELETE CASCADE,
                    contact_id INTEGER REFERENCES purl_contacts(id) ON DELETE CASCADE,
                    token_hash VARCHAR(64) NOT NULL UNIQUE,
                    scope VARCHAR(20) NOT NULL DEFAULT 'read',
                    expires_at TIMESTAMP WITH TIME ZONE,
                    last_used_at TIMESTAMP WITH TIME ZONE,
                    revoked_at TIMESTAMP WITH TIME ZONE,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                )""",
                "CREATE INDEX IF NOT EXISTS idx_purl_tokens_hash ON purl_access_tokens(token_hash)",
                """CREATE TABLE IF NOT EXISTS purl_applications (
                    id SERIAL PRIMARY KEY,
                    organization_id INTEGER NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
                    workspace_id INTEGER NOT NULL REFERENCES purl_workspaces(id) ON DELETE CASCADE,
                    application_type VARCHAR(20) NOT NULL,
                    status VARCHAR(30) NOT NULL DEFAULT 'in_progress',
                    version INTEGER NOT NULL DEFAULT 1,
                    data JSONB NOT NULL DEFAULT '{}'::jsonb,
                    completeness_pct INTEGER DEFAULT 0,
                    started_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    submitted_at TIMESTAMP WITH TIME ZONE,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(workspace_id, application_type, version)
                )""",
                """CREATE TABLE IF NOT EXISTS purl_loans (
                    id SERIAL PRIMARY KEY,
                    organization_id INTEGER NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
                    workspace_id INTEGER NOT NULL REFERENCES purl_workspaces(id) ON DELETE CASCADE,
                    application_id INTEGER REFERENCES purl_applications(id),
                    main_loan_id INTEGER,
                    loan_number VARCHAR(100),
                    status VARCHAR(30) NOT NULL DEFAULT 'active',
                    loan_purpose VARCHAR(50),
                    loan_amount DECIMAL(15, 2),
                    meta_data JSONB NOT NULL DEFAULT '{}'::jsonb,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                )""",
                """CREATE TABLE IF NOT EXISTS purl_documents (
                    id SERIAL PRIMARY KEY,
                    organization_id INTEGER NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
                    workspace_id INTEGER NOT NULL REFERENCES purl_workspaces(id) ON DELETE CASCADE,
                    loan_id INTEGER REFERENCES purl_loans(id) ON DELETE CASCADE,
                    doc_type VARCHAR(100) NOT NULL,
                    doc_category VARCHAR(50) NOT NULL,
                    status VARCHAR(30) NOT NULL DEFAULT 'uploaded',
                    file_name VARCHAR(500) NOT NULL,
                    storage_key VARCHAR(1000) NOT NULL UNIQUE,
                    size_bytes BIGINT NOT NULL,
                    mime_type VARCHAR(255) NOT NULL,
                    uploaded_by_contact_id INTEGER REFERENCES purl_contacts(id),
                    uploaded_by_user_id INTEGER REFERENCES users(id),
                    meta_data JSONB NOT NULL DEFAULT '{}'::jsonb,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                )""",
                """CREATE TABLE IF NOT EXISTS purl_tasks (
                    id SERIAL PRIMARY KEY,
                    organization_id INTEGER NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
                    workspace_id INTEGER REFERENCES purl_workspaces(id) ON DELETE CASCADE,
                    title VARCHAR(500) NOT NULL,
                    description TEXT,
                    task_type VARCHAR(50) DEFAULT 'general',
                    status VARCHAR(30) NOT NULL DEFAULT 'open',
                    priority VARCHAR(20) NOT NULL DEFAULT 'medium',
                    assigned_to_user_id INTEGER REFERENCES users(id),
                    assigned_to_contact_id INTEGER REFERENCES purl_contacts(id),
                    due_at TIMESTAMP WITH TIME ZONE,
                    completed_at TIMESTAMP WITH TIME ZONE,
                    meta_data JSONB NOT NULL DEFAULT '{}'::jsonb,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                )""",
                """CREATE TABLE IF NOT EXISTS purl_messages (
                    id SERIAL PRIMARY KEY,
                    organization_id INTEGER NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
                    workspace_id INTEGER NOT NULL REFERENCES purl_workspaces(id) ON DELETE CASCADE,
                    message_type VARCHAR(30) NOT NULL DEFAULT 'text',
                    content TEXT NOT NULL,
                    sender_type VARCHAR(20) NOT NULL,
                    sender_user_id INTEGER REFERENCES users(id),
                    sender_contact_id INTEGER REFERENCES purl_contacts(id),
                    related_document_id INTEGER REFERENCES purl_documents(id),
                    related_task_id INTEGER REFERENCES purl_tasks(id),
                    is_read_by_borrower BOOLEAN DEFAULT FALSE,
                    read_at TIMESTAMP WITH TIME ZONE,
                    meta_data JSONB NOT NULL DEFAULT '{}'::jsonb,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                )""",
                "CREATE INDEX IF NOT EXISTS idx_purl_messages_workspace ON purl_messages(workspace_id, created_at DESC)",
                """CREATE TABLE IF NOT EXISTS purl_audit_log (
                    id SERIAL PRIMARY KEY,
                    organization_id INTEGER NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
                    actor_type VARCHAR(20) NOT NULL,
                    actor_id INTEGER,
                    workspace_id INTEGER REFERENCES purl_workspaces(id),
                    action VARCHAR(100) NOT NULL,
                    resource_type VARCHAR(100) NOT NULL,
                    resource_id INTEGER,
                    changes JSONB,
                    meta_data JSONB NOT NULL DEFAULT '{}'::jsonb,
                    ip_address VARCHAR(45),
                    request_id VARCHAR(100),
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                )""",
                "CREATE INDEX IF NOT EXISTS idx_purl_audit_workspace ON purl_audit_log(workspace_id, created_at DESC)"
            ]

            success_count = 0
            errors = []
            for i, sql in enumerate(sql_commands):
                try:
                    db.execute(sql_text(sql))
                    db.commit()
                    success_count += 1
                except Exception as e:
                    db.rollback()
                    error_msg = str(e)
                    if 'already exists' in error_msg.lower() or 'duplicate' in error_msg.lower():
                        success_count += 1
                        continue
                    errors.append(f"Statement {i+1}: {error_msg[:200]}")

            return {
                "success": len(errors) == 0,
                "message": f"PURL migration: {success_count}/{len(sql_commands)} statements succeeded",
                "tables_created": [
                    "purl_workspaces", "purl_contacts", "purl_access_tokens",
                    "purl_applications", "purl_loans", "purl_documents",
                    "purl_tasks", "purl_messages", "purl_audit_log"
                ],
                "errors": errors if errors else None
            }
        except Exception as e:
            return {"success": False, "error": "Internal server error"}


    # Email Monitor Migration Endpoint
    @app.post("/api/v1/migrations/add-email-monitor")
    async def add_email_monitor_migration(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
        """Run migration to add email monitor tables"""
        try:
            import os
            from sqlalchemy import text as sql_text

            migration_path = os.path.join(os.path.dirname(__file__), "migrations", "add_email_monitor_tables.sql")

            with open(migration_path, 'r') as f:
                sql = f.read()

            # Split by semicolon and filter
            raw_statements = sql.split(';')
            statements = []
            for s in raw_statements:
                # Strip leading comment lines
                lines = s.strip().split('\n')
                clean_lines = [l for l in lines if not l.strip().startswith('--')]
                clean_stmt = '\n'.join(clean_lines).strip()
                if clean_stmt:
                    statements.append(clean_stmt)

            results = []
            success_count = 0
            for i, statement in enumerate(statements):
                try:
                    db.execute(sql_text(statement))
                    db.commit()
                    success_count += 1
                except Exception as e:
                    db.rollback()
                    error_msg = str(e)
                    if 'already exists' in error_msg.lower() or 'duplicate' in error_msg.lower():
                        success_count += 1
                        continue
                    results.append(f"Statement {i+1}: {error_msg[:200]}")

            return {
                "success": len(results) == 0,
                "message": f"Email monitor migration: {success_count} statements succeeded",
                "tables_created": [
                    "email_monitor_addresses", "email_monitor_keywords", "email_monitor_rules",
                    "email_monitor_captured", "email_crm_links", "email_relevance_analysis",
                    "email_filter_whitelist", "email_filter_blacklist", "email_provider_config",
                    "gmail_oauth_tokens", "outlook_oauth_tokens", "email_monitor_log"
                ],
                "total_statements": len(statements),
                "succeeded": success_count,
                "errors": results if results else None
            }
        except Exception as e:
            return {"success": False, "error": "Internal server error"}

    # Morning Check-in Migration Endpoint
    @app.post("/api/v1/migrations/add-morning-checkin")
    async def add_morning_checkin_migration(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
        """Run migration to add morning check-in tables"""
        try:
            import os
            from sqlalchemy import text as sql_text

            migration_path = os.path.join(os.path.dirname(__file__), "migrations", "add_morning_checkin.sql")

            with open(migration_path, 'r') as f:
                sql = f.read()

            # Use raw connection to execute multi-statement SQL
            connection = db.connection().connection
            cursor = connection.cursor()
            cursor.execute(sql)
            connection.commit()

            return {"status": "success", "message": "Morning check-in tables created successfully"}
        except Exception as e:
            db.rollback()
            logger.error(f"Migration error: {e}")
            raise HTTPException(status_code=500, detail="Internal server error")

    # Rate Sheet Migration Endpoint
    @app.post("/api/v1/migrations/add-rate-sheets")
    async def add_rate_sheets_migration(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
        """Run migration to add rate sheet and refinance opportunity tables"""
        try:
            from sqlalchemy import text as sql_text

            # Create tables using SQLAlchemy models (handles SQLite/PostgreSQL automatically)
            from models.rate_sheet import RateSheet, RateSheetRate, RefinanceOpportunity
            from database import engine

            tables_created = []
            errors = []

            for model in [RateSheet, RateSheetRate, RefinanceOpportunity]:
                try:
                    model.__table__.create(engine, checkfirst=True)
                    tables_created.append(model.__tablename__)
                except Exception as e:
                    error_msg = str(e)
                    if 'already exists' in error_msg.lower():
                        tables_created.append(f"{model.__tablename__} (already exists)")
                    else:
                        errors.append(f"{model.__tablename__}: {error_msg[:100]}")

            return {
                "success": len(errors) == 0,
                "message": f"Rate sheet migration complete: {len(tables_created)} tables",
                "tables_created": tables_created,
                "errors": errors if errors else None
            }
        except Exception as e:
            logger.error(f"Rate sheet migration error: {e}")
            return {"success": False, "error": "Internal server error"}


    @app.post("/api/v1/migrations/add-external-message-id")
    async def add_external_message_id_migration(
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
    ):
        """
        Migration: Add external_message_id column to incoming_data_events table
        This column is needed for email deduplication
        """
        try:
            # Check if user is admin (you can add admin check if needed)
            logger.info(f"Running migration: add external_message_id column (user: {current_user.id})")

            # Check if column already exists
            result = db.execute(text("""
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = 'incoming_data_events'
                AND column_name = 'external_message_id'
            """))

            if result.fetchone():
                return {
                    "success": True,
                    "message": "Column 'external_message_id' already exists",
                    "already_exists": True
                }

            # Add the column
            db.execute(text("""
                ALTER TABLE incoming_data_events
                ADD COLUMN external_message_id VARCHAR;
            """))

            # Add index for performance
            db.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_incoming_data_events_external_message_id
                ON incoming_data_events(external_message_id);
            """))

            db.commit()

            logger.info("Successfully added 'external_message_id' column with index")

            return {
                "success": True,
                "message": "Successfully added 'external_message_id' column with index",
                "already_exists": False
            }

        except Exception as e:
            logger.error(f"Migration failed: {e}")
            db.rollback()
            return {
                "success": False,
                "message": "Migration failed",
                "error": "Internal server error"
            }

    @app.post("/api/v1/migrations/add-conversation-memory")
    async def add_conversation_memory_migration(
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
    ):
        """
        Migration: Add conversation_memory table for AI Memory System
        This table stores conversation metadata alongside Pinecone vectors
        """
        try:
            logger.info(f"Running migration: add conversation_memory table (user: {current_user.id})")

            # Check if table already exists
            result = db.execute(text("""
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'public'
                AND table_name = 'conversation_memory'
            """))

            if result.fetchone():
                # Count existing rows
                count_result = db.execute(text("SELECT COUNT(*) FROM conversation_memory"))
                row_count = count_result.fetchone()[0]

                return {
                    "success": True,
                    "message": "Table 'conversation_memory' already exists",
                    "already_exists": True,
                    "row_count": row_count
                }

            # Create the table
            db.execute(text("""
                CREATE TABLE conversation_memory (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    lead_id INTEGER REFERENCES leads(id) ON DELETE SET NULL,
                    loan_id INTEGER REFERENCES loans(id) ON DELETE SET NULL,
                    conversation_summary TEXT NOT NULL,
                    key_points JSONB,
                    sentiment VARCHAR(50),
                    intent VARCHAR(255),
                    pinecone_id VARCHAR(255) UNIQUE,
                    relevance_score FLOAT,
                    access_count INTEGER DEFAULT 0,
                    last_accessed_at TIMESTAMP WITH TIME ZONE,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                )
            """))

            # Create indexes
            db.execute(text("""
                CREATE INDEX idx_conversation_memory_user_id ON conversation_memory(user_id)
            """))
            db.execute(text("""
                CREATE INDEX idx_conversation_memory_lead_id ON conversation_memory(lead_id)
            """))
            db.execute(text("""
                CREATE INDEX idx_conversation_memory_loan_id ON conversation_memory(loan_id)
            """))
            db.execute(text("""
                CREATE INDEX idx_conversation_memory_pinecone_id ON conversation_memory(pinecone_id)
            """))
            db.execute(text("""
                CREATE INDEX idx_conversation_memory_created_at ON conversation_memory(created_at)
            """))

            # Create updated_at trigger function if it doesn't exist
            db.execute(text("""
                CREATE OR REPLACE FUNCTION update_updated_at_column()
                RETURNS TRIGGER AS $$
                BEGIN
                    NEW.updated_at = CURRENT_TIMESTAMP;
                    RETURN NEW;
                END;
                $$ language 'plpgsql'
            """))

            # Create trigger
            db.execute(text("""
                CREATE TRIGGER update_conversation_memory_updated_at
                    BEFORE UPDATE ON conversation_memory
                    FOR EACH ROW
                    EXECUTE FUNCTION update_updated_at_column()
            """))

            db.commit()

            logger.info("Successfully created conversation_memory table with indexes and triggers")

            return {
                "success": True,
                "message": "Successfully created conversation_memory table with indexes and triggers",
                "already_exists": False,
                "row_count": 0
            }

        except Exception as e:
            logger.error(f"Migration failed: {e}")
            db.rollback()
            return {
                "success": False,
                "message": "Migration failed",
                "error": "Internal server error"
            }

    @app.post("/api/v1/migrations/add-permanent-memory")
    async def add_permanent_memory_migration(
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user),
    ):
        """
        Migration: Add permanent AI conversation memory tables
        Creates ai_conversation_memory and ai_action_history tables
        """
        try:
            logger.info("Running migration: add permanent AI memory tables")

            tables_created = []

            # Check if ai_conversation_memory exists
            result = db.execute(text("""
                SELECT table_name FROM information_schema.tables
                WHERE table_schema = 'public' AND table_name = 'ai_conversation_memory'
            """))

            if not result.fetchone():
                # Create ai_conversation_memory table
                db.execute(text("""
                    CREATE TABLE ai_conversation_memory (
                        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                        user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                        session_id UUID NOT NULL,
                        message_index INTEGER NOT NULL,
                        role VARCHAR(20) NOT NULL,
                        content TEXT NOT NULL,
                        action_id UUID,
                        action_data JSONB,
                        created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL
                    )
                """))

                # Create indexes
                db.execute(text("CREATE INDEX idx_conv_user_date ON ai_conversation_memory(user_id, created_at)"))
                db.execute(text("CREATE INDEX idx_conv_session ON ai_conversation_memory(session_id, message_index)"))
                db.execute(text("CREATE INDEX idx_conv_search ON ai_conversation_memory USING gin(to_tsvector('english', content))"))

                tables_created.append("ai_conversation_memory")
                logger.info("Created ai_conversation_memory table with indexes")
            else:
                logger.info("ai_conversation_memory already exists")

            # Check if ai_action_history exists
            result = db.execute(text("""
                SELECT table_name FROM information_schema.tables
                WHERE table_schema = 'public' AND table_name = 'ai_action_history'
            """))

            if not result.fetchone():
                # Create ai_action_history table
                db.execute(text("""
                    CREATE TABLE ai_action_history (
                        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                        user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                        action_id UUID NOT NULL UNIQUE,
                        action_type VARCHAR(50) NOT NULL,
                        preview_data JSONB NOT NULL,
                        execution_data JSONB,
                        status VARCHAR(20) NOT NULL,
                        created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL,
                        executed_at TIMESTAMP WITH TIME ZONE
                    )
                """))

                # Create index
                db.execute(text("CREATE INDEX idx_action_user_date ON ai_action_history(user_id, created_at)"))

                tables_created.append("ai_action_history")
                logger.info("Created ai_action_history table with indexes")
            else:
                logger.info("ai_action_history already exists")

            db.commit()

            if tables_created:
                return {
                    "success": True,
                    "message": f"Successfully created permanent memory tables: {', '.join(tables_created)}",
                    "tables_created": tables_created
                }
            else:
                return {
                    "success": True,
                    "message": "All permanent memory tables already exist",
                    "tables_created": []
                }

        except Exception as e:
            logger.error(f"Migration failed: {e}")
            db.rollback()
            return {
                "success": False,
                "message": "Migration failed",
                "error": "Internal server error"
            }


    @app.post("/api/v1/migrations/add-lead-milestone-columns")
    async def add_lead_milestone_columns(
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user),
    ):
        """
        Migration: Add milestone date columns to leads table for task triggering
        """
        try:
            logger.info("Running migration: add lead milestone columns")
            columns_added = []

            # Check and add each column
            columns_to_add = [
                ("application_started_date", "TIMESTAMP WITH TIME ZONE"),
                ("application_completed_date", "TIMESTAMP WITH TIME ZONE"),
                ("credit_pulled_date", "TIMESTAMP WITH TIME ZONE"),
                ("preapproval_issued_date", "TIMESTAMP WITH TIME ZONE"),
                ("property_address", "VARCHAR(500)")
            ]

            for col_name, col_type in columns_to_add:
                result = db.execute(text("""
                    SELECT column_name FROM information_schema.columns
                    WHERE table_name = 'leads' AND column_name = :col_name
                """), {"col_name": col_name})

                if not result.fetchone():
                    alter_sql = "ALTER TABLE leads ADD COLUMN " + col_name + " " + col_type
                    db.execute(text(alter_sql))
                    columns_added.append(col_name)
                    logger.info(f"Added column {col_name} to leads table")

            db.commit()

            return {
                "success": True,
                "columns_added": columns_added,
                "message": f"Added {len(columns_added)} columns to leads table" if columns_added else "All columns already exist"
            }

        except Exception as e:
            logger.error(f"Lead milestone columns migration failed: {e}")
            db.rollback()
            return {
                "success": False,
                "message": "Migration failed",
                "error": "Internal server error"
            }


    @app.post("/api/v1/migrations/backfill-lead-received-date")
    async def backfill_lead_received_date(
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user),
    ):
        """
        Migration: Backfill lead_received_date from created_at for existing leads.
        This ensures all leads have proper SLA tracking timestamps.
        """
        try:
            logger.info("Running migration: backfill lead_received_date")

            # Count leads without lead_received_date
            count_result = db.execute(text("""
                SELECT COUNT(*) as count FROM leads WHERE lead_received_date IS NULL
            """)).fetchone()
            leads_to_update = count_result[0] if count_result else 0

            if leads_to_update == 0:
                return {
                    "success": True,
                    "leads_updated": 0,
                    "message": "All leads already have lead_received_date set"
                }

            # Update leads without lead_received_date
            db.execute(text("""
                UPDATE leads
                SET lead_received_date = created_at
                WHERE lead_received_date IS NULL
            """))
            db.commit()

            logger.info(f"Backfilled lead_received_date for {leads_to_update} leads")

            return {
                "success": True,
                "leads_updated": leads_to_update,
                "message": f"Backfilled lead_received_date for {leads_to_update} leads from created_at"
            }

        except Exception as e:
            logger.error(f"Lead received date backfill failed: {e}")
            db.rollback()
            return {
                "success": False,
                "message": "Migration failed",
                "error": "Internal server error"
            }


    @app.post("/api/v1/migrations/add-stage-changed-at")
    async def add_stage_changed_at_column(
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user),
    ):
        """
        Migration: Add stage_changed_at column to leads table for workflow day calculations.
        This tracks when the lead's stage last changed to properly calculate workflow task timing.
        """
        try:
            logger.info("Running migration: add stage_changed_at column")
            columns_added = []

            # Check if column exists
            result = db.execute(text("""
                SELECT column_name FROM information_schema.columns
                WHERE table_name = 'leads' AND column_name = 'stage_changed_at'
            """))

            if not result.fetchone():
                db.execute(text("ALTER TABLE leads ADD COLUMN stage_changed_at TIMESTAMP WITH TIME ZONE"))
                columns_added.append("stage_changed_at")
                logger.info("Added column stage_changed_at to leads table")

                # Initialize stage_changed_at to created_at for existing leads
                db.execute(text("""
                    UPDATE leads
                    SET stage_changed_at = created_at
                    WHERE stage_changed_at IS NULL
                """))
                logger.info("Initialized stage_changed_at for existing leads")

            db.commit()

            return {
                "success": True,
                "columns_added": columns_added,
                "message": f"Added {len(columns_added)} columns to leads table" if columns_added else "Column already exists"
            }

        except Exception as e:
            logger.error(f"Stage changed at migration failed: {e}")
            db.rollback()
            return {
                "success": False,
                "message": "Migration failed",
                "error": "Internal server error"
            }


    @app.post("/api/v1/migrations/add-loan-milestone-columns")
    async def add_loan_milestone_columns(
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user),
    ):
        """
        Migration: Add milestone date columns to loans table for task triggering
        """
        try:
            logger.info("Running migration: add loan milestone columns")
            columns_added = []

            columns_to_add = [
                ("initial_disclosures_sent_date", "TIMESTAMP WITH TIME ZONE"),
                ("initial_disclosures_signed_date", "TIMESTAMP WITH TIME ZONE"),
                ("cd_received_signed_date", "TIMESTAMP WITH TIME ZONE"),
                ("final_closing_package_sent_date", "TIMESTAMP WITH TIME ZONE")
            ]

            for col_name, col_type in columns_to_add:
                result = db.execute(text("""
                    SELECT column_name FROM information_schema.columns
                    WHERE table_name = 'loans' AND column_name = :col_name
                """), {"col_name": col_name})

                if not result.fetchone():
                    alter_sql = "ALTER TABLE loans ADD COLUMN " + col_name + " " + col_type
                    db.execute(text(alter_sql))
                    columns_added.append(col_name)
                    logger.info(f"Added column {col_name} to loans table")

            db.commit()

            return {
                "success": True,
                "columns_added": columns_added,
                "message": f"Added {len(columns_added)} columns to loans table" if columns_added else "All columns already exist"
            }

        except Exception as e:
            logger.error(f"Loan milestone columns migration failed: {e}")
            db.rollback()
            return {
                "success": False,
                "message": "Migration failed",
                "error": "Internal server error"
            }


    @app.post("/api/v1/migrations/fix-lead-stage-values")
    async def fix_lead_stage_values_migration(
        key: str = "",
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user),
    ):
        """
        Migration: Fix invalid lead stage values in the database.
        Converts invalid enum values to valid ones.
        Call with: POST /api/v1/migrations/fix-lead-stage-values?key=fix-stages-now
        """
        if key != "fix-stages-now":
            raise HTTPException(status_code=403, detail="Invalid key. Use ?key=fix-stages-now")

        try:
            logger.info("Running migration: fix lead stage values")

            # Map of invalid values to valid LeadStage enum values
            stage_fixes = {
                'Credit Only': 'Pre-Qualified',
                'credit only': 'Pre-Qualified',
                'Pre Approved': 'Pre-Approved',
                'Pre Qualified': 'Pre-Qualified',
                'Long Term Nurture': 'Long-Term Nurture',
                'Attempted': 'Attempted Contact',
                'new': 'New',
                'NEW': 'New',
            }

            fixed_count = 0
            for old_value, new_value in stage_fixes.items():
                try:
                    result = db.execute(text(
                        "UPDATE leads SET stage = :new_value WHERE stage = :old_value"
                    ), {"old_value": old_value, "new_value": new_value})
                    if result.rowcount > 0:
                        logger.info(f"Fixed {result.rowcount} leads: '{old_value}' -> '{new_value}'")
                        fixed_count += result.rowcount
                except Exception as e:
                    logger.warning(f"Could not fix '{old_value}': {e}")
                    db.rollback()

            # Also set any NULL stages to 'New'
            try:
                result = db.execute(text("UPDATE leads SET stage = 'New' WHERE stage IS NULL"))
                if result.rowcount > 0:
                    logger.info(f"Set {result.rowcount} NULL stages to 'New'")
                    fixed_count += result.rowcount
            except Exception as e:
                logger.warning(f"Could not fix NULL stages: {e}")
                db.rollback()

            db.commit()

            return {
                "success": True,
                "message": f"Fixed {fixed_count} lead stage values",
                "fixed_count": fixed_count
            }
        except Exception as e:
            logger.error(f"Lead stage fix migration failed: {e}")
            db.rollback()
            return {
                "success": False,
                "message": "Migration failed",
                "error": "Internal server error"
            }


    @app.post("/api/v1/migrations/convert-lead-stage-to-enum-names")
    async def convert_lead_stage_to_enum_names_migration(
        key: str = "",
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user),
    ):
        """
        Migration: Convert lead stage display values to PostgreSQL enum names.
        The database enum uses uppercase names (NEW, PROSPECT, etc.) but we stored
        display values (New, Prospect, etc.). This fixes that mismatch.
        Call with: POST /api/v1/migrations/convert-lead-stage-to-enum-names?key=convert-stages
        """
        if key != "convert-stages":
            raise HTTPException(status_code=403, detail="Invalid key. Use ?key=convert-stages")

        try:
            logger.info("Running migration: convert lead stage values to enum names")

            # Map display values to PostgreSQL enum names
            stage_mapping = {
                'New': 'NEW',
                'Attempted Contact': 'ATTEMPTED_CONTACT',
                'Prospect': 'PROSPECT',
                'Application': 'APPLICATION',
                'Pre-Qualified': 'PRE_QUALIFIED',
                'Pre-Approved': 'PRE_APPROVED',
                'Under Contract': 'UNDER_CONTRACT',
                'Long-Term Nurture': 'LONG_TERM_NURTURE',
                'Closed': 'CLOSED',
                'AMR': 'AMR',
                'Referral Source': 'REFERRAL_SOURCE',
                'Withdrawn': 'WITHDRAWN',
                'Does Not Qualify': 'DOES_NOT_QUALIFY',
            }

            results = []
            total_fixed = 0

            for display_value, enum_name in stage_mapping.items():
                try:
                    # First check how many rows have this value
                    check = db.execute(text(
                        "SELECT COUNT(*) FROM leads WHERE stage::text = :val"
                    ), {"val": display_value}).scalar()

                    if check and check > 0:
                        # Update to enum name using string interpolation (safe since enum_name is from our dict)
                        result = db.execute(text(
                            f"UPDATE leads SET stage = '{enum_name}'::leadstage WHERE stage::text = :display_val"
                        ), {"display_val": display_value})
                        results.append(f"'{display_value}' -> '{enum_name}': {result.rowcount} rows")
                        total_fixed += result.rowcount
                except Exception as e:
                    results.append(f"'{display_value}': Error - {str(e)}")
                    db.rollback()

            db.commit()

            return {
                "success": True,
                "message": f"Fixed {total_fixed} lead stage values",
                "details": results,
                "total_fixed": total_fixed
            }
        except Exception as e:
            logger.error(f"Lead stage conversion migration failed: {e}")
            db.rollback()
            return {
                "success": False,
                "message": "Migration failed",
                "error": "Internal server error"
            }


    @app.post("/api/v1/migrations/add-subscription-system")
    async def add_subscription_system_migration(
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user),
    ):
        """
        Migration: Add subscription and permission system tables
        Creates organization_subscriptions, feature_definitions, feature_usage, usage_warnings, admin_actions
        """
        try:
            logger.info("Running migration: add subscription system tables")

            tables_created = []

            # 1. Create organization_subscriptions table
            result = db.execute(text("""
                SELECT table_name FROM information_schema.tables
                WHERE table_schema = 'public' AND table_name = 'organization_subscriptions'
            """))

            if not result.fetchone():
                db.execute(text("""
                    CREATE TABLE organization_subscriptions (
                        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                        organization_id INTEGER NOT NULL UNIQUE,
                        tier VARCHAR(50) NOT NULL DEFAULT 'lead_management',
                        stripe_customer_id VARCHAR(255),
                        stripe_subscription_id VARCHAR(255),
                        billing_cycle VARCHAR(20) DEFAULT 'monthly',
                        monthly_price NUMERIC(10, 2) NOT NULL DEFAULT 99.00,
                        status VARCHAR(20) DEFAULT 'active',
                        trial_ends_at TIMESTAMP WITH TIME ZONE,
                        current_period_start TIMESTAMP WITH TIME ZONE,
                        current_period_end TIMESTAMP WITH TIME ZONE,
                        enabled_addons JSONB DEFAULT '[]'::jsonb,
                        created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL,
                        updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL
                    )
                """))
                db.execute(text("CREATE INDEX idx_org_sub_org ON organization_subscriptions(organization_id)"))
                db.execute(text("CREATE INDEX idx_org_sub_tier ON organization_subscriptions(tier)"))
                db.execute(text("CREATE INDEX idx_org_sub_status ON organization_subscriptions(status)"))
                tables_created.append("organization_subscriptions")
                logger.info("Created organization_subscriptions table")
            else:
                logger.info("organization_subscriptions already exists")

            # 2. Create feature_definitions table
            result = db.execute(text("""
                SELECT table_name FROM information_schema.tables
                WHERE table_schema = 'public' AND table_name = 'feature_definitions'
            """))

            if not result.fetchone():
                db.execute(text("""
                    CREATE TABLE feature_definitions (
                        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                        feature_key VARCHAR(100) NOT NULL UNIQUE,
                        name VARCHAR(255) NOT NULL,
                        description TEXT,
                        category VARCHAR(50) NOT NULL,
                        min_tier VARCHAR(50) NOT NULL,
                        monthly_limit INTEGER,
                        is_addon BOOLEAN DEFAULT FALSE,
                        addon_price NUMERIC(10, 2),
                        is_active BOOLEAN DEFAULT TRUE,
                        created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL
                    )
                """))
                db.execute(text("CREATE INDEX idx_feature_key ON feature_definitions(feature_key)"))
                db.execute(text("CREATE INDEX idx_feature_tier ON feature_definitions(min_tier)"))
                tables_created.append("feature_definitions")
                logger.info("Created feature_definitions table")

                # Seed default feature definitions
                db.execute(text("""
                    INSERT INTO feature_definitions (feature_key, name, category, min_tier, monthly_limit)
                    VALUES
                    ('ai_queries', 'AI Assistant Queries', 'ai', 'lead_management', 100),
                    ('emails', 'Email Sends', 'communications', 'lead_management', 500),
                    ('sms', 'SMS Messages', 'communications', 'lead_management', 100),
                    ('leads', 'Lead Management', 'leads', 'lead_management', NULL),
                    ('active_loans', 'Active Loan Tracking', 'loans', 'lead_and_active', NULL),
                    ('mum_clients', 'MUM Client Management', 'mum', 'full_pipeline', NULL),
                    ('referral_partners', 'Referral Partner Network', 'partners', 'full_pipeline', NULL),
                    ('advanced_analytics', 'Advanced Analytics', 'analytics', 'full_pipeline', NULL),
                    ('api_access', 'API Access', 'integration', 'full_pipeline', NULL)
                """))
                logger.info("Seeded default feature definitions")
            else:
                logger.info("feature_definitions already exists")

            # 3. Create feature_usage table
            result = db.execute(text("""
                SELECT table_name FROM information_schema.tables
                WHERE table_schema = 'public' AND table_name = 'feature_usage'
            """))

            if not result.fetchone():
                db.execute(text("""
                    CREATE TABLE feature_usage (
                        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                        organization_id INTEGER NOT NULL,
                        feature_key VARCHAR(100) NOT NULL,
                        usage_count INTEGER DEFAULT 0,
                        period_start TIMESTAMP WITH TIME ZONE NOT NULL,
                        period_end TIMESTAMP WITH TIME ZONE NOT NULL,
                        created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL,
                        updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL
                    )
                """))
                db.execute(text("CREATE INDEX idx_usage_org ON feature_usage(organization_id)"))
                db.execute(text("CREATE INDEX idx_usage_feature ON feature_usage(feature_key)"))
                db.execute(text("CREATE INDEX idx_usage_period ON feature_usage(period_start, period_end)"))
                db.execute(text("CREATE UNIQUE INDEX idx_usage_unique ON feature_usage(organization_id, feature_key, period_start)"))
                tables_created.append("feature_usage")
                logger.info("Created feature_usage table")
            else:
                logger.info("feature_usage already exists")

            # 4. Create usage_warnings table
            result = db.execute(text("""
                SELECT table_name FROM information_schema.tables
                WHERE table_schema = 'public' AND table_name = 'usage_warnings'
            """))

            if not result.fetchone():
                db.execute(text("""
                    CREATE TABLE usage_warnings (
                        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                        organization_id INTEGER NOT NULL,
                        feature_key VARCHAR(100) NOT NULL,
                        warning_type VARCHAR(50) NOT NULL,
                        threshold_percent INTEGER,
                        message TEXT,
                        acknowledged BOOLEAN DEFAULT FALSE,
                        acknowledged_at TIMESTAMP WITH TIME ZONE,
                        acknowledged_by INTEGER REFERENCES users(id),
                        created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL
                    )
                """))
                db.execute(text("CREATE INDEX idx_warning_org ON usage_warnings(organization_id)"))
                db.execute(text("CREATE INDEX idx_warning_ack ON usage_warnings(acknowledged)"))
                tables_created.append("usage_warnings")
                logger.info("Created usage_warnings table")
            else:
                logger.info("usage_warnings already exists")

            # 5. Create admin_actions table
            result = db.execute(text("""
                SELECT table_name FROM information_schema.tables
                WHERE table_schema = 'public' AND table_name = 'admin_actions'
            """))

            if not result.fetchone():
                db.execute(text("""
                    CREATE TABLE admin_actions (
                        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                        admin_user_id INTEGER NOT NULL REFERENCES users(id),
                        organization_id INTEGER,
                        action_type VARCHAR(100) NOT NULL,
                        description TEXT,
                        previous_value JSONB,
                        new_value JSONB,
                        created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL
                    )
                """))
                db.execute(text("CREATE INDEX idx_admin_action_user ON admin_actions(admin_user_id)"))
                db.execute(text("CREATE INDEX idx_admin_action_org ON admin_actions(organization_id)"))
                db.execute(text("CREATE INDEX idx_admin_action_type ON admin_actions(action_type)"))
                tables_created.append("admin_actions")
                logger.info("Created admin_actions table")
            else:
                logger.info("admin_actions already exists")

            db.commit()

            if tables_created:
                return {
                    "success": True,
                    "message": f"Successfully created subscription system tables: {', '.join(tables_created)}",
                    "tables_created": tables_created
                }
            else:
                return {
                    "success": True,
                    "message": "All subscription system tables already exist",
                    "tables_created": []
                }

        except Exception as e:
            logger.error(f"Subscription migration failed: {e}")
            db.rollback()
            return {
                "success": False,
                "message": "Migration failed",
                "error": "Internal server error"
            }


    @app.post("/api/v1/migrations/add-rate-monitor-system")
    async def add_rate_monitor_system_migration(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
        """Migration: Add Rate Monitor tables for MUM refinance opportunity tracking"""
        try:
            from sqlalchemy import text as sql_text

            sql_commands = [
                # Rate Monitor Targets
                """CREATE TABLE IF NOT EXISTS rate_monitor_targets (
                    id SERIAL PRIMARY KEY,
                    mum_client_id INTEGER REFERENCES mum_clients(id) ON DELETE CASCADE,
                    target_type VARCHAR(50) NOT NULL,
                    monthly_savings_threshold DECIMAL(10, 2),
                    rate_drop_percentage DECIMAL(5, 3),
                    target_rate DECIMAL(5, 3),
                    loan_type VARCHAR(50) DEFAULT 'conventional',
                    loan_term INTEGER DEFAULT 30,
                    status VARCHAR(50) DEFAULT 'active',
                    is_active BOOLEAN DEFAULT TRUE,
                    auto_call_enabled BOOLEAN DEFAULT FALSE,
                    call_preference VARCHAR(50) DEFAULT 'business_hours',
                    last_triggered_at TIMESTAMP,
                    trigger_count INTEGER DEFAULT 0,
                    vapi_call_id VARCHAR(100),
                    last_call_status VARCHAR(50),
                    last_call_at TIMESTAMP,
                    appointment_scheduled BOOLEAN DEFAULT FALSE,
                    appointment_date TIMESTAMP,
                    notify_email BOOLEAN DEFAULT TRUE,
                    notify_sms BOOLEAN DEFAULT TRUE,
                    notify_lo BOOLEAN DEFAULT TRUE,
                    notes TEXT,
                    created_by INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )""",
                # Rate Monitor History
                """CREATE TABLE IF NOT EXISTS rate_monitor_history (
                    id SERIAL PRIMARY KEY,
                    target_id INTEGER REFERENCES rate_monitor_targets(id) ON DELETE CASCADE,
                    mum_client_id INTEGER REFERENCES mum_clients(id) ON DELETE SET NULL,
                    check_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    client_rate DECIMAL(5, 3),
                    market_rate DECIMAL(5, 3),
                    rate_difference DECIMAL(5, 3),
                    loan_balance DECIMAL(12, 2),
                    monthly_savings DECIMAL(10, 2),
                    annual_savings DECIMAL(12, 2),
                    threshold_met BOOLEAN DEFAULT FALSE,
                    threshold_type VARCHAR(50),
                    threshold_value DECIMAL(10, 3),
                    alert_generated BOOLEAN DEFAULT FALSE,
                    call_initiated BOOLEAN DEFAULT FALSE,
                    rate_source VARCHAR(100) DEFAULT 'optimal_blue',
                    rate_scenario JSONB
                )""",
                # Rate Monitor Alerts
                """CREATE TABLE IF NOT EXISTS rate_monitor_alerts (
                    id SERIAL PRIMARY KEY,
                    target_id INTEGER REFERENCES rate_monitor_targets(id) ON DELETE CASCADE,
                    mum_client_id INTEGER REFERENCES mum_clients(id) ON DELETE SET NULL,
                    history_id INTEGER REFERENCES rate_monitor_history(id) ON DELETE SET NULL,
                    alert_type VARCHAR(50) NOT NULL,
                    priority VARCHAR(20) DEFAULT 'medium',
                    client_rate DECIMAL(5, 3),
                    market_rate DECIMAL(5, 3),
                    monthly_savings DECIMAL(10, 2),
                    annual_savings DECIMAL(12, 2),
                    status VARCHAR(50) DEFAULT 'pending',
                    auto_call_attempted BOOLEAN DEFAULT FALSE,
                    vapi_call_id VARCHAR(100),
                    call_status VARCHAR(50),
                    call_outcome VARCHAR(100),
                    call_duration INTEGER,
                    call_summary TEXT,
                    appointment_scheduled_at TIMESTAMP,
                    assigned_to INTEGER,
                    follow_up_notes TEXT,
                    follow_up_date DATE,
                    converted_to_application BOOLEAN DEFAULT FALSE,
                    application_id INTEGER,
                    conversion_date DATE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    acknowledged_at TIMESTAMP,
                    resolved_at TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )""",
                # Optimal Blue Rate Cache
                """CREATE TABLE IF NOT EXISTS optimal_blue_rate_cache (
                    id SERIAL PRIMARY KEY,
                    cache_key VARCHAR(255) UNIQUE NOT NULL,
                    loan_type VARCHAR(50) NOT NULL,
                    loan_term INTEGER NOT NULL,
                    loan_amount DECIMAL(12, 2),
                    ltv DECIMAL(5, 2),
                    credit_score INTEGER,
                    property_type VARCHAR(50),
                    occupancy VARCHAR(50),
                    state VARCHAR(2),
                    rate DECIMAL(5, 3) NOT NULL,
                    apr DECIMAL(5, 3),
                    points DECIMAL(5, 3),
                    lender_credits DECIMAL(10, 2),
                    rate_options JSONB,
                    source VARCHAR(50) DEFAULT 'optimal_blue',
                    is_mock BOOLEAN DEFAULT FALSE,
                    fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    expires_at TIMESTAMP,
                    raw_response JSONB
                )""",
                # Indexes
                "CREATE INDEX IF NOT EXISTS idx_rate_targets_mum_client ON rate_monitor_targets(mum_client_id)",
                "CREATE INDEX IF NOT EXISTS idx_rate_targets_status ON rate_monitor_targets(status)",
                "CREATE INDEX IF NOT EXISTS idx_rate_targets_active ON rate_monitor_targets(is_active) WHERE is_active = TRUE",
                "CREATE INDEX IF NOT EXISTS idx_rate_targets_auto_call ON rate_monitor_targets(auto_call_enabled) WHERE auto_call_enabled = TRUE",
                "CREATE INDEX IF NOT EXISTS idx_rate_history_target ON rate_monitor_history(target_id)",
                "CREATE INDEX IF NOT EXISTS idx_rate_history_client ON rate_monitor_history(mum_client_id)",
                "CREATE INDEX IF NOT EXISTS idx_rate_history_timestamp ON rate_monitor_history(check_timestamp DESC)",
                "CREATE INDEX IF NOT EXISTS idx_rate_history_threshold_met ON rate_monitor_history(threshold_met) WHERE threshold_met = TRUE",
                "CREATE INDEX IF NOT EXISTS idx_rate_alerts_target ON rate_monitor_alerts(target_id)",
                "CREATE INDEX IF NOT EXISTS idx_rate_alerts_client ON rate_monitor_alerts(mum_client_id)",
                "CREATE INDEX IF NOT EXISTS idx_rate_alerts_status ON rate_monitor_alerts(status)",
                "CREATE INDEX IF NOT EXISTS idx_rate_alerts_pending ON rate_monitor_alerts(status) WHERE status = 'pending'",
                "CREATE INDEX IF NOT EXISTS idx_rate_alerts_created ON rate_monitor_alerts(created_at DESC)",
                "CREATE INDEX IF NOT EXISTS idx_rate_cache_key ON optimal_blue_rate_cache(cache_key)",
                "CREATE INDEX IF NOT EXISTS idx_rate_cache_expires ON optimal_blue_rate_cache(expires_at)",
                "CREATE INDEX IF NOT EXISTS idx_rate_cache_scenario ON optimal_blue_rate_cache(loan_type, loan_term, credit_score)",
                # Trigger function
                """CREATE OR REPLACE FUNCTION update_rate_monitor_updated_at()
                RETURNS TRIGGER AS $$
                BEGIN
                    NEW.updated_at = CURRENT_TIMESTAMP;
                    RETURN NEW;
                END;
                $$ language 'plpgsql'""",
                "DROP TRIGGER IF EXISTS rate_targets_updated_at ON rate_monitor_targets",
                """CREATE TRIGGER rate_targets_updated_at
                    BEFORE UPDATE ON rate_monitor_targets
                    FOR EACH ROW EXECUTE FUNCTION update_rate_monitor_updated_at()""",
                "DROP TRIGGER IF EXISTS rate_alerts_updated_at ON rate_monitor_alerts",
                """CREATE TRIGGER rate_alerts_updated_at
                    BEFORE UPDATE ON rate_monitor_alerts
                    FOR EACH ROW EXECUTE FUNCTION update_rate_monitor_updated_at()"""
            ]

            tables_created = []
            for sql in sql_commands:
                try:
                    db.execute(sql_text(sql))
                    db.commit()
                    # Track table creations
                    if "CREATE TABLE" in sql:
                        table_name = sql.split("CREATE TABLE IF NOT EXISTS ")[1].split(" ")[0].strip()
                        tables_created.append(table_name)
                except Exception as cmd_error:
                    logger.warning(f"SQL command warning: {cmd_error}")
                    db.rollback()

            logger.info(f"Rate Monitor migration completed. Tables: {tables_created}")
            return {
                "success": True,
                "message": "Rate Monitor tables created successfully",
                "tables_created": tables_created
            }

        except Exception as e:
            logger.error(f"Rate Monitor migration failed: {e}")
            db.rollback()
            return {
                "success": False,
                "message": "Migration failed",
                "error": "Internal server error"
            }


    @app.post("/api/v1/migrations/add-rate-monitor-columns")
    async def add_rate_monitor_columns_migration(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
        """Migration: Add standalone borrower columns to rate_monitor_targets table"""
        try:
            from sqlalchemy import text as sql_text

            sql_commands = [
                "ALTER TABLE rate_monitor_targets ADD COLUMN IF NOT EXISTS borrower_name VARCHAR(255)",
                "ALTER TABLE rate_monitor_targets ADD COLUMN IF NOT EXISTS borrower_phone VARCHAR(50)",
                "ALTER TABLE rate_monitor_targets ADD COLUMN IF NOT EXISTS borrower_email VARCHAR(255)",
                "ALTER TABLE rate_monitor_targets ADD COLUMN IF NOT EXISTS current_rate NUMERIC(5,3)",
                "ALTER TABLE rate_monitor_targets ADD COLUMN IF NOT EXISTS current_loan_amount NUMERIC(12,2)",
                "ALTER TABLE rate_monitor_targets DROP CONSTRAINT IF EXISTS rate_monitor_targets_mum_client_id_fkey",
            ]

            results = []
            for sql in sql_commands:
                try:
                    db.execute(sql_text(sql))
                    db.commit()
                    results.append({"sql": sql[:50] + "...", "status": "OK"})
                except Exception as e:
                    db.rollback()
                    results.append({"sql": sql[:50] + "...", "status": "SKIP", "error": "Internal server error"[:100]})

            return {
                "success": True,
                "message": "Rate Monitor columns migration completed",
                "results": results
            }
        except Exception as e:
            logger.error(f"Rate Monitor columns migration failed: {e}")
            return {"success": False, "error": "Internal server error"}


    @app.post("/api/v1/migrations/add-workflow-system")
    async def add_workflow_system_migration(
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user),
    ):
        """
        Migration: Add complete Active Loan Workflow System tables
        Creates workflow_rules, workflow_tasks, theme_day_*, last_mile_*, ai_analysis tables
        """
        try:
            logger.info("Running migration: add workflow system tables")
            tables_created = []

            # 1. Workflow Rules
            result = db.execute(text("""
                SELECT table_name FROM information_schema.tables
                WHERE table_schema = 'public' AND table_name = 'workflow_rules'
            """))
            if not result.fetchone():
                db.execute(text("""
                    CREATE TABLE workflow_rules (
                        id SERIAL PRIMARY KEY,
                        rule_name VARCHAR(200) NOT NULL,
                        trigger_field VARCHAR(100) NOT NULL,
                        rule_type VARCHAR(50) NOT NULL,
                        action_description TEXT NOT NULL,
                        assigned_role VARCHAR(50),
                        timing_offset INTEGER DEFAULT 0,
                        priority VARCHAR(20) DEFAULT 'medium',
                        ai_action JSONB,
                        conditions JSONB,
                        active BOOLEAN DEFAULT true,
                        company_id INTEGER,
                        created_at TIMESTAMP DEFAULT NOW(),
                        updated_at TIMESTAMP DEFAULT NOW()
                    )
                """))
                db.execute(text("CREATE INDEX idx_workflow_rules_trigger ON workflow_rules(trigger_field)"))
                db.execute(text("CREATE INDEX idx_workflow_rules_active ON workflow_rules(active)"))
                tables_created.append("workflow_rules")

            # 2. Workflow Tasks
            result = db.execute(text("""
                SELECT table_name FROM information_schema.tables
                WHERE table_schema = 'public' AND table_name = 'workflow_tasks'
            """))
            if not result.fetchone():
                db.execute(text("""
                    CREATE TABLE workflow_tasks (
                        id SERIAL PRIMARY KEY,
                        loan_id INTEGER REFERENCES loans(id),
                        rule_id INTEGER,
                        task_title VARCHAR(300) NOT NULL,
                        task_description TEXT,
                        assigned_to INTEGER REFERENCES users(id),
                        assigned_role VARCHAR(50),
                        due_date DATE,
                        status VARCHAR(50) DEFAULT 'pending',
                        priority VARCHAR(20) DEFAULT 'medium',
                        created_by_system BOOLEAN DEFAULT true,
                        trigger_date DATE,
                        trigger_field VARCHAR(100),
                        completed_at TIMESTAMP,
                        completed_by INTEGER REFERENCES users(id),
                        notes TEXT,
                        parent_workflow VARCHAR(100),
                        created_at TIMESTAMP DEFAULT NOW(),
                        updated_at TIMESTAMP DEFAULT NOW()
                    )
                """))
                db.execute(text("CREATE INDEX idx_workflow_tasks_loan ON workflow_tasks(loan_id)"))
                db.execute(text("CREATE INDEX idx_workflow_tasks_status ON workflow_tasks(status)"))
                db.execute(text("CREATE INDEX idx_workflow_tasks_due ON workflow_tasks(due_date)"))
                tables_created.append("workflow_tasks")

            # 3. Workflow Alerts
            result = db.execute(text("""
                SELECT table_name FROM information_schema.tables
                WHERE table_schema = 'public' AND table_name = 'workflow_alerts'
            """))
            if not result.fetchone():
                db.execute(text("""
                    CREATE TABLE workflow_alerts (
                        id SERIAL PRIMARY KEY,
                        loan_id INTEGER REFERENCES loans(id),
                        alert_type VARCHAR(50),
                        alert_message TEXT,
                        alert_level VARCHAR(20),
                        triggered_by VARCHAR(100),
                        triggered_field VARCHAR(100),
                        acknowledged BOOLEAN DEFAULT false,
                        acknowledged_by INTEGER REFERENCES users(id),
                        acknowledged_at TIMESTAMP,
                        auto_resolved BOOLEAN DEFAULT false,
                        resolved_at TIMESTAMP,
                        created_at TIMESTAMP DEFAULT NOW()
                    )
                """))
                db.execute(text("CREATE INDEX idx_workflow_alerts_loan ON workflow_alerts(loan_id)"))
                db.execute(text("CREATE INDEX idx_workflow_alerts_ack ON workflow_alerts(acknowledged)"))
                tables_created.append("workflow_alerts")

            # 4. Theme Day Config
            result = db.execute(text("""
                SELECT table_name FROM information_schema.tables
                WHERE table_schema = 'public' AND table_name = 'theme_day_config'
            """))
            if not result.fetchone():
                db.execute(text("""
                    CREATE TABLE theme_day_config (
                        id SERIAL PRIMARY KEY,
                        company_id INTEGER,
                        enabled BOOLEAN DEFAULT true,
                        assigned_role VARCHAR(50),
                        assigned_user_id INTEGER REFERENCES users(id),
                        auto_send_enabled BOOLEAN DEFAULT false,
                        send_day_of_week INTEGER DEFAULT 1,
                        send_time TIME DEFAULT '09:00:00',
                        include_lo_on_emails BOOLEAN DEFAULT true,
                        skip_holidays BOOLEAN DEFAULT true,
                        created_at TIMESTAMP DEFAULT NOW(),
                        updated_at TIMESTAMP DEFAULT NOW()
                    )
                """))
                tables_created.append("theme_day_config")

            # 5. Theme Day Schedule
            result = db.execute(text("""
                SELECT table_name FROM information_schema.tables
                WHERE table_schema = 'public' AND table_name = 'theme_day_schedule'
            """))
            if not result.fetchone():
                db.execute(text("""
                    CREATE TABLE theme_day_schedule (
                        id SERIAL PRIMARY KEY,
                        loan_id INTEGER REFERENCES loans(id),
                        disclosure_sent_date DATE NOT NULL,
                        closing_date DATE,
                        fast_closing BOOLEAN DEFAULT false,
                        theme_days_enabled BOOLEAN DEFAULT true,
                        paused BOOLEAN DEFAULT false,
                        paused_reason TEXT,
                        current_week INTEGER DEFAULT 0,
                        total_weeks_planned INTEGER,
                        created_at TIMESTAMP DEFAULT NOW(),
                        updated_at TIMESTAMP DEFAULT NOW()
                    )
                """))
                db.execute(text("CREATE INDEX idx_theme_schedule_loan ON theme_day_schedule(loan_id)"))
                tables_created.append("theme_day_schedule")

            # 6. Theme Day Messages
            result = db.execute(text("""
                SELECT table_name FROM information_schema.tables
                WHERE table_schema = 'public' AND table_name = 'theme_day_messages'
            """))
            if not result.fetchone():
                db.execute(text("""
                    CREATE TABLE theme_day_messages (
                        id SERIAL PRIMARY KEY,
                        loan_id INTEGER REFERENCES loans(id),
                        schedule_id INTEGER,
                        week_number INTEGER NOT NULL,
                        theme_name VARCHAR(100),
                        scheduled_send_date DATE NOT NULL,
                        actual_send_date TIMESTAMP,
                        ai_generated_content TEXT,
                        user_edited_content TEXT,
                        subject_line VARCHAR(200),
                        status VARCHAR(50) DEFAULT 'draft',
                        approved_by INTEGER REFERENCES users(id),
                        approved_at TIMESTAMP,
                        email_sent BOOLEAN DEFAULT false,
                        email_opened BOOLEAN DEFAULT false,
                        email_opened_at TIMESTAMP,
                        borrower_replied BOOLEAN DEFAULT false,
                        audit_flags JSONB,
                        created_at TIMESTAMP DEFAULT NOW(),
                        updated_at TIMESTAMP DEFAULT NOW()
                    )
                """))
                db.execute(text("CREATE INDEX idx_theme_messages_loan ON theme_day_messages(loan_id)"))
                db.execute(text("CREATE INDEX idx_theme_messages_status ON theme_day_messages(status)"))
                tables_created.append("theme_day_messages")

            # 7. Last Mile Calls
            result = db.execute(text("""
                SELECT table_name FROM information_schema.tables
                WHERE table_schema = 'public' AND table_name = 'last_mile_calls'
            """))
            if not result.fetchone():
                db.execute(text("""
                    CREATE TABLE last_mile_calls (
                        id SERIAL PRIMARY KEY,
                        loan_id INTEGER REFERENCES loans(id),
                        assigned_concierge_id INTEGER REFERENCES users(id),
                        scheduled_date TIMESTAMP,
                        completed_date TIMESTAMP,
                        call_duration_minutes INTEGER,
                        cd_status_reviewed BOOLEAN DEFAULT false,
                        wire_instructions_obtained BOOLEAN DEFAULT false,
                        closing_details_confirmed BOOLEAN DEFAULT false,
                        cd_reviewed BOOLEAN DEFAULT false,
                        wire_instructions_sent BOOLEAN DEFAULT false,
                        hybrid_closing_opted_in BOOLEAN DEFAULT false,
                        post_closing_call_scheduled BOOLEAN DEFAULT false,
                        borrower_confidence_level INTEGER,
                        borrower_sentiment VARCHAR(50),
                        outstanding_concerns TEXT,
                        ai_talking_points JSONB,
                        ai_analysis JSONB,
                        follow_up_email_sent BOOLEAN DEFAULT false,
                        created_at TIMESTAMP DEFAULT NOW(),
                        updated_at TIMESTAMP DEFAULT NOW()
                    )
                """))
                db.execute(text("CREATE INDEX idx_last_mile_loan ON last_mile_calls(loan_id)"))
                tables_created.append("last_mile_calls")

            # 8. Last Mile Tasks
            result = db.execute(text("""
                SELECT table_name FROM information_schema.tables
                WHERE table_schema = 'public' AND table_name = 'last_mile_tasks'
            """))
            if not result.fetchone():
                db.execute(text("""
                    CREATE TABLE last_mile_tasks (
                        id SERIAL PRIMARY KEY,
                        last_mile_call_id INTEGER,
                        loan_id INTEGER REFERENCES loans(id),
                        task_category VARCHAR(50),
                        task_description TEXT,
                        assigned_to INTEGER REFERENCES users(id),
                        status VARCHAR(50) DEFAULT 'pending',
                        due_date TIMESTAMP,
                        completed_at TIMESTAMP,
                        notes TEXT,
                        created_at TIMESTAMP DEFAULT NOW()
                    )
                """))
                tables_created.append("last_mile_tasks")

            # 9. Post Closing Calls
            result = db.execute(text("""
                SELECT table_name FROM information_schema.tables
                WHERE table_schema = 'public' AND table_name = 'post_closing_calls'
            """))
            if not result.fetchone():
                db.execute(text("""
                    CREATE TABLE post_closing_calls (
                        id SERIAL PRIMARY KEY,
                        loan_id INTEGER REFERENCES loans(id),
                        concierge_id INTEGER REFERENCES users(id),
                        scheduled_date TIMESTAMP,
                        completed_date TIMESTAMP,
                        experience_rating INTEGER,
                        experience_feedback TEXT,
                        mum_opted_in BOOLEAN DEFAULT false,
                        review_requested BOOLEAN DEFAULT false,
                        review_completed BOOLEAN DEFAULT false,
                        referrals_received INTEGER DEFAULT 0,
                        notes TEXT,
                        created_at TIMESTAMP DEFAULT NOW(),
                        updated_at TIMESTAMP DEFAULT NOW()
                    )
                """))
                tables_created.append("post_closing_calls")

            # 10. AI Analysis
            result = db.execute(text("""
                SELECT table_name FROM information_schema.tables
                WHERE table_schema = 'public' AND table_name = 'ai_analysis'
            """))
            if not result.fetchone():
                db.execute(text("""
                    CREATE TABLE ai_analysis (
                        id SERIAL PRIMARY KEY,
                        loan_id INTEGER REFERENCES loans(id),
                        analysis_type VARCHAR(100),
                        analysis_trigger VARCHAR(100),
                        input_data JSONB,
                        prompt_used TEXT,
                        ai_response TEXT,
                        parsed_response JSONB,
                        confidence_score DECIMAL(3,2),
                        recommendations JSONB,
                        risks_identified JSONB,
                        execution_time_ms INTEGER,
                        created_at TIMESTAMP DEFAULT NOW()
                    )
                """))
                db.execute(text("CREATE INDEX idx_ai_analysis_loan ON ai_analysis(loan_id)"))
                tables_created.append("ai_analysis")

            # 11. Workflow Execution Log
            result = db.execute(text("""
                SELECT table_name FROM information_schema.tables
                WHERE table_schema = 'public' AND table_name = 'workflow_execution_log'
            """))
            if not result.fetchone():
                db.execute(text("""
                    CREATE TABLE workflow_execution_log (
                        id SERIAL PRIMARY KEY,
                        loan_id INTEGER REFERENCES loans(id),
                        rule_id INTEGER,
                        trigger_field VARCHAR(100),
                        trigger_value TEXT,
                        action_type VARCHAR(50),
                        execution_status VARCHAR(50),
                        execution_result JSONB,
                        error_message TEXT,
                        execution_time_ms INTEGER,
                        created_at TIMESTAMP DEFAULT NOW()
                    )
                """))
                tables_created.append("workflow_execution_log")

            db.commit()

            if tables_created:
                return {
                    "success": True,
                    "message": f"Successfully created workflow system tables: {', '.join(tables_created)}",
                    "tables_created": tables_created
                }
            else:
                return {
                    "success": True,
                    "message": "All workflow system tables already exist",
                    "tables_created": []
                }

        except Exception as e:
            logger.error(f"Workflow migration failed: {e}")
            db.rollback()
            return {
                "success": False,
                "message": "Migration failed",
                "error": "Internal server error"
            }


    @app.post("/api/v1/migrations/seed-demo-caller-id")
    async def seed_demo_caller_id(
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
    ):
        """
        Migration: Seed a demo verified caller ID for the current user
        This allows the Power Dialer to work without actual telephony verification
        """
        try:
            # Check if user already has a verified caller ID
            existing = db.query(VerifiedCallerId).filter(
                VerifiedCallerId.user_id == current_user.id,
                VerifiedCallerId.verification_status == "verified"
            ).first()

            if existing:
                return {
                    "success": True,
                    "message": f"User already has verified caller ID: {existing.phone_number}",
                    "caller_id": existing.phone_number
                }

            # Create a demo verified caller ID
            demo_phone = "+18434169589"  # Demo telephony number
            caller_id = VerifiedCallerId(
                user_id=current_user.id,
                phone_number=demo_phone,
                friendly_name="Demo Business Line",
                provider_sid="demo_sid_for_testing",
                verification_status="verified"
            )
            db.add(caller_id)

            # Also update the user's settings to use this caller ID
            settings = db.query(AgentTelephonySettings).filter(
                AgentTelephonySettings.user_id == current_user.id
            ).first()

            if settings:
                settings.business_caller_id = demo_phone
            else:
                settings = AgentTelephonySettings(
                    user_id=current_user.id,
                    business_caller_id=demo_phone,
                    dialer_enabled=True
                )
                db.add(settings)

            db.commit()

            return {
                "success": True,
                "message": "Demo caller ID created successfully",
                "caller_id": demo_phone
            }

        except Exception as e:
            logger.error(f"Error seeding demo caller ID: {e}")
            db.rollback()
            return {
                "success": False,
                "error": "Internal server error"
            }


    @app.post("/api/v1/migrations/seed-workflow-rules")
    async def seed_workflow_rules_migration(
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user),
    ):
        """
        Migration: Seed default workflow rules for Active Loan Workflow System
        """
        try:
            # First, add missing columns if they don't exist
            alter_statements = [
                "ALTER TABLE workflow_rules ADD COLUMN IF NOT EXISTS trigger_type VARCHAR(100)",
                "ALTER TABLE workflow_rules ADD COLUMN IF NOT EXISTS trigger_config JSONB",
                "ALTER TABLE workflow_rules ADD COLUMN IF NOT EXISTS action_type VARCHAR(100)",
                "ALTER TABLE workflow_rules ADD COLUMN IF NOT EXISTS action_config JSONB",
                "ALTER TABLE workflow_rules ADD COLUMN IF NOT EXISTS is_active BOOLEAN DEFAULT true",
            ]
            for stmt in alter_statements:
                try:
                    db.execute(text(stmt))
                except Exception as e:
                    logger.warning(f"Error adding column (may already exist): {e}")
            db.commit()

            # Check if rules already exist
            result = db.execute(text("SELECT COUNT(*) FROM workflow_rules"))
            count = result.scalar()
            if count > 0:
                return {"success": True, "message": f"Workflow rules already seeded ({count} rules)"}

            # Default workflow rules
            rules = [
                # Stage-based triggers
                ("Processing Started", "stage_entered", {"stage": "processing"}, "create_task",
                 {"task_type": "document_collection", "title": "Collect processing documents", "due_in_days": 1, "priority": "high"}),
                ("Underwriting Started", "stage_entered", {"stage": "underwriting"}, "create_alert",
                 {"alert_type": "milestone", "message": "Loan entered underwriting", "severity": "low"}),
                ("Clear to Close", "stage_entered", {"stage": "clear_to_close"}, "create_task",
                 {"task_type": "closing_prep", "title": "Prepare closing documents", "due_in_days": 2, "priority": "high"}),

                # Document tracking
                ("Missing Appraisal", "missing_document", {"document_field": "appraisal_received_date"}, "create_alert",
                 {"alert_type": "document", "message": "Appraisal not yet received", "severity": "medium"}),
                ("Missing Title", "missing_document", {"document_field": "title_received_date"}, "create_alert",
                 {"alert_type": "document", "message": "Title work not received", "severity": "medium"}),
                ("Missing HOI", "missing_document", {"document_field": "hoi_received_date"}, "create_alert",
                 {"alert_type": "document", "message": "Homeowner insurance not received", "severity": "medium"}),

                # Date-based triggers
                ("Closing Approaching 7 Days", "date_approaching", {"date_field": "estimated_closing_date", "days_before": 7}, "create_task",
                 {"task_type": "closing_prep", "title": "7-day closing checklist", "due_in_days": 1, "priority": "high"}),
                ("Closing Approaching 3 Days", "date_approaching", {"date_field": "estimated_closing_date", "days_before": 3}, "create_alert",
                 {"alert_type": "urgent", "message": "Closing in 3 days - verify all clear", "severity": "high"}),
            ]

            import json
            for i, (name, trigger_type, trigger_config, action_type, action_config) in enumerate(rules):
                db.execute(text("""
                    INSERT INTO workflow_rules
                    (rule_name, trigger_field, rule_type, action_description,
                     trigger_type, trigger_config, action_type, action_config, priority)
                    VALUES (:name, :trigger_field, :rule_type, :action_desc,
                            :trigger_type, CAST(:trigger_config AS jsonb),
                            :action_type, CAST(:action_config AS jsonb), :priority)
                """), {
                    "name": name,
                    "trigger_field": trigger_type,
                    "rule_type": action_type,
                    "action_desc": action_config.get("title", action_config.get("message", "Workflow action")),
                    "trigger_type": trigger_type,
                    "trigger_config": json.dumps(trigger_config),
                    "action_type": action_type,
                    "action_config": json.dumps(action_config),
                    "priority": 100 - i
                })

            db.commit()
            return {
                "success": True,
                "message": f"Successfully seeded {len(rules)} workflow rules",
                "rules_created": len(rules)
            }

        except Exception as e:
            logger.error(f"Workflow rules seeding failed: {e}")
            db.rollback()
            return {"success": False, "error": "Internal server error"}


    @app.post("/api/v1/migrations/add-workflow-sla-system")
    async def add_workflow_sla_system_migration(
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user),
    ):
        """
        Migration: Add SLA Workflow Task Generation System

        Creates the complete database schema for SLA-driven workflow task generation:
        - New enum types (workflow_instance_status, workflow_task_status, etc.)
        - workflow_instances table for tracking workflow lifecycles
        - Extended workflow_task_instances with AI confidence and routing
        - workflow_ai_confidence table for AI decision tracking
        - lead_workflow_role_assignments and loan_workflow_role_assignments tables
        - Column additions to tasks, roles, leads, and workflow_configurations
        - Performance indexes and RLS policies

        This is Phase 1 of the SLA Workflow System implementation.
        """
        try:
            logger.info("Running migration: add SLA workflow system tables")

            from migrations.add_workflow_sla_system import run_migration, check_migration_status

            # Check if migration is already applied
            status = check_migration_status(db)
            if status['fully_applied']:
                return {
                    "success": True,
                    "message": "SLA Workflow System migration already applied",
                    "status": status
                }

            # Run the migration
            results = run_migration(db)

            if results['success']:
                return {
                    "success": True,
                    "message": "SLA Workflow System migration completed successfully",
                    "enums_created": results.get('enums_created', []),
                    "tables_created": results.get('tables_created', []),
                    "columns_added": results.get('columns_added', []),
                    "indexes_created": results.get('indexes_created', []),
                    "warnings": results.get('warnings', [])
                }
            else:
                return {
                    "success": False,
                    "message": "SLA Workflow System migration failed",
                    "errors": results.get('errors', []),
                    "warnings": results.get('warnings', [])
                }

        except Exception as e:
            logger.error(f"SLA Workflow System migration failed: {e}")
            db.rollback()
            return {
                "success": False,
                "message": "Migration failed",
                "error": "Internal server error"
            }


    @app.post("/api/v1/migrations/add-ab-testing-tables")
    async def add_ab_testing_tables_migration(
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
    ):
        """
        Migration: Add A/B testing tables for experiment management
        Creates 5 tables: experiments, variants, assignments, results, insights
        """
        try:
            logger.info(f"Running migration: add A/B testing tables (user: {current_user.id})")

            # Check if tables already exist
            result = db.execute(text("""
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'public'
                AND table_name = 'ab_experiments'
            """))

            if result.fetchone():
                return {
                    "success": True,
                    "message": "A/B testing tables already exist",
                    "already_exists": True
                }

            # Create all A/B testing tables
            sql_commands = [
                # 1. Experiments table
                """
                CREATE TABLE ab_experiments (
                    id SERIAL PRIMARY KEY,
                    name VARCHAR(255) NOT NULL,
                    description TEXT,
                    experiment_type VARCHAR(50) NOT NULL,
                    status VARCHAR(50) NOT NULL DEFAULT 'draft',
                    target_percentage FLOAT DEFAULT 100.0,
                    target_user_segment VARCHAR(100),
                    primary_metric VARCHAR(100) NOT NULL,
                    secondary_metrics JSON,
                    min_sample_size INTEGER DEFAULT 100,
                    confidence_level FLOAT DEFAULT 0.95,
                    winning_variant_id INTEGER,
                    winner_declared_at TIMESTAMP WITH TIME ZONE,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    started_at TIMESTAMP WITH TIME ZONE,
                    ended_at TIMESTAMP WITH TIME ZONE,
                    created_by_user_id INTEGER REFERENCES users(id),
                    experiment_metadata JSON
                )
                """,

                # 2. Variants table
                """
                CREATE TABLE ab_variants (
                    id SERIAL PRIMARY KEY,
                    experiment_id INTEGER NOT NULL REFERENCES ab_experiments(id) ON DELETE CASCADE,
                    name VARCHAR(100) NOT NULL,
                    description TEXT,
                    is_control BOOLEAN DEFAULT FALSE,
                    traffic_allocation FLOAT DEFAULT 50.0,
                    config JSON NOT NULL,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                )
                """,

                # 3. Assignments table
                """
                CREATE TABLE ab_assignments (
                    id SERIAL PRIMARY KEY,
                    experiment_id INTEGER NOT NULL REFERENCES ab_experiments(id) ON DELETE CASCADE,
                    variant_id INTEGER NOT NULL REFERENCES ab_variants(id) ON DELETE CASCADE,
                    user_id INTEGER REFERENCES users(id),
                    session_id VARCHAR(255),
                    assigned_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    assignment_method VARCHAR(50) DEFAULT 'random'
                )
                """,

                # 4. Results table
                """
                CREATE TABLE ab_results (
                    id SERIAL PRIMARY KEY,
                    experiment_id INTEGER NOT NULL REFERENCES ab_experiments(id) ON DELETE CASCADE,
                    variant_id INTEGER NOT NULL REFERENCES ab_variants(id) ON DELETE CASCADE,
                    user_id INTEGER REFERENCES users(id),
                    session_id VARCHAR(255),
                    metric_name VARCHAR(100) NOT NULL,
                    metric_value FLOAT NOT NULL,
                    context JSON,
                    recorded_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                )
                """,

                # 5. Insights table
                """
                CREATE TABLE ab_insights (
                    id SERIAL PRIMARY KEY,
                    experiment_id INTEGER NOT NULL REFERENCES ab_experiments(id) ON DELETE CASCADE,
                    analysis_date TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    variant_stats JSON,
                    p_value FLOAT,
                    is_significant BOOLEAN DEFAULT FALSE,
                    confidence_interval JSON,
                    recommended_winner_id INTEGER REFERENCES ab_variants(id),
                    recommendation_confidence FLOAT,
                    recommendation_reason TEXT,
                    sufficient_sample_size BOOLEAN DEFAULT FALSE,
                    current_sample_size INTEGER,
                    required_sample_size INTEGER,
                    analysis_metadata JSON
                )
                """,
            ]

            # Execute table creation
            for sql in sql_commands:
                db.execute(text(sql))

            # Create indices
            indices = [
                "CREATE INDEX idx_ab_experiments_status ON ab_experiments(status)",
                "CREATE INDEX idx_ab_experiments_type ON ab_experiments(experiment_type)",
                "CREATE INDEX idx_ab_assignments_experiment ON ab_assignments(experiment_id)",
                "CREATE INDEX idx_ab_assignments_user ON ab_assignments(user_id)",
                "CREATE INDEX idx_ab_assignments_session ON ab_assignments(session_id)",
                "CREATE INDEX idx_ab_results_experiment ON ab_results(experiment_id)",
                "CREATE INDEX idx_ab_results_variant ON ab_results(variant_id)",
                "CREATE INDEX idx_ab_results_metric ON ab_results(metric_name)",
                "CREATE INDEX idx_ab_results_recorded ON ab_results(recorded_at)",
                "CREATE INDEX idx_ab_insights_experiment ON ab_insights(experiment_id)",
            ]

            for index_sql in indices:
                db.execute(text(index_sql))

            # Add foreign key constraint for winning_variant_id
            db.execute(text("""
                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM pg_constraint
                        WHERE conname = 'ab_experiments_winning_variant_fkey'
                    ) THEN
                        ALTER TABLE ab_experiments
                        ADD CONSTRAINT ab_experiments_winning_variant_fkey
                        FOREIGN KEY (winning_variant_id) REFERENCES ab_variants(id);
                    END IF;
                END $$
            """))

            db.commit()

            logger.info("Successfully created A/B testing tables with indices and constraints")

            return {
                "success": True,
                "message": "Successfully created A/B testing tables (5 tables, 10 indices)",
                "tables_created": ["ab_experiments", "ab_variants", "ab_assignments", "ab_results", "ab_insights"],
                "already_exists": False
            }

        except Exception as e:
            logger.error(f"A/B testing migration failed: {e}")
            db.rollback()
            return {
                "success": False,
                "message": "Migration failed",
                "error": "Internal server error"
            }

    @app.post("/api/v1/migrations/add-onboarding-tables")
    async def add_onboarding_tables_migration(
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
    ):
        """
        Migration: Add onboarding tables and user verification fields
        Creates onboarding_progress, onboarding_errors, verification_tokens tables
        and adds onboarding fields to users table
        """
        try:
            logger.info(f"Running migration: add onboarding tables (user: {current_user.id})")

            migration_results = []

            # Add fields to users table
            logger.info("Adding fields to users table...")
            db.execute(text("""
                ALTER TABLE users
                ADD COLUMN IF NOT EXISTS phone VARCHAR(20),
                ADD COLUMN IF NOT EXISTS nmls_number VARCHAR(50),
                ADD COLUMN IF NOT EXISTS business_address VARCHAR(500),
                ADD COLUMN IF NOT EXISTS current_role VARCHAR(100),
                ADD COLUMN IF NOT EXISTS business_hours JSON,
                ADD COLUMN IF NOT EXISTS email_verified_at TIMESTAMP,
                ADD COLUMN IF NOT EXISTS phone_verified_at TIMESTAMP;
            """))
            migration_results.append("Added fields to users table")

            # Create indexes on users table
            db.execute(text("CREATE INDEX IF NOT EXISTS idx_users_nmls_number ON users(nmls_number);"))
            db.execute(text("CREATE INDEX IF NOT EXISTS idx_users_email_verified_at ON users(email_verified_at);"))
            db.execute(text("CREATE INDEX IF NOT EXISTS idx_users_phone_verified_at ON users(phone_verified_at);"))
            migration_results.append("Created indexes on users table")

            # Create onboarding_progress table
            logger.info("Creating onboarding_progress table...")
            db.execute(text("""
                CREATE TABLE IF NOT EXISTS onboarding_progress (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
                    current_step INTEGER NOT NULL DEFAULT 1,
                    step_1_data JSON,
                    step_2_data JSON,
                    step_3_data JSON,
                    step_4_data JSON,
                    step_5_data JSON,
                    step_6_data JSON,
                    step_7_data JSON,
                    step_8_data JSON,
                    step_9_data JSON,
                    step_10_data JSON,
                    completed_at TIMESTAMP,
                    last_updated TIMESTAMP DEFAULT NOW(),
                    created_at TIMESTAMP DEFAULT NOW()
                );
            """))
            migration_results.append("Created onboarding_progress table")

            # Create indexes on onboarding_progress
            db.execute(text("CREATE INDEX IF NOT EXISTS idx_onboarding_progress_user_id ON onboarding_progress(user_id);"))
            db.execute(text("CREATE INDEX IF NOT EXISTS idx_onboarding_progress_current_step ON onboarding_progress(current_step);"))
            migration_results.append("Created indexes on onboarding_progress")

            # Create onboarding_errors table
            logger.info("Creating onboarding_errors table...")
            db.execute(text("""
                CREATE TABLE IF NOT EXISTS onboarding_errors (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    error_code VARCHAR(20) NOT NULL,
                    step_number INTEGER NOT NULL,
                    error_message TEXT NOT NULL,
                    error_context JSON,
                    user_action VARCHAR(50),
                    created_at TIMESTAMP DEFAULT NOW()
                );
            """))
            migration_results.append("Created onboarding_errors table")

            # Create indexes on onboarding_errors
            db.execute(text("CREATE INDEX IF NOT EXISTS idx_onboarding_errors_user_id ON onboarding_errors(user_id);"))
            db.execute(text("CREATE INDEX IF NOT EXISTS idx_onboarding_errors_error_code ON onboarding_errors(error_code);"))
            db.execute(text("CREATE INDEX IF NOT EXISTS idx_onboarding_errors_step_number ON onboarding_errors(step_number);"))
            db.execute(text("CREATE INDEX IF NOT EXISTS idx_onboarding_errors_created_at ON onboarding_errors(created_at);"))
            migration_results.append("Created indexes on onboarding_errors")

            # Create verification_tokens table
            logger.info("Creating verification_tokens table...")
            db.execute(text("""
                CREATE TABLE IF NOT EXISTS verification_tokens (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    token_type VARCHAR(20) NOT NULL,
                    token VARCHAR(10) NOT NULL,
                    expires_at TIMESTAMP NOT NULL,
                    used_at TIMESTAMP,
                    created_at TIMESTAMP DEFAULT NOW()
                );
            """))
            migration_results.append("Created verification_tokens table")

            # Create indexes on verification_tokens
            db.execute(text("CREATE INDEX IF NOT EXISTS idx_verification_tokens_user_id ON verification_tokens(user_id);"))
            db.execute(text("CREATE INDEX IF NOT EXISTS idx_verification_tokens_token ON verification_tokens(token);"))
            db.execute(text("CREATE INDEX IF NOT EXISTS idx_verification_tokens_expires_at ON verification_tokens(expires_at);"))
            migration_results.append("Created indexes on verification_tokens")

            db.commit()

            logger.info("Successfully completed onboarding tables migration")

            return {
                "success": True,
                "message": "Successfully completed onboarding tables migration",
                "steps": migration_results
            }

        except Exception as e:
            logger.error(f"Onboarding tables migration failed: {e}")
            db.rollback()
            return {
                "success": False,
                "message": "Migration failed",
                "error": "Internal server error"
            }

    @app.post("/api/v1/migrations/add-ai-receptionist-dashboard-tables")
    async def add_ai_receptionist_dashboard_tables_migration(
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
    ):
        """
        Migration: Add AI Receptionist Dashboard tables
        Creates 6 tables: activity, metrics_daily, skills, errors, system_health, conversations
        """
        try:
            logger.info(f"Running migration: add AI Receptionist Dashboard tables (user: {current_user.id})")

            # Check if tables already exist
            result = db.execute(text("""
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'public'
                AND table_name = 'ai_receptionist_activity'
            """))

            if result.fetchone():
                return {
                    "success": True,
                    "message": "AI Receptionist Dashboard tables already exist",
                    "already_exists": True
                }

            # Create all AI Receptionist Dashboard tables
            sql_commands = [
                # 1. Activity table
                """
                CREATE TABLE ai_receptionist_activity (
                    id VARCHAR(36) PRIMARY KEY,
                    timestamp TIMESTAMP WITH TIME ZONE NOT NULL,
                    client_id VARCHAR(255),
                    client_name VARCHAR(255),
                    client_phone VARCHAR(50),
                    client_email VARCHAR(255),
                    action_type VARCHAR(100) NOT NULL,
                    channel VARCHAR(50),
                    message_in TEXT,
                    message_out TEXT,
                    confidence_score FLOAT,
                    ai_version VARCHAR(50),
                    lead_stage VARCHAR(100),
                    assigned_to VARCHAR(255),
                    outcome_status VARCHAR(100),
                    conversation_id VARCHAR(255),
                    transcript_url VARCHAR(500),
                    extra_data JSON
                )
                """,

                # 2. Daily metrics table
                """
                CREATE TABLE ai_receptionist_metrics_daily (
                    date DATE PRIMARY KEY,
                    total_conversations INTEGER DEFAULT 0,
                    inbound_calls INTEGER DEFAULT 0,
                    inbound_texts INTEGER DEFAULT 0,
                    outbound_messages INTEGER DEFAULT 0,
                    response_time_avg_seconds FLOAT,
                    response_time_p95_seconds FLOAT,
                    appointments_scheduled INTEGER DEFAULT 0,
                    forms_completed INTEGER DEFAULT 0,
                    loan_apps_initiated INTEGER DEFAULT 0,
                    lead_updates INTEGER DEFAULT 0,
                    task_updates INTEGER DEFAULT 0,
                    documents_requested INTEGER DEFAULT 0,
                    escalations INTEGER DEFAULT 0,
                    ai_confusion_count INTEGER DEFAULT 0,
                    successful_resolutions INTEGER DEFAULT 0,
                    lead_qualification_rate FLOAT,
                    appointment_show_rate FLOAT,
                    ai_coverage_percentage FLOAT,
                    estimated_revenue_created FLOAT,
                    saved_labor_hours FLOAT,
                    cost_per_interaction FLOAT,
                    avg_confidence_score FLOAT,
                    error_rate FLOAT,
                    extra_data JSON
                )
                """,

                # 3. Skills table
                """
                CREATE TABLE ai_receptionist_skills (
                    id VARCHAR(36) PRIMARY KEY,
                    skill_name VARCHAR(255) NOT NULL UNIQUE,
                    skill_category VARCHAR(100),
                    description TEXT,
                    accuracy_score FLOAT,
                    accuracy_score_7day FLOAT,
                    accuracy_score_30day FLOAT,
                    trend_7day FLOAT,
                    trend_30day FLOAT,
                    trend_direction VARCHAR(20),
                    usage_count INTEGER DEFAULT 0,
                    success_count INTEGER DEFAULT 0,
                    failure_count INTEGER DEFAULT 0,
                    needs_retraining BOOLEAN DEFAULT FALSE,
                    last_trained_at TIMESTAMP WITH TIME ZONE,
                    last_updated TIMESTAMP WITH TIME ZONE,
                    extra_data JSON
                )
                """,

                # 4. Errors table
                """
                CREATE TABLE ai_receptionist_errors (
                    id VARCHAR(36) PRIMARY KEY,
                    timestamp TIMESTAMP WITH TIME ZONE NOT NULL,
                    error_type VARCHAR(100),
                    severity VARCHAR(20),
                    context TEXT,
                    conversation_snippet TEXT,
                    conversation_id VARCHAR(255),
                    root_cause TEXT,
                    recommended_fix TEXT,
                    auto_fix_proposed TEXT,
                    needs_human_review BOOLEAN DEFAULT FALSE,
                    reviewed_by VARCHAR(255),
                    reviewed_at TIMESTAMP WITH TIME ZONE,
                    resolution_status VARCHAR(50) DEFAULT 'unresolved',
                    resolution_notes TEXT,
                    trained_into_model BOOLEAN DEFAULT FALSE,
                    training_data_id VARCHAR(255),
                    extra_data JSON
                )
                """,

                # 5. System health table
                """
                CREATE TABLE ai_receptionist_system_health (
                    component_name VARCHAR(255) PRIMARY KEY,
                    status VARCHAR(50) NOT NULL DEFAULT 'unknown',
                    latency_ms INTEGER,
                    error_rate FLOAT,
                    uptime_percentage FLOAT,
                    last_checked TIMESTAMP WITH TIME ZONE,
                    last_success TIMESTAMP WITH TIME ZONE,
                    last_failure TIMESTAMP WITH TIME ZONE,
                    consecutive_failures INTEGER DEFAULT 0,
                    alert_sent BOOLEAN DEFAULT FALSE,
                    alert_sent_at TIMESTAMP WITH TIME ZONE,
                    notes TEXT,
                    endpoint_url VARCHAR(500),
                    extra_data JSON
                )
                """,

                # 6. Conversations table
                """
                CREATE TABLE ai_receptionist_conversations (
                    id VARCHAR(36) PRIMARY KEY,
                    started_at TIMESTAMP WITH TIME ZONE NOT NULL,
                    ended_at TIMESTAMP WITH TIME ZONE,
                    duration_seconds INTEGER,
                    client_id VARCHAR(255),
                    client_name VARCHAR(255),
                    client_phone VARCHAR(50),
                    client_email VARCHAR(255),
                    channel VARCHAR(50),
                    direction VARCHAR(20),
                    transcript TEXT,
                    transcript_json JSON,
                    summary TEXT,
                    intent_detected VARCHAR(100),
                    sentiment VARCHAR(50),
                    key_topics JSON,
                    outcome VARCHAR(100),
                    escalated_to VARCHAR(255),
                    follow_up_required BOOLEAN DEFAULT FALSE,
                    follow_up_date TIMESTAMP WITH TIME ZONE,
                    avg_confidence_score FLOAT,
                    total_turns INTEGER,
                    recording_url VARCHAR(500),
                    extra_data JSON
                )
                """,
            ]

            # Execute table creation
            for sql in sql_commands:
                db.execute(text(sql))

            # Create indices
            indices = [
                "CREATE INDEX idx_activity_timestamp ON ai_receptionist_activity(timestamp DESC)",
                "CREATE INDEX idx_activity_client ON ai_receptionist_activity(client_id)",
                "CREATE INDEX idx_activity_type ON ai_receptionist_activity(action_type)",
                "CREATE INDEX idx_activity_client_timestamp ON ai_receptionist_activity(client_id, timestamp DESC)",
                "CREATE INDEX idx_activity_type_timestamp ON ai_receptionist_activity(action_type, timestamp DESC)",
                "CREATE INDEX idx_error_timestamp ON ai_receptionist_errors(timestamp DESC)",
                "CREATE INDEX idx_error_type ON ai_receptionist_errors(error_type)",
                "CREATE INDEX idx_error_status ON ai_receptionist_errors(resolution_status)",
                "CREATE INDEX idx_error_needs_review ON ai_receptionist_errors(needs_human_review)",
                "CREATE INDEX idx_conversation_started ON ai_receptionist_conversations(started_at DESC)",
                "CREATE INDEX idx_conversation_client ON ai_receptionist_conversations(client_id)",
                "CREATE INDEX idx_conversation_outcome ON ai_receptionist_conversations(outcome)",
                "CREATE INDEX idx_conversation_client_started ON ai_receptionist_conversations(client_id, started_at DESC)",
            ]

            for index_sql in indices:
                db.execute(text(index_sql))

            db.commit()

            logger.info("Successfully created AI Receptionist Dashboard tables with indices")

            return {
                "success": True,
                "message": "Successfully created AI Receptionist Dashboard tables (6 tables, 13 indices)",
                "tables_created": [
                    "ai_receptionist_activity",
                    "ai_receptionist_metrics_daily",
                    "ai_receptionist_skills",
                    "ai_receptionist_errors",
                    "ai_receptionist_system_health",
                    "ai_receptionist_conversations"
                ],
                "already_exists": False
            }

        except Exception as e:
            logger.error(f"AI Receptionist Dashboard migration failed: {e}")
            db.rollback()
            return {
                "success": False,
                "message": "Migration failed",
                "error": "Internal server error"
            }

    @app.post("/api/v1/migrations/add-voicemail-system")
    async def add_voicemail_system_migration(
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
    ):
        """
        Migration: Add Voicemail Drop System tables
        Creates 4 tables: voicemail_drops, voicemail_templates, voicemail_campaigns, voicemail_events
        Inserts 5 default templates
        """
        try:
            logger.info(f"Running migration: add Voicemail System tables (user: {current_user.id})")

            # Check if tables already exist
            result = db.execute(text("""
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'public'
                AND table_name = 'voicemail_drops'
            """))

            if result.fetchone():
                return {
                    "success": True,
                    "message": "Voicemail System tables already exist",
                    "already_exists": True
                }

            # Read and execute migration SQL
            migration_path = os.path.join(os.path.dirname(__file__), "migrations", "add_voicemail_system.sql")

            with open(migration_path, 'r') as f:
                migration_sql = f.read()

            # Split by semicolons and execute each statement
            statements = [stmt.strip() for stmt in migration_sql.split(';') if stmt.strip()]

            for statement in statements:
                if statement:
                    db.execute(text(statement))

            db.commit()

            logger.info("Successfully created Voicemail System tables with default templates")

            return {
                "success": True,
                "message": "Successfully created Voicemail System (4 tables, 16 indices, 5 default templates)",
                "tables_created": [
                    "voicemail_drops",
                    "voicemail_templates",
                    "voicemail_campaigns",
                    "voicemail_events"
                ],
                "default_templates": [
                    "Closing Disclosure Ready",
                    "Document Request",
                    "Rate Lock Expiration",
                    "Application Status Update",
                    "Appointment Reminder"
                ],
                "already_exists": False
            }

        except Exception as e:
            logger.error(f"Voicemail System migration failed: {e}")
            db.rollback()
            return {
                "success": False,
                "message": "Migration failed",
                "error": "Internal server error"
            }

    @app.post("/api/v1/migrations/fix-voicemail-drops-columns")
    async def fix_voicemail_drops_columns_migration(
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
    ):
        """
        Migration: Fix voicemail_drops table to add missing columns from new schema
        """
        try:
            logger.info(f"Running migration: fix voicemail_drops columns (user: {current_user.id})")

            # Read and execute migration SQL
            migration_path = os.path.join(os.path.dirname(__file__), "migrations", "fix_voicemail_drops_columns.sql")

            with open(migration_path, 'r') as f:
                migration_sql = f.read()

            # Execute the migration (it contains DO $$ blocks that handle checking for existing columns)
            db.execute(text(migration_sql))
            db.commit()

            logger.info("Successfully fixed voicemail_drops table columns")

            return {
                "success": True,
                "message": "Successfully added missing columns to voicemail_drops table"
            }

        except Exception as e:
            logger.error(f"Voicemail drops column fix migration failed: {e}")
            db.rollback()
            return {
                "success": False,
                "message": "Migration failed",
                "error": "Internal server error"
            }

    # ========================================================================
    # ADMIN MIGRATION ENDPOINTS
    # ========================================================================

    @app.post("/api/v1/admin/run-migration")
    async def run_database_migration(
        migration_name: str,
        api_key: str = Header(None, alias="X-API-Key")
    ):
        """Run a database migration (protected by CRON_API_KEY)."""
        import os
        from pathlib import Path

        # Verify API key
        expected_key = os.getenv("CRON_API_KEY")
        if not expected_key or api_key != expected_key:
            raise HTTPException(status_code=403, detail="Invalid API key")

        # Validate migration name (prevent path traversal)
        if not migration_name.replace("_", "").replace("-", "").isalnum():
            raise HTTPException(status_code=400, detail="Invalid migration name")

        migration_path = Path(__file__).parent / "migrations" / f"{migration_name}.sql"
        if not migration_path.exists():
            raise HTTPException(status_code=404, detail=f"Migration '{migration_name}' not found")

        try:
            sql = migration_path.read_text()

            # Execute the migration
            with engine.connect() as conn:
                # Split by semicolons but be careful with DO blocks
                conn.execute(text(sql))
                conn.commit()

            return {"status": "success", "migration": migration_name, "message": "Migration completed successfully"}
        except Exception as e:
            logger.error(f"Migration failed: {e}")
            raise HTTPException(status_code=500, detail="Migration failed")


    @app.post("/api/v1/public/migrations/add-followupboss-tables", response_model=None)
    async def add_followupboss_tables_migration(
        migration_key: str = "",
        db: Session = Depends(get_db)
    ):
        """Run the Follow Up Boss tables migration using existing db connection."""
        if migration_key != "fub-migration-2026":
            raise HTTPException(status_code=403, detail="Invalid migration key")

        try:
            # Run migrations using the existing database session
            migrations = [
                ("fub_user_connections", """
                    CREATE TABLE IF NOT EXISTS fub_user_connections (
                        id SERIAL PRIMARY KEY,
                        user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                        api_key_encrypted TEXT NOT NULL,
                        fub_user_id INTEGER,
                        fub_user_email VARCHAR(255),
                        fub_user_name VARCHAR(255),
                        webhook_secret VARCHAR(64),
                        webhook_url VARCHAR(500),
                        sync_enabled BOOLEAN DEFAULT TRUE,
                        sync_notes BOOLEAN DEFAULT TRUE,
                        sync_stages BOOLEAN DEFAULT TRUE,
                        sync_lead_updates BOOLEAN DEFAULT TRUE,
                        last_sync_at TIMESTAMP WITH TIME ZONE,
                        last_sync_status VARCHAR(50),
                        last_error TEXT,
                        created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                        updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                        UNIQUE(user_id)
                    )
                """),
                ("fub_lead_mappings", """
                    CREATE TABLE IF NOT EXISTS fub_lead_mappings (
                        id SERIAL PRIMARY KEY,
                        connection_id INTEGER NOT NULL REFERENCES fub_user_connections(id) ON DELETE CASCADE,
                        fub_person_id INTEGER NOT NULL,
                        lead_id INTEGER NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
                        sync_hash VARCHAR(64),
                        last_synced_at TIMESTAMP WITH TIME ZONE,
                        sync_direction VARCHAR(20) DEFAULT 'bidirectional',
                        fub_stage VARCHAR(100),
                        fub_assigned_to VARCHAR(255),
                        fub_updated_at TIMESTAMP WITH TIME ZONE,
                        created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                        updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                    )
                """),
                ("fub_sync_events", """
                    CREATE TABLE IF NOT EXISTS fub_sync_events (
                        id SERIAL PRIMARY KEY,
                        connection_id INTEGER NOT NULL REFERENCES fub_user_connections(id) ON DELETE CASCADE,
                        event_type VARCHAR(50) NOT NULL,
                        direction VARCHAR(20) NOT NULL,
                        fub_entity_type VARCHAR(50),
                        fub_entity_id INTEGER,
                        crm_entity_type VARCHAR(50),
                        crm_entity_id INTEGER,
                        status VARCHAR(20) NOT NULL DEFAULT 'pending',
                        error_message TEXT,
                        request_payload JSONB,
                        response_payload JSONB,
                        created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                        completed_at TIMESTAMP WITH TIME ZONE
                    )
                """),
                ("fub_stage_mappings", """
                    CREATE TABLE IF NOT EXISTS fub_stage_mappings (
                        id SERIAL PRIMARY KEY,
                        connection_id INTEGER NOT NULL REFERENCES fub_user_connections(id) ON DELETE CASCADE,
                        fub_stage_name VARCHAR(100) NOT NULL,
                        fub_stage_id INTEGER,
                        crm_stage VARCHAR(50) NOT NULL,
                        is_auto_mapped BOOLEAN DEFAULT TRUE,
                        confidence_score INTEGER DEFAULT 100,
                        created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                        updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                    )
                """),
            ]

            results = []
            for name, sql in migrations:
                try:
                    db.execute(text(sql))
                    db.commit()
                    results.append(f"\u2705 {name}")
                    logger.info(f"FUB migration: Created {name}")
                except Exception as e:
                    if "already exists" in str(e).lower():
                        results.append(f"\u23ed\ufe0f {name} (exists)")
                    else:
                        results.append(f"\u274c {name}: {str(e)}")
                        logger.error(f"FUB migration error for {name}: {e}")

            # Create indexes
            indexes = [
                "CREATE INDEX IF NOT EXISTS ix_fub_connections_user_id ON fub_user_connections(user_id)",
                "CREATE INDEX IF NOT EXISTS ix_fub_mappings_connection_person ON fub_lead_mappings(connection_id, fub_person_id)",
                "CREATE INDEX IF NOT EXISTS ix_fub_mappings_lead ON fub_lead_mappings(lead_id)",
                "CREATE INDEX IF NOT EXISTS ix_fub_events_connection_created ON fub_sync_events(connection_id, created_at DESC)",
                "CREATE INDEX IF NOT EXISTS ix_fub_events_status ON fub_sync_events(status)",
                "CREATE INDEX IF NOT EXISTS ix_fub_stages_connection_fub ON fub_stage_mappings(connection_id, fub_stage_name)",
            ]
            for idx_sql in indexes:
                try:
                    db.execute(text(idx_sql))
                    db.commit()
                except Exception as e:
                    logger.warning(f"Error creating index (may already exist): {e}")

            return {"status": "success", "message": "Follow Up Boss tables created successfully", "details": results}

        except Exception as e:
            logger.error(f"FUB migration error: {e}")
            raise HTTPException(status_code=500, detail="Migration failed")


    @app.post("/api/v1/admin/add-loans-organization-column")
    async def add_loans_organization_column(
        migration_key: str = "",
        db: Session = Depends(get_db)
    ):
        """Add organization_id column to loans table if it doesn't exist."""
        if migration_key != "fix-loans-2026":
            raise HTTPException(status_code=403, detail="Invalid migration key")

        try:
            # Check if column exists
            check_result = db.execute(text("""
                SELECT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name = 'loans' AND column_name = 'organization_id'
                )
            """)).fetchone()

            column_exists = check_result[0] if check_result else False

            if column_exists:
                return {"status": "success", "message": "Column already exists", "action": "none"}

            # Add the column
            db.execute(text("ALTER TABLE loans ADD COLUMN organization_id INTEGER"))
            db.execute(text("CREATE INDEX IF NOT EXISTS ix_loans_organization_id ON loans(organization_id)"))
            db.commit()

            return {"status": "success", "message": "Column added successfully", "action": "created"}
        except Exception as e:
            logger.error(f"Add organization_id column failed: {e}")
            raise HTTPException(status_code=500, detail="Internal server error")


    @app.post("/api/v1/admin/fix-loan-associations")
    async def fix_loan_associations(
        user_email: str = "tloss@cmgfi.com",
        migration_key: str = "",
        db: Session = Depends(get_db)
    ):
        """Associate orphaned loans with a user's organization."""
        if migration_key != "fix-loans-2026":
            raise HTTPException(status_code=403, detail="Invalid migration key")

        try:
            # Find the user using raw SQL
            user_result = db.execute(
                text("SELECT id, email, organization_id FROM users WHERE email = :email"),
                {"email": user_email}
            ).fetchone()

            if not user_result:
                # List available users
                users_result = db.execute(text("SELECT id, email, organization_id FROM users")).fetchall()
                user_list = [{"id": u[0], "email": u[1], "org_id": u[2]} for u in users_result]
                return {"status": "error", "message": f"User {user_email} not found", "available_users": user_list}

            user_id = user_result[0]
            org_id = user_result[2]

            # Update ALL loans in this org - set loan_officer_id to this user
            result = db.execute(
                text("""
                    UPDATE loans
                    SET organization_id = :org_id, loan_officer_id = :user_id
                    WHERE organization_id = :org_id
                """),
                {"org_id": org_id, "user_id": user_id}
            )
            updated_count = result.rowcount

            db.commit()

            # Get total loans for this org
            total_result = db.execute(
                text("SELECT COUNT(*) FROM loans WHERE organization_id = :org_id"),
                {"org_id": org_id}
            ).fetchone()
            total = total_result[0] if total_result else 0

            return {
                "status": "success",
                "user_email": user_email,
                "user_id": user_id,
                "organization_id": org_id,
                "loans_updated": updated_count,
                "total_loans_for_org": total,
                "message": "Updated organization_id and loan_officer_id on loans"
            }
        except Exception as e:
            logger.error(f"Fix loan associations failed: {e}")
            raise HTTPException(status_code=500, detail="Internal server error")


    @app.post("/api/v1/admin/fix-task-assignments")
    async def fix_task_assignments(
        migration_key: str = "",
        db: Session = Depends(get_db)
    ):
        """Fix task assignments to match loan_officer_id for multi-tenancy."""
        if migration_key != "fix-loans-2026":
            raise HTTPException(status_code=403, detail="Invalid migration key")

        try:
            results = {}

            # Fix ai_tasks that are associated with loans
            ai_result = db.execute(text("""
                UPDATE ai_tasks
                SET assigned_to_id = loans.loan_officer_id
                FROM loans
                WHERE ai_tasks.loan_id = loans.id
                AND loans.loan_officer_id IS NOT NULL
                AND (ai_tasks.assigned_to_id IS NULL OR ai_tasks.assigned_to_id != loans.loan_officer_id)
            """))
            results["ai_tasks_fixed"] = ai_result.rowcount

            # Fix regular tasks that are associated with loans
            task_result = db.execute(text("""
                UPDATE tasks
                SET owner_id = loans.loan_officer_id
                FROM loans
                WHERE tasks.loan_id = loans.id
                AND loans.loan_officer_id IS NOT NULL
                AND (tasks.owner_id IS NULL OR tasks.owner_id != loans.loan_officer_id)
            """))
            results["regular_tasks_fixed"] = task_result.rowcount

            # Fix regular tasks that are associated with leads (use lead's owner_id)
            lead_task_result = db.execute(text("""
                UPDATE tasks
                SET owner_id = leads.owner_id
                FROM leads
                WHERE tasks.lead_id = leads.id
                AND leads.owner_id IS NOT NULL
                AND (tasks.owner_id IS NULL OR tasks.owner_id != leads.owner_id)
            """))
            results["lead_tasks_fixed"] = lead_task_result.rowcount

            db.commit()

            # Get summary of AI task assignments after fix
            ai_summary_result = db.execute(text("""
                SELECT u.email, COUNT(*) as count
                FROM ai_tasks t
                LEFT JOIN users u ON u.id = t.assigned_to_id
                GROUP BY u.email, t.assigned_to_id
            """)).fetchall()
            results["ai_tasks_by_user"] = [{"email": r[0], "count": r[1]} for r in ai_summary_result]

            # Get summary of regular task assignments after fix
            task_summary_result = db.execute(text("""
                SELECT u.email, COUNT(*) as count
                FROM tasks t
                LEFT JOIN users u ON u.id = t.owner_id
                GROUP BY u.email, t.owner_id
            """)).fetchall()
            results["regular_tasks_by_user"] = [{"email": r[0], "count": r[1]} for r in task_summary_result]

            return {
                "status": "success",
                **results,
                "message": "Fixed task assignments based on loan_officer_id and lead.owner_id"
            }
        except Exception as e:
            logger.error(f"Fix task assignments failed: {e}")
            raise HTTPException(status_code=500, detail="Internal server error")

    @app.post("/api/v1/public/migrations/enforce-recruiting-org-id", response_model=None)
    async def enforce_recruiting_org_id_migration(
        migration_key: str = "",
        db: Session = Depends(get_db)
    ):
        """Enforce organization_id NOT NULL on all recruiting tables."""
        if migration_key != "recruit-org-2026":
            raise HTTPException(status_code=403, detail="Invalid migration key")

        try:
            from migrations.enforce_recruiting_org_id import run_migration
            results = run_migration()
            return {"status": "success", **results}
        except Exception as e:
            import traceback
            tb = traceback.format_exc()
            logger.error(f"Recruiting org_id migration failed: {e}\n{tb}")
            return {"status": "error", "error": str(e), "traceback": tb}
