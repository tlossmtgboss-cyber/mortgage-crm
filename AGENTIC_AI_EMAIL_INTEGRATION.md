# Agentic AI Email Integration - Architecture Plan

## 🎯 Vision
The AI acts as the "quarterback" - monitoring Outlook emails, extracting information, updating CRM fields, moving leads through stages, and creating tasks for user review. Over time, AI learns and reduces manual intervention.

---

## 🏗️ System Architecture

### 1. Microsoft Graph API Integration
**Purpose**: Connect to Outlook to read emails

**Components**:
- OAuth 2.0 authentication flow
- Microsoft Graph API client
- Email webhook subscriptions (real-time) or polling (batch)
- Secure token management

**Required Credentials**:
- Azure AD App Registration
- Client ID & Client Secret
- Redirect URI
- API Permissions: Mail.Read, Mail.ReadWrite

### 2. Email Monitoring Service
**Purpose**: Continuously monitor inbox for new/updated emails

**Features**:
- Real-time webhooks (preferred) or scheduled polling
- Filter by sender, subject, folder
- Track processed emails to avoid duplicates
- Queue system for processing

**Flow**:
```
Outlook Email Received
  ↓
Webhook/Poll Detects New Email
  ↓
Add to Processing Queue
  ↓
AI Email Parser
```

### 3. AI Email Parser & Extractor
**Purpose**: Use AI to understand email content and extract CRM-relevant data

**AI Models to Use**:
- OpenAI GPT-4 or Claude 3.5 Sonnet
- Structured output for field extraction
- Context-aware understanding

**Extraction Categories**:

#### Lead/Client Information
- Name (first, last)
- Email address
- Phone number
- Property address
- Property value
- Loan amount
- Credit score
- Employment status
- Income information
- Down payment

#### Status & Stage Signals
- Email patterns that indicate stage changes:
  - "I'm interested" → New Lead
  - "Here's my documents" → Document Collection
  - "Approved by underwriter" → Underwriting
  - "Clear to close" → Closing
  - "Loan funded" → Closed

#### Action Items
- Questions asked (create task to respond)
- Documents requested (create task to follow up)
- Appointments mentioned (create calendar task)
- Deadlines mentioned (create reminder task)

**AI Prompt Template**:
```
Analyze this email and extract all mortgage CRM relevant information:

EMAIL:
From: {sender}
Subject: {subject}
Date: {date}
Body: {body}

Extract:
1. Lead/Client identifying information
2. Property details
3. Financial information
4. Stage/status signals
5. Required actions
6. Confidence level (0-100) for each extraction

Format as structured JSON.
```

### 4. Task Approval Workflow
**Purpose**: All AI-suggested changes create tasks for user review initially

**Task Types**:

#### Update Task
- **Title**: "AI suggests updating [Lead Name]"
- **Description**: What AI found and wants to change
- **Actions**: Approve, Reject, Edit
- **Fields**: Show before/after values
- **Confidence**: Display AI confidence score

#### Stage Change Task
- **Title**: "AI suggests moving [Lead Name] to [New Stage]"
- **Description**: Why AI thinks stage should change
- **Evidence**: Email content that triggered it
- **Actions**: Approve, Reject, Keep Current Stage

#### Response Task
- **Title**: "Client question requires response: [Lead Name]"
- **Description**: Question from email
- **Suggested Response**: AI-generated draft reply
- **Actions**: Send, Edit & Send, Skip

**Task Schema Enhancement**:
```python
class Task(Base):
    # Existing fields...
    task_type = Column(String)  # "ai_update", "ai_stage_change", "ai_response"
    ai_suggestion = Column(JSON)  # Structured AI suggestion
    ai_confidence = Column(Float)  # 0-100 confidence score
    ai_approved = Column(Boolean)  # User approval status
    approval_timestamp = Column(DateTime)
    suggested_changes = Column(JSON)  # Before/after values
```

### 5. Learning & Confidence System
**Purpose**: Reduce manual reviews as AI learns from user approvals

**Confidence Scoring**:
- Start: All tasks require approval (confidence threshold: 0%)
- Learning: Track approval/rejection patterns
- Auto-approve: After N approvals, auto-execute high-confidence actions

**Learning Metrics**:
```python
class AILearningMetric(Base):
    action_type = Column(String)  # "field_update", "stage_change", etc.
    field_name = Column(String)  # Which field was updated
    confidence_threshold = Column(Float)  # Current auto-approval threshold
    total_suggestions = Column(Integer)
    approved_count = Column(Integer)
    rejected_count = Column(Integer)
    accuracy_rate = Column(Float)  # approved / total
    last_updated = Column(DateTime)
```

**Auto-Approval Rules**:
- Accuracy > 95% AND suggestions > 10 → Auto-approve at 90% confidence
- Accuracy > 90% AND suggestions > 25 → Auto-approve at 85% confidence
- Accuracy > 85% AND suggestions > 50 → Auto-approve at 80% confidence

**User Controls**:
- Settings to adjust auto-approval thresholds
- Per-field or per-action-type controls
- Manual override for specific lead types

### 6. Email-to-Stage Automation
**Purpose**: Intelligently move leads through pipeline based on email signals

**Stage Detection Patterns**:

```python
STAGE_SIGNALS = {
    "NEW": [
        "interested in buying",
        "looking for a loan",
        "want to get pre-approved",
        "first time home buyer"
    ],
    "CONTACTED": [
        "thanks for reaching out",
        "here's my information",
        "can we schedule a call"
    ],
    "QUALIFIED": [
        "my credit score is",
        "my income is",
        "here are my documents"
    ],
    "APPLICATION": [
        "submitted application",
        "application received",
        "loan application"
    ],
    "PROCESSING": [
        "underwriting",
        "reviewing documents",
        "additional documentation needed"
    ],
    "CLOSING": [
        "clear to close",
        "closing date",
        "final walkthrough"
    ],
    "WON": [
        "congratulations",
        "loan funded",
        "keys received",
        "closed successfully"
    ]
}
```

**Multi-Signal Analysis**:
- Combine email content, sender, timing, and history
- Don't move backwards without user approval
- Higher confidence threshold for stage changes

---

## 📊 Implementation Phases

### Phase 1: Foundation (Week 1-2)
✅ **Goals**: Basic email reading and storage
- [ ] Set up Azure AD App for Microsoft Graph
- [ ] Implement OAuth flow for Outlook
- [ ] Create email fetching service
- [ ] Store emails in database
- [ ] Basic email display in CRM

### Phase 2: AI Parsing (Week 3-4)
✅ **Goals**: AI can extract information from emails
- [ ] Integrate OpenAI/Claude API
- [ ] Build email parsing prompts
- [ ] Extract lead information
- [ ] Extract stage signals
- [ ] Store AI extractions

### Phase 3: Task Workflow (Week 5-6)
✅ **Goals**: AI suggestions create tasks for review
- [ ] Enhance Task model for AI suggestions
- [ ] Create AI suggestion task types
- [ ] Build approval UI components
- [ ] Implement approve/reject actions
- [ ] Track approval history

### Phase 4: Learning System (Week 7-8)
✅ **Goals**: AI learns from approvals
- [ ] Create learning metrics database
- [ ] Track approval patterns
- [ ] Calculate confidence scores
- [ ] Implement auto-approval logic
- [ ] User controls for thresholds

### Phase 5: Full Automation (Week 9-10)
✅ **Goals**: End-to-end intelligent automation
- [ ] Real-time webhook processing
- [ ] Automatic stage transitions
- [ ] Email response generation
- [ ] Performance optimization
- [ ] Testing & refinement

---

## 🔧 Technical Requirements

### Backend Services

#### EmailService
```python
class EmailService:
    async def fetch_emails(self, user_id, since_date)
    async def parse_email_with_ai(self, email_content)
    async def extract_lead_info(self, email_content)
    async def detect_stage_signals(self, email_content)
    async def create_approval_task(self, suggestion)
```

#### AILearningService
```python
class AILearningService:
    def record_approval(self, action_type, approved)
    def get_confidence_threshold(self, action_type, field)
    def should_auto_approve(self, confidence, action_type)
    def update_learning_metrics(self)
```

#### AutomationService
```python
class AutomationService:
    async def process_email_queue(self)
    async def apply_approved_changes(self, task_id)
    async def auto_update_with_confidence(self, suggestion)
    async def notify_user_of_changes(self, changes)
```

### Database Schema Additions

```python
class Email(Base):
    id = Column(Integer, primary_key=True)
    message_id = Column(String, unique=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    lead_id = Column(Integer, ForeignKey("leads.id"))
    sender = Column(String)
    subject = Column(String)
    body = Column(Text)
    received_date = Column(DateTime)
    processed = Column(Boolean, default=False)
    ai_extracted_data = Column(JSON)
    created_at = Column(DateTime)

class AIAction(Base):
    id = Column(Integer, primary_key=True)
    email_id = Column(Integer, ForeignKey("emails.id"))
    lead_id = Column(Integer, ForeignKey("leads.id"))
    action_type = Column(String)  # "update_field", "change_stage", "create_task"
    field_name = Column(String)
    old_value = Column(String)
    new_value = Column(String)
    confidence = Column(Float)
    approved = Column(Boolean)
    auto_applied = Column(Boolean)
    created_at = Column(DateTime)
    approved_at = Column(DateTime)
```

### Frontend Components

#### AI Task Dashboard
- View pending AI suggestions
- Approve/reject in bulk
- See confidence scores
- View email source

#### Learning Metrics Dashboard
- Show AI accuracy by field/action type
- Adjust auto-approval thresholds
- View approval history
- Disable auto-approval for specific actions

#### Email Activity Log
- View all processed emails
- See what was extracted
- Review AI decisions
- Manual reprocessing

---

## 🔐 Security & Privacy

### Data Protection
- Encrypt email content at rest
- Secure OAuth tokens
- Audit log all AI actions
- User consent for email access

### Permissions
- Role-based access to AI features
- Admin controls for auto-approval
- Per-user email integration
- Privacy settings

### Compliance
- GDPR considerations for email storage
- Data retention policies
- Right to be forgotten
- Audit trail for all changes

---

## 📈 Success Metrics

### Performance
- Email processing time < 30 seconds
- AI extraction accuracy > 90%
- Auto-approval rate after 3 months > 70%
- User task reduction > 60%

### User Experience
- Tasks created per day (trending down)
- User approval rate (trending up)
- Time saved per week (trending up)
- User satisfaction score

---

## 🚀 Quick Start Implementation

### Immediate Next Steps
1. **Azure Setup**: Create Azure AD App for Microsoft Graph
2. **Environment Variables**: Add Graph API credentials
3. **Database Migration**: Add Email and AIAction tables
4. **Basic Email Fetch**: Implement simple email retrieval
5. **AI Test**: Test email parsing with OpenAI/Claude

### First Working Demo
**Goal**: Show AI reading one email and suggesting a field update

**Steps**:
1. Fetch 1 email from Outlook
2. Send to AI for parsing
3. Display suggested changes
4. Create approval task
5. User approves
6. Apply changes to lead

---

## 💡 Questions to Clarify

1. **Microsoft Account**: Do you have admin access to create Azure AD apps?
2. **AI Provider**: Prefer OpenAI GPT-4 or Claude 3.5 Sonnet for email parsing?
3. **Email Volume**: How many emails per day do you typically receive?
4. **Priority**: Start with lead updates or stage automation first?
5. **Manual Review**: Initially, should ALL AI suggestions require approval?
6. **Email Folders**: Should we monitor all folders or specific ones (Inbox, specific folder)?
7. **Response Generation**: Should AI draft email responses for user review?

---

## 📋 Environment Variables Needed

```bash
# Microsoft Graph API
MICROSOFT_CLIENT_ID=your_client_id
MICROSOFT_CLIENT_SECRET=your_client_secret
MICROSOFT_TENANT_ID=your_tenant_id
MICROSOFT_REDIRECT_URI=https://your-app.com/auth/callback

# AI Provider
OPENAI_API_KEY=your_openai_key
# OR
ANTHROPIC_API_KEY=your_claude_key

# AI Settings
AI_CONFIDENCE_THRESHOLD=0.85
AI_AUTO_APPROVE_ENABLED=true
AI_LEARNING_MODE=true
```

---

**Ready to proceed?** Let me know:
1. If you want to start with Phase 1 (email connection)
2. Your Azure AD setup status
3. Which AI provider you prefer
4. Any specific email patterns or workflows to prioritize
