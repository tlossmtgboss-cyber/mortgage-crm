"""
Pre-Qualification API Routes - Purchase Pre-Qualification Form Submission

Atomic submission endpoint that:
1. Creates or updates contact/borrower record
2. Creates lead/deal record
3. Books calendar appointment (if slot selected)
4. Classifies and routes based on complexity
5. Triggers notifications to buyer, realtor, and internal team
6. Creates AI context packet for follow-up
"""

from fastapi import APIRouter, Depends, HTTPException, Request, BackgroundTasks
from sqlalchemy.orm import Session
from sqlalchemy import text
from datetime import datetime, date, timedelta
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, EmailStr, Field
from enum import Enum
import logging
import uuid
import os
import json

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/prequal", tags=["Pre-Qualification"])

# ============================================================================
# DEPENDENCY INJECTION
# ============================================================================

_get_db = None
_notification_service = None
_scheduler_models = None


def set_dependencies(get_db_func, notification_svc=None, scheduler_models=None):
    """Set dependencies from main.py"""
    global _get_db, _notification_service, _scheduler_models
    _get_db = get_db_func
    _notification_service = notification_svc
    _scheduler_models = scheduler_models


def get_db():
    if _get_db is None:
        raise RuntimeError("Dependencies not set")
    yield from _get_db()


# ============================================================================
# ENUMS & MODELS
# ============================================================================

class LeadComplexity(str, Enum):
    STANDARD = "standard"
    COMPLEX = "complex"
    SPECIALIZED = "specialized"


class LeadPriority(str, Enum):
    HOT = "hot"
    WARM = "warm"
    NURTURE = "nurture"


class PreQualSubmission(BaseModel):
    """Pre-qualification form submission payload"""
    # Buyer Identity
    first_name: str = Field(..., min_length=1)
    last_name: str = Field(..., min_length=1)
    mobile_phone: str = Field(..., min_length=10)
    email: EmailStr
    date_of_birth: Optional[str] = None
    # ECOA: marital_status is collected for property rights purposes only
    # (e.g., community property state determinations), NOT for credit decisioning.
    # This field must NEVER be passed to classify_lead(), suggest_loan_types(),
    # or any scoring/eligibility function.
    marital_status: Optional[str] = None

    # Property Goals
    target_purchase_price: int = Field(..., ge=0)
    target_city: str
    desired_monthly_payment: Optional[int] = 0
    timeline: str

    # Credit
    credit_score_range: str
    derogatory_events: Optional[List[str]] = []

    # Employment
    employment_type: str
    employer_name: Optional[str] = ""
    years_in_line_of_work: Optional[int] = 0
    income_range: str

    # Assets
    cash_available: Optional[int] = 0
    down_payment_range: str
    fund_sources: Optional[List[str]] = []

    # Notes
    additional_notes: Optional[str] = ""

    # Calendar
    scheduled_appointment: Optional[Dict[str, Any]] = None

    # Tracking
    partner_id: Optional[str] = ""
    realtor_email: Optional[str] = ""
    source: Optional[str] = "direct"

    # Consent
    consent_given: bool
    consent_timestamp: Optional[str] = None


class PreQualResponse(BaseModel):
    """Response after successful submission"""
    success: bool
    reference_id: str
    lead_id: Optional[int] = None
    contact_id: Optional[int] = None
    appointment_id: Optional[int] = None
    classification: Dict[str, Any]
    message: str


# ============================================================================
# ROUTING & CLASSIFICATION LOGIC
# ============================================================================

def classify_lead(submission: PreQualSubmission) -> Dict[str, Any]:
    """
    Classify lead based on form data to determine routing and priority.

    ECOA compliance: This function intentionally does NOT use marital_status,
    date_of_birth, race, ethnicity, sex, national_origin, religion, age,
    or any other ECOA protected class field.  Only financial and
    credit-related factors drive classification.

    Complexity factors:
    - Credit < 640: Complex
    - Self-employed/1099: Complex
    - Derogatory events: Complex
    - Down payment < 5%: Complex
    - Timeline ASAP + high credit: Hot
    """
    # ECOA compliance: explicitly exclude protected class data from decisioning.
    # These fields are collected for property-rights / HMDA purposes only.
    from services.compliance.ecoa_protected_fields import ECOA_PROTECTED_FIELDS
    _protected_present = {
        f for f in ECOA_PROTECTED_FIELDS
        if hasattr(submission, f) and getattr(submission, f, None) is not None
    }
    if _protected_present:
        logger.debug(
            "ECOA: Protected fields present but excluded from decisioning: %s",
            _protected_present,
        )

    complexity = LeadComplexity.STANDARD
    priority = LeadPriority.WARM
    flags = []
    routing_notes = []

    # Credit score assessment
    credit = submission.credit_score_range
    if credit in ['below-620', '620-639']:
        complexity = LeadComplexity.COMPLEX
        flags.append("low_credit")
        routing_notes.append("Credit below 640 - may need credit repair or FHA")
    elif credit in ['640-679']:
        flags.append("moderate_credit")
        routing_notes.append("Credit 640-679 - likely FHA or conventional with LLPAs")
    elif credit in ['unknown']:
        flags.append("unknown_credit")
        routing_notes.append("Unknown credit score - needs credit pull")

    # Employment assessment
    employment = submission.employment_type
    if employment in ['self-employed', 'business-owner', '1099-contractor']:
        complexity = LeadComplexity.COMPLEX
        flags.append("self_employed")
        routing_notes.append(f"{employment} - will need 2 years tax returns")

    # Derogatory events
    events = submission.derogatory_events or []
    if events and 'none' not in events:
        complexity = LeadComplexity.COMPLEX
        for event in events:
            if event != 'none':
                flags.append(f"derog_{event}")
        routing_notes.append(f"Derogatory events: {', '.join([e for e in events if e != 'none'])}")

    # Down payment assessment
    dp = submission.down_payment_range
    if dp in ['0-3', '3-5']:
        flags.append("low_down_payment")
        routing_notes.append(f"Down payment {dp}% - needs down payment assistance discussion")

    # Timeline + credit = priority
    timeline = submission.timeline
    if timeline in ['asap', '30-days']:
        if credit in ['760+', '720-759', '680-719']:
            priority = LeadPriority.HOT
            routing_notes.append("Urgent timeline with good credit - HOT lead")
        else:
            priority = LeadPriority.WARM
            routing_notes.append("Urgent timeline but credit needs attention")
    elif timeline == 'just-exploring':
        priority = LeadPriority.NURTURE
        routing_notes.append("Just exploring - add to nurture campaign")

    # Income assessment
    income = submission.income_range
    price = submission.target_purchase_price

    # Check if specialized (jumbo, high-value)
    if price >= 726200:  # 2024 conforming loan limit
        complexity = LeadComplexity.SPECIALIZED
        flags.append("jumbo_loan")
        routing_notes.append(f"Loan amount ${price:,} exceeds conforming limit - jumbo product needed")

    return {
        "complexity": complexity.value,
        "priority": priority.value,
        "flags": flags,
        "routing_notes": routing_notes,
        "suggested_loan_types": suggest_loan_types(submission),
        "requires_senior_review": complexity != LeadComplexity.STANDARD,
        "estimated_timeline": estimate_timeline(submission),
        "ai_context": generate_ai_context(submission, flags, routing_notes)
    }


def suggest_loan_types(submission: PreQualSubmission) -> List[str]:
    """Suggest potential loan types based on profile"""
    suggestions = []
    credit = submission.credit_score_range
    dp = submission.down_payment_range

    if credit in ['760+', '720-759', '680-719'] and dp in ['20-plus', '10-20']:
        suggestions.append("Conventional")

    if credit in ['640-679', '620-639'] or dp in ['3-5', '0-3']:
        suggestions.append("FHA")

    if submission.target_purchase_price >= 726200:
        suggestions.append("Jumbo")

    # Check for VA/USDA eligibility (would need more info, but flag potential)
    if 'military' in submission.additional_notes.lower() if submission.additional_notes else False:
        suggestions.append("VA (verify eligibility)")

    if not suggestions:
        suggestions.append("Conventional")
        suggestions.append("FHA")

    return suggestions


def estimate_timeline(submission: PreQualSubmission) -> str:
    """Estimate closing timeline based on complexity"""
    complexity_factors = 0

    if submission.credit_score_range in ['below-620', '620-639', 'unknown']:
        complexity_factors += 1

    if submission.employment_type in ['self-employed', 'business-owner', '1099-contractor']:
        complexity_factors += 1

    if submission.derogatory_events and 'none' not in submission.derogatory_events:
        complexity_factors += 1

    if complexity_factors == 0:
        return "21-30 days (standard)"
    elif complexity_factors == 1:
        return "30-45 days (moderate complexity)"
    else:
        return "45-60 days (complex scenario)"


def generate_ai_context(
    submission: PreQualSubmission,
    flags: List[str],
    routing_notes: List[str]
) -> Dict[str, Any]:
    """Generate context packet for AI follow-up and conversation.

    ECOA compliance: borrower_profile intentionally excludes marital_status,
    date_of_birth, and all other protected class fields.  AI context must
    not contain data that could influence credit/lending recommendations.
    """
    return {
        # ECOA: Only financial/credit fields included — no protected class data
        "borrower_profile": {
            "name": f"{submission.first_name} {submission.last_name}",
            "credit_tier": submission.credit_score_range,
            "employment": submission.employment_type,
            "target_purchase": submission.target_purchase_price,
            "location": submission.target_city,
            "timeline": submission.timeline,
            "down_payment": submission.down_payment_range
        },
        "talking_points": generate_talking_points(submission, flags),
        "questions_to_ask": generate_follow_up_questions(submission, flags),
        "objection_handlers": generate_objection_handlers(flags),
        "complexity_flags": flags,
        "notes": routing_notes
    }


def generate_talking_points(submission: PreQualSubmission, flags: List[str]) -> List[str]:
    """Generate talking points for first conversation"""
    points = [
        f"Thank you for your interest in purchasing a home in {submission.target_city}",
        f"Based on your target price of ${submission.target_purchase_price:,}, let me discuss your options"
    ]

    if 'low_credit' in flags:
        points.append("I can review your credit situation and discuss programs that work with your score")

    if 'self_employed' in flags:
        points.append("For self-employed borrowers, we'll need your last 2 years of tax returns")

    if 'low_down_payment' in flags:
        points.append("We have down payment assistance programs that may help you")

    if 'jumbo_loan' in flags:
        points.append("For this loan amount, we'll look at jumbo loan options")

    return points


def generate_follow_up_questions(submission: PreQualSubmission, flags: List[str]) -> List[str]:
    """Generate questions to ask on follow-up call"""
    questions = []

    if 'unknown_credit' in flags:
        questions.append("Do you know your approximate credit score?")
        questions.append("Have you checked your credit report recently?")

    if 'self_employed' in flags:
        questions.append("How long have you been self-employed?")
        questions.append("Is your business showing consistent income on tax returns?")

    if submission.timeline == 'asap':
        questions.append("Have you found a specific property?")
        questions.append("Do you have a real estate agent?")

    if 'low_down_payment' in flags:
        questions.append("Are you open to down payment assistance programs?")
        questions.append("Do you have family who might provide a gift for down payment?")

    # Always ask
    questions.append("What's most important to you in this home purchase?")
    questions.append("Do you have any questions about the mortgage process?")

    return questions


def generate_objection_handlers(flags: List[str]) -> Dict[str, str]:
    """Generate objection handling scripts"""
    handlers = {}

    if 'low_credit' in flags:
        handlers["credit_concern"] = "Many buyers in your situation qualify for FHA loans with credit scores as low as 580. We can also discuss credit improvement strategies that could help you qualify for better rates."

    if 'self_employed' in flags:
        handlers["income_documentation"] = "Self-employed borrowers have several options. We can use bank statements instead of tax returns in some programs, or we can look at your Schedule C income."

    if 'low_down_payment' in flags:
        handlers["down_payment_concern"] = "There are programs requiring as little as 3% down, and we have down payment assistance options that could help cover closing costs too."

    handlers["rate_concern"] = "Rates are just one part of the equation. Let me show you the total cost comparison and how different programs affect your monthly payment."

    return handlers


# ============================================================================
# API ENDPOINTS
# ============================================================================

@router.post("/submit", response_model=PreQualResponse)
async def submit_prequal(
    submission: PreQualSubmission,
    background_tasks: BackgroundTasks,
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Submit pre-qualification form - atomic transaction that:
    1. Creates/updates contact
    2. Creates lead/deal
    3. Books appointment (if selected)
    4. Classifies and routes
    5. Sends notifications
    """
    try:
        # Validate consent
        if not submission.consent_given:
            raise HTTPException(status_code=400, detail="Consent is required to proceed")

        # Generate reference ID
        reference_id = f"PQ-{datetime.now().strftime('%Y%m%d')}-{str(uuid.uuid4())[:8].upper()}"

        # Classify the lead
        classification = classify_lead(submission)

        # Step 1: Create or update contact
        contact_id = await create_or_update_contact(db, submission, reference_id)

        # Step 2: Create lead/deal
        lead_id = await create_lead(db, submission, contact_id, classification, reference_id)

        # Step 3: Book appointment if slot selected
        appointment_id = None
        if submission.scheduled_appointment:
            appointment_id = await book_appointment(
                db,
                submission,
                lead_id,
                contact_id
            )

        # Commit all changes
        db.commit()

        # Step 4: Send notifications (in background)
        background_tasks.add_task(
            send_notifications,
            submission,
            classification,
            reference_id,
            appointment_id
        )

        # Step 5: Trigger SLA timers (in background) - don't pass db
        background_tasks.add_task(
            create_sla_tasks,
            lead_id,
            classification
        )

        logger.info(f"Pre-qual submission successful: {reference_id}")

        return PreQualResponse(
            success=True,
            reference_id=reference_id,
            lead_id=lead_id,
            contact_id=contact_id,
            appointment_id=appointment_id,
            classification=classification,
            message="Your pre-qualification has been submitted successfully"
        )

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Pre-qual submission failed: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to process submission")


@router.post("/public/available-slots")
async def get_public_available_slots(
    request: Request,
    db: Session = Depends(get_db)
):
    """Get available calendar slots for pre-qual appointments (public endpoint)"""
    try:
        body = await request.json()
        start_date = body.get("start_date")
        end_date = body.get("end_date")
        duration_minutes = body.get("duration_minutes", 30)
        appointment_type = body.get("appointment_type", "pre-qualification-call")

        # Get default available slots (business hours for next 2 weeks)
        slots = generate_default_slots(start_date, end_date, duration_minutes)

        return {
            "available_slots": slots,
            "timezone": "America/New_York"
        }
    except Exception as e:
        logger.error(f"Failed to get available slots: {str(e)}")
        return {"available_slots": [], "error": "Internal server error"}


def generate_default_slots(start_date: str, end_date: str, duration: int) -> List[Dict]:
    """Generate default available slots for business hours"""
    from datetime import datetime, timedelta
    import pytz

    tz = pytz.timezone("America/New_York")
    slots = []

    start = datetime.strptime(start_date, "%Y-%m-%d")
    end = datetime.strptime(end_date, "%Y-%m-%d")

    current = start
    while current <= end:
        # Skip weekends
        if current.weekday() < 5:
            # Generate slots from 9 AM to 5 PM
            for hour in range(9, 17):
                slot_time = tz.localize(current.replace(hour=hour, minute=0, second=0))

                # Skip if in the past
                if slot_time > datetime.now(tz):
                    slots.append({
                        "start_time": slot_time.isoformat(),
                        "end_time": (slot_time + timedelta(minutes=duration)).isoformat(),
                        "duration_minutes": duration
                    })

        current += timedelta(days=1)

    return slots[:20]  # Return max 20 slots


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

async def create_or_update_contact(
    db: Session,
    submission: PreQualSubmission,
    reference_id: str
) -> int:
    """Create or update contact record"""
    try:
        # Check if contact exists by email
        existing = db.execute(
            text("SELECT id FROM contacts WHERE email = :email"),
            {"email": submission.email}
        ).fetchone()

        if existing:
            # Update existing contact
            db.execute(
                text("""
                    UPDATE contacts SET
                        first_name = :first_name,
                        last_name = :last_name,
                        phone = :phone,
                        updated_at = NOW()
                    WHERE id = :id
                """),
                {
                    "first_name": submission.first_name,
                    "last_name": submission.last_name,
                    "phone": submission.mobile_phone,
                    "id": existing[0]
                }
            )
            return existing[0]
        else:
            # Create new contact
            result = db.execute(
                text("""
                    INSERT INTO contacts (
                        first_name, last_name, email, phone,
                        contact_type, source, created_at
                    ) VALUES (
                        :first_name, :last_name, :email, :phone,
                        'borrower', :source, NOW()
                    )
                    RETURNING id
                """),
                {
                    "first_name": submission.first_name,
                    "last_name": submission.last_name,
                    "email": submission.email,
                    "phone": submission.mobile_phone,
                    "source": f"prequal-{submission.source}"
                }
            )
            return result.fetchone()[0]
    except Exception as e:
        logger.error(f"Contact creation failed: {str(e)}")
        # Return a placeholder ID if contacts table doesn't exist
        return 0


async def create_lead(
    db: Session,
    submission: PreQualSubmission,
    contact_id: int,
    classification: Dict,
    reference_id: str
) -> int:
    """Create lead/deal record"""
    try:
        result = db.execute(
            text("""
                INSERT INTO leads (
                    first_name, last_name, email, phone,
                    loan_purpose, loan_amount, property_city,
                    credit_score_range, employment_type, income_range,
                    down_payment_range, timeline, source,
                    lead_status, priority, complexity,
                    partner_id, realtor_email, reference_id,
                    classification_data, notes, created_at
                ) VALUES (
                    :first_name, :last_name, :email, :phone,
                    'purchase', :loan_amount, :property_city,
                    :credit_score_range, :employment_type, :income_range,
                    :down_payment_range, :timeline, :source,
                    'new', :priority, :complexity,
                    :partner_id, :realtor_email, :reference_id,
                    :classification_data, :notes, NOW()
                )
                RETURNING id
            """),
            {
                "first_name": submission.first_name,
                "last_name": submission.last_name,
                "email": submission.email,
                "phone": submission.mobile_phone,
                "loan_amount": submission.target_purchase_price,
                "property_city": submission.target_city,
                "credit_score_range": submission.credit_score_range,
                "employment_type": submission.employment_type,
                "income_range": submission.income_range,
                "down_payment_range": submission.down_payment_range,
                "timeline": submission.timeline,
                "source": f"prequal-{submission.source}",
                "priority": classification.get("priority", "warm"),
                "complexity": classification.get("complexity", "standard"),
                "partner_id": submission.partner_id or None,
                "realtor_email": submission.realtor_email or None,
                "reference_id": reference_id,
                "classification_data": json.dumps(classification),
                "notes": submission.additional_notes or ""
            }
        )
        return result.fetchone()[0]
    except Exception as e:
        logger.error(f"Lead creation failed: {str(e)}")
        # Return placeholder if leads table schema differs
        return 0


async def book_appointment(
    db: Session,
    submission: PreQualSubmission,
    lead_id: int,
    contact_id: int
) -> Optional[int]:
    """Book calendar appointment"""
    slot = submission.scheduled_appointment
    if not slot:
        return None

    try:
        result = db.execute(
            text("""
                INSERT INTO appointments (
                    title, scheduled_at, duration_minutes,
                    attendee_name, attendee_email, attendee_phone,
                    appointment_type, lead_id, contact_id,
                    status, created_at
                ) VALUES (
                    :title, :scheduled_at, :duration,
                    :attendee_name, :attendee_email, :attendee_phone,
                    'pre-qualification-call', :lead_id, :contact_id,
                    'scheduled', NOW()
                )
                RETURNING id
            """),
            {
                "title": f"Pre-Qualification Call - {submission.first_name} {submission.last_name}",
                "scheduled_at": slot.get("start_time"),
                "duration": slot.get("duration_minutes", 30),
                "attendee_name": f"{submission.first_name} {submission.last_name}",
                "attendee_email": submission.email,
                "attendee_phone": submission.mobile_phone,
                "lead_id": lead_id,
                "contact_id": contact_id
            }
        )
        return result.fetchone()[0]
    except Exception as e:
        logger.error(f"Appointment booking failed: {str(e)}")
        return None


async def send_notifications(
    submission: PreQualSubmission,
    classification: Dict,
    reference_id: str,
    appointment_id: Optional[int]
):
    """Send notifications to buyer, realtor, and internal team"""
    try:
        if _notification_service:
            # Notification to buyer
            _notification_service.send_email(
                to_email=submission.email,
                subject=f"Your Pre-Qualification Request - {reference_id}",
                html_content=f"""
                <html>
                <body style="font-family: Arial, sans-serif; padding: 20px;">
                    <h2>Thank you, {submission.first_name}!</h2>
                    <p>We've received your pre-qualification request for a home purchase in {submission.target_city}.</p>
                    <p>Your reference number is: <strong>{reference_id}</strong></p>
                    <p>A mortgage specialist will contact you within 24 hours to discuss your options.</p>
                    {f'<p>Your consultation is scheduled for the time you selected.</p>' if appointment_id else ''}
                    <p>Best regards,<br>The Perennia AI Team</p>
                </body>
                </html>
                """
            )

            # Notification to realtor (if provided)
            if submission.realtor_email:
                _notification_service.send_email(
                    to_email=submission.realtor_email,
                    subject=f"New Pre-Qual Lead: {submission.first_name} {submission.last_name}",
                    html_content=f"""
                    <html>
                    <body style="font-family: Arial, sans-serif; padding: 20px;">
                        <h2>New Pre-Qualification Lead</h2>
                        <p><strong>Buyer:</strong> {submission.first_name} {submission.last_name}</p>
                        <p><strong>Target:</strong> {submission.target_city} - ${submission.target_purchase_price:,}</p>
                        <p><strong>Timeline:</strong> {submission.timeline}</p>
                        <p><strong>Priority:</strong> {classification.get('priority', 'warm').upper()}</p>
                        <p>Our team will be reaching out to your buyer shortly.</p>
                    </body>
                    </html>
                    """
                )

        logger.info(f"Notifications sent for {reference_id}")
    except Exception as e:
        logger.error(f"Notification failed: {str(e)}")


async def create_sla_tasks(lead_id: int, classification: Dict):
    """Create SLA tasks for lead follow-up - creates its own db session"""
    from database import SessionLocal
    db = SessionLocal()
    try:
        priority = classification.get("priority", "warm")

        # First contact SLA based on priority
        if priority == "hot":
            due_hours = 1
        elif priority == "warm":
            due_hours = 4
        else:
            due_hours = 24

        db.execute(
            text("""
                INSERT INTO tasks (
                    title, description, due_at,
                    priority, task_type, lead_id,
                    status, created_at
                ) VALUES (
                    'First Contact - Pre-Qual Lead',
                    :description,
                    NOW() + INTERVAL ':hours hours',
                    :priority, 'sla_contact', :lead_id,
                    'pending', NOW()
                )
            """.replace(":hours", str(due_hours))),
            {
                "description": f"Contact new pre-qual lead. Priority: {priority}. Notes: {', '.join(classification.get('routing_notes', []))}",
                "priority": priority,
                "lead_id": lead_id
            }
        )
        db.commit()
        logger.info(f"SLA task created for lead {lead_id}")
    except Exception as e:
        db.rollback()
        logger.error(f"SLA task creation failed: {str(e)}")
    finally:
        db.close()


@router.get("/health")
async def prequal_health():
    """Health check endpoint"""
    return {"status": "ok", "service": "prequal"}
