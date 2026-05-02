# Client File Aggregate Root + Team Chat — Design Spec

**Date:** 2026-05-02
**Status:** Approved — ready for implementation planning
**Scope:** Create `client_files` table as the aggregate root, backfill from `leads`, adapt and install the LO Surface team chat package, wire frontend.

---

## 1. Context

The LO Surface package (`perennia_lo_surface.tar.gz`) delivers a 3-pane client file view with an embedded per-client team chat. The package assumes a `client_files` table, UUID PKs on users, Alembic migrations at `app/`, and Redis Streams publishing agent events. None of these exist in the current Perennia codebase.

This spec covers the minimal foundation needed to install the package: creating the aggregate root table, adapting the package's backend and frontend code to Perennia's architecture, and wiring everything up. It does not cover the full Phase 1 from the design doc (UnifiedInboxService, DocumentHubService, compliance substrate, etc.) — only what the team chat and 3-pane view require.

### What exists today

| Concern | Current state |
|---|---|
| Aggregate root | No `client_files` table. Leads and loans are separate, not unified. |
| User PKs | `users.id` = Integer. `organizations.id` = Integer. |
| Redis | Sync `redis.Redis` via `services/redis_service.py`. No `get_redis` FastAPI dependency. |
| Redis Streams | No XADD publishers. In-process `EventBus` for appointment lifecycle only. |
| RLS GUC | `app.current_tenant` (Integer cast). Not `app.current_org_id` (UUID text). |
| DB sessions | Sync `SessionLocal` via `get_db()` generator in `db.py`. |
| Migrations | Alembic exists at `backend/alembic/`. Inline migrations also used in `init_db.py`. |
| Frontend client-file | No `frontend/src/client-file/` directory. |
| React Query | `@tanstack/react-query ^5.90.16` already in `package.json`. |
| Collaborators | `LoanFileCollaborator` (loan-scoped). No client-file-level collaborator. |

### Package contents (from `perennia_lo_surface.tar.gz`)

**Backend (4 files):**
- `backend/app/models/team_chat.py` — 4 SQLAlchemy models (Channel, Message, Reaction, Read)
- `backend/app/services/team_chat.py` — TeamChatService (channel CRUD, messages, reactions, read cursors, presence)
- `backend/app/api/routes/team_chat.py` — 14 FastAPI endpoints under `/clients/{id}/team-chat/`
- `backend/app/workers/team_chat_bot.py` — Redis Stream consumer posting system messages

**Frontend (16 files):**
- `frontend/src/client-file/` — 3-pane layout (IdentityPanel, ActivityPane, ToolsRail), TeamChatPane, primitives (Avatar, Card, Glyph, Pill), hooks, api client, types, styles

---

## 2. Architecture decisions

### D1. `client_files.id` is UUID

The design doc specifies UUID PKs for the aggregate root. This makes `client_files` the first UUID-PK table in the system. FKs to Integer-PK tables (`users`, `organizations`) use Integer columns. FKs from new tables (`team_chat_*`) to `client_files` use UUID. This is the clean boundary between old and new schema.

### D2. Bridge column `lead_id` on `client_files`

`client_files.lead_id` (Integer, FK to `leads.id`, UNIQUE, nullable) enables bidirectional lookup during the transition period. Every existing lead gets a corresponding `client_files` row via backfill. New leads get one via a service hook.

### D3. Event publishers resolve via bridge column (for now)

No Redis Stream publishers exist today. The team chat bot worker will idle until streams are created in future phases. A `resolve_client_file_id(lead_id)` utility in the worker handles any early publisher that only knows `lead_id`. Future publishers (cadence agent, milestone engine) will emit `client_file_id` natively.

### D4. Service hook creates `client_files` on lead creation

A thin hook in the lead creation path creates the corresponding `ClientFile` row: copies identity fields, sets `lead_id`, flushes. No Postgres trigger (invisible to application, bad for debugging). No one-way migration (doesn't cover new leads).

### D5. New `ClientFileCollaborator` table for member resolution

Dedicated `client_file_collaborators` table with `(id, organization_id, client_file_id, user_id, role, created_at)`. Clean, matches the design doc, decoupled from loan-scoped `LoanFileCollaborator`. Team chat's `list_members` queries this plus the assigned-user columns on `client_files`.

### D6. Denormalized loan rollup columns on `client_files`

The identity panel and header need loan data at a glance. Joining through leads → loans on every load is an extra hop. Denormalized rollup columns on `client_files` are updated when loan data changes (same hook pattern as D4).

### D7. Team chat user references are Integer

All `author_user_id`, `user_id`, and `mentioned_user_ids` in the team chat tables use Integer (matching `users.id`). The package's UUID assumptions are adapted.

### D8. RLS uses `app.current_tenant` with Integer cast

RLS policies on all new tables use:
```sql
organization_id = NULLIF(current_setting('app.current_tenant', TRUE), '')::INTEGER
```
Matching the existing pattern in `database/tenant_mixin.py`, not the package's UUID text comparison.

### D9. Both `get_db` and `get_redis` are sync

`get_db()` yields sync `Session`. `get_redis_client()` returns sync `redis.Redis`. All team chat service methods and route handlers are plain `def`. FastAPI runs them in a threadpool.

---

## 3. Schema

### 3.1 `client_files` table

```sql
CREATE TABLE client_files (
    id                          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id             INTEGER NOT NULL REFERENCES organizations(id),
    lead_id                     INTEGER UNIQUE REFERENCES leads(id),

    -- Identity
    first_name                  VARCHAR,
    last_name                   VARCHAR,
    primary_email               VARCHAR,
    primary_phone               VARCHAR,
    lifecycle_stage             VARCHAR NOT NULL DEFAULT 'new_lead',
    source                      VARCHAR,
    preferred_channel           VARCHAR,
    sticky_note                 TEXT,

    -- Assignment (Integer FKs to users)
    assigned_loan_officer_id    INTEGER REFERENCES users(id),
    assigned_loan_assistant_id  INTEGER REFERENCES users(id),
    assigned_processor_id       INTEGER REFERENCES users(id),

    -- Denormalized loan rollups
    property_address            JSONB,
    active_loan_program         VARCHAR,
    active_loan_purpose         VARCHAR,
    active_loan_amount          NUMERIC(18,2),
    active_loan_fico            INTEGER,
    active_loan_ltv             NUMERIC(8,4),
    active_loan_lock_expires_at TIMESTAMPTZ,
    active_loan_projected_close_date TIMESTAMPTZ,

    -- Metadata
    tags                        JSONB NOT NULL DEFAULT '[]',
    last_contact_at             TIMESTAMPTZ,
    created_at                  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at                  TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_by_user_id          INTEGER REFERENCES users(id)
);

CREATE INDEX ix_client_files_org ON client_files(organization_id);
CREATE INDEX ix_client_files_lead ON client_files(lead_id);
CREATE INDEX ix_client_files_assigned_lo ON client_files(assigned_loan_officer_id);
CREATE INDEX ix_client_files_lifecycle ON client_files(organization_id, lifecycle_stage);
CREATE INDEX ix_client_files_tags ON client_files USING gin(tags);
```

RLS:
```sql
ALTER TABLE client_files ENABLE ROW LEVEL SECURITY;
ALTER TABLE client_files FORCE ROW LEVEL SECURITY;
CREATE POLICY client_files_org_isolation ON client_files
    USING (organization_id = NULLIF(current_setting('app.current_tenant', TRUE), '')::INTEGER)
    WITH CHECK (organization_id = NULLIF(current_setting('app.current_tenant', TRUE), '')::INTEGER);
```

### 3.2 `client_file_collaborators` table

```sql
CREATE TABLE client_file_collaborators (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id     INTEGER NOT NULL REFERENCES organizations(id),
    client_file_id      UUID NOT NULL REFERENCES client_files(id) ON DELETE CASCADE,
    user_id             INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role                VARCHAR NOT NULL DEFAULT 'viewer',
    notify_on_inbound   BOOLEAN NOT NULL DEFAULT FALSE,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),

    UNIQUE (client_file_id, user_id)
);

CREATE INDEX ix_cf_collaborators_client ON client_file_collaborators(client_file_id);
CREATE INDEX ix_cf_collaborators_user ON client_file_collaborators(user_id);
```

RLS: same `app.current_tenant` Integer pattern as `client_files`.

### 3.3 Team chat tables (adapted from package)

Four tables with these type changes from the package:

| Column | Package type | Adapted type |
|---|---|---|
| `organization_id` (was `org_id`) | `UUID` | `INTEGER REFERENCES organizations(id)` |
| `client_file_id` | `UUID REFERENCES client_files(id)` | unchanged |
| `author_user_id` | `UUID REFERENCES users(id)` | `INTEGER REFERENCES users(id)` |
| `user_id` (reactions, reads) | `UUID REFERENCES users(id)` | `INTEGER REFERENCES users(id)` |
| `mentioned_user_ids` | `UUID[]` | `INTEGER[]` |
| All `id` PKs | `UUID` | unchanged (UUID) |
| `channel_id`, `message_id` FKs | `UUID` | unchanged (UUID) |

Table structures, indexes, and constraints remain identical to the package. RLS policies adapted to `app.current_tenant` Integer pattern.

### 3.4 Backfill strategy

The backfill runs as a Python script (not raw SQL in the migration) because several Lead columns use `EncryptedString` — `address`, `city`, `state`, `zip_code` are encrypted at rest and only decrypted through the ORM. A raw `INSERT...SELECT` would copy encrypted blobs.

The backfill script iterates leads through SQLAlchemy, reads decrypted values, and creates `ClientFile` rows:

```python
# backend/migrations/backfill_client_files.py (run once after migration)
from db import SessionLocal
from database.models import Lead
from database.models.client_file import ClientFile

STAGE_MAP = {
    'FUNDED': 'closed_active',
    'CANCELLED': 'dead', 'DENIED': 'dead', 'DEAD': 'dead',
    'WITHDRAWN': 'dead', 'DOES_NOT_QUALIFY': 'dead',
    'NURTURE': 'nurture',
    'APPLICATION': 'pre_app', 'DISCLOSED': 'pre_app',
    'PROCESSING': 'in_processing', 'SUBMITTED': 'in_processing',
    'UNDERWRITING': 'in_underwriting', 'UW_RECEIVED': 'in_underwriting',
    'CONDITIONAL_APPROVAL': 'in_underwriting', 'APPROVED': 'in_underwriting',
    'SUSPENDED': 'in_underwriting',
    'CTC': 'clear_to_close', 'CLEAR_TO_CLOSE': 'clear_to_close',
    'CLOSING': 'clear_to_close', 'DOCS': 'clear_to_close',
    'DOCS_OUT': 'clear_to_close',
}

def backfill():
    db = SessionLocal()
    try:
        leads = db.query(Lead).all()
        for lead in leads:
            existing = db.query(ClientFile).filter(
                ClientFile.lead_id == lead.id
            ).first()
            if existing:
                continue
            prop_addr = None
            if lead.city:  # decrypted by ORM
                prop_addr = {
                    'city': lead.city, 'state': lead.state,
                    'zip': lead.zip_code, 'street': lead.address,
                }
            cf = ClientFile(
                organization_id=lead.organization_id,
                lead_id=lead.id,
                first_name=lead.first_name,
                last_name=lead.last_name,
                primary_email=lead.email,
                primary_phone=lead.phone,
                lifecycle_stage=STAGE_MAP.get(
                    (lead.stage or '').upper(), 'new_lead'
                ),
                source=lead.source,
                preferred_channel=lead.preferred_communication,
                assigned_loan_officer_id=lead.owner_id,
                property_address=prop_addr,
                active_loan_program=lead.program,
                active_loan_purpose=lead.loan_purpose,
                active_loan_amount=lead.loan_amount,
                active_loan_fico=lead.credit_score,
                active_loan_ltv=lead.ltv,
                active_loan_lock_expires_at=lead.lock_expiration,
                active_loan_projected_close_date=lead.closing_date,
                last_contact_at=lead.last_contact,
            )
            db.add(cf)
        db.commit()
    finally:
        db.close()
```

Run after the Alembic migration creates the table: `python -m migrations.backfill_client_files`.

---

## 4. Backend file adaptations

### 4.1 `backend/database/models/team_chat.py`

Source: `package/backend/app/models/team_chat.py`

Changes:
- `from app.db.base import Base` → `from db import Base`
- All `org_id` columns → `organization_id` (Integer, FK to organizations)
- `author_user_id` → Integer FK
- `user_id` (reactions, reads) → Integer FK
- `mentioned_user_ids` → `ARRAY(Integer)`
- Enum types remain as-is (PostgreSQL enums created in migration)

### 4.2 `backend/database/models/client_file.py` (new)

New SQLAlchemy model for `client_files` and `client_file_collaborators`. Uses `from db import Base`. Integer FKs for users/orgs, UUID PK for id.

### 4.3 `backend/database/models/__init__.py`

Add imports for:
- `ClientFile`, `ClientFileCollaborator` from `client_file`
- `TeamChatChannel`, `TeamChatMessage`, `TeamChatReaction`, `TeamChatRead` from `team_chat`
- Enum exports: `TeamChatAuthorKind`, `TeamChatAgentSlug`, `TeamChatReactionEmoji`

### 4.4 `backend/services/team_chat.py`

Source: `package/backend/app/services/team_chat.py`

Changes:
- `from app.models import ClientFile, User` → `from database.models import ClientFile, User`
- `from app.models.team_chat import ...` → `from database.models.team_chat import ...`
- All `org_id` params/attributes → `organization_id`
- `user.org_id` → `user.organization_id`
- `ClientFile.org_id` → `ClientFile.organization_id`
- `_user_display_name()` uses `first_name + " " + last_name` (no `display_name` column)
- `user.last_active_at` → `user.last_activity_at`
- `list_members()` queries `ClientFileCollaborator` instead of `Collaborator`
- All UUID user ID references → Integer throughout

### 4.5 `backend/routes/team_chat_routes.py`

Source: `package/backend/app/api/routes/team_chat.py`

Changes:
- `from app.api.deps import get_current_user, get_db, get_redis` →
  - `from auth.dependencies import get_current_user`
  - `from db import get_db`
  - `from routes.team_chat_routes import get_redis` (local dependency)
- `user.org_id` → `user.organization_id` in all route handlers
- `client_file_id` path param stays `uuid.UUID`
- `message_id` path param stays `uuid.UUID`
- Add `get_redis` dependency at top of file:
  ```python
  def get_redis():
      from services.redis_service import get_redis_client
      return get_redis_client()
  ```

### 4.6 `backend/workers/team_chat_bot.py`

Source: `package/backend/app/workers/team_chat_bot.py`

Changes:
- `from app.db.base import session_factory` → use `db.SessionLocal` with a context manager
- `from app.models.team_chat import ...` → `from database.models.team_chat import ...`
- `from app.services.team_chat import ...` → `from services.team_chat import ...`
- `_scoped_session()` uses `SessionLocal()` from `db`
- `org_id` in event payloads → passed as `organization_id` to service
- Add `resolve_client_file_id(session, lead_id)` utility for bridge lookups
- Redis client initialization uses `services.redis_service.get_redis_client()`

### 4.7 Lead creation hook

In the lead creation path (wherever `Lead()` is committed and flushed), add:

```python
from database.models.client_file import ClientFile

def _ensure_client_file(db: Session, lead: Lead) -> ClientFile:
    existing = db.execute(
        select(ClientFile).where(ClientFile.lead_id == lead.id)
    ).scalar_one_or_none()
    if existing:
        return existing
    cf = ClientFile(
        organization_id=lead.organization_id,
        lead_id=lead.id,
        first_name=lead.first_name,
        last_name=lead.last_name,
        primary_email=lead.email,
        primary_phone=lead.phone,
        lifecycle_stage='new_lead',
        source=lead.source,
        assigned_loan_officer_id=lead.owner_id,
    )
    db.add(cf)
    db.flush()
    return cf
```

This gets called after the lead is flushed (so `lead.id` exists). Exact integration point identified during implementation.

### 4.8 Router registration in `main.py`

```python
from routes.team_chat_routes import router as team_chat_router
app.include_router(team_chat_router, prefix="/api/v1")
```

---

## 5. Frontend integration

### 5.1 File placement

Copy `frontend/src/client-file/` wholesale from the package. No existing directory to conflict with.

Files (16):
- `ClientFileView.tsx`, `IdentityPanel.tsx`, `ActivityPane.tsx`, `ActivityComposer.tsx`
- `UnifiedTimeline.tsx`, `TeamChatPane.tsx`, `ToolsRail.tsx`, `RailPanels.tsx`
- `primitives/Avatar.tsx`, `primitives/Card.tsx`, `primitives/Glyph.tsx`, `primitives/Pill.tsx`
- `api.ts`, `hooks.ts`, `types.ts`, `format.ts`, `styles.css`, `index.ts`

### 5.2 Stylesheet import

In `frontend/src/main.tsx` (or app entry):
```ts
import "./client-file/styles.css";
```

Styles are namespaced under `pf-cf-*` — no collision risk.

### 5.3 API base URL

At app startup:
```ts
import { setApiBaseUrl } from "./client-file";
setApiBaseUrl("https://api.perenniaai.com/api/v1");
```

### 5.4 `ClientFileView` wiring

Find the route component that renders the client/lead detail view. Update to pass `currentUserId`:

```tsx
import { ClientFileView } from "./client-file";

// currentUserId from auth context (however the app reads the logged-in user)
<ClientFileView clientFileId={clientFileId} currentUserId={currentUser.id} />
```

### 5.5 CORS

Verify that the backend CORS middleware allows credentialed requests from `app.perenniaai.com`. The fetch wrappers use `credentials: "include"`.

---

## 6. Migration strategy

Single Alembic migration file: `backend/alembic/versions/client_file_and_team_chat_v1.py`

`down_revision` set to the current Alembic head.

**Upgrade order:**
1. Install `uuid-ossp` extension (if not present) for `gen_random_uuid()`
2. Create `client_files` table with all columns and indexes
3. Create `client_file_collaborators` table
4. Backfill `client_files` from `leads`
5. Create 3 enum types (`team_chat_author_kind`, `team_chat_agent_slug`, `team_chat_reaction_emoji`)
6. Create `team_chat_channels` table (without pinned_message FK)
7. Create `team_chat_messages` table with all indexes including GIN on `mentioned_user_ids`
8. Add `pinned_message_id` FK constraint on channels → messages
9. Create `team_chat_reactions` table
10. Create `team_chat_reads` table
11. Enable RLS + create policies on all 6 new tables

**Downgrade:**
1. Drop FK constraint on channels → messages
2. Drop team chat tables (reads, reactions, messages, channels) in reverse order
3. Drop enum types
4. Drop `client_file_collaborators`
5. Drop `client_files`

---

## 7. Worker deployment

The team chat bot runs as a separate Railway service:

```json
{
  "services": {
    "team_chat_bot": {
      "startCommand": "python -m workers.team_chat_bot",
      "healthcheck": null,
      "numReplicas": 1
    }
  }
}
```

Environment: `REDIS_URL`, `DATABASE_URL` (same as API service).

The worker will boot, create consumer groups on the 5 streams (with `mkstream=True`), and block on `XREADGROUP`. It idles until publishers exist — no impact on the running system.

---

## 8. What this spec does NOT cover

- Full Phase 1 services (UnifiedInboxService, DocumentHubService, TimelineService, etc.)
- Compliance substrate (Gate, AccessLog, Consent versioning)
- Borrower portal
- Relationship graph (`ExternalContact`, typed edges)
- Cadence agent, Insight agent, or any agent wiring
- Redis Stream publishers (these come with the agents)
- Notification fan-out for @mentions (email/push)
- Audit log mirroring for human chat messages
- Chat message retention policy

These are all future work that builds on the foundation this spec creates.

---

## 9. Verification checklist

After deployment:

- [ ] `client_files` table exists with backfilled data from all leads
- [ ] New lead creation also creates a `client_files` row
- [ ] Three-pane layout renders when navigating to a client file
- [ ] Filter pills above timeline filter event categories
- [ ] Right rail shows Insights → Follow-ups → Tasks → Documents → Relationships
- [ ] "Activity" and "Team chat" tabs appear above center pane
- [ ] Sending a team chat message persists and appears
- [ ] Reactions toggle correctly (all 4 emojis)
- [ ] Pinning a message shows yellow banner; re-pinning replaces
- [ ] @mentions render highlighted
- [ ] Unread badge appears on Team chat tab
- [ ] RLS enforced: org A cannot see org B's chat
- [ ] Worker logs `team_chat_bot.starting` on boot
