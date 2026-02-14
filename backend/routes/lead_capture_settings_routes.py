"""
Lead Capture Settings Routes
Comprehensive error handling pattern for lead capture configuration
"""

import re
import logging
from typing import Optional, List
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, validator
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from db import get_db as _db_dep

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/lead-capture-settings", tags=["Lead Capture Settings"])

# =============================================================================
# Dependency Injection Setup
# =============================================================================

_User = None
_get_current_user = None
_get_db = None

def set_dependencies(user_model, current_user_func, db_func):
    """Set dependencies for the routes"""
    global _User, _get_current_user, _get_db
    _User = user_model
    _get_current_user = current_user_func
    _get_db = db_func

def get_current_user():
    if _get_current_user is None:
        raise HTTPException(status_code=500, detail="Dependencies not configured")
    return Depends(_get_current_user)


async def _resolve_current_user(request: Request, db: Session = Depends(_db_dep)):
    """Proper FastAPI dependency that resolves to the actual user object."""
    if _get_current_user is None:
        raise HTTPException(status_code=500, detail="Dependencies not configured")
    auth = request.headers.get("Authorization", "")
    token = auth[7:] if auth.startswith("Bearer ") else ""
    return await _get_current_user(token, request, db)


# =============================================================================
# Custom Exceptions
# =============================================================================

class ValidationException(HTTPException):
    def __init__(self, field: str, message: str):
        super().__init__(
            status_code=422,
            detail={"type": "validation_error", "field": field, "message": message}
        )

class PermissionException(HTTPException):
    def __init__(self, message: str = "Permission denied"):
        super().__init__(
            status_code=403,
            detail={"type": "permission_error", "message": message}
        )


# =============================================================================
# Response Helpers
# =============================================================================

def success_response(data: dict, message: str = "Success"):
    """Standard success response format"""
    return {
        "success": True,
        "message": message,
        "data": data,
        "timestamp": datetime.utcnow().isoformat()
    }


# =============================================================================
# Pydantic Models with Validation
# =============================================================================

class LeadSource(BaseModel):
    """Configuration for a lead source"""
    id: str = Field(..., min_length=1, max_length=50)
    name: str = Field(..., min_length=1, max_length=100)
    category: str = Field(..., pattern="^(online|referral|marketing|direct|other)$")
    enabled: bool = True
    auto_assign: bool = False
    default_assignee_id: Optional[int] = None
    tracking_code: Optional[str] = None
    cost_per_lead: Optional[float] = Field(None, ge=0)

    @validator('id')
    def validate_id(cls, v):
        if not re.match(r'^[a-z0-9_-]+$', v):
            raise ValueError('ID must be lowercase letters, numbers, underscores, or hyphens')
        return v


class LeadStage(BaseModel):
    """Configuration for a lead stage"""
    id: str = Field(..., min_length=1, max_length=50)
    name: str = Field(..., min_length=1, max_length=100)
    order: int = Field(..., ge=0)
    color: str = Field("#3b82f6", pattern="^#[0-9a-fA-F]{6}$")
    is_active: bool = True
    is_converted: bool = False
    is_lost: bool = False
    sla_hours: Optional[int] = Field(None, ge=1, le=720)  # Max 30 days
    auto_actions: List[str] = []


class ScoringRule(BaseModel):
    """Lead scoring rule configuration"""
    id: str = Field(..., min_length=1, max_length=50)
    name: str = Field(..., min_length=1, max_length=100)
    field: str = Field(..., min_length=1, max_length=50)
    operator: str = Field(..., pattern="^(equals|contains|greater_than|less_than|exists|not_exists)$")
    value: Optional[str] = None
    points: int = Field(..., ge=-100, le=100)
    enabled: bool = True


class CaptureFormConfig(BaseModel):
    """Configuration for lead capture forms"""
    id: str = Field(..., min_length=1, max_length=50)
    name: str = Field(..., min_length=1, max_length=100)
    enabled: bool = True
    required_fields: List[str] = ["email"]
    optional_fields: List[str] = []
    default_source: Optional[str] = None
    redirect_url: Optional[str] = None
    confirmation_message: str = "Thank you for your submission!"
    notification_emails: List[str] = []

    @validator('required_fields')
    def validate_required_fields(cls, v):
        if not v:
            raise ValueError('At least one required field must be specified')
        valid_fields = ['email', 'phone', 'first_name', 'last_name', 'loan_amount',
                       'property_type', 'loan_purpose', 'credit_score_range']
        for field in v:
            if field not in valid_fields:
                raise ValueError(f'Invalid field: {field}')
        return v


class AssignmentSettings(BaseModel):
    """Lead assignment settings"""
    method: str = Field("round_robin", pattern="^(round_robin|weighted|geographic|manual)$")
    round_robin_users: List[int] = []
    weighted_assignments: List[dict] = []  # [{user_id, weight}]
    geographic_rules: List[dict] = []  # [{state, user_id}]
    fallback_user_id: Optional[int] = None
    respect_capacity: bool = True
    max_daily_leads: int = Field(50, ge=1, le=500)
    business_hours_only: bool = True


class DeduplicationSettings(BaseModel):
    """Lead deduplication settings"""
    enabled: bool = True
    match_fields: List[str] = ["email", "phone"]
    match_window_days: int = Field(30, ge=1, le=365)
    action_on_duplicate: str = Field("merge", pattern="^(merge|update|reject|create_task)$")
    notify_on_duplicate: bool = True


class LeadCaptureSettingsUpdate(BaseModel):
    """Complete lead capture settings update"""
    # Lead Sources
    lead_sources: List[LeadSource] = []

    # Lead Stages/Pipeline
    lead_stages: List[LeadStage] = []

    # Scoring
    scoring_enabled: bool = True
    scoring_rules: List[ScoringRule] = []
    hot_lead_threshold: int = Field(80, ge=0, le=100)
    warm_lead_threshold: int = Field(50, ge=0, le=100)

    # Capture Forms
    capture_forms: List[CaptureFormConfig] = []

    # Assignment
    assignment: AssignmentSettings = AssignmentSettings()

    # Deduplication
    deduplication: DeduplicationSettings = DeduplicationSettings()

    # Notifications
    notify_on_new_lead: bool = True
    notify_on_hot_lead: bool = True
    instant_notification_channels: List[str] = ["email"]  # email, sms, push

    # Follow-up
    auto_followup_enabled: bool = True
    initial_followup_minutes: int = Field(15, ge=1, le=1440)  # Max 24 hours
    followup_reminder_hours: int = Field(24, ge=1, le=168)  # Max 7 days

    @validator('warm_lead_threshold')
    def validate_thresholds(cls, v, values):
        if 'hot_lead_threshold' in values and v >= values['hot_lead_threshold']:
            raise ValueError('Warm lead threshold must be less than hot lead threshold')
        return v


# =============================================================================
# Default Configuration
# =============================================================================

DEFAULT_LEAD_SOURCES = [
    {"id": "website", "name": "Website", "category": "online", "enabled": True, "auto_assign": True},
    {"id": "zillow", "name": "Zillow", "category": "online", "enabled": True, "auto_assign": True},
    {"id": "realtor_com", "name": "Realtor.com", "category": "online", "enabled": True, "auto_assign": True},
    {"id": "referral_realtor", "name": "Realtor Referral", "category": "referral", "enabled": True, "auto_assign": False},
    {"id": "referral_past_client", "name": "Past Client Referral", "category": "referral", "enabled": True, "auto_assign": False},
    {"id": "referral_partner", "name": "Partner Referral", "category": "referral", "enabled": True, "auto_assign": False},
    {"id": "facebook_ads", "name": "Facebook Ads", "category": "marketing", "enabled": True, "auto_assign": True},
    {"id": "google_ads", "name": "Google Ads", "category": "marketing", "enabled": True, "auto_assign": True},
    {"id": "direct_mail", "name": "Direct Mail", "category": "marketing", "enabled": True, "auto_assign": True},
    {"id": "cold_call", "name": "Cold Call", "category": "direct", "enabled": True, "auto_assign": False},
    {"id": "walk_in", "name": "Walk-In", "category": "direct", "enabled": True, "auto_assign": False},
    {"id": "other", "name": "Other", "category": "other", "enabled": True, "auto_assign": False},
]

DEFAULT_LEAD_STAGES = [
    {"id": "new", "name": "New Lead", "order": 0, "color": "#3b82f6", "is_active": True, "sla_hours": 2},
    {"id": "contacted", "name": "Contacted", "order": 1, "color": "#8b5cf6", "is_active": True, "sla_hours": 24},
    {"id": "qualified", "name": "Qualified", "order": 2, "color": "#06b6d4", "is_active": True, "sla_hours": 48},
    {"id": "application", "name": "Application Started", "order": 3, "color": "#f59e0b", "is_active": True, "sla_hours": 72},
    {"id": "converted", "name": "Converted to Loan", "order": 4, "color": "#22c55e", "is_active": False, "is_converted": True},
    {"id": "lost", "name": "Lost/Dead", "order": 5, "color": "#ef4444", "is_active": False, "is_lost": True},
]

DEFAULT_SCORING_RULES = [
    {"id": "has_email", "name": "Has Email", "field": "email", "operator": "exists", "value": None, "points": 10, "enabled": True},
    {"id": "has_phone", "name": "Has Phone", "field": "phone", "operator": "exists", "value": None, "points": 15, "enabled": True},
    {"id": "high_loan_amount", "name": "Loan Amount > $500K", "field": "loan_amount", "operator": "greater_than", "value": "500000", "points": 20, "enabled": True},
    {"id": "purchase", "name": "Purchase Intent", "field": "loan_purpose", "operator": "equals", "value": "purchase", "points": 15, "enabled": True},
    {"id": "refinance", "name": "Refinance Intent", "field": "loan_purpose", "operator": "equals", "value": "refinance", "points": 10, "enabled": True},
    {"id": "good_credit", "name": "Good Credit (700+)", "field": "credit_score_range", "operator": "equals", "value": "700+", "points": 25, "enabled": True},
    {"id": "referral_source", "name": "Referral Source", "field": "source_category", "operator": "equals", "value": "referral", "points": 20, "enabled": True},
]

DEFAULT_CAPTURE_FORMS = [
    {
        "id": "website_main",
        "name": "Main Website Form",
        "enabled": True,
        "required_fields": ["email", "first_name", "last_name", "phone"],
        "optional_fields": ["loan_amount", "loan_purpose", "property_type"],
        "default_source": "website",
        "confirmation_message": "Thank you! A loan officer will contact you shortly."
    },
    {
        "id": "rate_quote",
        "name": "Rate Quote Form",
        "enabled": True,
        "required_fields": ["email", "phone", "loan_amount"],
        "optional_fields": ["credit_score_range", "property_type", "loan_purpose"],
        "default_source": "website",
        "confirmation_message": "Thank you! We'll send your personalized rate quote within minutes."
    },
]

DEFAULT_SETTINGS = {
    "lead_sources": DEFAULT_LEAD_SOURCES,
    "lead_stages": DEFAULT_LEAD_STAGES,
    "scoring_enabled": True,
    "scoring_rules": DEFAULT_SCORING_RULES,
    "hot_lead_threshold": 80,
    "warm_lead_threshold": 50,
    "capture_forms": DEFAULT_CAPTURE_FORMS,
    "assignment": {
        "method": "round_robin",
        "round_robin_users": [],
        "weighted_assignments": [],
        "geographic_rules": [],
        "fallback_user_id": None,
        "respect_capacity": True,
        "max_daily_leads": 50,
        "business_hours_only": True
    },
    "deduplication": {
        "enabled": True,
        "match_fields": ["email", "phone"],
        "match_window_days": 30,
        "action_on_duplicate": "merge",
        "notify_on_duplicate": True
    },
    "notify_on_new_lead": True,
    "notify_on_hot_lead": True,
    "instant_notification_channels": ["email"],
    "auto_followup_enabled": True,
    "initial_followup_minutes": 15,
    "followup_reminder_hours": 24
}


# =============================================================================
# API Endpoints
# =============================================================================

@router.get("")
async def get_lead_capture_settings(
    current_user = Depends(_resolve_current_user)
):
    """Get lead capture settings for the organization"""
    try:
        if current_user is None:
            raise PermissionException("Authentication required")

        # In production, load from database based on organization_id
        settings = DEFAULT_SETTINGS.copy()
        settings["last_updated"] = datetime.utcnow().isoformat()
        settings["updated_by"] = None

        return success_response(
            data=settings,
            message="Lead capture settings retrieved"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error fetching lead capture settings")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.put("")
async def update_lead_capture_settings(
    settings: LeadCaptureSettingsUpdate,
    current_user = Depends(_resolve_current_user)
):
    """Update lead capture settings"""
    try:
        if current_user is None:
            raise PermissionException("Authentication required")

        # Check admin permission
        if not getattr(current_user, 'is_admin', False) and not getattr(current_user, 'role', '') in ['admin', 'manager']:
            raise PermissionException("Admin access required to update lead capture settings")

        # Validate lead sources
        if len(settings.lead_sources) == 0:
            raise ValidationException("lead_sources", "At least one lead source must be configured")

        # Check for duplicate source IDs
        source_ids = [s.id for s in settings.lead_sources]
        if len(source_ids) != len(set(source_ids)):
            raise ValidationException("lead_sources", "Duplicate lead source IDs found")

        # Validate lead stages
        if len(settings.lead_stages) < 2:
            raise ValidationException("lead_stages", "At least two stages required (active and end state)")

        # Check for at least one converted and one lost stage
        has_converted = any(s.is_converted for s in settings.lead_stages)
        has_lost = any(s.is_lost for s in settings.lead_stages)
        if not has_converted:
            raise ValidationException("lead_stages", "At least one 'converted' stage is required")
        if not has_lost:
            raise ValidationException("lead_stages", "At least one 'lost' stage is required")

        # Check stage ordering
        stage_orders = [s.order for s in settings.lead_stages]
        if len(stage_orders) != len(set(stage_orders)):
            raise ValidationException("lead_stages", "Duplicate stage order values found")

        # Validate scoring rules
        if settings.scoring_enabled and len(settings.scoring_rules) == 0:
            raise ValidationException("scoring_rules", "At least one scoring rule required when scoring is enabled")

        # In production, save to database
        updated_settings = settings.dict()
        updated_settings["last_updated"] = datetime.utcnow().isoformat()
        updated_settings["updated_by"] = getattr(current_user, 'id', None)

        return success_response(
            data=updated_settings,
            message="Lead capture settings updated successfully"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error updating lead capture settings")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/lead-sources")
async def get_lead_source_options(
    current_user = Depends(_resolve_current_user)
):
    """Get available lead source categories and preset sources"""
    try:
        if current_user is None:
            raise PermissionException("Authentication required")

        categories = [
            {"id": "online", "name": "Online", "description": "Website, portals, and online sources"},
            {"id": "referral", "name": "Referral", "description": "Referrals from partners and clients"},
            {"id": "marketing", "name": "Marketing", "description": "Paid advertising and campaigns"},
            {"id": "direct", "name": "Direct", "description": "Direct contact and walk-ins"},
            {"id": "other", "name": "Other", "description": "Miscellaneous sources"},
        ]

        presets = DEFAULT_LEAD_SOURCES

        return success_response(
            data={
                "categories": categories,
                "presets": presets
            },
            message="Lead source options retrieved"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error fetching lead source options")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/scoring-fields")
async def get_scoring_field_options(
    current_user = Depends(_resolve_current_user)
):
    """Get available fields for scoring rules"""
    try:
        if current_user is None:
            raise PermissionException("Authentication required")

        fields = [
            {"id": "email", "name": "Email", "type": "string", "operators": ["exists", "not_exists", "contains"]},
            {"id": "phone", "name": "Phone", "type": "string", "operators": ["exists", "not_exists"]},
            {"id": "first_name", "name": "First Name", "type": "string", "operators": ["exists", "not_exists"]},
            {"id": "last_name", "name": "Last Name", "type": "string", "operators": ["exists", "not_exists"]},
            {"id": "loan_amount", "name": "Loan Amount", "type": "number", "operators": ["greater_than", "less_than", "equals"]},
            {"id": "loan_purpose", "name": "Loan Purpose", "type": "enum", "operators": ["equals"], "values": ["purchase", "refinance", "cash_out", "heloc"]},
            {"id": "property_type", "name": "Property Type", "type": "enum", "operators": ["equals"], "values": ["single_family", "condo", "townhouse", "multi_family"]},
            {"id": "credit_score_range", "name": "Credit Score Range", "type": "enum", "operators": ["equals"], "values": ["below_620", "620-679", "680-719", "720-759", "760+", "700+"]},
            {"id": "source_category", "name": "Source Category", "type": "enum", "operators": ["equals"], "values": ["online", "referral", "marketing", "direct", "other"]},
            {"id": "state", "name": "State", "type": "string", "operators": ["equals", "contains"]},
        ]

        operators = [
            {"id": "exists", "name": "Has value", "description": "Field has any value"},
            {"id": "not_exists", "name": "Is empty", "description": "Field is empty"},
            {"id": "equals", "name": "Equals", "description": "Field equals specific value"},
            {"id": "contains", "name": "Contains", "description": "Field contains text"},
            {"id": "greater_than", "name": "Greater than", "description": "Number is greater than value"},
            {"id": "less_than", "name": "Less than", "description": "Number is less than value"},
        ]

        return success_response(
            data={
                "fields": fields,
                "operators": operators
            },
            message="Scoring field options retrieved"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error fetching scoring field options")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/assignable-users")
async def get_assignable_users(
    current_user = Depends(_resolve_current_user),
    db = Depends(lambda: _get_db)
):
    """Get users that can be assigned leads"""
    from sqlalchemy import func, text

    try:
        if current_user is None:
            raise PermissionException("Authentication required")

        if db is None or _get_db is None:
            raise HTTPException(status_code=500, detail="Database not configured")

        # Get actual database session
        db_session = next(_get_db())

        # Query active users who can receive leads (loan officers, sales roles)
        assignable_roles = ['loan_officer', 'sales', 'admin', 'leadership']

        try:
            # Get users with lead counts
            users_query = db_session.execute(text("""
                SELECT
                    u.id,
                    u.full_name as name,
                    u.email,
                    COALESCE(u.role, 'loan_officer') as role,
                    COUNT(DISTINCT l.id) as current_leads,
                    50 as daily_capacity
                FROM users u
                LEFT JOIN leads l ON l.assigned_to = u.id
                    AND l.stage NOT IN ('converted', 'lost', 'closed')
                    AND l.created_at >= date('now', '-30 days')
                WHERE u.is_active = 1
                    AND (u.role IN ('loan_officer', 'sales', 'admin')
                         OR u.permission_role IN ('sales', 'admin', 'leadership'))
                GROUP BY u.id, u.full_name, u.email, u.role
                ORDER BY u.full_name
            """))

            users = []
            for row in users_query:
                users.append({
                    "id": row[0],
                    "name": row[1] or row[2].split("@")[0],  # Fallback to email prefix
                    "email": row[2],
                    "role": row[3].replace("_", " ").title() if row[3] else "Loan Officer",
                    "current_leads": row[4] or 0,
                    "daily_capacity": row[5] or 50
                })

            return success_response(
                data={"users": users},
                message=f"Found {len(users)} assignable users"
            )

        finally:
            db_session.close()

    except HTTPException:
        raise
    except SQLAlchemyError as e:
        logger.exception("Error fetching assignable users")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/statistics")
async def get_lead_statistics(
    current_user = Depends(_resolve_current_user),
    db = Depends(lambda: _get_db)
):
    """Get lead capture statistics"""
    from sqlalchemy import text

    try:
        if current_user is None:
            raise PermissionException("Authentication required")

        if db is None or _get_db is None:
            raise HTTPException(status_code=500, detail="Database not configured")

        db_session = next(_get_db())

        try:
            # Total leads in last 30 days
            total_result = db_session.execute(text("""
                SELECT COUNT(*) FROM leads
                WHERE created_at >= date('now', '-30 days')
            """)).scalar() or 0

            # Leads by source
            source_result = db_session.execute(text("""
                SELECT COALESCE(source, 'other') as src, COUNT(*) as cnt
                FROM leads
                WHERE created_at >= date('now', '-30 days')
                GROUP BY source
            """))
            leads_by_source = {row[0] or 'other': row[1] for row in source_result}

            # Leads by stage
            stage_result = db_session.execute(text("""
                SELECT COALESCE(stage, 'new') as stg, COUNT(*) as cnt
                FROM leads
                WHERE created_at >= date('now', '-30 days')
                GROUP BY stage
            """))
            leads_by_stage = {row[0] or 'new': row[1] for row in stage_result}

            # Conversion rate (converted / total)
            converted = leads_by_stage.get('converted', 0) + leads_by_stage.get('closed_won', 0)
            conversion_rate = round((converted / total_result * 100), 1) if total_result > 0 else 0

            # Average lead score
            avg_score = db_session.execute(text("""
                SELECT AVG(lead_score) FROM leads
                WHERE created_at >= date('now', '-30 days')
                AND lead_score IS NOT NULL
            """)).scalar() or 0

            stats = {
                "total_leads_30d": total_result,
                "leads_by_source": leads_by_source if leads_by_source else {"website": 0},
                "leads_by_stage": leads_by_stage if leads_by_stage else {"new": 0},
                "conversion_rate": conversion_rate,
                "avg_lead_score": round(float(avg_score), 1) if avg_score else 0,
                "avg_response_time_minutes": 15,  # Would need separate tracking table
                "duplicate_rate": 0  # Would need duplicate detection logic
            }

            return success_response(
                data=stats,
                message="Lead statistics retrieved"
            )

        finally:
            db_session.close()

    except HTTPException:
        raise
    except SQLAlchemyError as e:
        logger.exception("Error fetching lead statistics")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/test-scoring")
async def test_scoring_rules(
    test_lead: dict,
    current_user = Depends(_resolve_current_user)
):
    """Test scoring rules against a sample lead"""
    try:
        if current_user is None:
            raise PermissionException("Authentication required")

        # Simulate scoring
        score = 0
        applied_rules = []

        for rule in DEFAULT_SCORING_RULES:
            if not rule.get("enabled", True):
                continue

            field = rule["field"]
            operator = rule["operator"]
            value = rule.get("value")
            points = rule["points"]

            field_value = test_lead.get(field)

            matched = False
            if operator == "exists" and field_value:
                matched = True
            elif operator == "not_exists" and not field_value:
                matched = True
            elif operator == "equals" and str(field_value) == str(value):
                matched = True
            elif operator == "greater_than" and field_value and float(field_value) > float(value):
                matched = True
            elif operator == "less_than" and field_value and float(field_value) < float(value):
                matched = True
            elif operator == "contains" and field_value and value in str(field_value):
                matched = True

            if matched:
                score += points
                applied_rules.append({
                    "rule_id": rule["id"],
                    "rule_name": rule["name"],
                    "points": points
                })

        # Determine grade
        if score >= 80:
            grade = "hot"
        elif score >= 50:
            grade = "warm"
        else:
            grade = "cold"

        return success_response(
            data={
                "total_score": score,
                "grade": grade,
                "applied_rules": applied_rules,
                "max_possible_score": sum(r["points"] for r in DEFAULT_SCORING_RULES if r.get("enabled", True) and r["points"] > 0)
            },
            message=f"Lead scored: {score} points ({grade})"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error testing scoring rules")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/reset-defaults")
async def reset_to_defaults(
    current_user = Depends(_resolve_current_user)
):
    """Reset lead capture settings to defaults"""
    try:
        if current_user is None:
            raise PermissionException("Authentication required")

        if not getattr(current_user, 'is_admin', False) and not getattr(current_user, 'role', '') in ['admin', 'manager']:
            raise PermissionException("Admin access required to reset settings")

        settings = DEFAULT_SETTINGS.copy()
        settings["last_updated"] = datetime.utcnow().isoformat()
        settings["updated_by"] = getattr(current_user, 'id', None)
        settings["reset_to_defaults"] = True

        return success_response(
            data=settings,
            message="Lead capture settings reset to defaults"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error resetting lead capture settings")
        raise HTTPException(status_code=500, detail="Internal server error")
