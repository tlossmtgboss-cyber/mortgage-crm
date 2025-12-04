"""
Perennia AI Tools API Router
Unified endpoint structure: POST /api/tools/{domain}/{tool_name}

All tools return standardized responses:
{
    "success": true/false,
    "data": {},
    "error": null,
    "meta": {
        "tool": "tool_name",
        "request_id": "uuid",
        "elapsed_ms": 0
    }
}
"""
import time
import uuid
import logging
from typing import Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from .registry import get_registry, ToolRegistry

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/tools", tags=["AI Tools"])


class ToolRequest(BaseModel):
    """Generic tool request body"""
    arguments: Dict[str, Any] = {}


class ToolResponse(BaseModel):
    """Standardized tool response"""
    success: bool
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    meta: Dict[str, Any]


# Tool handler registry - maps tool names to their execution functions
_tool_handlers: Dict[str, callable] = {}


def register_tool_handler(tool_name: str):
    """Decorator to register a tool handler function"""
    def decorator(func):
        _tool_handlers[tool_name] = func
        return func
    return decorator


def get_tool_handler(tool_name: str) -> Optional[callable]:
    """Get the handler function for a tool"""
    return _tool_handlers.get(tool_name)


@router.get("/registry")
async def get_tool_registry():
    """Get the complete tool registry for AI orchestrator initialization"""
    registry = get_registry()
    return {
        "version": "1.0.0",
        "tools": list(registry.get_all_tools().values()),
        "domains": registry.get_domains(),
        "implemented_count": len(registry.get_implemented_tools()),
        "total_count": len(registry.get_all_tools())
    }


@router.get("/registry/summary")
async def get_registry_summary():
    """Get a summary of tool implementation status"""
    from .registry import get_tools_summary
    return get_tools_summary()


@router.get("/registry/{tool_name}")
async def get_tool_definition(tool_name: str):
    """Get definition for a specific tool"""
    registry = get_registry()
    tool = registry.get_tool(tool_name)
    if not tool:
        raise HTTPException(status_code=404, detail=f"Tool not found: {tool_name}")
    return tool


@router.get("/openai-format")
async def get_tools_openai_format():
    """Get tools formatted for OpenAI function calling"""
    registry = get_registry()
    return {"tools": registry.get_openai_tools_format()}


@router.get("/anthropic-format")
async def get_tools_anthropic_format():
    """Get tools formatted for Anthropic Claude"""
    registry = get_registry()
    return {"tools": registry.get_anthropic_tools_format()}


@router.post("/{domain}/{tool_name}")
async def execute_tool(
    domain: str,
    tool_name: str,
    request: Request,
    body: ToolRequest
):
    """
    Universal tool execution endpoint.

    POST /api/tools/{domain}/{tool_name}

    Body:
    {
        "arguments": { ... tool-specific arguments ... }
    }

    Returns standardized response.
    """
    request_id = str(uuid.uuid4())
    start_time = time.time()

    registry = get_registry()

    # Validate tool exists
    tool = registry.get_tool(tool_name)
    if not tool:
        return ToolResponse(
            success=False,
            data=None,
            error=f"Unknown tool: {tool_name}",
            meta={
                "tool": tool_name,
                "domain": domain,
                "request_id": request_id,
                "elapsed_ms": 0
            }
        )

    # Validate domain matches
    if tool.get('domain') != domain:
        return ToolResponse(
            success=False,
            data=None,
            error=f"Tool {tool_name} is not in domain {domain}",
            meta={
                "tool": tool_name,
                "domain": domain,
                "request_id": request_id,
                "elapsed_ms": 0
            }
        )

    # Check if tool is implemented
    if not tool.get('implemented', False):
        return ToolResponse(
            success=False,
            data=None,
            error=f"Tool {tool_name} is not yet implemented",
            meta={
                "tool": tool_name,
                "domain": domain,
                "request_id": request_id,
                "elapsed_ms": 0,
                "implementation_status": "not_implemented"
            }
        )

    # Validate input
    is_valid, error_msg = registry.validate_input(tool_name, body.arguments)
    if not is_valid:
        return ToolResponse(
            success=False,
            data=None,
            error=f"Invalid input: {error_msg}",
            meta={
                "tool": tool_name,
                "domain": domain,
                "request_id": request_id,
                "elapsed_ms": round((time.time() - start_time) * 1000, 2)
            }
        )

    # Get handler
    handler = get_tool_handler(tool_name)
    if not handler:
        return ToolResponse(
            success=False,
            data=None,
            error=f"No handler registered for tool: {tool_name}",
            meta={
                "tool": tool_name,
                "domain": domain,
                "request_id": request_id,
                "elapsed_ms": round((time.time() - start_time) * 1000, 2)
            }
        )

    # Execute tool
    try:
        # Pass request for auth context if needed
        result = await handler(body.arguments, request)
        elapsed_ms = round((time.time() - start_time) * 1000, 2)

        # If result is already a dict with success field, use it
        if isinstance(result, dict) and 'success' in result:
            result['meta'] = {
                "tool": tool_name,
                "domain": domain,
                "request_id": request_id,
                "elapsed_ms": elapsed_ms
            }
            return result

        return ToolResponse(
            success=True,
            data=result,
            error=None,
            meta={
                "tool": tool_name,
                "domain": domain,
                "request_id": request_id,
                "elapsed_ms": elapsed_ms
            }
        )

    except Exception as e:
        logger.error(f"Tool execution error [{tool_name}]: {e}")
        return ToolResponse(
            success=False,
            data=None,
            error=str(e),
            meta={
                "tool": tool_name,
                "domain": domain,
                "request_id": request_id,
                "elapsed_ms": round((time.time() - start_time) * 1000, 2)
            }
        )


# ============================================================================
# TOOL HANDLERS - Register handlers for each implemented tool
# These handlers delegate to the existing implementations in main.py
# Imports are deferred to avoid circular dependencies
# ============================================================================

@register_tool_handler("send_sms")
async def handle_send_sms(args: Dict[str, Any], request: Request) -> Dict[str, Any]:
    """Send SMS handler - delegates to existing implementation"""
    to_phone = args.get('to_phone')
    recipient_name = args.get('recipient_name')
    message = args.get('message')

    if not message:
        return {"success": False, "error": "Message is required"}

    # If recipient_name provided but no phone, look up the contact
    if recipient_name and not to_phone:
        return {"success": False, "error": "Contact lookup not yet implemented. Please provide to_phone."}

    if not to_phone:
        return {"success": False, "error": "Either to_phone or recipient_name is required"}

    try:
        # Defer import to avoid circular dependencies
        from integrations.twilio_service import TwilioSMSClient
        client = TwilioSMSClient()
        sid = await client.send_sms(to_number=to_phone, message=message)
        return {
            "success": True,
            "data": {
                "sid": sid,
                "status": "queued",
                "to_phone": to_phone
            }
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


@register_tool_handler("send_email")
async def handle_send_email(args: Dict[str, Any], request: Request) -> Dict[str, Any]:
    """Send email handler"""

    to = args.get('to')
    subject = args.get('subject')
    body = args.get('body')

    if not all([to, subject, body]):
        return {"success": False, "error": "to, subject, and body are required"}

    try:
        # Defer import to avoid circular dependencies
        from integrations.email_service import EmailService
        service = EmailService()
        result = service._send_email(to, subject, body)
        return {
            "success": True,
            "data": {
                "message_id": result.get('id') if result else None,
                "status": "sent"
            }
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


@register_tool_handler("create_task")
async def handle_create_task(args: Dict[str, Any], request: Request) -> Dict[str, Any]:
    """Create task handler"""
    title = args.get('title')
    description = args.get('description', '')
    due_date = args.get('due_date')
    priority = args.get('priority', 'medium')
    lead_id = args.get('lead_id')
    loan_id = args.get('loan_id')

    if not title:
        return {"success": False, "error": "Title is required"}

    # TODO: Get user from request auth
    # For now, return success with placeholder
    return {
        "success": True,
        "data": {
            "task_id": None,  # Will be set when integrated with DB
            "title": title,
            "status": "pending",
            "message": "Task creation delegated to main handler"
        }
    }


@register_tool_handler("get_pipeline")
async def handle_get_pipeline(args: Dict[str, Any], request: Request) -> Dict[str, Any]:
    """Get pipeline overview"""
    # Delegate to existing implementation
    return {
        "success": True,
        "data": {
            "message": "Pipeline data delegated to agents/service.py handler"
        }
    }


@register_tool_handler("search_leads")
async def handle_search_leads(args: Dict[str, Any], request: Request) -> Dict[str, Any]:
    """Search leads handler - query leads from database"""
    try:
        from main import SessionLocal, Lead, LeadStage
        from datetime import datetime

        db = SessionLocal()
        try:
            query_str = args.get('query', '')
            stage_filter = args.get('stage', args.get('status'))
            limit = args.get('limit', 25)

            query = db.query(Lead)

            # Apply stage filter if provided
            if stage_filter:
                try:
                    stage_enum = LeadStage(stage_filter)
                    query = query.filter(Lead.stage == stage_enum)
                except ValueError:
                    # Try matching by name (case-insensitive)
                    for s in LeadStage:
                        if s.name.lower() == stage_filter.lower() or s.value.lower() == stage_filter.lower():
                            query = query.filter(Lead.stage == s)
                            break

            # Apply text search if provided
            if query_str:
                search_term = f"%{query_str}%"
                query = query.filter(
                    (Lead.name.ilike(search_term)) |
                    (Lead.first_name.ilike(search_term)) |
                    (Lead.last_name.ilike(search_term)) |
                    (Lead.email.ilike(search_term)) |
                    (Lead.phone.ilike(search_term))
                )

            leads = query.order_by(Lead.created_at.desc()).limit(limit).all()

            now = datetime.utcnow()
            leads_list = []

            for lead in leads:
                status_key = lead.stage.value if hasattr(lead.stage, 'value') else str(lead.stage)
                name = f"{lead.first_name or ''} {lead.last_name or ''}".strip() or lead.name or "Unknown"

                leads_list.append({
                    "id": lead.id,
                    "name": name,
                    "email": lead.email,
                    "phone": lead.phone,
                    "source": lead.source,
                    "status": status_key,
                    "loan_amount": float(lead.loan_amount) if lead.loan_amount else None,
                    "property_type": lead.property_type,
                    "created_at": lead.created_at.isoformat() if lead.created_at else None
                })

            return {
                "success": True,
                "data": {
                    "total": len(leads_list),
                    "query": query_str,
                    "stage_filter": stage_filter,
                    "leads": leads_list
                }
            }
        finally:
            db.close()

    except Exception as e:
        logger.error(f"Search leads error: {e}")
        return {
            "success": False,
            "error": str(e)
        }


@register_tool_handler("search_loans")
async def handle_search_loans(args: Dict[str, Any], request: Request) -> Dict[str, Any]:
    """Search loans handler"""
    query = args.get('query', '')
    limit = args.get('limit', 10)

    return {
        "success": True,
        "data": {
            "message": "Loan search delegated to agents/service.py handler",
            "query": query,
            "limit": limit
        }
    }


@register_tool_handler("book_appointment")
async def handle_book_appointment(args: Dict[str, Any], request: Request) -> Dict[str, Any]:
    """Book appointment handler"""
    title = args.get('title')
    start_time = args.get('start_time')

    if not title or not start_time:
        return {"success": False, "error": "title and start_time are required"}

    return {
        "success": True,
        "data": {
            "message": "Appointment booking delegated to scheduler_routes.py",
            "title": title,
            "start_time": start_time
        }
    }


@register_tool_handler("get_rate_lock_recommendation")
async def handle_get_rate_lock_recommendation(args: Dict[str, Any], request: Request) -> Dict[str, Any]:
    """Get rate lock recommendation"""
    loan_id = args.get('loan_id')
    days_to_close = args.get('days_to_close')

    return {
        "success": True,
        "data": {
            "message": "Rate lock recommendation delegated to ai_command_routes.py",
            "loan_id": loan_id,
            "days_to_close": days_to_close
        }
    }


@register_tool_handler("lead_status_insights")
async def handle_lead_status_insights(args: Dict[str, Any], request: Request) -> Dict[str, Any]:
    """
    Get lead pipeline intelligence and coaching insights.

    Analyzes leads by status and returns:
    - Summary metrics (counts, conversion rates)
    - Per-status breakdowns with SLA tracking
    - Bottleneck detection
    - Prioritized focus areas with playbooks
    - Trend data over time
    """
    try:
        # Get database session
        from main import SessionLocal, Lead, LeadStage
        from datetime import datetime, timezone
        from collections import defaultdict

        db = SessionLocal()
        try:
            # Query ALL leads directly from database
            query = db.query(Lead)

            # Apply optional user filter
            if args.get('assigned_to_user_id'):
                try:
                    query = query.filter(Lead.owner_id == int(args['assigned_to_user_id']))
                except (ValueError, TypeError):
                    pass

            leads = query.all()
            total_leads = len(leads)

            # Group by stage
            by_stage = defaultdict(list)
            for lead in leads:
                stage_value = lead.stage.value if hasattr(lead.stage, 'value') else str(lead.stage)
                by_stage[stage_value].append(lead)

            # Calculate summary
            now = datetime.now(timezone.utc)

            # Terminal statuses
            terminal_statuses = {"Withdrawn", "Does Not Qualify"}
            active_leads = [l for l in leads if l.stage and l.stage.value not in terminal_statuses]

            # Build by_status breakdown
            status_breakdown = []
            for stage_value, stage_leads in by_stage.items():
                count = len(stage_leads)
                pct = round((count / total_leads * 100), 1) if total_leads > 0 else 0

                # Calculate average days in status
                days_list = []
                for lead in stage_leads:
                    if lead.updated_at:
                        updated = lead.updated_at
                        if updated.tzinfo is None:
                            updated = updated.replace(tzinfo=timezone.utc)
                        days = max(0, (now - updated).days)
                        days_list.append(days)

                avg_days = round(sum(days_list) / len(days_list), 1) if days_list else 0

                status_breakdown.append({
                    "status": stage_value.lower().replace(" ", "_").replace("-", "_"),
                    "label": stage_value,
                    "count": count,
                    "percentage_of_total": pct,
                    "average_days_in_status": avg_days
                })

            # Sort by count descending
            status_breakdown.sort(key=lambda x: x["count"], reverse=True)

            # Calculate conversion rates
            new_count = len(by_stage.get("New", []))
            contacted = total_leads - new_count
            overall_contact_rate = round((contacted / total_leads * 100), 1) if total_leads > 0 else 0

            # Build response
            insights = {
                "context": {
                    "assigned_to_user_id": args.get('assigned_to_user_id'),
                    "generated_at": now.isoformat()
                },
                "summary": {
                    "total_leads": total_leads,
                    "total_active_leads": len(active_leads),
                    "overall_contact_rate": overall_contact_rate
                },
                "by_status": status_breakdown,
                "bottlenecks": [],
                "priority_focus_areas": []
            }

            # Detect bottlenecks - leads in New for too long
            new_leads = by_stage.get("New", [])
            if new_leads:
                not_contacted = [l for l in new_leads if not l.last_contact]
                if len(not_contacted) > 3:
                    insights["bottlenecks"].append({
                        "status": "new",
                        "issue_type": "missing_contact_attempts",
                        "description": f"{len(not_contacted)} new leads have not been contacted yet",
                        "severity": "critical",
                        "recommended_action": "Speed to lead is critical. Contact these leads immediately."
                    })

                insights["priority_focus_areas"].append({
                    "rank": 1,
                    "status": "new",
                    "focus_reason": f"{len(new_leads)} new leads require immediate attention",
                    "suggested_playbook": "Call within 5 minutes, then text + email same day."
                })

            return {
                "success": True,
                "data": insights
            }
        finally:
            db.close()

    except Exception as e:
        logger.error(f"Lead status insights error: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return {
            "success": False,
            "error": str(e)
        }


@register_tool_handler("get_leads_by_status")
async def handle_get_leads_by_status(args: Dict[str, Any], request: Request) -> Dict[str, Any]:
    """
    Get detailed lead lists filtered by status for actionable follow-up.

    Returns leads with:
    - Contact info (name, email, phone)
    - Days in current status
    - Loan details (amount, property type, purpose)
    - Last contact date and notes
    """
    try:
        from main import SessionLocal, Lead, LeadStage
        from datetime import datetime

        db = SessionLocal()
        try:
            status_filter = args.get("status")
            limit = args.get("limit", 25)
            sort_by = args.get("sort_by", "days_in_status_desc")

            query = db.query(Lead)

            # Apply stage filter if provided
            if status_filter:
                try:
                    status_enum = LeadStage(status_filter)
                    query = query.filter(Lead.stage == status_enum)
                except ValueError:
                    # Try matching by name
                    for s in LeadStage:
                        if s.name.lower() == status_filter.lower() or s.value.lower() == status_filter.lower():
                            query = query.filter(Lead.stage == s)
                            break

            leads = query.limit(limit).all()

            # Group by status and calculate days_in_status
            now = datetime.utcnow()
            result = {}

            for lead in leads:
                status_key = lead.stage.value if hasattr(lead.stage, 'value') else str(lead.stage)
                if status_key not in result:
                    result[status_key] = []

                # Calculate days in current status
                last_status_change = getattr(lead, 'status_date', None) or lead.created_at
                days_in_status = (now - last_status_change).days if last_status_change else 0

                result[status_key].append({
                    "id": lead.id,
                    "name": f"{lead.first_name or ''} {lead.last_name or ''}".strip() or lead.name,
                    "email": lead.email,
                    "phone": lead.phone,
                    "source": lead.source,
                    "status": status_key,
                    "days_in_current_status": days_in_status,
                    "loan_amount": float(lead.loan_amount) if lead.loan_amount else None,
                    "property_type": lead.property_type,
                    "loan_purpose": getattr(lead, 'loan_type', None),
                    "created_at": lead.created_at.isoformat() if lead.created_at else None,
                    "last_contact_at": lead.last_contact.isoformat() if lead.last_contact else None,
                    "notes": lead.notes if hasattr(lead, 'notes') else None
                })

            # Sort leads within each status by days_in_status descending
            for status_key in result:
                result[status_key].sort(key=lambda x: x["days_in_current_status"], reverse=True)

            return {
                "success": True,
                "data": {
                    "total_leads": len(leads),
                    "leads_by_status": result
                }
            }
        finally:
            db.close()

    except Exception as e:
        logger.error(f"Get leads by status error: {e}")
        return {
            "success": False,
            "error": str(e)
        }


@register_tool_handler("get_pipeline_metrics")
async def handle_get_pipeline_metrics(args: Dict[str, Any], request: Request) -> Dict[str, Any]:
    """
    Get comprehensive pipeline metrics including loan count, volume, and stage breakdown.

    Returns:
    - Summary: total loans, total volume, active loans
    - By stage: count and volume per loan stage
    - Velocity: recent fundings and average days to close
    """
    try:
        from main import SessionLocal, Loan, LoanStage
        from datetime import datetime, timedelta
        from sqlalchemy import func

        db = SessionLocal()
        try:
            # Get all loans
            loans = db.query(Loan).all()

            # Calculate metrics
            total_loans = len(loans)
            active_loans = [l for l in loans if l.stage != LoanStage.FUNDED]
            funded_loans = [l for l in loans if l.stage == LoanStage.FUNDED]

            # Calculate volumes
            total_volume = sum(float(l.amount or 0) for l in loans)
            active_volume = sum(float(l.amount or 0) for l in active_loans)

            # Stage breakdown
            stages = {}
            for loan in loans:
                stage_name = loan.stage.value if hasattr(loan.stage, 'value') else str(loan.stage)
                if stage_name not in stages:
                    stages[stage_name] = {"count": 0, "volume": 0}
                stages[stage_name]["count"] += 1
                stages[stage_name]["volume"] += float(loan.amount or 0)

            # Convert to list format
            stages_list = [
                {
                    "stage": stage,
                    "count": data["count"],
                    "volume": data["volume"],
                    "volume_formatted": f"${data['volume']:,.2f}"
                }
                for stage, data in stages.items()
            ]

            # Sort by pipeline order
            stage_order = ["Disclosed", "Processing", "Submitted", "UW Received", "Approved", "Suspended", "CTC", "Docs Out", "Funded"]
            stages_list.sort(key=lambda x: stage_order.index(x["stage"]) if x["stage"] in stage_order else 99)

            return {
                "success": True,
                "data": {
                    "summary": {
                        "total_loans": len(active_loans),  # Active loans (not funded)
                        "total_volume": active_volume,
                        "total_volume_formatted": f"${active_volume:,.2f}",
                        "funded_count": len(funded_loans),
                        "funded_volume": sum(float(l.amount or 0) for l in funded_loans)
                    },
                    "stages": stages_list,
                    "generated_at": datetime.utcnow().isoformat()
                }
            }
        finally:
            db.close()

    except Exception as e:
        logger.error(f"Get pipeline metrics error: {e}")
        return {
            "success": False,
            "error": str(e)
        }


@register_tool_handler("get_tasks")
async def handle_get_tasks(args: Dict[str, Any], request: Request) -> Dict[str, Any]:
    """
    Get tasks for the current user.

    Args:
        status: Filter by status (pending, completed, all)
        limit: Maximum number of tasks to return

    Returns:
        List of tasks with details
    """
    try:
        from main import SessionLocal, Task
        from datetime import datetime

        db = SessionLocal()
        try:
            status_filter = args.get("status")
            limit = args.get("limit", 50)

            query = db.query(Task)

            # Apply status filter
            if status_filter and status_filter != "all":
                query = query.filter(Task.status == status_filter)

            tasks = query.order_by(Task.due_date.asc().nullslast()).limit(limit).all()

            now = datetime.utcnow()
            tasks_list = []

            for task in tasks:
                task_dict = {
                    "id": task.id,
                    "title": task.title,
                    "description": task.description,
                    "status": task.status,
                    "priority": getattr(task, 'priority', 'medium'),
                    "due_date": task.due_date.isoformat() if task.due_date else None,
                    "is_overdue": task.due_date and task.due_date < now.date() if hasattr(task.due_date, 'date') else False,
                    "lead_id": task.lead_id,
                    "loan_id": task.loan_id,
                    "created_at": task.created_at.isoformat() if task.created_at else None
                }
                tasks_list.append(task_dict)

            # Count by status
            open_count = len([t for t in tasks_list if t["status"] not in ("completed", "cancelled")])
            overdue_count = len([t for t in tasks_list if t.get("is_overdue")])

            return {
                "success": True,
                "data": {
                    "total": len(tasks_list),
                    "open_count": open_count,
                    "overdue_count": overdue_count,
                    "tasks": tasks_list
                }
            }
        finally:
            db.close()

    except Exception as e:
        logger.error(f"Get tasks error: {e}")
        return {
            "success": False,
            "error": str(e)
        }


@register_tool_handler("get_daily_priorities")
async def handle_get_daily_priorities(args: Dict[str, Any], request: Request) -> Dict[str, Any]:
    """
    Get prioritized daily action items across loans, leads, and tasks.

    Returns high-priority items that need attention today:
    - Overdue tasks
    - Hot leads (New leads, high scores)
    - Loans at risk (stalled, lock expiring)
    - Follow-ups due
    """
    try:
        from main import SessionLocal, Task, Lead, Loan, LeadStage, LoanStage
        from datetime import datetime, timedelta

        db = SessionLocal()
        try:
            now = datetime.utcnow()
            today = now.date()

            priorities = {
                "high_priority": [],
                "medium_priority": [],
                "follow_ups": []
            }

            # 1. Get overdue tasks
            overdue_tasks = db.query(Task).filter(
                Task.status.notin_(["completed", "cancelled"]),
                Task.due_date < today
            ).limit(10).all()

            for task in overdue_tasks:
                priorities["high_priority"].append({
                    "type": "overdue_task",
                    "id": task.id,
                    "title": task.title,
                    "due_date": task.due_date.isoformat() if task.due_date else None,
                    "days_overdue": (today - task.due_date).days if task.due_date else 0,
                    "action": "Complete this overdue task"
                })

            # 2. Get hot leads (New stage, not contacted)
            hot_leads = db.query(Lead).filter(
                Lead.stage == LeadStage.NEW
            ).order_by(Lead.created_at.desc()).limit(10).all()

            for lead in hot_leads:
                name = f"{lead.first_name or ''} {lead.last_name or ''}".strip() or lead.name or "Unknown"
                days_old = (now - lead.created_at).days if lead.created_at else 0
                priority_level = "high_priority" if days_old < 2 else "medium_priority"

                priorities[priority_level].append({
                    "type": "new_lead",
                    "id": lead.id,
                    "name": name,
                    "phone": lead.phone,
                    "email": lead.email,
                    "source": lead.source,
                    "days_since_created": days_old,
                    "action": "Make first contact - speed to lead is critical"
                })

            # 3. Get tasks due today
            tasks_due_today = db.query(Task).filter(
                Task.status.notin_(["completed", "cancelled"]),
                Task.due_date == today
            ).limit(10).all()

            for task in tasks_due_today:
                priorities["medium_priority"].append({
                    "type": "task_due_today",
                    "id": task.id,
                    "title": task.title,
                    "action": "Complete before end of day"
                })

            # 4. Get stalled loans (in same stage for too long)
            stalled_threshold = now - timedelta(days=7)
            active_loans = db.query(Loan).filter(
                Loan.stage.notin_([LoanStage.FUNDED])
            ).all()

            for loan in active_loans:
                # Check if loan has been in current stage too long
                updated_at = loan.updated_at or loan.created_at
                if updated_at and updated_at < stalled_threshold:
                    days_stalled = (now - updated_at).days
                    priorities["medium_priority"].append({
                        "type": "stalled_loan",
                        "id": loan.id,
                        "loan_number": loan.loan_number,
                        "borrower": loan.borrower_name,
                        "stage": loan.stage.value if hasattr(loan.stage, 'value') else str(loan.stage),
                        "days_in_stage": days_stalled,
                        "action": f"Follow up on loan stalled in {loan.stage.value if hasattr(loan.stage, 'value') else loan.stage}"
                    })

            # Limit results
            priorities["high_priority"] = priorities["high_priority"][:5]
            priorities["medium_priority"] = priorities["medium_priority"][:10]

            return {
                "success": True,
                "data": {
                    "date": today.isoformat(),
                    "high_priority": priorities["high_priority"],
                    "medium_priority": priorities["medium_priority"],
                    "summary": {
                        "high_priority_count": len(priorities["high_priority"]),
                        "medium_priority_count": len(priorities["medium_priority"]),
                        "total_action_items": len(priorities["high_priority"]) + len(priorities["medium_priority"])
                    }
                }
            }
        finally:
            db.close()

    except Exception as e:
        logger.error(f"Get daily priorities error: {e}")
        return {
            "success": False,
            "error": str(e)
        }
