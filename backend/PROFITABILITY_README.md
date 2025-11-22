# Profitability Intelligence System

AI-powered profitability analytics for mortgage companies.

## Overview

The Profitability Intelligence System provides real-time cost analysis, AI-powered insights, and strategic recommendations to help mortgage companies optimize their operations and maximize profit margins.

## Features

### Core Analytics
- **Cost Per Loan Tracking** - Real-time monitoring of all costs associated with closing loans
- **Role Profitability Analysis** - ROI analysis by role (Loan Officer, Processor, Underwriter, etc.)
- **Employee Performance Metrics** - Individual contribution tracking and benchmarking
- **Break-Even Analysis** - Calculate minimum loan volume needed for profitability

### AI Intelligence Layer
- **Natural Language Queries** - Ask questions in plain English about your profitability data
- **Smart Recommendations** - AI-generated strategic recommendations with ROI projections
- **Hiring Decision Analyzer** - Data-driven analysis for hiring decisions
- **Anomaly Detection** - Automatic detection of unusual patterns in financial metrics
- **Executive Digest** - Weekly AI-generated summaries for leadership

### Visualization
- **Executive Dashboard** - Real-time metrics and KPIs
- **Trend Analysis** - Historical performance tracking over 12+ months
- **Scenario Modeling** - "What-if" analysis for business decisions
- **Cost to Close Chart** - Live updating chart showing cost fluctuations

## Architecture

```
backend/
├── services/
│   ├── profitability_service.py    # Core calculations and metrics
│   ├── ai_insights_service.py      # Claude AI integration
│   └── weekly_digest_service.py    # Email digest generation
├── models/
│   └── profitability.py            # Database models
├── schemas/
│   └── profitability.py            # Pydantic schemas
├── profitability_routes.py         # Core API endpoints
└── ai_insights_routes.py           # AI-powered endpoints

frontend/
├── pages/
│   ├── ProfitabilityDashboard.js   # Main dashboard
│   └── ScenarioModeling.js         # What-if analysis
└── components/
    ├── AIInsightsPanel.jsx         # AI query interface
    ├── SmartRecommendations.jsx    # Recommendations display
    └── CostToCloseChart.js         # Real-time chart
```

## API Endpoints

### Core Profitability
- `GET /api/v1/profitability/dashboard` - Complete dashboard data
- `GET /api/v1/profitability/metrics` - Key metrics for a month
- `GET /api/v1/profitability/trends` - Historical trend data
- `GET /api/v1/profitability/roles` - Role profitability analysis
- `GET /api/v1/profitability/employees` - Employee costs and performance

### AI Insights
- `POST /api/v1/profitability/ai/query` - Natural language queries
- `GET /api/v1/profitability/ai/recommendations` - Smart recommendations
- `POST /api/v1/profitability/ai/hiring-analysis` - Hiring decision analysis
- `GET /api/v1/profitability/ai/executive-digest` - Weekly digest
- `GET /api/v1/profitability/ai/anomalies` - Anomaly detection
- `POST /api/v1/profitability/ai/compare-scenarios` - Scenario comparison

### Scenario Modeling
- `POST /api/v1/profitability/scenarios` - Create and run scenario
- `POST /api/v1/profitability/scenarios/run` - Run without saving
- `GET /api/v1/profitability/scenarios` - List saved scenarios

## Environment Variables

```env
# Required for AI features
ANTHROPIC_API_KEY=your_anthropic_api_key

# Required for email digests
SMTP_SERVER=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your_email@gmail.com
SMTP_PASSWORD=your_app_password
FROM_EMAIL=noreply@yourcompany.com
```

## Usage Examples

### Natural Language Query
```python
from services.ai_insights_service import AIInsightsService

service = AIInsightsService(db, org_id)
result = service.query_natural_language(
    "Who are my top 3 loan officers by ROI?"
)
print(result["answer"])
```

### Generate Recommendations
```python
recommendations = service.generate_smart_recommendations()
for rec in recommendations:
    print(f"{rec['priority']}: {rec['title']}")
    print(f"  Impact: {rec['impact']}")
```

### Hiring Analysis
```python
analysis = service.analyze_hiring_decision(
    role_name="Loan Officer",
    salary=85000
)
print(analysis["analysis"])
```

### Send Weekly Digest
```python
from services.weekly_digest_service import WeeklyDigestService

digest_service = WeeklyDigestService(db, org_id)
result = digest_service.send_digest(
    recipients=["ceo@company.com", "cfo@company.com"]
)
```

## Database Models

### Key Tables
- `profitability_roles` - Role definitions with departments
- `employee_costs` - Employee compensation and costs
- `profitability_loans` - Closed loans with revenue
- `loan_attributions` - Employee contributions to loans
- `expenses` - Operating expenses
- `profitability_scenarios` - Saved what-if scenarios
- `profitability_insights` - AI-generated insights
- `profitability_snapshots` - Monthly snapshots

## Frontend Components

### ProfitabilityDashboard
Main dashboard with tabs:
- Overview - Key metrics and trends
- Role Analysis - Profitability by role
- Top Performers - Employee rankings
- Insights - AI-generated insights
- AI Assistant - Natural language interface

### CostToCloseChart
Real-time chart component:
```jsx
<CostToCloseChart
  refreshInterval={60000}
  showLiveIndicator={true}
  height={280}
/>
```

### AIInsightsPanel
AI query interface:
```jsx
<AIInsightsPanel
  month="2025-11"
  onInsightGenerated={(result) => console.log(result)}
/>
```

### SmartRecommendations
Recommendations display:
```jsx
<SmartRecommendations
  month="2025-11"
  autoLoad={true}
  maxItems={5}
/>
```

## Deployment

### Railway (Backend)
```bash
cd backend
railway up
```

### Vercel (Frontend)
```bash
cd frontend
npm run build
vercel --prod
```

## Security

- All API endpoints require authentication
- Profitability data is organization-scoped
- AI queries are processed through Anthropic's secure API
- Email credentials should use app-specific passwords

## Support

For issues or feature requests, contact the development team or open an issue in the repository.
