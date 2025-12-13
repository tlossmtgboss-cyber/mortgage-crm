"""
Migration: Add PURL System Tables (SQLite-compatible)
Creates essential PURL tables for local development with SQLite.

Usage:
    cd backend
    source venv/bin/activate
    python migrations/add_purl_system_sqlite.py
"""
import sys
sys.path.append('..')

from sqlalchemy import create_engine, text
import os
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Get database URL
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./mortgage_crm.db")
engine = create_engine(DATABASE_URL)


def run_migration():
    """Create PURL System tables (SQLite-compatible)"""

    sql_commands = [
        # 1. WORKSPACES - Persistent household identity
        """
        CREATE TABLE IF NOT EXISTS purl_workspaces (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            organization_id INTEGER,
            slug VARCHAR(255) NOT NULL,
            status VARCHAR(50) NOT NULL DEFAULT 'lead',
            display_name VARCHAR(500) NOT NULL,
            source VARCHAR(255),
            owner_user_id INTEGER,
            lead_at TIMESTAMP,
            application_at TIMESTAMP,
            active_loan_at TIMESTAMP,
            closing_at TIMESTAMP,
            post_close_at TIMESTAMP,
            meta_data TEXT DEFAULT '{}',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(organization_id, slug)
        );
        """,

        # 2. CONTACTS - People associated with workspace
        """
        CREATE TABLE IF NOT EXISTS purl_contacts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            organization_id INTEGER NOT NULL,
            workspace_id INTEGER NOT NULL,
            contact_type VARCHAR(50) NOT NULL,
            first_name VARCHAR(255) NOT NULL,
            last_name VARCHAR(255) NOT NULL,
            email VARCHAR(255),
            phone VARCHAR(50),
            auth_user_id INTEGER,
            auth_provider VARCHAR(50),
            meta_data TEXT DEFAULT '{}',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (workspace_id) REFERENCES purl_workspaces(id) ON DELETE CASCADE
        );
        """,

        # 3. APPLICATIONS
        """
        CREATE TABLE IF NOT EXISTS purl_applications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            organization_id INTEGER NOT NULL,
            workspace_id INTEGER NOT NULL,
            application_type VARCHAR(20) NOT NULL DEFAULT 'pre_qual',
            status VARCHAR(30) NOT NULL DEFAULT 'in_progress',
            version INTEGER NOT NULL DEFAULT 1,
            data TEXT DEFAULT '{}',
            derived TEXT DEFAULT '{}',
            validation_errors TEXT DEFAULT '[]',
            completeness_pct INTEGER DEFAULT 0,
            started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            submitted_at TIMESTAMP,
            approved_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (workspace_id) REFERENCES purl_workspaces(id) ON DELETE CASCADE,
            UNIQUE(workspace_id, application_type, version)
        );
        """,

        # 4. PURL LOANS
        """
        CREATE TABLE IF NOT EXISTS purl_loans (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            organization_id INTEGER NOT NULL,
            workspace_id INTEGER NOT NULL,
            application_id INTEGER,
            main_loan_id INTEGER,
            loan_number VARCHAR(100),
            status VARCHAR(30) NOT NULL DEFAULT 'active',
            loan_purpose VARCHAR(50),
            product_type VARCHAR(100),
            loan_amount DECIMAL(15, 2),
            interest_rate DECIMAL(6, 4),
            property_address TEXT,
            property_type VARCHAR(50),
            target_close_date DATE,
            actual_close_date DATE,
            los_loan_id VARCHAR(100),
            meta_data TEXT DEFAULT '{}',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (workspace_id) REFERENCES purl_workspaces(id) ON DELETE CASCADE,
            FOREIGN KEY (application_id) REFERENCES purl_applications(id)
        );
        """,

        # 5. DOCUMENTS
        """
        CREATE TABLE IF NOT EXISTS purl_documents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            organization_id INTEGER NOT NULL,
            workspace_id INTEGER NOT NULL,
            loan_id INTEGER,
            doc_type VARCHAR(100) NOT NULL,
            doc_category VARCHAR(50) NOT NULL,
            status VARCHAR(30) NOT NULL DEFAULT 'uploaded',
            file_name VARCHAR(500) NOT NULL,
            storage_key VARCHAR(1000) NOT NULL UNIQUE,
            size_bytes BIGINT NOT NULL,
            mime_type VARCHAR(255) NOT NULL,
            sha256 VARCHAR(64),
            uploaded_by_contact_id INTEGER,
            uploaded_by_user_id INTEGER,
            ocr_text TEXT,
            extracted_data TEXT,
            reviewed_by INTEGER,
            reviewed_at TIMESTAMP,
            review_notes TEXT,
            retention_policy VARCHAR(50) DEFAULT 'standard',
            legal_hold BOOLEAN DEFAULT 0,
            expires_at TIMESTAMP,
            delete_after TIMESTAMP,
            meta_data TEXT DEFAULT '{}',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (workspace_id) REFERENCES purl_workspaces(id) ON DELETE CASCADE,
            FOREIGN KEY (loan_id) REFERENCES purl_loans(id) ON DELETE CASCADE
        );
        """,

        # 6. MILESTONE DEFINITIONS
        """
        CREATE TABLE IF NOT EXISTS purl_milestone_definitions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            organization_id INTEGER NOT NULL,
            code VARCHAR(100) NOT NULL,
            stage VARCHAR(50) NOT NULL,
            display_name VARCHAR(255) NOT NULL,
            description TEXT,
            order_index INTEGER NOT NULL,
            sla_days INTEGER,
            sla_type VARCHAR(20) NOT NULL DEFAULT 'soft',
            grace_percent INTEGER DEFAULT 75,
            notify_on_start BOOLEAN DEFAULT 0,
            notify_on_complete BOOLEAN DEFAULT 1,
            notify_on_delay BOOLEAN DEFAULT 1,
            is_active BOOLEAN DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(organization_id, code)
        );
        """,

        # 7. LOAN MILESTONES
        """
        CREATE TABLE IF NOT EXISTS purl_loan_milestones (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            organization_id INTEGER NOT NULL,
            loan_id INTEGER NOT NULL,
            milestone_definition_id INTEGER NOT NULL,
            status VARCHAR(30) NOT NULL DEFAULT 'pending',
            due_at TIMESTAMP,
            started_at TIMESTAMP,
            completed_at TIMESTAMP,
            assigned_to INTEGER,
            completion_notes TEXT,
            delay_reason TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (loan_id) REFERENCES purl_loans(id) ON DELETE CASCADE,
            FOREIGN KEY (milestone_definition_id) REFERENCES purl_milestone_definitions(id),
            UNIQUE(loan_id, milestone_definition_id)
        );
        """,

        # 8. TASKS
        """
        CREATE TABLE IF NOT EXISTS purl_tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            organization_id INTEGER NOT NULL,
            workspace_id INTEGER,
            loan_id INTEGER,
            title VARCHAR(500) NOT NULL,
            description TEXT,
            task_type VARCHAR(50) DEFAULT 'general',
            status VARCHAR(30) NOT NULL DEFAULT 'open',
            priority VARCHAR(20) NOT NULL DEFAULT 'medium',
            assigned_to_user_id INTEGER,
            assigned_to_contact_id INTEGER,
            related_document_id INTEGER,
            related_milestone_id INTEGER,
            due_at TIMESTAMP,
            completed_at TIMESTAMP,
            completed_by_user_id INTEGER,
            completed_by_contact_id INTEGER,
            meta_data TEXT DEFAULT '{}',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (workspace_id) REFERENCES purl_workspaces(id) ON DELETE CASCADE,
            FOREIGN KEY (loan_id) REFERENCES purl_loans(id) ON DELETE CASCADE
        );
        """,

        # 9. MESSAGES
        """
        CREATE TABLE IF NOT EXISTS purl_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            organization_id INTEGER NOT NULL,
            workspace_id INTEGER NOT NULL,
            message_type VARCHAR(30) NOT NULL DEFAULT 'text',
            content TEXT NOT NULL,
            sender_type VARCHAR(20) NOT NULL,
            sender_user_id INTEGER,
            sender_contact_id INTEGER,
            related_document_id INTEGER,
            related_task_id INTEGER,
            is_read_by_borrower BOOLEAN DEFAULT 0,
            read_at TIMESTAMP,
            meta_data TEXT DEFAULT '{}',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (workspace_id) REFERENCES purl_workspaces(id) ON DELETE CASCADE
        );
        """,

        # 10. ACCESS TOKENS
        """
        CREATE TABLE IF NOT EXISTS purl_access_tokens (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            organization_id INTEGER NOT NULL,
            workspace_id INTEGER NOT NULL,
            token_hash VARCHAR(255) NOT NULL UNIQUE,
            token_prefix VARCHAR(50) NOT NULL,
            scope VARCHAR(20) NOT NULL DEFAULT 'read',
            status VARCHAR(20) NOT NULL DEFAULT 'active',
            contact_id INTEGER,
            expires_at TIMESTAMP,
            last_used_at TIMESTAMP,
            revoked_at TIMESTAMP,
            revoked_by INTEGER,
            revoked_reason TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            created_by INTEGER,
            FOREIGN KEY (workspace_id) REFERENCES purl_workspaces(id) ON DELETE CASCADE,
            FOREIGN KEY (contact_id) REFERENCES purl_contacts(id) ON DELETE SET NULL
        );
        """,

        # 11. DOCUMENT REQUESTS
        """
        CREATE TABLE IF NOT EXISTS purl_document_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            organization_id INTEGER NOT NULL,
            workspace_id INTEGER NOT NULL,
            loan_id INTEGER,
            document_type VARCHAR(100) NOT NULL,
            document_category VARCHAR(50) NOT NULL,
            description TEXT,
            status VARCHAR(30) NOT NULL DEFAULT 'pending',
            is_required BOOLEAN DEFAULT 1,
            requested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            requested_by INTEGER,
            due_date DATE,
            reminder_count INTEGER DEFAULT 0,
            last_reminder_at TIMESTAMP,
            received_document_id INTEGER,
            received_at TIMESTAMP,
            meta_data TEXT DEFAULT '{}',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (workspace_id) REFERENCES purl_workspaces(id) ON DELETE CASCADE,
            FOREIGN KEY (loan_id) REFERENCES purl_loans(id) ON DELETE CASCADE
        );
        """,

        # 12. Create indexes
        "CREATE INDEX IF NOT EXISTS idx_purl_workspaces_slug ON purl_workspaces(slug);",
        "CREATE INDEX IF NOT EXISTS idx_purl_contacts_workspace ON purl_contacts(workspace_id);",
        "CREATE INDEX IF NOT EXISTS idx_purl_contacts_email ON purl_contacts(email);",
        "CREATE INDEX IF NOT EXISTS idx_purl_loans_workspace ON purl_loans(workspace_id);",
        "CREATE INDEX IF NOT EXISTS idx_purl_documents_workspace ON purl_documents(workspace_id);",
        "CREATE INDEX IF NOT EXISTS idx_purl_documents_status ON purl_documents(status);",
        "CREATE INDEX IF NOT EXISTS idx_purl_tasks_workspace ON purl_tasks(workspace_id);",
        "CREATE INDEX IF NOT EXISTS idx_purl_messages_workspace ON purl_messages(workspace_id);",
    ]

    with engine.connect() as connection:
        for i, sql in enumerate(sql_commands):
            try:
                logger.info(f"Running SQL command {i + 1}/{len(sql_commands)}")
                connection.execute(text(sql))
                connection.commit()
            except Exception as e:
                logger.error(f"Error executing SQL command {i + 1}: {e}")
                connection.rollback()
                continue

    logger.info("PURL System tables (SQLite) created successfully!")


if __name__ == "__main__":
    run_migration()
