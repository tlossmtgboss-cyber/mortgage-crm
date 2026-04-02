"""
Microsite Platform API Routes

Multi-tenant microsite management system endpoints for:
- Template pack management
- User microsite CRUD operations
- Asset uploads
- Public microsite rendering
- Lead capture
- Analytics tracking
"""

from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form, Request
from sqlalchemy.orm import Session
from sqlalchemy import text, or_
from typing import List, Optional
from datetime import datetime, timedelta, timezone
import os
import uuid
import hashlib

from database import get_db
from services.notification_service import NotificationService
import logging
from sqlalchemy.exc import SQLAlchemyError

logger = logging.getLogger(__name__)

# Wrapper for lazy loading get_current_user from main (avoids circular import)
def get_current_user_dep():
    """Get current user dependency from main module."""
    import main
    return main.get_current_user

def get_current_user_optional_dep():
    """Get optional current user dependency from main module."""
    import main
    return main.get_current_user_optional

from models.microsite import (
    MicrositeTemplatePack, MicrositePage, MicrositeAsset, MicrositePublishHistory,
    MicrositeAnalyticsEvent, MicrositeLead, OrganizationMicrositeSettings,
    MicrositeCustomPage,
    MicrositeStatus, TemplateStatus, LeadStatus, AnalyticsEventType,
    TemplatePackResponse, TemplatePackListResponse, TemplatePackCreate,
    MicrositeCreate, MicrositeUpdate, MicrositeResponse, MicrositePublicResponse,
    AssetUploadResponse, LeadCreate, LeadResponse,
    AnalyticsEventCreate, AnalyticsSummary,
    PublishResponse, PublishHistoryResponse,
    OrgMicrositeSettingsUpdate, OrgMicrositeSettingsResponse,
    ContentValidator, MicrositeSlugGenerator,
    CustomPageCreate, CustomPageUpdate, CustomPageResponse
)

router = APIRouter(prefix="/api/v1/microsites", tags=["microsites"])

# Configuration
MICROSITE_DOMAIN = os.getenv("MICROSITE_DOMAIN", "sites.perennia.ai")
STORAGE_PATH = os.getenv("MICROSITE_STORAGE_PATH", "/tmp/microsite-assets")


# ============================================================================
# TEMPLATE PACK ENDPOINTS
# ============================================================================

@router.get("/templates", response_model=List[TemplatePackListResponse])
async def list_template_packs(
    status: Optional[str] = "active",
    category: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_dep())
):
    """
    List available template packs for the current organization.
    Returns global templates + org-specific templates.
    """
    try:
        # Get user's organization_id (may be None)
        org_id = getattr(current_user, 'organization_id', None)

        # Build query - if org_id is None, just get global templates
        if org_id is not None:
            query = db.query(MicrositeTemplatePack).filter(
                MicrositeTemplatePack.status == status,
                or_(
                    MicrositeTemplatePack.organization_id == org_id,
                    MicrositeTemplatePack.organization_id.is_(None)
                )
            )
        else:
            # User has no organization - only show global templates
            query = db.query(MicrositeTemplatePack).filter(
                MicrositeTemplatePack.status == status,
                MicrositeTemplatePack.organization_id.is_(None)
            )

        if category:
            query = query.filter(MicrositeTemplatePack.category == category)

        templates = query.order_by(MicrositeTemplatePack.name).all()
        return templates
    except SQLAlchemyError as e:
        error_str = str(e).lower()
        # Handle missing table gracefully - return empty list
        if "undefined" in error_str and "table" in error_str or "does not exist" in error_str:
            logger.warning(f"Microsite templates table not found, returning empty list: {str(e)}")
            return []
        logger.error(f"Error fetching microsite templates: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Database error")


@router.get("/templates/{template_id}", response_model=TemplatePackResponse)
async def get_template_pack(
    template_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_dep())
):
    """Get specific template pack details including schema"""
    template = db.query(MicrositeTemplatePack).filter(
        MicrositeTemplatePack.id == template_id
    ).first()

    if not template:
        raise HTTPException(status_code=404, detail="Template pack not found")

    # Verify access (org-specific or global)
    if template.organization_id and template.organization_id != current_user.organization_id:
        raise HTTPException(status_code=403, detail="Access denied")

    return template


@router.post("/templates", response_model=TemplatePackResponse, status_code=status.HTTP_201_CREATED)
async def create_template_pack(
    template_data: TemplatePackCreate,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_dep())
):
    """Create new template pack (admin only)"""
    # Check if user has admin role
    if current_user.role not in ['admin', 'super_admin', 'owner']:
        raise HTTPException(status_code=403, detail="Insufficient permissions")

    # Check for slug/version uniqueness
    existing = db.query(MicrositeTemplatePack).filter(
        MicrositeTemplatePack.slug == template_data.slug,
        MicrositeTemplatePack.version == template_data.version
    ).first()

    if existing:
        raise HTTPException(status_code=400, detail="Template slug/version already exists")

    db_template = MicrositeTemplatePack(
        organization_id=current_user.organization_id,
        created_by=current_user.id,
        **template_data.model_dump()
    )

    db.add(db_template)
    db.commit()
    db.refresh(db_template)

    return db_template


# ============================================================================
# USER MICROSITE ENDPOINTS
# ============================================================================

@router.get("/my", response_model=MicrositeResponse)
async def get_my_microsite(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_dep())
):
    """Get current user's microsite"""
    microsite = db.query(MicrositePage).filter(
        MicrositePage.user_id == current_user.id
    ).first()

    if not microsite:
        raise HTTPException(status_code=404, detail="No microsite found for this user")

    # Add computed public_url
    response = MicrositeResponse.model_validate(microsite)
    response.public_url = f"https://{microsite.slug}.{MICROSITE_DOMAIN}"

    return response


@router.post("", response_model=MicrositeResponse, status_code=status.HTTP_201_CREATED)
async def create_microsite(
    microsite_data: MicrositeCreate,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_dep())
):
    """Create a new microsite for the current user"""
    # Check if user already has a microsite
    existing = db.query(MicrositePage).filter(
        MicrositePage.user_id == current_user.id
    ).first()

    if existing:
        raise HTTPException(
            status_code=400,
            detail="User already has a microsite. Use PUT to update."
        )

    # Check slug uniqueness
    slug_exists = db.query(MicrositePage).filter(
        MicrositePage.slug == microsite_data.slug
    ).first()

    if slug_exists:
        raise HTTPException(status_code=400, detail="Slug already taken")

    # Get template to pin version
    template = db.query(MicrositeTemplatePack).filter(
        MicrositeTemplatePack.id == microsite_data.template_pack_id
    ).first()

    if not template:
        raise HTTPException(status_code=404, detail="Template pack not found")

    # Merge defaults with user content
    content = {**template.defaults_json, **(microsite_data.content_json or {})}

    # Validate content against schema
    validation_errors = ContentValidator.validate_content(content, template.schema_json)
    if validation_errors:
        raise HTTPException(status_code=400, detail={"validation_errors": validation_errors})

    # Get org compliance settings
    org_settings = db.query(OrganizationMicrositeSettings).filter(
        OrganizationMicrositeSettings.organization_id == current_user.organization_id
    ).first()

    # Build compliance JSON with locked org fields
    compliance_json = microsite_data.compliance_json or {}
    if org_settings:
        compliance_json.update({
            'companyNmls': org_settings.company_nmls,
            'companyName': org_settings.company_name,
            'companyAddress': org_settings.company_address,
            'companyPhone': org_settings.company_phone,
            'companyEmail': org_settings.company_email,
            'complianceFooter': org_settings.compliance_footer_html,
            'ehlLogo': True
        })

    # Create microsite
    db_microsite = MicrositePage(
        organization_id=current_user.organization_id,
        user_id=current_user.id,
        template_pack_id=template.id,
        template_version=template.version,
        slug=microsite_data.slug,
        status=MicrositeStatus.DRAFT.value,
        content_json=content,
        branding_json=microsite_data.branding_json or {},
        compliance_json=compliance_json
    )

    db.add(db_microsite)
    db.commit()
    db.refresh(db_microsite)

    response = MicrositeResponse.model_validate(db_microsite)
    response.public_url = f"https://{db_microsite.slug}.{MICROSITE_DOMAIN}"

    return response


@router.put("/my", response_model=MicrositeResponse)
async def update_my_microsite(
    update_data: MicrositeUpdate,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_dep())
):
    """Update current user's microsite content"""
    microsite = db.query(MicrositePage).filter(
        MicrositePage.user_id == current_user.id
    ).first()

    if not microsite:
        raise HTTPException(status_code=404, detail="No microsite found")

    # Get template for schema validation
    template = db.query(MicrositeTemplatePack).filter(
        MicrositeTemplatePack.id == microsite.template_pack_id,
        MicrositeTemplatePack.version == microsite.template_version
    ).first()

    # Update fields
    if update_data.content_json is not None:
        # Validate against schema
        validation_errors = ContentValidator.validate_content(
            update_data.content_json,
            template.schema_json
        )
        if validation_errors:
            raise HTTPException(
                status_code=400,
                detail={"validation_errors": validation_errors}
            )
        microsite.content_json = update_data.content_json

    if update_data.branding_json is not None:
        microsite.branding_json = update_data.branding_json

    if update_data.compliance_json is not None:
        # Users cannot override locked compliance fields
        org_settings = db.query(OrganizationMicrositeSettings).filter(
            OrganizationMicrositeSettings.organization_id == current_user.organization_id
        ).first()

        if org_settings:
            locked_fields = {
                'companyNmls': org_settings.company_nmls,
                'companyName': org_settings.company_name,
                'companyAddress': org_settings.company_address,
                'companyPhone': org_settings.company_phone,
                'companyEmail': org_settings.company_email,
                'complianceFooter': org_settings.compliance_footer_html,
                'ehlLogo': True
            }
            microsite.compliance_json = {**update_data.compliance_json, **locked_fields}
        else:
            microsite.compliance_json = update_data.compliance_json

    if update_data.seo_title is not None:
        microsite.seo_title = update_data.seo_title

    if update_data.seo_description is not None:
        microsite.seo_description = update_data.seo_description

    if update_data.seo_keywords is not None:
        microsite.seo_keywords = update_data.seo_keywords

    if update_data.status is not None:
        microsite.status = update_data.status.value

    db.commit()
    db.refresh(microsite)

    response = MicrositeResponse.model_validate(microsite)
    response.public_url = f"https://{microsite.slug}.{MICROSITE_DOMAIN}"

    return response


@router.post("/my/publish", response_model=PublishResponse)
async def publish_microsite(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_dep())
):
    """Publish user's microsite"""
    microsite = db.query(MicrositePage).filter(
        MicrositePage.user_id == current_user.id
    ).first()

    if not microsite:
        raise HTTPException(status_code=404, detail="No microsite found")

    # Validate required fields before publishing
    template = db.query(MicrositeTemplatePack).filter(
        MicrositeTemplatePack.id == microsite.template_pack_id,
        MicrositeTemplatePack.version == microsite.template_version
    ).first()

    validation_errors = ContentValidator.check_required_for_publish(
        microsite.content_json,
        template.schema_json
    )
    if validation_errors:
        raise HTTPException(
            status_code=400,
            detail={
                "message": "Cannot publish: missing required fields",
                "errors": validation_errors
            }
        )

    # Check if org requires approval
    org_settings = db.query(OrganizationMicrositeSettings).filter(
        OrganizationMicrositeSettings.organization_id == current_user.organization_id
    ).first()

    if org_settings and org_settings.require_approval_before_publish:
        # Set to pending approval and notify admins
        microsite.status = MicrositeStatus.PENDING_APPROVAL.value
        db.commit()

        # Notify organization admins about pending approval
        try:
            from services.notification_service import notification_service
            admins = db.execute(text("""
                SELECT email FROM users
                WHERE organization_id = :org_id AND role IN ('admin', 'owner')
            """), {"org_id": current_user.organization_id}).fetchall()

            for admin in admins:
                notification_service.send_email(
                    to_email=admin[0],
                    subject=f"Microsite Pending Approval - {microsite.slug}",
                    html_content=f"""
                    <p>A microsite is pending your approval:</p>
                    <ul>
                        <li><strong>User:</strong> {current_user.email}</li>
                        <li><strong>Slug:</strong> {microsite.slug}</li>
                    </ul>
                    <p>Please review and approve or reject the microsite.</p>
                    """
                )
        except Exception as notify_err:
            logger.warning(f"Failed to notify admins of pending microsite: {notify_err}")

        return PublishResponse(
            success=True,
            message="Microsite submitted for approval",
            public_url=None,
            preview_url=f"https://{microsite.slug}.{MICROSITE_DOMAIN}?preview=true"
        )

    # Update status
    microsite.status = MicrositeStatus.PUBLISHED.value

    db.commit()

    return PublishResponse(
        success=True,
        message="Microsite published successfully",
        public_url=f"https://{microsite.slug}.{MICROSITE_DOMAIN}",
        preview_url=f"https://{microsite.slug}.{MICROSITE_DOMAIN}?preview=true"
    )


@router.post("/my/unpublish", response_model=PublishResponse)
async def unpublish_microsite(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_dep())
):
    """Unpublish user's microsite"""
    microsite = db.query(MicrositePage).filter(
        MicrositePage.user_id == current_user.id
    ).first()

    if not microsite:
        raise HTTPException(status_code=404, detail="No microsite found")

    microsite.status = MicrositeStatus.DRAFT.value
    db.commit()

    return PublishResponse(
        success=True,
        message="Microsite unpublished"
    )


@router.get("/my/history", response_model=List[PublishHistoryResponse])
async def get_publish_history(
    limit: int = 20,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_dep())
):
    """Get publish history for user's microsite"""
    microsite = db.query(MicrositePage).filter(
        MicrositePage.user_id == current_user.id
    ).first()

    if not microsite:
        raise HTTPException(status_code=404, detail="No microsite found")

    history = db.query(MicrositePublishHistory).filter(
        MicrositePublishHistory.microsite_id == microsite.id
    ).order_by(MicrositePublishHistory.published_at.desc()).limit(limit).all()

    return history


# ============================================================================
# ASSET MANAGEMENT ENDPOINTS
# ============================================================================

@router.post("/my/assets/upload", response_model=AssetUploadResponse)
async def upload_asset(
    file: UploadFile = File(...),
    asset_type: str = Form(...),
    field_name: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_dep())
):
    """Upload image or other asset for microsite"""
    microsite = db.query(MicrositePage).filter(
        MicrositePage.user_id == current_user.id
    ).first()

    if not microsite:
        raise HTTPException(status_code=404, detail="No microsite found")

    # Validate file type
    allowed_types = {
        'image': ['image/jpeg', 'image/png', 'image/webp', 'image/gif'],
        'logo': ['image/png', 'image/svg+xml', 'image/webp'],
        'headshot': ['image/jpeg', 'image/png', 'image/webp']
    }

    if file.content_type not in allowed_types.get(asset_type, allowed_types['image']):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid file type for {asset_type}"
        )

    # Validate file size (max 5MB)
    file_content = await file.read()
    if len(file_content) > 5 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File size must be less than 5MB")

    # Generate unique filename
    file_ext = os.path.splitext(file.filename)[1]
    unique_id = str(uuid.uuid4())[:8]
    new_filename = f"{microsite.slug}-{asset_type}-{unique_id}{file_ext}"

    # Create storage path
    org_path = f"{STORAGE_PATH}/{current_user.organization_id}/{microsite.id}"
    os.makedirs(org_path, exist_ok=True)

    file_path = f"{org_path}/{new_filename}"

    # Save file
    with open(file_path, 'wb') as f:
        f.write(file_content)

    # Generate public URL (adjust based on your CDN/storage setup)
    public_url = f"/api/v1/microsites/assets/{current_user.organization_id}/{microsite.id}/{new_filename}"

    # Create asset record
    asset = MicrositeAsset(
        microsite_id=microsite.id,
        asset_type=asset_type,
        file_name=file.filename,
        file_path=file_path,
        file_size=len(file_content),
        mime_type=file.content_type,
        field_name=field_name
    )

    db.add(asset)
    db.commit()
    db.refresh(asset)

    return AssetUploadResponse(
        id=asset.id,
        url=public_url,
        asset_type=asset_type,
        field_name=field_name,
        file_name=file.filename,
        file_size=len(file_content),
        width=asset.width,
        height=asset.height
    )


@router.get("/assets/{org_id}/{microsite_id}/{filename}")
async def serve_asset(
    org_id: int,
    microsite_id: int,
    filename: str
):
    """Serve uploaded microsite assets (logos, headshots, images)"""
    from fastapi.responses import FileResponse
    from pathlib import Path

    # Sanitize filename to prevent path traversal
    safe_filename = os.path.basename(filename)
    if not safe_filename or safe_filename != filename:
        raise HTTPException(status_code=400, detail="Invalid filename")

    # Build file path and verify it's within the expected directory
    base_dir = Path(STORAGE_PATH).resolve()
    file_path = (base_dir / str(org_id) / str(microsite_id) / safe_filename).resolve()
    if not str(file_path).startswith(str(base_dir)):
        raise HTTPException(status_code=400, detail="Invalid path")

    # Check if file exists
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Asset not found")

    # Determine content type from extension
    ext = os.path.splitext(safe_filename)[1].lower()
    content_types = {
        '.jpg': 'image/jpeg',
        '.jpeg': 'image/jpeg',
        '.png': 'image/png',
        '.gif': 'image/gif',
        '.webp': 'image/webp',
        '.svg': 'image/svg+xml'
    }
    content_type = content_types.get(ext, 'application/octet-stream')

    return FileResponse(
        file_path,
        media_type=content_type,
        headers={
            "Cache-Control": "public, max-age=31536000",  # Cache for 1 year
            "Access-Control-Allow-Origin": "*"
        }
    )


# ============================================================================
# PUBLIC RENDERING ENDPOINT
# ============================================================================

@router.get("/public/{slug}", response_model=MicrositePublicResponse)
async def get_public_microsite(
    slug: str,
    preview: Optional[bool] = False,
    db: Session = Depends(get_db)
):
    """
    Get published microsite data for public rendering.
    Used by frontend to generate static pages.
    """
    query = db.query(MicrositePage).filter(
        MicrositePage.slug == slug
    )

    # If not preview mode, only return published sites
    if not preview:
        query = query.filter(MicrositePage.status == MicrositeStatus.PUBLISHED.value)

    microsite = query.first()

    if not microsite:
        raise HTTPException(status_code=404, detail="Microsite not found")

    # Get template
    template = db.query(MicrositeTemplatePack).filter(
        MicrositeTemplatePack.id == microsite.template_pack_id,
        MicrositeTemplatePack.version == microsite.template_version
    ).first()

    # Get user info
    user = db.execute(text("""
        SELECT full_name, email FROM users WHERE id = :user_id
    """), {"user_id": microsite.user_id}).fetchone()

    # Increment view count (consider using Redis for performance)
    if not preview:
        microsite.view_count = (microsite.view_count or 0) + 1
        db.commit()

    return MicrositePublicResponse(
        id=microsite.id,
        slug=microsite.slug,
        content_json=microsite.content_json,
        branding_json=microsite.branding_json,
        compliance_json=microsite.compliance_json,
        seo_title=microsite.seo_title,
        seo_description=microsite.seo_description,
        seo_image_url=microsite.seo_image_url,
        template_name=template.name if template else None,
        template_version=microsite.template_version,
        template_layout=template.template_json if template else None,
        user_name=user[0] if user else None,
        user_email=user[1] if user else None
    )


# ============================================================================
# LEAD CAPTURE ENDPOINT (PUBLIC)
# ============================================================================

@router.post("/public/leads", status_code=status.HTTP_201_CREATED)
async def capture_lead(
    lead_data: LeadCreate,
    db: Session = Depends(get_db)
):
    """
    Public endpoint for lead capture from microsite forms.
    No authentication required.
    """
    # Get microsite by slug
    microsite = db.query(MicrositePage).filter(
        MicrositePage.slug == lead_data.microsite_slug,
        MicrositePage.status == MicrositeStatus.PUBLISHED.value
    ).first()

    if not microsite:
        raise HTTPException(status_code=404, detail="Microsite not found")

    # Create lead record
    lead = MicrositeLead(
        microsite_id=microsite.id,
        organization_id=microsite.organization_id,
        user_id=microsite.user_id,
        first_name=lead_data.first_name,
        last_name=lead_data.last_name,
        email=lead_data.email,
        phone=lead_data.phone,
        intent_type=lead_data.intent_type,
        qualifier_answer=lead_data.qualifier_answer,
        session_id=lead_data.session_id,
        utm_source=lead_data.utm_source,
        utm_medium=lead_data.utm_medium,
        utm_campaign=lead_data.utm_campaign
    )

    db.add(lead)

    # Update microsite lead count
    microsite.lead_count = (microsite.lead_count or 0) + 1

    db.commit()
    db.refresh(lead)

    # Create lead in main CRM pipeline
    crm_lead_id = None
    try:
        # Lazy import to avoid circular imports
        import main
        Lead = main.Lead
        LeadStage = main.LeadStage
        User = main.User

        # Check for existing lead by email to avoid duplicates
        existing_lead = None
        if lead_data.email:
            existing_lead = db.query(Lead).filter(Lead.email == lead_data.email).first()

        if existing_lead:
            # Update existing lead with microsite source info
            if not existing_lead.source:
                existing_lead.source = f"microsite:{microsite.slug}"
            crm_lead_id = existing_lead.id
            logger.info(f"Microsite lead {lead.id} linked to existing CRM lead {crm_lead_id}")
        else:
            # Create new lead in CRM
            full_name = f"{lead_data.first_name} {lead_data.last_name}".strip()
            crm_lead = Lead(
                name=full_name,
                first_name=lead_data.first_name,
                last_name=lead_data.last_name,
                email=lead_data.email,
                phone=lead_data.phone,
                stage=LeadStage.NEW,
                source=f"microsite:{microsite.slug}",
                owner_id=microsite.user_id,
                notes=f"Intent: {lead_data.intent_type or 'Not specified'}\nQualifier: {lead_data.qualifier_answer or 'None'}\nUTM: {lead_data.utm_source}/{lead_data.utm_medium}/{lead_data.utm_campaign}"
            )
            db.add(crm_lead)
            db.commit()
            db.refresh(crm_lead)
            crm_lead_id = crm_lead.id
            logger.info(f"Created CRM lead {crm_lead_id} from microsite lead {lead.id}")

        # Get loan officer info for notification
        lo_user = db.query(User).filter(User.id == microsite.user_id).first()

        if lo_user and lo_user.email:
            # Send notification to loan officer
            try:
                notification_service = NotificationService()
                notification_result = notification_service.send_lo_new_lead_alert(
                    lo_email=lo_user.email,
                    lo_name=lo_user.full_name or lo_user.email,
                    lead_name=f"{lead_data.first_name} {lead_data.last_name}".strip(),
                    lead_email=lead_data.email,
                    lead_phone=lead_data.phone,
                    lead_source=f"Microsite: {microsite.title or microsite.slug}",
                    intent_type=lead_data.intent_type,
                    lead_id=crm_lead_id,
                    microsite_name=microsite.title or microsite.slug
                )
                logger.info(f"Lead notification sent to {lo_user.email}: {notification_result}")
            except Exception as notify_err:
                logger.error(f"Failed to send lead notification: {notify_err}")
                # Don't fail the lead capture just because notification failed

    except Exception as crm_err:
        logger.error(f"Failed to create CRM lead or send notification: {crm_err}")
        # Don't fail the microsite lead capture - it's already saved

    return {
        "success": True,
        "lead_id": lead.id,
        "crm_lead_id": crm_lead_id,
        "message": "Thank you! We'll contact you shortly."
    }


# ============================================================================
# ANALYTICS ENDPOINT (PUBLIC)
# ============================================================================

@router.post("/public/analytics/track")
async def track_analytics_event(
    event: AnalyticsEventCreate,
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Public endpoint for tracking analytics events.
    Called from microsite frontend.
    """
    # Get microsite
    microsite = db.query(MicrositePage).filter(
        MicrositePage.slug == event.microsite_slug,
        MicrositePage.status == MicrositeStatus.PUBLISHED.value
    ).first()

    if not microsite:
        raise HTTPException(status_code=404, detail="Microsite not found")

    # Get client IP
    client_ip = request.client.host if request.client else None

    # Create analytics event
    analytics_event = MicrositeAnalyticsEvent(
        microsite_id=microsite.id,
        event_type=event.event_type.value,
        event_data=event.event_data,
        session_id=event.session_id,
        visitor_id=event.visitor_id,
        utm_source=event.utm_source,
        utm_medium=event.utm_medium,
        utm_campaign=event.utm_campaign,
        referrer=event.referrer,
        user_agent=event.user_agent,
        device_type=event.device_type,
        ip_address=client_ip
    )

    db.add(analytics_event)
    db.commit()

    return {"success": True}


# ============================================================================
# ANALYTICS DASHBOARD ENDPOINTS
# ============================================================================

@router.get("/my/analytics", response_model=AnalyticsSummary)
async def get_my_analytics(
    days: int = 30,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_dep())
):
    """Get analytics for user's microsite"""
    microsite = db.query(MicrositePage).filter(
        MicrositePage.user_id == current_user.id
    ).first()

    if not microsite:
        raise HTTPException(status_code=404, detail="No microsite found")

    start_date = datetime.now(timezone.utc) - timedelta(days=days)

    # Get basic metrics
    total_views = db.execute(text("""
        SELECT COUNT(*) FROM microsite_analytics_events
        WHERE microsite_id = :microsite_id
        AND event_type = 'page_view'
        AND created_at >= :start_date
    """), {"microsite_id": microsite.id, "start_date": start_date}).scalar() or 0

    unique_visitors = db.execute(text("""
        SELECT COUNT(DISTINCT visitor_id) FROM microsite_analytics_events
        WHERE microsite_id = :microsite_id
        AND created_at >= :start_date
        AND visitor_id IS NOT NULL
    """), {"microsite_id": microsite.id, "start_date": start_date}).scalar() or 0

    total_leads = db.execute(text("""
        SELECT COUNT(*) FROM microsite_leads
        WHERE microsite_id = :microsite_id
        AND created_at >= :start_date
    """), {"microsite_id": microsite.id, "start_date": start_date}).scalar() or 0

    # Calculate conversion rate
    conversion_rate = (total_leads / unique_visitors * 100) if unique_visitors > 0 else 0

    # Get intent breakdown
    intent_data = db.execute(text("""
        SELECT intent_type, COUNT(*) as count FROM microsite_leads
        WHERE microsite_id = :microsite_id
        AND created_at >= :start_date
        AND intent_type IS NOT NULL
        GROUP BY intent_type
    """), {"microsite_id": microsite.id, "start_date": start_date}).fetchall()

    intent_breakdown = {row[0]: row[1] for row in intent_data}

    # Get device breakdown
    device_data = db.execute(text("""
        SELECT device_type, COUNT(*) as count FROM microsite_analytics_events
        WHERE microsite_id = :microsite_id
        AND event_type = 'page_view'
        AND created_at >= :start_date
        AND device_type IS NOT NULL
        GROUP BY device_type
    """), {"microsite_id": microsite.id, "start_date": start_date}).fetchall()

    device_breakdown = {row[0]: row[1] for row in device_data}

    # Get top referrers
    referrer_data = db.execute(text("""
        SELECT referrer, COUNT(*) as count FROM microsite_analytics_events
        WHERE microsite_id = :microsite_id
        AND event_type = 'page_view'
        AND created_at >= :start_date
        AND referrer IS NOT NULL
        GROUP BY referrer
        ORDER BY count DESC
        LIMIT 10
    """), {"microsite_id": microsite.id, "start_date": start_date}).fetchall()

    top_referrers = [{"referrer": row[0], "count": row[1]} for row in referrer_data]

    # Get daily views
    daily_data = db.execute(text("""
        SELECT DATE(created_at) as date, COUNT(*) as count
        FROM microsite_analytics_events
        WHERE microsite_id = :microsite_id
        AND event_type = 'page_view'
        AND created_at >= :start_date
        GROUP BY DATE(created_at)
        ORDER BY date
    """), {"microsite_id": microsite.id, "start_date": start_date}).fetchall()

    daily_views = [{"date": str(row[0]), "count": row[1]} for row in daily_data]

    return AnalyticsSummary(
        period_days=days,
        total_views=total_views,
        unique_visitors=unique_visitors,
        total_leads=total_leads,
        conversion_rate=round(conversion_rate, 2),
        intent_breakdown=intent_breakdown,
        top_referrers=top_referrers,
        device_breakdown=device_breakdown,
        daily_views=daily_views
    )


@router.get("/my/leads", response_model=List[LeadResponse])
async def get_my_leads(
    status: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_dep())
):
    """Get leads captured from user's microsite"""
    microsite = db.query(MicrositePage).filter(
        MicrositePage.user_id == current_user.id
    ).first()

    if not microsite:
        raise HTTPException(status_code=404, detail="No microsite found")

    query = db.query(MicrositeLead).filter(
        MicrositeLead.microsite_id == microsite.id
    )

    if status:
        query = query.filter(MicrositeLead.status == status)

    leads = query.order_by(MicrositeLead.created_at.desc()).offset(offset).limit(limit).all()

    return leads


# ============================================================================
# ORGANIZATION SETTINGS ENDPOINTS
# ============================================================================

@router.get("/settings/org", response_model=OrgMicrositeSettingsResponse)
async def get_org_microsite_settings(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_dep())
):
    """Get organization microsite settings (admin only)"""
    if current_user.role not in ['admin', 'super_admin', 'owner']:
        raise HTTPException(status_code=403, detail="Insufficient permissions")

    settings = db.query(OrganizationMicrositeSettings).filter(
        OrganizationMicrositeSettings.organization_id == current_user.organization_id
    ).first()

    if not settings:
        # Create default settings
        settings = OrganizationMicrositeSettings(
            organization_id=current_user.organization_id
        )
        db.add(settings)
        db.commit()
        db.refresh(settings)

    return settings


@router.put("/settings/org", response_model=OrgMicrositeSettingsResponse)
async def update_org_microsite_settings(
    update_data: OrgMicrositeSettingsUpdate,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_dep())
):
    """Update organization microsite settings (admin only)"""
    if current_user.role not in ['admin', 'super_admin', 'owner']:
        raise HTTPException(status_code=403, detail="Insufficient permissions")

    settings = db.query(OrganizationMicrositeSettings).filter(
        OrganizationMicrositeSettings.organization_id == current_user.organization_id
    ).first()

    if not settings:
        settings = OrganizationMicrositeSettings(
            organization_id=current_user.organization_id
        )
        db.add(settings)

    # Update fields
    update_dict = update_data.model_dump(exclude_unset=True)
    _protected = {'id', 'organization_id', 'created_at', 'updated_at', 'user_id'}
    for key, value in update_dict.items():
        if key not in _protected:
            setattr(settings, key, value)

    db.commit()
    db.refresh(settings)

    return settings


# ============================================================================
# CUSTOM PAGE ENDPOINTS
# ============================================================================

def generate_page_slug(title: str) -> str:
    """Generate URL-friendly slug from title"""
    import re
    slug = title.lower()
    slug = re.sub(r'[^a-z0-9]+', '-', slug)
    slug = slug.strip('-')
    return slug


@router.get("/my/pages", response_model=List[CustomPageResponse])
async def get_my_custom_pages(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_dep())
):
    """Get all custom pages for user's microsite"""
    microsite = db.query(MicrositePage).filter(
        MicrositePage.user_id == current_user.id
    ).first()

    if not microsite:
        return []

    pages = db.query(MicrositeCustomPage).filter(
        MicrositeCustomPage.microsite_id == microsite.id
    ).order_by(MicrositeCustomPage.sort_order).all()

    return pages


@router.post("/my/pages", response_model=CustomPageResponse, status_code=status.HTTP_201_CREATED)
async def create_custom_page(
    page_data: CustomPageCreate,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_dep())
):
    """Create a new custom page for user's microsite"""
    microsite = db.query(MicrositePage).filter(
        MicrositePage.user_id == current_user.id
    ).first()

    if not microsite:
        raise HTTPException(status_code=404, detail="No microsite found. Create a microsite first.")

    # Generate slug if not provided
    slug = page_data.slug if page_data.slug else generate_page_slug(page_data.title)

    # Check for duplicate slug
    existing = db.query(MicrositeCustomPage).filter(
        MicrositeCustomPage.microsite_id == microsite.id,
        MicrositeCustomPage.slug == slug
    ).first()

    if existing:
        raise HTTPException(status_code=400, detail="A page with this URL already exists")

    # Get next sort order
    max_order = db.query(MicrositeCustomPage).filter(
        MicrositeCustomPage.microsite_id == microsite.id
    ).count()

    page = MicrositeCustomPage(
        microsite_id=microsite.id,
        title=page_data.title,
        slug=slug,
        content=page_data.content,
        is_published=page_data.is_published,
        sort_order=page_data.sort_order if page_data.sort_order else max_order
    )

    db.add(page)
    db.commit()
    db.refresh(page)

    return page


@router.get("/my/pages/{page_id}", response_model=CustomPageResponse)
async def get_custom_page(
    page_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_dep())
):
    """Get a specific custom page"""
    microsite = db.query(MicrositePage).filter(
        MicrositePage.user_id == current_user.id
    ).first()

    if not microsite:
        raise HTTPException(status_code=404, detail="No microsite found")

    page = db.query(MicrositeCustomPage).filter(
        MicrositeCustomPage.id == page_id,
        MicrositeCustomPage.microsite_id == microsite.id
    ).first()

    if not page:
        raise HTTPException(status_code=404, detail="Page not found")

    return page


@router.put("/my/pages/{page_id}", response_model=CustomPageResponse)
async def update_custom_page(
    page_id: int,
    page_data: CustomPageUpdate,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_dep())
):
    """Update a custom page"""
    microsite = db.query(MicrositePage).filter(
        MicrositePage.user_id == current_user.id
    ).first()

    if not microsite:
        raise HTTPException(status_code=404, detail="No microsite found")

    page = db.query(MicrositeCustomPage).filter(
        MicrositeCustomPage.id == page_id,
        MicrositeCustomPage.microsite_id == microsite.id
    ).first()

    if not page:
        raise HTTPException(status_code=404, detail="Page not found")

    # Update fields if provided
    if page_data.title is not None:
        page.title = page_data.title
    if page_data.slug is not None:
        # Check for duplicate slug
        existing = db.query(MicrositeCustomPage).filter(
            MicrositeCustomPage.microsite_id == microsite.id,
            MicrositeCustomPage.slug == page_data.slug,
            MicrositeCustomPage.id != page_id
        ).first()
        if existing:
            raise HTTPException(status_code=400, detail="A page with this URL already exists")
        page.slug = page_data.slug
    if page_data.content is not None:
        page.content = page_data.content
    if page_data.is_published is not None:
        page.is_published = page_data.is_published
    if page_data.sort_order is not None:
        page.sort_order = page_data.sort_order

    db.commit()
    db.refresh(page)

    return page


@router.delete("/my/pages/{page_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_custom_page(
    page_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_dep())
):
    """Delete a custom page"""
    microsite = db.query(MicrositePage).filter(
        MicrositePage.user_id == current_user.id
    ).first()

    if not microsite:
        raise HTTPException(status_code=404, detail="No microsite found")

    page = db.query(MicrositeCustomPage).filter(
        MicrositeCustomPage.id == page_id,
        MicrositeCustomPage.microsite_id == microsite.id
    ).first()

    if not page:
        raise HTTPException(status_code=404, detail="Page not found")

    db.delete(page)
    db.commit()

    return None


# ============================================================================
# ADMIN ENDPOINTS
# ============================================================================

@router.get("/admin/all", response_model=List[MicrositeResponse])
async def list_all_microsites(
    status: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_dep())
):
    """List all microsites in organization (admin only)"""
    if current_user.role not in ['admin', 'super_admin', 'owner']:
        raise HTTPException(status_code=403, detail="Insufficient permissions")

    query = db.query(MicrositePage).filter(
        MicrositePage.organization_id == current_user.organization_id
    )

    if status:
        query = query.filter(MicrositePage.status == status)

    microsites = query.order_by(MicrositePage.created_at.desc()).offset(offset).limit(limit).all()

    results = []
    for m in microsites:
        response = MicrositeResponse.model_validate(m)
        response.public_url = f"https://{m.slug}.{MICROSITE_DOMAIN}"
        results.append(response)

    return results
