"""
Health & System Status Routes

Root, health check, and system status endpoints.
Extracted from inline_legacy_routes.py.
"""
from fastapi import Depends, Request
from fastapi.responses import JSONResponse, HTMLResponse
from sqlalchemy.orm import Session
from sqlalchemy import text
from datetime import datetime, timezone
import logging
import time

logger = logging.getLogger(__name__)

# Record application start time at module load for uptime calculation
_APP_START_TIME = time.monotonic()
_APP_START_TIMESTAMP = datetime.now(timezone.utc)


def register_health_routes(app, get_db, **kwargs):
    """Register health and system status routes.

    Args:
        app: FastAPI application instance
        get_db: Database session dependency
        **kwargs: Additional dependencies:
            - health_checker: HealthChecker instance from production_hardening
            - SessionLocal: SQLAlchemy session factory (for direct connections)
    """
    health_checker = kwargs.get('health_checker')
    SessionLocal = kwargs.get('SessionLocal')

    # ========================================================================
    # Root endpoint (line ~14070 in inline_legacy_routes.py)
    # ========================================================================

    @app.get("/")
    async def root():
        return {
            "message": "Agentic AI Mortgage CRM - Full Stack",
            "version": "4.0.0",
            "status": "operational",
            "features": ["AI Automation", "Lead Management", "Loan Pipeline", "Analytics", "Coaching"],
            "docs": "/docs",
            "health": "/health"
        }

    # ========================================================================
    # PRD HTML page (lines ~14081-14727 in inline_legacy_routes.py)
    # ========================================================================

    @app.get("/prd", response_class=HTMLResponse)
    async def get_prd():
        """Serve the Product Requirements Document as a styled HTML page."""
        prd_content = """
    # Perennia AI - Product Requirements Document
    ## Intelligent Mortgage CRM Platform

    **Version:** 1.0  |  **Date:** December 2025  |  **Status:** Production Ready

    ---

    ## Executive Summary

    Perennia AI is a next-generation mortgage CRM platform that combines comprehensive loan origination management with advanced AI automation. The platform empowers loan officers to close more loans faster by automating routine tasks, providing intelligent coaching, and delivering actionable insights across the entire mortgage lifecycle.

    **Key Value Proposition:** Perennia AI reduces loan officer administrative burden by up to 60% through AI-powered automation while improving compliance, customer communication, and pipeline visibility.

    ---

    ## Market Opportunity

    ### Problem Statement
    Mortgage loan officers spend an estimated 60-70% of their time on administrative tasks:
    - Manual data entry and document collection
    - Email triage and response management
    - Pipeline tracking and status updates
    - Compliance documentation and audit trails
    - Scheduling and follow-up coordination

    This leaves only 30-40% of time for revenue-generating activities: client relationships, lead nurturing, and loan consultation.

    ### Solution
    Perennia AI automates these administrative workflows through:
    - **AI Email Processing** - Automatic classification, routing, and response drafting
    - **Intelligent Document Management** - OCR extraction, auto-filing, and condition tracking
    - **Smart Pipeline Management** - Predictive analytics and proactive alerts
    - **Automated Communications** - Multi-channel outreach with personalization
    - **Compliance Automation** - Real-time monitoring and audit trail generation

    ---

    ## Product Architecture

    ### Technology Stack
    - **Backend:** Python/FastAPI with async processing
    - **Database:** PostgreSQL with advanced analytics views
    - **AI/ML:** LangChain + Anthropic Claude for natural language processing
    - **Integrations:** Microsoft Graph API, Telnyx, various LOS systems
    - **Mobile:** React Native/Expo (cross-platform iOS/Android)
    - **Deployment:** Railway with automatic scaling

    ### Multi-Agent AI System
    Perennia AI employs a sophisticated multi-agent architecture with **20 specialized AI agents** and **160+ integrated tools**:

    | Agent | Purpose | Key Capabilities |
    |-------|---------|------------------|
    | Pipeline Analyst | Pipeline management | Metrics, forecasting, bottleneck detection |
    | Compliance Checker | Regulatory compliance | TRID/RESPA checks, fair lending analysis |
    | Lead Nurturer | Lead management | Scoring, engagement tracking, follow-up |
    | Document Tracker | Document management | Collection tracking, condition monitoring |
    | Communication Hub | Multi-channel comms | Email, SMS, voice coordination |
    | Rate Monitor | Rate intelligence | Lock recommendations, market alerts |
    | Client Advisor | Borrower support | Loan guidance, scenario analysis |
    | Team Coach | Performance coaching | Training, goal tracking, motivation |
    | Data Analyst | Analytics | Reporting, trend analysis, KPIs |
    | Marketing Manager | Campaign management | Lead generation, ROI tracking |
    | Quality Controller | Quality assurance | File audits, pre-submission checks |
    | Underwriting Assistant | UW support | Guideline checks, condition prep |
    | Closing Coordinator | Closing management | Timeline tracking, party coordination |
    | Post-Close Manager | Servicing prep | Transfer coordination, retention |
    | Branch Manager | Multi-office oversight | Team management, P&L analysis |
    | Vendor Manager | Third-party coordination | Appraisal, title, insurance tracking |
    | Training Specialist | Onboarding & training | Skill assessment, learning paths |
    | Innovation Scout | Industry monitoring | Tech trends, competitive analysis |
    | Executive Assistant | Productivity | Scheduling, task management |
    | Crisis Manager | Issue resolution | Escalation handling, recovery |

    ---

    ## Core Features

    ### 1. Intelligent CRM

    #### Lead Management
    - **Smart Lead Scoring** - AI-powered scoring based on engagement, profile, and intent signals
    - **Automated Lead Routing** - Rules-based assignment with load balancing
    - **Engagement Tracking** - Full history across email, SMS, phone, and web
    - **Nurture Campaigns** - Automated multi-touch sequences with personalization
    - **Source Attribution** - Track lead sources and campaign ROI

    #### Contact Management
    - **360-Degree View** - Complete borrower profile with all interactions
    - **Relationship Mapping** - Track referral sources, partners, past clients
    - **Communication Preferences** - Channel and timing preferences
    - **Document Portal** - Secure document upload for borrowers

    #### Pipeline Management
    - **Visual Pipeline** - Kanban-style loan tracking with drag-and-drop
    - **Stage Automation** - Automatic status updates based on milestones
    - **SLA Monitoring** - Real-time alerts for aging loans
    - **Forecasting** - AI-predicted close dates and probability
    - **Bottleneck Detection** - Identify and resolve pipeline blockages

    ### 2. AI-Powered Email Processing

    #### Email Intelligence
    - **Automatic Classification** - Categorize emails by intent (document submission, status inquiry, urgent request, etc.)
    - **Entity Extraction** - Identify borrowers, loan numbers, dates, amounts
    - **Smart Routing** - Route to appropriate team member or workflow
    - **Priority Scoring** - Surface urgent items requiring immediate attention

    #### Email Response Training System
    - **Learning from User Behavior** - AI learns from approved/rejected responses
    - **Pattern Recognition** - Build patterns from sender domains, subjects, intents
    - **Confidence Scoring** - Track accuracy with approval/rejection ratios
    - **Auto-Execute Capability** - High-confidence responses sent automatically (95% threshold)
    - **Human-in-the-Loop** - All actions reviewable and trainable

    #### Response Queue
    - **Pending Review Dashboard** - See all emails awaiting response
    - **AI Draft Responses** - Pre-generated responses ready for approval
    - **One-Click Actions** - Approve, reject, or modify AI recommendations
    - **Bulk Processing** - Handle multiple similar emails efficiently

    ### 3. Document Management

    #### Document Collection
    - **Smart Document Requests** - Generate personalized checklists
    - **Status Tracking** - Real-time visibility into document status
    - **Automated Reminders** - Multi-channel follow-up for missing docs
    - **Expiration Alerts** - Track document validity periods

    #### AI Document Processing
    - **OCR Extraction** - Extract data from uploaded documents
    - **Auto-Classification** - Categorize documents by type
    - **Data Validation** - Verify extracted data against loan file
    - **Condition Mapping** - Link documents to underwriting conditions

    ### 4. Communication Hub

    #### Multi-Channel Outreach
    - **Email Integration** - Microsoft 365 / Graph API integration
    - **SMS Messaging** - Two-way texting with templates
    - **Voice Calls** - Click-to-call with call logging
    - **Video Meetings** - Integrated scheduling and links

    #### Communication Automation
    - **Drip Campaigns** - Automated nurture sequences
    - **Milestone Notifications** - Automatic status updates to borrowers
    - **Appointment Reminders** - Reduce no-shows with smart reminders
    - **Team Collaboration** - Internal messaging and handoffs

    ### 5. Compliance & Audit

    #### Regulatory Compliance
    - **TRID Monitoring** - Loan Estimate and Closing Disclosure timing
    - **RESPA Compliance** - Fee tolerance and affiliated business tracking
    - **Fair Lending Analysis** - Rate and term disparity detection
    - **State Requirements** - State-specific rule enforcement

    #### Audit & Reporting
    - **Compliance Scorecards** - Real-time compliance health
    - **Audit Trail** - Complete activity logging
    - **Exception Reporting** - Surface compliance risks
    - **Regulatory Reporting** - HMDA and other required reports

    ### 6. Analytics & Reporting

    #### Dashboards
    - **Executive Dashboard** - High-level KPIs and trends
    - **Pipeline Dashboard** - Real-time pipeline health
    - **Individual Performance** - LO scorecards and goals
    - **Team Analytics** - Branch and team comparisons

    #### AI Insights
    - **Predictive Analytics** - Close probability and timing
    - **Anomaly Detection** - Unusual patterns and risks
    - **Recommendations** - AI-suggested actions
    - **Benchmarking** - Compare to company/industry averages

    ### 7. Mobile Application

    #### Cross-Platform Mobile App (React Native/Expo)
    - **iOS & Android** - Single codebase, native performance
    - **Real-Time Sync** - Instant updates across devices
    - **Offline Capability** - Work without connectivity
    - **Push Notifications** - Instant alerts for important events

    #### Mobile Features
    - **Pipeline View** - See and manage loans on-the-go
    - **Quick Actions** - One-tap common operations
    - **Document Capture** - Camera-based document upload
    - **Contact Access** - Full CRM from mobile

    ---

    ## Competitive Advantages

    ### 1. AI-First Architecture
    Unlike legacy CRMs with bolt-on AI features, Perennia AI was built from the ground up with AI at its core:
    - Multi-agent system for specialized tasks
    - Learning algorithms that improve with use
    - Natural language interface for complex queries
    - Predictive capabilities throughout the platform

    ### 2. Email Response Training
    Unique "learning by doing" approach to email automation:
    - System learns from every user approval/rejection
    - Builds personalized response patterns per user
    - Achieves 95%+ confidence before auto-executing
    - Continuously improves accuracy over time

    ### 3. Comprehensive Integration
    Deep integrations across the mortgage ecosystem:
    - Microsoft 365 for email/calendar
    - Major LOS platforms
    - Third-party vendors
    - Communication providers

    ### 4. Compliance by Design
    Built-in compliance monitoring vs. add-on compliance tools:
    - Real-time TRID/RESPA checking
    - Automatic audit trails
    - Fair lending analysis
    - State-specific rule enforcement

    ---

    ## Key Metrics & Results

    ### Productivity Gains
    - **60% reduction** in email processing time
    - **45% faster** document collection
    - **30% improvement** in response times
    - **25% increase** in loans per LO

    ### Quality Improvements
    - **95%+ accuracy** in AI email classification
    - **99.5%** compliance check accuracy
    - **40% reduction** in condition re-requests
    - **50% fewer** compliance exceptions

    ### Business Impact
    - **20% improvement** in lead conversion
    - **15% faster** average cycle time
    - **35% reduction** in fallout rate
    - **3x ROI** within first year

    ---

    ## Pricing Model

    | Tier | Users | Price/User/Month | Features |
    |------|-------|-----------------|----------|
    | Starter | 1-5 | $149 | Core CRM, Basic AI |
    | Professional | 6-25 | $199 | Full AI, Integrations |
    | Enterprise | 26+ | Custom | White-label, API access |

    ---

    ## Target Market

    ### Primary: Independent Mortgage Brokers
    - 5-50 loan officers
    - $50M-$500M annual volume
    - Technology-forward mindset
    - Growth-oriented

    ### Secondary: Small-to-Mid Banks/Credit Unions
    - In-house mortgage operations
    - Compliance-sensitive
    - Need efficiency gains

    ---

    ## Investment Thesis

    ### Market Size
    - **TAM:** $8.5B mortgage technology market
    - **SAM:** $2.1B CRM/automation segment
    - **SOM:** $210M initial target market

    ### Growth Drivers
    1. **Labor Shortage** - Fewer LOs, need more efficiency
    2. **Compliance Burden** - Increasing regulatory requirements
    3. **AI Adoption** - Industry ready for intelligent automation
    4. **Remote Work** - Need for digital-first workflows

    ### Competitive Moat
    1. **AI Learning System** - Improves with every interaction
    2. **Multi-Agent Architecture** - Difficult to replicate
    3. **Integration Depth** - Deep workflow connections
    4. **Data Network Effects** - Better predictions with more data

    ---

    *Perennia AI - Intelligent Mortgage CRM*

    *Document prepared for investor discussions. Confidential.*
    """

        # Convert markdown to styled HTML
        html = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Perennia AI - Intelligent Mortgage Production Manager</title>
        <style>
            * {{
                margin: 0;
                padding: 0;
                box-sizing: border-box;
            }}
            body {{
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif;
                line-height: 1.7;
                color: #1a1a2e;
                background: #ffffff;
                min-height: 100vh;
                padding: 40px 20px;
            }}
            .container {{
                max-width: 900px;
                margin: 0 auto;
                background: white;
                padding: 60px;
            }}
            h1 {{
                font-size: 2.5em;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                -webkit-background-clip: text;
                -webkit-text-fill-color: transparent;
                background-clip: text;
                margin-bottom: 10px;
            }}
            h2 {{
                font-size: 1.4em;
                color: #764ba2;
                margin-bottom: 25px;
                font-weight: 500;
            }}
            h2.section {{
                font-size: 1.8em;
                color: #1a1a2e;
                margin-top: 50px;
                margin-bottom: 20px;
                padding-bottom: 10px;
                border-bottom: 3px solid #667eea;
            }}
            h3 {{
                font-size: 1.3em;
                color: #333;
                margin-top: 30px;
                margin-bottom: 15px;
            }}
            h4 {{
                font-size: 1.1em;
                color: #555;
                margin-top: 20px;
                margin-bottom: 10px;
            }}
            .meta {{
                color: #666;
                font-size: 0.95em;
                margin-bottom: 30px;
            }}
            .highlight-box {{
                background: linear-gradient(135deg, #f5f7fa 0%, #e4e8eb 100%);
                border-left: 4px solid #667eea;
                padding: 20px 25px;
                margin: 25px 0;
                border-radius: 0 10px 10px 0;
            }}
            .highlight-box strong {{
                color: #764ba2;
            }}
            p {{
                margin-bottom: 15px;
                color: #444;
            }}
            ul {{
                margin: 15px 0 15px 25px;
            }}
            li {{
                margin-bottom: 8px;
                color: #444;
            }}
            table {{
                width: 100%;
                border-collapse: collapse;
                margin: 25px 0;
                font-size: 0.95em;
            }}
            th {{
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                padding: 15px;
                text-align: left;
                font-weight: 600;
            }}
            td {{
                padding: 12px 15px;
                border-bottom: 1px solid #eee;
            }}
            tr:hover td {{
                background: #f8f9ff;
            }}
            .metric {{
                display: inline-block;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                padding: 8px 15px;
                border-radius: 20px;
                margin: 5px 5px 5px 0;
                font-weight: 600;
            }}
            hr {{
                border: none;
                height: 2px;
                background: linear-gradient(to right, #667eea, #764ba2);
                margin: 40px 0;
            }}
            .footer {{
                text-align: center;
                margin-top: 50px;
                padding-top: 30px;
                border-top: 1px solid #eee;
                color: #888;
                font-style: italic;
            }}
            .agents-grid {{
                display: grid;
                grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
                gap: 15px;
                margin: 20px 0;
            }}
            .agent-card {{
                background: #f8f9ff;
                padding: 15px;
                border-radius: 10px;
                border: 1px solid #e0e5ff;
            }}
            .agent-card strong {{
                color: #667eea;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>Perennia AI</h1>
            <h2>Intelligent Mortgage Production Manager</h2>
            <p class="meta"><strong>Version:</strong> 1.0 &nbsp;|&nbsp; <strong>Date:</strong> December 2025 &nbsp;|&nbsp; <strong>Status:</strong> Production Ready</p>

            <hr>

            <h2 class="section">Executive Summary</h2>
            <p>Perennia AI is an intelligent mortgage production management platform that combines comprehensive loan origination, pipeline optimization, and profitability tracking with advanced AI automation. The platform empowers mortgage professionals to maximize production efficiency, increase profitability, and close more loans faster through intelligent workflow automation, real-time analytics, and AI-driven coaching.</p>

            <div class="highlight-box">
                <strong>Key Value Proposition:</strong> Perennia AI transforms mortgage operations by reducing administrative burden by up to 60%, optimizing loan cycle times, maximizing per-loan profitability, and providing complete visibility across the entire production pipeline.
            </div>

            <h2 class="section">Market Opportunity</h2>
            <h3>Problem Statement</h3>
            <p>Mortgage loan officers spend an estimated 60-70% of their time on administrative tasks:</p>
            <ul>
                <li>Manual data entry and document collection</li>
                <li>Email triage and response management</li>
                <li>Pipeline tracking and status updates</li>
                <li>Compliance documentation and audit trails</li>
                <li>Scheduling and follow-up coordination</li>
            </ul>
            <p>This leaves only 30-40% of time for revenue-generating activities.</p>

            <h3>Solution</h3>
            <ul>
                <li><strong>AI Email Processing</strong> - Automatic classification, routing, and response drafting</li>
                <li><strong>Intelligent Document Management</strong> - OCR extraction, auto-filing, and condition tracking</li>
                <li><strong>Smart Pipeline Management</strong> - Predictive analytics and proactive alerts</li>
                <li><strong>Automated Communications</strong> - Multi-channel outreach with personalization</li>
                <li><strong>Compliance Automation</strong> - Real-time monitoring and audit trail generation</li>
            </ul>

            <h2 class="section">Product Architecture</h2>
            <h3>Technology Stack</h3>
            <ul>
                <li><strong>Backend:</strong> Python/FastAPI with async processing</li>
                <li><strong>Database:</strong> PostgreSQL with advanced analytics views</li>
                <li><strong>AI/ML:</strong> LangChain + Anthropic Claude for natural language processing</li>
                <li><strong>Integrations:</strong> Microsoft Graph API, Telnyx, various LOS systems</li>
                <li><strong>Mobile:</strong> React Native/Expo (cross-platform iOS/Android)</li>
                <li><strong>Deployment:</strong> Railway with automatic scaling</li>
            </ul>

            <h3>Multi-Agent AI System</h3>
            <p>Perennia AI employs a sophisticated multi-agent architecture with <strong>20 specialized AI agents</strong> and <strong>160+ integrated tools</strong>:</p>

            <table>
                <tr><th>Agent</th><th>Purpose</th><th>Key Capabilities</th></tr>
                <tr><td>Pipeline Analyst</td><td>Pipeline management</td><td>Metrics, forecasting, bottleneck detection</td></tr>
                <tr><td>Compliance Checker</td><td>Regulatory compliance</td><td>TRID/RESPA checks, fair lending analysis</td></tr>
                <tr><td>Lead Nurturer</td><td>Lead management</td><td>Scoring, engagement tracking, follow-up</td></tr>
                <tr><td>Document Tracker</td><td>Document management</td><td>Collection tracking, condition monitoring</td></tr>
                <tr><td>Communication Hub</td><td>Multi-channel comms</td><td>Email, SMS, voice coordination</td></tr>
                <tr><td>Rate Monitor</td><td>Rate intelligence</td><td>Lock recommendations, market alerts</td></tr>
                <tr><td>Client Advisor</td><td>Borrower support</td><td>Loan guidance, scenario analysis</td></tr>
                <tr><td>Team Coach</td><td>Performance coaching</td><td>Training, goal tracking, motivation</td></tr>
                <tr><td>Data Analyst</td><td>Analytics</td><td>Reporting, trend analysis, KPIs</td></tr>
                <tr><td>Marketing Manager</td><td>Campaign management</td><td>Lead generation, ROI tracking</td></tr>
                <tr><td>Quality Controller</td><td>Quality assurance</td><td>File audits, pre-submission checks</td></tr>
                <tr><td>Underwriting Assistant</td><td>UW support</td><td>Guideline checks, condition prep</td></tr>
                <tr><td>Closing Coordinator</td><td>Closing management</td><td>Timeline tracking, party coordination</td></tr>
                <tr><td>Post-Close Manager</td><td>Servicing prep</td><td>Transfer coordination, retention</td></tr>
                <tr><td>Branch Manager</td><td>Multi-office oversight</td><td>Team management, P&L analysis</td></tr>
                <tr><td>Vendor Manager</td><td>Third-party coordination</td><td>Appraisal, title, insurance tracking</td></tr>
                <tr><td>Training Specialist</td><td>Onboarding & training</td><td>Skill assessment, learning paths</td></tr>
                <tr><td>Innovation Scout</td><td>Industry monitoring</td><td>Tech trends, competitive analysis</td></tr>
                <tr><td>Executive Assistant</td><td>Productivity</td><td>Scheduling, task management</td></tr>
                <tr><td>Crisis Manager</td><td>Issue resolution</td><td>Escalation handling, recovery</td></tr>
            </table>

            <h2 class="section">Core Features</h2>

            <h3>1. Intelligent CRM</h3>
            <h4>Lead Management</h4>
            <ul>
                <li><strong>Smart Lead Scoring</strong> - AI-powered scoring based on engagement, profile, and intent signals</li>
                <li><strong>Automated Lead Routing</strong> - Rules-based assignment with load balancing</li>
                <li><strong>Engagement Tracking</strong> - Full history across email, SMS, phone, and web</li>
                <li><strong>Nurture Campaigns</strong> - Automated multi-touch sequences with personalization</li>
            </ul>

            <h4>Pipeline Management</h4>
            <ul>
                <li><strong>Visual Pipeline</strong> - Kanban-style loan tracking with drag-and-drop</li>
                <li><strong>Stage Automation</strong> - Automatic status updates based on milestones</li>
                <li><strong>SLA Monitoring</strong> - Real-time alerts for aging loans</li>
                <li><strong>Forecasting</strong> - AI-predicted close dates and probability</li>
            </ul>

            <h3>2. AI-Powered Email Processing</h3>
            <h4>Email Response Training System</h4>
            <ul>
                <li><strong>Learning from User Behavior</strong> - AI learns from approved/rejected responses</li>
                <li><strong>Pattern Recognition</strong> - Build patterns from sender domains, subjects, intents</li>
                <li><strong>Confidence Scoring</strong> - Track accuracy with approval/rejection ratios</li>
                <li><strong>Auto-Execute Capability</strong> - High-confidence responses sent automatically (95% threshold)</li>
                <li><strong>Human-in-the-Loop</strong> - All actions reviewable and trainable</li>
            </ul>

            <h3>3. Document Management</h3>
            <ul>
                <li><strong>Smart Document Requests</strong> - Generate personalized checklists</li>
                <li><strong>OCR Extraction</strong> - Extract data from uploaded documents</li>
                <li><strong>Auto-Classification</strong> - Categorize documents by type</li>
                <li><strong>Automated Reminders</strong> - Multi-channel follow-up for missing docs</li>
            </ul>

            <h3>4. Communication Hub</h3>
            <ul>
                <li><strong>Email Integration</strong> - Microsoft 365 / Graph API integration</li>
                <li><strong>SMS Messaging</strong> - Two-way texting with templates</li>
                <li><strong>Voice Calls</strong> - Click-to-call with call logging</li>
                <li><strong>Video Meetings</strong> - Integrated scheduling and links</li>
            </ul>

            <h3>5. Compliance & Audit</h3>
            <ul>
                <li><strong>TRID Monitoring</strong> - Loan Estimate and Closing Disclosure timing</li>
                <li><strong>RESPA Compliance</strong> - Fee tolerance and affiliated business tracking</li>
                <li><strong>Fair Lending Analysis</strong> - Rate and term disparity detection</li>
                <li><strong>Audit Trail</strong> - Complete activity logging</li>
            </ul>

            <h3>6. Loan Efficiency Management</h3>
            <ul>
                <li><strong>Cycle Time Analytics</strong> - Track time-in-stage and identify bottlenecks</li>
                <li><strong>SLA Monitoring</strong> - Real-time alerts when loans exceed target timelines</li>
                <li><strong>Workflow Automation</strong> - Auto-trigger tasks based on loan milestones</li>
                <li><strong>Capacity Planning</strong> - Balance workload across team members</li>
                <li><strong>Turn Time Optimization</strong> - AI recommendations to accelerate closings</li>
            </ul>

            <h3>7. Profitability Management</h3>
            <ul>
                <li><strong>Loan-Level P&L</strong> - Track revenue, costs, and margin per loan</li>
                <li><strong>Commission Tracking</strong> - Automated commission calculations and splits</li>
                <li><strong>Cost Analysis</strong> - Monitor origination costs and overhead allocation</li>
                <li><strong>Revenue Forecasting</strong> - Predict income based on pipeline and close rates</li>
                <li><strong>Profitability Dashboards</strong> - Real-time visibility into financial performance</li>
                <li><strong>Margin Optimization</strong> - AI-driven pricing recommendations</li>
            </ul>

            <h3>8. Partner Management</h3>
            <ul>
                <li><strong>Referral Partner Portal</strong> - Self-service access for realtors and builders</li>
                <li><strong>Partner Performance Tracking</strong> - Monitor referral volume and conversion rates</li>
                <li><strong>Co-Marketing Tools</strong> - Branded materials and campaign coordination</li>
                <li><strong>Commission Sharing</strong> - Automated referral fee calculations</li>
                <li><strong>Partner Communication</strong> - Automated status updates to referral sources</li>
                <li><strong>Relationship Scoring</strong> - Identify top-performing partnerships</li>
            </ul>

            <h3>9. Mobile Application</h3>
            <ul>
                <li><strong>iOS & Android</strong> - Cross-platform React Native/Expo app</li>
                <li><strong>Real-Time Sync</strong> - Instant updates across devices</li>
                <li><strong>Document Capture</strong> - Camera-based document upload</li>
                <li><strong>Push Notifications</strong> - Instant alerts for important events</li>
            </ul>

            <h2 class="section">Competitive Advantages</h2>
            <ul>
                <li><strong>AI-First Architecture</strong> - Built from the ground up with AI at its core</li>
                <li><strong>Email Response Training</strong> - Unique "learning by doing" approach</li>
                <li><strong>Comprehensive Integration</strong> - Deep integrations across the mortgage ecosystem</li>
                <li><strong>Compliance by Design</strong> - Built-in compliance monitoring</li>
            </ul>

            <h2 class="section">Key Metrics & Results</h2>
            <h3>Productivity Gains</h3>
            <p>
                <span class="metric">60% reduction in email processing</span>
                <span class="metric">45% faster document collection</span>
                <span class="metric">30% improvement in response times</span>
                <span class="metric">25% increase in loans per LO</span>
            </p>

            <h3>Business Impact</h3>
            <p>
                <span class="metric">20% improvement in lead conversion</span>
                <span class="metric">15% faster cycle time</span>
                <span class="metric">35% reduction in fallout</span>
                <span class="metric">3x ROI within first year</span>
            </p>

            <div class="footer">
                <p><strong>Perennia AI</strong> - Intelligent Mortgage Production Manager</p>
                <p>Document prepared for investor discussions. Confidential.</p>
            </div>
        </div>
    </body>
    </html>
    """
        return HTMLResponse(content=html)

    # ========================================================================
    # Health check (lines ~14785-14796 in inline_legacy_routes.py)
    # ========================================================================

    @app.get("/health")
    async def health_check(db: Session = Depends(get_db)):
        """Basic health check - database connectivity"""
        try:
            db.execute(text("SELECT 1"))
            return {"status": "healthy", "database": "connected", "timestamp": datetime.now(timezone.utc), "version": "2026.01.22.1"}
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return JSONResponse(
                status_code=503,
                content={"status": "unhealthy", "error": "Internal server error"}
            )


    # ========================================================================
    # Ping endpoint (lines ~15504-15559 in inline_legacy_routes.py)
    # ========================================================================

    @app.get("/ping")
    async def ping(db: Session = Depends(get_db)):
        """Simple ping endpoint - also creates Salesforce tables if needed"""
        tables_created = []
        try:
            db.execute(text("""
                CREATE TABLE IF NOT EXISTS oauth_states (
                    id SERIAL PRIMARY KEY,
                    state_token VARCHAR(255) UNIQUE NOT NULL,
                    user_id INTEGER NOT NULL,
                    provider VARCHAR(50) NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    expires_at TIMESTAMP NOT NULL,
                    used BOOLEAN DEFAULT FALSE,
                    return_url TEXT,
                    state_metadata JSONB
                )
            """))
            db.commit()
            tables_created.append("oauth_states")
        except Exception as e:
            db.rollback()
            tables_created.append("oauth_states error: table creation failed")

        try:
            db.execute(text("""
                CREATE TABLE IF NOT EXISTS integration_profiles (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    provider VARCHAR(50) NOT NULL DEFAULT 'salesforce',
                    status VARCHAR(50) NOT NULL DEFAULT 'disconnected',
                    access_token_encrypted TEXT,
                    refresh_token_encrypted TEXT,
                    instance_url TEXT,
                    sf_org_id VARCHAR(100),
                    sf_user_id VARCHAR(100),
                    sf_username VARCHAR(255),
                    connected_at TIMESTAMP,
                    last_sync_at TIMESTAMP,
                    last_error TEXT,
                    field_map_version INTEGER DEFAULT 1,
                    sync_enabled BOOLEAN DEFAULT TRUE,
                    sync_interval_minutes INTEGER DEFAULT 15,
                    sync_direction VARCHAR(20) DEFAULT 'bidirectional',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(user_id, provider)
                )
            """))
            db.commit()
            tables_created.append("integration_profiles")
        except Exception as e:
            db.rollback()
            tables_created.append("integration_profiles error: table creation failed")

        return {"ping": "pong", "status": "ok", "tables": tables_created}

    # ========================================================================
    # API health check (lines ~15689-15700 in inline_legacy_routes.py)
    # ========================================================================

    @app.get("/api/v1/health")
    async def api_health_check(db: Session = Depends(get_db)):
        """API health check endpoint at /api/v1/health - database connectivity"""
        try:
            db.execute(text("SELECT 1"))
            return {"status": "healthy", "database": "connected", "timestamp": datetime.now(timezone.utc), "version": "2026.01.22.1"}
        except Exception as e:
            logger.error(f"API health check failed: {e}")
            return JSONResponse(
                status_code=503,
                content={"status": "unhealthy", "error": "Internal server error"}
            )

    # ========================================================================
    # Deploy test (lines ~15703-15706 in inline_legacy_routes.py)
    # ========================================================================

    @app.get("/deploy-test")
    async def deploy_test():
        """Simple endpoint to verify deployment - added 2025-12-27T22:45"""
        return {"deployed_at": "2026-01-22T09:10:00Z", "version": "2026.01.22.1", "test": "db-pool-fixes"}


    # ========================================================================
    # Debug routers (lines ~15709-15728 in inline_legacy_routes.py)
    # ========================================================================

    @app.get("/debug/routers")
    async def debug_routers():
        """Debug endpoint to check loaded routers"""
        routes = []
        for route in app.routes:
            if hasattr(route, 'path'):
                routes.append(route.path)
        scheduler_routes = [r for r in routes if 'scheduler' in r.lower()]

        # Check specifically for the public available-slots endpoint
        public_slots_exists = '/api/v1/scheduler/public/available-slots' in routes

        return {
            "total_routes": len(routes),
            "scheduler_routes_count": len(scheduler_routes),
            "scheduler_routes_sample": scheduler_routes[:30] if scheduler_routes else [],
            "smart_scheduler_loaded": any('/api/v1/scheduler/' in r for r in routes),
            "public_slots_endpoint_exists": public_slots_exists,
            "public_slots_path": "/api/v1/scheduler/public/available-slots"
        }

    # ========================================================================
    # Debug scheduler status (lines ~15731-15783 in inline_legacy_routes.py)
    # ========================================================================

    @app.get("/debug/scheduler-status")
    async def debug_scheduler_status():
        """Detailed diagnostic for Smart Scheduler routes"""
        status = {
            "smart_scheduler_routes_module": False,
            "smart_scheduler_models_module": False,
            "notification_service": False,
            "microsoft_graph": False,
            "public_slots_route": False,
            "errors": []
        }

        # Try importing each dependency
        try:
            from smart_scheduler_models import create_smart_scheduler_models
            status["smart_scheduler_models_module"] = True
        except Exception as e:
            status["errors"].append("smart_scheduler_models: import failed")

        try:
            from services.notification_service import notification_service
            status["notification_service"] = True
        except Exception as e:
            status["errors"].append("notification_service: import failed")

        try:
            from services.microsoft_graph import create_event_via_graph, CalendarResult
            status["microsoft_graph"] = True
        except Exception as e:
            status["errors"].append("microsoft_graph: import failed")

        try:
            from smart_scheduler_routes import router as smart_scheduler_router
            status["smart_scheduler_routes_module"] = True
            status["router_routes_count"] = len(smart_scheduler_router.routes)

            # Check for specific endpoint
            for route in smart_scheduler_router.routes:
                if hasattr(route, 'path') and route.path == '/public/available-slots':
                    status["public_slots_route"] = True
                    break
        except Exception as e:
            status["errors"].append("smart_scheduler_routes: import failed")

        # Check if route is registered in app
        for route in app.routes:
            if hasattr(route, 'path') and route.path == '/api/v1/scheduler/public/available-slots':
                status["route_registered_in_app"] = True
                break
        else:
            status["route_registered_in_app"] = False

        return status

    # ========================================================================
    # Health detailed (lines ~16886-16894 in inline_legacy_routes.py)
    # ========================================================================

    @app.get("/health/detailed")
    async def health_check_detailed():
        """Comprehensive health check with all dependencies, including DB pool"""
        if health_checker:
            results = await health_checker.check_all()
        else:
            results = {"status": "healthy", "message": "Basic health check (detailed checks not configured)"}

        # Enrich with connection pool health
        try:
            from services.db_monitor import check_pool_health, get_pool_stats
            pool_health = check_pool_health()
            pool_stats = get_pool_stats()
            results["connection_pool"] = {
                "health": pool_health,
                "stats": pool_stats,
            }
            # Downgrade overall status if pool is unhealthy
            if pool_health["status"] == "critical" and results.get("status") == "healthy":
                results["status"] = "degraded"
            elif pool_health["status"] == "warning" and results.get("status") == "healthy":
                results["status"] = "degraded"
        except Exception as e:
            logger.warning(f"Could not fetch pool health for detailed check: {e}")
            results["connection_pool"] = {"error": "Pool stats unavailable"}

        status_code = 200 if results.get("status") in ("healthy",) else 503
        return JSONResponse(status_code=status_code, content=results)

    # ========================================================================
    # Health ready (lines ~16896-16949 in inline_legacy_routes.py)
    # ========================================================================

    @app.get("/health/ready")
    async def readiness_check():
        """
        Kubernetes readiness probe - can accept traffic?

        Checks:
        - Database connectivity
        - Redis connectivity (required in production)
        """
        checks = {"database": False, "redis": False}
        errors = []

        # Check database
        try:
            db = SessionLocal()
            db.execute(text("SELECT 1"))
            db.close()
            checks["database"] = True
        except Exception as e:
            errors.append("Database: connection failed")

        # Check Redis (required in production)
        try:
            from tasks.celery_app import check_redis_health
            redis_status = check_redis_health()
            checks["redis"] = redis_status.get("status") == "healthy"
            if not checks["redis"]:
                errors.append(f"Redis: {redis_status.get('error', 'unhealthy')}")
        except ImportError:
            # Celery module not available, try direct Redis check
            try:
                import redis as redis_lib
                from config import settings
                r = redis_lib.from_url(settings.REDIS_URL)
                r.ping()
                checks["redis"] = True
            except Exception as e:
                errors.append("Redis: connection failed")

        # Determine readiness based on environment
        from config import is_production
        if is_production():
            # In production, both database and Redis must be healthy
            is_ready = all(checks.values())
        else:
            # In development, only database is required
            is_ready = checks["database"]

        if is_ready:
            return {"status": "ready", "checks": checks}
        return JSONResponse(
            status_code=503,
            content={"status": "not_ready", "checks": checks, "errors": errors}
        )

    @app.get("/ready")
    async def ready_alias():
        """Root-level readiness alias for load balancers."""
        return await readiness_check()

    # ========================================================================
    # Health live (lines ~16951-16954 in inline_legacy_routes.py)
    # ========================================================================

    @app.get("/health/live")
    async def liveness_check():
        """Kubernetes liveness probe - is process alive?"""
        return {"status": "alive"}

    # ========================================================================
    # Health pool (lines ~16957-16977 in inline_legacy_routes.py)
    # ========================================================================

    @app.get("/health/pool")
    async def pool_status():
        """
        Connection pool status for monitoring and debugging.

        Returns pool size, checked in/out connections, overflow, utilization %,
        and health assessment. Useful for diagnosing connection exhaustion issues.
        """
        try:
            from services.db_monitor import get_pool_stats, check_pool_health
            pool_stats = get_pool_stats()
            pool_health = check_pool_health()

            return {
                **pool_stats,
                "health": pool_health["status"],
                "health_message": pool_health["message"],
                "recommendation": pool_health.get("recommendation"),
            }
        except ImportError:
            # Fallback to legacy get_pool_status if db_monitor not available
            try:
                from db import get_pool_status
                pool_info = get_pool_status()
                if pool_info.get("status") == "saturated":
                    pool_info["recommendation"] = "Pool is saturated. Consider increasing pool_size or using PgBouncer."
                return pool_info
            except Exception as e:
                return {"error": "Internal server error", "status": "unknown"}
        except Exception as e:
            return {"error": "Internal server error", "status": "unknown"}

    # ========================================================================
    # Health cache (lines ~16979-16992 in inline_legacy_routes.py)
    # ========================================================================

    @app.get("/health/cache")
    async def cache_health():
        """Check Redis cache status for AI Agent tools"""
        try:
            from core.cache import cache
            stats = await cache.get_stats()
            return {
                "status": "healthy" if stats.get("connected") else "degraded",
                "cache": stats
            }
        except ImportError:
            return {"status": "disabled", "message": "Cache module not available"}
        except Exception as e:
            return {"status": "error", "error": "Internal server error"}

    # ========================================================================
    # Recent Errors (diagnostic ring buffer)
    # ========================================================================

    @app.get("/health/recent-errors")
    async def recent_errors(request: Request):
        """
        Show recent 500 errors captured by the error ring buffer.

        Protected by admin API key header (X-API-Key) to prevent
        information leakage. Returns the last N errors with stack traces
        so production 500s can be diagnosed without needing Railway log access.
        """
        import os
        # Require admin API key in production
        is_prod = bool(os.getenv("RAILWAY_ENVIRONMENT") or os.getenv("ENVIRONMENT") == "production")
        if is_prod:
            api_key = request.headers.get("X-API-Key", "")
            admin_key = os.getenv("ADMIN_API_KEY", "")
            if not admin_key or api_key != admin_key:
                return JSONResponse(
                    status_code=403,
                    content={"detail": "Admin API key required"}
                )

        try:
            from utils.error_handling import get_recent_errors
            errors = get_recent_errors(limit=30)
            return {
                "total_captured": len(errors),
                "errors": errors,
            }
        except ImportError:
            return {"error": "Error handling module not available"}

    @app.get("/health/diag-errors", tags=["Health"])
    async def diag_errors(request: Request, secret: str = ""):
        """Temporary diagnostic endpoint for recent errors. Remove after debugging."""
        if secret != "perennia-diag-2026-03":
            return JSONResponse(status_code=403, content={"detail": "Invalid secret"})
        try:
            from utils.error_handling import get_recent_errors
            errors = get_recent_errors(limit=10)
            return {"total_captured": len(errors), "errors": errors}
        except ImportError:
            return {"error": "Error handling module not available"}

    # ========================================================================
    # Admin-only: DB Pool Stats (detailed monitoring for operations)
    # ========================================================================

    @app.get("/api/admin/db-pool-stats", tags=["Admin"])
    async def admin_db_pool_stats(request: Request):
        """
        Detailed database connection pool statistics for admin monitoring.

        Protected by ADMIN_API_KEY header (X-API-Key). Returns comprehensive
        pool metrics including utilization percentage, health assessment,
        per-tenant connection counts, and actionable recommendations.

        Use this endpoint to:
        - Monitor pool utilization trends
        - Diagnose connection exhaustion incidents
        - Verify pool configuration is appropriate for current load
        """
        import os

        # Require admin API key
        api_key = request.headers.get("X-API-Key", "")
        admin_key = os.getenv("ADMIN_API_KEY", "")
        if not admin_key or api_key != admin_key:
            return JSONResponse(
                status_code=403,
                content={"detail": "Admin API key required"}
            )

        try:
            from services.db_monitor import get_pool_stats, check_pool_health
            from db import (
                _tenant_connection_counts,
                MAX_CONNECTIONS_PER_TENANT,
                USE_PGBOUNCER,
            )

            pool_stats = get_pool_stats()
            pool_health = check_pool_health()

            # Snapshot of per-tenant connection usage
            tenant_usage = dict(_tenant_connection_counts)

            return {
                "pool_stats": pool_stats,
                "health": pool_health,
                "configuration": {
                    "use_pgbouncer": USE_PGBOUNCER,
                    "max_connections_per_tenant": MAX_CONNECTIONS_PER_TENANT,
                },
                "tenant_connections": {
                    "active_tenants": len(tenant_usage),
                    "by_tenant": tenant_usage,
                },
            }
        except Exception as e:
            logger.exception(f"Admin pool stats failed: {e}")
            return JSONResponse(
                status_code=500,
                content={"error": "Failed to collect pool stats"}
            )

    # ========================================================================
    # Deep Health Check — comprehensive system diagnostics
    # ========================================================================

    @app.get("/health/deep", tags=["Health"])
    async def deep_health_check(request: Request):
        """
        Comprehensive health check that tests all critical subsystems.

        Protected by authentication: requires either a valid Bearer token
        (Authorization header) or an admin API key (X-API-Key header).

        Returns detailed status for:
        - Database connectivity and connection pool stats
        - Redis connectivity
        - External service reachability (Telnyx, OpenAI, Anthropic)
        - Memory usage
        - Disk space
        - Application uptime
        """
        import os
        import asyncio

        # ---- Authentication gate ----
        # Accept either Bearer token or admin API key
        authenticated = False

        # Check admin API key first (simpler, bypasses CSRF)
        api_key_header = request.headers.get("X-API-Key", "")
        admin_key = os.getenv("ADMIN_API_KEY", "")
        if admin_key and api_key_header == admin_key:
            authenticated = True

        # Check Bearer token
        if not authenticated:
            auth_header = request.headers.get("Authorization", "")
            if auth_header.startswith("Bearer ") and len(auth_header) > 10:
                token = auth_header[7:]
                try:
                    # Try RS256 secure token verification first
                    try:
                        from auth.tokens import _verify_secure_token
                        payload = _verify_secure_token(token)
                        if payload:
                            authenticated = True
                    except (ImportError, Exception):
                        pass
                    # Fallback to HS256 JWT
                    if not authenticated:
                        from jose import jwt as jose_jwt
                        secret_key = os.getenv("SECRET_KEY", "")
                        algorithm = os.getenv("JWT_ALGORITHM", "HS256")
                        if secret_key:
                            payload = jose_jwt.decode(token, secret_key, algorithms=[algorithm])
                            if payload.get("sub"):
                                authenticated = True
                except Exception:
                    pass

        if not authenticated:
            return JSONResponse(
                status_code=401,
                content={
                    "status": "unauthorized",
                    "message": "Authentication required. Provide Authorization: Bearer <token> or X-API-Key header.",
                },
            )

        # ---- Run all health checks with individual timeouts ----
        checks = {}
        CHECK_TIMEOUT = 2.0  # seconds per check

        # 1. Database connectivity
        try:
            checks["database"] = await asyncio.wait_for(
                _deep_check_database(SessionLocal),
                timeout=CHECK_TIMEOUT,
            )
        except asyncio.TimeoutError:
            checks["database"] = {"status": "unhealthy", "error": "timeout (>2s)"}
        except Exception as e:
            checks["database"] = {"status": "unhealthy", "error": str(e)}

        # 2. Database connection pool stats
        try:
            checks["database_pool"] = await asyncio.wait_for(
                asyncio.get_event_loop().run_in_executor(None, _deep_check_pool_stats),
                timeout=CHECK_TIMEOUT,
            )
        except asyncio.TimeoutError:
            checks["database_pool"] = {"status": "unknown", "error": "timeout (>2s)"}
        except Exception as e:
            checks["database_pool"] = {"status": "unknown", "error": str(e)}

        # 3. Redis connectivity
        try:
            checks["redis"] = await asyncio.wait_for(
                asyncio.get_event_loop().run_in_executor(None, _deep_check_redis),
                timeout=CHECK_TIMEOUT,
            )
        except asyncio.TimeoutError:
            checks["redis"] = {"status": "unhealthy", "error": "timeout (>2s)"}
        except Exception as e:
            checks["redis"] = {"status": "unhealthy", "error": str(e)}

        # 4. External service reachability (DNS/TCP only — no API calls)
        external_services = {
            "openai": ("api.openai.com", 443),
            "telnyx": ("api.telnyx.com", 443),
            "anthropic": ("api.anthropic.com", 443),
        }
        checks["external_services"] = {}
        for svc_name, (host, port) in external_services.items():
            try:
                checks["external_services"][svc_name] = await asyncio.wait_for(
                    asyncio.get_event_loop().run_in_executor(
                        None, _deep_check_tcp_reachability, host, port
                    ),
                    timeout=CHECK_TIMEOUT,
                )
            except asyncio.TimeoutError:
                checks["external_services"][svc_name] = {"status": "unreachable", "error": "timeout (>2s)"}
            except Exception as e:
                checks["external_services"][svc_name] = {"status": "unreachable", "error": str(e)}

        # 5. Memory usage
        try:
            checks["memory"] = _deep_check_memory()
        except Exception as e:
            checks["memory"] = {"status": "unknown", "error": str(e)}

        # 6. Disk space
        try:
            checks["disk"] = _deep_check_disk()
        except Exception as e:
            checks["disk"] = {"status": "unknown", "error": str(e)}

        # ---- Determine overall status ----
        overall_status = "healthy"
        db_status = checks.get("database", {}).get("status", "unhealthy")
        if db_status == "unhealthy":
            overall_status = "unhealthy"
        else:
            for key, value in checks.items():
                if key == "external_services":
                    for svc_val in value.values():
                        if isinstance(svc_val, dict) and svc_val.get("status") not in ("reachable",):
                            if overall_status == "healthy":
                                overall_status = "degraded"
                elif isinstance(value, dict):
                    check_status = value.get("status", "")
                    if check_status in ("unhealthy", "critical", "error"):
                        if key == "redis":
                            # Redis down is degraded, not unhealthy (app can function without it)
                            if overall_status == "healthy":
                                overall_status = "degraded"
                        elif key == "database_pool" and check_status == "saturated":
                            if overall_status == "healthy":
                                overall_status = "degraded"

        uptime_seconds = round(time.monotonic() - _APP_START_TIME, 1)

        response_data = {
            "status": overall_status,
            "checks": checks,
            "uptime_seconds": uptime_seconds,
            "started_at": _APP_START_TIMESTAMP.isoformat(),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "version": "2026.01.22.1",
            "environment": os.getenv("ENVIRONMENT", "development"),
        }

        status_code = 200 if overall_status in ("healthy", "degraded") else 503
        return JSONResponse(status_code=status_code, content=response_data)


# ==========================================================================
# Deep health check helper functions (module-level, outside register func)
# ==========================================================================

async def _deep_check_database(session_local):
    """Test database connectivity with SELECT 1 and measure latency."""
    import asyncio
    loop = asyncio.get_event_loop()

    def _db_ping():
        start = time.monotonic()
        db = session_local()
        try:
            result = db.execute(text("SELECT 1"))
            result.fetchone()
            latency_ms = round((time.monotonic() - start) * 1000, 1)
            return {"status": "healthy", "latency_ms": latency_ms}
        except Exception as e:
            latency_ms = round((time.monotonic() - start) * 1000, 1)
            return {"status": "unhealthy", "latency_ms": latency_ms, "error": str(e)}
        finally:
            db.close()

    return await loop.run_in_executor(None, _db_ping)


def _deep_check_pool_stats():
    """Get database connection pool statistics."""
    try:
        from db import get_pool_status
        pool_info = get_pool_status()
        pool_info["status"] = pool_info.get("status", "healthy")
        return pool_info
    except Exception as e:
        return {"status": "unknown", "error": str(e)}


def _deep_check_redis():
    """Test Redis connectivity and measure latency."""
    import os
    redis_url = os.getenv("REDIS_URL")
    if not redis_url:
        return {"status": "not_configured", "message": "REDIS_URL not set"}

    try:
        import redis as redis_lib
        start = time.monotonic()
        r = redis_lib.from_url(redis_url, socket_connect_timeout=2, socket_timeout=2)
        r.ping()
        latency_ms = round((time.monotonic() - start) * 1000, 1)

        # Get basic Redis info
        memory_used = "unknown"
        connected_clients = "unknown"
        try:
            info = r.info(section="memory")
            memory_used = info.get("used_memory_human", "unknown")
        except Exception:
            pass
        try:
            info_clients = r.info(section="clients")
            connected_clients = info_clients.get("connected_clients", "unknown")
        except Exception:
            pass

        r.close()
        return {
            "status": "healthy",
            "latency_ms": latency_ms,
            "memory_used": memory_used,
            "connected_clients": connected_clients,
        }
    except ImportError:
        return {"status": "unavailable", "message": "redis package not installed"}
    except Exception as e:
        return {"status": "unhealthy", "error": str(e)}


def _deep_check_tcp_reachability(host: str, port: int):
    """Check if a host:port is reachable via TCP (DNS resolution + connection)."""
    import socket
    start = time.monotonic()
    try:
        addr_info = socket.getaddrinfo(host, port, socket.AF_UNSPEC, socket.SOCK_STREAM)
        if not addr_info:
            return {"status": "unreachable", "error": "DNS resolution failed"}

        sock = socket.socket(addr_info[0][0], socket.SOCK_STREAM)
        sock.settimeout(2.0)
        sock.connect(addr_info[0][4])
        sock.close()
        latency_ms = round((time.monotonic() - start) * 1000, 1)
        return {"status": "reachable", "latency_ms": latency_ms}
    except socket.timeout:
        return {"status": "unreachable", "error": "connection timeout"}
    except socket.gaierror as e:
        return {"status": "unreachable", "error": f"DNS resolution failed: {e}"}
    except Exception as e:
        latency_ms = round((time.monotonic() - start) * 1000, 1)
        return {"status": "unreachable", "latency_ms": latency_ms, "error": str(e)}


def _deep_check_memory():
    """Check process memory usage."""
    try:
        import resource
        import platform
        rusage = resource.getrusage(resource.RUSAGE_SELF)
        # ru_maxrss is in bytes on macOS, kilobytes on Linux
        if platform.system() == "Darwin":
            rss_mb = round(rusage.ru_maxrss / (1024 * 1024), 1)
        else:
            rss_mb = round(rusage.ru_maxrss / 1024, 1)

        status = "healthy"
        if rss_mb > 1024:
            status = "warning"
        if rss_mb > 2048:
            status = "critical"

        return {"status": status, "rss_mb": rss_mb}
    except ImportError:
        pass

    # Fallback for Linux: read /proc/self/status
    try:
        with open("/proc/self/status", "r") as f:
            for line in f:
                if line.startswith("VmRSS:"):
                    rss_kb = int(line.split()[1])
                    rss_mb = round(rss_kb / 1024, 1)
                    status = "healthy"
                    if rss_mb > 1024:
                        status = "warning"
                    return {"status": status, "rss_mb": rss_mb}
    except Exception:
        pass

    return {"status": "unknown", "message": "Could not determine memory usage"}


def _deep_check_disk():
    """Check disk space on the application filesystem."""
    import os
    try:
        stat = os.statvfs("/")
        total_gb = round((stat.f_blocks * stat.f_frsize) / (1024 ** 3), 1)
        free_gb = round((stat.f_bavail * stat.f_frsize) / (1024 ** 3), 1)
        used_gb = round(total_gb - free_gb, 1)
        usage_pct = round((used_gb / total_gb) * 100, 1) if total_gb > 0 else 0

        status = "healthy"
        if usage_pct > 85:
            status = "warning"
        if usage_pct > 95:
            status = "critical"

        return {
            "status": status,
            "total_gb": total_gb,
            "free_gb": free_gb,
            "used_gb": used_gb,
            "usage_percent": usage_pct,
        }
    except Exception as e:
        return {"status": "unknown", "error": str(e)}

