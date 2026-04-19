"""
Database Models Package
Complete CRM data models for all profile types
"""

from .lead_profile import LeadProfile
from .active_loan_profile import ActiveLoanProfile
from .mum_client_profile import MUMClientProfile
from .team_member_profile import TeamMemberProfile
from .email_interaction import EmailInteraction
from .field_update_history import FieldUpdateHistory
from .data_conflict import DataConflict
from .user_integration import UserIntegration
from .sla_tracking import (
    SLAMeasure,
    LoanMilestoneHistory,
    SLAPerformanceSnapshot,
    SLAAlert,
    SLAEfficiencyReport,
    TimeUnit,
    SLAStatus,
    MilestoneType,
    AlertStatus
)
from .agent_governance import (
    AgentProfile,
    AgentTool,
    AgentExecution,
    GymTestScenario,
    GymTestRun,
    GymTestResult,
    AgentAlert as AgentGovernanceAlert,
    AgentMetricsTimeseries,
    AgentChatSession,
    AgentChatMessage,
    # Enums
    AgentStatus,
    HealthStatus,
    RiskTier,
    ExecutionStatus,
    AlertSeverity,
    TestStatus,
    ToolCategory,
    ToolRiskLevel
)
from .microsite import (
    MicrositeTemplatePack,
    MicrositePage,
    MicrositeAsset,
    MicrositePublishHistory,
    MicrositeAnalyticsEvent,
    MicrositeLead,
    OrganizationMicrositeSettings,
    # Enums
    MicrositeStatus,
    TemplateStatus,
    PublishAction,
    AssetType,
    AnalyticsEventType,
    LeadStatus,
    IntentType,
    # Utilities
    MicrositeSlugGenerator,
    ContentValidator
)

__all__ = [
    'LeadProfile',
    'ActiveLoanProfile',
    'MUMClientProfile',
    'TeamMemberProfile',
    'EmailInteraction',
    'FieldUpdateHistory',
    'DataConflict',
    'UserIntegration',
    # SLA Tracking
    'SLAMeasure',
    'LoanMilestoneHistory',
    'SLAPerformanceSnapshot',
    'SLAAlert',
    'SLAEfficiencyReport',
    'TimeUnit',
    'SLAStatus',
    'MilestoneType',
    'AlertStatus',
    # Agent Governance
    'AgentProfile',
    'AgentTool',
    'AgentExecution',
    'GymTestScenario',
    'GymTestRun',
    'GymTestResult',
    'AgentGovernanceAlert',
    'AgentMetricsTimeseries',
    'AgentChatSession',
    'AgentChatMessage',
    'AgentStatus',
    'HealthStatus',
    'RiskTier',
    'ExecutionStatus',
    'AlertSeverity',
    'TestStatus',
    'ToolCategory',
    'ToolRiskLevel',
    # Microsite Platform
    'MicrositeTemplatePack',
    'MicrositePage',
    'MicrositeAsset',
    'MicrositePublishHistory',
    'MicrositeAnalyticsEvent',
    'MicrositeLead',
    'OrganizationMicrositeSettings',
    'MicrositeStatus',
    'TemplateStatus',
    'PublishAction',
    'AssetType',
    'AnalyticsEventType',
    'LeadStatus',
    'IntentType',
    'MicrositeSlugGenerator',
    'ContentValidator'
]

from .sms_models import (
    SMSOptOut,
    SMSConsent,
    SMSComplianceLog,
    SMSRateLimitLog,
    SMSQueue,
    SMSConversation,
    SMSDeliveryLog,
)
# Backward compat alias
SMSRateLimit = SMSRateLimitLog

# Eagerly import submodules so `from models.X import Y` works even after
# models/__init__.py is partially loaded by conftest/main import chains.
from . import smart_docs_models as smart_docs_models  # noqa: F401
