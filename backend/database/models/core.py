"""
Core Database Models

Organization, User, Branch, and related authentication/settings models.
Extracted from main.py as part of the architecture decomposition.

Usage:
    from database.models.core import User, Organization, Branch

    # In SQLAlchemy queries
    user = db.query(User).filter(User.email == email).first()
"""

from datetime import datetime, timezone
from sqlalchemy import (
    Column, Integer, String, Float, Boolean, DateTime, Date,
    Text, ForeignKey, JSON, UniqueConstraint, Index
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

# Import Base from the db module (renamed from database.py)
from db import Base
from encryption_utils import EncryptedString


# ============================================================================
# ORGANIZATION & MULTI-TENANCY
# ============================================================================

class Organization(Base):
    """Multi-tenant organization model - each company/team has their own organization"""
    __tablename__ = "organizations"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    slug = Column(String, unique=True, index=True)  # URL-friendly identifier
    domain = Column(String, unique=True, index=True)  # Email domain for auto-assignment

    # Organization settings
    settings = Column(JSON, default=dict)  # General org settings

    # Subscription info (links to organization_subscriptions table)
    subscription_tier = Column(String, default="lead_management")

    # SSO enforcement (Enterprise Check 5.12) - when True, password login is blocked
    sso_enforced = Column(Boolean, default=False)

    # MFA enforcement (Enterprise Check 4.6) - when True, all users must enable MFA
    mfa_required = Column(Boolean, default=False)

    # Status
    is_active = Column(Boolean, default=True)

    # Org-wide default timezone (individual users can override via User.timezone)
    timezone = Column(String(50), default="America/Chicago")

    # Booking page branding
    booking_slug = Column(String, unique=True, index=True, nullable=True)  # URL-safe slug for public booking pages
    booking_logo_url = Column(Text, nullable=True)  # Org logo shown on booking page
    booking_primary_color = Column(String(7), default="#1a73e8")  # Hex color for primary elements
    booking_accent_color = Column(String(7), default="#34a853")  # Hex color for accent elements
    booking_tagline = Column(String(200), nullable=True)  # Short tagline on booking page
    booking_welcome_message = Column(Text, nullable=True)  # Custom welcome text
    booking_custom_css = Column(Text, nullable=True)  # Optional sanitized custom CSS
    booking_cover_image_url = Column(Text, nullable=True)  # Background/cover image
    booking_show_testimonials = Column(Boolean, default=False)
    booking_testimonials = Column(JSON, default=list)  # Array of {name, text, role} objects

    # Timestamps
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    users = relationship("User", back_populates="organization")
    branches = relationship("Branch", back_populates="organization")
    microsoft_config = relationship("MicrosoftAppConfig", back_populates="organization", uselist=False)


class Branch(Base):
    """Branch/office within an organization"""
    __tablename__ = "branches"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    company = Column(String)
    nmls_id = Column(String)
    organization_id = Column(Integer, ForeignKey("organizations.id"))
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    # Relationships
    users = relationship("User", back_populates="branch")
    organization = relationship("Organization", back_populates="branches")


# ============================================================================
# USER & AUTHENTICATION
# ============================================================================

class User(Base):
    """User/employee account"""
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)  # NOTE: Not encrypted — unique+indexed for auth lookups. Consider adding email_hash column.
    hashed_password = Column(String, nullable=False)
    first_name = Column(EncryptedString)  # PII: name
    last_name = Column(EncryptedString)  # PII: name
    role = Column(String, default="loan_officer")  # Legacy role field

    @property
    def full_name(self) -> str:
        """Computed property for backwards compatibility."""
        if self.first_name and self.last_name:
            return f"{self.first_name} {self.last_name}"
        return self.first_name or self.last_name or ""

    # Phase 2: permission roles
    permission_role = Column(String, default="sales")  # 'admin', 'site_admin', 'leadership', 'management', 'sales', 'processing', 'operations'
    branch_id = Column(Integer, ForeignKey("branches.id"))
    organization_id = Column(Integer, ForeignKey("organizations.id"))  # Multi-tenant: user's organization
    is_active = Column(Boolean, default=True)

    # Organizational hierarchy
    manager_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)

    # Briefing preferences
    briefing_enabled = Column(Boolean, default=True)
    briefing_hour = Column(Integer, default=7)  # 0-23 in user's timezone
    briefing_preferences = Column(JSONB, nullable=True)  # Section toggles, thresholds, AI tone (NULL = all defaults)
    email_verified = Column(Boolean, default=False)
    onboarding_completed = Column(Boolean, default=False)
    user_metadata = Column(JSON)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    # Onboarding fields
    phone = Column(EncryptedString)  # PII: phone number
    nmls_number = Column(String, index=True)  # NOTE: Not encrypted — indexed for lookups. Public registry number.
    business_address = Column(EncryptedString)  # PII: physical address
    current_role = Column(String)
    business_hours = Column(JSON)
    email_verified_at = Column(DateTime)
    phone_verified_at = Column(DateTime)

    # Microsite slug - URL-friendly identifier for LO public profile
    slug = Column(String, unique=True, index=True)

    # Company/branding - added via migration for portal display
    company_logo_url = Column(Text, nullable=True)
    headshot_url = Column(Text, nullable=True)
    title = Column(Text, nullable=True)  # e.g., "Senior Loan Officer"
    team_name = Column(Text, nullable=True)  # e.g., "Tim Loss Team"
    nmls_id = Column(String, nullable=True)

    # Timezone for AI scheduling and display
    # Default aligned with SCHEDULER_DEFAULT_TIMEZONE env var fallback (see routes/scheduler/constants.py)
    timezone = Column(String, default="America/Chicago")

    # Activity tracking
    last_activity_at = Column(DateTime, nullable=True)

    # Account lockout (enterprise security - Check 4.4)
    failed_login_attempts = Column(Integer, default=0)
    locked_until = Column(DateTime, nullable=True)
    last_failed_login_at = Column(DateTime, nullable=True)

    # MFA (enterprise security - Check 4.6)
    mfa_secret = Column(EncryptedString, nullable=True)  # PII/security: TOTP secret (encrypted at-rest)
    mfa_enabled = Column(Boolean, default=False)
    mfa_backup_codes = Column(JSON, nullable=True)  # Hashed backup codes
    mfa_enabled_at = Column(DateTime, nullable=True)

    # SSO provisioning (Enterprise Check 5.11)
    sso_provider = Column(String, nullable=True)  # 'saml' or 'oidc' if JIT-provisioned
    sso_subject_id = Column(String, nullable=True)  # IdP unique identifier (NameID or sub claim)

    # Password change tracking (HIGH-03: session revocation after password reset)
    password_changed_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    branch = relationship("Branch", back_populates="users")
    organization = relationship("Organization", back_populates="users")
    leads = relationship("Lead", back_populates="owner")
    loans = relationship("Loan", back_populates="loan_officer")

    device_tokens = relationship("DeviceToken", back_populates="user", cascade="all, delete-orphan")

    # Manager hierarchy (self-referential)
    manager = relationship("User", remote_side="User.id", foreign_keys="User.manager_id",
                           backref="direct_reports")


class ApiKey(Base):
    """API key for programmatic access (Zapier, integrations)"""
    __tablename__ = "api_keys"

    id = Column(Integer, primary_key=True, index=True)
    key = Column(String, unique=True, index=True, nullable=True)  # Legacy plaintext — cleared after migration
    key_hash = Column(String(64), nullable=True, index=True)  # SHA-256 hex digest of the raw key
    key_prefix = Column(String(12), nullable=True)  # First 8 chars for display/identification
    name = Column(String, nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=True, index=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    last_used_at = Column(DateTime, nullable=True)

    # API key scopes (enterprise security - Check 4.11)
    scopes = Column(JSON, default=list)  # e.g. ["read:leads", "write:leads", "read:loans"]
    description = Column(String, nullable=True)
    expires_at = Column(DateTime, nullable=True)


class UserSettings(Base):
    """Key-value settings for users"""
    __tablename__ = "user_settings"
    __table_args__ = (UniqueConstraint('user_id', 'setting_key', name='uix_user_setting'),)

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    setting_key = Column(String, nullable=False)
    setting_value = Column(Text, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


# ============================================================================
# CALENDAR & SCHEDULING
# ============================================================================

class CalendarAssignment(Base):
    """Calendar assignments for different purposes in the application"""
    __tablename__ = "calendar_assignments"
    __table_args__ = (UniqueConstraint('organization_id', 'purpose', name='uix_org_calendar_purpose'),)

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=True)
    purpose = Column(String, nullable=False, index=True)  # e.g., 'purchase_application', 'refinance_application'
    purpose_label = Column(String, nullable=True)  # Human-readable label
    assigned_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    calendly_url = Column(String, nullable=True)
    booking_link_id = Column(Integer, nullable=True)  # Smart Scheduler booking link ID
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    assigned_user = relationship("User", foreign_keys=[assigned_user_id])


# ============================================================================
# EMAIL & COMMUNICATION SETTINGS
# ============================================================================

class EmailSignature(Base):
    """Email signature configuration for users"""
    __tablename__ = "email_signatures"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False, index=True)

    # Personal info
    full_name = Column(String, nullable=True)
    title = Column(String, nullable=True)
    team_name = Column(String, nullable=True)

    # Images (stored as URLs or base64)
    headshot_url = Column(Text, nullable=True)
    company_logo_url = Column(Text, nullable=True)

    # Contact info
    email = Column(EncryptedString, nullable=True)  # PII: email address
    office_phone = Column(EncryptedString, nullable=True)  # PII: phone number
    cell_phone = Column(EncryptedString, nullable=True)  # PII: phone number
    fax = Column(EncryptedString, nullable=True)  # PII: phone/fax number
    address = Column(EncryptedString, nullable=True)  # PII: physical address

    # Links
    website_url = Column(String, nullable=True)
    apply_now_url = Column(String, nullable=True)
    doc_upload_url = Column(String, nullable=True)
    schedule_url = Column(String, nullable=True)

    # Social links
    linkedin_url = Column(String, nullable=True)
    facebook_url = Column(String, nullable=True)
    instagram_url = Column(String, nullable=True)
    twitter_url = Column(String, nullable=True)

    # License info
    nmls_id = Column(String, nullable=True)
    branch_nmls_id = Column(String, nullable=True)
    corporate_nmls_id = Column(String, nullable=True)

    # Branding
    primary_color = Column(String, default="#006B6B")
    secondary_color = Column(String, default="#1B3A4B")
    tagline = Column(String, nullable=True)

    # Settings
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


# ============================================================================
# IMPERSONATION & SECURITY
# ============================================================================

class ImpersonationSession(Base):
    """Session tracking for user impersonation (manager viewing employee account)"""
    __tablename__ = "impersonation_sessions"

    id = Column(Integer, primary_key=True, index=True)
    session_token = Column(String, unique=True, index=True, nullable=False)
    manager_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    impersonated_user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    mode = Column(String, nullable=False)  # 'read_only' or 'full_access'
    reason = Column(String, nullable=False)
    duration_minutes = Column(Integer, nullable=False)
    notify_employee = Column(Boolean, default=False)
    started_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    expires_at = Column(DateTime, nullable=False)
    ended_at = Column(DateTime, nullable=True)
    is_active = Column(Boolean, default=True)


# ============================================================================
# ONBOARDING
# ============================================================================

class OnboardingProgress(Base):
    """Multi-step onboarding progress tracking"""
    __tablename__ = "onboarding_progress"
    __table_args__ = {'extend_existing': True}

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False, index=True)
    current_step = Column(Integer, default=1, nullable=False, index=True)

    # JSON columns for each step's data
    step_1_data = Column(JSON)
    step_2_data = Column(JSON)
    step_3_data = Column(JSON)
    step_4_data = Column(JSON)
    step_5_data = Column(JSON)
    step_6_data = Column(JSON)
    step_7_data = Column(JSON)
    step_8_data = Column(JSON)
    step_9_data = Column(JSON)
    step_10_data = Column(JSON)

    # Completion tracking
    completed_steps = Column(JSON, default=list)
    completed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


class OnboardingError(Base):
    """Track errors during onboarding for debugging"""
    __tablename__ = "onboarding_errors"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    step = Column(Integer, nullable=False)
    error_type = Column(String, nullable=False)
    error_message = Column(Text, nullable=False)
    error_details = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class VerificationToken(Base):
    """Email/phone verification tokens"""
    __tablename__ = "verification_tokens"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    token = Column(String, unique=True, nullable=False, index=True)
    token_type = Column(String, nullable=False)  # 'email' or 'phone'
    expires_at = Column(DateTime, nullable=False)
    used_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


# ============================================================================
# EXPORTS
# ============================================================================

__all__ = [
    # Organization
    "Organization",
    "Branch",
    # User
    "User",
    "ApiKey",
    "UserSettings",
    # Calendar
    "CalendarAssignment",
    # Email
    "EmailSignature",
    # Security
    "ImpersonationSession",
    # Onboarding
    "OnboardingProgress",
    "OnboardingError",
    "VerificationToken",
]
