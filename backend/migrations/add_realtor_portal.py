"""
Migration: Add Realtor Portal Tables
Creates infrastructure for real-time CRM-synced realtor portal with:
- Realtor portal users and loan associations
- Status-action permission matrix
- Letter generation and versioning
- Communication event tracking
- CRM sync state management
- Rate/limit policies
- SMS command history

The platform provides:
- Real-time WebSocket sync with CRM
- Dynamic permission system based on loan status
- AI-powered letter generation with versioning
- Multi-channel communication tracking
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
    """Create Realtor Portal tables"""

    sql_commands = [
        # ============================================================================
        # ENABLE REQUIRED EXTENSIONS
        # ============================================================================
        """
        CREATE EXTENSION IF NOT EXISTS pgcrypto;
        """,

        # ============================================================================
        # 1. REALTOR PORTAL USERS - Realtors with portal access
        # ============================================================================
        """
        CREATE TABLE IF NOT EXISTS realtor_portal_users (
            id SERIAL PRIMARY KEY,
            organization_id INTEGER NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,

            -- Core identity
            email VARCHAR(255) NOT NULL,
            phone VARCHAR(50),
            first_name VARCHAR(255) NOT NULL,
            last_name VARCHAR(255) NOT NULL,

            -- Authentication
            password_hash VARCHAR(255),
            auth_provider VARCHAR(50) DEFAULT 'email',

            -- Realtor details
            brokerage_name VARCHAR(255),
            license_number VARCHAR(100),
            license_state VARCHAR(10),

            -- Associated LO (their primary contact)
            primary_lo_id INTEGER REFERENCES users(id) ON DELETE SET NULL,

            -- Portal settings
            notification_preferences JSONB DEFAULT '{"email": true, "sms": true, "push": false}'::jsonb,
            timezone VARCHAR(100) DEFAULT 'America/New_York',

            -- Status
            is_active BOOLEAN DEFAULT TRUE,
            last_login_at TIMESTAMP WITH TIME ZONE,
            login_count INTEGER DEFAULT 0,

            -- Timestamps
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,

            CONSTRAINT unique_realtor_email_org UNIQUE(organization_id, email)
        );
        """,

        """
        CREATE INDEX IF NOT EXISTS idx_realtor_portal_users_org
        ON realtor_portal_users(organization_id, is_active);
        """,

        """
        CREATE INDEX IF NOT EXISTS idx_realtor_portal_users_email
        ON realtor_portal_users(email);
        """,

        """
        CREATE INDEX IF NOT EXISTS idx_realtor_portal_users_lo
        ON realtor_portal_users(primary_lo_id);
        """,

        # ============================================================================
        # 2. REALTOR LOAN ASSOCIATIONS - Links realtors to specific loans
        # ============================================================================
        """
        CREATE TABLE IF NOT EXISTS realtor_loan_associations (
            id SERIAL PRIMARY KEY,
            realtor_id INTEGER NOT NULL REFERENCES realtor_portal_users(id) ON DELETE CASCADE,
            loan_id INTEGER NOT NULL REFERENCES loans(id) ON DELETE CASCADE,

            -- Role on this loan
            role VARCHAR(50) DEFAULT 'buyer_agent',

            -- Access level
            access_granted_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            access_granted_by INTEGER REFERENCES users(id),
            access_revoked_at TIMESTAMP WITH TIME ZONE,

            -- Engagement tracking
            last_viewed_at TIMESTAMP WITH TIME ZONE,
            view_count INTEGER DEFAULT 0,

            -- Notification preferences for this loan
            notify_status_changes BOOLEAN DEFAULT TRUE,
            notify_documents BOOLEAN DEFAULT TRUE,
            notify_messages BOOLEAN DEFAULT TRUE,

            -- Timestamps
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,

            CONSTRAINT unique_realtor_loan UNIQUE(realtor_id, loan_id),
            CONSTRAINT valid_realtor_role CHECK (role IN ('buyer_agent', 'seller_agent', 'dual_agent', 'referring_agent'))
        );
        """,

        """
        CREATE INDEX IF NOT EXISTS idx_realtor_loan_assoc_realtor
        ON realtor_loan_associations(realtor_id, access_revoked_at NULLS FIRST);
        """,

        """
        CREATE INDEX IF NOT EXISTS idx_realtor_loan_assoc_loan
        ON realtor_loan_associations(loan_id);
        """,

        # ============================================================================
        # 3. PORTAL STATUS ACTIONS - Defines what realtors can do at each loan status
        # ============================================================================
        """
        CREATE TABLE IF NOT EXISTS portal_status_actions (
            id SERIAL PRIMARY KEY,
            organization_id INTEGER REFERENCES organizations(id) ON DELETE CASCADE,

            -- Status configuration
            loan_status VARCHAR(50) NOT NULL,

            -- Available actions (all boolean)
            can_view_status BOOLEAN DEFAULT TRUE,
            can_view_timeline BOOLEAN DEFAULT TRUE,
            can_view_documents BOOLEAN DEFAULT FALSE,
            can_download_documents BOOLEAN DEFAULT FALSE,
            can_upload_documents BOOLEAN DEFAULT FALSE,
            can_send_messages BOOLEAN DEFAULT TRUE,
            can_request_update BOOLEAN DEFAULT TRUE,
            can_generate_prequal BOOLEAN DEFAULT FALSE,
            can_generate_preapproval BOOLEAN DEFAULT FALSE,
            can_view_conditions BOOLEAN DEFAULT FALSE,
            can_schedule_meeting BOOLEAN DEFAULT TRUE,

            -- Visibility settings
            visible_document_types TEXT[] DEFAULT ARRAY[]::TEXT[],
            hidden_fields TEXT[] DEFAULT ARRAY[]::TEXT[],

            -- AI assistant availability
            ai_assistant_enabled BOOLEAN DEFAULT TRUE,
            ai_allowed_topics TEXT[] DEFAULT ARRAY['status', 'timeline', 'general']::TEXT[],

            -- Priority (for org-specific overrides)
            priority INTEGER DEFAULT 0,

            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,

            CONSTRAINT unique_org_status_action UNIQUE(organization_id, loan_status)
        );
        """,

        """
        CREATE INDEX IF NOT EXISTS idx_portal_status_actions_lookup
        ON portal_status_actions(organization_id NULLS LAST, loan_status, priority DESC);
        """,

        # ============================================================================
        # 4. LETTER TEMPLATES - Versioned templates for pre-qual/pre-approval letters
        # ============================================================================
        """
        CREATE TABLE IF NOT EXISTS letter_templates (
            id SERIAL PRIMARY KEY,
            organization_id INTEGER NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,

            -- Template identification
            template_type VARCHAR(50) NOT NULL,
            name VARCHAR(255) NOT NULL,
            version INTEGER NOT NULL DEFAULT 1,

            -- Template content
            html_template TEXT NOT NULL,
            css_styles TEXT,
            header_html TEXT,
            footer_html TEXT,

            -- Variable schema
            variables_schema JSONB NOT NULL DEFAULT '{}'::jsonb,

            -- PDF generation settings
            page_size VARCHAR(20) DEFAULT 'letter',
            margins JSONB DEFAULT '{"top": "1in", "bottom": "1in", "left": "1in", "right": "1in"}'::jsonb,

            -- Status
            is_active BOOLEAN DEFAULT TRUE,
            is_default BOOLEAN DEFAULT FALSE,

            -- Compliance
            requires_nmls BOOLEAN DEFAULT TRUE,
            requires_signature BOOLEAN DEFAULT TRUE,
            expiration_days INTEGER DEFAULT 90,

            -- Audit
            created_by INTEGER REFERENCES users(id),
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,

            CONSTRAINT unique_template_version UNIQUE(organization_id, template_type, version),
            CONSTRAINT valid_template_type CHECK (template_type IN ('prequal', 'preapproval', 'commitment', 'rate_lock', 'custom'))
        );
        """,

        """
        CREATE INDEX IF NOT EXISTS idx_letter_templates_org_type
        ON letter_templates(organization_id, template_type, is_active);
        """,

        # ============================================================================
        # 5. PRE-APPROVAL LETTERS - Generated letters with versioning
        # ============================================================================
        """
        CREATE TABLE IF NOT EXISTS pre_approval_letters (
            id SERIAL PRIMARY KEY,
            organization_id INTEGER NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
            loan_id INTEGER NOT NULL REFERENCES loans(id) ON DELETE CASCADE,
            template_id INTEGER REFERENCES letter_templates(id),

            -- Letter details
            letter_type VARCHAR(50) NOT NULL,
            version INTEGER NOT NULL DEFAULT 1,

            -- Content
            generated_html TEXT NOT NULL,
            generated_pdf_url TEXT,
            variables_used JSONB NOT NULL DEFAULT '{}'::jsonb,

            -- Property-specific (for property-specific letters)
            property_address TEXT,
            purchase_price DECIMAL(15,2),

            -- Approval details
            approved_amount DECIMAL(15,2) NOT NULL,
            down_payment_percent DECIMAL(5,2),
            loan_program VARCHAR(100),
            interest_rate DECIMAL(6,4),

            -- Validity
            issued_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
            is_void BOOLEAN DEFAULT FALSE,
            voided_at TIMESTAMP WITH TIME ZONE,
            voided_by INTEGER REFERENCES users(id),
            void_reason TEXT,

            -- Generation details
            generated_by INTEGER REFERENCES users(id),
            generated_by_realtor INTEGER REFERENCES realtor_portal_users(id),
            generation_method VARCHAR(50) DEFAULT 'manual',

            -- Access tracking
            download_count INTEGER DEFAULT 0,
            last_downloaded_at TIMESTAMP WITH TIME ZONE,
            share_token VARCHAR(100) UNIQUE,

            -- Timestamps
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,

            CONSTRAINT valid_letter_type CHECK (letter_type IN ('prequal', 'preapproval', 'commitment', 'rate_lock', 'custom'))
        );
        """,

        """
        CREATE INDEX IF NOT EXISTS idx_pre_approval_letters_loan
        ON pre_approval_letters(loan_id, is_void, expires_at DESC);
        """,

        """
        CREATE INDEX IF NOT EXISTS idx_pre_approval_letters_share
        ON pre_approval_letters(share_token) WHERE share_token IS NOT NULL;
        """,

        """
        CREATE INDEX IF NOT EXISTS idx_pre_approval_letters_realtor
        ON pre_approval_letters(generated_by_realtor) WHERE generated_by_realtor IS NOT NULL;
        """,

        # ============================================================================
        # 6. COMMUNICATION EVENTS - Track all portal communications
        # ============================================================================
        """
        CREATE TABLE IF NOT EXISTS portal_communication_events (
            id SERIAL PRIMARY KEY,
            organization_id INTEGER NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,

            -- Participants
            realtor_id INTEGER REFERENCES realtor_portal_users(id) ON DELETE SET NULL,
            loan_id INTEGER REFERENCES loans(id) ON DELETE SET NULL,
            user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,

            -- Event details
            event_type VARCHAR(50) NOT NULL,
            channel VARCHAR(50) NOT NULL,
            direction VARCHAR(20) NOT NULL,

            -- Content
            subject TEXT,
            content TEXT,
            content_html TEXT,
            attachments JSONB DEFAULT '[]'::jsonb,

            -- Metadata
            metadata JSONB DEFAULT '{}'::jsonb,

            -- Delivery status
            status VARCHAR(50) DEFAULT 'sent',
            delivered_at TIMESTAMP WITH TIME ZONE,
            read_at TIMESTAMP WITH TIME ZONE,
            failed_at TIMESTAMP WITH TIME ZONE,
            failure_reason TEXT,

            -- AI involvement
            ai_generated BOOLEAN DEFAULT FALSE,
            ai_model VARCHAR(100),
            ai_prompt_tokens INTEGER,
            ai_completion_tokens INTEGER,

            -- Timestamps
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,

            CONSTRAINT valid_event_type CHECK (event_type IN ('message', 'notification', 'status_update', 'document_share', 'letter_share', 'meeting_request', 'system')),
            CONSTRAINT valid_channel CHECK (channel IN ('email', 'sms', 'portal', 'push', 'webhook')),
            CONSTRAINT valid_direction CHECK (direction IN ('inbound', 'outbound', 'system'))
        );
        """,

        """
        CREATE INDEX IF NOT EXISTS idx_comm_events_realtor
        ON portal_communication_events(realtor_id, created_at DESC);
        """,

        """
        CREATE INDEX IF NOT EXISTS idx_comm_events_loan
        ON portal_communication_events(loan_id, created_at DESC);
        """,

        """
        CREATE INDEX IF NOT EXISTS idx_comm_events_type
        ON portal_communication_events(event_type, created_at DESC);
        """,

        # ============================================================================
        # 7. CRM SYNC STATE - Track WebSocket sync state for real-time updates
        # ============================================================================
        """
        CREATE TABLE IF NOT EXISTS portal_crm_sync_state (
            id SERIAL PRIMARY KEY,

            -- What we're syncing
            entity_type VARCHAR(50) NOT NULL,
            entity_id INTEGER NOT NULL,

            -- Sync metadata
            last_synced_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            last_sync_version INTEGER DEFAULT 1,
            sync_hash VARCHAR(64),

            -- Connection tracking
            active_connections INTEGER DEFAULT 0,
            last_connection_at TIMESTAMP WITH TIME ZONE,

            -- Conflict handling
            has_conflicts BOOLEAN DEFAULT FALSE,
            conflict_data JSONB,

            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,

            CONSTRAINT unique_sync_entity UNIQUE(entity_type, entity_id)
        );
        """,

        """
        CREATE INDEX IF NOT EXISTS idx_crm_sync_state_entity
        ON portal_crm_sync_state(entity_type, entity_id);
        """,

        """
        CREATE INDEX IF NOT EXISTS idx_crm_sync_state_stale
        ON portal_crm_sync_state(last_synced_at)
        WHERE active_connections > 0;
        """,

        # ============================================================================
        # 8. PORTAL LIMIT POLICIES - Rate limiting and usage policies
        # ============================================================================
        """
        CREATE TABLE IF NOT EXISTS portal_limit_policies (
            id SERIAL PRIMARY KEY,
            organization_id INTEGER REFERENCES organizations(id) ON DELETE CASCADE,

            -- Policy identification
            policy_type VARCHAR(50) NOT NULL,
            policy_key VARCHAR(100) NOT NULL,

            -- Limits
            max_per_hour INTEGER,
            max_per_day INTEGER,
            max_per_month INTEGER,
            max_concurrent INTEGER,

            -- Current usage (reset periodically)
            current_hour_usage INTEGER DEFAULT 0,
            current_day_usage INTEGER DEFAULT 0,
            current_month_usage INTEGER DEFAULT 0,

            -- Reset timestamps
            hour_reset_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            day_reset_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            month_reset_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,

            -- Status
            is_active BOOLEAN DEFAULT TRUE,

            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,

            CONSTRAINT unique_limit_policy UNIQUE(organization_id, policy_type, policy_key)
        );
        """,

        """
        CREATE INDEX IF NOT EXISTS idx_limit_policies_lookup
        ON portal_limit_policies(organization_id NULLS LAST, policy_type, is_active);
        """,

        # ============================================================================
        # 9. SMS COMMAND HISTORY - Track SMS-based portal commands
        # ============================================================================
        """
        CREATE TABLE IF NOT EXISTS portal_sms_command_history (
            id SERIAL PRIMARY KEY,

            -- Sender identification
            phone_number VARCHAR(50) NOT NULL,
            realtor_id INTEGER REFERENCES realtor_portal_users(id) ON DELETE SET NULL,

            -- Command details
            raw_message TEXT NOT NULL,
            parsed_command VARCHAR(50),
            parsed_args JSONB DEFAULT '{}'::jsonb,

            -- Loan context (if determined)
            loan_id INTEGER REFERENCES loans(id) ON DELETE SET NULL,

            -- Processing
            status VARCHAR(50) DEFAULT 'received',
            response_sent TEXT,
            processed_at TIMESTAMP WITH TIME ZONE,

            -- AI processing (if used)
            ai_interpreted BOOLEAN DEFAULT FALSE,
            ai_confidence DECIMAL(3,2),

            -- Error tracking
            error_message TEXT,

            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,

            CONSTRAINT valid_sms_status CHECK (status IN ('received', 'processing', 'completed', 'failed', 'invalid'))
        );
        """,

        """
        CREATE INDEX IF NOT EXISTS idx_sms_command_phone
        ON portal_sms_command_history(phone_number, created_at DESC);
        """,

        """
        CREATE INDEX IF NOT EXISTS idx_sms_command_realtor
        ON portal_sms_command_history(realtor_id, created_at DESC)
        WHERE realtor_id IS NOT NULL;
        """,

        # ============================================================================
        # 10. TRIGGERS - Auto-update timestamps
        # ============================================================================
        """
        CREATE OR REPLACE FUNCTION realtor_portal_update_updated_at()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.updated_at = CURRENT_TIMESTAMP;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """,

        """
        DROP TRIGGER IF EXISTS update_realtor_portal_users_updated_at ON realtor_portal_users;
        CREATE TRIGGER update_realtor_portal_users_updated_at
        BEFORE UPDATE ON realtor_portal_users
        FOR EACH ROW EXECUTE FUNCTION realtor_portal_update_updated_at();
        """,

        """
        DROP TRIGGER IF EXISTS update_realtor_loan_assoc_updated_at ON realtor_loan_associations;
        CREATE TRIGGER update_realtor_loan_assoc_updated_at
        BEFORE UPDATE ON realtor_loan_associations
        FOR EACH ROW EXECUTE FUNCTION realtor_portal_update_updated_at();
        """,

        """
        DROP TRIGGER IF EXISTS update_letter_templates_updated_at ON letter_templates;
        CREATE TRIGGER update_letter_templates_updated_at
        BEFORE UPDATE ON letter_templates
        FOR EACH ROW EXECUTE FUNCTION realtor_portal_update_updated_at();
        """,

        """
        DROP TRIGGER IF EXISTS update_pre_approval_letters_updated_at ON pre_approval_letters;
        CREATE TRIGGER update_pre_approval_letters_updated_at
        BEFORE UPDATE ON pre_approval_letters
        FOR EACH ROW EXECUTE FUNCTION realtor_portal_update_updated_at();
        """,

        """
        DROP TRIGGER IF EXISTS update_portal_status_actions_updated_at ON portal_status_actions;
        CREATE TRIGGER update_portal_status_actions_updated_at
        BEFORE UPDATE ON portal_status_actions
        FOR EACH ROW EXECUTE FUNCTION realtor_portal_update_updated_at();
        """,

        """
        DROP TRIGGER IF EXISTS update_portal_crm_sync_state_updated_at ON portal_crm_sync_state;
        CREATE TRIGGER update_portal_crm_sync_state_updated_at
        BEFORE UPDATE ON portal_crm_sync_state
        FOR EACH ROW EXECUTE FUNCTION realtor_portal_update_updated_at();
        """,

        """
        DROP TRIGGER IF EXISTS update_portal_limit_policies_updated_at ON portal_limit_policies;
        CREATE TRIGGER update_portal_limit_policies_updated_at
        BEFORE UPDATE ON portal_limit_policies
        FOR EACH ROW EXECUTE FUNCTION realtor_portal_update_updated_at();
        """,

        # ============================================================================
        # 11. SEED DEFAULT STATUS ACTIONS - System-wide defaults
        # ============================================================================
        """
        INSERT INTO portal_status_actions (
            organization_id, loan_status,
            can_view_status, can_view_timeline, can_view_documents, can_download_documents,
            can_upload_documents, can_send_messages, can_request_update,
            can_generate_prequal, can_generate_preapproval, can_view_conditions,
            can_schedule_meeting, ai_assistant_enabled
        ) VALUES
        -- Lead stage: Limited access, can generate prequal
        (NULL, 'lead', true, false, false, false, false, true, true, true, false, false, true, true),

        -- Application stage: More visibility
        (NULL, 'application', true, true, false, false, false, true, true, true, false, false, true, true),

        -- Processing: Can see documents
        (NULL, 'processing', true, true, true, true, true, true, true, false, true, false, true, true),

        -- Submitted to UW: Full visibility
        (NULL, 'submitted', true, true, true, true, true, true, true, false, true, true, true, true),

        -- Underwriting: Full visibility
        (NULL, 'underwriting', true, true, true, true, true, true, true, false, true, true, true, true),

        -- Conditional Approval: Full access
        (NULL, 'conditional_approval', true, true, true, true, true, true, true, false, true, true, true, true),

        -- Clear to Close: Final stage visibility
        (NULL, 'clear_to_close', true, true, true, true, false, true, true, false, false, true, true, true),

        -- Closed/Funded: Read-only
        (NULL, 'funded', true, true, true, true, false, false, false, false, false, false, false, true),

        -- Denied: Limited
        (NULL, 'denied', true, true, false, false, false, true, false, false, false, false, true, true),

        -- Withdrawn: Limited
        (NULL, 'withdrawn', true, true, false, false, false, false, false, false, false, false, false, false)

        ON CONFLICT (organization_id, loan_status) DO NOTHING;
        """,

        # ============================================================================
        # 12. SEED DEFAULT LIMIT POLICIES
        # ============================================================================
        """
        INSERT INTO portal_limit_policies (
            organization_id, policy_type, policy_key,
            max_per_hour, max_per_day, max_per_month
        ) VALUES
        -- Letter generation limits (system-wide defaults)
        (NULL, 'letter_generation', 'prequal', 10, 50, 500),
        (NULL, 'letter_generation', 'preapproval', 5, 20, 200),

        -- API call limits
        (NULL, 'api_calls', 'realtor_portal', 1000, 10000, 100000),

        -- Message limits
        (NULL, 'messages', 'sms', 50, 200, 2000),
        (NULL, 'messages', 'email', 100, 500, 5000),

        -- AI assistant limits
        (NULL, 'ai_assistant', 'queries', 100, 500, 5000)

        ON CONFLICT (organization_id, policy_type, policy_key) DO NOTHING;
        """,

        # ============================================================================
        # 13. CREATE DEFAULT LETTER TEMPLATE (Pre-Qual)
        # ============================================================================
        """
        INSERT INTO letter_templates (
            organization_id, template_type, name, version,
            html_template, variables_schema, is_default
        ) VALUES (
            1,
            'prequal',
            'Standard Pre-Qualification Letter',
            1,
            E'<!DOCTYPE html>
<html>
<head>
    <style>
        body { font-family: Arial, sans-serif; margin: 40px; line-height: 1.6; }
        .header { text-align: center; margin-bottom: 30px; }
        .logo { max-height: 60px; }
        .date { text-align: right; margin-bottom: 20px; }
        .recipient { margin-bottom: 20px; }
        .body { margin-bottom: 30px; }
        .amount { font-size: 1.2em; font-weight: bold; color: #2563eb; }
        .footer { margin-top: 40px; font-size: 0.9em; color: #666; }
        .signature { margin-top: 40px; }
        .nmls { font-size: 0.8em; color: #888; }
    </style>
</head>
<body>
    <div class="header">
        <img src="{{company_logo}}" alt="{{company_name}}" class="logo">
    </div>

    <div class="date">{{letter_date}}</div>

    <div class="recipient">
        <strong>{{borrower_name}}</strong><br>
        {{borrower_address}}
    </div>

    <div class="body">
        <p>Dear {{borrower_first_name}},</p>

        <p>Based on the information you have provided, I am pleased to inform you that you
        <strong>pre-qualify</strong> for a home loan up to:</p>

        <p class="amount">${{prequal_amount}}</p>

        <p>This pre-qualification is based on the following:</p>
        <ul>
            <li>Estimated annual income: ${{annual_income}}</li>
            <li>Estimated credit profile: {{credit_tier}}</li>
            <li>Loan program: {{loan_program}}</li>
        </ul>

        <p>This letter is not a commitment to lend and is subject to verification of all
        information provided, satisfactory appraisal, title search, and other conditions.</p>

        <p>This pre-qualification is valid for <strong>90 days</strong> from the date of this letter.</p>

        <p>Please contact me if you have any questions.</p>
    </div>

    <div class="signature">
        <p>Sincerely,</p>
        <p>
            <strong>{{lo_name}}</strong><br>
            {{lo_title}}<br>
            {{lo_phone}}<br>
            {{lo_email}}
        </p>
        <p class="nmls">NMLS# {{lo_nmls}} | {{company_name}} NMLS# {{company_nmls}}</p>
    </div>

    <div class="footer">
        <p>{{compliance_footer}}</p>
    </div>
</body>
</html>',
            '{
                "borrower_name": {"type": "string", "required": true},
                "borrower_first_name": {"type": "string", "required": true},
                "borrower_address": {"type": "string", "required": false},
                "prequal_amount": {"type": "currency", "required": true},
                "annual_income": {"type": "currency", "required": true},
                "credit_tier": {"type": "string", "required": true},
                "loan_program": {"type": "string", "required": true},
                "letter_date": {"type": "date", "required": true},
                "lo_name": {"type": "string", "required": true, "source": "user"},
                "lo_title": {"type": "string", "required": true, "source": "user"},
                "lo_phone": {"type": "string", "required": true, "source": "user"},
                "lo_email": {"type": "string", "required": true, "source": "user"},
                "lo_nmls": {"type": "string", "required": true, "source": "user"},
                "company_name": {"type": "string", "required": true, "source": "org"},
                "company_nmls": {"type": "string", "required": true, "source": "org"},
                "company_logo": {"type": "url", "required": true, "source": "org"},
                "compliance_footer": {"type": "string", "required": true, "source": "org"}
            }'::jsonb,
            true
        )
        ON CONFLICT (organization_id, template_type, version) DO NOTHING;
        """,

        # ============================================================================
        # 14. ROW-LEVEL SECURITY POLICIES
        # ============================================================================
        """
        ALTER TABLE realtor_portal_users ENABLE ROW LEVEL SECURITY;
        """,

        """
        ALTER TABLE realtor_loan_associations ENABLE ROW LEVEL SECURITY;
        """,

        """
        ALTER TABLE pre_approval_letters ENABLE ROW LEVEL SECURITY;
        """,

        """
        ALTER TABLE portal_communication_events ENABLE ROW LEVEL SECURITY;
        """,

        # ============================================================================
        # 15. GIN INDEXES FOR JSONB SEARCH
        # ============================================================================
        """
        CREATE INDEX IF NOT EXISTS idx_realtor_notification_prefs_gin
        ON realtor_portal_users USING GIN (notification_preferences);
        """,

        """
        CREATE INDEX IF NOT EXISTS idx_letter_variables_gin
        ON pre_approval_letters USING GIN (variables_used);
        """,

        """
        CREATE INDEX IF NOT EXISTS idx_comm_events_metadata_gin
        ON portal_communication_events USING GIN (metadata);
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

    logger.info("Realtor Portal migration completed successfully!")


def rollback_migration():
    """Drop all Realtor Portal tables (use with caution!)"""

    drop_commands = [
        "DROP TABLE IF EXISTS portal_sms_command_history CASCADE;",
        "DROP TABLE IF EXISTS portal_limit_policies CASCADE;",
        "DROP TABLE IF EXISTS portal_crm_sync_state CASCADE;",
        "DROP TABLE IF EXISTS portal_communication_events CASCADE;",
        "DROP TABLE IF EXISTS pre_approval_letters CASCADE;",
        "DROP TABLE IF EXISTS letter_templates CASCADE;",
        "DROP TABLE IF EXISTS portal_status_actions CASCADE;",
        "DROP TABLE IF EXISTS realtor_loan_associations CASCADE;",
        "DROP TABLE IF EXISTS realtor_portal_users CASCADE;",
        "DROP FUNCTION IF EXISTS realtor_portal_update_updated_at() CASCADE;",
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

    logger.info("Realtor Portal tables dropped!")


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "rollback":
        confirm = input("Are you sure you want to drop all Realtor Portal tables? (yes/no): ")
        if confirm.lower() == "yes":
            rollback_migration()
        else:
            print("Rollback cancelled.")
    else:
        run_migration()
