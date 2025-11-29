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

__all__ = [
    'LeadProfile',
    'ActiveLoanProfile',
    'MUMClientProfile',
    'TeamMemberProfile',
    'EmailInteraction',
    'FieldUpdateHistory',
    'DataConflict',
    # SLA Tracking
    'SLAMeasure',
    'LoanMilestoneHistory',
    'SLAPerformanceSnapshot',
    'SLAAlert',
    'SLAEfficiencyReport',
    'TimeUnit',
    'SLAStatus',
    'MilestoneType',
    'AlertStatus'
]
