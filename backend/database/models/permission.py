"""
Permission Models

Models for user permissions, roles, and access control.
Extracted from main.py as part of the architecture decomposition.

Usage:
    from database.models.permission import CRMPage, RolePagePermission, UserPagePermission

    # Query page permissions
    perms = db.query(RolePagePermission).filter(RolePagePermission.role == "admin").all()
"""

from datetime import datetime, timezone
from sqlalchemy import (
    Column, Integer, String, Float, Boolean, DateTime, Date,
    Text, ForeignKey, JSON, Enum as SQLEnum, UniqueConstraint, func
)
from sqlalchemy.orm import relationship

# Import Base from the db module
from db import Base

# Import enums from the database package
from database.enums import PermissionLevel, InviteStatus


# ============================================================================
# EMPLOYEE INVITES
# ============================================================================

class EmployeeInvite(Base):
    """Tracks employee invitation lifecycle. Links to user record once invite is accepted."""
    __tablename__ = "employee_invites"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), nullable=False, index=True)
    first_name = Column(String(100), nullable=False)
    last_name = Column(String(100), nullable=False)
    job_title = Column(String(100))
    permission_role = Column(String(50), nullable=False, default="sales")
    invite_token = Column(String(64), unique=True, nullable=True, index=True)
    status = Column(String(20), default="pending", nullable=False)
    created_at = Column(DateTime, server_default=func.now())
    expires_at = Column(DateTime, nullable=False)
    accepted_at = Column(DateTime)
    invited_by_user_id = Column(Integer, ForeignKey("users.id"))
    user_id = Column(Integer, ForeignKey("users.id"))
    branch_id = Column(Integer, ForeignKey("branches.id"))
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=True)
    initial_config = Column(JSON, default=dict)


# ============================================================================
# CRM PAGES & PERMISSIONS
# ============================================================================

class CRMPage(Base):
    """Defines navigable pages/features in the CRM for permission matrix."""
    __tablename__ = "crm_pages"

    id = Column(Integer, primary_key=True, index=True)
    key = Column(String(50), unique=True, nullable=False)
    label = Column(String(100), nullable=False)
    description = Column(Text)
    category = Column(String(50))
    icon = Column(String(50))
    route = Column(String(100))
    sort_order = Column(Integer, default=0)
    is_active = Column(Boolean, default=True)
    parent_id = Column(Integer, ForeignKey("crm_pages.id"))

    # Relationships
    children = relationship("CRMPage", backref="parent", remote_side="CRMPage.id")


class RolePagePermission(Base):
    """Default page permissions per role."""
    __tablename__ = "role_page_permissions"

    id = Column(Integer, primary_key=True, index=True)
    role = Column(String(50), nullable=False)
    page_id = Column(Integer, ForeignKey("crm_pages.id"), nullable=False)
    permission_level = Column(SQLEnum(PermissionLevel), default=PermissionLevel.NONE)

    # Relationships
    page = relationship("CRMPage")

    __table_args__ = (UniqueConstraint('role', 'page_id', name='uq_role_page'),)


class UserPagePermission(Base):
    """Per-user permission overrides. Only stores deviations from role defaults."""
    __tablename__ = "user_page_permissions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    page_id = Column(Integer, ForeignKey("crm_pages.id"), nullable=False)
    permission_level = Column(SQLEnum(PermissionLevel), nullable=False)

    # Relationships
    page = relationship("CRMPage")

    __table_args__ = (UniqueConstraint('user_id', 'page_id', name='uq_user_page'),)


class UserPermission(Base):
    """User-specific permissions"""
    __tablename__ = "user_permissions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    permission_key = Column(String(255), nullable=False)
    granted = Column(Boolean, default=False)
    granted_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    granted_at = Column(DateTime, nullable=True)
    expires_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        UniqueConstraint('user_id', 'permission_key', name='unique_user_permission'),
    )


class PermissionRequest(Base):
    """Permission requests from employees"""
    __tablename__ = "permission_requests"

    id = Column(Integer, primary_key=True, index=True)
    employee_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    permission_key = Column(String(255), nullable=False)
    justification = Column(Text, nullable=False)
    urgency = Column(SQLEnum('low', 'medium', 'high', name='urgency_enum'), default='medium')
    is_temporary = Column(Boolean, default=False)
    duration_days = Column(Integer, nullable=True)

    status = Column(SQLEnum('pending', 'approved', 'denied', 'more_info_needed', name='request_status_enum'), default='pending')
    manager_notes = Column(Text, nullable=True)
    decided_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    decided_at = Column(DateTime, nullable=True)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


# ============================================================================
# AI QUICK ACTIONS
# ============================================================================

class AIQuickAction(Base):
    """Defines available AI quick actions for the landing page. Role-gated."""
    __tablename__ = "ai_quick_actions"

    id = Column(Integer, primary_key=True, index=True)
    key = Column(String(50), unique=True, nullable=False)
    label = Column(String(100), nullable=False)
    subtitle = Column(String(200))
    description = Column(Text)
    icon = Column(String(50))
    primary_prompt = Column(Text)
    requires_chat = Column(Boolean, default=True)
    sort_order = Column(Integer, default=0)
    is_active = Column(Boolean, default=True)
    requires_page_id = Column(Integer, ForeignKey("crm_pages.id"))
    requires_permission_level = Column(SQLEnum(PermissionLevel), default=PermissionLevel.VIEW)

    # Relationships
    requires_page = relationship("CRMPage")


class AIQuickActionRole(Base):
    """Maps which roles can see which AI quick actions."""
    __tablename__ = "ai_quick_action_roles"

    id = Column(Integer, primary_key=True, index=True)
    ai_action_id = Column(Integer, ForeignKey("ai_quick_actions.id"), nullable=False)
    role = Column(String(50), nullable=False)

    # Relationships
    ai_action = relationship("AIQuickAction", backref="role_mappings")

    __table_args__ = (UniqueConstraint('ai_action_id', 'role', name='uq_quick_action_role'),)


# ============================================================================
# RESPONSIBILITIES
# ============================================================================

class Responsibility(Base):
    """Defines job responsibilities that can be assigned to users."""
    __tablename__ = "responsibilities"

    id = Column(Integer, primary_key=True, index=True)
    key = Column(String(50), unique=True, nullable=False)
    label = Column(String(100), nullable=False)
    description = Column(Text)
    category = Column(String(50))
    icon = Column(String(50))
    sort_order = Column(Integer, default=0)
    is_active = Column(Boolean, default=True)

    # Relationships (back_populates for mapper resolution)
    role_responsibilities = relationship("RoleResponsibility", back_populates="responsibility")
    user_responsibilities = relationship("UserResponsibility", back_populates="responsibility")


class Role(Base):
    """Canonical RBAC/team role (Loan Officer, Processor, etc.).

    Mapped to the existing `roles` table. This is the `Role` that
    workflow_sla.LeadWorkflowRoleAssignment.role (FK -> roles.id) resolves to.
    Schema mirrors the production `roles` table.
    """
    __tablename__ = "roles"
    __table_args__ = {'extend_existing': True}

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    code = Column(String, nullable=True)
    description = Column(Text, nullable=True)
    is_active = Column(Boolean, nullable=True, default=True)
    created_at = Column(DateTime(timezone=True), nullable=True, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=True, server_default=func.now(), onupdate=func.now())
    abbreviation = Column(String, nullable=True)


class RoleResponsibility(Base):
    """Default responsibilities assigned per role."""
    __tablename__ = "role_responsibilities"

    id = Column(Integer, primary_key=True, index=True)
    role = Column(String(50), nullable=False)
    responsibility_id = Column(Integer, ForeignKey("responsibilities.id"), nullable=False)

    # Relationships
    responsibility = relationship("Responsibility", back_populates="role_responsibilities")

    __table_args__ = (UniqueConstraint('role', 'responsibility_id', name='uq_role_responsibility'),)


class UserResponsibility(Base):
    """Actual responsibilities assigned to a user."""
    __tablename__ = "user_responsibilities"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    responsibility_id = Column(Integer, ForeignKey("responsibilities.id"), nullable=False)
    is_enabled = Column(Boolean, default=True)
    sla_config = Column(JSON, default=dict)

    # Relationships
    responsibility = relationship("Responsibility", back_populates="user_responsibilities")

    __table_args__ = (UniqueConstraint('user_id', 'responsibility_id', name='uq_user_responsibility'),)


# ============================================================================
# EXPORTS
# ============================================================================

__all__ = [
    # Employee Invites
    "EmployeeInvite",
    # CRM Pages
    "CRMPage",
    "RolePagePermission",
    "UserPagePermission",
    "UserPermission",
    "PermissionRequest",
    # AI Quick Actions
    "AIQuickAction",
    "AIQuickActionRole",
    # Responsibilities
    "Responsibility",
    "RoleResponsibility",
    "UserResponsibility",
]
