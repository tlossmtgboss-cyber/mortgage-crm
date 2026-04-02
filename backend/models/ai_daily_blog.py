"""
AI Daily Blog + PDF Content Factory - SQLAlchemy Models
"""

import uuid
from datetime import datetime
from sqlalchemy import Column, String, Integer, Float, Boolean, DateTime, Text, ForeignKey, Index
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from database import Base


def gen_uuid() -> str:
    return str(uuid.uuid4())


class BlogVoiceProfile(Base):
    """Saved brand voice presets with sliders and toggles"""
    __tablename__ = "blog_voice_profiles"

    id = Column(String, primary_key=True, default=gen_uuid)
    user_id = Column(Integer, index=True)  # Logical reference to users, no FK constraint
    name = Column(String(255), nullable=False)
    sliders_json = Column(JSONB, default=dict)  # professional_casual, bold_conservative, etc.
    toggles_json = Column(JSONB, default=dict)  # use_emojis, use_hashtags, etc.
    examples_json = Column(JSONB, default=dict)  # Sample content for voice matching
    active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


class BlogComplianceProfile(Base):
    """Industry-specific compliance guardrails"""
    __tablename__ = "blog_compliance_profiles"

    id = Column(String, primary_key=True, default=gen_uuid)
    user_id = Column(Integer, index=True)  # Logical reference to users, no FK constraint
    name = Column(String(255), nullable=False)
    required_disclosures_json = Column(JSONB, default=list)  # Mandatory footer text
    banned_phrases_json = Column(JSONB, default=list)  # Prohibited words/phrases
    overrides_json = Column(JSONB, default=dict)
    active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class BlogSourceDocument(Base):
    """Uploaded PDFs, guides, training docs for content mining"""
    __tablename__ = "blog_source_documents"

    id = Column(String, primary_key=True, default=gen_uuid)
    user_id = Column(Integer, index=True)  # Logical reference to users, no FK constraint
    type = Column(String(50), default="pdf")
    title = Column(String(500), nullable=False)
    author = Column(String(255))
    file_path = Column(Text, nullable=False)
    file_size = Column(Integer, default=0)
    page_count = Column(Integer, default=0)
    extracted_text = Column(Text)
    page_map_json = Column(JSONB, default=dict)  # Page-to-text mapping
    concept_map_json = Column(JSONB, default=dict)  # Extracted concepts for mining
    rights_attestation = Column(Boolean, default=False)
    processed = Column(Boolean, default=False, index=True)
    processing_error = Column(Text)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    # Relationships
    content_items = relationship("BlogContentItem", back_populates="source_document")
    topics = relationship("BlogTopicQueue", back_populates="source_document")


class BlogCampaign(Base):
    """Organized content strategies with settings"""
    __tablename__ = "blog_campaigns"

    id = Column(String, primary_key=True, default=gen_uuid)
    user_id = Column(Integer, index=True)  # Logical reference to users, no FK constraint
    name = Column(String(255), nullable=False)
    brief_json = Column(JSONB, default=dict)  # Campaign goals, keywords, audience
    archetype_weights_json = Column(JSONB, default=dict)  # informative: 0.4, story: 0.2, etc.
    voice_profile_id = Column(String, ForeignKey("blog_voice_profiles.id"))
    compliance_profile_id = Column(String, ForeignKey("blog_compliance_profiles.id"))
    posting_mode = Column(String(50), default="draft")  # auto, schedule, draft, manual
    auto_schedule = Column(Boolean, default=False)
    posts_per_week = Column(Integer, default=3)
    active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    # Relationships
    content_items = relationship("BlogContentItem", back_populates="campaign")
    topics = relationship("BlogTopicQueue", back_populates="campaign")


class BlogContentItem(Base):
    """Generated blog posts and social content"""
    __tablename__ = "blog_content_items"

    id = Column(String, primary_key=True, default=gen_uuid)
    user_id = Column(Integer, index=True)  # Logical reference to users, no FK constraint
    campaign_id = Column(String, ForeignKey("blog_campaigns.id"), index=True)
    source_document_id = Column(String, ForeignKey("blog_source_documents.id"), index=True)
    status = Column(String(50), default="draft", index=True)  # draft, pending_approval, scheduled, published, archived
    scheduled_at = Column(DateTime, index=True)
    published_at = Column(DateTime)
    archetype = Column(String(50), default="informative")  # informative, story, data-driven, how-to, myth-busting
    title = Column(String(500), default="")
    slug = Column(String(500), default="", index=True)
    blog_md = Column(Text, default="")  # Full blog post in markdown
    blog_html = Column(Text, default="")  # Rendered HTML
    social_json = Column(JSONB, default=dict)  # {linkedin: "...", facebook: "...", instagram: "..."}
    image_url = Column(Text)
    image_prompt = Column(Text)
    metadata_json = Column(JSONB, default=dict)  # keyword, predicted_engagement, etc.
    source_trace_json = Column(JSONB, default=dict)  # Track what source text inspired this
    voice_profile_id = Column(String, ForeignKey("blog_voice_profiles.id"))
    compliance_profile_id = Column(String, ForeignKey("blog_compliance_profiles.id"))
    uniqueness_score = Column(Float)  # 0-1 how unique vs existing content
    engagement_score = Column(Float)  # Predicted engagement
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    campaign = relationship("BlogCampaign", back_populates="content_items")
    source_document = relationship("BlogSourceDocument", back_populates="content_items")
    images = relationship("BlogImageAsset", back_populates="content_item")
    publish_logs = relationship("BlogPublishLog", back_populates="content_item")
    performance = relationship("BlogPerformanceFeedback", back_populates="content_item")

    __table_args__ = (
        Index('ix_blog_content_user_status', 'user_id', 'status'),
        Index('ix_blog_content_scheduled', 'user_id', 'status', 'scheduled_at'),
    )


class BlogContentJob(Base):
    """Background processing jobs for content generation"""
    __tablename__ = "blog_content_jobs"

    id = Column(String, primary_key=True, default=gen_uuid)
    user_id = Column(Integer, index=True)  # Logical reference to users, no FK constraint
    type = Column(String(100), nullable=False, index=True)  # pdf_extract, batch_generate, daily_post, publish
    status = Column(String(50), default="queued", index=True)  # queued, processing, completed, failed
    payload_json = Column(JSONB, default=dict)
    result_json = Column(JSONB, default=dict)
    error = Column(Text)
    progress = Column(Integer, default=0)  # 0-100
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    started_at = Column(DateTime)
    completed_at = Column(DateTime)


class BlogImageAsset(Base):
    """Generated branded images"""
    __tablename__ = "blog_image_assets"

    id = Column(String, primary_key=True, default=gen_uuid)
    user_id = Column(Integer, index=True)  # Logical reference to users, no FK constraint
    content_item_id = Column(String, ForeignKey("blog_content_items.id"), index=True)
    provider = Column(String(50), default="template")  # template, dalle, midjourney
    prompt = Column(Text, default="")
    url = Column(Text, nullable=False)
    file_path = Column(Text)
    metadata_json = Column(JSONB, default=dict)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    # Relationships
    content_item = relationship("BlogContentItem", back_populates="images")


class BlogSocialConnection(Base):
    """Connected social platforms for publishing"""
    __tablename__ = "blog_social_connections"

    id = Column(String, primary_key=True, default=gen_uuid)
    user_id = Column(Integer, index=True)  # Logical reference to users, no FK constraint
    provider = Column(String(50), nullable=False)  # buffer, linkedin, facebook, instagram, twitter
    profile_id = Column(String(255), nullable=False)
    profile_name = Column(String(255))
    access_token_encrypted = Column(Text, nullable=False)
    refresh_token_encrypted = Column(Text)
    token_expires_at = Column(DateTime)
    channel_map_json = Column(JSONB, default=dict)
    status = Column(String(50), default="active")  # active, expired, revoked
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class BlogPublishLog(Base):
    """Record of all publishing attempts"""
    __tablename__ = "blog_publish_logs"

    id = Column(String, primary_key=True, default=gen_uuid)
    user_id = Column(Integer, index=True)  # Logical reference to users, no FK constraint
    content_item_id = Column(String, ForeignKey("blog_content_items.id"), index=True)
    platform = Column(String(50), nullable=False)
    status = Column(String(50), default="pending", index=True)  # pending, success, failed
    external_id = Column(String(255))
    external_url = Column(Text)
    response_json = Column(JSONB, default=dict)
    error = Column(Text)
    retry_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    completed_at = Column(DateTime)

    # Relationships
    content_item = relationship("BlogContentItem", back_populates="publish_logs")


class BlogTopicQueue(Base):
    """Pre-generated topic ideas for content"""
    __tablename__ = "blog_topic_queue"

    id = Column(String, primary_key=True, default=gen_uuid)
    user_id = Column(Integer, index=True)  # Logical reference to users, no FK constraint
    campaign_id = Column(String, ForeignKey("blog_campaigns.id"))
    source_document_id = Column(String, ForeignKey("blog_source_documents.id"))
    topic = Column(String(500), nullable=False)
    keyword = Column(String(255))
    angle = Column(Text)
    archetype = Column(String(50), default="informative")
    priority = Column(Integer, default=0)
    used = Column(Boolean, default=False, index=True)
    used_at = Column(DateTime)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    # Relationships
    campaign = relationship("BlogCampaign", back_populates="topics")
    source_document = relationship("BlogSourceDocument", back_populates="topics")


class BlogAuditLog(Base):
    """Audit trail for all content changes"""
    __tablename__ = "blog_audit_logs"

    id = Column(String, primary_key=True, default=gen_uuid)
    user_id = Column(Integer, index=True)  # Logical reference to users, no FK constraint
    action = Column(String(100), nullable=False)
    entity_type = Column(String(100), nullable=False)
    entity_id = Column(Text, nullable=False)
    before_json = Column(JSONB, default=dict)
    after_json = Column(JSONB, default=dict)
    ip_address = Column(String(50))
    user_agent = Column(Text)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        Index('ix_blog_audit_entity', 'entity_type', 'entity_id'),
    )


class BlogPerformanceFeedback(Base):
    """Track content performance for ML feedback loop"""
    __tablename__ = "blog_performance_feedback"

    id = Column(String, primary_key=True, default=gen_uuid)
    user_id = Column(Integer, index=True)  # Logical reference to users, no FK constraint
    content_item_id = Column(String, ForeignKey("blog_content_items.id"), index=True)
    platform = Column(String(50))
    views = Column(Integer, default=0)
    likes = Column(Integer, default=0)
    comments = Column(Integer, default=0)
    shares = Column(Integer, default=0)
    clicks = Column(Integer, default=0)
    leads_generated = Column(Integer, default=0)
    engagement_rate = Column(Float)
    fetched_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    # Relationships
    content_item = relationship("BlogContentItem", back_populates="performance")


class BlogUserSettings(Base):
    """Per-user blog configuration"""
    __tablename__ = "blog_user_settings"

    id = Column(String, primary_key=True, default=gen_uuid)
    user_id = Column(Integer, unique=True)  # Logical reference to users, no FK constraint
    default_voice_profile_id = Column(String, ForeignKey("blog_voice_profiles.id"))
    default_compliance_profile_id = Column(String, ForeignKey("blog_compliance_profiles.id"))
    posting_mode = Column(String(50), default="draft")  # auto, schedule, draft, manual
    auto_generate_daily = Column(Boolean, default=False)
    daily_generate_time = Column(String(10), default="06:00")
    timezone = Column(String(100), default="America/New_York")
    brand_logo_url = Column(Text)
    brand_colors_json = Column(JSONB, default=dict)
    llm_provider = Column(String(50), default="openai")
    llm_model = Column(String(100), default="gpt-4-turbo-preview")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
