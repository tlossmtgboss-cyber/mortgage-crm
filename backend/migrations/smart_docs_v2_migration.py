"""
Smart Docs V2 Migration

Creates all new tables for the advanced document management system:
- E-Signature system (envelopes, recipients, fields, audit, templates)
- Income calculations (calculations, sources, verification tasks)
- Document intelligence (classifications, requirement rules, POS mappings, call intel needs)
- Follow-up automation (campaigns, events, appointments, templates)
- Document security (access logs, encryption records, integrity checks, retention policies, watermark logs)

Run: python -m migrations.smart_docs_v2_migration
"""

import logging
import os
import sys
from datetime import datetime, timezone

from sqlalchemy import create_engine, text

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logger = logging.getLogger(__name__)


def run_migration(engine=None):
    """Run the Smart Docs V2 migration."""
    if engine is None:
        database_url = os.getenv("DATABASE_URL", "postgresql://localhost:5432/perennia")
        if database_url.startswith("postgres://"):
            database_url = database_url.replace("postgres://", "postgresql://", 1)
        engine = create_engine(database_url)

    with engine.connect() as conn:
        logger.info("Starting Smart Docs V2 migration...")
        print("[SMART_DOCS_V2] Starting Smart Docs V2 migration...")

        # =================================================================
        # E-SIGNATURE TABLES
        # =================================================================

        print("[SMART_DOCS_V2] Creating esignature_envelopes table...")
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS esignature_envelopes (
                id SERIAL PRIMARY KEY,
                organization_id INTEGER,
                loan_id INTEGER,
                created_by_user_id INTEGER,
                envelope_uuid VARCHAR(36) UNIQUE NOT NULL,
                title VARCHAR(500) NOT NULL,
                description TEXT,
                status VARCHAR(32) NOT NULL DEFAULT 'DRAFT',
                document_hash_sha256 VARCHAR(64),
                document_storage_key VARCHAR(1024),
                signed_document_storage_key VARCHAR(1024),
                original_filename VARCHAR(512),
                page_count INTEGER,
                total_recipients INTEGER DEFAULT 0,
                completed_recipients INTEGER DEFAULT 0,
                sent_at TIMESTAMP,
                viewed_at TIMESTAMP,
                completed_at TIMESTAMP,
                voided_at TIMESTAMP,
                expires_at TIMESTAMP,
                void_reason TEXT,
                completion_certificate_key VARCHAR(1024),
                ip_address_created VARCHAR(45),
                reminder_frequency_hours INTEGER DEFAULT 48,
                last_reminder_sent_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            )
        """))

        print("[SMART_DOCS_V2] Creating esignature_recipients table...")
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS esignature_recipients (
                id SERIAL PRIMARY KEY,
                envelope_id INTEGER NOT NULL REFERENCES esignature_envelopes(id) ON DELETE CASCADE,
                recipient_type VARCHAR(32) NOT NULL DEFAULT 'signer',
                signing_order INTEGER DEFAULT 1,
                name VARCHAR(255) NOT NULL,
                email VARCHAR(255) NOT NULL,
                phone VARCHAR(32),
                access_code VARCHAR(128),
                status VARCHAR(32) NOT NULL DEFAULT 'pending',
                auth_method VARCHAR(32) DEFAULT 'email',
                signing_token VARCHAR(256) UNIQUE,
                signing_token_expires_at TIMESTAMP,
                viewed_at TIMESTAMP,
                signed_at TIMESTAMP,
                declined_at TIMESTAMP,
                decline_reason TEXT,
                signing_ip_address VARCHAR(45),
                signing_user_agent TEXT,
                signing_geo_location VARCHAR(512),
                signature_image_key VARCHAR(1024),
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            )
        """))

        print("[SMART_DOCS_V2] Creating esignature_fields table...")
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS esignature_fields (
                id SERIAL PRIMARY KEY,
                envelope_id INTEGER NOT NULL REFERENCES esignature_envelopes(id) ON DELETE CASCADE,
                recipient_id INTEGER REFERENCES esignature_recipients(id) ON DELETE SET NULL,
                field_type VARCHAR(32) NOT NULL,
                field_uuid VARCHAR(36) NOT NULL,
                page_number INTEGER NOT NULL DEFAULT 1,
                x_position NUMERIC(10, 2) NOT NULL,
                y_position NUMERIC(10, 2) NOT NULL,
                width NUMERIC(10, 2),
                height NUMERIC(10, 2),
                is_required BOOLEAN DEFAULT TRUE,
                placeholder_text VARCHAR(255),
                default_value TEXT,
                validation_regex VARCHAR(512),
                dropdown_options JSONB,
                group_name VARCHAR(128),
                value TEXT,
                filled_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """))

        print("[SMART_DOCS_V2] Creating esignature_audit_events table...")
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS esignature_audit_events (
                id SERIAL PRIMARY KEY,
                envelope_id INTEGER NOT NULL REFERENCES esignature_envelopes(id) ON DELETE CASCADE,
                recipient_id INTEGER REFERENCES esignature_recipients(id) ON DELETE SET NULL,
                event_type VARCHAR(64) NOT NULL,
                event_description TEXT,
                ip_address VARCHAR(45),
                user_agent TEXT,
                geo_location VARCHAR(512),
                metadata JSONB,
                document_hash_at_event VARCHAR(64),
                timestamp TIMESTAMP DEFAULT NOW()
            )
        """))

        print("[SMART_DOCS_V2] Creating esignature_templates table...")
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS esignature_templates (
                id SERIAL PRIMARY KEY,
                organization_id INTEGER,
                created_by_user_id INTEGER,
                name VARCHAR(255) NOT NULL,
                description TEXT,
                document_storage_key VARCHAR(1024),
                fields_config JSONB,
                default_recipients JSONB,
                category VARCHAR(128),
                is_active BOOLEAN DEFAULT TRUE,
                usage_count INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            )
        """))

        # =================================================================
        # INCOME CALCULATION TABLES
        # =================================================================

        print("[SMART_DOCS_V2] Creating income_calculations table...")
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS income_calculations (
                id SERIAL PRIMARY KEY,
                organization_id INTEGER,
                loan_id INTEGER,
                borrower_id INTEGER,
                calculation_type VARCHAR(64),
                status VARCHAR(32) NOT NULL DEFAULT 'pending',
                total_qualifying_monthly_income NUMERIC(15, 2),
                total_qualifying_annual_income NUMERIC(15, 2),
                calculation_method VARCHAR(64),
                dti_front_end NUMERIC(5, 2),
                dti_back_end NUMERIC(5, 2),
                proposed_housing_expense NUMERIC(12, 2),
                total_monthly_obligations NUMERIC(12, 2),
                ai_confidence_score NUMERIC(5, 2),
                ai_flags JSONB,
                ai_recommendations JSONB,
                ai_model_used VARCHAR(128),
                calculation_duration_ms INTEGER,
                source_documents JSONB,
                reviewed_by INTEGER,
                reviewed_at TIMESTAMP,
                review_notes TEXT,
                approved_by INTEGER,
                approved_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            )
        """))

        print("[SMART_DOCS_V2] Creating income_sources table...")
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS income_sources (
                id SERIAL PRIMARY KEY,
                calculation_id INTEGER REFERENCES income_calculations(id) ON DELETE CASCADE,
                borrower_id INTEGER,
                source_type VARCHAR(64),
                employer_name VARCHAR(255),
                position_title VARCHAR(255),
                employment_start_date DATE,
                employment_years NUMERIC(4, 1),
                is_primary BOOLEAN DEFAULT FALSE,
                base_monthly_income NUMERIC(12, 2),
                overtime_monthly NUMERIC(12, 2),
                bonus_monthly NUMERIC(12, 2),
                commission_monthly NUMERIC(12, 2),
                other_monthly NUMERIC(12, 2),
                total_monthly_income NUMERIC(12, 2),
                total_annual_income NUMERIC(15, 2),
                trending_direction VARCHAR(16),
                year1_income NUMERIC(15, 2),
                year2_income NUMERIC(15, 2),
                year_over_year_change_pct NUMERIC(6, 2),
                verification_status VARCHAR(32),
                verification_notes TEXT,
                source_document_ids JSONB,
                ai_confidence NUMERIC(5, 2),
                ai_notes TEXT,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            )
        """))

        print("[SMART_DOCS_V2] Creating income_verification_tasks table...")
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS income_verification_tasks (
                id SERIAL PRIMARY KEY,
                calculation_id INTEGER REFERENCES income_calculations(id) ON DELETE SET NULL,
                income_source_id INTEGER REFERENCES income_sources(id) ON DELETE SET NULL,
                loan_id INTEGER,
                organization_id INTEGER,
                task_type VARCHAR(64) NOT NULL,
                title VARCHAR(500) NOT NULL,
                description TEXT,
                priority VARCHAR(16) DEFAULT 'normal',
                status VARCHAR(32) NOT NULL DEFAULT 'pending',
                assigned_to_user_id INTEGER,
                ai_recommendation TEXT,
                resolution_notes TEXT,
                resolved_by INTEGER,
                resolved_at TIMESTAMP,
                due_date DATE,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            )
        """))

        # =================================================================
        # DOCUMENT INTELLIGENCE TABLES
        # =================================================================

        print("[SMART_DOCS_V2] Creating ai_document_classifications table...")
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS ai_document_classifications (
                id SERIAL PRIMARY KEY,
                organization_id INTEGER,
                document_id INTEGER,
                original_doc_type VARCHAR(128),
                predicted_doc_type VARCHAR(128),
                prediction_confidence NUMERIC(5, 4),
                alternative_classifications JSONB,
                classification_model VARCHAR(128),
                classification_duration_ms INTEGER,
                features_detected JSONB,
                text_snippet TEXT,
                is_correct BOOLEAN,
                corrected_doc_type VARCHAR(128),
                corrected_by INTEGER,
                corrected_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """))

        print("[SMART_DOCS_V2] Creating document_requirement_rules table...")
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS document_requirement_rules (
                id SERIAL PRIMARY KEY,
                organization_id INTEGER,
                rule_name VARCHAR(255) NOT NULL,
                rule_description TEXT,
                category VARCHAR(64),
                doc_type VARCHAR(128),
                trigger_conditions JSONB,
                required_count INTEGER DEFAULT 1,
                applies_to VARCHAR(32),
                priority VARCHAR(16) DEFAULT 'normal',
                freshness_days INTEGER,
                instructions TEXT,
                is_active BOOLEAN DEFAULT TRUE,
                sort_order INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            )
        """))

        print("[SMART_DOCS_V2] Creating pos_document_mappings table...")
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS pos_document_mappings (
                id SERIAL PRIMARY KEY,
                organization_id INTEGER,
                pos_field_path VARCHAR(512) NOT NULL,
                pos_field_value VARCHAR(512),
                maps_to_doc_type VARCHAR(128),
                maps_to_rule_id INTEGER REFERENCES document_requirement_rules(id) ON DELETE SET NULL,
                confidence_weight NUMERIC(5, 2),
                description TEXT,
                is_active BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """))

        print("[SMART_DOCS_V2] Creating call_intel_document_needs table...")
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS call_intel_document_needs (
                id SERIAL PRIMARY KEY,
                organization_id INTEGER,
                loan_id INTEGER,
                lead_id INTEGER,
                call_id INTEGER,
                call_date TIMESTAMP,
                detected_doc_type VARCHAR(128),
                detected_doc_description TEXT,
                detection_confidence NUMERIC(5, 4),
                source_transcript_snippet TEXT,
                keywords_matched JSONB,
                status VARCHAR(32) NOT NULL DEFAULT 'detected',
                linked_request_id INTEGER,
                confirmed_by INTEGER,
                confirmed_at TIMESTAMP,
                dismissed_by INTEGER,
                dismissed_at TIMESTAMP,
                dismiss_reason TEXT,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """))

        # =================================================================
        # DOCUMENT FOLLOW-UP TABLES
        # =================================================================

        print("[SMART_DOCS_V2] Creating document_followup_campaigns table...")
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS document_followup_campaigns (
                id SERIAL PRIMARY KEY,
                organization_id INTEGER,
                loan_id INTEGER,
                borrower_id INTEGER,
                campaign_type VARCHAR(64),
                status VARCHAR(32) NOT NULL DEFAULT 'draft',
                trigger_source VARCHAR(64),
                linked_request_ids JSONB,
                total_steps INTEGER DEFAULT 0,
                current_step INTEGER DEFAULT 0,
                step_config JSONB,
                next_action_at TIMESTAMP,
                started_at TIMESTAMP,
                completed_at TIMESTAMP,
                cancelled_at TIMESTAMP,
                cancel_reason TEXT,
                max_reminders INTEGER DEFAULT 5,
                reminders_sent INTEGER DEFAULT 0,
                borrower_responded BOOLEAN DEFAULT FALSE,
                response_date TIMESTAMP,
                created_by_user_id INTEGER,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            )
        """))

        print("[SMART_DOCS_V2] Creating document_followup_events table...")
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS document_followup_events (
                id SERIAL PRIMARY KEY,
                campaign_id INTEGER REFERENCES document_followup_campaigns(id) ON DELETE CASCADE,
                event_type VARCHAR(64) NOT NULL,
                step_number INTEGER,
                channel VARCHAR(32),
                template_used VARCHAR(255),
                recipient_email VARCHAR(255),
                recipient_phone VARCHAR(32),
                message_subject VARCHAR(500),
                message_preview TEXT,
                delivery_status VARCHAR(32),
                delivery_error TEXT,
                opened_at TIMESTAMP,
                clicked_at TIMESTAMP,
                metadata JSONB,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """))

        print("[SMART_DOCS_V2] Creating document_appointments table...")
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS document_appointments (
                id SERIAL PRIMARY KEY,
                organization_id INTEGER,
                loan_id INTEGER,
                borrower_id INTEGER,
                campaign_id INTEGER REFERENCES document_followup_campaigns(id) ON DELETE SET NULL,
                appointment_type VARCHAR(64),
                title VARCHAR(500) NOT NULL,
                description TEXT,
                status VARCHAR(32) NOT NULL DEFAULT 'scheduled',
                scheduled_date DATE,
                scheduled_time_start TIME,
                scheduled_time_end TIME,
                duration_minutes INTEGER DEFAULT 30,
                location_type VARCHAR(32),
                location_details TEXT,
                meeting_link VARCHAR(1024),
                assigned_to_user_id INTEGER,
                attendee_name VARCHAR(255),
                attendee_email VARCHAR(255),
                attendee_phone VARCHAR(32),
                documents_to_discuss JSONB,
                outcome_notes TEXT,
                documents_collected JSONB,
                reminder_sent BOOLEAN DEFAULT FALSE,
                reminder_sent_at TIMESTAMP,
                confirmed_at TIMESTAMP,
                completed_at TIMESTAMP,
                cancelled_at TIMESTAMP,
                cancellation_reason TEXT,
                rescheduled_from_id INTEGER REFERENCES document_appointments(id) ON DELETE SET NULL,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            )
        """))

        print("[SMART_DOCS_V2] Creating document_followup_templates table...")
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS document_followup_templates (
                id SERIAL PRIMARY KEY,
                organization_id INTEGER,
                name VARCHAR(255) NOT NULL,
                slug VARCHAR(128),
                channel VARCHAR(32),
                category VARCHAR(64),
                subject_template TEXT,
                body_template TEXT,
                variables JSONB,
                is_default BOOLEAN DEFAULT FALSE,
                is_active BOOLEAN DEFAULT TRUE,
                usage_count INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            )
        """))

        # =================================================================
        # DOCUMENT SECURITY TABLES
        # =================================================================

        print("[SMART_DOCS_V2] Creating document_access_logs table...")
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS document_access_logs (
                id SERIAL PRIMARY KEY,
                organization_id INTEGER,
                document_id INTEGER,
                document_type VARCHAR(128),
                user_id INTEGER,
                access_type VARCHAR(32) NOT NULL,
                access_granted BOOLEAN NOT NULL DEFAULT TRUE,
                denial_reason TEXT,
                ip_address VARCHAR(45),
                user_agent TEXT,
                geo_location VARCHAR(512),
                session_id VARCHAR(128),
                referrer_url VARCHAR(1024),
                duration_seconds INTEGER,
                pages_viewed JSONB,
                metadata JSONB,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """))

        print("[SMART_DOCS_V2] Creating document_encryption_records table...")
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS document_encryption_records (
                id SERIAL PRIMARY KEY,
                organization_id INTEGER,
                document_id INTEGER,
                document_type VARCHAR(128),
                encryption_algorithm VARCHAR(64) NOT NULL,
                key_id VARCHAR(256) NOT NULL,
                key_version INTEGER DEFAULT 1,
                encrypted_at TIMESTAMP DEFAULT NOW(),
                encryption_status VARCHAR(32) NOT NULL DEFAULT 'encrypted',
                iv_nonce VARCHAR(256),
                content_hash_before VARCHAR(128),
                content_hash_after VARCHAR(128),
                file_size_before BIGINT,
                file_size_after BIGINT,
                last_accessed_at TIMESTAMP,
                access_count INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """))

        print("[SMART_DOCS_V2] Creating document_integrity_checks table...")
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS document_integrity_checks (
                id SERIAL PRIMARY KEY,
                document_id INTEGER,
                document_type VARCHAR(128),
                check_type VARCHAR(64) NOT NULL,
                expected_hash VARCHAR(128),
                actual_hash VARCHAR(128),
                is_valid BOOLEAN,
                tamper_detected BOOLEAN DEFAULT FALSE,
                tamper_details TEXT,
                checked_by INTEGER,
                check_duration_ms INTEGER,
                storage_key_checked VARCHAR(1024),
                file_size_expected BIGINT,
                file_size_actual BIGINT,
                metadata JSONB,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """))

        print("[SMART_DOCS_V2] Creating document_retention_policies table...")
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS document_retention_policies (
                id SERIAL PRIMARY KEY,
                organization_id INTEGER,
                doc_type VARCHAR(128),
                policy_name VARCHAR(255) NOT NULL,
                retention_days INTEGER NOT NULL,
                retention_after_event VARCHAR(64),
                action_on_expiry VARCHAR(32) NOT NULL DEFAULT 'archive',
                notify_days_before INTEGER DEFAULT 30,
                is_active BOOLEAN DEFAULT TRUE,
                regulatory_reference TEXT,
                applies_to_states JSONB,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            )
        """))

        print("[SMART_DOCS_V2] Creating document_watermark_logs table...")
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS document_watermark_logs (
                id SERIAL PRIMARY KEY,
                document_id INTEGER,
                watermark_type VARCHAR(32) NOT NULL,
                watermark_text TEXT,
                applied_to_user_id INTEGER,
                applied_at TIMESTAMP DEFAULT NOW(),
                output_storage_key VARCHAR(1024),
                metadata JSONB
            )
        """))

        # =================================================================
        # INDEXES
        # =================================================================

        print("[SMART_DOCS_V2] Creating indexes...")

        indexes = [
            # E-Signature envelope indexes
            "CREATE INDEX IF NOT EXISTS ix_esign_envelopes_org ON esignature_envelopes(organization_id)",
            "CREATE INDEX IF NOT EXISTS ix_esign_envelopes_loan ON esignature_envelopes(loan_id)",
            "CREATE INDEX IF NOT EXISTS ix_esign_envelopes_uuid ON esignature_envelopes(envelope_uuid)",
            "CREATE INDEX IF NOT EXISTS ix_esign_envelopes_status ON esignature_envelopes(status)",
            "CREATE INDEX IF NOT EXISTS ix_esign_envelopes_created_by ON esignature_envelopes(created_by_user_id)",
            "CREATE INDEX IF NOT EXISTS ix_esign_envelopes_expires ON esignature_envelopes(expires_at)",

            # E-Signature recipient indexes
            "CREATE INDEX IF NOT EXISTS ix_esign_recipients_envelope ON esignature_recipients(envelope_id)",
            "CREATE INDEX IF NOT EXISTS ix_esign_recipients_email ON esignature_recipients(email)",
            "CREATE INDEX IF NOT EXISTS ix_esign_recipients_status ON esignature_recipients(status)",
            "CREATE INDEX IF NOT EXISTS ix_esign_recipients_token ON esignature_recipients(signing_token)",

            # E-Signature field indexes
            "CREATE INDEX IF NOT EXISTS ix_esign_fields_envelope ON esignature_fields(envelope_id)",
            "CREATE INDEX IF NOT EXISTS ix_esign_fields_recipient ON esignature_fields(recipient_id)",
            "CREATE INDEX IF NOT EXISTS ix_esign_fields_uuid ON esignature_fields(field_uuid)",

            # E-Signature audit indexes
            "CREATE INDEX IF NOT EXISTS ix_esign_audit_envelope ON esignature_audit_events(envelope_id)",
            "CREATE INDEX IF NOT EXISTS ix_esign_audit_recipient ON esignature_audit_events(recipient_id)",
            "CREATE INDEX IF NOT EXISTS ix_esign_audit_event_type ON esignature_audit_events(event_type)",
            "CREATE INDEX IF NOT EXISTS ix_esign_audit_timestamp ON esignature_audit_events(timestamp)",

            # E-Signature template indexes
            "CREATE INDEX IF NOT EXISTS ix_esign_templates_org ON esignature_templates(organization_id)",
            "CREATE INDEX IF NOT EXISTS ix_esign_templates_category ON esignature_templates(category)",
            "CREATE INDEX IF NOT EXISTS ix_esign_templates_active ON esignature_templates(is_active)",

            # Income calculation indexes
            "CREATE INDEX IF NOT EXISTS ix_income_calc_org ON income_calculations(organization_id)",
            "CREATE INDEX IF NOT EXISTS ix_income_calc_loan ON income_calculations(loan_id)",
            "CREATE INDEX IF NOT EXISTS ix_income_calc_borrower ON income_calculations(borrower_id)",
            "CREATE INDEX IF NOT EXISTS ix_income_calc_status ON income_calculations(status)",

            # Income source indexes
            "CREATE INDEX IF NOT EXISTS ix_income_src_calc ON income_sources(calculation_id)",
            "CREATE INDEX IF NOT EXISTS ix_income_src_borrower ON income_sources(borrower_id)",
            "CREATE INDEX IF NOT EXISTS ix_income_src_type ON income_sources(source_type)",

            # Income verification task indexes
            "CREATE INDEX IF NOT EXISTS ix_income_verif_calc ON income_verification_tasks(calculation_id)",
            "CREATE INDEX IF NOT EXISTS ix_income_verif_loan ON income_verification_tasks(loan_id)",
            "CREATE INDEX IF NOT EXISTS ix_income_verif_org ON income_verification_tasks(organization_id)",
            "CREATE INDEX IF NOT EXISTS ix_income_verif_status ON income_verification_tasks(status)",
            "CREATE INDEX IF NOT EXISTS ix_income_verif_assigned ON income_verification_tasks(assigned_to_user_id)",
            "CREATE INDEX IF NOT EXISTS ix_income_verif_due ON income_verification_tasks(due_date)",

            # AI document classification indexes
            "CREATE INDEX IF NOT EXISTS ix_ai_doc_class_org ON ai_document_classifications(organization_id)",
            "CREATE INDEX IF NOT EXISTS ix_ai_doc_class_doc ON ai_document_classifications(document_id)",
            "CREATE INDEX IF NOT EXISTS ix_ai_doc_class_predicted ON ai_document_classifications(predicted_doc_type)",
            "CREATE INDEX IF NOT EXISTS ix_ai_doc_class_correct ON ai_document_classifications(is_correct)",

            # Document requirement rule indexes
            "CREATE INDEX IF NOT EXISTS ix_doc_req_rules_org ON document_requirement_rules(organization_id)",
            "CREATE INDEX IF NOT EXISTS ix_doc_req_rules_category ON document_requirement_rules(category)",
            "CREATE INDEX IF NOT EXISTS ix_doc_req_rules_doc_type ON document_requirement_rules(doc_type)",
            "CREATE INDEX IF NOT EXISTS ix_doc_req_rules_active ON document_requirement_rules(is_active)",

            # POS document mapping indexes
            "CREATE INDEX IF NOT EXISTS ix_pos_doc_map_org ON pos_document_mappings(organization_id)",
            "CREATE INDEX IF NOT EXISTS ix_pos_doc_map_field ON pos_document_mappings(pos_field_path)",
            "CREATE INDEX IF NOT EXISTS ix_pos_doc_map_active ON pos_document_mappings(is_active)",

            # Call intel document needs indexes
            "CREATE INDEX IF NOT EXISTS ix_call_intel_doc_org ON call_intel_document_needs(organization_id)",
            "CREATE INDEX IF NOT EXISTS ix_call_intel_doc_loan ON call_intel_document_needs(loan_id)",
            "CREATE INDEX IF NOT EXISTS ix_call_intel_doc_lead ON call_intel_document_needs(lead_id)",
            "CREATE INDEX IF NOT EXISTS ix_call_intel_doc_call ON call_intel_document_needs(call_id)",
            "CREATE INDEX IF NOT EXISTS ix_call_intel_doc_status ON call_intel_document_needs(status)",

            # Document follow-up campaign indexes
            "CREATE INDEX IF NOT EXISTS ix_doc_followup_camp_org ON document_followup_campaigns(organization_id)",
            "CREATE INDEX IF NOT EXISTS ix_doc_followup_camp_loan ON document_followup_campaigns(loan_id)",
            "CREATE INDEX IF NOT EXISTS ix_doc_followup_camp_borrower ON document_followup_campaigns(borrower_id)",
            "CREATE INDEX IF NOT EXISTS ix_doc_followup_camp_status ON document_followup_campaigns(status)",
            "CREATE INDEX IF NOT EXISTS ix_doc_followup_camp_next ON document_followup_campaigns(next_action_at)",

            # Document follow-up event indexes
            "CREATE INDEX IF NOT EXISTS ix_doc_followup_evt_campaign ON document_followup_events(campaign_id)",
            "CREATE INDEX IF NOT EXISTS ix_doc_followup_evt_type ON document_followup_events(event_type)",
            "CREATE INDEX IF NOT EXISTS ix_doc_followup_evt_channel ON document_followup_events(channel)",
            "CREATE INDEX IF NOT EXISTS ix_doc_followup_evt_delivery ON document_followup_events(delivery_status)",

            # Document appointment indexes
            "CREATE INDEX IF NOT EXISTS ix_doc_appt_org ON document_appointments(organization_id)",
            "CREATE INDEX IF NOT EXISTS ix_doc_appt_loan ON document_appointments(loan_id)",
            "CREATE INDEX IF NOT EXISTS ix_doc_appt_borrower ON document_appointments(borrower_id)",
            "CREATE INDEX IF NOT EXISTS ix_doc_appt_campaign ON document_appointments(campaign_id)",
            "CREATE INDEX IF NOT EXISTS ix_doc_appt_status ON document_appointments(status)",
            "CREATE INDEX IF NOT EXISTS ix_doc_appt_date ON document_appointments(scheduled_date)",
            "CREATE INDEX IF NOT EXISTS ix_doc_appt_assigned ON document_appointments(assigned_to_user_id)",

            # Document follow-up template indexes
            "CREATE INDEX IF NOT EXISTS ix_doc_followup_tpl_org ON document_followup_templates(organization_id)",
            "CREATE INDEX IF NOT EXISTS ix_doc_followup_tpl_slug ON document_followup_templates(slug)",
            "CREATE INDEX IF NOT EXISTS ix_doc_followup_tpl_channel ON document_followup_templates(channel)",
            "CREATE INDEX IF NOT EXISTS ix_doc_followup_tpl_active ON document_followup_templates(is_active)",

            # Document access log indexes
            "CREATE INDEX IF NOT EXISTS ix_doc_access_org ON document_access_logs(organization_id)",
            "CREATE INDEX IF NOT EXISTS ix_doc_access_doc ON document_access_logs(document_id)",
            "CREATE INDEX IF NOT EXISTS ix_doc_access_user ON document_access_logs(user_id)",
            "CREATE INDEX IF NOT EXISTS ix_doc_access_type ON document_access_logs(access_type)",
            "CREATE INDEX IF NOT EXISTS ix_doc_access_granted ON document_access_logs(access_granted)",
            "CREATE INDEX IF NOT EXISTS ix_doc_access_created ON document_access_logs(created_at)",
            "CREATE INDEX IF NOT EXISTS ix_doc_access_session ON document_access_logs(session_id)",

            # Document encryption record indexes
            "CREATE INDEX IF NOT EXISTS ix_doc_encrypt_org ON document_encryption_records(organization_id)",
            "CREATE INDEX IF NOT EXISTS ix_doc_encrypt_doc ON document_encryption_records(document_id)",
            "CREATE INDEX IF NOT EXISTS ix_doc_encrypt_key ON document_encryption_records(key_id)",
            "CREATE INDEX IF NOT EXISTS ix_doc_encrypt_status ON document_encryption_records(encryption_status)",

            # Document integrity check indexes
            "CREATE INDEX IF NOT EXISTS ix_doc_integrity_doc ON document_integrity_checks(document_id)",
            "CREATE INDEX IF NOT EXISTS ix_doc_integrity_type ON document_integrity_checks(check_type)",
            "CREATE INDEX IF NOT EXISTS ix_doc_integrity_valid ON document_integrity_checks(is_valid)",
            "CREATE INDEX IF NOT EXISTS ix_doc_integrity_tamper ON document_integrity_checks(tamper_detected)",

            # Document retention policy indexes
            "CREATE INDEX IF NOT EXISTS ix_doc_retention_org ON document_retention_policies(organization_id)",
            "CREATE INDEX IF NOT EXISTS ix_doc_retention_type ON document_retention_policies(doc_type)",
            "CREATE INDEX IF NOT EXISTS ix_doc_retention_active ON document_retention_policies(is_active)",

            # Document watermark log indexes
            "CREATE INDEX IF NOT EXISTS ix_doc_watermark_doc ON document_watermark_logs(document_id)",
            "CREATE INDEX IF NOT EXISTS ix_doc_watermark_user ON document_watermark_logs(applied_to_user_id)",
            "CREATE INDEX IF NOT EXISTS ix_doc_watermark_type ON document_watermark_logs(watermark_type)",
        ]

        for idx_sql in indexes:
            conn.execute(text(idx_sql))

        # =================================================================
        # ADD COLUMNS TO EXISTING TABLES
        # =================================================================

        print("[SMART_DOCS_V2] Adding columns to existing smart_documents table if needed...")
        conn.execute(text("""
            DO $$ BEGIN
                ALTER TABLE smart_documents ADD COLUMN IF NOT EXISTS organization_id INTEGER;
            EXCEPTION
                WHEN undefined_table THEN NULL;
            END $$;
        """))

        # =================================================================
        # COMMIT
        # =================================================================

        conn.commit()

        print("[SMART_DOCS_V2] Smart Docs V2 migration completed successfully!")
        logger.info("Smart Docs V2 migration completed successfully.")

        return {
            "success": True,
            "message": "Smart Docs V2 tables created successfully",
            "tables_created": [
                "esignature_envelopes",
                "esignature_recipients",
                "esignature_fields",
                "esignature_audit_events",
                "esignature_templates",
                "income_calculations",
                "income_sources",
                "income_verification_tasks",
                "ai_document_classifications",
                "document_requirement_rules",
                "pos_document_mappings",
                "call_intel_document_needs",
                "document_followup_campaigns",
                "document_followup_events",
                "document_appointments",
                "document_followup_templates",
                "document_access_logs",
                "document_encryption_records",
                "document_integrity_checks",
                "document_retention_policies",
                "document_watermark_logs",
            ],
        }


if __name__ == "__main__":
    run_migration()
    print("Smart Docs V2 migration complete!")
