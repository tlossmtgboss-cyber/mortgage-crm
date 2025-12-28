"""
Migration: Add Listing Agent Portal Tables
Creates infrastructure for transaction-scoped Listing Agent Portal with:
- Transaction parties (listing agents)
- Milestones and status tracking
- Portal invites with magic link authentication
- Conversation threads
- Weekly update deliveries
- PII-safe snapshot system

The platform provides:
- Transaction-scoped access (only see their specific transactions)
- Magic link authentication (no passwords required)
- Weekly automated updates on loan progress
- Secure messaging between listing agents and LOs
- PII protection (no borrower data exposed)
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
    """Create Listing Agent Portal tables"""

    sql_commands = [
        # ============================================================================
        # ENABLE REQUIRED EXTENSIONS
        # ============================================================================
        """
        CREATE EXTENSION IF NOT EXISTS pgcrypto;
        """,

        # ============================================================================
        # 1. LISTING TRANSACTIONS - Links to loans with listing agent context
        # ============================================================================
        """
        CREATE TABLE IF NOT EXISTS listing_transactions (
            id SERIAL PRIMARY KEY,
            organization_id INTEGER NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,

            -- Link to loan (one-to-one)
            loan_id INTEGER NOT NULL REFERENCES loans(id) ON DELETE CASCADE,

            -- Property info (safe to share)
            property_address TEXT NOT NULL,
            property_city VARCHAR(100),
            property_state VARCHAR(10),
            property_zip VARCHAR(20),
            purchase_price DECIMAL(15,2),

            -- Timeline
            contract_date DATE,
            target_close_date DATE,
            actual_close_date DATE,

            -- Status tracking
            current_status VARCHAR(50) DEFAULT 'active',
            status_changed_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,

            -- Flags
            is_active BOOLEAN DEFAULT TRUE,

            -- Timestamps
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,

            CONSTRAINT unique_loan_transaction UNIQUE(loan_id),
            CONSTRAINT valid_transaction_status CHECK (current_status IN ('active', 'pending', 'closing', 'closed', 'cancelled', 'on_hold'))
        );
        """,

        """
        CREATE INDEX IF NOT EXISTS idx_listing_transactions_org
        ON listing_transactions(organization_id, is_active);
        """,

        """
        CREATE INDEX IF NOT EXISTS idx_listing_transactions_loan
        ON listing_transactions(loan_id);
        """,

        """
        CREATE INDEX IF NOT EXISTS idx_listing_transactions_status
        ON listing_transactions(current_status, target_close_date);
        """,

        # ============================================================================
        # 2. TRANSACTION PARTIES - Listing agents and other parties
        # ============================================================================
        """
        CREATE TABLE IF NOT EXISTS transaction_parties (
            id SERIAL PRIMARY KEY,
            transaction_id INTEGER NOT NULL REFERENCES listing_transactions(id) ON DELETE CASCADE,

            -- Party identity
            role VARCHAR(50) NOT NULL,
            email VARCHAR(255) NOT NULL,
            first_name VARCHAR(100) NOT NULL,
            last_name VARCHAR(100) NOT NULL,
            phone VARCHAR(50),

            -- Professional info
            company_name VARCHAR(255),
            license_number VARCHAR(100),

            -- Notification preferences
            notify_weekly_updates BOOLEAN DEFAULT TRUE,
            notify_milestone_changes BOOLEAN DEFAULT TRUE,
            notify_messages BOOLEAN DEFAULT TRUE,
            unsubscribed_at TIMESTAMP WITH TIME ZONE,

            -- Status
            is_active BOOLEAN DEFAULT TRUE,

            -- Timestamps
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,

            CONSTRAINT unique_party_email_transaction UNIQUE(transaction_id, email),
            CONSTRAINT valid_party_role CHECK (role IN ('listing_agent', 'selling_agent', 'escrow_officer', 'title_officer', 'attorney', 'other'))
        );
        """,

        """
        CREATE INDEX IF NOT EXISTS idx_transaction_parties_email
        ON transaction_parties(email);
        """,

        """
        CREATE INDEX IF NOT EXISTS idx_transaction_parties_transaction
        ON transaction_parties(transaction_id, is_active);
        """,

        """
        CREATE INDEX IF NOT EXISTS idx_transaction_parties_role
        ON transaction_parties(role, is_active);
        """,

        # ============================================================================
        # 3. MILESTONES - Transaction progress tracking
        # ============================================================================
        """
        CREATE TABLE IF NOT EXISTS listing_milestones (
            id SERIAL PRIMARY KEY,
            transaction_id INTEGER NOT NULL REFERENCES listing_transactions(id) ON DELETE CASCADE,

            -- Milestone details
            milestone_key VARCHAR(100) NOT NULL,
            milestone_name VARCHAR(255) NOT NULL,
            description TEXT,

            -- Status
            status VARCHAR(50) DEFAULT 'pending',
            completed_at TIMESTAMP WITH TIME ZONE,

            -- Order for display
            display_order INTEGER NOT NULL DEFAULT 0,

            -- Optional target date
            target_date DATE,

            -- Timestamps
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,

            CONSTRAINT unique_milestone_key UNIQUE(transaction_id, milestone_key),
            CONSTRAINT valid_milestone_status CHECK (status IN ('pending', 'in_progress', 'completed', 'skipped', 'blocked'))
        );
        """,

        """
        CREATE INDEX IF NOT EXISTS idx_listing_milestones_transaction
        ON listing_milestones(transaction_id, display_order);
        """,

        """
        CREATE INDEX IF NOT EXISTS idx_listing_milestones_status
        ON listing_milestones(status);
        """,

        # ============================================================================
        # 4. PORTAL INVITES - Magic link authentication tokens
        # ============================================================================
        """
        CREATE TABLE IF NOT EXISTS listing_portal_invites (
            id SERIAL PRIMARY KEY,
            party_id INTEGER NOT NULL REFERENCES transaction_parties(id) ON DELETE CASCADE,

            -- Magic link token
            token VARCHAR(255) NOT NULL UNIQUE,

            -- Token lifecycle
            expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
            used_at TIMESTAMP WITH TIME ZONE,
            revoked_at TIMESTAMP WITH TIME ZONE,

            -- Session tracking
            session_token VARCHAR(255),
            session_expires_at TIMESTAMP WITH TIME ZONE,

            -- Analytics
            clicks INTEGER DEFAULT 0,
            last_clicked_at TIMESTAMP WITH TIME ZONE,

            -- Metadata
            sent_via VARCHAR(50) DEFAULT 'email',

            -- Timestamps
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        );
        """,

        """
        CREATE INDEX IF NOT EXISTS idx_portal_invites_token
        ON listing_portal_invites(token) WHERE revoked_at IS NULL;
        """,

        """
        CREATE INDEX IF NOT EXISTS idx_portal_invites_party
        ON listing_portal_invites(party_id);
        """,

        """
        CREATE INDEX IF NOT EXISTS idx_portal_invites_session
        ON listing_portal_invites(session_token) WHERE session_token IS NOT NULL;
        """,

        # ============================================================================
        # 5. PORTAL MESSAGES - Conversation threads
        # ============================================================================
        """
        CREATE TABLE IF NOT EXISTS listing_portal_messages (
            id SERIAL PRIMARY KEY,
            transaction_id INTEGER NOT NULL REFERENCES listing_transactions(id) ON DELETE CASCADE,

            -- Sender (either party or user)
            sender_party_id INTEGER REFERENCES transaction_parties(id) ON DELETE SET NULL,
            sender_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,

            -- Message content
            content TEXT NOT NULL,

            -- Read tracking
            read_at TIMESTAMP WITH TIME ZONE,
            read_by_party_id INTEGER REFERENCES transaction_parties(id) ON DELETE SET NULL,
            read_by_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,

            -- Attachments
            attachments JSONB DEFAULT '[]'::jsonb,

            -- Timestamps
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,

            CONSTRAINT sender_specified CHECK (sender_party_id IS NOT NULL OR sender_user_id IS NOT NULL)
        );
        """,

        """
        CREATE INDEX IF NOT EXISTS idx_portal_messages_transaction
        ON listing_portal_messages(transaction_id, created_at DESC);
        """,

        """
        CREATE INDEX IF NOT EXISTS idx_portal_messages_unread
        ON listing_portal_messages(transaction_id, read_at) WHERE read_at IS NULL;
        """,

        # ============================================================================
        # 6. UPDATE DELIVERIES - Track sent updates
        # ============================================================================
        """
        CREATE TABLE IF NOT EXISTS listing_update_deliveries (
            id SERIAL PRIMARY KEY,
            party_id INTEGER NOT NULL REFERENCES transaction_parties(id) ON DELETE CASCADE,
            transaction_id INTEGER NOT NULL REFERENCES listing_transactions(id) ON DELETE CASCADE,

            -- Delivery details
            delivery_type VARCHAR(50) NOT NULL,
            channel VARCHAR(50) DEFAULT 'email',

            -- Content snapshot (what was sent)
            snapshot_data JSONB NOT NULL,

            -- Status
            status VARCHAR(50) DEFAULT 'pending',
            sent_at TIMESTAMP WITH TIME ZONE,
            delivered_at TIMESTAMP WITH TIME ZONE,
            opened_at TIMESTAMP WITH TIME ZONE,
            clicked_at TIMESTAMP WITH TIME ZONE,
            bounced_at TIMESTAMP WITH TIME ZONE,

            -- Error tracking
            error_message TEXT,
            retry_count INTEGER DEFAULT 0,

            -- External IDs
            external_message_id VARCHAR(255),

            -- Timestamps
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,

            CONSTRAINT valid_delivery_type CHECK (delivery_type IN ('weekly_update', 'milestone_change', 'message_notification', 'invite', 'reminder')),
            CONSTRAINT valid_delivery_status CHECK (status IN ('pending', 'sent', 'delivered', 'opened', 'clicked', 'bounced', 'failed'))
        );
        """,

        """
        CREATE INDEX IF NOT EXISTS idx_update_deliveries_party
        ON listing_update_deliveries(party_id, created_at DESC);
        """,

        """
        CREATE INDEX IF NOT EXISTS idx_update_deliveries_transaction
        ON listing_update_deliveries(transaction_id, delivery_type);
        """,

        """
        CREATE INDEX IF NOT EXISTS idx_update_deliveries_status
        ON listing_update_deliveries(status, created_at) WHERE status = 'pending';
        """,

        # ============================================================================
        # 7. TRANSACTION SNAPSHOTS - Point-in-time status captures
        # ============================================================================
        """
        CREATE TABLE IF NOT EXISTS listing_transaction_snapshots (
            id SERIAL PRIMARY KEY,
            transaction_id INTEGER NOT NULL REFERENCES listing_transactions(id) ON DELETE CASCADE,

            -- Snapshot content (PII-safe)
            snapshot_data JSONB NOT NULL,

            -- Snapshot metadata
            snapshot_type VARCHAR(50) DEFAULT 'automatic',
            triggered_by VARCHAR(100),

            -- Hash for change detection
            content_hash VARCHAR(64),

            -- Timestamps
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        );
        """,

        """
        CREATE INDEX IF NOT EXISTS idx_transaction_snapshots_transaction
        ON listing_transaction_snapshots(transaction_id, created_at DESC);
        """,

        """
        CREATE INDEX IF NOT EXISTS idx_transaction_snapshots_hash
        ON listing_transaction_snapshots(transaction_id, content_hash);
        """,

        # ============================================================================
        # 8. UNSUBSCRIBE TOKENS - For email unsubscribe links
        # ============================================================================
        """
        CREATE TABLE IF NOT EXISTS listing_unsubscribe_tokens (
            id SERIAL PRIMARY KEY,
            party_id INTEGER NOT NULL REFERENCES transaction_parties(id) ON DELETE CASCADE,

            -- Token
            token VARCHAR(255) NOT NULL UNIQUE,

            -- What they're unsubscribing from
            unsubscribe_type VARCHAR(50) DEFAULT 'all',

            -- Usage
            used_at TIMESTAMP WITH TIME ZONE,

            -- Timestamps
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            expires_at TIMESTAMP WITH TIME ZONE,

            CONSTRAINT valid_unsubscribe_type CHECK (unsubscribe_type IN ('all', 'weekly_updates', 'milestones', 'messages'))
        );
        """,

        """
        CREATE INDEX IF NOT EXISTS idx_unsubscribe_tokens_token
        ON listing_unsubscribe_tokens(token) WHERE used_at IS NULL;
        """,

        """
        CREATE INDEX IF NOT EXISTS idx_unsubscribe_tokens_party
        ON listing_unsubscribe_tokens(party_id);
        """,

        # ============================================================================
        # 9. TRIGGERS - Auto-update timestamps
        # ============================================================================
        """
        CREATE OR REPLACE FUNCTION listing_portal_update_updated_at()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.updated_at = CURRENT_TIMESTAMP;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """,

        """
        DROP TRIGGER IF EXISTS update_listing_transactions_updated_at ON listing_transactions;
        CREATE TRIGGER update_listing_transactions_updated_at
        BEFORE UPDATE ON listing_transactions
        FOR EACH ROW EXECUTE FUNCTION listing_portal_update_updated_at();
        """,

        """
        DROP TRIGGER IF EXISTS update_transaction_parties_updated_at ON transaction_parties;
        CREATE TRIGGER update_transaction_parties_updated_at
        BEFORE UPDATE ON transaction_parties
        FOR EACH ROW EXECUTE FUNCTION listing_portal_update_updated_at();
        """,

        """
        DROP TRIGGER IF EXISTS update_listing_milestones_updated_at ON listing_milestones;
        CREATE TRIGGER update_listing_milestones_updated_at
        BEFORE UPDATE ON listing_milestones
        FOR EACH ROW EXECUTE FUNCTION listing_portal_update_updated_at();
        """,

        # ============================================================================
        # 10. SEED DEFAULT MILESTONES TEMPLATE
        # ============================================================================
        """
        CREATE TABLE IF NOT EXISTS listing_milestone_templates (
            id SERIAL PRIMARY KEY,
            organization_id INTEGER REFERENCES organizations(id) ON DELETE CASCADE,

            -- Template details
            milestone_key VARCHAR(100) NOT NULL,
            milestone_name VARCHAR(255) NOT NULL,
            description TEXT,
            display_order INTEGER NOT NULL DEFAULT 0,

            -- Whether this is default for new transactions
            is_default BOOLEAN DEFAULT FALSE,

            -- Timestamps
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,

            CONSTRAINT unique_milestone_template UNIQUE(organization_id, milestone_key)
        );
        """,

        """
        INSERT INTO listing_milestone_templates (organization_id, milestone_key, milestone_name, description, display_order, is_default)
        VALUES
        -- System-wide defaults (organization_id = NULL)
        (NULL, 'contract_received', 'Contract Received', 'Purchase contract and earnest money received', 1, true),
        (NULL, 'application_complete', 'Application Complete', 'Borrower has submitted full application', 2, true),
        (NULL, 'appraisal_ordered', 'Appraisal Ordered', 'Property appraisal has been ordered', 3, true),
        (NULL, 'appraisal_received', 'Appraisal Received', 'Appraisal report received and reviewed', 4, true),
        (NULL, 'submitted_to_underwriting', 'Submitted to Underwriting', 'File submitted for underwriting review', 5, true),
        (NULL, 'conditional_approval', 'Conditional Approval', 'Loan conditionally approved', 6, true),
        (NULL, 'clear_to_close', 'Clear to Close', 'All conditions satisfied, ready for closing', 7, true),
        (NULL, 'closing_scheduled', 'Closing Scheduled', 'Closing date and time confirmed', 8, true),
        (NULL, 'closing_complete', 'Closing Complete', 'Loan has funded and closed', 9, true)

        ON CONFLICT (organization_id, milestone_key) DO NOTHING;
        """,

        # ============================================================================
        # 11. GIN INDEXES FOR JSONB SEARCH
        # ============================================================================
        """
        CREATE INDEX IF NOT EXISTS idx_deliveries_snapshot_gin
        ON listing_update_deliveries USING GIN (snapshot_data);
        """,

        """
        CREATE INDEX IF NOT EXISTS idx_snapshots_data_gin
        ON listing_transaction_snapshots USING GIN (snapshot_data);
        """,

        """
        CREATE INDEX IF NOT EXISTS idx_messages_attachments_gin
        ON listing_portal_messages USING GIN (attachments);
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
                continue

    logger.info("Listing Agent Portal migration completed successfully!")


def rollback_migration():
    """Drop all Listing Agent Portal tables (use with caution!)"""

    drop_commands = [
        "DROP TABLE IF EXISTS listing_unsubscribe_tokens CASCADE;",
        "DROP TABLE IF EXISTS listing_transaction_snapshots CASCADE;",
        "DROP TABLE IF EXISTS listing_update_deliveries CASCADE;",
        "DROP TABLE IF EXISTS listing_portal_messages CASCADE;",
        "DROP TABLE IF EXISTS listing_portal_invites CASCADE;",
        "DROP TABLE IF EXISTS listing_milestones CASCADE;",
        "DROP TABLE IF EXISTS listing_milestone_templates CASCADE;",
        "DROP TABLE IF EXISTS transaction_parties CASCADE;",
        "DROP TABLE IF EXISTS listing_transactions CASCADE;",
        "DROP FUNCTION IF EXISTS listing_portal_update_updated_at() CASCADE;",
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

    logger.info("Listing Agent Portal tables dropped!")


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "rollback":
        confirm = input("Are you sure you want to drop all Listing Agent Portal tables? (yes/no): ")
        if confirm.lower() == "yes":
            rollback_migration()
        else:
            print("Rollback cancelled.")
    else:
        run_migration()
