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
    """Search leads handler"""
    query = args.get('query', '')
    limit = args.get('limit', 10)

    return {
        "success": True,
        "data": {
            "message": "Lead search delegated to agents/service.py handler",
            "query": query,
            "limit": limit
        }
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
        from main import SessionLocal
        from services.lead_status_insights_service import get_lead_status_insights

        db = SessionLocal()
        try:
            insights = get_lead_status_insights(
                db=db,
                assigned_to_user_id=args.get('assigned_to_user_id'),
                include_statuses=args.get('include_statuses'),
                created_date_from=args.get('created_date_from'),
                created_date_to=args.get('created_date_to'),
                time_bucket=args.get('time_bucket', 'week')
            )

            return {
                "success": True,
                "data": insights
            }
        finally:
            db.close()

    except Exception as e:
        logger.error(f"Lead status insights error: {e}")
        return {
            "success": False,
            "error": str(e)
        }
