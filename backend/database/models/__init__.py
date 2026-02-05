"""
Database Models Package

Organized SQLAlchemy model definitions extracted from main.py.

Structure:
    models/
    ├── __init__.py      # This file - aggregates all exports
    ├── core.py          # Organization, User, Branch, Auth models
    ├── lead_loan.py     # Lead and Loan pipeline models
    ├── task.py          # Task and AITask models
    ├── document.py      # Document management models
    ├── communication.py # Email, SMS, Call, Activity models
    ├── ai.py            # AI/ML related models
    ├── referral.py      # Referral partner models
    ├── workflow.py      # Workflow automation models
    ├── permission.py    # Permission and role models
    ├── security.py      # Security and audit models
    └── dialer.py        # Power dialer/telephony models (TODO)

Usage:
    from database.models import User, Organization, Lead, Loan
    from database.models.core import User, Branch
    from database.models.task import Task, AITask

Migration Notes:
    During the decomposition of main.py (75K lines -> modular structure),
    models are being extracted incrementally. New code should import from
    this module, but main.py still contains the authoritative definitions
    until the migration is complete.

    Pattern for extracting models:
    1. Copy model class from main.py to appropriate module
    2. Update imports (Base, Column, relationship, etc.)
    3. Add to module's __all__ list
    4. Add import to this __init__.py
    5. Update main.py to import from here (once all models extracted)
"""

# Core models - Organization, User, Auth
from .core import (
    Organization,
    Branch,
    User,
    ApiKey,
    UserSettings,
    CalendarAssignment,
    EmailSignature,
    ImpersonationSession,
    OnboardingProgress,
    OnboardingError,
    VerificationToken,
)

# Lead & Loan models (extracted from main.py)
from .lead_loan import Lead, Loan

# Task models
from .task import (
    AITask,
    Task,
)

# Document models
from .document import (
    EmailIntake,
    AttachmentIntake,
    Document,
)

# Communication models
from .communication import (
    Activity,
    StageHistory,
    Conversation,
    ConversationMemory,
    SMSMessage,
    SMSConversation,
    EmailMessage,
    Email,
    EmailDraft,
    EmailVerificationToken,
    TeamsMessage,
    VoicemailDrop,
    VoicemailTemplate,
    VoicemailCampaign,
    VoicemailEvent,
    CalendarEvent,
    IntegrationLog,
    IntegrationCredential,
)

# AI models
from .ai import (
    AIDelegatedTask,
    AIFeedbackLog,
    AIAction,
    AILearningMetric,
    AIKnowledgeBase,
    AIAuditLog,
    AIColleagueAction,
    AIColleagueLearningMetric,
    AIPerformanceDaily,
    AIJourneyInsight,
    AIHealthScore,
    AIMetricsDaily,
    AIChangelogDaily,
    AITrainingEvent,
)

# Referral models
from .referral import (
    ReferralPartner,
    LoanTeamMember,
    MUMClient,
)

# Workflow models
from .workflow import (
    ScheduledWorkflow,
    WorkflowExecution,
    Workflow,
    CalendarMapping,
    OnboardingStep,
    ProcessTemplate,
    ProcessRole,
    ProcessMilestone,
    ProcessTask,
)

# Permission models
from .permission import (
    EmployeeInvite,
    CRMPage,
    RolePagePermission,
    UserPagePermission,
    UserPermission,
    PermissionRequest,
    AIQuickAction,
    AIQuickActionRole,
    Responsibility,
    RoleResponsibility,
    UserResponsibility,
)

# Security models
from .security import (
    AuditLog,
    UserSession,
    EmergencyRevocation,
    AccessCertification,
    SecuritySnapshotDaily,
    IntegrationStatusLog,
    SystemAlert,
    SystemJobsLog,
    Notification,
)


__all__ = [
    # =====================
    # Core - Organization
    # =====================
    "Organization",
    "Branch",
    # Core - User & Auth
    "User",
    "ApiKey",
    "UserSettings",
    # Core - Calendar
    "CalendarAssignment",
    # Core - Email
    "EmailSignature",
    # Core - Security
    "ImpersonationSession",
    # Core - Onboarding
    "OnboardingProgress",
    "OnboardingError",
    "VerificationToken",

    # =====================
    # Lead & Loan Pipeline
    # =====================
    "Lead",
    "Loan",

    # =====================
    # Tasks
    # =====================
    "AITask",
    "Task",

    # =====================
    # Documents
    # =====================
    "EmailIntake",
    "AttachmentIntake",
    "Document",

    # =====================
    # Communication
    # =====================
    "Activity",
    "StageHistory",
    "Conversation",
    "ConversationMemory",
    "SMSMessage",
    "SMSConversation",
    "EmailMessage",
    "Email",
    "EmailDraft",
    "EmailVerificationToken",
    "TeamsMessage",
    "VoicemailDrop",
    "VoicemailTemplate",
    "VoicemailCampaign",
    "VoicemailEvent",
    "CalendarEvent",
    "IntegrationLog",
    "IntegrationCredential",

    # =====================
    # AI
    # =====================
    "AIDelegatedTask",
    "AIFeedbackLog",
    "AIAction",
    "AILearningMetric",
    "AIKnowledgeBase",
    "AIAuditLog",
    "AIColleagueAction",
    "AIColleagueLearningMetric",
    "AIPerformanceDaily",
    "AIJourneyInsight",
    "AIHealthScore",
    "AIMetricsDaily",
    "AIChangelogDaily",
    "AITrainingEvent",

    # =====================
    # Referral
    # =====================
    "ReferralPartner",
    "LoanTeamMember",
    "MUMClient",

    # =====================
    # Workflow
    # =====================
    "ScheduledWorkflow",
    "WorkflowExecution",
    "Workflow",
    "CalendarMapping",
    "OnboardingStep",
    "ProcessTemplate",
    "ProcessRole",
    "ProcessMilestone",
    "ProcessTask",

    # =====================
    # Permission
    # =====================
    "EmployeeInvite",
    "CRMPage",
    "RolePagePermission",
    "UserPagePermission",
    "UserPermission",
    "PermissionRequest",
    "AIQuickAction",
    "AIQuickActionRole",
    "Responsibility",
    "RoleResponsibility",
    "UserResponsibility",

    # =====================
    # Security
    # =====================
    "AuditLog",
    "UserSession",
    "EmergencyRevocation",
    "AccessCertification",
    "SecuritySnapshotDaily",
    "IntegrationStatusLog",
    "SystemAlert",
    "SystemJobsLog",
    "Notification",
]
