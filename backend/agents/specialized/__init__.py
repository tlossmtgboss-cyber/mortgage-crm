"""
Perennia AI - Specialized Agent Tools

This module contains 32 specialized AI agents with 329+ tools designed
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

EXTENDED AGENTS (24):
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
24. Document Intelligence Agent - AI-powered document classification, review, income calculation
25. Document Follow-Up Agent - Multi-channel document follow-up campaigns, urgency, escalation
26. Document Review Agent - Deep document review, fraud detection, risk scoring, and underwriting condition generation
27. Income Analysis Agent - Income calculation, DTI, trending, gap detection, gross-up, and underwriter findings
28. Document Lifecycle Agent - End-to-end document journey orchestration from request to approval
29. Processor Productivity Agent - Processor workflow optimization, priority queues, batch approval, submission checklists
30. Borrower Experience Agent - Borrower document journey optimization, sentiment, TCPA-compliant comms
31. QC Audit Agent - Pre-funding/post-closing QC, defect tracking, repurchase risk, investor overlay compliance
32. Document Security Agent - Document security monitoring, encryption enforcement, breach response, and privacy compliance
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
from .document_intelligence_agent import DocumentIntelligenceAgent
from .document_followup_agent import DocumentFollowUpAgent
from .document_review_agent import DocumentReviewAgent
from .income_analysis_agent import IncomeAnalysisAgent
from .document_lifecycle_agent import DocumentLifecycleAgent
from .processor_productivity_agent import ProcessorProductivityAgent
from .borrower_experience_agent import BorrowerExperienceAgent
from .qc_audit_agent import QCAuditAgent
from .document_security_agent import DocumentSecurityAgent
from .doc_compliance_agent import DocComplianceAgent

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
    "DocumentIntelligenceAgent",
    "DocumentFollowUpAgent",
    "DocumentReviewAgent",
    "IncomeAnalysisAgent",
    "DocumentLifecycleAgent",
    "ProcessorProductivityAgent",
    "BorrowerExperienceAgent",
    "QCAuditAgent",
    "DocumentSecurityAgent",
    "DocComplianceAgent",
]

# Agent count for verification
AGENT_COUNT = 33
TOOL_COUNT = 344  # 33 agents × ~10.4 tools average
