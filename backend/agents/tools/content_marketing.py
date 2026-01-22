"""
Content Marketing Tools

Tools for the Content Marketing Agent to manage:
- Content Marketing Automation System (Vocable.ai-style)
- Carousel Builder (AI-powered social media carousels)
"""

from typing import Any, Dict, Optional, List
from datetime import datetime, timedelta
import logging
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


# =============================================================================
# INPUT SCHEMAS
# =============================================================================

# Content Calendar Tools
class CreateCalendarInput(BaseModel):
    """Input for creating a content calendar"""
    name: str = Field(..., description="Calendar name")
    description: Optional[str] = Field(None, description="Calendar description")
    start_date: Optional[str] = Field(None, description="Start date (ISO format)")
    days: int = Field(default=30, description="Number of days to plan (7-90)")
    channels: Optional[List[str]] = Field(None, description="Target channels: blog, email, linkedin, facebook, instagram")
    auto_generate_briefs: bool = Field(default=True, description="Auto-generate content briefs")


class GetCalendarInput(BaseModel):
    """Input for getting calendar details"""
    calendar_id: str = Field(..., description="Calendar ID")
    include_briefs: bool = Field(default=True, description="Include content briefs")


class ListCalendarsInput(BaseModel):
    """Input for listing calendars"""
    status: Optional[str] = Field(None, description="Filter by status: draft, active, paused, completed")
    limit: int = Field(default=20, description="Maximum results")


class GenerateBriefsInput(BaseModel):
    """Input for generating content briefs"""
    calendar_id: str = Field(..., description="Calendar ID")
    count: int = Field(default=5, description="Number of briefs to generate")
    channels: Optional[List[str]] = Field(None, description="Target channels")


# Brand Voice Tools
class AnalyzeBrandVoiceInput(BaseModel):
    """Input for analyzing brand voice"""
    source_url: Optional[str] = Field(None, description="Website URL to analyze")
    sample_content: Optional[str] = Field(None, description="Sample content text to analyze")
    voice_name: str = Field(default="Primary Brand Voice", description="Name for this voice profile")


class GetBrandVoiceInput(BaseModel):
    """Input for getting brand voice profile"""
    voice_id: Optional[str] = Field(None, description="Specific voice ID (optional, defaults to primary)")


# Content Publishing Tools
class PublishContentInput(BaseModel):
    """Input for publishing content"""
    brief_id: str = Field(..., description="Content brief ID to publish")
    channel: str = Field(..., description="Channel to publish to: blog, email, linkedin, facebook, instagram")
    schedule_time: Optional[str] = Field(None, description="Schedule time (ISO format, optional for immediate)")


class GetPublishingAnalyticsInput(BaseModel):
    """Input for getting publishing analytics"""
    days: int = Field(default=30, description="Days to analyze")
    channel: Optional[str] = Field(None, description="Filter by channel")


# SEO Tools
class TrackKeywordInput(BaseModel):
    """Input for tracking a keyword"""
    keyword: str = Field(..., description="Keyword to track")
    category: Optional[str] = Field(None, description="Keyword category")
    current_ranking: Optional[int] = Field(None, description="Current ranking position")


class GetKeywordSuggestionsInput(BaseModel):
    """Input for getting keyword suggestions"""
    topic: Optional[str] = Field(None, description="Topic for suggestions")
    count: int = Field(default=10, description="Number of suggestions")


class GetKeywordOpportunitiesInput(BaseModel):
    """Input for finding keyword opportunities"""
    category: Optional[str] = Field(None, description="Filter by category")


# Carousel Tools
class CreateCarouselInput(BaseModel):
    """Input for creating a carousel project"""
    name: str = Field(..., description="Project name")
    project_type: str = Field(default="custom", description="Type: just_closed, marketing, rate_update, educational, custom")
    platform: str = Field(default="linkedin", description="Platform: linkedin, instagram, tiktok, facebook")
    loan_id: Optional[int] = Field(None, description="Link to loan for CRM data")
    lead_id: Optional[str] = Field(None, description="Link to lead for CRM data")
    active_loan_id: Optional[str] = Field(None, description="Link to active loan for CRM data")


class GenerateCarouselContentInput(BaseModel):
    """Input for generating carousel content with AI"""
    project_id: str = Field(..., description="Carousel project ID")
    num_slides: int = Field(default=5, description="Number of slides (3-10)")
    custom_prompt: Optional[str] = Field(None, description="Custom prompt for content")
    include_crm_data: bool = Field(default=True, description="Include linked CRM data")


class GetCarouselTemplatesInput(BaseModel):
    """Input for getting carousel templates"""
    template_type: Optional[str] = Field(None, description="Filter by type")
    platform: Optional[str] = Field(None, description="Filter by platform")


# Personalization Tools
class PreviewPersonalizationInput(BaseModel):
    """Input for previewing personalized content"""
    content: str = Field(..., description="Content with {{tokens}}")
    entity_type: str = Field(..., description="Entity type: lead, active_loan, mum_client")
    entity_id: str = Field(..., description="Entity ID for data resolution")


class GetPersonalizationTokensInput(BaseModel):
    """Input for getting available tokens"""
    entity_type: Optional[str] = Field(None, description="Filter by entity type")


# =============================================================================
# TOOL HANDLERS
# =============================================================================

async def create_content_calendar(
    input_data: Dict[str, Any],
    context: Dict[str, Any]
) -> Dict[str, Any]:
    """Create a new content calendar with optional auto-generated briefs."""
    from database import SessionLocal
    from services.content_marketing.content_calendar_service import ContentCalendarService

    db = SessionLocal()
    try:
        service = ContentCalendarService(db)

        start_date = None
        if input_data.get("start_date"):
            start_date = datetime.fromisoformat(input_data["start_date"])

        result = await service.create_calendar(
            user_id=context.get("user_id", 1),
            name=input_data["name"],
            description=input_data.get("description"),
            start_date=start_date,
            days=input_data.get("days", 30),
            channels=input_data.get("channels"),
            auto_generate_briefs=input_data.get("auto_generate_briefs", True),
        )

        return {
            "success": True,
            "data": result,
            "message": f"Calendar '{input_data['name']}' created with {result.get('brief_count', 0)} briefs"
        }

    except Exception as e:
        logger.error(f"Error creating calendar: {e}")
        return {"success": False, "error": str(e)}
    finally:
        db.close()


async def get_content_calendar(
    input_data: Dict[str, Any],
    context: Dict[str, Any]
) -> Dict[str, Any]:
    """Get content calendar details."""
    from database import SessionLocal
    from services.content_marketing.content_calendar_service import ContentCalendarService

    db = SessionLocal()
    try:
        service = ContentCalendarService(db)

        result = await service.get_calendar(
            calendar_id=input_data["calendar_id"],
            include_briefs=input_data.get("include_briefs", True),
        )

        if not result:
            return {"success": False, "error": "Calendar not found"}

        return {
            "success": True,
            "data": result,
            "message": f"Calendar '{result.get('name')}' retrieved"
        }

    except Exception as e:
        logger.error(f"Error getting calendar: {e}")
        return {"success": False, "error": str(e)}
    finally:
        db.close()


async def list_content_calendars(
    input_data: Dict[str, Any],
    context: Dict[str, Any]
) -> Dict[str, Any]:
    """List content calendars."""
    from database import SessionLocal
    from services.content_marketing.content_calendar_service import ContentCalendarService

    db = SessionLocal()
    try:
        service = ContentCalendarService(db)

        calendars = await service.list_calendars(
            user_id=context.get("user_id", 1),
            status=input_data.get("status"),
            limit=input_data.get("limit", 20),
        )

        return {
            "success": True,
            "data": {"calendars": calendars, "count": len(calendars)},
            "message": f"Found {len(calendars)} calendars"
        }

    except Exception as e:
        logger.error(f"Error listing calendars: {e}")
        return {"success": False, "error": str(e)}
    finally:
        db.close()


async def generate_content_briefs(
    input_data: Dict[str, Any],
    context: Dict[str, Any]
) -> Dict[str, Any]:
    """Generate AI content briefs for a calendar."""
    from database import SessionLocal
    from services.content_marketing.content_calendar_service import ContentCalendarService

    db = SessionLocal()
    try:
        service = ContentCalendarService(db)

        result = await service.generate_briefs(
            calendar_id=input_data["calendar_id"],
            count=input_data.get("count", 5),
            channels=input_data.get("channels"),
        )

        return {
            "success": True,
            "data": result,
            "message": f"Generated {len(result.get('briefs', []))} content briefs"
        }

    except Exception as e:
        logger.error(f"Error generating briefs: {e}")
        return {"success": False, "error": str(e)}
    finally:
        db.close()


async def analyze_brand_voice(
    input_data: Dict[str, Any],
    context: Dict[str, Any]
) -> Dict[str, Any]:
    """Analyze brand voice from website or content."""
    from database import SessionLocal
    from services.content_marketing.brand_voice_analyzer import BrandVoiceAnalyzerService

    db = SessionLocal()
    try:
        service = BrandVoiceAnalyzerService(db)

        result = await service.analyze_voice(
            user_id=context.get("user_id", 1),
            source_url=input_data.get("source_url"),
            sample_content=input_data.get("sample_content"),
            voice_name=input_data.get("voice_name", "Primary Brand Voice"),
        )

        return {
            "success": True,
            "data": result,
            "message": f"Brand voice profile '{input_data.get('voice_name')}' created"
        }

    except Exception as e:
        logger.error(f"Error analyzing brand voice: {e}")
        return {"success": False, "error": str(e)}
    finally:
        db.close()


async def get_brand_voice(
    input_data: Dict[str, Any],
    context: Dict[str, Any]
) -> Dict[str, Any]:
    """Get brand voice profile."""
    from database import SessionLocal
    from services.content_marketing.brand_voice_analyzer import BrandVoiceAnalyzerService

    db = SessionLocal()
    try:
        service = BrandVoiceAnalyzerService(db)

        result = await service.get_voice_profile(
            user_id=context.get("user_id", 1),
            voice_id=input_data.get("voice_id"),
        )

        if not result:
            return {"success": False, "error": "No brand voice profile found"}

        return {
            "success": True,
            "data": result,
            "message": f"Brand voice profile retrieved"
        }

    except Exception as e:
        logger.error(f"Error getting brand voice: {e}")
        return {"success": False, "error": str(e)}
    finally:
        db.close()


async def publish_content(
    input_data: Dict[str, Any],
    context: Dict[str, Any]
) -> Dict[str, Any]:
    """Publish or schedule content to a channel."""
    from database import SessionLocal
    from services.content_marketing.content_publisher_service import ContentPublisherService

    db = SessionLocal()
    try:
        service = ContentPublisherService(db)

        schedule_time = None
        if input_data.get("schedule_time"):
            schedule_time = datetime.fromisoformat(input_data["schedule_time"])

        result = await service.publish_content(
            brief_id=input_data["brief_id"],
            channel=input_data["channel"],
            user_id=context.get("user_id", 1),
            schedule_time=schedule_time,
        )

        action = "scheduled" if schedule_time else "published"
        return {
            "success": True,
            "data": result,
            "message": f"Content {action} to {input_data['channel']}"
        }

    except Exception as e:
        logger.error(f"Error publishing content: {e}")
        return {"success": False, "error": str(e)}
    finally:
        db.close()


async def get_publishing_analytics(
    input_data: Dict[str, Any],
    context: Dict[str, Any]
) -> Dict[str, Any]:
    """Get publishing analytics."""
    from database import SessionLocal
    from services.content_marketing.content_publisher_service import ContentPublisherService

    db = SessionLocal()
    try:
        service = ContentPublisherService(db)

        result = await service.get_analytics(
            user_id=context.get("user_id", 1),
            days=input_data.get("days", 30),
            channel=input_data.get("channel"),
        )

        return {
            "success": True,
            "data": result,
            "message": f"Analytics for past {input_data.get('days', 30)} days"
        }

    except Exception as e:
        logger.error(f"Error getting analytics: {e}")
        return {"success": False, "error": str(e)}
    finally:
        db.close()


async def track_keyword(
    input_data: Dict[str, Any],
    context: Dict[str, Any]
) -> Dict[str, Any]:
    """Track a keyword for SEO."""
    from database import SessionLocal
    from services.content_marketing.seo_keyword_service import SEOKeywordService

    db = SessionLocal()
    try:
        service = SEOKeywordService(db)

        result = await service.track_keyword(
            user_id=context.get("user_id", 1),
            keyword=input_data["keyword"],
            category=input_data.get("category"),
            current_ranking=input_data.get("current_ranking"),
        )

        return {
            "success": True,
            "data": result,
            "message": f"Now tracking keyword: {input_data['keyword']}"
        }

    except Exception as e:
        logger.error(f"Error tracking keyword: {e}")
        return {"success": False, "error": str(e)}
    finally:
        db.close()


async def get_keyword_suggestions(
    input_data: Dict[str, Any],
    context: Dict[str, Any]
) -> Dict[str, Any]:
    """Get AI-powered keyword suggestions."""
    from database import SessionLocal
    from services.content_marketing.seo_keyword_service import SEOKeywordService

    db = SessionLocal()
    try:
        service = SEOKeywordService(db)

        result = await service.suggest_keywords(
            topic=input_data.get("topic"),
            count=input_data.get("count", 10),
        )

        return {
            "success": True,
            "data": result,
            "message": f"Generated {len(result.get('keywords', []))} keyword suggestions"
        }

    except Exception as e:
        logger.error(f"Error getting keyword suggestions: {e}")
        return {"success": False, "error": str(e)}
    finally:
        db.close()


async def get_keyword_opportunities(
    input_data: Dict[str, Any],
    context: Dict[str, Any]
) -> Dict[str, Any]:
    """Find keyword ranking opportunities."""
    from database import SessionLocal
    from services.content_marketing.seo_keyword_service import SEOKeywordService

    db = SessionLocal()
    try:
        service = SEOKeywordService(db)

        result = await service.find_opportunities(
            user_id=context.get("user_id", 1),
            category=input_data.get("category"),
        )

        return {
            "success": True,
            "data": result,
            "message": f"Found {len(result.get('opportunities', []))} keyword opportunities"
        }

    except Exception as e:
        logger.error(f"Error finding opportunities: {e}")
        return {"success": False, "error": str(e)}
    finally:
        db.close()


async def create_carousel_project(
    input_data: Dict[str, Any],
    context: Dict[str, Any]
) -> Dict[str, Any]:
    """Create a new carousel project."""
    from database import SessionLocal
    from models.carousel_builder import CarouselProject, CarouselSlide, CarouselStatus, SlideBackgroundType, SlideLayoutTemplate
    import uuid

    db = SessionLocal()
    try:
        project_id = str(uuid.uuid4())[:12]

        # Get dimensions for aspect ratio
        dimensions = {"1:1": (1080, 1080), "4:5": (1080, 1350), "9:16": (1080, 1920)}
        aspect_ratio = "1:1"  # Default for LinkedIn
        if input_data.get("platform") in ["instagram", "tiktok"]:
            aspect_ratio = "4:5" if input_data.get("platform") == "instagram" else "9:16"
        width, height = dimensions.get(aspect_ratio, (1080, 1080))

        project = CarouselProject(
            id=project_id,
            user_id=context.get("user_id", 1),
            name=input_data["name"],
            project_type=input_data.get("project_type", "custom"),
            platform=input_data.get("platform", "linkedin"),
            aspect_ratio=aspect_ratio,
            width=width,
            height=height,
            loan_id=input_data.get("loan_id"),
            lead_id=input_data.get("lead_id"),
            active_loan_id=input_data.get("active_loan_id"),
            status=CarouselStatus.DRAFT,
        )
        db.add(project)

        # Create default first slide
        slide = CarouselSlide(
            id=str(uuid.uuid4())[:12],
            project_id=project_id,
            order=0,
            title="Your Title Here",
            subtitle="Add a subtitle",
            background_type=SlideBackgroundType.SOLID,
            background_color="#217F8D",
            layout_template=SlideLayoutTemplate.CENTERED,
            elements=[],
            custom_styles={},
        )
        db.add(slide)

        db.commit()
        db.refresh(project)

        return {
            "success": True,
            "data": {
                "project_id": project.id,
                "name": project.name,
                "project_type": project.project_type.value if hasattr(project.project_type, 'value') else str(project.project_type),
                "platform": project.platform.value if hasattr(project.platform, 'value') else str(project.platform),
                "status": "draft",
            },
            "message": f"Carousel project '{input_data['name']}' created"
        }

    except Exception as e:
        db.rollback()
        logger.error(f"Error creating carousel: {e}")
        return {"success": False, "error": str(e)}
    finally:
        db.close()


async def generate_carousel_content(
    input_data: Dict[str, Any],
    context: Dict[str, Any]
) -> Dict[str, Any]:
    """Generate AI content for a carousel."""
    from database import SessionLocal
    from models.carousel_builder import CarouselProject
    from services.carousel_content_service import carousel_content_service

    db = SessionLocal()
    try:
        project = db.query(CarouselProject).filter(
            CarouselProject.id == input_data["project_id"]
        ).first()

        if not project:
            return {"success": False, "error": "Project not found"}

        # Get CRM data if linked
        crm_data = None
        if input_data.get("include_crm_data", True):
            crm_data = await _get_crm_data_for_carousel(project, db)

        # Get LO info from user
        lo_info = {"name": context.get("user_name"), "email": context.get("user_email")}

        result = await carousel_content_service.generate_carousel_content(
            project_type=project.project_type.value if hasattr(project.project_type, 'value') else str(project.project_type),
            platform=project.platform.value if hasattr(project.platform, 'value') else str(project.platform),
            num_slides=input_data.get("num_slides", 5),
            crm_data=crm_data,
            custom_prompt=input_data.get("custom_prompt"),
            lo_info=lo_info,
        )

        if not result.get("success"):
            return {"success": False, "error": result.get("error", "Generation failed")}

        return {
            "success": True,
            "data": {
                "project_id": project.id,
                "slides": result.get("slides", []),
                "tokens_used": result.get("tokens_used"),
            },
            "message": f"Generated {len(result.get('slides', []))} slides for carousel"
        }

    except Exception as e:
        logger.error(f"Error generating carousel content: {e}")
        return {"success": False, "error": str(e)}
    finally:
        db.close()


async def _get_crm_data_for_carousel(project, db) -> Optional[Dict[str, Any]]:
    """Helper to get CRM data linked to a carousel project."""
    try:
        if project.active_loan_id:
            from models.active_loan_profile import ActiveLoanProfile
            loan = db.query(ActiveLoanProfile).filter(
                ActiveLoanProfile.id == project.active_loan_id
            ).first()
            if loan:
                return loan.to_dict()

        if project.lead_id:
            from models.lead_profile import LeadProfile
            lead = db.query(LeadProfile).filter(
                LeadProfile.id == project.lead_id
            ).first()
            if lead:
                return lead.to_dict()

    except Exception as e:
        logger.warning(f"Error fetching CRM data for carousel: {e}")

    return None


async def get_carousel_templates(
    input_data: Dict[str, Any],
    context: Dict[str, Any]
) -> Dict[str, Any]:
    """Get available carousel templates."""
    from database import SessionLocal
    from models.carousel_builder import CarouselTemplate

    db = SessionLocal()
    try:
        query = db.query(CarouselTemplate).filter(CarouselTemplate.is_active == True)

        if input_data.get("template_type"):
            query = query.filter(CarouselTemplate.template_type == input_data["template_type"])
        if input_data.get("platform"):
            query = query.filter(CarouselTemplate.platform == input_data["platform"])

        templates = query.all()

        return {
            "success": True,
            "data": {
                "templates": [
                    {
                        "id": t.id,
                        "name": t.name,
                        "description": t.description,
                        "template_type": t.template_type.value if hasattr(t.template_type, 'value') else str(t.template_type),
                        "platform": t.platform.value if hasattr(t.platform, 'value') else str(t.platform),
                        "slide_count": len(t.slide_templates or []),
                    }
                    for t in templates
                ],
                "count": len(templates),
            },
            "message": f"Found {len(templates)} carousel templates"
        }

    except Exception as e:
        logger.error(f"Error getting templates: {e}")
        return {"success": False, "error": str(e)}
    finally:
        db.close()


async def preview_personalization(
    input_data: Dict[str, Any],
    context: Dict[str, Any]
) -> Dict[str, Any]:
    """Preview content with personalization tokens resolved."""
    from database import SessionLocal
    from services.content_marketing.content_personalization_service import ContentPersonalizationService

    db = SessionLocal()
    try:
        service = ContentPersonalizationService(db)

        result = await service.preview_personalization(
            content=input_data["content"],
            entity_type=input_data["entity_type"],
            entity_id=input_data["entity_id"],
        )

        return {
            "success": True,
            "data": result,
            "message": "Personalization preview generated"
        }

    except Exception as e:
        logger.error(f"Error previewing personalization: {e}")
        return {"success": False, "error": str(e)}
    finally:
        db.close()


async def get_personalization_tokens(
    input_data: Dict[str, Any],
    context: Dict[str, Any]
) -> Dict[str, Any]:
    """Get available personalization tokens."""
    from database import SessionLocal
    from services.content_marketing.content_personalization_service import ContentPersonalizationService

    db = SessionLocal()
    try:
        service = ContentPersonalizationService(db)

        result = await service.get_available_tokens(
            entity_type=input_data.get("entity_type"),
        )

        return {
            "success": True,
            "data": result,
            "message": f"Found {len(result.get('tokens', []))} available tokens"
        }

    except Exception as e:
        logger.error(f"Error getting tokens: {e}")
        return {"success": False, "error": str(e)}
    finally:
        db.close()


# =============================================================================
# TOOL DEFINITIONS (for registration)
# =============================================================================

CONTENT_MARKETING_TOOLS = [
    # Calendar Tools
    {
        "name": "create_content_calendar",
        "description": "Create a new content marketing calendar with AI-generated briefs. Supports multi-channel planning (blog, email, social).",
        "handler": create_content_calendar,
        "input_schema": CreateCalendarInput,
        "category": "action",
        "risk_level": "low",
    },
    {
        "name": "get_content_calendar",
        "description": "Get content calendar details including all scheduled briefs and their status.",
        "handler": get_content_calendar,
        "input_schema": GetCalendarInput,
        "category": "query",
        "risk_level": "low",
    },
    {
        "name": "list_content_calendars",
        "description": "List all content calendars. Filter by status: draft, active, paused, completed.",
        "handler": list_content_calendars,
        "input_schema": ListCalendarsInput,
        "category": "query",
        "risk_level": "low",
    },
    {
        "name": "generate_content_briefs",
        "description": "Generate AI content briefs for a calendar. Creates topic suggestions, outlines, and CTA recommendations.",
        "handler": generate_content_briefs,
        "input_schema": GenerateBriefsInput,
        "category": "action",
        "risk_level": "low",
    },

    # Brand Voice Tools
    {
        "name": "analyze_brand_voice",
        "description": "Analyze brand voice from a website URL or sample content. Creates a voice profile for consistent content generation.",
        "handler": analyze_brand_voice,
        "input_schema": AnalyzeBrandVoiceInput,
        "category": "analysis",
        "risk_level": "low",
    },
    {
        "name": "get_brand_voice",
        "description": "Get the brand voice profile for content generation. Includes tone, vocabulary, and style guidelines.",
        "handler": get_brand_voice,
        "input_schema": GetBrandVoiceInput,
        "category": "query",
        "risk_level": "low",
    },

    # Publishing Tools
    {
        "name": "publish_content",
        "description": "Publish or schedule content to a channel (blog, email, linkedin, facebook, instagram).",
        "handler": publish_content,
        "input_schema": PublishContentInput,
        "category": "action",
        "risk_level": "medium",
        "requires_confirmation": True,
    },
    {
        "name": "get_publishing_analytics",
        "description": "Get publishing analytics including engagement metrics, best performing content, and channel performance.",
        "handler": get_publishing_analytics,
        "input_schema": GetPublishingAnalyticsInput,
        "category": "analysis",
        "risk_level": "low",
    },

    # SEO Tools
    {
        "name": "track_keyword",
        "description": "Start tracking a keyword for SEO. Monitor rankings over time.",
        "handler": track_keyword,
        "input_schema": TrackKeywordInput,
        "category": "action",
        "risk_level": "low",
    },
    {
        "name": "get_keyword_suggestions",
        "description": "Get AI-powered keyword suggestions for mortgage content. Returns relevant keywords with search volume estimates.",
        "handler": get_keyword_suggestions,
        "input_schema": GetKeywordSuggestionsInput,
        "category": "analysis",
        "risk_level": "low",
    },
    {
        "name": "get_keyword_opportunities",
        "description": "Find keyword ranking opportunities. Identifies quick wins and striking distance keywords.",
        "handler": get_keyword_opportunities,
        "input_schema": GetKeywordOpportunitiesInput,
        "category": "analysis",
        "risk_level": "low",
    },

    # Carousel Tools
    {
        "name": "create_carousel_project",
        "description": "Create a new carousel project for social media. Link to CRM data (loan, lead) for personalized content.",
        "handler": create_carousel_project,
        "input_schema": CreateCarouselInput,
        "category": "action",
        "risk_level": "low",
    },
    {
        "name": "generate_carousel_content",
        "description": "Generate AI carousel content. Creates slides for just_closed celebrations, rate updates, educational content, or marketing.",
        "handler": generate_carousel_content,
        "input_schema": GenerateCarouselContentInput,
        "category": "action",
        "risk_level": "low",
    },
    {
        "name": "get_carousel_templates",
        "description": "Get available carousel templates. Filter by type (just_closed, marketing, etc.) or platform (linkedin, instagram).",
        "handler": get_carousel_templates,
        "input_schema": GetCarouselTemplatesInput,
        "category": "query",
        "risk_level": "low",
    },

    # Personalization Tools
    {
        "name": "preview_personalization",
        "description": "Preview content with CRM tokens resolved. Shows how {{lead.first_name}} etc. will appear with real data.",
        "handler": preview_personalization,
        "input_schema": PreviewPersonalizationInput,
        "category": "query",
        "risk_level": "low",
    },
    {
        "name": "get_personalization_tokens",
        "description": "Get available personalization tokens for CRM data. Returns tokens like {{lead.first_name}}, {{loan.rate}}, etc.",
        "handler": get_personalization_tokens,
        "input_schema": GetPersonalizationTokensInput,
        "category": "query",
        "risk_level": "low",
    },
]
