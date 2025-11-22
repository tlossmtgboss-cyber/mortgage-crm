# Profitability System - Quick Reference

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
