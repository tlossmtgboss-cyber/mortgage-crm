"""
Content Marketing Automation Tables Migration

Creates tables for:
- Brand voice profiles
- Content calendars
- Content briefs
- Comments and approvals
- SEO keywords
- Content templates
- Personalization tokens
- Publishing logs
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
        # 1. Brand Voice Profiles
        """
        CREATE TABLE IF NOT EXISTS content_brand_voices (
            id TEXT PRIMARY KEY,
            user_id INTEGER,
            organization_id INTEGER DEFAULT 1,
            name TEXT NOT NULL,
            source_url TEXT,
            source_content TEXT,
            tone_formal_casual REAL DEFAULT 0.5,
            tone_authoritative_friendly REAL DEFAULT 0.5,
            tone_technical_simple REAL DEFAULT 0.5,
            tone_serious_playful REAL DEFAULT 0.5,
            vocabulary_level TEXT DEFAULT 'intermediate',
            sentence_structure TEXT,
            key_phrases TEXT DEFAULT '[]',
            avoided_phrases TEXT DEFAULT '[]',
            brand_values TEXT DEFAULT '[]',
            target_audience TEXT,
            industry_context TEXT DEFAULT 'mortgage lending',
            system_prompt TEXT,
            style_examples TEXT DEFAULT '[]',
            analysis_confidence REAL DEFAULT 0.0,
            is_active INTEGER DEFAULT 1,
            is_default INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """,

        # 2. Content Calendars
        """
        CREATE TABLE IF NOT EXISTS content_calendars (
            id TEXT PRIMARY KEY,
            user_id INTEGER,
            organization_id INTEGER DEFAULT 1,
            name TEXT NOT NULL,
            description TEXT,
            start_date DATE NOT NULL,
            end_date DATE NOT NULL,
            status TEXT DEFAULT 'draft',
            posts_per_week INTEGER DEFAULT 5,
            blog_posts_per_week INTEGER DEFAULT 3,
            social_posts_per_day INTEGER DEFAULT 1,
            channels TEXT DEFAULT '["blog", "linkedin", "facebook"]',
            brand_voice_id TEXT REFERENCES content_brand_voices(id),
            campaign_id TEXT,
            auto_generate_briefs INTEGER DEFAULT 1,
            auto_generate_content INTEGER DEFAULT 0,
            auto_publish INTEGER DEFAULT 0,
            primary_theme TEXT,
            target_keywords TEXT DEFAULT '[]',
            total_briefs INTEGER DEFAULT 0,
            published_count INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """,

        # 3. Content Briefs
        """
        CREATE TABLE IF NOT EXISTS content_briefs (
            id TEXT PRIMARY KEY,
            calendar_id TEXT REFERENCES content_calendars(id),
            user_id INTEGER,
            organization_id INTEGER DEFAULT 1,
            scheduled_date DATE NOT NULL,
            scheduled_time TIME,
            channels TEXT DEFAULT '[]',
            title TEXT,
            topic TEXT NOT NULL,
            archetype TEXT DEFAULT 'informative',
            primary_keyword TEXT,
            secondary_keywords TEXT DEFAULT '[]',
            target_word_count INTEGER DEFAULT 800,
            target_audience TEXT,
            key_points TEXT DEFAULT '[]',
            call_to_action TEXT,
            personalization_type TEXT DEFAULT 'general',
            personalization_segment TEXT,
            personalization_tokens TEXT DEFAULT '{}',
            template_id TEXT,
            content_item_id TEXT,
            status TEXT DEFAULT 'planned',
            assigned_to INTEGER,
            due_date DATE,
            generated_title TEXT,
            generated_content TEXT,
            generated_at TIMESTAMP,
            published_at TIMESTAMP,
            publish_results TEXT DEFAULT '{}',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """,

        # 4. Content Comments
        """
        CREATE TABLE IF NOT EXISTS content_comments (
            id TEXT PRIMARY KEY,
            brief_id TEXT REFERENCES content_briefs(id),
            content_item_id TEXT,
            user_id INTEGER NOT NULL,
            parent_comment_id TEXT REFERENCES content_comments(id),
            comment_type TEXT DEFAULT 'general',
            content TEXT NOT NULL,
            highlighted_text TEXT,
            position_start INTEGER,
            position_end INTEGER,
            resolved INTEGER DEFAULT 0,
            resolved_by INTEGER,
            resolved_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """,

        # 5. Content Approvals
        """
        CREATE TABLE IF NOT EXISTS content_approvals (
            id TEXT PRIMARY KEY,
            brief_id TEXT REFERENCES content_briefs(id),
            content_item_id TEXT,
            workflow_stage TEXT NOT NULL,
            status TEXT DEFAULT 'pending',
            requested_by INTEGER,
            assigned_to INTEGER,
            decision_by INTEGER,
            decision_at TIMESTAMP,
            decision_notes TEXT,
            content_version INTEGER DEFAULT 1,
            content_snapshot TEXT,
            due_date TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """,

        # 6. SEO Keywords
        """
        CREATE TABLE IF NOT EXISTS seo_keywords (
            id TEXT PRIMARY KEY,
            user_id INTEGER,
            organization_id INTEGER DEFAULT 1,
            keyword TEXT NOT NULL,
            search_volume INTEGER,
            difficulty_score REAL,
            cpc REAL,
            current_ranking INTEGER,
            target_ranking INTEGER DEFAULT 10,
            best_ranking INTEGER,
            ranking_history TEXT DEFAULT '[]',
            content_brief_ids TEXT DEFAULT '[]',
            content_item_ids TEXT DEFAULT '[]',
            category TEXT,
            intent TEXT,
            status TEXT DEFAULT 'active',
            priority INTEGER DEFAULT 3,
            last_checked_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """,

        # 7. Content Templates
        """
        CREATE TABLE IF NOT EXISTS content_templates (
            id TEXT PRIMARY KEY,
            user_id INTEGER,
            organization_id INTEGER DEFAULT 1,
            name TEXT NOT NULL,
            description TEXT,
            category TEXT NOT NULL,
            template_type TEXT NOT NULL,
            title_template TEXT,
            body_template TEXT NOT NULL,
            available_tokens TEXT DEFAULT '[]',
            required_tokens TEXT DEFAULT '[]',
            estimated_word_count INTEGER,
            archetype TEXT DEFAULT 'informative',
            default_keywords TEXT DEFAULT '[]',
            includes_disclosure INTEGER DEFAULT 1,
            disclosure_text TEXT,
            times_used INTEGER DEFAULT 0,
            last_used_at TIMESTAMP,
            is_system INTEGER DEFAULT 0,
            is_active INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """,

        # 8. Personalization Tokens
        """
        CREATE TABLE IF NOT EXISTS personalization_tokens (
            id TEXT PRIMARY KEY,
            token_name TEXT NOT NULL UNIQUE,
            display_name TEXT,
            description TEXT,
            source_model TEXT NOT NULL,
            source_field TEXT NOT NULL,
            format_type TEXT DEFAULT 'text',
            format_pattern TEXT,
            default_value TEXT,
            category TEXT,
            is_active INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """,

        # 9. Content Publish Logs
        """
        CREATE TABLE IF NOT EXISTS content_publish_logs (
            id TEXT PRIMARY KEY,
            brief_id TEXT REFERENCES content_briefs(id),
            content_item_id TEXT,
            channel TEXT NOT NULL,
            scheduled_at TIMESTAMP,
            published_at TIMESTAMP,
            status TEXT DEFAULT 'pending',
            external_post_id TEXT,
            external_url TEXT,
            error_message TEXT,
            retry_count INTEGER DEFAULT 0,
            views INTEGER DEFAULT 0,
            likes INTEGER DEFAULT 0,
            comments INTEGER DEFAULT 0,
            shares INTEGER DEFAULT 0,
            clicks INTEGER DEFAULT 0,
            metrics_updated_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """,

        # Indices
        "CREATE INDEX IF NOT EXISTS idx_brand_voices_user ON content_brand_voices(user_id)",
        "CREATE INDEX IF NOT EXISTS idx_calendars_user ON content_calendars(user_id)",
        "CREATE INDEX IF NOT EXISTS idx_calendars_status ON content_calendars(status)",
        "CREATE INDEX IF NOT EXISTS idx_briefs_calendar ON content_briefs(calendar_id)",
        "CREATE INDEX IF NOT EXISTS idx_briefs_date ON content_briefs(scheduled_date)",
        "CREATE INDEX IF NOT EXISTS idx_briefs_status ON content_briefs(status)",
        "CREATE INDEX IF NOT EXISTS idx_comments_brief ON content_comments(brief_id)",
        "CREATE INDEX IF NOT EXISTS idx_approvals_brief ON content_approvals(brief_id)",
        "CREATE INDEX IF NOT EXISTS idx_approvals_status ON content_approvals(status)",
        "CREATE INDEX IF NOT EXISTS idx_keywords_keyword ON seo_keywords(keyword)",
        "CREATE INDEX IF NOT EXISTS idx_templates_category ON content_templates(category)",
        "CREATE INDEX IF NOT EXISTS idx_templates_type ON content_templates(template_type)",
        "CREATE INDEX IF NOT EXISTS idx_publish_logs_brief ON content_publish_logs(brief_id)",
        "CREATE INDEX IF NOT EXISTS idx_publish_logs_channel ON content_publish_logs(channel)",
    ]


def get_postgresql_commands():
    """PostgreSQL-compatible SQL commands."""
    return [
        # 1. Brand Voice Profiles
        """
        CREATE TABLE IF NOT EXISTS content_brand_voices (
            id VARCHAR(50) PRIMARY KEY,
            user_id INTEGER,
            organization_id INTEGER DEFAULT 1,
            name VARCHAR(255) NOT NULL,
            source_url TEXT,
            source_content TEXT,
            tone_formal_casual NUMERIC(4,3) DEFAULT 0.5,
            tone_authoritative_friendly NUMERIC(4,3) DEFAULT 0.5,
            tone_technical_simple NUMERIC(4,3) DEFAULT 0.5,
            tone_serious_playful NUMERIC(4,3) DEFAULT 0.5,
            vocabulary_level VARCHAR(50) DEFAULT 'intermediate',
            sentence_structure TEXT,
            key_phrases JSONB DEFAULT '[]',
            avoided_phrases JSONB DEFAULT '[]',
            brand_values JSONB DEFAULT '[]',
            target_audience TEXT,
            industry_context TEXT DEFAULT 'mortgage lending',
            system_prompt TEXT,
            style_examples JSONB DEFAULT '[]',
            analysis_confidence NUMERIC(4,3) DEFAULT 0.0,
            is_active BOOLEAN DEFAULT TRUE,
            is_default BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        )
        """,

        # 2. Content Calendars
        """
        CREATE TABLE IF NOT EXISTS content_calendars (
            id VARCHAR(50) PRIMARY KEY,
            user_id INTEGER,
            organization_id INTEGER DEFAULT 1,
            name VARCHAR(255) NOT NULL,
            description TEXT,
            start_date DATE NOT NULL,
            end_date DATE NOT NULL,
            status VARCHAR(50) DEFAULT 'draft',
            posts_per_week INTEGER DEFAULT 5,
            blog_posts_per_week INTEGER DEFAULT 3,
            social_posts_per_day INTEGER DEFAULT 1,
            channels JSONB DEFAULT '["blog", "linkedin", "facebook"]',
            brand_voice_id VARCHAR(50) REFERENCES content_brand_voices(id),
            campaign_id VARCHAR(50),
            auto_generate_briefs BOOLEAN DEFAULT TRUE,
            auto_generate_content BOOLEAN DEFAULT FALSE,
            auto_publish BOOLEAN DEFAULT FALSE,
            primary_theme VARCHAR(255),
            target_keywords JSONB DEFAULT '[]',
            total_briefs INTEGER DEFAULT 0,
            published_count INTEGER DEFAULT 0,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        )
        """,

        # 3. Content Briefs
        """
        CREATE TABLE IF NOT EXISTS content_briefs (
            id VARCHAR(50) PRIMARY KEY,
            calendar_id VARCHAR(50) REFERENCES content_calendars(id),
            user_id INTEGER,
            organization_id INTEGER DEFAULT 1,
            scheduled_date DATE NOT NULL,
            scheduled_time TIME,
            channels JSONB DEFAULT '[]',
            title VARCHAR(500),
            topic TEXT NOT NULL,
            archetype VARCHAR(50) DEFAULT 'informative',
            primary_keyword VARCHAR(255),
            secondary_keywords JSONB DEFAULT '[]',
            target_word_count INTEGER DEFAULT 800,
            target_audience TEXT,
            key_points JSONB DEFAULT '[]',
            call_to_action TEXT,
            personalization_type VARCHAR(50) DEFAULT 'general',
            personalization_segment VARCHAR(255),
            personalization_tokens JSONB DEFAULT '{}',
            template_id VARCHAR(50),
            content_item_id VARCHAR(50),
            status VARCHAR(50) DEFAULT 'planned',
            assigned_to INTEGER,
            due_date DATE,
            generated_title VARCHAR(500),
            generated_content TEXT,
            generated_at TIMESTAMP WITH TIME ZONE,
            published_at TIMESTAMP WITH TIME ZONE,
            publish_results JSONB DEFAULT '{}',
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        )
        """,

        # 4. Content Comments
        """
        CREATE TABLE IF NOT EXISTS content_comments (
            id VARCHAR(50) PRIMARY KEY,
            brief_id VARCHAR(50) REFERENCES content_briefs(id),
            content_item_id VARCHAR(50),
            user_id INTEGER NOT NULL,
            parent_comment_id VARCHAR(50) REFERENCES content_comments(id),
            comment_type VARCHAR(50) DEFAULT 'general',
            content TEXT NOT NULL,
            highlighted_text TEXT,
            position_start INTEGER,
            position_end INTEGER,
            resolved BOOLEAN DEFAULT FALSE,
            resolved_by INTEGER,
            resolved_at TIMESTAMP WITH TIME ZONE,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        )
        """,

        # 5. Content Approvals
        """
        CREATE TABLE IF NOT EXISTS content_approvals (
            id VARCHAR(50) PRIMARY KEY,
            brief_id VARCHAR(50) REFERENCES content_briefs(id),
            content_item_id VARCHAR(50),
            workflow_stage VARCHAR(50) NOT NULL,
            status VARCHAR(50) DEFAULT 'pending',
            requested_by INTEGER,
            assigned_to INTEGER,
            decision_by INTEGER,
            decision_at TIMESTAMP WITH TIME ZONE,
            decision_notes TEXT,
            content_version INTEGER DEFAULT 1,
            content_snapshot TEXT,
            due_date TIMESTAMP WITH TIME ZONE,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        )
        """,

        # 6. SEO Keywords
        """
        CREATE TABLE IF NOT EXISTS seo_keywords (
            id VARCHAR(50) PRIMARY KEY,
            user_id INTEGER,
            organization_id INTEGER DEFAULT 1,
            keyword VARCHAR(255) NOT NULL,
            search_volume INTEGER,
            difficulty_score NUMERIC(5,2),
            cpc NUMERIC(8,2),
            current_ranking INTEGER,
            target_ranking INTEGER DEFAULT 10,
            best_ranking INTEGER,
            ranking_history JSONB DEFAULT '[]',
            content_brief_ids JSONB DEFAULT '[]',
            content_item_ids JSONB DEFAULT '[]',
            category VARCHAR(100),
            intent VARCHAR(50),
            status VARCHAR(50) DEFAULT 'active',
            priority INTEGER DEFAULT 3,
            last_checked_at TIMESTAMP WITH TIME ZONE,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        )
        """,

        # 7. Content Templates
        """
        CREATE TABLE IF NOT EXISTS content_templates (
            id VARCHAR(50) PRIMARY KEY,
            user_id INTEGER,
            organization_id INTEGER DEFAULT 1,
            name VARCHAR(255) NOT NULL,
            description TEXT,
            category VARCHAR(100) NOT NULL,
            template_type VARCHAR(50) NOT NULL,
            title_template TEXT,
            body_template TEXT NOT NULL,
            available_tokens JSONB DEFAULT '[]',
            required_tokens JSONB DEFAULT '[]',
            estimated_word_count INTEGER,
            archetype VARCHAR(50) DEFAULT 'informative',
            default_keywords JSONB DEFAULT '[]',
            includes_disclosure BOOLEAN DEFAULT TRUE,
            disclosure_text TEXT,
            times_used INTEGER DEFAULT 0,
            last_used_at TIMESTAMP WITH TIME ZONE,
            is_system BOOLEAN DEFAULT FALSE,
            is_active BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        )
        """,

        # 8. Personalization Tokens
        """
        CREATE TABLE IF NOT EXISTS personalization_tokens (
            id VARCHAR(50) PRIMARY KEY,
            token_name VARCHAR(100) NOT NULL UNIQUE,
            display_name VARCHAR(255),
            description TEXT,
            source_model VARCHAR(50) NOT NULL,
            source_field VARCHAR(100) NOT NULL,
            format_type VARCHAR(50) DEFAULT 'text',
            format_pattern VARCHAR(100),
            default_value TEXT,
            category VARCHAR(50),
            is_active BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        )
        """,

        # 9. Content Publish Logs
        """
        CREATE TABLE IF NOT EXISTS content_publish_logs (
            id VARCHAR(50) PRIMARY KEY,
            brief_id VARCHAR(50) REFERENCES content_briefs(id),
            content_item_id VARCHAR(50),
            channel VARCHAR(50) NOT NULL,
            scheduled_at TIMESTAMP WITH TIME ZONE,
            published_at TIMESTAMP WITH TIME ZONE,
            status VARCHAR(50) DEFAULT 'pending',
            external_post_id VARCHAR(255),
            external_url TEXT,
            error_message TEXT,
            retry_count INTEGER DEFAULT 0,
            views INTEGER DEFAULT 0,
            likes INTEGER DEFAULT 0,
            comments INTEGER DEFAULT 0,
            shares INTEGER DEFAULT 0,
            clicks INTEGER DEFAULT 0,
            metrics_updated_at TIMESTAMP WITH TIME ZONE,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        )
        """,

        # Indices
        "CREATE INDEX IF NOT EXISTS idx_brand_voices_user ON content_brand_voices(user_id)",
        "CREATE INDEX IF NOT EXISTS idx_calendars_user ON content_calendars(user_id)",
        "CREATE INDEX IF NOT EXISTS idx_calendars_status ON content_calendars(status)",
        "CREATE INDEX IF NOT EXISTS idx_briefs_calendar ON content_briefs(calendar_id)",
        "CREATE INDEX IF NOT EXISTS idx_briefs_date ON content_briefs(scheduled_date)",
        "CREATE INDEX IF NOT EXISTS idx_briefs_status ON content_briefs(status)",
        "CREATE INDEX IF NOT EXISTS idx_comments_brief ON content_comments(brief_id)",
        "CREATE INDEX IF NOT EXISTS idx_approvals_brief ON content_approvals(brief_id)",
        "CREATE INDEX IF NOT EXISTS idx_approvals_status ON content_approvals(status)",
        "CREATE INDEX IF NOT EXISTS idx_keywords_keyword ON seo_keywords(keyword)",
        "CREATE INDEX IF NOT EXISTS idx_templates_category ON content_templates(category)",
        "CREATE INDEX IF NOT EXISTS idx_templates_type ON content_templates(template_type)",
        "CREATE INDEX IF NOT EXISTS idx_publish_logs_brief ON content_publish_logs(brief_id)",
        "CREATE INDEX IF NOT EXISTS idx_publish_logs_channel ON content_publish_logs(channel)",
    ]


def seed_personalization_tokens():
    """Seed default personalization tokens for CRM data."""
    return [
        # Lead Profile tokens
        ("lead.first_name", "Lead First Name", "Lead's first name", "lead_profile", "first_name", "text", None, "Valued Customer", "personal"),
        ("lead.last_name", "Lead Last Name", "Lead's last name", "lead_profile", "last_name", "text", None, "", "personal"),
        ("lead.email", "Lead Email", "Lead's email address", "lead_profile", "email", "text", None, "", "personal"),
        ("lead.loan_amount", "Loan Amount", "Requested loan amount", "lead_profile", "loan_amount", "currency", "${:,.0f}", "$0", "loan"),
        ("lead.loan_type", "Loan Type", "Type of loan (FHA, VA, Conventional)", "lead_profile", "loan_type", "text", None, "mortgage", "loan"),
        ("lead.property_type", "Property Type", "Type of property", "lead_profile", "property_type", "text", None, "home", "property"),
        ("lead.city", "City", "Property city", "lead_profile", "city", "text", None, "", "property"),
        ("lead.state", "State", "Property state", "lead_profile", "state", "text", None, "", "property"),
        ("lead.credit_score", "Credit Score", "Estimated credit score", "lead_profile", "credit_score", "number", None, "", "loan"),
        ("lead.down_payment", "Down Payment", "Down payment amount", "lead_profile", "down_payment", "currency", "${:,.0f}", "", "loan"),
        ("lead.stage", "Lead Stage", "Current stage in pipeline", "lead_profile", "stage", "text", None, "", "status"),

        # Active Loan tokens
        ("loan.amount", "Loan Amount", "Active loan amount", "active_loan_profile", "amount", "currency", "${:,.0f}", "$0", "loan"),
        ("loan.rate", "Interest Rate", "Current interest rate", "active_loan_profile", "rate", "percentage", "{:.3f}%", "", "loan"),
        ("loan.term", "Loan Term", "Loan term in years", "active_loan_profile", "term", "number", None, "30", "loan"),
        ("loan.property_address", "Property Address", "Full property address", "active_loan_profile", "property_address", "text", None, "", "property"),
        ("loan.property_city", "Property City", "Property city", "active_loan_profile", "property_city", "text", None, "", "property"),
        ("loan.closing_date", "Closing Date", "Scheduled closing date", "active_loan_profile", "closing_scheduled_date", "date", "%B %d, %Y", "", "dates"),
        ("loan.days_to_close", "Days to Close", "Days until closing", "active_loan_profile", "days_to_closing", "number", None, "", "dates"),
        ("loan.current_milestone", "Current Milestone", "Current loan milestone", "active_loan_profile", "current_milestone", "text", None, "", "status"),
        ("loan.loan_officer", "Loan Officer", "Assigned loan officer name", "active_loan_profile", "loan_officer_name", "text", None, "", "team"),
        ("loan.processor", "Processor", "Assigned processor name", "active_loan_profile", "processor", "text", None, "", "team"),

        # MUM Client tokens
        ("mum.name", "Client Name", "MUM client full name", "mum_client_profile", "name", "text", None, "Valued Client", "personal"),
        ("mum.original_rate", "Original Rate", "Original interest rate", "mum_client_profile", "original_rate", "percentage", "{:.3f}%", "", "loan"),
        ("mum.current_rate", "Current Market Rate", "Current available rate", "mum_client_profile", "current_rate", "percentage", "{:.3f}%", "", "loan"),
        ("mum.loan_balance", "Loan Balance", "Current loan balance", "mum_client_profile", "loan_balance", "currency", "${:,.0f}", "", "loan"),
        ("mum.estimated_savings", "Estimated Savings", "Potential annual savings", "mum_client_profile", "estimated_savings", "currency", "${:,.0f}/year", "", "loan"),
        ("mum.refinance_opportunity", "Refinance Flag", "Has refinance opportunity", "mum_client_profile", "refinance_opportunity", "boolean", None, "false", "status"),
        ("mum.engagement_score", "Engagement Score", "Client engagement score", "mum_client_profile", "engagement_score", "number", None, "0", "status"),
    ]


def seed_content_templates():
    """Seed default mortgage content templates."""
    return [
        # Rate Update Blog
        {
            "id": "tpl_rate_update_blog",
            "name": "Monthly Rate Update",
            "description": "Monthly interest rate analysis and market update",
            "category": "rate_update",
            "template_type": "blog",
            "title_template": "{{ month }} {{ year }} Mortgage Rate Update: What {{ loan_type }} Borrowers Need to Know",
            "body_template": """# {{ month }} Mortgage Rate Update

As we move through {{ month }} {{ year }}, here's what you need to know about current mortgage rates and market conditions.

## Current Rate Environment

{{ market_analysis }}

## What This Means For You

{% if audience == 'first_time_buyer' %}
As a first-time homebuyer, these current rates present an opportunity to lock in financing for your new home. With rates {{ rate_trend }}, now may be an ideal time to get pre-approved.
{% elif audience == 'refinance' %}
If you're considering refinancing your existing mortgage, the current rate environment could help you {{ refinance_benefit }}.
{% else %}
Whether you're buying or refinancing, understanding current rates helps you make informed decisions about your mortgage.
{% endif %}

## Key Takeaways

{{ key_points }}

## Next Steps

{{ call_to_action }}

---

*{{ disclosure }}*
""",
            "available_tokens": ["month", "year", "loan_type", "market_analysis", "audience", "rate_trend", "refinance_benefit", "key_points", "call_to_action", "disclosure"],
            "required_tokens": ["month", "year"],
            "archetype": "data_driven",
            "estimated_word_count": 600,
            "is_system": True,
        },

        # First-Time Buyer Guide
        {
            "id": "tpl_first_time_buyer",
            "name": "First-Time Buyer Guide",
            "description": "Tips and guidance for first-time homebuyers",
            "category": "buyer_tips",
            "template_type": "blog",
            "title_template": "{{ count }} Essential Tips for First-Time Homebuyers in {{ state }}",
            "body_template": """# {{ count }} Essential Tips for First-Time Homebuyers in {{ state }}

Buying your first home is exciting, but it can also feel overwhelming. Here's what you need to know to navigate the process with confidence.

## Understanding Your Budget

Before you start house hunting, it's crucial to understand what you can afford. Consider:
- Your monthly income and expenses
- Down payment savings
- Closing costs (typically 2-5% of purchase price)

## The Pre-Approval Process

Getting pre-approved gives you a clear picture of your buying power and shows sellers you're a serious buyer.

{{ tips_content }}

## {{ state }}-Specific Programs

{{ local_programs }}

## Ready to Get Started?

{{ call_to_action }}

---

*{{ disclosure }}*
""",
            "available_tokens": ["count", "state", "tips_content", "local_programs", "call_to_action", "disclosure"],
            "required_tokens": ["state"],
            "archetype": "how_to",
            "estimated_word_count": 800,
            "is_system": True,
        },

        # Closing Celebration (LinkedIn)
        {
            "id": "tpl_closing_celebration_linkedin",
            "name": "Closing Celebration",
            "description": "Celebrate a successful closing on social media",
            "category": "closing_celebration",
            "template_type": "linkedin",
            "title_template": None,
            "body_template": """Congratulations to {{ client_first_name }} on closing on their {{ property_type }} in {{ city }}! 🏠🎉

It was a pleasure helping them navigate the {{ loan_type }} process. From application to keys in just {{ days_to_close }} days!

{{ personal_note }}

Ready to start your homeownership journey? Let's connect!

#MortgageSuccess #HomeBuyers #{{ city_hashtag }}RealEstate #ClosingDay
""",
            "available_tokens": ["client_first_name", "property_type", "city", "loan_type", "days_to_close", "personal_note", "city_hashtag"],
            "required_tokens": ["client_first_name", "city"],
            "archetype": "celebration",
            "estimated_word_count": 100,
            "is_system": True,
        },

        # Refinance Opportunity Email
        {
            "id": "tpl_refinance_email",
            "name": "Refinance Opportunity",
            "description": "Personalized email for MUM clients with refinance potential",
            "category": "refinance",
            "template_type": "email",
            "title_template": "{{ mum.name }}, Could You Save {{ mum.estimated_savings }} Per Year?",
            "body_template": """Hi {{ mum.name }},

I was reviewing your loan details and noticed an opportunity that could save you money.

**Your Current Loan:**
- Original Rate: {{ mum.original_rate }}
- Current Balance: {{ mum.loan_balance }}

**Today's Opportunity:**
- Available Rate: {{ mum.current_rate }}
- Potential Annual Savings: {{ mum.estimated_savings }}

Rates are {{ rate_trend }}, so this could be a great time to explore your options.

Would you like to schedule a quick call to discuss whether refinancing makes sense for your situation?

[Schedule a Call]({{ calendar_link }})

Best regards,
{{ loan_officer_name }}

---
*{{ disclosure }}*
""",
            "available_tokens": ["mum.name", "mum.original_rate", "mum.loan_balance", "mum.current_rate", "mum.estimated_savings", "rate_trend", "calendar_link", "loan_officer_name", "disclosure"],
            "required_tokens": ["mum.name", "mum.original_rate", "mum.current_rate"],
            "archetype": "informative",
            "estimated_word_count": 150,
            "is_system": True,
        },

        # Market Update (Facebook)
        {
            "id": "tpl_market_update_facebook",
            "name": "Weekly Market Update",
            "description": "Weekly housing market update for Facebook",
            "category": "market_analysis",
            "template_type": "facebook",
            "title_template": None,
            "body_template": """📊 {{ location }} Housing Market Update - Week of {{ week_date }}

{{ market_summary }}

🏠 Median Home Price: {{ median_price }}
📈 Month-over-Month Change: {{ mom_change }}
🏘️ Active Listings: {{ active_listings }}
⏰ Average Days on Market: {{ days_on_market }}

{{ insight }}

Questions about the market? Drop a comment below or send me a message!

#{{ location_hashtag }}RealEstate #HousingMarket #MortgageTips
""",
            "available_tokens": ["location", "week_date", "market_summary", "median_price", "mom_change", "active_listings", "days_on_market", "insight", "location_hashtag"],
            "required_tokens": ["location", "week_date"],
            "archetype": "data_driven",
            "estimated_word_count": 100,
            "is_system": True,
        },

        # Loan Milestone Update Email
        {
            "id": "tpl_milestone_update_email",
            "name": "Loan Milestone Update",
            "description": "Update email for active loan clients at key milestones",
            "category": "loan_update",
            "template_type": "email",
            "title_template": "{{ loan.current_milestone }} - Your Loan Update",
            "body_template": """Hi {{ lead.first_name }},

Great news! Your loan has reached a new milestone: **{{ loan.current_milestone }}**

**Loan Summary:**
- Property: {{ loan.property_address }}, {{ loan.property_city }}
- Loan Amount: {{ loan.amount }}
- Rate: {{ loan.rate }}
- Estimated Closing: {{ loan.closing_date }}

**What's Next:**
{{ next_steps }}

**Your Team:**
- Loan Officer: {{ loan.loan_officer }}
- Processor: {{ loan.processor }}

If you have any questions, please don't hesitate to reach out.

Best regards,
{{ loan.loan_officer }}
""",
            "available_tokens": ["lead.first_name", "loan.current_milestone", "loan.property_address", "loan.property_city", "loan.amount", "loan.rate", "loan.closing_date", "next_steps", "loan.loan_officer", "loan.processor"],
            "required_tokens": ["lead.first_name", "loan.current_milestone"],
            "archetype": "informative",
            "estimated_word_count": 150,
            "is_system": True,
        },
    ]


def run_migration():
    """Run the content marketing migration."""
    logger.info("=" * 60)
    logger.info("  CONTENT MARKETING TABLES MIGRATION")
    logger.info("=" * 60)

    is_sqlite = "sqlite" in DATABASE_URL.lower()
    logger.info(f"Database: {'SQLite' if is_sqlite else 'PostgreSQL'}")

    engine = create_engine(DATABASE_URL, poolclass=NullPool)
    sql_commands = get_sql_commands()

    try:
        with engine.connect() as conn:
            # Create tables
            for idx, sql in enumerate(sql_commands, 1):
                try:
                    logger.info(f"Executing command {idx}/{len(sql_commands)}...")
                    conn.execute(text(sql))
                    conn.commit()
                    logger.info(f"Command {idx} executed successfully")
                except Exception as e:
                    if "already exists" in str(e).lower():
                        logger.info(f"Command {idx}: Already exists")
                    else:
                        logger.error(f"Error executing command {idx}: {e}")

            # Seed personalization tokens
            logger.info("")
            logger.info("Seeding personalization tokens...")
            tokens = seed_personalization_tokens()
            for token in tokens:
                try:
                    if is_sqlite:
                        sql = """
                            INSERT OR IGNORE INTO personalization_tokens
                            (id, token_name, display_name, description, source_model, source_field, format_type, format_pattern, default_value, category)
                            VALUES (:id, :token_name, :display_name, :description, :source_model, :source_field, :format_type, :format_pattern, :default_value, :category)
                        """
                    else:
                        sql = """
                            INSERT INTO personalization_tokens
                            (id, token_name, display_name, description, source_model, source_field, format_type, format_pattern, default_value, category)
                            VALUES (:id, :token_name, :display_name, :description, :source_model, :source_field, :format_type, :format_pattern, :default_value, :category)
                            ON CONFLICT (token_name) DO NOTHING
                        """
                    conn.execute(text(sql), {
                        "id": f"tok_{token[0].replace('.', '_')}",
                        "token_name": token[0],
                        "display_name": token[1],
                        "description": token[2],
                        "source_model": token[3],
                        "source_field": token[4],
                        "format_type": token[5],
                        "format_pattern": token[6],
                        "default_value": token[7],
                        "category": token[8],
                    })
                    conn.commit()
                except Exception as e:
                    logger.warning(f"Token {token[0]}: {str(e)[:50]}")

            logger.info(f"Seeded {len(tokens)} personalization tokens")

            # Seed content templates
            logger.info("")
            logger.info("Seeding content templates...")
            templates = seed_content_templates()
            import json
            for tpl in templates:
                try:
                    if is_sqlite:
                        sql = """
                            INSERT OR IGNORE INTO content_templates
                            (id, name, description, category, template_type, title_template, body_template, available_tokens, required_tokens, archetype, estimated_word_count, is_system, is_active)
                            VALUES (:id, :name, :description, :category, :template_type, :title_template, :body_template, :available_tokens, :required_tokens, :archetype, :estimated_word_count, 1, 1)
                        """
                    else:
                        sql = """
                            INSERT INTO content_templates
                            (id, name, description, category, template_type, title_template, body_template, available_tokens, required_tokens, archetype, estimated_word_count, is_system, is_active)
                            VALUES (:id, :name, :description, :category, :template_type, :title_template, :body_template, :available_tokens, :required_tokens, :archetype, :estimated_word_count, TRUE, TRUE)
                            ON CONFLICT (id) DO NOTHING
                        """
                    conn.execute(text(sql), {
                        "id": tpl["id"],
                        "name": tpl["name"],
                        "description": tpl["description"],
                        "category": tpl["category"],
                        "template_type": tpl["template_type"],
                        "title_template": tpl.get("title_template"),
                        "body_template": tpl["body_template"],
                        "available_tokens": json.dumps(tpl["available_tokens"]),
                        "required_tokens": json.dumps(tpl["required_tokens"]),
                        "archetype": tpl["archetype"],
                        "estimated_word_count": tpl.get("estimated_word_count"),
                    })
                    conn.commit()
                except Exception as e:
                    logger.warning(f"Template {tpl['id']}: {str(e)[:50]}")

            logger.info(f"Seeded {len(templates)} content templates")

        logger.info("")
        logger.info("=" * 60)
        logger.info("  MIGRATION COMPLETE")
        logger.info("=" * 60)
        logger.info("Tables created:")
        logger.info("  - content_brand_voices")
        logger.info("  - content_calendars")
        logger.info("  - content_briefs")
        logger.info("  - content_comments")
        logger.info("  - content_approvals")
        logger.info("  - seo_keywords")
        logger.info("  - content_templates")
        logger.info("  - personalization_tokens")
        logger.info("  - content_publish_logs")
        logger.info("")
        logger.info("Seed data:")
        logger.info(f"  - {len(tokens)} personalization tokens")
        logger.info(f"  - {len(templates)} content templates")

    except Exception as e:
        logger.error(f"Migration failed: {e}")
        raise


if __name__ == "__main__":
    run_migration()
