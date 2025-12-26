-- Migration: Add Microsite Platform Tables
-- Creates infrastructure for multi-tenant microsite system

-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- 1. TEMPLATE PACKS - Reusable website templates
CREATE TABLE IF NOT EXISTS microsite_template_packs (
    id SERIAL PRIMARY KEY,
    organization_id INTEGER REFERENCES organizations(id) ON DELETE CASCADE,

    name VARCHAR(255) NOT NULL,
    description TEXT,
    slug VARCHAR(100) NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,
    status VARCHAR(50) DEFAULT 'active',

    template_json JSONB NOT NULL,
    schema_json JSONB NOT NULL,
    defaults_json JSONB NOT NULL,

    thumbnail_url TEXT,
    category VARCHAR(100),
    tags TEXT[],

    baseline_conversion_rate DECIMAL(5,4),

    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    created_by INTEGER REFERENCES users(id),

    CONSTRAINT unique_template_version UNIQUE(slug, version)
);

CREATE INDEX IF NOT EXISTS idx_template_packs_org_status
ON microsite_template_packs(organization_id, status);

CREATE INDEX IF NOT EXISTS idx_template_packs_slug_version
ON microsite_template_packs(slug, version);

-- 2. MICROSITES - User-specific microsite instances
CREATE TABLE IF NOT EXISTS microsites (
    id SERIAL PRIMARY KEY,
    organization_id INTEGER NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,

    template_pack_id INTEGER NOT NULL REFERENCES microsite_template_packs(id),
    template_version INTEGER NOT NULL,

    slug VARCHAR(100) NOT NULL UNIQUE,
    status VARCHAR(50) DEFAULT 'draft',

    content_json JSONB NOT NULL DEFAULT '{}',
    branding_json JSONB DEFAULT '{}',
    compliance_json JSONB DEFAULT '{}',

    seo_title VARCHAR(255),
    seo_description TEXT,
    seo_image_url TEXT,
    seo_keywords TEXT[],

    custom_domain VARCHAR(255),
    custom_domain_verified BOOLEAN DEFAULT FALSE,

    published_at TIMESTAMP WITH TIME ZONE,
    last_published_at TIMESTAMP WITH TIME ZONE,

    view_count INTEGER DEFAULT 0,
    lead_count INTEGER DEFAULT 0,
    conversion_rate DECIMAL(5,4),

    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT valid_microsite_status CHECK (status IN ('draft', 'published', 'archived'))
);

CREATE INDEX IF NOT EXISTS idx_microsites_user ON microsites(user_id);
CREATE INDEX IF NOT EXISTS idx_microsites_org_status ON microsites(organization_id, status);
CREATE INDEX IF NOT EXISTS idx_microsites_slug ON microsites(slug);
CREATE INDEX IF NOT EXISTS idx_microsites_published ON microsites(status, published_at) WHERE status = 'published';

-- 3. MICROSITE ASSETS - Uploaded images and media
CREATE TABLE IF NOT EXISTS microsite_assets (
    id SERIAL PRIMARY KEY,
    microsite_id INTEGER NOT NULL REFERENCES microsites(id) ON DELETE CASCADE,

    asset_type VARCHAR(50) NOT NULL,
    file_name VARCHAR(255) NOT NULL,
    file_path TEXT NOT NULL,
    file_size INTEGER,
    mime_type VARCHAR(100),

    width INTEGER,
    height INTEGER,
    alt_text TEXT,

    field_name VARCHAR(100),

    uploaded_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_microsite_assets_site ON microsite_assets(microsite_id);
CREATE INDEX IF NOT EXISTS idx_microsite_assets_type ON microsite_assets(microsite_id, asset_type);

-- 4. MICROSITE PUBLISH HISTORY - Audit trail and rollback
CREATE TABLE IF NOT EXISTS microsite_publish_history (
    id SERIAL PRIMARY KEY,
    microsite_id INTEGER NOT NULL REFERENCES microsites(id) ON DELETE CASCADE,

    content_snapshot JSONB NOT NULL,
    template_version INTEGER NOT NULL,

    action VARCHAR(50) NOT NULL,
    published_by INTEGER REFERENCES users(id),
    published_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,

    cdn_invalidated BOOLEAN DEFAULT FALSE,
    deploy_status VARCHAR(50) DEFAULT 'pending',
    deploy_error TEXT
);

CREATE INDEX IF NOT EXISTS idx_publish_history_site ON microsite_publish_history(microsite_id, published_at DESC);

-- 5. MICROSITE ANALYTICS EVENTS - Behavior and conversion tracking
CREATE TABLE IF NOT EXISTS microsite_analytics_events (
    id SERIAL PRIMARY KEY,
    microsite_id INTEGER NOT NULL REFERENCES microsites(id) ON DELETE CASCADE,

    event_type VARCHAR(100) NOT NULL,
    event_data JSONB,

    session_id VARCHAR(255),
    visitor_id VARCHAR(255),

    utm_source VARCHAR(255),
    utm_medium VARCHAR(255),
    utm_campaign VARCHAR(255),
    utm_term VARCHAR(255),
    utm_content VARCHAR(255),
    referrer TEXT,

    user_agent TEXT,
    ip_address INET,
    device_type VARCHAR(50),
    browser VARCHAR(100),

    variant VARCHAR(50),

    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_analytics_events_site_date ON microsite_analytics_events(microsite_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_analytics_events_type ON microsite_analytics_events(event_type, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_analytics_events_session ON microsite_analytics_events(session_id);

-- 6. MICROSITE LEADS - Lead captures from forms
CREATE TABLE IF NOT EXISTS microsite_leads (
    id SERIAL PRIMARY KEY,
    microsite_id INTEGER NOT NULL REFERENCES microsites(id) ON DELETE CASCADE,
    organization_id INTEGER NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,

    first_name VARCHAR(255),
    last_name VARCHAR(255),
    email VARCHAR(255) NOT NULL,
    phone VARCHAR(50),

    intent_type VARCHAR(100),
    qualifier_answer TEXT,

    lead_source VARCHAR(100) DEFAULT 'microsite',
    session_id VARCHAR(255),

    utm_source VARCHAR(255),
    utm_medium VARCHAR(255),
    utm_campaign VARCHAR(255),

    status VARCHAR(50) DEFAULT 'new',

    appointment_booked BOOLEAN DEFAULT FALSE,
    appointment_date TIMESTAMP WITH TIME ZONE,
    calendly_event_id VARCHAR(255),

    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_microsite_leads_site ON microsite_leads(microsite_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_microsite_leads_user ON microsite_leads(user_id, status);
CREATE INDEX IF NOT EXISTS idx_microsite_leads_email ON microsite_leads(email);
CREATE INDEX IF NOT EXISTS idx_microsite_leads_status ON microsite_leads(status, created_at DESC);

-- 7. ORGANIZATION MICROSITE SETTINGS - Compliance and branding controls
CREATE TABLE IF NOT EXISTS organization_microsite_settings (
    id SERIAL PRIMARY KEY,
    organization_id INTEGER NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,

    compliance_footer_html TEXT,
    required_disclosures_json JSONB,

    company_nmls VARCHAR(50),
    company_name VARCHAR(255),
    company_address TEXT,
    company_phone VARCHAR(50),
    company_email VARCHAR(255),

    google_analytics_id VARCHAR(100),
    facebook_pixel_id VARCHAR(100),
    google_tag_manager_id VARCHAR(100),

    default_logo_url TEXT,
    default_brand_colors_json JSONB,
    default_font_preset VARCHAR(100),

    allow_custom_domains BOOLEAN DEFAULT FALSE,
    require_approval_before_publish BOOLEAN DEFAULT FALSE,

    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT unique_org_microsite_settings UNIQUE(organization_id)
);

-- 8. TRIGGERS - Auto-update timestamps
CREATE OR REPLACE FUNCTION microsite_update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS update_microsites_updated_at ON microsites;
CREATE TRIGGER update_microsites_updated_at
BEFORE UPDATE ON microsites
FOR EACH ROW EXECUTE FUNCTION microsite_update_updated_at_column();

DROP TRIGGER IF EXISTS update_template_packs_updated_at ON microsite_template_packs;
CREATE TRIGGER update_template_packs_updated_at
BEFORE UPDATE ON microsite_template_packs
FOR EACH ROW EXECUTE FUNCTION microsite_update_updated_at_column();

-- 9. PUBLISH TRACKING TRIGGER - Auto-record publish history
CREATE OR REPLACE FUNCTION record_microsite_publish_event()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.status = 'published' AND (OLD.status != 'published' OR OLD.content_json != NEW.content_json) THEN
        INSERT INTO microsite_publish_history (
            microsite_id,
            content_snapshot,
            template_version,
            action,
            published_by
        ) VALUES (
            NEW.id,
            NEW.content_json,
            NEW.template_version,
            CASE WHEN OLD.status = 'published' THEN 'updated' ELSE 'published' END,
            NEW.user_id
        );

        NEW.last_published_at = NOW();
        IF OLD.status != 'published' THEN
            NEW.published_at = NOW();
        END IF;
    ELSIF NEW.status != 'published' AND OLD.status = 'published' THEN
        INSERT INTO microsite_publish_history (
            microsite_id,
            content_snapshot,
            template_version,
            action,
            published_by
        ) VALUES (
            NEW.id,
            NEW.content_json,
            NEW.template_version,
            'unpublished',
            NEW.user_id
        );
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS microsites_publish_tracking ON microsites;
CREATE TRIGGER microsites_publish_tracking
BEFORE UPDATE ON microsites
FOR EACH ROW EXECUTE FUNCTION record_microsite_publish_event();

-- 10. GIN INDEXES FOR JSONB SEARCH
CREATE INDEX IF NOT EXISTS idx_microsites_content_gin ON microsites USING GIN (content_json);
CREATE INDEX IF NOT EXISTS idx_template_packs_schema_gin ON microsite_template_packs USING GIN (schema_json);

-- 11. SEED DEFAULT TEMPLATE - High-Conversion Mortgage Template
INSERT INTO microsite_template_packs (
    organization_id,
    name,
    description,
    slug,
    version,
    status,
    template_json,
    schema_json,
    defaults_json,
    category,
    tags
) VALUES (
    NULL,
    'High-Conversion Mortgage',
    'High-converting mortgage microsite template with intent capture, testimonials, and lead forms',
    'high-conversion-v1',
    1,
    'active',
    '{
        "version": "1.0",
        "templateName": "High-Conversion Mortgage",
        "description": "High-converting mortgage microsite with intent capture",
        "sections": ["hero", "trustSignals", "benefits", "tools", "quickFunding", "finalCta"],
        "conversionSystem": {
            "intentCapture": {
                "enabled": true,
                "intents": [
                    {"id": "purchase", "label": "Home Purchase", "icon": "home"},
                    {"id": "refinance", "label": "Home Refinance", "icon": "refresh"},
                    {"id": "cashout", "label": "Cash-Out Refinance", "icon": "dollar"}
                ]
            }
        }
    }'::jsonb,
    '{
        "version": "1.0",
        "sections": {
            "hero": {
                "label": "Hero Section",
                "fields": {
                    "headline": {"type": "text", "label": "Main Headline", "required": true, "maxLength": 120, "editable": true},
                    "subheadline": {"type": "textarea", "label": "Subheadline", "required": true, "maxLength": 200, "editable": true},
                    "ctaButtonText": {"type": "text", "label": "CTA Button Text", "required": true, "maxLength": 50, "editable": true}
                }
            },
            "trustSignals": {
                "label": "Trust & Social Proof",
                "fields": {
                    "showTestimonial": {"type": "boolean", "label": "Show Testimonial", "default": true, "editable": true},
                    "testimonialText": {"type": "textarea", "label": "Testimonial Quote", "maxLength": 500, "editable": true},
                    "testimonialAuthor": {"type": "text", "label": "Testimonial Author", "maxLength": 100, "editable": true}
                }
            },
            "benefits": {
                "label": "Benefits Section",
                "fields": {
                    "benefitsSectionTitle": {"type": "text", "label": "Section Headline", "maxLength": 150, "editable": true},
                    "benefits": {"type": "repeatable", "label": "Benefit Items", "minItems": 3, "maxItems": 6}
                }
            },
            "branding": {
                "label": "Branding & Visual Identity",
                "fields": {
                    "logo": {"type": "image", "label": "Company Logo", "required": true, "editable": true},
                    "headshot": {"type": "image", "label": "Your Professional Headshot", "editable": true},
                    "brandColors": {"type": "colorPalette", "label": "Brand Colors"}
                }
            },
            "compliance": {
                "label": "Compliance & Licensing",
                "fields": {
                    "loanOfficerName": {"type": "text", "label": "Your Full Name", "required": true, "editable": true},
                    "nmls": {"type": "text", "label": "NMLS Number", "required": true, "editable": true},
                    "licensedStates": {"type": "multiselect", "label": "Licensed States", "required": true, "editable": true},
                    "companyNmls": {"type": "text", "label": "Company NMLS", "locked": true},
                    "companyName": {"type": "text", "label": "Company Legal Name", "locked": true},
                    "complianceFooter": {"type": "richtext", "label": "Compliance Footer", "locked": true}
                }
            },
            "contact": {
                "label": "Contact Information",
                "fields": {
                    "personalPhone": {"type": "phone", "label": "Your Direct Phone", "required": true, "editable": true},
                    "personalEmail": {"type": "email", "label": "Your Email", "required": true, "editable": true},
                    "calendlyUrl": {"type": "url", "label": "Calendly Booking URL", "editable": true}
                }
            },
            "seo": {
                "label": "SEO & Meta Tags",
                "fields": {
                    "metaTitle": {"type": "text", "label": "Page Title", "maxLength": 60, "required": true, "editable": true},
                    "metaDescription": {"type": "textarea", "label": "Meta Description", "maxLength": 160, "required": true, "editable": true}
                }
            }
        }
    }'::jsonb,
    '{
        "hero": {
            "headline": "Want to Save $1000s on Your Mortgage?",
            "subheadline": "Whether you are a first-time buyer or want to refinance at a lower rate, we can help.",
            "ctaButtonText": "Get Started Now"
        },
        "trustSignals": {
            "showTestimonial": true,
            "testimonialText": "Amazing service! We got pre-approved for $580K and were in our dream home less than 3 weeks later.",
            "testimonialAuthor": "Angela & Todd"
        },
        "benefits": {
            "benefitsSectionTitle": "6 Ways We Help You Lock in Lower Rates",
            "benefitsSectionSubtitle": "Let our experienced team guide you through the buying or refinancing process.",
            "benefits": [
                {"icon": "home-purchase", "title": "Secure Your Home Purchase Loan", "description": "We will help you apply for, compare, and choose a home purchase loan that makes your dream home affordable."},
                {"icon": "refinance", "title": "Refinance for Better Rates", "description": "Take advantage of great terms to lower your monthly payment or interest rate."},
                {"icon": "compare", "title": "Compare Rates & Pick the Best", "description": "Use our rate comparison tool to shop around and find the terms that work best for you."},
                {"icon": "fast-funding", "title": "Get Your Loan Funded Faster", "description": "Our fast funding options mean you will never miss out on the house you really want."},
                {"icon": "evaluation", "title": "Evaluate Your Property", "description": "Know where you stand with an up-to-date property evaluation."},
                {"icon": "cashout", "title": "Get a Cash-Out Refinance", "description": "Take advantage of your home equity with a cash-out refinance."}
            ]
        },
        "quickFunding": {
            "showQuickFunding": true,
            "fundingTitle": "Your Home Loan Could Be Fully Funded 30 Days From Now",
            "fundingDescription": "Get fast, custom loan quotes. Fill out our streamlined online application. Move through approval quickly."
        },
        "finalCta": {
            "finalCtaTitle": "Get Your Mortgage Rate Quote in Just 30 Seconds!",
            "finalCtaSubtitle": "Get your FREE customized rate comparison below:",
            "finalCtaButtonText": "Get My Rate Quote Now"
        }
    }'::jsonb,
    'high-conversion',
    ARRAY['mortgage', 'lead-capture', 'conversion-optimized']
)
ON CONFLICT (slug, version) DO NOTHING;

-- 12. SEED MINIMAL TEMPLATE
INSERT INTO microsite_template_packs (
    organization_id,
    name,
    description,
    slug,
    version,
    status,
    template_json,
    schema_json,
    defaults_json,
    category,
    tags
) VALUES (
    NULL,
    'Minimal Professional',
    'Clean, minimal design focused on professionalism and trust',
    'minimal-professional-v1',
    1,
    'active',
    '{
        "version": "1.0",
        "templateName": "Minimal Professional",
        "description": "Clean, minimal design for mortgage professionals",
        "sections": ["hero", "about", "services", "contact"],
        "style": "minimal"
    }'::jsonb,
    '{
        "version": "1.0",
        "sections": {
            "hero": {
                "label": "Hero Section",
                "fields": {
                    "headline": {"type": "text", "label": "Main Headline", "required": true, "maxLength": 80, "editable": true},
                    "subheadline": {"type": "textarea", "label": "Subheadline", "maxLength": 150, "editable": true}
                }
            },
            "about": {
                "label": "About Section",
                "fields": {
                    "bio": {"type": "textarea", "label": "Your Bio", "maxLength": 500, "editable": true},
                    "yearsExperience": {"type": "text", "label": "Years of Experience", "editable": true}
                }
            },
            "contact": {
                "label": "Contact Information",
                "fields": {
                    "phone": {"type": "phone", "label": "Phone", "required": true, "editable": true},
                    "email": {"type": "email", "label": "Email", "required": true, "editable": true}
                }
            }
        }
    }'::jsonb,
    '{
        "hero": {
            "headline": "Your Trusted Mortgage Partner",
            "subheadline": "Helping families achieve homeownership with personalized service"
        },
        "about": {
            "bio": "With years of experience in the mortgage industry, I am dedicated to helping you find the perfect loan for your needs.",
            "yearsExperience": "10+"
        }
    }'::jsonb,
    'minimal',
    ARRAY['mortgage', 'professional', 'clean']
)
ON CONFLICT (slug, version) DO NOTHING;
