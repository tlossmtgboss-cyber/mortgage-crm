"""
AI Daily Blog + PDF Content Factory - Database Migration
Creates all tables for automated content generation system
"""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text, inspect
from database import get_db_url

def run_migration():
    """Create AI Daily Blog tables"""
    engine = create_engine(get_db_url())

    with engine.connect() as conn:
        # Check if tables already exist
        inspector = inspect(engine)
        existing_tables = inspector.get_table_names()

        # Voice Profiles - Saved brand voice presets
        if 'blog_voice_profiles' not in existing_tables:
            conn.execute(text("""
                CREATE TABLE blog_voice_profiles (
                    id TEXT PRIMARY KEY,
                    user_id INTEGER REFERENCES users(id),
                    name VARCHAR(255) NOT NULL,
                    sliders_json JSONB DEFAULT '{}',
                    toggles_json JSONB DEFAULT '{}',
                    examples_json JSONB DEFAULT '{}',
                    active BOOLEAN DEFAULT true,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """))
            conn.execute(text("CREATE INDEX idx_voice_profiles_user ON blog_voice_profiles(user_id)"))
            print("✅ Created blog_voice_profiles table")

        # Compliance Profiles - Industry-specific guardrails
        if 'blog_compliance_profiles' not in existing_tables:
            conn.execute(text("""
                CREATE TABLE blog_compliance_profiles (
                    id TEXT PRIMARY KEY,
                    user_id INTEGER REFERENCES users(id),
                    name VARCHAR(255) NOT NULL,
                    required_disclosures_json JSONB DEFAULT '[]',
                    banned_phrases_json JSONB DEFAULT '[]',
                    overrides_json JSONB DEFAULT '{}',
                    active BOOLEAN DEFAULT true,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """))
            conn.execute(text("CREATE INDEX idx_compliance_profiles_user ON blog_compliance_profiles(user_id)"))
            print("✅ Created blog_compliance_profiles table")

        # Source Documents - Uploaded PDFs, guides, training docs
        if 'blog_source_documents' not in existing_tables:
            conn.execute(text("""
                CREATE TABLE blog_source_documents (
                    id TEXT PRIMARY KEY,
                    user_id INTEGER REFERENCES users(id),
                    type VARCHAR(50) DEFAULT 'pdf',
                    title VARCHAR(500) NOT NULL,
                    author VARCHAR(255),
                    file_path TEXT NOT NULL,
                    file_size INTEGER DEFAULT 0,
                    page_count INTEGER DEFAULT 0,
                    extracted_text TEXT,
                    page_map_json JSONB DEFAULT '{}',
                    concept_map_json JSONB DEFAULT '{}',
                    rights_attestation BOOLEAN DEFAULT false,
                    processed BOOLEAN DEFAULT false,
                    processing_error TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """))
            conn.execute(text("CREATE INDEX idx_source_docs_user ON blog_source_documents(user_id)"))
            conn.execute(text("CREATE INDEX idx_source_docs_processed ON blog_source_documents(processed)"))
            print("✅ Created blog_source_documents table")

        # Content Campaigns - Organized content strategies
        if 'blog_campaigns' not in existing_tables:
            conn.execute(text("""
                CREATE TABLE blog_campaigns (
                    id TEXT PRIMARY KEY,
                    user_id INTEGER REFERENCES users(id),
                    name VARCHAR(255) NOT NULL,
                    brief_json JSONB DEFAULT '{}',
                    archetype_weights_json JSONB DEFAULT '{}',
                    voice_profile_id TEXT REFERENCES blog_voice_profiles(id),
                    compliance_profile_id TEXT REFERENCES blog_compliance_profiles(id),
                    posting_mode VARCHAR(50) DEFAULT 'draft',
                    auto_schedule BOOLEAN DEFAULT false,
                    posts_per_week INTEGER DEFAULT 3,
                    active BOOLEAN DEFAULT true,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """))
            conn.execute(text("CREATE INDEX idx_campaigns_user ON blog_campaigns(user_id)"))
            print("✅ Created blog_campaigns table")

        # Content Items - Generated blog posts and social content
        if 'blog_content_items' not in existing_tables:
            conn.execute(text("""
                CREATE TABLE blog_content_items (
                    id TEXT PRIMARY KEY,
                    user_id INTEGER REFERENCES users(id),
                    campaign_id TEXT REFERENCES blog_campaigns(id),
                    source_document_id TEXT REFERENCES blog_source_documents(id),
                    status VARCHAR(50) DEFAULT 'draft',
                    scheduled_at TIMESTAMP,
                    published_at TIMESTAMP,
                    archetype VARCHAR(50) DEFAULT 'informative',
                    title VARCHAR(500) DEFAULT '',
                    slug VARCHAR(500) DEFAULT '',
                    blog_md TEXT DEFAULT '',
                    blog_html TEXT DEFAULT '',
                    social_json JSONB DEFAULT '{}',
                    image_url TEXT,
                    image_prompt TEXT,
                    metadata_json JSONB DEFAULT '{}',
                    source_trace_json JSONB DEFAULT '{}',
                    voice_profile_id TEXT REFERENCES blog_voice_profiles(id),
                    compliance_profile_id TEXT REFERENCES blog_compliance_profiles(id),
                    uniqueness_score FLOAT,
                    engagement_score FLOAT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """))
            conn.execute(text("CREATE INDEX idx_content_user ON blog_content_items(user_id)"))
            conn.execute(text("CREATE INDEX idx_content_status ON blog_content_items(status)"))
            conn.execute(text("CREATE INDEX idx_content_scheduled ON blog_content_items(scheduled_at)"))
            conn.execute(text("CREATE INDEX idx_content_slug ON blog_content_items(slug)"))
            print("✅ Created blog_content_items table")

        # Content Jobs - Background processing jobs
        if 'blog_content_jobs' not in existing_tables:
            conn.execute(text("""
                CREATE TABLE blog_content_jobs (
                    id TEXT PRIMARY KEY,
                    user_id INTEGER REFERENCES users(id),
                    type VARCHAR(100) NOT NULL,
                    status VARCHAR(50) DEFAULT 'queued',
                    payload_json JSONB DEFAULT '{}',
                    result_json JSONB DEFAULT '{}',
                    error TEXT,
                    progress INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    started_at TIMESTAMP,
                    completed_at TIMESTAMP
                )
            """))
            conn.execute(text("CREATE INDEX idx_jobs_user ON blog_content_jobs(user_id)"))
            conn.execute(text("CREATE INDEX idx_jobs_status ON blog_content_jobs(status)"))
            print("✅ Created blog_content_jobs table")

        # Image Assets - Generated branded images
        if 'blog_image_assets' not in existing_tables:
            conn.execute(text("""
                CREATE TABLE blog_image_assets (
                    id TEXT PRIMARY KEY,
                    user_id INTEGER REFERENCES users(id),
                    content_item_id TEXT REFERENCES blog_content_items(id),
                    provider VARCHAR(50) DEFAULT 'template',
                    prompt TEXT DEFAULT '',
                    url TEXT NOT NULL,
                    file_path TEXT,
                    metadata_json JSONB DEFAULT '{}',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """))
            conn.execute(text("CREATE INDEX idx_images_user ON blog_image_assets(user_id)"))
            conn.execute(text("CREATE INDEX idx_images_content ON blog_image_assets(content_item_id)"))
            print("✅ Created blog_image_assets table")

        # Social Connections - Connected social platforms
        if 'blog_social_connections' not in existing_tables:
            conn.execute(text("""
                CREATE TABLE blog_social_connections (
                    id TEXT PRIMARY KEY,
                    user_id INTEGER REFERENCES users(id),
                    provider VARCHAR(50) NOT NULL,
                    profile_id VARCHAR(255) NOT NULL,
                    profile_name VARCHAR(255),
                    access_token_encrypted TEXT NOT NULL,
                    refresh_token_encrypted TEXT,
                    token_expires_at TIMESTAMP,
                    channel_map_json JSONB DEFAULT '{}',
                    status VARCHAR(50) DEFAULT 'active',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """))
            conn.execute(text("CREATE INDEX idx_social_user ON blog_social_connections(user_id)"))
            print("✅ Created blog_social_connections table")

        # Publish Logs - Record of all publishing attempts
        if 'blog_publish_logs' not in existing_tables:
            conn.execute(text("""
                CREATE TABLE blog_publish_logs (
                    id TEXT PRIMARY KEY,
                    user_id INTEGER REFERENCES users(id),
                    content_item_id TEXT REFERENCES blog_content_items(id),
                    platform VARCHAR(50) NOT NULL,
                    status VARCHAR(50) DEFAULT 'pending',
                    external_id VARCHAR(255),
                    external_url TEXT,
                    response_json JSONB DEFAULT '{}',
                    error TEXT,
                    retry_count INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    completed_at TIMESTAMP
                )
            """))
            conn.execute(text("CREATE INDEX idx_publish_content ON blog_publish_logs(content_item_id)"))
            conn.execute(text("CREATE INDEX idx_publish_status ON blog_publish_logs(status)"))
            print("✅ Created blog_publish_logs table")

        # Topic Queue - Pre-generated topic ideas for content
        if 'blog_topic_queue' not in existing_tables:
            conn.execute(text("""
                CREATE TABLE blog_topic_queue (
                    id TEXT PRIMARY KEY,
                    user_id INTEGER REFERENCES users(id),
                    campaign_id TEXT REFERENCES blog_campaigns(id),
                    source_document_id TEXT REFERENCES blog_source_documents(id),
                    topic VARCHAR(500) NOT NULL,
                    keyword VARCHAR(255),
                    angle TEXT,
                    archetype VARCHAR(50) DEFAULT 'informative',
                    priority INTEGER DEFAULT 0,
                    used BOOLEAN DEFAULT false,
                    used_at TIMESTAMP,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """))
            conn.execute(text("CREATE INDEX idx_topics_user ON blog_topic_queue(user_id)"))
            conn.execute(text("CREATE INDEX idx_topics_used ON blog_topic_queue(used)"))
            print("✅ Created blog_topic_queue table")

        # Audit Logs - Track all content changes
        if 'blog_audit_logs' not in existing_tables:
            conn.execute(text("""
                CREATE TABLE blog_audit_logs (
                    id TEXT PRIMARY KEY,
                    user_id INTEGER REFERENCES users(id),
                    action VARCHAR(100) NOT NULL,
                    entity_type VARCHAR(100) NOT NULL,
                    entity_id TEXT NOT NULL,
                    before_json JSONB DEFAULT '{}',
                    after_json JSONB DEFAULT '{}',
                    ip_address VARCHAR(50),
                    user_agent TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """))
            conn.execute(text("CREATE INDEX idx_audit_user ON blog_audit_logs(user_id)"))
            conn.execute(text("CREATE INDEX idx_audit_entity ON blog_audit_logs(entity_type, entity_id)"))
            print("✅ Created blog_audit_logs table")

        # Performance Feedback - Track content performance for learning
        if 'blog_performance_feedback' not in existing_tables:
            conn.execute(text("""
                CREATE TABLE blog_performance_feedback (
                    id TEXT PRIMARY KEY,
                    user_id INTEGER REFERENCES users(id),
                    content_item_id TEXT REFERENCES blog_content_items(id),
                    platform VARCHAR(50),
                    views INTEGER DEFAULT 0,
                    likes INTEGER DEFAULT 0,
                    comments INTEGER DEFAULT 0,
                    shares INTEGER DEFAULT 0,
                    clicks INTEGER DEFAULT 0,
                    leads_generated INTEGER DEFAULT 0,
                    engagement_rate FLOAT,
                    fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """))
            conn.execute(text("CREATE INDEX idx_perf_content ON blog_performance_feedback(content_item_id)"))
            print("✅ Created blog_performance_feedback table")

        # User Blog Settings - Per-user configuration
        if 'blog_user_settings' not in existing_tables:
            conn.execute(text("""
                CREATE TABLE blog_user_settings (
                    id TEXT PRIMARY KEY,
                    user_id INTEGER UNIQUE REFERENCES users(id),
                    default_voice_profile_id TEXT REFERENCES blog_voice_profiles(id),
                    default_compliance_profile_id TEXT REFERENCES blog_compliance_profiles(id),
                    posting_mode VARCHAR(50) DEFAULT 'draft',
                    auto_generate_daily BOOLEAN DEFAULT false,
                    daily_generate_time TIME DEFAULT '06:00',
                    timezone VARCHAR(100) DEFAULT 'America/New_York',
                    brand_logo_url TEXT,
                    brand_colors_json JSONB DEFAULT '{}',
                    llm_provider VARCHAR(50) DEFAULT 'openai',
                    llm_model VARCHAR(100) DEFAULT 'gpt-4-turbo-preview',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """))
            print("✅ Created blog_user_settings table")

        conn.commit()
        print("\n✅ AI Daily Blog migration completed successfully!")

if __name__ == "__main__":
    run_migration()
