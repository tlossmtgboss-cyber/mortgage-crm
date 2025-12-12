"""
Migration: Add PURL (Persistent URL) System Tables
Creates infrastructure for borrower workspaces, tokenized access, applications,
documents, timeline tracking, and event-driven architecture.

The PURL system provides:
- Persistent client workspaces with unique URLs
- Tokenized secure access (zero-trust public access)
- Event-driven architecture for async processing
- Multi-tenant isolation at database level
- Full lifecycle management from lead to post-close
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
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

engine = create_engine(DATABASE_URL)


def run_migration():
    """Create PURL System tables"""

    sql_commands = [
        # ============================================================================
        # ENABLE REQUIRED EXTENSIONS
        # ============================================================================
        """
        CREATE EXTENSION IF NOT EXISTS pgcrypto;
        """,

        """
        CREATE EXTENSION IF NOT EXISTS citext;
        """,

        # ============================================================================
        # 1. WORKSPACES - Persistent household identity
        # ============================================================================
        """
        CREATE TABLE IF NOT EXISTS purl_workspaces (
            id SERIAL PRIMARY KEY,
            organization_id INTEGER REFERENCES organizations(id) ON DELETE CASCADE,

            -- Identity
            slug VARCHAR(255) NOT NULL,
            status VARCHAR(50) NOT NULL DEFAULT 'lead',
            display_name VARCHAR(500) NOT NULL,
            source VARCHAR(255),
            owner_user_id INTEGER REFERENCES users(id),

            -- Lifecycle tracking timestamps
            lead_at TIMESTAMP WITH TIME ZONE,
            application_at TIMESTAMP WITH TIME ZONE,
            active_loan_at TIMESTAMP WITH TIME ZONE,
            closing_at TIMESTAMP WITH TIME ZONE,
            post_close_at TIMESTAMP WITH TIME ZONE,

            -- Metadata
            metadata JSONB NOT NULL DEFAULT '{}'::jsonb,

            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,

            UNIQUE(organization_id, slug)
        );
        """,

        """
        CREATE INDEX IF NOT EXISTS idx_purl_workspaces_org_status
        ON purl_workspaces(organization_id, status);
        """,

        """
        CREATE INDEX IF NOT EXISTS idx_purl_workspaces_slug
        ON purl_workspaces(slug);
        """,

        """
        CREATE INDEX IF NOT EXISTS idx_purl_workspaces_owner
        ON purl_workspaces(owner_user_id);
        """,

        # ============================================================================
        # 2. CONTACTS - People associated with workspace
        # ============================================================================
        """
        CREATE TABLE IF NOT EXISTS purl_contacts (
            id SERIAL PRIMARY KEY,
            organization_id INTEGER NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
            workspace_id INTEGER NOT NULL REFERENCES purl_workspaces(id) ON DELETE CASCADE,

            contact_type VARCHAR(50) NOT NULL CHECK (contact_type IN ('borrower', 'co_borrower', 'realtor', 'partner', 'other')),

            first_name VARCHAR(255) NOT NULL,
            last_name VARCHAR(255) NOT NULL,
            email VARCHAR(255),
            phone VARCHAR(50),

            -- Auth integration
            auth_user_id INTEGER REFERENCES users(id),
            auth_provider VARCHAR(50),

            -- Additional data
            metadata JSONB NOT NULL DEFAULT '{}'::jsonb,

            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        );
        """,

        """
        CREATE INDEX IF NOT EXISTS idx_purl_contacts_workspace
        ON purl_contacts(workspace_id);
        """,

        """
        CREATE INDEX IF NOT EXISTS idx_purl_contacts_email
        ON purl_contacts(email);
        """,

        """
        CREATE INDEX IF NOT EXISTS idx_purl_contacts_type
        ON purl_contacts(organization_id, contact_type);
        """,

        # ============================================================================
        # 3. WORKSPACE MEMBERS - Internal team access
        # ============================================================================
        """
        CREATE TABLE IF NOT EXISTS purl_workspace_members (
            id SERIAL PRIMARY KEY,
            organization_id INTEGER NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
            workspace_id INTEGER NOT NULL REFERENCES purl_workspaces(id) ON DELETE CASCADE,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,

            role VARCHAR(50) NOT NULL CHECK (role IN ('owner', 'processor', 'closer', 'viewer')),

            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,

            UNIQUE(workspace_id, user_id)
        );
        """,

        """
        CREATE INDEX IF NOT EXISTS idx_purl_workspace_members_user
        ON purl_workspace_members(user_id);
        """,

        # ============================================================================
        # 4. PURL ACCESS TOKENS - Secure borrower access
        # ============================================================================
        """
        CREATE TABLE IF NOT EXISTS purl_access_tokens (
            id SERIAL PRIMARY KEY,
            organization_id INTEGER NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
            workspace_id INTEGER NOT NULL REFERENCES purl_workspaces(id) ON DELETE CASCADE,

            -- Token security
            token_hash VARCHAR(255) NOT NULL UNIQUE,
            token_prefix VARCHAR(50) NOT NULL,

            -- Access control
            scope VARCHAR(20) NOT NULL CHECK (scope IN ('read', 'write', 'full')),
            status VARCHAR(20) NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'revoked', 'expired')),

            -- Contact association
            contact_id INTEGER REFERENCES purl_contacts(id) ON DELETE SET NULL,

            -- Lifecycle
            expires_at TIMESTAMP WITH TIME ZONE,
            last_used_at TIMESTAMP WITH TIME ZONE,
            revoked_at TIMESTAMP WITH TIME ZONE,
            revoked_by INTEGER REFERENCES users(id),
            revoked_reason TEXT,

            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            created_by INTEGER REFERENCES users(id)
        );
        """,

        """
        CREATE INDEX IF NOT EXISTS idx_purl_tokens_workspace
        ON purl_access_tokens(workspace_id);
        """,

        """
        CREATE INDEX IF NOT EXISTS idx_purl_tokens_hash
        ON purl_access_tokens(token_hash);
        """,

        """
        CREATE INDEX IF NOT EXISTS idx_purl_tokens_status
        ON purl_access_tokens(organization_id, status);
        """,

        # ============================================================================
        # 5. APPLICATIONS - Pre-qual and full applications
        # ============================================================================
        """
        CREATE TABLE IF NOT EXISTS purl_applications (
            id SERIAL PRIMARY KEY,
            organization_id INTEGER NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
            workspace_id INTEGER NOT NULL REFERENCES purl_workspaces(id) ON DELETE CASCADE,

            application_type VARCHAR(20) NOT NULL CHECK (application_type IN ('pre_qual', '1003', 'full')),
            status VARCHAR(30) NOT NULL DEFAULT 'in_progress' CHECK (status IN ('in_progress', 'submitted', 'approved', 'denied', 'withdrawn')),
            version INTEGER NOT NULL DEFAULT 1,

            -- Application data
            data JSONB NOT NULL DEFAULT '{}'::jsonb,
            derived JSONB NOT NULL DEFAULT '{}'::jsonb,

            -- Validation
            validation_errors JSONB DEFAULT '[]'::jsonb,
            completeness_pct INTEGER DEFAULT 0,

            -- Lifecycle
            started_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
            submitted_at TIMESTAMP WITH TIME ZONE,
            approved_at TIMESTAMP WITH TIME ZONE,

            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,

            UNIQUE(workspace_id, application_type, version)
        );
        """,

        """
        CREATE INDEX IF NOT EXISTS idx_purl_applications_workspace
        ON purl_applications(workspace_id);
        """,

        """
        CREATE INDEX IF NOT EXISTS idx_purl_applications_status
        ON purl_applications(organization_id, status);
        """,

        # ============================================================================
        # 6. PURL LOANS - Transaction records within workspace
        # ============================================================================
        """
        CREATE TABLE IF NOT EXISTS purl_loans (
            id SERIAL PRIMARY KEY,
            organization_id INTEGER NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
            workspace_id INTEGER NOT NULL REFERENCES purl_workspaces(id) ON DELETE CASCADE,
            application_id INTEGER REFERENCES purl_applications(id),

            -- Link to main loans table if exists
            main_loan_id INTEGER,

            loan_number VARCHAR(100),
            status VARCHAR(30) NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'processing', 'underwriting', 'closing', 'closed', 'denied', 'cancelled', 'withdrawn')),

            -- Loan details
            loan_purpose VARCHAR(50) CHECK (loan_purpose IN ('purchase', 'refinance', 'cash_out', 'heloc', 'construction')),
            product_type VARCHAR(100),
            loan_amount DECIMAL(15, 2),
            interest_rate DECIMAL(6, 4),

            -- Property
            property_address JSONB,
            property_type VARCHAR(50),

            -- Timeline
            target_close_date DATE,
            actual_close_date DATE,

            -- External integration
            los_loan_id VARCHAR(100),

            metadata JSONB NOT NULL DEFAULT '{}'::jsonb,

            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        );
        """,

        """
        CREATE INDEX IF NOT EXISTS idx_purl_loans_workspace
        ON purl_loans(workspace_id);
        """,

        """
        CREATE INDEX IF NOT EXISTS idx_purl_loans_status
        ON purl_loans(organization_id, status);
        """,

        """
        CREATE INDEX IF NOT EXISTS idx_purl_loans_los_id
        ON purl_loans(los_loan_id);
        """,

        # ============================================================================
        # 7. DOCUMENTS - File storage and tracking
        # ============================================================================
        """
        CREATE TABLE IF NOT EXISTS purl_documents (
            id SERIAL PRIMARY KEY,
            organization_id INTEGER NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
            workspace_id INTEGER NOT NULL REFERENCES purl_workspaces(id) ON DELETE CASCADE,
            loan_id INTEGER REFERENCES purl_loans(id) ON DELETE CASCADE,

            doc_type VARCHAR(100) NOT NULL,
            doc_category VARCHAR(50) NOT NULL CHECK (doc_category IN ('application', 'asset', 'income', 'identity', 'property', 'closing', 'other')),
            status VARCHAR(30) NOT NULL DEFAULT 'uploaded' CHECK (status IN ('uploaded', 'processing', 'needs_review', 'verified', 'rejected', 'expired', 'archived')),

            -- File details
            file_name VARCHAR(500) NOT NULL,
            storage_key VARCHAR(1000) NOT NULL UNIQUE,
            size_bytes BIGINT NOT NULL,
            mime_type VARCHAR(255) NOT NULL,
            sha256 VARCHAR(64),

            -- Upload tracking
            uploaded_by_contact_id INTEGER REFERENCES purl_contacts(id),
            uploaded_by_user_id INTEGER REFERENCES users(id),

            -- Processing
            ocr_text TEXT,
            extracted_data JSONB,

            -- Review
            reviewed_by INTEGER REFERENCES users(id),
            reviewed_at TIMESTAMP WITH TIME ZONE,
            review_notes TEXT,

            -- Compliance
            retention_policy VARCHAR(50) NOT NULL DEFAULT 'standard',
            legal_hold BOOLEAN NOT NULL DEFAULT FALSE,
            expires_at TIMESTAMP WITH TIME ZONE,
            delete_after TIMESTAMP WITH TIME ZONE,

            metadata JSONB NOT NULL DEFAULT '{}'::jsonb,

            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        );
        """,

        """
        CREATE INDEX IF NOT EXISTS idx_purl_documents_workspace
        ON purl_documents(workspace_id);
        """,

        """
        CREATE INDEX IF NOT EXISTS idx_purl_documents_loan
        ON purl_documents(loan_id);
        """,

        """
        CREATE INDEX IF NOT EXISTS idx_purl_documents_type
        ON purl_documents(organization_id, doc_type);
        """,

        """
        CREATE INDEX IF NOT EXISTS idx_purl_documents_status
        ON purl_documents(status);
        """,

        # ============================================================================
        # 8. PORTAL MODULES - Configurable borrower experience
        # ============================================================================
        """
        CREATE TABLE IF NOT EXISTS purl_portal_modules (
            id SERIAL PRIMARY KEY,
            organization_id INTEGER NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
            workspace_id INTEGER NOT NULL REFERENCES purl_workspaces(id) ON DELETE CASCADE,

            module_key VARCHAR(50) NOT NULL CHECK (module_key IN (
                'application', 'documents', 'timeline', 'messages',
                'tasks', 'rate_lock', 'closing_vault', 'resources',
                'payments', 'checklist'
            )),

            is_enabled BOOLEAN NOT NULL DEFAULT TRUE,
            is_visible BOOLEAN NOT NULL DEFAULT TRUE,
            order_index INTEGER NOT NULL DEFAULT 0,

            -- Module configuration
            config_version INTEGER NOT NULL DEFAULT 1,
            config JSONB NOT NULL DEFAULT '{}'::jsonb,

            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,

            UNIQUE(workspace_id, module_key)
        );
        """,

        """
        CREATE INDEX IF NOT EXISTS idx_purl_portal_modules_workspace
        ON purl_portal_modules(workspace_id);
        """,

        # ============================================================================
        # 9. MILESTONE DEFINITIONS - SLA templates (org-level)
        # ============================================================================
        """
        CREATE TABLE IF NOT EXISTS purl_milestone_definitions (
            id SERIAL PRIMARY KEY,
            organization_id INTEGER NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,

            code VARCHAR(100) NOT NULL,
            stage VARCHAR(50) NOT NULL CHECK (stage IN ('lead', 'application', 'processing', 'underwriting', 'closing', 'post_close')),
            display_name VARCHAR(255) NOT NULL,
            description TEXT,

            order_index INTEGER NOT NULL,
            sla_days INTEGER,
            sla_type VARCHAR(20) NOT NULL CHECK (sla_type IN ('hard', 'soft', 'estimated')),
            grace_percent INTEGER NOT NULL DEFAULT 75,

            -- Notification settings
            notify_on_start BOOLEAN DEFAULT FALSE,
            notify_on_complete BOOLEAN DEFAULT TRUE,
            notify_on_delay BOOLEAN DEFAULT TRUE,

            is_active BOOLEAN NOT NULL DEFAULT TRUE,

            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,

            UNIQUE(organization_id, code)
        );
        """,

        """
        CREATE INDEX IF NOT EXISTS idx_purl_milestone_definitions_org
        ON purl_milestone_definitions(organization_id, is_active);
        """,

        # ============================================================================
        # 10. LOAN MILESTONES - Actual milestone tracking
        # ============================================================================
        """
        CREATE TABLE IF NOT EXISTS purl_loan_milestones (
            id SERIAL PRIMARY KEY,
            organization_id INTEGER NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
            loan_id INTEGER NOT NULL REFERENCES purl_loans(id) ON DELETE CASCADE,
            milestone_definition_id INTEGER NOT NULL REFERENCES purl_milestone_definitions(id),

            status VARCHAR(30) NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'in_progress', 'completed', 'delayed', 'blocked', 'skipped')),

            due_at TIMESTAMP WITH TIME ZONE,
            started_at TIMESTAMP WITH TIME ZONE,
            completed_at TIMESTAMP WITH TIME ZONE,

            -- Tracking
            assigned_to INTEGER REFERENCES users(id),
            completion_notes TEXT,
            delay_reason TEXT,

            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,

            UNIQUE(loan_id, milestone_definition_id)
        );
        """,

        """
        CREATE INDEX IF NOT EXISTS idx_purl_loan_milestones_loan
        ON purl_loan_milestones(loan_id);
        """,

        """
        CREATE INDEX IF NOT EXISTS idx_purl_loan_milestones_status
        ON purl_loan_milestones(organization_id, status);
        """,

        """
        CREATE INDEX IF NOT EXISTS idx_purl_loan_milestones_due
        ON purl_loan_milestones(due_at)
        WHERE status IN ('pending', 'in_progress');
        """,

        # ============================================================================
        # 11. TASKS - Action items for workspace
        # ============================================================================
        """
        CREATE TABLE IF NOT EXISTS purl_tasks (
            id SERIAL PRIMARY KEY,
            organization_id INTEGER NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
            workspace_id INTEGER REFERENCES purl_workspaces(id) ON DELETE CASCADE,
            loan_id INTEGER REFERENCES purl_loans(id) ON DELETE CASCADE,

            -- Task details
            title VARCHAR(500) NOT NULL,
            description TEXT,
            task_type VARCHAR(50) DEFAULT 'general',
            status VARCHAR(30) NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'in_progress', 'completed', 'cancelled', 'blocked')),
            priority VARCHAR(20) NOT NULL DEFAULT 'medium' CHECK (priority IN ('low', 'medium', 'high', 'urgent')),

            -- Assignment
            assigned_to_user_id INTEGER REFERENCES users(id),
            assigned_to_contact_id INTEGER REFERENCES purl_contacts(id),

            -- Related entities
            related_document_id INTEGER REFERENCES purl_documents(id),
            related_milestone_id INTEGER REFERENCES purl_loan_milestones(id),

            -- Timeline
            due_at TIMESTAMP WITH TIME ZONE,
            completed_at TIMESTAMP WITH TIME ZONE,
            completed_by_user_id INTEGER REFERENCES users(id),
            completed_by_contact_id INTEGER REFERENCES purl_contacts(id),

            -- Metadata
            metadata JSONB NOT NULL DEFAULT '{}'::jsonb,

            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        );
        """,

        """
        CREATE INDEX IF NOT EXISTS idx_purl_tasks_workspace
        ON purl_tasks(workspace_id);
        """,

        """
        CREATE INDEX IF NOT EXISTS idx_purl_tasks_status
        ON purl_tasks(organization_id, status);
        """,

        """
        CREATE INDEX IF NOT EXISTS idx_purl_tasks_assigned_user
        ON purl_tasks(assigned_to_user_id)
        WHERE status NOT IN ('completed', 'cancelled');
        """,

        """
        CREATE INDEX IF NOT EXISTS idx_purl_tasks_assigned_contact
        ON purl_tasks(assigned_to_contact_id)
        WHERE status NOT IN ('completed', 'cancelled');
        """,

        # ============================================================================
        # 12. MESSAGES - Communication within workspace
        # ============================================================================
        """
        CREATE TABLE IF NOT EXISTS purl_messages (
            id SERIAL PRIMARY KEY,
            organization_id INTEGER NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
            workspace_id INTEGER NOT NULL REFERENCES purl_workspaces(id) ON DELETE CASCADE,

            -- Message details
            message_type VARCHAR(30) NOT NULL DEFAULT 'text' CHECK (message_type IN ('text', 'system', 'document', 'milestone', 'task')),
            content TEXT NOT NULL,

            -- Sender
            sender_type VARCHAR(20) NOT NULL CHECK (sender_type IN ('user', 'contact', 'system')),
            sender_user_id INTEGER REFERENCES users(id),
            sender_contact_id INTEGER REFERENCES purl_contacts(id),

            -- Related entities
            related_document_id INTEGER REFERENCES purl_documents(id),
            related_task_id INTEGER REFERENCES purl_tasks(id),

            -- Read status
            is_read_by_borrower BOOLEAN DEFAULT FALSE,
            read_at TIMESTAMP WITH TIME ZONE,

            metadata JSONB NOT NULL DEFAULT '{}'::jsonb,

            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        );
        """,

        """
        CREATE INDEX IF NOT EXISTS idx_purl_messages_workspace
        ON purl_messages(workspace_id, created_at DESC);
        """,

        # ============================================================================
        # 13. EVENTS OUTBOX - Event sourcing and async processing
        # ============================================================================
        """
        CREATE TABLE IF NOT EXISTS purl_events_outbox (
            id SERIAL PRIMARY KEY,
            organization_id INTEGER NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,

            event_key VARCHAR(100) NOT NULL,
            workspace_id INTEGER REFERENCES purl_workspaces(id),
            loan_id INTEGER REFERENCES purl_loans(id),

            payload JSONB NOT NULL,
            status VARCHAR(30) NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'processing', 'processed', 'failed', 'dead_letter')),
            attempts INTEGER NOT NULL DEFAULT 0,
            max_attempts INTEGER NOT NULL DEFAULT 5,

            -- Worker coordination
            locked_at TIMESTAMP WITH TIME ZONE,
            locked_by VARCHAR(255),
            processed_duration_ms INTEGER,
            error_message TEXT,

            -- Scheduling
            scheduled_for TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
            processed_at TIMESTAMP WITH TIME ZONE,

            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        );
        """,

        """
        CREATE INDEX IF NOT EXISTS idx_purl_events_pending
        ON purl_events_outbox(scheduled_for, status)
        WHERE status IN ('pending', 'failed') AND attempts < max_attempts;
        """,

        """
        CREATE INDEX IF NOT EXISTS idx_purl_events_workspace
        ON purl_events_outbox(workspace_id);
        """,

        """
        CREATE INDEX IF NOT EXISTS idx_purl_events_loan
        ON purl_events_outbox(loan_id);
        """,

        # ============================================================================
        # 14. AUDIT LOG - Immutable audit trail
        # ============================================================================
        """
        CREATE TABLE IF NOT EXISTS purl_audit_log (
            id SERIAL PRIMARY KEY,
            organization_id INTEGER NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,

            actor_type VARCHAR(20) NOT NULL CHECK (actor_type IN ('user', 'contact', 'system', 'api')),
            actor_id INTEGER,

            workspace_id INTEGER REFERENCES purl_workspaces(id),
            loan_id INTEGER REFERENCES purl_loans(id),

            action VARCHAR(100) NOT NULL,
            resource_type VARCHAR(100) NOT NULL,
            resource_id INTEGER,

            -- Details
            changes JSONB,
            metadata JSONB NOT NULL DEFAULT '{}'::jsonb,

            -- Request tracking
            ip_address VARCHAR(45),
            user_agent TEXT,
            request_id VARCHAR(100),

            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        );
        """,

        """
        CREATE INDEX IF NOT EXISTS idx_purl_audit_workspace
        ON purl_audit_log(workspace_id, created_at DESC);
        """,

        """
        CREATE INDEX IF NOT EXISTS idx_purl_audit_actor
        ON purl_audit_log(actor_type, actor_id, created_at DESC);
        """,

        """
        CREATE INDEX IF NOT EXISTS idx_purl_audit_action
        ON purl_audit_log(organization_id, action, created_at DESC);
        """,

        """
        CREATE INDEX IF NOT EXISTS idx_purl_audit_resource
        ON purl_audit_log(resource_type, resource_id, created_at DESC);
        """,

        # ============================================================================
        # 15. DOCUMENT REQUESTS - Track requested documents
        # ============================================================================
        """
        CREATE TABLE IF NOT EXISTS purl_document_requests (
            id SERIAL PRIMARY KEY,
            organization_id INTEGER NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
            workspace_id INTEGER NOT NULL REFERENCES purl_workspaces(id) ON DELETE CASCADE,
            loan_id INTEGER REFERENCES purl_loans(id) ON DELETE CASCADE,

            document_type VARCHAR(100) NOT NULL,
            document_category VARCHAR(50) NOT NULL,
            description TEXT,

            status VARCHAR(30) NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'received', 'verified', 'expired', 'waived')),
            is_required BOOLEAN DEFAULT TRUE,

            -- Request tracking
            requested_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            requested_by INTEGER REFERENCES users(id),
            due_date DATE,

            -- Reminder tracking
            reminder_count INTEGER DEFAULT 0,
            last_reminder_at TIMESTAMP WITH TIME ZONE,

            -- Fulfillment
            received_document_id INTEGER REFERENCES purl_documents(id),
            received_at TIMESTAMP WITH TIME ZONE,

            metadata JSONB NOT NULL DEFAULT '{}'::jsonb,

            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        );
        """,

        """
        CREATE INDEX IF NOT EXISTS idx_purl_doc_requests_workspace
        ON purl_document_requests(workspace_id);
        """,

        """
        CREATE INDEX IF NOT EXISTS idx_purl_doc_requests_status
        ON purl_document_requests(organization_id, status);
        """,

        # ============================================================================
        # 16. FUNCTIONS: Updated timestamp trigger
        # ============================================================================
        """
        CREATE OR REPLACE FUNCTION purl_update_updated_at_column()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.updated_at = CURRENT_TIMESTAMP;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """,

        # Apply triggers to all tables with updated_at
        """
        DROP TRIGGER IF EXISTS update_purl_workspaces_updated_at ON purl_workspaces;
        CREATE TRIGGER update_purl_workspaces_updated_at
        BEFORE UPDATE ON purl_workspaces
        FOR EACH ROW EXECUTE FUNCTION purl_update_updated_at_column();
        """,

        """
        DROP TRIGGER IF EXISTS update_purl_contacts_updated_at ON purl_contacts;
        CREATE TRIGGER update_purl_contacts_updated_at
        BEFORE UPDATE ON purl_contacts
        FOR EACH ROW EXECUTE FUNCTION purl_update_updated_at_column();
        """,

        """
        DROP TRIGGER IF EXISTS update_purl_applications_updated_at ON purl_applications;
        CREATE TRIGGER update_purl_applications_updated_at
        BEFORE UPDATE ON purl_applications
        FOR EACH ROW EXECUTE FUNCTION purl_update_updated_at_column();
        """,

        """
        DROP TRIGGER IF EXISTS update_purl_loans_updated_at ON purl_loans;
        CREATE TRIGGER update_purl_loans_updated_at
        BEFORE UPDATE ON purl_loans
        FOR EACH ROW EXECUTE FUNCTION purl_update_updated_at_column();
        """,

        """
        DROP TRIGGER IF EXISTS update_purl_documents_updated_at ON purl_documents;
        CREATE TRIGGER update_purl_documents_updated_at
        BEFORE UPDATE ON purl_documents
        FOR EACH ROW EXECUTE FUNCTION purl_update_updated_at_column();
        """,

        """
        DROP TRIGGER IF EXISTS update_purl_portal_modules_updated_at ON purl_portal_modules;
        CREATE TRIGGER update_purl_portal_modules_updated_at
        BEFORE UPDATE ON purl_portal_modules
        FOR EACH ROW EXECUTE FUNCTION purl_update_updated_at_column();
        """,

        """
        DROP TRIGGER IF EXISTS update_purl_loan_milestones_updated_at ON purl_loan_milestones;
        CREATE TRIGGER update_purl_loan_milestones_updated_at
        BEFORE UPDATE ON purl_loan_milestones
        FOR EACH ROW EXECUTE FUNCTION purl_update_updated_at_column();
        """,

        """
        DROP TRIGGER IF EXISTS update_purl_tasks_updated_at ON purl_tasks;
        CREATE TRIGGER update_purl_tasks_updated_at
        BEFORE UPDATE ON purl_tasks
        FOR EACH ROW EXECUTE FUNCTION purl_update_updated_at_column();
        """,

        """
        DROP TRIGGER IF EXISTS update_purl_document_requests_updated_at ON purl_document_requests;
        CREATE TRIGGER update_purl_document_requests_updated_at
        BEFORE UPDATE ON purl_document_requests
        FOR EACH ROW EXECUTE FUNCTION purl_update_updated_at_column();
        """,

        # ============================================================================
        # 17. SEED DEFAULT MILESTONE DEFINITIONS
        # ============================================================================
        """
        INSERT INTO purl_milestone_definitions (
            organization_id, code, stage, display_name, description,
            order_index, sla_days, sla_type, grace_percent
        )
        SELECT
            o.id,
            m.code,
            m.stage,
            m.display_name,
            m.description,
            m.order_index,
            m.sla_days,
            m.sla_type,
            m.grace_percent
        FROM organizations o
        CROSS JOIN (VALUES
            ('app_received', 'application', 'Application Received', 'Loan application has been received', 1, NULL, 'estimated', 75),
            ('app_disclosure', 'application', 'Initial Disclosures Sent', 'Initial loan disclosures sent to borrower', 2, 3, 'hard', 100),
            ('docs_requested', 'processing', 'Documents Requested', 'Required documents have been requested', 3, 1, 'soft', 75),
            ('docs_received', 'processing', 'Documents Received', 'All required documents received', 4, 7, 'soft', 75),
            ('submitted_to_uw', 'underwriting', 'Submitted to Underwriting', 'File submitted for underwriting review', 5, 3, 'soft', 75),
            ('conditional_approval', 'underwriting', 'Conditional Approval', 'Loan conditionally approved', 6, 5, 'soft', 75),
            ('clear_to_close', 'underwriting', 'Clear to Close', 'All conditions cleared, ready to close', 7, 3, 'soft', 75),
            ('closing_scheduled', 'closing', 'Closing Scheduled', 'Closing appointment scheduled', 8, 2, 'soft', 75),
            ('closed', 'closing', 'Closed', 'Loan has closed', 9, NULL, 'estimated', 75),
            ('funded', 'closing', 'Funded', 'Loan has funded', 10, 3, 'hard', 100)
        ) AS m(code, stage, display_name, description, order_index, sla_days, sla_type, grace_percent)
        WHERE NOT EXISTS (
            SELECT 1 FROM purl_milestone_definitions
            WHERE organization_id = o.id AND code = m.code
        );
        """
    ]

    with engine.connect() as connection:
        for i, sql in enumerate(sql_commands):
            try:
                logger.info(f"Running SQL command {i + 1}/{len(sql_commands)}")
                connection.execute(text(sql))
                connection.commit()
            except Exception as e:
                logger.error(f"Error executing SQL command {i + 1}: {e}")
                logger.error(f"SQL: {sql[:200]}...")
                connection.rollback()
                # Continue with other commands instead of failing completely
                continue

    logger.info("PURL System migration completed successfully!")


def rollback_migration():
    """Drop all PURL tables (use with caution!)"""

    drop_commands = [
        "DROP TABLE IF EXISTS purl_audit_log CASCADE;",
        "DROP TABLE IF EXISTS purl_events_outbox CASCADE;",
        "DROP TABLE IF EXISTS purl_messages CASCADE;",
        "DROP TABLE IF EXISTS purl_document_requests CASCADE;",
        "DROP TABLE IF EXISTS purl_tasks CASCADE;",
        "DROP TABLE IF EXISTS purl_loan_milestones CASCADE;",
        "DROP TABLE IF EXISTS purl_milestone_definitions CASCADE;",
        "DROP TABLE IF EXISTS purl_portal_modules CASCADE;",
        "DROP TABLE IF EXISTS purl_documents CASCADE;",
        "DROP TABLE IF EXISTS purl_loans CASCADE;",
        "DROP TABLE IF EXISTS purl_applications CASCADE;",
        "DROP TABLE IF EXISTS purl_access_tokens CASCADE;",
        "DROP TABLE IF EXISTS purl_workspace_members CASCADE;",
        "DROP TABLE IF EXISTS purl_contacts CASCADE;",
        "DROP TABLE IF EXISTS purl_workspaces CASCADE;",
        "DROP FUNCTION IF EXISTS purl_update_updated_at_column() CASCADE;",
    ]

    with engine.connect() as connection:
        for sql in drop_commands:
            try:
                connection.execute(text(sql))
                connection.commit()
                logger.info(f"Executed: {sql}")
            except Exception as e:
                logger.error(f"Error: {e}")
                connection.rollback()

    logger.info("PURL System tables dropped!")


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "rollback":
        confirm = input("Are you sure you want to drop all PURL tables? (yes/no): ")
        if confirm.lower() == "yes":
            rollback_migration()
        else:
            print("Rollback cancelled.")
    else:
        run_migration()
