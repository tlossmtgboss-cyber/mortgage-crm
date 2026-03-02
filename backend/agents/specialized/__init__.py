"""
Perennia AI - Specialized Agent Tools

This module contains 23 specialized AI agents with 194+ tools designed
for mortgage CRM operations:

CORE CRM AGENTS (8):
1. Lead Management Agent - Lead lifecycle and conversion tools
2. Loan Pipeline Agent - Active loan monitoring and management
3. Task & Calendar Agent - Scheduling and task management
4. Communication Agent - Email, SMS, and notification handling
5. Document Agent - Document processing and management
6. Analytics Agent - Reporting and insights generation
7. Portfolio Agent - Post-close client management
8. Compliance Agent - Regulatory compliance monitoring

EXTENDED AGENTS (15):
9. Receptionist Agent - AI voice/chat receptionist
10. Profitability Agent - Loan and branch profitability analysis
11. Subscription Agent - SaaS subscription and billing management
12. Onboarding Agent - New user onboarding and training
13. Voice Agent - Voice command processing
14. Coaching Agent - LO performance coaching
15. SLA Agent - SLA tracking and milestone monitoring
16. Email Intel Agent - Email parsing and intelligence
17. Scheduler Agent - Smart calendar and meeting scheduling
18. Video Agent - Video meeting intelligence (UVIP)
19. Integrations Agent - Third-party integration management
20. Rate Advisor Agent - Rate lock and pricing advice
21. Salesforce Agent - Salesforce integration and bidirectional sync
22. Content Marketing Agent - Content calendars, carousels, SEO, publishing
23. Ops Manager Agent - Proactive pipeline patrol and impediment detection
"""

from .base import SpecializedAgent, AgentTool, AgentRegistry, ToolCategory, RiskLevel, ToolResult

# Core CRM Agents
from .lead_agent import LeadManagementAgent
from .loan_agent import LoanPipelineAgent
from .task_agent import TaskCalendarAgent
from .communication_agent import CommunicationAgent
from .document_agent import DocumentAgent
from .analytics_agent import AnalyticsAgent
from .portfolio_agent import PortfolioAgent
from .compliance_agent import ComplianceAgent

# Extended Agents
from .receptionist_agent import ReceptionistAgent
from .profitability_agent import ProfitabilityAgent
from .subscription_agent import SubscriptionAgent
from .onboarding_agent import OnboardingAgent
from .voice_agent import VoiceAgent
from .coaching_agent import CoachingAgent
from .sla_agent import SLAAgent
from .email_intel_agent import EmailIntelAgent
from .scheduler_agent import SchedulerAgent
from .video_agent import VideoAgent
from .integrations_agent import IntegrationsAgent
from .rate_advisor_agent import RateAdvisorAgent
from .salesforce_agent import SalesforceAgent
from .content_marketing_agent import ContentMarketingAgent
from .ops_manager_agent import OpsManagerAgent

__all__ = [
    # Base classes
    "SpecializedAgent",
    "AgentTool",
    "AgentRegistry",
    "ToolCategory",
    "RiskLevel",
    "ToolResult",

    # Core CRM Agents (8)
    "LeadManagementAgent",
    "LoanPipelineAgent",
    "TaskCalendarAgent",
    "CommunicationAgent",
    "DocumentAgent",
    "AnalyticsAgent",
    "PortfolioAgent",
    "ComplianceAgent",

    # Extended Agents (15)
    "ReceptionistAgent",
    "ProfitabilityAgent",
    "SubscriptionAgent",
    "OnboardingAgent",
    "VoiceAgent",
    "CoachingAgent",
    "SLAAgent",
    "EmailIntelAgent",
    "SchedulerAgent",
    "VideoAgent",
    "IntegrationsAgent",
    "RateAdvisorAgent",
    "SalesforceAgent",
    "ContentMarketingAgent",
    "OpsManagerAgent",
]

# Agent count for verification
AGENT_COUNT = 23
TOOL_COUNT = 194  # 23 agents × ~8.4 tools average
