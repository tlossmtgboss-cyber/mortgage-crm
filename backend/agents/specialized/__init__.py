"""
Perennia AI - Specialized Agent Tools

This module contains 8 specialized AI agents with 64 tools designed
for mortgage CRM operations:

1. Lead Management Agent - Lead lifecycle and conversion tools
2. Loan Pipeline Agent - Active loan monitoring and management
3. Task & Calendar Agent - Scheduling and task management
4. Communication Agent - Email, SMS, and notification handling
5. Document Agent - Document processing and management
6. Analytics Agent - Reporting and insights generation
7. Portfolio Agent - Post-close client management
8. Compliance Agent - Regulatory compliance monitoring
"""

from .base import SpecializedAgent, AgentTool
from .lead_agent import LeadManagementAgent
from .loan_agent import LoanPipelineAgent
from .task_agent import TaskCalendarAgent
from .communication_agent import CommunicationAgent
from .document_agent import DocumentAgent
from .analytics_agent import AnalyticsAgent
from .portfolio_agent import PortfolioAgent
from .compliance_agent import ComplianceAgent

__all__ = [
    # Base classes
    "SpecializedAgent",
    "AgentTool",
    # Specialized agents
    "LeadManagementAgent",
    "LoanPipelineAgent",
    "TaskCalendarAgent",
    "CommunicationAgent",
    "DocumentAgent",
    "AnalyticsAgent",
    "PortfolioAgent",
    "ComplianceAgent",
]
