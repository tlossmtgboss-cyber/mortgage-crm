# Product Requirements Document (PRD)
## Agentic AI Mortgage CRM

**Version:** 4.0.0
**Last Updated:** November 16, 2025
**Product Owner:** The Tim Loss Team
**Status:** Production Active

---

## Table of Contents

1. [Executive Summary](#executive-summary)
2. [Product Overview](#product-overview)
3. [Core Features](#core-features)
4. [AI-Powered Features](#ai-powered-features)
5. [Team Management](#team-management)
6. [Performance Management](#performance-management)
7. [Integrations](#integrations)
8. [Analytics & Reporting](#analytics--reporting)
9. [Technical Architecture](#technical-architecture)
10. [User Roles & Permissions](#user-roles--permissions)

---

## Executive Summary

The Agentic AI Mortgage CRM is a comprehensive, AI-powered customer relationship management system specifically designed for mortgage professionals. It combines intelligent automation, seamless integrations, and data-driven insights to help loan officers, processors, and teams manage their entire loan pipeline from lead to close.

### Key Differentiators
- **AI-First Architecture**: Every feature enhanced with AI capabilities
- **Full Lifecycle Management**: Lead capture → Pre-qualification → Application → Processing → Closing
- **Real-Time Automation**: AI handles repetitive tasks, prioritization, and insights
- **Voice-Enabled**: AI Receptionist handles inbound calls 24/7
- **Unified Communication**: Email, SMS, voice, and Teams integration in one platform

---

## Product Overview

### Vision
Transform the mortgage industry by eliminating administrative burden and empowering loan officers to focus on relationships and revenue-generating activities.

### Mission
Provide mortgage professionals with an AI-powered platform that automates 80% of administrative tasks while maintaining compliance and delivering superior customer experience.

### Target Users
- **Primary**: Loan Officers, Mortgage Brokers, Branch Managers
- **Secondary**: Processors, Production Assistants, Team Leaders
- **Tertiary**: Real Estate Partners, Referral Partners

---

## Core Features

### 1. Lead Management

#### 1.1 Lead Capture
- **Multi-Channel Intake**
  - Web form submissions (Buyer's Quick Start)
  - Phone calls (AI Receptionist)
  - Email inquiries (auto-parsed)
  - Manual entry
  - Partner referrals
  - API integrations

- **Lead Enrichment**
  - Automatic phone number validation
  - Email verification
  - Credit score estimation
  - Property value lookup
  - Employment verification hints

#### 1.2 Lead Organization
- **Smart Categorization**
  - Auto-tagging by source
  - Lead score calculation (0-100)
  - Hot/warm/cold classification
  - Qualification status
  - Partnership attribution

- **Lead Assignment**
  - Round-robin distribution
  - Territory-based routing
  - Skill-based assignment
  - Manual override capability
  - Load balancing

#### 1.3 Lead Nurturing
- **Automated Follow-ups**
  - AI-generated email sequences
  - SMS drip campaigns
  - Task creation for team
  - Appointment scheduling
  - Document requests

### 2. Pipeline Management

#### 2.1 Pipeline Stages
1. **New Lead** - Initial contact made
2. **Contacted** - First conversation completed
3. **Pre-Qualified** - Basic qualification done
4. **Application Started** - 1003 in progress
5. **Application Submitted** - Full application received
6. **Processing** - Underwriting in progress
7. **Clear to Close** - Ready for signing
8. **Funded** - Loan closed
9. **Dead/Lost** - Opportunity lost

#### 2.2 Stage Management
- **Visual Kanban Board**
  - Drag-and-drop cards
  - Color-coded by urgency
  - Quick actions on hover
  - Bulk operations
  - Filtering and search

- **Stage-Triggered Automation**
  - Auto-task creation
  - Email notifications
  - Document requests
  - Team assignments
  - Timeline updates

#### 2.3 Pipeline Analytics
- **Real-Time Metrics**
  - Conversion rates per stage
  - Average time in each stage
  - Pipeline velocity
  - Win/loss analysis
  - Revenue forecasting

### 3. Task Management

#### 3.1 Task Creation
- **Automatic Task Generation**
  - AI analyzes emails and creates tasks
  - Stage transitions trigger tasks
  - Deadline-based reminders
  - Compliance checkpoints
  - Follow-up sequences

- **Manual Task Entry**
  - Rich text descriptions
  - File attachments
  - Priority levels (low, medium, high, urgent)
  - Due dates and reminders
  - Task templates

#### 3.2 Task Organization
- **Views**
  - My Tasks (assigned to me)
  - Team Tasks (all team)
  - By Client (grouped by lead)
  - By Due Date (calendar view)
  - Completed (archive)

- **Filtering & Sorting**
  - Priority level
  - Due date
  - Assignment
  - Lead/loan stage
  - Task type

#### 3.3 Task Automation
- **Smart Prioritization**
  - AI ranks by urgency
  - Deadline proximity
  - Client importance
  - Revenue impact
  - Compliance requirements

### 4. Contact Management

#### 4.1 Contact Database
- **Contact Types**
  - Leads (prospects)
  - Clients (active/past)
  - Partners (real estate agents)
  - Vendors (appraisers, title)
  - Team members

- **Contact Fields**
  - Personal info (name, DOB, SSN)
  - Contact details (phone, email, address)
  - Employment data
  - Financial information
  - Preferences
  - Communication history
  - Custom fields

#### 4.2 Communication History
- **Unified Timeline**
  - All emails (sent/received)
  - SMS messages
  - Phone calls (with recordings)
  - Meetings/appointments
  - Document exchanges
  - Notes and annotations

#### 4.3 Relationship Mapping
- **Connections**
  - Co-borrowers
  - Real estate agents
  - Referral sources
  - Family members
  - Business associates

---

## AI-Powered Features

### 5. AI Assistant (Copilot)

#### 5.1 Conversational Interface
- **Natural Language Processing**
  - Ask questions in plain English
  - Context-aware responses
  - Multi-turn conversations
  - Intent recognition
  - Entity extraction

- **Smart Suggestions**
  - Next best actions
  - Email drafts
  - Response templates
  - Document recommendations
  - Meeting prep briefs

#### 5.2 Task Automation
- **Intelligent Actions**
  - Auto-categorize leads
  - Generate email responses
  - Create follow-up tasks
  - Update CRM fields
  - Schedule appointments

#### 5.3 Insights & Analytics
- **Predictive Intelligence**
  - Lead score calculation
  - Conversion probability
  - Risk assessment
  - Revenue forecasting
  - Bottleneck identification

### 6. AI Receptionist (Voice)

#### 6.1 Call Handling
- **24/7 Availability**
  - Professional greeting
  - Caller identification
  - Intent recognition
  - Intelligent routing
  - Appointment scheduling

- **Capabilities**
  - Answer common questions
  - Collect pre-approval info
  - Schedule callbacks
  - Transfer to team members
  - Take messages

#### 6.2 Call Routing
- **Smart Transfer**
  - Identify existing customers
  - Route to loan officer
  - Route to processor
  - Route to production assistant
  - Emergency escalation

- **Context Handoff**
  - Caller name and phone
  - Reason for call
  - Customer history
  - Urgency level
  - Prior conversations

#### 6.3 Dashboard & Analytics
- **Real-Time Monitoring**
  - Active conversations
  - Calls today
  - Appointments booked
  - AI coverage %
  - Error tracking

- **Performance Metrics**
  - Response time
  - Resolution rate
  - Transfer rate
  - Customer satisfaction
  - ROI tracking

#### 6.4 Call Features
- **During Call**
  - Live transcription
  - Sentiment analysis
  - Keyword detection
  - Compliance monitoring
  - Call recording

- **Post-Call**
  - Automatic CRM updates
  - Task creation
  - Email summaries
  - Follow-up scheduling
  - Recording storage

### 7. AI Underwriter

#### 7.1 Automated Analysis
- **Document Review**
  - Income verification
  - Asset verification
  - Credit report analysis
  - Appraisal review
  - Title search

- **Risk Assessment**
  - DTI calculation
  - LTV analysis
  - Credit score impact
  - Fraud detection
  - Compliance check

#### 7.2 Decision Support
- **Recommendations**
  - Loan program suggestions
  - Pricing options
  - Condition requirements
  - Documentation needs
  - Approval probability

### 8. Email Intelligence

#### 8.1 Auto-Processing
- **Email Parsing**
  - Extract key information
  - Identify intent
  - Categorize by type
  - Link to lead/loan
  - Extract documents

- **Auto-Actions**
  - Create tasks
  - Update pipeline stage
  - Schedule follow-ups
  - Save attachments
  - Log communication

#### 8.2 Smart Responses
- **AI-Generated Drafts**
  - Context-aware replies
  - Tone matching
  - Template selection
  - Personalization
  - Grammar check

#### 8.3 Email Sync
- **Outlook Integration**
  - Bi-directional sync
  - Auto-categorization
  - Thread tracking
  - Calendar integration
  - Contact sync

---

## Team Management

### 9. User Management

#### 9.1 User Accounts
- **Account Types**
  - Full users (paid seats)
  - Limited users (read-only)
  - External partners
  - API users
  - Admin accounts

- **User Profile**
  - Personal information
  - Contact details
  - Team assignment
  - Role assignment
  - Permissions
  - Availability calendar

#### 9.2 Team Structure
- **Organizational Hierarchy**
  - Departments
  - Teams
  - Reporting relationships
  - Territory assignments
  - Skill groups

### 10. Roles & Permissions

#### 10.1 Default Roles
1. **Admin** - Full system access
2. **Loan Officer** - Client management, pipeline
3. **Processor** - Document processing, conditions
4. **Production Assistant** - Lead intake, admin support
5. **Manager** - Team oversight, reporting
6. **Partner** - Limited client view

#### 10.2 Permission System
- **Granular Controls**
  - Feature access (50+ permissions)
  - Data visibility
  - Action capabilities
  - Export rights
  - Admin functions

- **Permission Categories**
  - Lead Management (view, create, edit, delete, assign)
  - Pipeline Management (view, update, advance stages)
  - Tasks (view, create, assign, complete)
  - Contacts (view, edit, export)
  - Analytics (view dashboards, export reports)
  - Settings (system config, user management)
  - Integrations (connect services, API access)

#### 10.3 Custom Roles
- **Role Builder**
  - Create custom roles
  - Combine permissions
  - Clone existing roles
  - Set default roles
  - Role templates

#### 10.4 Permission Requests
- **Self-Service**
  - Users can request access
  - Manager approval workflow
  - Temporary permissions
  - Audit trail
  - Expiration dates

---

## Performance Management

### 11. Goals & OKRs

#### 11.1 Goal Setting
- **Goal Framework**
  - Quarterly/annual objectives
  - Key results (KRs) with targets
  - Progress tracking
  - Status indicators
  - Linked responsibilities

- **Goal Types**
  - Revenue targets
  - Volume goals
  - Quality metrics
  - Skill development
  - Process improvements

#### 11.2 Key Results
- **Measurable Outcomes**
  - Numeric targets
  - Current progress
  - Unit of measurement
  - Status (on track, at risk, ahead, blocked)
  - Auto-calculation

#### 11.3 Assessments
- **Self-Assessment**
  - Employee progress updates
  - Achievements documented
  - Challenges noted
  - Support requested

- **Manager Assessment**
  - Performance feedback
  - Coaching notes
  - Development plans
  - Recognition

### 12. Responsibilities & Skills

#### 12.1 Job Descriptions
- **Rich Text Editor**
  - Role overview
  - Key responsibilities
  - Qualifications
  - Success metrics
  - Reporting structure

#### 12.2 Core Responsibilities
- **Responsibility Management**
  - Title and description
  - Ownership level (primary, shared, supportive)
  - Time allocation %
  - Priority level
  - Effective dates
  - Linked skills

- **Responsibility Features**
  - Drag-drop reordering
  - Archive old responsibilities
  - Version history
  - Skill tagging

#### 12.3 Skills Assessment
- **Skill Tracking**
  - Skills library (company-wide)
  - Required proficiency level (1-5)
  - Current proficiency level (1-5)
  - Gap analysis
  - Assessment notes

- **Training Recommendations**
  - Identify skill gaps
  - Suggest training
  - Track progress
  - Next assessment date
  - Manager assessments

#### 12.4 Performance Analytics
- **Team Insights**
  - Skills matrix view
  - Gap analysis
  - Training needs
  - Succession planning
  - Capacity planning

### 13. My Profile

#### 13.1 Employee Self-Service
- **Personal Dashboard**
  - Current role and team
  - Job description
  - Responsibilities
  - Goals and progress
  - Skills assessment

- **Self-Directed Development**
  - View performance goals
  - Update progress
  - Request assessments
  - Identify skill gaps
  - Track achievements

---

## Integrations

### 14. Microsoft Teams

#### 14.1 Teams Integration
- **Features**
  - Send messages from CRM
  - Receive notifications
  - Task reminders
  - Pipeline updates
  - Team collaboration

- **Bot Commands**
  - Create tasks
  - Check pipeline
  - Get lead info
  - Schedule meetings

### 15. Outlook Integration

#### 15.1 Email Sync
- **Bi-Directional Sync**
  - CRM → Outlook
  - Outlook → CRM
  - Thread tracking
  - Attachment sync
  - Contact sync

#### 15.2 Calendar Integration
- **Appointment Management**
  - Sync appointments
  - Book from CRM
  - Availability checking
  - Meeting reminders
  - Location tracking

### 16. SMS/Voice (Twilio)

#### 16.1 SMS Messaging
- **Features**
  - Send individual SMS
  - Bulk messaging
  - Templates
  - Scheduled sends
  - Delivery tracking
  - Reply handling

#### 16.2 Voice Calls
- **Phone System**
  - Click-to-call
  - Call recording
  - Call logs
  - Voicemail transcription
  - Call routing

### 17. AI Voice (VAPI)

#### 17.1 AI Receptionist
- **Voice AI Platform**
  - Natural conversations
  - Function calling
  - Call transfers
  - Appointment booking
  - Pre-approval intake

#### 17.2 Call Recording
- **Compliance**
  - All calls recorded
  - Transcriptions
  - Keyword detection
  - Quality monitoring
  - Storage & retrieval

### 18. Document Management

#### 18.1 File Storage
- **Document Types**
  - Applications (1003)
  - Income docs (W2, paystubs)
  - Asset statements
  - Credit reports
  - Appraisals
  - Title documents
  - Disclosures

#### 18.2 Document Features
- **Management**
  - Upload/download
  - Version control
  - Access permissions
  - Audit trail
  - Expiration tracking

---

## Analytics & Reporting

### 19. Dashboard

#### 19.1 Main Dashboard
- **At-a-Glance Metrics**
  - Pipeline value ($)
  - Active loans count
  - Tasks due today
  - Hot leads
  - Team performance
  - Revenue forecast

#### 19.2 Visual Analytics
- **Charts & Graphs**
  - Pipeline by stage (funnel)
  - Conversion rates (%)
  - Lead sources (pie chart)
  - Volume trends (line graph)
  - Team leaderboard

### 20. AI Receptionist Dashboard

#### 20.1 Real-Time Metrics
- **Live Monitoring**
  - Conversations today
  - Active calls
  - Appointments booked
  - AI coverage %
  - Errors count

#### 20.2 Performance Tracking
- **Operational Metrics**
  - Response times
  - Call duration
  - Transfer rate
  - Resolution rate
  - Customer satisfaction

#### 20.3 Activity Feed
- **Recent Calls**
  - Caller information
  - Call duration
  - Outcome
  - Recording link
  - Transcript
  - Actions taken

#### 20.4 ROI Analytics
- **Business Impact**
  - Labor hours saved
  - Missed calls prevented
  - Revenue generated
  - Cost per interaction
  - ROI percentage

### 21. Pipeline Efficiency Monitor

#### 21.1 Stage Analysis
- **Bottleneck Detection**
  - Average time in stage
  - Conversion rates
  - Drop-off points
  - Efficiency scores
  - Trend analysis

#### 21.2 Drill-Down Views
- **Detailed Insights**
  - Loans in each stage
  - Stuck loans alert
  - Action recommendations
  - Historical trends
  - Comparative analysis

### 22. Reports

#### 22.1 Standard Reports
- **Pre-Built Reports**
  - Pipeline snapshot
  - Lead source performance
  - Conversion funnel
  - Team productivity
  - Revenue forecast
  - Lost loan analysis

#### 22.2 Custom Reports
- **Report Builder**
  - Drag-drop fields
  - Custom filters
  - Date ranges
  - Grouping options
  - Export formats

#### 22.3 Scheduled Reports
- **Automation**
  - Daily/weekly/monthly
  - Email delivery
  - Multiple recipients
  - Format options (PDF, Excel)
  - Custom templates

---

## Technical Architecture

### 23. System Architecture

#### 23.1 Frontend
- **Technology Stack**
  - React 18
  - React Router
  - Axios
  - CSS3 with custom design system
  - Responsive design (mobile-first)

- **Deployment**
  - Vercel hosting
  - CDN delivery
  - Auto-deployment from Git
  - Preview deployments
  - Custom domain support

#### 23.2 Backend
- **Technology Stack**
  - FastAPI (Python)
  - SQLAlchemy ORM
  - PostgreSQL database
  - JWT authentication
  - RESTful API

- **Deployment**
  - Railway hosting
  - Auto-scaling
  - Environment isolation
  - Continuous deployment
  - Health monitoring

#### 23.3 Database
- **PostgreSQL**
  - Relational data model
  - ACID compliance
  - Full-text search
  - JSON support
  - Automated backups

- **Data Models**
  - 50+ tables
  - Foreign key constraints
  - Indexes for performance
  - Audit trails
  - Soft deletes

#### 23.4 AI Services
- **OpenAI Integration**
  - GPT-4o for chat
  - GPT-4o-mini for tasks
  - Embeddings for search
  - Function calling
  - Streaming responses

- **VAPI Integration**
  - Voice AI platform
  - Call handling
  - Real-time transcription
  - Webhook events
  - Transfer capabilities

### 24. Security

#### 24.1 Authentication
- **Methods**
  - Email/password
  - JWT tokens
  - Session management
  - Password requirements
  - Account lockout

#### 24.2 Authorization
- **Access Control**
  - Role-based permissions
  - Feature-level controls
  - Data-level security
  - API key management
  - Audit logging

#### 24.3 Data Protection
- **Security Measures**
  - HTTPS/TLS encryption
  - Database encryption
  - PII protection
  - GDPR compliance
  - SOC 2 ready

### 25. API

#### 25.1 REST API
- **Endpoints**
  - 200+ API routes
  - OpenAPI documentation
  - Versioned endpoints
  - Rate limiting
  - Error handling

#### 25.2 Webhooks
- **Event System**
  - Lead created
  - Stage changed
  - Task completed
  - Call ended
  - Document uploaded

---

## User Roles & Permissions

### 26. Detailed Permissions Matrix

| Permission | Admin | Loan Officer | Processor | Prod Asst | Manager | Partner |
|------------|-------|--------------|-----------|-----------|---------|---------|
| **Lead Management** |
| View All Leads | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ |
| View Own Leads | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Create Leads | ✅ | ✅ | ❌ | ✅ | ✅ | ❌ |
| Edit Leads | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ |
| Delete Leads | ✅ | ❌ | ❌ | ❌ | ✅ | ❌ |
| Assign Leads | ✅ | ❌ | ❌ | ✅ | ✅ | ❌ |
| **Pipeline** |
| View Pipeline | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Update Stage | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ |
| **Tasks** |
| View Tasks | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Create Tasks | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ |
| Assign Tasks | ✅ | ✅ | ❌ | ✅ | ✅ | ❌ |
| Delete Tasks | ✅ | ✅ | ❌ | ❌ | ✅ | ❌ |
| **Analytics** |
| View Dashboard | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ |
| Export Reports | ✅ | ✅ | ❌ | ❌ | ✅ | ❌ |
| **Settings** |
| User Management | ✅ | ❌ | ❌ | ❌ | ✅ | ❌ |
| System Config | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Integrations | ✅ | ❌ | ❌ | ❌ | ✅ | ❌ |
| **Performance Mgmt** |
| View My Profile | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ |
| View Team Profiles | ✅ | ❌ | ❌ | ❌ | ✅ | ❌ |
| Set Goals | ✅ | ❌ | ❌ | ❌ | ✅ | ❌ |
| Assess Skills | ✅ | ❌ | ❌ | ❌ | ✅ | ❌ |

### 27. Permission Request Workflow

1. **User requests permission** → "Request Access" button
2. **Manager receives notification** → Email + in-app
3. **Manager reviews request** → Approve/deny with reason
4. **User notified of decision** → Permission granted or explanation
5. **Audit log created** → Who, what, when tracked

---

## Feature Highlights Summary

### Top 10 Features

1. **AI Receptionist** - 24/7 phone coverage with intelligent routing
2. **Email Intelligence** - Auto-parse emails and create tasks
3. **Smart Pipeline** - Visual kanban with automation
4. **AI Assistant** - Conversational copilot for daily tasks
5. **Performance Management** - Goals, OKRs, skills tracking
6. **Multi-Channel Communication** - Email, SMS, voice, Teams
7. **Permission System** - Granular access control
8. **Real-Time Analytics** - Live dashboards and insights
9. **Document Management** - Secure storage and versioning
10. **Team Collaboration** - Shared tasks, notes, activities

### Automation Capabilities

- ✅ Auto-categorize leads from multiple sources
- ✅ Auto-create tasks from emails
- ✅ Auto-advance pipeline stages
- ✅ Auto-schedule follow-ups
- ✅ Auto-send appointment reminders
- ✅ Auto-log call activities
- ✅ Auto-transcribe voice messages
- ✅ Auto-generate email responses
- ✅ Auto-calculate lead scores
- ✅ Auto-assign leads to team

### Integration Ecosystem

**Built-In:**
- Microsoft Teams (messaging, notifications)
- Outlook (email, calendar sync)
- Twilio (SMS, voice calls)
- VAPI (AI voice assistant)
- OpenAI (GPT-4o for intelligence)

**Via API:**
- Encompass LOS
- Calendly (appointment scheduling)
- DocuSign (e-signatures)
- Credit bureaus
- Appraisal companies

---

## System URLs

**Production Environment:**
- Frontend: https://mortgage-crm-nine.vercel.app
- Backend API: https://app.perenniaai.com
- API Docs: https://app.perenniaai.com/docs
- AI Receptionist: (832) 648-2297

**Key Pages:**
- Login: `/login`
- Dashboard: `/dashboard`
- Pipeline: `/merge`
- Tasks: `/tasks`
- Team: `/team`
- My Profile: `/my-profile`
- AI Receptionist Dashboard: `/ai-receptionist-dashboard`
- Settings: `/settings`

---

## Version History

**v4.0.0** (Nov 2025)
- Added comprehensive performance management
- Added Goals & OKRs system
- Added Skills & Responsibilities tracking
- Added My Profile self-service
- Enhanced AI Receptionist dashboard
- Added webhook logging for calls

**v3.5.0** (Nov 2025)
- Added AI Receptionist with call routing
- Added call transfer system
- Added pre-approval application flow
- Enhanced permission system

**v3.0.0** (Oct 2025)
- Added granular permissions (50+ controls)
- Added permission request workflow
- Added role templates
- Enhanced team management

**v2.0.0** (Sep 2025)
- Added email intelligence
- Added AI Assistant copilot
- Added Teams integration
- Enhanced pipeline automation

**v1.0.0** (Aug 2025)
- Initial release
- Core CRM features
- Basic automation

---

## Future Roadmap

### Q1 2026
- [ ] Mobile app (iOS/Android)
- [ ] Advanced reporting builder
- [ ] LOS bi-directional sync
- [ ] Video calling integration
- [ ] AI-powered underwriting

### Q2 2026
- [ ] Referral partner portal
- [ ] Marketing automation
- [ ] Lead scoring AI enhancement
- [ ] Document AI (OCR extraction)
- [ ] Compliance monitoring

### Q3 2026
- [ ] Multi-language support
- [ ] White-label capability
- [ ] Advanced analytics (predictive)
- [ ] Workflow automation builder
- [ ] Custom integrations marketplace

---

**Document Status:** Active
**Next Review:** December 2025
**Maintained By:** Product Team
