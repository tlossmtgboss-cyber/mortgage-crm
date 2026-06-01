"""
User Creation & Onboarding System Models — back-compat shim.

The canonical onboarding models (the ``onboarding_*`` tables) are built by
``user_onboarding_integration.create_user_onboarding_models()`` on the single
canonical ``db.Base``. Historically this module ALSO defined the same models on
its own private ``declarative_base()``, which split the SQLAlchemy registry and
broke cross-model relationships once everything was unified.

This module now re-exports the canonical classes under their historical names so
existing ``from models.user_onboarding import Role, Category, ...`` imports keep
working, and defines the few models that only ever lived here
(``BulkUploadSession``, ``BulkUserDraft``, ``UserAuditLog``).
"""
from datetime import datetime, timezone

from sqlalchemy import (
    Column, Integer, String, Text, Boolean, DateTime, ForeignKey, JSON,
)
from sqlalchemy.orm import relationship

from db import Base
from user_onboarding_integration import create_user_onboarding_models

# Build (idempotently) and re-export the canonical onboarding models. The
# factory caches per Base, so this call and register_all_models() share classes.
_onboarding_models = create_user_onboarding_models(Base)

Role = _onboarding_models['Role']                                  # table: onboarding_roles
Category = _onboarding_models['Category']
Responsibility = _onboarding_models['Responsibility']             # OnboardingResponsibility
PermissionTemplate = _onboarding_models['PermissionTemplate']
UserProfile = _onboarding_models['UserProfile']
UserCategory = _onboarding_models['UserCategory']
UserResponsibility = _onboarding_models['UserResponsibility']     # OnboardingUserResponsibility
UserPermissions = _onboarding_models['UserPermissions']
KPIScorecard = _onboarding_models['KPIScorecard']
RoleDefaultCategory = _onboarding_models['RoleDefaultCategory']
RoleDefaultResponsibility = _onboarding_models['RoleDefaultResponsibility']
OnboardingSession = _onboarding_models['OnboardingSession']


def set_base(base):
    """Legacy no-op kept for backward compatibility."""
    pass


# ============================================================================
# MODELS THAT ONLY LIVE HERE (not produced by the onboarding factory)
# ============================================================================
class BulkUploadSession(Base):
    """Tracks bulk user upload sessions."""
    __tablename__ = "onboarding_bulk_upload_sessions"
    __table_args__ = {'extend_existing': True}

    id = Column(Integer, primary_key=True, index=True)
    uploaded_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    filename = Column(String(255), nullable=False)
    file_path = Column(Text, nullable=False)
    total_rows = Column(Integer, nullable=False)
    valid_rows = Column(Integer, nullable=False, default=0)
    invalid_rows = Column(Integer, nullable=False, default=0)
    status = Column(String(50), default="pending", nullable=False, index=True)
    validation_results = Column(JSON)
    column_mapping = Column(JSON)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    processed_at = Column(DateTime)

    drafts = relationship("BulkUserDraft", back_populates="session", cascade="all, delete-orphan")


class BulkUserDraft(Base):
    """Temporary storage for bulk upload user data before finalization."""
    __tablename__ = "onboarding_bulk_user_drafts"
    __table_args__ = {'extend_existing': True}

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey("onboarding_bulk_upload_sessions.id", ondelete="CASCADE"), nullable=False)
    row_number = Column(Integer, nullable=False)

    first_name = Column(String(100))
    last_name = Column(String(100))
    email = Column(String(255), index=True)
    phone = Column(String(20))
    internal_title = Column(String(150))

    role_name = Column(String(100))
    role_id = Column(Integer, ForeignKey("onboarding_roles.id"))
    categories = Column(JSON)
    category_ids = Column(JSON)
    responsibilities = Column(JSON)
    responsibility_ids = Column(JSON)
    permission_template_name = Column(String(100))
    permission_template_id = Column(Integer, ForeignKey("onboarding_permission_templates.id"))

    is_valid = Column(Boolean, default=True, nullable=False)
    validation_errors = Column(JSON)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    session = relationship("BulkUploadSession", back_populates="drafts")


class UserAuditLog(Base):
    """Audit trail for user-related actions."""
    __tablename__ = "onboarding_user_audit_log"
    __table_args__ = {'extend_existing': True}

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    action = Column(String(100), nullable=False, index=True)
    performed_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    details = Column(JSON)
    ip_address = Column(String(45))
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False, index=True)
