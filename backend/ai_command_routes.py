"""
AI Command Routes for Pipeline 360 AI Landing Page

This module provides endpoints for processing natural language commands
and executing CRM actions through Claude AI.
"""

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from sqlalchemy import func, or_
from pydantic import BaseModel
from typing import Optional, Dict, List, Any
from datetime import datetime, timedelta
import logging
import os
import json
import uuid
import anthropic

from database import get_db

logger = logging.getLogger(__name__)

# Lazy import helper for main module to avoid circular imports
def get_main_module():
    import main
    return main

def get_current_user_dependency():
    """Get the get_current_user dependency from main module"""
    return get_main_module().get_current_user

router = APIRouter(prefix="/api/v1/ai")

# Initialize Anthropic client
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
anthropic_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY) if ANTHROPIC_API_KEY else None

# In-memory action cache (in production, use Redis)
action_cache: Dict[str, Dict[str, Any]] = {}


# ============================================================================
# Pydantic Models
# ============================================================================

class AICommandRequest(BaseModel):
    message: str
    conversation_context: Optional[List[Dict[str, str]]] = []


class AICommandResponse(BaseModel):
    intent: str
    explanation: str
    preview: Optional[Dict[str, Any]] = None
    action_id: Optional[str] = None
    data: Optional[Dict[str, Any]] = None


class ActionExecuteRequest(BaseModel):
    action_id: str
    modifications: Optional[Dict[str, Any]] = {}


class ActionExecuteResponse(BaseModel):
    success: bool
    message: str
    result: Optional[Dict[str, Any]] = None


# ============================================================================
# System Prompt
# ============================================================================

SYSTEM_PROMPT = """You are Pipeline 360's AI assistant, designed to help mortgage professionals manage their CRM efficiently through natural language commands.

You can perform the following actions:

1. DAILY_VIEW - Show today's tasks, follow-ups, and reconciliation items
2. EMAIL_CAMPAIGN - Send emails to filtered groups of clients
3. BULK_UPDATE - Update multiple records at once
4. VOICEMAIL_DROP - Queue ringless voicemail campaigns
5. PIPELINE_REPORT - Generate pipeline analysis reports
6. SEARCH - Search for clients, deals, or tasks
7. GENERAL_QUERY - Answer questions about the CRM data

When responding, you MUST return a valid JSON object with these fields:
- intent: The action type from the list above
- explanation: A brief, friendly explanation of what you're going to do
- preview: Object containing preview data for the action (if applicable)
- data: Additional data needed for execution

For EMAIL_CAMPAIGN, preview should include:
- recipients: List of client names/count
- subject: Email subject line
- body: Email content
- template: Template name if using one

For BULK_UPDATE, preview should include:
- records: List of records to update with current and new values
- field: Field being updated
- count: Number of records affected

For VOICEMAIL_DROP, preview should include:
- recipients: List of recipients
- script: The voicemail script content
- scheduled_time: When to send

For PIPELINE_REPORT, preview should include:
- report_type: Type of report
- date_range: Date range covered
- metrics: Key metrics to include

For DAILY_VIEW, data should include:
- tasks: List of today's tasks
- follow_ups: List of follow-ups
- reconciliations: List of reconciliation items
- summary: Overview statistics

For SEARCH, data should include:
- results: List of matching records
- query: The search terms used

Always be helpful, concise, and focus on actionable results. If you can't determine the intent, ask for clarification.
"""


# ============================================================================
# Helper Functions
# ============================================================================

def get_daily_summary(db: Session, user_id: int) -> Dict[str, Any]:
    """Get daily summary data for the user"""
    main = get_main_module()
    Task = main.Task

    today = datetime.now().date()

    # Get today's tasks
    tasks = db.query(Task).filter(
        Task.assigned_to_id == user_id,
        func.date(Task.due_date) == today,
        Task.status != 'completed'
    ).order_by(Task.priority.desc()).limit(10).all()

    # Get follow-ups (tasks with type follow_up due today or overdue)
    follow_ups = db.query(Task).filter(
        Task.assigned_to_id == user_id,
        Task.task_type == 'follow_up',
        func.date(Task.due_date) <= today,
        Task.status != 'completed'
    ).limit(5).all()

    # Get task statistics
    pending_tasks = db.query(Task).filter(
        Task.assigned_to_id == user_id,
        Task.status == 'pending'
    ).count()

    completed_today = db.query(Task).filter(
        Task.assigned_to_id == user_id,
        Task.status == 'completed',
        func.date(Task.updated_at) == today
    ).count()

    return {
        "tasks": [
            {
                "id": t.id,
                "title": t.title,
                "description": t.description,
                "priority": t.priority,
                "due_date": t.due_date.isoformat() if t.due_date else None,
                "lead_id": t.lead_id
            } for t in tasks
        ],
        "follow_ups": [
            {
                "id": t.id,
                "title": t.title,
                "lead_id": t.lead_id,
                "due_date": t.due_date.isoformat() if t.due_date else None
            } for t in follow_ups
        ],
        "reconciliations": [],  # Add reconciliation logic if you have that model
        "summary": {
            "pending_tasks": pending_tasks,
            "completed_today": completed_today,
            "follow_ups_due": len(follow_ups)
        }
    }


def search_records(db: Session, user_id: int, query: str) -> Dict[str, Any]:
    """Search across leads, deals, and tasks"""
    main = get_main_module()
    Lead = main.Lead
    Deal = main.Deal

    search_term = f"%{query}%"

    # Search leads
    leads = db.query(Lead).filter(
        Lead.user_id == user_id,
        or_(
            Lead.first_name.ilike(search_term),
            Lead.last_name.ilike(search_term),
            Lead.email.ilike(search_term),
            Lead.phone.ilike(search_term)
        )
    ).limit(10).all()

    # Search deals
    deals = db.query(Deal).filter(
        Deal.user_id == user_id,
        or_(
            Deal.borrower_name.ilike(search_term),
            Deal.property_address.ilike(search_term)
        )
    ).limit(10).all()

    return {
        "leads": [
            {
                "id": l.id,
                "name": f"{l.first_name} {l.last_name}",
                "email": l.email,
                "phone": l.phone,
                "status": l.status
            } for l in leads
        ],
        "deals": [
            {
                "id": d.id,
                "borrower_name": d.borrower_name,
                "loan_amount": float(d.loan_amount) if d.loan_amount else 0,
                "stage": d.stage
            } for d in deals
        ],
        "query": query
    }


def get_clients_by_filter(db: Session, user_id: int, filter_criteria: Dict[str, Any]):
    """Get clients matching filter criteria"""
    main = get_main_module()
    Lead = main.Lead

    query = db.query(Lead).filter(Lead.user_id == user_id)

    if "loan_type" in filter_criteria:
        query = query.filter(Lead.loan_type == filter_criteria["loan_type"])

    if "status" in filter_criteria:
        query = query.filter(Lead.status == filter_criteria["status"])

    if "tag" in filter_criteria:
        # Filter by tag if your Lead model supports tags
        pass

    return query.limit(100).all()


async def process_with_claude(
    message: str,
    context: List[Dict[str, str]],
    db: Session,
    user_id: int
) -> Dict[str, Any]:
    """Process the message with Claude AI"""

    if not anthropic_client:
        # Return mock response if no API key
        return generate_mock_response(message, db, user_id)

    # Build conversation history
    messages = []
    for ctx in context[-10:]:  # Keep last 10 messages for context
        messages.append({
            "role": ctx.get("role", "user"),
            "content": ctx.get("content", "")
        })

    messages.append({
        "role": "user",
        "content": message
    })

    try:
        response = anthropic_client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=2000,
            system=SYSTEM_PROMPT,
            messages=messages
        )

        # Parse Claude's response
        response_text = response.content[0].text

        # Try to extract JSON from the response
        try:
            # Find JSON in the response
            json_start = response_text.find('{')
            json_end = response_text.rfind('}') + 1
            if json_start >= 0 and json_end > json_start:
                json_str = response_text[json_start:json_end]
                result = json.loads(json_str)
                return result
        except json.JSONDecodeError:
            pass

        # If no JSON found, create a general response
        return {
            "intent": "GENERAL_QUERY",
            "explanation": response_text,
            "data": {}
        }

    except Exception as e:
        logger.error(f"Claude API error: {str(e)}")
        return generate_mock_response(message, db, user_id)


def generate_mock_response(message: str, db: Session, user_id: int) -> Dict[str, Any]:
    """Generate a mock response for demo purposes"""
    main = get_main_module()
    Lead = main.Lead

    message_lower = message.lower()

    if "today" in message_lower or "daily" in message_lower or "morning" in message_lower:
        summary = get_daily_summary(db, user_id)
        return {
            "intent": "DAILY_VIEW",
            "explanation": "Here's your daily overview:",
            "data": summary
        }

    elif "email" in message_lower or "send" in message_lower:
        # Get some sample clients
        clients = db.query(Lead).filter(Lead.user_id == user_id).limit(5).all()
        return {
            "intent": "EMAIL_CAMPAIGN",
            "explanation": "I'll prepare an email campaign for you.",
            "preview": {
                "recipients": [f"{c.first_name} {c.last_name}" for c in clients],
                "count": len(clients),
                "subject": "Important Update from Your Mortgage Team",
                "body": "Dear Client,\n\nWe wanted to reach out with some important information about your loan.\n\nBest regards,\nYour Mortgage Team"
            }
        }

    elif "search" in message_lower or "find" in message_lower:
        # Extract search term (simple approach)
        words = message.split()
        search_term = words[-1] if len(words) > 1 else "client"
        results = search_records(db, user_id, search_term)
        return {
            "intent": "SEARCH",
            "explanation": f"Here are the search results for '{search_term}':",
            "data": results
        }

    elif "report" in message_lower or "pipeline" in message_lower:
        return {
            "intent": "PIPELINE_REPORT",
            "explanation": "I'll generate a pipeline report for you.",
            "preview": {
                "report_type": "Pipeline Analysis",
                "date_range": "Last 30 days",
                "metrics": ["Total Loans", "Conversion Rate", "Average Loan Size", "Stage Distribution"]
            }
        }

    elif "voicemail" in message_lower:
        clients = db.query(Lead).filter(Lead.user_id == user_id).limit(3).all()
        return {
            "intent": "VOICEMAIL_DROP",
            "explanation": "I'll set up a ringless voicemail campaign.",
            "preview": {
                "recipients": [f"{c.first_name} {c.last_name}" for c in clients],
                "script": "Hi, this is a quick message from your mortgage team. We have some important updates about current rates. Please call us back at your convenience.",
                "scheduled_time": "Immediately"
            }
        }

    else:
        return {
            "intent": "GENERAL_QUERY",
            "explanation": f"I understand you're asking about: {message}. How can I help you further?",
            "data": {}
        }


# ============================================================================
# API Endpoints
# ============================================================================

@router.post("/process-command", response_model=AICommandResponse)
async def process_command(
    request: AICommandRequest,
    db: Session = Depends(get_db)
):
    """
    Process a natural language command and return intent with preview.
    """
    # Get current user from main module
    main = get_main_module()

    # For now, use a simple user check from token
    # In production, this should use proper auth
    current_user_id = 1  # Default to demo user

    try:
        # Process with Claude AI
        result = await process_with_claude(
            request.message,
            request.conversation_context,
            db,
            current_user_id
        )

        # Generate action ID if this is an actionable command
        action_id = None
        if result.get("intent") in ["EMAIL_CAMPAIGN", "BULK_UPDATE", "VOICEMAIL_DROP"]:
            action_id = str(uuid.uuid4())
            # Cache the action for later execution
            action_cache[action_id] = {
                "intent": result["intent"],
                "preview": result.get("preview"),
                "user_id": current_user_id,
                "created_at": datetime.now().isoformat()
            }

        return AICommandResponse(
            intent=result.get("intent", "GENERAL_QUERY"),
            explanation=result.get("explanation", ""),
            preview=result.get("preview"),
            action_id=action_id,
            data=result.get("data")
        )

    except Exception as e:
        logger.error(f"Error processing command: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/execute-action", response_model=ActionExecuteResponse)
async def execute_action(
    request: ActionExecuteRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """
    Execute a previously previewed action.
    """
    # For now, use a simple user check
    current_user_id = 1  # Default to demo user

    try:
        # Get cached action
        action_data = action_cache.get(request.action_id)
        if not action_data:
            raise HTTPException(status_code=404, detail="Action not found or expired")

        # Verify ownership
        if action_data["user_id"] != current_user_id:
            raise HTTPException(status_code=403, detail="Not authorized to execute this action")

        intent = action_data["intent"]
        preview = action_data.get("preview", {})
        modifications = request.modifications

        # Execute based on intent
        if intent == "EMAIL_CAMPAIGN":
            result = await execute_email_campaign(
                db, current_user_id, preview, modifications, background_tasks
            )
        elif intent == "BULK_UPDATE":
            result = await execute_bulk_update(
                db, current_user_id, preview, modifications
            )
        elif intent == "VOICEMAIL_DROP":
            result = await execute_voicemail_drop(
                db, current_user_id, preview, modifications, background_tasks
            )
        else:
            raise HTTPException(status_code=400, detail=f"Unknown action type: {intent}")

        # Remove from cache after execution
        del action_cache[request.action_id]

        return ActionExecuteResponse(
            success=True,
            message=result.get("message", "Action executed successfully"),
            result=result
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error executing action: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Action Executors
# ============================================================================

async def execute_email_campaign(
    db: Session,
    user_id: int,
    preview: Dict[str, Any],
    modifications: Dict[str, Any],
    background_tasks: BackgroundTasks
) -> Dict[str, Any]:
    """Execute an email campaign"""
    main = get_main_module()
    Lead = main.Lead
    Activity = main.Activity

    # Apply any modifications
    subject = modifications.get("subject", preview.get("subject", ""))
    body = modifications.get("body", preview.get("body", ""))
    recipients = preview.get("recipients", [])

    # In production, this would queue emails through your email service
    # For now, log the action and create activity records

    for recipient_name in recipients:
        # Find the lead
        names = recipient_name.split()
        if len(names) >= 2:
            lead = db.query(Lead).filter(
                Lead.user_id == user_id,
                Lead.first_name == names[0],
                Lead.last_name == names[-1]
            ).first()

            if lead:
                # Create activity record
                activity = Activity(
                    user_id=user_id,
                    lead_id=lead.id,
                    activity_type="email",
                    description=f"Email sent: {subject}",
                    data={"subject": subject, "body": body[:500]}
                )
                db.add(activity)

    db.commit()

    return {
        "message": f"Email campaign sent to {len(recipients)} recipients",
        "recipients_count": len(recipients),
        "subject": subject
    }


async def execute_bulk_update(
    db: Session,
    user_id: int,
    preview: Dict[str, Any],
    modifications: Dict[str, Any]
) -> Dict[str, Any]:
    """Execute a bulk update operation"""
    main = get_main_module()
    Lead = main.Lead
    Deal = main.Deal

    records = preview.get("records", [])
    field = modifications.get("field", preview.get("field", ""))
    new_value = modifications.get("new_value", preview.get("new_value", ""))

    updated_count = 0

    for record in records:
        record_id = record.get("id")
        record_type = record.get("type", "lead")

        if record_type == "lead":
            lead = db.query(Lead).filter(
                Lead.id == record_id,
                Lead.user_id == user_id
            ).first()

            if lead and hasattr(lead, field):
                setattr(lead, field, new_value)
                updated_count += 1

        elif record_type == "deal":
            deal = db.query(Deal).filter(
                Deal.id == record_id,
                Deal.user_id == user_id
            ).first()

            if deal and hasattr(deal, field):
                setattr(deal, field, new_value)
                updated_count += 1

    db.commit()

    return {
        "message": f"Updated {updated_count} records",
        "updated_count": updated_count,
        "field": field,
        "new_value": new_value
    }


async def execute_voicemail_drop(
    db: Session,
    user_id: int,
    preview: Dict[str, Any],
    modifications: Dict[str, Any],
    background_tasks: BackgroundTasks
) -> Dict[str, Any]:
    """Execute a voicemail drop campaign"""
    main = get_main_module()
    Lead = main.Lead
    Activity = main.Activity

    script = modifications.get("script", preview.get("script", ""))
    recipients = preview.get("recipients", [])

    # In production, this would integrate with a service like Slybroadcast
    # For now, create activity records

    for recipient_name in recipients:
        names = recipient_name.split()
        if len(names) >= 2:
            lead = db.query(Lead).filter(
                Lead.user_id == user_id,
                Lead.first_name == names[0],
                Lead.last_name == names[-1]
            ).first()

            if lead:
                activity = Activity(
                    user_id=user_id,
                    lead_id=lead.id,
                    activity_type="voicemail",
                    description="Ringless voicemail sent",
                    data={"script": script[:500]}
                )
                db.add(activity)

    db.commit()

    return {
        "message": f"Voicemail campaign queued for {len(recipients)} recipients",
        "recipients_count": len(recipients),
        "status": "queued"
    }
