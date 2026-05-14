# Contributing to Perennia AI

Engineering standards for the Perennia AI platform. All PRs must follow these guidelines.

## File Size Limits

- **Backend Python files**: 500 lines max (excluding `tests/`, `migrations/`, `alembic/`)
- **Frontend component files** (JS/JSX/TS/TSX): 400 lines max
- If a file exceeds the limit, decompose it before merging
- CI enforces these limits as warnings; pre-commit hook blocks new files that exceed them

## Code Organization

| What | Where |
|------|-------|
| Backend routes | `backend/routes/` (one file per domain) |
| Frontend components | `frontend/src/components/` or feature directories |
| Database models | `backend/database/models/` submodules |
| Services / business logic | `backend/services/` |
| Middleware | `backend/middleware/` |
| Pydantic schemas | `backend/schemas/` |
| Agent tools | `backend/agents/tools/` |

**Do not add code to `backend/main.py`.** Use `app_factory.py`, `middleware_config.py`, `router_registry.py`, or `app_lifespan.py` instead.

## TypeScript

- All **new** frontend files must be `.ts` or `.tsx` (enforced by pre-commit hook)
- Existing `.js`/`.jsx` files can remain until migrated
- New stylesheets must use `.module.css` (enforced by pre-commit hook)

## Testing

- All new backend features need tests in `backend/tests/`
- Use `@pytest.mark.unit` for isolated tests (no DB, no network)
- Use `@pytest.mark.integration` for tests that need PostgreSQL or external services
- Integration tests go in `backend/tests/integration/`
- Mock external services (Anthropic, Vapi, Telnyx, Microsoft Graph)
- Use real PostgreSQL for database tests (CI provides a Postgres service)
- Available markers: `unit`, `integration`, `e2e`, `contract`, `golden`, `critical`, `agents`, `security`, `compliance`, `performance`, `slow`

## Database

- Financial columns use `Numeric(18,2)` for dollar amounts, `Numeric(8,4)` for rates -- never `Float`
- All tenant-scoped models must have an `organization_id` column
- New models go in `backend/database/models/` as submodules and must be re-exported from `__init__.py`
- No inline DDL in startup code -- schema changes belong in migration scripts under `backend/migrations/`
- `checkfirst=True` only checks table existence, not missing columns -- use explicit `ALTER TABLE ADD COLUMN IF NOT EXISTS` for column additions

## Security

- All upload endpoints must use `secure_upload()` from `backend/middleware/upload_security.py`
- New models with `organization_id` must have RLS policies enforced via `get_db()` tenant context
- No hardcoded secrets -- use environment variables
- CSRF protection is active; exempt paths must be explicitly listed

## AI / Agents

- New agent tools use the `@mortgage_tool` decorator in `backend/agents/tools/`
- Agent roles must be registered in `backend/agents/AGENT_INVENTORY.md`
- All LLM calls must track cost via `AICostTracker.record_usage()`
- Tool registry bridge: tools registered with `@mortgage_tool` are automatically available to agents via `dynamic_tool_loader.py`

## Commit Messages

Format: `type: short description`

Types: `feat`, `fix`, `refactor`, `test`, `docs`, `chore`

When AI-assisted, include:
```
Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>
```

## PR Checklist

- [ ] No file exceeds size limits (500 lines backend, 400 lines frontend)
- [ ] New frontend files are `.ts`/`.tsx`
- [ ] Tests added for new functionality
- [ ] No `Float` columns for financial data
- [ ] No hardcoded secrets
- [ ] No new code in `main.py`
