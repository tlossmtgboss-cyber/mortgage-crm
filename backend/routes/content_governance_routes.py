"""
Marketing Content Governance API Routes

Enterprise compliance review workflow for all marketing materials.
Enterprise lenders require that every email, SMS, social, and print asset
passes a compliance review before it can be distributed to borrowers or
prospects.

Workflow summary:
    1. Creator POSTs a draft template (status = draft)
    2. Creator submits for review (status -> pending_review)
    3. Compliance reviewer approves / rejects / requests revision
       - approve        -> status = approved
       - reject         -> status = rejected
       - request-revision -> status = draft  (so creator can edit and re-submit)
    4. Only approved templates may be used for distribution
    5. Every distribution event is logged (ContentUsageLog) for auditing

Permission model:
    - Any authenticated user may create, update (while draft/revision_requested),
      and submit their own templates.
    - Only users with permission_role in {"compliance", "admin", "site_admin"}
      may approve, reject, or request-revision.
    - All status transitions are recorded in ContentApproval for audit trail.

Endpoints:
    POST   /api/v1/marketing/governance/templates
    GET    /api/v1/marketing/governance/templates
    GET    /api/v1/marketing/governance/templates/{template_id}
    PUT    /api/v1/marketing/governance/templates/{template_id}
    POST   /api/v1/marketing/governance/templates/{template_id}/submit-for-review
    POST   /api/v1/marketing/governance/templates/{template_id}/approve
    POST   /api/v1/marketing/governance/templates/{template_id}/reject
    POST   /api/v1/marketing/governance/templates/{template_id}/request-revision
    GET    /api/v1/marketing/governance/templates/{template_id}/audit
    GET    /api/v1/marketing/governance/pending-reviews
    POST   /api/v1/marketing/governance/templates/{template_id}/use
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from auth.dependencies import get_current_user
from db import get_db, get_async_db
from database.models.content_governance import (
    ApprovalDecision,
    ContentApproval,
    ContentStatus,
    ContentTemplate,
    ContentType,
    ContentUsageLog,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------

router = APIRouter(
    prefix="/api/v1/marketing/governance",
    tags=["marketing-content-governance"],
)

# ---------------------------------------------------------------------------
# COMPLIANCE ROLES — users that may approve / reject content
# ---------------------------------------------------------------------------

_COMPLIANCE_ROLES = {"compliance", "admin", "site_admin"}

# ---------------------------------------------------------------------------
# PYDANTIC SCHEMAS — Request Models
# ---------------------------------------------------------------------------


class ContentTemplateCreate(BaseModel):
    """Payload for creating a new content template (starts as draft)."""

    title: str = Field(..., min_length=1, max_length=500, description="Human-readable name for the template")
    content_type: ContentType = Field(..., description="Channel: email | sms | social | print")
    subject_line: Optional[str] = Field(
        None,
        max_length=998,
        description="Email subject line (required for email; omit for sms/print/social)",
    )
    body_html: Optional[str] = Field(None, description="HTML body (email / print)")
    body_text: Optional[str] = Field(None, description="Plain-text body or SMS message body")
    category: Optional[str] = Field(None, max_length=200, description="E.g. 'rate_promo', 'post_close'")
    tags: Optional[List[str]] = Field(None, description="Searchable labels, e.g. ['fair_housing', 'q1_2026']")


class ContentTemplateUpdate(BaseModel):
    """Payload for editing a template that is in draft or revision_requested status."""

    title: Optional[str] = Field(None, min_length=1, max_length=500)
    content_type: Optional[ContentType] = None
    subject_line: Optional[str] = Field(None, max_length=998)
    body_html: Optional[str] = None
    body_text: Optional[str] = None
    category: Optional[str] = Field(None, max_length=200)
    tags: Optional[List[str]] = None


class ReviewDecisionRequest(BaseModel):
    """Payload for approve / reject / request-revision actions."""

    review_notes: Optional[str] = Field(
        None,
        description="Rationale, change requests, or approval confirmation notes",
    )


class UseTemplateRequest(BaseModel):
    """Payload for logging a distribution event against an approved template."""

    channel: Optional[str] = Field(
        None,
        max_length=50,
        description="Actual dispatch channel used (e.g. 'email', 'sms'). Defaults to template content_type.",
    )
    recipient_count: int = Field(..., ge=0, description="Number of recipients in this send")
    campaign_id: Optional[int] = Field(None, description="campaign_definitions.id if sent via a campaign")
    reference_id: Optional[str] = Field(
        None,
        description="External reference (email send job ID, campaign execution ID, etc.)",
    )


# ---------------------------------------------------------------------------
# PYDANTIC SCHEMAS — Response Models
# ---------------------------------------------------------------------------


class ContentApprovalResponse(BaseModel):
    """Single approval event in the audit trail."""

    id: str
    reviewer_id: int
    reviewer_name: Optional[str]
    status: ApprovalDecision
    review_notes: Optional[str]
    reviewed_at: datetime
    created_at: datetime

    class Config:
        from_attributes = True


class ContentTemplateResponse(BaseModel):
    """Full template detail, including latest approval summary."""

    id: str
    organization_id: int
    title: str
    content_type: ContentType
    subject_line: Optional[str]
    body_html: Optional[str]
    body_text: Optional[str]
    category: Optional[str]
    tags: Optional[List[str]]
    status: ContentStatus
    created_by: int
    creator_name: Optional[str]
    created_at: datetime
    updated_at: datetime

    # Convenience: last approval decision details (if any)
    last_review_status: Optional[ApprovalDecision] = None
    last_review_notes: Optional[str] = None
    last_reviewed_at: Optional[datetime] = None
    last_reviewed_by_name: Optional[str] = None

    class Config:
        from_attributes = True


class ContentTemplateSummary(BaseModel):
    """Lightweight list item — no body content."""

    id: str
    organization_id: int
    title: str
    content_type: ContentType
    category: Optional[str]
    tags: Optional[List[str]]
    status: ContentStatus
    created_by: int
    creator_name: Optional[str]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ContentUsageLogResponse(BaseModel):
    """Single usage log entry."""

    id: str
    template_id: str
    used_by: int
    user_name: Optional[str]
    used_at: datetime
    channel: Optional[str]
    recipient_count: int
    campaign_id: Optional[int]
    reference_id: Optional[str]

    class Config:
        from_attributes = True


class AuditTrailResponse(BaseModel):
    """Full audit trail for a template: approvals + usage."""

    template_id: str
    title: str
    status: ContentStatus
    approvals: List[ContentApprovalResponse]
    usage_logs: List[ContentUsageLogResponse]
    total_uses: int
    total_recipients: int


# ---------------------------------------------------------------------------
# HELPERS
# ---------------------------------------------------------------------------


def _require_compliance_role(user: Any) -> None:
    """Raise 403 if the user is not in a compliance-capable role."""
    role = getattr(user, "permission_role", "") or ""
    if role not in _COMPLIANCE_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Compliance reviewer role required (compliance, admin, or site_admin)",
        )


def _get_template_or_404(db: Session, template_id: str, organization_id: int) -> ContentTemplate:
    """Fetch a template by ID within the caller's organization, or raise 404."""
    tmpl = (
        db.query(ContentTemplate)
        .filter(
            ContentTemplate.id == template_id,
            ContentTemplate.organization_id == organization_id,
        )
        .first()
    )
    if not tmpl:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Template '{template_id}' not found",
        )
    return tmpl


def _user_display_name(user: Any) -> str:
    """Return a readable name from a User ORM object."""
    if hasattr(user, "first_name") and hasattr(user, "last_name"):
        parts = [user.first_name or "", user.last_name or ""]
        name = " ".join(p for p in parts if p).strip()
        return name or getattr(user, "email", "Unknown")
    return getattr(user, "email", "Unknown")


def _build_template_response(tmpl: ContentTemplate, db: Session) -> ContentTemplateResponse:
    """Build ContentTemplateResponse, resolving creator name and last review."""
    from database.models.core import User

    creator_name: Optional[str] = None
    if tmpl.created_by:
        creator = db.query(User).filter(User.id == tmpl.created_by).first()
        if creator:
            creator_name = _user_display_name(creator)

    # Last approval in chronological order
    last_review_status = None
    last_review_notes = None
    last_reviewed_at = None
    last_reviewed_by_name = None

    if tmpl.approvals:
        last_approval = tmpl.approvals[-1]  # ordered ASC by created_at via relationship
        last_review_status = last_approval.status
        last_review_notes = last_approval.review_notes
        last_reviewed_at = last_approval.reviewed_at
        reviewer = db.query(User).filter(User.id == last_approval.reviewer_id).first()
        if reviewer:
            last_reviewed_by_name = _user_display_name(reviewer)

    return ContentTemplateResponse(
        id=tmpl.id,
        organization_id=tmpl.organization_id,
        title=tmpl.title,
        content_type=tmpl.content_type,
        subject_line=tmpl.subject_line,
        body_html=tmpl.body_html,
        body_text=tmpl.body_text,
        category=tmpl.category,
        tags=tmpl.tags,
        status=tmpl.status,
        created_by=tmpl.created_by,
        creator_name=creator_name,
        created_at=tmpl.created_at,
        updated_at=tmpl.updated_at,
        last_review_status=last_review_status,
        last_review_notes=last_review_notes,
        last_reviewed_at=last_reviewed_at,
        last_reviewed_by_name=last_reviewed_by_name,
    )


def _append_approval(
    db: Session,
    template_id: str,
    reviewer_id: int,
    decision: ApprovalDecision,
    notes: Optional[str],
) -> ContentApproval:
    """Write a new ContentApproval row and return it."""
    now = datetime.now(timezone.utc)
    approval = ContentApproval(
        id=str(uuid.uuid4()),
        template_id=template_id,
        reviewer_id=reviewer_id,
        status=decision,
        review_notes=notes,
        reviewed_at=now,
        created_at=now,
    )
    db.add(approval)
    return approval


# ---------------------------------------------------------------------------
# ENDPOINTS
# ---------------------------------------------------------------------------


@router.post(
    "/templates",
    response_model=ContentTemplateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new content template (status=draft)",
)
async def create_template(
    payload: ContentTemplateCreate,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    current_user=Depends(get_current_user),
) -> ContentTemplateResponse:
    """Create a new marketing content template.

    The template is created with ``status=draft``. It must be explicitly
    submitted for review before a compliance reviewer can approve it.
    """
    org_id: int = getattr(request.state, "organization_id", None) or getattr(current_user, "organization_id", None)
    if not org_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Organization context required")

    now = datetime.now(timezone.utc)
    tmpl = ContentTemplate(
        id=str(uuid.uuid4()),
        organization_id=org_id,
        title=payload.title,
        content_type=payload.content_type,
        subject_line=payload.subject_line,
        body_html=payload.body_html,
        body_text=payload.body_text,
        category=payload.category,
        tags=payload.tags,
        status=ContentStatus.DRAFT,
        created_by=current_user.id,
        created_at=now,
        updated_at=now,
    )
    db.add(tmpl)
    await db.commit()
    await db.refresh(tmpl)

    logger.info(
        "content_template.created template_id=%s org_id=%s user_id=%s",
        tmpl.id,
        org_id,
        current_user.id,
    )
    return _build_template_response(tmpl, db)


@router.get(
    "/templates",
    response_model=List[ContentTemplateSummary],
    summary="List content templates with optional status filter",
)
async def list_templates(
    request: Request,
    template_status: Optional[ContentStatus] = Query(None, alias="status", description="Filter by lifecycle status"),
    content_type: Optional[ContentType] = Query(None, description="Filter by content type"),
    category: Optional[str] = Query(None, description="Filter by category"),
    limit: int = Query(100, ge=1, le=500, description="Maximum rows to return"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
) -> List[ContentTemplateSummary]:
    """List templates visible to the caller's organization.

    Supports filtering by status, content_type, and category. Results are
    ordered newest-first by ``updated_at``.
    """
    from database.models.core import User

    org_id: int = getattr(request.state, "organization_id", None) or getattr(current_user, "organization_id", None)
    if not org_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Organization context required")

    query = db.query(ContentTemplate).filter(ContentTemplate.organization_id == org_id)

    if template_status is not None:
        query = query.filter(ContentTemplate.status == template_status)
    if content_type is not None:
        query = query.filter(ContentTemplate.content_type == content_type)
    if category is not None:
        query = query.filter(ContentTemplate.category == category)

    templates = (
        query.order_by(ContentTemplate.updated_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    results = []
    for tmpl in templates:
        creator_name: Optional[str] = None
        if tmpl.created_by:
            creator = db.query(User).filter(User.id == tmpl.created_by).first()
            if creator:
                creator_name = _user_display_name(creator)
        results.append(
            ContentTemplateSummary(
                id=tmpl.id,
                organization_id=tmpl.organization_id,
                title=tmpl.title,
                content_type=tmpl.content_type,
                category=tmpl.category,
                tags=tmpl.tags,
                status=tmpl.status,
                created_by=tmpl.created_by,
                creator_name=creator_name,
                created_at=tmpl.created_at,
                updated_at=tmpl.updated_at,
            )
        )
    return results


@router.get(
    "/templates/{template_id}",
    response_model=ContentTemplateResponse,
    summary="Get full template detail",
)
async def get_template(
    template_id: str,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    current_user=Depends(get_current_user),
) -> ContentTemplateResponse:
    """Fetch a single template by ID, including last review decision."""
    org_id: int = getattr(request.state, "organization_id", None) or getattr(current_user, "organization_id", None)
    if not org_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Organization context required")

    tmpl = _get_template_or_404(db, template_id, org_id)
    return _build_template_response(tmpl, db)


@router.put(
    "/templates/{template_id}",
    response_model=ContentTemplateResponse,
    summary="Update a template (only allowed when draft or revision_requested)",
)
async def update_template(
    template_id: str,
    payload: ContentTemplateUpdate,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    current_user=Depends(get_current_user),
) -> ContentTemplateResponse:
    """Edit a template's content or metadata.

    Only permitted when the template is in ``draft`` or ``revision_requested``
    status. Attempting to edit a ``pending_review``, ``approved``, ``rejected``,
    or ``archived`` template returns HTTP 409 Conflict.
    """
    org_id: int = getattr(request.state, "organization_id", None) or getattr(current_user, "organization_id", None)
    if not org_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Organization context required")

    tmpl = _get_template_or_404(db, template_id, org_id)

    _EDITABLE_STATUSES = {ContentStatus.DRAFT, ContentStatus.REVISION_REQUESTED}
    if tmpl.status not in _EDITABLE_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Template cannot be edited in '{tmpl.status.value}' status. "
                "Only draft or revision_requested templates are editable."
            ),
        )

    # Apply non-None fields from payload
    update_data = payload.model_dump(exclude_none=True)
    if not update_data:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No fields provided for update",
        )
    for field, value in update_data.items():
        setattr(tmpl, field, value)

    tmpl.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(tmpl)

    logger.info(
        "content_template.updated template_id=%s user_id=%s fields=%s",
        template_id,
        current_user.id,
        list(update_data.keys()),
    )
    return _build_template_response(tmpl, db)


@router.post(
    "/templates/{template_id}/submit-for-review",
    response_model=ContentTemplateResponse,
    summary="Submit a draft template to compliance for review",
)
async def submit_for_review(
    template_id: str,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    current_user=Depends(get_current_user),
) -> ContentTemplateResponse:
    """Move a template from ``draft`` (or ``revision_requested``) to ``pending_review``.

    This notifies the compliance queue that the template is ready for review.
    Only the template creator or an admin may submit.
    """
    org_id: int = getattr(request.state, "organization_id", None) or getattr(current_user, "organization_id", None)
    if not org_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Organization context required")

    tmpl = _get_template_or_404(db, template_id, org_id)

    _SUBMITTABLE_STATUSES = {ContentStatus.DRAFT, ContentStatus.REVISION_REQUESTED}
    if tmpl.status not in _SUBMITTABLE_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Template is already in '{tmpl.status.value}' status and cannot be re-submitted. "
                "Only draft or revision_requested templates may be submitted for review."
            ),
        )

    # Require at least some content before submission
    if not tmpl.body_html and not tmpl.body_text:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Template must have body content (body_html or body_text) before submission",
        )

    tmpl.status = ContentStatus.PENDING_REVIEW
    tmpl.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(tmpl)

    logger.info(
        "content_template.submitted_for_review template_id=%s user_id=%s",
        template_id,
        current_user.id,
    )
    return _build_template_response(tmpl, db)


@router.post(
    "/templates/{template_id}/approve",
    response_model=ContentTemplateResponse,
    summary="Approve a pending template (compliance role required)",
)
async def approve_template(
    template_id: str,
    payload: ReviewDecisionRequest,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    current_user=Depends(get_current_user),
) -> ContentTemplateResponse:
    """Approve a template that is in ``pending_review``.

    Requires ``permission_role`` of compliance, admin, or site_admin.
    A ContentApproval row with ``status=approved`` is appended for the
    audit trail; the template status transitions to ``approved``.
    """
    _require_compliance_role(current_user)

    org_id: int = getattr(request.state, "organization_id", None) or getattr(current_user, "organization_id", None)
    if not org_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Organization context required")

    tmpl = _get_template_or_404(db, template_id, org_id)

    if tmpl.status != ContentStatus.PENDING_REVIEW:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Template is in '{tmpl.status.value}' status. "
                "Only pending_review templates can be approved."
            ),
        )

    _append_approval(db, template_id, current_user.id, ApprovalDecision.APPROVED, payload.review_notes)
    tmpl.status = ContentStatus.APPROVED
    tmpl.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(tmpl)

    logger.info(
        "content_template.approved template_id=%s reviewer_id=%s",
        template_id,
        current_user.id,
    )
    return _build_template_response(tmpl, db)


@router.post(
    "/templates/{template_id}/reject",
    response_model=ContentTemplateResponse,
    summary="Reject a pending template (compliance role required)",
)
async def reject_template(
    template_id: str,
    payload: ReviewDecisionRequest,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    current_user=Depends(get_current_user),
) -> ContentTemplateResponse:
    """Reject a template that is in ``pending_review``.

    Requires ``permission_role`` of compliance, admin, or site_admin.
    ``review_notes`` should explain the reason for rejection so the creator
    knows what needs to be fixed before re-submitting.

    A ContentApproval row with ``status=rejected`` is appended.
    """
    _require_compliance_role(current_user)

    org_id: int = getattr(request.state, "organization_id", None) or getattr(current_user, "organization_id", None)
    if not org_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Organization context required")

    tmpl = _get_template_or_404(db, template_id, org_id)

    if tmpl.status != ContentStatus.PENDING_REVIEW:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Template is in '{tmpl.status.value}' status. "
                "Only pending_review templates can be rejected."
            ),
        )

    _append_approval(db, template_id, current_user.id, ApprovalDecision.REJECTED, payload.review_notes)
    tmpl.status = ContentStatus.REJECTED
    tmpl.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(tmpl)

    logger.info(
        "content_template.rejected template_id=%s reviewer_id=%s",
        template_id,
        current_user.id,
    )
    return _build_template_response(tmpl, db)


@router.post(
    "/templates/{template_id}/request-revision",
    response_model=ContentTemplateResponse,
    summary="Request changes to a pending template (compliance role required)",
)
async def request_revision(
    template_id: str,
    payload: ReviewDecisionRequest,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    current_user=Depends(get_current_user),
) -> ContentTemplateResponse:
    """Request revisions to a ``pending_review`` template.

    Requires ``permission_role`` of compliance, admin, or site_admin.
    ``review_notes`` is strongly recommended — it tells the creator exactly
    what changes to make.

    The template is moved back to ``draft`` (technically ``revision_requested``
    in the status column to distinguish it from a brand-new draft) so the
    creator can edit and re-submit. A ContentApproval row with
    ``status=revision_requested`` is appended for the audit trail.
    """
    _require_compliance_role(current_user)

    org_id: int = getattr(request.state, "organization_id", None) or getattr(current_user, "organization_id", None)
    if not org_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Organization context required")

    tmpl = _get_template_or_404(db, template_id, org_id)

    if tmpl.status != ContentStatus.PENDING_REVIEW:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Template is in '{tmpl.status.value}' status. "
                "Only pending_review templates can have revisions requested."
            ),
        )

    _append_approval(db, template_id, current_user.id, ApprovalDecision.REVISION_REQUESTED, payload.review_notes)
    tmpl.status = ContentStatus.REVISION_REQUESTED
    tmpl.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(tmpl)

    logger.info(
        "content_template.revision_requested template_id=%s reviewer_id=%s",
        template_id,
        current_user.id,
    )
    return _build_template_response(tmpl, db)


@router.get(
    "/templates/{template_id}/audit",
    response_model=AuditTrailResponse,
    summary="Full approval history and usage log for a template",
)
async def get_audit_trail(
    template_id: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
) -> AuditTrailResponse:
    """Return the complete audit trail for a template.

    Includes every ContentApproval decision (who reviewed, what decision,
    when, and any notes) and every ContentUsageLog entry (who used it, on
    what channel, to how many recipients).
    """
    from database.models.core import User

    org_id: int = getattr(request.state, "organization_id", None) or getattr(current_user, "organization_id", None)
    if not org_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Organization context required")

    tmpl = _get_template_or_404(db, template_id, org_id)

    # Build approval history
    approval_responses: List[ContentApprovalResponse] = []
    for appr in tmpl.approvals:
        reviewer = db.query(User).filter(User.id == appr.reviewer_id).first()
        reviewer_name = _user_display_name(reviewer) if reviewer else None
        approval_responses.append(
            ContentApprovalResponse(
                id=appr.id,
                reviewer_id=appr.reviewer_id,
                reviewer_name=reviewer_name,
                status=appr.status,
                review_notes=appr.review_notes,
                reviewed_at=appr.reviewed_at,
                created_at=appr.created_at,
            )
        )

    # Build usage log
    usage_responses: List[ContentUsageLogResponse] = []
    total_recipients = 0
    for log in tmpl.usage_logs:
        user = db.query(User).filter(User.id == log.used_by).first()
        user_name = _user_display_name(user) if user else None
        usage_responses.append(
            ContentUsageLogResponse(
                id=log.id,
                template_id=log.template_id,
                used_by=log.used_by,
                user_name=user_name,
                used_at=log.used_at,
                channel=log.channel,
                recipient_count=log.recipient_count,
                campaign_id=log.campaign_id,
                reference_id=log.reference_id,
            )
        )
        total_recipients += log.recipient_count

    return AuditTrailResponse(
        template_id=tmpl.id,
        title=tmpl.title,
        status=tmpl.status,
        approvals=approval_responses,
        usage_logs=usage_responses,
        total_uses=len(usage_responses),
        total_recipients=total_recipients,
    )


@router.get(
    "/pending-reviews",
    response_model=List[ContentTemplateSummary],
    summary="All templates pending compliance review (compliance dashboard)",
)
async def list_pending_reviews(
    request: Request,
    content_type: Optional[ContentType] = Query(None, description="Filter by content type"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
) -> List[ContentTemplateSummary]:
    """Return all templates in ``pending_review`` status for the caller's org.

    Intended for the compliance dashboard. Does NOT restrict to
    compliance-only roles — visibility of the queue is open to all
    authenticated users so LOs can also monitor the queue for their own
    submissions.

    Results are ordered oldest-first (``created_at ASC``) so reviewers
    process them in FIFO order.
    """
    from database.models.core import User

    org_id: int = getattr(request.state, "organization_id", None) or getattr(current_user, "organization_id", None)
    if not org_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Organization context required")

    query = db.query(ContentTemplate).filter(
        ContentTemplate.organization_id == org_id,
        ContentTemplate.status == ContentStatus.PENDING_REVIEW,
    )

    if content_type is not None:
        query = query.filter(ContentTemplate.content_type == content_type)

    templates = (
        query.order_by(ContentTemplate.created_at.asc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    results = []
    for tmpl in templates:
        creator_name: Optional[str] = None
        if tmpl.created_by:
            creator = db.query(User).filter(User.id == tmpl.created_by).first()
            if creator:
                creator_name = _user_display_name(creator)
        results.append(
            ContentTemplateSummary(
                id=tmpl.id,
                organization_id=tmpl.organization_id,
                title=tmpl.title,
                content_type=tmpl.content_type,
                category=tmpl.category,
                tags=tmpl.tags,
                status=tmpl.status,
                created_by=tmpl.created_by,
                creator_name=creator_name,
                created_at=tmpl.created_at,
                updated_at=tmpl.updated_at,
            )
        )
    return results


@router.post(
    "/templates/{template_id}/use",
    response_model=ContentUsageLogResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Log a distribution event for an approved template",
)
async def use_template(
    template_id: str,
    payload: UseTemplateRequest,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    current_user=Depends(get_current_user),
) -> ContentUsageLogResponse:
    """Record that an approved template has been used for a distribution event.

    Enforces that only ``approved`` templates may be used. Attempting to use
    a draft, pending, rejected, or archived template returns HTTP 409 Conflict.

    One usage log entry is written per call. If a single campaign sends
    to multiple batches, call this endpoint once per batch, or once overall
    with the total ``recipient_count``.
    """
    org_id: int = getattr(request.state, "organization_id", None) or getattr(current_user, "organization_id", None)
    if not org_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Organization context required")

    tmpl = _get_template_or_404(db, template_id, org_id)

    if tmpl.status != ContentStatus.APPROVED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Template is in '{tmpl.status.value}' status. "
                "Only approved templates may be used for distribution."
            ),
        )

    channel = payload.channel or tmpl.content_type.value
    now = datetime.now(timezone.utc)

    log = ContentUsageLog(
        id=str(uuid.uuid4()),
        template_id=template_id,
        used_by=current_user.id,
        used_at=now,
        channel=channel,
        recipient_count=payload.recipient_count,
        campaign_id=payload.campaign_id,
        reference_id=payload.reference_id,
    )
    db.add(log)
    await db.commit()
    await db.refresh(log)

    user_name = _user_display_name(current_user)

    logger.info(
        "content_template.used template_id=%s user_id=%s channel=%s recipients=%d",
        template_id,
        current_user.id,
        channel,
        payload.recipient_count,
    )

    return ContentUsageLogResponse(
        id=log.id,
        template_id=log.template_id,
        used_by=log.used_by,
        user_name=user_name,
        used_at=log.used_at,
        channel=log.channel,
        recipient_count=log.recipient_count,
        campaign_id=log.campaign_id,
        reference_id=log.reference_id,
    )
