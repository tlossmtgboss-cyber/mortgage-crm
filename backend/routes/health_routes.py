"""
Health & System Status Routes

Root, health check, and system status endpoints.
Extracted from inline_legacy_routes.py.

Enterprise health check endpoints:
  GET /health          - Simple 200 OK for load balancers (no auth, fast, no DB)
  GET /health/detailed - Comprehensive check with per-component status (requires auth)
  GET /health/ready    - Readiness probe: can this instance accept traffic? (DB must connect)
  GET /health/live     - Liveness probe: is the process responsive?
"""
from fastapi import Depends, Request
from fastapi.responses import JSONResponse, HTMLResponse
from sqlalchemy.orm import Session
from sqlalchemy import text, select
from sqlalchemy.ext.asyncio import AsyncSession
from db import get_async_db
from datetime import datetime, timezone
from utils.response import success_response, error_response, ErrorCodes
import asyncio
import logging
import os
import secrets
import sys
import time

logger = logging.getLogger(__name__)

# Record application start time at module load for uptime calculation
_APP_START_TIME = time.monotonic()
_APP_START_TIMESTAMP = datetime.now(timezone.utc)

# Application version — from environment or hardcoded
_APP_VERSION = os.getenv("APP_VERSION", "2026.04.10.1")


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

    @app.get("/health", tags=["Health"])
    async def health_check(db: Session = Depends(get_db)):
        """
        Enterprise health check for load balancers, monitoring, and uptime probes.

        No auth required. Returns comprehensive service status with latency
        measurements. Designed to complete in under 500ms.

        Critical services (database): failure returns HTTP 503.
        Non-critical services (redis, ai_service, telephony): failure returns
        HTTP 200 with degraded status so load balancers keep routing traffic.

        For deeper diagnostics (memory, pool stats, auth-gated), use
        GET /health/detailed.
        """
        services = {}
        is_healthy = True
        CHECK_TIMEOUT = 2.0  # seconds -- keep total under 500ms budget

        # --- Database: SELECT 1 with latency measurement ---
        try:
            loop = asyncio.get_event_loop()

            def _db_ping():
                start = time.monotonic()
                try:
                    db.execute(text("SELECT 1"))
                    latency = round((time.monotonic() - start) * 1000, 1)
                    return {"status": "healthy", "latency_ms": latency}
                except Exception as exc:
                    latency = round((time.monotonic() - start) * 1000, 1)
                    return {"status": "unhealthy", "latency_ms": latency, "error": str(exc)[:200]}

            db_result = await asyncio.wait_for(
                loop.run_in_executor(None, _db_ping),
                timeout=CHECK_TIMEOUT,
            )
            services["database"] = db_result
            if db_result["status"] != "healthy":
                is_healthy = False
        except asyncio.TimeoutError:
            services["database"] = {"status": "unhealthy", "error": "timeout (>2s)"}
            is_healthy = False
        except Exception as e:
            services["database"] = {"status": "unhealthy", "error": str(e)[:200]}
            is_healthy = False

        # --- Redis: PING with latency measurement ---
        try:
            loop = asyncio.get_event_loop()

            def _redis_ping():
                try:
                    from services.redis_service import redis_service
                    client = redis_service.get_client()
                    if client is None:
                        # Redis not configured or circuit breaker open
                        if not os.getenv("REDIS_URL"):
                            return {"status": "not_configured"}
                        return {"status": "unhealthy", "error": "client unavailable (circuit breaker open or init failed)"}
                    start = time.monotonic()
                    client.ping()
                    latency = round((time.monotonic() - start) * 1000, 1)
                    redis_service.record_success()
                    return {"status": "healthy", "latency_ms": latency}
                except Exception as exc:
                    return {"status": "unhealthy", "error": str(exc)[:200]}

            redis_result = await asyncio.wait_for(
                loop.run_in_executor(None, _redis_ping),
                timeout=CHECK_TIMEOUT,
            )
            services["redis"] = redis_result
        except asyncio.TimeoutError:
            services["redis"] = {"status": "unhealthy", "error": "timeout (>2s)"}
        except Exception as e:
            services["redis"] = {"status": "unhealthy", "error": str(e)[:200]}

        # --- AI service: check ANTHROPIC_API_KEY presence (no live call) ---
        anthropic_key = os.getenv("ANTHROPIC_API_KEY")
        services["ai_service"] = {
            "status": "healthy" if anthropic_key else "not_configured",
        }

        # --- Telephony: check TELNYX_API_KEY presence (no live call) ---
        telnyx_key = os.getenv("TELNYX_API_KEY")
        services["telephony"] = {
            "status": "healthy" if telnyx_key else "not_configured",
        }

        # --- Token blacklist mode (redis vs in-memory fallback) ---
        try:
            from auth.tokens import token_blacklist
            services["token_blacklist"] = token_blacklist.get_status()
        except Exception as e:
            services["token_blacklist"] = {"status": "unknown", "error": str(e)[:200]}

        # --- Build response ---
        uptime_seconds = round(time.monotonic() - _APP_START_TIME, 1)
        overall_status = "healthy" if is_healthy else "unhealthy"

        response_body = {
            "status": overall_status,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "version": _APP_VERSION,
            "services": services,
            "uptime_seconds": uptime_seconds,
        }

        status_code = 200 if is_healthy else 503
        return JSONResponse(status_code=status_code, content=response_body)


    # ========================================================================
    # Ping endpoint (lines ~15504-15559 in inline_legacy_routes.py)
    # ========================================================================

    @app.get("/ping")
    async def ping(db: AsyncSession = Depends(get_async_db)):
        """Simple ping endpoint - also creates Salesforce tables if needed"""
        tables_created = []
        try:
            await db.execute(text("""
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
            await db.commit()
            tables_created.append("oauth_states")
        except Exception as e:
            await db.rollback()
            tables_created.append("oauth_states error: table creation failed")

        try:
            await db.execute(text("""
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
            await db.commit()
            tables_created.append("integration_profiles")
        except Exception as e:
            await db.rollback()
            tables_created.append("integration_profiles error: table creation failed")

        return {"ping": "pong", "status": "ok", "tables": tables_created}

    # ========================================================================
    # API health check (lines ~15689-15700 in inline_legacy_routes.py)
    # ========================================================================

    @app.get("/api/v1/health")
    async def api_health_check(db: AsyncSession = Depends(get_async_db)):
        """API health check endpoint at /api/v1/health - database connectivity"""
        try:
            await db.execute(text("SELECT 1"))
            return success_response(data={
                "status": "healthy",
                "database": "connected",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "version": _APP_VERSION,
            })
        except Exception as e:
            logger.error(f"API health check failed: {type(e).__name__}: {e}")
            return error_response(
                code=ErrorCodes.SERVICE_UNAVAILABLE,
                message=f"Health check failed: {type(e).__name__}: {str(e)[:200]}",
                status_code=503,
            )

    # ========================================================================
    # Detailed health check at /api/v1/health/detailed (unauthenticated)
    # For load balancers, monitoring dashboards, and uptime checks.
    # ========================================================================

    @app.get("/api/v1/health/detailed")
    async def api_health_detailed(db: Session = Depends(get_db)):
        """
        Comprehensive health check for load balancers and monitoring.

        No authentication required. Checks:
        - Database connectivity (SELECT 1 with 3s timeout)
        - Redis connectivity (PING)
        - Connection pool stats
        - External service API key configuration (no live calls)

        Returns 200 if all critical services (database) are healthy,
        503 if any critical service is down.
        """
        checks = {}
        overall = True

        # --- Database connectivity (with 3-second timeout) ---
        try:
            loop = asyncio.get_event_loop()

            def _db_ping():
                start = time.monotonic()
                try:
                    db.execute(text("SELECT 1"))
                    latency_ms = round((time.monotonic() - start) * 1000, 1)
                    return {"status": "healthy", "latency_ms": latency_ms}
                except Exception as e:
                    latency_ms = round((time.monotonic() - start) * 1000, 1)
                    return {"status": "unhealthy", "latency_ms": latency_ms, "error": str(e)}

            db_result = await asyncio.wait_for(
                loop.run_in_executor(None, _db_ping),
                timeout=3.0,
            )
            checks["database"] = db_result
            if db_result["status"] != "healthy":
                overall = False
        except asyncio.TimeoutError:
            checks["database"] = {"status": "unhealthy", "error": "timeout (>3s)"}
            overall = False
        except Exception as e:
            checks["database"] = {"status": "unhealthy", "error": str(e)}
            overall = False

        # --- Connection pool stats ---
        try:
            from db import get_pool_status
            checks["connection_pool"] = get_pool_status()
        except Exception as e:
            checks["connection_pool"] = {"status": "unknown", "error": str(e)}

        # --- Redis (via centralized redis_service) ---
        try:
            from services.redis_service import check_redis_health
            redis_health = check_redis_health()
            redis_status = redis_health.get("status", "unknown")
            checks["redis"] = redis_health
            if redis_status == "unhealthy":
                overall = False
        except Exception as e:
            checks["redis"] = {"status": "unknown", "error": str(e)}

        # --- External services (config check only -- no live API calls) ---
        for name, env_var in [
            ("anthropic", "ANTHROPIC_API_KEY"),
            ("telnyx", "TELNYX_API_KEY"),
            ("vapi", "VAPI_API_KEY"),
            ("apns", "APNS_KEY_ID"),
            ("stripe", "STRIPE_SECRET_KEY"),
        ]:
            checks[name] = {
                "status": "configured" if os.getenv(env_var) else "not_configured"
            }

        # --- Build response ---
        uptime_seconds = round(time.monotonic() - _APP_START_TIME, 1)
        if overall:
            return success_response(data={
                "status": "healthy",
                "checks": checks,
                "uptime_seconds": uptime_seconds,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "version": _APP_VERSION,
            })
        else:
            return error_response(
                code=ErrorCodes.SERVICE_UNAVAILABLE,
                message="One or more services are degraded",
                status_code=503,
                details={
                    "status": "degraded",
                    "checks": checks,
                    "uptime_seconds": uptime_seconds,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "version": _APP_VERSION,
                },
            )

    # ========================================================================
    # Deploy test (lines ~15703-15706 in inline_legacy_routes.py)
    # ========================================================================

    @app.get("/deploy-test")
    async def deploy_test():
        """Simple endpoint to verify deployment - added 2025-12-27T22:45"""
        return {"deployed_at": "2026-01-22T09:10:00Z", "version": _APP_VERSION, "test": "db-pool-fixes"}


    # ========================================================================
    # Health detailed (lines ~16886-16894 in inline_legacy_routes.py)
    # ========================================================================

    @app.get("/health/detailed", tags=["Health"])
    async def health_check_detailed(request: Request):
        """
        Comprehensive health check with per-component status, latency, and diagnostics.

        Requires authentication: Bearer token (Authorization header) or admin
        API key (X-API-Key header). Returns structured results for every
        subsystem so monitoring dashboards can alert on individual components.

        Each check includes: status ("ok" / "error"), latency_ms, optional error.
        Overall status: "healthy" (all pass), "degraded" (non-critical fail), "unhealthy" (DB down).
        """
        # ---- Authentication gate ----
        authenticated = False

        # Check admin API key first (simpler, bypasses CSRF)
        api_key_header = request.headers.get("X-API-Key", "")
        admin_key = os.getenv("ADMIN_API_KEY", "")
        if admin_key and api_key_header and secrets.compare_digest(api_key_header, admin_key):
            authenticated = True

        # Check Bearer token
        if not authenticated:
            auth_header = request.headers.get("Authorization", "")
            if auth_header.startswith("Bearer ") and len(auth_header) > 10:
                token = auth_header[7:]
                try:
                    from auth.tokens import _verify_secure_token
                    payload = _verify_secure_token(token)
                    if payload:
                        authenticated = True
                except (ImportError, Exception):
                    pass
                if not authenticated:
                    try:
                        import jwt as jose_jwt
                        secret_key = os.getenv("SECRET_KEY", "")
                        algorithm = os.getenv("JWT_ALGORITHM", "HS256")
                        if secret_key:
                            payload = jose_jwt.decode(token, secret_key, algorithms=[algorithm], options={"verify_aud": False})
                            if payload.get("sub"):
                                authenticated = True
                    except Exception as _exc:  # noqa: BLE001
                        pass

        if not authenticated:
            return JSONResponse(
                status_code=401,
                content={
                    "status": "unauthorized",
                    "message": "Authentication required. Provide Authorization: Bearer <token> or X-API-Key header.",
                },
            )

        # ---- Run all checks concurrently with individual timeouts ----
        checks = {}
        CHECK_TIMEOUT = 3.0  # seconds per check

        # 1. Database connectivity (SELECT 1 with 3s timeout)
        try:
            checks["database"] = await asyncio.wait_for(
                _deep_check_database(SessionLocal),
                timeout=CHECK_TIMEOUT,
            )
        except asyncio.TimeoutError:
            checks["database"] = {"status": "error", "latency_ms": round(CHECK_TIMEOUT * 1000), "error": "timeout (>3s)"}
        except Exception as e:
            checks["database"] = {"status": "error", "error": str(e)}

        # 2. Database connection pool stats
        try:
            checks["database_pool"] = await asyncio.wait_for(
                asyncio.get_event_loop().run_in_executor(None, _deep_check_pool_stats),
                timeout=CHECK_TIMEOUT,
            )
        except asyncio.TimeoutError:
            checks["database_pool"] = {"status": "error", "error": "timeout (>3s)"}
        except Exception as e:
            checks["database_pool"] = {"status": "error", "error": str(e)}

        # 3. Redis connectivity
        try:
            checks["redis"] = await asyncio.wait_for(
                asyncio.get_event_loop().run_in_executor(None, _deep_check_redis),
                timeout=CHECK_TIMEOUT,
            )
        except asyncio.TimeoutError:
            checks["redis"] = {"status": "error", "error": "timeout (>3s)"}
        except Exception as e:
            checks["redis"] = {"status": "error", "error": str(e)}

        # 4. Memory usage
        try:
            checks["memory"] = _deep_check_memory()
        except Exception as e:
            checks["memory"] = {"status": "error", "error": str(e)}

        # 5. Token blacklist mode (redis vs in-memory fallback)
        try:
            from auth.tokens import token_blacklist
            checks["token_blacklist"] = token_blacklist.get_status()
        except Exception as e:
            checks["token_blacklist"] = {"status": "error", "error": str(e)[:200]}

        # ---- Determine overall status ----
        db_status = checks.get("database", {}).get("status", "error")
        if db_status == "error":
            overall_status = "unhealthy"
        else:
            overall_status = "healthy"
            for key, value in checks.items():
                if isinstance(value, dict):
                    check_status = value.get("status", "")
                    if check_status in ("error", "critical", "unhealthy"):
                        if key in ("database",):
                            overall_status = "unhealthy"
                            break
                        elif overall_status == "healthy":
                            overall_status = "degraded"
                    elif check_status == "warning" and overall_status == "healthy":
                        overall_status = "degraded"

        uptime_seconds = round(time.monotonic() - _APP_START_TIME, 1)

        response_data = {
            "status": overall_status,
            "version": _APP_VERSION,
            "uptime_seconds": uptime_seconds,
            "started_at": _APP_START_TIMESTAMP.isoformat(),
            "python_version": sys.version,
            "memory_mb": checks.get("memory", {}).get("rss_mb"),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "environment": os.getenv("ENVIRONMENT", os.getenv("RAILWAY_ENVIRONMENT", "development")),
            "checks": checks,
        }

        status_code = 200 if overall_status in ("healthy", "degraded") else 503
        return JSONResponse(status_code=status_code, content=response_data)

    # ========================================================================
    # Health ready (lines ~16896-16949 in inline_legacy_routes.py)
    # ========================================================================

    @app.get("/health/ready", tags=["Health"])
    async def readiness_check():
        """
        Readiness probe -- can this instance accept traffic?

        No auth required. Returns 200 if the database is reachable (SELECT 1
        within 3 seconds). Returns 503 otherwise. Redis is checked but its
        failure only causes "degraded", not "not_ready", since the app can
        operate with the in-memory token blacklist fallback.

        Suitable for Kubernetes readiness probes, Railway health checks, and
        load balancer target group health checks.
        """
        checks = {}
        errors = []

        # --- Database (critical -- must pass for readiness) ---
        db_ok = False
        db_start = time.monotonic()
        try:
            db_session = SessionLocal()
            try:
                db_session.execute(text("SELECT 1"))
                latency_ms = round((time.monotonic() - db_start) * 1000, 1)
                checks["database"] = {"status": "ok", "latency_ms": latency_ms}
                db_ok = True
            finally:
                db_session.close()
        except Exception as e:
            latency_ms = round((time.monotonic() - db_start) * 1000, 1)
            checks["database"] = {"status": "error", "latency_ms": latency_ms, "error": str(e)[:200]}
            errors.append(f"Database: {type(e).__name__}")

        # --- Redis (non-critical) ---
        redis_url = os.getenv("REDIS_URL")
        if redis_url:
            try:
                import redis as redis_lib
                start = time.monotonic()
                r = redis_lib.from_url(redis_url, socket_connect_timeout=2, socket_timeout=2)
                r.ping()
                latency_ms = round((time.monotonic() - start) * 1000, 1)
                r.close()
                checks["redis"] = {"status": "ok", "latency_ms": latency_ms}
            except ImportError:
                checks["redis"] = {"status": "ok", "note": "redis package not installed, using in-memory fallback"}
            except Exception as e:
                checks["redis"] = {"status": "error", "error": str(e)[:200]}
                errors.append(f"Redis: {type(e).__name__}")
        else:
            checks["redis"] = {"status": "ok", "note": "not configured, using in-memory fallback"}

        # --- Readiness decision: database must be connected ---
        is_ready = db_ok
        if is_ready:
            return {"status": "ready", "checks": checks}
        return JSONResponse(
            status_code=503,
            content={"status": "not_ready", "checks": checks, "errors": errors},
        )

    @app.get("/ready", tags=["Health"])
    async def ready_alias():
        """Root-level readiness alias for load balancers."""
        return await readiness_check()

    # ========================================================================
    # Health live (lines ~16951-16954 in inline_legacy_routes.py)
    # ========================================================================

    @app.get("/health/live", tags=["Health"])
    async def liveness_check():
        """
        Liveness probe -- is this process responsive?

        No auth, no DB call, no external dependencies. If this returns
        anything at all, the process is alive. Returns uptime for convenience.
        """
        return {
            "status": "alive",
            "uptime_seconds": round(time.monotonic() - _APP_START_TIME, 1),
        }

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
    # Token blacklist status (dedicated endpoint for security monitoring)
    # ========================================================================

    @app.get("/health/token-blacklist", tags=["Health"])
    async def token_blacklist_status():
        """
        Token blacklist health status.

        Reports the active backend (redis vs in-memory), count of blacklisted
        tokens, and whether the blacklist is shared across Railway replicas.

        No auth required -- exposes operational status only, no sensitive data.
        Use this endpoint to monitor whether token revocation is functioning
        correctly across all replicas.
        """
        try:
            from auth.tokens import token_blacklist
            status = token_blacklist.get_status()
            status["timestamp"] = datetime.now(timezone.utc).isoformat()
            return status
        except Exception as e:
            logger.error(f"Token blacklist status check failed: {e}")
            return {
                "status": "error",
                "mode": "unknown",
                "error": str(e)[:200],
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

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
        import secrets
        # Always require admin API key — endpoint exposes stack traces
        api_key = request.headers.get("X-API-Key", "")
        admin_key = os.getenv("ADMIN_API_KEY", "")
        if not admin_key or not secrets.compare_digest(api_key, admin_key):
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

    # ========================================================================
    # Smart Docs POST diagnostic — tests middleware + DB INSERT
    # ========================================================================

    @app.post("/health/smart-docs-post-test")
    async def smart_docs_post_test(request: Request):
        """
        Diagnostic POST that replicates the full add_custom_request handler flow.
        No auth — tests each step and reports where it fails.
        Send the same JSON body the frontend sends.
        """
        import traceback as _tb
        import json as _json

        try:
            return await _smart_docs_post_test_inner(request, _tb, _json)
        except Exception as e:
            return JSONResponse(
                status_code=200,
                content={
                    "UNCAUGHT_ERROR": f"{type(e).__name__}: {e}",
                    "traceback": _tb.format_exc()[-1500:],
                },
            )

    async def _smart_docs_post_test_inner(request, _tb, _json):
        steps = {}

        # Step 1: Read request body
        try:
            body_bytes = await request.body()
            steps["1_body_read"] = f"ok ({len(body_bytes)} bytes)"
            body_data = _json.loads(body_bytes) if body_bytes else {}
        except Exception as e:
            steps["1_body_read"] = f"FAIL: {type(e).__name__}: {e}"
            return {"steps": steps, "failed_at": "body_read"}

        # Step 2: Parse with Pydantic model
        try:
            from routes.smart_docs_models import AddCustomRequestBody
            body = AddCustomRequestBody(**body_data)
            steps["2_pydantic_parse"] = f"ok (title={body.title!r}, doc_type={body.doc_type!r})"
        except Exception as e:
            steps["2_pydantic_parse"] = f"FAIL: {type(e).__name__}: {e}"
            return {"steps": steps, "failed_at": "pydantic_parse"}

        # Step 3: DB connection
        try:
            from db import SessionLocal
            db = SessionLocal()
            from sqlalchemy import text as _text
            db.execute(_text("SELECT 1")).fetchone()
            steps["3_db_connection"] = "ok"
        except Exception as e:
            steps["3_db_connection"] = f"FAIL: {type(e).__name__}: {e}"
            return {"steps": steps, "failed_at": "db_connection"}

        try:
            # Step 4: Find a test loan
            loan_row = db.execute(_text(
                "SELECT id FROM loans ORDER BY id DESC LIMIT 1"
            )).first()
            if not loan_row:
                steps["4_find_loan"] = "FAIL: no loans in DB"
                return {"steps": steps, "failed_at": "find_loan"}
            loan_id = loan_row[0]
            borrower_id = 0
            steps["4_find_loan"] = f"ok (loan_id={loan_id}, borrower_id={borrower_id})"

            # Step 5: Import NeedsListGenerator
            try:
                from services.smart_docs.needs_list_generator import NeedsListGenerator
                steps["5_import_generator"] = "ok"
            except Exception as e:
                steps["5_import_generator"] = f"FAIL: {type(e).__name__}: {e}"
                steps["5_traceback"] = _tb.format_exc()[-500:]
                return {"steps": steps, "failed_at": "import_generator"}

            # Step 6: Instantiate NeedsListGenerator
            try:
                generator = NeedsListGenerator(db)
                steps["6_instantiate_generator"] = "ok"
            except Exception as e:
                steps["6_instantiate_generator"] = f"FAIL: {type(e).__name__}: {e}"
                return {"steps": steps, "failed_at": "instantiate_generator"}

            # Step 7: Call add_custom_request
            try:
                result = generator.add_custom_request(
                    loan_id=loan_id,
                    borrower_id=borrower_id,
                    title=body.title,
                    description=body.description,
                    instructions=body.instructions,
                    priority=body.priority,
                    due_date=body.due_date,
                    doc_type=body.doc_type,
                    requires_esign=body.requires_esign,
                )
                steps["7_add_custom_request"] = f"ok (id={result.get('id')})"
            except Exception as e:
                db.rollback()
                steps["7_add_custom_request"] = f"FAIL: {type(e).__name__}: {e}"
                steps["7_traceback"] = _tb.format_exc()[-800:]
                return {"steps": steps, "failed_at": "add_custom_request"}

            # Step 8: Clean up (delete the test request)
            try:
                req_id = result.get("id")
                if req_id:
                    db.execute(_text(
                        "DELETE FROM smart_document_requests WHERE id = :rid"
                    ), {"rid": req_id})
                    db.commit()
                    steps["8_cleanup"] = f"ok (deleted request {req_id})"
                else:
                    steps["8_cleanup"] = "skipped (no id in result)"
            except Exception as e:
                db.rollback()
                steps["8_cleanup"] = f"FAIL: {type(e).__name__}: {e}"

        finally:
            db.close()

        return {"steps": steps, "result": "ALL STEPS PASSED"}

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
        if admin_key and api_key_header and secrets.compare_digest(api_key_header, admin_key):
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
                        import jwt as jose_jwt
                        secret_key = os.getenv("SECRET_KEY", "")
                        algorithm = os.getenv("JWT_ALGORITHM", "HS256")
                        if secret_key:
                            payload = jose_jwt.decode(token, secret_key, algorithms=[algorithm], options={"verify_aud": False})
                            if payload.get("sub"):
                                authenticated = True
                except Exception as _exc:  # noqa: BLE001
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
            "version": _APP_VERSION,
            "environment": os.getenv("ENVIRONMENT", "development"),
        }

        status_code = 200 if overall_status in ("healthy", "degraded") else 503
        return JSONResponse(status_code=status_code, content=response_data)

    # ========================================================================
    # Admin-only: Pool Stats (PERF-006)
    # ========================================================================

    @app.get("/health/pool-stats", tags=["Health"])
    async def pool_stats_admin(request: Request):
        """
        Detailed connection pool statistics for admin monitoring.

        Protected by authentication: admin API key (X-API-Key header) or
        valid Bearer token. Returns comprehensive pool metrics including
        utilization percentage, overflow high-water mark, per-tenant
        connection counts, and health assessment.
        """
        if not _authenticate_admin(request):
            return JSONResponse(
                status_code=401,
                content={
                    "status": "unauthorized",
                    "message": "Authentication required. Provide Authorization: Bearer <token> or X-API-Key header.",
                },
            )

        try:
            from db import get_pool_stats as _db_pool_stats
            stats = _db_pool_stats()

            # Enrich with health assessment from db_monitor if available
            try:
                from services.db_monitor import check_pool_health
                health = check_pool_health()
                stats["health"] = health["status"]
                stats["health_message"] = health["message"]
                if health.get("recommendation"):
                    stats["recommendation"] = health["recommendation"]
            except ImportError:
                pass

            stats["timestamp"] = datetime.now(timezone.utc).isoformat()
            return stats
        except Exception as e:
            logger.exception(f"Pool stats endpoint failed: {e}")
            return JSONResponse(
                status_code=500,
                content={"error": "Failed to collect pool stats", "status": "unknown"},
            )

    # ========================================================================
    # Admin-only: Query Stats (PERF-006)
    # ========================================================================

    @app.get("/health/query-stats", tags=["Health"])
    async def query_stats_admin(request: Request):
        """
        Aggregate SQL query timing statistics for admin monitoring.

        Protected by authentication: admin API key (X-API-Key header) or
        valid Bearer token. Returns total queries, slow query count,
        average query time, and p95 query time.

        Requires middleware.query_timing to be initialized at startup.
        """
        if not _authenticate_admin(request):
            return JSONResponse(
                status_code=401,
                content={
                    "status": "unauthorized",
                    "message": "Authentication required. Provide Authorization: Bearer <token> or X-API-Key header.",
                },
            )

        try:
            from middleware.query_timing import get_query_stats
            stats = get_query_stats()
            stats["timestamp"] = datetime.now(timezone.utc).isoformat()
            return stats
        except ImportError:
            return JSONResponse(
                status_code=501,
                content={
                    "error": "Query timing middleware not available",
                    "message": "middleware.query_timing module not found",
                },
            )
        except Exception as e:
            logger.exception(f"Query stats endpoint failed: {e}")
            return JSONResponse(
                status_code=500,
                content={"error": "Failed to collect query stats"},
            )

    # ========================================================================
    # Graceful Degradation Status — public endpoint (no admin required)
    # ========================================================================

    @app.get("/api/v1/health/degradation", tags=["Health"])
    async def get_degradation_status(request: Request):
        """
        Get current graceful degradation status.

        Returns the system service level (full/degraded/minimal/maintenance),
        per-service health (database, Redis, AI API, Telnyx, Vapi), available
        capabilities, and user-facing message. No authentication required so
        the frontend can poll this to show banners when services are down.

        Also includes `last_backup_verified` reflecting the most recent
        successful backup-verify workflow run. If no verification in >8 days
        the status is flagged as a warning.
        """
        import os as _os

        try:
            from services.graceful_degradation import GracefulDegradation

            # Build Redis client (best-effort)
            redis_client = None
            try:
                import redis as redis_lib
                redis_url = _os.getenv("REDIS_URL")
                if redis_url:
                    redis_client = redis_lib.from_url(redis_url, socket_timeout=5)
            except Exception as _exc:  # noqa: BLE001
                pass

            # Build DB session (best-effort)
            db = None
            try:
                if SessionLocal:
                    db = SessionLocal()
            except Exception as _exc:  # noqa: BLE001
                pass

            # Build circuit breaker (best-effort)
            breaker = None
            try:
                from services.circuit_breaker import CircuitBreaker
                breaker = CircuitBreaker(
                    name="anthropic_api",
                    failure_threshold=5,
                    recovery_timeout=30,
                )
            except Exception as _exc:  # noqa: BLE001
                pass

            try:
                degradation = GracefulDegradation(
                    redis_client=redis_client,
                    db=db,
                    circuit_breaker=breaker,
                )
                capabilities = await degradation.get_capabilities()

                # --- Backup verification freshness check ---
                backup_status = _check_backup_freshness()

                # --- RPO / RTO compliance ---
                rpo_rto = _compute_rpo_rto_compliance(
                    backup_status, _APP_START_TIME
                )

                return {
                    "service_level": capabilities["level"],
                    "capabilities": capabilities["capabilities"],
                    "health": capabilities["health"],
                    "last_backup_verified": backup_status,
                    "disaster_recovery": rpo_rto,
                    "message": capabilities.get("message"),
                    "actions": capabilities.get("actions", []),
                    "timestamp": capabilities.get("timestamp"),
                }
            finally:
                if db:
                    try:
                        db.close()
                    except Exception as _exc:  # noqa: BLE001
                        pass

        except Exception as e:
            logger.error(f"Degradation health check failed: {e}")
            _fallback_backup = _check_backup_freshness()
            return JSONResponse(
                status_code=503,
                content={
                    "service_level": "unknown",
                    "error": "Could not determine degradation status",
                    "last_backup_verified": _fallback_backup,
                    "disaster_recovery": _compute_rpo_rto_compliance(
                        _fallback_backup, _APP_START_TIME
                    ),
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            )

    # ========================================================================
    # DR Runbook — returns the disaster recovery runbook with last-verified dates
    # ========================================================================

    @app.get("/health/dr-runbook", tags=["Health"])
    async def dr_runbook():
        """
        Disaster recovery runbook with step-by-step procedures and
        last-verified dates.

        No authentication required. Returns the documented DR procedures
        so operations teams can quickly reference recovery steps during
        an incident. Each procedure includes its last verification date
        from the automated backup-verify CI workflow.
        """
        backup_status = _check_backup_freshness()
        last_verified = backup_status.get("last_verified")

        runbook = {
            "title": "Perennia AI Disaster Recovery Runbook",
            "last_backup_verified": last_verified,
            "backup_freshness": backup_status,
            "procedures": [
                {
                    "id": "DR-001",
                    "name": "Railway Snapshot Restore",
                    "description": "Restore from Railway's automated daily PostgreSQL snapshot",
                    "estimated_rto": "10 minutes",
                    "last_tested": last_verified,
                    "steps": [
                        "1. Log into Railway dashboard (railway.app)",
                        "2. Navigate to the PostgreSQL service",
                        "3. Click 'Snapshots' tab",
                        "4. Select the most recent snapshot (or target date)",
                        "5. Click 'Restore' — this creates a new DB instance",
                        "6. Update DATABASE_URL env var on the backend service to point to the new instance",
                        "7. Trigger a redeploy of the backend service",
                        "8. Verify via GET /health and GET /health/dr-status",
                    ],
                },
                {
                    "id": "DR-002",
                    "name": "Point-in-Time Recovery (PITR)",
                    "description": "Restore to a specific timestamp using Railway WAL archiving",
                    "estimated_rto": "15 minutes",
                    "last_tested": last_verified,
                    "prerequisites": [
                        "WAL archiving must be enabled on the Railway PostgreSQL instance",
                        "Railway CLI installed and authenticated",
                    ],
                    "steps": [
                        "1. Identify the target recovery timestamp (UTC)",
                        "2. Run: railway db restore --point-in-time \"YYYY-MM-DDTHH:MM:SSZ\"",
                        "3. Railway creates a new database instance restored to that timestamp",
                        "4. Update DATABASE_URL env var to point to the new instance",
                        "5. Redeploy the backend service",
                        "6. Verify via GET /health and GET /health/dr-status",
                        "7. Run sanity queries: SELECT count(*) FROM users; SELECT count(*) FROM loans;",
                    ],
                },
                {
                    "id": "DR-003",
                    "name": "Restore from Weekly pg_dump (CI-verified)",
                    "description": "Restore from the weekly pg_dump that was verified by the backup-verify CI workflow",
                    "estimated_rto": "30 minutes",
                    "last_tested": last_verified,
                    "steps": [
                        "1. Download the most recent backup from S3: aws s3 cp s3://$BACKUP_S3_BUCKET/backups/YYYY/MM/perennia-backup-YYYY-MM-DD.sql.gz /tmp/",
                        "2. Decompress: gunzip /tmp/perennia-backup-YYYY-MM-DD.sql.gz",
                        "3. Create a new PostgreSQL instance on Railway",
                        "4. Restore: pg_restore --no-owner --no-acl --dbname=$NEW_DB_URL /tmp/perennia-backup-YYYY-MM-DD.sql",
                        "5. Update DATABASE_URL env var to point to the new instance",
                        "6. Redeploy the backend service",
                        "7. Verify via GET /health and GET /health/dr-status",
                        "8. Run application-layer validation: check critical tables, FK constraints, join queries",
                    ],
                },
                {
                    "id": "DR-004",
                    "name": "Full Environment Rebuild",
                    "description": "Complete rebuild of the production environment from scratch",
                    "estimated_rto": "60 minutes",
                    "last_tested": None,
                    "steps": [
                        "1. Create new Railway project (or use existing backup project)",
                        "2. Deploy PostgreSQL service",
                        "3. Restore database using DR-003 procedure",
                        "4. Set all environment variables from the env var backup (Railway settings export)",
                        "5. Deploy backend service from main branch",
                        "6. Update DNS records for api.perenniaai.com",
                        "7. Verify via GET /health/deep",
                        "8. Verify frontend connectivity at app.perenniaai.com",
                        "9. Run smoke tests: create lead, create loan, run AI agent query",
                    ],
                },
            ],
            "contacts": {
                "primary_oncall": "Platform team",
                "escalation": "Engineering lead",
                "infrastructure": "Railway support (https://railway.app/support)",
            },
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        return runbook

    # ========================================================================
    # DR Status — comprehensive disaster recovery posture check
    # ========================================================================

    @app.get("/health/dr-status", tags=["Health"])
    async def dr_status():
        """
        Disaster recovery status endpoint.

        Returns the complete DR posture: backup freshness, multi-layer
        backup strategy, RPO/RTO compliance, and PITR readiness.
        No authentication required so monitoring can poll continuously.
        """
        backup_status = _check_backup_freshness()
        rpo_rto = _compute_rpo_rto_compliance(backup_status, _APP_START_TIME)

        # Check S3 bucket configuration
        s3_configured = bool(os.getenv("BACKUP_S3_BUCKET", "").strip())

        # Check Railway API token (needed for automated env var updates)
        railway_token_configured = bool(os.getenv("RAILWAY_API_TOKEN", "").strip())

        return {
            "status": "ok" if backup_status.get("status") == "ok" else backup_status.get("status", "unknown"),
            "backup_freshness": backup_status,
            "disaster_recovery": rpo_rto,
            "infrastructure": {
                "s3_archival_configured": s3_configured,
                "railway_api_configured": railway_token_configured,
                "env_var_feedback_loop": railway_token_configured,
                "s3_fallback_available": s3_configured,
            },
            "runbook_url": "/health/dr-runbook",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }


# ==========================================================================
# Admin authentication helper (module-level, reused by multiple endpoints)
# ==========================================================================

def _authenticate_admin(request: Request) -> bool:
    """Check whether the request carries valid admin credentials.

    Accepts either:
    - X-API-Key header matching ADMIN_API_KEY env var
    - Authorization: Bearer <token> with a valid RS256 or HS256 JWT

    Returns True if authenticated, False otherwise.
    """
    # Check admin API key first (simpler, bypasses CSRF)
    api_key_header = request.headers.get("X-API-Key", "")
    admin_key = os.getenv("ADMIN_API_KEY", "")
    if admin_key and api_key_header and secrets.compare_digest(api_key_header, admin_key):
        return True

    # Check Bearer token
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer ") and len(auth_header) > 10:
        token = auth_header[7:]
        try:
            from auth.tokens import _verify_secure_token
            payload = _verify_secure_token(token)
            if payload:
                return True
        except (ImportError, Exception):
            pass
        try:
            import jwt as jose_jwt
            secret_key = os.getenv("SECRET_KEY", "")
            algorithm = os.getenv("JWT_ALGORITHM", "HS256")
            if secret_key:
                payload = jose_jwt.decode(token, secret_key, algorithms=[algorithm], options={"verify_aud": False})
                if payload.get("sub"):
                    return True
        except Exception as _exc:  # noqa: BLE001
            pass

    return False


# ==========================================================================
# Deep health check helper functions (module-level, outside register func)
# ==========================================================================

async def _deep_check_database(session_local):
    """Test database connectivity with SELECT 1 and measure latency."""
    loop = asyncio.get_event_loop()

    def _db_ping():
        start = time.monotonic()
        db = session_local()
        try:
            result = db.execute(text("SELECT 1"))
            result.fetchone()
            latency_ms = round((time.monotonic() - start) * 1000, 1)
            return {"status": "ok", "latency_ms": latency_ms}
        except Exception as e:
            latency_ms = round((time.monotonic() - start) * 1000, 1)
            return {"status": "error", "latency_ms": latency_ms, "error": str(e)[:200]}
        finally:
            db.close()

    return await loop.run_in_executor(None, _db_ping)


def _deep_check_pool_stats():
    """Get database connection pool statistics."""
    start = time.monotonic()
    try:
        from db import get_pool_status
        pool_info = get_pool_status()
        latency_ms = round((time.monotonic() - start) * 1000, 1)
        # Normalize status
        raw_status = pool_info.get("status", "healthy")
        pool_info["status"] = "ok" if raw_status in ("healthy",) else ("error" if raw_status == "saturated" else raw_status)
        pool_info["latency_ms"] = latency_ms
        return pool_info
    except Exception as e:
        return {"status": "error", "error": str(e)[:200]}


def _deep_check_redis():
    """Test Redis connectivity and measure latency."""
    redis_url = os.getenv("REDIS_URL")
    if not redis_url:
        return {"status": "ok", "note": "REDIS_URL not set, using in-memory fallback"}

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
        except Exception as _exc:  # noqa: BLE001
            pass
        try:
            info_clients = r.info(section="clients")
            connected_clients = info_clients.get("connected_clients", "unknown")
        except Exception as _exc:  # noqa: BLE001
            pass

        r.close()
        return {
            "status": "ok",
            "latency_ms": latency_ms,
            "memory_used": memory_used,
            "connected_clients": connected_clients,
        }
    except ImportError:
        return {"status": "ok", "note": "redis package not installed, using in-memory fallback"}
    except Exception as e:
        return {"status": "error", "error": str(e)[:200]}


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
    """Check process memory usage (RSS in MB)."""
    rss_mb = None

    try:
        import resource
        import platform
        rusage = resource.getrusage(resource.RUSAGE_SELF)
        # ru_maxrss is in bytes on macOS, kilobytes on Linux
        if platform.system() == "Darwin":
            rss_mb = round(rusage.ru_maxrss / (1024 * 1024), 1)
        else:
            rss_mb = round(rusage.ru_maxrss / 1024, 1)
    except ImportError:
        pass

    # Fallback for Linux: read /proc/self/status
    if rss_mb is None:
        try:
            with open("/proc/self/status", "r") as f:
                for line in f:
                    if line.startswith("VmRSS:"):
                        rss_kb = int(line.split()[1])
                        rss_mb = round(rss_kb / 1024, 1)
                        break
        except Exception as _exc:  # noqa: BLE001
            pass

    if rss_mb is None:
        return {"status": "ok", "rss_mb": None, "note": "Could not determine memory usage"}

    status = "ok"
    if rss_mb > 1024:
        status = "warning"
    if rss_mb > 2048:
        status = "error"

    return {"status": status, "rss_mb": rss_mb}


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


# ==========================================================================
# Backup verification freshness check
# ==========================================================================

# Warning threshold: flag if no verified backup in more than 8 days
_BACKUP_STALE_DAYS = 8

# --- RPO / RTO compliance targets ---
# RPO: max acceptable data loss window (7 days — Railway PITR daily snapshots)
RPO_TARGET_SECONDS = 7 * 24 * 60 * 60  # 604800 seconds (7 days)
# RTO: max acceptable downtime before full service is restored (30 minutes)
RTO_TARGET_SECONDS = 30 * 60  # 1800 seconds (30 min)


def _read_backup_timestamp_from_s3() -> str | None:
    """Attempt to read the latest-backup-verified.txt timestamp from S3.

    Returns the raw timestamp string if successful, None otherwise.
    This is a best-effort fallback -- never raises.
    """
    bucket = os.getenv("BACKUP_S3_BUCKET", "").strip()
    if not bucket:
        return None
    try:
        import boto3
        from botocore.config import Config as BotoConfig

        s3 = boto3.client(
            "s3",
            config=BotoConfig(connect_timeout=3, read_timeout=3),
        )
        obj = s3.get_object(
            Bucket=bucket,
            Key="backups/latest-backup-verified.txt",
        )
        return obj["Body"].read().decode("utf-8").strip()
    except Exception as e:
        logger.debug(f"S3 backup timestamp fallback failed: {e}")
        return None


def _parse_backup_timestamp(raw: str, source: str = "env") -> dict:
    """Parse an ISO-8601 backup timestamp and return freshness status."""
    from datetime import timedelta

    try:
        ts_str = raw.replace("Z", "+00:00") if raw.endswith("Z") else raw
        last_verified = datetime.fromisoformat(ts_str)
        if last_verified.tzinfo is None:
            last_verified = last_verified.replace(tzinfo=timezone.utc)

        age = datetime.now(timezone.utc) - last_verified
        age_days = round(age.total_seconds() / 86400, 1)

        result = {
            "last_verified": last_verified.isoformat(),
            "age_days": age_days,
            "source": source,
        }

        if age > timedelta(days=_BACKUP_STALE_DAYS):
            result["status"] = "warning"
            result["message"] = (
                f"No backup verification in {age_days} days "
                f"(threshold: {_BACKUP_STALE_DAYS} days)."
            )
        else:
            result["status"] = "ok"

        return result
    except (ValueError, TypeError) as e:
        return {
            "status": "error",
            "note": f"Could not parse backup timestamp: {raw!r}",
            "error": str(e),
            "source": source,
        }


def _check_backup_freshness():
    """Check when the last backup verification succeeded.

    Reads the LAST_BACKUP_VERIFIED environment variable (ISO-8601 timestamp)
    which should be set by the deployment pipeline after a successful
    backup-verify workflow run.  If the env var is not set, falls back to
    reading the latest-backup-verified.txt file from S3 (requires
    BACKUP_S3_BUCKET env var and AWS credentials).

    If neither source is available, returns status "unknown".
    If the timestamp is older than 8 days, returns status "warning".
    """
    # Primary: check env var (set by Railway CLI in backup-verify workflow)
    raw = os.getenv("LAST_BACKUP_VERIFIED", "").strip()
    if raw:
        return _parse_backup_timestamp(raw, source="env")

    # Fallback: read from S3 timestamp file
    s3_raw = _read_backup_timestamp_from_s3()
    if s3_raw:
        return _parse_backup_timestamp(s3_raw, source="s3")

    return {
        "status": "unknown",
        "note": (
            "LAST_BACKUP_VERIFIED env var not set and S3 fallback "
            "unavailable. Configure the backup-verify workflow to "
            "update this value after each successful run."
        ),
    }


def _compute_rpo_rto_compliance(backup_status: dict, app_start_monotonic: float) -> dict:
    """Compute RPO and RTO compliance from backup status and app uptime.

    Returns a dict with RPO/RTO targets, current measurements, compliance
    booleans, and the multi-layer backup strategy so monitoring dashboards
    can alert on violations and auditors can see all backup methods.
    """
    from datetime import timedelta

    result = {
        "rpo_target_seconds": RPO_TARGET_SECONDS,
        "rpo_target_human": "7 days",
        "rto_target_seconds": RTO_TARGET_SECONDS,
        "rto_target_human": "30 minutes",
    }

    # --- Multi-layer backup strategy ---
    result["backup_methods"] = [
        {
            "name": "railway_daily_snapshots",
            "description": "Railway automated daily PostgreSQL snapshots with 7-day retention",
            "frequency": "daily",
            "retention": "7 days",
            "rpo_contribution": "24 hours (last snapshot)",
            "rto_contribution": "~10 minutes (Railway snapshot restore)",
            "type": "automated",
        },
        {
            "name": "weekly_pg_dump_ci",
            "description": "Weekly pg_dump via GitHub Actions CI, restored into scratch DB to verify restorability",
            "frequency": "weekly (Sunday 08:00 UTC)",
            "retention": "90 days (GitHub Actions artifact)",
            "rpo_contribution": "7 days (last verified dump)",
            "rto_contribution": "~30 minutes (pg_restore into fresh instance)",
            "type": "verified",
            "last_verified": backup_status.get("last_verified"),
        },
        {
            "name": "s3_archival",
            "description": "Compressed pg_dump uploaded to S3 with STANDARD_IA storage class for long-term off-site retention",
            "frequency": "weekly (after successful CI verification)",
            "retention": "indefinite (S3 lifecycle policy)",
            "rpo_contribution": "7 days (mirrors CI dump)",
            "rto_contribution": "~45 minutes (S3 download + pg_restore)",
            "type": "archival",
            "bucket_configured": bool(os.getenv("BACKUP_S3_BUCKET", "").strip()),
        },
    ]

    # --- RPO compliance: is the last verified backup within the RPO window? ---
    backup_age_days = backup_status.get("age_days")
    if backup_age_days is not None:
        backup_age_seconds = backup_age_days * 86400
        result["rpo_current_seconds"] = round(backup_age_seconds)
        result["rpo_compliant"] = backup_age_seconds <= RPO_TARGET_SECONDS
    else:
        # No backup timestamp available -- cannot confirm compliance
        result["rpo_current_seconds"] = None
        result["rpo_compliant"] = None  # indeterminate

    # --- RTO measurement: how long did the last cold-start take? ---
    # Use current uptime as a proxy: if the app just started, the elapsed
    # time since module load approximates the startup portion of RTO.
    # A full RTO also includes Railway PITR restore (~10-15 min) which
    # we cannot measure live, so we report the app-start component and
    # an estimated total.
    uptime_seconds = round(time.monotonic() - app_start_monotonic, 1)

    # Estimated PITR restore time (Railway documentation: ~10-15 min)
    ESTIMATED_PITR_RESTORE_SECONDS = 900  # 15 min conservative estimate

    # If the app has been up for < 5 minutes, the startup latency is
    # a reasonable RTO component measurement. After that we just report
    # the estimate.
    if uptime_seconds < 300:
        app_start_seconds = round(uptime_seconds, 1)
    else:
        # App has been up a while; we don't know the actual startup time.
        # Report None for the measured component.
        app_start_seconds = None

    result["rto_estimated_total_seconds"] = (
        ESTIMATED_PITR_RESTORE_SECONDS + (app_start_seconds or 120)
    )
    result["rto_app_start_seconds"] = app_start_seconds
    result["rto_pitr_estimate_seconds"] = ESTIMATED_PITR_RESTORE_SECONDS
    result["rto_compliant"] = (
        result["rto_estimated_total_seconds"] <= RTO_TARGET_SECONDS
    )

    return result

