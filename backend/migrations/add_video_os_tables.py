"""
Video OS Database Migration
Creates tables for the internal video generation, hosting, and analytics system.

Tables:
- video_brand_templates: Brand kits (fonts, colors, watermarks, themes)
- video_voice_profiles: Voice configurations for TTS
- video_projects: Main video projects
- video_storyboard_scenes: Scene definitions for each project
- video_render_jobs: Async render job tracking
- video_render_artifacts: Output files from renders
- video_library: Hosted videos with sharing controls
- video_analytics_events: Player events for analytics
- video_viewer_sessions: Viewer tracking and attribution
- video_cta_overlays: Call-to-action configurations
- video_asset_library: Reusable assets (images, clips, music)
"""

import os
import logging
from datetime import datetime
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

logger = logging.getLogger(__name__)

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./mortgage_crm.db")


def run_migration():
    """Run the Video OS migration."""
    if DATABASE_URL.startswith("postgres"):
        db_url = DATABASE_URL.replace("postgres://", "postgresql://", 1)
    else:
        db_url = DATABASE_URL

    engine = create_engine(db_url)
    Session = sessionmaker(bind=engine)
    session = Session()

    try:
        is_postgres = "postgresql" in db_url

        if is_postgres:
            # PostgreSQL version with all features
            session.execute(text("""
                -- =====================================================
                -- ENUMS
                -- =====================================================

                DO $$ BEGIN
                    CREATE TYPE video_source_type AS ENUM (
                        'thought', 'blog', 'podcast', 'script', 'upload'
                    );
                EXCEPTION WHEN duplicate_object THEN NULL;
                END $$;

                DO $$ BEGIN
                    CREATE TYPE video_project_status AS ENUM (
                        'draft', 'queued', 'processing', 'ready', 'failed', 'archived'
                    );
                EXCEPTION WHEN duplicate_object THEN NULL;
                END $$;

                DO $$ BEGIN
                    CREATE TYPE render_job_state AS ENUM (
                        'created', 'scripted', 'voiced', 'storyboarded',
                        'visualized', 'rendering', 'rendered', 'published', 'failed'
                    );
                EXCEPTION WHEN duplicate_object THEN NULL;
                END $$;

                DO $$ BEGIN
                    CREATE TYPE video_format AS ENUM (
                        'portrait_9x16', 'square_1x1', 'landscape_16x9'
                    );
                EXCEPTION WHEN duplicate_object THEN NULL;
                END $$;

                DO $$ BEGIN
                    CREATE TYPE video_visibility AS ENUM (
                        'private', 'internal', 'unlisted', 'public'
                    );
                EXCEPTION WHEN duplicate_object THEN NULL;
                END $$;

                DO $$ BEGIN
                    CREATE TYPE visual_source_type AS ENUM (
                        'ai_image', 'stock', 'uploaded', 'screen_recording', 'avatar'
                    );
                EXCEPTION WHEN duplicate_object THEN NULL;
                END $$;

                DO $$ BEGIN
                    CREATE TYPE motion_style AS ENUM (
                        'static', 'pan_left', 'pan_right', 'zoom_in', 'zoom_out',
                        'ken_burns', 'cut', 'fade', 'slide'
                    );
                EXCEPTION WHEN duplicate_object THEN NULL;
                END $$;

                DO $$ BEGIN
                    CREATE TYPE caption_style AS ENUM (
                        'classic', 'karaoke', 'pop', 'highlight', 'minimal', 'bold'
                    );
                EXCEPTION WHEN duplicate_object THEN NULL;
                END $$;
            """))

            # Brand Templates
            session.execute(text("""
                CREATE TABLE IF NOT EXISTS video_brand_templates (
                    id SERIAL PRIMARY KEY,
                    organization_id INTEGER,
                    name VARCHAR(255) NOT NULL,
                    description TEXT,

                    -- Visual branding
                    primary_color VARCHAR(7) DEFAULT '#1a365d',
                    secondary_color VARCHAR(7) DEFAULT '#2b6cb0',
                    accent_color VARCHAR(7) DEFAULT '#ed8936',
                    background_color VARCHAR(7) DEFAULT '#000000',
                    text_color VARCHAR(7) DEFAULT '#ffffff',

                    -- Typography
                    heading_font VARCHAR(100) DEFAULT 'Montserrat',
                    body_font VARCHAR(100) DEFAULT 'Open Sans',
                    caption_font VARCHAR(100) DEFAULT 'Roboto',

                    -- Assets
                    logo_url TEXT,
                    watermark_url TEXT,
                    watermark_position VARCHAR(20) DEFAULT 'bottom_right',
                    watermark_opacity DECIMAL(3,2) DEFAULT 0.7,
                    intro_video_url TEXT,
                    outro_video_url TEXT,
                    background_music_url TEXT,
                    music_volume DECIMAL(3,2) DEFAULT 0.15,

                    -- Caption styling
                    caption_style caption_style DEFAULT 'pop',
                    caption_position VARCHAR(20) DEFAULT 'center',
                    caption_background BOOLEAN DEFAULT true,
                    caption_max_words INTEGER DEFAULT 3,

                    -- Lower thirds / overlays
                    lower_third_template JSONB DEFAULT '{}',

                    -- Compliance
                    nmls_number VARCHAR(50),
                    disclaimer_text TEXT,
                    show_disclaimer BOOLEAN DEFAULT false,

                    is_default BOOLEAN DEFAULT false,
                    is_active BOOLEAN DEFAULT true,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                )
            """))

            # Voice Profiles
            session.execute(text("""
                CREATE TABLE IF NOT EXISTS video_voice_profiles (
                    id SERIAL PRIMARY KEY,
                    organization_id INTEGER,
                    user_id INTEGER,

                    name VARCHAR(255) NOT NULL,
                    description TEXT,

                    -- Voice configuration
                    voice_engine VARCHAR(50) DEFAULT 'local_tts',
                    voice_id VARCHAR(255),
                    language VARCHAR(10) DEFAULT 'en-US',

                    -- Voice characteristics
                    speaking_rate DECIMAL(3,2) DEFAULT 1.0,
                    pitch DECIMAL(3,2) DEFAULT 1.0,
                    volume_gain_db DECIMAL(4,2) DEFAULT 0.0,

                    -- Clone settings (for future)
                    is_clone BOOLEAN DEFAULT false,
                    clone_sample_urls JSONB DEFAULT '[]',
                    clone_consent_at TIMESTAMP WITH TIME ZONE,
                    clone_consent_by INTEGER,

                    -- Usage
                    total_characters_used BIGINT DEFAULT 0,
                    last_used_at TIMESTAMP WITH TIME ZONE,

                    is_default BOOLEAN DEFAULT false,
                    is_active BOOLEAN DEFAULT true,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                )
            """))

            # Video Projects (main entity)
            session.execute(text("""
                CREATE TABLE IF NOT EXISTS video_projects (
                    id SERIAL PRIMARY KEY,
                    organization_id INTEGER,
                    created_by INTEGER NOT NULL,

                    -- Project info
                    title VARCHAR(500) NOT NULL,
                    description TEXT,

                    -- Source content
                    source_type video_source_type DEFAULT 'thought',
                    source_text TEXT,
                    source_url TEXT,

                    -- Generation settings
                    brand_template_id INTEGER REFERENCES video_brand_templates(id),
                    voice_profile_id INTEGER REFERENCES video_voice_profiles(id),
                    target_duration_seconds INTEGER DEFAULT 60,
                    target_formats JSONB DEFAULT '["portrait_9x16"]',

                    -- Generated content
                    generated_script TEXT,
                    generated_blog TEXT,
                    generated_podcast_notes TEXT,
                    hook_variants JSONB DEFAULT '[]',

                    -- Status
                    status video_project_status DEFAULT 'draft',
                    error_message TEXT,

                    -- Metadata
                    tags JSONB DEFAULT '[]',
                    category VARCHAR(100),

                    -- Relations
                    lead_id INTEGER,
                    loan_id INTEGER,
                    campaign_id INTEGER,

                    -- Timestamps
                    published_at TIMESTAMP WITH TIME ZONE,
                    archived_at TIMESTAMP WITH TIME ZONE,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                )
            """))

            # Storyboard Scenes
            session.execute(text("""
                CREATE TABLE IF NOT EXISTS video_storyboard_scenes (
                    id SERIAL PRIMARY KEY,
                    project_id INTEGER NOT NULL REFERENCES video_projects(id) ON DELETE CASCADE,

                    scene_index INTEGER NOT NULL,
                    duration_seconds DECIMAL(6,2) NOT NULL,

                    -- Audio
                    voiceover_text TEXT NOT NULL,
                    voiceover_start_time DECIMAL(8,3),
                    voiceover_end_time DECIMAL(8,3),

                    -- Captions
                    on_screen_text TEXT,
                    caption_words JSONB DEFAULT '[]',
                    caption_style caption_style DEFAULT 'pop',

                    -- Visual
                    visual_source visual_source_type DEFAULT 'ai_image',
                    visual_prompt TEXT,
                    visual_url TEXT,
                    visual_thumbnail_url TEXT,

                    -- Motion
                    motion_style motion_style DEFAULT 'ken_burns',
                    transition_in VARCHAR(50) DEFAULT 'fade',
                    transition_out VARCHAR(50) DEFAULT 'fade',

                    -- Overlays
                    hook_text TEXT,
                    cta_overlay_id INTEGER,
                    show_lower_third BOOLEAN DEFAULT false,
                    lower_third_text TEXT,

                    -- Metadata
                    scene_type VARCHAR(50) DEFAULT 'content',
                    notes TEXT,

                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,

                    UNIQUE(project_id, scene_index)
                )
            """))

            # Render Jobs
            session.execute(text("""
                CREATE TABLE IF NOT EXISTS video_render_jobs (
                    id SERIAL PRIMARY KEY,
                    job_id VARCHAR(50) UNIQUE NOT NULL,
                    project_id INTEGER NOT NULL REFERENCES video_projects(id),

                    -- Format
                    format video_format NOT NULL,
                    resolution VARCHAR(20) DEFAULT '1080x1920',
                    fps INTEGER DEFAULT 30,

                    -- State machine
                    state render_job_state DEFAULT 'created',
                    progress INTEGER DEFAULT 0,
                    current_step VARCHAR(100),

                    -- Timing
                    queued_at TIMESTAMP WITH TIME ZONE,
                    started_at TIMESTAMP WITH TIME ZONE,
                    completed_at TIMESTAMP WITH TIME ZONE,

                    -- Resources
                    worker_id VARCHAR(100),
                    gpu_seconds DECIMAL(10,2) DEFAULT 0,
                    cpu_seconds DECIMAL(10,2) DEFAULT 0,

                    -- Error handling
                    retry_count INTEGER DEFAULT 0,
                    max_retries INTEGER DEFAULT 3,
                    error_message TEXT,
                    error_details JSONB,

                    -- Output
                    output_duration_seconds DECIMAL(8,2),
                    output_file_size_bytes BIGINT,

                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                )
            """))

            # Render Artifacts
            session.execute(text("""
                CREATE TABLE IF NOT EXISTS video_render_artifacts (
                    id SERIAL PRIMARY KEY,
                    render_job_id INTEGER NOT NULL REFERENCES video_render_jobs(id) ON DELETE CASCADE,

                    artifact_type VARCHAR(50) NOT NULL,
                    file_url TEXT NOT NULL,
                    file_size_bytes BIGINT,
                    mime_type VARCHAR(100),

                    -- Metadata
                    duration_seconds DECIMAL(8,2),
                    resolution VARCHAR(20),

                    -- For SRT/VTT
                    word_count INTEGER,

                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                )
            """))

            # Video Library (hosted videos)
            session.execute(text("""
                CREATE TABLE IF NOT EXISTS video_library (
                    id SERIAL PRIMARY KEY,
                    organization_id INTEGER,

                    -- Video info
                    title VARCHAR(500) NOT NULL,
                    description TEXT,

                    -- Source
                    project_id INTEGER REFERENCES video_projects(id),
                    render_job_id INTEGER REFERENCES video_render_jobs(id),

                    -- Files
                    video_url TEXT NOT NULL,
                    thumbnail_url TEXT,
                    preview_gif_url TEXT,
                    poster_url TEXT,

                    -- Metadata
                    duration_seconds DECIMAL(8,2),
                    file_size_bytes BIGINT,
                    format video_format,
                    resolution VARCHAR(20),

                    -- Sharing
                    share_token VARCHAR(100) UNIQUE,
                    visibility video_visibility DEFAULT 'private',
                    password_hash VARCHAR(255),
                    expires_at TIMESTAMP WITH TIME ZONE,

                    -- Embedding
                    allow_embed BOOLEAN DEFAULT true,
                    allowed_domains JSONB DEFAULT '[]',

                    -- CTAs
                    cta_enabled BOOLEAN DEFAULT false,
                    cta_config JSONB DEFAULT '{}',

                    -- Stats (denormalized for speed)
                    view_count INTEGER DEFAULT 0,
                    unique_viewer_count INTEGER DEFAULT 0,
                    total_watch_time_seconds BIGINT DEFAULT 0,
                    avg_watch_percent DECIMAL(5,2) DEFAULT 0,

                    -- Organization
                    folder_path VARCHAR(500) DEFAULT '/',
                    tags JSONB DEFAULT '[]',

                    -- Timestamps
                    published_at TIMESTAMP WITH TIME ZONE,
                    last_viewed_at TIMESTAMP WITH TIME ZONE,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                )
            """))

            # Viewer Sessions
            session.execute(text("""
                CREATE TABLE IF NOT EXISTS video_viewer_sessions (
                    id SERIAL PRIMARY KEY,
                    video_id INTEGER NOT NULL REFERENCES video_library(id),

                    -- Viewer identity
                    session_id VARCHAR(100) NOT NULL,
                    viewer_id VARCHAR(255),

                    -- CRM attribution
                    lead_id INTEGER,
                    contact_id INTEGER,
                    user_id INTEGER,

                    -- Viewer info
                    viewer_name VARCHAR(255),
                    viewer_email VARCHAR(255),
                    viewer_company VARCHAR(255),

                    -- Device/context
                    user_agent TEXT,
                    ip_address VARCHAR(45),
                    country VARCHAR(2),
                    city VARCHAR(100),
                    referrer TEXT,

                    -- Engagement
                    watch_time_seconds INTEGER DEFAULT 0,
                    max_percent_watched DECIMAL(5,2) DEFAULT 0,
                    completed BOOLEAN DEFAULT false,

                    -- Heatmap data
                    watched_segments JSONB DEFAULT '[]',

                    -- CTA interaction
                    cta_shown BOOLEAN DEFAULT false,
                    cta_clicked BOOLEAN DEFAULT false,
                    cta_clicked_at TIMESTAMP WITH TIME ZONE,

                    -- Timestamps
                    started_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    last_activity_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    ended_at TIMESTAMP WITH TIME ZONE
                )
            """))

            # Analytics Events
            session.execute(text("""
                CREATE TABLE IF NOT EXISTS video_analytics_events (
                    id SERIAL PRIMARY KEY,
                    video_id INTEGER NOT NULL REFERENCES video_library(id),
                    session_id INTEGER REFERENCES video_viewer_sessions(id),

                    -- Event
                    event_type VARCHAR(50) NOT NULL,
                    event_data JSONB DEFAULT '{}',

                    -- Position
                    video_time_seconds DECIMAL(8,2),
                    percent_watched DECIMAL(5,2),

                    -- Context
                    client_timestamp TIMESTAMP WITH TIME ZONE,

                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                )
            """))

            # CTA Overlays
            session.execute(text("""
                CREATE TABLE IF NOT EXISTS video_cta_overlays (
                    id SERIAL PRIMARY KEY,
                    organization_id INTEGER,

                    name VARCHAR(255) NOT NULL,
                    cta_type VARCHAR(50) NOT NULL,

                    -- Timing
                    show_at_percent DECIMAL(5,2),
                    show_at_seconds DECIMAL(8,2),
                    show_on_pause BOOLEAN DEFAULT false,
                    show_on_end BOOLEAN DEFAULT true,

                    -- Content
                    headline TEXT,
                    description TEXT,
                    button_text VARCHAR(100),
                    button_url TEXT,
                    button_color VARCHAR(7),

                    -- Form fields (for lead capture)
                    form_fields JSONB DEFAULT '[]',

                    -- Styling
                    position VARCHAR(20) DEFAULT 'center',
                    animation VARCHAR(50) DEFAULT 'fade_in',

                    -- Actions
                    action_type VARCHAR(50),
                    action_config JSONB DEFAULT '{}',

                    is_active BOOLEAN DEFAULT true,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                )
            """))

            # Asset Library
            session.execute(text("""
                CREATE TABLE IF NOT EXISTS video_asset_library (
                    id SERIAL PRIMARY KEY,
                    organization_id INTEGER,
                    uploaded_by INTEGER,

                    -- Asset info
                    name VARCHAR(255) NOT NULL,
                    description TEXT,
                    asset_type VARCHAR(50) NOT NULL,

                    -- File
                    file_url TEXT NOT NULL,
                    thumbnail_url TEXT,
                    file_size_bytes BIGINT,
                    mime_type VARCHAR(100),

                    -- Metadata
                    duration_seconds DECIMAL(8,2),
                    width INTEGER,
                    height INTEGER,

                    -- Organization
                    folder_path VARCHAR(500) DEFAULT '/',
                    tags JSONB DEFAULT '[]',

                    -- Usage tracking
                    usage_count INTEGER DEFAULT 0,
                    last_used_at TIMESTAMP WITH TIME ZONE,

                    is_active BOOLEAN DEFAULT true,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                )
            """))

            # Content Vault (approved snippets for brand consistency)
            session.execute(text("""
                CREATE TABLE IF NOT EXISTS video_content_vault (
                    id SERIAL PRIMARY KEY,
                    organization_id INTEGER,
                    created_by INTEGER,

                    content_type VARCHAR(50) NOT NULL,
                    title VARCHAR(255) NOT NULL,
                    content TEXT NOT NULL,

                    -- Categorization
                    category VARCHAR(100),
                    tags JSONB DEFAULT '[]',

                    -- Usage
                    usage_count INTEGER DEFAULT 0,
                    last_used_at TIMESTAMP WITH TIME ZONE,

                    -- Approval
                    is_approved BOOLEAN DEFAULT false,
                    approved_by INTEGER,
                    approved_at TIMESTAMP WITH TIME ZONE,

                    is_active BOOLEAN DEFAULT true,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                )
            """))

            # Indexes
            session.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_video_projects_org ON video_projects(organization_id);
                CREATE INDEX IF NOT EXISTS idx_video_projects_status ON video_projects(status);
                CREATE INDEX IF NOT EXISTS idx_video_projects_created_by ON video_projects(created_by);

                CREATE INDEX IF NOT EXISTS idx_video_render_jobs_project ON video_render_jobs(project_id);
                CREATE INDEX IF NOT EXISTS idx_video_render_jobs_state ON video_render_jobs(state);
                CREATE INDEX IF NOT EXISTS idx_video_render_jobs_job_id ON video_render_jobs(job_id);

                CREATE INDEX IF NOT EXISTS idx_video_library_org ON video_library(organization_id);
                CREATE INDEX IF NOT EXISTS idx_video_library_share_token ON video_library(share_token);
                CREATE INDEX IF NOT EXISTS idx_video_library_visibility ON video_library(visibility);

                CREATE INDEX IF NOT EXISTS idx_video_viewer_sessions_video ON video_viewer_sessions(video_id);
                CREATE INDEX IF NOT EXISTS idx_video_viewer_sessions_lead ON video_viewer_sessions(lead_id);
                CREATE INDEX IF NOT EXISTS idx_video_viewer_sessions_email ON video_viewer_sessions(viewer_email);

                CREATE INDEX IF NOT EXISTS idx_video_analytics_video ON video_analytics_events(video_id);
                CREATE INDEX IF NOT EXISTS idx_video_analytics_session ON video_analytics_events(session_id);
                CREATE INDEX IF NOT EXISTS idx_video_analytics_type ON video_analytics_events(event_type);
            """))

            # Seed default brand template
            session.execute(text("""
                INSERT INTO video_brand_templates (
                    name, description, is_default, is_active,
                    primary_color, secondary_color, accent_color,
                    heading_font, body_font, caption_font,
                    caption_style, watermark_position
                ) VALUES (
                    'Default Mortgage Template',
                    'Clean, professional template for mortgage content',
                    true, true,
                    '#1a365d', '#2b6cb0', '#ed8936',
                    'Montserrat', 'Open Sans', 'Roboto',
                    'pop', 'bottom_right'
                )
                ON CONFLICT DO NOTHING
            """))

            # Seed default voice profile
            session.execute(text("""
                INSERT INTO video_voice_profiles (
                    name, description, is_default, is_active,
                    voice_engine, language, speaking_rate
                ) VALUES (
                    'Default Professional Voice',
                    'Clear, professional American English voice',
                    true, true,
                    'local_tts', 'en-US', 1.0
                )
                ON CONFLICT DO NOTHING
            """))

        else:
            # SQLite version (simplified)
            session.execute(text("""
                CREATE TABLE IF NOT EXISTS video_brand_templates (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    organization_id INTEGER,
                    name VARCHAR(255) NOT NULL,
                    description TEXT,
                    primary_color VARCHAR(7) DEFAULT '#1a365d',
                    secondary_color VARCHAR(7) DEFAULT '#2b6cb0',
                    accent_color VARCHAR(7) DEFAULT '#ed8936',
                    background_color VARCHAR(7) DEFAULT '#000000',
                    text_color VARCHAR(7) DEFAULT '#ffffff',
                    heading_font VARCHAR(100) DEFAULT 'Montserrat',
                    body_font VARCHAR(100) DEFAULT 'Open Sans',
                    caption_font VARCHAR(100) DEFAULT 'Roboto',
                    logo_url TEXT,
                    watermark_url TEXT,
                    watermark_position VARCHAR(20) DEFAULT 'bottom_right',
                    watermark_opacity DECIMAL(3,2) DEFAULT 0.7,
                    intro_video_url TEXT,
                    outro_video_url TEXT,
                    background_music_url TEXT,
                    music_volume DECIMAL(3,2) DEFAULT 0.15,
                    caption_style VARCHAR(20) DEFAULT 'pop',
                    caption_position VARCHAR(20) DEFAULT 'center',
                    caption_background INTEGER DEFAULT 1,
                    caption_max_words INTEGER DEFAULT 3,
                    lower_third_template TEXT DEFAULT '{}',
                    nmls_number VARCHAR(50),
                    disclaimer_text TEXT,
                    show_disclaimer INTEGER DEFAULT 0,
                    is_default INTEGER DEFAULT 0,
                    is_active INTEGER DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """))

            session.execute(text("""
                CREATE TABLE IF NOT EXISTS video_voice_profiles (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    organization_id INTEGER,
                    user_id INTEGER,
                    name VARCHAR(255) NOT NULL,
                    description TEXT,
                    voice_engine VARCHAR(50) DEFAULT 'local_tts',
                    voice_id VARCHAR(255),
                    language VARCHAR(10) DEFAULT 'en-US',
                    speaking_rate DECIMAL(3,2) DEFAULT 1.0,
                    pitch DECIMAL(3,2) DEFAULT 1.0,
                    volume_gain_db DECIMAL(4,2) DEFAULT 0.0,
                    is_clone INTEGER DEFAULT 0,
                    clone_sample_urls TEXT DEFAULT '[]',
                    clone_consent_at TIMESTAMP,
                    clone_consent_by INTEGER,
                    total_characters_used INTEGER DEFAULT 0,
                    last_used_at TIMESTAMP,
                    is_default INTEGER DEFAULT 0,
                    is_active INTEGER DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """))

            session.execute(text("""
                CREATE TABLE IF NOT EXISTS video_projects (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    organization_id INTEGER,
                    created_by INTEGER NOT NULL,
                    title VARCHAR(500) NOT NULL,
                    description TEXT,
                    source_type VARCHAR(20) DEFAULT 'thought',
                    source_text TEXT,
                    source_url TEXT,
                    brand_template_id INTEGER,
                    voice_profile_id INTEGER,
                    target_duration_seconds INTEGER DEFAULT 60,
                    target_formats TEXT DEFAULT '["portrait_9x16"]',
                    generated_script TEXT,
                    generated_blog TEXT,
                    generated_podcast_notes TEXT,
                    hook_variants TEXT DEFAULT '[]',
                    status VARCHAR(20) DEFAULT 'draft',
                    error_message TEXT,
                    tags TEXT DEFAULT '[]',
                    category VARCHAR(100),
                    lead_id INTEGER,
                    loan_id INTEGER,
                    campaign_id INTEGER,
                    published_at TIMESTAMP,
                    archived_at TIMESTAMP,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """))

            session.execute(text("""
                CREATE TABLE IF NOT EXISTS video_storyboard_scenes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_id INTEGER NOT NULL,
                    scene_index INTEGER NOT NULL,
                    duration_seconds DECIMAL(6,2) NOT NULL,
                    voiceover_text TEXT NOT NULL,
                    voiceover_start_time DECIMAL(8,3),
                    voiceover_end_time DECIMAL(8,3),
                    on_screen_text TEXT,
                    caption_words TEXT DEFAULT '[]',
                    caption_style VARCHAR(20) DEFAULT 'pop',
                    visual_source VARCHAR(20) DEFAULT 'ai_image',
                    visual_prompt TEXT,
                    visual_url TEXT,
                    visual_thumbnail_url TEXT,
                    motion_style VARCHAR(20) DEFAULT 'ken_burns',
                    transition_in VARCHAR(50) DEFAULT 'fade',
                    transition_out VARCHAR(50) DEFAULT 'fade',
                    hook_text TEXT,
                    cta_overlay_id INTEGER,
                    show_lower_third INTEGER DEFAULT 0,
                    lower_third_text TEXT,
                    scene_type VARCHAR(50) DEFAULT 'content',
                    notes TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(project_id, scene_index)
                )
            """))

            session.execute(text("""
                CREATE TABLE IF NOT EXISTS video_render_jobs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    job_id VARCHAR(50) UNIQUE NOT NULL,
                    project_id INTEGER NOT NULL,
                    format VARCHAR(20) NOT NULL,
                    resolution VARCHAR(20) DEFAULT '1080x1920',
                    fps INTEGER DEFAULT 30,
                    state VARCHAR(20) DEFAULT 'created',
                    progress INTEGER DEFAULT 0,
                    current_step VARCHAR(100),
                    queued_at TIMESTAMP,
                    started_at TIMESTAMP,
                    completed_at TIMESTAMP,
                    worker_id VARCHAR(100),
                    gpu_seconds DECIMAL(10,2) DEFAULT 0,
                    cpu_seconds DECIMAL(10,2) DEFAULT 0,
                    retry_count INTEGER DEFAULT 0,
                    max_retries INTEGER DEFAULT 3,
                    error_message TEXT,
                    error_details TEXT,
                    output_duration_seconds DECIMAL(8,2),
                    output_file_size_bytes INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """))

            session.execute(text("""
                CREATE TABLE IF NOT EXISTS video_render_artifacts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    render_job_id INTEGER NOT NULL,
                    artifact_type VARCHAR(50) NOT NULL,
                    file_url TEXT NOT NULL,
                    file_size_bytes INTEGER,
                    mime_type VARCHAR(100),
                    duration_seconds DECIMAL(8,2),
                    resolution VARCHAR(20),
                    word_count INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """))

            session.execute(text("""
                CREATE TABLE IF NOT EXISTS video_library (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    organization_id INTEGER,
                    title VARCHAR(500) NOT NULL,
                    description TEXT,
                    project_id INTEGER,
                    render_job_id INTEGER,
                    video_url TEXT NOT NULL,
                    thumbnail_url TEXT,
                    preview_gif_url TEXT,
                    poster_url TEXT,
                    duration_seconds DECIMAL(8,2),
                    file_size_bytes INTEGER,
                    format VARCHAR(20),
                    resolution VARCHAR(20),
                    share_token VARCHAR(100) UNIQUE,
                    visibility VARCHAR(20) DEFAULT 'private',
                    password_hash VARCHAR(255),
                    expires_at TIMESTAMP,
                    allow_embed INTEGER DEFAULT 1,
                    allowed_domains TEXT DEFAULT '[]',
                    cta_enabled INTEGER DEFAULT 0,
                    cta_config TEXT DEFAULT '{}',
                    view_count INTEGER DEFAULT 0,
                    unique_viewer_count INTEGER DEFAULT 0,
                    total_watch_time_seconds INTEGER DEFAULT 0,
                    avg_watch_percent DECIMAL(5,2) DEFAULT 0,
                    folder_path VARCHAR(500) DEFAULT '/',
                    tags TEXT DEFAULT '[]',
                    published_at TIMESTAMP,
                    last_viewed_at TIMESTAMP,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """))

            session.execute(text("""
                CREATE TABLE IF NOT EXISTS video_viewer_sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    video_id INTEGER NOT NULL,
                    session_id VARCHAR(100) NOT NULL,
                    viewer_id VARCHAR(255),
                    lead_id INTEGER,
                    contact_id INTEGER,
                    user_id INTEGER,
                    viewer_name VARCHAR(255),
                    viewer_email VARCHAR(255),
                    viewer_company VARCHAR(255),
                    user_agent TEXT,
                    ip_address VARCHAR(45),
                    country VARCHAR(2),
                    city VARCHAR(100),
                    referrer TEXT,
                    watch_time_seconds INTEGER DEFAULT 0,
                    max_percent_watched DECIMAL(5,2) DEFAULT 0,
                    completed INTEGER DEFAULT 0,
                    watched_segments TEXT DEFAULT '[]',
                    cta_shown INTEGER DEFAULT 0,
                    cta_clicked INTEGER DEFAULT 0,
                    cta_clicked_at TIMESTAMP,
                    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_activity_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    ended_at TIMESTAMP
                )
            """))

            session.execute(text("""
                CREATE TABLE IF NOT EXISTS video_analytics_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    video_id INTEGER NOT NULL,
                    session_id INTEGER,
                    event_type VARCHAR(50) NOT NULL,
                    event_data TEXT DEFAULT '{}',
                    video_time_seconds DECIMAL(8,2),
                    percent_watched DECIMAL(5,2),
                    client_timestamp TIMESTAMP,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """))

            session.execute(text("""
                CREATE TABLE IF NOT EXISTS video_cta_overlays (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    organization_id INTEGER,
                    name VARCHAR(255) NOT NULL,
                    cta_type VARCHAR(50) NOT NULL,
                    show_at_percent DECIMAL(5,2),
                    show_at_seconds DECIMAL(8,2),
                    show_on_pause INTEGER DEFAULT 0,
                    show_on_end INTEGER DEFAULT 1,
                    headline TEXT,
                    description TEXT,
                    button_text VARCHAR(100),
                    button_url TEXT,
                    button_color VARCHAR(7),
                    form_fields TEXT DEFAULT '[]',
                    position VARCHAR(20) DEFAULT 'center',
                    animation VARCHAR(50) DEFAULT 'fade_in',
                    action_type VARCHAR(50),
                    action_config TEXT DEFAULT '{}',
                    is_active INTEGER DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """))

            session.execute(text("""
                CREATE TABLE IF NOT EXISTS video_asset_library (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    organization_id INTEGER,
                    uploaded_by INTEGER,
                    name VARCHAR(255) NOT NULL,
                    description TEXT,
                    asset_type VARCHAR(50) NOT NULL,
                    file_url TEXT NOT NULL,
                    thumbnail_url TEXT,
                    file_size_bytes INTEGER,
                    mime_type VARCHAR(100),
                    duration_seconds DECIMAL(8,2),
                    width INTEGER,
                    height INTEGER,
                    folder_path VARCHAR(500) DEFAULT '/',
                    tags TEXT DEFAULT '[]',
                    usage_count INTEGER DEFAULT 0,
                    last_used_at TIMESTAMP,
                    is_active INTEGER DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """))

            session.execute(text("""
                CREATE TABLE IF NOT EXISTS video_content_vault (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    organization_id INTEGER,
                    created_by INTEGER,
                    content_type VARCHAR(50) NOT NULL,
                    title VARCHAR(255) NOT NULL,
                    content TEXT NOT NULL,
                    category VARCHAR(100),
                    tags TEXT DEFAULT '[]',
                    usage_count INTEGER DEFAULT 0,
                    last_used_at TIMESTAMP,
                    is_approved INTEGER DEFAULT 0,
                    approved_by INTEGER,
                    approved_at TIMESTAMP,
                    is_active INTEGER DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """))

            # Indexes for SQLite
            session.execute(text("CREATE INDEX IF NOT EXISTS idx_video_projects_status ON video_projects(status)"))
            session.execute(text("CREATE INDEX IF NOT EXISTS idx_video_render_jobs_state ON video_render_jobs(state)"))
            session.execute(text("CREATE INDEX IF NOT EXISTS idx_video_library_share_token ON video_library(share_token)"))

            # Seed defaults
            session.execute(text("""
                INSERT OR IGNORE INTO video_brand_templates (
                    name, description, is_default, is_active
                ) VALUES (
                    'Default Mortgage Template',
                    'Clean, professional template for mortgage content',
                    1, 1
                )
            """))

            session.execute(text("""
                INSERT OR IGNORE INTO video_voice_profiles (
                    name, description, is_default, is_active,
                    voice_engine, language, speaking_rate
                ) VALUES (
                    'Default Professional Voice',
                    'Clear, professional American English voice',
                    1, 1,
                    'local_tts', 'en-US', 1.0
                )
            """))

        session.commit()
        logger.info("Video OS migration completed successfully")
        return {"success": True, "message": "Video OS tables created"}

    except Exception as e:
        session.rollback()
        logger.error(f"Video OS migration failed: {e}")
        raise
    finally:
        session.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_migration()
