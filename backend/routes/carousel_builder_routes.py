"""
Carousel Builder Routes

API endpoints for the AI-powered carousel builder:
- CRUD operations for carousel projects and slides
- Theme and template management
- Export functionality
"""

from fastapi import APIRouter, Depends, Request, Query, HTTPException
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import text, func, and_, or_, desc
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone
import logging
import uuid

from database import get_db
from models.carousel_builder import (
    CarouselProject, CarouselSlide, CarouselTheme, CarouselTemplate, CarouselExport,
    CarouselProjectType, CarouselPlatform, CarouselAspectRatio, CarouselStatus,
    SlideBackgroundType, SlideLayoutTemplate, ExportStatus
)
from services.carousel_content_service import carousel_content_service
from services.perennia_s3_service import get_s3_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/carousels", tags=["Carousel Builder"])

# Will be set by main.py
User = None
get_current_user = None


def set_dependencies(user_model, current_user_func):
    """Set dependencies from main.py"""
    global User, get_current_user
    User = user_model
    get_current_user = current_user_func


def generate_short_uuid():
    return str(uuid.uuid4())[:12]


def ensure_carousel_tables(db: Session):
    """Ensure carousel tables exist, create them if not."""
    try:
        # Check if tables exist by trying a simple query
        db.execute(text("SELECT 1 FROM carousel_projects LIMIT 1"))
        return True
    except Exception as e:
        logger.warning(f"Carousel tables may not exist, attempting to create: {e}")
        try:
            # Run migration
            from migrations.add_carousel_builder_tables import run_migration
            run_migration()
            logger.info("Carousel tables created successfully")
            return True
        except Exception as migration_error:
            logger.error(f"Failed to create carousel tables: {migration_error}")
            return False


# =============================================================================
# Health Check / Diagnostic Endpoint
# =============================================================================

@router.get("/health")
async def carousel_health_check(db: Session = Depends(get_db)):
    """Check carousel builder health and table status."""
    status = {"status": "ok", "tables": {}}

    tables = ["carousel_projects", "carousel_slides", "carousel_themes", "carousel_templates", "carousel_exports"]

    for table in tables:
        try:
            ALLOWED_TABLES = {"carousel_projects", "carousel_slides", "carousel_themes", "carousel_templates", "carousel_exports"}
            if table not in ALLOWED_TABLES:
                raise ValueError(f"Invalid table name: {table}")
            result = db.execute(text("SELECT COUNT(*) FROM " + table))
            count = result.scalar()
            status["tables"][table] = {"exists": True, "count": count}
        except Exception as e:
            status["tables"][table] = {"exists": False, "error": "Internal server error"}
            status["status"] = "degraded"

    # Try to run migration if any table is missing
    if status["status"] == "degraded":
        try:
            from migrations.add_carousel_builder_tables import run_migration
            run_migration()
            status["migration_run"] = True
        except Exception as e:
            status["migration_error"] = str(e)

    return status


# =============================================================================
# Pydantic Models - Requests
# =============================================================================

class ProjectCreate(BaseModel):
    """Create a new carousel project"""
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    project_type: str = Field(default="custom")
    platform: str = Field(default="linkedin")
    aspect_ratio: str = Field(default="1:1")
    loan_id: Optional[int] = None
    lead_id: Optional[str] = None
    active_loan_id: Optional[str] = None
    theme_id: Optional[str] = None
    template_id: Optional[str] = None


class ProjectUpdate(BaseModel):
    """Update carousel project"""
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    platform: Optional[str] = None
    aspect_ratio: Optional[str] = None
    theme_id: Optional[str] = None
    custom_branding: Optional[Dict[str, Any]] = None
    status: Optional[str] = None


class SlideCreate(BaseModel):
    """Create a new slide"""
    title: Optional[str] = None
    subtitle: Optional[str] = None
    body_text: Optional[str] = None
    background_type: str = Field(default="solid")
    background_color: str = Field(default="#ffffff")
    background_gradient: Optional[Dict[str, Any]] = None
    background_image_url: Optional[str] = None
    layout_template: str = Field(default="centered")
    elements: List[Dict[str, Any]] = Field(default_factory=list)
    custom_styles: Dict[str, Any] = Field(default_factory=dict)


class SlideUpdate(BaseModel):
    """Update a slide"""
    title: Optional[str] = None
    subtitle: Optional[str] = None
    body_text: Optional[str] = None
    background_type: Optional[str] = None
    background_color: Optional[str] = None
    background_gradient: Optional[Dict[str, Any]] = None
    background_image_url: Optional[str] = None
    layout_template: Optional[str] = None
    elements: Optional[List[Dict[str, Any]]] = None
    custom_styles: Optional[Dict[str, Any]] = None


class SlideReorder(BaseModel):
    """Reorder slides"""
    slide_ids: List[str] = Field(..., min_items=1)


class ExportRequest(BaseModel):
    """Request carousel export"""
    format: str = Field(default="png")
    quality: int = Field(default=90, ge=1, le=100)
    scale: int = Field(default=2, ge=1, le=4)


class ThemeCreate(BaseModel):
    """Create a custom theme"""
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    colors: Dict[str, str] = Field(default_factory=dict)
    typography: Dict[str, Any] = Field(default_factory=dict)
    spacing: Dict[str, Any] = Field(default_factory=dict)
    decorations: Dict[str, Any] = Field(default_factory=dict)
    category: Optional[str] = None
    tags: List[str] = Field(default_factory=list)


class AIGenerateRequest(BaseModel):
    """Request AI-generated carousel content"""
    num_slides: int = Field(default=5, ge=3, le=10)
    custom_prompt: Optional[str] = None
    include_crm_data: bool = Field(default=True)
    lo_info: Optional[Dict[str, Any]] = None


class ImageUploadRequest(BaseModel):
    """Request presigned URL for image upload"""
    file_name: str = Field(..., min_length=1)
    content_type: str = Field(default="image/png")
    file_size: Optional[int] = None


# =============================================================================
# Pydantic Models - Responses
# =============================================================================

class SlideResponse(BaseModel):
    id: str
    order: int
    title: Optional[str]
    subtitle: Optional[str]
    body_text: Optional[str]
    background_type: str
    background_color: Optional[str]
    background_gradient: Optional[Dict[str, Any]]
    background_image_url: Optional[str]
    layout_template: str
    elements: List[Dict[str, Any]]
    custom_styles: Dict[str, Any]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ProjectResponse(BaseModel):
    id: str
    name: str
    description: Optional[str]
    project_type: str
    platform: str
    aspect_ratio: str
    width: int
    height: int
    loan_id: Optional[int]
    lead_id: Optional[str]
    theme_id: Optional[str]
    custom_branding: Dict[str, Any]
    status: str
    ai_generated: bool
    slide_count: Optional[int] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ProjectDetailResponse(ProjectResponse):
    slides: List[SlideResponse] = []


class ThemeResponse(BaseModel):
    id: str
    name: str
    description: Optional[str]
    preview_url: Optional[str]
    colors: Dict[str, str]
    typography: Dict[str, Any]
    spacing: Dict[str, Any]
    decorations: Dict[str, Any]
    category: Optional[str]
    tags: List[str]
    is_system: bool
    times_used: int
    created_at: datetime

    class Config:
        from_attributes = True


class TemplateResponse(BaseModel):
    id: str
    name: str
    description: Optional[str]
    preview_url: Optional[str]
    template_type: str
    platform: str
    aspect_ratio: str
    slide_count: int
    required_data_bindings: List[str]
    category: Optional[str]
    tags: List[str]
    times_used: int
    created_at: datetime

    class Config:
        from_attributes = True


# =============================================================================
# Helper Functions
# =============================================================================

async def get_user_from_request(request: Request, db: Session):
    """Helper to extract token and get current user."""
    auth_header = request.headers.get('Authorization', '')
    if not auth_header.startswith('Bearer '):
        raise HTTPException(status_code=401, detail="Missing authorization token")
    token = auth_header.replace('Bearer ', '')
    return await get_current_user(token, request, db)


def get_dimensions_for_aspect_ratio(aspect_ratio: str) -> tuple:
    """Get width and height for an aspect ratio."""
    dimensions = {
        "1:1": (1080, 1080),
        "4:5": (1080, 1350),
        "9:16": (1080, 1920),
    }
    return dimensions.get(aspect_ratio, (1080, 1080))


def check_project_access(project: CarouselProject, user_id: int) -> bool:
    """Check if user has access to the project."""
    return project.user_id == user_id


# =============================================================================
# Project Routes
# =============================================================================

@router.get("")
async def list_projects(
    request: Request,
    db: Session = Depends(get_db),
    project_type: Optional[str] = Query(None),
    platform: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0)
):
    """List user's carousel projects."""
    try:
        # Ensure tables exist
        ensure_carousel_tables(db)

        user = await get_user_from_request(request, db)

        query = db.query(CarouselProject).filter(
            CarouselProject.user_id == user.id
        )

        if project_type:
            query = query.filter(CarouselProject.project_type == project_type)
        if platform:
            query = query.filter(CarouselProject.platform == platform)
        if status:
            query = query.filter(CarouselProject.status == status)
        if search:
            query = query.filter(CarouselProject.name.ilike(f"%{search}%"))

        projects = query.order_by(desc(CarouselProject.updated_at)).offset(offset).limit(limit).all()

        # Add slide count
        result = []
        for project in projects:
            slide_count = db.query(func.count(CarouselSlide.id)).filter(
                CarouselSlide.project_id == project.id
            ).scalar()

            project_data = {
                "id": project.id,
                "name": project.name,
                "description": project.description,
                "project_type": project.project_type.value if hasattr(project.project_type, 'value') else str(project.project_type),
                "platform": project.platform.value if hasattr(project.platform, 'value') else str(project.platform),
                "aspect_ratio": project.aspect_ratio.value if hasattr(project.aspect_ratio, 'value') else str(project.aspect_ratio),
                "width": project.width,
                "height": project.height,
                "loan_id": project.loan_id,
                "lead_id": project.lead_id,
                "theme_id": project.theme_id,
                "custom_branding": project.custom_branding or {},
                "status": project.status.value if hasattr(project.status, 'value') else str(project.status),
                "ai_generated": project.ai_generated,
                "slide_count": slide_count,
                "created_at": project.created_at,
                "updated_at": project.updated_at,
            }
            result.append(project_data)

        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.warning(f"Error listing carousel projects: {e}")
        return []


@router.post("")
async def create_project(
    request: Request,
    project_data: ProjectCreate,
    db: Session = Depends(get_db)
):
    """Create a new carousel project."""
    try:
        # Ensure tables exist
        if not ensure_carousel_tables(db):
            raise HTTPException(status_code=500, detail="Carousel tables not available. Please contact support.")

        user = await get_user_from_request(request, db)

        _carousel_org_id = getattr(user, 'organization_id', None)
        if not _carousel_org_id:
            raise HTTPException(status_code=403, detail="Organization context required")

        width, height = get_dimensions_for_aspect_ratio(project_data.aspect_ratio)

        # Convert string values to enums if needed
        try:
            project_type_enum = CarouselProjectType(project_data.project_type) if project_data.project_type else CarouselProjectType.CUSTOM
        except ValueError:
            project_type_enum = CarouselProjectType.CUSTOM

        try:
            platform_enum = CarouselPlatform(project_data.platform) if project_data.platform else CarouselPlatform.LINKEDIN
        except ValueError:
            platform_enum = CarouselPlatform.LINKEDIN

        try:
            aspect_ratio_enum = CarouselAspectRatio(project_data.aspect_ratio) if project_data.aspect_ratio else CarouselAspectRatio.SQUARE
        except ValueError:
            aspect_ratio_enum = CarouselAspectRatio.SQUARE

        project = CarouselProject(
            id=generate_short_uuid(),
            user_id=user.id,
            organization_id=_carousel_org_id,
            name=project_data.name,
            description=project_data.description,
            project_type=project_type_enum,
            platform=platform_enum,
            aspect_ratio=aspect_ratio_enum,
            width=width,
            height=height,
            loan_id=project_data.loan_id,
            lead_id=project_data.lead_id,
            active_loan_id=project_data.active_loan_id,
            theme_id=project_data.theme_id,
            status=CarouselStatus.DRAFT,
        )

        db.add(project)

        # If template_id provided, copy slides from template
        if project_data.template_id:
            template = db.query(CarouselTemplate).filter(
                CarouselTemplate.id == project_data.template_id
            ).first()
            if template and template.slide_templates:
                for i, slide_template in enumerate(template.slide_templates):
                    slide = CarouselSlide(
                        id=generate_short_uuid(),
                        project_id=project.id,
                        order=i,
                        title=slide_template.get('title'),
                        subtitle=slide_template.get('subtitle'),
                        body_text=slide_template.get('body_text'),
                        background_type=slide_template.get('background_type', 'solid'),
                        background_color=slide_template.get('background_color', '#ffffff'),
                        background_gradient=slide_template.get('background_gradient'),
                        layout_template=slide_template.get('layout_template', 'centered'),
                        elements=slide_template.get('elements', []),
                        custom_styles=slide_template.get('custom_styles', {}),
                    )
                    db.add(slide)

                # Update template usage count
                template.times_used = (template.times_used or 0) + 1
        else:
            # Create a default first slide
            default_slide = CarouselSlide(
                id=generate_short_uuid(),
                project_id=project.id,
                order=0,
                title="Your Title Here",
                subtitle="Add a subtitle",
                background_type=SlideBackgroundType.SOLID,
                background_color="#217F8D",
                layout_template=SlideLayoutTemplate.CENTERED,
                elements=[],
                custom_styles={},
            )
            db.add(default_slide)

        db.commit()
        db.refresh(project)

        # Fetch with slides
        project = db.query(CarouselProject).options(
            joinedload(CarouselProject.slides)
        ).filter(CarouselProject.id == project.id).first()

        return {
            "id": project.id,
            "name": project.name,
            "description": project.description,
            "project_type": project.project_type.value if hasattr(project.project_type, 'value') else str(project.project_type),
            "platform": project.platform.value if hasattr(project.platform, 'value') else str(project.platform),
            "aspect_ratio": project.aspect_ratio.value if hasattr(project.aspect_ratio, 'value') else str(project.aspect_ratio),
            "width": project.width,
            "height": project.height,
            "loan_id": project.loan_id,
            "lead_id": project.lead_id,
            "theme_id": project.theme_id,
            "custom_branding": project.custom_branding or {},
            "status": project.status.value if hasattr(project.status, 'value') else str(project.status),
            "ai_generated": project.ai_generated,
            "created_at": project.created_at,
            "updated_at": project.updated_at,
            "slides": [
                {
                    "id": s.id,
                    "order": s.order,
                    "title": s.title,
                    "subtitle": s.subtitle,
                    "body_text": s.body_text,
                    "background_type": s.background_type.value if hasattr(s.background_type, 'value') else str(s.background_type),
                    "background_color": s.background_color,
                    "background_gradient": s.background_gradient,
                    "background_image_url": s.background_image_url,
                    "layout_template": s.layout_template.value if hasattr(s.layout_template, 'value') else str(s.layout_template),
                    "elements": s.elements or [],
                    "custom_styles": s.custom_styles or {},
                    "created_at": s.created_at,
                    "updated_at": s.updated_at,
                }
                for s in sorted(project.slides, key=lambda x: x.order)
            ],
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating carousel project: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Failed to create carousel")


# =============================================================================
# Static Routes (must be defined BEFORE /{project_id} to avoid path conflicts)
# =============================================================================

# Theme Routes
@router.get("/themes", response_model=List[ThemeResponse])
async def list_themes(
    request: Request,
    db: Session = Depends(get_db),
    category: Optional[str] = Query(None),
    include_system: bool = Query(True)
):
    """List available themes."""
    user = await get_user_from_request(request, db)

    query = db.query(CarouselTheme).filter(CarouselTheme.is_active == True)

    if include_system:
        query = query.filter(
            or_(
                CarouselTheme.is_system == True,
                CarouselTheme.user_id == user.id
            )
        )
    else:
        query = query.filter(CarouselTheme.user_id == user.id)

    if category:
        query = query.filter(CarouselTheme.category == category)

    themes = query.order_by(desc(CarouselTheme.is_system), CarouselTheme.name).all()

    return [
        {
            "id": t.id,
            "name": t.name,
            "description": t.description,
            "preview_url": t.preview_url,
            "colors": t.colors or {},
            "typography": t.typography or {},
            "spacing": t.spacing or {},
            "decorations": t.decorations or {},
            "category": t.category,
            "tags": t.tags or [],
            "is_system": t.is_system,
            "times_used": t.times_used or 0,
            "created_at": t.created_at,
        }
        for t in themes
    ]


@router.post("/themes", response_model=ThemeResponse)
async def create_theme(
    request: Request,
    theme_data: ThemeCreate,
    db: Session = Depends(get_db)
):
    """Create a custom theme."""
    user = await get_user_from_request(request, db)

    _carousel_org_id = getattr(user, 'organization_id', None)
    if not _carousel_org_id:
        raise HTTPException(status_code=403, detail="Organization context required")

    theme = CarouselTheme(
        id=generate_short_uuid(),
        user_id=user.id,
        organization_id=_carousel_org_id,
        name=theme_data.name,
        description=theme_data.description,
        colors=theme_data.colors,
        typography=theme_data.typography,
        spacing=theme_data.spacing,
        decorations=theme_data.decorations,
        category=theme_data.category,
        tags=theme_data.tags,
        is_system=False,
        is_active=True,
    )

    db.add(theme)
    db.commit()
    db.refresh(theme)

    return {
        "id": theme.id,
        "name": theme.name,
        "description": theme.description,
        "preview_url": theme.preview_url,
        "colors": theme.colors or {},
        "typography": theme.typography or {},
        "spacing": theme.spacing or {},
        "decorations": theme.decorations or {},
        "category": theme.category,
        "tags": theme.tags or [],
        "is_system": theme.is_system,
        "times_used": theme.times_used or 0,
        "created_at": theme.created_at,
    }


# Template Routes
@router.get("/templates", response_model=List[TemplateResponse])
async def list_templates(
    request: Request,
    db: Session = Depends(get_db),
    template_type: Optional[str] = Query(None),
    platform: Optional[str] = Query(None),
    category: Optional[str] = Query(None)
):
    """List available templates."""
    user = await get_user_from_request(request, db)

    query = db.query(CarouselTemplate).filter(CarouselTemplate.is_active == True)

    if template_type:
        query = query.filter(CarouselTemplate.template_type == template_type)
    if platform:
        query = query.filter(CarouselTemplate.platform == platform)
    if category:
        query = query.filter(CarouselTemplate.category == category)

    templates = query.order_by(desc(CarouselTemplate.times_used)).all()

    return [
        {
            "id": t.id,
            "name": t.name,
            "description": t.description,
            "preview_url": t.preview_url,
            "template_type": t.template_type.value if hasattr(t.template_type, 'value') else str(t.template_type),
            "platform": t.platform.value if hasattr(t.platform, 'value') else str(t.platform),
            "aspect_ratio": t.aspect_ratio.value if hasattr(t.aspect_ratio, 'value') else str(t.aspect_ratio),
            "slide_count": len(t.slide_templates or []),
            "required_data_bindings": t.required_data_bindings or [],
            "category": t.category,
            "tags": t.tags or [],
            "times_used": t.times_used or 0,
            "created_at": t.created_at,
        }
        for t in templates
    ]


@router.get("/templates/{template_id}", response_model=TemplateResponse)
async def get_template(
    request: Request,
    template_id: str,
    db: Session = Depends(get_db)
):
    """Get a template by ID."""
    user = await get_user_from_request(request, db)

    template = db.query(CarouselTemplate).filter(
        CarouselTemplate.id == template_id
    ).first()

    if not template:
        raise HTTPException(status_code=404, detail="Template not found")

    return {
        "id": template.id,
        "name": template.name,
        "description": template.description,
        "preview_url": template.preview_url,
        "template_type": template.template_type.value if hasattr(template.template_type, 'value') else str(template.template_type),
        "platform": template.platform.value if hasattr(template.platform, 'value') else str(template.platform),
        "aspect_ratio": template.aspect_ratio.value if hasattr(template.aspect_ratio, 'value') else str(template.aspect_ratio),
        "slide_count": len(template.slide_templates or []),
        "required_data_bindings": template.required_data_bindings or [],
        "category": template.category,
        "tags": template.tags or [],
        "times_used": template.times_used or 0,
        "created_at": template.created_at,
    }


# AI Routes
@router.get("/ai/tokens")
async def get_available_tokens(
    request: Request,
    db: Session = Depends(get_db)
):
    """Get list of available tokens for CRM data binding."""
    await get_user_from_request(request, db)

    tokens = carousel_content_service.get_available_tokens()

    # Group tokens by category
    grouped = {
        "loan": {},
        "property": {},
        "borrower": {},
        "lo": {},
        "date": {},
    }

    for token, description in tokens.items():
        # Extract category from token (e.g., {{loan.amount}} -> loan)
        category = token.replace("{{", "").split(".")[0]
        if category in grouped:
            grouped[category][token] = description

    return {
        "tokens": tokens,
        "grouped": grouped,
        "usage_example": "Use {{borrower.first_name}} in slide content to insert the borrower's first name.",
    }


@router.get("/ai/project-types")
async def get_project_types(
    request: Request,
    db: Session = Depends(get_db)
):
    """Get available project types with descriptions."""
    await get_user_from_request(request, db)

    return {
        "project_types": [
            {
                "value": "just_closed",
                "label": "Just Closed",
                "description": "Celebrate a successful loan closing with your clients",
                "suggested_crm_data": ["active_loan", "mum_client"],
            },
            {
                "value": "rate_update",
                "label": "Rate Update",
                "description": "Share mortgage rate updates and market trends",
                "suggested_crm_data": [],
            },
            {
                "value": "educational",
                "label": "Educational",
                "description": "Teach homebuyers about mortgage concepts and tips",
                "suggested_crm_data": [],
            },
            {
                "value": "marketing",
                "label": "Marketing",
                "description": "Promote your services and value proposition",
                "suggested_crm_data": [],
            },
            {
                "value": "custom",
                "label": "Custom",
                "description": "Create custom content with your own prompt",
                "suggested_crm_data": ["active_loan", "lead", "mum_client"],
            },
        ],
    }


# =============================================================================
# Dynamic Project Routes (/{project_id}/...)
# =============================================================================

@router.get("/{project_id}", response_model=ProjectDetailResponse)
async def get_project(
    request: Request,
    project_id: str,
    db: Session = Depends(get_db)
):
    """Get a carousel project with its slides."""
    user = await get_user_from_request(request, db)

    project = db.query(CarouselProject).options(
        joinedload(CarouselProject.slides)
    ).filter(
        CarouselProject.id == project_id
    ).first()

    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    if not check_project_access(project, user.id):
        raise HTTPException(status_code=403, detail="Access denied")

    return {
        "id": project.id,
        "name": project.name,
        "description": project.description,
        "project_type": project.project_type.value if hasattr(project.project_type, 'value') else str(project.project_type),
        "platform": project.platform.value if hasattr(project.platform, 'value') else str(project.platform),
        "aspect_ratio": project.aspect_ratio.value if hasattr(project.aspect_ratio, 'value') else str(project.aspect_ratio),
        "width": project.width,
        "height": project.height,
        "loan_id": project.loan_id,
        "lead_id": project.lead_id,
        "theme_id": project.theme_id,
        "custom_branding": project.custom_branding or {},
        "status": project.status.value if hasattr(project.status, 'value') else str(project.status),
        "ai_generated": project.ai_generated,
        "created_at": project.created_at,
        "updated_at": project.updated_at,
        "slides": [
            {
                "id": s.id,
                "order": s.order,
                "title": s.title,
                "subtitle": s.subtitle,
                "body_text": s.body_text,
                "background_type": s.background_type.value if hasattr(s.background_type, 'value') else str(s.background_type),
                "background_color": s.background_color,
                "background_gradient": s.background_gradient,
                "background_image_url": s.background_image_url,
                "layout_template": s.layout_template.value if hasattr(s.layout_template, 'value') else str(s.layout_template),
                "elements": s.elements or [],
                "custom_styles": s.custom_styles or {},
                "created_at": s.created_at,
                "updated_at": s.updated_at,
            }
            for s in sorted(project.slides, key=lambda x: x.order)
        ],
    }


@router.put("/{project_id}", response_model=ProjectResponse)
async def update_project(
    request: Request,
    project_id: str,
    project_data: ProjectUpdate,
    db: Session = Depends(get_db)
):
    """Update a carousel project."""
    user = await get_user_from_request(request, db)

    project = db.query(CarouselProject).filter(
        CarouselProject.id == project_id
    ).first()

    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    if not check_project_access(project, user.id):
        raise HTTPException(status_code=403, detail="Access denied")

    # Update fields
    update_data = project_data.dict(exclude_unset=True)

    if 'aspect_ratio' in update_data:
        width, height = get_dimensions_for_aspect_ratio(update_data['aspect_ratio'])
        project.width = width
        project.height = height

    _protected = {'id', 'organization_id', 'created_at', 'updated_at', 'user_id'}
    for key, value in update_data.items():
        if hasattr(project, key) and key not in _protected:
            setattr(project, key, value)

    project.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(project)

    slide_count = db.query(func.count(CarouselSlide.id)).filter(
        CarouselSlide.project_id == project.id
    ).scalar()

    return {
        "id": project.id,
        "name": project.name,
        "description": project.description,
        "project_type": project.project_type.value if hasattr(project.project_type, 'value') else str(project.project_type),
        "platform": project.platform.value if hasattr(project.platform, 'value') else str(project.platform),
        "aspect_ratio": project.aspect_ratio.value if hasattr(project.aspect_ratio, 'value') else str(project.aspect_ratio),
        "width": project.width,
        "height": project.height,
        "loan_id": project.loan_id,
        "lead_id": project.lead_id,
        "theme_id": project.theme_id,
        "custom_branding": project.custom_branding or {},
        "status": project.status.value if hasattr(project.status, 'value') else str(project.status),
        "ai_generated": project.ai_generated,
        "slide_count": slide_count,
        "created_at": project.created_at,
        "updated_at": project.updated_at,
    }


@router.delete("/{project_id}")
async def delete_project(
    request: Request,
    project_id: str,
    db: Session = Depends(get_db)
):
    """Delete a carousel project."""
    user = await get_user_from_request(request, db)

    project = db.query(CarouselProject).filter(
        CarouselProject.id == project_id
    ).first()

    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    if not check_project_access(project, user.id):
        raise HTTPException(status_code=403, detail="Access denied")

    db.delete(project)
    db.commit()

    return {"success": True, "message": "Project deleted"}


# =============================================================================
# Slide Routes
# =============================================================================

@router.get("/{project_id}/slides", response_model=List[SlideResponse])
async def list_slides(
    request: Request,
    project_id: str,
    db: Session = Depends(get_db)
):
    """List slides for a project."""
    user = await get_user_from_request(request, db)

    project = db.query(CarouselProject).filter(
        CarouselProject.id == project_id
    ).first()

    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    if not check_project_access(project, user.id):
        raise HTTPException(status_code=403, detail="Access denied")

    slides = db.query(CarouselSlide).filter(
        CarouselSlide.project_id == project_id
    ).order_by(CarouselSlide.order).all()

    return [
        {
            "id": s.id,
            "order": s.order,
            "title": s.title,
            "subtitle": s.subtitle,
            "body_text": s.body_text,
            "background_type": s.background_type.value if hasattr(s.background_type, 'value') else str(s.background_type),
            "background_color": s.background_color,
            "background_gradient": s.background_gradient,
            "background_image_url": s.background_image_url,
            "layout_template": s.layout_template.value if hasattr(s.layout_template, 'value') else str(s.layout_template),
            "elements": s.elements or [],
            "custom_styles": s.custom_styles or {},
            "created_at": s.created_at,
            "updated_at": s.updated_at,
        }
        for s in slides
    ]


@router.post("/{project_id}/slides", response_model=SlideResponse)
async def create_slide(
    request: Request,
    project_id: str,
    slide_data: SlideCreate,
    db: Session = Depends(get_db)
):
    """Add a new slide to a project."""
    user = await get_user_from_request(request, db)

    project = db.query(CarouselProject).filter(
        CarouselProject.id == project_id
    ).first()

    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    if not check_project_access(project, user.id):
        raise HTTPException(status_code=403, detail="Access denied")

    # Get next order
    max_order = db.query(func.max(CarouselSlide.order)).filter(
        CarouselSlide.project_id == project_id
    ).scalar() or -1

    slide = CarouselSlide(
        id=generate_short_uuid(),
        project_id=project_id,
        order=max_order + 1,
        title=slide_data.title,
        subtitle=slide_data.subtitle,
        body_text=slide_data.body_text,
        background_type=slide_data.background_type,
        background_color=slide_data.background_color,
        background_gradient=slide_data.background_gradient,
        background_image_url=slide_data.background_image_url,
        layout_template=slide_data.layout_template,
        elements=slide_data.elements,
        custom_styles=slide_data.custom_styles,
    )

    db.add(slide)

    # Update project timestamp
    project.updated_at = datetime.now(timezone.utc)

    db.commit()
    db.refresh(slide)

    return {
        "id": slide.id,
        "order": slide.order,
        "title": slide.title,
        "subtitle": slide.subtitle,
        "body_text": slide.body_text,
        "background_type": slide.background_type.value if hasattr(slide.background_type, 'value') else str(slide.background_type),
        "background_color": slide.background_color,
        "background_gradient": slide.background_gradient,
        "background_image_url": slide.background_image_url,
        "layout_template": slide.layout_template.value if hasattr(slide.layout_template, 'value') else str(slide.layout_template),
        "elements": slide.elements or [],
        "custom_styles": slide.custom_styles or {},
        "created_at": slide.created_at,
        "updated_at": slide.updated_at,
    }


@router.put("/{project_id}/slides/reorder")
async def reorder_slides(
    request: Request,
    project_id: str,
    reorder_data: SlideReorder,
    db: Session = Depends(get_db)
):
    """Reorder slides in a project."""
    user = await get_user_from_request(request, db)

    project = db.query(CarouselProject).filter(
        CarouselProject.id == project_id
    ).first()

    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    if not check_project_access(project, user.id):
        raise HTTPException(status_code=403, detail="Access denied")

    # Update order for each slide
    for i, slide_id in enumerate(reorder_data.slide_ids):
        db.query(CarouselSlide).filter(
            CarouselSlide.id == slide_id,
            CarouselSlide.project_id == project_id
        ).update({"order": i})

    project.updated_at = datetime.now(timezone.utc)
    db.commit()

    return {"success": True, "message": "Slides reordered"}


@router.put("/{project_id}/slides/{slide_id}", response_model=SlideResponse)
async def update_slide(
    request: Request,
    project_id: str,
    slide_id: str,
    slide_data: SlideUpdate,
    db: Session = Depends(get_db)
):
    """Update a slide."""
    user = await get_user_from_request(request, db)

    project = db.query(CarouselProject).filter(
        CarouselProject.id == project_id
    ).first()

    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    if not check_project_access(project, user.id):
        raise HTTPException(status_code=403, detail="Access denied")

    slide = db.query(CarouselSlide).filter(
        CarouselSlide.id == slide_id,
        CarouselSlide.project_id == project_id
    ).first()

    if not slide:
        raise HTTPException(status_code=404, detail="Slide not found")

    # Update fields
    update_data = slide_data.dict(exclude_unset=True)
    _protected = {'id', 'organization_id', 'created_at', 'updated_at', 'user_id'}
    for key, value in update_data.items():
        if hasattr(slide, key) and key not in _protected:
            setattr(slide, key, value)

    slide.updated_at = datetime.now(timezone.utc)
    project.updated_at = datetime.now(timezone.utc)

    db.commit()
    db.refresh(slide)

    return {
        "id": slide.id,
        "order": slide.order,
        "title": slide.title,
        "subtitle": slide.subtitle,
        "body_text": slide.body_text,
        "background_type": slide.background_type.value if hasattr(slide.background_type, 'value') else str(slide.background_type),
        "background_color": slide.background_color,
        "background_gradient": slide.background_gradient,
        "background_image_url": slide.background_image_url,
        "layout_template": slide.layout_template.value if hasattr(slide.layout_template, 'value') else str(slide.layout_template),
        "elements": slide.elements or [],
        "custom_styles": slide.custom_styles or {},
        "created_at": slide.created_at,
        "updated_at": slide.updated_at,
    }


@router.delete("/{project_id}/slides/{slide_id}")
async def delete_slide(
    request: Request,
    project_id: str,
    slide_id: str,
    db: Session = Depends(get_db)
):
    """Delete a slide."""
    user = await get_user_from_request(request, db)

    project = db.query(CarouselProject).filter(
        CarouselProject.id == project_id
    ).first()

    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    if not check_project_access(project, user.id):
        raise HTTPException(status_code=403, detail="Access denied")

    slide = db.query(CarouselSlide).filter(
        CarouselSlide.id == slide_id,
        CarouselSlide.project_id == project_id
    ).first()

    if not slide:
        raise HTTPException(status_code=404, detail="Slide not found")

    deleted_order = slide.order
    db.delete(slide)

    # Reorder remaining slides
    db.query(CarouselSlide).filter(
        CarouselSlide.project_id == project_id,
        CarouselSlide.order > deleted_order
    ).update({"order": CarouselSlide.order - 1})

    project.updated_at = datetime.now(timezone.utc)
    db.commit()

    return {"success": True, "message": "Slide deleted"}


@router.post("/{project_id}/slides/{slide_id}/duplicate", response_model=SlideResponse)
async def duplicate_slide(
    request: Request,
    project_id: str,
    slide_id: str,
    db: Session = Depends(get_db)
):
    """Duplicate a slide."""
    user = await get_user_from_request(request, db)

    project = db.query(CarouselProject).filter(
        CarouselProject.id == project_id
    ).first()

    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    if not check_project_access(project, user.id):
        raise HTTPException(status_code=403, detail="Access denied")

    original = db.query(CarouselSlide).filter(
        CarouselSlide.id == slide_id,
        CarouselSlide.project_id == project_id
    ).first()

    if not original:
        raise HTTPException(status_code=404, detail="Slide not found")

    # Shift orders for slides after this one
    db.query(CarouselSlide).filter(
        CarouselSlide.project_id == project_id,
        CarouselSlide.order > original.order
    ).update({"order": CarouselSlide.order + 1})

    # Create duplicate
    new_slide = CarouselSlide(
        id=generate_short_uuid(),
        project_id=project_id,
        order=original.order + 1,
        title=original.title,
        subtitle=original.subtitle,
        body_text=original.body_text,
        background_type=original.background_type,
        background_color=original.background_color,
        background_gradient=original.background_gradient,
        background_image_url=original.background_image_url,
        layout_template=original.layout_template,
        elements=original.elements.copy() if original.elements else [],
        custom_styles=original.custom_styles.copy() if original.custom_styles else {},
    )

    db.add(new_slide)
    project.updated_at = datetime.now(timezone.utc)

    db.commit()
    db.refresh(new_slide)

    return {
        "id": new_slide.id,
        "order": new_slide.order,
        "title": new_slide.title,
        "subtitle": new_slide.subtitle,
        "body_text": new_slide.body_text,
        "background_type": new_slide.background_type.value if hasattr(new_slide.background_type, 'value') else str(new_slide.background_type),
        "background_color": new_slide.background_color,
        "background_gradient": new_slide.background_gradient,
        "background_image_url": new_slide.background_image_url,
        "layout_template": new_slide.layout_template.value if hasattr(new_slide.layout_template, 'value') else str(new_slide.layout_template),
        "elements": new_slide.elements or [],
        "custom_styles": new_slide.custom_styles or {},
        "created_at": new_slide.created_at,
        "updated_at": new_slide.updated_at,
    }


# =============================================================================
# Apply Template Route
# =============================================================================

class ApplyTemplateRequest(BaseModel):
    """Request to apply a template to an existing project"""
    template_id: str


@router.post("/{project_id}/apply-template")
async def apply_template_to_project(
    request: Request,
    project_id: str,
    template_data: ApplyTemplateRequest,
    db: Session = Depends(get_db)
):
    """
    Apply a template to an existing project.

    This replaces all existing slides with the template's slides.
    """
    user = await get_user_from_request(request, db)

    project = db.query(CarouselProject).filter(
        CarouselProject.id == project_id
    ).first()

    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    if not check_project_access(project, user.id):
        raise HTTPException(status_code=403, detail="Access denied")

    # Get the template
    template = db.query(CarouselTemplate).filter(
        CarouselTemplate.id == template_data.template_id
    ).first()

    if not template:
        raise HTTPException(status_code=404, detail="Template not found")

    # Delete existing slides
    db.query(CarouselSlide).filter(
        CarouselSlide.project_id == project_id
    ).delete()

    # Create slides from template
    new_slides = []
    if template.slide_templates:
        for i, slide_template in enumerate(template.slide_templates):
            slide = CarouselSlide(
                id=generate_short_uuid(),
                project_id=project_id,
                order=i,
                title=slide_template.get('title'),
                subtitle=slide_template.get('subtitle'),
                body_text=slide_template.get('body_text'),
                background_type=slide_template.get('background_type', 'solid'),
                background_color=slide_template.get('background_color', '#217F8D'),
                background_gradient=slide_template.get('background_gradient'),
                layout_template=slide_template.get('layout_template', 'centered'),
                elements=slide_template.get('elements', []),
                custom_styles=slide_template.get('custom_styles', {}),
            )
            db.add(slide)
            new_slides.append(slide)

    # Update template usage count
    template.times_used = (template.times_used or 0) + 1

    # Update project timestamp
    project.updated_at = datetime.now(timezone.utc)

    db.commit()

    # Refresh slides
    for slide in new_slides:
        db.refresh(slide)

    return {
        "success": True,
        "project": {
            "id": project.id,
            "name": project.name,
        },
        "slides": [
            {
                "id": s.id,
                "order": s.order,
                "title": s.title,
                "subtitle": s.subtitle,
                "body_text": s.body_text,
                "background_type": s.background_type.value if hasattr(s.background_type, 'value') else str(s.background_type),
                "background_color": s.background_color,
                "background_gradient": s.background_gradient,
                "background_image_url": s.background_image_url,
                "layout_template": s.layout_template.value if hasattr(s.layout_template, 'value') else str(s.layout_template),
                "elements": s.elements or [],
                "custom_styles": s.custom_styles or {},
                "created_at": s.created_at,
                "updated_at": s.updated_at,
            }
            for s in new_slides
        ],
        "template_applied": template.name,
    }


# =============================================================================
# Export Routes
# =============================================================================

@router.post("/{project_id}/export")
async def request_export(
    request: Request,
    project_id: str,
    export_data: ExportRequest,
    db: Session = Depends(get_db)
):
    """Request carousel export. Returns export ID for tracking."""
    user = await get_user_from_request(request, db)

    project = db.query(CarouselProject).filter(
        CarouselProject.id == project_id
    ).first()

    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    if not check_project_access(project, user.id):
        raise HTTPException(status_code=403, detail="Access denied")

    # Create export record
    export = CarouselExport(
        id=generate_short_uuid(),
        project_id=project_id,
        user_id=user.id,
        export_format=export_data.format,
        quality=export_data.quality,
        scale=export_data.scale,
        status=ExportStatus.PENDING,
    )

    db.add(export)

    # Update project
    project.last_exported_at = datetime.now(timezone.utc)
    project.export_format = export_data.format
    project.status = CarouselStatus.EXPORTED

    db.commit()
    db.refresh(export)

    return {
        "export_id": export.id,
        "status": export.status.value,
        "message": "Export requested. Use client-side html2canvas for rendering.",
    }


@router.get("/{project_id}/export/status")
async def get_export_status(
    request: Request,
    project_id: str,
    export_id: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    """Get export status."""
    user = await get_user_from_request(request, db)

    project = db.query(CarouselProject).filter(
        CarouselProject.id == project_id
    ).first()

    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    if not check_project_access(project, user.id):
        raise HTTPException(status_code=403, detail="Access denied")

    if export_id:
        export = db.query(CarouselExport).filter(
            CarouselExport.id == export_id,
            CarouselExport.project_id == project_id
        ).first()
    else:
        export = db.query(CarouselExport).filter(
            CarouselExport.project_id == project_id
        ).order_by(desc(CarouselExport.created_at)).first()

    if not export:
        raise HTTPException(status_code=404, detail="Export not found")

    return {
        "export_id": export.id,
        "status": export.status.value,
        "format": export.export_format,
        "quality": export.quality,
        "scale": export.scale,
        "file_keys": export.file_keys or [],
        "zip_file_key": export.zip_file_key,
        "created_at": export.created_at,
        "completed_at": export.completed_at,
        "error_message": export.error_message,
    }


# =============================================================================
# AI Generation Routes
# =============================================================================

@router.post("/{project_id}/generate")
async def generate_carousel_content(
    request: Request,
    project_id: str,
    generate_data: AIGenerateRequest,
    db: Session = Depends(get_db)
):
    """
    Generate AI content for a carousel project.

    Uses Claude to generate slide content based on project type,
    platform, and optionally linked CRM data (loan/lead).
    """
    user = await get_user_from_request(request, db)

    project = db.query(CarouselProject).filter(
        CarouselProject.id == project_id
    ).first()

    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    if not check_project_access(project, user.id):
        raise HTTPException(status_code=403, detail="Access denied")

    # Get CRM data if available and requested
    crm_data = None
    if generate_data.include_crm_data:
        crm_data = await get_crm_data_for_project(project, db)

    # Add LO info from user if not provided
    lo_info = generate_data.lo_info or {}
    if not lo_info.get('name') and not lo_info.get('loan_officer_name'):
        lo_info['name'] = getattr(user, 'name', None) or getattr(user, 'full_name', None)
    if not lo_info.get('email') and not lo_info.get('loan_officer_email'):
        lo_info['email'] = getattr(user, 'email', None)

    # Generate content
    result = await carousel_content_service.generate_carousel_content(
        project_type=project.project_type.value if hasattr(project.project_type, 'value') else str(project.project_type),
        platform=project.platform.value if hasattr(project.platform, 'value') else str(project.platform),
        num_slides=generate_data.num_slides,
        crm_data=crm_data,
        custom_prompt=generate_data.custom_prompt,
        lo_info=lo_info,
    )

    if not result.get('success'):
        raise HTTPException(
            status_code=500,
            detail=result.get('error', 'AI generation failed')
        )

    # Optionally create slides from the generated content
    generated_slides = result.get('slides', [])

    return {
        "success": True,
        "project_id": project_id,
        "slides": generated_slides,
        "metadata": {
            "project_type": project.project_type.value if hasattr(project.project_type, 'value') else str(project.project_type),
            "platform": project.platform.value if hasattr(project.platform, 'value') else str(project.platform),
            "num_slides": len(generated_slides),
            "crm_data_used": crm_data is not None,
            "tokens_used": result.get('tokens_used'),
            "generated_at": result.get('generated_at'),
        },
    }


@router.post("/{project_id}/apply-generated")
async def apply_generated_content(
    request: Request,
    project_id: str,
    slides_data: List[Dict[str, Any]],
    db: Session = Depends(get_db)
):
    """
    Apply AI-generated slides to a project.

    Replaces existing slides with the generated content.
    """
    user = await get_user_from_request(request, db)

    project = db.query(CarouselProject).filter(
        CarouselProject.id == project_id
    ).first()

    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    if not check_project_access(project, user.id):
        raise HTTPException(status_code=403, detail="Access denied")

    # Delete existing slides
    db.query(CarouselSlide).filter(
        CarouselSlide.project_id == project_id
    ).delete()

    # Create new slides from generated content
    new_slides = []
    for i, slide_data in enumerate(slides_data):
        # Determine background color from suggested colors
        bg_color = "#217F8D"  # Default
        if slide_data.get('suggested_colors'):
            bg_color = slide_data['suggested_colors'][0]

        slide = CarouselSlide(
            id=generate_short_uuid(),
            project_id=project_id,
            order=i,
            title=slide_data.get('title', ''),
            subtitle=slide_data.get('subtitle', ''),
            body_text=slide_data.get('body_text', ''),
            background_type=SlideBackgroundType.GRADIENT if slide_data.get('suggested_background') == 'gradient' else SlideBackgroundType.SOLID,
            background_color=bg_color,
            background_gradient={
                "angle": 135,
                "colors": slide_data.get('suggested_colors', [bg_color, "#1a5f6a"])
            } if slide_data.get('suggested_background') == 'gradient' else None,
            layout_template=SlideLayoutTemplate.CENTERED,
            elements=[],
            custom_styles={"textColor": "#ffffff"},
        )
        db.add(slide)
        new_slides.append(slide)

    # Mark project as AI generated
    project.ai_generated = True
    project.updated_at = datetime.now(timezone.utc)

    db.commit()

    # Refresh slides
    for slide in new_slides:
        db.refresh(slide)

    return {
        "success": True,
        "project_id": project_id,
        "slides_created": len(new_slides),
        "slides": [
            {
                "id": s.id,
                "order": s.order,
                "title": s.title,
                "subtitle": s.subtitle,
                "body_text": s.body_text,
                "background_type": s.background_type.value if hasattr(s.background_type, 'value') else str(s.background_type),
                "background_color": s.background_color,
                "background_gradient": s.background_gradient,
                "layout_template": s.layout_template.value if hasattr(s.layout_template, 'value') else str(s.layout_template),
            }
            for s in new_slides
        ],
    }


@router.get("/{project_id}/crm-data")
async def get_project_crm_data(
    request: Request,
    project_id: str,
    db: Session = Depends(get_db)
):
    """Get CRM data linked to a project."""
    user = await get_user_from_request(request, db)

    project = db.query(CarouselProject).filter(
        CarouselProject.id == project_id
    ).first()

    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    if not check_project_access(project, user.id):
        raise HTTPException(status_code=403, detail="Access denied")

    crm_data = await get_crm_data_for_project(project, db)

    return {
        "project_id": project_id,
        "has_crm_data": crm_data is not None,
        "data_source": get_data_source_type(project),
        "crm_data": crm_data,
        "available_tokens": list(carousel_content_service.get_available_tokens().keys()) if crm_data else [],
    }


async def get_crm_data_for_project(project: CarouselProject, db: Session) -> Optional[Dict[str, Any]]:
    """Helper to fetch CRM data linked to a project."""
    try:
        # Check for linked active loan
        if project.active_loan_id:
            from models.active_loan_profile import ActiveLoanProfile
            loan = db.query(ActiveLoanProfile).filter(
                ActiveLoanProfile.id == project.active_loan_id
            ).first()
            if loan:
                return loan.to_dict()

        # Check for linked lead
        if project.lead_id:
            from models.lead_profile import LeadProfile
            lead = db.query(LeadProfile).filter(
                LeadProfile.id == project.lead_id
            ).first()
            if lead:
                return lead.to_dict()

        # Check for linked MUM client (funded loan)
        if project.loan_id:
            from models.mum_client_profile import MUMClientProfile
            mum = db.query(MUMClientProfile).filter(
                MUMClientProfile.id == str(project.loan_id)
            ).first()
            if mum:
                return mum.to_dict()

    except Exception as e:
        logger.warning(f"Error fetching CRM data for project {project.id}: {e}")

    return None


def get_data_source_type(project: CarouselProject) -> Optional[str]:
    """Get the type of CRM data linked to a project."""
    if project.active_loan_id:
        return "active_loan"
    if project.lead_id:
        return "lead"
    if project.loan_id:
        return "mum_client"
    return None


# =============================================================================
# Image Upload Routes
# =============================================================================

@router.post("/{project_id}/images/upload-url")
async def get_image_upload_url(
    request: Request,
    project_id: str,
    upload_data: ImageUploadRequest,
    db: Session = Depends(get_db)
):
    """
    Get a presigned URL for uploading an image to S3.

    The client should use this URL to upload the image directly to S3,
    then call the confirm endpoint with the storage key.
    """
    user = await get_user_from_request(request, db)

    project = db.query(CarouselProject).filter(
        CarouselProject.id == project_id
    ).first()

    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    if not check_project_access(project, user.id):
        raise HTTPException(status_code=403, detail="Access denied")

    # Validate content type
    allowed_types = ['image/jpeg', 'image/png', 'image/gif', 'image/webp']
    if upload_data.content_type not in allowed_types:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid content type. Allowed: {', '.join(allowed_types)}"
        )

    # Generate storage key
    # TENANT-011: Prefix with org_id for multi-tenant S3 isolation
    s3_service = get_s3_service()
    ext = upload_data.file_name.rsplit('.', 1)[-1].lower() if '.' in upload_data.file_name else 'png'
    _org_id = getattr(user, 'organization_id', None) or "unscoped"
    storage_key = f"org_{_org_id}/carousels/{project_id}/images/{generate_short_uuid()}.{ext}"

    # Get presigned URL
    result = s3_service.get_presigned_put_url(storage_key, upload_data.content_type)

    if not result.get("success"):
        raise HTTPException(status_code=500, detail=result.get("error", "Failed to generate upload URL"))

    return {
        "upload_url": result["presigned_url"],
        "storage_key": storage_key,
        "method": "PUT",
        "headers": result.get("headers", {}),
        "expires_in": result.get("expires_in"),
    }


@router.post("/{project_id}/images/confirm")
async def confirm_image_upload(
    request: Request,
    project_id: str,
    storage_key: str,
    db: Session = Depends(get_db)
):
    """
    Confirm an image upload and get the public URL.

    Call this after successfully uploading to the presigned URL.
    """
    user = await get_user_from_request(request, db)

    project = db.query(CarouselProject).filter(
        CarouselProject.id == project_id
    ).first()

    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    if not check_project_access(project, user.id):
        raise HTTPException(status_code=403, detail="Access denied")

    # Verify the upload
    s3_service = get_s3_service()
    verify_result = s3_service.verify_upload(storage_key)

    if not verify_result.get("success") or not verify_result.get("exists"):
        raise HTTPException(status_code=404, detail="Image not found. Upload may have failed.")

    # Make the image publicly accessible and get URL
    carousel_org_id = getattr(user, 'organization_id', None)
    url_result = s3_service.make_public_and_get_url(storage_key, organization_id=carousel_org_id)

    if not url_result.get("success"):
        raise HTTPException(status_code=500, detail="Failed to get image URL")

    return {
        "success": True,
        "storage_key": storage_key,
        "url": url_result.get("public_url") or url_result.get("presigned_url"),
        "file_size": verify_result.get("file_size"),
        "content_type": verify_result.get("content_type"),
    }


@router.delete("/{project_id}/images/{storage_key:path}")
async def delete_image(
    request: Request,
    project_id: str,
    storage_key: str,
    db: Session = Depends(get_db)
):
    """Delete an uploaded image."""
    user = await get_user_from_request(request, db)

    project = db.query(CarouselProject).filter(
        CarouselProject.id == project_id
    ).first()

    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    if not check_project_access(project, user.id):
        raise HTTPException(status_code=403, detail="Access denied")

    # Verify the storage key belongs to this project
    if not storage_key.startswith(f"carousels/{project_id}/"):
        raise HTTPException(status_code=403, detail="Cannot delete images from other projects")

    s3_service = get_s3_service()
    result = s3_service.delete_document(storage_key)

    if not result.get("success"):
        raise HTTPException(status_code=500, detail="Failed to delete image")

    return {"success": True, "deleted": storage_key}
