# Perennia iMessage — Build Skill

Native iMessage messaging inside Perennia AI, modeled after Sendblue's
product surface but owned end-to-end. Self-hosted relay (BlueBubbles on a
Mac mini) + Perennia-native UX, routing, AI hooks, and dashboard. Real
blue bubbles. Telnyx fallback when iMessage is unavailable.

This skill is the index. Drop the matching files into Perennia's repo,
follow the post-delivery action items at the bottom, and you're live.

---

## 1. Architecture

```
                       ┌──────────────────────────┐
                       │  Mac mini (TLDev HQ)     │
                       │  ─ BlueBubbles Server    │
                       │  ─ Apple ID + iMessage   │
                       │  ─ Private API helper    │
                       │  ─ Cloudflare Tunnel     │
                       └──────────────┬───────────┘
                                      │ HTTPS (CF Access service-token)
                                      ▼
   ┌──────────────────────────────────────────────────────────────┐
   │  Perennia FastAPI (Railway)                                   │
   │                                                               │
   │  app/integrations/imessage/                                   │
   │    ├── client.py     ── async BlueBubbles wrapper              │
   │    ├── service.py    ── send/receive, routing, fan-out         │
   │    ├── router.py     ── /api/imessage/* + /webhooks/imessage   │
   │    ├── models.py     ── 5 ORM tables                           │
   │    └── …                                                       │
   │                                                               │
   │  Webhook ingest fans out to:                                  │
   │   • AI Operations Manager      (record_inbound_async)         │
   │   • Deal Breaker Radar         (evaluate_message_async)       │
   │   • Engagement engine SLA      (reset_followup_sla)           │
   │   • Calculator Agent           (classify_borrower_async)      │
   │   • Real-time WebSocket bus    (broadcast_to_tenant)          │
   └──────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
   ┌──────────────────────────────────────────────────────────────┐
   │  Perennia React (Vercel)                                      │
   │  features/imessage/                                           │
   │    ├── BlueBubbleThread.tsx     ── authentic blue/SMS bubbles  │
   │    ├── MessageComposer.tsx      ── send-style, voice, channel  │
   │    ├── ChannelBadge.tsx         ── iMessage/SMS pill           │
   │    ├── useThread.ts             ── live state + optimistic     │
   │    └── api/imessageApi.ts       ── REST client                 │
   └──────────────────────────────────────────────────────────────┘
```

Channel routing decision tree on outbound:

```
SendMessageRequest.channel
├── imessage  → force iMessage; if BB times out, fall back to Telnyx SMS
├── sms       → straight to Telnyx (skips BB entirely)
└── auto      → check imessage_lookup_cache for (line, handle):
                 ├── cache hit → use cached service
                 └── cache miss → live probe via BB
                                  /api/v1/handle/availability
                                  → upsert cache → use result
```

---

## 2. Code map

| File                                                                                  | Role                                                                |
| ------------------------------------------------------------------------------------- | ------------------------------------------------------------------- |
| `ops/bluebubbles-mac-setup.md`                                                        | One-time Mac mini hardening + BlueBubbles install                   |
| `ops/cloudflare-tunnel.md`                                                            | Stable public URL with Service Auth lockdown                        |
| `ops/runbook.md`                                                                      | On-call playbook, alarm thresholds, capacity                        |
| `backend/app/integrations/imessage/config.py`                                         | `IMessageSettings` (env-driven)                                     |
| `backend/app/integrations/imessage/chat_guid.py`                                      | BB chat-GUID parse/build/normalize helpers                          |
| `backend/app/integrations/imessage/schemas.py`                                        | Pydantic models — BB, Perennia API, AI pipeline                     |
| `backend/app/integrations/imessage/models.py`                                         | SQLAlchemy ORM — 5 tables, encrypted body + creds                   |
| `backend/app/integrations/imessage/client.py`                                         | Async httpx wrapper, retry, CF Access, error hierarchy              |
| `backend/app/integrations/imessage/service.py`                                        | Send, ingest, route, fan-out to agents                              |
| `backend/app/integrations/imessage/router.py`                                         | `api_router` + `webhook_router`                                     |
| `backend/app/integrations/imessage/factory.py`                                        | Warm BB client registry, DI factory, lifespan shutdown              |
| `backend/alembic/versions/20260427_add_imessage_tables.py`                            | Migration — set `down_revision` before running                      |
| `frontend/src/features/imessage/types.ts`                                             | TS mirror of Pydantic schemas + realtime events                     |
| `frontend/src/features/imessage/api/imessageApi.ts`                                   | Frontend REST client                                                |
| `frontend/src/features/imessage/hooks/useThread.ts`                                   | Live thread state, optimistic send, debounced typing                |
| `frontend/src/features/imessage/components/BlueBubbleThread.tsx`                      | Authentic Apple-blue/SMS-green bubble renderer                      |
| `frontend/src/features/imessage/components/MessageComposer.tsx`                       | Channel-aware composer, send-style picker, voice memo, reply quote  |
| `frontend/src/features/imessage/components/ChannelBadge.tsx`                          | iMessage/SMS/Detecting pill                                         |

---

## 3. Database — `imessage_*` tables

| Table                    | Purpose                                                                 |
| ------------------------ | ----------------------------------------------------------------------- |
| `imessage_lines`         | Mac mini relays. Tenant-scoped. Holds per-line BB password (encrypted). |
| `imessage_threads`       | One per (tenant, contact, line). Holds the BB `chat_guid` for reuse.    |
| `imessage_messages`      | Every message. Body encrypted at rest. Full BB identifiers retained.    |
| `imessage_lookup_cache`  | Phone → `iMessage`/`SMS` per line, TTL 7d (configurable).               |
| `imessage_webhook_log`   | Append-only, dedupe via SHA256 signature, audit + replay.               |

---

## 4. Environment variables

All read by `IMessageSettings` (Pydantic), prefix `IMESSAGE_`:

```bash
# BlueBubbles
IMESSAGE_BB_BASE_URL=https://imessage-1.tldevelopment.dev
IMESSAGE_BB_PASSWORD=<openssl rand -hex 32>

# Cloudflare Access service-token (recommended)
IMESSAGE_CF_ACCESS_CLIENT_ID=<from CF Zero Trust>
IMESSAGE_CF_ACCESS_CLIENT_SECRET=<from CF Zero Trust>

# Webhook URL secret (rotates per deploy)
IMESSAGE_WEBHOOK_URL_SECRET=<openssl rand -hex 32>

# Behavior
IMESSAGE_TELNYX_FALLBACK_ENABLED=true
IMESSAGE_REQUEST_TIMEOUT_SECONDS=20.0
IMESSAGE_MAX_RETRIES=3
IMESSAGE_IMESSAGE_LOOKUP_CACHE_TTL_SECONDS=604800   # 7d
IMESSAGE_TYPING_INDICATOR_DWELL_MS=1500

# Default sender (single-line bootstrap)
[email protected]
IMESSAGE_BRAND_NAME=TL Mortgage
IMESSAGE_BRAND_VCARD_CDN_URL=https://cdn.perennia.ai/vcards/tl-mortgage.vcf
```

Per-line overrides (`bb_password`, `cf_access_client_id`,
`cf_access_client_secret`) live encrypted on each `imessage_lines` row —
needed when you scale to a Mac per tenant.

---

## 5. RBAC matrix

| Endpoint                                   | Roles                                              |
| ------------------------------------------ | -------------------------------------------------- |
| `POST /api/imessage/messages`              | loan_officer, processor, admin, ai_agent           |
| `POST /api/imessage/tapbacks`              | loan_officer, processor, admin                     |
| `POST /api/imessage/typing`                | loan_officer, processor, admin                     |
| `POST /api/imessage/detect-imessage`       | loan_officer, processor, admin, ai_agent           |
| `GET  /api/imessage/contacts/{id}/thread`  | (delegated to your existing contact-read policy)   |
| `GET  /api/imessage/lines`                 | admin                                              |
| `POST /webhooks/imessage/{token}/{line_id}`| public; gated by URL token + line existence        |
| `POST /webhooks/imessage/{token}/{line_id}/heartbeat` | public; gated identically                |

---

## 6. AI pipeline integration

`service.py` fans out on every inbound `new-message` event (excluding
echoes of our own outbound):

| Hook                                     | When called                                           | Purpose                                                |
| ---------------------------------------- | ----------------------------------------------------- | ------------------------------------------------------ |
| `ops_manager.record_inbound_async`       | Every inbound text                                    | Feeds AI Operations Manager metrics + dashboards       |
| `deal_breaker.evaluate_message_async`    | Every inbound text                                    | Surfaces declines, risk-laden language, cancel intent  |
| `reset_followup_sla(...)`                | Every inbound text                                    | Resets engagement-engine follow-up timer for the LO    |
| `calculator.classify_borrower_async`     | First inbound from a contact only                     | Classifies into 8 borrower types → tailored calc surf  |
| `broadcast_to_tenant(...)`               | Every inbound + outbound + status update              | Live UI updates over WebSocket                         |

The 7-agent call-intel pipeline already running on Deepgram transcripts
is unaffected — iMessage flows through the same `record_inbound_async`
intake but with `channel="imessage"` set, so the agents that are
channel-aware (Calculator, Deal Breaker) will branch correctly.

---

## 7. BlueBubbles webhook subscriptions

In the BlueBubbles UI → API & Webhooks → Add Webhook:

- URL: `https://api.perennia.ai/webhooks/imessage/{IMESSAGE_WEBHOOK_URL_SECRET}/{line_id}`
- Subscribe to:
  - `new-message`             ← inbound + outbound echoes
  - `updated-message`         ← delivery, read, error stamps
  - `typing-indicator`        ← live "..." for the UI
  - `chat-read-status-changed`← borrower opened the thread
  - `group-name-change`       ← (future co-borrower threads)
  - `participant-removed`
  - `participant-added`

The `hello-world` event from BB is logged but not acted on.

---

## 8. Channel-routing semantics (cheat sheet)

| Send request channel | iMessage cache | Result                                        |
| -------------------- | -------------- | --------------------------------------------- |
| `imessage`           | n/a            | Force iMessage. On BB timeout → Telnyx SMS.   |
| `sms`                | n/a            | Straight to Telnyx. BB never invoked.         |
| `auto`               | hit: iMessage  | iMessage send.                                |
| `auto`               | hit: SMS       | Telnyx send.                                  |
| `auto`               | miss           | Live probe via BB; cache result; act on it.   |

---

## 9. Validation checklist

Before promoting to LO seats:

- [ ] Mac mini powered on, BB UI shows iMessage **and** FaceTime green
- [ ] `cloudflared` agent running (`brew services list`)
- [ ] `GET /api/v1/ping?password=...` over the tunnel returns
      `{"status":200,"message":"pong"}`
- [ ] `imessage_lines` row inserted for tenant, `enabled=true`
- [ ] BlueBubbles webhook configured with matching token + line_id
- [ ] Send a manual `POST /api/imessage/messages` to your own phone:
      - returns 201 with `bb_message_guid`
      - row appears in `imessage_messages` with status transitioning
        `queued → sending → sent → delivered → read`
      - WebSocket pushes the matching `imessage.message.created` and
        `imessage.message.updated` events
- [ ] Reply from your phone — webhook lands, fan-out runs, frontend
      thread updates live
- [ ] Telnyx fallback verified: temporarily kill the tunnel and resend;
      message goes via SMS green-bubble path with the same UI shell
- [ ] Heartbeat from Mac → `/heartbeat` endpoint stamping
      `imessage_lines.last_ping_at`
- [ ] Tapback from your phone reflects in UI within 2s
- [ ] Read receipt round-trip: outbound message shows "Read HH:MM" once
      borrower opens the thread

---

## 10. Post-delivery action items (Tim)

1. **Migration**: open `20260427_add_imessage_tables.py`, set
   `down_revision = "<your-latest-revision-id>"`, then run
   `alembic upgrade head` against staging first.

2. **Replace placeholder imports** (search for `# === replace` in the code):

   - `app.audit.service.AuditLogger`
   - `app.contacts.repository.ContactRepository`
   - `app.engagement.sla.reset_followup_sla`
   - `app.intelligence.calculator_agent.CalculatorAgent`
   - `app.intelligence.deal_breaker_radar.DealBreakerRadar`
   - `app.intelligence.ops_manager.AIOperationsManager`
   - `app.realtime.broadcast.broadcast_to_tenant`
   - `app.integrations.telnyx.adapter.TelnyxAdapter`
   - `app.db.base.Base`
   - `app.db.types.EncryptedText`
   - `app.api.dependencies.{CurrentUser, get_current_user, get_db_session, require_role}`

   Frontend:
   - `@/lib/apiClient` → your existing authenticated fetch wrapper
   - `@/lib/realtime` → your `useRealtimeChannel` hook (or socket.io adapter)

3. **Buy hardware**: Mac mini M2 + UPS + ethernet. Follow
   `ops/bluebubbles-mac-setup.md` step-by-step.

4. **Cloudflare Tunnel**: follow `ops/cloudflare-tunnel.md`. Lock the
   tunnel behind a service-token Access policy before exposing
   credentials to Railway env.

5. **Insert the first line row**:
   ```sql
   INSERT INTO imessage_lines
     (tenant_id, label, handle, bb_base_url, enabled, daily_send_limit)
   VALUES
     ('<tldev-tenant-uuid>', 'Mac Mini #1',
      '[email protected]',
      'https://imessage-1.tldevelopment.dev',
      true, 2500);
   ```

6. **Wire the webhook**: in BlueBubbles UI add the URL with token + line_id
   and the events listed in §7.

7. **Mount routers** in your FastAPI app:
   ```python
   from app.integrations.imessage import api_router, webhook_router, shutdown_clients
   app.include_router(api_router)
   app.include_router(webhook_router)

   @app.on_event("shutdown")
   async def _close_imessage():
       await shutdown_clients()
   ```

8. **Frontend mount**: drop `<BlueBubbleThread>` and `<MessageComposer>`
   into the contact-detail panel, wired with `useThread({ contactId })`
   and `<ChannelBadge>` in the thread header.

---

## 11. Future extensions (architecture already supports)

- **Second Mac**: insert another `imessage_lines` row, point
  `IMESSAGE_BB_BASE_URL` per-line, route by tenant or by hash. Capacity
  doubles with no schema changes.
- **Co-borrower group threads**: `imessage_threads.is_group=true` +
  `participants` JSONB; expand `BlueBubbleThread` to render sender chips.
- **vCard contact-card share**: `IMessageService.send` already accepts
  `media_url`; pass the brand vCard URL to deliver as a contact card
  bubble, and borrowers can save the LO with one tap.
- **Multi-tenant SaaS**: every read goes through `tenant_id` already;
  the only change is per-tenant Mac provisioning workflows.
- **Tapback from Perennia → borrower**: `POST /api/imessage/tapbacks` is
  live; just add the picker UI on long-press of any inbound bubble.
