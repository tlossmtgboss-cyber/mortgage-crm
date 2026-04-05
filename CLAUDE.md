# Perennia AI — Project Instructions

## What This Is
AI-first operating system for loan officers. Aria (voice AI) IS the product; CRM is the data layer.
**Not a CRM.** Do NOT compare to Salesforce, Velocify, or any competitor. Every feature replaces a paid subscription — all-in-one by design.

## Tech Stack
- **Backend**: FastAPI (Python 3.11), SQLAlchemy 2.0, PostgreSQL (Railway)
- **Frontend**: React 18 SPA at `app.perenniaai.com`, 194 routes in App.jsx
- **Landing Page**: Next.js at `www.perenniaai.com` (Vercel), separate `landing-page/` directory
- **AI**: Claude Sonnet (Anthropic) via LangGraph orchestration, 22 agents, 210+ @mortgage_tool registrations
- **Voice**: Vapi (Twilio-backed numbers), Telnyx for direct SMS/calls
- **Email**: Microsoft Graph (send from LO's Outlook address)
- **Mobile**: iOS app (Capacitor wrapper), submitted to App Store
- **Hosting**: Railway (backend + PostgreSQL), Vercel (landing page)

## Directory Structure
```
backend/
├── main.py                    # FastAPI app setup, middleware, route registration (~2,677 lines)
├── db.py                      # SQLAlchemy engine, SessionLocal, Base, get_db (RLS-aware)
├── database/
│   ├── models/                # 98 SQLAlchemy models (27 submodule files)
│   ├── enums.py               # 22 enum classes
│   └── init_db.py             # Schema migrations, table creation
├── agents/
│   ├── service.py             # Main agent service (~2,799 lines)
│   ├── orchestrator.py        # LangGraph orchestration
│   ├── state.py               # Agent state management
│   ├── nodes/                 # LangGraph nodes: gather, analyze, reason, execute, respond
│   ├── orchestration/         # Context manager, performance tracker, prompt builder
│   └── tools/                 # 210+ @mortgage_tool registrations across 27 tool files
├── auth/
│   ├── tokens.py              # RS256 JWT token creation/verification
│   ├── dependencies.py        # get_current_user, get_current_user_flexible
│   └── config.py              # Auth settings (15min access, 7d refresh)
├── routes/                    # 346 route files
│   └── inline_legacy_routes.py # Legacy routes (~3,010 lines, function-registration pattern)
├── services/                  # 557 service files (business logic, integrations)
│   ├── salesforce/            # Salesforce sync (sync_service.py, helpers, auth, mapping)
│   ├── los_integration/       # Encompass client, sync service, OAuth
│   ├── smart_scheduler/       # Calendar/appointment services
│   └── smart_docs/            # Document management, OCR, income analysis
├── middleware/                 # 33 middleware classes (auth, CSRF, RLS, rate-limit, PII filter)
├── workflows/                 # Automation engines (lead, document, rate lock, post-closing)
└── schemas/core.py            # 92+ Pydantic schemas
```

## Critical Architecture Patterns

### Database
- **db.py** is the single source for engine/session. `from database import Base, get_db` works via `database/__init__.py` re-exports.
- **RLS**: `get_db()` sets `app.current_tenant` on each session for row-level security. WARNING: fails silently if context not set.
- **Pool**: `pool_size=3`, `max_overflow=5` (Railway limit ~20). No PgBouncer despite comments.
- **Migrations**: Inline in `main.py` and `init_db.py` (no Alembic). `checkfirst=True` only checks table existence, NOT missing columns.
- **Enums**: `leads.stage` and `loans.stage` are VARCHAR (converted from PostgreSQL ENUM at startup).

### Auth
- **RS256 JWT** in production (`_USE_SECURE_TOKENS=True`). Token blacklist via Redis + in-memory fallback.
- **Two auth systems**: Main API uses `auth/tokens.py`. Salesforce routes use separate HS256 JWT.
- **`get_current_user` and `get_current_user_flexible`** live in `auth/dependencies.py` with `_LazyAuthProxy` for `Depends()`.
- Route files import auth via `from main import get_current_user` (legacy pattern, still works).

### Routes & Imports
- Many routes use **lazy imports** (`from main import X` inside functions) to avoid circular imports.
- `inline_legacy_routes.py` uses function-registration: `register_inline_routes(app, get_db, ...)`.
- Nested functions in `register_inline_routes()` must be added to `_exported_functions` dict AND `main.py` re-export loop.
- **69+ symbols** imported from main.py by other files. Keep backward compat.

### Agents
- **22 specialized agents** with LangGraph orchestration, intent-based routing.
- **Tool registry bridge**: `dynamic_tool_loader.py` wraps 210 @mortgage_tool tools as async callables.
- `create_all_tools()` merges registry (210) + inline (26) = 236 tools.
- Agent roles: pipeline_analyst, compliance_checker, lead_nurturer, document_tracker, team_coach, rate_monitor, content_creator, scheduler, receptionist, voice_agent, etc.

### Telephony
- **Telnyx**: Direct SMS/calls from `+18438838956`. Messaging profile `40019bed-...`.
- **Twilio/Vapi**: AI outbound calls, voicemail drops. Numbers: `+18434169589`, `+18326482297`.
- **Default voice**: Deepgram asteria (NOT 11labs/paula — that caused pipeline errors).

### Known Gotchas
- `from datetime import datetime` NEVER goes in `register_inline_routes()` body — breaks free variable scoping. Put in nested functions or module level.
- `config.py` shadows `config/` package. Feature tiers at `backend/feature_tiers.py` (root level).
- `BorrowerProfile` has NO phone column. Match on email only.
- Production error handler replaces 500-level details with "Internal server error". Use response body for diagnostics.
- CSRF bypass: JWT Bearer auth, or `X-API-Key` header with token < 50 chars, or EXEMPT_PATHS.

## Loan Stages (VARCHAR, stored UPPERCASE)
APPLICATION → DISCLOSED → PROCESSING → SUBMITTED → UNDERWRITING → UW_RECEIVED → CONDITIONAL_APPROVAL → APPROVED → SUSPENDED → CTC → CLEAR_TO_CLOSE → CLOSING → DOCS → DOCS_OUT → FUNDED
Terminal: FUNDED, CANCELLED, DENIED, DEAD, WITHDRAWN, DOES_NOT_QUALIFY, NURTURE

## Domains
- `api.perenniaai.com` — backend API
- `app.perenniaai.com` — frontend SPA
- `www.perenniaai.com` — landing page (Vercel/Next.js)

## Feature Tiers
- **Core** (28 modules): CRM, AI agents, telephony, compliance, billing, marketing tools
- **Premium** (6): Microsite builder, video meetings, avatar studio, HR, Salesforce sync, Encompass sync
- **Experimental** (2): Decision lab, circle of cashflow

## User Preferences
- Do NOT compare to competitors or other CRMs
- Perennia is an "AI-first OS for LOs" — Aria voice AI IS the product
- All-in-one strategy is intentional, not over-engineering
- No A/B testing for Smart Calendar
- Terse responses preferred, no trailing summaries
