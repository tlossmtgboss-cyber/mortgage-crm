"""
Chat and Screenshot Parsing Routes
Simplified chat endpoints with caching and Vision AI for screenshot parsing
"""
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from sqlalchemy import text
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timezone, timedelta
import logging
import os
from routes.auth_deps import current_user_dep

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1")


def get_models():
    """Get models at runtime to avoid circular imports"""
    import main
    return {
        'User': main.User,
        'Lead': main.Lead,
        'ReferralPartner': main.ReferralPartner,
        'LeadStage': main.LeadStage,
    }


def get_db_dep():
    """Get database dependency at runtime"""
    from db import get_db
    return get_db


def get_current_user_dep():
    """Get current user dependency at runtime"""
    import main
    return main.get_current_user


# Pydantic models
class SimpleChatRequest(BaseModel):
    message: str
    user_id: Optional[str] = None


@router.post("/chat")
async def simple_chat(
    request: SimpleChatRequest,
    use_cache: bool = True,
    db: Session = Depends(lambda: get_db_dep()),
    current_user = Depends(current_user_dep)
):
    """
    Simplified chat endpoint with response caching.

    This is a streamlined wrapper around the LangGraph orchestrator
    with automatic caching for improved response times.

    Query params:
    - use_cache: bool (default True) - Set to false for fresh response
    """
    import time
    start_time = time.time()

    user_id = request.user_id or str(current_user.id)
    message = request.message.strip()

    if not message:
        raise HTTPException(status_code=400, detail="Message is required")

    # Check response cache first
    if use_cache:
        try:
            from utils.cache import cache as response_cache
            cached = await response_cache.get(message, user_id)
            if cached:
                logger.info(f"[CHAT CACHE HIT] {message[:50]}...")
                return {
                    "response": cached.get("response", ""),
                    "intent": cached.get("intent"),
                    "confidence": cached.get("confidence"),
                    "cached": True,
                    "response_time": round(time.time() - start_time, 3),
                    "cached_at": cached.get("cached_at")
                }
        except Exception as e:
            logger.warning(f"Cache check failed: {e}")

    # Execute via LangGraph orchestrator
    try:
        from agents.orchestrator import run_orchestrator
        from agents.service import create_tool_functions_from_main

        tool_functions = create_tool_functions_from_main(db, current_user)

        result = await run_orchestrator(
            message=message,
            user_id=user_id,
            user_email=current_user.email,
            user_role=getattr(current_user, 'role', 'loan_officer'),
            tool_functions=tool_functions,
            autonomous_mode=True,
            conversation_history=[],
            return_structured=True
        )

        response_data = {
            "response": result.get("response", ""),
            "intent": result.get("intent"),
            "confidence": result.get("confidence"),
            "cached": False,
            "response_time": round(time.time() - start_time, 3),
            "metadata": {
                "follow_up_suggestions": result.get("follow_up_suggestions", []),
                "data_quality": result.get("data_quality"),
                "warnings": result.get("warnings", [])
            }
        }

        # Cache high-confidence responses
        if use_cache and result.get("confidence", 0) >= 0.7:
            try:
                from utils.cache import cache as response_cache
                await response_cache.set(
                    query=message,
                    response=response_data,
                    intent=result.get("intent", "general"),
                    user_id=user_id
                )
            except Exception as e:
                logger.warning(f"Cache set failed: {e}")

        return response_data

    except Exception as e:
        logger.error(f"Chat error: {e}", exc_info=True)
        return {
            "response": f"I encountered an error processing your request: {str(e)}",
            "intent": None,
            "confidence": 0,
            "cached": False,
            "response_time": round(time.time() - start_time, 3),
            "error": "Internal server error"
        }


@router.post("/chat/fresh")
async def simple_chat_fresh(
    request: SimpleChatRequest,
    db: Session = Depends(lambda: get_db_dep()),
    current_user = Depends(current_user_dep)
):
    """
    Force fresh response (bypass cache).
    Useful when you need real-time data or after making changes.
    """
    return await simple_chat(request, use_cache=False, db=db, current_user=current_user)


@router.post("/ai/parse-screenshot")
async def parse_screenshot(
    request: Request,
    db: Session = Depends(lambda: get_db_dep()),
    current_user = Depends(current_user_dep)
):
    """
    Parse a screenshot using OpenAI Vision to extract referral partner and lead information.

    This endpoint:
    1. Uses GPT-4 Vision to analyze the screenshot
    2. Extracts partner info (realtor, title agent, etc.) and lead info
    3. Creates/updates referral partner in CRM if not exists
    4. Creates lead linked to the partner if not exists
    5. Creates a follow-up task for the user

    Request body:
    {
        "image_base64": "base64-encoded-image-data"
    }

    Returns:
    {
        "message": "Human-readable summary of what was done",
        "entities_created": {
            "referral_partner": {"id": 123, "name": "...", "created": true/false},
            "lead": {"id": 456, "name": "...", "created": true/false},
            "task": {"id": 789, "title": "..."}
        },
        "extracted_data": { ... raw extracted data ... }
    }
    """
    import base64
    import httpx
    import json
    import re

    models = get_models()
    Lead = models['Lead']
    ReferralPartner = models['ReferralPartner']
    LeadStage = models['LeadStage']

    try:
        data = await request.json()
        image_base64 = data.get("image_base64", "").strip()

        if not image_base64:
            raise HTTPException(status_code=400, detail="image_base64 is required")

        # Remove data URL prefix if present
        if image_base64.startswith("data:"):
            image_base64 = image_base64.split(",", 1)[1] if "," in image_base64 else image_base64

        logger.info(f"[SCREENSHOT] Processing screenshot for user {current_user.id}")

        # === Step 1: Use OpenAI Vision to analyze the screenshot ===
        openai_api_key = os.getenv("OPENAI_API_KEY")
        if not openai_api_key:
            raise HTTPException(status_code=500, detail="OpenAI API key not configured")

        vision_prompt = """Analyze this screenshot and extract any referral partner and potential mortgage lead information.

Look for:
1. REFERRAL PARTNER INFO (realtor, real estate agent, title agent, insurance agent, financial advisor, CPA, attorney, builder, etc.):
   - Name (full name)
   - Company/Brokerage
   - Phone number
   - Email
   - Type/Category (realtor, title_agent, insurance_agent, financial_advisor, cpa, attorney, builder, other)

2. LEAD/CLIENT INFO (the person who might need a mortgage):
   - Name (full name)
   - Phone number
   - Email
   - Property address or location (if mentioned)
   - Loan type interest (purchase, refinance, etc.)
   - Any other relevant details

Return ONLY a JSON object in this exact format (no markdown, no explanation):
{
    "referral_partner": {
        "name": "Full Name or null",
        "company": "Company Name or null",
        "phone": "Phone or null",
        "email": "Email or null",
        "type": "realtor|title_agent|insurance_agent|financial_advisor|cpa|attorney|builder|other or null"
    },
    "lead": {
        "name": "Full Name or null",
        "phone": "Phone or null",
        "email": "Email or null",
        "address": "Property Address or null",
        "loan_type": "purchase|refinance|other or null",
        "notes": "Any other relevant details or null"
    },
    "context": "Brief description of what this screenshot shows"
}

If you cannot identify a partner or lead, set those fields to null but still return the JSON structure."""

        async with httpx.AsyncClient(timeout=60.0) as client:
            vision_response = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {openai_api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": "gpt-4o",
                    "messages": [
                        {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": vision_prompt},
                                {
                                    "type": "image_url",
                                    "image_url": {
                                        "url": f"data:image/jpeg;base64,{image_base64}",
                                        "detail": "high"
                                    }
                                }
                            ]
                        }
                    ],
                    "max_tokens": 1000
                }
            )

            if vision_response.status_code != 200:
                error_text = vision_response.text
                logger.error(f"[SCREENSHOT] Vision API error: {error_text}")
                raise HTTPException(status_code=500, detail=f"Vision API error: {vision_response.status_code}")

            vision_result = vision_response.json()
            vision_content = vision_result["choices"][0]["message"]["content"].strip()

            # Parse the JSON from the response
            if "```json" in vision_content:
                vision_content = vision_content.split("```json")[1].split("```")[0].strip()
            elif "```" in vision_content:
                vision_content = vision_content.split("```")[1].split("```")[0].strip()

            try:
                extracted_data = json.loads(vision_content)
            except json.JSONDecodeError as e:
                logger.error(f"[SCREENSHOT] Failed to parse vision response: {vision_content}")
                json_match = re.search(r'\{[\s\S]*\}', vision_content)
                if json_match:
                    extracted_data = json.loads(json_match.group())
                else:
                    raise HTTPException(status_code=500, detail="Failed to parse extracted data")

        logger.info(f"[SCREENSHOT] Extracted data: {json.dumps(extracted_data, indent=2)}")

        entities_created = {
            "referral_partner": None,
            "lead": None,
            "task": None
        }

        partner_data = extracted_data.get("referral_partner", {})
        lead_data = extracted_data.get("lead", {})
        context = extracted_data.get("context", "Screenshot analysis")

        # === Step 2: Create/Find Referral Partner ===
        referral_partner_id = None
        if partner_data and partner_data.get("name"):
            partner_name = partner_data["name"]
            partner_email = partner_data.get("email")
            partner_phone = partner_data.get("phone")
            partner_company = partner_data.get("company")
            partner_type = partner_data.get("type", "other")

            existing_partner = None
            if partner_email:
                existing_partner = db.query(ReferralPartner).filter(
                    ReferralPartner.email == partner_email
                ).first()

            if not existing_partner and partner_name:
                existing_partner = db.query(ReferralPartner).filter(
                    ReferralPartner.name == partner_name
                ).first()

            if existing_partner:
                referral_partner_id = existing_partner.id
                entities_created["referral_partner"] = {
                    "id": existing_partner.id,
                    "name": existing_partner.name,
                    "created": False
                }
                logger.info(f"[SCREENSHOT] Found existing partner: {existing_partner.name} (ID: {existing_partner.id})")
            else:
                new_partner = ReferralPartner(
                    name=partner_name,
                    business_name=partner_company or "",
                    contact_name=partner_name,
                    category=partner_type or "realtor",
                    company=partner_company,
                    type=partner_type,
                    phone=partner_phone,
                    email=partner_email,
                    status="active",
                    notes=f"Added via screenshot import on {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')}"
                )
                db.add(new_partner)
                db.flush()
                referral_partner_id = new_partner.id
                entities_created["referral_partner"] = {
                    "id": new_partner.id,
                    "name": new_partner.name,
                    "created": True
                }
                logger.info(f"[SCREENSHOT] Created new partner: {partner_name} (ID: {new_partner.id})")

        # === Step 3: Create/Find Lead ===
        lead_id = None
        missing_fields = []
        lead_creation_blocked = False

        if lead_data and lead_data.get("name"):
            lead_name = lead_data["name"]
            lead_email = lead_data.get("email")
            lead_phone = lead_data.get("phone")
            lead_address = lead_data.get("address")
            lead_loan_type = lead_data.get("loan_type")
            lead_notes = lead_data.get("notes")

            name_parts = lead_name.split(" ", 1)
            first_name = name_parts[0]
            last_name = name_parts[1] if len(name_parts) > 1 else ""

            if not first_name or not first_name.strip():
                missing_fields.append({
                    "field": "first_name",
                    "label": "First Name",
                    "question": "What is the lead's first name?"
                })

            if not lead_phone and not lead_email:
                missing_fields.append({
                    "field": "phone_or_email",
                    "label": "Phone or Email",
                    "question": "What is their phone number or email address?"
                })

            if not referral_partner_id and not partner_data.get("name"):
                missing_fields.append({
                    "field": "referral_partner",
                    "label": "Referral Partner",
                    "question": "Who referred this lead? (realtor name, company, etc.)"
                })

            existing_lead = None
            if lead_email:
                existing_lead = db.query(Lead).filter(
                    Lead.email == lead_email,
                    Lead.owner_id == current_user.id
                ).first()

            if not existing_lead and lead_phone:
                existing_lead = db.query(Lead).filter(
                    Lead.phone == lead_phone,
                    Lead.owner_id == current_user.id
                ).first()

            if not existing_lead and lead_name:
                existing_lead = db.query(Lead).filter(
                    Lead.name == lead_name,
                    Lead.owner_id == current_user.id
                ).first()

            if existing_lead:
                lead_id = existing_lead.id
                entities_created["lead"] = {
                    "id": existing_lead.id,
                    "name": existing_lead.name,
                    "created": False
                }
                logger.info(f"[SCREENSHOT] Found existing lead: {existing_lead.name} (ID: {existing_lead.id})")
            elif missing_fields:
                lead_creation_blocked = True
                entities_created["lead"] = {
                    "id": None,
                    "name": lead_name,
                    "created": False,
                    "blocked": True,
                    "reason": "missing_required_fields"
                }
                logger.info(f"[SCREENSHOT] Lead creation blocked - missing fields: {[f['field'] for f in missing_fields]}")
            else:
                new_lead = Lead(
                    name=lead_name,
                    first_name=first_name,
                    last_name=last_name,
                    email=lead_email,
                    phone=lead_phone,
                    address=lead_address,
                    property_address=lead_address,
                    loan_type=lead_loan_type,
                    source="screenshot_import",
                    stage=LeadStage.NEW,
                    owner_id=current_user.id,
                    referral_partner_id=referral_partner_id,
                    notes=f"Imported from screenshot on {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')}. {lead_notes or ''}",
                    lead_received_date=datetime.now(timezone.utc)
                )
                db.add(new_lead)
                db.flush()

                from services.client_file_service import ensure_client_file
                ensure_client_file(db, new_lead)

                lead_id = new_lead.id
                entities_created["lead"] = {
                    "id": new_lead.id,
                    "name": new_lead.name,
                    "created": True
                }
                logger.info(f"[SCREENSHOT] Created new lead: {lead_name} (ID: {new_lead.id})")

        # === Step 4: Create Follow-up Task ===
        task_title = "Follow up on screenshot import"
        task_description_parts = []

        if entities_created["referral_partner"]:
            partner_info = entities_created["referral_partner"]
            if partner_info["created"]:
                task_description_parts.append(f"New referral partner added: {partner_info['name']}")
            else:
                task_description_parts.append(f"Existing partner identified: {partner_info['name']}")

        if entities_created["lead"]:
            lead_info = entities_created["lead"]
            if lead_info.get("created"):
                task_description_parts.append(f"New lead added: {lead_info['name']}")
                task_title = f"Contact new lead: {lead_info['name']}"
            elif not lead_info.get("blocked"):
                task_description_parts.append(f"Existing lead identified: {lead_info['name']}")

        task_description_parts.append(f"\nContext: {context}")
        task_description = "\n".join(task_description_parts)

        if entities_created["referral_partner"] or entities_created["lead"]:
            task_priority = "high" if entities_created["lead"] and entities_created["lead"].get("created") else "medium"
            task_due = datetime.now(timezone.utc) + timedelta(days=1)
            task_contact_name = entities_created["lead"]["name"] if entities_created["lead"] else (entities_created["referral_partner"]["name"] if entities_created["referral_partner"] else None)
            task_related_type = "lead" if lead_id else "partner"

            result = db.execute(text("""
                INSERT INTO tasks (title, description, status, priority, due_date, owner_id, lead_id, related_contact_name, related_type, created_at, updated_at)
                VALUES (:title, :description, :status, :priority, :due_date, :owner_id, :lead_id, :contact_name, :related_type, NOW(), NOW())
                RETURNING id
            """), {
                "title": task_title,
                "description": task_description,
                "status": "pending",
                "priority": task_priority,
                "due_date": task_due,
                "owner_id": current_user.id,
                "lead_id": lead_id,
                "contact_name": task_contact_name,
                "related_type": task_related_type
            })
            task_id = result.scalar()
            entities_created["task"] = {
                "id": task_id,
                "title": task_title
            }
            logger.info(f"[SCREENSHOT] Created task: {task_title} (ID: {task_id})")

        db.commit()

        # === Step 5: Build response message ===
        message_parts = []

        if entities_created["referral_partner"]:
            partner = entities_created["referral_partner"]
            if partner["created"]:
                message_parts.append(f"I've added {partner['name']} as a new referral partner in your CRM.")
            else:
                message_parts.append(f"I found {partner['name']} is already in your referral partners.")

        if entities_created["lead"]:
            lead = entities_created["lead"]
            if lead.get("blocked"):
                lead_name = lead.get("name", "the lead")
                message_parts.append(f"I found potential lead information for {lead_name}, but I need some additional details before I can create the lead.")
            elif lead.get("created"):
                message_parts.append(f"I've created a new lead for {lead['name']}.")
            else:
                message_parts.append(f"I found {lead['name']} is already in your leads.")

        if entities_created["task"]:
            message_parts.append(f"I've created a follow-up task for you: '{entities_created['task']['title']}'.")

        if not message_parts:
            message_parts.append("I analyzed the screenshot but couldn't identify any partner or lead information. Please try with a clearer image showing contact details.")

        response_message = " ".join(message_parts)

        response_data = {
            "message": response_message,
            "response": response_message,
            "entities_created": entities_created,
            "extracted_data": extracted_data
        }

        if missing_fields:
            response_data["missing_fields"] = missing_fields
            response_data["needs_followup"] = True
            field_labels = [f["label"] for f in missing_fields]
            response_data["followup_prompt"] = f"To create this lead, I still need: {', '.join(field_labels)}. Can you provide this information?"

        return response_data

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"[SCREENSHOT] Error processing screenshot: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Failed to process screenshot")


@router.post("/ai/complete-lead-from-screenshot")
async def complete_lead_from_screenshot(
    request: Request,
    db: Session = Depends(lambda: get_db_dep()),
    current_user = Depends(current_user_dep)
):
    """
    Complete lead creation with user-provided missing information.

    This endpoint is called after parse-screenshot returns missing_fields.
    The user provides the missing data (phone, email, referral partner name),
    and this endpoint creates the lead with the combined data.

    Request body:
    {
        "extracted_data": { ... original extracted data from parse-screenshot ... },
        "additional_info": {
            "phone": "optional phone number",
            "email": "optional email address",
            "referral_partner_name": "optional partner name"
        }
    }
    """
    models = get_models()
    Lead = models['Lead']
    ReferralPartner = models['ReferralPartner']
    LeadStage = models['LeadStage']

    try:
        data = await request.json()
        extracted_data = data.get("extracted_data", {})
        additional_info = data.get("additional_info", {})

        lead_data = extracted_data.get("lead", {})
        partner_data = extracted_data.get("referral_partner", {})

        if not lead_data:
            raise HTTPException(status_code=400, detail="No lead data provided")

        lead_name = lead_data.get("name", "")
        lead_email = additional_info.get("email") or lead_data.get("email")
        lead_phone = additional_info.get("phone") or lead_data.get("phone")
        lead_address = lead_data.get("address")
        lead_loan_type = lead_data.get("loan_type")
        lead_notes = lead_data.get("notes")

        referral_partner_name = additional_info.get("referral_partner_name") or partner_data.get("name")
        referral_partner_id = None

        if referral_partner_name:
            existing_partner = db.query(ReferralPartner).filter(
                ReferralPartner.name == referral_partner_name
            ).first()

            if existing_partner:
                referral_partner_id = existing_partner.id
            else:
                new_partner = ReferralPartner(
                    name=referral_partner_name,
                    business_name=partner_data.get("company", ""),
                    contact_name=referral_partner_name,
                    category=partner_data.get("type", "realtor"),
                    company=partner_data.get("company"),
                    type=partner_data.get("type", "other"),
                    phone=partner_data.get("phone"),
                    email=partner_data.get("email"),
                    status="active",
                    notes=f"Added via screenshot import on {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')}"
                )
                db.add(new_partner)
                db.flush()
                referral_partner_id = new_partner.id

        name_parts = lead_name.split(" ", 1)
        first_name = name_parts[0]
        last_name = name_parts[1] if len(name_parts) > 1 else ""

        validation_errors = []
        if not first_name or not first_name.strip():
            validation_errors.append("First name is required")
        if not lead_phone and not lead_email:
            validation_errors.append("Phone number or email is required")
        if not referral_partner_id:
            validation_errors.append("Referral partner is required")

        if validation_errors:
            raise HTTPException(status_code=400, detail=f"Missing required fields: {', '.join(validation_errors)}")

        new_lead = Lead(
            name=lead_name,
            first_name=first_name,
            last_name=last_name,
            email=lead_email,
            phone=lead_phone,
            address=lead_address,
            property_address=lead_address,
            loan_type=lead_loan_type,
            source="screenshot_import",
            stage=LeadStage.NEW,
            owner_id=current_user.id,
            referral_partner_id=referral_partner_id,
            notes=f"Imported from screenshot on {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')}. {lead_notes or ''}",
            lead_received_date=datetime.now(timezone.utc)
        )
        db.add(new_lead)
        db.flush()

        from services.client_file_service import ensure_client_file
        ensure_client_file(db, new_lead)

        task_title = f"Contact new lead: {new_lead.name}"
        task_due = datetime.now(timezone.utc) + timedelta(days=1)
        result = db.execute(text("""
            INSERT INTO tasks (title, description, status, priority, due_date, owner_id, lead_id, related_contact_name, related_type, created_at, updated_at)
            VALUES (:title, :description, :status, :priority, :due_date, :owner_id, :lead_id, :contact_name, :related_type, NOW(), NOW())
            RETURNING id
        """), {
            "title": task_title,
            "description": f"New lead added: {new_lead.name}",
            "status": "pending",
            "priority": "high",
            "due_date": task_due,
            "owner_id": current_user.id,
            "lead_id": new_lead.id,
            "contact_name": new_lead.name,
            "related_type": "lead"
        })
        task_id = result.scalar()

        db.commit()

        logger.info(f"[SCREENSHOT] Created lead with additional info: {new_lead.name} (ID: {new_lead.id})")

        return {
            "message": f"I've created a new lead for {new_lead.name} and added a follow-up task.",
            "entities_created": {
                "lead": {
                    "id": new_lead.id,
                    "name": new_lead.name,
                    "created": True
                },
                "task": {
                    "id": task_id,
                    "title": task_title
                }
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"[SCREENSHOT] Error completing lead creation: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Failed to create lead")


@router.get("/ai/langgraph-status")
async def langgraph_status():
    """
    Check if LangGraph agent is available and configured.
    """
    try:
        from agents.orchestrator import create_orchestrator
        from agents.state import AgentState

        return {
            "available": True,
            "version": "1.0.0",
            "nodes": ["analyze", "gather", "reason", "execute", "respond"],
            "message": "LangGraph AI Agent is available"
        }
    except ImportError as e:
        return {
            "available": False,
            "error": "Internal server error",
            "message": "LangGraph dependencies not installed"
        }


def set_dependencies(get_db_func, get_current_user_func):
    """Set dependencies for this router"""
    global _get_db, _get_current_user
    _get_db = get_db_func
    _get_current_user = get_current_user_func
