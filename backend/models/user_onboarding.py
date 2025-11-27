"""
User Creation & Onboarding System Models
Complete data models for the user creation workflow including:
- Roles
- Categories
- Responsibilities
- Permission Templates
- User Permissions
- KPI Scorecards
- Bulk Upload Sessions
"""

from sqlalchemy import (
    Column, Integer, String, Text, Boolean, DateTime, ForeignKey,
    JSON, Float, Index, UniqueConstraint, Table
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
import uuid

# Import Base from main - will be set dynamically
Base = None

def set_base(base):
    """Set the Base for models - called from main.py"""
    global Base
    Base = base


# ============================================================================
# ROLE MODEL
# ============================================================================
class Role(Base):
    """
    User roles define the primary job function
    Examples: Loan Officer, Processor, Concierge, etc.
    """
    __tablename__ = "roles"
    __table_args__ = {'extend_existing': True}

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False, unique=True, index=True)
    description = Column(Text)
    default_permission_template_id = Column(Integer, ForeignKey("permission_templates.id"))
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    default_permission_template = relationship("PermissionTemplate", foreign_keys=[default_permission_template_id])
    users = relationship("UserProfile", back_populates="role")
    default_categories = relationship("RoleDefaultCategory", back_populates="role", cascade="all, delete-orphan")
    default_responsibilities = relationship("RoleDefaultResponsibility", back_populates="role", cascade="all, delete-orphan")


# ============================================================================
# CATEGORY MODEL
# ============================================================================
class Category(Base):
    """
    Categories represent operational areas of responsibility
    Examples: Lead Generation, Borrower Engagement, Processing & Milestones
    """
    __tablename__ = "categories"
    __table_args__ = {'extend_existing': True}

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False, unique=True, index=True)
    description = Column(Text)
    sort_order = Column(Integer, default=0, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    # Relationships
    responsibilities = relationship("Responsibility", back_populates="category")


# ============================================================================
# RESPONSIBILITY MODEL
# ============================================================================
class Responsibility(Base):
    """
    Responsibilities are specific tasks/duties that can be assigned to users
    Each responsibility maps to KPIs for scorecard generation
    """
    __tablename__ = "responsibilities"
    __table_args__ = {'extend_existing': True}

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200), nullable=False, index=True)
    description = Column(Text)
    category_id = Column(Integer, ForeignKey("categories.id"), nullable=False)
    applicable_role_ids = Column(JSON, default=list)  # List of role IDs this responsibility applies to
    kpi_mapping = Column(JSON)  # Maps to KPI definitions for scorecard generation
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    category = relationship("Category", back_populates="responsibilities")


# ============================================================================
# JUNCTION TABLES FOR ROLE DEFAULTS
# ============================================================================
class RoleDefaultCategory(Base):
    """Junction table for default categories per role"""
    __tablename__ = "role_default_categories"
    __table_args__ = (
        UniqueConstraint('role_id', 'category_id', name='uix_role_default_category'),
        {'extend_existing': True}
    )

    id = Column(Integer, primary_key=True, index=True)
    role_id = Column(Integer, ForeignKey("roles.id", ondelete="CASCADE"), nullable=False)
    category_id = Column(Integer, ForeignKey("categories.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    # Relationships
    role = relationship("Role", back_populates="default_categories")
    category = relationship("Category")


class RoleDefaultResponsibility(Base):
    """Junction table for default responsibilities per role"""
    __tablename__ = "role_default_responsibilities"
    __table_args__ = (
        UniqueConstraint('role_id', 'responsibility_id', name='uix_role_default_responsibility'),
        {'extend_existing': True}
    )

    id = Column(Integer, primary_key=True, index=True)
    role_id = Column(Integer, ForeignKey("roles.id", ondelete="CASCADE"), nullable=False)
    responsibility_id = Column(Integer, ForeignKey("responsibilities.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    # Relationships
    role = relationship("Role", back_populates="default_responsibilities")
    responsibility = relationship("Responsibility")


# ============================================================================
# USER PROFILE MODEL (Extended user info for onboarding)
# ============================================================================
class UserProfile(Base):
    """
    Extended user profile for onboarding system
    Links to the main User table via user_id
    """
    __tablename__ = "user_profiles"
    __table_args__ = {'extend_existing': True}

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False)

    # Basic info (may duplicate some User fields for flexibility)
    first_name = Column(String(100))
    last_name = Column(String(100))
    internal_title = Column(String(150))
    profile_image_url = Column(Text)

    # Role and status
    role_id = Column(Integer, ForeignKey("roles.id"))
    permission_template_id = Column(Integer, ForeignKey("permission_templates.id"))
    status = Column(String(50), default="pending_setup", nullable=False, index=True)
    # Status values: 'pending_setup', 'active_awaiting_setup', 'active', 'suspended', 'deactivated'

    # Activation
    activation_token = Column(String(255), unique=True, index=True)
    activation_token_expires_at = Column(DateTime)
    activated_at = Column(DateTime)

    # Timestamps
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    created_by = Column(Integer, ForeignKey("users.id"))

    # Relationships
    role = relationship("Role", back_populates="users")
    permission_template = relationship("PermissionTemplate")
    categories = relationship("UserCategory", back_populates="user_profile", cascade="all, delete-orphan")
    responsibilities = relationship("UserResponsibility", back_populates="user_profile", cascade="all, delete-orphan")
    permissions = relationship("UserPermissions", back_populates="user_profile", uselist=False, cascade="all, delete-orphan")
    scorecard = relationship("KPIScorecard", back_populates="user_profile", uselist=False, cascade="all, delete-orphan")


# ============================================================================
# USER JUNCTION TABLES
# ============================================================================
class UserCategory(Base):
    """Junction table for user-category assignments"""
    __tablename__ = "user_categories"
    __table_args__ = (
        UniqueConstraint('user_profile_id', 'category_id', name='uix_user_category'),
        {'extend_existing': True}
    )

    id = Column(Integer, primary_key=True, index=True)
    user_profile_id = Column(Integer, ForeignKey("user_profiles.id", ondelete="CASCADE"), nullable=False)
    category_id = Column(Integer, ForeignKey("categories.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    # Relationships
    user_profile = relationship("UserProfile", back_populates="categories")
    category = relationship("Category")


class UserResponsibility(Base):
    """Junction table for user-responsibility assignments"""
    __tablename__ = "user_responsibilities"
    __table_args__ = (
        UniqueConstraint('user_profile_id', 'responsibility_id', name='uix_user_responsibility'),
        {'extend_existing': True}
    )

    id = Column(Integer, primary_key=True, index=True)
    user_profile_id = Column(Integer, ForeignKey("user_profiles.id", ondelete="CASCADE"), nullable=False)
    responsibility_id = Column(Integer, ForeignKey("responsibilities.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    # Relationships
    user_profile = relationship("UserProfile", back_populates="responsibilities")
    responsibility = relationship("Responsibility")


# ============================================================================
# PERMISSION TEMPLATE MODEL
# ============================================================================
class PermissionTemplate(Base):
    """
    Pre-configured permission sets that can be applied to users
    Stores granular permissions as JSON
    """
    __tablename__ = "permission_templates"
    __table_args__ = {'extend_existing': True}

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False, unique=True, index=True)
    description = Column(Text)
    permissions = Column(JSON, nullable=False, default=dict)
    is_system_template = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    created_by = Column(Integer, ForeignKey("users.id"))


# ============================================================================
# USER PERMISSIONS MODEL
# ============================================================================
class UserPermissions(Base):
    """
    Stores individual user's permissions
    Can be from a template or custom-configured
    """
    __tablename__ = "user_permissions_v2"  # v2 to avoid conflict with existing table
    __table_args__ = {'extend_existing': True}

    id = Column(Integer, primary_key=True, index=True)
    user_profile_id = Column(Integer, ForeignKey("user_profiles.id", ondelete="CASCADE"), unique=True, nullable=False)
    permissions = Column(JSON, nullable=False, default=dict)
    source = Column(String(50), default="template", nullable=False)  # 'template', 'custom', 'override'
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    user_profile = relationship("UserProfile", back_populates="permissions")


# ============================================================================
# KPI SCORECARD MODEL
# ============================================================================
class KPIScorecard(Base):
    """
    Auto-generated KPI scorecard based on user's responsibilities
    Stores the scorecard configuration as JSON
    """
    __tablename__ = "kpi_scorecards"
    __table_args__ = {'extend_existing': True}

    id = Column(Integer, primary_key=True, index=True)
    user_profile_id = Column(Integer, ForeignKey("user_profiles.id", ondelete="CASCADE"), unique=True, nullable=False)
    scorecard_config = Column(JSON, nullable=False, default=dict)
    # scorecard_config structure:
    # {
    #   "daily_kpis": [...],
    #   "weekly_kpis": [...],
    #   "monthly_kpis": [...],
    #   "efficiency_scores": [...],
    #   "communication_scores": [...],
    #   "referral_scores": [...],
    #   "mum_engagement_scores": [...]
    # }
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    user_profile = relationship("UserProfile", back_populates="scorecard")


# ============================================================================
# BULK UPLOAD MODELS
# ============================================================================
class BulkUploadSession(Base):
    """
    Tracks bulk user upload sessions
    """
    __tablename__ = "bulk_upload_sessions"
    __table_args__ = {'extend_existing': True}

    id = Column(Integer, primary_key=True, index=True)
    uploaded_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    filename = Column(String(255), nullable=False)
    file_path = Column(Text, nullable=False)
    total_rows = Column(Integer, nullable=False)
    valid_rows = Column(Integer, nullable=False, default=0)
    invalid_rows = Column(Integer, nullable=False, default=0)
    status = Column(String(50), default="pending", nullable=False, index=True)
    # Status values: 'pending', 'validated', 'processing', 'completed', 'failed'
    validation_results = Column(JSON)
    column_mapping = Column(JSON)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    processed_at = Column(DateTime)

    # Relationships
    drafts = relationship("BulkUserDraft", back_populates="session", cascade="all, delete-orphan")


class BulkUserDraft(Base):
    """
    Temporary storage for bulk upload user data before finalization
    """
    __tablename__ = "bulk_user_drafts"
    __table_args__ = {'extend_existing': True}

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey("bulk_upload_sessions.id", ondelete="CASCADE"), nullable=False)
    row_number = Column(Integer, nullable=False)

    # User data
    first_name = Column(String(100))
    last_name = Column(String(100))
    email = Column(String(255), index=True)
    phone = Column(String(20))
    internal_title = Column(String(150))

    # Role and permissions (text values from file)
    role_name = Column(String(100))
    role_id = Column(Integer, ForeignKey("roles.id"))
    categories = Column(JSON)  # Array of category names
    category_ids = Column(JSON)  # Array of resolved category IDs
    responsibilities = Column(JSON)  # Array of responsibility names
    responsibility_ids = Column(JSON)  # Array of resolved responsibility IDs
    permission_template_name = Column(String(100))
    permission_template_id = Column(Integer, ForeignKey("permission_templates.id"))

    # Validation
    is_valid = Column(Boolean, default=True, nullable=False)
    validation_errors = Column(JSON)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    # Relationships
    session = relationship("BulkUploadSession", back_populates="drafts")


# ============================================================================
# AUDIT LOG MODEL
# ============================================================================
class UserAuditLog(Base):
    """
    Audit trail for user-related actions
    """
    __tablename__ = "user_audit_log"
    __table_args__ = {'extend_existing': True}

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))  # User affected
    action = Column(String(100), nullable=False, index=True)
    # Action values: 'user_created', 'user_updated', 'permissions_changed',
    #                'role_changed', 'user_activated', 'user_deactivated', etc.
    performed_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    details = Column(JSON)
    ip_address = Column(String(45))  # IPv6 compatible
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False, index=True)


# ============================================================================
# ONBOARDING SESSION MODEL
# ============================================================================
class OnboardingSession(Base):
    """
    Tracks the state of a user creation wizard session
    """
    __tablename__ = "onboarding_sessions"
    __table_args__ = {'extend_existing': True}

    id = Column(Integer, primary_key=True, index=True)
    session_token = Column(String(255), unique=True, index=True, nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"))  # The user being created
    user_profile_id = Column(Integer, ForeignKey("user_profiles.id"))
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)

    # Wizard state
    current_step = Column(String(50), default="basic_info", nullable=False)
    # Steps: 'basic_info', 'role_builder', 'permissions_builder', 'review_confirm'

    # Step data (stored as JSON for flexibility)
    basic_info_data = Column(JSON)
    role_builder_data = Column(JSON)
    permissions_data = Column(JSON)

    # Status
    status = Column(String(50), default="in_progress", nullable=False)
    # Status values: 'in_progress', 'completed', 'cancelled', 'expired'

    # Timestamps
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    expires_at = Column(DateTime)
    completed_at = Column(DateTime)
