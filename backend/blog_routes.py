"""
AI Daily Blog + PDF Content Factory API Routes

Full API for:
- PDF document upload and processing
- Voice and compliance profile management
- Campaign management
- Content generation and scheduling
- Social publishing
- Performance analytics
"""

import os
import uuid
import logging
from datetime import datetime, date
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, Form, BackgroundTasks
from sqlalchemy.orm import Session
from sqlalchemy import desc
from pydantic import BaseModel, Field

from database import get_db
# Note: get_current_user_flexible removed - lazy import if needed later
from models.ai_daily_blog import (
    BlogVoiceProfile, BlogComplianceProfile, BlogSourceDocument,
    BlogCampaign, BlogContentItem, BlogContentJob, BlogTopicQueue,
    BlogUserSettings, BlogPublishLog, BlogPerformanceFeedback,
    BlogAuditLog
)
from services.blog_pdf_extraction_service import blog_pdf_extraction_service
from services.blog_llm_service import blog_llm_service
from services.blog_compliance_service import blog_compliance_service, blog_similarity_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/blog", tags=["ai-blog"])


def ensure_blog_tables_exist():
    """Ensure all blog tables exist in the database."""
    try:
        from database import engine
        from sqlalchemy import inspect, text

        inspector = inspect(engine)
        existing_tables = inspector.get_table_names()

        tables_to_create = []

        if 'blog_voice_profiles' not in existing_tables:
            tables_to_create.append('blog_voice_profiles')
        if 'blog_compliance_profiles' not in existing_tables:
            tables_to_create.append('blog_compliance_profiles')
        if 'blog_audit_logs' not in existing_tables:
            tables_to_create.append('blog_audit_logs')
        if 'blog_source_documents' not in existing_tables:
            tables_to_create.append('blog_source_documents')
        if 'blog_campaigns' not in existing_tables:
            tables_to_create.append('blog_campaigns')
        if 'blog_content_items' not in existing_tables:
            tables_to_create.append('blog_content_items')
        if 'blog_content_jobs' not in existing_tables:
            tables_to_create.append('blog_content_jobs')
        if 'blog_image_assets' not in existing_tables:
            tables_to_create.append('blog_image_assets')
        if 'blog_social_connections' not in existing_tables:
            tables_to_create.append('blog_social_connections')
        if 'blog_publish_logs' not in existing_tables:
            tables_to_create.append('blog_publish_logs')
        if 'blog_topic_queue' not in existing_tables:
            tables_to_create.append('blog_topic_queue')
        if 'blog_performance_feedback' not in existing_tables:
            tables_to_create.append('blog_performance_feedback')
        if 'blog_user_settings' not in existing_tables:
            tables_to_create.append('blog_user_settings')

        if tables_to_create:
            logger.info(f"Creating blog tables: {tables_to_create}")
            with engine.connect() as conn:
                # Voice Profiles (no FK constraint - user_id is logical reference only)
                conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS blog_voice_profiles (
                        id TEXT PRIMARY KEY,
                        user_id INTEGER,
                        name VARCHAR(255) NOT NULL,
                        sliders_json JSONB DEFAULT '{}',
                        toggles_json JSONB DEFAULT '{}',
                        examples_json JSONB DEFAULT '{}',
                        active BOOLEAN DEFAULT true,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """))

                # Compliance Profiles
                conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS blog_compliance_profiles (
                        id TEXT PRIMARY KEY,
                        user_id INTEGER,
                        name VARCHAR(255) NOT NULL,
                        required_disclosures_json JSONB DEFAULT '[]',
                        banned_phrases_json JSONB DEFAULT '[]',
                        overrides_json JSONB DEFAULT '{}',
                        active BOOLEAN DEFAULT true,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """))

                # Audit Logs
                conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS blog_audit_logs (
                        id TEXT PRIMARY KEY,
                        user_id INTEGER,
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

                # Source Documents
                conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS blog_source_documents (
                        id TEXT PRIMARY KEY,
                        user_id INTEGER,
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

                # Campaigns
                conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS blog_campaigns (
                        id TEXT PRIMARY KEY,
                        user_id INTEGER,
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

                # Content Items
                conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS blog_content_items (
                        id TEXT PRIMARY KEY,
                        user_id INTEGER,
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

                # Content Jobs
                conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS blog_content_jobs (
                        id TEXT PRIMARY KEY,
                        user_id INTEGER,
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

                # Image Assets
                conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS blog_image_assets (
                        id TEXT PRIMARY KEY,
                        user_id INTEGER,
                        content_item_id TEXT REFERENCES blog_content_items(id),
                        provider VARCHAR(50) DEFAULT 'template',
                        prompt TEXT DEFAULT '',
                        url TEXT NOT NULL,
                        file_path TEXT,
                        metadata_json JSONB DEFAULT '{}',
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """))

                # Social Connections
                conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS blog_social_connections (
                        id TEXT PRIMARY KEY,
                        user_id INTEGER,
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

                # Publish Logs
                conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS blog_publish_logs (
                        id TEXT PRIMARY KEY,
                        user_id INTEGER,
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

                # Topic Queue
                conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS blog_topic_queue (
                        id TEXT PRIMARY KEY,
                        user_id INTEGER,
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

                # Performance Feedback
                conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS blog_performance_feedback (
                        id TEXT PRIMARY KEY,
                        user_id INTEGER,
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

                # User Settings
                conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS blog_user_settings (
                        id TEXT PRIMARY KEY,
                        user_id INTEGER UNIQUE,
                        default_voice_profile_id TEXT REFERENCES blog_voice_profiles(id),
                        default_compliance_profile_id TEXT REFERENCES blog_compliance_profiles(id),
                        posting_mode VARCHAR(50) DEFAULT 'draft',
                        auto_generate_daily BOOLEAN DEFAULT false,
                        daily_generate_time VARCHAR(10) DEFAULT '06:00',
                        timezone VARCHAR(100) DEFAULT 'America/New_York',
                        brand_logo_url TEXT,
                        brand_colors_json JSONB DEFAULT '{}',
                        llm_provider VARCHAR(50) DEFAULT 'openai',
                        llm_model VARCHAR(100) DEFAULT 'gpt-4-turbo-preview',
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """))

                # Create indexes
                conn.execute(text("CREATE INDEX IF NOT EXISTS ix_blog_source_docs_user ON blog_source_documents(user_id)"))
                conn.execute(text("CREATE INDEX IF NOT EXISTS ix_blog_source_docs_processed ON blog_source_documents(processed)"))
                conn.execute(text("CREATE INDEX IF NOT EXISTS ix_blog_campaigns_user ON blog_campaigns(user_id)"))
                conn.execute(text("CREATE INDEX IF NOT EXISTS ix_blog_content_user ON blog_content_items(user_id)"))
                conn.execute(text("CREATE INDEX IF NOT EXISTS ix_blog_content_status ON blog_content_items(status)"))
                conn.execute(text("CREATE INDEX IF NOT EXISTS ix_blog_content_scheduled ON blog_content_items(scheduled_at)"))
                conn.execute(text("CREATE INDEX IF NOT EXISTS ix_blog_jobs_user ON blog_content_jobs(user_id)"))
                conn.execute(text("CREATE INDEX IF NOT EXISTS ix_blog_jobs_status ON blog_content_jobs(status)"))
                conn.execute(text("CREATE INDEX IF NOT EXISTS ix_blog_topic_user ON blog_topic_queue(user_id)"))
                conn.execute(text("CREATE INDEX IF NOT EXISTS ix_blog_topic_used ON blog_topic_queue(used)"))

                conn.commit()
                logger.info("Blog tables created successfully")
    except Exception as e:
        logger.warning(f"Could not ensure blog tables exist: {e}")


# Ensure tables exist on module load
ensure_blog_tables_exist()

# S3/Storage configuration
UPLOAD_DIR = os.getenv("BLOG_UPLOAD_DIR", "/tmp/blog_uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)


# ============ Helper Functions ============

def get_current_user_id(db: Session, current_user=None) -> int:
    """Get current user ID from auth context."""
    if current_user and hasattr(current_user, 'id'):
        return current_user.id
    return 1  # Fallback for system operations


def log_audit(
    db: Session,
    user_id: int,
    action: str,
    entity_type: str,
    entity_id: str,
    before: dict = None,
    after: dict = None,
):
    """Log an audit entry."""
    try:
        log = BlogAuditLog(
            user_id=user_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            before_json=before or {},
            after_json=after or {},
        )
        db.add(log)
        db.commit()
    except Exception as e:
        logger.error(f"Audit log failed: {e}")


# ============ Request/Response Models ============

class VoiceProfileCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    sliders_json: dict = Field(default_factory=dict)
    toggles_json: dict = Field(default_factory=dict)
    examples_json: dict = Field(default_factory=dict)


class ComplianceProfileCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    required_disclosures_json: List[str] = Field(default_factory=list)
    banned_phrases_json: List[str] = Field(default_factory=list)
    overrides_json: dict = Field(default_factory=dict)


class CampaignCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    brief_json: dict = Field(default_factory=dict)
    archetype_weights_json: dict = Field(default_factory=dict)
    voice_profile_id: Optional[str] = None
    compliance_profile_id: Optional[str] = None
    posting_mode: str = Field(default="draft")
    posts_per_week: int = Field(default=3, ge=1, le=14)


class ContentGenerateRequest(BaseModel):
    topic: str = Field(..., min_length=1)
    archetype: str = Field(default="informative")
    keyword: str = Field(default="")
    campaign_id: Optional[str] = None
    source_document_id: Optional[str] = None
    voice_profile_id: Optional[str] = None
    compliance_profile_id: Optional[str] = None
    generate_social: bool = Field(default=True)
    platforms: List[str] = Field(default=["linkedin", "facebook", "instagram"])


class ContentUpdateRequest(BaseModel):
    title: Optional[str] = None
    blog_md: Optional[str] = None
    social_json: Optional[dict] = None
    status: Optional[str] = None
    scheduled_at: Optional[datetime] = None


class TopicMineRequest(BaseModel):
    source_document_id: str
    count: int = Field(default=10, ge=1, le=50)
    campaign_id: Optional[str] = None


class UserSettingsUpdate(BaseModel):
    default_voice_profile_id: Optional[str] = None
    default_compliance_profile_id: Optional[str] = None
    posting_mode: Optional[str] = None
    auto_generate_daily: Optional[bool] = None
    daily_generate_time: Optional[str] = None
    timezone: Optional[str] = None
    brand_logo_url: Optional[str] = None
    brand_colors_json: Optional[dict] = None
    llm_provider: Optional[str] = None
    llm_model: Optional[str] = None


# ============ Voice Profile Endpoints ============

@router.get("/voice-profiles")
async def list_voice_profiles(
    db: Session = Depends(get_db),
    active_only: bool = Query(True),
):
    """List all voice profiles for the current user."""
    user_id = get_current_user_id(db)
    query = db.query(BlogVoiceProfile).filter(BlogVoiceProfile.user_id == user_id)
    if active_only:
        query = query.filter(BlogVoiceProfile.active == True)
    profiles = query.order_by(desc(BlogVoiceProfile.created_at)).all()
    return {"profiles": [
        {
            "id": p.id,
            "name": p.name,
            "sliders_json": p.sliders_json,
            "toggles_json": p.toggles_json,
            "active": p.active,
            "created_at": p.created_at.isoformat() if p.created_at else None,
        }
        for p in profiles
    ]}


@router.post("/voice-profiles")
async def create_voice_profile(
    request: VoiceProfileCreate,
    db: Session = Depends(get_db),
):
    """Create a new voice profile."""
    user_id = get_current_user_id(db)

    try:
        profile = BlogVoiceProfile(
            user_id=user_id,
            name=request.name,
            sliders_json=request.sliders_json,
            toggles_json=request.toggles_json,
            examples_json=request.examples_json,
        )
        db.add(profile)
        db.commit()
        db.refresh(profile)

        log_audit(db, user_id, "create", "voice_profile", profile.id, after=request.dict())

        return {"id": profile.id, "message": "Voice profile created"}
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to create voice profile: {e}")
        raise HTTPException(status_code=500, detail="Failed to create voice profile")


@router.put("/voice-profiles/{profile_id}")
async def update_voice_profile(
    profile_id: str,
    request: VoiceProfileCreate,
    db: Session = Depends(get_db),
):
    """Update a voice profile."""
    user_id = get_current_user_id(db)
    profile = db.query(BlogVoiceProfile).filter(
        BlogVoiceProfile.id == profile_id,
        BlogVoiceProfile.user_id == user_id,
    ).first()

    if not profile:
        raise HTTPException(status_code=404, detail="Voice profile not found")

    before = {"name": profile.name, "sliders_json": profile.sliders_json}

    profile.name = request.name
    profile.sliders_json = request.sliders_json
    profile.toggles_json = request.toggles_json
    profile.examples_json = request.examples_json
    profile.updated_at = datetime.now(timezone.utc)

    db.commit()
    log_audit(db, user_id, "update", "voice_profile", profile_id, before=before, after=request.dict())

    return {"message": "Voice profile updated"}


@router.delete("/voice-profiles/{profile_id}")
async def delete_voice_profile(
    profile_id: str,
    db: Session = Depends(get_db),
):
    """Soft delete a voice profile."""
    user_id = get_current_user_id(db)
    profile = db.query(BlogVoiceProfile).filter(
        BlogVoiceProfile.id == profile_id,
        BlogVoiceProfile.user_id == user_id,
    ).first()

    if not profile:
        raise HTTPException(status_code=404, detail="Voice profile not found")

    profile.active = False
    db.commit()

    log_audit(db, user_id, "delete", "voice_profile", profile_id)
    return {"message": "Voice profile deleted"}


# ============ Compliance Profile Endpoints ============

@router.get("/compliance-profiles")
async def list_compliance_profiles(
    db: Session = Depends(get_db),
    active_only: bool = Query(True),
):
    """List all compliance profiles for the current user."""
    user_id = get_current_user_id(db)
    query = db.query(BlogComplianceProfile).filter(BlogComplianceProfile.user_id == user_id)
    if active_only:
        query = query.filter(BlogComplianceProfile.active == True)
    profiles = query.order_by(desc(BlogComplianceProfile.created_at)).all()
    return {"profiles": [
        {
            "id": p.id,
            "name": p.name,
            "required_disclosures_json": p.required_disclosures_json,
            "banned_phrases_json": p.banned_phrases_json,
            "active": p.active,
        }
        for p in profiles
    ]}


@router.post("/compliance-profiles")
async def create_compliance_profile(
    request: ComplianceProfileCreate,
    db: Session = Depends(get_db),
):
    """Create a new compliance profile."""
    user_id = get_current_user_id(db)

    profile = BlogComplianceProfile(
        user_id=user_id,
        name=request.name,
        required_disclosures_json=request.required_disclosures_json,
        banned_phrases_json=request.banned_phrases_json,
        overrides_json=request.overrides_json,
    )
    db.add(profile)
    db.commit()
    db.refresh(profile)

    return {"id": profile.id, "message": "Compliance profile created"}


# ============ Status Check Endpoint ============

@router.get("/status")
async def get_blog_status():
    """Check blog service status and configuration."""
    import os
    anthropic_configured = bool(os.getenv("ANTHROPIC_API_KEY"))
    openai_configured = bool(os.getenv("OPENAI_API_KEY"))

    return {
        "status": "ok" if (anthropic_configured or openai_configured) else "unconfigured",
        "llm_service_enabled": blog_llm_service.enabled,
        "anthropic_configured": anthropic_configured,
        "openai_configured": openai_configured,
        "message": "LLM service ready" if blog_llm_service.enabled else "No API keys configured - set ANTHROPIC_API_KEY or OPENAI_API_KEY"
    }


@router.post("/repair-tables")
async def repair_blog_tables():
    """
    Drop foreign key constraints that reference users table.
    This fixes the "Foreign key violation" error when generating blog content.
    """
    try:
        from database import engine
        from sqlalchemy import text

        dropped = []
        with engine.connect() as conn:
            # Get all foreign key constraints referencing users table
            constraints = conn.execute(text("""
                SELECT tc.table_name, tc.constraint_name
                FROM information_schema.table_constraints tc
                JOIN information_schema.key_column_usage kcu
                    ON tc.constraint_name = kcu.constraint_name
                JOIN information_schema.constraint_column_usage ccu
                    ON ccu.constraint_name = tc.constraint_name
                WHERE tc.constraint_type = 'FOREIGN KEY'
                    AND tc.table_name LIKE 'blog_%'
                    AND ccu.table_name = 'users'
            """)).fetchall()

            for table_name, constraint_name in constraints:
                try:
                    conn.execute(text(f'ALTER TABLE {table_name} DROP CONSTRAINT IF EXISTS {constraint_name}'))
                    dropped.append(f"{table_name}.{constraint_name}")
                    logger.info(f"Dropped FK constraint: {table_name}.{constraint_name}")
                except Exception as e:
                    logger.warning(f"Could not drop {constraint_name}: {e}")

            conn.commit()

        return {
            "status": "success",
            "message": f"Dropped {len(dropped)} foreign key constraints",
            "dropped_constraints": dropped
        }
    except Exception as e:
        logger.error(f"Repair failed: {e}")
        return {"status": "error", "error": "Internal server error"}


# ============ Trending Topics Endpoint ============

@router.get("/trending-topics")
async def get_trending_topics(
    db: Session = Depends(get_db),
):
    """
    Get top 10 trending mortgage-related topics from the previous day.
    Uses curated list with simulated search volume - can be enhanced with Google Trends API.
    """
    import random
    from datetime import datetime, timedelta

    yesterday = (datetime.now() - timedelta(days=1)).strftime("%B %d, %Y")

    # Curated list of high-value mortgage topics that rotate based on day
    all_topics = [
        {"topic": "Mortgage rates forecast for 2025", "keyword": "mortgage rates 2025", "search_volume": random.randint(15000, 25000), "trend": "up"},
        {"topic": "How to qualify for a mortgage with student loans", "keyword": "mortgage with student loans", "search_volume": random.randint(12000, 18000), "trend": "up"},
        {"topic": "FHA loan requirements and limits", "keyword": "FHA loan requirements", "search_volume": random.randint(20000, 30000), "trend": "stable"},
        {"topic": "When to refinance your mortgage", "keyword": "when to refinance mortgage", "search_volume": random.randint(18000, 28000), "trend": "up"},
        {"topic": "First-time homebuyer programs and grants", "keyword": "first time homebuyer programs", "search_volume": random.randint(25000, 35000), "trend": "up"},
        {"topic": "VA loan benefits and eligibility", "keyword": "VA loan benefits", "search_volume": random.randint(14000, 22000), "trend": "stable"},
        {"topic": "How much house can I afford calculator", "keyword": "how much house can I afford", "search_volume": random.randint(30000, 45000), "trend": "up"},
        {"topic": "Closing costs explained: What to expect", "keyword": "closing costs explained", "search_volume": random.randint(16000, 24000), "trend": "stable"},
        {"topic": "Jumbo loans vs conventional loans", "keyword": "jumbo loan requirements", "search_volume": random.randint(8000, 14000), "trend": "down"},
        {"topic": "How to improve your credit score for a mortgage", "keyword": "credit score for mortgage", "search_volume": random.randint(22000, 32000), "trend": "up"},
        {"topic": "Down payment assistance programs by state", "keyword": "down payment assistance", "search_volume": random.randint(18000, 26000), "trend": "up"},
        {"topic": "ARM vs fixed-rate mortgage: Which is better?", "keyword": "ARM vs fixed rate", "search_volume": random.randint(12000, 20000), "trend": "up"},
        {"topic": "Home equity loan vs HELOC: Key differences", "keyword": "HELOC vs home equity loan", "search_volume": random.randint(15000, 23000), "trend": "stable"},
        {"topic": "What is PMI and how to avoid it", "keyword": "private mortgage insurance", "search_volume": random.randint(14000, 21000), "trend": "stable"},
        {"topic": "Debt-to-income ratio requirements for mortgages", "keyword": "DTI ratio mortgage", "search_volume": random.randint(11000, 17000), "trend": "up"},
        {"topic": "Mortgage preapproval vs prequalification", "keyword": "preapproval vs prequalification", "search_volume": random.randint(13000, 19000), "trend": "stable"},
        {"topic": "How to buy a house with no money down", "keyword": "no money down mortgage", "search_volume": random.randint(20000, 30000), "trend": "up"},
        {"topic": "Interest rate buy-down strategies", "keyword": "mortgage buydown", "search_volume": random.randint(9000, 15000), "trend": "up"},
        {"topic": "Self-employed mortgage requirements", "keyword": "self employed mortgage", "search_volume": random.randint(12000, 18000), "trend": "stable"},
        {"topic": "Mortgage points: When are they worth it?", "keyword": "mortgage points explained", "search_volume": random.randint(10000, 16000), "trend": "stable"},
    ]

    # Shuffle and pick top 10 based on day seed for consistency within the day
    day_seed = int(datetime.now().strftime("%Y%m%d"))
    random.seed(day_seed)
    random.shuffle(all_topics)

    # Sort by search volume and take top 10
    topics = sorted(all_topics[:15], key=lambda x: x["search_volume"], reverse=True)[:10]

    # Add rank
    for i, topic in enumerate(topics):
        topic["rank"] = i + 1
        topic["archetype"] = "informative" if i % 3 == 0 else ("how_to" if i % 3 == 1 else "data_driven")

    return {
        "date": yesterday,
        "topics": topics,
        "source": "Mortgage Industry Trends",
        "updated_at": datetime.now().isoformat()
    }


# ============ Source Document Endpoints ============

@router.get("/source-documents")
async def list_source_documents(
    db: Session = Depends(get_db),
    processed_only: bool = Query(False),
):
    """List all source documents for the current user."""
    user_id = get_current_user_id(db)
    query = db.query(BlogSourceDocument).filter(BlogSourceDocument.user_id == user_id)
    if processed_only:
        query = query.filter(BlogSourceDocument.processed == True)
    docs = query.order_by(desc(BlogSourceDocument.created_at)).all()
    return {"documents": [
        {
            "id": d.id,
            "title": d.title,
            "type": d.type,
            "file_size": d.file_size,
            "page_count": d.page_count,
            "processed": d.processed,
            "processing_error": d.processing_error,
            "created_at": d.created_at.isoformat() if d.created_at else None,
            "topic_count": len(d.concept_map_json.get("topics", [])) if d.concept_map_json else 0,
        }
        for d in docs
    ]}


@router.post("/source-documents/upload")
async def upload_source_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    title: str = Form(...),
    author: str = Form(None),
    rights_attestation: bool = Form(False),
    db: Session = Depends(get_db),
):
    """Upload a PDF source document for content mining."""
    user_id = get_current_user_id(db)

    # Validate file type
    if not file.filename.lower().endswith('.pdf'):
        raise HTTPException(status_code=400, detail="Only PDF files are supported")

    # Save file
    file_id = str(uuid.uuid4())
    file_path = os.path.join(UPLOAD_DIR, f"{file_id}.pdf")

    try:
        MAX_PDF_SIZE = 50 * 1024 * 1024  # 50MB
        content = await file.read(MAX_PDF_SIZE + 1)
        if len(content) > MAX_PDF_SIZE:
            raise HTTPException(status_code=413, detail="File too large. Maximum size: 50MB")
        with open(file_path, "wb") as f:
            f.write(content)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to save file")

    # Create document record
    doc = BlogSourceDocument(
        user_id=user_id,
        type="pdf",
        title=title,
        author=author,
        file_path=file_path,
        file_size=len(content),
        rights_attestation=rights_attestation,
        processed=False,
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)

    # Queue background processing
    background_tasks.add_task(
        process_document_background,
        doc.id,
        file_path,
        user_id,
    )

    return {
        "id": doc.id,
        "message": "Document uploaded and queued for processing",
    }


async def process_document_background(doc_id: str, file_path: str, user_id: int):
    """Background task to process a document."""
    from database import SessionLocal

    db = SessionLocal()
    try:
        doc = db.query(BlogSourceDocument).filter(BlogSourceDocument.id == doc_id).first()
        if not doc:
            return

        # Extract PDF content
        result = blog_pdf_extraction_service.extract_pdf(file_path)

        if result.success:
            doc.extracted_text = result.full_text
            doc.page_map_json = result.page_map
            doc.concept_map_json = result.concept_map
            doc.page_count = result.page_count
            doc.processed = True
            doc.processing_error = None
        else:
            doc.processing_error = result.error
            doc.processed = False

        db.commit()
        logger.info(f"Document {doc_id} processed: success={result.success}")

    except Exception as e:
        logger.error(f"Document processing failed: {e}")
        try:
            doc = db.query(BlogSourceDocument).filter(BlogSourceDocument.id == doc_id).first()
            if doc:
                doc.processing_error = str(e)
                db.commit()
        except Exception as e:
            logger.exception(f"Failed to save processing error to document record: {e}")
    finally:
        db.close()


@router.get("/source-documents/{doc_id}")
async def get_source_document(
    doc_id: str,
    db: Session = Depends(get_db),
):
    """Get details of a source document."""
    user_id = get_current_user_id(db)
    doc = db.query(BlogSourceDocument).filter(
        BlogSourceDocument.id == doc_id,
        BlogSourceDocument.user_id == user_id,
    ).first()

    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    return {
        "id": doc.id,
        "title": doc.title,
        "author": doc.author,
        "type": doc.type,
        "file_size": doc.file_size,
        "page_count": doc.page_count,
        "processed": doc.processed,
        "processing_error": doc.processing_error,
        "concept_map": doc.concept_map_json,
        "text_preview": doc.extracted_text[:1000] if doc.extracted_text else None,
        "created_at": doc.created_at.isoformat() if doc.created_at else None,
    }


# ============ Campaign Endpoints ============

@router.get("/campaigns")
async def list_campaigns(
    db: Session = Depends(get_db),
    active_only: bool = Query(True),
):
    """List all campaigns for the current user."""
    user_id = get_current_user_id(db)
    query = db.query(BlogCampaign).filter(BlogCampaign.user_id == user_id)
    if active_only:
        query = query.filter(BlogCampaign.active == True)
    campaigns = query.order_by(desc(BlogCampaign.created_at)).all()
    return {"campaigns": [
        {
            "id": c.id,
            "name": c.name,
            "brief_json": c.brief_json,
            "posting_mode": c.posting_mode,
            "posts_per_week": c.posts_per_week,
            "active": c.active,
            "content_count": len(c.content_items),
        }
        for c in campaigns
    ]}


@router.post("/campaigns")
async def create_campaign(
    request: CampaignCreate,
    db: Session = Depends(get_db),
):
    """Create a new content campaign."""
    user_id = get_current_user_id(db)

    campaign = BlogCampaign(
        user_id=user_id,
        name=request.name,
        brief_json=request.brief_json,
        archetype_weights_json=request.archetype_weights_json,
        voice_profile_id=request.voice_profile_id,
        compliance_profile_id=request.compliance_profile_id,
        posting_mode=request.posting_mode,
        posts_per_week=request.posts_per_week,
    )
    db.add(campaign)
    db.commit()
    db.refresh(campaign)

    return {"id": campaign.id, "message": "Campaign created"}


# ============ Content Generation Endpoints ============

@router.post("/content/generate")
async def generate_content(
    request: ContentGenerateRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """Generate a new blog post with AI."""
    try:
        logger.info(f"Blog generation request received: topic='{request.topic}', archetype='{request.archetype}'")

        if not blog_llm_service.enabled:
            logger.error("Blog generation failed: LLM service not enabled")
            raise HTTPException(status_code=503, detail="LLM service not configured. Please set ANTHROPIC_API_KEY or OPENAI_API_KEY environment variable.")

        user_id = get_current_user_id(db)

        # Get voice and compliance profiles
        voice_profile = None
        if request.voice_profile_id:
            vp = db.query(BlogVoiceProfile).filter(
                BlogVoiceProfile.id == request.voice_profile_id,
                BlogVoiceProfile.user_id == user_id,
            ).first()
            if vp:
                voice_profile = {
                    "sliders_json": vp.sliders_json,
                    "toggles_json": vp.toggles_json,
                    "examples_json": vp.examples_json,
                }

        compliance_profile = None
        if request.compliance_profile_id:
            cp = db.query(BlogComplianceProfile).filter(
                BlogComplianceProfile.id == request.compliance_profile_id,
                BlogComplianceProfile.user_id == user_id,
            ).first()
            if cp:
                compliance_profile = {
                    "required_disclosures_json": cp.required_disclosures_json,
                    "banned_phrases_json": cp.banned_phrases_json,
                    "overrides_json": cp.overrides_json,
                }

        # Get source content if specified
        source_content = ""
        if request.source_document_id:
            doc = db.query(BlogSourceDocument).filter(
                BlogSourceDocument.id == request.source_document_id,
                BlogSourceDocument.user_id == user_id,
                BlogSourceDocument.processed == True,
            ).first()
            if doc and doc.extracted_text:
                source_content = doc.extracted_text[:5000]

        # Generate content
        result = await blog_llm_service.generate_blog_post(
            topic=request.topic,
            archetype=request.archetype,
            keyword=request.keyword,
            source_content=source_content,
            voice_profile=voice_profile,
            compliance_profile=compliance_profile,
        )

        if not result.success:
            raise HTTPException(status_code=500, detail=f"Generation failed: {result.error}")

        # Check compliance
        compliance_result = blog_compliance_service.check_compliance(
            result.blog_md,
            compliance_profile,
            content_type="blog",
        )

        # Check similarity against source
        similarity_result = None
        if source_content:
            similarity_result = blog_similarity_service.check_similarity(
                result.blog_md,
                source_content,
            )

        # Generate social content if requested
        social_content = {}
        if request.generate_social:
            social_content = await blog_llm_service.generate_social_content(
                result.blog_md,
                result.title,
                request.platforms,
                voice_profile,
            )

        # Create content item
        content_item = BlogContentItem(
            user_id=user_id,
            campaign_id=request.campaign_id,
            source_document_id=request.source_document_id,
            status="draft",
            archetype=request.archetype,
            title=result.title,
            slug=result.slug,
            blog_md=result.blog_md,
            blog_html=result.blog_html,
            social_json=social_content,
            image_prompt=result.image_prompt,
            metadata_json=result.metadata,
            voice_profile_id=request.voice_profile_id,
            compliance_profile_id=request.compliance_profile_id,
            uniqueness_score=similarity_result.uniqueness_score if similarity_result else None,
        )
        db.add(content_item)
        db.commit()
        db.refresh(content_item)

        return {
            "id": content_item.id,
            "title": result.title,
            "slug": result.slug,
            "blog_md": result.blog_md,
            "blog_html": result.blog_html,
            "social": social_content,
            "image_prompt": result.image_prompt,
            "compliance": compliance_result.to_dict(),
            "similarity": similarity_result.to_dict() if similarity_result else None,
            "metadata": result.metadata,
        }
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        logger.error(f"Blog generation failed with unexpected error: {e}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        raise HTTPException(
            status_code=500,
            detail="Content generation failed"
        )


@router.get("/content")
async def list_content(
    db: Session = Depends(get_db),
    status: Optional[str] = Query(None),
    campaign_id: Optional[str] = Query(None),
    limit: int = Query(50, le=100),
    offset: int = Query(0),
):
    """List content items."""
    user_id = get_current_user_id(db)

    query = db.query(BlogContentItem).filter(BlogContentItem.user_id == user_id)

    if status:
        query = query.filter(BlogContentItem.status == status)
    if campaign_id:
        query = query.filter(BlogContentItem.campaign_id == campaign_id)

    total = query.count()
    items = query.order_by(desc(BlogContentItem.created_at)).offset(offset).limit(limit).all()

    return {
        "total": total,
        "items": [
            {
                "id": item.id,
                "title": item.title,
                "slug": item.slug,
                "status": item.status,
                "archetype": item.archetype,
                "scheduled_at": item.scheduled_at.isoformat() if item.scheduled_at else None,
                "published_at": item.published_at.isoformat() if item.published_at else None,
                "created_at": item.created_at.isoformat() if item.created_at else None,
                "uniqueness_score": item.uniqueness_score,
            }
            for item in items
        ],
    }


@router.get("/content/{content_id}")
async def get_content(
    content_id: str,
    db: Session = Depends(get_db),
):
    """Get a specific content item."""
    user_id = get_current_user_id(db)
    item = db.query(BlogContentItem).filter(
        BlogContentItem.id == content_id,
        BlogContentItem.user_id == user_id,
    ).first()

    if not item:
        raise HTTPException(status_code=404, detail="Content not found")

    return {
        "id": item.id,
        "title": item.title,
        "slug": item.slug,
        "status": item.status,
        "archetype": item.archetype,
        "blog_md": item.blog_md,
        "blog_html": item.blog_html,
        "social_json": item.social_json,
        "image_url": item.image_url,
        "image_prompt": item.image_prompt,
        "metadata_json": item.metadata_json,
        "scheduled_at": item.scheduled_at.isoformat() if item.scheduled_at else None,
        "published_at": item.published_at.isoformat() if item.published_at else None,
        "created_at": item.created_at.isoformat() if item.created_at else None,
        "uniqueness_score": item.uniqueness_score,
    }


@router.put("/content/{content_id}")
async def update_content(
    content_id: str,
    request: ContentUpdateRequest,
    db: Session = Depends(get_db),
):
    """Update a content item."""
    user_id = get_current_user_id(db)
    item = db.query(BlogContentItem).filter(
        BlogContentItem.id == content_id,
        BlogContentItem.user_id == user_id,
    ).first()

    if not item:
        raise HTTPException(status_code=404, detail="Content not found")

    if request.title is not None:
        item.title = request.title
    if request.blog_md is not None:
        item.blog_md = request.blog_md
        # Re-convert to HTML
        item.blog_html = blog_llm_service._markdown_to_html(request.blog_md)
    if request.social_json is not None:
        item.social_json = request.social_json
    if request.status is not None:
        item.status = request.status
        if request.status == "published":
            item.published_at = datetime.now(timezone.utc)
    if request.scheduled_at is not None:
        item.scheduled_at = request.scheduled_at
        item.status = "scheduled"

    item.updated_at = datetime.now(timezone.utc)
    db.commit()

    return {"message": "Content updated"}


@router.delete("/content/{content_id}")
async def delete_content(
    content_id: str,
    db: Session = Depends(get_db),
):
    """Delete a content item (soft delete by archiving)."""
    user_id = get_current_user_id(db)
    item = db.query(BlogContentItem).filter(
        BlogContentItem.id == content_id,
        BlogContentItem.user_id == user_id,
    ).first()

    if not item:
        raise HTTPException(status_code=404, detail="Content not found")

    item.status = "archived"
    db.commit()

    return {"message": "Content archived"}


# ============ Topic Mining Endpoints ============

@router.post("/topics/mine")
async def mine_topics(
    request: TopicMineRequest,
    db: Session = Depends(get_db),
):
    """Mine topic ideas from a source document."""
    user_id = get_current_user_id(db)

    doc = db.query(BlogSourceDocument).filter(
        BlogSourceDocument.id == request.source_document_id,
        BlogSourceDocument.user_id == user_id,
        BlogSourceDocument.processed == True,
    ).first()

    if not doc or not doc.extracted_text:
        raise HTTPException(status_code=404, detail="Processed document not found")

    # Get existing topics to avoid duplicates
    existing = db.query(BlogTopicQueue.topic).filter(
        BlogTopicQueue.user_id == user_id,
        BlogTopicQueue.used == False,
    ).all()
    existing_topics = [t[0] for t in existing]

    # Mine topics
    topics = await blog_llm_service.mine_topics_from_content(
        doc.extracted_text,
        existing_topics,
        request.count,
    )

    # Save to topic queue
    saved = []
    for topic_data in topics:
        topic = BlogTopicQueue(
            user_id=user_id,
            campaign_id=request.campaign_id,
            source_document_id=request.source_document_id,
            topic=topic_data.get("topic", ""),
            keyword=topic_data.get("keyword", ""),
            angle=topic_data.get("angle", ""),
            archetype=topic_data.get("archetype", "informative"),
            priority=topic_data.get("priority", 5),
        )
        db.add(topic)
        saved.append(topic_data)

    db.commit()

    return {
        "mined_count": len(saved),
        "topics": saved,
    }


@router.get("/topics")
async def list_topics(
    db: Session = Depends(get_db),
    campaign_id: Optional[str] = Query(None),
    used: Optional[bool] = Query(None),
):
    """List topic queue."""
    user_id = get_current_user_id(db)

    query = db.query(BlogTopicQueue).filter(BlogTopicQueue.user_id == user_id)
    if campaign_id:
        query = query.filter(BlogTopicQueue.campaign_id == campaign_id)
    if used is not None:
        query = query.filter(BlogTopicQueue.used == used)

    topics = query.order_by(desc(BlogTopicQueue.priority), desc(BlogTopicQueue.created_at)).all()

    return {"topics": [
        {
            "id": t.id,
            "topic": t.topic,
            "keyword": t.keyword,
            "angle": t.angle,
            "archetype": t.archetype,
            "priority": t.priority,
            "used": t.used,
            "campaign_id": t.campaign_id,
        }
        for t in topics
    ]}


# ============ Compliance Checking Endpoints ============

@router.post("/compliance/check")
async def check_compliance(
    content: str = Form(...),
    compliance_profile_id: Optional[str] = Form(None),
    db: Session = Depends(get_db),
):
    """Check content for compliance issues."""
    user_id = get_current_user_id(db)

    compliance_profile = None
    if compliance_profile_id:
        cp = db.query(BlogComplianceProfile).filter(
            BlogComplianceProfile.id == compliance_profile_id,
            BlogComplianceProfile.user_id == user_id,
        ).first()
        if cp:
            compliance_profile = {
                "required_disclosures_json": cp.required_disclosures_json,
                "banned_phrases_json": cp.banned_phrases_json,
                "overrides_json": cp.overrides_json,
            }

    result = blog_compliance_service.check_compliance(content, compliance_profile)
    return result.to_dict()


@router.post("/similarity/check")
async def check_similarity(
    content: str = Form(...),
    source_document_id: Optional[str] = Form(None),
    db: Session = Depends(get_db),
):
    """Check content similarity against source material."""
    user_id = get_current_user_id(db)

    source_content = ""
    if source_document_id:
        doc = db.query(BlogSourceDocument).filter(
            BlogSourceDocument.id == source_document_id,
            BlogSourceDocument.user_id == user_id,
        ).first()
        if doc and doc.extracted_text:
            source_content = doc.extracted_text

    if not source_content:
        return {"error": "No source content to compare"}

    result = blog_similarity_service.check_similarity(content, source_content)
    return result.to_dict()


# ============ User Settings Endpoints ============

@router.get("/settings")
async def get_user_settings(
    db: Session = Depends(get_db),
):
    """Get user blog settings."""
    user_id = get_current_user_id(db)

    settings = db.query(BlogUserSettings).filter(
        BlogUserSettings.user_id == user_id
    ).first()

    if not settings:
        # Create default settings
        settings = BlogUserSettings(user_id=user_id)
        db.add(settings)
        db.commit()
        db.refresh(settings)

    return {
        "default_voice_profile_id": settings.default_voice_profile_id,
        "default_compliance_profile_id": settings.default_compliance_profile_id,
        "posting_mode": settings.posting_mode,
        "auto_generate_daily": settings.auto_generate_daily,
        "daily_generate_time": settings.daily_generate_time,
        "timezone": settings.timezone,
        "brand_logo_url": settings.brand_logo_url,
        "brand_colors_json": settings.brand_colors_json,
        "llm_provider": settings.llm_provider,
        "llm_model": settings.llm_model,
    }


@router.put("/settings")
async def update_user_settings(
    request: UserSettingsUpdate,
    db: Session = Depends(get_db),
):
    """Update user blog settings."""
    user_id = get_current_user_id(db)

    settings = db.query(BlogUserSettings).filter(
        BlogUserSettings.user_id == user_id
    ).first()

    if not settings:
        settings = BlogUserSettings(user_id=user_id)
        db.add(settings)

    _protected = {'id', 'organization_id', 'created_at', 'updated_at'}
    for field, value in request.dict(exclude_unset=True).items():
        if value is not None and field not in _protected:
            setattr(settings, field, value)

    settings.updated_at = datetime.now(timezone.utc)
    db.commit()

    return {"message": "Settings updated"}


# ============ Analytics Endpoints ============

@router.get("/analytics/overview")
async def get_analytics_overview(
    days: int = Query(30, ge=1, le=365),
    db: Session = Depends(get_db),
):
    """Get content analytics overview."""
    user_id = get_current_user_id(db)

    from sqlalchemy import func
    from datetime import timedelta

    start_date = datetime.now(timezone.utc) - timedelta(days=days)

    # Count content by status
    status_counts = db.query(
        BlogContentItem.status,
        func.count(BlogContentItem.id)
    ).filter(
        BlogContentItem.user_id == user_id,
        BlogContentItem.created_at >= start_date,
    ).group_by(BlogContentItem.status).all()

    # Count by archetype
    archetype_counts = db.query(
        BlogContentItem.archetype,
        func.count(BlogContentItem.id)
    ).filter(
        BlogContentItem.user_id == user_id,
        BlogContentItem.created_at >= start_date,
    ).group_by(BlogContentItem.archetype).all()

    # Get performance metrics
    performance = db.query(
        func.sum(BlogPerformanceFeedback.views),
        func.sum(BlogPerformanceFeedback.likes),
        func.sum(BlogPerformanceFeedback.comments),
        func.sum(BlogPerformanceFeedback.shares),
        func.sum(BlogPerformanceFeedback.clicks),
    ).filter(
        BlogPerformanceFeedback.user_id == user_id,
        BlogPerformanceFeedback.created_at >= start_date,
    ).first()

    return {
        "period_days": days,
        "content_by_status": dict(status_counts),
        "content_by_archetype": dict(archetype_counts),
        "performance": {
            "total_views": performance[0] or 0,
            "total_likes": performance[1] or 0,
            "total_comments": performance[2] or 0,
            "total_shares": performance[3] or 0,
            "total_clicks": performance[4] or 0,
        },
    }


@router.get("/content/{content_id}/performance")
async def get_content_performance(
    content_id: str,
    db: Session = Depends(get_db),
):
    """Get performance data for a specific content item."""
    user_id = get_current_user_id(db)

    item = db.query(BlogContentItem).filter(
        BlogContentItem.id == content_id,
        BlogContentItem.user_id == user_id,
    ).first()

    if not item:
        raise HTTPException(status_code=404, detail="Content not found")

    performance = db.query(BlogPerformanceFeedback).filter(
        BlogPerformanceFeedback.content_item_id == content_id,
    ).order_by(desc(BlogPerformanceFeedback.fetched_at)).all()

    return {
        "content_id": content_id,
        "title": item.title,
        "performance": [
            {
                "platform": p.platform,
                "views": p.views,
                "likes": p.likes,
                "comments": p.comments,
                "shares": p.shares,
                "clicks": p.clicks,
                "engagement_rate": p.engagement_rate,
                "fetched_at": p.fetched_at.isoformat() if p.fetched_at else None,
            }
            for p in performance
        ],
    }
