"""
Migration: Add Phase 5 Tables
Creates tables for:
- Live Agent Escalation (agents, escalations, queue)
- Call Quality Assurance (scorecards, reviews, criteria)
- Voice Biometrics (voiceprints, caller profiles)
- Multi-Tenant & White-Label (tenants, branding, usage)
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

# Detect database type
is_sqlite = DATABASE_URL.startswith("sqlite")


def get_sql_commands():
    """Get SQL commands appropriate for the database type."""

    if is_sqlite:
        # SQLite-compatible syntax
        return [
            # =================================================================
            # Live Agent Escalation Tables
            # =================================================================

            # 1. Live Agents
            """
            CREATE TABLE IF NOT EXISTS live_agents (
                id VARCHAR(50) PRIMARY KEY,
                name VARCHAR(100) NOT NULL,
                email VARCHAR(255) NOT NULL,
                phone VARCHAR(20),
                status VARCHAR(20) DEFAULT 'offline',
                skills TEXT,
                languages TEXT,
                max_concurrent_calls INTEGER DEFAULT 3,
                current_calls INTEGER DEFAULT 0,
                total_escalations INTEGER DEFAULT 0,
                avg_handle_time_seconds INTEGER DEFAULT 0,
                satisfaction_rating REAL DEFAULT 0.0,
                shift_start VARCHAR(10),
                shift_end VARCHAR(10),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_active_at TIMESTAMP
            );
            """,

            # 2. Escalations
            """
            CREATE TABLE IF NOT EXISTS escalations (
                id VARCHAR(50) PRIMARY KEY,
                call_id VARCHAR(50) NOT NULL,
                caller_phone VARCHAR(20) NOT NULL,
                status VARCHAR(20) DEFAULT 'pending',
                priority VARCHAR(20) DEFAULT 'normal',
                reason TEXT,
                trigger_type VARCHAR(30),
                assigned_agent_id VARCHAR(50),
                context TEXT,
                ai_summary TEXT,
                customer_sentiment REAL,
                wait_time_seconds INTEGER DEFAULT 0,
                handle_time_seconds INTEGER DEFAULT 0,
                resolution VARCHAR(50),
                resolution_notes TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                assigned_at TIMESTAMP,
                completed_at TIMESTAMP,
                FOREIGN KEY (assigned_agent_id) REFERENCES live_agents(id)
            );
            """,

            # 3. Escalation Queue
            """
            CREATE TABLE IF NOT EXISTS escalation_queue (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                escalation_id VARCHAR(50) NOT NULL,
                position INTEGER NOT NULL,
                priority_score REAL DEFAULT 0.0,
                required_skills TEXT,
                required_language VARCHAR(10),
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (escalation_id) REFERENCES escalations(id) ON DELETE CASCADE
            );
            """,

            # =================================================================
            # Call Quality Assurance Tables
            # =================================================================

            # 4. QA Scorecards
            """
            CREATE TABLE IF NOT EXISTS qa_scorecards (
                id VARCHAR(50) PRIMARY KEY,
                call_id VARCHAR(50) NOT NULL,
                scorecard_type VARCHAR(20) DEFAULT 'automated',
                overall_score REAL DEFAULT 0.0,
                grade VARCHAR(5),
                scores TEXT,
                recommendations TEXT,
                strengths TEXT,
                improvements TEXT,
                reviewed_by INTEGER,
                review_date TIMESTAMP,
                ai_confidence REAL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """,

            # 5. QA Reviews (Human review requests)
            """
            CREATE TABLE IF NOT EXISTS qa_reviews (
                id VARCHAR(50) PRIMARY KEY,
                call_id VARCHAR(50) NOT NULL,
                call_date TIMESTAMP NOT NULL,
                duration_seconds INTEGER DEFAULT 0,
                agent_id VARCHAR(50),
                status VARCHAR(20) DEFAULT 'pending',
                priority VARCHAR(20) DEFAULT 'normal',
                review_type VARCHAR(30) DEFAULT 'standard',
                assigned_reviewer_id INTEGER,
                scorecard_id VARCHAR(50),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                assigned_at TIMESTAMP,
                completed_at TIMESTAMP,
                FOREIGN KEY (scorecard_id) REFERENCES qa_scorecards(id)
            );
            """,

            # 6. QA Criteria Definitions
            """
            CREATE TABLE IF NOT EXISTS qa_criteria (
                id VARCHAR(30) PRIMARY KEY,
                name VARCHAR(100) NOT NULL,
                description TEXT,
                category VARCHAR(50),
                weight REAL DEFAULT 1.0,
                max_score REAL DEFAULT 5.0,
                is_critical BOOLEAN DEFAULT FALSE,
                evaluation_guidelines TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """,

            # 7. QA Calibration Records
            """
            CREATE TABLE IF NOT EXISTS qa_calibration (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                call_id VARCHAR(50) NOT NULL,
                criterion_id VARCHAR(30) NOT NULL,
                ai_score REAL,
                human_score REAL,
                variance REAL,
                reviewer_id INTEGER,
                calibrated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (criterion_id) REFERENCES qa_criteria(id)
            );
            """,

            # =================================================================
            # Voice Biometrics Tables
            # =================================================================

            # 8. Voiceprints
            """
            CREATE TABLE IF NOT EXISTS voiceprints (
                id VARCHAR(50) PRIMARY KEY,
                caller_id VARCHAR(50) NOT NULL,
                phone_number VARCHAR(20),
                status VARCHAR(20) DEFAULT 'active',
                voiceprint_data TEXT,
                quality_score REAL DEFAULT 0.0,
                sample_count INTEGER DEFAULT 0,
                verification_count INTEGER DEFAULT 0,
                successful_verifications INTEGER DEFAULT 0,
                failed_verifications INTEGER DEFAULT 0,
                spoof_attempts INTEGER DEFAULT 0,
                consent_given BOOLEAN DEFAULT TRUE,
                consent_date TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP,
                last_used_at TIMESTAMP
            );
            """,

            # 9. Caller Profiles
            """
            CREATE TABLE IF NOT EXISTS caller_profiles (
                caller_id VARCHAR(50) PRIMARY KEY,
                name VARCHAR(100),
                phone_numbers TEXT,
                is_verified BOOLEAN DEFAULT FALSE,
                trust_level VARCHAR(20) DEFAULT 'new',
                total_calls INTEGER DEFAULT 0,
                verified_calls INTEGER DEFAULT 0,
                preferences TEXT,
                notes TEXT,
                first_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_seen TIMESTAMP
            );
            """,

            # 10. Verification History
            """
            CREATE TABLE IF NOT EXISTS verification_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                voiceprint_id VARCHAR(50) NOT NULL,
                call_id VARCHAR(50),
                result VARCHAR(20) NOT NULL,
                confidence REAL DEFAULT 0.0,
                spoof_detected BOOLEAN DEFAULT FALSE,
                verification_time_ms INTEGER DEFAULT 0,
                verified_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (voiceprint_id) REFERENCES voiceprints(id)
            );
            """,

            # =================================================================
            # Multi-Tenant & White-Label Tables
            # =================================================================

            # 11. Tenants
            """
            CREATE TABLE IF NOT EXISTS tenants (
                id VARCHAR(50) PRIMARY KEY,
                name VARCHAR(100) NOT NULL,
                slug VARCHAR(100) UNIQUE NOT NULL,
                tier VARCHAR(20) DEFAULT 'starter',
                status VARCHAR(20) DEFAULT 'active',
                primary_contact_name VARCHAR(100),
                primary_contact_email VARCHAR(255) NOT NULL,
                primary_contact_phone VARCHAR(20),
                billing_email VARCHAR(255),
                api_key_hash VARCHAR(64),
                sla_tier VARCHAR(20) DEFAULT 'standard',
                sla_response_time_hours INTEGER DEFAULT 24,
                sla_uptime_percentage REAL DEFAULT 99.5,
                trial_ends_at TIMESTAMP,
                subscription_ends_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP
            );
            """,

            # 12. Tenant Limits
            """
            CREATE TABLE IF NOT EXISTS tenant_limits (
                tenant_id VARCHAR(50) PRIMARY KEY,
                max_monthly_calls INTEGER DEFAULT 1000,
                max_concurrent_calls INTEGER DEFAULT 5,
                max_users INTEGER DEFAULT 10,
                max_phone_numbers INTEGER DEFAULT 3,
                max_custom_voices INTEGER DEFAULT 1,
                max_integrations INTEGER DEFAULT 5,
                recording_retention_days INTEGER DEFAULT 30,
                analytics_retention_days INTEGER DEFAULT 90,
                api_rate_limit_per_minute INTEGER DEFAULT 60,
                FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE
            );
            """,

            # 13. Tenant Branding
            """
            CREATE TABLE IF NOT EXISTS tenant_branding (
                tenant_id VARCHAR(50) PRIMARY KEY,
                company_name VARCHAR(100),
                company_logo_url TEXT,
                primary_color VARCHAR(10) DEFAULT '#1976D2',
                secondary_color VARCHAR(10) DEFAULT '#424242',
                accent_color VARCHAR(10) DEFAULT '#FF9800',
                default_voice_id VARCHAR(50),
                custom_voice_ids TEXT,
                greeting_template TEXT,
                hold_music_url TEXT,
                script_templates TEXT,
                fallback_messages TEXT,
                email_from_name VARCHAR(100),
                email_from_address VARCHAR(255),
                email_footer_html TEXT,
                email_logo_url TEXT,
                sms_sender_id VARCHAR(20),
                sms_signature VARCHAR(100),
                custom_domain VARCHAR(255),
                subdomain VARCHAR(100),
                favicon_url TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE
            );
            """,

            # 14. Tenant Features
            """
            CREATE TABLE IF NOT EXISTS tenant_features (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tenant_id VARCHAR(50) NOT NULL,
                feature_name VARCHAR(50) NOT NULL,
                is_enabled BOOLEAN DEFAULT FALSE,
                custom_config TEXT,
                enabled_at TIMESTAMP,
                UNIQUE (tenant_id, feature_name),
                FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE
            );
            """,

            # 15. Tenant Usage
            """
            CREATE TABLE IF NOT EXISTS tenant_usage (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tenant_id VARCHAR(50) NOT NULL,
                period_start TIMESTAMP NOT NULL,
                period_end TIMESTAMP NOT NULL,
                total_calls INTEGER DEFAULT 0,
                successful_calls INTEGER DEFAULT 0,
                failed_calls INTEGER DEFAULT 0,
                total_call_minutes REAL DEFAULT 0.0,
                peak_concurrent_calls INTEGER DEFAULT 0,
                api_requests INTEGER DEFAULT 0,
                api_errors INTEGER DEFAULT 0,
                sms_sent INTEGER DEFAULT 0,
                emails_sent INTEGER DEFAULT 0,
                escalations INTEGER DEFAULT 0,
                voiceprint_verifications INTEGER DEFAULT 0,
                recording_storage_mb REAL DEFAULT 0.0,
                document_storage_mb REAL DEFAULT 0.0,
                FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE
            );
            """,

            # 16. Tenant Settings
            """
            CREATE TABLE IF NOT EXISTS tenant_settings (
                tenant_id VARCHAR(50) PRIMARY KEY,
                settings TEXT,
                metadata TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE
            );
            """,

            # =================================================================
            # Indices
            # =================================================================
            "CREATE INDEX IF NOT EXISTS idx_live_agents_status ON live_agents(status);",
            "CREATE INDEX IF NOT EXISTS idx_escalations_status ON escalations(status);",
            "CREATE INDEX IF NOT EXISTS idx_escalations_call ON escalations(call_id);",
            "CREATE INDEX IF NOT EXISTS idx_escalations_agent ON escalations(assigned_agent_id);",
            "CREATE INDEX IF NOT EXISTS idx_queue_priority ON escalation_queue(priority_score DESC);",
            "CREATE INDEX IF NOT EXISTS idx_scorecards_call ON qa_scorecards(call_id);",
            "CREATE INDEX IF NOT EXISTS idx_reviews_status ON qa_reviews(status);",
            "CREATE INDEX IF NOT EXISTS idx_reviews_reviewer ON qa_reviews(assigned_reviewer_id);",
            "CREATE INDEX IF NOT EXISTS idx_voiceprints_caller ON voiceprints(caller_id);",
            "CREATE INDEX IF NOT EXISTS idx_voiceprints_phone ON voiceprints(phone_number);",
            "CREATE INDEX IF NOT EXISTS idx_verification_voiceprint ON verification_history(voiceprint_id);",
            "CREATE INDEX IF NOT EXISTS idx_tenants_slug ON tenants(slug);",
            "CREATE INDEX IF NOT EXISTS idx_tenants_status ON tenants(status);",
            "CREATE INDEX IF NOT EXISTS idx_tenant_usage_period ON tenant_usage(tenant_id, period_start);",
        ]
    else:
        # PostgreSQL syntax
        return [
            # =================================================================
            # Live Agent Escalation Tables
            # =================================================================

            # 1. Live Agents
            """
            CREATE TABLE IF NOT EXISTS live_agents (
                id VARCHAR(50) PRIMARY KEY,
                name VARCHAR(100) NOT NULL,
                email VARCHAR(255) NOT NULL,
                phone VARCHAR(20),
                status VARCHAR(20) DEFAULT 'offline',
                skills TEXT[],
                languages TEXT[] DEFAULT ARRAY['en'],
                max_concurrent_calls INTEGER DEFAULT 3,
                current_calls INTEGER DEFAULT 0,
                total_escalations INTEGER DEFAULT 0,
                avg_handle_time_seconds INTEGER DEFAULT 0,
                satisfaction_rating NUMERIC(3,2) DEFAULT 0.0,
                shift_start TIME,
                shift_end TIME,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                last_active_at TIMESTAMP WITH TIME ZONE
            );
            """,

            # 2. Escalations
            """
            CREATE TABLE IF NOT EXISTS escalations (
                id VARCHAR(50) PRIMARY KEY,
                call_id VARCHAR(50) NOT NULL,
                caller_phone VARCHAR(20) NOT NULL,
                status VARCHAR(20) DEFAULT 'pending',
                priority VARCHAR(20) DEFAULT 'normal',
                reason TEXT,
                trigger_type VARCHAR(30),
                assigned_agent_id VARCHAR(50) REFERENCES live_agents(id),
                context JSONB,
                ai_summary TEXT,
                customer_sentiment NUMERIC(4,3),
                wait_time_seconds INTEGER DEFAULT 0,
                handle_time_seconds INTEGER DEFAULT 0,
                resolution VARCHAR(50),
                resolution_notes TEXT,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                assigned_at TIMESTAMP WITH TIME ZONE,
                completed_at TIMESTAMP WITH TIME ZONE
            );
            """,

            # 3. Escalation Queue
            """
            CREATE TABLE IF NOT EXISTS escalation_queue (
                id SERIAL PRIMARY KEY,
                escalation_id VARCHAR(50) NOT NULL REFERENCES escalations(id) ON DELETE CASCADE,
                position INTEGER NOT NULL,
                priority_score NUMERIC(5,2) DEFAULT 0.0,
                required_skills TEXT[],
                required_language VARCHAR(10),
                added_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
            );
            """,

            # =================================================================
            # Call Quality Assurance Tables
            # =================================================================

            # 4. QA Scorecards
            """
            CREATE TABLE IF NOT EXISTS qa_scorecards (
                id VARCHAR(50) PRIMARY KEY,
                call_id VARCHAR(50) NOT NULL,
                scorecard_type VARCHAR(20) DEFAULT 'automated',
                overall_score NUMERIC(5,2) DEFAULT 0.0,
                grade VARCHAR(5),
                scores JSONB,
                recommendations TEXT[],
                strengths TEXT[],
                improvements TEXT[],
                reviewed_by INTEGER REFERENCES users(id),
                review_date TIMESTAMP WITH TIME ZONE,
                ai_confidence NUMERIC(4,3),
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
            );
            """,

            # 5. QA Reviews
            """
            CREATE TABLE IF NOT EXISTS qa_reviews (
                id VARCHAR(50) PRIMARY KEY,
                call_id VARCHAR(50) NOT NULL,
                call_date TIMESTAMP WITH TIME ZONE NOT NULL,
                duration_seconds INTEGER DEFAULT 0,
                agent_id VARCHAR(50),
                status VARCHAR(20) DEFAULT 'pending',
                priority VARCHAR(20) DEFAULT 'normal',
                review_type VARCHAR(30) DEFAULT 'standard',
                assigned_reviewer_id INTEGER REFERENCES users(id),
                scorecard_id VARCHAR(50) REFERENCES qa_scorecards(id),
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                assigned_at TIMESTAMP WITH TIME ZONE,
                completed_at TIMESTAMP WITH TIME ZONE
            );
            """,

            # 6. QA Criteria Definitions
            """
            CREATE TABLE IF NOT EXISTS qa_criteria (
                id VARCHAR(30) PRIMARY KEY,
                name VARCHAR(100) NOT NULL,
                description TEXT,
                category VARCHAR(50),
                weight NUMERIC(4,2) DEFAULT 1.0,
                max_score NUMERIC(4,2) DEFAULT 5.0,
                is_critical BOOLEAN DEFAULT FALSE,
                evaluation_guidelines TEXT,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
            );
            """,

            # 7. QA Calibration Records
            """
            CREATE TABLE IF NOT EXISTS qa_calibration (
                id SERIAL PRIMARY KEY,
                call_id VARCHAR(50) NOT NULL,
                criterion_id VARCHAR(30) NOT NULL REFERENCES qa_criteria(id),
                ai_score NUMERIC(4,2),
                human_score NUMERIC(4,2),
                variance NUMERIC(4,2),
                reviewer_id INTEGER REFERENCES users(id),
                calibrated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
            );
            """,

            # =================================================================
            # Voice Biometrics Tables
            # =================================================================

            # 8. Voiceprints
            """
            CREATE TABLE IF NOT EXISTS voiceprints (
                id VARCHAR(50) PRIMARY KEY,
                caller_id VARCHAR(50) NOT NULL,
                phone_number VARCHAR(20),
                status VARCHAR(20) DEFAULT 'active',
                voiceprint_data BYTEA,
                quality_score NUMERIC(4,3) DEFAULT 0.0,
                sample_count INTEGER DEFAULT 0,
                verification_count INTEGER DEFAULT 0,
                successful_verifications INTEGER DEFAULT 0,
                failed_verifications INTEGER DEFAULT 0,
                spoof_attempts INTEGER DEFAULT 0,
                consent_given BOOLEAN DEFAULT TRUE,
                consent_date TIMESTAMP WITH TIME ZONE,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP WITH TIME ZONE,
                last_used_at TIMESTAMP WITH TIME ZONE
            );
            """,

            # 9. Caller Profiles
            """
            CREATE TABLE IF NOT EXISTS caller_profiles (
                caller_id VARCHAR(50) PRIMARY KEY,
                name VARCHAR(100),
                phone_numbers TEXT[],
                is_verified BOOLEAN DEFAULT FALSE,
                trust_level VARCHAR(20) DEFAULT 'new',
                total_calls INTEGER DEFAULT 0,
                verified_calls INTEGER DEFAULT 0,
                preferences JSONB,
                notes TEXT,
                first_seen TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                last_seen TIMESTAMP WITH TIME ZONE
            );
            """,

            # 10. Verification History
            """
            CREATE TABLE IF NOT EXISTS verification_history (
                id SERIAL PRIMARY KEY,
                voiceprint_id VARCHAR(50) NOT NULL REFERENCES voiceprints(id),
                call_id VARCHAR(50),
                result VARCHAR(20) NOT NULL,
                confidence NUMERIC(4,3) DEFAULT 0.0,
                spoof_detected BOOLEAN DEFAULT FALSE,
                verification_time_ms INTEGER DEFAULT 0,
                verified_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
            );
            """,

            # =================================================================
            # Multi-Tenant & White-Label Tables
            # =================================================================

            # 11. Tenants
            """
            CREATE TABLE IF NOT EXISTS tenants (
                id VARCHAR(50) PRIMARY KEY,
                name VARCHAR(100) NOT NULL,
                slug VARCHAR(100) UNIQUE NOT NULL,
                tier VARCHAR(20) DEFAULT 'starter',
                status VARCHAR(20) DEFAULT 'active',
                primary_contact_name VARCHAR(100),
                primary_contact_email VARCHAR(255) NOT NULL,
                primary_contact_phone VARCHAR(20),
                billing_email VARCHAR(255),
                api_key_hash VARCHAR(64),
                sla_tier VARCHAR(20) DEFAULT 'standard',
                sla_response_time_hours INTEGER DEFAULT 24,
                sla_uptime_percentage NUMERIC(5,2) DEFAULT 99.5,
                trial_ends_at TIMESTAMP WITH TIME ZONE,
                subscription_ends_at TIMESTAMP WITH TIME ZONE,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP WITH TIME ZONE
            );
            """,

            # 12. Tenant Limits
            """
            CREATE TABLE IF NOT EXISTS tenant_limits (
                tenant_id VARCHAR(50) PRIMARY KEY REFERENCES tenants(id) ON DELETE CASCADE,
                max_monthly_calls INTEGER DEFAULT 1000,
                max_concurrent_calls INTEGER DEFAULT 5,
                max_users INTEGER DEFAULT 10,
                max_phone_numbers INTEGER DEFAULT 3,
                max_custom_voices INTEGER DEFAULT 1,
                max_integrations INTEGER DEFAULT 5,
                recording_retention_days INTEGER DEFAULT 30,
                analytics_retention_days INTEGER DEFAULT 90,
                api_rate_limit_per_minute INTEGER DEFAULT 60
            );
            """,

            # 13. Tenant Branding
            """
            CREATE TABLE IF NOT EXISTS tenant_branding (
                tenant_id VARCHAR(50) PRIMARY KEY REFERENCES tenants(id) ON DELETE CASCADE,
                company_name VARCHAR(100),
                company_logo_url TEXT,
                primary_color VARCHAR(10) DEFAULT '#1976D2',
                secondary_color VARCHAR(10) DEFAULT '#424242',
                accent_color VARCHAR(10) DEFAULT '#FF9800',
                default_voice_id VARCHAR(50),
                custom_voice_ids TEXT[],
                greeting_template TEXT,
                hold_music_url TEXT,
                script_templates JSONB,
                fallback_messages JSONB,
                email_from_name VARCHAR(100),
                email_from_address VARCHAR(255),
                email_footer_html TEXT,
                email_logo_url TEXT,
                sms_sender_id VARCHAR(20),
                sms_signature VARCHAR(100),
                custom_domain VARCHAR(255),
                subdomain VARCHAR(100),
                favicon_url TEXT,
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
            );
            """,

            # 14. Tenant Features
            """
            CREATE TABLE IF NOT EXISTS tenant_features (
                id SERIAL PRIMARY KEY,
                tenant_id VARCHAR(50) NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
                feature_name VARCHAR(50) NOT NULL,
                is_enabled BOOLEAN DEFAULT FALSE,
                custom_config JSONB,
                enabled_at TIMESTAMP WITH TIME ZONE,
                UNIQUE (tenant_id, feature_name)
            );
            """,

            # 15. Tenant Usage
            """
            CREATE TABLE IF NOT EXISTS tenant_usage (
                id SERIAL PRIMARY KEY,
                tenant_id VARCHAR(50) NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
                period_start TIMESTAMP WITH TIME ZONE NOT NULL,
                period_end TIMESTAMP WITH TIME ZONE NOT NULL,
                total_calls INTEGER DEFAULT 0,
                successful_calls INTEGER DEFAULT 0,
                failed_calls INTEGER DEFAULT 0,
                total_call_minutes NUMERIC(10,2) DEFAULT 0.0,
                peak_concurrent_calls INTEGER DEFAULT 0,
                api_requests INTEGER DEFAULT 0,
                api_errors INTEGER DEFAULT 0,
                sms_sent INTEGER DEFAULT 0,
                emails_sent INTEGER DEFAULT 0,
                escalations INTEGER DEFAULT 0,
                voiceprint_verifications INTEGER DEFAULT 0,
                recording_storage_mb NUMERIC(10,2) DEFAULT 0.0,
                document_storage_mb NUMERIC(10,2) DEFAULT 0.0
            );
            """,

            # 16. Tenant Settings
            """
            CREATE TABLE IF NOT EXISTS tenant_settings (
                tenant_id VARCHAR(50) PRIMARY KEY REFERENCES tenants(id) ON DELETE CASCADE,
                settings JSONB,
                metadata JSONB,
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
            );
            """,

            # =================================================================
            # Indices
            # =================================================================
            "CREATE INDEX IF NOT EXISTS idx_live_agents_status ON live_agents(status);",
            "CREATE INDEX IF NOT EXISTS idx_escalations_status ON escalations(status);",
            "CREATE INDEX IF NOT EXISTS idx_escalations_call ON escalations(call_id);",
            "CREATE INDEX IF NOT EXISTS idx_escalations_agent ON escalations(assigned_agent_id);",
            "CREATE INDEX IF NOT EXISTS idx_queue_priority ON escalation_queue(priority_score DESC);",
            "CREATE INDEX IF NOT EXISTS idx_scorecards_call ON qa_scorecards(call_id);",
            "CREATE INDEX IF NOT EXISTS idx_reviews_status ON qa_reviews(status);",
            "CREATE INDEX IF NOT EXISTS idx_reviews_reviewer ON qa_reviews(assigned_reviewer_id);",
            "CREATE INDEX IF NOT EXISTS idx_voiceprints_caller ON voiceprints(caller_id);",
            "CREATE INDEX IF NOT EXISTS idx_voiceprints_phone ON voiceprints(phone_number);",
            "CREATE INDEX IF NOT EXISTS idx_verification_voiceprint ON verification_history(voiceprint_id);",
            "CREATE INDEX IF NOT EXISTS idx_tenants_slug ON tenants(slug);",
            "CREATE INDEX IF NOT EXISTS idx_tenants_status ON tenants(status);",
            "CREATE INDEX IF NOT EXISTS idx_tenant_usage_period ON tenant_usage(tenant_id, period_start);",

            # Insert default QA criteria
            """
            INSERT INTO qa_criteria (id, name, description, category, weight, max_score, is_critical)
            VALUES
                ('greeting', 'Professional Greeting', 'Proper greeting and introduction', 'opening', 1.0, 5.0, false),
                ('listening', 'Active Listening', 'Demonstrates understanding of caller needs', 'communication', 1.2, 5.0, false),
                ('resolution', 'Problem Resolution', 'Effectively addresses caller concern', 'resolution', 1.5, 5.0, true),
                ('knowledge', 'Product Knowledge', 'Accurate information provided', 'expertise', 1.3, 5.0, true),
                ('empathy', 'Empathy & Rapport', 'Shows understanding and builds rapport', 'communication', 1.0, 5.0, false),
                ('clarity', 'Clarity of Communication', 'Clear and understandable responses', 'communication', 1.1, 5.0, false),
                ('efficiency', 'Call Efficiency', 'Appropriate call duration and pacing', 'efficiency', 0.8, 5.0, false),
                ('compliance', 'Compliance & Protocol', 'Follows required procedures', 'compliance', 1.4, 5.0, true),
                ('closing', 'Professional Closing', 'Proper call conclusion', 'closing', 0.9, 5.0, false),
                ('documentation', 'Documentation', 'Accurate notes and follow-up', 'admin', 0.8, 5.0, false)
            ON CONFLICT (id) DO NOTHING;
            """,
        ]


def run_migration():
    """Create Phase 5 tables"""
    sql_commands = get_sql_commands()

    try:
        with engine.connect() as conn:
            for idx, sql in enumerate(sql_commands, 1):
                try:
                    logger.info(f"Executing command {idx}/{len(sql_commands)}...")
                    conn.execute(text(sql))
                    conn.commit()
                    logger.info(f"Command {idx} executed successfully")
                except Exception as e:
                    if "already exists" in str(e).lower():
                        logger.info(f"Command {idx} skipped (already exists)")
                    else:
                        logger.error(f"Error executing command {idx}: {e}")
                    continue

        logger.info("Phase 5 tables migration completed successfully!")
        return True

    except Exception as e:
        logger.error(f"Migration failed: {e}")
        return False


if __name__ == "__main__":
    logger.info("=" * 60)
    logger.info("  PHASE 5 DATABASE MIGRATION")
    logger.info("  Tables: Escalation, QA, Biometrics, Multi-Tenant")
    logger.info("=" * 60)
    logger.info(f"Database: {'SQLite' if is_sqlite else 'PostgreSQL'}")
    logger.info("")

    success = run_migration()

    if success:
        logger.info("")
        logger.info("=" * 60)
        logger.info("  MIGRATION COMPLETE")
        logger.info("=" * 60)
        logger.info("Tables created:")
        logger.info("  Live Agent Escalation:")
        logger.info("    - live_agents")
        logger.info("    - escalations")
        logger.info("    - escalation_queue")
        logger.info("  Call Quality Assurance:")
        logger.info("    - qa_scorecards")
        logger.info("    - qa_reviews")
        logger.info("    - qa_criteria")
        logger.info("    - qa_calibration")
        logger.info("  Voice Biometrics:")
        logger.info("    - voiceprints")
        logger.info("    - caller_profiles")
        logger.info("    - verification_history")
        logger.info("  Multi-Tenant:")
        logger.info("    - tenants")
        logger.info("    - tenant_limits")
        logger.info("    - tenant_branding")
        logger.info("    - tenant_features")
        logger.info("    - tenant_usage")
        logger.info("    - tenant_settings")
        logger.info("")
    else:
        logger.error("Migration failed!")
        sys.exit(1)
