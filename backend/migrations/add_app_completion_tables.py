"""
Migration: Add Application Completion Orchestrator Tables

Creates tables for the Application Completion Orchestrator (ACO):
1. application_completeness_reviews — scores loan apps 0-100
2. missing_items — individual gaps found in an application
3. document_staging_requests — docs needed, staged, sent
4. borrower_communication_logs — all orchestration messages
5. appointment_coordinations — PA call scheduling
6. application_score_history — append-only score tracking

Run:      python migrations/add_app_completion_tables.py
Rollback: python migrations/add_app_completion_tables.py --rollback
"""

import logging
import os
import sys

from sqlalchemy import create_engine, text

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logger = logging.getLogger(__name__)


def get_database_url():
    """Get database URL from environment or .env file."""
    db_url = os.getenv("DATABASE_URL")
    if db_url:
        if db_url.startswith("postgres://"):
            db_url = db_url.replace("postgres://", "postgresql://", 1)
        return db_url

    env_path = os.path.join(os.path.dirname(__file__), '..', '.env')
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                if line.startswith('DATABASE_URL='):
                    return line.strip().split('=', 1)[1]

    return "postgresql://localhost:5432/perennia"


def run_migration(engine=None):
    """Create Application Completion Orchestrator tables if they don't exist."""
    if engine is None:
        database_url = get_database_url()
        engine = create_engine(database_url)

    with engine.connect() as conn:
        logger.info("Starting Application Completion Orchestrator migration...")
        print("[ACO] Starting Application Completion Orchestrator migration...")

        # =================================================================
        # TABLE 1: application_completeness_reviews
        # =================================================================

        print("[ACO] Creating application_completeness_reviews table...")
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS application_completeness_reviews (
                id SERIAL PRIMARY KEY,
                organization_id VARCHAR NOT NULL,
                loan_id VARCHAR NOT NULL,
                borrower_id VARCHAR,
                review_status VARCHAR DEFAULT 'PENDING',
                overall_score NUMERIC(5,2) DEFAULT 0,
                data_completeness_score NUMERIC(5,2) DEFAULT 0,
                data_consistency_score NUMERIC(5,2) DEFAULT 0,
                document_readiness_score NUMERIC(5,2) DEFAULT 0,
                complexity_score INTEGER DEFAULT 0,
                complexity_level VARCHAR DEFAULT 'LOW',
                confidence_score NUMERIC(5,2) DEFAULT 0,
                next_recommended_action VARCHAR,
                total_missing_items INTEGER DEFAULT 0,
                total_clarifications_needed INTEGER DEFAULT 0,
                total_documents_needed INTEGER DEFAULT 0,
                total_escalations INTEGER DEFAULT 0,
                items_resolved_by_ai INTEGER DEFAULT 0,
                items_resolved_by_staff INTEGER DEFAULT 0,
                ai_model_used VARCHAR,
                review_duration_ms INTEGER,
                review_summary TEXT,
                section_scores JSONB,
                triggered_by VARCHAR DEFAULT 'APPLICATION_SUBMITTED',
                assigned_to_user_id VARCHAR,
                assigned_to_queue VARCHAR,
                completed_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            )
        """))

        # =================================================================
        # TABLE 2: missing_items
        # =================================================================

        print("[ACO] Creating missing_items table...")
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS missing_items (
                id SERIAL PRIMARY KEY,
                organization_id VARCHAR NOT NULL,
                review_id INTEGER REFERENCES application_completeness_reviews(id),
                loan_id VARCHAR NOT NULL,
                item_type VARCHAR NOT NULL,
                severity VARCHAR DEFAULT 'MEDIUM',
                field_path VARCHAR,
                field_section VARCHAR,
                borrower_question TEXT,
                internal_note TEXT,
                resolution_method VARCHAR,
                status VARCHAR DEFAULT 'IDENTIFIED',
                source_engine VARCHAR,
                ai_confidence NUMERIC(5,2),
                current_value VARCHAR,
                resolved_value VARCHAR,
                resolved_by_user_id VARCHAR,
                resolved_by_type VARCHAR,
                sent_at TIMESTAMP,
                responded_at TIMESTAMP,
                resolved_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            )
        """))

        # =================================================================
        # TABLE 3: document_staging_requests
        # =================================================================

        print("[ACO] Creating document_staging_requests table...")
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS document_staging_requests (
                id SERIAL PRIMARY KEY,
                organization_id VARCHAR NOT NULL,
                review_id INTEGER REFERENCES application_completeness_reviews(id),
                loan_id VARCHAR NOT NULL,
                doc_type VARCHAR NOT NULL,
                doc_label VARCHAR NOT NULL,
                reason_code VARCHAR,
                reason_description TEXT,
                status VARCHAR DEFAULT 'IDENTIFIED',
                priority VARCHAR DEFAULT 'MEDIUM',
                staged_by_user_id VARCHAR,
                staged_at TIMESTAMP,
                sent_at TIMESTAMP,
                sent_channel VARCHAR,
                uploaded_at TIMESTAMP,
                uploaded_document_id VARCHAR,
                reviewed_at TIMESTAMP,
                reviewed_by_user_id VARCHAR,
                cleared_at TIMESTAMP,
                waived_at TIMESTAMP,
                waived_reason VARCHAR,
                due_date TIMESTAMP,
                borrower_notified BOOLEAN DEFAULT FALSE,
                portal_published BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            )
        """))

        # =================================================================
        # TABLE 4: borrower_communication_logs
        # =================================================================

        print("[ACO] Creating borrower_communication_logs table...")
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS borrower_communication_logs (
                id SERIAL PRIMARY KEY,
                organization_id VARCHAR NOT NULL,
                loan_id VARCHAR NOT NULL,
                review_id INTEGER REFERENCES application_completeness_reviews(id),
                missing_item_id INTEGER REFERENCES missing_items(id),
                channel VARCHAR NOT NULL,
                sender_type VARCHAR NOT NULL,
                message_intent VARCHAR,
                template_id VARCHAR,
                message_body TEXT NOT NULL,
                recipient_phone VARCHAR,
                recipient_email VARCHAR,
                delivery_status VARCHAR DEFAULT 'QUEUED',
                response_detected BOOLEAN DEFAULT FALSE,
                response_body TEXT,
                response_intent VARCHAR,
                response_confidence NUMERIC(5,2),
                sentiment VARCHAR,
                error_message VARCHAR,
                external_message_id VARCHAR,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            )
        """))

        # =================================================================
        # TABLE 5: appointment_coordinations
        # =================================================================

        print("[ACO] Creating appointment_coordinations table...")
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS appointment_coordinations (
                id SERIAL PRIMARY KEY,
                organization_id VARCHAR NOT NULL,
                loan_id VARCHAR NOT NULL,
                review_id INTEGER REFERENCES application_completeness_reviews(id),
                assigned_pa_user_id VARCHAR,
                assigned_lo_user_id VARCHAR,
                borrower_name VARCHAR,
                borrower_phone VARCHAR,
                borrower_email VARCHAR,
                proposed_windows JSONB,
                booked_start TIMESTAMP,
                booked_end TIMESTAMP,
                duration_minutes INTEGER DEFAULT 15,
                booking_status VARCHAR DEFAULT 'AVAILABILITY_REQUESTED',
                appointment_type VARCHAR DEFAULT 'APPLICATION_REVIEW',
                meeting_link VARCHAR,
                calendar_event_id VARCHAR,
                pre_call_brief TEXT,
                unresolved_items_count INTEGER DEFAULT 0,
                complexity_score INTEGER DEFAULT 0,
                borrower_confirmed BOOLEAN DEFAULT FALSE,
                pa_confirmed BOOLEAN DEFAULT FALSE,
                call_notes TEXT,
                items_resolved_in_call INTEGER DEFAULT 0,
                completed_at TIMESTAMP,
                cancelled_at TIMESTAMP,
                cancel_reason VARCHAR,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            )
        """))

        # =================================================================
        # TABLE 6: application_score_history (append-only)
        # =================================================================

        print("[ACO] Creating application_score_history table...")
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS application_score_history (
                id SERIAL PRIMARY KEY,
                organization_id VARCHAR NOT NULL,
                loan_id VARCHAR NOT NULL,
                review_id INTEGER REFERENCES application_completeness_reviews(id),
                prior_score NUMERIC(5,2),
                new_score NUMERIC(5,2),
                score_delta NUMERIC(5,2),
                reason VARCHAR NOT NULL,
                reason_detail TEXT,
                actor_type VARCHAR NOT NULL,
                actor_user_id VARCHAR,
                missing_item_id INTEGER REFERENCES missing_items(id),
                section_affected VARCHAR,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """))

        # =================================================================
        # INDEXES: application_completeness_reviews
        # =================================================================

        print("[ACO] Creating indexes for application_completeness_reviews...")

        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_acr_org_loan
            ON application_completeness_reviews (organization_id, loan_id)
        """))
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_acr_org_status
            ON application_completeness_reviews (organization_id, review_status)
        """))
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_acr_org_score
            ON application_completeness_reviews (organization_id, overall_score)
        """))
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_acr_org_queue_status
            ON application_completeness_reviews (organization_id, assigned_to_queue, review_status)
        """))

        # =================================================================
        # INDEXES: missing_items
        # =================================================================

        print("[ACO] Creating indexes for missing_items...")

        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_mi_org_loan
            ON missing_items (organization_id, loan_id)
        """))
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_mi_org_type_status
            ON missing_items (organization_id, item_type, status)
        """))
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_mi_org_severity_status
            ON missing_items (organization_id, severity, status)
        """))
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_mi_loan_field_path
            ON missing_items (loan_id, field_path)
        """))

        # =================================================================
        # INDEXES: document_staging_requests
        # =================================================================

        print("[ACO] Creating indexes for document_staging_requests...")

        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_dsr_org_loan
            ON document_staging_requests (organization_id, loan_id)
        """))
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_dsr_org_status_priority
            ON document_staging_requests (organization_id, status, priority)
        """))
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_dsr_loan_doc_type
            ON document_staging_requests (loan_id, doc_type)
        """))

        # =================================================================
        # INDEXES: borrower_communication_logs
        # =================================================================

        print("[ACO] Creating indexes for borrower_communication_logs...")

        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_bcl_org_loan
            ON borrower_communication_logs (organization_id, loan_id)
        """))
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_bcl_org_delivery_status
            ON borrower_communication_logs (organization_id, delivery_status)
        """))
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_bcl_org_created_at
            ON borrower_communication_logs (organization_id, created_at)
        """))

        # =================================================================
        # INDEXES: appointment_coordinations
        # =================================================================

        print("[ACO] Creating indexes for appointment_coordinations...")

        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_ac_org_loan
            ON appointment_coordinations (organization_id, loan_id)
        """))
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_ac_org_booking_status
            ON appointment_coordinations (organization_id, booking_status)
        """))
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_ac_org_booked_start
            ON appointment_coordinations (organization_id, booked_start)
        """))

        # =================================================================
        # INDEXES: application_score_history
        # =================================================================

        print("[ACO] Creating indexes for application_score_history...")

        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_ash_org_loan
            ON application_score_history (organization_id, loan_id)
        """))
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_ash_org_loan_created
            ON application_score_history (organization_id, loan_id, created_at)
        """))

        conn.commit()
        print("[ACO] Application Completion Orchestrator migration complete.")
        logger.info("Application Completion Orchestrator migration complete.")


def rollback_migration():
    """Rollback the migration (for development/testing)."""
    database_url = get_database_url()
    engine = create_engine(database_url)

    print("Rolling back Application Completion Orchestrator migration...")

    with engine.connect() as conn:
        # Drop indexes first (all use IF EXISTS for safety)
        index_names = [
            # application_completeness_reviews
            "ix_acr_org_loan",
            "ix_acr_org_status",
            "ix_acr_org_score",
            "ix_acr_org_queue_status",
            # missing_items
            "ix_mi_org_loan",
            "ix_mi_org_type_status",
            "ix_mi_org_severity_status",
            "ix_mi_loan_field_path",
            # document_staging_requests
            "ix_dsr_org_loan",
            "ix_dsr_org_status_priority",
            "ix_dsr_loan_doc_type",
            # borrower_communication_logs
            "ix_bcl_org_loan",
            "ix_bcl_org_delivery_status",
            "ix_bcl_org_created_at",
            # appointment_coordinations
            "ix_ac_org_loan",
            "ix_ac_org_booking_status",
            "ix_ac_org_booked_start",
            # application_score_history
            "ix_ash_org_loan",
            "ix_ash_org_loan_created",
        ]
        for idx in index_names:
            try:
                conn.execute(text(f"DROP INDEX IF EXISTS {idx}"))
                print(f"  Dropped index {idx}")
            except Exception as e:
                print(f"  Could not drop index {idx}: {e}")

        # Drop tables in reverse dependency order (children before parents)
        tables = [
            "application_score_history",
            "appointment_coordinations",
            "borrower_communication_logs",
            "document_staging_requests",
            "missing_items",
            "application_completeness_reviews",
        ]
        for tbl in tables:
            conn.execute(text(f"DROP TABLE IF EXISTS {tbl} CASCADE"))
            print(f"  Dropped table {tbl}")

        conn.commit()

    print("Rollback completed!")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--rollback":
        rollback_migration()
    else:
        run_migration()
