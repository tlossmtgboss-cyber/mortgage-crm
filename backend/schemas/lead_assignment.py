"""
Lead Assignment Pydantic Schemas

Request/response models for the lead assignment configuration API.
"""

from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, validator


# =============================================================================
# Config Schemas
# =============================================================================

class AssignmentConfigUpdate(BaseModel):
    """Update organization assignment config."""
    strategy: str = Field(
        "round_robin",
        pattern="^(round_robin|weighted|geographic|load_balanced|rule_based|manual)$",
    )
    fallback_user_id: Optional[int] = None
    respect_capacity: bool = True
    max_daily_leads_per_user: int = Field(50, ge=1, le=500)
    business_hours_only: bool = False
    business_hours_start: str = Field("08:00", pattern=r"^\d{2}:\d{2}$")
    business_hours_end: str = Field("18:00", pattern=r"^\d{2}:\d{2}$")
    business_hours_timezone: str = "America/New_York"
    notify_on_assignment: bool = True
    notification_channels: List[str] = ["email"]
    dedup_enabled: bool = True
    dedup_match_fields: List[str] = ["email", "phone"]
    dedup_window_days: int = Field(30, ge=1, le=365)
    dedup_action: str = Field("merge", pattern="^(merge|update|reject)$")

    @validator("notification_channels", each_item=True)
    def validate_channels(cls, v):
        if v not in ("email", "sms", "push"):
            raise ValueError(f"Invalid channel: {v}")
        return v


class AssignmentConfigResponse(BaseModel):
    """Assignment config response."""
    id: int
    organization_id: int
    strategy: str
    fallback_user_id: Optional[int]
    respect_capacity: bool
    max_daily_leads_per_user: int
    business_hours_only: bool
    business_hours_start: str
    business_hours_end: str
    business_hours_timezone: str
    notify_on_assignment: bool
    notification_channels: List[str]
    round_robin_index: int
    dedup_enabled: bool
    dedup_match_fields: List[str]
    dedup_window_days: int
    dedup_action: str
    is_active: bool
    updated_at: Optional[datetime]

    class Config:
        from_attributes = True


# =============================================================================
# Rule Schemas
# =============================================================================

class RuleCondition(BaseModel):
    """Single condition in a rule."""
    field: str = Field(..., min_length=1, max_length=50)
    op: str = Field(
        ..., pattern="^(eq|neq|in|not_in|gt|gte|lt|lte|contains)$"
    )
    value: Any


class RuleCreate(BaseModel):
    """Create a new assignment rule."""
    rule_name: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = Field(None, max_length=500)
    priority: int = Field(100, ge=1, le=10000)
    conditions: List[RuleCondition]
    match_type: str = Field("ALL", pattern="^(ALL|ANY)$")
    target_type: str = Field(..., pattern="^(USER|POOL|ROUND_ROBIN|ROLE)$")
    target_config: Dict[str, Any]

    @validator("conditions")
    def validate_conditions(cls, v):
        if not v:
            raise ValueError("At least one condition is required")
        valid_fields = [
            "loan_amount", "loan_purpose", "loan_type", "property_type",
            "state", "zip_code", "credit_score", "source", "ai_score",
            "first_time_buyer", "employment_status", "referral_partner_id",
        ]
        for cond in v:
            if cond.field not in valid_fields:
                raise ValueError(
                    f"Invalid field: {cond.field}. Valid: {', '.join(valid_fields)}"
                )
        return v


class RuleUpdate(BaseModel):
    """Update an existing rule."""
    rule_name: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = Field(None, max_length=500)
    priority: Optional[int] = Field(None, ge=1, le=10000)
    conditions: Optional[List[RuleCondition]] = None
    match_type: Optional[str] = Field(None, pattern="^(ALL|ANY)$")
    target_type: Optional[str] = Field(None, pattern="^(USER|POOL|ROUND_ROBIN|ROLE)$")
    target_config: Optional[Dict[str, Any]] = None
    is_active: Optional[bool] = None


class RuleResponse(BaseModel):
    """Rule response."""
    id: int
    organization_id: int
    rule_name: str
    description: Optional[str]
    priority: int
    conditions: List[Dict[str, Any]]
    match_type: str
    target_type: str
    target_config: Dict[str, Any]
    is_active: bool
    created_at: Optional[datetime]
    updated_at: Optional[datetime]

    class Config:
        from_attributes = True


# =============================================================================
# Pool Schemas
# =============================================================================

class PoolMemberCreate(BaseModel):
    """Add a member to the assignment pool."""
    user_id: int
    weight: int = Field(100, ge=1, le=1000)
    max_daily_leads: int = Field(50, ge=1, le=500)
    geographic_states: Optional[List[str]] = None
    specialties: Optional[List[str]] = None


class PoolMemberUpdate(BaseModel):
    """Update a pool member."""
    weight: Optional[int] = Field(None, ge=1, le=1000)
    max_daily_leads: Optional[int] = Field(None, ge=1, le=500)
    geographic_states: Optional[List[str]] = None
    specialties: Optional[List[str]] = None
    is_active: Optional[bool] = None


class PoolMemberResponse(BaseModel):
    """Pool member response."""
    id: int
    user_id: int
    weight: int
    max_daily_leads: int
    is_active: bool
    geographic_states: Optional[List[str]]
    specialties: Optional[List[str]]
    # Populated at runtime
    user_name: Optional[str] = None
    current_daily_leads: Optional[int] = None

    class Config:
        from_attributes = True


# =============================================================================
# Exception Schemas
# =============================================================================

class ExceptionCreate(BaseModel):
    """Create an assignment exception."""
    user_id: int
    exception_type: str = Field(
        ..., pattern="^(PTO|CAPACITY_OVERRIDE|BLOCKED|TRAINING)$"
    )
    reason: Optional[str] = Field(None, max_length=500)
    starts_at: datetime
    ends_at: Optional[datetime] = None

    @validator("ends_at")
    def validate_dates(cls, v, values):
        if v and "starts_at" in values and v <= values["starts_at"]:
            raise ValueError("ends_at must be after starts_at")
        return v


class ExceptionResponse(BaseModel):
    """Exception response."""
    id: int
    user_id: int
    exception_type: str
    reason: Optional[str]
    starts_at: datetime
    ends_at: Optional[datetime]
    is_active: bool
    created_at: Optional[datetime]

    class Config:
        from_attributes = True


# =============================================================================
# Test & Audit Schemas
# =============================================================================

class TestAssignmentRequest(BaseModel):
    """Test which LO a lead would be assigned to (dry run)."""
    loan_amount: Optional[float] = None
    loan_purpose: Optional[str] = None
    loan_type: Optional[str] = None
    property_type: Optional[str] = None
    state: Optional[str] = None
    zip_code: Optional[str] = None
    credit_score: Optional[int] = None
    source: Optional[str] = None


class TestAssignmentResponse(BaseModel):
    """Result of a test assignment."""
    assigned_user_id: Optional[int]
    assigned_user_name: Optional[str]
    strategy_used: str
    rule_matched: Optional[str]
    decision_reason: str
    candidates_evaluated: int
    is_dry_run: bool = True


class AuditLogEntry(BaseModel):
    """Single audit log entry."""
    id: int
    lead_id: Optional[int]
    action: str
    strategy_used: Optional[str]
    rule_name: Optional[str]
    from_user_id: Optional[int]
    to_user_id: Optional[int]
    decision_reason: Optional[str]
    created_at: Optional[datetime]

    class Config:
        from_attributes = True


class ReassignRequest(BaseModel):
    """Reassign a lead to a different user."""
    lead_id: int
    to_user_id: int
    reason: Optional[str] = Field(None, max_length=500)
