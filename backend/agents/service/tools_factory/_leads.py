"""Lead search & pipeline-intelligence tools (extracted verbatim)."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any, Callable, Dict

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


def build_lead_tools(db: Session, current_user: Any, ctx: Dict[str, Any]) -> Dict[str, Callable]:
    tools: Dict[str, Callable] = {}

    org_id = ctx["org_id"]
    _has_org_wide_access = ctx["_has_org_wide_access"]

    # ============ Search Tools ============

    async def execute_search_leads(args):
        """Search for leads by name, email, or phone."""
        query_str = args.get("query", "")
        limit = args.get("limit", 10)

        try:
            # Scope: org-wide for admins/managers, user-only for others
            if _has_org_wide_access and org_id:
                base_filter = "organization_id = :org_id"
                base_params = {"org_id": org_id, "limit": limit}
            elif _has_org_wide_access and not org_id:
                base_filter = "1=1"
                base_params = {"limit": limit}
            else:
                base_filter = "owner_id = :user_id AND (:org_id IS NULL OR organization_id = :org_id)"
                base_params = {"user_id": current_user.id, "org_id": org_id, "limit": limit}

            if query_str:
                search = f"%{query_str}%"
                base_params["search"] = search
                lead_search_sql = (
                    "SELECT id, name, email, phone, stage"
                    " FROM leads"
                    " WHERE " + base_filter +
                    " AND (name ILIKE :search OR email ILIKE :search OR phone ILIKE :search)"
                    " LIMIT :limit"
                )
                lead_rows = db.execute(
                    text(lead_search_sql),
                    base_params
                ).fetchall()
            else:
                lead_list_sql = (
                    "SELECT id, name, email, phone, stage"
                    " FROM leads WHERE " + base_filter +
                    " LIMIT :limit"
                )
                lead_rows = db.execute(
                    text(lead_list_sql),
                    base_params
                ).fetchall()

            return {
                "count": len(lead_rows),
                "leads": [{
                    "id": l.id,
                    "name": l.name,
                    "email": l.email,
                    "phone": l.phone,
                    "stage": str(l.stage) if l.stage else None
                } for l in lead_rows]
            }
        except Exception as e:
            logger.error(f"Error in search_leads: {e}")
            db.rollback()
            return {"count": 0, "leads": [], "error": "Internal server error"}

    tools["search_leads"] = execute_search_leads

    # ============ Lead Pipeline Intelligence Tools ============

    async def execute_lead_status_insights(args):
        """
        Get lead pipeline intelligence and coaching insights.

        Analyzes leads by status and returns:
        - Summary metrics (counts, conversion rates)
        - Per-status breakdowns with SLA tracking
        - Bottleneck detection
        - Prioritized focus areas with playbooks
        - Trend data over time

        Use this for coaching-level answers, not raw lead lists.
        """
        try:
            from services.lead_status_insights_service import get_lead_status_insights

            # Use current user's ID if not specified
            assigned_to = args.get("assigned_to_user_id")
            if assigned_to is None:
                assigned_to = str(current_user.id)

            insights = get_lead_status_insights(
                db=db,
                assigned_to_user_id=assigned_to,
                include_statuses=args.get("include_statuses"),
                created_date_from=args.get("created_date_from"),
                created_date_to=args.get("created_date_to"),
                time_bucket=args.get("time_bucket", "week")
            )

            return insights
        except Exception as e:
            logger.error(f"Error in lead_status_insights: {e}")
            return {"error": "Internal server error"}

    tools["lead_status_insights"] = execute_lead_status_insights

    async def execute_get_leads_by_status(args):
        """
        Get detailed lead list for specific statuses.

        Use this when you need record-level detail to decide who to call, text, or email.
        For coaching/analytics overview, use lead_status_insights instead.
        """
        statuses = args.get("statuses", ["new", "attempted_contact", "prospect"])
        max_results = args.get("max_results", 100)
        include_details = args.get("include_details", True)

        try:
            # Map status keys to enum values
            status_map = {
                "new": "New",
                "attempted_contact": "Attempted Contact",
                "prospect": "Prospect",
                "application": "Application",
                "pre_qualified": "Pre-Qualified",
                "pre_approved": "Pre-Approved",
                "nurture": "Long-Term Nurture",
                "withdrawn": "Withdrawn",
                "does_not_qualify": "Does Not Qualify"
            }

            mapped_statuses = []
            for s in statuses:
                mapped = status_map.get(s.lower().replace(" ", "_").replace("-", "_"))
                if mapped:
                    mapped_statuses.append(mapped)

            if not mapped_statuses:
                mapped_statuses = ["New", "Attempted Contact", "Prospect"]

            # Build the IN clause safely
            status_placeholders = ", ".join([f":status_{i}" for i in range(len(mapped_statuses))])
            params = {"user_id": current_user.id, "org_id": org_id, "limit": max_results}
            for i, status in enumerate(mapped_statuses):
                params[f"status_{i}"] = status

            leads_by_status_sql = (
                "SELECT id, name, first_name, last_name, email, phone, stage,"
                " source, ai_score, loan_amount, preapproval_amount,"
                " last_contact, created_at, updated_at, notes"
                " FROM leads"
                " WHERE owner_id = :user_id"
                " AND (:org_id IS NULL OR organization_id = :org_id)"
                " AND stage::text IN (" + status_placeholders + ")"
                " ORDER BY"
                " CASE stage::text"
                " WHEN 'New' THEN 1"
                " WHEN 'Attempted Contact' THEN 2"
                " WHEN 'Prospect' THEN 3"
                " WHEN 'Application' THEN 4"
                " WHEN 'Pre-Qualified' THEN 5"
                " WHEN 'Pre-Approved' THEN 6"
                " ELSE 7"
                " END,"
                " updated_at DESC"
                " LIMIT :limit"
            )
            query = text(leads_by_status_sql)

            lead_rows = db.execute(query, params).fetchall()

            leads = []
            for l in lead_rows:
                lead_data = {
                    "id": l.id,
                    "name": l.name,
                    "email": l.email,
                    "phone": l.phone,
                    "stage": str(l.stage) if l.stage else None
                }

                if include_details:
                    lead_data.update({
                        "first_name": l.first_name,
                        "last_name": l.last_name,
                        "source": l.source,
                        "ai_score": l.ai_score,
                        "loan_amount": float(l.loan_amount) if l.loan_amount else None,
                        "preapproval_amount": float(l.preapproval_amount) if l.preapproval_amount else None,
                        "last_contact": l.last_contact.isoformat() if l.last_contact else None,
                        "created_at": l.created_at.isoformat() if l.created_at else None,
                        "updated_at": l.updated_at.isoformat() if l.updated_at else None,
                        "notes": l.notes[:200] if l.notes else None
                    })

                    # Calculate days in current status
                    if l.updated_at:
                        from datetime import datetime, timezone
                        now = datetime.now(timezone.utc)
                        updated = l.updated_at
                        if updated.tzinfo is None:
                            updated = updated.replace(tzinfo=timezone.utc)
                        lead_data["days_in_current_status"] = (now - updated).days

                leads.append(lead_data)

            # Group by status for easy consumption
            by_status = {}
            for lead in leads:
                status = lead.get("stage", "Unknown")
                if status not in by_status:
                    by_status[status] = []
                by_status[status].append(lead)

            return {
                "total_count": len(leads),
                "statuses_queried": mapped_statuses,
                "leads": leads,
                "by_status": by_status
            }
        except Exception as e:
            logger.error(f"Error in get_leads_by_status: {e}")
            db.rollback()
            return {"error": "Internal server error", "leads": []}

    tools["get_leads_by_status"] = execute_get_leads_by_status

    async def execute_get_top_leads(args):
        """
        Get the top leads by score for immediate calling action.

        Returns leads sorted by:
        1. AI score (highest first)
        2. Stage priority (New > Prospect > Application)
        3. Recency (newest first)

        Perfect for "Call my top 3 leads right now" queries.
        All returned leads have valid phone numbers.
        """
        limit = args.get("limit", 10)
        require_phone = args.get("require_phone", True)

        try:
            # Query leads with phone numbers, sorted by AI score and recency
            query_sql = """
                SELECT
                    l.id,
                    l.first_name,
                    l.last_name,
                    l.name,
                    l.phone,
                    l.email,
                    l.ai_score,
                    l.stage,
                    l.source,
                    l.loan_amount,
                    l.created_at,
                    l.last_contact,
                    l.notes
                FROM leads l
                WHERE l.stage NOT IN ('Withdrawn', 'Does Not Qualify')
                  AND l.owner_id = :user_id
                  AND (:org_id IS NULL OR l.organization_id = :org_id)
            """

            if require_phone:
                query_sql += " AND l.phone IS NOT NULL AND l.phone != ''"

            # Sort by AI score (desc), then by stage priority, then by recency
            query_sql += """
                ORDER BY
                    COALESCE(l.ai_score, 50) DESC,
                    CASE l.stage
                        WHEN 'New' THEN 100
                        WHEN 'Attempted Contact' THEN 90
                        WHEN 'Prospect' THEN 80
                        WHEN 'Application' THEN 70
                        WHEN 'Pre-Qualified' THEN 60
                        WHEN 'Pre-Approved' THEN 50
                        ELSE 10
                    END DESC,
                    l.created_at DESC
                LIMIT :limit
            """

            rows = db.execute(text(query_sql), {"user_id": current_user.id, "org_id": org_id, "limit": limit}).fetchall()

            top_leads = []
            for i, row in enumerate(rows, 1):
                name = f"{row.first_name or ''} {row.last_name or ''}".strip() or row.name or "Unknown"

                top_leads.append({
                    "rank": i,
                    "id": row.id,
                    "name": name,
                    "phone": row.phone,
                    "email": row.email,
                    "score": row.ai_score or 50,
                    "stage": row.stage,
                    "source": row.source,
                    "loan_amount": float(row.loan_amount) if row.loan_amount else None,
                    "created_at": row.created_at.isoformat() if row.created_at else None,
                    "last_contact": row.last_contact.isoformat() if row.last_contact else None,
                    "notes": row.notes[:200] if row.notes else None,
                    "call_ready": True
                })

            # Summary stats
            avg_score = sum(l["score"] for l in top_leads) / len(top_leads) if top_leads else 0
            stages = {}
            for lead in top_leads:
                stages[lead["stage"]] = stages.get(lead["stage"], 0) + 1

            return {
                "total": len(top_leads),
                "leads": top_leads,
                "summary": {
                    "average_score": round(avg_score, 1),
                    "by_stage": stages,
                    "all_have_phone": True
                },
                "call_action": {
                    "ready_to_dial": len(top_leads),
                    "suggestion": f"Click to call any of these {len(top_leads)} leads directly"
                }
            }

        except Exception as e:
            logger.error(f"Error in get_top_leads: {e}")
            db.rollback()
            return {"error": "Internal server error", "leads": []}

    tools["get_top_leads"] = execute_get_top_leads

    async def execute_get_stale_leads(args):
        """
        Get leads that haven't been contacted in a specified number of days.

        Useful for:
        - Re-engagement campaigns
        - Preventing leads from going cold
        - Identifying follow-up opportunities
        """
        days_threshold = args.get("days_threshold", 7)
        limit = args.get("limit", 50)
        include_never_contacted = args.get("include_never_contacted", True)

        try:
            now = datetime.now()
            threshold_date = now - timedelta(days=days_threshold)

            # Build query for stale leads
            if include_never_contacted:
                query_sql = """
                    SELECT
                        l.id,
                        l.first_name,
                        l.last_name,
                        l.name,
                        l.phone,
                        l.email,
                        l.ai_score,
                        l.stage,
                        l.source,
                        l.loan_amount,
                        l.created_at,
                        l.last_contact
                    FROM leads l
                    WHERE l.stage NOT IN ('Withdrawn', 'Does Not Qualify')
                      AND l.owner_id = :user_id
                      AND (:org_id IS NULL OR l.organization_id = :org_id)
                      AND (l.last_contact IS NULL OR l.last_contact < :threshold)
                    ORDER BY l.last_contact ASC NULLS FIRST
                    LIMIT :limit
                """
            else:
                query_sql = """
                    SELECT
                        l.id,
                        l.first_name,
                        l.last_name,
                        l.name,
                        l.phone,
                        l.email,
                        l.ai_score,
                        l.stage,
                        l.source,
                        l.loan_amount,
                        l.created_at,
                        l.last_contact
                    FROM leads l
                    WHERE l.stage NOT IN ('Withdrawn', 'Does Not Qualify')
                      AND l.owner_id = :user_id
                      AND (:org_id IS NULL OR l.organization_id = :org_id)
                      AND l.last_contact IS NOT NULL
                      AND l.last_contact < :threshold
                    ORDER BY l.last_contact ASC
                    LIMIT :limit
                """

            rows = db.execute(text(query_sql), {
                "user_id": current_user.id,
                "org_id": org_id,
                "threshold": threshold_date,
                "limit": limit
            }).fetchall()

            stale_leads = []
            never_contacted_count = 0

            for row in rows:
                name = f"{row.first_name or ''} {row.last_name or ''}".strip() or row.name or "Unknown"

                if row.last_contact:
                    days_since = (now - row.last_contact).days
                else:
                    days_since = None
                    never_contacted_count += 1

                stale_leads.append({
                    "id": row.id,
                    "name": name,
                    "phone": row.phone,
                    "email": row.email,
                    "source": row.source,
                    "stage": row.stage,
                    "loan_amount": float(row.loan_amount) if row.loan_amount else None,
                    "created_at": row.created_at.isoformat() if row.created_at else None,
                    "last_contact": row.last_contact.isoformat() if row.last_contact else None,
                    "days_since_contact": days_since,
                    "never_contacted": row.last_contact is None,
                    "priority": "high" if days_since is None or days_since > 14 else "medium"
                })

            return {
                "total": len(stale_leads),
                "never_contacted_count": never_contacted_count,
                "days_threshold": days_threshold,
                "leads": stale_leads,
                "summary": {
                    "total_stale": len(stale_leads),
                    "never_contacted": never_contacted_count,
                    "contacted_but_stale": len(stale_leads) - never_contacted_count,
                    "high_priority": len([l for l in stale_leads if l["priority"] == "high"])
                }
            }

        except Exception as e:
            logger.error(f"Error in get_stale_leads: {e}")
            db.rollback()
            return {"error": "Internal server error", "leads": []}

    tools["get_stale_leads"] = execute_get_stale_leads

    return tools
