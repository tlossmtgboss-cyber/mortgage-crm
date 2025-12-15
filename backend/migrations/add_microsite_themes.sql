-- =============================================================================
-- MICROSITE THEME MARKETPLACE - DATABASE MIGRATION
-- =============================================================================
-- This migration creates the database schema for the microsite theme marketplace
-- system. It includes:
-- - Theme registry for storing available themes
-- - Microsite configuration linking users to themes
-- - Profile customization for theme-specific content
-- =============================================================================


-- =============================================================================
-- SECTION 1: ENUM TYPES
-- =============================================================================

-- Theme category enum
DO $$ BEGIN
    CREATE TYPE microsite_theme_category AS ENUM (
        'professional',     -- Clean, corporate designs
        'modern',          -- Contemporary, trendy designs
        'classic',         -- Traditional, timeless designs
        'minimal',         -- Simple, focused designs
        'bold',            -- High-impact, standout designs
        'elegant',         -- Sophisticated, refined designs
        'custom'           -- User-uploaded/custom themes
    );
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

-- Theme status enum
DO $$ BEGIN
    CREATE TYPE microsite_theme_status AS ENUM (
        'active',          -- Available for selection
        'draft',           -- In development, not visible
        'deprecated',      -- Still works but hidden from new selection
        'archived'         -- Completely disabled
    );
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;


-- =============================================================================
-- SECTION 2: MICROSITE THEMES TABLE
-- =============================================================================
-- Registry of all available microsite themes

CREATE TABLE IF NOT EXISTS microsite_themes (
    id SERIAL PRIMARY KEY,

    -- Theme identification
    slug VARCHAR(100) NOT NULL UNIQUE,
    name VARCHAR(200) NOT NULL,
    description TEXT,

    -- Theme metadata
    category microsite_theme_category NOT NULL DEFAULT 'professional',
    status microsite_theme_status NOT NULL DEFAULT 'active',

    -- Preview assets
    thumbnail_url VARCHAR(500),
    preview_url VARCHAR(500),
    preview_images JSONB DEFAULT '[]',  -- Array of preview image URLs

    -- Theme configuration
    component_name VARCHAR(100) NOT NULL,  -- React component name to render
    default_config JSONB DEFAULT '{}',  -- Default theme configuration

    -- Features & capabilities
    features JSONB DEFAULT '[]',  -- Array of feature strings like ["contact_form", "testimonials"]
    supports_custom_colors BOOLEAN NOT NULL DEFAULT TRUE,
    supports_custom_fonts BOOLEAN NOT NULL DEFAULT FALSE,

    -- Layout options
    layout_options JSONB DEFAULT '{}',  -- Available layout configurations
    -- Example: {"headerStyle": ["centered", "left", "split"], "heroStyle": ["image", "gradient", "video"]}

    -- Pricing (for future marketplace)
    is_premium BOOLEAN NOT NULL DEFAULT FALSE,
    price_cents INTEGER DEFAULT 0,

    -- Ordering & display
    display_order INTEGER NOT NULL DEFAULT 0,
    is_featured BOOLEAN NOT NULL DEFAULT FALSE,

    -- Multi-tenant support
    organization_id INTEGER REFERENCES organizations(id) ON DELETE CASCADE,  -- NULL = global theme
    created_by_id INTEGER REFERENCES users(id) ON DELETE SET NULL,

    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Insert default themes
INSERT INTO microsite_themes (slug, name, description, category, component_name, features, display_order, is_featured)
VALUES
    ('bold-impact', 'Bold Impact', 'A bold, modern theme with strong call-to-actions and lead capture focus.', 'bold', 'BoldImpact', '["hero_image", "contact_form", "rate_calculator", "testimonials", "about_section"]', 1, TRUE),
    ('professional-clean', 'Professional Clean', 'A clean, professional theme perfect for established loan officers.', 'professional', 'ProfessionalClean', '["hero_image", "contact_form", "credentials", "about_section"]', 2, FALSE),
    ('modern-gradient', 'Modern Gradient', 'A contemporary theme with gradient backgrounds and smooth animations.', 'modern', 'ModernGradient', '["hero_gradient", "contact_form", "testimonials", "about_section"]', 3, FALSE),
    ('minimal-focus', 'Minimal Focus', 'A minimalist theme that puts the focus on your message and lead capture.', 'minimal', 'MinimalFocus', '["contact_form", "about_section"]', 4, FALSE)
ON CONFLICT (slug) DO NOTHING;


-- =============================================================================
-- SECTION 3: MICROSITES TABLE
-- =============================================================================
-- Links users to their selected theme and configuration

CREATE TABLE IF NOT EXISTS microsites (
    id SERIAL PRIMARY KEY,

    -- User linkage
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    organization_id INTEGER REFERENCES organizations(id) ON DELETE CASCADE,

    -- Theme selection
    theme_id INTEGER REFERENCES microsite_themes(id) ON DELETE SET NULL,

    -- Custom configuration (overrides theme defaults)
    theme_config JSONB DEFAULT '{}',
    -- Example: {
    --   "primaryColor": "#2563eb",
    --   "headerStyle": "centered",
    --   "heroStyle": "image",
    --   "showTestimonials": true
    -- }

    -- SEO & metadata
    meta_title VARCHAR(200),
    meta_description VARCHAR(500),
    og_image_url VARCHAR(500),

    -- Custom domain support (future)
    custom_domain VARCHAR(200),
    custom_domain_verified BOOLEAN DEFAULT FALSE,

    -- Publishing status
    is_published BOOLEAN NOT NULL DEFAULT FALSE,
    published_at TIMESTAMP WITH TIME ZONE,

    -- Analytics tracking
    ga_tracking_id VARCHAR(50),
    fb_pixel_id VARCHAR(50),

    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,

    -- Unique constraint: one microsite per user
    CONSTRAINT uq_microsites_user UNIQUE (user_id)
);


-- =============================================================================
-- SECTION 4: MICROSITE PROFILES TABLE
-- =============================================================================
-- Extended profile data for microsites (separate from base user profile)

CREATE TABLE IF NOT EXISTS microsite_profiles (
    id SERIAL PRIMARY KEY,

    -- Link to microsite
    microsite_id INTEGER NOT NULL REFERENCES microsites(id) ON DELETE CASCADE,

    -- Extended profile information
    headline VARCHAR(200),  -- "Your Trusted Mortgage Expert"
    tagline VARCHAR(300),   -- "Making homeownership dreams a reality"
    bio_extended TEXT,      -- Longer bio for microsite

    -- Hero section
    hero_image_url VARCHAR(500),
    hero_video_url VARCHAR(500),
    hero_background_color VARCHAR(20),

    -- Professional credentials
    years_experience INTEGER,
    total_loans_funded INTEGER,
    total_volume_funded DECIMAL(15, 2),  -- In dollars
    specialties JSONB DEFAULT '[]',  -- ["First-time buyers", "VA loans", "Jumbo loans"]
    certifications JSONB DEFAULT '[]',  -- ["CMPS", "FHA Direct Endorsed"]

    -- Social proof
    testimonials JSONB DEFAULT '[]',
    -- Example: [{"name": "John D.", "text": "Great experience!", "rating": 5, "date": "2024-01-15"}]

    -- Social links
    social_links JSONB DEFAULT '{}',
    -- Example: {"linkedin": "url", "facebook": "url", "instagram": "url"}

    -- Contact preferences
    calendly_url VARCHAR(500),
    contact_form_enabled BOOLEAN DEFAULT TRUE,
    show_phone BOOLEAN DEFAULT TRUE,
    show_email BOOLEAN DEFAULT TRUE,

    -- Call to action
    cta_text VARCHAR(100) DEFAULT 'Get Started Today',
    cta_secondary_text VARCHAR(100) DEFAULT 'Check Rates',

    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,

    -- Unique constraint: one profile per microsite
    CONSTRAINT uq_microsite_profiles_microsite UNIQUE (microsite_id)
);


-- =============================================================================
-- SECTION 5: PERFORMANCE INDEXES
-- =============================================================================

-- Theme indexes
CREATE INDEX IF NOT EXISTS ix_microsite_themes_category ON microsite_themes(category);
CREATE INDEX IF NOT EXISTS ix_microsite_themes_status ON microsite_themes(status);
CREATE INDEX IF NOT EXISTS ix_microsite_themes_featured ON microsite_themes(is_featured, display_order);
CREATE INDEX IF NOT EXISTS ix_microsite_themes_org ON microsite_themes(organization_id) WHERE organization_id IS NOT NULL;

-- Microsite indexes
CREATE INDEX IF NOT EXISTS ix_microsites_user ON microsites(user_id);
CREATE INDEX IF NOT EXISTS ix_microsites_theme ON microsites(theme_id);
CREATE INDEX IF NOT EXISTS ix_microsites_published ON microsites(is_published);
CREATE INDEX IF NOT EXISTS ix_microsites_custom_domain ON microsites(custom_domain) WHERE custom_domain IS NOT NULL;

-- Profile indexes
CREATE INDEX IF NOT EXISTS ix_microsite_profiles_microsite ON microsite_profiles(microsite_id);


-- =============================================================================
-- SECTION 6: UPDATE TRIGGERS
-- =============================================================================

-- Trigger for microsite_themes updated_at
DO $$
BEGIN
    DROP TRIGGER IF EXISTS update_microsite_themes_updated_at ON microsite_themes;
    CREATE TRIGGER update_microsite_themes_updated_at
        BEFORE UPDATE ON microsite_themes
        FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
EXCEPTION
    WHEN undefined_function THEN
        -- Create the function if it doesn't exist
        CREATE OR REPLACE FUNCTION update_updated_at_column()
        RETURNS TRIGGER AS $func$
        BEGIN
            NEW.updated_at = CURRENT_TIMESTAMP;
            RETURN NEW;
        END;
        $func$ language 'plpgsql';

        CREATE TRIGGER update_microsite_themes_updated_at
            BEFORE UPDATE ON microsite_themes
            FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
END $$;

-- Trigger for microsites updated_at
DO $$
BEGIN
    DROP TRIGGER IF EXISTS update_microsites_updated_at ON microsites;
    CREATE TRIGGER update_microsites_updated_at
        BEFORE UPDATE ON microsites
        FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
END $$;

-- Trigger for microsite_profiles updated_at
DO $$
BEGIN
    DROP TRIGGER IF EXISTS update_microsite_profiles_updated_at ON microsite_profiles;
    CREATE TRIGGER update_microsite_profiles_updated_at
        BEFORE UPDATE ON microsite_profiles
        FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
END $$;


-- =============================================================================
-- SECTION 7: ROW-LEVEL SECURITY (RLS)
-- =============================================================================

-- Enable RLS on tables
ALTER TABLE microsites ENABLE ROW LEVEL SECURITY;
ALTER TABLE microsite_profiles ENABLE ROW LEVEL SECURITY;

-- Note: microsite_themes is read-mostly and controlled by organization_id field

-- RLS Policy: Users can only manage their own microsites
DO $$
BEGIN
    DROP POLICY IF EXISTS microsites_user_isolation ON microsites;
    CREATE POLICY microsites_user_isolation ON microsites
        FOR ALL
        USING (user_id = current_setting('app.current_user_id')::INTEGER);
EXCEPTION
    WHEN undefined_object THEN NULL;
END $$;

-- RLS Policy: Users can only manage profiles for their microsites
DO $$
BEGIN
    DROP POLICY IF EXISTS microsite_profiles_user_isolation ON microsite_profiles;
    CREATE POLICY microsite_profiles_user_isolation ON microsite_profiles
        FOR ALL
        USING (
            microsite_id IN (
                SELECT id FROM microsites WHERE user_id = current_setting('app.current_user_id')::INTEGER
            )
        );
EXCEPTION
    WHEN undefined_object THEN NULL;
END $$;


-- =============================================================================
-- MIGRATION COMPLETE
-- =============================================================================
