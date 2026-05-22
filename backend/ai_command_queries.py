"""
AI Command Query Functions for Perennia AI

This module contains database query functions used by the AI command system:
- get_daily_summary: Daily summary with tasks, leads, loans, follow-ups
- search_records: Search across leads and loans
- get_clients_by_filter: Filter clients by criteria
- execute_analytical_query: Run analytical queries
- get_market_intelligence: Fetch market data for rate lock recommendations
- get_fallback_market_data: Fallback market data when scrapers unavailable
- get_sla_turnaround_times: Fetch SLA turnaround times
"""

from sqlalchemy.orm import Session
from sqlalchemy import func, or_
from typing import Dict, Any, Optional
from datetime import datetime
import logging

from ai_command_models import get_main_module

logger = logging.getLogger(__name__)


def get_daily_summary(db: Session, user_id: int) -> Dict[str, Any]:
    """Get daily summary data for the user - includes REAL CRM data"""
    # Clear any previous failed transaction state
    try:
        db.rollback()
    except Exception as e:
        logger.error(f"Error in get_daily_summary rollback: {e}")

    main = get_main_module()
    Task = main.Task
    Lead = main.Lead
    Loan = main.Loan
    AITask = main.AITask
    TaskType = main.TaskType

    today = datetime.now().date()

    # Get ALL pending tasks (not just today's) with lead/loan info
    all_tasks = db.query(Task).filter(
        Task.owner_id == user_id,
        Task.status != 'completed'
    ).order_by(Task.priority.desc(), Task.due_date.asc()).limit(20).all()

    # Also get AI tasks which have borrower_name field
    ai_tasks = []
    try:
        ai_tasks = db.query(AITask).filter(
            AITask.assigned_to_id == user_id,
            AITask.type != TaskType.COMPLETED
        ).order_by(AITask.due_date.asc()).limit(20).all()
    except Exception as e:
        logger.debug(f"AITask query failed: {e}")
        db.rollback()

    # Get workflow tasks (these are the tasks shown on the /tasks page)
    workflow_tasks = []
    try:
        from sqlalchemy import text
        result = db.execute(text("""
            SELECT wt.id, wt.task_title, wt.task_description, wt.priority,
                   wt.due_date, wt.status, wt.loan_id, l.borrower_name
            FROM workflow_tasks wt
            LEFT JOIN loans l ON wt.loan_id = l.id
            WHERE wt.status NOT IN ('completed', 'cancelled')
            ORDER BY wt.due_date ASC NULLS LAST
            LIMIT 50
        """))
        workflow_tasks = [dict(row._mapping) for row in result]
    except Exception as e:
        logger.debug(f"Workflow tasks query failed (table may not exist): {e}")
        db.rollback()

    # Build loan_id -> borrower_name map for AI tasks using raw SQL to avoid enum issues
    loan_ids = [t.loan_id for t in ai_tasks if t.loan_id]
    loan_map = {}
    if loan_ids:
        try:
            from sqlalchemy import text
            result = db.execute(text("""
                SELECT id, borrower_name FROM loans WHERE id = ANY(:loan_ids)
            """), {"loan_ids": loan_ids})
            loan_map = {row.id: row.borrower_name for row in result}
        except Exception as e:
            logger.debug(f"Loan name lookup failed: {e}")
            db.rollback()

    # Build a map of lead_id -> lead_name for enriching task display
    lead_ids = [t.lead_id for t in all_tasks if t.lead_id]
    lead_ids.extend([t.lead_id for t in ai_tasks if t.lead_id])
    lead_map = {}
    if lead_ids:
        leads_for_tasks = db.query(Lead).filter(Lead.id.in_(lead_ids)).all()
        lead_map = {l.id: l.name for l in leads_for_tasks}

    # Separate today's tasks and overdue tasks
    today_tasks = [t for t in all_tasks if t.due_date and t.due_date.date() == today]
    overdue_tasks = [t for t in all_tasks if t.due_date and t.due_date.date() < today]

    # Get ACTUAL LEAD DATA
    all_leads = db.query(Lead).filter(Lead.owner_id == user_id).all()
    total_leads = len(all_leads)

    # Group leads by status
    lead_status_breakdown = {}
    for lead in all_leads:
        status = lead.stage if lead.stage else 'Unassigned'
        lead_status_breakdown[status] = lead_status_breakdown.get(status, 0) + 1

    # Get ACTUAL LOAN DATA - use raw SQL to avoid enum deserialization issues
    all_loans = []
    total_loans = 0
    total_pipeline_value = 0
    loan_stage_breakdown = {}
    try:
        # Use raw SQL to get loan counts by stage, avoiding enum issues
        from sqlalchemy import text
        result = db.execute(text("""
            SELECT
                COALESCE(stage::text, 'Unknown') as stage,
                COUNT(*) as count,
                SUM(COALESCE(amount, 0)) as total_amount
            FROM loans
            WHERE loan_officer_id = :user_id
            GROUP BY stage
        """), {"user_id": user_id})

        for row in result:
            stage_name = row.stage if row.stage else 'Unknown'
            loan_stage_breakdown[stage_name] = row.count
            total_loans += row.count
            total_pipeline_value += float(row.total_amount or 0)
    except Exception as e:
        logger.warning(f"Loan query failed, using fallback: {e}")
        db.rollback()
        # Fallback: try simple count query
        try:
            total_loans = db.query(func.count(Loan.id)).filter(Loan.loan_officer_id == user_id).scalar() or 0
            total_pipeline_value = db.query(func.sum(Loan.amount)).filter(Loan.loan_officer_id == user_id).scalar() or 0
        except Exception as e:
            logger.error(f"Error in get_daily_summary loan fallback query: {e}")
            db.rollback()

    # Get MUM clients (safely check if table exists)
    mum_clients = []
    try:
        # Check if MUMClient model exists and query
        if hasattr(main, 'MUMClient'):
            MUMClient = main.MUMClient
            mum_clients = db.query(MUMClient).filter(MUMClient.loan_officer_id == user_id).limit(10).all()
    except Exception as e:
        db.rollback()  # Rollback to clear failed transaction
        logger.debug(f"MUM query failed (table may not exist): {e}")

    # Get unread emails/messages (safely check if table exists)
    unread_messages = 0
    try:
        if hasattr(main, 'EmailMessage'):
            EmailMessage = main.EmailMessage
            unread_messages = db.query(EmailMessage).filter(
                EmailMessage.user_id == user_id,
                EmailMessage.direction == 'inbound',
                EmailMessage.status == 'received'
            ).count()
    except Exception as e:
        db.rollback()  # Rollback to clear failed transaction
        logger.debug(f"EmailMessage query failed (table may not exist): {e}")

    # Build follow-ups from leads needing attention
    follow_ups = []

    # Helper function to enrich task title with lead/borrower name
    def get_enriched_task_title(task, is_ai_task=False):
        title = task.title
        borrower_name = None

        # For AI tasks, use borrower_name field directly or look up from loan
        if is_ai_task:
            borrower_name = getattr(task, 'borrower_name', None)
            if not borrower_name and task.loan_id:
                borrower_name = loan_map.get(task.loan_id)

        # For regular tasks, use lead_name from lead_map
        if not borrower_name:
            borrower_name = lead_map.get(task.lead_id) if hasattr(task, 'lead_id') and task.lead_id else None

        # Add borrower/lead name to title
        if borrower_name:
            # Check if name already in title to avoid duplication
            if borrower_name.lower() not in title.lower():
                return f"{title} - {borrower_name}"
        return title

    # Overdue tasks need immediate attention
    if overdue_tasks:
        follow_ups.append({
            "type": "Overdue Tasks",
            "items": [f"{get_enriched_task_title(t)} (Due: {t.due_date.strftime('%m/%d') if t.due_date else 'N/A'})" for t in overdue_tasks[:5]],
            "priority": "High"
        })

    # New leads need initial contact
    new_stage_leads = [l for l in all_leads if l.stage and l.stage == 'New']
    if new_stage_leads:
        follow_ups.append({
            "type": "New Leads Follow-up",
            "items": [f"{l.name} ({l.loan_type or 'N/A'})" for l in new_stage_leads[:5]],
            "priority": "High"
        })

    # Pre-approved leads - rate lock opportunities
    preapproved = [l for l in all_leads if l.stage and l.stage == 'Pre-Approved']
    if preapproved:
        follow_ups.append({
            "type": "Pre-Approved - Rate Lock Check",
            "items": [f"{l.name} (${l.preapproval_amount or 0:,.0f})" for l in preapproved[:5]],
            "priority": "High"
        })

    # Prospects need nurturing
    prospects = [l for l in all_leads if l.stage and l.stage == 'Prospect']
    if prospects:
        follow_ups.append({
            "type": "Prospect Nurturing",
            "items": [f"{l.name}" for l in prospects[:5]],
            "priority": "Medium"
        })

    # Build reconciliations from loans in pipeline
    reconciliations = []

    # Loans needing attention by stage
    processing_loans = [l for l in all_loans if l.stage == 'Processing']
    if processing_loans:
        reconciliations.append({
            "type": "Processing - Document Collection",
            "items": [f"{loan.borrower_name} (${loan.amount or 0:,.0f})" for loan in processing_loans[:3]]
        })

    uw_loans = [l for l in all_loans if l.stage in ['UW Received', 'Approved']]
    if uw_loans:
        reconciliations.append({
            "type": "Underwriting Review",
            "items": [f"{loan.borrower_name} ({loan.stage} - ${loan.amount or 0:,.0f})" for loan in uw_loans[:3]]
        })

    ctc_loans = [l for l in all_loans if l.stage == 'CTC']
    if ctc_loans:
        reconciliations.append({
            "type": "Clear to Close - Schedule Closing",
            "items": [f"{loan.borrower_name} (${loan.amount or 0:,.0f})" for loan in ctc_loans[:3]]
        })

    # MUM clients needing attention
    if mum_clients:
        reconciliations.append({
            "type": "MUM Client Check-ins",
            "items": [f"{c.borrower_name} ({c.loan_type or 'N/A'})" for c in mum_clients[:3]]
        })

    # Combine regular tasks and AI tasks, sorted by due date
    combined_tasks = []

    # Add regular tasks
    for t in all_tasks[:10]:
        combined_tasks.append({
            "id": t.id,
            "title": get_enriched_task_title(t, is_ai_task=False),
            "description": t.description,
            "priority": t.priority,
            "due_date": t.due_date.isoformat() if t.due_date else None,
            "lead_id": t.lead_id,
            "lead_name": lead_map.get(t.lead_id) if t.lead_id else None,
            "borrower_name": None,
            "source": "task"
        })

    # Add AI tasks with borrower names
    for t in ai_tasks[:10]:
        borrower = t.borrower_name
        if not borrower and t.loan_id:
            borrower = loan_map.get(t.loan_id)
        combined_tasks.append({
            "id": f"ai-{t.id}",
            "title": get_enriched_task_title(t, is_ai_task=True),
            "description": t.description,
            "priority": t.priority,
            "due_date": t.due_date.isoformat() if t.due_date else None,
            "lead_id": t.lead_id,
            "lead_name": lead_map.get(t.lead_id) if t.lead_id else None,
            "borrower_name": borrower,
            "loan_id": t.loan_id,
            "source": "ai_task"
        })

    # Add workflow tasks (from /tasks page)
    for wt in workflow_tasks[:20]:
        combined_tasks.append({
            "id": f"wf-{wt['id']}",
            "title": wt.get('task_title', 'Workflow Task'),
            "description": wt.get('task_description'),
            "priority": wt.get('priority', 'medium'),
            "due_date": wt['due_date'].isoformat() if wt.get('due_date') else None,
            "lead_id": None,
            "lead_name": None,
            "borrower_name": wt.get('borrower_name'),
            "loan_id": wt.get('loan_id'),
            "source": "workflow_task"
        })

    # Sort combined tasks by due date (None values at end)
    combined_tasks.sort(key=lambda x: (x["due_date"] is None, x["due_date"] or ""))

    return {
        "tasks": combined_tasks[:15],
        "follow_ups": follow_ups,
        "reconciliations": reconciliations,
        "summary": {
            "total_tasks": len(all_tasks) + len(ai_tasks) + len(workflow_tasks),
            "workflow_tasks": len(workflow_tasks),
            "overdue_tasks": len(overdue_tasks),
            "active_leads": total_leads,
            "hot_prospects": len([l for l in all_leads if l.stage and l.stage in ['Prospect', 'Pre-Approved']]),
            "loans_in_pipeline": total_loans,
            "pipeline_volume": f"${total_pipeline_value:,.0f}",
            "unread_messages": unread_messages,
            "mum_clients": len(mum_clients),
            "lead_status_breakdown": lead_status_breakdown,
            "loan_stage_breakdown": loan_stage_breakdown
        }
    }


def search_records(db: Session, user_id: int, query: str) -> Dict[str, Any]:
    """Search across leads and loans"""
    main = get_main_module()
    Lead = main.Lead
    Loan = main.Loan

    search_term = f"%{query}%"

    # Search leads (using owner_id and name field)
    leads = db.query(Lead).filter(
        Lead.owner_id == user_id,
        or_(
            Lead.name.ilike(search_term),
            Lead.email.ilike(search_term),
            Lead.phone.ilike(search_term)
        )
    ).limit(10).all()

    # Search loans using raw SQL to avoid enum deserialization issues
    loan_results = []
    try:
        from sqlalchemy import text
        result = db.execute(text("""
            SELECT id, borrower_name, amount, stage::text as stage
            FROM loans
            WHERE loan_officer_id = :user_id
            AND (borrower_name ILIKE :search_term OR property_address ILIKE :search_term)
            LIMIT 10
        """), {"user_id": user_id, "search_term": search_term})
        loan_results = [
            {
                "id": row.id,
                "borrower_name": row.borrower_name,
                "loan_amount": float(row.amount) if row.amount else 0,
                "stage": row.stage
            } for row in result
        ]
    except Exception as e:
        logger.debug(f"Loan search failed: {e}")
        db.rollback()

    return {
        "leads": [
            {
                "id": l.id,
                "name": l.name,
                "email": l.email,
                "phone": l.phone,
                "status": l.stage if l.stage else "Unassigned"
            } for l in leads
        ],
        "loans": loan_results,
        "query": query
    }


def get_clients_by_filter(db: Session, user_id: int, filter_criteria: Dict[str, Any]):
    """Get clients matching filter criteria"""
    main = get_main_module()
    Lead = main.Lead

    query = db.query(Lead).filter(Lead.owner_id == user_id)

    if "loan_type" in filter_criteria:
        query = query.filter(Lead.loan_type == filter_criteria["loan_type"])

    if "status" in filter_criteria:
        query = query.filter(Lead.status == filter_criteria["status"])

    if "tag" in filter_criteria:
        from sqlalchemy import text
        tag_leads = db.execute(
            text("SELECT lead_id FROM lead_tags WHERE tag = :tag"),
            {"tag": filter_criteria["tag"]}
        ).fetchall()
        tag_lead_ids = [row[0] for row in tag_leads]
        if tag_lead_ids:
            query = query.filter(Lead.id.in_(tag_lead_ids))
        else:
            query = query.filter(Lead.id == None)

    return query.limit(100).all()


def execute_analytical_query(db: Session, user_id: int, query_type: str, params: Dict[str, Any] = None) -> Dict[str, Any]:
    """Execute an analytical query and return formatted results"""
    from query_executor import execute_query, format_results

    if params is None:
        params = {}

    # Map tool names to query types
    query_type_map = {
        "query_pipeline_analysis": "pipeline_analysis",
        "query_lead_source_performance": "lead_source_performance",
        "query_conversion_funnel": "conversion_funnel",
        "query_loan_type_performance": "loan_type_performance",
        "query_monthly_trends": "monthly_trends",
        "query_stale_leads": "stale_leads_report",
        "query_high_value_opportunities": "high_value_opportunities",
        "query_activity_summary": "activity_summary",
    }

    actual_query_type = query_type_map.get(query_type, query_type)

    # Execute the query
    result = execute_query(db, actual_query_type, params, user_id)

    # Format for Claude
    formatted = format_results(actual_query_type, result)

    return {
        "query_type": actual_query_type,
        "success": result.get("success", False),
        "data": result.get("data", []),
        "count": result.get("count", 0),
        "formatted_text": formatted
    }


def get_market_intelligence(lock_days: int = 30) -> Dict[str, Any]:
    """Fetch current market intelligence for rate lock recommendations"""
    try:
        from scrapers import MarketDataOrchestrator

        orchestrator = MarketDataOrchestrator()
        snapshot = orchestrator.get_market_snapshot()

        if not snapshot:
            snapshot = get_fallback_market_data()

        # Get rate lock context for specific days
        lock_context = orchestrator.get_rate_lock_context(lock_days)

        return {
            "current_rates": {
                "30yr_fixed": snapshot.get("mortgage_rates", {}).get("rate_30yr", 6.50),
                "15yr_fixed": snapshot.get("mortgage_rates", {}).get("rate_15yr", 5.75),
                "spread_to_10yr": snapshot.get("mortgage_rates", {}).get("spread_to_10yr", 2.35)
            },
            "treasury_yields": {
                "2yr": snapshot.get("treasury", {}).get("2yr", 4.25),
                "5yr": snapshot.get("treasury", {}).get("5yr", 4.10),
                "10yr": snapshot.get("treasury", {}).get("10yr", 4.15),
                "30yr": snapshot.get("treasury", {}).get("30yr", 4.35),
                "spread_2s10s": snapshot.get("treasury", {}).get("spread_2s10s", -0.10)
            },
            "market_conditions": {
                "volatility": snapshot.get("volatility", {}).get("assessment", "moderate"),
                "vix": snapshot.get("volatility", {}).get("vix", 18.5),
                "market_score": snapshot.get("market_score", 55)
            },
            "rate_lock_recommendation": {
                "overall": snapshot.get("recommendation", "CAUTIOUS"),
                "lock_period": lock_days,
                "context": lock_context
            },
            "timestamp": snapshot.get("timestamp")
        }
    except Exception as e:
        logger.error(f"Error fetching market intelligence: {e}")
        return get_fallback_market_data()


def get_fallback_market_data() -> Dict[str, Any]:
    """Fallback market data when scrapers unavailable"""
    return {
        "current_rates": {
            "30yr_fixed": 6.50,
            "15yr_fixed": 5.75,
            "spread_to_10yr": 2.35
        },
        "treasury_yields": {
            "2yr": 4.25,
            "5yr": 4.10,
            "10yr": 4.15,
            "30yr": 4.35,
            "spread_2s10s": -0.10
        },
        "market_conditions": {
            "volatility": "moderate",
            "vix": 18.5,
            "market_score": 55
        },
        "rate_lock_recommendation": {
            "overall": "CAUTIOUS",
            "guidance": "Market conditions suggest careful evaluation. Consider locking if rate is acceptable and closing within 30 days. For longer timelines, monitor for better opportunities.",
            "factors": [
                "Treasury yields relatively stable",
                "Moderate volatility environment",
                "Mortgage spreads within normal range"
            ]
        },
        "timestamp": datetime.now().isoformat(),
        "is_fallback": True
    }


def get_sla_turnaround_times(db: Session) -> Dict[str, Any]:
    """Fetch SLA turnaround times from the SLA tracking system"""
    try:
        from crud.sla_tracking import get_all_sla_measures, get_dashboard_summary

        # Get all active SLA measures
        measures = get_all_sla_measures(db, organization_id=1, active_only=True)

        # Format SLA measures for display
        sla_list = []
        for measure in measures:
            # Convert target value to readable format
            target_value = measure.target_value
            target_unit = measure.target_unit if hasattr(measure, 'target_unit') else 'hours'

            # Format milestone type for display
            milestone_name = measure.milestone_type.value if hasattr(measure.milestone_type, 'value') else str(measure.milestone_type)
            display_name = milestone_name.replace('_', ' ').title()

            # Calculate display time (convert hours to days if > 24)
            if target_unit == 'hours' and target_value >= 24:
                display_time = f"{target_value / 24:.1f} business days"
            elif target_unit == 'hours':
                display_time = f"{target_value:.0f} hours"
            elif target_unit == 'days':
                display_time = f"{target_value:.0f} business days"
            else:
                display_time = f"{target_value} {target_unit}"

            sla_list.append({
                "milestone": display_name,
                "name": measure.name,
                "target": display_time,
                "target_hours": target_value,
                "description": measure.description,
                "warning_threshold": f"{measure.warning_threshold_pct}%",
                "business_hours_only": measure.business_hours_only if hasattr(measure, 'business_hours_only') else True
            })

        # Get dashboard summary for current performance
        try:
            summary = get_dashboard_summary(db, organization_id=1)
        except Exception as e:
            logger.error(f"Error getting SLA dashboard summary: {e}")
            summary = {}

        return {
            "sla_measures": sla_list,
            "total_measures": len(sla_list),
            "current_performance": {
                "on_time_rate": summary.get("on_time_rate", "N/A"),
                "active_milestones": summary.get("active_milestones", 0),
                "at_risk": summary.get("at_risk", 0),
                "overdue": summary.get("overdue", 0)
            },
            "business_hours": {
                "start": "9:00 AM",
                "end": "5:00 PM",
                "work_days": "Monday - Friday"
            }
        }
    except Exception as e:
        logger.error(f"Error fetching SLA turnaround times: {e}")
        # Return default SLA values if database fetch fails
        return {
            "sla_measures": [
                {"milestone": "Application To Approval", "name": "Application to Approval", "target": "5-10 business days", "description": "Time from application submission to credit approval"},
                {"milestone": "Processing", "name": "Initial Processing", "target": "1-3 business days", "description": "Initial document collection and review"},
                {"milestone": "Underwriting", "name": "Underwriting Review", "target": "3-5 business days", "description": "Full underwriting analysis"},
                {"milestone": "Clear To Close", "name": "Clear to Close", "target": "1-2 business days", "description": "Final approval after conditions cleared"},
                {"milestone": "Funding", "name": "Funding", "target": "Same/next business day", "description": "Post-closing disbursement"}
            ],
            "total_measures": 5,
            "is_default": True,
            "note": "These are typical industry targets. Check /sla page for your organization's specific SLAs."
        }
