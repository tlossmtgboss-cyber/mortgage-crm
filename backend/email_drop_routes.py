"""
Email Drop Routes
Backend API endpoints for drag-and-drop email processing
Handles email parsing, AI extraction, and CRM integration
"""

import os
import logging
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

# Initialize router
router = APIRouter(prefix="/api/v1/email-drop", tags=["email-drop"])

logger = logging.getLogger(__name__)

# =============================================================================
# Pydantic Schemas
# =============================================================================

class EmailData(BaseModel):
    """Email data from frontend drop zone"""
    filename: str
    from_address: str = Field(alias="from")
    to_address: Optional[str] = Field(None, alias="to")
    subject: str
    date: str
    body: str
    raw_content: Optional[str] = None
    matched_borrower: Optional[str] = None
    matched_loan_number: Optional[str] = None
    confidence: int = 50

    class Config:
        populate_by_name = True


class AIParseRequest(BaseModel):
    """Request for AI-powered email parsing"""
    email_data: EmailData
    parse_mode: str = "smart"  # "smart", "lead", "loan", "document"


class AIParseResponse(BaseModel):
    """Response from AI email parsing"""
    success: bool
    extracted_fields: Dict[str, Any]
    confidence_scores: Dict[str, int]
    suggested_action: str  # "create_lead", "update_lead", "create_loan", "update_loan", "archive"
    questions: List[Dict[str, Any]] = []  # Follow-up questions for user
    matched_entities: Dict[str, Any] = {}
    ai_summary: str = ""


class ProcessEmailRequest(BaseModel):
    """Request to process and save email data"""
    action: str  # "lead", "loan", "archive"
    email_data: EmailData
    extracted_fields: Dict[str, Any] = {}
    target_entity_id: Optional[str] = None  # ID of existing lead/loan to update
    target_entity_type: Optional[str] = None  # "lead" or "loan"
    create_new: bool = False
    user_answers: Dict[str, Any] = {}  # Answers to follow-up questions


class ProcessEmailResponse(BaseModel):
    """Response from email processing"""
    success: bool
    action_taken: str
    entity_id: Optional[str] = None
    entity_type: Optional[str] = None
    message: str
    conflicts: List[Dict[str, Any]] = []


class SearchMatchRequest(BaseModel):
    """Request to search for matching entities"""
    search_term: str
    email: Optional[str] = None
    loan_number: Optional[str] = None


class SearchMatchResponse(BaseModel):
    """Response with matching entities"""
    leads: List[Dict[str, Any]]
    loans: List[Dict[str, Any]]
    best_match: Optional[Dict[str, Any]] = None


# =============================================================================
# Dependency Injection Setup
# =============================================================================

# Import database from main module
def get_db():
    """Get database session - imported from main"""
    from database import SessionLocal
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# =============================================================================
# AI Email Parsing
# =============================================================================

async def parse_email_with_ai(email_data: EmailData, db: Session) -> Dict[str, Any]:
    """
    Use Claude AI to intelligently parse email content
    Extracts borrower info, loan details, and suggests actions
    """
    try:
        import anthropic

        client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

        # Build the parsing prompt
        prompt = f"""You are an AI assistant for a mortgage CRM. Parse this email and extract relevant information.

EMAIL DETAILS:
From: {email_data.from_address}
Subject: {email_data.subject}
Date: {email_data.date}
Body:
{email_data.body[:3000]}

TASK:
1. Determine if this email relates to a LEAD (prospective borrower) or an active LOAN
2. Extract all relevant fields you can find
3. Assess confidence level for each extracted field (0-100)
4. Suggest the best action: create_lead, update_lead, create_loan, update_loan, or archive
5. Generate follow-up questions if important information is ambiguous or missing

RESPOND IN THIS EXACT JSON FORMAT:
{{
    "profile_type": "lead" or "loan",
    "suggested_action": "create_lead|update_lead|create_loan|update_loan|archive",
    "extracted_fields": {{
        "first_name": "value or null",
        "last_name": "value or null",
        "email": "value or null",
        "phone": "value or null",
        "loan_number": "value or null",
        "loan_amount": "value or null",
        "property_address": "value or null",
        "loan_type": "value or null",
        "interest_rate": "value or null",
        "closing_date": "value or null",
        "credit_score": "value or null",
        "employer": "value or null",
        "annual_income": "value or null"
    }},
    "confidence_scores": {{
        "first_name": 0-100,
        "last_name": 0-100,
        ...
    }},
    "questions": [
        {{
            "field": "field_name",
            "question": "What is the borrower's phone number?",
            "options": ["Option 1", "Option 2"] // optional
        }}
    ],
    "summary": "Brief summary of what this email is about",
    "urgency": "low|medium|high"
}}"""

        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=2000,
            messages=[{"role": "user", "content": prompt}]
        )

        # Parse the response
        import json
        response_text = response.content[0].text

        # Extract JSON from response
        json_start = response_text.find('{')
        json_end = response_text.rfind('}') + 1
        if json_start >= 0 and json_end > json_start:
            parsed = json.loads(response_text[json_start:json_end])
            return {
                "success": True,
                **parsed
            }
        else:
            logger.error("No valid JSON in AI response")
            return {"success": False, "error": "Failed to parse AI response"}

    except Exception as e:
        logger.error(f"AI parsing error: {e}")
        # Fallback to basic parsing
        return {
            "success": True,
            "profile_type": "lead",
            "suggested_action": "create_lead",
            "extracted_fields": {
                "email": extract_email_from_string(email_data.from_address),
                "first_name": email_data.matched_borrower.split()[0] if email_data.matched_borrower else None,
                "last_name": email_data.matched_borrower.split()[-1] if email_data.matched_borrower and ' ' in email_data.matched_borrower else None,
                "loan_number": email_data.matched_loan_number
            },
            "confidence_scores": {
                "email": 90,
                "first_name": 60 if email_data.matched_borrower else 0,
                "last_name": 60 if email_data.matched_borrower else 0,
                "loan_number": 80 if email_data.matched_loan_number else 0
            },
            "questions": [],
            "summary": f"Email from {email_data.from_address} about: {email_data.subject}",
            "urgency": "medium"
        }


def extract_email_from_string(from_field: str) -> Optional[str]:
    """Extract email address from 'Name <email>' format"""
    import re
    match = re.search(r'[\w\.-]+@[\w\.-]+\.\w+', from_field)
    return match.group(0) if match else from_field


# =============================================================================
# API Endpoints
# =============================================================================

@router.post("/parse", response_model=AIParseResponse)
async def parse_email(
    request: AIParseRequest,
    db: Session = Depends(get_db)
):
    """
    Parse a dropped email with AI and return extracted fields + suggestions
    This is the first step - frontend calls this to get AI analysis
    """
    try:
        email_data = request.email_data

        # Call AI parsing
        ai_result = await parse_email_with_ai(email_data, db)

        if not ai_result.get("success"):
            raise HTTPException(status_code=500, detail="AI parsing failed")

        # Search for matching entities in database
        matched_entities = await search_for_matches(
            email_data=email_data,
            extracted_fields=ai_result.get("extracted_fields", {}),
            db=db
        )

        return AIParseResponse(
            success=True,
            extracted_fields=ai_result.get("extracted_fields", {}),
            confidence_scores=ai_result.get("confidence_scores", {}),
            suggested_action=ai_result.get("suggested_action", "create_lead"),
            questions=ai_result.get("questions", []),
            matched_entities=matched_entities,
            ai_summary=ai_result.get("summary", "")
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Email parse error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/process", response_model=ProcessEmailResponse)
async def process_email(
    request: ProcessEmailRequest,
    db: Session = Depends(get_db)
):
    """
    Process the email based on user's chosen action
    Creates/updates lead, loan, or archives the email
    """
    try:
        action = request.action
        email_data = request.email_data
        extracted = request.extracted_fields

        # Import models here to avoid circular imports
        from database.enums import DocumentType, DocumentCategory
        from database.models import Lead, Loan, Document

        result = {
            "success": False,
            "action_taken": action,
            "entity_id": None,
            "entity_type": None,
            "message": "",
            "conflicts": []
        }

        if action == "lead":
            result = await process_as_lead(
                email_data=email_data,
                extracted_fields=extracted,
                target_id=request.target_entity_id,
                create_new=request.create_new,
                user_answers=request.user_answers,
                db=db
            )

        elif action == "loan":
            result = await process_as_loan(
                email_data=email_data,
                extracted_fields=extracted,
                target_id=request.target_entity_id,
                create_new=request.create_new,
                user_answers=request.user_answers,
                db=db
            )

        elif action == "archive":
            result = await archive_email(
                email_data=email_data,
                target_id=request.target_entity_id,
                target_type=request.target_entity_type,
                db=db
            )
        else:
            raise HTTPException(status_code=400, detail=f"Invalid action: {action}")

        return ProcessEmailResponse(**result)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Email process error: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/search-matches", response_model=SearchMatchResponse)
async def search_matches(
    request: SearchMatchRequest,
    db: Session = Depends(get_db)
):
    """
    Search for matching leads and loans based on email/name/loan number
    """
    try:
        from database.models import Lead, Loan

        leads = []
        loans = []

        # Search leads
        lead_query = db.query(Lead)
        if request.email:
            lead_query = lead_query.filter(Lead.email.ilike(f"%{request.email}%"))
        elif request.search_term:
            lead_query = lead_query.filter(
                (Lead.name.ilike(f"%{request.search_term}%")) |
                (Lead.email.ilike(f"%{request.search_term}%"))
            )

        for lead in lead_query.limit(10).all():
            leads.append({
                "id": lead.id,
                "type": "lead",
                "name": lead.name,
                "email": lead.email,
                "phone": lead.phone,
                "stage": str(lead.stage.value) if lead.stage else None,
                "display_name": lead.name or lead.email
            })

        # Search loans
        loan_query = db.query(Loan)
        if request.loan_number:
            loan_query = loan_query.filter(Loan.loan_number.ilike(f"%{request.loan_number}%"))
        elif request.search_term:
            loan_query = loan_query.filter(
                (Loan.borrower_name.ilike(f"%{request.search_term}%")) |
                (Loan.loan_number.ilike(f"%{request.search_term}%"))
            )

        for loan in loan_query.limit(10).all():
            loans.append({
                "id": loan.id,
                "type": "loan",
                "loan_number": loan.loan_number,
                "borrower_name": loan.borrower_name,
                "stage": str(loan.stage) if loan.stage else None,
                "property_address": loan.property_address,
                "display_name": f"{loan.borrower_name} - {loan.loan_number}"
            })

        # Determine best match
        best_match = None
        if leads:
            best_match = {"type": "lead", "data": leads[0]}
        elif loans:
            best_match = {"type": "loan", "data": loans[0]}

        return SearchMatchResponse(
            leads=leads,
            loans=loans,
            best_match=best_match
        )

    except Exception as e:
        logger.error(f"Search matches error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


# =============================================================================
# Processing Functions
# =============================================================================

async def search_for_matches(
    email_data: EmailData,
    extracted_fields: Dict[str, Any],
    db: Session
) -> Dict[str, Any]:
    """Search database for matching entities based on extracted data"""
    from database.models import Lead, Loan

    matches = {
        "leads": [],
        "loans": [],
        "best_match": None,
        "match_confidence": 0
    }

    # Extract email from 'From' field
    email = extract_email_from_string(email_data.from_address)

    # Search by email
    if email:
        lead = db.query(Lead).filter(Lead.email == email).first()
        if lead:
            matches["leads"].append({
                "id": lead.id,
                "name": lead.name,
                "email": lead.email,
                "match_reason": "email_exact"
            })
            matches["best_match"] = {"type": "lead", "id": lead.id, "reason": "email"}
            matches["match_confidence"] = 95

    # Search by loan number
    loan_number = extracted_fields.get("loan_number") or email_data.matched_loan_number
    if loan_number:
        loan = db.query(Loan).filter(Loan.loan_number == loan_number).first()
        if loan:
            matches["loans"].append({
                "id": loan.id,
                "loan_number": loan.loan_number,
                "borrower_name": loan.borrower_name,
                "match_reason": "loan_number_exact"
            })
            if not matches["best_match"]:
                matches["best_match"] = {"type": "loan", "id": loan.id, "reason": "loan_number"}
                matches["match_confidence"] = 100

    # Search by name (combine first_name + last_name from extracted fields)
    first_name = extracted_fields.get("first_name")
    last_name = extracted_fields.get("last_name")
    full_name = f"{first_name} {last_name}".strip() if first_name or last_name else None

    if full_name:
        lead = db.query(Lead).filter(
            Lead.name.ilike(f"%{full_name}%")
        ).first()
        if lead and lead.id not in [m["id"] for m in matches["leads"]]:
            matches["leads"].append({
                "id": lead.id,
                "name": lead.name,
                "email": lead.email,
                "match_reason": "name_match"
            })
            if not matches["best_match"]:
                matches["best_match"] = {"type": "lead", "id": lead.id, "reason": "name"}
                matches["match_confidence"] = 75

    return matches


async def process_as_lead(
    email_data: EmailData,
    extracted_fields: Dict[str, Any],
    target_id: Optional[str],
    create_new: bool,
    user_answers: Dict[str, Any],
    db: Session
) -> Dict[str, Any]:
    """Create or update a lead from email data"""
    from database.models import Lead

    # Merge user answers with extracted fields
    fields = {**extracted_fields, **user_answers}

    # Get email from from_address
    email = extract_email_from_string(email_data.from_address)
    if not fields.get("email"):
        fields["email"] = email

    if target_id and not create_new:
        # Update existing lead
        lead = db.query(Lead).filter(Lead.id == int(target_id)).first()
        if not lead:
            return {
                "success": False,
                "action_taken": "update_lead",
                "message": f"Lead {target_id} not found"
            }

        # Update fields (only non-null values)
        conflicts = []
        _protected = {'id', 'organization_id', 'created_at', 'updated_at', 'owner_id'}
        for field, value in fields.items():
            if value is not None and hasattr(lead, field) and field not in _protected:
                current = getattr(lead, field)
                if current and current != value:
                    conflicts.append({
                        "field": field,
                        "current": current,
                        "proposed": value
                    })
                else:
                    setattr(lead, field, value)

        # Add note about email source
        note = f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M')}] Updated from email: {email_data.subject}"
        lead.notes = (lead.notes or "") + note

        db.commit()

        return {
            "success": True,
            "action_taken": "update_lead",
            "entity_id": str(lead.id),
            "entity_type": "lead",
            "message": f"Updated lead: {lead.name}",
            "conflicts": conflicts
        }
    else:
        # Create new lead
        # Check if email already exists
        existing = db.query(Lead).filter(Lead.email == fields.get("email")).first()
        if existing:
            return {
                "success": False,
                "action_taken": "create_lead",
                "entity_id": str(existing.id),
                "entity_type": "lead",
                "message": f"Lead with email {fields.get('email')} already exists"
            }

        # Build name from first_name + last_name
        name = f"{fields.get('first_name', '')} {fields.get('last_name', '')}".strip()
        if not name:
            name = email_data.matched_borrower or "Unknown"

        lead = Lead(
            name=name,
            email=fields.get("email"),
            phone=fields.get("phone"),
            source="email_drop",
            notes=f"Created from email drop: {email_data.subject}\nFrom: {email_data.from_address}"
        )

        # Set additional fields if provided
        _protected = {'id', 'organization_id', 'created_at', 'updated_at', 'owner_id'}
        for field in ["employer_name", "annual_income", "loan_amount", "property_address",
                     "loan_type", "credit_score"]:
            if fields.get(field):
                if hasattr(lead, field) and field not in _protected:
                    setattr(lead, field, fields[field])

        db.add(lead)
        db.commit()
        db.refresh(lead)

        return {
            "success": True,
            "action_taken": "create_lead",
            "entity_id": str(lead.id),
            "entity_type": "lead",
            "message": f"Created new lead: {lead.name}",
            "conflicts": []
        }


async def process_as_loan(
    email_data: EmailData,
    extracted_fields: Dict[str, Any],
    target_id: Optional[str],
    create_new: bool,
    user_answers: Dict[str, Any],
    db: Session
) -> Dict[str, Any]:
    """Create or update a loan from email data"""
    from database.models import Loan

    # Merge user answers with extracted fields
    fields = {**extracted_fields, **user_answers}

    if target_id and not create_new:
        # Update existing loan
        loan = db.query(Loan).filter(Loan.id == int(target_id)).first()
        if not loan:
            return {
                "success": False,
                "action_taken": "update_loan",
                "message": f"Loan {target_id} not found"
            }

        # Update fields
        conflicts = []
        _protected = {'id', 'organization_id', 'created_at', 'updated_at', 'loan_officer_id'}
        for field, value in fields.items():
            if value is not None and hasattr(loan, field) and field not in _protected:
                current = getattr(loan, field)
                if current and str(current) != str(value):
                    conflicts.append({
                        "field": field,
                        "current": str(current),
                        "proposed": str(value)
                    })
                else:
                    setattr(loan, field, value)

        # Add note
        note = f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M')}] Updated from email: {email_data.subject}"
        loan.notes = (loan.notes or "") + note

        db.commit()

        return {
            "success": True,
            "action_taken": "update_loan",
            "entity_id": str(loan.id),
            "entity_type": "loan",
            "message": f"Updated loan: {loan.loan_number}",
            "conflicts": conflicts
        }
    else:
        # Create new loan
        borrower_name = f"{fields.get('first_name', '')} {fields.get('last_name', '')}".strip()
        if not borrower_name:
            borrower_name = email_data.matched_borrower or "Unknown Borrower"

        # Generate loan number if not provided
        loan_number = fields.get("loan_number") or email_data.matched_loan_number
        if not loan_number:
            loan_number = f"DROP-{datetime.now().strftime('%Y%m%d%H%M%S')}"

        # Check if loan number exists
        existing = db.query(Loan).filter(Loan.loan_number == loan_number).first()
        if existing:
            return {
                "success": False,
                "action_taken": "create_loan",
                "entity_id": str(existing.id),
                "entity_type": "loan",
                "message": f"Loan {loan_number} already exists"
            }

        loan = Loan(
            loan_number=loan_number,
            borrower_name=borrower_name,
            borrower_email=extract_email_from_string(email_data.from_address),
            stage="Application",
            notes=f"Created from email drop: {email_data.subject}\nFrom: {email_data.from_address}"
        )

        # Set additional fields
        if fields.get("loan_amount"):
            loan.loan_amount = float(fields["loan_amount"])
        if fields.get("property_address"):
            loan.property_address = fields["property_address"]
        if fields.get("interest_rate"):
            loan.interest_rate = float(fields["interest_rate"])
        if fields.get("loan_type"):
            loan.loan_type = fields["loan_type"]

        db.add(loan)
        db.commit()
        db.refresh(loan)

        return {
            "success": True,
            "action_taken": "create_loan",
            "entity_id": str(loan.id),
            "entity_type": "loan",
            "message": f"Created new loan: {loan.loan_number}",
            "conflicts": []
        }


async def archive_email(
    email_data: EmailData,
    target_id: Optional[str],
    target_type: Optional[str],
    db: Session
) -> Dict[str, Any]:
    """Archive email as a document attached to a borrower/loan"""
    from database.enums import DocumentType, DocumentCategory
    from database.models import Document

    # Create document record
    doc = Document(
        doc_type=DocumentType.OTHER,
        doc_category=DocumentCategory.CORRESPONDENCE,
        filename=email_data.filename or f"email_{datetime.now().strftime('%Y%m%d_%H%M%S')}.eml",
        original_filename=email_data.filename,
        source="EMAIL_DROP",
        status="active",
        notes=f"Subject: {email_data.subject}\nFrom: {email_data.from_address}\nDate: {email_data.date}\n\n{email_data.body[:500]}..."
    )

    # Attach to borrower or loan
    if target_id and target_type == "lead":
        doc.borrower_id = int(target_id)
    elif target_id and target_type == "loan":
        doc.loan_id = int(target_id)

    # For now, store the email content in notes since we don't have file storage
    # In production, you'd upload to S3/GCS and store the URL
    doc.file_location = f"email_archive/{datetime.now().strftime('%Y/%m/%d')}/{doc.filename}"

    db.add(doc)
    db.commit()
    db.refresh(doc)

    return {
        "success": True,
        "action_taken": "archive",
        "entity_id": str(doc.id),
        "entity_type": "document",
        "message": f"Email archived as document #{doc.id}",
        "conflicts": []
    }


# =============================================================================
# Health Check
# =============================================================================

@router.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "email-drop",
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
