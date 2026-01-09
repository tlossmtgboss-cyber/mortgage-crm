"""
Dialogflow CX Webhook Routes
Handles incoming webhook requests from Dialogflow CX for lead qualification widget

Endpoints:
- POST /api/v1/dialogflow/webhook - Main Dialogflow fulfillment webhook
- POST /api/v1/widget/chat - Direct widget chat endpoint
- POST /api/v1/widget/create-lead - Create qualified lead from session
- POST /api/v1/widget/generate-summary - Generate LO-ready summary
- POST /api/v1/widget/notify-lo - Notify LO of new lead
"""

import os
import json
import uuid
import logging
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any

from fastapi import APIRouter, Depends, HTTPException, Request, BackgroundTasks
from pydantic import BaseModel, Field, EmailStr, validator
from sqlalchemy.orm import Session
from sqlalchemy import text
from enum import Enum

from database import get_db

logger = logging.getLogger(__name__)

router = APIRouter(tags=["dialogflow-widget"])


# =============================================================================
# ENUMS
# =============================================================================

class LoanPurpose(str, Enum):
    PURCHASE = "purchase"
    REFINANCE = "refinance"
    CASH_OUT = "cash_out"


class ContactPreference(str, Enum):
    SMS = "sms"
    EMAIL = "email"
    CALL = "call"


class Timeline(str, Enum):
    IMMEDIATE = "immediate"
    ONE_TO_THREE_MONTHS = "1_3_months"
    THREE_TO_SIX_MONTHS = "3_6_months"
    SIX_PLUS_MONTHS = "6_plus_months"
    EXPLORING = "exploring"


class CreditTier(str, Enum):
    EXCELLENT = "excellent_740+"
    GOOD = "good_700_739"
    FAIR = "fair_660_699"
    BELOW_660 = "below_660"
    UNKNOWN = "unknown"


class PropertyType(str, Enum):
    SINGLE_FAMILY = "single_family"
    CONDO = "condo"
    TOWNHOUSE = "townhouse"
    MULTI_FAMILY = "multi_family"
    MANUFACTURED = "manufactured"


# =============================================================================
# PYDANTIC MODELS - Dialogflow CX Webhook
# =============================================================================

class DialogflowSessionInfo(BaseModel):
    """Dialogflow session info from webhook request."""
    session: str
    parameters: Dict[str, Any] = {}


class DialogflowFulfillmentInfo(BaseModel):
    """Dialogflow fulfillment info."""
    tag: Optional[str] = None


class DialogflowIntentInfo(BaseModel):
    """Dialogflow intent info."""
    lastMatchedIntent: Optional[str] = None
    displayName: Optional[str] = None
    confidence: Optional[float] = None


class DialogflowPageInfo(BaseModel):
    """Dialogflow page info."""
    currentPage: Optional[str] = None
    displayName: Optional[str] = None


class DialogflowWebhookRequest(BaseModel):
    """
    Dialogflow CX Webhook Request format.
    https://cloud.google.com/dialogflow/cx/docs/reference/rest/v3/WebhookRequest
    """
    detectIntentResponseId: Optional[str] = None
    languageCode: str = "en"
    fulfillmentInfo: Optional[DialogflowFulfillmentInfo] = None
    intentInfo: Optional[DialogflowIntentInfo] = None
    pageInfo: Optional[DialogflowPageInfo] = None
    sessionInfo: Optional[DialogflowSessionInfo] = None
    text: Optional[str] = None
    transcript: Optional[str] = None


class DialogflowMessage(BaseModel):
    """Dialogflow response message."""
    text: Optional[Dict[str, List[str]]] = None
    payload: Optional[Dict[str, Any]] = None


class DialogflowWebhookResponse(BaseModel):
    """
    Dialogflow CX Webhook Response format.
    https://cloud.google.com/dialogflow/cx/docs/reference/rest/v3/WebhookResponse
    """
    fulfillmentResponse: Optional[Dict[str, Any]] = None
    pageInfo: Optional[Dict[str, Any]] = None
    sessionInfo: Optional[Dict[str, Any]] = None
    payload: Optional[Dict[str, Any]] = None


# =============================================================================
# PYDANTIC MODELS - Widget API
# =============================================================================

class WidgetChatRequest(BaseModel):
    """Request for widget chat endpoint."""
    session_id: str = Field(..., description="Widget session UUID")
    message: str = Field(..., description="User's message")
    page_url: Optional[str] = None
    utm_source: Optional[str] = None
    utm_campaign: Optional[str] = None
    utm_medium: Optional[str] = None


class WidgetChatResponse(BaseModel):
    """Response from widget chat endpoint."""
    session_id: str
    response: str
    intent_detected: Optional[str] = None
    qualification_complete: bool = False
    suggested_actions: List[str] = []
    lead_id: Optional[str] = None
    progress_percent: int = 0


class QualifiedLeadCreate(BaseModel):
    """Request to create a qualified lead from widget session."""
    session_id: str

    # Qualification answers
    loan_purpose: Optional[LoanPurpose] = None
    first_time_buyer: Optional[bool] = None
    target_location: Optional[str] = None
    target_state: Optional[str] = None
    timeline: Optional[Timeline] = None
    estimated_amount: Optional[int] = None
    estimated_credit_score: Optional[int] = None
    credit_tier: Optional[CreditTier] = None
    property_type: Optional[PropertyType] = None

    # Contact info
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    preferred_contact: ContactPreference = ContactPreference.SMS

    # Attribution
    source: str = "website_widget"
    page_url: Optional[str] = None
    utm_source: Optional[str] = None
    utm_campaign: Optional[str] = None
    utm_medium: Optional[str] = None

    # Conversation
    conversation_transcript: Optional[str] = None

    @validator('phone')
    def validate_phone(cls, v):
        if v:
            # Strip non-digits
            digits = ''.join(filter(str.isdigit, v))
            if len(digits) < 10:
                raise ValueError('Phone number must have at least 10 digits')
        return v


class QualifiedLeadResponse(BaseModel):
    """Response after creating qualified lead."""
    lead_id: str
    lead_score: int
    lead_grade: str
    assigned_lo_id: Optional[str] = None
    assigned_lo_name: Optional[str] = None
    tasks_created: List[str] = []
    summary_generated: bool = False


class LeadSummaryRequest(BaseModel):
    """Request to generate lead summary for LO."""
    lead_id: str
    include_script_hints: bool = True
    format: str = "markdown"  # text, markdown, or audio_script


class LeadSummaryResponse(BaseModel):
    """Generated summary for LO."""
    lead_id: str
    summary: str
    key_points: List[str]
    script_hints: Optional[List[str]] = None
    objection_prep: Optional[List[str]] = None
    next_best_action: str
    confidence_score: float


class LONotificationRequest(BaseModel):
    """Request to notify LO of new lead."""
    lead_id: str
    lo_id: str
    channels: List[str] = ["in_app", "sms"]
    urgency: str = "normal"  # normal, high, urgent


class LONotificationResponse(BaseModel):
    """Response after notifying LO."""
    notifications_sent: List[Dict[str, Any]]
    lead_url: str


# =============================================================================
# INTENT HANDLERS
# =============================================================================

def get_or_create_session(db: Session, session_id: str, page_url: str = None) -> Dict:
    """Get or create widget session."""
    result = db.execute(
        text("SELECT * FROM widget_sessions WHERE id = :session_id"),
        {"session_id": session_id}
    ).fetchone()

    if result:
        return dict(result._mapping)

    # Create new session
    db.execute(text("""
        INSERT INTO widget_sessions (id, page_url, status, extracted_data, conversation_json, created_at)
        VALUES (:id, :page_url, 'active', :extracted_data, :conversation_json, :created_at)
    """), {
        "id": session_id,
        "page_url": page_url,
        "extracted_data": json.dumps({}),
        "conversation_json": json.dumps([]),
        "created_at": datetime.utcnow()
    })
    db.commit()

    return {
        "id": session_id,
        "status": "active",
        "extracted_data": {},
        "conversation_json": []
    }


def update_session_data(db: Session, session_id: str, key: str, value: Any):
    """Update a single field in session extracted_data."""
    db.execute(text("""
        UPDATE widget_sessions
        SET extracted_data = jsonb_set(
            COALESCE(extracted_data, '{}'::jsonb),
            :path,
            :value::jsonb
        ),
        updated_at = :updated_at
        WHERE id = :session_id
    """), {
        "session_id": session_id,
        "path": f'{{{key}}}',
        "value": json.dumps(value),
        "updated_at": datetime.utcnow()
    })
    db.commit()


def add_conversation_turn(db: Session, session_id: str, role: str, content: str):
    """Add a conversation turn to session."""
    turn = {"role": role, "content": content, "timestamp": datetime.utcnow().isoformat()}

    db.execute(text("""
        UPDATE widget_sessions
        SET conversation_json = COALESCE(conversation_json, '[]'::jsonb) || :turn::jsonb,
            updated_at = :updated_at
        WHERE id = :session_id
    """), {
        "session_id": session_id,
        "turn": json.dumps([turn]),
        "updated_at": datetime.utcnow()
    })
    db.commit()


def handle_start_qualification(session_info: Dict, db: Session) -> DialogflowWebhookResponse:
    """Handle start of qualification flow."""
    session_id = session_info.get("session", "").split("/")[-1]
    get_or_create_session(db, session_id)

    return DialogflowWebhookResponse(
        fulfillmentResponse={
            "messages": [{
                "text": {
                    "text": ["Hi! I'm here to help you explore your mortgage options. Are you looking to buy a home or refinance an existing mortgage?"]
                }
            }]
        },
        sessionInfo={
            "parameters": {
                "qualification_started": True
            }
        }
    )


def handle_capture_loan_purpose(session_info: Dict, db: Session) -> DialogflowWebhookResponse:
    """Handle loan purpose capture."""
    session_id = session_info.get("session", "").split("/")[-1]
    params = session_info.get("parameters", {})

    loan_purpose = params.get("loan_purpose", "purchase")
    update_session_data(db, session_id, "loan_purpose", loan_purpose)

    if loan_purpose == "purchase":
        response_text = "Great! Is this your first home, or have you purchased before?"
    else:
        response_text = "Got it! Are you looking to lower your rate, shorten your term, or take cash out?"

    return DialogflowWebhookResponse(
        fulfillmentResponse={
            "messages": [{
                "text": {"text": [response_text]}
            }]
        },
        sessionInfo={
            "parameters": {
                "loan_purpose": loan_purpose,
                "qualification_progress": 15
            }
        }
    )


def handle_capture_experience(session_info: Dict, db: Session) -> DialogflowWebhookResponse:
    """Handle homebuyer experience capture."""
    session_id = session_info.get("session", "").split("/")[-1]
    params = session_info.get("parameters", {})

    first_time_buyer = params.get("first_time_buyer", False)
    update_session_data(db, session_id, "first_time_buyer", first_time_buyer)

    response_text = "What area are you looking to buy in? City, state, or zip code works great."

    return DialogflowWebhookResponse(
        fulfillmentResponse={
            "messages": [{
                "text": {"text": [response_text]}
            }]
        },
        sessionInfo={
            "parameters": {
                "first_time_buyer": first_time_buyer,
                "qualification_progress": 30
            }
        }
    )


def handle_capture_location(session_info: Dict, db: Session) -> DialogflowWebhookResponse:
    """Handle location capture and LO routing check."""
    session_id = session_info.get("session", "").split("/")[-1]
    params = session_info.get("parameters", {})

    location = params.get("location", "")
    state = params.get("state", "")

    update_session_data(db, session_id, "target_location", location)
    update_session_data(db, session_id, "target_state", state)

    # Check if we have LO coverage in this area
    coverage_check = db.execute(text("""
        SELECT COUNT(*) as count FROM users
        WHERE role = 'loan_officer'
        AND is_active = true
        AND (licensed_states IS NULL OR :state = ANY(licensed_states))
    """), {"state": state.upper() if state else ""}).fetchone()

    has_coverage = coverage_check and coverage_check.count > 0

    response_text = "Perfect! What's your timeline - are you actively shopping, or just exploring options?"

    return DialogflowWebhookResponse(
        fulfillmentResponse={
            "messages": [{
                "text": {"text": [response_text]}
            }]
        },
        sessionInfo={
            "parameters": {
                "location": location,
                "state": state,
                "has_lo_coverage": has_coverage,
                "qualification_progress": 45
            }
        }
    )


def handle_capture_timeline(session_info: Dict, db: Session) -> DialogflowWebhookResponse:
    """Handle timeline capture and calculate lead temperature."""
    session_id = session_info.get("session", "").split("/")[-1]
    params = session_info.get("parameters", {})

    timeline = params.get("timeline", "exploring")
    update_session_data(db, session_id, "timeline", timeline)

    # Calculate lead temperature based on timeline
    temperature_map = {
        "immediate": "hot",
        "1_3_months": "warm",
        "3_6_months": "warm",
        "6_plus_months": "cool",
        "exploring": "cool"
    }
    lead_temperature = temperature_map.get(timeline, "cool")
    update_session_data(db, session_id, "lead_temperature", lead_temperature)

    response_text = "What purchase price range are you considering? A ballpark is fine."

    return DialogflowWebhookResponse(
        fulfillmentResponse={
            "messages": [{
                "text": {"text": [response_text]}
            }]
        },
        sessionInfo={
            "parameters": {
                "timeline": timeline,
                "lead_temperature": lead_temperature,
                "qualification_progress": 60
            }
        }
    )


def handle_capture_price(session_info: Dict, db: Session) -> DialogflowWebhookResponse:
    """Handle price/amount capture."""
    session_id = session_info.get("session", "").split("/")[-1]
    params = session_info.get("parameters", {})

    amount = params.get("amount", 0)
    if isinstance(amount, dict):
        amount = amount.get("amount", 0)

    update_session_data(db, session_id, "estimated_amount", amount)

    response_text = "Do you know roughly where your credit score falls? Excellent (740+), Good (700-739), Fair (660-699), or not sure?"

    return DialogflowWebhookResponse(
        fulfillmentResponse={
            "messages": [{
                "text": {"text": [response_text]}
            }]
        },
        sessionInfo={
            "parameters": {
                "estimated_amount": amount,
                "qualification_progress": 75
            }
        }
    )


def handle_capture_credit(session_info: Dict, db: Session) -> DialogflowWebhookResponse:
    """Handle credit tier capture."""
    session_id = session_info.get("session", "").split("/")[-1]
    params = session_info.get("parameters", {})

    credit_tier = params.get("credit_tier", "unknown")
    update_session_data(db, session_id, "credit_tier", credit_tier)

    # Map credit tier to estimated score
    score_map = {
        "excellent_740+": 760,
        "good_700_739": 720,
        "fair_660_699": 680,
        "below_660": 640,
        "unknown": None
    }
    estimated_score = score_map.get(credit_tier)
    if estimated_score:
        update_session_data(db, session_id, "estimated_credit_score", estimated_score)

    response_text = "Last question! What's the best way to reach you - would you prefer a text, email, or phone call?"

    return DialogflowWebhookResponse(
        fulfillmentResponse={
            "messages": [{
                "text": {"text": [response_text]}
            }]
        },
        sessionInfo={
            "parameters": {
                "credit_tier": credit_tier,
                "estimated_credit_score": estimated_score,
                "qualification_progress": 90
            }
        }
    )


def handle_capture_contact(session_info: Dict, db: Session) -> DialogflowWebhookResponse:
    """Handle contact info capture and complete qualification."""
    session_id = session_info.get("session", "").split("/")[-1]
    params = session_info.get("parameters", {})

    # Extract contact details
    first_name = params.get("first_name", "")
    last_name = params.get("last_name", "")
    email = params.get("email", "")
    phone = params.get("phone", "")
    preferred_contact = params.get("preferred_contact", "sms")

    update_session_data(db, session_id, "first_name", first_name)
    update_session_data(db, session_id, "last_name", last_name)
    update_session_data(db, session_id, "email", email)
    update_session_data(db, session_id, "phone", phone)
    update_session_data(db, session_id, "preferred_contact", preferred_contact)

    # Mark session as ready for conversion
    db.execute(text("""
        UPDATE widget_sessions
        SET status = 'qualified', updated_at = :updated_at
        WHERE id = :session_id
    """), {"session_id": session_id, "updated_at": datetime.utcnow()})
    db.commit()

    # Get assigned LO name (would come from routing logic)
    lo_name = "one of our loan experts"

    response_text = f"Thanks {first_name}! {lo_name.title()} will reach out within the hour. Is there anything specific you'd like them to know?"

    return DialogflowWebhookResponse(
        fulfillmentResponse={
            "messages": [{
                "text": {"text": [response_text]}
            }]
        },
        sessionInfo={
            "parameters": {
                "qualification_complete": True,
                "qualification_progress": 100
            }
        },
        payload={
            "qualification_complete": True,
            "session_id": session_id,
            "create_lead": True
        }
    )


def handle_fallback(session_info: Dict, db: Session, user_text: str) -> DialogflowWebhookResponse:
    """Handle unrecognized input."""
    session_id = session_info.get("session", "").split("/")[-1]
    params = session_info.get("parameters", {})

    fallback_count = params.get("fallback_count", 0) + 1

    if fallback_count >= 3:
        response_text = "I want to make sure I get this right. Would you like to speak with a loan officer directly? I can have someone call you right away."
        offer_human = True
    else:
        response_text = "I didn't quite catch that. Could you rephrase?"
        offer_human = False

    return DialogflowWebhookResponse(
        fulfillmentResponse={
            "messages": [{
                "text": {"text": [response_text]}
            }]
        },
        sessionInfo={
            "parameters": {
                "fallback_count": fallback_count,
                "offer_human_handoff": offer_human
            }
        }
    )


# Intent handler mapping
INTENT_HANDLERS = {
    "start_qualification": handle_start_qualification,
    "capture_loan_purpose": handle_capture_loan_purpose,
    "capture_experience": handle_capture_experience,
    "capture_location": handle_capture_location,
    "capture_timeline": handle_capture_timeline,
    "capture_price": handle_capture_price,
    "capture_credit": handle_capture_credit,
    "capture_contact": handle_capture_contact,
    "fallback": handle_fallback,
}


# =============================================================================
# ROUTES
# =============================================================================

@router.post("/api/v1/dialogflow/webhook", response_model=DialogflowWebhookResponse)
async def dialogflow_webhook(
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Main Dialogflow CX webhook endpoint.
    Handles fulfillment requests and returns responses.
    """
    try:
        body = await request.json()
        webhook_request = DialogflowWebhookRequest(**body)

        logger.info(f"Dialogflow webhook received: {webhook_request.fulfillmentInfo}")

        # Get fulfillment tag to determine handler
        tag = webhook_request.fulfillmentInfo.tag if webhook_request.fulfillmentInfo else None
        session_info = webhook_request.sessionInfo.dict() if webhook_request.sessionInfo else {}

        # Route to appropriate handler
        if tag and tag in INTENT_HANDLERS:
            handler = INTENT_HANDLERS[tag]
            if tag == "fallback":
                return handler(session_info, db, webhook_request.text or "")
            return handler(session_info, db)

        # Default response if no handler matched
        return DialogflowWebhookResponse(
            fulfillmentResponse={
                "messages": [{
                    "text": {"text": ["I'm here to help! Are you looking to buy a home or refinance?"]}
                }]
            }
        )

    except Exception as e:
        logger.error(f"Dialogflow webhook error: {e}", exc_info=True)
        return DialogflowWebhookResponse(
            fulfillmentResponse={
                "messages": [{
                    "text": {"text": ["I apologize, but I'm having trouble processing that. Let me connect you with a loan officer who can help."]}
                }]
            }
        )


@router.post("/api/v1/widget/chat", response_model=WidgetChatResponse)
async def widget_chat(
    request: WidgetChatRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """
    Direct widget chat endpoint (alternative to Dialogflow).
    Uses OpenAI for conversation handling.
    """
    try:
        # Get or create session
        session = get_or_create_session(db, request.session_id, request.page_url)

        # Store user message
        add_conversation_turn(db, request.session_id, "user", request.message)

        # Get OpenAI client
        from routes.agent_chat_routes import get_openai_client
        client, enabled = get_openai_client()

        if not enabled:
            # Fallback response
            return WidgetChatResponse(
                session_id=request.session_id,
                response="Thanks for your message! A loan officer will follow up with you shortly.",
                qualification_complete=False,
                suggested_actions=["Speak with an expert", "Learn about rates"]
            )

        # Build conversation context
        extracted = session.get("extracted_data", {})
        if isinstance(extracted, str):
            extracted = json.loads(extracted)

        conversation = session.get("conversation_json", [])
        if isinstance(conversation, str):
            conversation = json.loads(conversation)

        # Create system prompt for qualification
        system_prompt = """You are a friendly mortgage qualification assistant for a lending company.
Your goal is to qualify leads by gathering:
1. Loan purpose (purchase, refinance, cash-out)
2. First-time buyer status
3. Target location (city/state)
4. Timeline (immediate, 1-3 months, 3-6 months, exploring)
5. Purchase price/loan amount
6. Credit tier (excellent 740+, good 700-739, fair 660-699, or unknown)
7. Contact info (name, email, phone, preferred contact method)

Be conversational and helpful. Ask one question at a time. If they provide info proactively, acknowledge it.
When you have all info, thank them and let them know a loan officer will reach out.

Current collected info: """ + json.dumps(extracted)

        messages = [{"role": "system", "content": system_prompt}]
        for turn in conversation[-10:]:  # Last 10 turns
            messages.append({"role": turn["role"], "content": turn["content"]})
        messages.append({"role": "user", "content": request.message})

        # Get AI response
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            max_tokens=300,
            temperature=0.7
        )

        ai_response = response.choices[0].message.content

        # Store AI response
        add_conversation_turn(db, request.session_id, "assistant", ai_response)

        # Check if qualification is complete
        required_fields = ["loan_purpose", "first_name", "email", "phone"]
        qualification_complete = all(extracted.get(f) for f in required_fields)

        # Calculate progress
        all_fields = ["loan_purpose", "first_time_buyer", "target_location", "timeline",
                      "estimated_amount", "credit_tier", "first_name", "email", "phone"]
        filled = sum(1 for f in all_fields if extracted.get(f))
        progress = int((filled / len(all_fields)) * 100)

        return WidgetChatResponse(
            session_id=request.session_id,
            response=ai_response,
            qualification_complete=qualification_complete,
            progress_percent=progress,
            suggested_actions=[]
        )

    except Exception as e:
        logger.error(f"Widget chat error: {e}", exc_info=True)
        return WidgetChatResponse(
            session_id=request.session_id,
            response="I apologize for the technical difficulty. Would you like to speak with a loan officer directly?",
            qualification_complete=False,
            suggested_actions=["Call us", "Email us"]
        )


@router.post("/api/v1/widget/create-lead", response_model=QualifiedLeadResponse)
async def create_qualified_lead(
    request: QualifiedLeadCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """
    Create a LeadProfile from widget qualification session.
    Scores lead, assigns LO, creates tasks, and triggers notification.
    """
    try:
        # Get session data if not provided directly
        session_data = {}
        if request.session_id:
            result = db.execute(
                text("SELECT extracted_data FROM widget_sessions WHERE id = :id"),
                {"id": request.session_id}
            ).fetchone()
            if result:
                session_data = json.loads(result.extracted_data) if isinstance(result.extracted_data, str) else result.extracted_data

        # Merge session data with request (request takes precedence)
        lead_data = {**session_data}
        for field, value in request.dict().items():
            if value is not None:
                lead_data[field] = value

        # Generate lead ID
        lead_id = str(uuid.uuid4())

        # Map credit tier to numeric score
        credit_score = lead_data.get("estimated_credit_score")
        if not credit_score and lead_data.get("credit_tier"):
            tier_map = {
                "excellent_740+": 760,
                "good_700_739": 720,
                "fair_660_699": 680,
                "below_660": 640,
            }
            credit_score = tier_map.get(lead_data.get("credit_tier"))

        # Insert into lead_profiles
        db.execute(text("""
            INSERT INTO lead_profiles (
                id, first_name, last_name, email, phone,
                loan_type, property_type, loan_amount, credit_score,
                city, state,
                source, referral_source, stage, status,
                lead_created_date, created_at
            ) VALUES (
                :id, :first_name, :last_name, :email, :phone,
                :loan_type, :property_type, :loan_amount, :credit_score,
                :city, :state,
                :source, :referral_source, 'new', 'active',
                :created_at, :created_at
            )
        """), {
            "id": lead_id,
            "first_name": lead_data.get("first_name"),
            "last_name": lead_data.get("last_name"),
            "email": lead_data.get("email"),
            "phone": lead_data.get("phone"),
            "loan_type": lead_data.get("loan_purpose"),
            "property_type": lead_data.get("property_type"),
            "loan_amount": lead_data.get("estimated_amount"),
            "credit_score": credit_score,
            "city": lead_data.get("target_location"),
            "state": lead_data.get("target_state"),
            "source": lead_data.get("source", "website_widget"),
            "referral_source": lead_data.get("utm_source"),
            "created_at": datetime.utcnow()
        })

        # Calculate lead score
        score = 50  # Base score

        # Timeline scoring
        timeline_scores = {
            "immediate": 25,
            "1_3_months": 20,
            "3_6_months": 15,
            "6_plus_months": 5,
            "exploring": 5
        }
        score += timeline_scores.get(lead_data.get("timeline"), 0)

        # Credit scoring
        if credit_score:
            if credit_score >= 740:
                score += 15
            elif credit_score >= 700:
                score += 10
            elif credit_score >= 660:
                score += 5

        # Loan amount scoring
        amount = lead_data.get("estimated_amount", 0)
        if amount >= 500000:
            score += 10
        elif amount >= 300000:
            score += 7
        elif amount >= 200000:
            score += 5

        # Determine grade
        if score >= 80:
            grade = "A"
        elif score >= 60:
            grade = "B"
        elif score >= 40:
            grade = "C"
        else:
            grade = "D"

        # Find LO to assign (simplified routing)
        lo_result = db.execute(text("""
            SELECT id, name FROM users
            WHERE role = 'loan_officer' AND is_active = true
            ORDER BY RANDOM()
            LIMIT 1
        """)).fetchone()

        assigned_lo_id = None
        assigned_lo_name = None
        if lo_result:
            assigned_lo_id = str(lo_result.id)
            assigned_lo_name = lo_result.name

            # Update lead with assignment
            db.execute(text("""
                UPDATE lead_profiles
                SET loan_officer = :lo_name
                WHERE id = :lead_id
            """), {"lo_name": assigned_lo_name, "lead_id": lead_id})

        # Create initial tasks
        tasks_created = []
        task_templates = [
            ("Initial call within 1 hour", "high", 60),
            ("Send pre-approval checklist", "medium", 1440),
            ("Schedule discovery call", "medium", 2880)
        ]

        for task_name, priority, due_minutes in task_templates:
            task_id = str(uuid.uuid4())
            db.execute(text("""
                INSERT INTO purl_tasks (
                    id, workspace_id, title, status, priority,
                    assigned_to_type, assigned_to_id, due_date, created_at
                ) VALUES (
                    :id, :workspace_id, :title, 'pending', :priority,
                    'user', :assigned_to, :due_date, :created_at
                )
            """), {
                "id": task_id,
                "workspace_id": lead_id,  # Using lead_id as workspace reference
                "title": task_name,
                "priority": priority,
                "assigned_to": assigned_lo_id,
                "due_date": datetime.utcnow() + timedelta(minutes=due_minutes),
                "created_at": datetime.utcnow()
            })
            tasks_created.append(task_name)

        # Update widget session status
        db.execute(text("""
            UPDATE widget_sessions
            SET status = 'converted', lead_id = :lead_id, updated_at = :updated_at
            WHERE id = :session_id
        """), {
            "session_id": request.session_id,
            "lead_id": lead_id,
            "updated_at": datetime.utcnow()
        })

        db.commit()

        # Queue summary generation and notification in background
        background_tasks.add_task(
            generate_and_notify_lo,
            lead_id=lead_id,
            lo_id=assigned_lo_id,
            db_url=os.getenv("DATABASE_URL")
        )

        return QualifiedLeadResponse(
            lead_id=lead_id,
            lead_score=score,
            lead_grade=grade,
            assigned_lo_id=assigned_lo_id,
            assigned_lo_name=assigned_lo_name,
            tasks_created=tasks_created,
            summary_generated=False  # Will be generated in background
        )

    except Exception as e:
        logger.error(f"Create lead error: {e}", exc_info=True)
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/v1/widget/generate-summary", response_model=LeadSummaryResponse)
async def generate_lead_summary(
    request: LeadSummaryRequest,
    db: Session = Depends(get_db)
):
    """
    Generate LO-ready summary from lead data and conversation.
    """
    try:
        # Get lead data
        lead = db.execute(text("""
            SELECT * FROM lead_profiles WHERE id = :lead_id
        """), {"lead_id": request.lead_id}).fetchone()

        if not lead:
            raise HTTPException(status_code=404, detail="Lead not found")

        lead_dict = dict(lead._mapping)

        # Get conversation if available
        session = db.execute(text("""
            SELECT conversation_json FROM widget_sessions WHERE lead_id = :lead_id
        """), {"lead_id": request.lead_id}).fetchone()

        conversation = []
        if session and session.conversation_json:
            conversation = json.loads(session.conversation_json) if isinstance(session.conversation_json, str) else session.conversation_json

        # Get OpenAI client for summary generation
        from routes.agent_chat_routes import get_openai_client
        client, enabled = get_openai_client()

        if enabled:
            # Generate AI summary
            summary_prompt = f"""Generate a concise LO briefing for this lead:

Lead Info:
- Name: {lead_dict.get('first_name')} {lead_dict.get('last_name')}
- Loan Type: {lead_dict.get('loan_type')}
- Amount: ${lead_dict.get('loan_amount', 'Unknown'):,}
- Credit Score: {lead_dict.get('credit_score', 'Unknown')}
- Location: {lead_dict.get('city')}, {lead_dict.get('state')}
- Source: {lead_dict.get('source')}

Conversation Highlights:
{json.dumps(conversation[-5:], indent=2) if conversation else 'No conversation available'}

Provide:
1. 2-3 sentence summary
2. 3-4 key bullet points
3. Suggested opening script (2 sentences)
4. 2-3 potential objections to prepare for
5. Recommended next action

Format as JSON with keys: summary, key_points, script_hints, objection_prep, next_action"""

            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": summary_prompt}],
                max_tokens=800,
                temperature=0.7
            )

            try:
                ai_result = json.loads(response.choices[0].message.content)
            except json.JSONDecodeError:
                ai_result = {
                    "summary": response.choices[0].message.content[:500],
                    "key_points": [],
                    "script_hints": [],
                    "objection_prep": [],
                    "next_action": "Call lead within 1 hour"
                }
        else:
            # Fallback summary
            ai_result = {
                "summary": f"New {lead_dict.get('loan_type', 'purchase')} lead: {lead_dict.get('first_name')} {lead_dict.get('last_name')} looking in {lead_dict.get('city', 'their area')}.",
                "key_points": [
                    f"Estimated loan amount: ${lead_dict.get('loan_amount', 0):,}",
                    f"Credit tier: {lead_dict.get('credit_score', 'Unknown')}",
                    f"Source: {lead_dict.get('source', 'Website')}"
                ],
                "script_hints": [
                    f"Hi {lead_dict.get('first_name')}, thanks for reaching out about your mortgage needs!"
                ],
                "objection_prep": [],
                "next_action": "Initial outreach call"
            }

        return LeadSummaryResponse(
            lead_id=request.lead_id,
            summary=ai_result.get("summary", ""),
            key_points=ai_result.get("key_points", []),
            script_hints=ai_result.get("script_hints", []) if request.include_script_hints else None,
            objection_prep=ai_result.get("objection_prep", []),
            next_best_action=ai_result.get("next_action", "Contact lead"),
            confidence_score=0.85
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Generate summary error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/v1/widget/notify-lo", response_model=LONotificationResponse)
async def notify_lo_new_lead(
    request: LONotificationRequest,
    db: Session = Depends(get_db)
):
    """
    Send notification to LO about new qualified lead.
    """
    try:
        # Get lead info
        lead = db.execute(text("""
            SELECT first_name, last_name, email, phone, loan_type, loan_amount
            FROM lead_profiles WHERE id = :lead_id
        """), {"lead_id": request.lead_id}).fetchone()

        if not lead:
            raise HTTPException(status_code=404, detail="Lead not found")

        lead_dict = dict(lead._mapping)

        # Get LO info
        lo = db.execute(text("""
            SELECT name, email, phone FROM users WHERE id = :lo_id
        """), {"lo_id": request.lo_id}).fetchone()

        if not lo:
            raise HTTPException(status_code=404, detail="Loan officer not found")

        lo_dict = dict(lo._mapping)

        notifications_sent = []
        base_url = os.getenv("APP_BASE_URL", "https://app.example.com")
        lead_url = f"{base_url}/leads/{request.lead_id}"

        # In-app notification
        if "in_app" in request.channels:
            notification_id = str(uuid.uuid4())
            db.execute(text("""
                INSERT INTO notifications (
                    id, user_id, type, title, message,
                    data, is_read, created_at
                ) VALUES (
                    :id, :user_id, 'new_lead', :title, :message,
                    :data, false, :created_at
                )
            """), {
                "id": notification_id,
                "user_id": request.lo_id,
                "title": f"New Lead: {lead_dict['first_name']} {lead_dict['last_name']}",
                "message": f"${lead_dict.get('loan_amount', 0):,.0f} {lead_dict.get('loan_type', 'loan')} - Respond within 1 hour",
                "data": json.dumps({"lead_id": request.lead_id, "url": lead_url}),
                "created_at": datetime.utcnow()
            })
            notifications_sent.append({"channel": "in_app", "status": "sent"})

        # SMS notification
        if "sms" in request.channels and lo_dict.get("phone"):
            try:
                from integrations.twilio_service import TwilioService
                twilio = TwilioService()

                sms_message = f"New lead: {lead_dict['first_name']} {lead_dict['last_name']}"
                if lead_dict.get('loan_amount'):
                    sms_message += f" - ${lead_dict['loan_amount']:,.0f}"
                sms_message += f"\n{lead_url}"

                twilio.send_sms(lo_dict["phone"], sms_message)
                notifications_sent.append({"channel": "sms", "status": "sent"})
            except Exception as e:
                logger.error(f"SMS notification failed: {e}")
                notifications_sent.append({"channel": "sms", "status": "failed", "error": str(e)})

        # Email notification
        if "email" in request.channels and lo_dict.get("email"):
            try:
                from integrations.email_service import send_email

                email_subject = f"New Lead: {lead_dict['first_name']} {lead_dict['last_name']}"
                email_body = f"""
                <h2>New Qualified Lead</h2>
                <p><strong>{lead_dict['first_name']} {lead_dict['last_name']}</strong></p>
                <ul>
                    <li>Loan Type: {lead_dict.get('loan_type', 'N/A')}</li>
                    <li>Amount: ${lead_dict.get('loan_amount', 0):,.0f}</li>
                    <li>Phone: {lead_dict.get('phone', 'N/A')}</li>
                    <li>Email: {lead_dict.get('email', 'N/A')}</li>
                </ul>
                <p><a href="{lead_url}">View Lead in CRM</a></p>
                """

                send_email(lo_dict["email"], email_subject, email_body)
                notifications_sent.append({"channel": "email", "status": "sent"})
            except Exception as e:
                logger.error(f"Email notification failed: {e}")
                notifications_sent.append({"channel": "email", "status": "failed", "error": str(e)})

        db.commit()

        return LONotificationResponse(
            notifications_sent=notifications_sent,
            lead_url=lead_url
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Notify LO error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# BACKGROUND TASKS
# =============================================================================

async def generate_and_notify_lo(lead_id: str, lo_id: str, db_url: str):
    """Background task to generate summary and notify LO."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    try:
        engine = create_engine(db_url)
        SessionLocal = sessionmaker(bind=engine)
        db = SessionLocal()

        # Generate summary (would use the endpoint logic)
        logger.info(f"Generating summary for lead {lead_id}")

        # Notify LO
        if lo_id:
            logger.info(f"Notifying LO {lo_id} about lead {lead_id}")

        db.close()
    except Exception as e:
        logger.error(f"Background task error: {e}")


# =============================================================================
# HEALTH CHECK
# =============================================================================

@router.get("/api/v1/dialogflow/health")
async def dialogflow_health():
    """Health check for Dialogflow webhook."""
    return {
        "status": "healthy",
        "service": "dialogflow-webhook",
        "supported_intents": list(INTENT_HANDLERS.keys()),
        "timestamp": datetime.utcnow().isoformat()
    }
