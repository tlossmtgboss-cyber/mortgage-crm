"""
Carousel Builder Tables Migration

Creates tables for:
- Carousel projects
- Carousel slides
- Carousel themes
- Carousel templates
- Carousel exports
"""

import os
import sys
import logging

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text
from sqlalchemy.pool import NullPool

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./mortgage_crm.db")


def get_sql_commands():
    """Get SQL commands based on database type."""
    is_sqlite = "sqlite" in DATABASE_URL.lower()

    if is_sqlite:
        return get_sqlite_commands()
    else:
        return get_postgresql_commands()


def get_sqlite_commands():
    """SQLite-compatible SQL commands."""
    return [
        # 1. Carousel Themes (create first - referenced by projects and templates)
        """
        CREATE TABLE IF NOT EXISTS carousel_themes (
            id TEXT PRIMARY KEY,
            user_id INTEGER,
            organization_id INTEGER DEFAULT 1,
            name TEXT NOT NULL,
            description TEXT,
            preview_url TEXT,
            colors TEXT DEFAULT '{}',
            typography TEXT DEFAULT '{}',
            spacing TEXT DEFAULT '{}',
            decorations TEXT DEFAULT '{}',
            category TEXT,
            tags TEXT DEFAULT '[]',
            times_used INTEGER DEFAULT 0,
            is_system INTEGER DEFAULT 0,
            is_active INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """,

        # 2. Carousel Templates
        """
        CREATE TABLE IF NOT EXISTS carousel_templates (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT,
            preview_url TEXT,
            template_type TEXT DEFAULT 'custom',
            platform TEXT DEFAULT 'linkedin',
            aspect_ratio TEXT DEFAULT '1:1',
            slide_templates TEXT DEFAULT '[]',
            default_theme_id TEXT REFERENCES carousel_themes(id),
            required_data_bindings TEXT DEFAULT '[]',
            optional_data_bindings TEXT DEFAULT '[]',
            category TEXT,
            tags TEXT DEFAULT '[]',
            times_used INTEGER DEFAULT 0,
            is_active INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """,

        # 3. Carousel Projects
        """
        CREATE TABLE IF NOT EXISTS carousel_projects (
            id TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            organization_id INTEGER DEFAULT 1,
            name TEXT NOT NULL,
            description TEXT,
            project_type TEXT DEFAULT 'custom',
            platform TEXT DEFAULT 'linkedin',
            aspect_ratio TEXT DEFAULT '1:1',
            width INTEGER DEFAULT 1080,
            height INTEGER DEFAULT 1080,
            loan_id INTEGER,
            lead_id TEXT,
            active_loan_id TEXT,
            theme_id TEXT REFERENCES carousel_themes(id),
            custom_branding TEXT DEFAULT '{}',
            status TEXT DEFAULT 'draft',
            ai_prompt TEXT,
            ai_generated INTEGER DEFAULT 0,
            generation_tokens_used INTEGER DEFAULT 0,
            last_exported_at TIMESTAMP,
            export_format TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """,

        # 4. Carousel Slides
        """
        CREATE TABLE IF NOT EXISTS carousel_slides (
            id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL REFERENCES carousel_projects(id) ON DELETE CASCADE,
            "order" INTEGER DEFAULT 0,
            title TEXT,
            subtitle TEXT,
            body_text TEXT,
            background_type TEXT DEFAULT 'solid',
            background_color TEXT DEFAULT '#ffffff',
            background_gradient TEXT,
            background_image_url TEXT,
            background_image_key TEXT,
            layout_template TEXT DEFAULT 'centered',
            elements TEXT DEFAULT '[]',
            custom_styles TEXT DEFAULT '{}',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """,

        # 5. Carousel Exports
        """
        CREATE TABLE IF NOT EXISTS carousel_exports (
            id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL REFERENCES carousel_projects(id) ON DELETE CASCADE,
            user_id INTEGER NOT NULL,
            export_format TEXT DEFAULT 'png',
            quality INTEGER DEFAULT 90,
            scale INTEGER DEFAULT 2,
            file_keys TEXT DEFAULT '[]',
            zip_file_key TEXT,
            status TEXT DEFAULT 'pending',
            error_message TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            completed_at TIMESTAMP
        )
        """,

        # Indexes
        "CREATE INDEX IF NOT EXISTS idx_carousel_projects_user ON carousel_projects(user_id)",
        "CREATE INDEX IF NOT EXISTS idx_carousel_projects_loan ON carousel_projects(loan_id)",
        "CREATE INDEX IF NOT EXISTS idx_carousel_projects_lead ON carousel_projects(lead_id)",
        "CREATE INDEX IF NOT EXISTS idx_carousel_projects_active_loan ON carousel_projects(active_loan_id)",
        "CREATE INDEX IF NOT EXISTS idx_carousel_slides_project ON carousel_slides(project_id)",
        "CREATE INDEX IF NOT EXISTS idx_carousel_exports_project ON carousel_exports(project_id)",
    ]


def get_postgresql_commands():
    """PostgreSQL-compatible SQL commands."""
    return [
        # Create enum types
        """
        DO $$ BEGIN
            CREATE TYPE carousel_project_type AS ENUM ('just_closed', 'marketing', 'rate_update', 'educational', 'custom');
        EXCEPTION
            WHEN duplicate_object THEN NULL;
        END $$
        """,
        """
        DO $$ BEGIN
            CREATE TYPE carousel_platform AS ENUM ('linkedin', 'instagram', 'tiktok', 'facebook');
        EXCEPTION
            WHEN duplicate_object THEN NULL;
        END $$
        """,
        """
        DO $$ BEGIN
            CREATE TYPE carousel_aspect_ratio AS ENUM ('1:1', '4:5', '9:16');
        EXCEPTION
            WHEN duplicate_object THEN NULL;
        END $$
        """,
        """
        DO $$ BEGIN
            CREATE TYPE carousel_status AS ENUM ('draft', 'generating', 'ready', 'exported');
        EXCEPTION
            WHEN duplicate_object THEN NULL;
        END $$
        """,
        """
        DO $$ BEGIN
            CREATE TYPE slide_background_type AS ENUM ('solid', 'gradient', 'image');
        EXCEPTION
            WHEN duplicate_object THEN NULL;
        END $$
        """,
        """
        DO $$ BEGIN
            CREATE TYPE slide_layout_template AS ENUM ('centered', 'left', 'right', 'split', 'full_image');
        EXCEPTION
            WHEN duplicate_object THEN NULL;
        END $$
        """,
        """
        DO $$ BEGIN
            CREATE TYPE export_status AS ENUM ('pending', 'processing', 'completed', 'failed');
        EXCEPTION
            WHEN duplicate_object THEN NULL;
        END $$
        """,

        # 1. Carousel Themes
        """
        CREATE TABLE IF NOT EXISTS carousel_themes (
            id VARCHAR(50) PRIMARY KEY,
            user_id INTEGER REFERENCES users(id),
            organization_id INTEGER DEFAULT 1,
            name VARCHAR(255) NOT NULL,
            description TEXT,
            preview_url TEXT,
            colors JSONB DEFAULT '{}',
            typography JSONB DEFAULT '{}',
            spacing JSONB DEFAULT '{}',
            decorations JSONB DEFAULT '{}',
            category VARCHAR(100),
            tags JSONB DEFAULT '[]',
            times_used INTEGER DEFAULT 0,
            is_system BOOLEAN DEFAULT FALSE,
            is_active BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """,

        # 2. Carousel Templates
        """
        CREATE TABLE IF NOT EXISTS carousel_templates (
            id VARCHAR(50) PRIMARY KEY,
            name VARCHAR(255) NOT NULL,
            description TEXT,
            preview_url TEXT,
            template_type carousel_project_type DEFAULT 'custom',
            platform carousel_platform DEFAULT 'linkedin',
            aspect_ratio carousel_aspect_ratio DEFAULT '1:1',
            slide_templates JSONB DEFAULT '[]',
            default_theme_id VARCHAR(50) REFERENCES carousel_themes(id),
            required_data_bindings JSONB DEFAULT '[]',
            optional_data_bindings JSONB DEFAULT '[]',
            category VARCHAR(100),
            tags JSONB DEFAULT '[]',
            times_used INTEGER DEFAULT 0,
            is_active BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """,

        # 3. Carousel Projects
        """
        CREATE TABLE IF NOT EXISTS carousel_projects (
            id VARCHAR(50) PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id),
            organization_id INTEGER DEFAULT 1,
            name VARCHAR(255) NOT NULL,
            description TEXT,
            project_type carousel_project_type DEFAULT 'custom',
            platform carousel_platform DEFAULT 'linkedin',
            aspect_ratio carousel_aspect_ratio DEFAULT '1:1',
            width INTEGER DEFAULT 1080,
            height INTEGER DEFAULT 1080,
            loan_id INTEGER REFERENCES loans(id),
            lead_id VARCHAR(50),
            active_loan_id VARCHAR(50),
            theme_id VARCHAR(50) REFERENCES carousel_themes(id),
            custom_branding JSONB DEFAULT '{}',
            status carousel_status DEFAULT 'draft',
            ai_prompt TEXT,
            ai_generated BOOLEAN DEFAULT FALSE,
            generation_tokens_used INTEGER DEFAULT 0,
            last_exported_at TIMESTAMP,
            export_format VARCHAR(20),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """,

        # 4. Carousel Slides
        """
        CREATE TABLE IF NOT EXISTS carousel_slides (
            id VARCHAR(50) PRIMARY KEY,
            project_id VARCHAR(50) NOT NULL REFERENCES carousel_projects(id) ON DELETE CASCADE,
            "order" INTEGER DEFAULT 0,
            title VARCHAR(500),
            subtitle VARCHAR(500),
            body_text TEXT,
            background_type slide_background_type DEFAULT 'solid',
            background_color VARCHAR(20) DEFAULT '#ffffff',
            background_gradient JSONB,
            background_image_url TEXT,
            background_image_key VARCHAR(500),
            layout_template slide_layout_template DEFAULT 'centered',
            elements JSONB DEFAULT '[]',
            custom_styles JSONB DEFAULT '{}',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """,

        # 5. Carousel Exports
        """
        CREATE TABLE IF NOT EXISTS carousel_exports (
            id VARCHAR(50) PRIMARY KEY,
            project_id VARCHAR(50) NOT NULL REFERENCES carousel_projects(id) ON DELETE CASCADE,
            user_id INTEGER NOT NULL REFERENCES users(id),
            export_format VARCHAR(20) DEFAULT 'png',
            quality INTEGER DEFAULT 90,
            scale INTEGER DEFAULT 2,
            file_keys JSONB DEFAULT '[]',
            zip_file_key VARCHAR(500),
            status export_status DEFAULT 'pending',
            error_message TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            completed_at TIMESTAMP
        )
        """,

        # Indexes
        "CREATE INDEX IF NOT EXISTS idx_carousel_projects_user ON carousel_projects(user_id)",
        "CREATE INDEX IF NOT EXISTS idx_carousel_projects_org ON carousel_projects(organization_id)",
        "CREATE INDEX IF NOT EXISTS idx_carousel_projects_loan ON carousel_projects(loan_id)",
        "CREATE INDEX IF NOT EXISTS idx_carousel_projects_lead ON carousel_projects(lead_id)",
        "CREATE INDEX IF NOT EXISTS idx_carousel_projects_active_loan ON carousel_projects(active_loan_id)",
        "CREATE INDEX IF NOT EXISTS idx_carousel_slides_project ON carousel_slides(project_id)",
        "CREATE INDEX IF NOT EXISTS idx_carousel_exports_project ON carousel_exports(project_id)",
        "CREATE INDEX IF NOT EXISTS idx_carousel_themes_user ON carousel_themes(user_id)",
    ]


def seed_default_themes():
    """Seed default carousel themes."""
    return [
        # Professional Teal (Brand default)
        """
        INSERT INTO carousel_themes (id, name, description, colors, typography, spacing, decorations, category, tags, is_system, is_active)
        SELECT 'theme_teal', 'Professional Teal', 'Clean professional theme with teal accents',
            '{"primary": "#217F8D", "secondary": "#c9a227", "accent": "#10b981", "background": "#ffffff", "text": "#1a1a1a", "muted": "#6b7280"}',
            '{"headingFont": "Inter", "bodyFont": "Inter", "titleSize": 48, "subtitleSize": 24, "bodySize": 18}',
            '{"padding": 40, "elementGap": 16}',
            '{"cornerRadius": 0, "showBorder": false, "shadowEnabled": false}',
            'professional', '["mortgage", "professional", "clean"]', 1, 1
        WHERE NOT EXISTS (SELECT 1 FROM carousel_themes WHERE id = 'theme_teal')
        """,

        # Celebration Gold
        """
        INSERT INTO carousel_themes (id, name, description, colors, typography, spacing, decorations, category, tags, is_system, is_active)
        SELECT 'theme_gold', 'Celebration Gold', 'Elegant gold theme for celebrations',
            '{"primary": "#c9a227", "secondary": "#217F8D", "accent": "#f59e0b", "background": "#fffbeb", "text": "#1a1a1a", "muted": "#78716c"}',
            '{"headingFont": "Playfair Display", "bodyFont": "Inter", "titleSize": 52, "subtitleSize": 26, "bodySize": 18}',
            '{"padding": 48, "elementGap": 20}',
            '{"cornerRadius": 8, "showBorder": true, "borderColor": "#c9a227", "shadowEnabled": true}',
            'celebration', '["celebration", "elegant", "just_closed"]', 1, 1
        WHERE NOT EXISTS (SELECT 1 FROM carousel_themes WHERE id = 'theme_gold')
        """,

        # Modern Dark
        """
        INSERT INTO carousel_themes (id, name, description, colors, typography, spacing, decorations, category, tags, is_system, is_active)
        SELECT 'theme_dark', 'Modern Dark', 'Sleek dark theme for modern content',
            '{"primary": "#3b82f6", "secondary": "#8b5cf6", "accent": "#ec4899", "background": "#0f172a", "text": "#f8fafc", "muted": "#94a3b8"}',
            '{"headingFont": "Poppins", "bodyFont": "Inter", "titleSize": 44, "subtitleSize": 22, "bodySize": 16}',
            '{"padding": 36, "elementGap": 14}',
            '{"cornerRadius": 12, "showBorder": false, "shadowEnabled": false}',
            'modern', '["dark", "modern", "tech"]', 1, 1
        WHERE NOT EXISTS (SELECT 1 FROM carousel_themes WHERE id = 'theme_dark')
        """,

        # Warm Gradient
        """
        INSERT INTO carousel_themes (id, name, description, colors, typography, spacing, decorations, category, tags, is_system, is_active)
        SELECT 'theme_warm', 'Warm Gradient', 'Inviting warm gradient theme',
            '{"primary": "#f97316", "secondary": "#eab308", "accent": "#ef4444", "background": "#fff7ed", "text": "#1c1917", "muted": "#78716c"}',
            '{"headingFont": "Nunito", "bodyFont": "Nunito", "titleSize": 46, "subtitleSize": 24, "bodySize": 17}',
            '{"padding": 42, "elementGap": 18}',
            '{"cornerRadius": 16, "showBorder": false, "shadowEnabled": true}',
            'warm', '["warm", "friendly", "approachable"]', 1, 1
        WHERE NOT EXISTS (SELECT 1 FROM carousel_themes WHERE id = 'theme_warm')
        """,

        # Minimal White
        """
        INSERT INTO carousel_themes (id, name, description, colors, typography, spacing, decorations, category, tags, is_system, is_active)
        SELECT 'theme_minimal', 'Minimal White', 'Clean minimal white theme',
            '{"primary": "#1a1a1a", "secondary": "#525252", "accent": "#217F8D", "background": "#ffffff", "text": "#1a1a1a", "muted": "#a3a3a3"}',
            '{"headingFont": "Inter", "bodyFont": "Inter", "titleSize": 42, "subtitleSize": 20, "bodySize": 16}',
            '{"padding": 50, "elementGap": 12}',
            '{"cornerRadius": 0, "showBorder": true, "borderColor": "#e5e5e5", "shadowEnabled": false}',
            'minimal', '["minimal", "clean", "white"]', 1, 1
        WHERE NOT EXISTS (SELECT 1 FROM carousel_themes WHERE id = 'theme_minimal')
        """,
    ]


def seed_default_templates():
    """Seed default carousel templates."""
    return [
        # Just Closed Template
        """
        INSERT INTO carousel_templates (id, name, description, template_type, platform, aspect_ratio, slide_templates, default_theme_id, required_data_bindings, category, tags, is_active)
        SELECT 'tmpl_just_closed', 'Just Closed Celebration', 'Celebrate a successful closing with your client', 'just_closed', 'linkedin', '1:1',
            '[
                {"title": "JUST CLOSED!", "subtitle": "Another Dream Home Funded", "layout_template": "centered", "background_type": "gradient"},
                {"title": "{{property.city}}, {{property.state}}", "subtitle": "{{loan.amount}}", "layout_template": "centered", "background_type": "solid"},
                {"title": "Congratulations!", "subtitle": "{{borrower.first_name}}", "body_text": "Welcome to your new home!", "layout_template": "centered", "background_type": "gradient"},
                {"title": "Ready for Yours?", "subtitle": "Let''s Make It Happen", "body_text": "Contact me today!", "layout_template": "centered", "background_type": "solid"}
            ]',
            'theme_gold',
            '["property.city", "property.state"]',
            'celebration', '["just_closed", "celebration", "success"]', 1
        WHERE NOT EXISTS (SELECT 1 FROM carousel_templates WHERE id = 'tmpl_just_closed')
        """,

        # Rate Update Template
        """
        INSERT INTO carousel_templates (id, name, description, template_type, platform, aspect_ratio, slide_templates, default_theme_id, required_data_bindings, category, tags, is_active)
        SELECT 'tmpl_rate_update', 'Rate Update Alert', 'Share mortgage rate updates with your audience', 'rate_update', 'linkedin', '1:1',
            '[
                {"title": "RATE UPDATE", "subtitle": "What You Need to Know", "layout_template": "centered", "background_type": "gradient"},
                {"title": "Rates Are Moving", "subtitle": "Here''s What It Means", "body_text": "Whether you''re buying or refinancing, now is the time to pay attention.", "layout_template": "left", "background_type": "solid"},
                {"title": "For Buyers", "subtitle": "Lock In Your Rate", "body_text": "Don''t wait - secure your rate before the next move.", "layout_template": "centered", "background_type": "solid"},
                {"title": "Get Your Quote", "subtitle": "Free, No Obligation", "body_text": "Contact me for a personalized rate quote today!", "layout_template": "centered", "background_type": "gradient"}
            ]',
            'theme_teal',
            '[]',
            'market', '["rates", "market", "update"]', 1
        WHERE NOT EXISTS (SELECT 1 FROM carousel_templates WHERE id = 'tmpl_rate_update')
        """,

        # Educational - First Time Buyer
        """
        INSERT INTO carousel_templates (id, name, description, template_type, platform, aspect_ratio, slide_templates, default_theme_id, required_data_bindings, category, tags, is_active)
        SELECT 'tmpl_ftb_tips', 'First Time Buyer Tips', 'Educational content for first time homebuyers', 'educational', 'instagram', '4:5',
            '[
                {"title": "First Time Buyer?", "subtitle": "5 Things You Need to Know", "layout_template": "centered", "background_type": "gradient"},
                {"title": "1. Get Pre-Approved", "subtitle": "Know Your Budget", "body_text": "Pre-approval shows sellers you''re serious.", "layout_template": "left", "background_type": "solid"},
                {"title": "2. Check Your Credit", "subtitle": "Higher Score = Better Rate", "body_text": "Even 20 points can save thousands.", "layout_template": "left", "background_type": "solid"},
                {"title": "3. Save for More Than Down Payment", "subtitle": "Closing Costs Matter", "body_text": "Plan for 2-5% in closing costs.", "layout_template": "left", "background_type": "solid"},
                {"title": "4. Research Programs", "subtitle": "First-Time Buyer Benefits", "body_text": "FHA, VA, down payment assistance - options exist!", "layout_template": "left", "background_type": "solid"},
                {"title": "Questions?", "subtitle": "I''m Here to Help", "body_text": "DM me or comment below!", "layout_template": "centered", "background_type": "gradient"}
            ]',
            'theme_warm',
            '[]',
            'educational', '["education", "first_time_buyer", "tips"]', 1
        WHERE NOT EXISTS (SELECT 1 FROM carousel_templates WHERE id = 'tmpl_ftb_tips')
        """,

        # Marketing - Why Work With Me
        """
        INSERT INTO carousel_templates (id, name, description, template_type, platform, aspect_ratio, slide_templates, default_theme_id, required_data_bindings, category, tags, is_active)
        SELECT 'tmpl_why_me', 'Why Work With Me', 'Showcase your value proposition', 'marketing', 'linkedin', '1:1',
            '[
                {"title": "Why Work With Me?", "subtitle": "Your Trusted Mortgage Partner", "layout_template": "centered", "background_type": "gradient"},
                {"title": "Local Expertise", "subtitle": "I Know This Market", "body_text": "Years of experience in your area.", "layout_template": "left", "background_type": "solid"},
                {"title": "Fast Communication", "subtitle": "Always Available", "body_text": "You''ll never wonder what''s happening with your loan.", "layout_template": "left", "background_type": "solid"},
                {"title": "Competitive Rates", "subtitle": "Multiple Lender Options", "body_text": "I shop to find you the best deal.", "layout_template": "left", "background_type": "solid"},
                {"title": "Let''s Connect", "subtitle": "Your Dream Home Awaits", "body_text": "Schedule a free consultation today!", "layout_template": "centered", "background_type": "gradient"}
            ]',
            'theme_teal',
            '[]',
            'marketing', '["marketing", "value_prop", "personal_brand"]', 1
        WHERE NOT EXISTS (SELECT 1 FROM carousel_templates WHERE id = 'tmpl_why_me')
        """,
    ]


def run_migration():
    """Run the carousel builder migration."""
    logger.info(f"Running Carousel Builder migration on: {DATABASE_URL[:50]}...")

    engine = create_engine(DATABASE_URL, poolclass=NullPool)

    try:
        with engine.connect() as conn:
            # Create tables
            commands = get_sql_commands()
            for i, cmd in enumerate(commands, 1):
                try:
                    conn.execute(text(cmd))
                    conn.commit()
                    logger.info(f"  [{i}/{len(commands)}] Executed successfully")
                except Exception as e:
                    if "already exists" in str(e).lower() or "duplicate" in str(e).lower():
                        logger.info(f"  [{i}/{len(commands)}] Already exists, skipping")
                    else:
                        logger.warning(f"  [{i}/{len(commands)}] Warning: {e}")

            # Seed default themes
            logger.info("Seeding default themes...")
            theme_commands = seed_default_themes()
            for cmd in theme_commands:
                try:
                    conn.execute(text(cmd))
                    conn.commit()
                except Exception as e:
                    logger.debug(f"Theme seed: {e}")

            # Seed default templates
            logger.info("Seeding default templates...")
            template_commands = seed_default_templates()
            for cmd in template_commands:
                try:
                    conn.execute(text(cmd))
                    conn.commit()
                except Exception as e:
                    logger.debug(f"Template seed: {e}")

            # Count results
            theme_count = conn.execute(text("SELECT COUNT(*) FROM carousel_themes")).scalar()
            template_count = conn.execute(text("SELECT COUNT(*) FROM carousel_templates")).scalar()

            logger.info(f"Migration complete!")
            logger.info(f"  - carousel_themes: {theme_count} themes")
            logger.info(f"  - carousel_templates: {template_count} templates")
            logger.info(f"  - carousel_projects: ready")
            logger.info(f"  - carousel_slides: ready")
            logger.info(f"  - carousel_exports: ready")

    except Exception as e:
        logger.error(f"Migration failed: {e}")
        raise


if __name__ == "__main__":
    run_migration()
