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

# Microsoft Graph email OAuth tokens
from .microsoft_email import MicrosoftEmailToken

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

# 50-state disclosure requirements
from .state_disclosure import StateDisclosure

# AI Prospect Re-Engagement models
from .ai_prospect_conversation import (
    AIProspectConversation,
    AIReengagementConfig,
    ConversationState,
)

# Device token & push notification models (mobile app infrastructure)
from .device_token import DeviceToken, PushNotificationPreference

# SSO configuration models (SAML, OIDC)
from .sso import SSOConfig

# SSO enterprise configuration (SAML/OIDC with encrypted certs)
from .sso_config import SSOConfiguration

# Webhook models (API Gateway & Developer Experience)
from .webhook import (
    WebhookSubscription,
    WebhookDeliveryLog,
    WebhookEventCatalog,
)

# Content library models (pre-built and custom marketing templates)
from .content_library import (
    ContentLibraryItem,
    ContentLibraryUsageLog,
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
    ESignConsentSession,
    ESignKBASession,
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

# Decision audit trail models (append-only audit log, retention config)
from .decision_audit import (
    DecisionAuditLog,
    AuditRetentionConfig,
    ArchivedDecisionAuditLog,
)

# TCPA Smart Docs consent & DNC models
from .tcpa_smart_docs import (
    SmartDocsConsentRecord,
    InternalDNCEntry,
    OutreachLog,
)

# Business rule configuration (database-backed thresholds & limits)
from .business_rules import BusinessRuleConfig

# Calendar event mapping (provider-agnostic sync)
from .calendar_event_map import CalendarEventMap

# Document processing cache (hash-based AI result caching)
from .document_cache import DocumentProcessingCache

# eClosing session models (Snapdocs/Pavaso/NotaryCam integration)
from .eclosing import (
    EClosingSession,
    EClosingSessionStatus,
    ClosingType,
    NotaryType,
    EClosingProvider,
)

# Plaid bank account integration
from .plaid_connection import PlaidConnection

# AUS (Automated Underwriting System) submission tracking
from .aus_submission import AUSSubmission

# IRS Transcript (4506-C request and income verification)
from .irs_transcript import (
    IRSTranscriptRequest,
    TranscriptType,
    TranscriptStatus,
)

# AI Benchmark (classification accuracy benchmarking)
from .ai_benchmark import (
    AIBenchmarkDataset,
    AIBenchmarkSample,
)

# Document version control (Smart Docs V2)
from .document_version import DocumentVersion, ChangeType

# Document annotation (Smart Docs V2)
from .document_annotation import DocumentAnnotation, AnnotationType, AnnotationStatus

# Document search index (Smart Docs V2 full-text search)
from .document_search_index import (
    DocumentSearchIndex,
    SavedSearch,
    SearchAnalyticsEvent,
)

# Smart Docs batch job tracking
from .batch_job import (
    BatchJob,
    BatchJobType,
    BatchJobStatus,
)

# Smart Docs V2 document templates
from .document_template import (
    DocumentTemplate,
    DocumentGenerationLog,
)

# Document Archive (post-closing archive lifecycle)
from .document_archive import (
    DocumentArchive,
    ArchiveType,
    ArchiveStatus,
    RetentionPolicy,
    StorageClass,
)

# Smart Docs Escalation Engine (rule-based escalation chains)
from .escalation_rule import (
    EscalationRule as SmartDocsEscalationRule,
    EscalationEvent as SmartDocsEscalationEvent,
)

# Smart Docs Follow-Up Cadence Engine
from .followup_cadence import (
    FollowupCadence,
    FollowupExecution,
)

# Smart Docs White-Label (per-org branding & email templates)
from .white_label_config import (
    WhiteLabelConfig,
    EmailTemplate as SmartDocsEmailTemplate,
)

# Smart Docs SLA Configuration & Tracking
from .doc_sla_config import DocSLAConfig, DocSLATracking

# Lead Assignment Configuration
from .lead_assignment import (
    LeadAssignmentConfig,
    LeadAssignmentRule,
    LeadAssignmentPool,
    LeadAssignmentException,
    LeadAssignmentAuditLog,
)

# Smart Docs Document Routing (Enterprise)
from .routing_rule import (
    RoutingRule,
    ProcessingQueue,
    RoutingAuditLog,
)

# Smart Docs Approval Chain (Enterprise multi-step approval workflows)
from .approval_chain import (
    ApprovalChainConfig,
    ApprovalRequest,
    ApprovalDecision,
    ApprovalDelegation,
    ApprovalType,
    ApprovalRequestStatus,
    DecisionVerdict,
    TimeoutAction,
    DelegationType,
)

# Smart Docs V2 Field Mapping (Enterprise document-to-CRM field mapping)
from .doc_field_mapping import (
    FieldMappingConfig,
    CustomField,
)

# Recurring Availability (weekly patterns, date exceptions, org templates)
from .recurring_availability import (
    RecurringAvailability,
    AvailabilityException,
    AvailabilityTemplate,
)

# Appointment Reminder Configuration & Logging
from .reminder_config import (
    ReminderTemplate,
    ReminderLog,
)

# Waiting room / queue management
from .waiting_room import WaitlistEntry, WaitlistStatus

# Reschedule history (appointment rescheduling audit trail)
from .reschedule_history import RescheduleHistory

# Appointment Templates (pre-configured appointment settings)
from .appointment_template import AppointmentTemplate

# Calendar labels (color-coded appointment categorization)
from .calendar_label import CalendarLabel, AppointmentLabel

# Calendar feed subscription (iCalendar / webcal)
from .calendar_feed import CalendarFeedToken

# Post-appointment surveys
from .appointment_survey import AppointmentSurvey

# Appointment locations (saved meeting locations for scheduling)
from .appointment_location import AppointmentLocation

# Cancellation Policy (per-org appointment cancellation rules)
from .cancellation_policy import CancellationPolicy

# Application Completion Orchestrator (ACO) models
from .app_completion import (
    ApplicationCompletenessReview,
    MissingItem,
    DocumentStagingRequest,
    BorrowerCommunicationLog,
    AppointmentCoordination,
    ApplicationScoreHistory,
    ReviewStatus,
    ComplexityLevel,
    NextAction,
    MissingItemType,
    MissingItemSeverity,
    MissingItemStatus,
    ResolutionMethod,
    DocStagingStatus,
    CommChannel,
    SenderType,
    MessageIntent,
    BookingStatus,
    ScoreChangeReason,
    ActorType,
)

# Smart Scheduler models (appointment scheduling, availability, booking)
from .scheduler import (
    SchedulerConfig,
    AvailabilitySlot,
    SchedulerAppointmentType,
    Appointment as SchedulerAppointment,
    SchedulerRoutingRule,
    BlockedTime,
    BookingLink,
    AppointmentReminder as SchedulerAppointmentReminder,
    AppointmentStatusHistory,
    SchedulerAuditLog,
    SlotHold,
)

# Agent performance metrics (AI agent invocation tracking)
from .agent_metrics import AgentInvocation

# Compliance decision audit log (TCPA/DNC/calling-hours immutable log)
from .compliance_log import ComplianceDecisionLog

# Consent audit trail (immutable log of all consent grants/revocations/verifications)
from .consent_audit import ConsentAuditLog

# SMS persistence models (campaign & scheduled job DB-backed state)
from .sms_persistence import SMSCampaignRecord, ScheduledSMSJobRecord

# Morning Briefing (daily AI-generated briefings per user)
from .morning_briefing import MorningBriefing

# Security Training Records (SOC 2 CC1.4 training evidence)
from .security_training import SecurityTrainingRecord

from .sms_delivery import SMSDeliveryLog
from .sms_panel_message import SMSPanelMessage

# Voice consent tracking (TCPA AI voice call consent)
from .voice_consent import (
    VoiceConsent,
    VoiceConsentAudit,
)

# Password policy (SOC 2 CC6.1 — history + login attempts)
from .password_history import PasswordHistory, LoginAttempt

# Partner Portal (session tokens, pre-approval letter requests)
from .partner import PartnerSession, PreApprovalLetterRequest

# iMessage / BlueBubbles integration
from integrations.imessage.models import (
    IMessageLine,
    IMessageThread,
    IMessageMessage,
    IMessageLookupCache,
    IMessageWebhookLog,
)

# Team Chat models
from .team_chat import (
    TeamChatChannel,
    TeamChatMessage,
    TeamChatReaction,
    TeamChatRead,
    TeamChatAuthorKind,
    TeamChatAgentSlug,
    TeamChatReactionEmoji,
)

# Client File aggregate root + collaborators
from .client_file import ClientFile, ClientFileCollaborator

# Aria Campaign models (mass text outreach)
from .aria_campaign import AriaCampaign, AriaCampaignRecipient

# GDPR erasure request lifecycle tracking
from .gdpr import ErasureRequest

# Loan Officer License (multi-state SAFE Act compliance)
from .lo_license import LoanOfficerLicense, LicenseStatus, LicenseType

# Briefing Thread models (morning briefing reply state machine + audit chain)
from .briefing_thread import BriefingThread, BriefingTask, BriefingAuditLog
from .contact_card import ContactCardMember

# AI Cost Records (persistent dollar-cost tracking for AI API calls)
from .ai_cost_record import AICostRecord

# Builder Application models (CMG Builder Portal submissions)
from .builder_application import BuilderApplication, BuilderDocument

# Rate Watch models (market rate polling, targets, refi opportunities)
from .rate_watch import (
    RateWatchRunLog,
    RateObservation,
    RateMarginConfig,
    BorrowerTargetRate,
    RefiOpportunityEvent,
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
    # Microsoft Graph Email
    # =====================
    "MicrosoftEmailToken",

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
    # State Disclosures (50-state)
    # =====================
    "StateDisclosure",

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
    "ContentLibraryUsageLog",
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
    # Decision Audit Trail
    # =====================
    "DecisionAuditLog",
    "AuditRetentionConfig",
    "ArchivedDecisionAuditLog",

    # =====================
    # Calendar Event Map
    # =====================
    "CalendarEventMap",

    # =====================
    # Document Processing Cache
    # =====================
    "DocumentProcessingCache",

    # =====================
    # TCPA Smart Docs
    # =====================
    "SmartDocsConsentRecord",
    "InternalDNCEntry",
    "OutreachLog",

    # =====================
    # Business Rule Config
    # =====================
    "BusinessRuleConfig",

    # =====================
    # eClosing Sessions
    # =====================
    "EClosingSession",
    "EClosingSessionStatus",
    "ClosingType",
    "NotaryType",
    "EClosingProvider",

    # =====================
    # Plaid Integration
    # =====================
    "PlaidConnection",

    # =====================
    # AUS Submissions
    # =====================
    "AUSSubmission",

    # =====================
    # IRS Transcript (4506-C)
    # =====================
    "IRSTranscriptRequest",
    "TranscriptType",
    "TranscriptStatus",

    # =====================
    # AI Benchmark
    # =====================
    "AIBenchmarkDataset",
    "AIBenchmarkSample",

    # =====================
    # Document Version Control
    # =====================
    "DocumentVersion",
    "ChangeType",

    # =====================
    # Document Annotation
    # =====================
    "DocumentAnnotation",
    "AnnotationType",
    "AnnotationStatus",

    # =====================
    # Document Search Index
    # =====================
    "DocumentSearchIndex",
    "SavedSearch",
    "SearchAnalyticsEvent",

    # =====================
    # Smart Docs Batch Jobs
    # =====================
    "BatchJob",
    "BatchJobType",
    "BatchJobStatus",

    # =====================
    # Smart Docs V2 Document Templates
    # =====================
    "DocumentTemplate",
    "DocumentGenerationLog",

    # =====================
    # Document Archive
    # =====================
    "DocumentArchive",
    "ArchiveType",
    "ArchiveStatus",
    "RetentionPolicy",
    "StorageClass",

    # =====================
    # Smart Docs Escalation Engine
    # =====================
    "SmartDocsEscalationRule",
    "SmartDocsEscalationEvent",

    # =====================
    # Smart Docs Follow-Up Cadence
    # =====================
    "FollowupCadence",
    "FollowupExecution",

    # =====================
    # Smart Docs White-Label
    # =====================
    "WhiteLabelConfig",
    "SmartDocsEmailTemplate",

    # =====================
    # Smart Docs SLA Config & Tracking
    # =====================
    "DocSLAConfig",
    "DocSLATracking",

    # =====================
    # Lead Assignment
    # =====================
    "LeadAssignmentConfig",
    "LeadAssignmentRule",
    "LeadAssignmentPool",
    "LeadAssignmentException",
    "LeadAssignmentAuditLog",

    # =====================
    # Smart Docs Document Routing
    # =====================
    "RoutingRule",
    "ProcessingQueue",
    "RoutingAuditLog",

    # =====================
    # Smart Docs Approval Chain
    # =====================
    "ApprovalChainConfig",
    "ApprovalRequest",
    "ApprovalDecision",
    "ApprovalDelegation",
    "ApprovalType",
    "ApprovalRequestStatus",
    "DecisionVerdict",
    "TimeoutAction",
    "DelegationType",

    # =====================
    # Smart Docs V2 Field Mapping
    # =====================
    "FieldMappingConfig",
    "CustomField",

    # =====================
    # Recurring Availability
    # =====================
    "RecurringAvailability",
    "AvailabilityException",
    "AvailabilityTemplate",

    # =====================
    # Appointment Reminders
    # =====================
    "ReminderTemplate",
    "ReminderLog",

    # =====================
    # Waiting Room / Queue
    # =====================
    "WaitlistEntry",
    "WaitlistStatus",

    # =====================
    # Appointment Templates
    # =====================
    "AppointmentTemplate",

    # =====================
    # Calendar Labels
    # =====================
    "CalendarLabel",
    "AppointmentLabel",

    # =====================
    # Calendar Feed (iCal)
    # =====================
    "CalendarFeedToken",

    # =====================
    # Post-Appointment Surveys
    # =====================
    "AppointmentSurvey",

    # =====================
    # Reschedule History
    # =====================
    "RescheduleHistory",

    # =====================
    # Appointment Locations
    # =====================
    "AppointmentLocation",

    # =====================
    # Cancellation Policy
    # =====================
    "CancellationPolicy",

    # =====================
    # Application Completion Orchestrator (ACO)
    # =====================
    "ApplicationCompletenessReview",
    "MissingItem",
    "DocumentStagingRequest",
    "BorrowerCommunicationLog",
    "AppointmentCoordination",
    "ApplicationScoreHistory",
    "ReviewStatus",
    "ComplexityLevel",
    "NextAction",
    "MissingItemType",
    "MissingItemSeverity",
    "MissingItemStatus",
    "ResolutionMethod",
    "DocStagingStatus",
    "CommChannel",
    "SenderType",
    "MessageIntent",
    "BookingStatus",
    "ScoreChangeReason",
    "ActorType",

    # =====================
    # Smart Scheduler
    # =====================
    "SchedulerConfig",
    "AvailabilitySlot",
    "SchedulerAppointmentType",
    "SchedulerAppointment",
    "SchedulerRoutingRule",
    "BlockedTime",
    "BookingLink",
    "SchedulerAppointmentReminder",
    "AppointmentStatusHistory",
    "SchedulerAuditLog",
    "SlotHold",

    # =====================
    # Agent Performance Metrics
    # =====================
    "AgentInvocation",

    # =====================
    # Compliance Decision Audit Log
    # =====================
    "ComplianceDecisionLog",

    # =====================
    # Consent Audit Trail
    # =====================
    "ConsentAuditLog",

    # =====================
    # SMS Persistence
    # =====================
    "SMSCampaignRecord",
    "ScheduledSMSJobRecord",

    # =====================
    # Morning Briefing
    # =====================
    "MorningBriefing",

    # =====================
    # Security Training (SOC 2 CC1.4)
    # =====================
    "SecurityTrainingRecord",

    # =====================
    # SMS Delivery & Panel
    # =====================
    "SMSDeliveryLog",
    "SMSPanelMessage",

    # =====================
    # Voice Consent (TCPA)
    # =====================
    "VoiceConsent",
    "VoiceConsentAudit",

    # =====================
    # Password Policy (SOC 2 CC6.1)
    # =====================
    "PasswordHistory",
    "LoginAttempt",

    # =====================
    # Partner Portal
    # =====================
    "PartnerSession",
    "PreApprovalLetterRequest",

    # =====================
    # iMessage / BlueBubbles
    # =====================
    "IMessageLine",
    "IMessageThread",
    "IMessageMessage",
    "IMessageLookupCache",
    "IMessageWebhookLog",

    # =====================
    # Team Chat
    # =====================
    "TeamChatChannel",
    "TeamChatMessage",
    "TeamChatReaction",
    "TeamChatRead",
    "TeamChatAuthorKind",
    "TeamChatAgentSlug",
    "TeamChatReactionEmoji",

    # =====================
    # Client File Aggregate
    # =====================
    "ClientFile",
    "ClientFileCollaborator",

    # =====================
    # Aria Campaign (Mass Text Outreach)
    # =====================
    "AriaCampaign",
    "AriaCampaignRecipient",

    # =====================
    # GDPR Erasure Requests
    # =====================
    "ErasureRequest",

    # =====================
    # Loan Officer License (SAFE Act)
    # =====================
    "LoanOfficerLicense",
    "LicenseStatus",
    "LicenseType",

    # =====================
    # Briefing Thread (morning briefing reply state machine)
    # =====================
    "BriefingThread",
    "BriefingTask",
    "BriefingAuditLog",

    # =====================
    # Contact Card
    # =====================
    "ContactCardMember",

    # =====================
    # AI Cost Records
    # =====================
    "AICostRecord",

    # =====================
    # Builder Application
    # =====================
    "BuilderApplication",
    "BuilderDocument",

    # =====================
    # Rate Watch
    # =====================
    "RateWatchRunLog",
    "RateObservation",
    "RateMarginConfig",
    "BorrowerTargetRate",
    "RefiOpportunityEvent",
]
