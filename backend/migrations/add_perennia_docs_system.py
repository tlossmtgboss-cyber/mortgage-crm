"""
Migration: Add Perennia Docs AI System Tables

Creates all tables for the AI-powered document management system:
- perennia_document_requests
- perennia_documents
- perennia_template_packs
- perennia_document_rules
- perennia_document_events
- perennia_notifications
- perennia_retention_policies
- perennia_portal_sessions

Run with:
    python -m migrations.add_perennia_docs_system
"""

import os
import sys
import logging
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Get database URL
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://localhost:5432/perennia")
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)


MIGRATION_SQL = """
-- =============================================================================
-- PERENNIA DOCS AI - DATABASE MIGRATION
-- =============================================================================

-- Template Packs (create first for FK reference)
CREATE TABLE IF NOT EXISTS perennia_template_packs (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    slug VARCHAR(100) NOT NULL,
    description TEXT,
    version VARCHAR(20) DEFAULT '1',
    loan_programs TEXT[],
    employment_types TEXT[],
    property_types TEXT[],
    config JSONB NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_template_pack_slug_version UNIQUE (slug, version)
);

-- Document Requests
CREATE TABLE IF NOT EXISTS perennia_document_requests (
    id SERIAL PRIMARY KEY,
    loan_id INTEGER REFERENCES loans(id),
    lead_id INTEGER REFERENCES leads(id),
    template_pack_id INTEGER REFERENCES perennia_template_packs(id),
    doc_type VARCHAR(50) NOT NULL,
    doc_subtype VARCHAR(50),
    title VARCHAR(255) NOT NULL,
    description TEXT,
    quantity INTEGER DEFAULT 1,
    status VARCHAR(20) DEFAULT 'pending',
    priority VARCHAR(20) DEFAULT 'normal',
    expiration_date TIMESTAMP WITH TIME ZONE,
    expiration_threshold INTEGER DEFAULT 90,
    template_pack_version VARCHAR(20),
    reminder_schedule JSONB,
    last_reminder_sent TIMESTAMP WITH TIME ZONE,
    reminder_count INTEGER DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_doc_request_loan ON perennia_document_requests(loan_id);
CREATE INDEX IF NOT EXISTS idx_doc_request_lead ON perennia_document_requests(lead_id);
CREATE INDEX IF NOT EXISTS idx_doc_request_status ON perennia_document_requests(status);
CREATE INDEX IF NOT EXISTS idx_doc_request_expiration ON perennia_document_requests(expiration_date);
CREATE INDEX IF NOT EXISTS idx_doc_request_doc_type ON perennia_document_requests(doc_type);

-- Documents
CREATE TABLE IF NOT EXISTS perennia_documents (
    id SERIAL PRIMARY KEY,
    loan_id INTEGER REFERENCES loans(id),
    lead_id INTEGER REFERENCES leads(id),
    request_id INTEGER REFERENCES perennia_document_requests(id),
    borrower_id INTEGER,
    uploaded_by_user_id INTEGER REFERENCES users(id),

    -- File metadata
    file_name VARCHAR(500) NOT NULL,
    file_size BIGINT NOT NULL,
    mime_type VARCHAR(100) NOT NULL,

    -- Storage keys (S3 paths)
    original_storage_key VARCHAR(500) NOT NULL,
    compressed_storage_key VARCHAR(500),
    preview_storage_key VARCHAR(500),

    -- Compression info
    compression_ratio NUMERIC(5, 2),
    compression_method VARCHAR(50),
    derivative_type VARCHAR(20) DEFAULT 'ORIGINAL',

    -- Status tracking
    status VARCHAR(20) DEFAULT 'pending_upload',
    rejection_reason TEXT,

    -- AI Classification
    classification_status VARCHAR(20) DEFAULT 'pending',
    doc_type VARCHAR(50),
    doc_subtype VARCHAR(50),
    classification_confidence NUMERIC(3, 2),
    extracted_data JSONB,
    validation_errors JSONB,
    quality_checks JSONB,

    -- AI metadata
    ai_model VARCHAR(50),
    ai_prompt_hash VARCHAR(64),
    retrieval_context_ids TEXT[],

    -- Virus scan
    virus_scan_status VARCHAR(20) DEFAULT 'pending',
    virus_scan_result JSONB,

    -- Document dates
    document_date TIMESTAMP WITH TIME ZONE,
    expires_at TIMESTAMP WITH TIME ZONE,

    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_document_loan ON perennia_documents(loan_id);
CREATE INDEX IF NOT EXISTS idx_document_lead ON perennia_documents(lead_id);
CREATE INDEX IF NOT EXISTS idx_document_request ON perennia_documents(request_id);
CREATE INDEX IF NOT EXISTS idx_document_status ON perennia_documents(status);
CREATE INDEX IF NOT EXISTS idx_document_scan_status ON perennia_documents(virus_scan_status);
CREATE INDEX IF NOT EXISTS idx_document_expires ON perennia_documents(expires_at);
CREATE INDEX IF NOT EXISTS idx_document_doc_type ON perennia_documents(doc_type);

-- Document Rules
CREATE TABLE IF NOT EXISTS perennia_document_rules (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    trigger VARCHAR(50) NOT NULL,
    conditions JSONB NOT NULL,
    actions JSONB NOT NULL,
    priority INTEGER DEFAULT 100,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_rule_trigger ON perennia_document_rules(trigger);
CREATE INDEX IF NOT EXISTS idx_rule_active ON perennia_document_rules(is_active);

-- Document Events (Audit Trail)
CREATE TABLE IF NOT EXISTS perennia_document_events (
    id SERIAL PRIMARY KEY,
    loan_id INTEGER REFERENCES loans(id),
    lead_id INTEGER REFERENCES leads(id),
    request_id INTEGER REFERENCES perennia_document_requests(id),
    document_id INTEGER REFERENCES perennia_documents(id),
    event_type VARCHAR(50) NOT NULL,
    event_data JSONB,
    actor_type VARCHAR(20) NOT NULL,
    actor_id INTEGER,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_event_loan ON perennia_document_events(loan_id);
CREATE INDEX IF NOT EXISTS idx_event_document ON perennia_document_events(document_id);
CREATE INDEX IF NOT EXISTS idx_event_type ON perennia_document_events(event_type);
CREATE INDEX IF NOT EXISTS idx_event_created ON perennia_document_events(created_at);

-- Notifications
CREATE TABLE IF NOT EXISTS perennia_notifications (
    id SERIAL PRIMARY KEY,
    loan_id INTEGER REFERENCES loans(id),
    lead_id INTEGER REFERENCES leads(id),
    recipient_email VARCHAR(255),
    recipient_phone VARCHAR(20),
    recipient_user_id INTEGER REFERENCES users(id),
    channel VARCHAR(10) NOT NULL,
    template VARCHAR(50) NOT NULL,
    subject VARCHAR(500),
    body TEXT NOT NULL,
    metadata JSONB,
    status VARCHAR(20) DEFAULT 'pending',
    sent_at TIMESTAMP WITH TIME ZONE,
    failure_reason TEXT,
    quiet_hours_start VARCHAR(5) DEFAULT '21:00',
    quiet_hours_end VARCHAR(5) DEFAULT '08:00',
    scheduled_for TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_notification_status ON perennia_notifications(status);
CREATE INDEX IF NOT EXISTS idx_notification_scheduled ON perennia_notifications(scheduled_for);

-- Retention Policies
CREATE TABLE IF NOT EXISTS perennia_retention_policies (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    doc_types TEXT[],
    retention_years INTEGER DEFAULT 3,
    archive_after_days INTEGER DEFAULT 365,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Portal Sessions (Magic Link Auth)
CREATE TABLE IF NOT EXISTS perennia_portal_sessions (
    id SERIAL PRIMARY KEY,
    lead_id INTEGER REFERENCES leads(id) NOT NULL,
    loan_id INTEGER REFERENCES loans(id),
    magic_link_token VARCHAR(255) UNIQUE NOT NULL,
    token_expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
    session_expires_at TIMESTAMP WITH TIME ZONE,
    last_activity_at TIMESTAMP WITH TIME ZONE,
    ip_address VARCHAR(45),
    user_agent VARCHAR(500),
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_portal_session_token ON perennia_portal_sessions(magic_link_token);
CREATE INDEX IF NOT EXISTS idx_portal_session_lead ON perennia_portal_sessions(lead_id);

-- =============================================================================
-- SEED DEFAULT TEMPLATE PACKS
-- =============================================================================

INSERT INTO perennia_template_packs (name, slug, description, version, loan_programs, employment_types, config, is_active)
VALUES
(
    'Conventional W2 Salaried',
    'conventional-w2-salaried',
    'Standard document requirements for conventional loans with W2 employment',
    '1',
    ARRAY['CONVENTIONAL'],
    ARRAY['W2'],
    '{
        "documentRequirements": [
            {
                "docType": "PAYSTUB",
                "title": "Recent Paystubs",
                "description": "Upload your 2 most recent paystubs showing year-to-date earnings",
                "quantity": 2,
                "expirationThreshold": 30,
                "required": true
            },
            {
                "docType": "W2",
                "title": "W-2 Forms",
                "description": "Upload W-2 forms from the past 2 years",
                "quantity": 2,
                "expirationThreshold": 365,
                "required": true
            },
            {
                "docType": "BANK_STATEMENT",
                "docSubtype": "CHECKING",
                "title": "Bank Statements",
                "description": "Upload your 2 most recent bank statements for all accounts",
                "quantity": 2,
                "expirationThreshold": 60,
                "required": true
            },
            {
                "docType": "DRIVERS_LICENSE",
                "title": "Government ID",
                "description": "Upload a copy of your drivers license or passport",
                "quantity": 1,
                "expirationThreshold": 365,
                "required": true
            }
        ],
        "reminderSchedule": [1, 3, 7, 14],
        "autoApproveRules": {
            "enabled": true,
            "minConfidence": 0.95,
            "requireCleanScan": true
        }
    }'::jsonb,
    true
),
(
    'Conventional Self-Employed',
    'conventional-self-employed',
    'Document requirements for self-employed borrowers on conventional loans',
    '1',
    ARRAY['CONVENTIONAL'],
    ARRAY['SELF_EMPLOYED'],
    '{
        "documentRequirements": [
            {
                "docType": "TAX_RETURN",
                "docSubtype": "1040",
                "title": "Personal Tax Returns",
                "description": "Upload complete personal tax returns (all pages and schedules) for past 2 years",
                "quantity": 2,
                "expirationThreshold": 365,
                "required": true
            },
            {
                "docType": "TAX_RETURN",
                "docSubtype": "SCHEDULE_C",
                "title": "Business Tax Returns",
                "description": "Upload business tax returns for past 2 years if applicable",
                "quantity": 2,
                "expirationThreshold": 365,
                "required": false
            },
            {
                "docType": "PROFIT_LOSS",
                "title": "Year-to-Date P&L",
                "description": "Upload a year-to-date profit and loss statement",
                "quantity": 1,
                "expirationThreshold": 30,
                "required": true
            },
            {
                "docType": "BANK_STATEMENT",
                "docSubtype": "BUSINESS",
                "title": "Business Bank Statements",
                "description": "Upload 3 months of business bank statements",
                "quantity": 3,
                "expirationThreshold": 60,
                "required": true
            },
            {
                "docType": "BANK_STATEMENT",
                "docSubtype": "CHECKING",
                "title": "Personal Bank Statements",
                "description": "Upload 2 months of personal bank statements",
                "quantity": 2,
                "expirationThreshold": 60,
                "required": true
            },
            {
                "docType": "DRIVERS_LICENSE",
                "title": "Government ID",
                "description": "Upload a copy of your drivers license or passport",
                "quantity": 1,
                "expirationThreshold": 365,
                "required": true
            }
        ],
        "reminderSchedule": [1, 3, 7, 14],
        "autoApproveRules": {
            "enabled": false
        }
    }'::jsonb,
    true
),
(
    'FHA Standard',
    'fha-standard',
    'Standard document requirements for FHA loans',
    '1',
    ARRAY['FHA'],
    ARRAY['W2', 'SELF_EMPLOYED'],
    '{
        "documentRequirements": [
            {
                "docType": "PAYSTUB",
                "title": "Recent Paystubs",
                "description": "Upload your most recent 30 days of paystubs",
                "quantity": 2,
                "expirationThreshold": 30,
                "required": true
            },
            {
                "docType": "W2",
                "title": "W-2 Forms",
                "description": "Upload W-2 forms from the past 2 years",
                "quantity": 2,
                "expirationThreshold": 365,
                "required": true
            },
            {
                "docType": "TAX_RETURN",
                "docSubtype": "1040",
                "title": "Tax Returns",
                "description": "Upload complete tax returns for the past 2 years",
                "quantity": 2,
                "expirationThreshold": 365,
                "required": true
            },
            {
                "docType": "BANK_STATEMENT",
                "title": "Bank Statements",
                "description": "Upload 2 months of bank statements for all accounts",
                "quantity": 2,
                "expirationThreshold": 60,
                "required": true
            },
            {
                "docType": "DRIVERS_LICENSE",
                "title": "Government ID",
                "description": "Upload a copy of your drivers license or passport",
                "quantity": 1,
                "expirationThreshold": 365,
                "required": true
            }
        ],
        "reminderSchedule": [1, 3, 7, 14],
        "autoApproveRules": {
            "enabled": true,
            "minConfidence": 0.95,
            "requireCleanScan": true
        }
    }'::jsonb,
    true
),
(
    'VA Standard',
    'va-standard',
    'Standard document requirements for VA loans',
    '1',
    ARRAY['VA'],
    ARRAY['W2', 'SELF_EMPLOYED'],
    '{
        "documentRequirements": [
            {
                "docType": "PAYSTUB",
                "title": "Recent Paystubs",
                "description": "Upload your most recent 30 days of paystubs",
                "quantity": 2,
                "expirationThreshold": 30,
                "required": true
            },
            {
                "docType": "W2",
                "title": "W-2 Forms",
                "description": "Upload W-2 forms from the past 2 years",
                "quantity": 2,
                "expirationThreshold": 365,
                "required": true
            },
            {
                "docType": "BANK_STATEMENT",
                "title": "Bank Statements",
                "description": "Upload 2 months of bank statements",
                "quantity": 2,
                "expirationThreshold": 60,
                "required": true
            },
            {
                "docType": "DRIVERS_LICENSE",
                "title": "Government ID",
                "description": "Upload a copy of your drivers license or passport",
                "quantity": 1,
                "expirationThreshold": 365,
                "required": true
            },
            {
                "docType": "OTHER",
                "docSubtype": "DD214",
                "title": "DD-214 / Certificate of Eligibility",
                "description": "Upload your DD-214 or VA Certificate of Eligibility",
                "quantity": 1,
                "expirationThreshold": 365,
                "required": true
            }
        ],
        "reminderSchedule": [1, 3, 7, 14],
        "autoApproveRules": {
            "enabled": true,
            "minConfidence": 0.95,
            "requireCleanScan": true
        }
    }'::jsonb,
    true
)
ON CONFLICT (slug, version) DO NOTHING;

-- =============================================================================
-- SEED DEFAULT RULES
-- =============================================================================

INSERT INTO perennia_document_rules (name, description, trigger, conditions, actions, priority, is_active)
VALUES
(
    'Auto-approve high confidence documents',
    'Automatically approve documents with high AI confidence and clean virus scan',
    'document_classified',
    '[
        {"field": "classification_confidence", "operator": "greater_than", "value": 0.95},
        {"field": "virus_scan_status", "operator": "equals", "value": "clean"},
        {"field": "quality_checks_passed", "operator": "equals", "value": true}
    ]'::jsonb,
    '[
        {"type": "UPDATE_STATUS", "params": {"newStatus": "approved"}},
        {"type": "CREATE_NOTIFICATION", "params": {"template": "DOCUMENT_APPROVED", "channel": "EMAIL"}}
    ]'::jsonb,
    10,
    true
),
(
    'Flag expired documents',
    'Automatically reject documents that are past expiration threshold',
    'document_classified',
    '[
        {"field": "is_expired", "operator": "equals", "value": true}
    ]'::jsonb,
    '[
        {"type": "UPDATE_STATUS", "params": {"newStatus": "rejected", "reason": "Document is expired. Please upload a more recent version."}},
        {"type": "CREATE_NOTIFICATION", "params": {"template": "DOCUMENT_EXPIRED", "channel": "EMAIL"}}
    ]'::jsonb,
    5,
    true
),
(
    'Notify LO on virus detection',
    'Send urgent notification when virus is detected in uploaded document',
    'virus_detected',
    '[]'::jsonb,
    '[
        {"type": "CREATE_NOTIFICATION", "params": {"template": "VIRUS_DETECTED", "channel": "EMAIL", "priority": "urgent", "recipientType": "LO"}}
    ]'::jsonb,
    1,
    true
)
ON CONFLICT DO NOTHING;

-- =============================================================================
-- SEED DEFAULT RETENTION POLICY
-- =============================================================================

INSERT INTO perennia_retention_policies (name, description, doc_types, retention_years, archive_after_days, is_active)
VALUES
(
    'Standard Mortgage Documents',
    'Default retention policy for all mortgage documents - 7 years per regulatory requirements',
    ARRAY['*'],
    7,
    365,
    true
)
ON CONFLICT DO NOTHING;
"""


def run_migration() -> dict:
    """Run the Perennia Docs AI migration."""
    results = {
        'success': True,
        'tables_created': [],
        'errors': []
    }

    engine = create_engine(DATABASE_URL)

    try:
        with engine.connect() as conn:
            # Execute migration SQL
            conn.execute(text(MIGRATION_SQL))
            conn.commit()

            # Verify tables were created
            verification = conn.execute(text("""
                SELECT table_name FROM information_schema.tables
                WHERE table_schema = 'public'
                AND table_name LIKE 'perennia_%'
                ORDER BY table_name
            """))

            results['tables_created'] = [row[0] for row in verification]

            logger.info(f"Created {len(results['tables_created'])} Perennia Docs AI tables")

    except Exception as e:
        logger.error(f"Migration failed: {e}")
        results['success'] = False
        results['errors'].append(str(e))

    return results


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description='Perennia Docs AI migration')
    parser.add_argument('--check', action='store_true', help='Check existing tables only')
    args = parser.parse_args()

    if args.check:
        engine = create_engine(DATABASE_URL)
        with engine.connect() as conn:
            result = conn.execute(text("""
                SELECT table_name FROM information_schema.tables
                WHERE table_schema = 'public'
                AND table_name LIKE 'perennia_%'
                ORDER BY table_name
            """))
            tables = [row[0] for row in result]
            print(f"Found {len(tables)} Perennia tables: {tables}")
    else:
        print("Running Perennia Docs AI migration...")
        results = run_migration()

        if results['success']:
            print(f"\n✓ Migration completed successfully!")
            print(f"Tables created: {results['tables_created']}")
        else:
            print(f"\n✗ Migration failed!")
            print(f"Errors: {results['errors']}")
