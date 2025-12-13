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
    'ToolRiskLevel'
]
