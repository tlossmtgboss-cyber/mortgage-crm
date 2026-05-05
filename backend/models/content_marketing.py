"""
Content Marketing Automation Models

Vocable.ai-style content marketing system for mortgage CRM including:
- Brand voice analysis and profiles
- Content calendars and briefs
- Team collaboration (comments, approvals)
- SEO keyword tracking
- Content templates with personalization
"""

from sqlalchemy import (
    Column, Integer, String, Text, Float, Boolean, DateTime, Date, Time,
    ForeignKey, JSON, Enum as SQLEnum
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from datetime import datetime
import enum
import uuid

from database import Base


def generate_uuid():
    return str(uuid.uuid4())[:12]


# =============================================================================
# Enums
# =============================================================================

class ContentStatus(str, enum.Enum):
    PLANNED = "planned"
    BRIEF_APPROVED = "brief_approved"
    GENERATING = "generating"
    DRAFT = "draft"
    REVIEW = "review"
    APPROVED = "approved"
    SCHEDULED = "scheduled"
    PUBLISHED = "published"
    FAILED = "failed"


class CalendarStatus(str, enum.Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"


class ApprovalStatus(str, enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    CHANGES_REQUESTED = "changes_requested"


class ContentChannel(str, enum.Enum):
    BLOG = "blog"
    EMAIL = "email"
    LINKEDIN = "linkedin"
    FACEBOOK = "facebook"
    INSTAGRAM = "instagram"
    TWITTER = "twitter"
    SMS = "sms"


class ContentArchetype(str, enum.Enum):
    INFORMATIVE = "informative"
    STORY = "story"
    DATA_DRIVEN = "data_driven"
    HOW_TO = "how_to"
    COMPARISON = "comparison"
    NEWS = "news"
    CELEBRATION = "celebration"


class PersonalizationType(str, enum.Enum):
    LEAD = "lead"
    LOAN = "loan"
    MUM = "mum"
    GENERAL = "general"


# =============================================================================
# Brand Voice Profile
# =============================================================================

class ContentBrandVoice(Base):
    """Brand voice analysis and configuration for content generation."""
    __tablename__ = "content_brand_voices"

    id = Column(String(50), primary_key=True, default=generate_uuid)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    organization_id = Column(Integer, default=1)

    name = Column(String(255), nullable=False)
    source_url = Column(Text, nullable=True)  # Website URL analyzed
    source_content = Column(Text, nullable=True)  # Sample content analyzed

    # Extracted voice characteristics (0-1 scale)
    tone_formal_casual = Column(Float, default=0.5)  # 0=formal, 1=casual
    tone_authoritative_friendly = Column(Float, default=0.5)  # 0=authoritative, 1=friendly
    tone_technical_simple = Column(Float, default=0.5)  # 0=technical, 1=simple
    tone_serious_playful = Column(Float, default=0.5)  # 0=serious, 1=playful

    vocabulary_level = Column(String(50), default="intermediate")  # basic, intermediate, advanced
    sentence_structure = Column(Text, nullable=True)  # Description of sentence patterns

    # JSON arrays
    key_phrases = Column(JSON, default=list)  # Phrases to use
    avoided_phrases = Column(JSON, default=list)  # Phrases to avoid
    brand_values = Column(JSON, default=list)  # Core values

    target_audience = Column(Text, nullable=True)
    industry_context = Column(Text, default="mortgage lending")

    # Generated prompts for LLM
    system_prompt = Column(Text, nullable=True)
    style_examples = Column(JSON, default=list)

    analysis_confidence = Column(Float, default=0.0)

    is_active = Column(Boolean, default=True)
    is_default = Column(Boolean, default=False)

    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    # Relationships
    calendars = relationship("ContentCalendar", back_populates="brand_voice")


# =============================================================================
# Content Calendar
# =============================================================================

class ContentCalendar(Base):
    """30-day content calendar for planning and scheduling."""
    __tablename__ = "content_calendars"

    id = Column(String(50), primary_key=True, default=generate_uuid)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    organization_id = Column(Integer, default=1)

    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)

    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)
    status = Column(String(50), default=CalendarStatus.DRAFT.value)

    # Calendar settings
    posts_per_week = Column(Integer, default=5)
    blog_posts_per_week = Column(Integer, default=3)
    social_posts_per_day = Column(Integer, default=1)

    channels = Column(JSON, default=["blog", "linkedin", "facebook"])

    brand_voice_id = Column(String(50), ForeignKey("content_brand_voices.id"), nullable=True)
    campaign_id = Column(String(50), nullable=True)  # Links to blog_campaigns if needed

    # Auto-generation settings
    auto_generate_briefs = Column(Boolean, default=True)
    auto_generate_content = Column(Boolean, default=False)
    auto_publish = Column(Boolean, default=False)

    # Theme/focus for the calendar period
    primary_theme = Column(String(255), nullable=True)
    target_keywords = Column(JSON, default=list)

    # Stats
    total_briefs = Column(Integer, default=0)
    published_count = Column(Integer, default=0)

    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    # Relationships
    brand_voice = relationship("ContentBrandVoice", back_populates="calendars")
    briefs = relationship("ContentBrief", back_populates="calendar", cascade="all, delete-orphan")


# =============================================================================
# Content Brief
# =============================================================================

class ContentBrief(Base):
    """Individual content piece planning with scheduling."""
    __tablename__ = "content_briefs"

    id = Column(String(50), primary_key=True, default=generate_uuid)
    calendar_id = Column(String(50), ForeignKey("content_calendars.id"), nullable=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    organization_id = Column(Integer, default=1)

    # Scheduling
    scheduled_date = Column(Date, nullable=False)
    scheduled_time = Column(Time, nullable=True)
    channels = Column(JSON, default=list)  # ["blog", "linkedin", "facebook"]

    # Brief details
    title = Column(String(500), nullable=True)
    topic = Column(Text, nullable=False)
    archetype = Column(String(50), default=ContentArchetype.INFORMATIVE.value)

    # SEO
    primary_keyword = Column(String(255), nullable=True)
    secondary_keywords = Column(JSON, default=list)

    # Content specifications
    target_word_count = Column(Integer, default=800)
    target_audience = Column(Text, nullable=True)
    key_points = Column(JSON, default=list)  # Bullet points to cover
    call_to_action = Column(Text, nullable=True)

    # CRM personalization
    personalization_type = Column(String(50), default=PersonalizationType.GENERAL.value)
    personalization_segment = Column(String(255), nullable=True)  # e.g., "first_time_buyers"
    personalization_tokens = Column(JSON, default=dict)  # Token values to use

    # Content reference
    template_id = Column(String(50), ForeignKey("content_templates.id"), nullable=True)
    content_item_id = Column(String(50), nullable=True)  # Links to blog_content_items

    # Status tracking
    status = Column(String(50), default=ContentStatus.PLANNED.value)

    # Collaboration
    assigned_to = Column(Integer, ForeignKey("users.id"), nullable=True)
    due_date = Column(Date, nullable=True)

    # Generated content storage (before moving to content_item)
    generated_title = Column(String(500), nullable=True)
    generated_content = Column(Text, nullable=True)
    generated_at = Column(DateTime, nullable=True)

    # Publishing
    published_at = Column(DateTime, nullable=True)
    publish_results = Column(JSON, default=dict)  # Results per channel

    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    # Relationships
    calendar = relationship("ContentCalendar", back_populates="briefs")
    template = relationship("ContentTemplate")
    comments = relationship("ContentComment", back_populates="brief", cascade="all, delete-orphan")
    approvals = relationship("ContentBriefApproval", back_populates="brief", cascade="all, delete-orphan")


# =============================================================================
# Content Comments (Collaboration)
# =============================================================================

class ContentComment(Base):
    """Team collaboration comments on content."""
    __tablename__ = "content_comments"

    id = Column(String(50), primary_key=True, default=generate_uuid)
    brief_id = Column(String(50), ForeignKey("content_briefs.id"), nullable=True)
    content_item_id = Column(String(50), nullable=True)  # Links to blog_content_items
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    parent_comment_id = Column(String(50), ForeignKey("content_comments.id"), nullable=True)

    comment_type = Column(String(50), default="general")  # general, suggestion, edit_request, approval_note
    content = Column(Text, nullable=False)

    # For inline comments
    highlighted_text = Column(Text, nullable=True)
    position_start = Column(Integer, nullable=True)
    position_end = Column(Integer, nullable=True)

    # Resolution
    resolved = Column(Boolean, default=False)
    resolved_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    resolved_at = Column(DateTime, nullable=True)

    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    # Relationships
    brief = relationship("ContentBrief", back_populates="comments")
    replies = relationship("ContentComment", backref="parent", remote_side=[id])


# =============================================================================
# Content Approvals
# =============================================================================

class ContentBriefApproval(Base):
    """Approval workflow tracking for content briefs."""
    __tablename__ = "content_brief_approvals"

    id = Column(String(50), primary_key=True, default=generate_uuid)
    brief_id = Column(String(50), ForeignKey("content_briefs.id"), nullable=True)
    content_item_id = Column(String(50), nullable=True)  # Links to blog_content_items

    # Workflow tracking
    workflow_stage = Column(String(50), nullable=False)  # draft_review, compliance_review, final_approval
    status = Column(String(50), default=ApprovalStatus.PENDING.value)

    # Approval details
    requested_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    assigned_to = Column(Integer, ForeignKey("users.id"), nullable=True)
    decision_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    decision_at = Column(DateTime, nullable=True)
    decision_notes = Column(Text, nullable=True)

    # Version tracking
    content_version = Column(Integer, default=1)
    content_snapshot = Column(Text, nullable=True)  # Snapshot of content at approval request

    due_date = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=func.now())

    # Relationships
    brief = relationship("ContentBrief", back_populates="approvals")


# Alias for backward compatibility
ContentApproval = ContentBriefApproval


# =============================================================================
# SEO Keywords
# =============================================================================

class SEOKeyword(Base):
    """SEO keyword tracking and rankings."""
    __tablename__ = "seo_keywords"

    id = Column(String(50), primary_key=True, default=generate_uuid)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    organization_id = Column(Integer, default=1)

    keyword = Column(String(255), nullable=False)
    search_volume = Column(Integer, nullable=True)
    difficulty_score = Column(Float, nullable=True)  # 0-100
    cpc = Column(Float, nullable=True)  # Cost per click

    current_ranking = Column(Integer, nullable=True)
    target_ranking = Column(Integer, default=10)
    best_ranking = Column(Integer, nullable=True)

    # Tracking history
    ranking_history = Column(JSON, default=list)  # [{date, ranking}, ...]

    # Associated content
    content_brief_ids = Column(JSON, default=list)
    content_item_ids = Column(JSON, default=list)

    # Categorization
    category = Column(String(100), nullable=True)  # mortgage, refinance, first_time_buyer, etc.
    intent = Column(String(50), nullable=True)  # informational, transactional, navigational

    # Status
    status = Column(String(50), default="active")  # active, achieved, paused, archived
    priority = Column(Integer, default=3)  # 1=highest, 5=lowest

    last_checked_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())


# =============================================================================
# Content Templates
# =============================================================================

class ContentMarketingTemplate(Base):
    """Mortgage industry content templates with personalization."""
    __tablename__ = "content_marketing_templates"

    id = Column(String(50), primary_key=True, default=generate_uuid)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)  # NULL for system templates
    organization_id = Column(Integer, default=1)

    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    category = Column(String(100), nullable=False)  # rate_update, market_analysis, buyer_tips, refinance, closing_celebration

    # Template content
    template_type = Column(String(50), nullable=False)  # blog, email, linkedin, facebook, instagram, sms
    title_template = Column(Text, nullable=True)  # Jinja2 template
    body_template = Column(Text, nullable=False)  # Jinja2 template with {{ tokens }}

    # Personalization tokens available
    available_tokens = Column(JSON, default=list)  # ['first_name', 'loan_amount', etc.]
    required_tokens = Column(JSON, default=list)  # Tokens that must have values

    # Metadata
    estimated_word_count = Column(Integer, nullable=True)
    archetype = Column(String(50), default=ContentArchetype.INFORMATIVE.value)
    default_keywords = Column(JSON, default=list)

    # Compliance
    includes_disclosure = Column(Boolean, default=True)
    disclosure_text = Column(Text, nullable=True)

    # Usage stats
    times_used = Column(Integer, default=0)
    last_used_at = Column(DateTime, nullable=True)

    is_system = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)

    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())


ContentTemplate = ContentMarketingTemplate


# =============================================================================
# Personalization Tokens
# =============================================================================

class PersonalizationToken(Base):
    """CRM field mappings for content personalization."""
    __tablename__ = "personalization_tokens"

    id = Column(String(50), primary_key=True, default=generate_uuid)

    token_name = Column(String(100), nullable=False, unique=True)  # e.g., 'lead.first_name'
    display_name = Column(String(255), nullable=True)  # e.g., 'Lead First Name'
    description = Column(Text, nullable=True)

    # Data source
    source_model = Column(String(50), nullable=False)  # lead_profile, active_loan_profile, mum_client_profile
    source_field = Column(String(100), nullable=False)  # Field name in the model

    # Formatting
    format_type = Column(String(50), default="text")  # text, currency, date, percentage, number
    format_pattern = Column(String(100), nullable=True)  # e.g., "${:,.2f}" for currency

    # Fallback
    default_value = Column(Text, nullable=True)

    # Categorization
    category = Column(String(50), nullable=True)  # personal, loan, property, dates, team

    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=func.now())


# =============================================================================
# Content Publishing Log
# =============================================================================

class ContentPublishLog(Base):
    """Track content publishing across channels."""
    __tablename__ = "content_publish_logs"

    id = Column(String(50), primary_key=True, default=generate_uuid)
    brief_id = Column(String(50), ForeignKey("content_briefs.id"), nullable=True)
    content_item_id = Column(String(50), nullable=True)

    channel = Column(String(50), nullable=False)  # blog, linkedin, facebook, instagram, email

    # Publishing details
    scheduled_at = Column(DateTime, nullable=True)
    published_at = Column(DateTime, nullable=True)
    status = Column(String(50), default="pending")  # pending, scheduled, published, failed

    # External references
    external_post_id = Column(String(255), nullable=True)  # ID from the platform
    external_url = Column(Text, nullable=True)  # URL of published content

    # Results
    error_message = Column(Text, nullable=True)
    retry_count = Column(Integer, default=0)

    # Engagement metrics (updated periodically)
    views = Column(Integer, default=0)
    likes = Column(Integer, default=0)
    comments = Column(Integer, default=0)
    shares = Column(Integer, default=0)
    clicks = Column(Integer, default=0)

    metrics_updated_at = Column(DateTime, nullable=True)

    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
