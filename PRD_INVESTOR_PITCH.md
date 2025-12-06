# Perennia AI - Product Requirements Document
## Intelligent Mortgage CRM Platform

**Version:** 1.0
**Date:** December 2025
**Status:** Production Ready

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
- **Integrations:** Microsoft Graph API, Twilio, various LOS systems
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

#### Email Response Training System (NEW)
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

#### Condition Management
- **Condition Tracking** - Monitor PTD, PTC, PTF conditions
- **Automated Clearing** - AI-suggested condition clearances
- **Escalation Workflows** - Alert on overdue conditions
- **Audit Trail** - Complete history of condition changes

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

#### Templates & Personalization
- **Template Library** - Pre-built templates for common scenarios
- **Dynamic Fields** - Personalize with loan/borrower data
- **A/B Testing** - Optimize message effectiveness
- **Compliance Approval** - Marketing compliance workflows

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

#### Reports
- **Production Reports** - Units, volume, revenue
- **Conversion Analysis** - Funnel and fallout metrics
- **SLA Reports** - Cycle time and milestone tracking
- **Financial Reports** - Commission and profitability

#### AI Insights
- **Predictive Analytics** - Close probability and timing
- **Anomaly Detection** - Unusual patterns and risks
- **Recommendations** - AI-suggested actions
- **Benchmarking** - Compare to company/industry averages

### 7. Workflow Automation

#### Milestone Workflows
- **Stage Transitions** - Automated tasks on status change
- **Document Workflows** - Collection and review processes
- **Approval Workflows** - Multi-level approval routing
- **Exception Handling** - Escalation and resolution paths

#### Task Management
- **Smart Task Creation** - AI-generated tasks from emails/events
- **Priority Scoring** - Focus on highest-impact tasks
- **Due Date Management** - Automated deadline tracking
- **Assignment Rules** - Route tasks to right team members

#### Integrations
- **LOS Integration** - Bi-directional sync with loan systems
- **Calendar Sync** - Microsoft/Google calendar integration
- **Accounting Integration** - Commission and fee tracking
- **Third-Party Services** - Appraisal, title, credit vendors

### 8. Mobile Application

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
- **Voice Notes** - Audio notes with transcription

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

### 5. Modern Technology Stack
Built on modern, scalable infrastructure:
- Async processing for high performance
- Containerized deployment for reliability
- API-first design for extensibility
- Mobile-first responsive design

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

## Roadmap

### Current Release (v1.0)
- Full CRM functionality
- AI email processing with learning
- Document management
- Compliance monitoring
- Analytics dashboards
- Mobile app foundation

### Q1 2026
- Enhanced mobile app features
- Voice AI for phone interactions
- Advanced forecasting models
- LOS integrations expansion

### Q2 2026
- Video meeting integration
- Borrower self-service portal
- Advanced marketing automation
- Custom workflow builder

### Q3 2026
- Multi-language support
- White-label capabilities
- Enterprise SSO
- Advanced API marketplace

---

## Pricing Model

### Per-Seat Licensing
| Tier | Users | Price/User/Month | Features |
|------|-------|-----------------|----------|
| Starter | 1-5 | $149 | Core CRM, Basic AI |
| Professional | 6-25 | $199 | Full AI, Integrations |
| Enterprise | 26+ | Custom | White-label, API access |

### Implementation
- **Onboarding:** $2,500 - $10,000 based on complexity
- **Training:** Included in first 90 days
- **Support:** Email/chat included, phone support at Professional+

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
- Branch networks

### Expansion: Large Mortgage Companies
- Enterprise features
- Custom integrations
- White-label options
- Volume-based pricing

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

## Team Requirements

### Current Needs
- **AI/ML Engineers** - Enhance agent capabilities
- **Mobile Developers** - Expand mobile app
- **Sales Team** - Go-to-market execution
- **Customer Success** - Onboarding and retention

### Use of Funds
- 40% - Product Development
- 30% - Sales & Marketing
- 20% - Customer Success
- 10% - Operations

---

## Appendix

### Technical Specifications
- **API Rate Limits:** 1,000 requests/minute
- **Data Retention:** 7 years (configurable)
- **Uptime SLA:** 99.9%
- **Security:** SOC 2 Type II compliant
- **Encryption:** AES-256 at rest, TLS 1.3 in transit

### Integration Partners
- Microsoft 365
- Encompass
- Byte Software
- Twilio
- DocuSign
- Credit bureaus

### Compliance Certifications
- SOC 2 Type II
- CCPA Compliant
- GLBA Compliant
- State licensing support

---

*Document prepared for investor discussions. Confidential.*
