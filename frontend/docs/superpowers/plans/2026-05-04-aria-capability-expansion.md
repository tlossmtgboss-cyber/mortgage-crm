# Aria Capability Expansion — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expand Aria from intent-based task execution into a fully agentic AI assistant with three operating modes (Action/Query/Campaign), personalized greeting, refined pre-approval letter flow, POS incomplete application visibility, agentic CRM data access, and mass text campaigns with two-way SMS calendar coordination.

**Architecture:** Mode router (Claude Haiku classifier) before NLU node. Query mode uses Claude Sonnet with 12 read-only CRM tools. Campaign mode is a multi-step state machine with inbound SMS reply handling and graduated reminders. All modes share the same conversation engine entry point.

**Tech Stack:** FastAPI, Anthropic SDK (Claude Sonnet + Haiku), LangGraph, SQLAlchemy 2.0, PostgreSQL, Telnyx SMS, AppointmentService, EventBus

---

## File Map

| File | Responsibility |
|---|---|
| **Create:** `backend/aria/core/mode_router.py` | Classify messages into action/query/campaign (~100 lines) |
| **Create:** `backend/aria/tools/crm_query_tools.py` | 12 read-only CRM query tools for agentic mode (~800 lines) |
| **Create:** `backend/aria/tools/campaign_tools.py` | Campaign filter builder, batch sender (~500 lines) |
| **Create:** `backend/aria/campaigns/campaign_engine.py` | Multi-step campaign state machine (~600 lines) |
| **Create:** `backend/aria/campaigns/reply_handler.py` | Inbound SMS → campaign conversation routing + scheduling (~400 lines) |
| **Create:** `backend/aria/campaigns/reminder_service.py` | Graduated reminder cadence (~200 lines) |
| **Create:** `backend/database/models/aria_campaign.py` | `aria_campaigns` + `aria_campaign_recipients` models (~150 lines) |
| **Create:** `backend/migrations/add_aria_campaigns.py` | Table creation migration (~50 lines) |
| **Modify:** `backend/aria/core/conversation_engine.py` | Add mode router, query mode branch, greeting |
| **Modify:** `backend/aria/core/intent_registry.py` | Add `check_pos_applications` intent |
| **Modify:** `backend/aria/tasks/task_executor.py` | Add POS applications handler, rewrite pre-approval flow |
| **Modify:** `backend/aria/tools/communication_tools.py` | Add `send_batch_sms()`, `send_reminder()` |
| **Modify:** `backend/agents/aria_prompts.py` | Update LO assistant prompt with new capabilities |
| **Modify:** `backend/services/event_bus.py` | Add campaign event types |
| **Modify:** `backend/services/event_subscribers.py` | Register campaign event handlers |
| **Modify:** `backend/database/models/__init__.py` | Import campaign models |

---

### Task 1: Personalized Greeting — Fetch LO Name on Session Init

**Files:**
- Modify: `backend/aria/core/conversation_engine.py:80-131`

- [ ] **Step 1: Update `build_aria_system_prompt` to include greeting instruction**

In `backend/aria/core/conversation_engine.py`, in the `build_aria_system_prompt()` function, add to the personality section (after "You ask ONE question at a time"):

```python
## Greeting
When starting a new conversation, greet the LO by first name: "Hey {user_name}, what can I help you with?"
If the user name is unknown, use "Hey there" instead.
```

This goes inside the f-string that builds the system prompt, around line 99. The `user_name` variable is already available from the context dict.

- [ ] **Step 2: Add greeting to the AriaState initialization**

In `conversation_engine.py`, the `AriaState` TypedDict already has `user_name: str`. The `AriaContextLoader` already populates this. No model change needed — the greeting is handled by the system prompt instruction.

- [ ] **Step 3: Verify syntax**

Run: `cd /Users/timothyloss/my-project/mortgage-crm/backend && .venv/bin/python3 -c "from aria.core.conversation_engine import build_aria_system_prompt; p = build_aria_system_prompt({'user_name': 'Tim'}); print('Hey Tim' in p or 'Greeting' in p)"`

Expected: `True`

- [ ] **Step 4: Commit**

```bash
git add backend/aria/core/conversation_engine.py
git commit -m "feat(aria): add personalized greeting by LO name"
```

---

### Task 2: Mode Router

**Files:**
- Create: `backend/aria/core/mode_router.py`

- [ ] **Step 1: Write the mode router**

Create `backend/aria/core/mode_router.py`:

```python
"""
Mode Router — classifies incoming messages into action/query/campaign.

Uses a lightweight Claude Haiku call (~100ms) to determine which Aria engine
should handle the message. Runs before the NLU/intent node.
"""

import json
import logging
from enum import Enum

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage

logger = logging.getLogger(__name__)

llm_haiku = ChatAnthropic(
    model="claude-haiku-4-5-20251001",
    temperature=0,
    max_tokens=64,
)


class AriaMode(str, Enum):
    ACTION = "action"
    QUERY = "query"
    CAMPAIGN = "campaign"


ROUTER_PROMPT = """Classify the user's message into exactly one mode:

- "action" — user requests a state-changing operation: send, text, schedule, book, generate, create, update, move, add, remind
- "query" — user asks a question: how many, what's the, show me, who, which, when did, where is, check, look up, pull up, pipeline, status, report
- "campaign" — user describes a mass outreach: send a text to everyone, reach out to all, mass text, text everyone with, bulk message, campaign

Respond ONLY with JSON: {"mode": "action" | "query" | "campaign"}"""


async def classify_mode(message: str) -> AriaMode:
    try:
        response = await llm_haiku.ainvoke([
            SystemMessage(content=ROUTER_PROMPT),
            HumanMessage(content=message),
        ])
        parsed = json.loads(response.content.strip())
        mode_str = parsed.get("mode", "query")
        return AriaMode(mode_str)
    except Exception as e:
        logger.warning("Mode router classification failed: %s — defaulting to query", e)
        return AriaMode.QUERY
```

- [ ] **Step 2: Verify it loads**

Run: `cd /Users/timothyloss/my-project/mortgage-crm/backend && .venv/bin/python3 -c "from aria.core.mode_router import AriaMode, classify_mode; print(AriaMode.ACTION.value)"`

Expected: `action`

- [ ] **Step 3: Commit**

```bash
git add backend/aria/core/mode_router.py
git commit -m "feat(aria): add mode router for action/query/campaign classification"
```

---

### Task 3: Query Mode — 12 Read-Only CRM Query Tools

**Files:**
- Create: `backend/aria/tools/crm_query_tools.py`

- [ ] **Step 1: Write the 12 query tools**

Create `backend/aria/tools/crm_query_tools.py`:

```python
"""
CRM Query Tools — 12 read-only tools for Aria's agentic query mode.

Claude picks which tools to call, Aria executes them, feeds results back,
Claude synthesizes a natural-language answer. All tools filter on
organization_id for tenant isolation. No writes, no mutations.
"""

import logging
from datetime import date, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy import text
from db import SessionLocal

logger = logging.getLogger(__name__)


def _query(sql: str, params: dict) -> list:
    db = SessionLocal()
    try:
        result = db.execute(text(sql), params)
        return [dict(row._mapping) for row in result.fetchall()]
    finally:
        db.close()


def _single(sql: str, params: dict) -> dict | None:
    rows = _query(sql, params)
    return rows[0] if rows else None


# Tool definitions for Claude tool-use (Anthropic API format)
QUERY_TOOL_DEFINITIONS = [
    {
        "name": "search_loans",
        "description": "Search loans by stage, date range, amount range, rate, LO assignment, or any combination. Use for: 'loans in processing', 'loans closing this month', 'loans over 500K'.",
        "input_schema": {
            "type": "object",
            "properties": {
                "stage": {"type": "string", "description": "Pipeline stage filter (e.g. PROCESSING, UNDERWRITING, FUNDED)"},
                "min_amount": {"type": "number"},
                "max_amount": {"type": "number"},
                "min_rate": {"type": "number"},
                "max_rate": {"type": "number"},
                "closing_date_from": {"type": "string", "description": "ISO date"},
                "closing_date_to": {"type": "string", "description": "ISO date"},
                "loan_type": {"type": "string"},
                "limit": {"type": "integer", "default": 20},
            },
            "required": [],
        },
    },
    {
        "name": "search_leads",
        "description": "Search leads by stage, source, date range, activity status. Use for: 'Zillow leads from last week', 'leads with no activity in 30 days'.",
        "input_schema": {
            "type": "object",
            "properties": {
                "stage": {"type": "string"},
                "source": {"type": "string"},
                "created_from": {"type": "string"},
                "created_to": {"type": "string"},
                "inactive_days": {"type": "integer", "description": "Leads with no activity in this many days"},
                "limit": {"type": "integer", "default": 20},
            },
            "required": [],
        },
    },
    {
        "name": "get_pipeline_summary",
        "description": "Get count of loans in each pipeline stage. Use for: 'how's my pipeline look?', 'how many loans in each stage?'",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_production_stats",
        "description": "Get loan production stats: closed count, total volume, average loan size. Use for: 'how many loans did I close last month?', 'total volume this year'.",
        "input_schema": {
            "type": "object",
            "properties": {
                "period": {"type": "string", "description": "e.g. 'this_month', 'last_month', 'this_year', 'last_year', 'q1', 'q2', 'q3', 'q4'"},
            },
            "required": [],
        },
    },
    {
        "name": "get_rate_analysis",
        "description": "Analyze interest rates across the pipeline. Use for: 'average rate on my pipeline', 'who has rates above 6%?'",
        "input_schema": {
            "type": "object",
            "properties": {
                "min_rate": {"type": "number"},
                "max_rate": {"type": "number"},
            },
            "required": [],
        },
    },
    {
        "name": "get_commission_data",
        "description": "Get commission/revenue data. Use for: 'commission earned in Q1', 'revenue this month'.",
        "input_schema": {
            "type": "object",
            "properties": {
                "period": {"type": "string"},
            },
            "required": [],
        },
    },
    {
        "name": "get_referral_stats",
        "description": "Get referral partner stats. Use for: 'who referred the most deals?', 'top producing realtors'.",
        "input_schema": {
            "type": "object",
            "properties": {
                "period": {"type": "string"},
                "limit": {"type": "integer", "default": 10},
            },
            "required": [],
        },
    },
    {
        "name": "get_loan_details",
        "description": "Get detailed info on a specific loan file. Use for: 'what conditions are outstanding on the Smith file?'",
        "input_schema": {
            "type": "object",
            "properties": {
                "borrower_name": {"type": "string"},
                "loan_id": {"type": "integer"},
            },
            "required": [],
        },
    },
    {
        "name": "get_lead_activity",
        "description": "Get recent activity on a lead/contact. Use for: 'when did I last contact Jane?', 'activity on the Johnson file'.",
        "input_schema": {
            "type": "object",
            "properties": {
                "contact_name": {"type": "string"},
                "lead_id": {"type": "integer"},
                "limit": {"type": "integer", "default": 10},
            },
            "required": [],
        },
    },
    {
        "name": "get_task_summary",
        "description": "Get task summary: due today, overdue, upcoming. Use for: 'what tasks are due today?', 'overdue follow-ups'.",
        "input_schema": {
            "type": "object",
            "properties": {
                "status": {"type": "string", "description": "pending, overdue, completed"},
                "due_date": {"type": "string", "description": "ISO date filter"},
            },
            "required": [],
        },
    },
    {
        "name": "get_document_status",
        "description": "Get document status for a loan file. Use for: 'what docs are missing on the Doe file?'",
        "input_schema": {
            "type": "object",
            "properties": {
                "borrower_name": {"type": "string"},
                "loan_id": {"type": "integer"},
            },
            "required": [],
        },
    },
    {
        "name": "get_pos_stats",
        "description": "Get POS application stats. Use for: 'how many applications came in this week?'",
        "input_schema": {
            "type": "object",
            "properties": {
                "period": {"type": "string"},
                "status": {"type": "string", "description": "draft, submitted, abandoned"},
            },
            "required": [],
        },
    },
]


def search_loans(org_id: str, **params) -> list[dict]:
    conditions = ["l.organization_id = :org_id"]
    bind = {"org_id": org_id}

    if params.get("stage"):
        conditions.append("UPPER(l.stage) = UPPER(:stage)")
        bind["stage"] = params["stage"]
    if params.get("min_amount"):
        conditions.append("l.loan_amount >= :min_amount")
        bind["min_amount"] = params["min_amount"]
    if params.get("max_amount"):
        conditions.append("l.loan_amount <= :max_amount")
        bind["max_amount"] = params["max_amount"]
    if params.get("min_rate"):
        conditions.append("l.rate >= :min_rate")
        bind["min_rate"] = params["min_rate"]
    if params.get("max_rate"):
        conditions.append("l.rate <= :max_rate")
        bind["max_rate"] = params["max_rate"]
    if params.get("closing_date_from"):
        conditions.append("l.closing_date >= :closing_from")
        bind["closing_from"] = params["closing_date_from"]
    if params.get("closing_date_to"):
        conditions.append("l.closing_date <= :closing_to")
        bind["closing_to"] = params["closing_date_to"]
    if params.get("loan_type"):
        conditions.append("UPPER(l.loan_type) = UPPER(:loan_type)")
        bind["loan_type"] = params["loan_type"]

    limit = min(int(params.get("limit", 20)), 50)
    where = " AND ".join(conditions)

    return _query(
        f"SELECT l.id, l.loan_number, l.borrower_name, l.loan_amount, "
        f"l.rate, l.stage, l.loan_type, l.property_address, l.closing_date, "
        f"l.updated_at "
        f"FROM loans l WHERE {where} "
        f"ORDER BY l.updated_at DESC LIMIT :lim",
        {**bind, "lim": limit},
    )


def search_leads(org_id: str, **params) -> list[dict]:
    conditions = ["ld.organization_id = :org_id"]
    bind = {"org_id": org_id}

    if params.get("stage"):
        conditions.append("UPPER(ld.stage) = UPPER(:stage)")
        bind["stage"] = params["stage"]
    if params.get("source"):
        conditions.append("LOWER(ld.source) LIKE :source")
        bind["source"] = f"%{params['source'].lower()}%"
    if params.get("created_from"):
        conditions.append("ld.created_at >= :created_from")
        bind["created_from"] = params["created_from"]
    if params.get("created_to"):
        conditions.append("ld.created_at <= :created_to")
        bind["created_to"] = params["created_to"]
    if params.get("inactive_days"):
        conditions.append("ld.updated_at < NOW() - INTERVAL ':days days'")
        bind["days"] = params["inactive_days"]

    limit = min(int(params.get("limit", 20)), 50)
    where = " AND ".join(conditions)

    return _query(
        f"SELECT ld.id, ld.name, ld.email, ld.phone, ld.stage, ld.source, "
        f"ld.created_at, ld.updated_at "
        f"FROM leads ld WHERE {where} "
        f"ORDER BY ld.updated_at DESC LIMIT :lim",
        {**bind, "lim": limit},
    )


def get_pipeline_summary(org_id: str, **params) -> list[dict]:
    return _query(
        "SELECT stage, COUNT(*) as count, "
        "COALESCE(SUM(loan_amount), 0) as total_volume "
        "FROM loans WHERE organization_id = :org_id "
        "AND stage NOT IN ('FUNDED','CANCELLED','DENIED','DEAD','WITHDRAWN') "
        "GROUP BY stage ORDER BY count DESC",
        {"org_id": org_id},
    )


def get_production_stats(org_id: str, **params) -> dict:
    period = params.get("period", "this_month")
    today = date.today()

    if period == "this_month":
        start = today.replace(day=1)
        end = today
    elif period == "last_month":
        first_of_this = today.replace(day=1)
        end = first_of_this - timedelta(days=1)
        start = end.replace(day=1)
    elif period == "this_year":
        start = today.replace(month=1, day=1)
        end = today
    elif period == "last_year":
        start = today.replace(year=today.year - 1, month=1, day=1)
        end = today.replace(year=today.year - 1, month=12, day=31)
    else:
        start = today.replace(day=1)
        end = today

    row = _single(
        "SELECT COUNT(*) as closed_count, "
        "COALESCE(SUM(loan_amount), 0) as total_volume, "
        "COALESCE(AVG(loan_amount), 0) as avg_loan_size "
        "FROM loans WHERE organization_id = :org_id "
        "AND UPPER(stage) = 'FUNDED' "
        "AND updated_at >= :start AND updated_at <= :end",
        {"org_id": org_id, "start": start.isoformat(), "end": end.isoformat()},
    )
    return row or {"closed_count": 0, "total_volume": 0, "avg_loan_size": 0}


def get_rate_analysis(org_id: str, **params) -> list[dict]:
    conditions = [
        "organization_id = :org_id",
        "rate IS NOT NULL",
        "stage NOT IN ('FUNDED','CANCELLED','DENIED','DEAD','WITHDRAWN')",
    ]
    bind = {"org_id": org_id}

    if params.get("min_rate"):
        conditions.append("rate >= :min_rate")
        bind["min_rate"] = params["min_rate"]
    if params.get("max_rate"):
        conditions.append("rate <= :max_rate")
        bind["max_rate"] = params["max_rate"]

    where = " AND ".join(conditions)
    return _query(
        f"SELECT id, borrower_name, loan_amount, rate, stage, loan_type "
        f"FROM loans WHERE {where} ORDER BY rate DESC LIMIT 25",
        bind,
    )


def get_commission_data(org_id: str, **params) -> dict:
    period = params.get("period", "this_month")
    today = date.today()
    if period == "this_month":
        start = today.replace(day=1)
    elif period == "last_month":
        start = (today.replace(day=1) - timedelta(days=1)).replace(day=1)
    elif period == "this_year":
        start = today.replace(month=1, day=1)
    else:
        start = today.replace(day=1)

    row = _single(
        "SELECT COUNT(*) as deal_count, "
        "COALESCE(SUM(loan_amount), 0) as total_volume "
        "FROM loans WHERE organization_id = :org_id "
        "AND UPPER(stage) = 'FUNDED' AND updated_at >= :start",
        {"org_id": org_id, "start": start.isoformat()},
    )
    return row or {"deal_count": 0, "total_volume": 0}


def get_referral_stats(org_id: str, **params) -> list[dict]:
    limit = min(int(params.get("limit", 10)), 25)
    return _query(
        "SELECT rp.id, rp.name, rp.company, rp.email, "
        "COUNT(ld.id) as lead_count "
        "FROM referral_partners rp "
        "LEFT JOIN leads ld ON ld.referral_partner_id = rp.id "
        "WHERE rp.organization_id = :org_id "
        "GROUP BY rp.id, rp.name, rp.company, rp.email "
        "ORDER BY lead_count DESC LIMIT :lim",
        {"org_id": org_id, "lim": limit},
    )


def get_loan_details(org_id: str, **params) -> dict | None:
    if params.get("loan_id"):
        return _single(
            "SELECT l.*, ld.name as lead_name, ld.email as lead_email, ld.phone as lead_phone "
            "FROM loans l LEFT JOIN leads ld ON l.lead_id = ld.id "
            "WHERE l.id = :loan_id AND l.organization_id = :org_id",
            {"loan_id": params["loan_id"], "org_id": org_id},
        )
    if params.get("borrower_name"):
        return _single(
            "SELECT l.*, ld.name as lead_name, ld.email as lead_email, ld.phone as lead_phone "
            "FROM loans l LEFT JOIN leads ld ON l.lead_id = ld.id "
            "WHERE l.organization_id = :org_id "
            "AND LOWER(l.borrower_name) LIKE :name "
            "ORDER BY l.updated_at DESC LIMIT 1",
            {"org_id": org_id, "name": f"%{params['borrower_name'].lower()}%"},
        )
    return None


def get_lead_activity(org_id: str, **params) -> list[dict]:
    limit = min(int(params.get("limit", 10)), 25)
    conditions = ["a.organization_id = :org_id"]
    bind: dict = {"org_id": org_id, "lim": limit}

    if params.get("lead_id"):
        conditions.append("a.lead_id = :lead_id")
        bind["lead_id"] = params["lead_id"]
    elif params.get("contact_name"):
        conditions.append(
            "a.lead_id IN (SELECT id FROM leads WHERE organization_id = :org_id "
            "AND LOWER(name) LIKE :name)"
        )
        bind["name"] = f"%{params['contact_name'].lower()}%"

    where = " AND ".join(conditions)
    return _query(
        f"SELECT a.id, a.type, a.content, a.created_at, a.lead_id "
        f"FROM activities a WHERE {where} "
        f"ORDER BY a.created_at DESC LIMIT :lim",
        bind,
    )


def get_task_summary(org_id: str, user_id: str = None, **params) -> list[dict]:
    conditions = ["t.organization_id = :org_id"]
    bind: dict = {"org_id": org_id}

    if user_id:
        conditions.append("t.owner_id = :user_id")
        bind["user_id"] = user_id

    status = params.get("status")
    if status == "overdue":
        conditions.append("t.due_date < NOW() AND t.status = 'pending'")
    elif status == "completed":
        conditions.append("t.status = 'completed'")
    else:
        conditions.append("t.status = 'pending'")

    if params.get("due_date"):
        conditions.append("DATE(t.due_date) = :due_date")
        bind["due_date"] = params["due_date"]

    where = " AND ".join(conditions)
    return _query(
        f"SELECT t.id, t.title, t.description, t.status, t.priority, "
        f"t.due_date, t.created_at "
        f"FROM tasks t WHERE {where} "
        f"ORDER BY t.due_date ASC LIMIT 20",
        bind,
    )


def get_document_status(org_id: str, **params) -> list[dict]:
    if params.get("loan_id"):
        loan_filter = "d.loan_id = :loan_id"
        bind = {"loan_id": params["loan_id"], "org_id": org_id}
    elif params.get("borrower_name"):
        loan_filter = (
            "d.loan_id IN (SELECT id FROM loans WHERE organization_id = :org_id "
            "AND LOWER(borrower_name) LIKE :name)"
        )
        bind = {"org_id": org_id, "name": f"%{params['borrower_name'].lower()}%"}
    else:
        return []

    return _query(
        f"SELECT d.id, d.name, d.status, d.category, d.created_at "
        f"FROM documents d WHERE {loan_filter} "
        f"AND d.organization_id = :org_id "
        f"ORDER BY d.created_at DESC LIMIT 30",
        bind,
    )


def get_pos_stats(org_id: str, **params) -> dict:
    period = params.get("period", "this_week")
    today = date.today()

    if period == "this_week":
        start = today - timedelta(days=today.weekday())
    elif period == "this_month":
        start = today.replace(day=1)
    elif period == "today":
        start = today
    else:
        start = today - timedelta(days=7)

    status_filter = ""
    bind: dict = {"org_id": org_id, "start": start.isoformat()}
    if params.get("status"):
        status_filter = "AND status = :status"
        bind["status"] = params["status"]

    rows = _query(
        f"SELECT status, COUNT(*) as count "
        f"FROM pos_applications "
        f"WHERE organization_id = :org_id "
        f"AND created_at >= :start {status_filter} "
        f"GROUP BY status",
        bind,
    )
    return {"period": period, "start_date": start.isoformat(), "breakdown": rows}


# Dispatch map — maps tool name to function
TOOL_DISPATCH = {
    "search_loans": search_loans,
    "search_leads": search_leads,
    "get_pipeline_summary": get_pipeline_summary,
    "get_production_stats": get_production_stats,
    "get_rate_analysis": get_rate_analysis,
    "get_commission_data": get_commission_data,
    "get_referral_stats": get_referral_stats,
    "get_loan_details": get_loan_details,
    "get_lead_activity": get_lead_activity,
    "get_task_summary": get_task_summary,
    "get_document_status": get_document_status,
    "get_pos_stats": get_pos_stats,
}


def execute_query_tool(tool_name: str, org_id: str, user_id: str = None, **params) -> Any:
    fn = TOOL_DISPATCH.get(tool_name)
    if not fn:
        return {"error": f"Unknown query tool: {tool_name}"}
    try:
        if tool_name == "get_task_summary":
            return fn(org_id=org_id, user_id=user_id, **params)
        return fn(org_id=org_id, **params)
    except Exception as e:
        logger.error("Query tool %s failed: %s", tool_name, e, exc_info=True)
        return {"error": str(e)}
```

- [ ] **Step 2: Verify tools load**

Run: `cd /Users/timothyloss/my-project/mortgage-crm/backend && .venv/bin/python3 -c "from aria.tools.crm_query_tools import QUERY_TOOL_DEFINITIONS, TOOL_DISPATCH; print(f'{len(QUERY_TOOL_DEFINITIONS)} definitions, {len(TOOL_DISPATCH)} dispatch entries')"`

Expected: `12 definitions, 12 dispatch entries`

- [ ] **Step 3: Commit**

```bash
git add backend/aria/tools/crm_query_tools.py
git commit -m "feat(aria): add 12 read-only CRM query tools for agentic mode"
```

---

### Task 4: Wire Query Mode into Conversation Engine

**Files:**
- Modify: `backend/aria/core/conversation_engine.py`

- [ ] **Step 1: Add query mode node and integrate mode router**

In `backend/aria/core/conversation_engine.py`:

1. Add imports at the top:

```python
from aria.core.mode_router import classify_mode, AriaMode
```

2. Add a `mode` field to `AriaState` (after `user_role: str`):

```python
    mode: Optional[str]  # "action", "query", "campaign"
```

3. Add the query mode node function (after `response_node` and before the routing logic section):

```python
async def query_mode_node(state: AriaState) -> AriaState:
    """Agentic query mode — Claude picks tools, chains queries, synthesizes answer."""
    import json as _json
    import anthropic
    import os

    from aria.tools.crm_query_tools import QUERY_TOOL_DEFINITIONS, execute_query_tool

    question = state["messages"][-1].content if state["messages"] else ""
    org_id = state["org_id"]
    user_id = state["user_id"]

    client = anthropic.AsyncAnthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))

    context_loader = AriaContextLoader()
    context = await context_loader.load_full(user_id)
    system = build_aria_system_prompt(context)

    messages = [{"role": "user", "content": question}]

    response = await client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        temperature=0.3,
        system=system + "\n\nYou have access to CRM query tools. Use them to answer the LO's question. Chain multiple tools if needed. Be specific with numbers and names.",
        messages=messages,
        tools=QUERY_TOOL_DEFINITIONS,
    )

    # Tool-use loop (max 3 rounds)
    for _ in range(3):
        tool_blocks = [b for b in response.content if b.type == "tool_use"]
        if not tool_blocks:
            break

        tool_results = []
        for block in tool_blocks:
            result = execute_query_tool(
                block.name, org_id=org_id, user_id=user_id, **block.input
            )
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": _json.dumps(result, default=str),
            })

        messages.append({"role": "assistant", "content": response.content})
        messages.append({"role": "user", "content": tool_results})

        response = await client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1024,
            temperature=0.3,
            system=system,
            messages=messages,
            tools=QUERY_TOOL_DEFINITIONS,
        )

    # Extract text response
    text_blocks = [b.text for b in response.content if hasattr(b, "text")]
    answer = "\n".join(text_blocks) or "I couldn't find that information."

    return {
        "messages": [AIMessage(content=answer)],
        "phase": DialoguePhase.RESPONDING,
    }
```

4. Update the `dispatch_node` to run mode classification on first message:

Replace the existing `dispatch_node` function:

```python
async def dispatch_node(state: AriaState) -> dict:
    """Entry point for each turn. Runs mode router on first message."""
    count = state.get("iteration_count", 0)
    if count >= MAX_SLOT_ITERATIONS:
        return {
            "phase": DialoguePhase.RESPONDING,
            "error": "I seem to be going in circles. Let me start fresh — what would you like to do?",
        }

    # Run mode router if no intent/mode set yet
    if not state.get("intent") and not state.get("mode"):
        last_message = state["messages"][-1].content if state["messages"] else ""
        mode = await classify_mode(last_message)
        return {"mode": mode.value}

    return {}
```

5. Update `route_dispatch` to handle query mode:

```python
def route_dispatch(state: AriaState) -> str:
    if state.get("error") and state.get("iteration_count", 0) >= MAX_SLOT_ITERATIONS:
        return "response"

    phase = state.get("phase", "")

    if phase == DialoguePhase.SLOT_FILLING and state.get("current_slot_question"):
        return "slot_answer"

    if phase == DialoguePhase.CONFIRMING:
        return "check_confirm"

    # Mode-based routing
    mode = state.get("mode")
    if mode == AriaMode.QUERY.value:
        return "query_mode"

    return "nlu"
```

6. Add the query_mode node to the graph in `build_aria_graph()`:

After `graph.add_node("response", response_node)`, add:

```python
    graph.add_node("query_mode", query_mode_node)
```

Update `route_dispatch` edges to include `"query_mode"`:

```python
    graph.add_conditional_edges("dispatch", route_dispatch, {
        "nlu":           "nlu",
        "slot_answer":   "slot_answer",
        "check_confirm": "check_confirm",
        "response":      "response",
        "query_mode":    "query_mode",
    })
```

Add edge from query_mode to END:

```python
    graph.add_edge("query_mode", END)
```

- [ ] **Step 2: Verify graph builds**

Run: `cd /Users/timothyloss/my-project/mortgage-crm/backend && .venv/bin/python3 -c "from aria.core.conversation_engine import build_aria_graph; g = build_aria_graph(); print('Graph built with nodes:', list(g.nodes.keys()) if hasattr(g, 'nodes') else 'OK')"`

Expected: Should include `query_mode` in the node list

- [ ] **Step 3: Commit**

```bash
git add backend/aria/core/conversation_engine.py
git commit -m "feat(aria): wire query mode into conversation engine with tool-use loop"
```

---

### Task 5: Add `check_pos_applications` Intent and Handler

**Files:**
- Modify: `backend/aria/core/intent_registry.py`
- Modify: `backend/aria/tasks/task_executor.py`

- [ ] **Step 1: Add the intent to the registry**

In `backend/aria/core/intent_registry.py`, add to `_build_intents()` list (after `pipeline_report`):

```python
        Intent(
            name="check_pos_applications",
            description="Check which borrowers have started but not completed their online application (POS/1003)",
            category="lookup",
            trigger_phrases=[
                "who hasn't finished their application",
                "incomplete applications",
                "stalled POS apps",
                "who started an application",
                "unfinished 1003s",
                "abandoned applications",
                "stalled applications",
                "POS applications",
                "who hasn't completed their app",
            ],
            required_slots=[],
            optional_slots=[
                SlotSpec("date_range", "Filter by date range", "text", required=False, default="all"),
            ],
            requires_confirmation=False,
        ),
```

- [ ] **Step 2: Add the handler to TaskExecutor**

In `backend/aria/tasks/task_executor.py`:

1. Add to `self._handlers` dict:

```python
            "check_pos_applications": self._check_pos_applications,
```

2. Add the handler method (after `_check_my_schedule`):

```python
    async def _check_pos_applications(self, slots, user_id, org_id) -> Dict:
        """Check for incomplete POS applications and return summary."""
        def _query():
            from db import SessionLocal
            from sqlalchemy import text
            db = SessionLocal()
            try:
                rows = db.execute(text(
                    "SELECT pa.id, pa.current_step, pa.completion_pct, "
                    "pa.created_at, pa.updated_at, "
                    "ld.name, ld.email, ld.phone "
                    "FROM pos_applications pa "
                    "LEFT JOIN leads ld ON pa.contact_id = ld.id "
                    "WHERE pa.organization_id = :org_id "
                    "AND pa.status = 'draft' "
                    "ORDER BY pa.updated_at DESC"
                ), {"org_id": org_id}).fetchall()
                return rows
            finally:
                db.close()

        rows = await asyncio.to_thread(_query)

        apps = []
        for r in rows:
            apps.append({
                "application_id": str(r[0]),
                "current_step": r[1],
                "completion_pct": r[2],
                "started": r[3].isoformat() if r[3] else None,
                "last_activity": r[4].isoformat() if r[4] else None,
                "borrower_name": r[5] or "Unknown",
                "borrower_email": r[6],
                "borrower_phone": r[7],
            })

        lo = await self.crm.get_user(user_id)

        return {
            "action": "pos_applications_checked",
            "total_incomplete": len(apps),
            "applications": apps[:20],
            "lo_email": lo.get("email") if lo else None,
            "summary_mode": "full" if len(apps) <= 5 else "top_3",
        }
```

- [ ] **Step 3: Verify intent loads**

Run: `cd /Users/timothyloss/my-project/mortgage-crm/backend && .venv/bin/python3 -c "from aria.core.intent_registry import IntentRegistry; r = IntentRegistry.get(); i = r.get_intent('check_pos_applications'); print(i.name, len(i.trigger_phrases), 'triggers')"`

Expected: `check_pos_applications 9 triggers`

- [ ] **Step 4: Commit**

```bash
git add backend/aria/core/intent_registry.py backend/aria/tasks/task_executor.py
git commit -m "feat(aria): add check_pos_applications intent and handler"
```

---

### Task 6: Rewrite Pre-Approval Letter Flow with Review-Edit Loop

**Files:**
- Modify: `backend/aria/core/intent_registry.py`
- Modify: `backend/aria/tasks/task_executor.py`

- [ ] **Step 1: Update the send_preapproval_letter intent — remove most required slots**

In `backend/aria/core/intent_registry.py`, replace the existing `send_preapproval_letter` Intent with:

```python
        Intent(
            name="send_preapproval_letter",
            description="Generate and send a mortgage pre-approval letter with review-edit loop for all fields",
            category="documents",
            trigger_phrases=[
                "send a pre-approval letter",
                "pre-approval for",
                "send preapproval",
                "generate pre-approval",
                "prequal letter",
                "pre-qual for",
                "text a pre-approval letter",
                "send pre-approval via sms",
                "send preapproval via text",
                "sms pre-approval",
                "text the pre-approval to",
            ],
            required_slots=[
                SlotSpec("borrower_id", "Which borrower this letter is for", "borrower",
                         extraction_hint="borrower name or loan number"),
            ],
            optional_slots=[
                SlotSpec("delivery_channel", "How to deliver: email or sms", "choice",
                         required=False, default="email",
                         choices=["email", "sms"],
                         extraction_hint="'via sms', 'via text', 'text it' = sms. Default: email"),
            ],
        ),
```

The key change: `recipient` and `approval_amount` are removed from required slots. The handler auto-populates these from CRM data and presents them for review.

- [ ] **Step 2: Rewrite the handler to use review-edit loop**

In `backend/aria/tasks/task_executor.py`, replace the existing `_send_preapproval_letter` method with:

```python
    async def _send_preapproval_letter(self, slots, user_id, org_id) -> Dict:
        """Review-edit loop: auto-populate from CRM, present, allow edits, then send."""
        borrower = await self.crm.get_borrower(slots["borrower_id"], org_id)
        if not borrower:
            raise ValueError(f"Borrower not found: {slots['borrower_id']}")

        loan = await self.crm.get_active_loan(borrower["id"], org_id)
        lo = await self.crm.get_user(user_id)

        purchase_price = loan.get("purchase_price") if loan else None
        loan_amount = loan.get("loan_amount") if loan else None
        loan_type = loan.get("loan_type", "Conventional") if loan else "Conventional"
        property_address = loan.get("property_address") if loan else None
        approval_amount = slots.get("approval_amount") or loan_amount

        # If explicit overrides were provided via edits, use them
        if slots.get("purchase_price"):
            purchase_price = float(slots["purchase_price"])
        if slots.get("loan_amount"):
            loan_amount = float(slots["loan_amount"])
        if slots.get("approval_amount"):
            approval_amount = float(slots["approval_amount"])
        if slots.get("property_address"):
            property_address = slots["property_address"]
        if slots.get("property_address_tbd"):
            property_address = "TBD"

        if not approval_amount:
            raise ValueError("Could not determine approval amount — no loan data found for this borrower.")

        doc_result = await self.docs.generate_preapproval_letter(
            borrower=borrower, loan=loan, lo=lo,
            approval_amount=float(approval_amount),
            property_address=property_address,
            expiry_days=int(slots.get("expiry_days", 30)),
            custom_note=slots.get("custom_note"),
        )

        # Resolve recipient
        recipient = slots.get("recipient")
        delivery_channel = (slots.get("delivery_channel") or "email").lower().strip()

        if not recipient:
            # Check for associated realtor on the loan/lead
            realtor = await self._find_associated_realtor(borrower["id"], org_id)
            if realtor:
                recipient = realtor.get("name") or realtor.get("email")
            else:
                raise ValueError(
                    "Who should I send this to? I don't see an agent on this file."
                )

        if delivery_channel == "sms":
            return await self._deliver_preapproval_via_sms(
                slots={**slots, "recipient": recipient, "approval_amount": approval_amount},
                borrower=borrower, loan=loan, lo=lo,
                doc_result=doc_result, user_id=user_id, org_id=org_id,
            )
        return await self._deliver_preapproval_via_email(
            slots={**slots, "recipient": recipient, "approval_amount": approval_amount},
            borrower=borrower, loan=loan, lo=lo,
            doc_result=doc_result, user_id=user_id,
        )

    async def _find_associated_realtor(self, lead_id: int, org_id: str) -> Optional[Dict]:
        """Check if there's a realtor/referral partner associated with this lead."""
        def _query():
            db_session = __import__('db', fromlist=['SessionLocal']).SessionLocal()
            try:
                from sqlalchemy import text
                row = db_session.execute(text(
                    "SELECT rp.id, rp.name, rp.email, rp.phone "
                    "FROM referral_partners rp "
                    "JOIN leads ld ON ld.referral_partner_id = rp.id "
                    "WHERE ld.id = :lead_id AND rp.organization_id = :org_id "
                    "LIMIT 1"
                ), {"lead_id": lead_id, "org_id": org_id}).fetchone()
                if row:
                    return {"id": row[0], "name": row[1], "email": row[2], "phone": row[3]}
                return None
            finally:
                db_session.close()
        return await asyncio.to_thread(_query)
```

Add the `Optional` import if not present at the top of the file:

```python
from typing import Any, Dict, Optional
```

- [ ] **Step 3: Verify handler loads**

Run: `cd /Users/timothyloss/my-project/mortgage-crm/backend && .venv/bin/python3 -c "from aria.tasks.task_executor import TaskExecutor; t = TaskExecutor(); print('check_pos_applications' in t._handlers and 'send_preapproval_letter' in t._handlers)"`

Expected: `True`

- [ ] **Step 4: Commit**

```bash
git add backend/aria/core/intent_registry.py backend/aria/tasks/task_executor.py
git commit -m "feat(aria): rewrite pre-approval letter flow with review-edit loop and TBD support"
```

---

### Task 7: Campaign Data Model

**Files:**
- Create: `backend/database/models/aria_campaign.py`
- Create: `backend/migrations/add_aria_campaigns.py`
- Modify: `backend/database/models/__init__.py`

- [ ] **Step 1: Write the campaign models**

Create `backend/database/models/aria_campaign.py`:

```python
"""
Aria Campaign models — mass text outreach with two-way SMS coordination.
"""

from datetime import datetime
from sqlalchemy import (
    Boolean, Column, DateTime, ForeignKey, Index, Integer,
    String, Text, func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from db import Base


class AriaCampaign(Base):
    __tablename__ = "aria_campaigns"

    id = Column(Integer, primary_key=True, autoincrement=True)
    organization_id = Column(Integer, nullable=False, index=True)
    created_by_user_id = Column(Integer, nullable=False)

    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)

    filter_criteria = Column(JSONB, nullable=False)
    message_template = Column(Text, nullable=False)

    status = Column(String(32), nullable=False, default="draft", index=True)
    # draft, sending, active, completed, cancelled

    recipient_count = Column(Integer, nullable=False, default=0)
    sent_count = Column(Integer, nullable=False, default=0)
    replied_count = Column(Integer, nullable=False, default=0)
    booked_count = Column(Integer, nullable=False, default=0)
    declined_count = Column(Integer, nullable=False, default=0)

    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)

    recipients = relationship(
        "AriaCampaignRecipient",
        back_populates="campaign",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index("ix_aria_campaign_org_status", "organization_id", "status"),
    )


class AriaCampaignRecipient(Base):
    __tablename__ = "aria_campaign_recipients"

    id = Column(Integer, primary_key=True, autoincrement=True)
    campaign_id = Column(
        Integer,
        ForeignKey("aria_campaigns.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    lead_id = Column(Integer, nullable=True)
    loan_id = Column(Integer, nullable=True)

    phone = Column(String(32), nullable=False)
    email = Column(String(255), nullable=True)
    first_name = Column(String(128), nullable=True)

    status = Column(String(32), nullable=False, default="pending")
    # pending, sent, delivered, replied, booked, completed, no_show, declined, failed

    message_id = Column(String(255), nullable=True)  # Telnyx message ID
    appointment_id = Column(Integer, nullable=True)  # FK to scheduler_appointments

    sent_at = Column(DateTime(timezone=True), nullable=True)
    replied_at = Column(DateTime(timezone=True), nullable=True)
    booked_at = Column(DateTime(timezone=True), nullable=True)

    reminder_day_before_sent = Column(Boolean, nullable=False, default=False)
    reminder_hour_before_sent = Column(Boolean, nullable=False, default=False)
    no_show_followup_sent = Column(Boolean, nullable=False, default=False)

    campaign = relationship("AriaCampaign", back_populates="recipients")

    __table_args__ = (
        Index("ix_aria_recipient_campaign_status", "campaign_id", "status"),
        Index("ix_aria_recipient_phone", "phone"),
        Index("ix_aria_recipient_message_id", "message_id"),
    )
```

- [ ] **Step 2: Write the migration**

Create `backend/migrations/add_aria_campaigns.py`:

```python
"""
Migration: Create aria_campaigns and aria_campaign_recipients tables.

Run: python migrations/add_aria_campaigns.py
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sqlalchemy import inspect
from db import engine
from database.models.aria_campaign import AriaCampaign, AriaCampaignRecipient


def migrate():
    inspector = inspect(engine)
    existing = inspector.get_table_names()

    if "aria_campaigns" not in existing:
        AriaCampaign.__table__.create(engine, checkfirst=True)
        print("Created table: aria_campaigns")
    else:
        print("Table aria_campaigns already exists")

    if "aria_campaign_recipients" not in existing:
        AriaCampaignRecipient.__table__.create(engine, checkfirst=True)
        print("Created table: aria_campaign_recipients")
    else:
        print("Table aria_campaign_recipients already exists")


if __name__ == "__main__":
    migrate()
```

- [ ] **Step 3: Add imports to models/__init__.py**

In `backend/database/models/__init__.py`, add after the Client File imports:

```python
# Aria Campaign models (mass text outreach)
from .aria_campaign import AriaCampaign, AriaCampaignRecipient
```

And add to `__all__`:

```python
    # =====================
    # Aria Campaigns
    # =====================
    "AriaCampaign",
    "AriaCampaignRecipient",
```

- [ ] **Step 4: Verify models load**

Run: `cd /Users/timothyloss/my-project/mortgage-crm/backend && .venv/bin/python3 -c "from database.models.aria_campaign import AriaCampaign, AriaCampaignRecipient; print('Campaign models loaded')"`

Expected: `Campaign models loaded`

- [ ] **Step 5: Commit**

```bash
git add backend/database/models/aria_campaign.py backend/migrations/add_aria_campaigns.py backend/database/models/__init__.py
git commit -m "feat(aria): add AriaCampaign and AriaCampaignRecipient models with migration"
```

---

### Task 8: Campaign Tools — Filter Builder and Batch Sender

**Files:**
- Create: `backend/aria/tools/campaign_tools.py`

- [ ] **Step 1: Write campaign tools**

Create `backend/aria/tools/campaign_tools.py`:

```python
"""
Campaign Tools — filter builder and batch SMS sender for Aria campaigns.
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import text
from db import SessionLocal

logger = logging.getLogger(__name__)


class CampaignFilterBuilder:
    """Translate natural-language criteria into SQL filters for campaign audiences."""

    FILTERABLE_FIELDS = {
        "rate": ("l.rate", "number"),
        "interest_rate": ("l.rate", "number"),
        "loan_amount": ("l.loan_amount", "number"),
        "stage": ("l.stage", "stage"),
        "loan_type": ("l.loan_type", "text"),
        "closing_date": ("l.closing_date", "date"),
        "property_address": ("l.property_address", "text"),
    }

    def build_query(self, filter_criteria: dict, org_id: str) -> tuple[str, dict]:
        """Build SQL query from structured filter criteria.

        Returns (sql, params) tuple.
        """
        conditions = ["l.organization_id = :org_id"]
        params: dict = {"org_id": org_id}

        for field, spec in filter_criteria.items():
            col_info = self.FILTERABLE_FIELDS.get(field)
            if not col_info:
                continue
            col, col_type = col_info

            if isinstance(spec, dict):
                if "gt" in spec:
                    conditions.append(f"{col} > :f_{field}_gt")
                    params[f"f_{field}_gt"] = spec["gt"]
                if "gte" in spec:
                    conditions.append(f"{col} >= :f_{field}_gte")
                    params[f"f_{field}_gte"] = spec["gte"]
                if "lt" in spec:
                    conditions.append(f"{col} < :f_{field}_lt")
                    params[f"f_{field}_lt"] = spec["lt"]
                if "lte" in spec:
                    conditions.append(f"{col} <= :f_{field}_lte")
                    params[f"f_{field}_lte"] = spec["lte"]
                if "eq" in spec:
                    conditions.append(f"{col} = :f_{field}_eq")
                    params[f"f_{field}_eq"] = spec["eq"]
                if "in" in spec:
                    values = spec["in"]
                    placeholders = ", ".join(f":f_{field}_in_{i}" for i in range(len(values)))
                    conditions.append(f"UPPER({col}) IN ({placeholders})")
                    for i, v in enumerate(values):
                        params[f"f_{field}_in_{i}"] = v.upper() if isinstance(v, str) else v
            else:
                conditions.append(f"UPPER({col}) = UPPER(:f_{field}")
                params[f"f_{field}"] = spec

        where = " AND ".join(conditions)

        sql = (
            f"SELECT l.id as loan_id, l.lead_id, l.borrower_name, "
            f"l.rate, l.loan_amount, l.stage, "
            f"ld.phone, ld.email, ld.name as lead_name "
            f"FROM loans l "
            f"LEFT JOIN leads ld ON l.lead_id = ld.id "
            f"WHERE {where} "
            f"AND ld.phone IS NOT NULL AND ld.phone != '' "
            f"ORDER BY l.updated_at DESC"
        )
        return sql, params

    def preview(self, filter_criteria: dict, org_id: str) -> List[Dict]:
        sql, params = self.build_query(filter_criteria, org_id)
        db = SessionLocal()
        try:
            rows = db.execute(text(sql), params).fetchall()
            return [dict(r._mapping) for r in rows]
        finally:
            db.close()


class BatchSMSSender:
    """Send campaign SMS messages in batches via Telnyx."""

    def __init__(self):
        from aria.tools.communication_tools import CommunicationTools
        self.comms = CommunicationTools()

    async def send_batch(
        self,
        recipients: List[Dict],
        message_template: str,
        lo: Dict,
        org_id: str,
        campaign_id: int,
        available_slots: List[str] = None,
    ) -> List[Dict]:
        """Send SMS to a list of recipients with personalization.

        Returns list of send results.
        """
        results = []

        for recipient in recipients:
            message = self._personalize(
                message_template,
                recipient=recipient,
                lo=lo,
                available_slots=available_slots,
            )

            try:
                from services.sms_compliance import check_sms_consent
                can_send, reason = await asyncio.to_thread(
                    check_sms_consent,
                    recipient["phone"],
                    organization_id=org_id,
                )
                if not can_send:
                    results.append({
                        "phone": recipient["phone"],
                        "status": "blocked",
                        "reason": reason,
                    })
                    continue

                send_result = await self.comms.send_sms(
                    to_phone=recipient["phone"],
                    from_user=lo,
                    message=message,
                    org_id=org_id,
                )
                results.append({
                    "phone": recipient["phone"],
                    "status": "sent",
                    "message_id": send_result.get("message_id"),
                    "sent_at": send_result.get("sent_at"),
                })
            except Exception as e:
                logger.error("Campaign SMS to %s failed: %s", recipient.get("phone", "?"), e)
                results.append({
                    "phone": recipient["phone"],
                    "status": "failed",
                    "error": str(e),
                })

            # Rate limit: ~1 message per 100ms
            await asyncio.sleep(0.1)

        return results

    def _personalize(
        self,
        template: str,
        recipient: Dict,
        lo: Dict,
        available_slots: List[str] = None,
    ) -> str:
        msg = template
        msg = msg.replace("[first_name]", recipient.get("first_name") or recipient.get("lead_name", "").split()[0] if recipient.get("lead_name") else "there")
        msg = msg.replace("[lo_name]", lo.get("full_name", "your loan officer"))

        if available_slots:
            for i, slot in enumerate(available_slots[:3], 1):
                msg = msg.replace(f"[slot_{i}]", slot)

        return msg
```

- [ ] **Step 2: Verify it loads**

Run: `cd /Users/timothyloss/my-project/mortgage-crm/backend && .venv/bin/python3 -c "from aria.tools.campaign_tools import CampaignFilterBuilder; print('Campaign tools loaded')"`

Expected: `Campaign tools loaded`

- [ ] **Step 3: Commit**

```bash
git add backend/aria/tools/campaign_tools.py
git commit -m "feat(aria): add campaign filter builder and batch SMS sender"
```

---

### Task 9: Campaign Engine — Multi-Step State Machine

**Files:**
- Create: `backend/aria/campaigns/campaign_engine.py`
- Create: `backend/aria/campaigns/__init__.py`

- [ ] **Step 1: Create the campaigns package**

Run: `mkdir -p /Users/timothyloss/my-project/mortgage-crm/backend/aria/campaigns && touch /Users/timothyloss/my-project/mortgage-crm/backend/aria/campaigns/__init__.py`

- [ ] **Step 2: Write the campaign engine**

Create `backend/aria/campaigns/campaign_engine.py`:

```python
"""
Campaign Engine — orchestrates the multi-step campaign workflow.

Steps: parse_filter → preview_audience → compose_message → confirm → execute → track
"""

import json
import logging
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage

from aria.tools.campaign_tools import CampaignFilterBuilder, BatchSMSSender

logger = logging.getLogger(__name__)


class CampaignStep(str, Enum):
    PARSE_FILTER = "parse_filter"
    PREVIEW_AUDIENCE = "preview_audience"
    COMPOSE_MESSAGE = "compose_message"
    CONFIRM = "confirm"
    EXECUTING = "executing"
    ACTIVE = "active"
    COMPLETED = "completed"


llm = ChatAnthropic(
    model="claude-sonnet-4-6",
    temperature=0.3,
    max_tokens=512,
)


class CampaignEngine:
    def __init__(self):
        self.filter_builder = CampaignFilterBuilder()
        self.batch_sender = BatchSMSSender()

    async def parse_filter(
        self, user_message: str, org_id: str
    ) -> Dict[str, Any]:
        """Parse a natural-language campaign request into structured filter criteria."""
        prompt = f"""Parse this campaign request into a structured filter.

User said: "{user_message}"

Available filter fields and operators:
- rate: {{gt, gte, lt, lte, eq}} (interest rate as decimal, e.g. 6.0)
- loan_amount: {{gt, gte, lt, lte, eq}}
- stage: {{in: [list], eq: "value"}} (stages: FUNDED, CLOSING, CLEAR_TO_CLOSE, etc.)
- loan_type: {{eq: "value"}} (Conventional, FHA, VA, USDA)
- closing_date: {{gt, lt}} (ISO date)

Respond ONLY with JSON:
{{
  "filter_criteria": {{...}},
  "description": "human-readable summary of the filter"
}}"""

        response = await llm.ainvoke([
            SystemMessage(content="You parse campaign criteria into structured filters. JSON only."),
            HumanMessage(content=prompt),
        ])

        try:
            parsed = json.loads(response.content.strip())
        except json.JSONDecodeError:
            return {"filter_criteria": {}, "description": "Could not parse filter"}

        filter_criteria = parsed.get("filter_criteria", {})
        recipients = self.filter_builder.preview(filter_criteria, org_id)

        return {
            "step": CampaignStep.PREVIEW_AUDIENCE.value,
            "filter_criteria": filter_criteria,
            "description": parsed.get("description", ""),
            "recipient_count": len(recipients),
            "preview": recipients[:5],
        }

    async def compose_message(
        self, intent: str, lo_name: str, include_slots: bool = True
    ) -> str:
        """Draft an SMS message based on the campaign intent."""
        prompt = f"""Draft a brief, professional SMS for a mortgage campaign.

Campaign intent: {intent}
Sender: {lo_name}
Include calendar slots: {include_slots}

Use these placeholders:
- [first_name] — recipient's first name
- [lo_name] — loan officer's name
{"- [slot_1], [slot_2], [slot_3] — available meeting times" if include_slots else ""}

Keep it under 300 characters. End with a clear call to action.
Reply with the message text only, no JSON or explanation."""

        response = await llm.ainvoke([
            SystemMessage(content="You draft professional SMS messages for mortgage outreach."),
            HumanMessage(content=prompt),
        ])

        return response.content.strip().strip('"')

    async def execute_campaign(
        self,
        campaign_id: int,
        filter_criteria: dict,
        message_template: str,
        org_id: str,
        user_id: str,
        available_slots: List[str] = None,
    ) -> Dict[str, Any]:
        """Execute the campaign: filter, send, track."""
        from aria.tools.crm_tools import CRMTools

        crm = CRMTools()
        lo = await crm.get_user(user_id)

        recipients = self.filter_builder.preview(filter_criteria, org_id)

        results = await self.batch_sender.send_batch(
            recipients=recipients,
            message_template=message_template,
            lo=lo,
            org_id=org_id,
            campaign_id=campaign_id,
            available_slots=available_slots,
        )

        # Persist to aria_campaign_recipients
        try:
            from db import SessionLocal
            from database.models.aria_campaign import AriaCampaign, AriaCampaignRecipient

            db = SessionLocal()
            try:
                campaign = db.query(AriaCampaign).filter(AriaCampaign.id == campaign_id).first()
                if campaign:
                    sent = 0
                    for i, r in enumerate(results):
                        recip = AriaCampaignRecipient(
                            campaign_id=campaign_id,
                            lead_id=recipients[i].get("lead_id") if i < len(recipients) else None,
                            loan_id=recipients[i].get("loan_id") if i < len(recipients) else None,
                            phone=r["phone"],
                            first_name=recipients[i].get("lead_name", "").split()[0] if i < len(recipients) and recipients[i].get("lead_name") else None,
                            status=r["status"],
                            message_id=r.get("message_id"),
                            sent_at=datetime.now(timezone.utc) if r["status"] == "sent" else None,
                        )
                        db.add(recip)
                        if r["status"] == "sent":
                            sent += 1

                    campaign.status = "active"
                    campaign.recipient_count = len(recipients)
                    campaign.sent_count = sent
                    db.commit()
            except Exception as e:
                db.rollback()
                logger.error("Failed to persist campaign results: %s", e)
            finally:
                db.close()
        except ImportError:
            logger.debug("DB models not available — campaign results not persisted")

        sent_count = sum(1 for r in results if r["status"] == "sent")
        blocked_count = sum(1 for r in results if r["status"] == "blocked")
        failed_count = sum(1 for r in results if r["status"] == "failed")

        return {
            "campaign_id": campaign_id,
            "total_recipients": len(recipients),
            "sent": sent_count,
            "blocked": blocked_count,
            "failed": failed_count,
            "status": "active",
        }

    async def get_campaign_status(self, campaign_id: int) -> Dict[str, Any]:
        """Get current campaign status with reply/booking counts."""
        from db import SessionLocal
        from database.models.aria_campaign import AriaCampaign

        db = SessionLocal()
        try:
            campaign = db.query(AriaCampaign).filter(AriaCampaign.id == campaign_id).first()
            if not campaign:
                return {"error": "Campaign not found"}
            return {
                "campaign_id": campaign.id,
                "name": campaign.name,
                "status": campaign.status,
                "recipient_count": campaign.recipient_count,
                "sent_count": campaign.sent_count,
                "replied_count": campaign.replied_count,
                "booked_count": campaign.booked_count,
                "declined_count": campaign.declined_count,
            }
        finally:
            db.close()
```

- [ ] **Step 3: Verify it loads**

Run: `cd /Users/timothyloss/my-project/mortgage-crm/backend && .venv/bin/python3 -c "from aria.campaigns.campaign_engine import CampaignEngine, CampaignStep; print(CampaignStep.PARSE_FILTER.value)"`

Expected: `parse_filter`

- [ ] **Step 4: Commit**

```bash
git add backend/aria/campaigns/__init__.py backend/aria/campaigns/campaign_engine.py
git commit -m "feat(aria): add campaign engine with multi-step state machine"
```

---

### Task 10: Campaign Reply Handler

**Files:**
- Create: `backend/aria/campaigns/reply_handler.py`

- [ ] **Step 1: Write the reply handler**

Create `backend/aria/campaigns/reply_handler.py`:

```python
"""
Campaign Reply Handler — routes inbound SMS to campaign conversations.

When a borrower replies to a campaign SMS thread, this handler:
1. Matches the inbound phone to a campaign recipient via message_id
2. Uses Claude Haiku to interpret the reply (schedule, decline, question)
3. Books via AppointmentService if scheduling
4. Updates recipient status
"""

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage

logger = logging.getLogger(__name__)

llm_haiku = ChatAnthropic(
    model="claude-haiku-4-5-20251001",
    temperature=0,
    max_tokens=256,
)


class CampaignReplyHandler:

    async def handle_inbound(
        self, from_phone: str, message_body: str, org_id: str
    ) -> Optional[Dict[str, Any]]:
        """Process an inbound SMS that may be a campaign reply.

        Returns a response dict if this is a campaign message, None otherwise.
        """
        recipient = self._find_campaign_recipient(from_phone)
        if not recipient:
            return None

        intent = await self._classify_reply(message_body)

        if intent["action"] == "schedule":
            return await self._handle_schedule(recipient, intent, org_id)
        elif intent["action"] == "decline":
            return await self._handle_decline(recipient)
        elif intent["action"] == "reschedule":
            return await self._handle_reschedule(recipient, org_id)
        else:
            return await self._handle_clarify(recipient)

    def _find_campaign_recipient(self, phone: str) -> Optional[Dict]:
        """Find a campaign recipient by phone number."""
        from db import SessionLocal
        from sqlalchemy import text

        db = SessionLocal()
        try:
            row = db.execute(text(
                "SELECT cr.id, cr.campaign_id, cr.lead_id, cr.loan_id, "
                "cr.phone, cr.first_name, cr.status, cr.appointment_id, "
                "ac.created_by_user_id, ac.organization_id "
                "FROM aria_campaign_recipients cr "
                "JOIN aria_campaigns ac ON cr.campaign_id = ac.id "
                "WHERE cr.phone = :phone AND cr.status IN ('sent', 'delivered', 'replied') "
                "ORDER BY cr.sent_at DESC LIMIT 1"
            ), {"phone": phone}).fetchone()

            if not row:
                return None

            return {
                "id": row[0], "campaign_id": row[1], "lead_id": row[2],
                "loan_id": row[3], "phone": row[4], "first_name": row[5],
                "status": row[6], "appointment_id": row[7],
                "lo_user_id": row[8], "organization_id": row[9],
            }
        finally:
            db.close()

    async def _classify_reply(self, message: str) -> Dict[str, Any]:
        """Use Claude Haiku to classify the borrower's reply."""
        response = await llm_haiku.ainvoke([
            SystemMessage(content=(
                "Classify this SMS reply to a mortgage outreach. "
                "Respond ONLY with JSON: "
                '{"action": "schedule|decline|reschedule|clarify", '
                '"datetime_mentioned": "ISO datetime or null", '
                '"raw_time": "the time phrase they used or null"}'
            )),
            HumanMessage(content=message),
        ])

        try:
            return json.loads(response.content.strip())
        except json.JSONDecodeError:
            return {"action": "clarify", "datetime_mentioned": None}

    async def _handle_schedule(
        self, recipient: Dict, intent: Dict, org_id: str
    ) -> Dict:
        """Book the appointment and send confirmation."""
        from services.appointment.service import AppointmentService
        from db import SessionLocal
        from dateutil import parser as dtparser

        dt_str = intent.get("datetime_mentioned")
        if not dt_str:
            return {
                "action": "ask_time",
                "phone": recipient["phone"],
                "response": f"Great, {recipient['first_name'] or 'there'}! What day and time works best for you?",
            }

        scheduled_start = dtparser.parse(dt_str)

        db = SessionLocal()
        try:
            svc = AppointmentService(
                db=db, organization_id=recipient["organization_id"]
            )
            result = await svc.create_appointment(
                data={
                    "title": f"Call — {recipient['first_name'] or 'Borrower'}",
                    "scheduled_start": scheduled_start.isoformat(),
                    "duration_minutes": 30,
                    "assigned_user_id": recipient["lo_user_id"],
                    "attendee_phone": recipient["phone"],
                    "attendee_name": recipient["first_name"] or "",
                    "meeting_type": "consultation",
                    "meeting_mode": "phone",
                },
                source="aria_campaign",
                requester_user_id=recipient["lo_user_id"],
            )
            db.commit()

            appointment_id = (
                getattr(result, "appointment_id", None)
                or (result.get("appointment_id") if isinstance(result, dict) else None)
            )

            self._update_recipient_status(
                recipient["id"], "booked", appointment_id=appointment_id
            )
            self._increment_campaign_counter(recipient["campaign_id"], "booked_count")

            return {
                "action": "booked",
                "phone": recipient["phone"],
                "appointment_id": appointment_id,
                "response": (
                    f"You're set for {scheduled_start.strftime('%A at %I:%M %p')}! "
                    f"Calendar invite on the way."
                ),
            }
        except Exception as e:
            db.rollback()
            logger.error("Campaign booking failed: %s", e)
            return {
                "action": "booking_failed",
                "phone": recipient["phone"],
                "response": "I had trouble booking that time. Could you try a different time?",
            }
        finally:
            db.close()

    async def _handle_decline(self, recipient: Dict) -> Dict:
        self._update_recipient_status(recipient["id"], "declined")
        self._increment_campaign_counter(recipient["campaign_id"], "declined_count")
        return {
            "action": "declined",
            "phone": recipient["phone"],
            "response": "No problem at all. Take care!",
        }

    async def _handle_reschedule(self, recipient: Dict, org_id: str) -> Dict:
        """Propose new time slots."""
        from aria.tools.communication_tools import CommunicationTools
        comms = CommunicationTools()

        schedule = await comms.get_schedule(
            lo_id=recipient["lo_user_id"],
            org_id=str(recipient["organization_id"]),
        )
        slots = schedule.get("available_slots", [])[:3]

        if not slots:
            return {
                "action": "no_slots",
                "phone": recipient["phone"],
                "response": "Let me check with the team and get back to you with some times.",
            }

        slot_text = ", ".join(
            f"{s.get('day', '')} {s.get('start', '')}" for s in slots
        )
        return {
            "action": "propose_slots",
            "phone": recipient["phone"],
            "response": f"How about {slot_text}?",
        }

    async def _handle_clarify(self, recipient: Dict) -> Dict:
        return {
            "action": "clarify",
            "phone": recipient["phone"],
            "response": (
                "Would you like to pick a time for a quick call, "
                "or would you prefer we reach out another way?"
            ),
        }

    def _update_recipient_status(
        self, recipient_id: int, status: str, appointment_id: int = None
    ):
        from db import SessionLocal
        from sqlalchemy import text

        db = SessionLocal()
        try:
            params: dict = {"id": recipient_id, "status": status}
            extra = ""
            if status == "booked" and appointment_id:
                extra = ", appointment_id = :apt_id, booked_at = NOW()"
                params["apt_id"] = appointment_id
            elif status == "replied":
                extra = ", replied_at = NOW()"

            db.execute(text(
                f"UPDATE aria_campaign_recipients SET status = :status{extra} WHERE id = :id"
            ), params)
            db.commit()
        except Exception as e:
            db.rollback()
            logger.error("Failed to update recipient status: %s", e)
        finally:
            db.close()

    def _increment_campaign_counter(self, campaign_id: int, counter: str):
        from db import SessionLocal
        from sqlalchemy import text

        db = SessionLocal()
        try:
            db.execute(text(
                f"UPDATE aria_campaigns SET {counter} = {counter} + 1 WHERE id = :id"
            ), {"id": campaign_id})
            db.commit()
        except Exception as e:
            db.rollback()
            logger.error("Failed to increment campaign counter: %s", e)
        finally:
            db.close()
```

- [ ] **Step 2: Verify it loads**

Run: `cd /Users/timothyloss/my-project/mortgage-crm/backend && .venv/bin/python3 -c "from aria.campaigns.reply_handler import CampaignReplyHandler; print('Reply handler loaded')"`

Expected: `Reply handler loaded`

- [ ] **Step 3: Commit**

```bash
git add backend/aria/campaigns/reply_handler.py
git commit -m "feat(aria): add campaign reply handler with scheduling and decline flows"
```

---

### Task 11: Campaign Reminder Service

**Files:**
- Create: `backend/aria/campaigns/reminder_service.py`

- [ ] **Step 1: Write the reminder service**

Create `backend/aria/campaigns/reminder_service.py`:

```python
"""
Graduated reminder cadence for campaign-booked appointments.

- Day before: "Reminder: you have a call with [LO] tomorrow at [time]"
- 1 hour before: "Your call with [LO] is in 1 hour"
- No-show (15 min after missed): "We missed you — want to reschedule?"
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import List, Dict

from sqlalchemy import text
from db import SessionLocal

logger = logging.getLogger(__name__)


class CampaignReminderService:

    async def check_and_send_reminders(self) -> Dict[str, int]:
        """Check all campaign appointments and send due reminders.

        Call this on a schedule (e.g., every 15 minutes via cron/task runner).
        """
        from aria.tools.communication_tools import CommunicationTools
        comms = CommunicationTools()

        now = datetime.now(timezone.utc)
        counts = {"day_before": 0, "hour_before": 0, "no_show": 0}

        # Day-before reminders
        day_before_recipients = self._get_due_reminders("day_before", now)
        for r in day_before_recipients:
            msg = (
                f"Reminder: you have a call with {r['lo_name']} "
                f"tomorrow at {r['appointment_time']}."
            )
            try:
                await comms.send_sms(
                    to_phone=r["phone"], from_user={"id": r["lo_user_id"]},
                    message=msg, org_id=str(r["organization_id"]),
                )
                self._mark_reminder_sent(r["recipient_id"], "reminder_day_before_sent")
                counts["day_before"] += 1
            except Exception as e:
                logger.error("Day-before reminder failed for %s: %s", r["phone"], e)

        # Hour-before reminders
        hour_before_recipients = self._get_due_reminders("hour_before", now)
        for r in hour_before_recipients:
            msg = f"Your call with {r['lo_name']} is in 1 hour."
            try:
                await comms.send_sms(
                    to_phone=r["phone"], from_user={"id": r["lo_user_id"]},
                    message=msg, org_id=str(r["organization_id"]),
                )
                self._mark_reminder_sent(r["recipient_id"], "reminder_hour_before_sent")
                counts["hour_before"] += 1
            except Exception as e:
                logger.error("Hour-before reminder failed for %s: %s", r["phone"], e)

        # No-show follow-ups
        no_show_recipients = self._get_due_reminders("no_show", now)
        for r in no_show_recipients:
            msg = (
                f"We missed you today — want to reschedule? "
                f"Reply with a time that works."
            )
            try:
                await comms.send_sms(
                    to_phone=r["phone"], from_user={"id": r["lo_user_id"]},
                    message=msg, org_id=str(r["organization_id"]),
                )
                self._mark_reminder_sent(r["recipient_id"], "no_show_followup_sent")
                self._update_recipient_status(r["recipient_id"], "no_show")
                counts["no_show"] += 1
            except Exception as e:
                logger.error("No-show follow-up failed for %s: %s", r["phone"], e)

        return counts

    def _get_due_reminders(self, reminder_type: str, now: datetime) -> List[Dict]:
        db = SessionLocal()
        try:
            if reminder_type == "day_before":
                window_start = now + timedelta(hours=23)
                window_end = now + timedelta(hours=25)
                flag_col = "reminder_day_before_sent"
            elif reminder_type == "hour_before":
                window_start = now + timedelta(minutes=55)
                window_end = now + timedelta(minutes=65)
                flag_col = "reminder_hour_before_sent"
            elif reminder_type == "no_show":
                window_start = now - timedelta(minutes=30)
                window_end = now - timedelta(minutes=15)
                flag_col = "no_show_followup_sent"
            else:
                return []

            rows = db.execute(text(f"""
                SELECT cr.id, cr.phone, cr.first_name,
                       sa.scheduled_start, sa.assigned_user_id,
                       ac.organization_id,
                       u.first_name || ' ' || u.last_name as lo_name
                FROM aria_campaign_recipients cr
                JOIN scheduler_appointments sa ON cr.appointment_id = sa.id
                JOIN aria_campaigns ac ON cr.campaign_id = ac.id
                LEFT JOIN users u ON sa.assigned_user_id = u.id
                WHERE cr.status = 'booked'
                AND cr.{flag_col} = false
                AND sa.scheduled_start BETWEEN :ws AND :we
                AND sa.status = 'booked'
            """), {"ws": window_start, "we": window_end}).fetchall()

            return [
                {
                    "recipient_id": r[0],
                    "phone": r[1],
                    "first_name": r[2],
                    "appointment_time": r[3].strftime("%I:%M %p") if r[3] else "",
                    "lo_user_id": r[4],
                    "organization_id": r[5],
                    "lo_name": r[6] or "your loan officer",
                }
                for r in rows
            ]
        except Exception as e:
            logger.error("Failed to fetch %s reminders: %s", reminder_type, e)
            return []
        finally:
            db.close()

    def _mark_reminder_sent(self, recipient_id: int, flag: str):
        db = SessionLocal()
        try:
            db.execute(text(
                f"UPDATE aria_campaign_recipients SET {flag} = true WHERE id = :id"
            ), {"id": recipient_id})
            db.commit()
        except Exception as e:
            db.rollback()
            logger.error("Failed to mark reminder sent: %s", e)
        finally:
            db.close()

    def _update_recipient_status(self, recipient_id: int, status: str):
        db = SessionLocal()
        try:
            db.execute(text(
                "UPDATE aria_campaign_recipients SET status = :status WHERE id = :id"
            ), {"id": recipient_id, "status": status})
            db.commit()
        except Exception as e:
            db.rollback()
            logger.error("Failed to update recipient status: %s", e)
        finally:
            db.close()
```

- [ ] **Step 2: Verify it loads**

Run: `cd /Users/timothyloss/my-project/mortgage-crm/backend && .venv/bin/python3 -c "from aria.campaigns.reminder_service import CampaignReminderService; print('Reminder service loaded')"`

Expected: `Reminder service loaded`

- [ ] **Step 3: Commit**

```bash
git add backend/aria/campaigns/reminder_service.py
git commit -m "feat(aria): add graduated reminder cadence for campaign appointments"
```

---

### Task 12: Add `send_batch_sms` and `send_reminder` to CommunicationTools

**Files:**
- Modify: `backend/aria/tools/communication_tools.py`

- [ ] **Step 1: Add the two new methods**

In `backend/aria/tools/communication_tools.py`, add these methods to the `CommunicationTools` class (after `get_schedule`):

```python
    async def send_batch_sms(
        self, recipients: list, from_user: Dict,
        message_template: str, org_id: str,
    ) -> list:
        """Send SMS to multiple recipients. Returns list of results."""
        results = []
        for recipient in recipients:
            try:
                result = await self.send_sms(
                    to_phone=recipient["phone"],
                    from_user=from_user,
                    message=message_template.replace(
                        "[first_name]",
                        recipient.get("first_name", "there"),
                    ),
                    org_id=org_id,
                )
                results.append({**result, "phone": recipient["phone"]})
            except Exception as e:
                results.append({
                    "phone": recipient["phone"],
                    "status": "failed",
                    "error": str(e),
                })
        return results

    async def send_reminder(
        self, to_phone: str, from_user: Dict,
        message: str, org_id: str,
    ) -> Dict:
        """Send a reminder SMS (thin wrapper around send_sms for clarity)."""
        return await self.send_sms(
            to_phone=to_phone,
            from_user=from_user,
            message=message,
            org_id=org_id,
        )
```

- [ ] **Step 2: Verify it loads**

Run: `cd /Users/timothyloss/my-project/mortgage-crm/backend && .venv/bin/python3 -c "from aria.tools.communication_tools import CommunicationTools; c = CommunicationTools(); print(hasattr(c, 'send_batch_sms') and hasattr(c, 'send_reminder'))"`

Expected: `True`

- [ ] **Step 3: Commit**

```bash
git add backend/aria/tools/communication_tools.py
git commit -m "feat(aria): add send_batch_sms and send_reminder to CommunicationTools"
```

---

### Task 13: Update LO Assistant Prompt with New Capabilities

**Files:**
- Modify: `backend/agents/aria_prompts.py`

- [ ] **Step 1: Update the LO_ASSISTANT_PROMPT**

In `backend/agents/aria_prompts.py`, update the `LO_ASSISTANT_PROMPT` capabilities section. Replace the existing "You have full access to the CRM system" section with:

```python
You have full access to the CRM system and can answer ANY question about your data:
- "How's my pipeline?" → pipeline summary with counts and volume by stage
- "How many loans did I close last month?" → production stats
- "Who has rates above 6%?" → rate analysis across pipeline
- "What tasks are due today?" → task summary
- "Show me leads from Zillow last week" → filtered lead search
- "What docs are missing on the Smith file?" → document status
- "Top producing realtors" → referral partner stats
- "How many applications came in this week?" → POS application stats
- Any question about loans, leads, tasks, production, commissions, referrals, or pipeline

POS application visibility:
- "Who hasn't finished their application?" → list of incomplete borrower applications
- Shows: borrower name, current step, completion %, start date, last activity
- 1-5 apps: full voice summary. 6+: top 3 + offer to email the full list
- Proactively offers to text borrowers a reminder to finish

Pre-approval letters — review-edit loop:
- "Send a pre-approval for John Smith" → pulls all data from CRM, presents for review
- Shows: name, purchase price, loan amount, loan type, property address
- You can edit any field: "make it $500K" → updates and re-presents
- Property address: use what's in CRM, change it, or set to "TBD" for buyers still shopping
- Auto-checks for associated realtor on the file
- If no realtor found: "Who should I send this to?"

Campaign mode — mass text with calendar coordination:
- "Text everyone with a rate above 6%" → builds filter, shows count, drafts message
- You preview and approve before anything sends
- Recipients can reply to schedule calls — Aria handles two-way SMS
- Graduated reminders: day-before, hour-before, no-show follow-up
- "How's the rate outreach going?" → campaign dashboard
```

- [ ] **Step 2: Verify prompt loads**

Run: `cd /Users/timothyloss/my-project/mortgage-crm/backend && .venv/bin/python3 -c "from agents.aria_prompts import get_prompt; p = get_prompt('lo_assistant'); print('campaign' in p.lower() and 'pipeline' in p.lower())"`

Expected: `True`

- [ ] **Step 3: Commit**

```bash
git add backend/agents/aria_prompts.py
git commit -m "feat(aria): update LO assistant prompt with query, POS, campaign capabilities"
```

---

### Task 14: Wire Inbound SMS to Campaign Reply Handler

**Files:**
- Modify: `backend/integrations/sms_webhook_handler.py`

- [ ] **Step 1: Add campaign reply routing to the inbound SMS path**

In `backend/integrations/sms_webhook_handler.py`, find the function that handles inbound SMS events (the function that processes `message.received` events). Add campaign reply handling early in the flow:

After signature verification and before normal inbound processing, add:

```python
    # Check if this is a campaign reply
    try:
        from aria.campaigns.reply_handler import CampaignReplyHandler
        handler = CampaignReplyHandler()
        import asyncio
        campaign_result = asyncio.run(handler.handle_inbound(
            from_phone=from_phone,
            message_body=message_body,
            org_id=str(organization_id),
        ))
        if campaign_result:
            # This is a campaign reply — send auto-response and return
            if campaign_result.get("response"):
                from aria.tools.communication_tools import CommunicationTools
                comms = CommunicationTools()
                asyncio.run(comms.send_sms(
                    to_phone=from_phone,
                    from_user={"id": campaign_result.get("lo_user_id", "")},
                    message=campaign_result["response"],
                    org_id=str(organization_id),
                ))
            logger.info("Campaign reply handled: %s -> %s", from_phone, campaign_result.get("action"))
            return campaign_result
    except ImportError:
        pass
    except Exception as e:
        logger.warning("Campaign reply check failed (non-blocking): %s", e)
```

Note: The exact integration point depends on the webhook handler's structure. Look for where `message.received` events are processed and `from_phone`/`message_body` are extracted. Add this block before the existing inbound message handling logic.

- [ ] **Step 2: Verify it doesn't break existing flow**

Run: `cd /Users/timothyloss/my-project/mortgage-crm/backend && .venv/bin/python3 -c "from integrations.sms_webhook_handler import verify_telnyx_signature; print('SMS webhook handler loads')"`

Expected: `SMS webhook handler loads`

- [ ] **Step 3: Commit**

```bash
git add backend/integrations/sms_webhook_handler.py
git commit -m "feat(aria): route inbound SMS through campaign reply handler"
```

---

### Task 15: Final Integration Verification

- [ ] **Step 1: Verify all new modules load without import errors**

Run:
```bash
cd /Users/timothyloss/my-project/mortgage-crm/backend && .venv/bin/python3 -c "
# Mode router
from aria.core.mode_router import classify_mode, AriaMode
print('1. Mode router:', AriaMode.QUERY.value)

# Query tools
from aria.tools.crm_query_tools import QUERY_TOOL_DEFINITIONS, TOOL_DISPATCH
print(f'2. Query tools: {len(QUERY_TOOL_DEFINITIONS)} definitions')

# Campaign tools
from aria.tools.campaign_tools import CampaignFilterBuilder, BatchSMSSender
print('3. Campaign tools loaded')

# Campaign engine
from aria.campaigns.campaign_engine import CampaignEngine, CampaignStep
print('4. Campaign engine:', CampaignStep.PARSE_FILTER.value)

# Reply handler
from aria.campaigns.reply_handler import CampaignReplyHandler
print('5. Reply handler loaded')

# Reminder service
from aria.campaigns.reminder_service import CampaignReminderService
print('6. Reminder service loaded')

# Campaign models
from database.models.aria_campaign import AriaCampaign, AriaCampaignRecipient
print('7. Campaign models loaded')

# Updated conversation engine
from aria.core.conversation_engine import build_aria_graph
print('8. Conversation engine graph builds')

# Updated intent registry
from aria.core.intent_registry import IntentRegistry
r = IntentRegistry.get()
print(f'9. Intent registry: {len(r.intents)} intents, check_pos={r.get_intent(\"check_pos_applications\") is not None}')

# Updated task executor
from aria.tasks.task_executor import TaskExecutor
t = TaskExecutor()
print(f'10. Task executor: {len(t._handlers)} handlers')

# Updated prompts
from agents.aria_prompts import get_prompt
p = get_prompt('lo_assistant')
print(f'11. LO prompt: {len(p)} chars, has campaign={\"campaign\" in p.lower()}')

print('\\nAll checks passed')
"
```

Expected: All 11 checks pass

- [ ] **Step 2: Run migration verification**

Run: `cd /Users/timothyloss/my-project/mortgage-crm/backend && .venv/bin/python3 -c "from database.models.aria_campaign import AriaCampaign; print('Table name:', AriaCampaign.__tablename__)"`

Expected: `Table name: aria_campaigns`
