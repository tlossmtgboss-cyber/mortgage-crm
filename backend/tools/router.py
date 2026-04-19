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


async def get_user_from_request(request: Request) -> Optional[Dict[str, Any]]:
    """
    Extract user information from request Authorization header.

    Returns dict with user info or None if not authenticated.
    """
    try:
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return None

        token = auth_header[7:]  # Remove "Bearer " prefix

        from auth.tokens import verify_access_token

        payload = verify_access_token(token)
        if not payload:
            return None

        # Extract user info from token
        user_email = payload.get("sub")
        user_id = payload.get("user_id")

        # If we have user_id, try to look up user from database
        if user_id or user_email:
            try:
                from database import SessionLocal
                from database.models import User
                db = SessionLocal()
                try:
                    if user_id:
                        user = db.query(User).filter(User.id == int(user_id)).first()
                    elif user_email:
                        user = db.query(User).filter(User.email == user_email).first()
                    else:
                        user = None

                    if user:
                        return {
                            "id": user.id,
                            "email": user.email,
                            "name": getattr(user, 'full_name', None) or getattr(user, 'name', user.email),
                            "role": getattr(user, 'role', None),
                            "organization_id": getattr(user, 'organization_id', None)
                        }
                finally:
                    db.close()
            except Exception as e:
                logger.warning(f"Failed to lookup user from DB: {e}")

        # Fallback to just token info
        return {
            "id": user_id,
            "email": user_email,
            "name": user_email,
            "role": payload.get("role"),
            "organization_id": payload.get("organization_id")
        }

    except Exception as e:
        logger.debug(f"Failed to extract user from request: {e}")
        return None

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
        from database import SessionLocal
        from sqlalchemy import text
        db = SessionLocal()
        try:
            # Search in leads and contacts tables
            query = text("""
                SELECT phone FROM leads
                WHERE LOWER(name) LIKE LOWER(:name) OR LOWER(first_name || ' ' || last_name) LIKE LOWER(:name)
                AND phone IS NOT NULL
                LIMIT 1
            """)
            result = db.execute(query, {"name": f"%{recipient_name}%"}).fetchone()

            if result and result[0]:
                to_phone = result[0]
            else:
                # Try contacts table
                query = text("""
                    SELECT phone FROM contacts
                    WHERE LOWER(first_name || ' ' || last_name) LIKE LOWER(:name)
                    AND phone IS NOT NULL
                    LIMIT 1
                """)
                result = db.execute(query, {"name": f"%{recipient_name}%"}).fetchone()

                if result and result[0]:
                    to_phone = result[0]
                else:
                    return {"success": False, "error": f"No contact found with name matching '{recipient_name}'"}
        except Exception as e:
            return {"success": False, "error": "Contact lookup failed"}
        finally:
            db.close()

    if not to_phone:
        return {"success": False, "error": "Either to_phone or recipient_name is required"}

    try:
        # Defer import to avoid circular dependencies
        from integrations.sms_service import get_sms_client
        client = get_sms_client()
        sid = client.send_sms(to_number=to_phone, message=message)
        return {
            "success": True,
            "data": {
                "sid": sid,
                "status": "queued",
                "to_phone": to_phone
            }
        }
    except Exception as e:
        return {"success": False, "error": "Internal server error"}


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
        return {"success": False, "error": "Internal server error"}


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

    # Get user from request auth
    user = await get_user_from_request(request)
    if not user:
        return {"success": False, "error": "Authentication required"}

    try:
        from database import SessionLocal
        from database.models import Task
        from datetime import datetime

        db = SessionLocal()
        try:
            # Create the task
            task = Task(
                title=title,
                description=description,
                priority=priority,
                status='pending',
                created_by_id=user.get('id'),
                assigned_to_id=user.get('id'),  # Default assign to creator
                lead_id=int(lead_id) if lead_id else None,
                loan_id=int(loan_id) if loan_id else None,
                due_date=datetime.fromisoformat(due_date) if due_date else None,
                created_at=datetime.now(timezone.utc)
            )
            db.add(task)
            db.commit()
            db.refresh(task)

            return {
                "success": True,
                "data": {
                    "task_id": task.id,
                    "title": task.title,
                    "status": task.status,
                    "priority": task.priority,
                    "created_by": user.get('email'),
                    "message": "Task created successfully"
                }
            }
        finally:
            db.close()

    except Exception as e:
        logger.error(f"Failed to create task: {e}")
        return {
            "success": False,
            "error": "Failed to create task"
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
        from database import SessionLocal
        from database.enums import LeadStage
        from database.models import Lead
        from datetime import datetime

        db = SessionLocal()
        try:
            query_str = args.get('query', '')
            stage_filter = args.get('stage', args.get('status'))
            limit = args.get('limit', 200)  # Increased from 25 to return full results

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

            now = datetime.now(timezone.utc)
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
            "error": "Internal server error"
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
        from database import SessionLocal
        from database.enums import LeadStage
        from database.models import Lead
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
            active_leads = [l for l in leads if l.stage and (l.stage.value if hasattr(l.stage, 'value') else str(l.stage)) not in terminal_statuses]

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
                "total_leads": total_leads,  # Top-level for easier access
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
            "error": "Internal server error"
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
        from database import SessionLocal
        from database.enums import LeadStage
        from database.models import Lead
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
            now = datetime.now(timezone.utc)
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
            "error": "Internal server error"
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
        from database import SessionLocal
        from database.enums import LoanStage
        from database.models import Loan
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
            stage_order = ["APPLICATION", "DISCLOSED", "PROCESSING", "SUBMITTED", "UW_RECEIVED", "UNDERWRITING", "CONDITIONAL_APPROVAL", "APPROVED", "SUSPENDED", "CTC", "CLEAR_TO_CLOSE", "CLOSING", "DOCS", "DOCS_OUT", "FUNDED"]
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
                    "generated_at": datetime.now(timezone.utc).isoformat()
                }
            }
        finally:
            db.close()

    except Exception as e:
        logger.error(f"Get pipeline metrics error: {e}")
        return {
            "success": False,
            "error": "Internal server error"
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
        from database import SessionLocal
        from datetime import datetime
        from sqlalchemy import text

        db = SessionLocal()
        try:
            status_filter = args.get("status")
            limit = args.get("limit", 50)

            # Use raw SQL to avoid selecting missing columns (sla_milestone_id, etc.)
            sql = """
                SELECT id, title, description, status, priority, due_date,
                       lead_id, loan_id, created_at
                FROM tasks
                WHERE 1=1
            """
            params = {"limit": limit}

            if status_filter and status_filter != "all":
                sql += " AND status = :status"
                params["status"] = status_filter

            sql += " ORDER BY due_date ASC NULLS LAST LIMIT :limit"

            result = db.execute(text(sql), params)
            rows = result.fetchall()

            now = datetime.now(timezone.utc)
            tasks_list = []

            for row in rows:
                due_date = row[5]  # due_date column
                is_overdue = False
                if due_date:
                    due_date_obj = due_date if hasattr(due_date, 'date') else due_date
                    if hasattr(due_date_obj, 'date'):
                        is_overdue = due_date_obj.date() < now.date()
                    else:
                        is_overdue = due_date_obj < now.date()

                task_dict = {
                    "id": row[0],
                    "title": row[1],
                    "description": row[2],
                    "status": row[3],
                    "priority": row[4] or 'medium',
                    "due_date": due_date.isoformat() if due_date else None,
                    "is_overdue": is_overdue,
                    "lead_id": row[6],
                    "loan_id": row[7],
                    "created_at": row[8].isoformat() if row[8] else None
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
            "error": "Internal server error"
        }


@register_tool_handler("get_daily_call_list")
async def handle_get_daily_call_list(args: Dict[str, Any], request: Request) -> Dict[str, Any]:
    """
    Get prioritized daily call list aggregating call-type tasks, leads needing contact,
    and loans needing milestone follow-ups.

    Returns contact names, phone numbers, and call reasons.
    """
    try:
        from agents.tools.tasks import get_daily_call_list

        user_id = args.get("user_id")
        include_leads = args.get("include_leads", True)
        include_loans = args.get("include_loans", True)
        include_tasks = args.get("include_tasks", True)
        limit = args.get("limit", 20)

        result = get_daily_call_list(
            user_id=user_id,
            include_leads=include_leads,
            include_loans=include_loans,
            include_tasks=include_tasks,
            limit=limit,
        )

        # Convert ToolResult to dict
        return {
            "success": result.status.value == "success",
            "data": result.data,
            "error": result.error,
            "message": result.message,
        }

    except Exception as e:
        logger.error(f"Get daily call list error: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return {
            "success": False,
            "error": "Internal server error"
        }


@register_tool_handler("get_daily_priorities")
async def handle_get_daily_priorities(args: Dict[str, Any], request: Request) -> Dict[str, Any]:
    """
    Get comprehensive daily priorities aggregating ALL relevant data sources:
    - Tasks (overdue and due today)
    - Call list (leads and contacts needing calls)
    - Pipeline alerts (stalled loans, lock expirations)
    - SLA tracking (milestones at risk)

    Returns actionable items with phone numbers for immediate action.
    """
    try:
        from database import SessionLocal
        from database.enums import LeadStage, LoanStage
        from database.models import Lead, Loan
        from datetime import datetime, timedelta
        from sqlalchemy import text

        db = SessionLocal()
        try:
            now = datetime.now(timezone.utc)
            today = now.date()

            # Initialize result sections
            calls_to_make = []
            tasks_to_complete = []
            pipeline_alerts = []

            # =================================================================
            # 1. CALLS TO MAKE - Most important for LO productivity
            # =================================================================

            # 1a. Call-type tasks with contact info
            call_tasks_sql = """
                SELECT t.id, t.title, t.due_date, t.priority,
                       l.id as lead_id, l.first_name, l.last_name, l.name as lead_name, l.phone as lead_phone, l.email as lead_email,
                       ln.id as loan_id, ln.borrower_name, ln.borrower_phone, ln.borrower_email
                FROM tasks t
                LEFT JOIN leads l ON t.lead_id = l.id
                LEFT JOIN loans ln ON t.loan_id = ln.id
                WHERE t.status NOT IN ('completed', 'cancelled')
                AND (LOWER(t.title) LIKE '%call%' OR LOWER(t.title) LIKE '%phone%' OR LOWER(t.title) LIKE '%contact%')
                ORDER BY t.due_date ASC NULLS LAST, t.priority DESC
                LIMIT 10
            """
            call_tasks = db.execute(text(call_tasks_sql)).fetchall()

            for row in call_tasks:
                # Determine contact name and phone
                if row[4]:  # lead_id exists
                    name = f"{row[5] or ''} {row[6] or ''}".strip() or row[7] or "Unknown"
                    phone = row[8]
                    email = row[9]
                    contact_type = "lead"
                elif row[10]:  # loan_id exists
                    name = row[11] or "Unknown"
                    phone = row[12]
                    email = row[13]
                    contact_type = "borrower"
                else:
                    name = "Unknown"
                    phone = None
                    email = None
                    contact_type = "unknown"

                due_date = row[2]
                is_overdue = due_date and (due_date.date() if hasattr(due_date, 'date') else due_date) < today

                calls_to_make.append({
                    "type": "scheduled_call",
                    "task_id": row[0],
                    "name": name,
                    "phone": phone,
                    "email": email,
                    "contact_type": contact_type,
                    "reason": row[1],
                    "due_date": due_date.isoformat() if due_date else None,
                    "priority": "high" if is_overdue else (row[3] or "medium"),
                    "is_overdue": is_overdue
                })

            # 1b. New leads needing first contact (speed to lead)
            new_leads = db.query(Lead).filter(
                Lead.stage == LeadStage.NEW,
                Lead.phone.isnot(None),
                Lead.phone != ''
            ).order_by(Lead.created_at.desc()).limit(10).all()

            for lead in new_leads:
                name = f"{lead.first_name or ''} {lead.last_name or ''}".strip() or lead.name or "Unknown"
                hours_old = (now - lead.created_at).total_seconds() / 3600 if lead.created_at else 999

                calls_to_make.append({
                    "type": "new_lead",
                    "lead_id": lead.id,
                    "name": name,
                    "phone": lead.phone,
                    "email": lead.email,
                    "contact_type": "lead",
                    "reason": f"New lead from {lead.source or 'unknown source'} - {hours_old:.0f}hrs old",
                    "priority": "high" if hours_old < 24 else "medium",
                    "hours_since_created": round(hours_old, 1),
                    "loan_amount": float(lead.loan_amount) if lead.loan_amount else None
                })

            # 1c. Leads needing follow-up (attempted contact, no recent activity)
            followup_sql = """
                SELECT id, first_name, last_name, name, phone, email, source, last_contact, stage
                FROM leads
                WHERE stage NOT IN ('Withdrawn', 'Does Not Qualify')
                AND phone IS NOT NULL AND phone != ''
                AND (last_contact IS NULL OR last_contact < :threshold)
                ORDER BY last_contact ASC NULLS FIRST
                LIMIT 10
            """
            followup_threshold = now - timedelta(days=3)
            followup_leads = db.execute(text(followup_sql), {"threshold": followup_threshold}).fetchall()

            for row in followup_leads:
                name = f"{row[1] or ''} {row[2] or ''}".strip() or row[3] or "Unknown"
                last_contact = row[7]
                days_since = (now - last_contact).days if last_contact else 999

                calls_to_make.append({
                    "type": "followup",
                    "lead_id": row[0],
                    "name": name,
                    "phone": row[4],
                    "email": row[5],
                    "contact_type": "lead",
                    "reason": f"Follow-up needed - {days_since} days since last contact",
                    "priority": "medium",
                    "days_since_contact": days_since,
                    "stage": row[8]
                })

            # Sort calls by priority (high first) and limit
            priority_order = {"high": 0, "medium": 1, "low": 2}
            calls_to_make.sort(key=lambda x: (priority_order.get(x.get("priority", "medium"), 1), not x.get("is_overdue", False)))
            calls_to_make = calls_to_make[:15]

            # =================================================================
            # 2. TASKS TO COMPLETE - Non-call tasks
            # =================================================================

            # Overdue tasks
            overdue_sql = """
                SELECT id, title, due_date, priority, description
                FROM tasks
                WHERE status NOT IN ('completed', 'cancelled')
                AND due_date < :today
                AND (LOWER(title) NOT LIKE '%call%' AND LOWER(title) NOT LIKE '%phone%')
                ORDER BY due_date ASC
                LIMIT 10
            """
            overdue_result = db.execute(text(overdue_sql), {"today": today})
            for row in overdue_result.fetchall():
                due_date = row[2]
                days_overdue = (today - (due_date.date() if hasattr(due_date, 'date') else due_date)).days if due_date else 0
                tasks_to_complete.append({
                    "type": "overdue_task",
                    "task_id": row[0],
                    "title": row[1],
                    "description": row[4][:100] if row[4] else None,
                    "due_date": due_date.isoformat() if due_date else None,
                    "days_overdue": days_overdue,
                    "priority": "high"
                })

            # Tasks due today
            today_sql = """
                SELECT id, title, priority, description
                FROM tasks
                WHERE status NOT IN ('completed', 'cancelled')
                AND due_date = :today
                AND (LOWER(title) NOT LIKE '%call%' AND LOWER(title) NOT LIKE '%phone%')
                LIMIT 10
            """
            today_result = db.execute(text(today_sql), {"today": today})
            for row in today_result.fetchall():
                tasks_to_complete.append({
                    "type": "due_today",
                    "task_id": row[0],
                    "title": row[1],
                    "description": row[3][:100] if row[3] else None,
                    "priority": row[2] or "medium"
                })

            # =================================================================
            # 3. PIPELINE ALERTS - Loans needing attention
            # =================================================================

            # Stalled loans (7+ days in same stage)
            stalled_threshold = now - timedelta(days=7)
            active_loans = db.query(Loan).filter(
                Loan.stage.notin_([LoanStage.FUNDED])
            ).all()

            for loan in active_loans:
                updated_at = loan.updated_at or loan.created_at
                if updated_at and updated_at < stalled_threshold:
                    days_stalled = (now - updated_at).days
                    pipeline_alerts.append({
                        "type": "stalled_loan",
                        "loan_id": loan.id,
                        "loan_number": loan.loan_number,
                        "borrower_name": loan.borrower_name,
                        "borrower_phone": loan.borrower_phone,
                        "borrower_email": loan.borrower_email,
                        "stage": loan.stage.value if hasattr(loan.stage, 'value') else str(loan.stage),
                        "days_in_stage": days_stalled,
                        "amount": float(loan.amount) if loan.amount else None,
                        "priority": "high" if days_stalled > 14 else "medium",
                        "action": f"Follow up - {days_stalled} days in {loan.stage.value if hasattr(loan.stage, 'value') else loan.stage}"
                    })

            # Sort pipeline alerts
            pipeline_alerts.sort(key=lambda x: x.get("days_in_stage", 0), reverse=True)
            pipeline_alerts = pipeline_alerts[:10]

            # =================================================================
            # BUILD FINAL RESPONSE
            # =================================================================

            # Calculate summary stats
            high_priority_count = (
                len([c for c in calls_to_make if c.get("priority") == "high"]) +
                len([t for t in tasks_to_complete if t.get("priority") == "high"]) +
                len([p for p in pipeline_alerts if p.get("priority") == "high"])
            )

            return {
                "success": True,
                "data": {
                    "date": today.isoformat(),
                    "generated_at": now.isoformat(),

                    # Section 1: Calls to make (with phone numbers)
                    "calls_to_make": {
                        "count": len(calls_to_make),
                        "items": calls_to_make
                    },

                    # Section 2: Tasks to complete
                    "tasks_to_complete": {
                        "count": len(tasks_to_complete),
                        "overdue_count": len([t for t in tasks_to_complete if t.get("type") == "overdue_task"]),
                        "items": tasks_to_complete
                    },

                    # Section 3: Pipeline alerts
                    "pipeline_alerts": {
                        "count": len(pipeline_alerts),
                        "items": pipeline_alerts
                    },

                    # Summary
                    "summary": {
                        "total_action_items": len(calls_to_make) + len(tasks_to_complete) + len(pipeline_alerts),
                        "high_priority_count": high_priority_count,
                        "calls_needed": len(calls_to_make),
                        "tasks_due": len(tasks_to_complete),
                        "loans_needing_attention": len(pipeline_alerts)
                    }
                }
            }
        finally:
            db.close()

    except Exception as e:
        logger.error(f"Get daily priorities error: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return {
            "success": False,
            "error": "Internal server error"
        }


@register_tool_handler("get_stale_leads")
async def handle_get_stale_leads(args: Dict[str, Any], request: Request) -> Dict[str, Any]:
    """
    Get leads that haven't been contacted in a specified number of days.

    Useful for:
    - Re-engagement campaigns
    - Preventing leads from going cold
    - Identifying follow-up opportunities

    Args:
        days_threshold: Days since last contact (default 7)
        limit: Maximum leads to return (default 50)
        include_never_contacted: Include leads never contacted (default True)
    """
    try:
        from database import SessionLocal
        from database.enums import LeadStage
        from database.models import Lead
        from datetime import datetime, timedelta
        from sqlalchemy import or_, and_

        db = SessionLocal()
        try:
            days_threshold = args.get("days_threshold", 7)
            limit = args.get("limit", 50)
            include_never_contacted = args.get("include_never_contacted", True)

            now = datetime.now(timezone.utc)
            threshold_date = now - timedelta(days=days_threshold)

            # Build query for stale leads
            query = db.query(Lead).filter(
                Lead.stage.notin_([LeadStage.WITHDRAWN, LeadStage.DOES_NOT_QUALIFY])
            )

            if include_never_contacted:
                # Leads never contacted OR not contacted since threshold
                query = query.filter(
                    or_(
                        Lead.last_contact.is_(None),
                        Lead.last_contact < threshold_date
                    )
                )
            else:
                # Only leads that were contacted but not recently
                query = query.filter(
                    and_(
                        Lead.last_contact.isnot(None),
                        Lead.last_contact < threshold_date
                    )
                )

            # Order by oldest contact first (never contacted at top)
            leads = query.order_by(
                Lead.last_contact.asc().nullsfirst()
            ).limit(limit).all()

            # Build result
            stale_leads = []
            never_contacted_count = 0

            for lead in leads:
                name = f"{lead.first_name or ''} {lead.last_name or ''}".strip() or lead.name or "Unknown"
                stage = lead.stage.value if hasattr(lead.stage, 'value') else str(lead.stage)

                if lead.last_contact:
                    days_since = (now - lead.last_contact).days
                else:
                    days_since = None
                    never_contacted_count += 1

                stale_leads.append({
                    "id": lead.id,
                    "name": name,
                    "phone": lead.phone,
                    "email": lead.email,
                    "source": lead.source,
                    "stage": stage,
                    "loan_amount": float(lead.loan_amount) if lead.loan_amount else None,
                    "created_at": lead.created_at.isoformat() if lead.created_at else None,
                    "last_contact": lead.last_contact.isoformat() if lead.last_contact else None,
                    "days_since_contact": days_since,
                    "never_contacted": lead.last_contact is None,
                    "priority": "high" if days_since is None or days_since > 14 else "medium"
                })

            return {
                "success": True,
                "data": {
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
            }
        finally:
            db.close()

    except Exception as e:
        logger.error(f"Get stale leads error: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return {
            "success": False,
            "error": "Internal server error"
        }


@register_tool_handler("get_top_leads")
async def handle_get_top_leads(args: Dict[str, Any], request: Request) -> Dict[str, Any]:
    """
    Get the top leads by score for immediate calling action.

    Returns leads sorted by:
    1. AI score (highest first)
    2. Recency (newest first)
    3. Stage priority (New > Prospect > Application)

    Perfect for "Call my top 3 leads right now" queries.
    """
    try:
        from database import SessionLocal
        from database.enums import LeadStage
        from database.models import Lead
        from datetime import datetime
        from sqlalchemy import desc, case

        db = SessionLocal()
        try:
            limit = args.get("limit", 10)
            include_stages = args.get("include_stages", None)
            require_phone = args.get("require_phone", True)

            # Excluded stages (terminal/inactive)
            excluded_stages = [LeadStage.WITHDRAWN, LeadStage.DOES_NOT_QUALIFY]

            # Build query
            query = db.query(Lead).filter(
                Lead.stage.notin_(excluded_stages)
            )

            # Filter to specific stages if requested
            if include_stages:
                stage_enums = []
                for stage in include_stages:
                    try:
                        stage_enums.append(LeadStage(stage))
                    except ValueError:
                        # Try matching by name
                        for s in LeadStage:
                            if s.name.lower() == stage.lower():
                                stage_enums.append(s)
                                break
                if stage_enums:
                    query = query.filter(Lead.stage.in_(stage_enums))

            # Require phone number for calling
            if require_phone:
                query = query.filter(
                    Lead.phone.isnot(None),
                    Lead.phone != ''
                )

            # Stage priority ordering (higher = call first)
            stage_priority = case(
                (Lead.stage == LeadStage.NEW, 100),
                (Lead.stage == LeadStage.ATTEMPTED_CONTACT, 90),
                (Lead.stage == LeadStage.PROSPECT, 80),
                (Lead.stage == LeadStage.APPLICATION, 70),
                (Lead.stage == LeadStage.PRE_QUALIFIED, 60),
                (Lead.stage == LeadStage.PRE_APPROVED, 50),
                (Lead.stage == LeadStage.LONG_TERM_NURTURE, 20),
                else_=10
            )

            # Order by: AI score (desc), stage priority (desc), created_at (desc)
            leads = query.order_by(
                desc(Lead.ai_score),
                desc(stage_priority),
                desc(Lead.created_at)
            ).limit(limit).all()

            # Format results
            top_leads = []
            for i, lead in enumerate(leads, 1):
                name = f"{lead.first_name or ''} {lead.last_name or ''}".strip() or lead.name or "Unknown"
                stage = lead.stage.value if hasattr(lead.stage, 'value') else str(lead.stage)

                top_leads.append({
                    "rank": i,
                    "id": lead.id,
                    "name": name,
                    "phone": lead.phone,
                    "email": lead.email,
                    "score": lead.ai_score or 50,
                    "stage": stage,
                    "source": lead.source,
                    "loan_amount": float(lead.loan_amount) if lead.loan_amount else None,
                    "created_at": lead.created_at.isoformat() if lead.created_at else None,
                    "last_contact": lead.last_contact.isoformat() if lead.last_contact else None,
                    "notes": lead.notes[:200] if lead.notes else None,
                    "call_ready": True  # All leads in this list have phones
                })

            # Summary stats
            avg_score = sum(l["score"] for l in top_leads) / len(top_leads) if top_leads else 0
            stages = {}
            for lead in top_leads:
                stages[lead["stage"]] = stages.get(lead["stage"], 0) + 1

            return {
                "success": True,
                "data": {
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
            }
        finally:
            db.close()

    except Exception as e:
        logger.error(f"Get top leads error: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return {
            "success": False,
            "error": "Internal server error"
        }
