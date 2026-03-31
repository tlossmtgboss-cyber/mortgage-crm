"""
AI Assistant & Conversations Routes

Handles AI chat functionality with agentic function calling capabilities.
Endpoints for:
- AI chat with function calling (create tasks, update leads, send SMS, etc.)
- Conversation history retrieval
- AI task completion suggestions
"""

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone, timedelta
from sqlalchemy.orm import Session
import logging
import json
import os

from db import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["AI Assistant"])


# =============================================================================
# Runtime imports to avoid circular dependencies
# =============================================================================

def get_models():
    """Get models at runtime to avoid circular imports"""
    import main
    return {
        'User': main.User,
        'Lead': main.Lead,
        'Loan': main.Loan,
        'Activity': main.Activity,
        'ActivityType': main.ActivityType,
        'AITask': main.AITask,
        'TaskType': main.TaskType,
        'LeadStage': main.LeadStage,
        'Conversation': main.Conversation,
    }


def get_current_user_dep():
    """Get current user dependency at runtime"""
    import main
    return main.get_current_user


def get_openai_client():
    """Get OpenAI client at runtime"""
    import main
    return main.openai_client


def get_or_():
    """Get SQLAlchemy or_ at runtime"""
    from sqlalchemy import or_
    return or_


# =============================================================================
# Pydantic Schemas
# =============================================================================

class ConversationCreate(BaseModel):
    message: str
    lead_id: Optional[int] = None
    loan_id: Optional[int] = None
    context: Optional[Dict[str, Any]] = None


class ConversationResponse(BaseModel):
    id: int
    message: str
    response: Optional[str]
    role: str
    created_at: datetime

    class Config:
        from_attributes = True


# =============================================================================
# AI Function Execution
# =============================================================================

async def execute_ai_function(
    function_name: str,
    function_args: dict,
    db: Session,
    current_user,
    context_lead=None,
    context_loan=None
) -> dict:
    """Execute AI function calls and return results"""
    models = get_models()
    User = models['User']
    Lead = models['Lead']
    Loan = models['Loan']
    Activity = models['Activity']
    ActivityType = models['ActivityType']
    AITask = models['AITask']
    TaskType = models['TaskType']
    LeadStage = models['LeadStage']
    or_ = get_or_()

    try:
        if function_name == "create_task":
            # Create a new task
            lead_id = function_args.get("lead_id") or (context_lead.id if context_lead else None)
            loan_id = function_args.get("loan_id") or (context_loan.id if context_loan else None)

            task_type = TaskType.IN_PROGRESS  # Default to in progress for new tasks

            new_task = AITask(
                type=task_type,
                title=function_args["title"],
                description=function_args.get("description", ""),
                assigned_to_id=current_user.id,
                lead_id=lead_id,
                loan_id=loan_id,
                priority=function_args.get("priority", "medium"),
                due_date=datetime.fromisoformat(function_args["due_date"]) if function_args.get("due_date") else None,
                ai_reasoning="Created by AI assistant"
            )
            db.add(new_task)
            db.commit()
            db.refresh(new_task)

            # Log activity
            if lead_id:
                activity = Activity(
                    type=ActivityType.NOTE,
                    description=f"AI created task: {function_args['title']}",
                    lead_id=lead_id,
                    user_id=current_user.id
                )
                db.add(activity)
                db.commit()

            return {
                "success": True,
                "task_id": new_task.id,
                "message": f"Task '{function_args['title']}' created successfully"
            }

        elif function_name == "update_lead_stage":
            lead_id = function_args["lead_id"]
            lead = db.query(Lead).filter(Lead.id == lead_id, Lead.owner_id == current_user.id).first()

            if not lead:
                return {"success": False, "error": "Lead not found or access denied"}

            old_stage = lead.stage.value
            new_stage_str = function_args["new_stage"]
            new_stage = LeadStage[new_stage_str.upper().replace(" ", "_")]

            lead.stage = new_stage
            lead.updated_at = datetime.now(timezone.utc)

            # Log activity
            reason = function_args.get("reason", "Stage updated by AI")
            activity = Activity(
                type=ActivityType.STAGE_CHANGE,
                description=f"AI updated stage from {old_stage} to {new_stage_str}. Reason: {reason}",
                lead_id=lead_id,
                user_id=current_user.id
            )
            db.add(activity)
            db.commit()

            # Event-driven workflow enrollment (eliminates 60s polling delay)
            try:
                from services.workflow_scheduler import trigger_workflow_evaluation_for_lead
                trigger_workflow_evaluation_for_lead(
                    db, lead_id, new_stage_str,
                    lead_source=getattr(lead, 'source', None),
                    user_id=current_user.id,
                )
            except Exception as e:
                logger.warning(f"Workflow evaluation trigger failed for lead {lead_id}: {e}")

            return {
                "success": True,
                "lead_id": lead_id,
                "old_stage": old_stage,
                "new_stage": new_stage_str,
                "message": f"Lead stage updated from {old_stage} to {new_stage_str}"
            }

        elif function_name == "add_activity":
            lead_id = function_args.get("lead_id") or (context_lead.id if context_lead else None)
            loan_id = function_args.get("loan_id") or (context_loan.id if context_loan else None)

            # Map activity type string to enum
            type_map = {
                "note": ActivityType.NOTE,
                "call": ActivityType.CALL,
                "email": ActivityType.EMAIL,
                "meeting": ActivityType.MEETING,
                "sms": ActivityType.SMS,
                "other": ActivityType.NOTE
            }

            activity_type = type_map.get(function_args["activity_type"], ActivityType.NOTE)

            activity = Activity(
                type=activity_type,
                description=function_args["description"],
                lead_id=lead_id,
                loan_id=loan_id,
                user_id=current_user.id
            )
            db.add(activity)
            db.commit()
            db.refresh(activity)

            return {
                "success": True,
                "activity_id": activity.id,
                "message": "Activity added successfully"
            }

        elif function_name == "get_lead_details":
            lead_id = function_args["lead_id"]
            lead = db.query(Lead).filter(Lead.id == lead_id, Lead.owner_id == current_user.id).first()

            if not lead:
                return {"success": False, "error": "Lead not found or access denied"}

            return {
                "success": True,
                "lead": {
                    "id": lead.id,
                    "name": lead.name,
                    "email": lead.email,
                    "phone": lead.phone,
                    "stage": lead.stage.value,
                    "ai_score": lead.ai_score,
                    "credit_score": lead.credit_score,
                    "loan_type": lead.loan_type,
                    "preapproval_amount": lead.preapproval_amount,
                    "property_value": lead.property_value,
                    "employment_status": lead.employment_status,
                    "annual_income": lead.annual_income
                }
            }

        elif function_name == "get_high_priority_leads":
            limit = function_args.get("limit", 10)

            # Get high-priority leads (high score, active stages)
            leads = db.query(Lead).filter(
                Lead.owner_id == current_user.id,
                Lead.stage.in_([LeadStage.NEW, LeadStage.ATTEMPTED_CONTACT, LeadStage.PROSPECT, LeadStage.APPLICATION, LeadStage.PRE_QUALIFIED])
            ).order_by(Lead.ai_score.desc()).limit(limit).all()

            return {
                "success": True,
                "count": len(leads),
                "leads": [
                    {
                        "id": lead.id,
                        "name": lead.name,
                        "stage": lead.stage.value,
                        "ai_score": lead.ai_score,
                        "credit_score": lead.credit_score,
                        "email": lead.email
                    }
                    for lead in leads
                ]
            }

        elif function_name == "search_leads":
            query = function_args["query"].lower()
            stage_filter = function_args.get("stage")

            # Search by name or email
            leads_query = db.query(Lead).filter(
                Lead.owner_id == current_user.id,
                or_(
                    Lead.name.ilike(f"%{query}%"),
                    Lead.email.ilike(f"%{query}%")
                )
            )

            if stage_filter:
                try:
                    stage_enum = LeadStage[stage_filter.upper().replace(" ", "_")]
                    leads_query = leads_query.filter(Lead.stage == stage_enum)
                except KeyError:
                    pass

            leads = leads_query.limit(10).all()

            return {
                "success": True,
                "count": len(leads),
                "leads": [
                    {
                        "id": lead.id,
                        "name": lead.name,
                        "email": lead.email,
                        "stage": lead.stage.value,
                        "ai_score": lead.ai_score
                    }
                    for lead in leads
                ]
            }

        elif function_name == "get_lead_stats":
            # Get lead counts by stage
            leads = db.query(Lead).filter(Lead.owner_id == current_user.id).all()
            total = len(leads)

            # Count by stage
            stage_counts = {}
            for lead in leads:
                stage_name = lead.stage.value if lead.stage else "Unknown"
                stage_counts[stage_name] = stage_counts.get(stage_name, 0) + 1

            return {
                "success": True,
                "total_leads": total,
                "by_stage": stage_counts,
                "summary": f"You have {total} total leads" + (f" across {len(stage_counts)} stages" if stage_counts else "")
            }

        elif function_name == "send_sms":
            # Send SMS using telephony provider
            recipient_phone = function_args.get("recipient_phone")
            recipient_name = function_args.get("recipient_name")
            message_text = function_args.get("message", "")
            lead_id = function_args.get("lead_id") or (context_lead.id if context_lead else None)

            # Look up phone number if recipient_name provided
            if not recipient_phone and recipient_name:
                # Search leads
                lead = db.query(Lead).filter(
                    Lead.owner_id == current_user.id,
                    Lead.name.ilike(f"%{recipient_name}%")
                ).first()
                if lead and lead.phone:
                    recipient_phone = lead.phone
                    lead_id = lead.id
                else:
                    # Search users
                    user = db.query(User).filter(
                        User.full_name.ilike(f"%{recipient_name}%")
                    ).first()
                    if user and user.phone:
                        recipient_phone = user.phone
                    elif user and user.user_metadata:
                        profile = user.user_metadata if isinstance(user.user_metadata, dict) else {}
                        recipient_phone = profile.get('phone')

            if not recipient_phone:
                return {"success": False, "error": f"Could not find phone number for {recipient_name or 'recipient'}"}

            # Format phone number
            phone_digits = ''.join(filter(str.isdigit, recipient_phone))
            if len(phone_digits) == 10:
                recipient_phone = f"+1{phone_digits}"
            elif len(phone_digits) == 11 and phone_digits.startswith('1'):
                recipient_phone = f"+{phone_digits}"

            # Send the SMS via Telnyx
            telnyx_key = os.getenv("TELNYX_API_KEY")
            telnyx_phone = os.getenv("TELNYX_PHONE_NUMBER")

            if not all([telnyx_key, telnyx_phone]):
                return {"success": False, "error": "Telnyx not configured"}

            try:
                from telephony.sms import send_sms as telnyx_send_sms
                result = telnyx_send_sms(
                    to=recipient_phone,
                    from_=telnyx_phone,
                    text=message_text,
                    api_key=telnyx_key,
                )

                # Log activity
                if lead_id:
                    activity = Activity(
                        type=ActivityType.SMS,
                        description=f"SMS sent: {message_text[:100]}...",
                        lead_id=lead_id,
                        user_id=current_user.id
                    )
                    db.add(activity)
                    db.commit()

                msg_id = result.get("id", "unknown")
                return {
                    "success": True,
                    "message_sid": msg_id,
                    "recipient": recipient_name or recipient_phone,
                    "result": f"SMS sent successfully to {recipient_name or recipient_phone}"
                }
            except Exception as sms_error:
                return {"success": False, "error": "SMS failed"}

        elif function_name == "update_user_profile":
            # Update user profile
            user_name = function_args.get("user_name")
            user_email = function_args.get("user_email")
            phone = function_args.get("phone")
            title = function_args.get("title")
            nmls_number = function_args.get("nmls_number")

            # Find the user
            target_user = None
            if user_email:
                target_user = db.query(User).filter(User.email == user_email).first()
            elif user_name:
                target_user = db.query(User).filter(User.full_name.ilike(f"%{user_name}%")).first()

            if not target_user:
                return {"success": False, "error": f"User not found: {user_name or user_email}"}

            updates = []

            # Update phone
            if phone:
                target_user.phone = phone
                updates.append(f"phone: {phone}")

            # Update title (in user_metadata)
            if title:
                if not target_user.user_metadata:
                    target_user.user_metadata = {}
                target_user.user_metadata['title'] = title
                updates.append(f"title: {title}")

            # Update NMLS
            if nmls_number:
                if hasattr(target_user, 'nmls_number'):
                    target_user.nmls_number = nmls_number
                else:
                    if not target_user.user_metadata:
                        target_user.user_metadata = {}
                    target_user.user_metadata['nmls_number'] = nmls_number
                updates.append(f"NMLS: {nmls_number}")

            db.commit()

            return {
                "success": True,
                "user": target_user.full_name or target_user.email,
                "updates": updates,
                "result": f"Updated profile for {target_user.full_name or target_user.email}: {', '.join(updates)}"
            }

        elif function_name == "schedule_appointment":
            # Create an appointment/task for scheduling
            title = function_args.get("title", "Meeting")
            attendee_name = function_args.get("attendee_name", "")
            date_time_str = function_args.get("date_time", "")
            duration = function_args.get("duration_minutes", 30)
            notes = function_args.get("notes", "")

            # Parse the date_time (handle relative dates like "tomorrow")
            from dateutil import parser as date_parser
            from dateutil.relativedelta import relativedelta

            try:
                if "tomorrow" in date_time_str.lower():
                    scheduled_time = datetime.now(timezone.utc) + timedelta(days=1)
                    # Parse time if included
                    time_match = date_time_str.lower().replace("tomorrow", "").strip()
                    if time_match:
                        try:
                            time_parsed = date_parser.parse(time_match)
                            scheduled_time = scheduled_time.replace(
                                hour=time_parsed.hour,
                                minute=time_parsed.minute
                            )
                        except (ValueError, TypeError):
                            scheduled_time = scheduled_time.replace(hour=10, minute=0)  # Default 10am
                else:
                    scheduled_time = date_parser.parse(date_time_str)
            except (ValueError, TypeError):
                scheduled_time = datetime.now(timezone.utc) + timedelta(days=1)
                scheduled_time = scheduled_time.replace(hour=10, minute=0)

            # Find lead if attendee_name provided
            lead_id = context_lead.id if context_lead else None
            if attendee_name and not lead_id:
                lead = db.query(Lead).filter(
                    Lead.owner_id == current_user.id,
                    Lead.name.ilike(f"%{attendee_name}%")
                ).first()
                if lead:
                    lead_id = lead.id

            # Create task for the appointment
            task_title = f"{title} with {attendee_name}" if attendee_name else title
            task_description = f"Duration: {duration} minutes\n{notes}" if notes else f"Duration: {duration} minutes"

            new_task = AITask(
                type=TaskType.IN_PROGRESS,  # Default to in progress for new tasks
                title=task_title,
                description=task_description,
                assigned_to_id=current_user.id,
                lead_id=lead_id,
                priority="high",
                due_date=scheduled_time,
                ai_reasoning="Scheduled by AI assistant"
            )
            db.add(new_task)
            db.commit()
            db.refresh(new_task)

            return {
                "success": True,
                "task_id": new_task.id,
                "scheduled_time": scheduled_time.isoformat(),
                "result": f"Appointment scheduled: {task_title} for {scheduled_time.strftime('%B %d, %Y at %I:%M %p')}"
            }

        else:
            return {"success": False, "error": f"Unknown function: {function_name}"}

    except Exception as e:
        logger.error(f"Error executing AI function {function_name}: {e}")
        db.rollback()
        return {"success": False, "error": "Internal server error"}


# =============================================================================
# AI Tool Definitions
# =============================================================================

def get_ai_tools():
    """Return the list of tools available for AI function calling"""
    return [
        {
            "type": "function",
            "function": {
                "name": "create_task",
                "description": "Create a new task for a lead or loan. Use this when the user asks you to create a task, reminder, or follow-up.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "title": {
                            "type": "string",
                            "description": "The task title (e.g., 'Call John about pre-approval')"
                        },
                        "description": {
                            "type": "string",
                            "description": "Detailed description of the task"
                        },
                        "lead_id": {
                            "type": "integer",
                            "description": "The lead ID this task is for (if applicable)"
                        },
                        "loan_id": {
                            "type": "integer",
                            "description": "The loan ID this task is for (if applicable)"
                        },
                        "due_date": {
                            "type": "string",
                            "description": "Due date in ISO format (e.g., '2025-11-10T10:00:00')"
                        },
                        "priority": {
                            "type": "string",
                            "enum": ["high", "medium", "low"],
                            "description": "Task priority level"
                        }
                    },
                    "required": ["title"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "update_lead_stage",
                "description": "Update a lead's stage in the pipeline. Use this when progressing a lead or changing their status.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "lead_id": {
                            "type": "integer",
                            "description": "The lead ID to update"
                        },
                        "new_stage": {
                            "type": "string",
                            "enum": ["New", "Attempted Contact", "Prospect", "Pre-Qualified", "Pre-Approved", "Application", "Completed", "Withdrawn", "Does Not Qualify"],
                            "description": "The new stage for the lead"
                        },
                        "reason": {
                            "type": "string",
                            "description": "Brief reason for the stage change"
                        }
                    },
                    "required": ["lead_id", "new_stage"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "add_activity",
                "description": "Add a note, activity, or log entry to a lead or loan. Use this to record conversations, notes, or important events.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "lead_id": {
                            "type": "integer",
                            "description": "The lead ID (if applicable)"
                        },
                        "loan_id": {
                            "type": "integer",
                            "description": "The loan ID (if applicable)"
                        },
                        "activity_type": {
                            "type": "string",
                            "enum": ["note", "call", "email", "meeting", "sms", "other"],
                            "description": "Type of activity"
                        },
                        "description": {
                            "type": "string",
                            "description": "The activity description or note content"
                        }
                    },
                    "required": ["description", "activity_type"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "get_lead_details",
                "description": "Retrieve detailed information about a specific lead. Use this when you need more information about a lead.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "lead_id": {
                            "type": "integer",
                            "description": "The lead ID to retrieve"
                        }
                    },
                    "required": ["lead_id"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "get_high_priority_leads",
                "description": "Get a list of high-priority leads that need attention. Use this when asked about priorities or what to work on.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "limit": {
                            "type": "integer",
                            "description": "Maximum number of leads to return (default 10)",
                            "default": 10
                        }
                    }
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "search_leads",
                "description": "Search for leads by name, email, or other criteria.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Search query (name, email, etc.)"
                        },
                        "stage": {
                            "type": "string",
                            "description": "Filter by stage"
                        }
                    },
                    "required": ["query"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "get_lead_stats",
                "description": "Get statistics about leads including total count, counts by stage, and pipeline summary. Use this when asked about how many leads, lead counts, or pipeline status.",
                "parameters": {
                    "type": "object",
                    "properties": {}
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "send_sms",
                "description": "Send an SMS text message to a contact, lead, or user. YOU MUST CALL THIS TOOL when user asks to 'send a text', 'text them', 'SMS someone', etc. You can look up phone by recipient name.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "recipient_phone": {
                            "type": "string",
                            "description": "Phone number to send SMS to (E.164 format preferred, e.g., +18005551234)"
                        },
                        "recipient_name": {
                            "type": "string",
                            "description": "Name of person to send SMS to - system will look up their phone number from leads, contacts, or users"
                        },
                        "message": {
                            "type": "string",
                            "description": "The text message content to send"
                        },
                        "lead_id": {
                            "type": "integer",
                            "description": "Optional lead ID to associate the SMS with"
                        }
                    },
                    "required": ["message"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "update_user_profile",
                "description": "Update a user's profile information including phone number, title, or NMLS number. Call this when asked to update someone's profile, add a phone number, or change user details.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "user_name": {
                            "type": "string",
                            "description": "Name of user to update (will search by name)"
                        },
                        "user_email": {
                            "type": "string",
                            "description": "Email of user to update"
                        },
                        "phone": {
                            "type": "string",
                            "description": "New phone number to set"
                        },
                        "title": {
                            "type": "string",
                            "description": "New title to set (e.g., 'Senior Loan Officer')"
                        },
                        "nmls_number": {
                            "type": "string",
                            "description": "NMLS number to set"
                        }
                    }
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "schedule_appointment",
                "description": "Schedule a meeting or appointment. Call this when user asks to 'schedule a call', 'set up a meeting', 'book an appointment', etc.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "title": {
                            "type": "string",
                            "description": "Title of the appointment"
                        },
                        "attendee_name": {
                            "type": "string",
                            "description": "Name of the person to meet with"
                        },
                        "date_time": {
                            "type": "string",
                            "description": "Date and time for the appointment (e.g., 'tomorrow at 2pm', '2025-12-01T14:00:00')"
                        },
                        "duration_minutes": {
                            "type": "integer",
                            "description": "Duration in minutes (default 30)"
                        },
                        "notes": {
                            "type": "string",
                            "description": "Additional notes for the appointment"
                        }
                    },
                    "required": ["title", "date_time"]
                }
            }
        }
    ]


# =============================================================================
# Routes
# =============================================================================

@router.post("/ai/chat", response_model=ConversationResponse)
async def ai_chat(
    conversation: ConversationCreate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_dep())
):
    """AI Assistant chat endpoint with agentic function calling capabilities"""

    openai_client = get_openai_client()
    if not openai_client:
        raise HTTPException(status_code=503, detail="OpenAI API key not configured")

    models = get_models()
    Lead = models['Lead']
    Loan = models['Loan']
    Conversation = models['Conversation']

    # Build context from lead or loan if provided
    context_info = ""
    context_lead = None
    context_loan = None

    if conversation.lead_id:
        context_lead = db.query(Lead).filter(Lead.id == conversation.lead_id).first()
        if context_lead:
            context_info = f"Lead: {context_lead.name}, Stage: {context_lead.stage.value}, Score: {context_lead.ai_score}, Credit: {context_lead.credit_score}"

    if conversation.loan_id:
        context_loan = db.query(Loan).filter(Loan.id == conversation.loan_id).first()
        if context_loan:
            context_info = f"Loan: {context_loan.loan_number}, Borrower: {context_loan.borrower_name}, Stage: {str(context_loan.stage)}, Amount: ${context_loan.amount:,.0f}"

    # Define available functions for AI to call
    tools = get_ai_tools()

    # Get conversation history for context
    history = db.query(Conversation).filter(
        Conversation.user_id == current_user.id
    ).order_by(Conversation.created_at.desc()).limit(5).all()

    # Build messages for OpenAI
    messages = [
        {
            "role": "system",
            "content": f"""You are an agentic AI assistant for a mortgage CRM system. You can autonomously execute actions to help loan officers.

Current user: {current_user.full_name or current_user.email}
{f'Context: {context_info}' if context_info else ''}

## ACTION TOOLS - YOU MUST CALL THESE WHEN REQUESTED
CRITICAL: When a user asks you to SEND a text, SEND an email, SCHEDULE a meeting, or PERFORM any action - YOU MUST CALL THE APPROPRIATE TOOL AND EXECUTE IT. DO NOT tell them how to do it manually. YOU HAVE THE CAPABILITY.

Available action tools:
- **send_sms**: Send SMS text messages. Call this when user says "send a text", "text them", "SMS", etc. You can look up phone by name.
- **update_user_profile**: Update user profile info (phone, title, NMLS). Call this when user says "update profile", "add phone number", etc.
- **schedule_appointment**: Schedule meetings/calls. Call this when user says "schedule a call", "set up a meeting", "book appointment".
- **create_task**: Create tasks and reminders
- **update_lead_stage**: Update a lead's pipeline stage
- **add_activity**: Add notes and activities

## INFORMATION TOOLS
- **get_lead_details**: Get detailed lead information
- **get_high_priority_leads**: Get priority leads
- **search_leads**: Search for leads by name/email
- **get_lead_stats**: Get pipeline statistics

## CRITICAL RULES
1. When user says "send a text to [name]" -> CALL send_sms with recipient_name and message
2. When user says "schedule a call with [name]" -> CALL schedule_appointment
3. When user says "update [name]'s profile" -> CALL update_user_profile
4. NEVER say "I can't send texts" or "I don't have that capability" - YOU DO. USE THE TOOLS.
5. ALWAYS execute the action, then confirm what you did.

Be proactive, professional, and action-oriented. When asked to perform an action, DO IT immediately."""
        }
    ]

    # Add recent history
    for msg in reversed(history):
        messages.append({"role": "user", "content": msg.message})
        if msg.response:
            messages.append({"role": "assistant", "content": msg.response})

    # Add current message
    messages.append({"role": "user", "content": conversation.message})

    try:
        # Call OpenAI with function calling
        response = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            tools=tools,
            tool_choice="auto",
            temperature=0.7,
            max_tokens=1000
        )

        response_message = response.choices[0].message
        tool_calls = response_message.tool_calls
        actions_taken = []

        # Execute any function calls
        if tool_calls:
            messages.append(response_message)

            for tool_call in tool_calls:
                function_name = tool_call.function.name
                function_args = json.loads(tool_call.function.arguments)

                logger.info(f"AI calling function: {function_name} with args: {function_args}")

                # Execute the function
                function_response = await execute_ai_function(
                    function_name,
                    function_args,
                    db,
                    current_user,
                    context_lead,
                    context_loan
                )

                actions_taken.append({
                    "function": function_name,
                    "args": function_args,
                    "result": function_response
                })

                # Add function response to messages
                messages.append({
                    "tool_call_id": tool_call.id,
                    "role": "tool",
                    "name": function_name,
                    "content": json.dumps(function_response)
                })

            # Get final response from AI after function execution
            second_response = openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=messages,
                temperature=0.7,
                max_tokens=500
            )

            ai_response = second_response.choices[0].message.content
        else:
            ai_response = response_message.content

        # Save conversation with actions metadata
        metadata = conversation.context or {}
        if actions_taken:
            metadata["actions_taken"] = actions_taken

        db_conversation = Conversation(
            user_id=current_user.id,
            lead_id=conversation.lead_id,
            loan_id=conversation.loan_id,
            message=conversation.message,
            response=ai_response,
            role="user",
            metadata=metadata
        )
        db.add(db_conversation)

        # Save assistant response
        db_assistant = Conversation(
            user_id=current_user.id,
            lead_id=conversation.lead_id,
            loan_id=conversation.loan_id,
            message=ai_response,
            role="assistant",
            metadata={"actions": actions_taken} if actions_taken else None
        )
        db.add(db_assistant)

        db.commit()
        db.refresh(db_conversation)

        logger.info(f"AI chat completed for user {current_user.id}. Actions taken: {len(actions_taken)}")
        return db_conversation

    except Exception as e:
        logger.error(f"OpenAI API error: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail="AI service error")


@router.get("/conversations", response_model=List[ConversationResponse])
async def get_conversations(
    skip: int = 0,
    limit: int = 50,
    lead_id: Optional[int] = None,
    loan_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_dep())
):
    """Get conversation history"""

    models = get_models()
    Conversation = models['Conversation']

    query = db.query(Conversation).filter(Conversation.user_id == current_user.id)

    if lead_id:
        query = query.filter(Conversation.lead_id == lead_id)
    if loan_id:
        query = query.filter(Conversation.loan_id == loan_id)

    conversations = query.order_by(Conversation.created_at.desc()).offset(skip).limit(limit).all()
    return conversations


@router.post("/ai/complete-task")
async def ai_complete_task(
    task_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_dep())
):
    """Use AI to suggest task completion"""

    openai_client = get_openai_client()
    if not openai_client:
        raise HTTPException(status_code=503, detail="OpenAI API key not configured")

    models = get_models()
    AITask = models['AITask']
    Loan = models['Loan']

    task = db.query(AITask).filter(
        AITask.id == task_id,
        AITask.assigned_to_id == current_user.id
    ).first()

    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    try:
        # Get context
        context = f"Task: {task.title}\nDescription: {task.description or 'N/A'}\nPriority: {task.priority}"

        if task.loan_id:
            loan = db.query(Loan).filter(Loan.id == task.loan_id).first()
            if loan:
                context += f"\nLoan: {loan.loan_number}, Stage: {str(loan.stage)}"

        # Ask AI for completion suggestion
        response = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": "You are a helpful assistant for mortgage loan officers. Suggest a brief completion action for the given task."
                },
                {
                    "role": "user",
                    "content": f"Suggest how to complete this task:\n{context}"
                }
            ],
            temperature=0.7,
            max_tokens=200
        )

        suggestion = response.choices[0].message.content

        return {
            "task_id": task_id,
            "suggestion": suggestion,
            "confidence": 85
        }

    except Exception as e:
        logger.error(f"AI task completion error: {e}")
        raise HTTPException(status_code=500, detail="AI service error")
