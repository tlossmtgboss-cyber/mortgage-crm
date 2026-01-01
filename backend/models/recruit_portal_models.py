"""
Candidate Recruit Portal Models

Models for the public-facing candidate portal with:
- Portal workspaces and tokens
- Company updates/propaganda
- Chat messages
- Appointments
- Production calculator
"""

from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime


# =============================================================================
# Portal Workspace Models
# =============================================================================

class PortalWorkspaceBase(BaseModel):
    """Base model for portal workspace."""
    candidate_id: int
    slug: str
    is_active: bool = True
    theme_config: Optional[dict] = None


class PortalWorkspace(PortalWorkspaceBase):
    """Portal workspace with ID and metadata."""
    id: int
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class PortalWorkspaceCreate(BaseModel):
    """Model for creating a portal workspace."""
    candidate_id: int
    slug: Optional[str] = None  # Auto-generated if not provided


# =============================================================================
# Portal Token Models
# =============================================================================

class PortalToken(BaseModel):
    """Portal access token."""
    id: int
    workspace_id: int
    token: str
    scope: str = "full"
    expires_at: Optional[datetime] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# =============================================================================
# Company Update Models
# =============================================================================

class CompanyUpdateBase(BaseModel):
    """Base model for company updates."""
    title: str
    content: str
    media_url: Optional[str] = None
    category: str = "news"  # news, culture, success_stories, benefits
    is_featured: bool = False


class CompanyUpdate(CompanyUpdateBase):
    """Company update with metadata."""
    id: int
    published_at: Optional[datetime] = None
    created_by: Optional[int] = None

    class Config:
        from_attributes = True


class CompanyUpdateCreate(CompanyUpdateBase):
    """Model for creating a company update."""
    pass


# =============================================================================
# Chat Message Models
# =============================================================================

class ChatMessage(BaseModel):
    """Portal chat message."""
    id: Optional[int] = None
    workspace_id: int
    role: str  # user, assistant
    content: str
    metadata: Optional[dict] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class ChatRequest(BaseModel):
    """Request for chat interaction."""
    message: str
    context: Optional[dict] = None


class ChatResponse(BaseModel):
    """Response from chat interaction."""
    response: str
    metadata: Optional[dict] = None


# =============================================================================
# Appointment Models
# =============================================================================

class AppointmentBase(BaseModel):
    """Base model for portal appointments."""
    appointment_type: str
    scheduled_at: datetime
    duration_minutes: int = 30
    notes: Optional[str] = None


class Appointment(AppointmentBase):
    """Appointment with metadata."""
    id: int
    workspace_id: int
    status: str = "scheduled"
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class AppointmentCreate(AppointmentBase):
    """Model for creating an appointment."""
    pass


# =============================================================================
# Calculator Models
# =============================================================================

class CalculatorInput(BaseModel):
    """Input for production calculator."""
    current_volume: float = Field(..., description="Current annual loan volume ($)")
    current_units: int = Field(..., description="Current annual units closed")


class CalculatorResult(BaseModel):
    """Result from production calculator."""
    current_volume: float
    current_units: int
    projected_volume: float
    projected_units: int
    volume_increase: float
    volume_increase_pct: float
    unit_increase: int
    unit_increase_pct: float
    potential_earnings: float
    current_earnings: float
    earnings_increase: float
    earnings_increase_pct: float


# =============================================================================
# Portal Data Models (for API responses)
# =============================================================================

class PortalData(BaseModel):
    """Complete portal data for rendering."""
    workspace_id: int
    candidate_name: str
    candidate_status: Optional[str] = None
    company_name: str = "Perennia"
    company_tagline: str = "Join the team that helps you succeed"
    recruiter_name: Optional[str] = None
    recruiter_photo: Optional[str] = None
    recruiter_phone: Optional[str] = None
    recruiter_email: Optional[str] = None
    next_steps: Optional[str] = None
    calculator_config: Optional[dict] = None
    theme_config: Optional[dict] = None


class AvailabilitySlot(BaseModel):
    """Available time slot for scheduling."""
    start_time: str
    end_time: str
    is_available: bool = True
