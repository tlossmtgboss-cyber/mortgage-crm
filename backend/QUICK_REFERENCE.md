# Perennia AI Mortgage CRM - Quick Reference

## API Endpoints Cheat Sheet

### Dashboard & Metrics
```bash
# Get full dashboard
GET /api/v1/profitability/dashboard?month=2025-11

# Get metrics only
GET /api/v1/profitability/metrics?month=2025-11

# Get trends (last N months)
GET /api/v1/profitability/trends?months=12
```

### AI Features
```bash
# Natural language query
POST /api/v1/profitability/ai/query
Body: { "question": "Who are my top performers?", "month": "2025-11" }

# Get recommendations
GET /api/v1/profitability/ai/recommendations?month=2025-11

# Hiring analysis
POST /api/v1/profitability/ai/hiring-analysis
Body: { "role_name": "Loan Officer", "salary": 85000 }

# Executive digest
GET /api/v1/profitability/ai/executive-digest?month=2025-11

# Detect anomalies
GET /api/v1/profitability/ai/anomalies?month=2025-11
```

### Data Management
```bash
# List/create expenses
GET /api/v1/profitability/expenses
POST /api/v1/profitability/expenses

# List/create employees
GET /api/v1/profitability/employees
POST /api/v1/profitability/employees

# List/create loans
GET /api/v1/profitability/loans
POST /api/v1/profitability/loans

# List/create roles
GET /api/v1/profitability/roles
POST /api/v1/profitability/roles
```

### Scenarios
```bash
# Run scenario
POST /api/v1/profitability/scenarios/run?base_month=2025-11
Body: { "add_employees": 1, "role": "Loan Officer", "salary": 85000 }

# List saved scenarios
GET /api/v1/profitability/scenarios?saved_only=true
```

## Key Metrics Explained

| Metric | Description | Good Range |
|--------|-------------|------------|
| Cost Per Loan | Total expenses / loans closed | < $5,000 |
| Revenue Per Loan | Total revenue / loans closed | > $6,000 |
| Profit Margin | (Revenue - Expenses) / Revenue | > 15% |
| Break-Even Loans | Expenses / Revenue per loan | Meet or exceed |
| ROI by Role | (Revenue - Cost) / Cost × 100 | > 100% |

## Common AI Questions

**Performance:**
- "Who are my top 3 loan officers by ROI?"
- "Which roles have the highest profit contribution?"
- "How does this month compare to last month?"

**Costs:**
- "What's driving our cost per loan?"
- "Where can we reduce expenses?"
- "How do our costs compare to industry average?"

**Hiring:**
- "Should we hire another loan officer?"
- "What's the ROI of adding a processor?"
- "Are we overstaffed in any area?"

**Strategy:**
- "How can we improve profit margin by 5%?"
- "What are our biggest opportunities?"
- "What risks should we be aware of?"

## Frontend Components

```jsx
// AI Insights Panel
import AIInsightsPanel from '../components/AIInsightsPanel';
<AIInsightsPanel month={selectedMonth} />

// Smart Recommendations
import SmartRecommendations from '../components/SmartRecommendations';
<SmartRecommendations month={selectedMonth} autoLoad={true} />

// Cost to Close Chart
import CostToCloseChart from '../components/CostToCloseChart';
<CostToCloseChart refreshInterval={60000} height={280} />
```

## Environment Setup

```env
# Required
ANTHROPIC_API_KEY=sk-ant-...
DATABASE_URL=postgresql://...

# Optional (for email digests)
SMTP_SERVER=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=email@domain.com
SMTP_PASSWORD=app_password
```

## Testing Endpoints

```bash
# Test AI query
curl -X POST "https://your-api/api/v1/profitability/ai/query" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"question": "What is our cost per loan?"}'

# Test recommendations
curl "https://your-api/api/v1/profitability/ai/recommendations" \
  -H "Authorization: Bearer $TOKEN"
```

## Troubleshooting

**AI features not working:**
- Check ANTHROPIC_API_KEY is set in Railway
- Verify API key has credits

**No data showing:**
- Add employee costs and loans
- Run insight generation

**Chart not updating:**
- Check network tab for API errors
- Verify authentication token

---

## PURL System Endpoints

### Token Management
```bash
# Generate new PURL token
POST /api/purl/generate
Body: { "lead_id": "uuid", "expiry_days": 30 }

# Validate token
GET /api/purl/validate/{token}

# Refresh expiring token
POST /api/purl/refresh/{token}

# Revoke token
DELETE /api/purl/revoke/{token}
```

### Borrower Portal
```bash
# Get portal data
GET /api/purl/portal/{token}

# Get workspace
GET /api/purl/portal/{token}/workspace

# Submit application
POST /api/purl/portal/{token}/application

# Get timeline
GET /api/purl/portal/{token}/timeline
```

### Document Management
```bash
# List documents
GET /api/purl/portal/{token}/documents

# Upload document
POST /api/purl/portal/{token}/documents

# Delete document
DELETE /api/purl/portal/{token}/documents/{doc_id}
```

---

## Agent System Endpoints

### Chat & Interaction
```bash
# Chat with agent
POST /api/agents/chat
Body: { "message": "...", "agent_type": "pipeline_analyst" }

# WebSocket connection
WS /api/agents/ws/{session_id}
```

### Agent Governance
```bash
# Get governance rules
GET /api/agents/governance

# Request approval
POST /api/agents/governance/approval-request

# Approve/reject action
POST /api/agents/governance/approval/{request_id}
```

### Agent Gym
```bash
# List scenarios
GET /api/agents/gym/scenarios

# Run scenario
POST /api/agents/gym/scenario
Body: { "scenario_id": "...", "agent_type": "..." }

# Get results
GET /api/agents/gym/results/{run_id}
```

---

## Common Commands

### Quick Start
```bash
# Backend
cd backend && source venv/bin/activate
pip install -r requirements.txt
python main.py

# Frontend
cd frontend && npm install && npm start
```

### Database
```bash
# Run all migrations
python migrations/add_purl_system.py
python migrations/add_agent_governance_system.py

# Seed data
python scripts/seed_test_data.py
python scripts/seed_agent_data.py

# Validate system
python scripts/validate_workflow_sla_system.py
```

### Testing
```bash
# All tests
pytest tests/ -v

# PURL tests
python tests/test_purl_quick.py

# Full workflow test
python scripts/test_full_workflow.py
```

---

## Specialized Agents Reference

| Agent | Type Key | Primary Use |
|-------|----------|-------------|
| Pipeline Analyst | `pipeline_analyst` | Pipeline metrics & forecasting |
| Compliance Checker | `compliance_checker` | Regulatory compliance |
| Lead Nurturer | `lead_nurturer` | Lead engagement |
| Document Tracker | `document_tracker` | Document collection |
| Scheduler | `scheduler` | Appointment booking |
| Coaching | `coaching` | LO performance |
| Rate Advisor | `rate_advisor` | Rate lock guidance |
| Email Intel | `email_intel` | Email parsing |
| Receptionist | `receptionist` | Inbound handling |
| Voice | `voice` | Phone interactions |

---

## Quick Troubleshooting

| Issue | Solution |
|-------|----------|
| PURL token invalid | Check expiration, verify token format |
| Agent not responding | Check ANTHROPIC_API_KEY, verify agent type |
| WebSocket disconnects | Check WS_TIMEOUT setting, network stability |
| Document upload fails | Check file size (<10MB), verify file type |
| Database connection error | Verify DATABASE_URL, check PostgreSQL status |
