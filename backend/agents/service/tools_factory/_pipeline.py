"""Pipeline & daily-priorities tools (extracted verbatim)."""

from __future__ import annotations

import logging
from typing import Any, Callable, Dict

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


def build_pipeline_tools(db: Session, current_user: Any, ctx: Dict[str, Any]) -> Dict[str, Callable]:
    tools: Dict[str, Callable] = {}

    # Unpack context to match the original closure variable names
    org_id = ctx["org_id"]
    _user_role = ctx["_user_role"]  # noqa: F841 — kept for parity
    _has_org_wide_access = ctx["_has_org_wide_access"]

    # ============ Pipeline Tools ============

    async def execute_get_pipeline(args):
        """Get pipeline summary with leads and loans by stage."""
        include_details = args.get("include_details", True)

        try:
            # Scope: org-wide for admins/managers, user-only for others
            if _has_org_wide_access and org_id:
                lead_filter = "organization_id = :org_id"
                loan_filter = "organization_id = :org_id"
                params = {"org_id": org_id}
            elif _has_org_wide_access and not org_id:
                # Platform admin with no org — show all
                lead_filter = "1=1"
                loan_filter = "1=1"
                params = {}
            else:
                lead_filter = "owner_id = :user_id AND (:org_id IS NULL OR organization_id = :org_id)"
                loan_filter = "loan_officer_id = :user_id AND (:org_id IS NULL OR organization_id = :org_id)"
                params = {"user_id": current_user.id, "org_id": org_id}

            # Get leads using raw SQL to avoid import issues (include owner for org-wide views)
            lead_where = lead_filter.replace('organization_id', 'ld.organization_id').replace('owner_id', 'ld.owner_id')
            lead_sql = (
                "SELECT ld.id, ld.name, ld.email, ld.phone, ld.stage,"
                " CONCAT(u.first_name, ' ', u.last_name) as owner_name"
                " FROM leads ld"
                " LEFT JOIN users u ON u.id = ld.owner_id"
                " WHERE " + lead_where
            )
            lead_rows = db.execute(
                text(lead_sql),
                params
            ).fetchall()

            # Get loans using raw SQL (include LO name for org-wide views)
            loan_where = loan_filter.replace('organization_id', 'l.organization_id').replace('loan_officer_id', 'l.loan_officer_id')
            loan_sql = (
                "SELECT l.id, l.loan_number, l.borrower_name, l.stage, l.amount,"
                " l.processor, l.underwriter, l.days_in_stage, l.closing_date,"
                " CONCAT(u.first_name, ' ', u.last_name) as lo_name"
                " FROM loans l"
                " LEFT JOIN users u ON u.id = l.loan_officer_id"
                " WHERE " + loan_where
            )
            loan_rows = db.execute(
                text(loan_sql),
                params
            ).fetchall()

            # Organize leads by stage
            lead_stages = {}
            for lead in lead_rows:
                stage = str(lead.stage) if lead.stage else "New"
                if stage not in lead_stages:
                    lead_stages[stage] = {"count": 0, "items": []}
                lead_stages[stage]["count"] += 1
                if include_details:
                    lead_stages[stage]["items"].append({
                        "id": lead.id,
                        "name": lead.name,
                        "type": "lead"
                    })

            # Organize loans by stage
            loan_stages = {}
            for loan in loan_rows:
                stage = str(loan.stage) if loan.stage else "Unknown"
                if stage not in loan_stages:
                    loan_stages[stage] = {"count": 0, "items": []}
                loan_stages[stage]["count"] += 1
                if include_details:
                    item = {
                        "id": loan.id,
                        "name": loan.borrower_name or f"Loan #{loan.id}",
                        "amount": float(loan.amount) if loan.amount else 0,
                        "processor": loan.processor,
                        "underwriter": loan.underwriter,
                        "days_in_stage": loan.days_in_stage,
                        "closing_date": loan.closing_date.isoformat() if loan.closing_date else None,
                        "type": "loan"
                    }
                    lo_name = getattr(loan, 'lo_name', None)
                    if lo_name and _has_org_wide_access:
                        item["loan_officer"] = lo_name
                    loan_stages[stage]["items"].append(item)

            scope_label = "organization-wide" if _has_org_wide_access else "your"
            return {
                "total_leads": len(lead_rows),
                "total_loans": len(loan_rows),
                "lead_stages": lead_stages,
                "loan_stages": loan_stages,
                "scope": "organization" if _has_org_wide_access else "user",
                "summary": f"{len(lead_rows)} leads, {len(loan_rows)} active loans ({scope_label})"
            }
        except Exception as e:
            logger.error(f"Error in get_pipeline: {e}")
            db.rollback()
            return {"error": "Internal server error", "total_leads": 0, "total_loans": 0}

    tools["get_pipeline"] = execute_get_pipeline

    # ============ Analytics Tools ============

    async def execute_get_pipeline_metrics(args):
        """Get pipeline analytics and metrics."""
        try:
            # Get loan counts by stage
            stage_counts = db.execute(
                text("""SELECT stage, COUNT(*) as count, SUM(amount) as total_amount
                       FROM loans WHERE loan_officer_id = :user_id
                       AND (:org_id IS NULL OR organization_id = :org_id)
                       GROUP BY stage"""),
                {"user_id": current_user.id, "org_id": org_id}
            ).fetchall()

            # Get closing metrics (only count future closing dates)
            closing_metrics = db.execute(
                text("""SELECT
                       COUNT(*) FILTER (WHERE closing_date >= CURRENT_DATE AND closing_date <= CURRENT_DATE + INTERVAL '7 days') as closing_7_days,
                       COUNT(*) FILTER (WHERE closing_date >= CURRENT_DATE AND closing_date <= CURRENT_DATE + INTERVAL '30 days') as closing_30_days,
                       SUM(amount) FILTER (WHERE closing_date >= CURRENT_DATE AND closing_date <= CURRENT_DATE + INTERVAL '30 days') as volume_30_days
                       FROM loans WHERE loan_officer_id = :user_id AND stage::text != 'Funded'
                       AND (:org_id IS NULL OR organization_id = :org_id)"""),
                {"user_id": current_user.id, "org_id": org_id}
            ).fetchone()

            return {
                "stage_breakdown": [{
                    "stage": str(s.stage) if s.stage else "Unknown",
                    "count": s.count,
                    "total_amount": float(s.total_amount) if s.total_amount else 0
                } for s in stage_counts],
                "closing_7_days": closing_metrics.closing_7_days or 0,
                "closing_30_days": closing_metrics.closing_30_days or 0,
                "volume_30_days": float(closing_metrics.volume_30_days) if closing_metrics.volume_30_days else 0
            }
        except Exception as e:
            logger.error(f"Error in get_pipeline_metrics: {e}")
            db.rollback()
            return {"error": "Internal server error"}

    tools["get_pipeline_metrics"] = execute_get_pipeline_metrics

    # ============ Daily Priorities Tools ============

    async def execute_get_daily_priorities(args):
        """Get prioritized list of actions for today."""
        try:
            # Get overdue tasks from ai_tasks table (the active task table)
            overdue_tasks = db.execute(
                text("""SELECT t.id, t.title, t.due_date, t.priority,
                       COALESCE(t.borrower_name, ln.borrower_name, ld.name) as contact_name
                       FROM ai_tasks t
                       LEFT JOIN loans ln ON t.loan_id = ln.id
                       LEFT JOIN leads ld ON t.lead_id = ld.id
                       WHERE t.assigned_to_id = :user_id
                       AND (:org_id IS NULL OR t.organization_id = :org_id)
                       AND t.type::text != 'Completed'
                       AND t.due_date < CURRENT_DATE
                       ORDER BY
                           CASE WHEN t.priority = 'high' THEN 1
                                WHEN t.priority = 'medium' THEN 2
                                ELSE 3 END,
                           t.due_date ASC
                       LIMIT 5"""),
                {"user_id": current_user.id, "org_id": org_id}
            ).fetchall()

            # Get today's tasks
            today_tasks = db.execute(
                text("""SELECT t.id, t.title, t.due_date, t.priority,
                       COALESCE(t.borrower_name, ln.borrower_name, ld.name) as contact_name
                       FROM ai_tasks t
                       LEFT JOIN loans ln ON t.loan_id = ln.id
                       LEFT JOIN leads ld ON t.lead_id = ld.id
                       WHERE t.assigned_to_id = :user_id
                       AND (:org_id IS NULL OR t.organization_id = :org_id)
                       AND t.type::text != 'Completed'
                       AND t.due_date::date = CURRENT_DATE
                       ORDER BY
                           CASE WHEN t.priority = 'high' THEN 1
                                WHEN t.priority = 'medium' THEN 2
                                ELSE 3 END
                       LIMIT 10"""),
                {"user_id": current_user.id, "org_id": org_id}
            ).fetchall()

            # Also get tomorrow's tasks
            tomorrow_tasks = db.execute(
                text("""SELECT t.id, t.title, t.due_date, t.priority,
                       COALESCE(t.borrower_name, ln.borrower_name, ld.name) as contact_name
                       FROM ai_tasks t
                       LEFT JOIN loans ln ON t.loan_id = ln.id
                       LEFT JOIN leads ld ON t.lead_id = ld.id
                       WHERE t.assigned_to_id = :user_id
                       AND (:org_id IS NULL OR t.organization_id = :org_id)
                       AND t.type::text != 'Completed'
                       AND t.due_date::date = CURRENT_DATE + INTERVAL '1 day'
                       ORDER BY
                           CASE WHEN t.priority = 'high' THEN 1
                                WHEN t.priority = 'medium' THEN 2
                                ELSE 3 END
                       LIMIT 5"""),
                {"user_id": current_user.id, "org_id": org_id}
            ).fetchall()

            # Get loans closing soon (future only - past dates mean loan is delayed or already closed)
            closing_soon = db.execute(
                text("""SELECT id, loan_number, borrower_name, closing_date, stage, amount
                       FROM loans
                       WHERE loan_officer_id = :user_id
                       AND (:org_id IS NULL OR organization_id = :org_id)
                       AND closing_date >= CURRENT_DATE
                       AND closing_date <= CURRENT_DATE + INTERVAL '7 days'
                       AND stage::text NOT IN ('Funded')
                       ORDER BY closing_date ASC
                       LIMIT 5"""),
                {"user_id": current_user.id, "org_id": org_id}
            ).fetchall()

            # Also check for loans with PAST closing dates that aren't funded (these need attention)
            overdue_closings = db.execute(
                text("""SELECT id, loan_number, borrower_name, closing_date, stage, amount
                       FROM loans
                       WHERE loan_officer_id = :user_id
                       AND (:org_id IS NULL OR organization_id = :org_id)
                       AND closing_date < CURRENT_DATE
                       AND stage::text NOT IN ('Funded', 'Cancelled', 'Denied')
                       ORDER BY closing_date DESC
                       LIMIT 5"""),
                {"user_id": current_user.id, "org_id": org_id}
            ).fetchall()

            return {
                "overdue_tasks": [{
                    "id": t.id,
                    "title": t.title,
                    "due_date": t.due_date.isoformat() if t.due_date else None,
                    "priority": t.priority,
                    "contact_name": t.contact_name
                } for t in overdue_tasks],
                "today_tasks": [{
                    "id": t.id,
                    "title": t.title,
                    "due_date": t.due_date.isoformat() if t.due_date else None,
                    "priority": t.priority,
                    "contact_name": t.contact_name
                } for t in today_tasks],
                "tomorrow_tasks": [{
                    "id": t.id,
                    "title": t.title,
                    "due_date": t.due_date.isoformat() if t.due_date else None,
                    "priority": t.priority,
                    "contact_name": t.contact_name
                } for t in tomorrow_tasks],
                "closing_soon": [{
                    "loan_number": l.loan_number,
                    "borrower_name": l.borrower_name,
                    "closing_date": l.closing_date.isoformat() if l.closing_date else None,
                    "stage": str(l.stage) if l.stage else None,
                    "amount": float(l.amount) if l.amount else 0
                } for l in closing_soon],
                "overdue_closings": [{
                    "loan_number": l.loan_number,
                    "borrower_name": l.borrower_name,
                    "closing_date": l.closing_date.isoformat() if l.closing_date else None,
                    "stage": str(l.stage) if l.stage else None,
                    "amount": float(l.amount) if l.amount else 0,
                    "status": "PAST DUE - needs update"
                } for l in overdue_closings],
                "summary": f"{len(overdue_tasks)} overdue tasks, {len(today_tasks)} due today, {len(closing_soon)} closing within 7 days" + (f", {len(overdue_closings)} loans with PAST closing dates needing attention" if overdue_closings else "")
            }
        except Exception as e:
            logger.error(f"Error in get_daily_priorities: {e}")
            db.rollback()  # Roll back to allow subsequent queries
            return {"error": "Internal server error"}

    tools["get_daily_priorities"] = execute_get_daily_priorities

    return tools
