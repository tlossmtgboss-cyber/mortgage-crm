# Perennia AI Mortgage CRM - Copilot Instructions

## System Architecture

This is a production-grade mortgage CRM with **AI-first architecture**. The system uses a **multi-agent orchestration pattern** where specialized AI agents handle different business functions through a centralized tool registry.

### Core Components

**Backend (FastAPI + SQLAlchemy)**
- `backend/main.py`: Monolithic FastAPI app (2500+ lines) - handles all routes, auth, middleware
- `backend/models/`: Profile-based data models (LeadProfile, ActiveLoanProfile, MUMClientProfile, TeamMemberProfile)
- `backend/agents/`: LangGraph-based AI orchestration system with 8 specialized agents
- `backend/agents/tools/`: 160+ tools organized into 5 parts (base, CRM, communication, operations, business)

**Frontend (React + Vite)**
- `frontend/src/App.jsx`: Main app (4600+ lines) with lazy-loaded routes and chunk retry logic
- `frontend/src/routes/index.jsx`: Centralized route definitions using `lazyRetry()` pattern
- Component organization: `pages/` for routes, `components/` for reusable UI

**AI System**
- Uses **Anthropic Claude** as primary AI provider (`CLAUDE.md` contains 2700+ lines of agent tools)
- Agent orchestrator in `backend/agents/orchestrator.py` with intent-based tool routing
- Tools are scoped by intent: `["general", "crm", "compliance", "sla", "reports", "coaching", "customer"]`

## Development Patterns

### Database & Models
```python
# Use profile-based models, not generic entities
from backend.models import LeadProfile, ActiveLoanProfile
# Loan stages are UPPERCASE strings: "APPLICATION", "DISCLOSED", "PROCESSING", etc.
# Terminal stages: ("FUNDED", "CANCELLED", "DENIED", "DEAD", "WITHDRAWN")
```

### Frontend Routing
```jsx
// Use lazyRetry pattern for all page imports to handle deploy chunk failures  
const Dashboard = lazyRetry(() => import('./pages/Dashboard'));
// Routes are generated via getRoutes(layoutProps) function
// All pages wrapped in <LazyPage> with error boundaries
```

### AI Tool Development
```python
# Register tools using the @mortgage_tool decorator
@mortgage_tool(
    name="get_pipeline", 
    description="Get loan pipeline data",
    agent_roles=["pipeline_analyst", "compliance_officer"],
    risk_level="LOW"
)
def get_pipeline(user_id: str, filters: Dict = None) -> ToolResult:
    # Always return ToolResult.success() or ToolResult.error()
```

### Component Architecture
- **Context providers**: `ImpersonationProvider`, `PermissionProvider`, `ModuleProvider`, `BrandingProvider`
- **Custom hooks**: `useLayoutFix`, `useMediaQuery`, `useCalendarKeyboard` for common functionality
- **Error boundaries**: All lazy routes wrapped with error handling and retry logic

## Deployment Workflows

### Railway Deployment (Primary)
```bash
# Backend auto-deploys on git push using Dockerfile in backend/
railway variables set ANTHROPIC_API_KEY='your-key'
railway logs  # Monitor deployments
# First deploy takes 5-10 minutes (DB setup), subsequent deploys 2-3 minutes
```

### Database Migrations
```bash
# Run migrations on production
railway run python backend/migrations/[migration_file].py
# Or use the migration runner endpoints
POST /api/run-migration
```

### Environment Management
- `.env.example` templates in both `backend/` and `frontend/`
- Railway manages production variables automatically
- Local development uses `docker-compose.yml` for PostgreSQL

### Testing Commands
```bash
# Backend API testing
python backend/test_api.py
./comprehensive_test.sh

# Frontend deployment
cd frontend && npm run build
# Deploy to Vercel (recommended for frontend)
```

## Key Business Logic

### Loan Pipeline Stages
The system tracks 18 distinct loan stages with SLA targets. Use `LoanStage` enum and understand that "CLEAR_TO_CLOSE" and "CTC" are the same stage. Pipeline queries exclude terminal stages.

### Agent Tool Scoping
Each user intent maps to specific tools:
- `"general"`: ["get_daily_priorities", "get_pipeline", "get_tasks"]  
- `"crm"`: ["search_leads", "search_loans", "create_lead"]
- `"compliance"`: ["search_loans", "get_pipeline"]

### Multi-tenant Architecture
- Organization-based data isolation in all models
- Role-based permissions: `getUserEffectiveRole()`, `getDefaultRouteForRole()`
- Impersonation system for admin users

## Critical Implementation Notes

1. **Always use `lazyRetry()` for new page imports** to handle chunk load failures after deployments
2. **Database queries must filter by organization_id** for multi-tenant isolation  
3. **Agent tools return `ToolResult` objects**, never raw data
4. **Frontend API calls use `getAuthHeaders()`** for consistent authentication
5. **Loan stage transitions follow SLA targets** defined in `SLA_TARGETS` constant
6. **Railway deployment requires migration runs** for database schema changes

## Common Anti-patterns to Avoid

- Don't create generic CRUD models - use specific profiles (Lead/Loan/MUM/Team)
- Don't import pages directly - always use `lazyRetry()` wrapper
- Don't bypass the agent tool registry - register all AI functions properly
- Don't hardcode API URLs - use environment variables and `API_BASE_URL`
- Don't skip error boundaries on new routes

This system prioritizes **AI-driven workflows** over traditional CRUD operations. When adding features, consider how they integrate with the existing agent orchestration system and tool registry.