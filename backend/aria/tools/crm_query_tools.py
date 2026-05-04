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
        conditions.append(f"ld.updated_at < NOW() - INTERVAL '{params['inactive_days']} days'")
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
