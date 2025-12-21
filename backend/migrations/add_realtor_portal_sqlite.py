"""
Migration: Add Realtor Portal Tables (SQLite-compatible)
Creates essential Realtor Portal tables for local development with SQLite.

Usage:
    cd backend
    source venv/bin/activate
    python migrations/add_realtor_portal_sqlite.py
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
    """Create Realtor Portal tables (SQLite-compatible)"""

    sql_commands = [
        # ============================================================================
        # 1. REALTOR PORTAL USERS - Realtors with portal access
        # ============================================================================
        """
        CREATE TABLE IF NOT EXISTS realtor_portal_users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            organization_id INTEGER NOT NULL,

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
            primary_lo_id INTEGER,

            -- Portal settings (JSON stored as TEXT)
            notification_preferences TEXT DEFAULT '{"email": true, "sms": true, "push": false}',
            timezone VARCHAR(100) DEFAULT 'America/New_York',

            -- Status
            is_active BOOLEAN DEFAULT 1,
            last_login_at TIMESTAMP,
            login_count INTEGER DEFAULT 0,

            -- Timestamps
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

            UNIQUE(organization_id, email)
        );
        """,

        "CREATE INDEX IF NOT EXISTS idx_realtor_portal_users_org ON realtor_portal_users(organization_id, is_active);",
        "CREATE INDEX IF NOT EXISTS idx_realtor_portal_users_email ON realtor_portal_users(email);",
        "CREATE INDEX IF NOT EXISTS idx_realtor_portal_users_lo ON realtor_portal_users(primary_lo_id);",

        # ============================================================================
        # 2. REALTOR LOAN ASSOCIATIONS - Links realtors to specific loans
        # ============================================================================
        """
        CREATE TABLE IF NOT EXISTS realtor_loan_associations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            realtor_id INTEGER NOT NULL,
            loan_id INTEGER NOT NULL,

            -- Role on this loan
            role VARCHAR(50) DEFAULT 'buyer_agent',

            -- Access level
            access_granted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            access_granted_by INTEGER,
            access_revoked_at TIMESTAMP,

            -- Engagement tracking
            last_viewed_at TIMESTAMP,
            view_count INTEGER DEFAULT 0,

            -- Notification preferences for this loan
            notify_status_changes BOOLEAN DEFAULT 1,
            notify_documents BOOLEAN DEFAULT 1,
            notify_messages BOOLEAN DEFAULT 1,

            -- Timestamps
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

            UNIQUE(realtor_id, loan_id)
        );
        """,

        "CREATE INDEX IF NOT EXISTS idx_realtor_loan_assoc_realtor ON realtor_loan_associations(realtor_id);",
        "CREATE INDEX IF NOT EXISTS idx_realtor_loan_assoc_loan ON realtor_loan_associations(loan_id);",

        # ============================================================================
        # 3. PORTAL STATUS ACTIONS - Defines what realtors can do at each loan status
        # ============================================================================
        """
        CREATE TABLE IF NOT EXISTS portal_status_actions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            organization_id INTEGER,

            -- Status configuration
            loan_status VARCHAR(50) NOT NULL,

            -- Available actions (all boolean)
            can_view_status BOOLEAN DEFAULT 1,
            can_view_timeline BOOLEAN DEFAULT 1,
            can_view_documents BOOLEAN DEFAULT 0,
            can_download_documents BOOLEAN DEFAULT 0,
            can_upload_documents BOOLEAN DEFAULT 0,
            can_send_messages BOOLEAN DEFAULT 1,
            can_request_update BOOLEAN DEFAULT 1,
            can_generate_prequal BOOLEAN DEFAULT 0,
            can_generate_preapproval BOOLEAN DEFAULT 0,
            can_view_conditions BOOLEAN DEFAULT 0,
            can_schedule_meeting BOOLEAN DEFAULT 1,

            -- Visibility settings (arrays stored as JSON TEXT)
            visible_document_types TEXT DEFAULT '[]',
            hidden_fields TEXT DEFAULT '[]',

            -- AI assistant availability
            ai_assistant_enabled BOOLEAN DEFAULT 1,
            ai_allowed_topics TEXT DEFAULT '["status", "timeline", "general"]',

            -- Priority (for org-specific overrides)
            priority INTEGER DEFAULT 0,

            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

            UNIQUE(organization_id, loan_status)
        );
        """,

        "CREATE INDEX IF NOT EXISTS idx_portal_status_actions_lookup ON portal_status_actions(organization_id, loan_status);",

        # ============================================================================
        # 4. LETTER TEMPLATES - Versioned templates for pre-qual/pre-approval letters
        # ============================================================================
        """
        CREATE TABLE IF NOT EXISTS letter_templates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            organization_id INTEGER NOT NULL,

            -- Template identification
            template_type VARCHAR(50) NOT NULL,
            name VARCHAR(255) NOT NULL,
            version INTEGER NOT NULL DEFAULT 1,

            -- Template content
            html_template TEXT NOT NULL,
            css_styles TEXT,
            header_html TEXT,
            footer_html TEXT,

            -- Variable schema (JSON stored as TEXT)
            variables_schema TEXT NOT NULL DEFAULT '{}',

            -- PDF generation settings
            page_size VARCHAR(20) DEFAULT 'letter',
            margins TEXT DEFAULT '{"top": "1in", "bottom": "1in", "left": "1in", "right": "1in"}',

            -- Status
            is_active BOOLEAN DEFAULT 1,
            is_default BOOLEAN DEFAULT 0,

            -- Compliance
            requires_nmls BOOLEAN DEFAULT 1,
            requires_signature BOOLEAN DEFAULT 1,
            expiration_days INTEGER DEFAULT 90,

            -- Audit
            created_by INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

            UNIQUE(organization_id, template_type, version)
        );
        """,

        "CREATE INDEX IF NOT EXISTS idx_letter_templates_org_type ON letter_templates(organization_id, template_type, is_active);",

        # ============================================================================
        # 5. PRE-APPROVAL LETTERS - Generated letters with versioning
        # ============================================================================
        """
        CREATE TABLE IF NOT EXISTS pre_approval_letters (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            organization_id INTEGER NOT NULL,
            loan_id INTEGER NOT NULL,
            template_id INTEGER,

            -- Letter details
            letter_type VARCHAR(50) NOT NULL,
            version INTEGER NOT NULL DEFAULT 1,

            -- Content
            generated_html TEXT NOT NULL,
            generated_pdf_url TEXT,
            variables_used TEXT NOT NULL DEFAULT '{}',

            -- Property-specific (for property-specific letters)
            property_address TEXT,
            purchase_price DECIMAL(15,2),

            -- Approval details
            approved_amount DECIMAL(15,2) NOT NULL,
            down_payment_percent DECIMAL(5,2),
            loan_program VARCHAR(100),
            interest_rate DECIMAL(6,4),

            -- Validity
            issued_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            expires_at TIMESTAMP NOT NULL,
            is_void BOOLEAN DEFAULT 0,
            voided_at TIMESTAMP,
            voided_by INTEGER,
            void_reason TEXT,

            -- Generation details
            generated_by INTEGER,
            generated_by_realtor INTEGER,
            generation_method VARCHAR(50) DEFAULT 'manual',

            -- Access tracking
            download_count INTEGER DEFAULT 0,
            last_downloaded_at TIMESTAMP,
            share_token VARCHAR(100) UNIQUE,

            -- Timestamps
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """,

        "CREATE INDEX IF NOT EXISTS idx_pre_approval_letters_loan ON pre_approval_letters(loan_id, is_void);",
        "CREATE INDEX IF NOT EXISTS idx_pre_approval_letters_share ON pre_approval_letters(share_token);",
        "CREATE INDEX IF NOT EXISTS idx_pre_approval_letters_realtor ON pre_approval_letters(generated_by_realtor);",

        # ============================================================================
        # 6. COMMUNICATION EVENTS - Track all portal communications
        # ============================================================================
        """
        CREATE TABLE IF NOT EXISTS portal_communication_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            organization_id INTEGER NOT NULL,

            -- Participants
            realtor_id INTEGER,
            loan_id INTEGER,
            user_id INTEGER,

            -- Event details
            event_type VARCHAR(50) NOT NULL,
            channel VARCHAR(50) NOT NULL,
            direction VARCHAR(20) NOT NULL,

            -- Content
            subject TEXT,
            content TEXT,
            content_html TEXT,
            attachments TEXT DEFAULT '[]',

            -- Metadata (JSON stored as TEXT)
            metadata TEXT DEFAULT '{}',

            -- Delivery status
            status VARCHAR(50) DEFAULT 'sent',
            delivered_at TIMESTAMP,
            read_at TIMESTAMP,
            failed_at TIMESTAMP,
            failure_reason TEXT,

            -- AI involvement
            ai_generated BOOLEAN DEFAULT 0,
            ai_model VARCHAR(100),
            ai_prompt_tokens INTEGER,
            ai_completion_tokens INTEGER,

            -- Timestamps
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """,

        "CREATE INDEX IF NOT EXISTS idx_comm_events_realtor ON portal_communication_events(realtor_id, created_at);",
        "CREATE INDEX IF NOT EXISTS idx_comm_events_loan ON portal_communication_events(loan_id, created_at);",
        "CREATE INDEX IF NOT EXISTS idx_comm_events_type ON portal_communication_events(event_type, created_at);",

        # ============================================================================
        # 7. CRM SYNC STATE - Track WebSocket sync state for real-time updates
        # ============================================================================
        """
        CREATE TABLE IF NOT EXISTS portal_crm_sync_state (
            id INTEGER PRIMARY KEY AUTOINCREMENT,

            -- What we're syncing
            entity_type VARCHAR(50) NOT NULL,
            entity_id INTEGER NOT NULL,

            -- Sync metadata
            last_synced_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_sync_version INTEGER DEFAULT 1,
            sync_hash VARCHAR(64),

            -- Connection tracking
            active_connections INTEGER DEFAULT 0,
            last_connection_at TIMESTAMP,

            -- Conflict handling
            has_conflicts BOOLEAN DEFAULT 0,
            conflict_data TEXT,

            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

            UNIQUE(entity_type, entity_id)
        );
        """,

        "CREATE INDEX IF NOT EXISTS idx_crm_sync_state_entity ON portal_crm_sync_state(entity_type, entity_id);",

        # ============================================================================
        # 8. PORTAL LIMIT POLICIES - Rate limiting and usage policies
        # ============================================================================
        """
        CREATE TABLE IF NOT EXISTS portal_limit_policies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            organization_id INTEGER,

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
            hour_reset_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            day_reset_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            month_reset_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

            -- Status
            is_active BOOLEAN DEFAULT 1,

            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

            UNIQUE(organization_id, policy_type, policy_key)
        );
        """,

        "CREATE INDEX IF NOT EXISTS idx_limit_policies_lookup ON portal_limit_policies(organization_id, policy_type, is_active);",

        # ============================================================================
        # 9. SMS COMMAND HISTORY - Track SMS-based portal commands
        # ============================================================================
        """
        CREATE TABLE IF NOT EXISTS portal_sms_command_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,

            -- Sender identification
            phone_number VARCHAR(50) NOT NULL,
            realtor_id INTEGER,

            -- Command details
            raw_message TEXT NOT NULL,
            parsed_command VARCHAR(50),
            parsed_args TEXT DEFAULT '{}',

            -- Loan context (if determined)
            loan_id INTEGER,

            -- Processing
            status VARCHAR(50) DEFAULT 'received',
            response_sent TEXT,
            processed_at TIMESTAMP,

            -- AI processing (if used)
            ai_interpreted BOOLEAN DEFAULT 0,
            ai_confidence DECIMAL(3,2),

            -- Error tracking
            error_message TEXT,

            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """,

        "CREATE INDEX IF NOT EXISTS idx_sms_command_phone ON portal_sms_command_history(phone_number, created_at);",
        "CREATE INDEX IF NOT EXISTS idx_sms_command_realtor ON portal_sms_command_history(realtor_id, created_at);",

        # ============================================================================
        # 10. SEED DEFAULT STATUS ACTIONS - System-wide defaults
        # ============================================================================
        """
        INSERT OR IGNORE INTO portal_status_actions (
            organization_id, loan_status,
            can_view_status, can_view_timeline, can_view_documents, can_download_documents,
            can_upload_documents, can_send_messages, can_request_update,
            can_generate_prequal, can_generate_preapproval, can_view_conditions,
            can_schedule_meeting, ai_assistant_enabled
        ) VALUES
        (NULL, 'lead', 1, 0, 0, 0, 0, 1, 1, 1, 0, 0, 1, 1),
        (NULL, 'application', 1, 1, 0, 0, 0, 1, 1, 1, 0, 0, 1, 1),
        (NULL, 'processing', 1, 1, 1, 1, 1, 1, 1, 0, 1, 0, 1, 1),
        (NULL, 'submitted', 1, 1, 1, 1, 1, 1, 1, 0, 1, 1, 1, 1),
        (NULL, 'underwriting', 1, 1, 1, 1, 1, 1, 1, 0, 1, 1, 1, 1),
        (NULL, 'conditional_approval', 1, 1, 1, 1, 1, 1, 1, 0, 1, 1, 1, 1),
        (NULL, 'clear_to_close', 1, 1, 1, 1, 0, 1, 1, 0, 0, 1, 1, 1),
        (NULL, 'funded', 1, 1, 1, 1, 0, 0, 0, 0, 0, 0, 0, 1),
        (NULL, 'denied', 1, 1, 0, 0, 0, 1, 0, 0, 0, 0, 1, 1),
        (NULL, 'withdrawn', 1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0);
        """,

        # ============================================================================
        # 11. SEED DEFAULT LIMIT POLICIES
        # ============================================================================
        """
        INSERT OR IGNORE INTO portal_limit_policies (
            organization_id, policy_type, policy_key,
            max_per_hour, max_per_day, max_per_month
        ) VALUES
        (NULL, 'letter_generation', 'prequal', 10, 50, 500),
        (NULL, 'letter_generation', 'preapproval', 5, 20, 200),
        (NULL, 'api_calls', 'realtor_portal', 1000, 10000, 100000),
        (NULL, 'messages', 'sms', 50, 200, 2000),
        (NULL, 'messages', 'email', 100, 500, 5000),
        (NULL, 'ai_assistant', 'queries', 100, 500, 5000);
        """,

        # ============================================================================
        # 12. CREATE DEFAULT LETTER TEMPLATE (Pre-Qual)
        # ============================================================================
        """
        INSERT OR IGNORE INTO letter_templates (
            organization_id, template_type, name, version,
            html_template, variables_schema, is_default
        ) VALUES (
            1,
            'prequal',
            'Standard Pre-Qualification Letter',
            1,
            '<!DOCTYPE html>
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
            }',
            1
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
                connection.rollback()
                continue

    logger.info("Realtor Portal tables (SQLite) created successfully!")


def rollback_migration():
    """Drop all Realtor Portal tables (use with caution!)"""

    drop_commands = [
        "DROP TABLE IF EXISTS portal_sms_command_history;",
        "DROP TABLE IF EXISTS portal_limit_policies;",
        "DROP TABLE IF EXISTS portal_crm_sync_state;",
        "DROP TABLE IF EXISTS portal_communication_events;",
        "DROP TABLE IF EXISTS pre_approval_letters;",
        "DROP TABLE IF EXISTS letter_templates;",
        "DROP TABLE IF EXISTS portal_status_actions;",
        "DROP TABLE IF EXISTS realtor_loan_associations;",
        "DROP TABLE IF EXISTS realtor_portal_users;",
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
