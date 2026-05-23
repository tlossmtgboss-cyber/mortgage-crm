# Workflow Flowchart View — Design Spec

## Overview

Replace the current day-based WorkflowDashboard with a flowchart-first view. Each of the 10 workflows (Prospect, PreQual, Pre-Approval, Under Contract, Lead Purchase, Theme Day, Last Mile, Post Close, Credit Repair, Nurture) gets its own visual flowchart page. The flowchart is both an editor (design workflow steps) and an operational dashboard (live lead counts, health status).

Built on a custom SVG/HTML canvas evolved from the V4 prototype — no external flowchart library.

## Page Structure & Routing

**Routes:**
- `/workflow` — redirects to first workflow (e.g., `/workflow/prospect`)
- `/workflow/:workflowKey` — individual workflow flowchart page
- `/workflow/settings` — workflow management (add, rename, reorder, delete)

**Three-Panel Layout:**
- **Left sidebar** (~200px): workflow list with lead counts, `+ Add Workflow` button at bottom, active workflow highlighted. Persists across all `/workflow/*` routes via layout component.
- **Center canvas** (flex): SVG + HTML overlay for the flowchart. Pan/zoom/drag. Toolbar at top for adding nodes, zoom controls, simulation toggle.
- **Right drawer** (~320px, conditional): slides in when a node is selected. Tabbed: Config / Leads / History / Metrics. Closes on canvas click or X button.

**Component tree:**
```
WorkflowLayout          (sidebar + <Outlet />)
├── WorkflowSidebar     (nav list, add button)
├── WorkflowFlowchart   (canvas + toolbar + drawer)
│   ├── FlowchartCanvas (SVG edges + HTML nodes, pan/zoom)
│   ├── FlowchartToolbar (add node, zoom, simulate)
│   └── NodeDetailDrawer (tabbed detail panel)
└── WorkflowSettings    (CRUD management page)
```

## Data Model

### workflow_definitions

| Column | Type | Notes |
|--------|------|-------|
| id | UUID, PK | |
| organization_id | UUID, FK → organizations | Tenant isolation |
| key | String | Unique per org — "prospect", "prequal", etc. |
| name | String | Display name — "Prospect", "PreQual", etc. |
| color | String | Hex color for sidebar/theming |
| sort_order | Integer | Sidebar ordering |
| is_active | Boolean | Default true, soft-delete sets false |
| created_at | DateTime | |
| updated_at | DateTime | |

### workflow_nodes

| Column | Type | Notes |
|--------|------|-------|
| id | UUID, PK | |
| workflow_definition_id | UUID, FK | |
| type | String | "start", "task", "condition", "delay", "notification", "end" |
| label | String | Display label |
| description | Text | Full description shown in detail drawer |
| x | Float | Canvas x position |
| y | Float | Canvas y position |
| channels | JSON | `{phone: true, text: false, email: true, referral_partner: false}` |
| role | String | "LO", "Concierge", "AI", "Processor", "Manager", "System" |
| day_label | String | "Day 1", "Day 2-4", etc. |
| time_of_day | String | "AM", "PM", or "" |
| repeat_weekly | Boolean | |
| status | String | "healthy", "broken", "disabled" |
| config | JSON | Extensible for future fields |
| sort_order | Integer | Non-visual ordering for export/list views |
| created_at | DateTime | |
| updated_at | DateTime | |

### workflow_edges

| Column | Type | Notes |
|--------|------|-------|
| id | UUID, PK | |
| workflow_definition_id | UUID, FK | |
| from_node_id | UUID, FK → workflow_nodes | |
| to_node_id | UUID, FK → workflow_nodes | |
| label | String, nullable | "Yes", "No", "No Response", etc. |
| created_at | DateTime | |

### Lead position tracking

Add two columns to the existing `leads` table:
- `workflow_definition_id` (UUID, FK → workflow_definitions, nullable) — which workflow the lead is in
- `workflow_node_id` (UUID, FK → workflow_nodes, nullable) — which specific node within that workflow

A lead is in one workflow at a time. The 10 default workflows map to existing pipeline stage categories (Prospect, PreQual, etc.), but workflow assignment is stored explicitly rather than derived from stage — this allows custom workflows that don't map 1:1 to stages.

### Lead movement history

Add a `workflow_lead_movements` table to power the History tab:

| Column | Type | Notes |
|--------|------|-------|
| id | UUID, PK | |
| lead_id | UUID, FK → leads | |
| from_node_id | UUID, FK → workflow_nodes, nullable | Null on first entry |
| to_node_id | UUID, FK → workflow_nodes | |
| moved_at | DateTime | |
| moved_by | UUID, FK → users, nullable | Null if automated |

Rows are append-only. Queried for the History tab and for dwell-time metrics.

### Migration path

- Seed the 10 default `workflow_definitions` on first run for each org.
- Existing workflow configs from the old day-based system can be imported as nodes via a one-time migration script.
- Old WorkflowConfigEditor remains available as a fallback during transition.

## API Endpoints

### Workflow Definitions CRUD

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/v1/workflow/definitions` | List all for org (extend existing endpoint) |
| POST | `/api/v1/workflow/definitions` | Create new workflow |
| PUT | `/api/v1/workflow/definitions/:id` | Update name, color, sort_order |
| DELETE | `/api/v1/workflow/definitions/:id` | Soft-delete (set is_active=false) |
| PUT | `/api/v1/workflow/definitions/reorder` | Bulk update sort_order |

### Workflow Graph (nodes + edges)

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/v1/workflow/:key/graph` | All nodes + edges + lead counts in one payload |
| POST | `/api/v1/workflow/:key/nodes` | Add a node |
| PUT | `/api/v1/workflow/:key/nodes/:id` | Update node config, label, position, etc. |
| DELETE | `/api/v1/workflow/:key/nodes/:id` | Delete node + cascade edge cleanup |
| PUT | `/api/v1/workflow/:key/nodes/positions` | Bulk position update (debounced after drag) |
| POST | `/api/v1/workflow/:key/edges` | Add an edge |
| DELETE | `/api/v1/workflow/:key/edges/:id` | Remove an edge |

### Live Data (detail drawer tabs)

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/v1/workflow/:key/nodes/:id/leads` | Paginated leads at a node (Leads tab) |
| GET | `/api/v1/workflow/:key/nodes/:id/metrics` | Completion rate, avg dwell time, throughput (Metrics tab) |
| GET | `/api/v1/workflow/:key/nodes/:id/history` | Recent lead movements in/out (History tab) |

The `GET /graph` endpoint returns the full flowchart in one call to avoid N+1 queries. Detail drawer tabs make separate calls only when opened.

## Frontend Components

### FlowchartCanvas

Core rendering engine evolved from V4 prototype:
- SVG layer for edges (bezier curves with arrow markers, labels on condition branches)
- HTML overlay for nodes (positioned with `transform: translate()`, enables rich content)
- Pan via mousedown on canvas background, zoom via scroll wheel
- Node drag updates local state, debounced `PUT /positions` on mouseup
- Click node → opens detail drawer, click canvas → closes drawer
- Edge drawing: click a node's output port, drag to another node's input port

### Node rendering (rich nodes)

Each node on the canvas displays:
- Label (bold)
- Day label + time of day + assigned role (muted subtitle)
- Lead count badge (colored pill, e.g., "5 leads")
- Channel icons row (phone, text, email, referral partner — only active channels shown)
- Health status dot (green = healthy, orange = warning/broken, gray = disabled)
- Node border color varies by type: primary for start, accent for condition, indigo for notification, warning for delay

### FlowchartToolbar

Top bar above the canvas:
- Add node buttons: Task, Condition, Delay, Notification — click then click canvas to place
- Zoom in / out / reset buttons
- Simulate button (walks the flow path with step-by-step animation, inherited from V4)
- Workflow name + total lead count as header text

### NodeDetailDrawer

Right panel (~320px), 4 tabs:
- **Config**: editable fields — label, description, channels (checkboxes), role (dropdown), day_label, time_of_day, repeat_weekly. Auto-saves on change (debounced PUT).
- **Leads**: paginated list of leads at this node. Shows name, time at this step, contact info. Click a lead → navigates to lead detail page.
- **History**: recent lead movements — "John Smith moved here from Welcome Call · 2h ago". Reverse chronological feed.
- **Metrics**: completion rate (% that move forward vs. stall), avg dwell time, throughput per week. Simple stat cards.

### WorkflowSidebar

- Workflow list items: colored dot + name + count badge
- Active state: highlighted background, left border accent
- `+ Add Workflow` button at bottom → inline form (name + color picker) or modal
- Each item is a `<NavLink to={/workflow/${key}}>`

### WorkflowSettings page

- Table/list of all workflows with name, color, lead count, active status
- Inline rename, color picker, drag-to-reorder
- Delete with confirmation (must reassign or archive leads in that workflow first)

## AI Execution Engine

The flowchart is not just visual — it's an execution engine. When a node's assigned role is "AI", the system automatically executes the task using the configured channels. AI operates under a progressive autonomy model where it earns trust through demonstrated results.

### Progressive Autonomy Model

Every AI-assigned node has a **confidence score** (0–100%) that determines the level of human oversight:

| Level | Score | Behavior |
|-------|-------|----------|
| Supervised | 0–59% | AI drafts action → LO reviews & approves before execution |
| Guided | 60–84% | AI executes automatically → LO gets notified and can override within window |
| Autonomous | 85–100% | AI executes independently → outcomes logged, LO reviews periodically |

LO always has a kill switch — any node can be manually forced to Supervised mode regardless of score. Confidence can also be capped per channel (e.g., "never let AI make calls above Guided mode").

### Learning Loop

Every AI action feeds back into the confidence model: execute → observe outcome → score → adjust confidence.

**What increases confidence:**
- Positive outcome — lead responds, moves to next node, books appointment (+3–5 pts)
- Human approves without edits — LO approves AI's draft as-is (+2 pts)
- Consistent success streak — 10+ consecutive successful actions (+5 pts bonus)

**What decreases confidence:**
- Human rejects action (-5 pts)
- Human edits substantially — rewrites >50% of draft (-3 pts)
- Negative outcome — lead unsubscribes, complains (-10 pts)
- Compliance violation — any regulatory flag (-25 pts, hard reset to Supervised)

**Confidence is scoped per:** workflow × node type × channel × organization. A single node could be Autonomous for email but Supervised for calls.

### Per-Node AI Configuration

Each AI-assigned node gets an expanded config section with guidance:

- **Objective** — what this step is trying to accomplish
- **Talking points / script guidance** — conversation structure, key questions, responses to common objections
- **Tone** — warm & conversational, professional, urgent, etc.
- **Success criteria** — what outcome advances the lead to the next node
- **Failure / escalation rules** — what happens on no answer, rejection, complex questions, compliance flags
- **Max retries** — attempts per channel, cooldown between retries
- **Per-channel confidence bars** — visual display of current confidence by channel

### Guardrails (Always Enforced)

Non-negotiable regardless of confidence level. AI cannot override these:

- **Compliance hours only** — no calls/texts outside 8am–9pm borrower local time (TCPA)
- **Rate limiting** — max 3 contact attempts per lead per day across all channels
- **PII protection** — AI never logs SSN, DOB, or financial details in action records
- **Compliance violation = hard stop** — any flag resets node confidence to 0, requires manual review
- **Human escalation path always available** — lead says "talk to a person" = immediate handoff
- **Audit trail** — every AI action logged with full context for compliance review

### Execution Infrastructure

| Channel | Provider | How AI Executes |
|---------|----------|-----------------|
| Phone calls | Vapi (Twilio-backed) | AI creates a Vapi call with node's talking points as assistant prompt. Deepgram asteria for voice. |
| Text / SMS | Telnyx | AI generates message from node guidance, sends via Telnyx SMS API from +18438838956. |
| Email | Microsoft Graph | AI drafts email from node guidance/templates, sends from LO's Outlook address. |
| Referral Partner | Telnyx / Graph | AI notifies referring agent via their preferred channel. |

### Action Outcome Tracking

New table: `workflow_ai_actions`

| Column | Type | Notes |
|--------|------|-------|
| id | UUID, PK | |
| workflow_node_id | UUID, FK | Which node triggered this |
| lead_id | UUID, FK | |
| channel | String | "phone", "text", "email" |
| autonomy_level | String | "supervised", "guided", "autonomous" |
| action_plan | JSON | What AI planned to do (draft text, call script) |
| human_review | JSON, nullable | LO edits/approval if in supervised/guided mode |
| execution_result | JSON | What happened (call duration, delivery status) |
| outcome | String | "success", "no_response", "negative", "error", "escalated" |
| confidence_before | Float | Score before this action |
| confidence_after | Float | Score after outcome |
| created_at | DateTime | |
| completed_at | DateTime, nullable | |

This table IS the learning data. Every row captures plan → review → execution → outcome → confidence delta. Over time, patterns emerge: which scripts work, which channels perform best for each node type, when leads are most responsive.

## Design System

Uses existing Perennia theme tokens:
- `pageBg: #FAF7F1`, `cardBg: #FFFFFF`, `primary: #1F3D2E`, `accent: #B8924A`
- `border: #ECE6D8`, `text: #1A1F1B`, `muted: #8B8A7E`
- `success: #2D7A52`, `error: #9B2C2C`, `warning: #B25F18`
- Fonts: Fraunces (headers), Geist/Inter (body), Geist Mono (monospace)

## What stays / what goes

- **Stays**: WorkflowStagePage, WorkflowStatusDetail (existing stage detail views), WorkflowScorecard, WorkflowUpcomingTasks (can be linked from the new UI)
- **Goes**: WorkflowDashboard.js replaced by WorkflowLayout + WorkflowFlowchart
- **Fallback**: WorkflowConfigEditor.js remains accessible (e.g., from settings page) during transition
- **Prototype files**: WorkflowBuilderV1-V6 and WorkflowBuilderShowcase stay as-is (prototype reference, separate routes)
