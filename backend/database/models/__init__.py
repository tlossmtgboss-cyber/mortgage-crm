"""
Database Models Package

Organized SQLAlchemy model definitions extracted from main.py.

Structure:
    models/
    ├── __init__.py           # This file - aggregates all exports
    ├── core.py               # Organization, User, Branch, Auth models
    ├── lead_loan.py          # Lead and Loan pipeline models
    ├── task.py               # Task and AITask models
    ├── document.py           # Document management models
    ├── communication.py      # Email, SMS, Call, Activity models
    ├── ai.py                 # AI/ML related models
    ├── referral.py           # Referral partner models
    ├── workflow.py           # Workflow automation models
    ├── permission.py         # Permission and role models
    ├── security.py           # Security and audit models
    ├── subscription.py       # Subscription, billing, promo codes
    ├── microsoft.py          # Microsoft OAuth/Graph integration
    ├── data_reconciliation.py # Data reconciliation engine (DRE)
    ├── it_helpdesk.py        # IT helpdesk tickets and tools
    ├── client.py             # Client management profiles
    ├── hr_goals.py           # HR goals, skills, assessments
    ├── dialer.py             # Power dialer/telephony models
    ├── borrower.py           # Borrower application system
    └── estimate.py           # Loan estimate parser/comparison

Usage:
    from database.models import User, Organization, Lead, Loan
    from database.models.core import User, Branch
    from database.models.task import Task, AITask
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
    EscalationRecord,
    HandoffLog,
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
    ConversationSession,
    EntityExtraction,
    ChannelPreference,
    MessageTemplate,
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

# Subscription & billing models
from .subscription import (
    SubscriptionPlan,
    Subscription,
    PromoCode,
    TeamMember,
)

# Microsoft integration models
from .microsoft import (
    MicrosoftToken,
    MicrosoftOAuthToken,
    MicrosoftAppConfig,
)

# Data reconciliation engine models
from .data_reconciliation import (
    IncomingDataEvent,
    ExtractedData,
    BlockedSender,
    DuplicatePair,
    MergeTrainingEvent,
    MergeAIModel,
)

# IT helpdesk models
from .it_helpdesk import (
    ITHelpdeskTicket,
    ITHelpdeskTool,
)

# Client management models
from .client import (
    ClientProfile,
    TeamRole,
    ProcessFlowDocument,
    KPISnapshot,
)

# HR goals & skills models
from .hr_goals import (
    UserJobDescription,
    Skill,
    EmployeeResponsibility,
    ResponsibilitySkill,
    UserGoal,
    GoalKeyResult,
    GoalEmployeeAssessment,
    GoalManagerAssessment,
    GoalResponsibility,
    UserSkillAssessment,
)

# Power dialer / telephony models
from .dialer import (
    AgentTelephonySettings,
    VerifiedCallerId,
    DialerSession,
    DialerSessionTask,
    CallLog,
    ActiveCall,
    ContactDNCStatus,
)

# Borrower application system models
from .borrower import (
    BorrowerProfile,
    BorrowerAuthEvent,
    BorrowerMagicLink,
    BorrowerApplication,
    ApplicationDocument,
    CoborrowerInvitation,
    ApplicationEvent,
    ApplicationNotification,
    ApplicationSession,
    VoiceApplicationSession,
)

# Loan estimate parser/comparison models
from .estimate import (
    EstimateParseCache,
    EstimateParseFailure,
    EstimateComparison,
)

# Platform contract models
from .platform_contract import PlatformContract

# Refinance intelligence models
from .refinance_intelligence import (
    RefiOpportunity,
    RefiScenario,
    PortfolioMonitoringRun,
)

# Credit bureau monitoring models
from .credit_monitoring import (
    CreditMonitoringSubscription,
    CreditAlert,
    CreditInquiryAlert,
    MonitoringStatus,
    CreditBureauProvider,
    ContactType,
    AlertType,
    InquiryType,
    NotificationChannel,
)

# Rate lock & market data models
from .rate_lock import (
    RateLock,
    RateMarketData,
)

# Marketing campaign models
from .marketing import (
    AudienceSegment,
    CampaignDefinition,
    DripSequence,
)

# LOS integration & sync models
from .los_sync import (
    LosFieldMapping,
    LosSyncLog,
)

# Encompass LOS configuration
from .encompass_config import EncompassConfig

# Compliance models (TRID, ECOA, HMDA)
from .compliance import (
    LoanFee,
    DisclosureEvent,
    AdverseActionNotice,
    ComplianceAlert,
    ToleranceCategory,
    DisclosureType,
    AdverseActionReason,
)

# AI Prospect Re-Engagement models
from .ai_prospect_conversation import (
    AIProspectConversation,
    AIReengagementConfig,
    ConversationState,
)

# SSO configuration models (SAML, OIDC)
from .sso import SSOConfig

# Webhook models (API Gateway & Developer Experience)
from .webhook import (
    WebhookSubscription,
    WebhookDeliveryLog,
    WebhookEventCatalog,
)

# Content library models (pre-built and custom marketing templates)
from .content_library import (
    ContentLibraryItem,
    ContentUsageLog,
    ContentType,
    ContentCategory,
)

# AI Document Intelligence models
from .document_intelligence import (
    AIDocumentClassification,
    DocumentRequirementRule,
    POSDocumentMapping,
    CallIntelDocumentNeed,
    DocumentRuleCategory,
    DocumentRulePriority,
    DocumentRuleAppliesTo,
    CallIntelDocNeedStatus,
)

# Document follow-up & scheduling models
from .document_followup import (
    FollowupCampaign,
    FollowupEvent,
    DocumentAppointment,
    FollowupTemplate,
    CampaignType,
    CampaignStatus,
    CampaignTriggerSource,
    FollowupEventType,
    DeliveryStatus,
    AppointmentType,
    AppointmentStatus,
    LocationType,
)

# E-Signature models (envelopes, recipients, fields, audit, templates)
from .esignature import (
    ESignatureEnvelope,
    ESignatureRecipient,
    ESignatureField,
    ESignatureAuditEvent,
    ESignatureTemplate,
    EnvelopeStatus,
    RecipientType,
    RecipientStatus,
    RecipientAuthMethod,
    SignatureFieldType,
    AuditEventType,
)

# Document security & audit models
from .document_security import (
    DocumentAccessLog,
    DocumentEncryptionRecord,
    DocumentIntegrityCheck,
    DocumentRetentionPolicy,
    DocumentWatermarkLog,
    AccessType,
    EncryptionStatus,
    IntegrityCheckType,
    RetentionAction,
    WatermarkType,
)

# Scheduling analytics & continuous learning models
from .scheduling_analytics import (
    SchedulingInsight,
    AppointmentOutcome,
)

# Calendar event mapping (provider-agnostic sync)
from .calendar_event_map import CalendarEventMap


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
    "EscalationRecord",
    "HandoffLog",

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
    "ConversationSession",
    "EntityExtraction",
    "ChannelPreference",
    "MessageTemplate",

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

    # =====================
    # Subscription & Billing
    # =====================
    "SubscriptionPlan",
    "Subscription",
    "PromoCode",
    "TeamMember",

    # =====================
    # Microsoft Integration
    # =====================
    "MicrosoftToken",
    "MicrosoftOAuthToken",
    "MicrosoftAppConfig",

    # =====================
    # Data Reconciliation
    # =====================
    "IncomingDataEvent",
    "ExtractedData",
    "BlockedSender",
    "DuplicatePair",
    "MergeTrainingEvent",
    "MergeAIModel",

    # =====================
    # IT Helpdesk
    # =====================
    "ITHelpdeskTicket",
    "ITHelpdeskTool",

    # =====================
    # Client Management
    # =====================
    "ClientProfile",
    "TeamRole",
    "ProcessFlowDocument",
    "KPISnapshot",

    # =====================
    # HR Goals & Skills
    # =====================
    "UserJobDescription",
    "Skill",
    "EmployeeResponsibility",
    "ResponsibilitySkill",
    "UserGoal",
    "GoalKeyResult",
    "GoalEmployeeAssessment",
    "GoalManagerAssessment",
    "GoalResponsibility",
    "UserSkillAssessment",

    # =====================
    # Power Dialer
    # =====================
    "AgentTelephonySettings",
    "VerifiedCallerId",
    "DialerSession",
    "DialerSessionTask",
    "CallLog",
    "ActiveCall",
    "ContactDNCStatus",

    # =====================
    # Borrower Application
    # =====================
    "BorrowerProfile",
    "BorrowerAuthEvent",
    "BorrowerMagicLink",
    "BorrowerApplication",
    "ApplicationDocument",
    "CoborrowerInvitation",
    "ApplicationEvent",
    "ApplicationNotification",
    "ApplicationSession",
    "VoiceApplicationSession",

    # =====================
    # Loan Estimates
    # =====================
    "EstimateParseCache",
    "EstimateParseFailure",
    "EstimateComparison",

    # =====================
    # Platform Contracts
    # =====================
    "PlatformContract",

    # =====================
    # Refinance Intelligence
    # =====================
    "RefiOpportunity",
    "RefiScenario",
    "PortfolioMonitoringRun",

    # =====================
    # Rate Lock & Market Data
    # =====================
    "RateLock",
    "RateMarketData",

    # =====================
    # Marketing Campaigns
    # =====================
    "AudienceSegment",
    "CampaignDefinition",
    "DripSequence",

    # =====================
    # LOS Integration & Sync
    # =====================
    "LosFieldMapping",
    "LosSyncLog",

    # =====================
    # Encompass LOS Config
    # =====================
    "EncompassConfig",

    # =====================
    # Compliance (TRID, ECOA, HMDA)
    # =====================
    "LoanFee",
    "DisclosureEvent",
    "AdverseActionNotice",
    "ComplianceAlert",
    "ToleranceCategory",
    "DisclosureType",
    "AdverseActionReason",

    # =====================
    # AI Prospect Re-Engagement
    # =====================
    "AIProspectConversation",
    "AIReengagementConfig",
    "ConversationState",

    # =====================
    # SSO (SAML, OIDC)
    # =====================
    "SSOConfig",

    # =====================
    # Webhooks (API Gateway)
    # =====================
    "WebhookSubscription",
    "WebhookDeliveryLog",
    "WebhookEventCatalog",

    # =====================
    # Content Library
    # =====================
    "ContentLibraryItem",
    "ContentUsageLog",
    "ContentType",
    "ContentCategory",

    # =====================
    # AI Document Intelligence
    # =====================
    "AIDocumentClassification",
    "DocumentRequirementRule",
    "POSDocumentMapping",
    "CallIntelDocumentNeed",
    "DocumentRuleCategory",
    "DocumentRulePriority",
    "DocumentRuleAppliesTo",
    "CallIntelDocNeedStatus",

    # =====================
    # Document Follow-Up
    # =====================
    "FollowupCampaign",
    "FollowupEvent",
    "DocumentAppointment",
    "FollowupTemplate",
    "CampaignType",
    "CampaignStatus",
    "CampaignTriggerSource",
    "FollowupEventType",
    "DeliveryStatus",
    "AppointmentType",
    "AppointmentStatus",
    "LocationType",

    # =====================
    # E-Signature
    # =====================
    "ESignatureEnvelope",
    "ESignatureRecipient",
    "ESignatureField",
    "ESignatureAuditEvent",
    "ESignatureTemplate",
    "EnvelopeStatus",
    "RecipientType",
    "RecipientStatus",
    "RecipientAuthMethod",
    "SignatureFieldType",
    "AuditEventType",

    # =====================
    # Document Security
    # =====================
    "DocumentAccessLog",
    "DocumentEncryptionRecord",
    "DocumentIntegrityCheck",
    "DocumentRetentionPolicy",
    "DocumentWatermarkLog",
    "AccessType",
    "EncryptionStatus",
    "IntegrityCheckType",
    "RetentionAction",
    "WatermarkType",

    # =====================
    # Scheduling Analytics
    # =====================
    "SchedulingInsight",
    "AppointmentOutcome",

    # =====================
    # Calendar Event Map
    # =====================
    "CalendarEventMap",
]
