"""
User Onboarding Integration Module
This file provides SQLAlchemy models and FastAPI routes for the user onboarding system.
Import and initialize from main.py after the Base is created.
"""

from sqlalchemy import (
    Column, Integer, String, Text, Boolean, DateTime, ForeignKey,
    JSON, Float, Index, UniqueConstraint
)
from sqlalchemy.orm import relationship
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends, HTTPException, status, Request, UploadFile, File, Form
from pydantic import BaseModel, EmailStr, validator
from typing import List, Optional, Dict, Any
import secrets
import logging
import csv
import io
import re
import hmac

logger = logging.getLogger(__name__)


def create_user_onboarding_models(Base):
    """
    Create all user onboarding models using the provided Base class
    Returns a dictionary of model classes
    """

    class OnboardingRole(Base):
        """User roles for the onboarding system"""
        __tablename__ = "onboarding_roles"
        __table_args__ = {'extend_existing': True}

        id = Column(Integer, primary_key=True, index=True)
        name = Column(String(100), nullable=False, unique=True, index=True)
        description = Column(Text)
        default_permission_template_id = Column(Integer)
        is_active = Column(Boolean, default=True, nullable=False)
        created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
        updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    class OnboardingCategory(Base):
        """Categories of responsibilities"""
        __tablename__ = "onboarding_categories"
        __table_args__ = {'extend_existing': True}

        id = Column(Integer, primary_key=True, index=True)
        name = Column(String(100), nullable=False, unique=True, index=True)
        description = Column(Text)
        sort_order = Column(Integer, default=0, nullable=False)
        is_active = Column(Boolean, default=True, nullable=False)
        created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    class OnboardingResponsibility(Base):
        """Specific responsibilities that can be assigned"""
        __tablename__ = "onboarding_responsibilities"
        __table_args__ = {'extend_existing': True}

        id = Column(Integer, primary_key=True, index=True)
        name = Column(String(200), nullable=False, index=True)
        description = Column(Text)
        category_id = Column(Integer, ForeignKey("onboarding_categories.id"), nullable=False)
        applicable_role_ids = Column(JSON, default=list)
        kpi_mapping = Column(JSON)
        is_active = Column(Boolean, default=True, nullable=False)
        created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
        updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    class OnboardingPermissionTemplate(Base):
        """Permission templates for quick assignment"""
        __tablename__ = "onboarding_permission_templates"
        __table_args__ = {'extend_existing': True}

        id = Column(Integer, primary_key=True, index=True)
        name = Column(String(100), nullable=False, unique=True, index=True)
        description = Column(Text)
        permissions = Column(JSON, nullable=False, default=dict)
        is_system_template = Column(Boolean, default=False, nullable=False)
        created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
        updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
        created_by = Column(Integer, ForeignKey("users.id"))

    class OnboardingUserProfile(Base):
        """Extended user profile for onboarding"""
        __tablename__ = "onboarding_user_profiles"
        __table_args__ = {'extend_existing': True}

        id = Column(Integer, primary_key=True, index=True)
        user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False)
        first_name = Column(String(100))
        last_name = Column(String(100))
        internal_title = Column(String(150))
        profile_image_url = Column(Text)
        role_id = Column(Integer, ForeignKey("onboarding_roles.id"))
        permission_template_id = Column(Integer, ForeignKey("onboarding_permission_templates.id"))
        status = Column(String(50), default="pending_setup", nullable=False, index=True)
        activation_token = Column(String(255), unique=True, index=True)
        activation_token_expires_at = Column(DateTime)
        activated_at = Column(DateTime)
        created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
        updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
        created_by = Column(Integer, ForeignKey("users.id"))

    class OnboardingUserCategory(Base):
        """User-category assignments"""
        __tablename__ = "onboarding_user_categories"
        __table_args__ = (
            UniqueConstraint('user_profile_id', 'category_id', name='uix_onboarding_user_category'),
            {'extend_existing': True}
        )

        id = Column(Integer, primary_key=True, index=True)
        user_profile_id = Column(Integer, ForeignKey("onboarding_user_profiles.id", ondelete="CASCADE"), nullable=False)
        category_id = Column(Integer, ForeignKey("onboarding_categories.id", ondelete="CASCADE"), nullable=False)
        created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    class OnboardingUserResponsibility(Base):
        """User-responsibility assignments"""
        __tablename__ = "onboarding_user_responsibilities"
        __table_args__ = (
            UniqueConstraint('user_profile_id', 'responsibility_id', name='uix_onboarding_user_responsibility'),
            {'extend_existing': True}
        )

        id = Column(Integer, primary_key=True, index=True)
        user_profile_id = Column(Integer, ForeignKey("onboarding_user_profiles.id", ondelete="CASCADE"), nullable=False)
        responsibility_id = Column(Integer, ForeignKey("onboarding_responsibilities.id", ondelete="CASCADE"), nullable=False)
        created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    class OnboardingUserPermissions(Base):
        """User's actual permissions"""
        __tablename__ = "onboarding_user_permissions"
        __table_args__ = {'extend_existing': True}

        id = Column(Integer, primary_key=True, index=True)
        user_profile_id = Column(Integer, ForeignKey("onboarding_user_profiles.id", ondelete="CASCADE"), unique=True, nullable=False)
        permissions = Column(JSON, nullable=False, default=dict)
        source = Column(String(50), default="template", nullable=False)
        created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
        updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    class OnboardingKPIScorecard(Base):
        """Auto-generated KPI scorecards"""
        __tablename__ = "onboarding_kpi_scorecards"
        __table_args__ = {'extend_existing': True}

        id = Column(Integer, primary_key=True, index=True)
        user_profile_id = Column(Integer, ForeignKey("onboarding_user_profiles.id", ondelete="CASCADE"), unique=True, nullable=False)
        scorecard_config = Column(JSON, nullable=False, default=dict)
        created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
        updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    class OnboardingRoleDefaultCategory(Base):
        """Default categories for each role"""
        __tablename__ = "onboarding_role_default_categories"
        __table_args__ = (
            UniqueConstraint('role_id', 'category_id', name='uix_onboarding_role_default_category'),
            {'extend_existing': True}
        )

        id = Column(Integer, primary_key=True, index=True)
        role_id = Column(Integer, ForeignKey("onboarding_roles.id", ondelete="CASCADE"), nullable=False)
        category_id = Column(Integer, ForeignKey("onboarding_categories.id", ondelete="CASCADE"), nullable=False)
        created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    class OnboardingRoleDefaultResponsibility(Base):
        """Default responsibilities for each role"""
        __tablename__ = "onboarding_role_default_responsibilities"
        __table_args__ = (
            UniqueConstraint('role_id', 'responsibility_id', name='uix_onboarding_role_default_responsibility'),
            {'extend_existing': True}
        )

        id = Column(Integer, primary_key=True, index=True)
        role_id = Column(Integer, ForeignKey("onboarding_roles.id", ondelete="CASCADE"), nullable=False)
        responsibility_id = Column(Integer, ForeignKey("onboarding_responsibilities.id", ondelete="CASCADE"), nullable=False)
        created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    class OnboardingSession(Base):
        """Wizard session tracking"""
        __tablename__ = "onboarding_wizard_sessions"
        __table_args__ = {'extend_existing': True}

        id = Column(Integer, primary_key=True, index=True)
        session_token = Column(String(255), unique=True, index=True, nullable=False)
        user_id = Column(Integer, ForeignKey("users.id"))
        user_profile_id = Column(Integer, ForeignKey("onboarding_user_profiles.id"))
        created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
        current_step = Column(String(50), default="basic_info", nullable=False)
        basic_info_data = Column(JSON)
        role_builder_data = Column(JSON)
        permissions_data = Column(JSON)
        status = Column(String(50), default="in_progress", nullable=False)
        created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
        updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
        expires_at = Column(DateTime)
        completed_at = Column(DateTime)

    class OnboardingAuditLog(Base):
        """Audit trail"""
        __tablename__ = "onboarding_audit_log"
        __table_args__ = {'extend_existing': True}

        id = Column(Integer, primary_key=True, index=True)
        user_id = Column(Integer, ForeignKey("users.id"))
        action = Column(String(100), nullable=False, index=True)
        performed_by = Column(Integer, ForeignKey("users.id"), nullable=False)
        details = Column(JSON)
        ip_address = Column(String(45))
        created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False, index=True)

    return {
        'Role': OnboardingRole,
        'Category': OnboardingCategory,
        'Responsibility': OnboardingResponsibility,
        'PermissionTemplate': OnboardingPermissionTemplate,
        'UserProfile': OnboardingUserProfile,
        'UserCategory': OnboardingUserCategory,
        'UserResponsibility': OnboardingUserResponsibility,
        'UserPermissions': OnboardingUserPermissions,
        'KPIScorecard': OnboardingKPIScorecard,
        'RoleDefaultCategory': OnboardingRoleDefaultCategory,
        'RoleDefaultResponsibility': OnboardingRoleDefaultResponsibility,
        'OnboardingSession': OnboardingSession,
        'AuditLog': OnboardingAuditLog
    }


def seed_onboarding_data(db, models):
    """
    Seed the database with initial onboarding data
    """
    Role = models['Role']
    Category = models['Category']
    Responsibility = models['Responsibility']
    PermissionTemplate = models['PermissionTemplate']
    RoleDefaultCategory = models['RoleDefaultCategory']
    RoleDefaultResponsibility = models['RoleDefaultResponsibility']

    # Check if already seeded
    if db.query(Role).count() > 0:
        logger.info("Onboarding data already seeded, skipping...")
        return

    logger.info("Seeding user onboarding data...")

    # Create roles
    roles_data = [
        ("Application Analysis", "Analyzes and reviews loan applications for eligibility and risk"),
        ("Concierge", "Manages borrower communication, milestone updates, and partner engagement"),
        ("Jr. Loan Officer", "Assists with lead qualification and basic loan processing under supervision"),
        ("Jr. Processor", "Supports loan processing with document collection and condition tracking"),
        ("Loan Officer", "Originates loans, manages borrower relationships, and closes transactions"),
        ("Loan Officer Assistant", "Supports loan officers with administrative tasks and borrower communication"),
        ("Processing Assistant", "Assists processors with documentation and milestone tracking"),
        ("Processor", "Manages complete loan processing from application to clear-to-close"),
        ("Production Assistant 1", "Entry-level support for loan production operations"),
        ("Production Assistant 2", "Mid-level support for loan production with expanded responsibilities")
    ]

    roles = {}
    for name, desc in roles_data:
        role = Role(name=name, description=desc, is_active=True)
        db.add(role)
        db.flush()
        roles[name] = role

    # Create categories
    categories_data = [
        ("Lead Generation", "Activities related to generating and capturing new leads", 1),
        ("Borrower Engagement", "Direct communication and relationship management with borrowers", 2),
        ("Partner Engagement", "Managing relationships with referral partners and external stakeholders", 3),
        ("Application Review", "Initial review and analysis of loan applications", 4),
        ("Pre-Approval Workflow", "Pre-qualification and pre-approval processes", 5),
        ("Processing & Milestones", "Core loan processing tasks and milestone management", 6),
        ("Closing Coordination", "Final steps to close the loan transaction", 7),
        ("Post-Closing / MUM", "Post-closing activities and mortgage under management", 8),
        ("Referral Management", "Managing referral sources and tracking referral performance", 9),
        ("Rate Lock Support", "Rate lock advisory and market monitoring", 10)
    ]

    categories = {}
    for name, desc, order in categories_data:
        cat = Category(name=name, description=desc, sort_order=order, is_active=True)
        db.add(cat)
        db.flush()
        categories[name] = cat

    # Create responsibilities (simplified list)
    responsibilities_data = [
        ("Lead qualification", "Qualify inbound leads based on pre-defined criteria", "Lead Generation",
         {"daily_kpis": ["leads_contacted", "leads_qualified"]}),
        ("Outbound prospecting", "Proactive outreach to generate new leads", "Lead Generation",
         {"daily_kpis": ["outbound_calls_made"]}),
        ("Borrower milestone updates", "Communicate loan progress and milestones to borrowers", "Borrower Engagement",
         {"daily_kpis": ["milestone_updates_sent"]}),
        ("Application consultation", "Guide borrowers through the application process", "Borrower Engagement",
         {"weekly_kpis": ["consultations_completed"]}),
        ("Weekly partner updates", "Provide regular updates to referral partners", "Partner Engagement",
         {"weekly_kpis": ["partner_updates_sent"]}),
        ("Initial application review", "Review new applications for completeness", "Application Review",
         {"daily_kpis": ["applications_reviewed"]}),
        ("Credit analysis", "Analyze borrower credit profiles", "Application Review",
         {"daily_kpis": ["credit_analyses_completed"]}),
        ("Pre-qualification processing", "Process pre-qualification requests", "Pre-Approval Workflow",
         {"daily_kpis": ["prequalifications_issued"]}),
        ("Milestone tracking", "Track and update loan milestones", "Processing & Milestones",
         {"daily_kpis": ["milestones_updated"]}),
        ("Condition management", "Manage and clear loan conditions", "Processing & Milestones",
         {"daily_kpis": ["conditions_cleared"]}),
        ("Closing documentation preparation", "Prepare final closing documents", "Closing Coordination",
         {"weekly_kpis": ["closing_docs_prepared"]}),
        ("Post-close check-ins", "Follow up with borrowers after closing", "Post-Closing / MUM",
         {"monthly_kpis": ["post_close_contacts"]}),
        ("MUM annual reviews", "Conduct annual mortgage reviews", "Post-Closing / MUM",
         {"monthly_kpis": ["annual_reviews_completed"]}),
        ("Referral tracking", "Track and manage referral sources", "Referral Management",
         {"monthly_kpis": ["referrals_tracked"]}),
        ("Rate monitoring", "Monitor market rates and advise borrowers", "Rate Lock Support",
         {"daily_kpis": ["rate_alerts_sent"]})
    ]

    responsibilities = {}
    for name, desc, cat_name, kpi_map in responsibilities_data:
        resp = Responsibility(
            name=name,
            description=desc,
            category_id=categories[cat_name].id,
            kpi_mapping=kpi_map,
            is_active=True
        )
        db.add(resp)
        db.flush()
        responsibilities[name] = resp

    # Create permission templates
    templates_data = [
        {
            "name": "Loan Officer - Full Access",
            "description": "Complete access to leads, loans, and borrower communication",
            "is_system_template": True,
            "permissions": {
                "leads": {"view": True, "edit": True, "reassign": True, "delete": False, "import": True},
                "active_loans": {"view_assigned": True, "view_all_branch": True, "update_borrower_info": True, "approve_tasks": True, "update_milestones": True, "add_docs_messages": True},
                "mum": {"view": True, "execute_annual_reviews": True, "trigger_ai_followups": True, "manage_refi_alerts": True},
                "communication_ai": {"click_to_dial": True, "teams_texting": True, "view_ai_call_summaries": True, "view_email_intelligence": True, "access_borrower_sentiment": True},
                "referral_partners": {"view": True, "edit": True, "assign_leads": True, "view_analytics": True},
                "scorecards_reporting": {"view_own": True, "view_team": True, "view_company": True, "export_data": True},
                "admin": {"manage_users": False, "modify_permissions": False, "configure_ai_settings": False, "company_level_settings": False, "configure_rate_lock": False}
            }
        },
        {
            "name": "Processor - Standard",
            "description": "Standard processor permissions for assigned loans",
            "is_system_template": True,
            "permissions": {
                "leads": {"view": True, "edit": False, "reassign": False, "delete": False, "import": False},
                "active_loans": {"view_assigned": True, "view_all_branch": False, "update_borrower_info": True, "approve_tasks": False, "update_milestones": True, "add_docs_messages": True},
                "mum": {"view": True, "execute_annual_reviews": False, "trigger_ai_followups": False, "manage_refi_alerts": False},
                "communication_ai": {"click_to_dial": True, "teams_texting": True, "view_ai_call_summaries": True, "view_email_intelligence": True, "access_borrower_sentiment": False},
                "referral_partners": {"view": True, "edit": False, "assign_leads": False, "view_analytics": False},
                "scorecards_reporting": {"view_own": True, "view_team": False, "view_company": False, "export_data": False},
                "admin": {"manage_users": False, "modify_permissions": False, "configure_ai_settings": False, "company_level_settings": False, "configure_rate_lock": False}
            }
        },
        {
            "name": "Junior Staff - Limited",
            "description": "Limited permissions for junior staff members",
            "is_system_template": True,
            "permissions": {
                "leads": {"view": True, "edit": False, "reassign": False, "delete": False, "import": False},
                "active_loans": {"view_assigned": True, "view_all_branch": False, "update_borrower_info": False, "approve_tasks": False, "update_milestones": False, "add_docs_messages": True},
                "mum": {"view": True, "execute_annual_reviews": False, "trigger_ai_followups": False, "manage_refi_alerts": False},
                "communication_ai": {"click_to_dial": True, "teams_texting": True, "view_ai_call_summaries": False, "view_email_intelligence": False, "access_borrower_sentiment": False},
                "referral_partners": {"view": True, "edit": False, "assign_leads": False, "view_analytics": False},
                "scorecards_reporting": {"view_own": True, "view_team": False, "view_company": False, "export_data": False},
                "admin": {"manage_users": False, "modify_permissions": False, "configure_ai_settings": False, "company_level_settings": False, "configure_rate_lock": False}
            }
        },
        {
            "name": "Admin - Full Control",
            "description": "Full administrative access to all system features",
            "is_system_template": True,
            "permissions": {
                "leads": {"view": True, "edit": True, "reassign": True, "delete": True, "import": True},
                "active_loans": {"view_assigned": True, "view_all_branch": True, "update_borrower_info": True, "approve_tasks": True, "update_milestones": True, "add_docs_messages": True},
                "mum": {"view": True, "execute_annual_reviews": True, "trigger_ai_followups": True, "manage_refi_alerts": True},
                "communication_ai": {"click_to_dial": True, "teams_texting": True, "view_ai_call_summaries": True, "view_email_intelligence": True, "access_borrower_sentiment": True},
                "referral_partners": {"view": True, "edit": True, "assign_leads": True, "view_analytics": True},
                "scorecards_reporting": {"view_own": True, "view_team": True, "view_company": True, "export_data": True},
                "admin": {"manage_users": True, "modify_permissions": True, "configure_ai_settings": True, "company_level_settings": True, "configure_rate_lock": True}
            }
        }
    ]

    templates = {}
    for t_data in templates_data:
        template = PermissionTemplate(
            name=t_data["name"],
            description=t_data["description"],
            permissions=t_data["permissions"],
            is_system_template=t_data["is_system_template"]
        )
        db.add(template)
        db.flush()
        templates[t_data["name"]] = template

    # Set default templates for roles
    roles["Loan Officer"].default_permission_template_id = templates["Loan Officer - Full Access"].id
    roles["Processor"].default_permission_template_id = templates["Processor - Standard"].id
    roles["Jr. Loan Officer"].default_permission_template_id = templates["Junior Staff - Limited"].id
    roles["Jr. Processor"].default_permission_template_id = templates["Junior Staff - Limited"].id

    db.commit()
    logger.info("✅ User onboarding seed data created successfully!")


def create_onboarding_router(get_db, get_current_user, User, models, pwd_context, create_access_token):
    """
    Create FastAPI router with all user creation endpoints
    """
    router = APIRouter(prefix="/api/v1/admin/users", tags=["User Creation & Onboarding"])

    # Permission check helper - allow admin, leadership, managers, and sales to access user management
    # Note: In production, you'd restrict this more - for demo purposes we allow broader access
    ALLOWED_PERMISSION_ROLES = ['admin', 'site_admin', 'leadership', 'management', 'sales']  # Phase 2 permission_role values
    ALLOWED_LEGACY_ROLES = ['admin', 'manager', 'loan_officer']  # Legacy role values

    def check_admin_permission(user):
        """Check if user has admin-level permissions for user management"""
        # Check Phase 2 permission_role first
        permission_role = getattr(user, 'permission_role', None)
        if permission_role and permission_role in ALLOWED_PERMISSION_ROLES:
            return True
        # Fallback to legacy role
        legacy_role = getattr(user, 'role', None)
        if legacy_role and legacy_role in ALLOWED_LEGACY_ROLES:
            return True
        return False

    Role = models['Role']
    Category = models['Category']
    Responsibility = models['Responsibility']
    PermissionTemplate = models['PermissionTemplate']
    UserProfile = models['UserProfile']
    UserCategory = models['UserCategory']
    UserResponsibility = models['UserResponsibility']
    UserPermissions = models['UserPermissions']
    KPIScorecard = models['KPIScorecard']
    RoleDefaultCategory = models['RoleDefaultCategory']
    RoleDefaultResponsibility = models['RoleDefaultResponsibility']
    OnboardingSession = models['OnboardingSession']
    AuditLog = models['AuditLog']

    # Pydantic schemas
    class BasicInfoRequest(BaseModel):
        first_name: str
        last_name: str
        email: EmailStr
        phone: Optional[str] = None
        internal_title: Optional[str] = None

    class RoleBuilderRequest(BaseModel):
        user_id: int
        onboarding_session_id: int
        role_id: int
        category_ids: List[int]
        responsibility_ids: List[int]

    class PermissionsBuilderRequest(BaseModel):
        user_id: int
        onboarding_session_id: int
        permission_source: str
        permission_template_id: Optional[int] = None
        custom_permissions: Optional[Dict[str, Any]] = None

    class FinalizeUserRequest(BaseModel):
        user_id: int
        onboarding_session_id: int

    class ResponsibilityFilterRequest(BaseModel):
        category_ids: List[int]
        role_id: Optional[int] = None

    class ActivatePasswordRequest(BaseModel):
        activation_token: str
        password: str
        password_confirmation: str

    class UnifiedCreateUserRequest(BaseModel):
        """Unified request for creating a user in one step"""
        first_name: str
        last_name: str
        email: EmailStr
        phone: Optional[str] = None
        internal_title: Optional[str] = None
        role_id: int
        category_ids: List[int] = []
        responsibility_ids: List[int] = []
        permission_template_id: Optional[int] = None
        custom_permissions: Optional[Dict[str, Any]] = None
        send_activation_email: bool = True

    # Helper functions
    def generate_activation_token():
        return secrets.token_urlsafe(32)

    def generate_permission_summary(permissions):
        if not permissions:
            return "No permissions configured"
        parts = []
        leads = permissions.get('leads', {})
        if leads.get('view') and leads.get('edit'):
            parts.append("Can view and edit leads")
        loans = permissions.get('active_loans', {})
        if loans.get('view_all_branch'):
            parts.append("can view all branch loans")
        admin = permissions.get('admin', {})
        if not admin.get('manage_users'):
            parts.append("no admin access")
        return "; ".join(parts) if parts else "Standard permissions"

    def generate_kpi_scorecard_config(responsibility_ids, db):
        config = {
            "daily_kpis": [], "weekly_kpis": [], "monthly_kpis": [],
            "efficiency_scores": [], "communication_scores": [],
            "referral_scores": [], "mum_engagement_scores": []
        }
        resps = db.query(Responsibility).filter(Responsibility.id.in_(responsibility_ids)).all()
        seen = set()
        for resp in resps:
            if resp.kpi_mapping:
                for kpi_type in config.keys():
                    if kpi_type in resp.kpi_mapping:
                        for kpi_id in resp.kpi_mapping[kpi_type]:
                            if kpi_id not in seen:
                                config[kpi_type].append({"id": kpi_id, "name": kpi_id.replace("_", " ").title()})
                                seen.add(kpi_id)
        return config

    # Endpoints
    @router.post("/create")
    async def create_user_unified(
        data: UnifiedCreateUserRequest,
        request: Request,
        db = Depends(get_db),
        current_user = Depends(get_current_user)
    ):
        """Create a new user with all settings in one request"""
        if not check_admin_permission(current_user):
            raise HTTPException(status_code=403, detail="Permission denied")

        # Check if email already exists
        existing = db.query(User).filter(User.email == data.email).first()
        if existing:
            raise HTTPException(status_code=400, detail="Email already exists")

        # Get role info
        role = db.query(Role).filter(Role.id == data.role_id).first()
        if not role:
            raise HTTPException(status_code=400, detail="Invalid role_id")

        try:
            # Create user
            new_user = User(
                email=data.email,
                hashed_password="",  # Will be set during activation
                first_name=data.first_name,
                last_name=data.last_name,
                phone=data.phone,
                role=role.name.lower().replace(" ", "_"),
                permission_role="pending",
                is_active=False
            )
            db.add(new_user)
            db.flush()

            # Create user profile
            profile = UserProfile(
                user_id=new_user.id,
                first_name=data.first_name,
                last_name=data.last_name,
                internal_title=data.internal_title or role.name,
                role_id=data.role_id,
                status="pending_activation",
                created_by=current_user.id
            )
            db.add(profile)
            db.flush()

            # Add categories
            for cat_id in data.category_ids:
                db.add(UserCategory(user_profile_id=profile.id, category_id=cat_id))

            # Add responsibilities
            for resp_id in data.responsibility_ids:
                db.add(UserResponsibility(user_profile_id=profile.id, responsibility_id=resp_id))

            # Handle permissions
            permissions_data = {}
            permission_source = "custom"
            if data.permission_template_id:
                template = db.query(PermissionTemplate).filter(PermissionTemplate.id == data.permission_template_id).first()
                if template:
                    permissions_data = template.permissions or {}
                    permission_source = "template"
            elif data.custom_permissions:
                permissions_data = data.custom_permissions

            user_perms = UserPermissions(
                user_profile_id=profile.id,
                permissions=permissions_data,
                source=permission_source
            )
            db.add(user_perms)

            # Create KPI scorecard
            scorecard_config = generate_kpi_scorecard_config(data.responsibility_ids, db)
            scorecard = KPIScorecard(
                user_profile_id=profile.id,
                scorecard_config=scorecard_config
            )
            db.add(scorecard)

            # Generate activation token
            activation_token = generate_activation_token()
            profile.activation_token = activation_token
            profile.activation_token_expires = datetime.now(timezone.utc) + timedelta(days=7)

            # Create audit log
            audit = AuditLog(
                user_id=new_user.id,
                action="user_created_unified",
                performed_by=current_user.id,
                details={
                    "email": data.email,
                    "role_id": data.role_id,
                    "category_ids": data.category_ids,
                    "responsibility_ids": data.responsibility_ids
                },
                ip_address=request.client.host if request.client else None
            )
            db.add(audit)

            db.commit()

            # Build scorecard response
            scorecard_response = {
                "id": scorecard.id,
                "kpi_config": scorecard_config,
                "summary": f"Scorecard configured with {len(data.responsibility_ids)} responsibilities"
            }

            return {
                "success": True,
                "user_id": new_user.id,
                "user_profile_id": profile.id,
                "email": data.email,
                "full_name": f"{data.first_name} {data.last_name}",
                "role": role.name,
                "scorecard": scorecard_response,
                "activation_token": activation_token,
                "message": f"User created successfully. Activation email {'will be sent' if data.send_activation_email else 'not sent'}."
            }

        except Exception as e:
            db.rollback()
            raise HTTPException(status_code=500, detail="Error creating user")

    @router.post("/create/single")
    async def create_single_user(
        data: BasicInfoRequest,
        request: Request,
        db = Depends(get_db),
        current_user = Depends(get_current_user)
    ):
        """Create a new user - Step 1: Basic Information"""
        if not check_admin_permission(current_user):
            raise HTTPException(status_code=403, detail="Permission denied")

        existing = db.query(User).filter(User.email == data.email).first()
        if existing:
            raise HTTPException(status_code=400, detail="Email already exists")

        try:
            new_user = User(
                email=data.email,
                hashed_password="",
                first_name=data.first_name,
                last_name=data.last_name,
                phone=data.phone,
                role="pending",
                permission_role="pending",
                is_active=False
            )
            db.add(new_user)
            db.flush()

            profile = UserProfile(
                user_id=new_user.id,
                first_name=data.first_name,
                last_name=data.last_name,
                internal_title=data.internal_title,
                status="pending_setup",
                created_by=current_user.id
            )
            db.add(profile)
            db.flush()

            session = OnboardingSession(
                session_token=secrets.token_urlsafe(32),
                user_id=new_user.id,
                user_profile_id=profile.id,
                created_by=current_user.id,
                current_step="basic_info",
                status="in_progress",
                basic_info_data=data.dict(),
                expires_at=datetime.now(timezone.utc) + timedelta(hours=24)
            )
            db.add(session)
            db.flush()

            audit = AuditLog(
                user_id=new_user.id,
                action="user_created",
                performed_by=current_user.id,
                details={"step": "basic_info", "email": data.email},
                ip_address=request.client.host if request.client else None
            )
            db.add(audit)
            db.commit()

            return {
                "success": True,
                "data": {
                    "user_id": new_user.id,
                    "user_profile_id": profile.id,
                    "onboarding_session_id": session.id,
                    "status": "pending_setup",
                    "next_step": "role_builder"
                }
            }
        except Exception as e:
            db.rollback()
            raise HTTPException(status_code=500, detail="Internal server error")

    @router.post("/create/single/role-builder")
    async def save_role_builder(
        data: RoleBuilderRequest,
        db = Depends(get_db),
        current_user = Depends(get_current_user)
    ):
        """Save role configuration - Step 2"""
        if not check_admin_permission(current_user):
            raise HTTPException(status_code=403, detail="Permission denied")

        session = db.query(OnboardingSession).filter(
            OnboardingSession.id == data.onboarding_session_id,
            OnboardingSession.user_id == data.user_id
        ).first()
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")

        profile = db.query(UserProfile).filter(UserProfile.user_id == data.user_id).first()
        if not profile:
            raise HTTPException(status_code=404, detail="Profile not found")

        role = db.query(Role).filter(Role.id == data.role_id).first()
        if not role:
            raise HTTPException(status_code=400, detail="Invalid role")

        try:
            profile.role_id = data.role_id

            db.query(UserCategory).filter(UserCategory.user_profile_id == profile.id).delete()
            db.query(UserResponsibility).filter(UserResponsibility.user_profile_id == profile.id).delete()

            for cat_id in data.category_ids:
                db.add(UserCategory(user_profile_id=profile.id, category_id=cat_id))

            for resp_id in data.responsibility_ids:
                db.add(UserResponsibility(user_profile_id=profile.id, responsibility_id=resp_id))

            session.role_builder_data = {
                "role_id": data.role_id,
                "category_ids": data.category_ids,
                "responsibility_ids": data.responsibility_ids
            }
            session.current_step = "role_builder"
            db.commit()

            resps = db.query(Responsibility).filter(Responsibility.id.in_(data.responsibility_ids)).all()
            resp_names = [r.name for r in resps[:3]]
            summary = f"This user will be a {role.name} with responsibilities: {', '.join(resp_names)}..."

            return {"success": True, "data": {"user_id": data.user_id, "role_summary": summary, "next_step": "permissions_builder"}}
        except Exception as e:
            db.rollback()
            raise HTTPException(status_code=500, detail="Internal server error")

    @router.post("/create/single/permissions-builder")
    async def save_permissions(
        data: PermissionsBuilderRequest,
        db = Depends(get_db),
        current_user = Depends(get_current_user)
    ):
        """Save permissions - Step 3"""
        if not check_admin_permission(current_user):
            raise HTTPException(status_code=403, detail="Permission denied")

        session = db.query(OnboardingSession).filter(
            OnboardingSession.id == data.onboarding_session_id,
            OnboardingSession.user_id == data.user_id
        ).first()
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")

        profile = db.query(UserProfile).filter(UserProfile.user_id == data.user_id).first()
        if not profile:
            raise HTTPException(status_code=404, detail="Profile not found")

        try:
            if data.permission_source == "template" and data.permission_template_id:
                template = db.query(PermissionTemplate).filter(PermissionTemplate.id == data.permission_template_id).first()
                if not template:
                    raise HTTPException(status_code=400, detail="Invalid template")
                profile.permission_template_id = data.permission_template_id
                perms_data = template.permissions
            else:
                perms_data = data.custom_permissions or {}

            existing = db.query(UserPermissions).filter(UserPermissions.user_profile_id == profile.id).first()
            if existing:
                existing.permissions = perms_data
                existing.source = data.permission_source
            else:
                db.add(UserPermissions(user_profile_id=profile.id, permissions=perms_data, source=data.permission_source))

            session.permissions_data = data.dict()
            session.current_step = "permissions_builder"
            db.commit()

            return {"success": True, "data": {"user_id": data.user_id, "permission_summary": generate_permission_summary(perms_data), "next_step": "review_confirm"}}
        except Exception as e:
            db.rollback()
            raise HTTPException(status_code=500, detail="Internal server error")

    @router.get("/create/single/review/{user_id}")
    async def get_review_summary(
        user_id: int,
        db = Depends(get_db),
        current_user = Depends(get_current_user)
    ):
        """Get review summary - Step 4"""
        if not check_admin_permission(current_user):
            raise HTTPException(status_code=403, detail="Permission denied")

        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        profile = db.query(UserProfile).filter(UserProfile.user_id == user_id).first()
        if not profile:
            raise HTTPException(status_code=404, detail="Profile not found")

        role = db.query(Role).filter(Role.id == profile.role_id).first()

        user_cats = db.query(UserCategory).filter(UserCategory.user_profile_id == profile.id).all()
        categories = []
        for uc in user_cats:
            cat = db.query(Category).filter(Category.id == uc.category_id).first()
            if cat:
                categories.append({"id": cat.id, "name": cat.name})

        user_resps = db.query(UserResponsibility).filter(UserResponsibility.user_profile_id == profile.id).all()
        responsibilities = []
        for ur in user_resps:
            resp = db.query(Responsibility).filter(Responsibility.id == ur.responsibility_id).first()
            if resp:
                cat = db.query(Category).filter(Category.id == resp.category_id).first()
                responsibilities.append({"id": resp.id, "name": resp.name, "category_name": cat.name if cat else ""})

        user_perms = db.query(UserPermissions).filter(UserPermissions.user_profile_id == profile.id).first()
        template_name = "Custom"
        if profile.permission_template_id:
            template = db.query(PermissionTemplate).filter(PermissionTemplate.id == profile.permission_template_id).first()
            if template:
                template_name = template.name

        return {
            "success": True,
            "data": {
                "user": {"id": user.id, "first_name": profile.first_name, "last_name": profile.last_name, "email": user.email, "phone": user.phone, "internal_title": profile.internal_title},
                "role": {"id": role.id if role else None, "name": role.name if role else "Not assigned"},
                "categories": categories,
                "responsibilities": responsibilities,
                "permissions": {"template_name": template_name, "source": user_perms.source if user_perms else "none", "summary": generate_permission_summary(user_perms.permissions if user_perms else {})},
                "scorecard_preview": {"daily_kpis": [], "weekly_kpis": [], "monthly_kpis": []}
            }
        }

    @router.post("/create/single/finalize")
    async def finalize_user(
        data: FinalizeUserRequest,
        request: Request,
        db = Depends(get_db),
        current_user = Depends(get_current_user)
    ):
        """Finalize user creation - Final Step"""
        if not check_admin_permission(current_user):
            raise HTTPException(status_code=403, detail="Permission denied")

        session = db.query(OnboardingSession).filter(
            OnboardingSession.id == data.onboarding_session_id,
            OnboardingSession.user_id == data.user_id
        ).first()
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")

        user = db.query(User).filter(User.id == data.user_id).first()
        profile = db.query(UserProfile).filter(UserProfile.user_id == data.user_id).first()
        if not user or not profile:
            raise HTTPException(status_code=404, detail="User not found")

        try:
            user_resps = db.query(UserResponsibility).filter(UserResponsibility.user_profile_id == profile.id).all()
            resp_ids = [ur.responsibility_id for ur in user_resps]

            scorecard_config = generate_kpi_scorecard_config(resp_ids, db)
            scorecard = KPIScorecard(user_profile_id=profile.id, scorecard_config=scorecard_config)
            db.add(scorecard)

            token = generate_activation_token()
            profile.activation_token = token
            profile.activation_token_expires_at = datetime.now(timezone.utc) + timedelta(days=7)
            profile.status = "active_awaiting_setup"

            session.status = "completed"
            session.completed_at = datetime.now(timezone.utc)

            audit = AuditLog(
                user_id=user.id,
                action="user_finalized",
                performed_by=current_user.id,
                details={"scorecard_generated": True},
                ip_address=request.client.host if request.client else None
            )
            db.add(audit)
            db.commit()

            # Send activation email
            email_sent = False
            try:
                from email_service import email_service
                user_full_name = f"{profile.first_name} {profile.last_name}"
                email_sent = email_service.send_activation_email(
                    to_email=user.email,
                    user_name=user_full_name,
                    activation_token=token
                )
            except Exception as email_err:
                import logging
                logging.warning(f"Failed to send activation email: {email_err}")

            return {
                "success": True,
                "data": {
                    "user_id": user.id,
                    "email": user.email,
                    "status": "active_awaiting_setup",
                    "scorecard_id": scorecard.id,
                    "activation_email_sent": email_sent,
                    "activation_token": token if not email_sent else None,  # Return token if email failed
                    "activation_token_expires_at": profile.activation_token_expires_at.isoformat()
                }
            }
        except Exception as e:
            db.rollback()
            raise HTTPException(status_code=500, detail="Internal server error")

    @router.post("/users/{user_id}/resend-activation")
    async def resend_activation_email(
        user_id: int,
        db = Depends(get_db),
        current_user = Depends(get_current_user)
    ):
        """Resend activation email for a pending user"""
        if not check_admin_permission(current_user):
            raise HTTPException(status_code=403, detail="Permission denied")

        user = db.query(User).filter(User.id == user_id).first()
        profile = db.query(UserProfile).filter(UserProfile.user_id == user_id).first()

        if not user or not profile:
            raise HTTPException(status_code=404, detail="User not found")

        if profile.status not in ['pending_setup', 'active_awaiting_setup']:
            raise HTTPException(status_code=400, detail="User has already activated their account")

        # Generate new token
        token = generate_activation_token()
        profile.activation_token = token
        profile.activation_token_expires_at = datetime.now(timezone.utc) + timedelta(days=7)
        db.commit()

        # Send activation email
        email_sent = False
        try:
            from email_service import email_service
            user_full_name = f"{profile.first_name} {profile.last_name}"
            email_sent = email_service.send_activation_email(
                to_email=user.email,
                user_name=user_full_name,
                activation_token=token
            )
        except Exception as email_err:
            import logging
            logging.warning(f"Failed to send activation email: {email_err}")

        return {
            "success": True,
            "data": {
                "user_id": user.id,
                "email": user.email,
                "activation_email_sent": email_sent,
                "activation_token": token if not email_sent else None,
                "activation_token_expires_at": profile.activation_token_expires_at.isoformat()
            }
        }

    # Public activation endpoints (no auth required)
    @router.post("/activate/validate")
    async def validate_activation_token(
        data: dict,
        db = Depends(get_db)
    ):
        """Validate an activation token and return user info"""
        token = data.get('token')
        if not token:
            raise HTTPException(status_code=400, detail="Token is required")

        # First try UserProfile (onboarding system)
        profile = db.query(UserProfile).filter(UserProfile.activation_token == token).first()
        if profile:
            if profile.activation_token_expires_at and profile.activation_token_expires_at < datetime.now(timezone.utc):
                raise HTTPException(status_code=400, detail="Activation token has expired. Please contact your administrator for a new link.")

            if profile.status == 'active':
                raise HTTPException(status_code=400, detail="Account has already been activated")

            user = db.query(User).filter(User.id == profile.user_id).first()

            return {
                "success": True,
                "data": {
                    "user_id": user.id,
                    "email": user.email,
                    "first_name": profile.first_name,
                    "last_name": profile.last_name,
                    "source": "onboarding"
                }
            }

        # Try invitation system (token stored in user_metadata JSON)
        # Use raw SQL to avoid ORM issues with missing columns
        from sqlalchemy import text
        try:
            # Query users with matching invitation token using raw SQL
            result = db.execute(text("""
                SELECT id, email, full_name, is_active, hashed_password, user_metadata
                FROM users
                WHERE user_metadata IS NOT NULL
            """))
            users_data = result.fetchall()

            for row in users_data:
                user_id, email, full_name, is_active, hashed_password, user_metadata = row

                # Parse user_metadata - it might be a string or dict
                if isinstance(user_metadata, str):
                    import json
                    try:
                        user_metadata = json.loads(user_metadata)
                    except Exception as e:
                        logger.exception(f"Failed to parse user_metadata JSON for user_id={user_id}: {e}")
                        continue

                if user_metadata and hmac.compare_digest(user_metadata.get("invitation_token") or "", token):
                    # Check expiration
                    expires_at_str = user_metadata.get("invitation_expires_at")
                    if expires_at_str:
                        expires_at = datetime.fromisoformat(expires_at_str.replace('Z', '+00:00'))
                        if expires_at < datetime.now(timezone.utc):
                            raise HTTPException(status_code=400, detail="Activation token has expired. Please contact your administrator for a new link.")

                    # Check if already activated
                    if is_active and hashed_password and hashed_password != "":
                        raise HTTPException(status_code=400, detail="Account has already been activated")

                    # Parse name
                    first_name = ""
                    last_name = ""
                    if full_name:
                        parts = full_name.split(" ", 1)
                        first_name = parts[0]
                        last_name = parts[1] if len(parts) > 1 else ""

                    return {
                        "success": True,
                        "data": {
                            "user_id": user_id,
                            "email": email,
                            "first_name": first_name,
                            "last_name": last_name,
                            "source": "invitation"
                        }
                    }
        except Exception as e:
            logger.warning(f"Error querying invitation tokens: {e}")

        raise HTTPException(status_code=404, detail="Invalid activation token")

    @router.post("/activate/complete")
    async def complete_activation(
        data: dict,
        db = Depends(get_db)
    ):
        """Complete activation by setting password"""
        token = data.get('token')
        password = data.get('password')

        if not token or not password:
            raise HTTPException(status_code=400, detail="Token and password are required")

        if len(password) < 8:
            raise HTTPException(status_code=400, detail="Password must be at least 8 characters")

        # First try UserProfile (onboarding system)
        profile = db.query(UserProfile).filter(UserProfile.activation_token == token).first()
        if profile:
            if profile.activation_token_expires_at and profile.activation_token_expires_at < datetime.now(timezone.utc):
                raise HTTPException(status_code=400, detail="Activation token has expired")

            if profile.status == 'active':
                raise HTTPException(status_code=400, detail="Account has already been activated")

            user = db.query(User).filter(User.id == profile.user_id).first()
            if not user:
                raise HTTPException(status_code=404, detail="User not found")

            try:
                # Update user password
                user.hashed_password = pwd_context.hash(password)

                # Update profile status
                profile.status = 'active'
                profile.activation_token = None
                profile.activation_token_expires_at = None
                profile.activated_at = datetime.now(timezone.utc)

                # Create audit log
                audit = AuditLog(
                    user_id=user.id,
                    action="account_activated",
                    performed_by=user.id,
                    details={"activated_via": "email_token", "source": "onboarding"}
                )
                db.add(audit)
                db.commit()

                return {
                    "success": True,
                    "data": {
                        "user_id": user.id,
                        "email": user.email,
                        "status": "active",
                        "message": "Account activated successfully. You can now log in."
                    }
                }
            except Exception as e:
                db.rollback()
                raise HTTPException(status_code=500, detail="Internal server error")

        # Try invitation system (token stored in user_metadata JSON)
        # Use raw SQL to avoid ORM issues with missing columns
        from sqlalchemy import text
        try:
            result = db.execute(text("""
                SELECT id, email, full_name, is_active, hashed_password, user_metadata
                FROM users
                WHERE user_metadata IS NOT NULL
            """))
            users_data = result.fetchall()

            for row in users_data:
                user_id, email, full_name, is_active, hashed_password, user_metadata_raw = row

                # Parse user_metadata - it might be a string or dict
                if isinstance(user_metadata_raw, str):
                    import json
                    try:
                        user_metadata = json.loads(user_metadata_raw)
                    except Exception as e:
                        logger.exception(f"Failed to parse user_metadata JSON for user_id={user_id}: {e}")
                        continue
                else:
                    user_metadata = user_metadata_raw

                if user_metadata and hmac.compare_digest(user_metadata.get("invitation_token") or "", token):
                    # Check expiration
                    expires_at_str = user_metadata.get("invitation_expires_at")
                    if expires_at_str:
                        expires_at = datetime.fromisoformat(expires_at_str.replace('Z', '+00:00'))
                        if expires_at < datetime.now(timezone.utc):
                            raise HTTPException(status_code=400, detail="Activation token has expired")

                    # Check if already activated
                    if is_active and hashed_password and hashed_password != "":
                        raise HTTPException(status_code=400, detail="Account has already been activated")

                    try:
                        # Update user password and activate using raw SQL
                        import json
                        hashed_pw = pwd_context.hash(password)

                        # Update user_metadata
                        metadata = user_metadata.copy() if user_metadata else {}
                        metadata["status"] = "active"
                        metadata["activated_at"] = datetime.now(timezone.utc).isoformat()
                        metadata["invitation_token"] = None  # Clear token

                        db.execute(text("""
                            UPDATE users
                            SET hashed_password = :hashed_password,
                                is_active = :is_active,
                                user_metadata = :user_metadata
                            WHERE id = :user_id
                        """), {
                            "hashed_password": hashed_pw,
                            "is_active": True,
                            "user_metadata": json.dumps(metadata),
                            "user_id": user_id
                        })

                        # Create audit log
                        audit = AuditLog(
                            user_id=user_id,
                            action="account_activated",
                            performed_by=user_id,
                            details={"activated_via": "email_token", "source": "invitation"}
                        )
                        db.add(audit)
                        db.commit()

                        return {
                            "success": True,
                            "data": {
                                "user_id": user_id,
                                "email": email,
                                "status": "active",
                                "message": "Account activated successfully. You can now log in."
                            }
                        }
                    except Exception as e:
                        db.rollback()
                        raise HTTPException(status_code=500, detail="Internal server error")
        except HTTPException:
            raise
        except Exception as e:
            logger.warning(f"Error querying invitation tokens for completion: {e}")

        raise HTTPException(status_code=404, detail="Invalid activation token")

    # Reference data endpoints
    @router.get("/roles")
    async def list_roles(db = Depends(get_db), current_user = Depends(get_current_user)):
        if not check_admin_permission(current_user):
            raise HTTPException(status_code=403, detail="Permission denied")
        roles = db.query(Role).filter(Role.is_active == True).order_by(Role.name).all()
        return {"success": True, "data": {"roles": [{"id": r.id, "name": r.name, "description": r.description} for r in roles]}}

    @router.get("/roles/{role_id}/defaults")
    async def get_role_defaults(role_id: int, db = Depends(get_db), current_user = Depends(get_current_user)):
        if not check_admin_permission(current_user):
            raise HTTPException(status_code=403, detail="Permission denied")
        role = db.query(Role).filter(Role.id == role_id).first()
        if not role:
            raise HTTPException(status_code=404, detail="Role not found")

        default_cats = db.query(RoleDefaultCategory).filter(RoleDefaultCategory.role_id == role_id).all()
        categories = []
        for dc in default_cats:
            cat = db.query(Category).filter(Category.id == dc.category_id).first()
            if cat:
                categories.append({"id": cat.id, "name": cat.name})

        default_resps = db.query(RoleDefaultResponsibility).filter(RoleDefaultResponsibility.role_id == role_id).all()
        responsibilities = []
        for dr in default_resps:
            resp = db.query(Responsibility).filter(Responsibility.id == dr.responsibility_id).first()
            if resp:
                responsibilities.append({"id": resp.id, "name": resp.name})

        template = None
        if role.default_permission_template_id:
            t = db.query(PermissionTemplate).filter(PermissionTemplate.id == role.default_permission_template_id).first()
            if t:
                template = {"id": t.id, "name": t.name}

        return {"success": True, "data": {"role_id": role.id, "role_name": role.name, "default_categories": categories, "default_responsibilities": responsibilities, "default_permission_template": template}}

    @router.get("/categories")
    async def list_categories(db = Depends(get_db), current_user = Depends(get_current_user)):
        if not check_admin_permission(current_user):
            raise HTTPException(status_code=403, detail="Permission denied")
        cats = db.query(Category).filter(Category.is_active == True).order_by(Category.sort_order).all()
        return {"success": True, "data": {"categories": [{"id": c.id, "name": c.name, "description": c.description} for c in cats]}}

    @router.get("/responsibilities")
    async def list_responsibilities(db = Depends(get_db), current_user = Depends(get_current_user)):
        """List all active responsibilities with their category info"""
        if not check_admin_permission(current_user):
            raise HTTPException(status_code=403, detail="Permission denied")
        resps = db.query(Responsibility).filter(Responsibility.is_active == True).order_by(Responsibility.category_id, Responsibility.name).all()
        result = []
        for r in resps:
            cat = db.query(Category).filter(Category.id == r.category_id).first()
            result.append({"id": r.id, "name": r.name, "description": r.description, "category_id": r.category_id, "category_name": cat.name if cat else ""})
        return {"success": True, "data": {"responsibilities": result}}

    @router.post("/responsibilities/filter")
    async def filter_responsibilities(data: ResponsibilityFilterRequest, db = Depends(get_db), current_user = Depends(get_current_user)):
        if not check_admin_permission(current_user):
            raise HTTPException(status_code=403, detail="Permission denied")
        resps = db.query(Responsibility).filter(Responsibility.is_active == True, Responsibility.category_id.in_(data.category_ids)).all()
        result = []
        for r in resps:
            cat = db.query(Category).filter(Category.id == r.category_id).first()
            result.append({"id": r.id, "name": r.name, "description": r.description, "category_id": r.category_id, "category_name": cat.name if cat else ""})
        return {"success": True, "data": {"responsibilities": result}}

    @router.get("/permission-templates")
    async def list_templates(db = Depends(get_db), current_user = Depends(get_current_user)):
        if not check_admin_permission(current_user):
            raise HTTPException(status_code=403, detail="Permission denied")
        templates = db.query(PermissionTemplate).order_by(PermissionTemplate.name).all()
        return {"success": True, "data": {"templates": [{"id": t.id, "name": t.name, "description": t.description, "is_system_template": t.is_system_template} for t in templates]}}

    @router.get("/permission-templates/{template_id}")
    async def get_template(template_id: int, db = Depends(get_db), current_user = Depends(get_current_user)):
        if not check_admin_permission(current_user):
            raise HTTPException(status_code=403, detail="Permission denied")
        t = db.query(PermissionTemplate).filter(PermissionTemplate.id == template_id).first()
        if not t:
            raise HTTPException(status_code=404, detail="Template not found")
        return {"success": True, "data": {"id": t.id, "name": t.name, "description": t.description, "is_system_template": t.is_system_template, "permissions": t.permissions}}

    # Activation endpoints
    @router.get("/activate/validate/{activation_token}")
    async def validate_token(activation_token: str, db = Depends(get_db)):
        profile = db.query(UserProfile).filter(UserProfile.activation_token == activation_token).first()
        if not profile:
            raise HTTPException(status_code=400, detail="Invalid token")
        if profile.activation_token_expires_at < datetime.now(timezone.utc):
            raise HTTPException(status_code=400, detail="Token expired")
        user = db.query(User).filter(User.id == profile.user_id).first()
        role = db.query(Role).filter(Role.id == profile.role_id).first()
        return {"success": True, "data": {"token_valid": True, "user": {"id": user.id, "first_name": profile.first_name, "last_name": profile.last_name, "email": user.email, "role_name": role.name if role else ""}, "expires_at": profile.activation_token_expires_at.isoformat()}}

    @router.post("/activate/set-password")
    async def set_password(data: ActivatePasswordRequest, request: Request, db = Depends(get_db)):
        if data.password != data.password_confirmation:
            raise HTTPException(status_code=400, detail="Passwords don't match")
        profile = db.query(UserProfile).filter(UserProfile.activation_token == data.activation_token).first()
        if not profile:
            raise HTTPException(status_code=400, detail="Invalid token")
        if profile.activation_token_expires_at < datetime.now(timezone.utc):
            raise HTTPException(status_code=400, detail="Token expired")
        user = db.query(User).filter(User.id == profile.user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        try:
            user.hashed_password = pwd_context.hash(data.password)
            user.is_active = True
            profile.status = "active"
            profile.activated_at = datetime.now(timezone.utc)
            profile.activation_token = None

            audit = AuditLog(user_id=user.id, action="user_activated", performed_by=user.id, details={"method": "email_token"}, ip_address=request.client.host if request.client else None)
            db.add(audit)
            db.commit()

            token = create_access_token(data={"sub": user.email})
            return {"success": True, "data": {"user_id": user.id, "status": "active", "redirect_url": "/dashboard", "auth_token": token}}
        except Exception as e:
            db.rollback()
            raise HTTPException(status_code=500, detail="Internal server error")

    # Bulk Upload Endpoints
    @router.post("/bulk/parse")
    async def bulk_parse(
        file: UploadFile = File(...),
        db = Depends(get_db),
        current_user = Depends(get_current_user)
    ):
        """Parse uploaded CSV file and return headers and preview"""
        if not check_admin_permission(current_user):
            raise HTTPException(status_code=403, detail="Permission denied")

        if not file.filename.endswith('.csv'):
            raise HTTPException(status_code=400, detail="Only CSV files are supported")

        try:
            contents = await file.read()
            decoded = contents.decode('utf-8')
            reader = csv.DictReader(io.StringIO(decoded))

            headers = reader.fieldnames or []
            rows = list(reader)
            preview = rows[:5]  # First 5 rows for preview

            return {
                "success": True,
                "headers": headers,
                "preview": preview,
                "total_rows": len(rows)
            }
        except Exception as e:
            raise HTTPException(status_code=400, detail="Error parsing file")

    @router.post("/bulk/validate")
    async def bulk_validate(
        file: UploadFile = File(...),
        column_mapping: str = Form(...),
        db = Depends(get_db),
        current_user = Depends(get_current_user)
    ):
        """Validate mapped CSV data before processing"""
        if not check_admin_permission(current_user):
            raise HTTPException(status_code=403, detail="Permission denied")

        import json
        mapping = json.loads(column_mapping)

        try:
            contents = await file.read()
            decoded = contents.decode('utf-8')
            reader = csv.DictReader(io.StringIO(decoded))
            rows = list(reader)

            valid_rows = []
            invalid_rows = []
            existing_emails = set()

            # Get existing emails from database
            all_users = db.query(User).all()
            db_emails = {u.email.lower() for u in all_users}

            for idx, row in enumerate(rows):
                errors = []

                # Get mapped values
                first_name = row.get(mapping.get('first_name', ''), '').strip()
                last_name = row.get(mapping.get('last_name', ''), '').strip()
                email = row.get(mapping.get('email', ''), '').strip().lower()

                # Validate required fields
                if not first_name:
                    errors.append("Missing first name")
                if not last_name:
                    errors.append("Missing last name")
                if not email:
                    errors.append("Missing email")
                elif not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', email):
                    errors.append("Invalid email format")
                elif email in db_emails:
                    errors.append("Email already exists in system")
                elif email in existing_emails:
                    errors.append("Duplicate email in file")

                existing_emails.add(email)

                row_data = {
                    "row": idx + 1,
                    "first_name": first_name,
                    "last_name": last_name,
                    "email": email,
                    "phone": row.get(mapping.get('phone', ''), '').strip()
                }

                if errors:
                    row_data["errors"] = errors
                    invalid_rows.append(row_data)
                else:
                    valid_rows.append(row_data)

            return {
                "success": True,
                "valid_count": len(valid_rows),
                "invalid_count": len(invalid_rows),
                "valid_rows": valid_rows,
                "invalid_rows": invalid_rows,
                "total_rows": len(rows)
            }
        except Exception as e:
            raise HTTPException(status_code=400, detail="Error validating file")

    @router.post("/bulk/process")
    async def bulk_process(
        request: Request,
        file: UploadFile = File(...),
        column_mapping: str = Form(...),
        default_role_id: Optional[int] = Form(None),
        db = Depends(get_db),
        current_user = Depends(get_current_user)
    ):
        """Process and create users from CSV"""
        if not check_admin_permission(current_user):
            raise HTTPException(status_code=403, detail="Permission denied")

        import json
        mapping = json.loads(column_mapping)

        # Get default role
        default_role = None
        if default_role_id:
            default_role = db.query(Role).filter(Role.id == default_role_id).first()
        if not default_role:
            default_role = db.query(Role).filter(Role.name == "Loan Officer").first()

        try:
            contents = await file.read()
            decoded = contents.decode('utf-8')
            reader = csv.DictReader(io.StringIO(decoded))
            rows = list(reader)

            results = []
            created_count = 0
            failed_count = 0

            for idx, row in enumerate(rows):
                first_name = row.get(mapping.get('first_name', ''), '').strip()
                last_name = row.get(mapping.get('last_name', ''), '').strip()
                email = row.get(mapping.get('email', ''), '').strip().lower()
                phone = row.get(mapping.get('phone', ''), '').strip()

                # Skip invalid rows
                if not first_name or not last_name or not email:
                    results.append({
                        "row": idx + 1,
                        "email": email,
                        "status": "failed",
                        "error": "Missing required fields"
                    })
                    failed_count += 1
                    continue

                # Check if email exists
                existing = db.query(User).filter(User.email == email).first()
                if existing:
                    results.append({
                        "row": idx + 1,
                        "email": email,
                        "status": "skipped",
                        "error": "Email already exists"
                    })
                    failed_count += 1
                    continue

                try:
                    # Create user
                    new_user = User(
                        email=email,
                        hashed_password="",
                        first_name=first_name,
                        last_name=last_name,
                        phone=phone,
                        role=default_role.name.lower().replace(" ", "_") if default_role else "loan_officer",
                        permission_role="pending",
                        is_active=False
                    )
                    db.add(new_user)
                    db.flush()

                    # Create profile
                    activation_token = generate_activation_token()
                    profile = UserProfile(
                        user_id=new_user.id,
                        first_name=first_name,
                        last_name=last_name,
                        role_id=default_role.id if default_role else None,
                        status="pending_activation",
                        activation_token=activation_token,
                        activation_token_expires_at=datetime.now(timezone.utc) + timedelta(days=7),
                        created_by=current_user.id
                    )
                    db.add(profile)
                    db.flush()

                    # Create audit log
                    audit = AuditLog(
                        user_id=new_user.id,
                        action="user_created_bulk",
                        performed_by=current_user.id,
                        details={"email": email, "source": "bulk_upload"},
                        ip_address=request.client.host if request.client else None
                    )
                    db.add(audit)

                    results.append({
                        "row": idx + 1,
                        "email": email,
                        "user_id": new_user.id,
                        "status": "created",
                        "activation_token": activation_token
                    })
                    created_count += 1

                except Exception as e:
                    results.append({
                        "row": idx + 1,
                        "email": email,
                        "status": "failed",
                        "error": "Internal server error"
                    })
                    failed_count += 1

            db.commit()

            return {
                "success": True,
                "results": results,
                "summary": {
                    "total": len(rows),
                    "created": created_count,
                    "failed": failed_count
                }
            }
        except Exception as e:
            db.rollback()
            raise HTTPException(status_code=500, detail="Error processing file")

    return router
