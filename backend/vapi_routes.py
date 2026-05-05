"""
Vapi AI Receptionist - FastAPI Routes
Webhook handlers and API endpoints
"""
from fastapi import APIRouter, Depends, HTTPException, Request, BackgroundTasks, Header
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from typing import Dict, Any, List, Optional
from pydantic import BaseModel
from datetime import datetime, timedelta
import logging

from database import get_db
from vapi_service import VapiService, VapiCRMIntegration
from vapi_models import VapiCall, VapiCallNote, VapiAssistant
from middleware.webhook_verification import require_vapi_webhook
import os
import json
import secrets

try:
    from utils.pii_mask import mask_phone
except ImportError:
    mask_phone = lambda x: x[:3] + "***" + x[-2:] if x and len(x) > 5 else "***"

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/vapi", tags=["vapi"])


def _resolve_org_id_from_assistant(db: Session, data: dict) -> Optional[int]:
    """Resolve organization_id from Vapi webhook payload via assistant lookup."""
    assistant_id = (
        data.get("assistant_id")
        or data.get("assistantId")
        or (data.get("call", {}) or {}).get("assistantId")
        or (data.get("message", {}) or {}).get("call", {}).get("assistantId")
    )
    if assistant_id:
        assistant = db.query(VapiAssistant).filter(
            VapiAssistant.assistant_id == assistant_id
        ).first()
        if assistant and getattr(assistant, "organization_id", None):
            return assistant.organization_id
    logger.warning(
        "TENANT-ISOLATION: Could not resolve org_id from webhook payload (assistant_id=%s)",
        assistant_id,
    )
    return None

# Backward compatibility alias — existing routes may reference verify_vapi_request
verify_vapi_request = require_vapi_webhook


def get_current_user_flexible():
    """Lazy import auth dependency"""
    from auth.dependencies import get_current_user_flexible as _get_current_user_flexible
    return _get_current_user_flexible


async def verify_admin_access(
    x_admin_key: Optional[str] = Header(None),
    authorization: Optional[str] = Header(None)
):
    """
    Verify admin access for diagnostic endpoints.
    Requires either:
    1. X-Admin-Key header matching MIGRATION_ADMIN_KEY env var
    2. Valid admin user token (checks is_admin flag)
    """
    from database import SessionLocal
    from sqlalchemy import text

    admin_key = os.getenv("MIGRATION_ADMIN_KEY")

    # Option 1: Check admin key header
    if admin_key and x_admin_key and secrets.compare_digest(x_admin_key, admin_key):
        return True

    # Option 2: Check for authenticated admin user via JWT token
    if authorization and authorization.startswith("Bearer "):
        try:
            from auth.tokens import verify_access_token

            token = authorization.replace("Bearer ", "")

            try:
                payload = verify_access_token(token)
                if payload:
                    email = payload.get("sub")

                    if email:
                        db = SessionLocal()
                        try:
                            result = db.execute(text("""
                                SELECT u.id, u.is_admin, u.role
                                FROM users u
                                WHERE u.email = :email
                            """), {"email": email}).fetchone()

                            if result and (result[1] or result[2] in ('admin', 'site_admin')):
                                return True
                        finally:
                            db.close()
            except Exception as e:
                logger.warning(f"JWT decode failed: {e}")

        except Exception as e:
            logger.warning(f"Admin auth check failed: {e}")

    raise HTTPException(
        status_code=403,
        detail="Admin access required. Provide X-Admin-Key header or authenticate as admin user."
    )


# Pydantic Models
class VapiWebhookPayload(BaseModel):
    """Vapi webhook payload"""
    message: Dict[str, Any]


class CallResponse(BaseModel):
    """Call response model"""
    id: int
    vapi_call_id: str
    phone_number: Optional[str] = None
    caller_name: Optional[str] = None
    status: str
    duration: Optional[int] = None
    summary: Optional[str] = None
    transcript: Optional[str] = None
    sentiment: Optional[str] = None
    lead_id: Optional[int] = None
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class CreateOutboundCallRequest(BaseModel):
    """Request to create outbound call"""
    lead_id: int
    assistant_id: str
    purpose: Optional[str] = "follow_up"


class AssistantConfigRequest(BaseModel):
    """Create/Update assistant configuration"""
    name: str
    first_message: str
    system_prompt: str
    voice_id: Optional[str] = "b7d50908-b17c-442d-ad8d-810c63997ed9"
    language: Optional[str] = "en"


# Webhook Endpoints (Authenticated via Vapi secret)
@router.post("/webhook")
async def vapi_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    _: bool = Depends(verify_vapi_request)
):
    """
    Main Vapi webhook endpoint.
    Handles all webhook events from Vapi including assistant-request,
    function-call, status-update, and end-of-call-report.
    """
    try:
        payload = await request.json()
        message = payload.get("message", {})
        message_type = message.get("type", "")
        logger.info(f"Vapi webhook received: {message_type}")

        if message_type == "assistant-request":
            return _build_assistant_response(db, message)

        background_tasks.add_task(process_webhook_background, payload)

        return JSONResponse(
            status_code=200,
            content={"status": "received"}
        )

    except Exception as e:
        logger.error(f"Webhook error: {str(e)}")
        return JSONResponse(
            status_code=200,
            content={"status": "error", "message": "Webhook processing error"}
        )


def _build_assistant_response(db: Session, message: dict) -> dict:
    """Build a full assistant config response for Vapi assistant-request."""
    call_data = message.get("call", {})
    customer_phone = call_data.get("customer", {}).get("number", "")

    # Resolve company name dynamically from the org that owns this phone number
    from services.company_name_resolver import resolve_company_name
    org_id = _resolve_org_id_from_assistant(db, message)
    company_name = resolve_company_name(db, org_id)

    first_message = f"Thank you for calling {company_name}. This is Aria. How may I help you today?"
    system_content = (
        f"You are Aria, the AI receptionist for {company_name} mortgage company.\n\n"
        + _ARIA_RECEPTIONIST_PROMPT_BODY
    )

    try:
        from database.models import Lead
        query = db.query(Lead).filter(Lead.phone == customer_phone)
        if org_id:
            query = query.filter(Lead.organization_id == org_id)
        lead = query.first()
        if lead:
            first_message = f"Hello {lead.first_name}! Thanks for calling back. How can I help you today?"
            system_content += f"\n\nCALLER CONTEXT: You are speaking with {lead.first_name} {lead.last_name}, an existing customer."
    except Exception as e:
        logger.warning(f"Could not fetch lead data for assistant-request: {e}")

    server_base = os.getenv("API_BASE_URL", "https://api.perenniaai.com")

    return {
        "assistant": {
            "firstMessage": first_message,
            "model": {
                "model": "gpt-4o",
                "provider": "openai",
                "temperature": 0.7,
                "messages": [{"role": "system", "content": system_content}],
                "tools": _build_tools(server_base),
            },
            "voice": {
                "provider": "cartesia",
                "voiceId": "b7d50908-b17c-442d-ad8d-810c63997ed9",
            },
            "transcriber": {
                "provider": "deepgram",
                "model": "nova-2",
                "language": "en",
                "endpointing": 255,
            },
            "endCallMessage": "Thank you for calling. Have a great day!",
            "recordingEnabled": True,
            "silenceTimeoutSeconds": 30,
            "maxDurationSeconds": 1800,
            "responseDelaySeconds": 0.4,
            "llmRequestDelaySeconds": 0.1,
            "numWordsToInterruptAssistant": 2,
            "serverUrl": f"{server_base}/api/vapi/webhook",
        }
    }


def _build_tools(server_base: str) -> list:
    """Build the Vapi tool definitions with correct server URLs."""
    def _tool(name, description, params, required=None):
        return {
            "type": "function",
            "async": False,
            "function": {
                "name": name,
                "description": description,
                "parameters": {
                    "type": "object",
                    "properties": params,
                    "required": required or [],
                },
            },
            "server": {"url": f"{server_base}/api/vapi/functions/{name.replace('_', '-')}"},
        }

    return [
        _tool("identify_caller",
              "Identify caller by phone number to check if they're an existing customer. Call at START of every call.",
              {"phone_number": {"type": "string", "description": "The caller's phone number"}},
              ["phone_number"]),
        _tool("transfer_to_production_assistant",
              "Transfer call to Production Assistant. Use for new leads, active loans, and general inquiries.",
              {
                  "vapi_call_id": {"type": "string", "description": "Current Vapi call ID"},
                  "caller_name": {"type": "string", "description": "Caller's full name"},
                  "caller_phone": {"type": "string", "description": "Caller's phone number"},
                  "reason": {"type": "string", "description": "Reason for call"},
                  "caller_type": {"type": "string", "enum": ["new_lead", "active_loan", "existing_client", "prospect"]},
                  "additional_context": {"type": "string", "description": "Additional context"},
              },
              ["vapi_call_id", "caller_name", "caller_phone", "reason", "caller_type"]),
        _tool("transfer_to_loan_officer",
              "Transfer to Loan Officer. ONLY for CRITICAL emergencies.",
              {
                  "vapi_call_id": {"type": "string"},
                  "caller_name": {"type": "string"},
                  "caller_phone": {"type": "string"},
                  "urgency_reason": {"type": "string"},
                  "additional_context": {"type": "string"},
              },
              ["vapi_call_id", "caller_name", "caller_phone", "urgency_reason"]),
        _tool("transfer_to_processor",
              "Transfer to Processor for processing/documentation questions.",
              {
                  "vapi_call_id": {"type": "string"},
                  "caller_name": {"type": "string"},
                  "caller_phone": {"type": "string"},
                  "reason": {"type": "string"},
                  "loan_number": {"type": "string", "description": "Loan number if mentioned"},
                  "additional_context": {"type": "string"},
              },
              ["vapi_call_id", "caller_name", "caller_phone", "reason"]),
        _tool("create_task",
              "Create a callback task when caller requests follow-up.",
              {
                  "phone_number": {"type": "string"},
                  "title": {"type": "string"},
                  "description": {"type": "string"},
                  "priority": {"type": "string", "enum": ["low", "medium", "high"]},
              },
              ["phone_number", "title"]),
        _tool("schedule_appointment",
              "Book a PHONE appointment. We only offer phone appointments.",
              {
                  "phone_number": {"type": "string"},
                  "type": {"type": "string", "enum": ["Call"]},
                  "appointment_time": {"type": "string"},
                  "notes": {"type": "string"},
              },
              ["phone_number", "type"]),
        _tool("get_available_time_slots",
              "Check available phone appointment times.",
              {"date": {"type": "string", "description": "YYYY-MM-DD"}}),
        _tool("submit_preapproval_application",
              "Submit a pre-approval application collected over the phone.",
              {
                  "phone_number": {"type": "string"},
                  "first_name": {"type": "string"},
                  "last_name": {"type": "string"},
                  "email": {"type": "string"},
                  "location": {"type": "string"},
                  "price_target": {"type": "string"},
                  "down_payment": {"type": "string"},
                  "household_income": {"type": "string"},
                  "credit_range": {"type": "string", "enum": ["760+", "740-759", "700-739", "660-699", "620-659", "<620", "Unsure"]},
                  "employment_type": {"type": "string"},
                  "first_time_buyer": {"type": "string"},
                  "timeframe": {"type": "string"},
              },
              ["phone_number", "first_name", "last_name"]),
        _tool("schedule_calendly_appointment",
              "Provide Calendly scheduling link for discovery call.",
              {
                  "phone_number": {"type": "string"},
                  "name": {"type": "string"},
                  "email": {"type": "string"},
              },
              ["phone_number"]),
        _tool("get_lead_info",
              "Look up a lead by phone number to get their CRM profile, loan details, stage, and notes.",
              {"phone_number": {"type": "string", "description": "The caller's phone number"}},
              ["phone_number"]),
        _tool("update_lead_status",
              "Update a lead's stage and add notes after the conversation progresses them. Use after qualifying, scheduling, or collecting application info.",
              {
                  "phone_number": {"type": "string", "description": "The lead's phone number"},
                  "stage": {"type": "string", "description": "New stage: New, Attempted Contact, Prospect, Pre-Qualified, Pre-Approved, Application"},
                  "notes": {"type": "string", "description": "Call summary or notes to append"},
              },
              ["phone_number"]),
    ]


_ARIA_RECEPTIONIST_PROMPT_BODY = (
    "CRITICAL CONVERSATION RULES - FOLLOW EXACTLY:\n"
    "- Ask ONLY ONE question at a time. NEVER ask two questions in the same response.\n"
    "- After asking a question, STOP talking immediately and wait for the caller to answer.\n"
    "- Keep responses SHORT - maximum 2-3 sentences.\n"
    "- Be conversational and friendly, not robotic.\n\n"
    "Your job:\n"
    "- Greet callers warmly\n"
    "- Identify and route calls to the appropriate team member\n"
    "- Help with pre-approval applications over the phone\n"
    "- Schedule PHONE appointments only (never video or in-person)\n"
    "- Answer questions about mortgage products\n"
    "- Create callback tasks when needed\n\n"
    "Mortgage products: Conventional, FHA, VA, USDA, Jumbo, Refinancing, Home equity lines.\n\n"
    "ROUTING RULES:\n"
    "1. At call start: get name and phone, call identify_caller\n"
    "2. New leads / active loans: transfer_to_production_assistant\n"
    "3. Loan Officer requests: LO is ALWAYS in appointments — offer Production Assistant or schedule callback\n"
    "4. Processing/doc questions: transfer_to_processor\n"
    "5. Appointments: get_available_time_slots then schedule_appointment (phone only)\n"
    "6. Pre-approval: collect info one question at a time, then submit_preapproval_application\n\n"
    "Conversation style: one question at a time, natural, patient, no jargon."
)

_ARIA_RECEPTIONIST_PROMPT = (
    "You are Aria, the AI receptionist for The Tim Loss Team mortgage company.\n\n"
    + _ARIA_RECEPTIONIST_PROMPT_BODY
)


async def process_webhook_background(payload: Dict[str, Any]):
    """Process webhook in background task - creates its own db session"""
    from database import SessionLocal
    db = SessionLocal()
    try:
        integration = VapiCRMIntegration(db)
        await integration.process_call_webhook(payload)
        db.commit()
        logger.info("Webhook processed successfully")
    except Exception as e:
        db.rollback()
        logger.error(f"Background webhook processing error: {str(e)}")
    finally:
        db.close()


@router.post("/webhook/assistant-request")
async def assistant_request_webhook(
    request: Request,
    db: Session = Depends(get_db),
    _: bool = Depends(verify_vapi_request)
):
    """
    Handle assistant-request webhook
    Used to provide dynamic assistant configuration per call
    """
    try:
        payload = await request.json()
        call_data = payload.get("message", {}).get("call", {})
        phone_number = call_data.get("phoneNumber")

        logger.info("Assistant request received for inbound call")

        # Customize assistant behavior based on caller
        try:
            from database.models import Lead
            # TENANT-001: Scope phone lookup to the organization associated with
            # the Vapi assistant (derived from the call's assistant metadata).
            org_id = None
            assistant_id = call_data.get("assistantId")
            if assistant_id:
                assistant = db.query(VapiAssistant).filter(VapiAssistant.assistant_id == assistant_id).first()
                if assistant:
                    org_id = getattr(assistant, 'organization_id', None)
            query = db.query(Lead).filter(Lead.phone == phone_number)
            if org_id:
                query = query.filter(Lead.organization_id == org_id)
            lead = query.first()

            if lead:
                # Existing customer
                return {
                    "assistant": {
                        "firstMessage": f"Hello {lead.first_name}! Thanks for calling back. How can I help you today?",
                        "model": {
                            "messages": [{
                                "role": "system",
                                "content": f"You are speaking with {lead.first_name} {lead.last_name}, an existing customer. Be warm and personalized."
                            }]
                        }
                    }
                }
        except Exception as e:
            logger.warning(f"Could not fetch lead data: {e}")

        # New caller
        return {
            "assistant": {
                "firstMessage": "Hello! Thank you for calling CMG Home Loans. I'm your AI assistant. How can I help you today?",
                "model": {
                    "messages": [{
                        "role": "system",
                        "content": "You are a professional mortgage company receptionist. Be welcoming and gather their information politely."
                    }]
                }
            }
        }

    except Exception as e:
        logger.error(f"Assistant request error: {str(e)}")
        return JSONResponse(status_code=200, content={})


# ============================================================================
# FUNCTION CALLING ENDPOINTS (Called by Vapi during conversations)
# All endpoints authenticated via verify_vapi_request
# ============================================================================

@router.post("/functions/get-lead-info")
async def get_lead_info_function(
    request: Request,
    db: Session = Depends(get_db),
    _: bool = Depends(verify_vapi_request)
):
    """
    Get lead information by phone number
    Called by Vapi to personalize conversation
    """
    try:
        from database.models import Lead
        from sqlalchemy import or_

        data = await request.json()
        phone = data.get("phone_number")

        if not phone:
            return {"success": False, "error": "Phone number required"}

        org_id = _resolve_org_id_from_assistant(db, data)

        # Clean phone number (remove formatting)
        phone_clean = ''.join(filter(str.isdigit, phone))

        # Search for lead by phone (scoped to org)
        query = db.query(Lead).filter(
            or_(
                Lead.phone == phone,
                Lead.phone.contains(phone_clean[-10:])
            )
        )
        if org_id:
            query = query.filter(Lead.organization_id == org_id)
        lead = query.first()

        if not lead:
            return {
                "success": True,
                "found": False,
                "message": "No existing lead found"
            }

        return {
            "success": True,
            "found": True,
            "lead": {
                "id": lead.id,
                "name": lead.name,
                "email": lead.email,
                "phone": lead.phone,
                "stage": lead.stage.value if hasattr(lead.stage, 'value') else (lead.stage or "New"),
                "source": lead.source,
                "loan_type": lead.loan_type,
                "preapproval_amount": float(lead.preapproval_amount) if lead.preapproval_amount else None,
                "credit_score": lead.credit_score,
                "notes": lead.notes
            }
        }

    except Exception as e:
        logger.error(f"Error in get_lead_info_function: {e}")
        return {"success": False, "error": "Internal server error"}


@router.post("/functions/update-lead-status")
async def update_lead_status_function(
    request: Request,
    db: Session = Depends(get_db),
    _: bool = Depends(verify_vapi_request)
):
    """
    Update lead status/stage
    Called by Vapi when conversation progresses the lead
    """
    try:
        from database.models import Lead
        from sqlalchemy import or_
        from datetime import datetime, timezone

        data = await request.json()
        phone = data.get("phone_number")
        new_stage = data.get("stage")  # e.g., "Prospect", "Application Started"
        notes = data.get("notes", "")

        if not phone:
            return {"success": False, "error": "Phone number required"}

        org_id = _resolve_org_id_from_assistant(db, data)

        # Clean phone number
        phone_clean = ''.join(filter(str.isdigit, phone))

        # Find lead (scoped to org)
        query = db.query(Lead).filter(
            or_(
                Lead.phone == phone,
                Lead.phone.contains(phone_clean[-10:])
            )
        )
        if org_id:
            query = query.filter(Lead.organization_id == org_id)
        lead = query.first()

        if not lead:
            return {"success": False, "error": "Lead not found"}

        # Update stage if provided (stage is VARCHAR, direct assignment)
        if new_stage:
            valid_stages = {
                "new": "New",
                "attempted contact": "Attempted Contact",
                "prospect": "Prospect",
                "pre-qualified": "Pre-Qualified",
                "pre-approved": "Pre-Approved",
                "application": "Application",
                "long-term nurture": "Long-Term Nurture",
                "credit repair": "Credit Repair",
                "do not call": "Do Not Call",
            }
            stage_key = new_stage.lower().strip()
            if stage_key in valid_stages:
                lead.stage = valid_stages[stage_key]
            else:
                lead.stage = new_stage

        # Append notes
        if notes:
            timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
            new_note = f"\n[{timestamp}] AI Call: {notes}"
            lead.notes = (lead.notes or "") + new_note

        lead.last_contact = datetime.now(timezone.utc)
        lead.updated_at = datetime.now(timezone.utc)

        db.commit()
        db.refresh(lead)

        return {
            "success": True,
            "message": "Lead updated successfully",
            "lead_id": lead.id,
            "current_stage": lead.stage.value if hasattr(lead.stage, 'value') else (lead.stage or None)
        }

    except Exception as e:
        logger.error(f"Error in update_lead_status_function: {e}")
        db.rollback()
        return {"success": False, "error": "Internal server error"}


@router.post("/functions/create-task")
async def create_task_function(
    request: Request,
    db: Session = Depends(get_db),
    _: bool = Depends(verify_vapi_request)
):
    """
    Create a follow-up task
    Called by Vapi when action items are identified
    If priority is high, sends SMS notification to task owner
    """
    try:
        from database.models import Task, Lead, User
        from sqlalchemy import or_
        from datetime import datetime, timezone, timedelta
        data = await request.json()
        phone = data.get("phone_number")
        title = data.get("title")
        description = data.get("description", "")
        priority = data.get("priority", "medium")  # low, medium, high
        due_date_str = data.get("due_date")  # ISO format string

        if not phone or not title:
            return {"success": False, "error": "Phone number and title required"}

        org_id = _resolve_org_id_from_assistant(db, data)

        # Clean phone number
        phone_clean = ''.join(filter(str.isdigit, phone))

        # Find lead (scoped to org)
        query = db.query(Lead).filter(
            or_(
                Lead.phone == phone,
                Lead.phone.contains(phone_clean[-10:])
            )
        )
        if org_id:
            query = query.filter(Lead.organization_id == org_id)
        lead = query.first()

        if not lead:
            return {"success": False, "error": "Lead not found"}

        # Parse due date if provided
        due_date = None
        if due_date_str:
            try:
                due_date = datetime.fromisoformat(due_date_str.replace('Z', '+00:00'))
            except (ValueError, TypeError):
                # Default to 24 hours from now if parsing fails
                due_date = datetime.now(timezone.utc) + timedelta(days=1)
        else:
            # Default to 24 hours from now
            due_date = datetime.now(timezone.utc) + timedelta(days=1)

        # Create task
        task = Task(
            title=title,
            description=description,
            status="pending",
            priority=priority,
            due_date=due_date,
            lead_id=lead.id,
            owner_id=lead.owner_id,
            related_contact_name=lead.name,
            related_type="lead"
        )

        db.add(task)
        db.commit()
        db.refresh(task)

        # Send SMS notification if urgent (high priority)
        sms_sent = False
        if priority == "high":
            try:
                # Get task owner's phone number
                owner = db.query(User).filter(User.id == lead.owner_id).first()
                if owner and owner.user_metadata:
                    owner_phone = owner.user_metadata.get("phone")
                    if owner_phone:
                        # Initialize SMS client
                        from integrations.sms_service import get_sms_client
                        sms_client = get_sms_client(db=db)

                        # Create urgent notification message
                        caller_name = lead.name or "Unknown caller"
                        sms_message = f"🚨 URGENT: {caller_name} needs immediate callback.\n\nReason: {title}\n\n{description}\n\nView task in CRM: https://perenniaai.com/tasks"

                        # Send SMS
                        send_result = sms_client.send_sms(
                            to_phone=owner_phone,
                            message=sms_message
                        )

                        if send_result.get("success"):
                            sms_sent = True
                            logger.info(f"Urgent task SMS sent. ID: {send_result.get('message_id')}")
                        else:
                            logger.warning(f"Failed to send urgent task SMS: {send_result.get('error')}")
            except Exception as sms_error:
                # Log error but don't fail the task creation
                logger.error(f"Error sending urgent task SMS: {sms_error}")

        response_message = "I've notified them immediately. They'll call you back shortly." if sms_sent and priority == "high" else "Task created successfully"

        return {
            "success": True,
            "message": response_message,
            "task_id": task.id,
            "due_date": task.due_date.isoformat() if task.due_date else None,
            "sms_sent": sms_sent
        }

    except Exception as e:
        logger.error(f"Error in create_task_function: {e}")
        db.rollback()
        return {"success": False, "error": "Internal server error"}


@router.post("/functions/schedule-appointment")
async def schedule_appointment_function(
    request: Request,
    db: Session = Depends(get_db),
    _: bool = Depends(verify_vapi_request)
):
    """
    Schedule an appointment/meeting
    Called by Vapi when customer requests appointment
    """
    try:
        from database.enums import ActivityType
        from database.models import Activity, Lead, Task
        from sqlalchemy import or_
        from datetime import datetime, timezone

        data = await request.json()
        phone = data.get("phone_number")
        appointment_type = data.get("type", "Meeting")  # Meeting, Call, etc.
        appointment_time_str = data.get("appointment_time")
        notes = data.get("notes", "")

        if not phone:
            return {"success": False, "error": "Phone number required"}

        org_id = _resolve_org_id_from_assistant(db, data)

        # Clean phone number
        phone_clean = ''.join(filter(str.isdigit, phone))

        # Find lead (scoped to org)
        query = db.query(Lead).filter(
            or_(
                Lead.phone == phone,
                Lead.phone.contains(phone_clean[-10:])
            )
        )
        if org_id:
            query = query.filter(Lead.organization_id == org_id)
        lead = query.first()

        if not lead:
            return {"success": False, "error": "Lead not found"}

        # Parse appointment time
        appointment_time = None
        if appointment_time_str:
            try:
                appointment_time = datetime.fromisoformat(appointment_time_str.replace('Z', '+00:00'))
            except (ValueError, TypeError):
                pass  # Leave appointment_time as None if parsing fails

        # Map appointment type to ActivityType
        activity_type_map = {
            "meeting": ActivityType.MEETING,
            "call": ActivityType.CALL,
            "email": ActivityType.EMAIL,
        }

        activity_type = activity_type_map.get(appointment_type.lower(), ActivityType.MEETING)

        # Create activity
        content = f"Appointment scheduled via AI call"
        if notes:
            content += f": {notes}"
        if appointment_time:
            content += f" at {appointment_time.strftime('%Y-%m-%d %H:%M %Z')}"

        activity = Activity(
            type=activity_type,
            content=content,
            lead_id=lead.id,
            user_id=lead.owner_id,
            user_metadata={
                "scheduled_time": appointment_time.isoformat() if appointment_time else None,
                "appointment_type": appointment_type,
                "source": "vapi_ai_call"
            }
        )

        db.add(activity)

        # Also create a task for the appointment
        task = Task(
            title=f"{appointment_type}: {lead.name}",
            description=content,
            status="pending",
            priority="high",
            due_date=appointment_time,
            lead_id=lead.id,
            owner_id=lead.owner_id,
            related_contact_name=lead.name,
            related_type="appointment"
        )

        db.add(task)

        # Log appointment to AI Receptionist Dashboard
        from ai_receptionist_dashboard_models import AIReceptionistActivity
        import uuid as uuid_lib

        appointment_activity = AIReceptionistActivity(
            id=str(uuid_lib.uuid4()),
            timestamp=appointment_time or datetime.now(timezone.utc),
            client_phone=phone,
            client_name=lead.name if lead else None,
            action_type='appointment_booked',
            channel='voice',
            message_in=f"Appointment request: {appointment_type}",
            message_out=f"Scheduled {appointment_type} for {appointment_time.strftime('%Y-%m-%d %H:%M') if appointment_time else 'TBD'}",
            confidence_score=0.95,
            outcome_status='success',
            extra_data={
                'appointment_type': appointment_type,
                'scheduled_time': appointment_time.isoformat() if appointment_time else None,
                'task_id': task.id,
                'activity_id': activity.id,
                'notes': notes
            }
        )
        db.add(appointment_activity)

        db.commit()
        db.refresh(activity)
        db.refresh(task)
        db.refresh(appointment_activity)

        return {
            "success": True,
            "message": "Appointment scheduled successfully",
            "activity_id": activity.id,
            "task_id": task.id,
            "appointment_time": appointment_time.isoformat() if appointment_time else None
        }

    except Exception as e:
        logger.error(f"Error in schedule_appointment_function: {e}")
        db.rollback()
        return {"success": False, "error": "Internal server error"}


@router.post("/functions/get-available-time-slots")
async def available_time_slots_function(
    request: Request,
    db: Session = Depends(get_db),
    _: bool = Depends(verify_vapi_request)
):
    """
    Get available appointment time slots.
    Route name matches tool definition: get_available_time_slots → get-available-time-slots
    Vapi sends POST with JSON body containing function call args.
    """
    try:
        from datetime import datetime, timezone, timedelta

        data = {}
        try:
            data = await request.json()
        except Exception:
            pass
        date = data.get("date")

        if date:
            try:
                target_date = datetime.fromisoformat(date.replace('Z', '+00:00')).date()
            except (ValueError, TypeError):
                target_date = (datetime.now(timezone.utc) + timedelta(days=1)).date()
        else:
            target_date = (datetime.now(timezone.utc) + timedelta(days=1)).date()

        slots = []
        for day_offset in range(7):
            check_date = target_date + timedelta(days=day_offset)
            if check_date.weekday() >= 5:
                continue
            for hour in range(9, 17):
                slot_time = datetime.combine(
                    check_date,
                    datetime.min.time().replace(hour=hour)
                ).replace(tzinfo=timezone.utc)

                if slot_time > datetime.now(timezone.utc):
                    slots.append({
                        "time": slot_time.isoformat(),
                        "display": slot_time.strftime("%A, %B %d at %I:%M %p"),
                        "available": True
                    })

        return {
            "success": True,
            "date": target_date.isoformat(),
            "slots": slots[:20]
        }

    except Exception as e:
        logger.error(f"Error in available_time_slots_function: {e}")
        return {"success": False, "error": "Internal server error"}


@router.post("/functions/submit-preapproval-application")
async def submit_preapproval_application_function(
    request: Request,
    db: Session = Depends(get_db),
    _: bool = Depends(verify_vapi_request)
):
    """
    Submit pre-approval application collected over the phone
    Called by Vapi when customer wants to apply for pre-approval
    """
    try:
        from database.models import Lead, Task
        from sqlalchemy import or_
        from datetime import datetime, timezone

        data = await request.json()

        # Required fields
        phone = data.get("phone_number")
        first_name = data.get("first_name")
        last_name = data.get("last_name")
        email = data.get("email")

        if not phone or not first_name or not last_name:
            return {"success": False, "error": "Phone, first name, and last name are required"}

        org_id = _resolve_org_id_from_assistant(db, data)

        # Clean phone number
        phone_clean = ''.join(filter(str.isdigit, phone))

        # Find or create lead (scoped to org)
        query = db.query(Lead).filter(
            or_(
                Lead.phone == phone,
                Lead.phone.contains(phone_clean[-10:])
            )
        )
        if org_id:
            query = query.filter(Lead.organization_id == org_id)
        lead = query.first()

        if not lead:
            # Create new lead
            lead = Lead(
                first_name=first_name,
                last_name=last_name,
                name=f"{first_name} {last_name}",
                email=email,
                phone=phone,
                source="AI Phone Call",
                stage="Application Started",
                owner_id=1  # Default to first user
            )
            db.add(lead)
            db.flush()

            from services.client_file_service import ensure_client_file
            ensure_client_file(db, lead)
        else:
            # Update existing lead
            if email:
                lead.email = email
            lead.first_name = first_name
            lead.last_name = last_name
            lead.name = f"{first_name} {last_name}"
            if lead.stage in ["New", "Attempted Contact", "Prospect"]:
                lead.stage = "Application Started"

        # Collect application data
        application_data = {
            # Contact info
            "first_name": first_name,
            "last_name": last_name,
            "email": email or lead.email,
            "phone": phone,
            "preferred_contact": data.get("preferred_contact", "Phone"),

            # Scenario
            "occupancy": data.get("occupancy", "Primary Residence"),
            "timeframe": data.get("timeframe"),
            "location": data.get("location"),

            # Budget
            "price_target": data.get("price_target"),
            "down_payment": data.get("down_payment"),
            "monthly_comfort": data.get("monthly_comfort"),

            # Profile
            "credit_range": data.get("credit_range"),
            "first_time_buyer": data.get("first_time_buyer"),
            "va_eligible": data.get("va_eligible"),
            "employment_type": data.get("employment_type"),
            "household_income": data.get("household_income"),
            "employer": data.get("employer"),

            # Preferences
            "has_agent": data.get("has_agent"),
            "agent_name": data.get("agent_name"),
            "letter_type": data.get("letter_type", "Full Pre-Approval"),

            # Notes
            "notes": data.get("notes", "Application submitted via AI phone call"),
            "source": "AI Phone Call"
        }

        # Store application data in lead metadata
        if not lead.metadata:
            lead.metadata = {}
        lead.metadata["phone_application"] = application_data
        lead.metadata["application_date"] = datetime.now(timezone.utc).isoformat()

        # Create a task for the loan officer to review the application
        task = Task(
            title=f"Review Phone Pre-Approval Application: {lead.name}",
            description=f"Pre-approval application collected via AI phone call. Review and complete application in system.\n\nCollected information:\n" +
                       "\n".join([f"- {k.replace('_', ' ').title()}: {v}" for k, v in application_data.items() if v]),
            status="pending",
            priority="high",
            lead_id=lead.id,
            owner_id=lead.owner_id,
            related_contact_name=lead.name,
            related_type="application"
        )

        db.add(task)
        db.commit()
        db.refresh(lead)
        db.refresh(task)

        return {
            "success": True,
            "message": "Pre-approval application submitted successfully",
            "lead_id": lead.id,
            "task_id": task.id,
            "next_steps": "A loan officer will review your application and contact you within 24 hours"
        }

    except Exception as e:
        logger.error(f"Error in submit_preapproval_application_function: {e}")
        db.rollback()
        return {"success": False, "error": "Internal server error"}


@router.post("/functions/schedule-calendly-appointment")
async def schedule_calendly_appointment_function(
    request: Request,
    db: Session = Depends(get_db),
    _: bool = Depends(verify_vapi_request)
):
    """
    Provide Calendly link for scheduling discovery call.
    Called by Vapi when customer wants to schedule an appointment.

    Now automatically sends the Calendly link via SMS!
    """
    try:
        from database.enums import ActivityType
        from database.models import Lead, Task, Activity
        from sqlalchemy import or_
        from vapi_service import AIReceptionistSMSService

        data = await request.json()
        phone = data.get("phone_number")
        name = data.get("name", "")
        email = data.get("email", "")
        send_sms = data.get("send_sms", True)  # Default to sending SMS
        context = data.get("context", "discovery call")  # e.g., "pre-approval", "refinance"

        if not phone:
            return {"success": False, "error": "Phone number required"}

        org_id = _resolve_org_id_from_assistant(db, data)

        # Clean phone number
        phone_clean = ''.join(filter(str.isdigit, phone))

        # Find or create lead (scoped to org)
        query = db.query(Lead).filter(
            or_(
                Lead.phone == phone,
                Lead.phone.contains(phone_clean[-10:])
            )
        )
        if org_id:
            query = query.filter(Lead.organization_id == org_id)
        lead = query.first()

        if not lead and name:
            # Create new lead
            parts = name.split(' ', 1)
            first_name = parts[0]
            last_name = parts[1] if len(parts) > 1 else ""

            lead = Lead(
                first_name=first_name,
                last_name=last_name,
                name=name,
                email=email,
                phone=phone,
                source="AI Phone Call",
                stage="Prospect",
                owner_id=1
            )
            db.add(lead)
            db.flush()

            from services.client_file_service import ensure_client_file
            ensure_client_file(db, lead)

        # Calendly link (configured via environment variable)
        import os
        calendly_link = os.getenv("CALENDLY_LINK", "https://calendly.com/timloss/discovery-call")

        # Send SMS with Calendly link
        sms_sent = False
        sms_result = None
        if send_sms:
            try:
                sms_service = AIReceptionistSMSService(db)
                sms_result = await sms_service.send_calendly_link(
                    phone_number=phone,
                    caller_name=name or (lead.first_name if lead else None),
                    context=context
                )
                sms_sent = sms_result.get("success", False)
                logger.info(f"Calendly SMS sent to {mask_phone(phone)}: {sms_sent}")
            except Exception as sms_error:
                logger.error(f"Error sending Calendly SMS: {sms_error}")

        # Create activity
        if lead:
            activity = Activity(
                type=ActivityType.NOTE,
                content=f"Calendly link sent via AI call: {calendly_link}" + (f" (SMS sent)" if sms_sent else " (SMS failed)"),
                lead_id=lead.id,
                user_id=lead.owner_id
            )
            db.add(activity)
            db.commit()

        # Build response message based on SMS status
        if sms_sent:
            response_message = f"Perfect! I just sent you a text with the booking link. You'll receive it in just a moment. Is there anything else I can help you with?"
        else:
            response_message = f"I'd love to help you schedule a discovery call. Here's the link: {calendly_link}. You can book a time that works best for you. Would you like me to repeat that?"

        return {
            "success": True,
            "calendly_link": calendly_link,
            "sms_sent": sms_sent,
            "message": response_message
        }

    except Exception as e:
        logger.error(f"Error in schedule_calendly_appointment_function: {e}")
        db.rollback()
        return {"success": False, "error": "Internal server error"}


# ============================================================================
# CALL ROUTING & TRANSFER ENDPOINTS
# ============================================================================

@router.post("/functions/identify-caller")
async def identify_caller_function(
    request: Request,
    db: Session = Depends(get_db),
    _: bool = Depends(verify_vapi_request)
):
    """
    Identify caller and get routing recommendation
    Called by Vapi at start of call to personalize and route appropriately
    """
    try:
        data = await request.json()
        phone = data.get("phone_number")

        if not phone:
            return {"success": False, "error": "Phone number required"}

        integration = VapiCRMIntegration(db)
        result = await integration.identify_caller(phone)

        return {
            "success": True,
            **result
        }

    except Exception as e:
        logger.error(f"Error in identify_caller_function: {e}")
        return {"success": False, "error": "Internal server error"}


@router.post("/functions/transfer-to-production-assistant")
async def transfer_to_production_assistant_function(
    request: Request,
    db: Session = Depends(get_db),
    _: bool = Depends(verify_vapi_request)
):
    """
    Transfer call to Production Assistant with whisper context
    Called by Vapi when routing new leads or active loans
    """
    try:
        from vapi_models import StaffAvailability

        data = await request.json()
        vapi_call_id = data.get("vapi_call_id")
        caller_name = data.get("caller_name")
        caller_phone = data.get("caller_phone")
        reason = data.get("reason", "General inquiry")
        caller_type = data.get("caller_type", "new_lead")
        additional_context = data.get("additional_context", "")

        if not vapi_call_id or not caller_phone:
            return {"success": False, "error": "vapi_call_id and caller_phone required"}

        org_id = _resolve_org_id_from_assistant(db, data)

        # Find available Production Assistant (scoped to org)
        query = db.query(StaffAvailability).filter(
            StaffAvailability.role == 'production_assistant',
            StaffAvailability.available_for_calls == True,
            StaffAvailability.status == 'available'
        )
        if org_id:
            query = query.filter(StaffAvailability.organization_id == org_id)
        pa = query.first()

        if not pa:
            # Fallback: get first PA regardless of availability (still scoped)
            query = db.query(StaffAvailability).filter(
                StaffAvailability.role == 'production_assistant'
            )
            if org_id:
                query = query.filter(StaffAvailability.organization_id == org_id)
            pa = query.first()

        if not pa:
            return {
                "success": False,
                "error": "No Production Assistant configured",
                "fallback_action": "create_task"
            }

        # Prepare whisper data
        whisper_data = {
            "caller_name": caller_name,
            "caller_phone": caller_phone,
            "reason": reason,
            "caller_type": caller_type,
            "additional_context": additional_context,
            "urgency_level": "medium"
        }

        # Execute transfer
        integration = VapiCRMIntegration(db)
        result = await integration.transfer_call_with_whisper(
            vapi_call_id=vapi_call_id,
            recipient_user_id=pa.user_id,
            recipient_role="production_assistant",
            whisper_data=whisper_data
        )

        if result["success"]:
            return {
                "success": True,
                "message": f"Transferring you to our Production Assistant now. Please hold.",
                "transferred_to": "Production Assistant",
                **result
            }
        else:
            return {
                "success": False,
                "error": result.get("reason"),
                "message": "I'm sorry, the Production Assistant is currently unavailable. Let me create a callback task for you.",
                "fallback_action": result.get("fallback_action")
            }

    except Exception as e:
        logger.error(f"Error in transfer_to_production_assistant_function: {e}")
        db.rollback()
        return {"success": False, "error": "Internal server error"}


@router.post("/functions/transfer-to-loan-officer")
async def transfer_to_loan_officer_function(
    request: Request,
    db: Session = Depends(get_db),
    _: bool = Depends(verify_vapi_request)
):
    """
    Transfer call to Loan Officer with whisper context
    Called by Vapi for urgent situations or specific LO requests
    """
    try:
        from vapi_models import StaffAvailability

        data = await request.json()
        vapi_call_id = data.get("vapi_call_id")
        caller_name = data.get("caller_name")
        caller_phone = data.get("caller_phone")
        urgency_reason = data.get("urgency_reason", "Urgent client request")
        additional_context = data.get("additional_context", "")

        if not vapi_call_id or not caller_phone:
            return {"success": False, "error": "vapi_call_id and caller_phone required"}

        org_id = _resolve_org_id_from_assistant(db, data)

        # Find available Loan Officer (scoped to org)
        query = db.query(StaffAvailability).filter(
            StaffAvailability.role == 'loan_officer',
            StaffAvailability.available_for_calls == True,
            StaffAvailability.status == 'available'
        )
        if org_id:
            query = query.filter(StaffAvailability.organization_id == org_id)
        lo = query.first()

        if not lo:
            # Check if LO exists but unavailable (still scoped)
            query = db.query(StaffAvailability).filter(
                StaffAvailability.role == 'loan_officer'
            )
            if org_id:
                query = query.filter(StaffAvailability.organization_id == org_id)
            lo = query.first()

            if lo and not lo.available_for_calls:
                return {
                    "success": False,
                    "error": "Loan Officer is currently unavailable",
                    "message": "The Loan Officer is currently in an appointment. I can connect you with their Production Assistant who can help immediately, or schedule a callback.",
                    "fallback_action": "offer_pa_or_schedule"
                }

        if not lo:
            return {
                "success": False,
                "error": "No Loan Officer configured",
                "fallback_action": "create_urgent_task"
            }

        # Prepare whisper data
        whisper_data = {
            "caller_name": caller_name,
            "caller_phone": caller_phone,
            "reason": urgency_reason,
            "caller_type": "urgent_request",
            "additional_context": additional_context,
            "urgency_level": "high"
        }

        # Execute transfer
        integration = VapiCRMIntegration(db)
        result = await integration.transfer_call_with_whisper(
            vapi_call_id=vapi_call_id,
            recipient_user_id=lo.user_id,
            recipient_role="loan_officer",
            whisper_data=whisper_data
        )

        if result["success"]:
            return {
                "success": True,
                "message": f"Transferring you to the Loan Officer now. Please hold.",
                "transferred_to": "Loan Officer",
                **result
            }
        else:
            return {
                "success": False,
                "error": result.get("reason"),
                "message": "The Loan Officer is currently unavailable. Let me take your information and have them call you back as soon as possible.",
                "fallback_action": "create_urgent_task"
            }

    except Exception as e:
        logger.error(f"Error in transfer_to_loan_officer_function: {e}")
        db.rollback()
        return {"success": False, "error": "Internal server error"}


@router.post("/functions/transfer-to-processor")
async def transfer_to_processor_function(
    request: Request,
    db: Session = Depends(get_db),
    _: bool = Depends(verify_vapi_request)
):
    """
    Transfer call to Processor with whisper context
    Called by Vapi for processing/documentation questions
    """
    try:
        from vapi_models import StaffAvailability

        data = await request.json()
        vapi_call_id = data.get("vapi_call_id")
        caller_name = data.get("caller_name")
        caller_phone = data.get("caller_phone")
        reason = data.get("reason", "Processing question")
        loan_number = data.get("loan_number", "")
        additional_context = data.get("additional_context", "")

        if not vapi_call_id or not caller_phone:
            return {"success": False, "error": "vapi_call_id and caller_phone required"}

        org_id = _resolve_org_id_from_assistant(db, data)

        # Find available Processor (scoped to org)
        query = db.query(StaffAvailability).filter(
            StaffAvailability.role == 'processor',
            StaffAvailability.available_for_calls == True,
            StaffAvailability.status == 'available'
        )
        if org_id:
            query = query.filter(StaffAvailability.organization_id == org_id)
        processor = query.first()

        if not processor:
            # Fallback: get first processor (still scoped)
            query = db.query(StaffAvailability).filter(
                StaffAvailability.role == 'processor'
            )
            if org_id:
                query = query.filter(StaffAvailability.organization_id == org_id)
            processor = query.first()

        if not processor:
            return {
                "success": False,
                "error": "No Processor configured",
                "message": "Let me take your information and have our processor call you back.",
                "fallback_action": "create_task"
            }

        # Prepare whisper data
        context_msg = additional_context
        if loan_number:
            context_msg += f" Loan #: {loan_number}"

        whisper_data = {
            "caller_name": caller_name,
            "caller_phone": caller_phone,
            "reason": reason,
            "caller_type": "processing_inquiry",
            "additional_context": context_msg,
            "urgency_level": "medium"
        }

        # Execute transfer
        integration = VapiCRMIntegration(db)
        result = await integration.transfer_call_with_whisper(
            vapi_call_id=vapi_call_id,
            recipient_user_id=processor.user_id,
            recipient_role="processor",
            whisper_data=whisper_data
        )

        if result["success"]:
            return {
                "success": True,
                "message": f"Transferring you to our Processor now. Please hold.",
                "transferred_to": "Processor",
                **result
            }
        else:
            return {
                "success": False,
                "error": result.get("reason"),
                "message": "The Processor is currently unavailable. Let me create a callback task for you.",
                "fallback_action": result.get("fallback_action")
            }

    except Exception as e:
        logger.error(f"Error in transfer_to_processor_function: {e}")
        db.rollback()
        return {"success": False, "error": "Internal server error"}


# ============================================================================
# AUTHENTICATED CALL ROUTING MANAGEMENT ENDPOINTS
# ============================================================================

@router.get("/receptionist/available-staff")
async def get_available_staff(
    role: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_flexible)
):
    """Get list of staff available for call routing"""
    try:
        from vapi_models import StaffAvailability

        org_id = getattr(current_user, "organization_id", None)
        query = db.query(StaffAvailability).filter(
            StaffAvailability.available_for_calls == True
        )
        if org_id:
            query = query.filter(StaffAvailability.organization_id == org_id)

        if role:
            query = query.filter(StaffAvailability.role == role)

        staff = query.all()

        return {
            "success": True,
            "staff": [
                {
                    "user_id": s.user_id,
                    "role": s.role,
                    "status": s.status,
                    "primary_phone": s.primary_phone,
                    "department": s.department,
                    "current_call_count": s.current_call_count,
                    "max_concurrent_calls": s.max_concurrent_calls,
                    "out_of_office": s.out_of_office
                }
                for s in staff
            ]
        }

    except Exception as e:
        logger.error(f"Error getting available staff: {e}")
        return {"success": False, "error": "Internal server error"}


@router.get("/receptionist/routing-log")
async def get_routing_log(
    limit: int = 100,
    skip: int = 0,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_flexible)
):
    """Get call routing history"""
    try:
        from vapi_models import CallRoutingLog

        org_id = getattr(current_user, "organization_id", None)
        query = db.query(CallRoutingLog)
        if org_id:
            query = query.filter(CallRoutingLog.organization_id == org_id)
        logs = query.order_by(
            CallRoutingLog.created_at.desc()
        ).offset(skip).limit(limit).all()

        return {
            "success": True,
            "routing_logs": [
                {
                    "id": log.id,
                    "vapi_call_id": log.vapi_call_id,
                    "routing_decision": log.routing_decision,
                    "caller_type": log.caller_type,
                    "routed_to_role": log.routed_to_role,
                    "caller_name": log.caller_name,
                    "caller_phone": log.caller_phone,
                    "call_reason": log.call_reason,
                    "transfer_successful": log.transfer_successful,
                    "created_at": log.created_at.isoformat() if log.created_at else None
                }
                for log in logs
            ]
        }

    except Exception as e:
        logger.error(f"Error getting routing log: {e}")
        return {"success": False, "error": "Internal server error"}


@router.post("/receptionist/staff-availability")
async def update_staff_availability(
    request: Request,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_flexible)
):
    """Update staff availability for call routing"""
    try:
        from vapi_models import StaffAvailability

        data = await request.json()
        user_id = data.get("user_id")
        status = data.get("status")  # available, busy, offline, dnd
        available_for_calls = data.get("available_for_calls")

        if not user_id:
            return {"success": False, "error": "user_id required"}

        org_id = getattr(current_user, "organization_id", None)

        # Find or create staff availability record (scoped to org)
        query = db.query(StaffAvailability).filter(
            StaffAvailability.user_id == user_id
        )
        if org_id:
            query = query.filter(StaffAvailability.organization_id == org_id)
        staff = query.first()

        if not staff:
            # Create new record
            staff = StaffAvailability(
                user_id=user_id,
                status=status or 'available',
                available_for_calls=available_for_calls if available_for_calls is not None else True,
                role=data.get("role", "production_assistant"),
                primary_phone=data.get("primary_phone"),
                department=data.get("department")
            )
            db.add(staff)
        else:
            # Update existing
            if status:
                staff.status = status
            if available_for_calls is not None:
                staff.available_for_calls = available_for_calls
            if data.get("primary_phone"):
                staff.primary_phone = data.get("primary_phone")
            if data.get("out_of_office") is not None:
                staff.out_of_office = data.get("out_of_office")

        staff.updated_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(staff)

        return {
            "success": True,
            "message": "Staff availability updated",
            "staff": {
                "user_id": staff.user_id,
                "status": staff.status,
                "available_for_calls": staff.available_for_calls,
                "role": staff.role
            }
        }

    except Exception as e:
        logger.error(f"Error updating staff availability: {e}")
        db.rollback()
        return {"success": False, "error": "Internal server error"}


# Authenticated Endpoints
@router.get("/calls", response_model=List[CallResponse])
async def get_calls(
    skip: int = 0,
    limit: int = 100,
    status: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_flexible)
):
    """Get all Vapi calls with filtering"""
    org_id = getattr(current_user, "organization_id", None)
    query = db.query(VapiCall)
    if org_id:
        query = query.filter(VapiCall.organization_id == org_id)
    query = query.order_by(VapiCall.created_at.desc())

    if status:
        query = query.filter(VapiCall.status == status)

    calls = query.offset(skip).limit(limit).all()
    return calls


@router.get("/calls/{call_id}", response_model=CallResponse)
async def get_call(
    call_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_flexible)
):
    """Get specific call details"""
    org_id = getattr(current_user, "organization_id", None)
    query = db.query(VapiCall).filter(VapiCall.id == call_id)
    if org_id:
        query = query.filter(VapiCall.organization_id == org_id)
    call = query.first()
    if not call:
        raise HTTPException(status_code=404, detail="Call not found")
    return call


@router.get("/calls/{call_id}/transcript")
async def get_call_transcript(
    call_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_flexible)
):
    """Get formatted call transcript"""
    org_id = getattr(current_user, "organization_id", None)
    query = db.query(VapiCall).filter(VapiCall.id == call_id)
    if org_id:
        query = query.filter(VapiCall.organization_id == org_id)
    call = query.first()
    if not call:
        raise HTTPException(status_code=404, detail="Call not found")

    return {
        "call_id": call.id,
        "vapi_call_id": call.vapi_call_id,
        "phone_number": call.phone_number,
        "transcript": call.transcript,
        "summary": call.summary,
        "duration": call.duration,
        "sentiment": call.sentiment
    }


@router.get("/calls/{call_id}/notes")
async def get_call_notes(
    call_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_flexible)
):
    """Get action items and notes from call"""
    org_id = getattr(current_user, "organization_id", None)
    query = db.query(VapiCallNote).filter(
        VapiCallNote.call_id == call_id
    )
    if org_id:
        query = query.filter(VapiCallNote.organization_id == org_id)
    notes = query.all()

    return {
        "call_id": call_id,
        "notes": [
            {
                "id": note.id,
                "note_type": note.note_type,
                "content": note.content,
                "priority": note.priority,
                "completed": note.completed,
                "due_date": note.due_date.isoformat() if note.due_date else None,
                "created_at": note.created_at.isoformat() if note.created_at else None
            }
            for note in notes
        ]
    }


@router.post("/calls/outbound")
async def create_outbound_call(
    request: CreateOutboundCallRequest,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_flexible)
):
    """Initiate outbound call to a lead"""
    integration = VapiCRMIntegration(db)

    try:
        vapi_call = await integration.create_outbound_call(
            lead_id=request.lead_id,
            assistant_id=request.assistant_id,
            purpose=request.purpose
        )

        return {
            "success": True,
            "call_id": vapi_call.id,
            "vapi_call_id": vapi_call.vapi_call_id,
            "status": vapi_call.status
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail="Bad request")
    except Exception as e:
        logger.error(f"Outbound call error: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to create call")


@router.get("/stats/daily")
async def get_daily_stats(
    days: int = 30,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_flexible)
):
    """Get daily call statistics"""
    from sqlalchemy import func

    org_id = getattr(current_user, "organization_id", None)
    start_date = datetime.now(timezone.utc) - timedelta(days=days)

    query = db.query(
        func.date(VapiCall.created_at).label('date'),
        func.count(VapiCall.id).label('total_calls'),
        func.sum(VapiCall.duration).label('total_duration'),
        func.avg(VapiCall.duration).label('avg_duration')
    ).filter(
        VapiCall.created_at >= start_date
    )
    if org_id:
        query = query.filter(VapiCall.organization_id == org_id)
    stats = query.group_by(
        func.date(VapiCall.created_at)
    ).all()

    return {
        "period_days": days,
        "stats": [
            {
                "date": str(stat.date),
                "total_calls": stat.total_calls,
                "total_duration": stat.total_duration or 0,
                "avg_duration": float(stat.avg_duration) if stat.avg_duration else 0
            }
            for stat in stats
        ]
    }


@router.get("/stats/sentiment")
async def get_sentiment_analysis(
    days: int = 30,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_flexible)
):
    """Get sentiment analysis of calls"""
    from sqlalchemy import func

    org_id = getattr(current_user, "organization_id", None)
    start_date = datetime.now(timezone.utc) - timedelta(days=days)

    query = db.query(
        VapiCall.sentiment,
        func.count(VapiCall.id).label('count')
    ).filter(
        VapiCall.created_at >= start_date,
        VapiCall.sentiment.isnot(None)
    )
    if org_id:
        query = query.filter(VapiCall.organization_id == org_id)
    sentiment_stats = query.group_by(
        VapiCall.sentiment
    ).all()

    return {
        "period_days": days,
        "sentiment_distribution": {
            stat.sentiment: stat.count
            for stat in sentiment_stats
        }
    }


# Assistant Management
@router.post("/assistants")
async def create_assistant(
    config: AssistantConfigRequest,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_flexible)
):
    """Create new Vapi assistant"""
    vapi = VapiService()

    try:
        response = await vapi.create_assistant(
            name=config.name,
            first_message=config.first_message,
            system_prompt=config.system_prompt,
            voice_id=config.voice_id
        )

        # Save to database
        assistant = VapiAssistant(
            vapi_assistant_id=response.get("id"),
            name=config.name,
            first_message=config.first_message,
            system_prompt=config.system_prompt,
            voice_id=config.voice_id,
            language=config.language,
            config=response
        )

        db.add(assistant)
        db.commit()
        db.refresh(assistant)

        return {
            "success": True,
            "assistant": {
                "id": assistant.id,
                "vapi_id": assistant.vapi_assistant_id,
                "name": assistant.name
            }
        }

    except Exception as e:
        logger.error(f"Create assistant error: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to create assistant")


@router.get("/assistants")
async def list_assistants(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_flexible)
):
    """List all configured assistants"""
    org_id = getattr(current_user, "organization_id", None)
    query = db.query(VapiAssistant).filter(
        VapiAssistant.is_active == True
    )
    if org_id:
        query = query.filter(VapiAssistant.organization_id == org_id)
    assistants = query.all()

    return {
        "assistants": [
            {
                "id": a.id,
                "vapi_id": a.vapi_assistant_id,
                "name": a.name,
                "description": a.description,
                "total_calls": a.total_calls,
                "total_minutes": a.total_minutes
            }
            for a in assistants
        ]
    }


@router.get("/config")
async def get_vapi_config(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_flexible)
):
    """Get Vapi configuration status"""
    import os

    has_api_key = bool(os.getenv("VAPI_API_KEY"))

    # Count total calls (scoped to org)
    from sqlalchemy import func
    org_id = getattr(current_user, "organization_id", None)
    call_query = db.query(func.count(VapiCall.id))
    assistant_query = db.query(func.count(VapiAssistant.id)).filter(
        VapiAssistant.is_active == True
    )
    if org_id:
        call_query = call_query.filter(VapiCall.organization_id == org_id)
        assistant_query = assistant_query.filter(VapiAssistant.organization_id == org_id)
    total_calls = call_query.scalar() or 0
    active_assistants = assistant_query.scalar() or 0

    return {
        "enabled": has_api_key,
        "total_calls": total_calls,
        "active_assistants": active_assistants,
        "webhook_url": f"{os.getenv('PRODUCTION_DOMAIN', 'localhost')}/api/vapi/webhook"
    }


# ============================================================================
# DIAGNOSTIC ENDPOINTS - Check and fix VAPI assistant configuration
# ============================================================================

@router.get("/diagnostic/assistant")
async def diagnose_vapi_assistant(admin: Any = Depends(verify_admin_access), full: bool = False):
    """
    Diagnose VAPI assistant configuration.
    Checks if firstMessage is configured and returns full assistant config.
    Use ?full=true to get complete VAPI response.
    Requires admin access via X-Admin-Key header or admin JWT.
    """
    import httpx
    import os

    vapi_api_key = os.getenv("VAPI_API_KEY")
    assistant_id = os.getenv("VAPI_ASSISTANT_ID", "120e239e-4d19-4e43-ad92-1f8b07d08c8c")

    if not vapi_api_key:
        return {"error": "VAPI_API_KEY not configured", "fix": "Set VAPI_API_KEY in environment"}

    headers = {
        "Authorization": f"Bearer {vapi_api_key}",
        "Content-Type": "application/json"
    }

    try:
        async with httpx.AsyncClient() as client:
            # Get assistant configuration
            response = await client.get(
                f"https://api.vapi.ai/assistant/{assistant_id}",
                headers=headers,
                timeout=10
            )

            if response.status_code != 200:
                return {
                    "error": f"Failed to fetch assistant: {response.status_code}",
                    "response": response.text,
                    "assistant_id": assistant_id
                }

            assistant = response.json()

            # Return full config if requested
            if full:
                return {
                    "assistant_id": assistant_id,
                    "full_config": assistant
                }

            # Check for firstMessage
            first_message = assistant.get("firstMessage")
            voice_config = assistant.get("voice", {})
            model_config = assistant.get("model", {})
            transcriber_config = assistant.get("transcriber", {})

            issues = []
            warnings = []

            if not first_message:
                issues.append("NO_FIRST_MESSAGE: Assistant has no greeting configured")
            elif first_message.strip() == "":
                issues.append("EMPTY_FIRST_MESSAGE: Greeting is empty string")

            if not voice_config:
                issues.append("NO_VOICE_CONFIG: No voice provider configured")
            else:
                # Check voice config in detail
                if not voice_config.get("voiceId"):
                    issues.append("NO_VOICE_ID: Voice ID not set")
                if voice_config.get("provider") == "playht":
                    # PlayHT specific checks
                    if not voice_config.get("emotion"):
                        warnings.append("No emotion set for PlayHT voice")

            if not model_config:
                issues.append("NO_MODEL_CONFIG: No AI model configured")

            # Check for silenceTimeoutSeconds - if too short, might disconnect early
            silence_timeout = assistant.get("silenceTimeoutSeconds")
            if silence_timeout and silence_timeout < 10:
                warnings.append(f"Silence timeout is only {silence_timeout}s - might disconnect too early")

            # Check responseDelaySeconds - if too high, causes perceived silence
            response_delay = assistant.get("responseDelaySeconds")
            if response_delay and response_delay > 1:
                warnings.append(f"Response delay is {response_delay}s - might cause initial silence")

            # Check firstMessageMode
            first_message_mode = assistant.get("firstMessageMode")

            return {
                "status": "healthy" if not issues else "issues_found",
                "assistant_id": assistant_id,
                "name": assistant.get("name"),
                "first_message": first_message,
                "first_message_mode": first_message_mode,
                "has_first_message": bool(first_message and first_message.strip()),
                "voice": {
                    "provider": voice_config.get("provider"),
                    "voice_id": voice_config.get("voiceId"),
                    "stability": voice_config.get("stability"),
                    "speed": voice_config.get("speed")
                },
                "model": {
                    "provider": model_config.get("provider"),
                    "model": model_config.get("model")
                },
                "transcriber": {
                    "provider": transcriber_config.get("provider"),
                    "model": transcriber_config.get("model")
                },
                "timing": {
                    "silence_timeout_seconds": silence_timeout,
                    "response_delay_seconds": response_delay,
                    "llm_request_delay_seconds": assistant.get("llmRequestDelaySeconds"),
                    "num_words_to_interrupt_assistant": assistant.get("numWordsToInterruptAssistant")
                },
                "issues": issues,
                "warnings": warnings,
                "fix_url": "/api/vapi/diagnostic/fix-greeting" if "NO_FIRST_MESSAGE" in str(issues) else None
            }

    except Exception as e:
        logger.error(f"Diagnostic error: {str(e)}")
        return {"error": "Internal server error"}


@router.post("/diagnostic/fix-greeting")
async def fix_vapi_greeting(
    greeting: str = "Hello! Thank you for calling The Tim Loss Team. I'm Aria, your AI assistant. How can I help you today?",
    admin: Any = Depends(verify_admin_access)
):
    """
    Fix VAPI assistant greeting by setting firstMessage.
    This updates the assistant configuration in VAPI directly.
    Requires admin access via X-Admin-Key header or admin JWT.
    """
    import httpx
    import os

    vapi_api_key = os.getenv("VAPI_API_KEY")
    assistant_id = os.getenv("VAPI_ASSISTANT_ID", "120e239e-4d19-4e43-ad92-1f8b07d08c8c")

    if not vapi_api_key:
        return {"error": "VAPI_API_KEY not configured"}

    headers = {
        "Authorization": f"Bearer {vapi_api_key}",
        "Content-Type": "application/json"
    }

    try:
        async with httpx.AsyncClient() as client:
            # Update assistant with new greeting
            response = await client.patch(
                f"https://api.vapi.ai/assistant/{assistant_id}",
                headers=headers,
                json={"firstMessage": greeting},
                timeout=10
            )

            if response.status_code == 200:
                updated = response.json()
                return {
                    "success": True,
                    "message": "Greeting updated successfully",
                    "assistant_id": assistant_id,
                    "new_greeting": updated.get("firstMessage"),
                    "test_instructions": "Call the AI receptionist now to verify the greeting works"
                }
            else:
                return {
                    "success": False,
                    "error": f"Failed to update: {response.status_code}",
                    "response": response.text
                }

    except Exception as e:
        logger.error(f"Fix greeting error: {str(e)}")
        return {"success": False, "error": "Internal server error"}


@router.post("/diagnostic/change-voice")
async def change_voice_provider(
    provider: str = "deepgram",
    voice_id: str = "asteria",
    admin: Any = Depends(verify_admin_access)
):
    """
    Change the VAPI assistant's voice provider.
    Requires admin access via X-Admin-Key header or admin JWT.

    Deepgram voices: asteria, luna, stella, athena, hera, orion, arcas, perseus, angus, orpheus, helios, zeus
    PlayHT voices: jennifer, matt, etc.
    ElevenLabs voices: rachel, domi, bella, etc.
    """
    import httpx
    import os

    vapi_api_key = os.getenv("VAPI_API_KEY")
    assistant_id = os.getenv("VAPI_ASSISTANT_ID", "120e239e-4d19-4e43-ad92-1f8b07d08c8c")

    if not vapi_api_key:
        return {"error": "VAPI_API_KEY not configured"}

    headers = {
        "Authorization": f"Bearer {vapi_api_key}",
        "Content-Type": "application/json"
    }

    # Build voice config based on provider
    if provider == "deepgram":
        voice_config = {
            "provider": "deepgram",
            "voiceId": voice_id  # asteria, luna, stella, athena, hera, orion, arcas, perseus, angus, orpheus, helios, zeus
        }
    elif provider == "playht":
        voice_config = {
            "provider": "playht",
            "voiceId": voice_id,
            "speed": 1.1,
            "emotion": "female_happy"
        }
    elif provider == "elevenlabs":
        voice_config = {
            "provider": "11labs",
            "voiceId": voice_id,
            "stability": 0.5,
            "similarityBoost": 0.75
        }
    else:
        return {"error": f"Unknown provider: {provider}. Use 'deepgram', 'playht', or 'elevenlabs'"}

    try:
        async with httpx.AsyncClient() as client:
            response = await client.patch(
                f"https://api.vapi.ai/assistant/{assistant_id}",
                headers=headers,
                json={"voice": voice_config},
                timeout=10
            )

            if response.status_code == 200:
                updated = response.json()
                new_voice = updated.get("voice", {})
                return {
                    "success": True,
                    "message": f"Voice changed to {provider} - {voice_id}",
                    "assistant_id": assistant_id,
                    "new_voice": {
                        "provider": new_voice.get("provider"),
                        "voice_id": new_voice.get("voiceId")
                    },
                    "test_instructions": "Trigger a test call to hear the new voice"
                }
            else:
                return {
                    "success": False,
                    "error": f"Failed to update: {response.status_code}",
                    "response": response.text
                }

    except Exception as e:
        logger.error(f"Change voice error: {str(e)}")
        return {"success": False, "error": "Internal server error"}


@router.get("/diagnostic/phone-numbers")
async def diagnose_phone_numbers(admin: Any = Depends(verify_admin_access)):
    """
    Check VAPI phone number configurations.
    Shows which assistant is linked to each number.
    Requires admin access via X-Admin-Key header or admin JWT.
    """
    import httpx
    import os

    vapi_api_key = os.getenv("VAPI_API_KEY")

    if not vapi_api_key:
        return {"error": "VAPI_API_KEY not configured"}

    headers = {
        "Authorization": f"Bearer {vapi_api_key}",
        "Content-Type": "application/json"
    }

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                "https://api.vapi.ai/phone-number",
                headers=headers,
                timeout=10
            )

            if response.status_code != 200:
                return {"error": f"Failed to fetch: {response.status_code}"}

            phones = response.json()

            return {
                "phone_numbers": [
                    {
                        "id": p.get("id"),
                        "number": p.get("number"),
                        "assistant_id": p.get("assistantId"),
                        "squad_id": p.get("squadId"),
                        "server_url": p.get("serverUrl"),
                        "has_assistant": bool(p.get("assistantId")),
                        "uses_webhook": bool(p.get("serverUrl") and not p.get("assistantId")),
                        "provider": p.get("provider"),
                        "status": p.get("status")
                    }
                    for p in phones
                ],
                "count": len(phones)
            }

    except Exception as e:
        logger.error(f"Phone diagnostic error: {str(e)}")
        return {"error": "Internal server error"}


@router.post("/diagnostic/restore-phone-config")
async def restore_phone_config(admin: Any = Depends(verify_admin_access)):
    """
    Restore the Vapi phone number to use assistantId (not serverUrl).
    Fixes the case where configure-phone-routing removed the assistantId.
    """
    import httpx

    vapi_api_key = os.getenv("VAPI_API_KEY")
    assistant_id = os.getenv("VAPI_ASSISTANT_ID", "120e239e-4d19-4e43-ad92-1f8b07d08c8c")
    phone_number_id = "6adaf897-34d7-42d5-bc34-f1a17162a453"

    if not vapi_api_key:
        return {"error": "VAPI_API_KEY not configured"}

    headers = {"Authorization": f"Bearer {vapi_api_key}", "Content-Type": "application/json"}

    try:
        async with httpx.AsyncClient() as client:
            current = await client.get(
                f"https://api.vapi.ai/phone-number/{phone_number_id}",
                headers=headers, timeout=10,
            )
            if current.status_code != 200:
                return {"error": f"Could not fetch phone number: {current.status_code}", "body": current.text}

            phone_data = current.json()
            current_assistant = phone_data.get("assistantId")
            current_server_url = phone_data.get("serverUrl")

            if current_assistant == assistant_id:
                return {
                    "status": "already_correct",
                    "assistant_id": current_assistant,
                    "server_url": current_server_url,
                }

            resp = await client.patch(
                f"https://api.vapi.ai/phone-number/{phone_number_id}",
                headers=headers,
                json={"assistantId": assistant_id, "serverUrl": None},
                timeout=15,
            )

            if resp.status_code == 200:
                return {
                    "status": "restored",
                    "previous_assistant_id": current_assistant,
                    "previous_server_url": current_server_url,
                    "new_assistant_id": assistant_id,
                }
            return {"error": f"Vapi API error: {resp.status_code}", "body": resp.text}
    except Exception as e:
        logger.error(f"restore-phone-config error: {e}")
        return {"error": str(e)}


@router.get("/diagnostic/account")
async def diagnose_vapi_account(admin: Any = Depends(verify_admin_access)):
    """
    Check VAPI account status including credits and usage.
    Requires admin access via X-Admin-Key header or admin JWT.
    """
    import httpx
    import os

    vapi_api_key = os.getenv("VAPI_API_KEY")

    if not vapi_api_key:
        return {"error": "VAPI_API_KEY not configured"}

    headers = {
        "Authorization": f"Bearer {vapi_api_key}",
        "Content-Type": "application/json"
    }

    try:
        async with httpx.AsyncClient() as client:
            # Get account/organization info
            org_response = await client.get(
                "https://api.vapi.ai/org",
                headers=headers,
                timeout=10
            )

            org_data = org_response.json() if org_response.status_code == 200 else {"error": org_response.text}

            # Try to get usage/billing info
            usage_response = await client.get(
                "https://api.vapi.ai/usage",
                headers=headers,
                timeout=10
            )

            usage_data = usage_response.json() if usage_response.status_code == 200 else None

            return {
                "account": {
                    "org_id": org_data.get("id"),
                    "name": org_data.get("name"),
                    "billing_status": org_data.get("billingStatus"),
                    "plan": org_data.get("plan"),
                    "hipaa_enabled": org_data.get("hipaaEnabled"),
                    "credits_remaining": org_data.get("creditsRemaining"),
                    "error": org_data.get("error")
                },
                "usage": usage_data,
                "api_key_valid": org_response.status_code == 200,
                "potential_issues": []
            }

    except Exception as e:
        logger.error(f"Account diagnostic error: {str(e)}")
        return {"error": "Internal server error"}


@router.get("/diagnostic/recent-calls")
async def get_recent_vapi_calls(limit: int = 10, admin: Any = Depends(verify_admin_access)):
    """
    Fetch recent calls directly from VAPI API.
    Shows call status, duration, and any errors.
    Requires admin access via X-Admin-Key header or admin JWT.
    """
    import httpx
    import os

    vapi_api_key = os.getenv("VAPI_API_KEY")

    if not vapi_api_key:
        return {"error": "VAPI_API_KEY not configured"}

    headers = {
        "Authorization": f"Bearer {vapi_api_key}",
        "Content-Type": "application/json"
    }

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"https://api.vapi.ai/call?limit={limit}",
                headers=headers,
                timeout=15
            )

            if response.status_code != 200:
                return {"error": f"Failed to fetch: {response.status_code}", "response": response.text}

            calls = response.json()

            return {
                "calls": [
                    {
                        "id": c.get("id"),
                        "status": c.get("status"),
                        "type": c.get("type"),
                        "ended_reason": c.get("endedReason"),
                        "duration_seconds": c.get("duration"),
                        "created_at": c.get("createdAt"),
                        "phone_number": c.get("phoneNumber", {}).get("number") if isinstance(c.get("phoneNumber"), dict) else c.get("phoneNumber"),
                        "customer_number": c.get("customer", {}).get("number") if c.get("customer") else None,
                        "assistant_id": c.get("assistantId"),
                        "transcript_preview": (c.get("transcript") or "")[:200] if c.get("transcript") else None,
                        "error_message": c.get("messages", [{}])[-1].get("content") if c.get("messages") else None
                    }
                    for c in calls
                ],
                "count": len(calls)
            }

    except Exception as e:
        logger.error(f"Recent calls error: {str(e)}")
        return {"error": "Internal server error"}


@router.post("/migrate")
async def run_vapi_migration(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_flexible)
):
    """Run Vapi database migration to create tables"""
    from sqlalchemy import text

    sql_commands = [
        # 1. Vapi Calls table
        """
        CREATE TABLE IF NOT EXISTS vapi_calls (
            id SERIAL PRIMARY KEY,
            vapi_call_id VARCHAR(255) UNIQUE NOT NULL,
            phone_number VARCHAR(20),
            caller_name VARCHAR(255),
            direction VARCHAR(20),
            status VARCHAR(50),
            started_at TIMESTAMP WITH TIME ZONE,
            ended_at TIMESTAMP WITH TIME ZONE,
            duration INTEGER,
            transcript TEXT,
            summary TEXT,
            recording_url VARCHAR(512),
            sentiment VARCHAR(50),
            intent VARCHAR(100),
            language VARCHAR(10) DEFAULT 'en',
            metadata JSON,
            vapi_raw_data JSON,
            lead_id INTEGER REFERENCES leads(id),
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        );
        """,

        # 2. Vapi Call Notes table
        """
        CREATE TABLE IF NOT EXISTS vapi_call_notes (
            id SERIAL PRIMARY KEY,
            call_id INTEGER NOT NULL REFERENCES vapi_calls(id) ON DELETE CASCADE,
            note_type VARCHAR(50),
            content TEXT NOT NULL,
            priority VARCHAR(20),
            completed BOOLEAN DEFAULT FALSE,
            assigned_to INTEGER REFERENCES users(id),
            due_date TIMESTAMP WITH TIME ZONE,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        );
        """,

        # 3. Vapi Assistants table
        """
        CREATE TABLE IF NOT EXISTS vapi_assistants (
            id SERIAL PRIMARY KEY,
            vapi_assistant_id VARCHAR(255) UNIQUE,
            name VARCHAR(255) NOT NULL,
            description TEXT,
            voice_id VARCHAR(100),
            language VARCHAR(10) DEFAULT 'en',
            first_message TEXT,
            system_prompt TEXT,
            is_active BOOLEAN DEFAULT TRUE,
            config JSON,
            total_calls INTEGER DEFAULT 0,
            total_minutes FLOAT DEFAULT 0.0,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        );
        """,

        # 4. Vapi Phone Numbers table
        """
        CREATE TABLE IF NOT EXISTS vapi_phone_numbers (
            id SERIAL PRIMARY KEY,
            vapi_number_id VARCHAR(255) UNIQUE,
            phone_number VARCHAR(20) UNIQUE NOT NULL,
            name VARCHAR(255),
            assistant_id INTEGER REFERENCES vapi_assistants(id),
            department VARCHAR(100),
            is_active BOOLEAN DEFAULT TRUE,
            config JSON,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        );
        """,

        # Indices for performance
        "CREATE INDEX IF NOT EXISTS idx_vapi_calls_call_id ON vapi_calls(vapi_call_id);",
        "CREATE INDEX IF NOT EXISTS idx_vapi_calls_phone ON vapi_calls(phone_number);",
        "CREATE INDEX IF NOT EXISTS idx_vapi_calls_status ON vapi_calls(status);",
        "CREATE INDEX IF NOT EXISTS idx_vapi_calls_lead ON vapi_calls(lead_id);",
        "CREATE INDEX IF NOT EXISTS idx_vapi_calls_created ON vapi_calls(created_at);",
        "CREATE INDEX IF NOT EXISTS idx_vapi_call_notes_call ON vapi_call_notes(call_id);",
        "CREATE INDEX IF NOT EXISTS idx_vapi_call_notes_type ON vapi_call_notes(note_type);",
        "CREATE INDEX IF NOT EXISTS idx_vapi_call_notes_assigned ON vapi_call_notes(assigned_to);",
        "CREATE INDEX IF NOT EXISTS idx_vapi_assistants_active ON vapi_assistants(is_active);",
        "CREATE INDEX IF NOT EXISTS idx_vapi_phone_numbers_active ON vapi_phone_numbers(is_active);",
    ]

    results = []
    try:
        for idx, sql in enumerate(sql_commands, 1):
            try:
                db.execute(text(sql))
                db.commit()
                results.append({"command": idx, "status": "success"})
                logger.info(f"✅ Command {idx}/{len(sql_commands)} executed successfully")
            except Exception as e:
                results.append({"command": idx, "status": "error", "error": "Internal server error"})
                logger.error(f"❌ Error executing command {idx}: {e}")
                continue

        return {
            "success": True,
            "message": "Migration completed",
            "results": results
        }

    except Exception as e:
        logger.error(f"Migration error: {str(e)}")
        raise HTTPException(status_code=500, detail="Migration failed")


# ============================================================================
# AI RECEPTIONIST SMS ENDPOINTS
# ============================================================================

@router.post("/webhook/sms")
async def ai_receptionist_sms_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    _: bool = Depends(verify_vapi_request)
):
    """
    Webhook for inbound SMS to AI Receptionist.

    This handles SMS messages sent to the AI receptionist phone number
    and provides intelligent auto-responses based on intent.

    Integrates with the existing SMS Intelligence system but adds
    AI receptionist-specific handling.
    """
    try:
        # Parse Telnyx/Vapi webhook payload
        form_data = await request.form()
        from_number = form_data.get("From", "")
        to_number = form_data.get("To", "")
        message_body = form_data.get("Body", "")
        message_sid = form_data.get("MessageSid", "")

        logger.info(f"AI Receptionist SMS webhook: {from_number} -> {to_number}: {message_body[:50]}...")

        # Process in background for fast response to provider
        background_tasks.add_task(
            process_ai_receptionist_sms,
            db, from_number, to_number, message_body, message_sid
        )

        # Return empty TwiML response (we'll send our own response via API)
        return JSONResponse(
            status_code=200,
            content={"status": "received"},
            headers={"Content-Type": "application/json"}
        )

    except Exception as e:
        logger.error(f"AI Receptionist SMS webhook error: {e}")
        return JSONResponse(status_code=200, content={"status": "error"})


async def process_ai_receptionist_sms(
    db: Session,
    from_number: str,
    to_number: str,
    message_body: str,
    message_sid: str
):
    """Process AI Receptionist SMS in background."""
    try:
        from vapi_service import AIReceptionistSMSService

        sms_service = AIReceptionistSMSService(db)
        result = await sms_service.handle_inbound_sms(
            from_number=from_number,
            message_body=message_body,
            to_number=to_number
        )

        logger.info(f"AI Receptionist SMS processed: {result}")

    except Exception as e:
        logger.error(f"Error processing AI Receptionist SMS: {e}")


@router.post("/sms/send-calendly")
async def send_calendly_sms(
    request: Request,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_flexible)
):
    """
    Manually send Calendly link via SMS.

    Useful for:
    - Sending to a lead who didn't call
    - Re-sending a link
    - Sending from the CRM interface
    """
    try:
        from vapi_service import AIReceptionistSMSService

        data = await request.json()
        phone_number = data.get("phone_number")
        name = data.get("name")
        context = data.get("context", "consultation")

        if not phone_number:
            return {"success": False, "error": "phone_number required"}

        sms_service = AIReceptionistSMSService(db)
        result = await sms_service.send_calendly_link(
            phone_number=phone_number,
            caller_name=name,
            context=context
        )

        return result

    except Exception as e:
        logger.error(f"Error sending Calendly SMS: {e}")
        return {"success": False, "error": "Internal server error"}


@router.post("/sms/send-followup")
async def send_followup_sms(
    request: Request,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_flexible)
):
    """
    Manually send follow-up SMS.

    Useful for:
    - Post-call follow-ups
    - Lead nurturing
    - Appointment reminders
    """
    try:
        from vapi_service import AIReceptionistSMSService

        data = await request.json()
        phone_number = data.get("phone_number")
        name = data.get("name")
        message_type = data.get("type", "general")  # general, appointment, calendly

        if not phone_number:
            return {"success": False, "error": "phone_number required"}

        sms_service = AIReceptionistSMSService(db)

        if message_type == "appointment":
            appointment_time = data.get("appointment_time")
            appointment_type = data.get("appointment_type", "consultation")
            if not appointment_time:
                return {"success": False, "error": "appointment_time required for appointment type"}

            result = await sms_service.send_appointment_confirmation(
                phone_number=phone_number,
                caller_name=name,
                appointment_time=appointment_time,
                appointment_type=appointment_type
            )
        elif message_type == "calendly":
            context = data.get("context")
            result = await sms_service.send_calendly_link(
                phone_number=phone_number,
                caller_name=name,
                context=context
            )
        else:
            # General follow-up
            result = await sms_service.send_post_call_followup(
                phone_number=phone_number,
                caller_name=name,
                call_summary=data.get("summary"),
                appointment_scheduled=data.get("appointment_scheduled", False),
                appointment_time=data.get("appointment_time"),
                include_calendly=data.get("include_calendly", True)
            )

        return result

    except Exception as e:
        logger.error(f"Error sending follow-up SMS: {e}")
        return {"success": False, "error": "Internal server error"}


@router.get("/sms/config")
async def get_sms_config(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_flexible)
):
    """Get AI Receptionist SMS configuration."""
    import os

    return {
        "enabled": bool(os.getenv("TELNYX_API_KEY")),
        "post_call_sms_enabled": os.getenv("ENABLE_POST_CALL_SMS", "true").lower() == "true",
        "calendly_link": os.getenv("CALENDLY_LINK", "https://calendly.com/timloss/discovery-call"),
        "business_name": os.getenv("BUSINESS_NAME", "CMG Home Loans"),
        "lo_name": os.getenv("LO_NAME", "Tim"),
        "webhook_url": "/api/vapi/webhook/sms"
    }


@router.post("/functions/send-sms-calendly-link")
async def send_sms_calendly_link_function(
    request: Request,
    db: Session = Depends(get_db),
    _: bool = Depends(verify_vapi_request)
):
    """
    VAPI Function: Send Calendly link via SMS.

    Called by VAPI when the AI says "I'll text you the booking link"
    during a phone call.
    """
    try:
        from vapi_service import AIReceptionistSMSService
        from services.sms_compliance import check_sms_consent

        data = await request.json()
        phone_number = data.get("phone_number")
        name = data.get("name", "")

        if not phone_number:
            return {
                "success": False,
                "error": "Phone number required",
                "message": "I don't have your phone number. Could you provide it?"
            }

        # TCPA compliance gate — check DNC, consent, and contact hours
        can_send, reason = check_sms_consent(phone_number, db=db)
        if not can_send:
            logger.warning("Vapi SMS blocked by compliance for %s: %s", phone_number[-4:], reason)
            return {
                "success": False,
                "error": f"Compliance block: {reason}",
                "message": "I'm unable to send a text to that number right now. Let me give you the link verbally instead. You can book a time at calendly dot com slash timloss slash discovery-call. Would you like me to repeat that?"
            }

        sms_service = AIReceptionistSMSService(db)
        result = await sms_service.send_calendly_link(
            phone_number=phone_number,
            caller_name=name
        )

        if result.get("success"):
            return {
                "success": True,
                "message": "Perfect! I just sent you a text with the booking link. You should receive it any moment. Is there anything else I can help you with?"
            }
        else:
            return {
                "success": False,
                "error": result.get("error"),
                "message": "I'm having trouble sending the text right now. Let me give you the link verbally instead. You can book a time at calendly dot com slash timloss slash discovery-call. Would you like me to repeat that?"
            }

    except Exception as e:
        logger.error(f"Error in send_sms_calendly_link_function: {e}")
        return {
            "success": False,
            "error": "Internal server error",
            "message": "I'm having some technical difficulties. Let me get your information and have someone follow up with the booking link."
        }
