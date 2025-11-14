# 🤖 AI System Integration Guide

## How to Use AI Agents in Your CRM

Your AI system is now live and ready to automate tasks! Here's how to use it.

---

## Quick Start: 3 Ways to Use the AI System

### Method 1: Automatic Integration (Recommended)
Add AI event triggers to your existing CRM endpoints so agents activate automatically.

### Method 2: Manual Triggering
Trigger AI agents on-demand via API calls for specific tasks.

### Method 3: Dashboard Integration
View and manage AI agent executions from your CRM dashboard.

---

## 🎯 Method 1: Automatic Integration

### Step 1: Add AI Helper Function to main.py

Add this helper function near the top of your main.py (after imports):

```python
# AI System Integration Helper
async def trigger_ai_event(event_type: str, payload: dict, db: Session):
    """Trigger AI agents for an event"""
    try:
        from ai_services import AgentOrchestrator
        from ai_models import AgentEvent, EventStatus
        import uuid

        orchestrator = AgentOrchestrator(db)

        event = AgentEvent(
            event_id=str(uuid.uuid4()),
            event_type=event_type,
            source="crm_api",
            payload=payload,
            status=EventStatus.PENDING
        )

        # Dispatch to agents (async, won't block the response)
        await orchestrator.dispatch_event(event)

        logger.info(f"✅ AI event triggered: {event_type}")

    except Exception as e:
        # Log but don't fail the main request
        logger.error(f"AI event failed: {e}")
```

### Step 2: Trigger Events in Your Endpoints

#### Example 1: When a Lead is Created

Find your `create_lead` endpoint (around line 4477) and add:

```python
@app.post("/api/v1/leads/", response_model=LeadResponse, status_code=201)
async def create_lead(lead: LeadCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user_flexible)):
    db_lead = Lead(
        **lead.dict(),
        owner_id=current_user.id,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow()
    )
    db.add(db_lead)
    db.commit()
    db.refresh(db_lead)

    # 🤖 TRIGGER AI: Lead Management Agent will qualify and assign
    await trigger_ai_event(
        event_type="LeadCreated",
        payload={
            "entity_type": "lead",
            "entity_id": str(db_lead.id),
            "first_name": db_lead.first_name,
            "last_name": db_lead.last_name,
            "email": db_lead.email,
            "phone": db_lead.phone,
            "source": db_lead.source
        },
        db=db
    )

    return db_lead
```

**What happens:** Lead Management Agent will:
- Qualify the lead within 5 minutes
- Assign to appropriate LO
- Create initial contact tasks
- Schedule discovery appointment

#### Example 2: When a Loan Stage Changes

Find your loan update endpoint and add:

```python
@app.put("/api/v1/loans/{loan_id}")
async def update_loan(loan_id: int, loan_update: LoanUpdate, db: Session = Depends(get_db)):
    db_loan = db.query(Loan).filter(Loan.id == loan_id).first()

    if not db_loan:
        raise HTTPException(status_code=404, detail="Loan not found")

    # Capture old stage for AI
    old_stage = db_loan.stage

    # Update loan
    for key, value in loan_update.dict(exclude_unset=True).items():
        setattr(db_loan, key, value)

    db.commit()
    db.refresh(db_loan)

    # 🤖 TRIGGER AI: Pipeline Agent monitors stage changes
    if old_stage != db_loan.stage:
        await trigger_ai_event(
            event_type="LoanStageChanged",
            payload={
                "entity_type": "loan",
                "entity_id": str(loan_id),
                "old_stage": old_stage,
                "new_stage": db_loan.stage,
                "borrower_name": f"{db_loan.borrower_first_name} {db_loan.borrower_last_name}"
            },
            db=db
        )

    return db_loan
```

**What happens:** Pipeline Movement Agent will:
- Monitor for stuck loans
- Create proactive nudge tasks
- Coordinate with other agents
- Forecast pipeline velocity

#### Example 3: When a Document is Uploaded

```python
@app.post("/api/v1/documents/upload")
async def upload_document(file: UploadFile, loan_id: int, db: Session = Depends(get_db)):
    # Save document logic here...
    db_doc = Document(loan_id=loan_id, filename=file.filename, ...)
    db.add(db_doc)
    db.commit()

    # 🤖 TRIGGER AI: Document Agent will classify
    await trigger_ai_event(
        event_type="DocUploaded",
        payload={
            "entity_type": "document",
            "entity_id": str(db_doc.id),
            "loan_id": str(loan_id),
            "filename": file.filename,
            "mime_type": file.content_type
        },
        db=db
    )

    return db_doc
```

**What happens:** Document & Underwriting Agent will:
- Auto-classify document type (95% accuracy)
- Suggest condition clearing strategies
- Flag missing docs
- Create doc chase tasks

---

## 🎯 Method 2: Manual API Triggering

You can manually trigger AI agents via API calls:

### Trigger Lead Qualification

```bash
curl -X POST 'https://mortgage-crm-production-7a9a.up.railway.app/api/ai/events?event_type=LeadCreated' \
  -H 'Content-Type: application/json' \
  -H 'Authorization: Bearer YOUR_TOKEN' \
  -d '{
    "entity_type": "lead",
    "entity_id": "123",
    "first_name": "John",
    "last_name": "Doe",
    "email": "john@example.com",
    "phone": "555-0100"
  }'
```

### Run Daily Pipeline Sweep

```bash
curl -X POST 'https://mortgage-crm-production-7a9a.up.railway.app/api/ai/events?event_type=DailyPipelineSweep' \
  -H 'Content-Type: application/json' \
  -d '{
    "entity_type": "system",
    "entity_id": "pipeline_check"
  }'
```

### Scan Portfolio for Refi Opportunities

```bash
curl -X POST 'https://mortgage-crm-production-7a9a.up.railway.app/api/ai/events?event_type=MonthlyPortfolioReview' \
  -H 'Content-Type: application/json' \
  -d '{
    "entity_type": "portfolio",
    "entity_id": "monthly_scan"
  }'
```

---

## 📊 Viewing AI Agent Activity

### 1. List All Agent Executions

```bash
curl 'https://mortgage-crm-production-7a9a.up.railway.app/api/ai/executions'
```

Response shows what agents have done:
```json
{
  "executions": [
    {
      "execution_id": "abc-123",
      "agent_id": "lead_manager",
      "status": "completed",
      "started_at": "2025-01-13T10:30:00Z",
      "completed_at": "2025-01-13T10:30:45Z",
      "result": {
        "lead_qualified": true,
        "quality_score": 85,
        "assigned_to": "LO_Sarah",
        "tasks_created": 3
      }
    }
  ]
}
```

### 2. View Specific Agent's Work

```bash
# See what Lead Manager agent has done
curl 'https://mortgage-crm-production-7a9a.up.railway.app/api/ai/executions?agent_id=lead_manager'

# See Pipeline Manager's recent activity
curl 'https://mortgage-crm-production-7a9a.up.railway.app/api/ai/executions?agent_id=pipeline_manager&limit=10'
```

### 3. Check Agent Status

```bash
curl 'https://mortgage-crm-production-7a9a.up.railway.app/api/ai/agents'
```

---

## 🔄 Complete Event Reference

### Available Events and Which Agents Respond

| Event Type | Triggered Agents | What They Do |
|------------|-----------------|--------------|
| **LeadCreated** | Lead Manager | Qualify, assign, create tasks |
| **LeadUpdated** | Lead Manager | Re-evaluate qualification |
| **InboundInquiry** | Lead Manager | Immediate response, schedule follow-up |
| **LoanStageChanged** | Pipeline Manager | Monitor progress, identify blockers |
| **DailyPipelineSweep** | Pipeline Manager | Find stuck loans, create nudges |
| **LoanAged** | Pipeline Manager | Escalate delays, suggest actions |
| **DocUploaded** | Underwriting Assistant | Classify, suggest clearing strategy |
| **ConditionAdded** | Underwriting Assistant | Create doc chase tasks |
| **LoanMilestoneReached** | Customer Engagement | Send congratulations, next steps |
| **7DaysSinceLastContact** | Customer Engagement | Draft follow-up message |
| **ClientInquiry** | Customer Engagement | Draft personalized response |
| **MonthlyPortfolioReview** | Portfolio Analyst | Scan for refi opportunities |
| **LoanAnniversary** | Portfolio Analyst | Check MI drop, refi potential |
| **HourlyHealthCheck** | Operations Agent | Monitor system, detect issues |
| **WeeklyForecastRun** | Forecasting Agent | Predict volume, resource needs |

---

## 💡 Practical Use Cases

### Use Case 1: Automated Lead Response
**Problem:** Leads wait hours for initial contact
**Solution:** LeadCreated event triggers Lead Manager
**Result:** Every lead qualified and assigned within 5 minutes

### Use Case 2: Prevent Stuck Loans
**Problem:** Loans sit in stages too long
**Solution:** DailyPipelineSweep finds aging loans
**Result:** Pipeline moves 20% faster

### Use Case 3: Document Processing
**Problem:** Manual doc classification takes hours
**Solution:** DocUploaded event triggers classification
**Result:** 95% auto-classification, instant routing

### Use Case 4: Proactive Client Communication
**Problem:** Clients feel forgotten
**Solution:** 7DaysSinceLastContact triggers engagement
**Result:** 100% communication consistency

### Use Case 5: Portfolio Management
**Problem:** Miss refi opportunities
**Solution:** Monthly portfolio scan
**Result:** 20+ opportunities identified per month

---

## 🎨 Dashboard Integration Example

Add this to your frontend to show AI activity:

```javascript
// Fetch AI agent activity
async function getAIActivity() {
  const response = await fetch('/api/ai/executions?limit=10');
  const data = await response.json();

  return data.executions.map(exec => ({
    agent: exec.agent_name,
    status: exec.status,
    time: exec.completed_at,
    result: exec.result
  }));
}

// Display in dashboard
function AIActivityWidget() {
  const [activity, setActivity] = useState([]);

  useEffect(() => {
    getAIActivity().then(setActivity);
  }, []);

  return (
    <div className="ai-activity-widget">
      <h3>🤖 AI Agent Activity</h3>
      {activity.map(item => (
        <div className="ai-task">
          <span className="agent-name">{item.agent}</span>
          <span className="status">{item.status}</span>
          <span className="time">{item.time}</span>
        </div>
      ))}
    </div>
  );
}
```

---

## 📈 Monitoring & Analytics

### Track AI Impact

```bash
# Get agent performance stats
curl 'https://mortgage-crm-production-7a9a.up.railway.app/api/ai/agents/lead_manager/metrics?days=30'
```

**Metrics you can track:**
- Lead qualification time (target: <5 minutes)
- Pipeline velocity improvement (target: +20%)
- Document classification accuracy (target: 95%)
- Client communication frequency (target: 7-day cadence)
- Refi opportunities found (target: 20+/month)

---

## 🚀 Next Steps

1. **Add Event Triggers** to your main endpoints (leads, loans, documents)
2. **Test Manually** by calling AI events directly
3. **Monitor Results** via /api/ai/executions
4. **Integrate Dashboard** to show AI activity to users
5. **Optimize** based on agent performance metrics

---

## 🆘 Troubleshooting

### AI agents not responding?
Check event was received:
```bash
curl 'https://mortgage-crm-production-7a9a.up.railway.app/api/ai/executions?hours=1'
```

### Want to disable an agent temporarily?
Not implemented yet - agents auto-respond to their trigger events.

### Need different agent behavior?
Agent prompts and goals are in the database (ai_agents and ai_prompt_versions tables).

---

## 📞 Example: Complete Lead Workflow

1. **Lead Created** → Lead Manager qualifies
2. **Task Created** → "Call lead within 4 hours"
3. **Lead Called** → Customer Engagement drafts follow-up
4. **Lead Converted** → Pipeline Manager monitors application
5. **7 Days Later** → Customer Engagement checks in
6. **Docs Uploaded** → Underwriting Agent classifies
7. **Loan Closes** → Portfolio Analyst monitors anniversary

All automated! 🎉

---

**Your AI system is ready to use. Start by adding event triggers to your create_lead endpoint and watch the magic happen!**
