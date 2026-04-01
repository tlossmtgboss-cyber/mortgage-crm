"""
Data Reconciliation Engine (DRE) Helper Functions

Extracted from inline_legacy_routes.py.
Contains: AI email classification, loan field extraction, entity matching,
data application, Microsoft OAuth/email sync, Calendly integration,
and milestone task creation.

Usage:
    Call init_dre_helpers(openai_client, SECRET_KEY) at startup.
    Functions are then importable from this module.
"""
import os
import re
import json
import base64
import logging
import secrets
import requests
from datetime import datetime, date, timedelta, timezone
from typing import Dict, Any, Optional, List

from sqlalchemy.orm import Session
from sqlalchemy import func, text

logger = logging.getLogger(__name__)

# Module-level references set by init_dre_helpers()
_openai_client = None
_SECRET_KEY = ""

# Lazy model imports (resolved on first use to avoid circular imports)
_models_loaded = False


def _ensure_models():
    """Lazy-import all needed models/enums to avoid circular imports at module load."""
    global _models_loaded
    if _models_loaded:
        return
    # These will be importable after main.py has set up everything
    global Loan, Lead, MUMClient, ReferralPartner, ExtractedData, Task
    global MicrosoftOAuthToken, IncomingDataEvent, IntegrationCredential
    global LoanStage, LeadStage
    from database.models import (
        Loan, Lead, MUMClient, ReferralPartner, ExtractedData, Task,
        MicrosoftOAuthToken, IncomingDataEvent, IntegrationCredential,
    )
    from database.enums import LoanStage, LeadStage
    _models_loaded = True


def init_dre_helpers(openai_client=None, secret_key: str = ""):
    """Initialize module-level dependencies. Call once at startup."""
    global _openai_client, _SECRET_KEY
    _openai_client = openai_client
    _SECRET_KEY = secret_key


# ============================================================================
# API KEY HELPER
# ============================================================================

def generate_api_key() -> str:
    """Generate a secure API key with prefix 'sk_'"""
    random_part = secrets.token_urlsafe(32)
    return f"sk_{random_part}"


# ============================================================================
# AI HELPER FUNCTIONS
# ============================================================================

def generate_ai_insights(loan) -> str:
    """Generate AI insights for a loan (simple rule-based for now)"""
    insights = []

    if loan.days_in_stage and loan.days_in_stage > 10:
        stage_name = loan.stage.value if hasattr(loan.stage, 'value') else str(loan.stage) if loan.stage else 'unknown'
        insights.append(f"⚠️ Loan has been in {stage_name} stage for {loan.days_in_stage} days")

    if loan.closing_date:
        try:
            # Handle both date and datetime objects
            if hasattr(loan.closing_date, 'tzinfo'):
                closing_dt = loan.closing_date if loan.closing_date.tzinfo else loan.closing_date.replace(tzinfo=timezone.utc)
            else:
                # It's a date object, convert to datetime
                closing_dt = datetime.combine(loan.closing_date, datetime.min.time()).replace(tzinfo=timezone.utc)
            if (closing_dt - datetime.now(timezone.utc)).days < 7:
                insights.append("🔥 Closing date approaching - prioritize tasks")
        except Exception as e:
            logger.exception(f"Failed to calculate closing date insight: {e}")

    if loan.rate and loan.rate > 7.0:
        insights.append("💰 Higher rate loan - consider rate lock strategies")

    if not insights:
        insights.append("✅ Loan progressing normally")

    return " | ".join(insights)


def calculate_lead_score(lead) -> int:
    """Calculate AI score for a lead"""
    score = 50

    if lead.credit_score:
        if lead.credit_score >= 740:
            score += 30
        elif lead.credit_score >= 680:
            score += 20
        elif lead.credit_score >= 620:
            score += 10
        else:
            score -= 10

    if lead.preapproval_amount and lead.preapproval_amount > 0:
        score += 15

    if lead.email:
        score += 5

    if lead.phone:
        score += 5

    if lead.debt_to_income:
        if lead.debt_to_income < 0.36:
            score += 10
        elif lead.debt_to_income > 0.50:
            score -= 15

    return min(max(score, 0), 100)


# ============================================================================
# DATA RECONCILIATION ENGINE (DRE) - AI EXTRACTION
# ============================================================================

def classify_email_content(content: str, subject: str) -> Dict[str, Any]:
    """Use AI to classify email content and determine category"""

    if not _openai_client:
        logger.warning("OpenAI client not initialized - using fallback classification")
        # Fallback: Use keyword matching to classify
        content_lower = content.lower()
        subject_lower = subject.lower()

        if any(word in subject_lower or word in content_lower for word in ['loan', 'mortgage', 'borrower', 'closing', 'rate lock']):
            return {"category": "loan_update", "subcategory": "general", "confidence": 0.5}
        else:
            return {"category": "loan_update", "subcategory": "general", "confidence": 0.3}

    try:
        response = _openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": """You are an email classification expert for mortgage loan processing.

    FIRST: Determine if this email is related to the mortgage/lending business.
    If the email is about ANY of these, classify as "unrelated":
    - Software updates, tech newsletters, product announcements
    - Marketing/promotional emails not about mortgage services
    - Personal emails, social media notifications
    - General news, politics, entertainment
    - Subscriptions, newsletters unrelated to mortgage industry
    - Internal company announcements not about loans

    ONLY classify as mortgage-related if the email contains:
    - Loan numbers, borrower names, property addresses
    - Loan status updates, milestone changes
    - Rate locks, appraisals, title, insurance
    - Closing documents, CDs, funding
    - Lead inquiries about getting a mortgage

    Categories (ONLY use if mortgage-related):
    - lead_update: New lead information or lead status changes
    - loan_update: Active loan milestone updates
    - rate_lock: Rate lock confirmations or expirations
    - appraisal: Appraisal scheduling or results
    - title: Title work, clear to close
    - insurance: HOI binders, insurance updates
    - closing: Closing date/time, CD delivery
    - document: Document receipt confirmations
    - portfolio: Servicing, escrow, tax updates
    - unrelated: NOT mortgage-related (use this liberally for anything that's not clearly about a mortgage transaction)

    Return JSON: {"category": "...", "subcategory": "...", "confidence": 0.0-1.0}"""
                },
                {
                    "role": "user",
                    "content": f"<email_subject>{subject}</email_subject>\n\n<email_content>{content[:1000]}</email_content>"
                }
            ],
            response_format={"type": "json_object"},
            temperature=0.3
        )

        result = json.loads(response.choices[0].message.content)
        return result
    except Exception as e:
        logger.error(f"Email classification error: {e}")
        # Return loan_update with low confidence so email still gets processed
        return {"category": "loan_update", "subcategory": "error", "confidence": 0.3}


def extract_loan_fields(content: str, category: str) -> Dict[str, Dict[str, Any]]:
    """Extract structured loan fields from email content"""

    if not _openai_client:
        logger.warning("OpenAI client not initialized - cannot extract loan fields, returning empty")
        return {}

    try:
        response = _openai_client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "system",
                    "content": f"""Extract mortgage loan fields from this {category} email.

    **CRITICAL - BORROWER NAME EXTRACTION:**
    You MUST extract the borrower name. Look for these patterns:
    1. "Borrower:  LastName" or "Borrower: FirstName LastName"
    2. "Borrower(s): Name1 and Name2"
    3. Subject line patterns like "Loan # XXX - LastName -" or "[LastName-LoanNumber]"
    4. Email signatures or references to "the borrower"
    If you see text like "Borrower:  Spink" - extract "Spink" as borrower_name!

    Extract any present fields:
    - loan_number: string (look for patterns like RCA#, Loan #, file #)
    - borrower_name: string (**REQUIRED** - extract from Borrower: field, subject line, or any reference)
    - coborrower_name: string (if present)
    - property_address: string
    - property_city: string
    - property_state: string
    - property_zip: string
    - loan_amount: float
    - program: string (e.g., "FHA 30 Yr Fixed", "VA 30 Yr Fixed", "Conv 30 Yr Fixed")
    - term: integer (loan term in years, e.g., 30)
    - rate: float (as decimal, e.g., 6.125)
    - rate_lock_date: ISO date
    - lock_expiration: ISO date
    - appraisal_ordered_date: ISO date
    - appraisal_scheduled_date: ISO date
    - appraisal_completed_date: ISO date
    - appraisal_value: float
    - closing_scheduled_date: ISO date
    - closing_date: ISO datetime
    - milestone: string (e.g., "RateLocked", "AppraisalOrdered", "ClearToClose", "InspectionCompleted")
    - documents_received: list of strings
    - lender: string
    - loan_officer_name: string
    - loan_officer_email: string
    - realtor_name: string
    - title_company: string

    For each field found, return:
    {{"field_name": {{"value": actual_value, "confidence": 0.0-1.0}}}}

    Return JSON object. Only include fields you found. Use null for missing."""
                },
                {
                    "role": "user",
                    "content": content[:3000]  # Increased to capture more content
                }
            ],
            response_format={"type": "json_object"},
            temperature=0.2
        )

        fields = json.loads(response.choices[0].message.content)
        logger.info(f"Extracted fields: {list(fields.keys())}")
        return fields
    except Exception as e:
        logger.error(f"Field extraction error: {e}")
        return {}


def extract_borrower_from_subject(subject: str) -> Optional[str]:
    """Extract borrower name from email subject line as fallback"""
    if not subject:
        return None

    # Pattern 1: "FirstName LastName RCA0000006026" - Full name before loan number
    match = re.search(r'^([A-Za-z]+(?:\s+[A-Za-z]+)+)\s+[A-Z]{2,3}\d{7,}', subject)
    if match:
        return match.group(1).strip()

    # Pattern 2: "Closing Docs Downloaded, FirstName LastName, RCA..."
    match = re.search(r',\s*([A-Za-z]+(?:\s+[A-Za-z]+)+)\s*,\s*[A-Z]{2,3}\d+', subject)
    if match:
        return match.group(1).strip()

    # Pattern 3: "LastName - RCA0000011023" format
    match = re.search(r'([A-Za-z]+)\s*-\s*[A-Z]{2,3}\d{7,}', subject)
    if match:
        return match.group(1).strip()

    # Pattern 4: "Loan # XXX - LastName -" or "Loan # XXX - LastName - Status"
    match = re.search(r'Loan\s*#?\s*\w+\s*-\s*([A-Za-z]+)\s*-', subject, re.IGNORECASE)
    if match:
        return match.group(1).strip()

    # Pattern 5: "[LastName-LoanNumber]" like "[Spink-RCA0000006026]"
    match = re.search(r'\[([A-Za-z]+)-\w+\]', subject)
    if match:
        return match.group(1).strip()

    # Pattern 6: "Disclosures for FirstName LastName, RCA..."
    match = re.search(r'Disclosures for\s+([A-Za-z]+(?:\s+[A-Za-z]+)+)\s*,', subject, re.IGNORECASE)
    if match:
        return match.group(1).strip()

    # Pattern 7: "for FirstName LastName were" - generic
    match = re.search(r'for\s+([A-Za-z]+(?:\s+[A-Za-z]+)+)\s+were', subject, re.IGNORECASE)
    if match:
        return match.group(1).strip()

    return None


def match_entity(fields: Dict[str, Any], db: Session, user_id: int, organization_id: int = None) -> Dict[str, Any]:
    """Match extracted fields to existing CRM entities

    Enhanced matching includes:
    - Loan number exact and partial matching
    - Borrower name matching (primary and co-borrower)
    - Last name matching for spouse/family identification
    - Email and phone matching for leads
    - Combined first_name + last_name support

    Args:
        organization_id: Tenant filter. When provided, lead queries are scoped
                         to this organization to prevent cross-tenant data leakage.
    """
    _ensure_models()

    match_results = {
        "entity_type": None,
        "entity_id": None,
        "confidence": 0.0,
        "candidates": []
    }

    def get_last_name(full_name: str) -> str:
        """Extract last name from full name"""
        if not full_name:
            return ""
        parts = full_name.strip().split()
        return parts[-1].lower() if parts else ""

    def names_match(name1: str, name2: str) -> tuple:
        """Check if names match - returns (is_match, confidence)"""
        if not name1 or not name2:
            return False, 0.0
        n1 = name1.lower().strip()
        n2 = name2.lower().strip()

        # Exact match
        if n1 == n2:
            return True, 0.95

        # One contains the other (partial name match)
        if n1 in n2 or n2 in n1:
            return True, 0.80

        def normalize_name(name: str) -> set:
            """Extract name parts, handling 'Last, First' and 'First Last' formats"""
            name = name.lower().strip()
            if ',' in name:
                parts = [p.strip() for p in name.split(',')]
                parts = list(reversed(parts))
            else:
                parts = name.split()
            return set(p for p in parts if len(p) > 1)

        parts1 = normalize_name(n1)
        parts2 = normalize_name(n2)

        common_parts = parts1 & parts2
        if len(common_parts) >= 2:
            return True, 0.90

        if len(common_parts) == 1:
            ln1 = get_last_name(name1)
            ln2 = get_last_name(name2)
            if ln1 and ln2 and ln1 == ln2:
                return True, 0.75

        ln1, ln2 = get_last_name(name1), get_last_name(name2)
        if ln1 and ln2 and ln1 == ln2:
            return True, 0.75

        return False, 0.0

    def normalize_phone(phone: str) -> str:
        """Normalize phone number for comparison"""
        if not phone:
            return ""
        return ''.join(c for c in phone if c.isdigit())[-10:]

    def normalize_email(email: str) -> str:
        """Normalize email for comparison"""
        if not email:
            return ""
        return email.lower().strip()

    # Build combined borrower name from first_name + last_name if not already present
    borrower_name = None
    if "borrower_name" in fields and fields["borrower_name"].get("value"):
        borrower_name = fields["borrower_name"]["value"]
    elif "first_name" in fields or "last_name" in fields:
        first = fields.get("first_name", {}).get("value", "") or ""
        last = fields.get("last_name", {}).get("value", "") or ""
        if first or last:
            borrower_name = f"{first} {last}".strip()
            logger.info(f"Built borrower_name from first_name + last_name: '{borrower_name}'")

    # Extract email and phone from fields
    extracted_email = None
    extracted_phone = None
    if "borrower_email" in fields and fields["borrower_email"].get("value"):
        extracted_email = normalize_email(fields["borrower_email"]["value"])
    if "borrower_phone" in fields and fields["borrower_phone"].get("value"):
        extracted_phone = normalize_phone(fields["borrower_phone"]["value"])

    logger.info(f"=" * 60)
    logger.info(f"MATCH_ENTITY DEBUG - Starting match process")
    logger.info(f"=" * 60)
    logger.info(f"Input fields: {list(fields.keys()) if fields else 'None'}")
    logger.info(f"Extracted borrower_name: '{borrower_name}'")
    logger.info(f"Extracted email: '{extracted_email}'")
    logger.info(f"Extracted phone: '{extracted_phone}'")

    # Collect all potential loan numbers from various fields
    loan_numbers_to_try = []
    if "loan_number" in fields and fields["loan_number"].get("value"):
        loan_numbers_to_try.append(str(fields["loan_number"]["value"]).strip())
    if "file_number" in fields and fields["file_number"].get("value"):
        loan_numbers_to_try.append(str(fields["file_number"]["value"]).strip())
    if "cmg_file_number" in fields and fields["cmg_file_number"].get("value"):
        loan_numbers_to_try.append(str(fields["cmg_file_number"]["value"]).strip())
    if "lender_loan_number" in fields and fields["lender_loan_number"].get("value"):
        loan_numbers_to_try.append(str(fields["lender_loan_number"]["value"]).strip())
    if "investor_loan_number" in fields and fields["investor_loan_number"].get("value"):
        loan_numbers_to_try.append(str(fields["investor_loan_number"]["value"]).strip())

    # Remove duplicates while preserving order
    loan_numbers_to_try = list(dict.fromkeys(loan_numbers_to_try))
    logger.info(f"Loan numbers to try: {loan_numbers_to_try}")
    logger.info(f"Total loan numbers to match: {len(loan_numbers_to_try)}")

    # Try to match by loan number first (highest confidence)
    for loan_num in loan_numbers_to_try:
        loan_num_upper = loan_num.upper()
        logger.info(f"Attempting to match loan number: '{loan_num}'")

        def get_loan_entity_type(loan_obj):
            """Return 'portfolio' for funded loans, 'loan' for active loans"""
            if loan_obj and loan_obj.stage == LoanStage.FUNDED:
                return "portfolio"
            return "loan"

        # ========== CHECK MUM CLIENTS FIRST (Portfolio) ==========
        logger.info(f"[MUM] Searching MUM clients for loan_number='{loan_num}'")
        try:
            total_mum = db.query(MUMClient).count()
            logger.info(f"[MUM] Total MUM clients in database: {total_mum}")

            mum_client = db.query(MUMClient).filter(
                func.upper(MUMClient.loan_number) == loan_num_upper
            ).first()

            if mum_client:
                logger.info(f"[MUM] ✓ EXACT MATCH: {mum_client.name} (id={mum_client.id}, loan#={mum_client.loan_number})")
                match_results["candidates"].append({
                    "type": "portfolio",
                    "id": mum_client.id,
                    "name": mum_client.name,
                    "loan_number": mum_client.loan_number,
                    "confidence": 0.98,
                    "match_type": "mum_loan_number_exact"
                })
            else:
                logger.info(f"[MUM] No exact match for loan_number='{loan_num}'")
                mum_clients = db.query(MUMClient).filter(
                    MUMClient.loan_number.ilike(f"%{loan_num}%")
                ).all()
                logger.info(f"[MUM] Partial match search found {len(mum_clients)} clients")
                for client in mum_clients:
                    logger.info(f"[MUM] ✓ PARTIAL MATCH: {client.name} (loan#={client.loan_number})")
                    match_results["candidates"].append({
                        "type": "portfolio",
                        "id": client.id,
                        "name": client.name,
                        "loan_number": client.loan_number,
                        "confidence": 0.92,
                        "match_type": "mum_loan_number_partial"
                    })
        except Exception as e:
            logger.warning(f"MUM client loan number matching error: {e}")

        # ========== ACTIVE LOAN PROFILE MATCHING ==========
        try:
            from models.active_loan_profile import ActiveLoanProfile

            active_loan = db.query(ActiveLoanProfile).filter(
                func.upper(ActiveLoanProfile.loan_number) == loan_num_upper,
                ActiveLoanProfile.is_deleted == False
            ).first()

            if active_loan:
                logger.info(f"Found match in ActiveLoanProfile: {active_loan.id}")
                match_results["candidates"].append({
                    "type": "active_loan",
                    "id": str(active_loan.id),
                    "name": f"Active Loan {active_loan.loan_number}",
                    "loan_number": active_loan.loan_number,
                    "confidence": 0.99,
                    "match_type": "active_loan_exact"
                })
            else:
                active_loans = db.query(ActiveLoanProfile).filter(
                    ActiveLoanProfile.loan_number.ilike(f"%{loan_num}%"),
                    ActiveLoanProfile.is_deleted == False
                ).all()

                for al in active_loans:
                    logger.info(f"Found partial match in ActiveLoanProfile: {al.id}")
                    match_results["candidates"].append({
                        "type": "active_loan",
                        "id": str(al.id),
                        "name": f"Active Loan {al.loan_number}",
                        "loan_number": al.loan_number,
                        "confidence": 0.90,
                        "match_type": "active_loan_partial"
                    })

        except Exception as e:
            logger.debug(f"ActiveLoanProfile check skipped: {e}")

        # ========== REGULAR LOAN TABLE MATCHING ==========
        try:
            loan = db.query(Loan).filter(
                func.upper(Loan.loan_number) == loan_num_upper,
                Loan.loan_officer_id == user_id
            ).first()

            if loan:
                entity_type = get_loan_entity_type(loan)
                logger.info(f"Found exact match with user's loan: {loan.id} (type: {entity_type})")
                match_results["candidates"].append({
                    "type": entity_type,
                    "id": loan.id,
                    "name": loan.borrower_name,
                    "loan_number": loan.loan_number,
                    "confidence": 0.98,
                    "match_type": "loan_user_owned_exact"
                })
            else:
                loan = db.query(Loan).filter(
                    func.upper(Loan.loan_number) == loan_num_upper
                ).first()
                if loan:
                    entity_type = get_loan_entity_type(loan)
                    logger.info(f"Found exact match (any user): {loan.id} (type: {entity_type})")
                    match_results["candidates"].append({
                        "type": entity_type,
                        "id": loan.id,
                        "name": loan.borrower_name,
                        "loan_number": loan.loan_number,
                        "confidence": 0.95,
                        "match_type": "loan_exact"
                    })
                else:
                    logger.info(f"Trying partial match for: {loan_num}")
                    loans = db.query(Loan).filter(
                        Loan.loan_number.ilike(f"%{loan_num}%")
                    ).all()
                    logger.info(f"Found {len(loans)} partial matches")
                    for l in loans:
                        entity_type = get_loan_entity_type(l)
                        conf = 0.90 if l.loan_officer_id == user_id else 0.85
                        match_results["candidates"].append({
                            "type": entity_type,
                            "id": l.id,
                            "name": l.borrower_name,
                            "loan_number": l.loan_number,
                            "confidence": conf,
                            "match_type": "loan_partial"
                        })
        except Exception as e:
            logger.warning(f"Loan table matching error: {e}")

        # If we have loan number candidates, pick the best one and return early
        if match_results["candidates"]:
            best = max(match_results["candidates"], key=lambda x: x["confidence"])
            logger.info(f"Best loan number match: {best['type']} id={best['id']} conf={best['confidence']:.2f}")
            match_results["entity_type"] = best["type"]
            match_results["entity_id"] = best["id"]
            match_results["confidence"] = best["confidence"]
            return match_results

    # ========== LEAD MATCHING (Email, Phone, Name) ==========
    if extracted_email:
        logger.info(f"Trying email match: '{extracted_email}'")
        email_leads = db.query(Lead).filter(
            Lead.email.ilike(extracted_email)
        ).all()
        for lead in email_leads:
            conf = 0.98 if lead.owner_id == user_id else 0.92
            match_results["candidates"].append({
                "type": "lead",
                "id": lead.id,
                "name": lead.name,
                "confidence": conf,
                "match_type": "email_exact"
            })
            logger.info(f"Email match found: Lead {lead.id} - {lead.name}")

    # Try phone matching (high confidence)
    if extracted_phone and len(extracted_phone) >= 10:
        logger.info(f"Trying phone match: '{extracted_phone}'")
        # TENANT-002: Scope lead query to organization to prevent cross-tenant leakage
        lead_query = db.query(Lead)
        if organization_id:
            lead_query = lead_query.filter(Lead.organization_id == organization_id)
        all_leads = lead_query.all()
        for lead in all_leads:
            if lead.phone:
                lead_phone = normalize_phone(lead.phone)
                if lead_phone and lead_phone == extracted_phone:
                    existing = next((c for c in match_results["candidates"]
                                   if c["type"] == "lead" and c["id"] == lead.id), None)
                    if not existing:
                        conf = 0.95 if lead.owner_id == user_id else 0.88
                        match_results["candidates"].append({
                            "type": "lead",
                            "id": lead.id,
                            "name": lead.name,
                            "confidence": conf,
                            "match_type": "phone_exact"
                        })
                        logger.info(f"Phone match found: Lead {lead.id} - {lead.name}")

    # Try to match by borrower name
    borrower_last_name = get_last_name(borrower_name) if borrower_name else ""
    if borrower_name:
        logger.info(f"Attempting to match borrower name: '{borrower_name}' (last name: '{borrower_last_name}')")

        # TENANT-002: Scope lead query to organization to prevent cross-tenant leakage
        lead_name_query = db.query(Lead)
        if organization_id:
            lead_name_query = lead_name_query.filter(Lead.organization_id == organization_id)
        all_leads = lead_name_query.all()
        for lead in all_leads:
            if lead.name:
                is_match, conf = names_match(borrower_name, lead.name)
                if is_match:
                    existing = next((c for c in match_results["candidates"]
                                   if c["type"] == "lead" and c["id"] == lead.id), None)
                    if existing:
                        existing["confidence"] = min(0.99, existing["confidence"] + 0.1)
                        existing["match_type"] += "+name"
                    else:
                        final_conf = conf if lead.owner_id == user_id else conf * 0.90
                        match_results["candidates"].append({
                            "type": "lead",
                            "id": lead.id,
                            "name": lead.name,
                            "confidence": final_conf,
                            "match_type": "lead_name"
                        })
                        logger.info(f"Name match found: Lead {lead.id} - {lead.name} (conf: {final_conf:.2f})")

    # ========== LOAN MATCHING (Name, Email, Phone) ==========
    if borrower_name or extracted_email or extracted_phone:
        try:
            loan_results = db.execute(
                text("""
                    SELECT id, borrower_name, coborrower_name, loan_officer_id,
                           borrower_email, borrower_phone, co_borrower_email, loan_number
                    FROM loans
                    WHERE loan_officer_id = :user_id
                """),
                {"user_id": user_id}
            ).fetchall()
            logger.info(f"Found {len(loan_results)} loans for user {user_id}")
        except Exception as e:
            logger.error(f"Error querying user loans: {e}")
            loan_results = []

        for loan_row in loan_results:
            loan_id, loan_borrower_name, loan_coborrower_name, loan_officer_id, loan_borrower_email, loan_borrower_phone, loan_coborrower_email, loan_loan_number = loan_row

            # ===== EMAIL MATCHING =====
            if extracted_email and loan_borrower_email:
                if normalize_email(extracted_email) == normalize_email(loan_borrower_email):
                    existing = next((c for c in match_results["candidates"]
                                   if c["type"] == "loan" and c["id"] == loan_id), None)
                    if existing:
                        existing["confidence"] = min(0.99, existing["confidence"] + 0.15)
                        existing["match_type"] += "+email"
                    else:
                        match_results["candidates"].append({
                            "type": "loan",
                            "id": loan_id,
                            "name": loan_borrower_name,
                            "loan_number": loan_loan_number,
                            "confidence": 0.96,
                            "match_type": "borrower_email"
                        })
                        logger.info(f"Loan email match: {loan_id} - {loan_borrower_name} (email: {loan_borrower_email})")

            if extracted_email and loan_coborrower_email:
                if normalize_email(extracted_email) == normalize_email(loan_coborrower_email):
                    existing = next((c for c in match_results["candidates"]
                                   if c["type"] == "loan" and c["id"] == loan_id), None)
                    if existing:
                        existing["confidence"] = min(0.99, existing["confidence"] + 0.12)
                        existing["match_type"] += "+coborrower_email"
                    else:
                        match_results["candidates"].append({
                            "type": "loan",
                            "id": loan_id,
                            "name": f"{loan_borrower_name} (co-borrower email match)",
                            "loan_number": loan_loan_number,
                            "confidence": 0.92,
                            "match_type": "coborrower_email"
                        })

            # ===== PHONE MATCHING =====
            if extracted_phone and loan_borrower_phone:
                if normalize_phone(extracted_phone) == normalize_phone(loan_borrower_phone):
                    existing = next((c for c in match_results["candidates"]
                                   if c["type"] == "loan" and c["id"] == loan_id), None)
                    if existing:
                        existing["confidence"] = min(0.99, existing["confidence"] + 0.12)
                        existing["match_type"] += "+phone"
                    else:
                        match_results["candidates"].append({
                            "type": "loan",
                            "id": loan_id,
                            "name": loan_borrower_name,
                            "loan_number": loan_loan_number,
                            "confidence": 0.93,
                            "match_type": "borrower_phone"
                        })
                        logger.info(f"Loan phone match: {loan_id} - {loan_borrower_name}")

            # ===== NAME MATCHING =====
            if borrower_name and loan_borrower_name:
                is_match, conf = names_match(borrower_name, loan_borrower_name)
                if is_match:
                    existing = next((c for c in match_results["candidates"]
                                   if c["type"] == "loan" and c["id"] == loan_id), None)
                    if existing:
                        existing["confidence"] = min(0.99, existing["confidence"] + 0.10)
                        existing["match_type"] += "+name"
                    else:
                        match_results["candidates"].append({
                            "type": "loan",
                            "id": loan_id,
                            "name": loan_borrower_name,
                            "loan_number": loan_loan_number,
                            "confidence": conf,
                            "match_type": "borrower_name"
                        })
                        logger.info(f"Loan borrower match: {loan_id} - {loan_borrower_name} (conf: {conf:.2f})")

            if borrower_name and loan_coborrower_name:
                is_match, conf = names_match(borrower_name, loan_coborrower_name)
                if is_match:
                    existing = next((c for c in match_results["candidates"]
                                   if c["type"] == "loan" and c["id"] == loan_id), None)
                    if existing:
                        existing["confidence"] = min(0.99, existing["confidence"] + 0.08)
                        existing["match_type"] += "+coborrower_name"
                    else:
                        match_results["candidates"].append({
                            "type": "loan",
                            "id": loan_id,
                            "name": f"{loan_borrower_name} (co-borrower: {loan_coborrower_name})",
                            "loan_number": loan_loan_number,
                            "confidence": conf * 0.95,
                            "match_type": "coborrower_name"
                        })

            # Last name match
            if borrower_last_name:
                borrower_ln = get_last_name(loan_borrower_name) if loan_borrower_name else ""
                coborrower_ln = get_last_name(loan_coborrower_name) if loan_coborrower_name else ""

                if borrower_last_name == borrower_ln or borrower_last_name == coborrower_ln:
                    existing = next((c for c in match_results["candidates"]
                                   if c["type"] == "loan" and c["id"] == loan_id), None)
                    if not existing:
                        match_results["candidates"].append({
                            "type": "loan",
                            "id": loan_id,
                            "name": loan_borrower_name,
                            "loan_number": loan_loan_number,
                            "confidence": 0.75,
                            "match_type": "last_name_family"
                        })

        # If no matches found with user filter, try broader search for loans
        if not any(c["type"] == "loan" for c in match_results["candidates"]):
            logger.info("No loan matches with user filter, trying all loans...")
            try:
                all_loan_results = db.execute(
                    text("""
                        SELECT id, borrower_name, coborrower_name, loan_officer_id,
                               borrower_email, borrower_phone, co_borrower_email, loan_number
                        FROM loans
                    """)
                ).fetchall()
                logger.info(f"Found {len(all_loan_results)} total loans in database")
            except Exception as e:
                logger.error(f"Error querying all loans: {e}")
                all_loan_results = []

            for loan_row in all_loan_results:
                loan_id, loan_borrower_name, loan_coborrower_name, loan_officer_id, loan_borrower_email, loan_borrower_phone, loan_coborrower_email, loan_loan_number = loan_row

                if extracted_email and loan_borrower_email:
                    if normalize_email(extracted_email) == normalize_email(loan_borrower_email):
                        match_results["candidates"].append({
                            "type": "loan",
                            "id": loan_id,
                            "name": loan_borrower_name,
                            "loan_number": loan_loan_number,
                            "confidence": 0.94,
                            "match_type": "borrower_email_global"
                        })
                        logger.info(f"Global loan email match: {loan_id} - {loan_borrower_name}")
                        continue

                if extracted_phone and loan_borrower_phone:
                    if normalize_phone(extracted_phone) == normalize_phone(loan_borrower_phone):
                        match_results["candidates"].append({
                            "type": "loan",
                            "id": loan_id,
                            "name": loan_borrower_name,
                            "loan_number": loan_loan_number,
                            "confidence": 0.90,
                            "match_type": "borrower_phone_global"
                        })
                        logger.info(f"Global loan phone match: {loan_id} - {loan_borrower_name}")
                        continue

                if loan_borrower_name:
                    is_match, conf = names_match(borrower_name, loan_borrower_name)
                    if is_match:
                        match_results["candidates"].append({
                            "type": "loan",
                            "id": loan_id,
                            "name": loan_borrower_name,
                            "loan_number": loan_loan_number,
                            "confidence": conf * 0.85,
                            "match_type": "borrower_name_global"
                        })
                        logger.info(f"Global loan borrower match: {loan_id} - {loan_borrower_name}")

                if loan_coborrower_name:
                    is_match, conf = names_match(borrower_name, loan_coborrower_name)
                    if is_match:
                        match_results["candidates"].append({
                            "type": "loan",
                            "id": loan_id,
                            "name": f"{loan_borrower_name} (co-borrower: {loan_coborrower_name})",
                            "loan_number": loan_loan_number,
                            "confidence": conf * 0.80,
                            "match_type": "coborrower_name_global"
                        })

    # ========== PARTNER MATCHING (Referral Partners) ==========
    partner_name = fields.get("partner_name", {}).get("value") or fields.get("agent_name", {}).get("value") or fields.get("realtor_name", {}).get("value")
    partner_email = fields.get("partner_email", {}).get("value") or fields.get("agent_email", {}).get("value") or fields.get("realtor_email", {}).get("value")
    partner_phone = fields.get("partner_phone", {}).get("value") or fields.get("agent_phone", {}).get("value") or fields.get("realtor_phone", {}).get("value")
    partner_company = fields.get("partner_company", {}).get("value") or fields.get("brokerage", {}).get("value") or fields.get("company", {}).get("value")

    if partner_name or partner_email or partner_phone:
        logger.info(f"Trying partner match: name='{partner_name}', email='{partner_email}', phone='{partner_phone}'")
        all_partners = db.query(ReferralPartner).filter(ReferralPartner.status == "active").all()

        for partner in all_partners:
            partner_conf = 0.0
            match_reasons = []

            if partner_email and partner.email:
                if normalize_email(partner_email) == normalize_email(partner.email):
                    partner_conf = max(partner_conf, 0.95)
                    match_reasons.append("email")

            if partner_phone and partner.phone:
                if normalize_phone(partner_phone) == normalize_phone(partner.phone):
                    partner_conf = max(partner_conf, 0.90)
                    match_reasons.append("phone")

            if partner_name and partner.name:
                is_match, conf = names_match(partner_name, partner.name)
                if is_match:
                    partner_conf = max(partner_conf, conf * 0.90)
                    match_reasons.append("name")

            if partner_company and partner.company:
                if partner_company.lower().strip() in partner.company.lower() or partner.company.lower() in partner_company.lower().strip():
                    partner_conf = min(0.98, partner_conf + 0.10)
                    match_reasons.append("company")

            if partner_conf > 0.5:
                match_results["candidates"].append({
                    "type": "partner",
                    "id": partner.id,
                    "name": partner.name,
                    "confidence": partner_conf,
                    "match_type": "+".join(match_reasons)
                })
                logger.info(f"Partner match found: {partner.name} ({partner_conf:.2f}) via {'+'.join(match_reasons)}")

    # ========== PORTFOLIO/MUM CLIENT MATCHING (by name, email, phone) ==========
    if borrower_name or extracted_email or extracted_phone:
        logger.info(f"[MUM-NAME] Starting name/email/phone matching for borrower='{borrower_name}'")
        try:
            all_mum_clients = db.query(MUMClient).all()
            logger.info(f"[MUM-NAME] Checking {len(all_mum_clients)} MUM clients for name match")

            sample_names = [c.name for c in all_mum_clients[:5]]
            logger.info(f"[MUM-NAME] Sample MUM client names: {sample_names}")

            for client in all_mum_clients:
                existing = next((c for c in match_results["candidates"]
                               if c["type"] == "portfolio" and c["id"] == client.id), None)
                if existing:
                    continue

                client_conf = 0.0
                match_reasons = []

                if extracted_email and client.email:
                    if normalize_email(extracted_email) == normalize_email(client.email):
                        client_conf = max(client_conf, 0.95)
                        match_reasons.append("email")

                if extracted_phone and client.phone:
                    if normalize_phone(extracted_phone) == normalize_phone(client.phone):
                        client_conf = max(client_conf, 0.90)
                        match_reasons.append("phone")

                if borrower_name and client.name:
                    is_match, conf = names_match(borrower_name, client.name)
                    if is_match:
                        client_conf = max(client_conf, conf * 0.88)
                        match_reasons.append("name")

                if client_conf > 0.5:
                    match_results["candidates"].append({
                        "type": "portfolio",
                        "id": client.id,
                        "name": client.name,
                        "loan_number": client.loan_number,
                        "confidence": client_conf,
                        "match_type": "+".join(match_reasons)
                    })
                    logger.info(f"Portfolio match found: {client.name} ({client_conf:.2f}) via {'+'.join(match_reasons)}")
        except Exception as e:
            logger.warning(f"Portfolio matching failed (table may not exist): {e}")

    # Return best candidate if found
    logger.info(f"=" * 60)
    logger.info(f"MATCH_ENTITY DEBUG - Final Results")
    logger.info(f"=" * 60)
    logger.info(f"Total candidates found: {len(match_results['candidates'])}")

    if match_results["candidates"]:
        for i, cand in enumerate(match_results["candidates"]):
            logger.info(f"  Candidate {i+1}: {cand['type']} - {cand.get('name', 'N/A')} (id={cand['id']}, conf={cand['confidence']:.2f}, via={cand.get('match_type', 'unknown')})")

        best = max(match_results["candidates"], key=lambda x: x["confidence"])
        logger.info(f"✓ BEST MATCH: {best['type']} - {best.get('name', 'N/A')} (id={best['id']}, conf={best['confidence']:.2f})")
        match_results["entity_type"] = best["type"]
        match_results["entity_id"] = best["id"]
        match_results["confidence"] = best["confidence"]
    else:
        logger.info("✗ NO MATCH FOUND - All matching strategies failed")
        logger.info(f"  Searched with: name='{borrower_name}', email='{extracted_email}', phone='{extracted_phone}'")
        logger.info(f"  Loan numbers tried: {loan_numbers_to_try}")

    logger.info(f"=" * 60)
    return match_results


def classify_email_intent(subject: str, content: str, fields: Dict[str, Any]) -> Dict[str, Any]:
    """Classify the intent/type of the email based on subject and content"""

    subject_lower = subject.lower() if subject else ""
    content_lower = content.lower() if content else ""

    if any(keyword in subject_lower for keyword in ["clear to close", "cleartoclose", "ctc", "clear-to-close"]):
        return {"intent": "Clear to Close", "description": "Borrower has been cleared to close on their loan", "confidence": 0.95}

    if any(keyword in subject_lower for keyword in ["appraisal", "appraisal report", "home appraisal"]):
        return {"intent": "Appraisal Update", "description": "Appraisal report or update received", "confidence": 0.90}

    if any(keyword in subject_lower for keyword in ["rate lock", "lock confirmation", "locked rate"]):
        return {"intent": "Rate Lock", "description": "Interest rate has been locked for the loan", "confidence": 0.90}

    if any(keyword in subject_lower for keyword in ["underwriting", "underwriter", "uw approval", "conditionally approved"]):
        return {"intent": "Underwriting Update", "description": "Update from underwriting department", "confidence": 0.85}

    if any(keyword in subject_lower for keyword in ["title", "closing", "settlement"]):
        return {"intent": "Title/Closing Update", "description": "Update related to title or closing process", "confidence": 0.80}

    if "loan_number" in fields or "borrower_name" in fields:
        return {"intent": "Loan Update", "description": "General loan status update", "confidence": 0.70}

    return {"intent": "General", "description": "General communication", "confidence": 0.50}


def get_entity_name(entity_type: str, entity_id, db: Session) -> str:
    """Get the name of the matched entity"""
    _ensure_models()
    try:
        if entity_type == "loan":
            loan = db.query(Loan).filter(Loan.id == entity_id).first()
            return loan.borrower_name if loan and loan.borrower_name else f"Loan #{entity_id}"
        elif entity_type == "lead":
            lead = db.query(Lead).filter(Lead.id == entity_id).first()
            return lead.name if lead and lead.name else f"Lead #{entity_id}"
        elif entity_type == "active_loan":
            try:
                from models.active_loan_profile import ActiveLoanProfile
                from models.lead_profile import LeadProfile
                import uuid as uuid_mod

                if isinstance(entity_id, str):
                    try:
                        loan_uuid = uuid_mod.UUID(entity_id)
                    except ValueError:
                        loan_uuid = entity_id
                else:
                    loan_uuid = entity_id

                active_loan = db.query(ActiveLoanProfile).filter(
                    ActiveLoanProfile.id == loan_uuid
                ).first()

                if active_loan:
                    if active_loan.lead_profile_id:
                        lead_profile = db.query(LeadProfile).filter(
                            LeadProfile.id == active_loan.lead_profile_id
                        ).first()
                        if lead_profile:
                            name_parts = []
                            if lead_profile.first_name:
                                name_parts.append(lead_profile.first_name)
                            if lead_profile.last_name:
                                name_parts.append(lead_profile.last_name)
                            if name_parts:
                                return " ".join(name_parts)
                    return f"Portfolio Loan {active_loan.loan_number}"
            except Exception as e:
                logger.error(f"Error getting ActiveLoanProfile: {e}")
            return f"Portfolio Loan #{entity_id}"
        elif entity_type == "client":
            client = db.query(Lead).filter(Lead.id == entity_id).first()
            return client.name if client and client.name else f"Client #{entity_id}"
        elif entity_type == "portfolio":
            try:
                loan = db.query(Loan).filter(Loan.id == entity_id).first()
                if loan:
                    return loan.borrower_name if loan.borrower_name else f"Portfolio Loan #{entity_id}"
            except Exception as e:
                logger.exception(f"Failed to look up portfolio Loan for entity_id {entity_id}: {e}")
            mum_client = db.query(MUMClient).filter(MUMClient.id == entity_id).first()
            return mum_client.name if mum_client and mum_client.name else f"Portfolio Client #{entity_id}"
        elif entity_type == "partner":
            partner = db.query(ReferralPartner).filter(ReferralPartner.id == entity_id).first()
            return partner.name if partner and partner.name else f"Partner #{entity_id}"
    except Exception as e:
        logger.error(f"Error getting entity name: {e}")

    return f"{entity_type} #{entity_id}"


def generate_recommended_action(email_intent: Dict[str, Any], entity_type: str, fields: Dict[str, Any]) -> Dict[str, Any]:
    """Generate recommended action based on email intent and context"""

    intent = email_intent.get("intent", "General")

    if intent == "Clear to Close":
        return {
            "title": "Update Status to Clear to Close",
            "description": "The AI recommends updating the loan status to 'Clear to Close' based on this email notification.",
            "action_type": "status_update",
            "action_value": "Clear to Close",
            "learning_status": "Learning from your approvals to auto-execute in the future"
        }

    if intent == "Appraisal Update":
        return {
            "title": "Update Appraisal Information",
            "description": "The AI recommends updating the appraisal value and date in the loan record.",
            "action_type": "field_update",
            "action_value": "appraisal_data",
            "learning_status": "Learning from your approvals to auto-execute in the future"
        }

    if intent == "Rate Lock":
        return {
            "title": "Update Rate and Lock Date",
            "description": "The AI recommends updating the interest rate and lock expiration date.",
            "action_type": "field_update",
            "action_value": "rate_lock_data",
            "learning_status": "Learning from your approvals to auto-execute in the future"
        }

    if intent == "Underwriting Update":
        return {
            "title": "Update Status to Underwriting",
            "description": "The AI recommends updating the loan status based on underwriting progress.",
            "action_type": "status_update",
            "action_value": "In Underwriting",
            "learning_status": "Learning from your approvals to auto-execute in the future"
        }

    return {
        "title": "Update Loan Information",
        "description": "The AI recommends applying the extracted data to the matched loan record.",
        "action_type": "field_update",
        "action_value": "general",
        "learning_status": "Learning from your approvals to auto-execute in the future"
    }


# ============================================================================
# CALENDLY TIME SLOT SCHEDULING FOR TASKS
# ============================================================================

def detect_scheduling_intent(title: str, description: str = "") -> bool:
    """Detect if a task is about scheduling a meeting/call with someone."""
    scheduling_keywords = [
        "schedule", "scheduling", "appointment", "meeting", "call",
        "pick a time", "pick time", "choose a time", "choose time",
        "set up a call", "set up call", "book", "booking",
        "calendar", "availability", "when to speak", "time to speak",
        "time to meet", "time to talk", "consultation", "consult"
    ]

    text_combined = f"{title} {description}".lower()
    return any(keyword in text_combined for keyword in scheduling_keywords)


def get_calendly_time_slots_for_user(user_id: int, db: Session, num_slots: int = 5) -> dict:
    """Fetch available Calendly time slots for a user."""
    _ensure_models()

    try:
        cred = db.query(IntegrationCredential).filter(
            IntegrationCredential.user_id == user_id,
            IntegrationCredential.integration_type == "calendly",
            IntegrationCredential.is_active == True
        ).first()

        calendly_token = None
        if cred and cred.api_key:
            calendly_token = cred.api_key
        else:
            calendly_token = os.getenv("CALENDLY_API_TOKEN")

        if not calendly_token:
            logger.warning(f"No Calendly token found for user {user_id}")
            return {"success": False, "error": "Calendly not configured", "slots": []}

        headers = {
            "Authorization": f"Bearer {calendly_token}",
            "Content-Type": "application/json"
        }

        user_response = requests.get(
            "https://api.calendly.com/users/me",
            headers=headers,
            timeout=10
        )

        if user_response.status_code != 200:
            logger.error(f"Calendly user API error: {user_response.status_code}")
            return {"success": False, "error": "Could not fetch Calendly user", "slots": []}

        user_uri = user_response.json().get("resource", {}).get("uri")

        event_types_response = requests.get(
            "https://api.calendly.com/event_types",
            headers=headers,
            params={"user": user_uri, "active": "true"},
            timeout=10
        )

        if event_types_response.status_code != 200:
            logger.error(f"Calendly event types API error: {event_types_response.status_code}")
            return {"success": False, "error": "Could not fetch event types", "slots": []}

        event_types = event_types_response.json().get("collection", [])

        if not event_types:
            return {"success": False, "error": "No active Calendly event types", "slots": []}

        event_type = event_types[0]
        event_type_uuid = event_type.get("uri", "").split("/")[-1]
        event_type_name = event_type.get("name", "Meeting")
        scheduling_url = event_type.get("scheduling_url", "")
        duration_minutes = event_type.get("duration", 30)

        start_time = datetime.now(timezone.utc).isoformat()
        end_time = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()

        availability_response = requests.get(
            "https://api.calendly.com/event_type_available_times",
            headers=headers,
            params={
                "event_type": f"https://api.calendly.com/event_types/{event_type_uuid}",
                "start_time": start_time,
                "end_time": end_time
            },
            timeout=10
        )

        if availability_response.status_code != 200:
            logger.error(f"Calendly availability API error: {availability_response.status_code}")
            return {"success": False, "error": "Could not fetch availability", "slots": []}

        available_times = availability_response.json().get("collection", [])

        formatted_slots = []
        for slot in available_times[:num_slots]:
            start_str = slot.get("start_time", "")
            if start_str:
                slot_dt = datetime.fromisoformat(start_str.replace("Z", "+00:00"))
                display_date = slot_dt.strftime("%A, %b %d at %-I:%M %p")
                booking_link = f"{scheduling_url}?month={slot_dt.strftime('%Y-%m')}&date={slot_dt.strftime('%Y-%m-%d')}"

                formatted_slots.append({
                    "display": display_date,
                    "iso": start_str,
                    "booking_link": booking_link,
                    "duration_minutes": duration_minutes
                })

        return {
            "success": True,
            "event_type_name": event_type_name,
            "scheduling_url": scheduling_url,
            "duration_minutes": duration_minutes,
            "slots": formatted_slots
        }

    except requests.exceptions.RequestException as e:
        logger.error(f"Calendly API request error: {e}")
        return {"success": False, "error": "Internal server error", "slots": []}
    except Exception as e:
        logger.error(f"Error fetching Calendly slots: {e}")
        return {"success": False, "error": "Internal server error", "slots": []}


def generate_scheduling_email_draft(
    client_name: str,
    calendly_slots: dict,
    user_name: str = "Your Loan Officer"
) -> str:
    """Generate an AI-drafted email with embedded Calendly time slots."""
    first_name = client_name.split()[0] if client_name else "there"

    if not calendly_slots.get("success") or not calendly_slots.get("slots"):
        return f"""Hi {first_name},

    I'd like to schedule a call with you to discuss your loan. Please let me know what times work best for you this week.

    Looking forward to connecting!

    Best regards,
    {user_name}"""

    slots = calendly_slots.get("slots", [])
    duration = calendly_slots.get("duration_minutes", 30)

    time_slots_html = ""
    for slot in slots:
        display = slot.get("display", "")
        link = slot.get("booking_link", "")
        time_slots_html += f"""
    <div style="margin: 8px 0;">
      <a href="{link}" style="display: inline-block; padding: 12px 24px; background: linear-gradient(135deg, #218D8D 0%, #10b981 100%); color: white; text-decoration: none; border-radius: 8px; font-weight: 600; font-size: 14px;">
        {display}
      </a>
    </div>"""

    email_body = f"""Hi {first_name},

    I'd like to schedule a {duration}-minute call to discuss your mortgage. Please click one of the available times below to book directly on my calendar:

    <div style="margin: 20px 0; padding: 16px; background: #f7fafc; border-radius: 12px; border: 1px solid #e2e8f0;">
    <strong style="color: #1a202c; font-size: 14px;">📅 Available Time Slots:</strong>
    {time_slots_html}
    </div>

    If none of these times work, you can also <a href="{calendly_slots.get('scheduling_url', '#')}" style="color: #218D8D; font-weight: 600;">view all available times</a> on my calendar.

    Looking forward to speaking with you!

    Best regards,
    {user_name}"""

    return email_body


# ============================================================================
# MILESTONE TASK CREATION
# ============================================================================

def create_milestone_tasks(loan, updated_fields: list, db: Session) -> list:
    """Create tasks automatically when milestone dates are populated."""
    _ensure_models()
    tasks_created = []

    milestone_task_triggers = [
        ("stage->PROCESSING", "Review Application Package", "Review newly submitted application for completeness", 0, "high"),
        ("stage->SUBMITTED", "Monitor UW Queue", "Application submitted - monitor underwriting queue", 1, "medium"),
        ("stage->UW_RECEIVED", "Follow Up on Underwriting", "File in underwriting - follow up for status", 2, "high"),
        ("stage->APPROVED", "Review Approval Conditions", "Loan approved - review and clear any conditions", 0, "high"),
        ("stage->CTC", "Schedule Closing", "Clear to Close received - coordinate closing date", 0, "urgent"),
        ("stage->FUNDED", "Send Thank You & Request Review", "Loan funded - send thank you and request review", 1, "medium"),
        ("appraisal_ordered_date", "Follow Up on Appraisal", "Appraisal ordered - follow up in 3 days if not scheduled", 3, "medium"),
        ("appraisal_scheduled_date", "Confirm Appraisal Access", "Appraisal scheduled - confirm property access", 0, "medium"),
        ("appraisal_completed_date", "Review Appraisal Report", "Appraisal completed - review report for value/issues", 1, "high"),
        ("lock_date", "Monitor Lock Expiration", "Rate locked - monitor expiration and closing timeline", 0, "high"),
        ("lock_expiration_date", "Lock Expiration Alert", "Rate lock expires soon - verify closing timeline", -3, "urgent"),
        ("closing_date", "7-Day Closing Checklist", "Closing approaching - verify all items ready", -7, "high"),
        ("closing_date", "Final Closing Prep", "Closing in 3 days - final verification", -3, "urgent"),
    ]

    try:
        logger.info(f"🔍 create_milestone_tasks called for loan {loan.loan_number} with updated_fields: {updated_fields}")

        for trigger_field, task_title, task_desc, days_offset, priority in milestone_task_triggers:
            if trigger_field not in updated_fields:
                continue

            logger.info(f"🎯 Trigger matched: {trigger_field} -> Creating task: {task_title}")

            due_date = None
            if trigger_field.startswith("stage->"):
                due_date = datetime.now(timezone.utc) + timedelta(days=days_offset)
            else:
                date_value = getattr(loan, trigger_field, None)
                if date_value:
                    if isinstance(date_value, datetime):
                        due_date = date_value + timedelta(days=days_offset)
                    else:
                        due_date = datetime.now(timezone.utc) + timedelta(days=max(0, days_offset))

            if not due_date:
                due_date = datetime.now(timezone.utc) + timedelta(days=1)

            existing_task = db.query(Task).filter(
                Task.loan_id == loan.id,
                Task.title == task_title,
                Task.status != "completed"
            ).first()

            if existing_task:
                logger.info(f"Task '{task_title}' already exists for loan {loan.loan_number}, skipping")
                continue

            new_task = Task(
                title=task_title,
                description=f"{task_desc}\n\nLoan: {loan.loan_number}\nBorrower: {loan.borrower_name or 'N/A'}",
                status="pending",
                priority=priority,
                due_date=due_date,
                loan_id=loan.id,
                owner_id=loan.loan_officer_id,
                related_contact_name=loan.borrower_name,
                related_type="loan",
                created_at=datetime.now(timezone.utc)
            )

            db.add(new_task)
            tasks_created.append(task_title)
            logger.info(f"📋 Created task: '{task_title}' for loan {loan.loan_number}, due: {due_date}")

        if tasks_created:
            logger.info(f"💾 Committing {len(tasks_created)} tasks to database...")
            db.commit()
            logger.info(f"✅ Tasks committed successfully: {tasks_created}")
        else:
            logger.info(f"ℹ️ No matching triggers found for updated_fields: {updated_fields}")

    except Exception as e:
        import traceback
        logger.error(f"Error creating milestone tasks: {e}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        db.rollback()

    return tasks_created


def create_lead_milestone_tasks(lead, updated_fields: list, db: Session) -> list:
    """Create tasks automatically when lead milestone dates are populated."""
    _ensure_models()
    tasks_created = []

    lead_task_triggers = [
        ("application_started_date", "Review Started Application", "Application started - follow up to encourage completion", 1, "high"),
        ("application_completed_date", "Review Completed Application", "Application completed - review for completeness and pull credit", 0, "high"),
        ("stage->APPLICATION", "Process Application Package", "Application received - begin processing and verification", 0, "high"),
        ("credit_pulled_date", "Review Credit Report", "Credit pulled - review report and discuss with borrower", 0, "high"),
        ("preapproval_issued_date", "Send Preapproval Letter", "Preapproval issued - send letter to borrower and realtor", 0, "high"),
        ("stage->PRE_APPROVED", "Connect with Realtor", "Lead pre-approved - connect with realtor for home search", 1, "medium"),
    ]

    try:
        for trigger_field, task_title, task_desc, days_offset, priority in lead_task_triggers:
            if trigger_field not in updated_fields:
                continue

            due_date = None
            if trigger_field.startswith("stage->"):
                due_date = datetime.now(timezone.utc) + timedelta(days=days_offset)
            else:
                date_value = getattr(lead, trigger_field, None)
                if date_value:
                    if isinstance(date_value, datetime):
                        due_date = date_value + timedelta(days=days_offset)
                    else:
                        due_date = datetime.now(timezone.utc) + timedelta(days=max(0, days_offset))

            if not due_date:
                due_date = datetime.now(timezone.utc) + timedelta(days=1)

            existing_task = db.query(Task).filter(
                Task.lead_id == lead.id,
                Task.title == task_title,
                Task.status != "completed"
            ).first()

            if existing_task:
                logger.info(f"Task '{task_title}' already exists for lead {lead.name}, skipping")
                continue

            new_task = Task(
                title=task_title,
                description=f"{task_desc}\n\nLead: {lead.name}\nEmail: {lead.email or 'N/A'}",
                status="pending",
                priority=priority,
                due_date=due_date,
                lead_id=lead.id,
                owner_id=lead.owner_id,
                created_at=datetime.now(timezone.utc)
            )

            db.add(new_task)
            tasks_created.append(task_title)
            logger.info(f"📋 Created task: '{task_title}' for lead {lead.name}, due: {due_date}")

        if tasks_created:
            db.commit()

    except Exception as e:
        logger.error(f"Error creating lead milestone tasks: {e}")
        db.rollback()

    return tasks_created


# ============================================================================
# DATA APPLICATION
# ============================================================================

def apply_extracted_data(extracted_data, db: Session) -> bool:
    """Apply extracted data to CRM entities - save all extracted fields to the borrower's profile"""
    _ensure_models()

    def get_field_value(fields: dict, field_name: str, min_confidence: float = 0.70):
        """Helper to safely get field value if confidence is high enough"""
        if field_name in fields:
            field = fields[field_name]
            if isinstance(field, dict) and field.get("confidence", 0) >= min_confidence:
                return field.get("value")
        return None

    def parse_date(date_str):
        """Parse various date formats to datetime"""
        if not date_str:
            return None
        try:
            if isinstance(date_str, datetime):
                return date_str
            return datetime.fromisoformat(str(date_str).replace('Z', '+00:00'))
        except (ValueError, TypeError):
            try:
                from dateutil import parser
                return parser.parse(str(date_str))
            except (ValueError, TypeError):
                return None

    try:
        fields = extracted_data.fields or {}
        updated_fields = []

        if extracted_data.match_entity_type == "loan" and extracted_data.match_entity_id:
            loan = db.query(Loan).filter(Loan.id == extracted_data.match_entity_id).first()
            if not loan:
                logger.warning(f"Loan {extracted_data.match_entity_id} not found for data application - approving without applying data")
                return True

            logger.info(f"Applying extracted data to loan {loan.id} ({loan.loan_number})")

            # Capture old stage for SLA tracking
            _dre_old_stage = loan.stage
            if _dre_old_stage and hasattr(_dre_old_stage, 'value'):
                _dre_old_stage = _dre_old_stage.value

            if value := get_field_value(fields, "borrower_name"):
                loan.borrower_name = str(value)
                updated_fields.append("borrower_name")
            elif get_field_value(fields, "first_name") or get_field_value(fields, "last_name"):
                first = get_field_value(fields, "first_name") or ""
                last = get_field_value(fields, "last_name") or ""
                full_name = f"{first} {last}".strip()
                if full_name:
                    loan.borrower_name = full_name
                    updated_fields.append("borrower_name")

            if value := get_field_value(fields, "borrower_email"):
                loan.borrower_email = str(value)
                updated_fields.append("borrower_email")

            if value := get_field_value(fields, "borrower_phone"):
                loan.borrower_phone = str(value)
                updated_fields.append("borrower_phone")

            if value := get_field_value(fields, "coborrower_name"):
                loan.coborrower_name = str(value)
                updated_fields.append("coborrower_name")

            if value := get_field_value(fields, "amount"):
                loan.amount = float(value)
                updated_fields.append("amount")
            elif value := get_field_value(fields, "loan_amount"):
                loan.amount = float(value)
                updated_fields.append("amount")

            if value := get_field_value(fields, "rate"):
                loan.rate = float(value)
                updated_fields.append("rate")

            if value := get_field_value(fields, "program"):
                loan.program = str(value)
                updated_fields.append("program")

            if value := get_field_value(fields, "property_address"):
                loan.property_address = str(value)
                updated_fields.append("property_address")

            if value := get_field_value(fields, "property_city"):
                loan.property_city = str(value)
                updated_fields.append("property_city")

            if value := get_field_value(fields, "property_state"):
                loan.property_state = str(value)
                updated_fields.append("property_state")

            if value := get_field_value(fields, "property_zip"):
                loan.property_zip = str(value)
                updated_fields.append("property_zip")

            if value := get_field_value(fields, "processor"):
                loan.processor = str(value)
                updated_fields.append("processor")

            if value := get_field_value(fields, "underwriter"):
                loan.underwriter = str(value)
                updated_fields.append("underwriter")

            if value := get_field_value(fields, "lender"):
                loan.lender = str(value)
                updated_fields.append("lender")

            if value := get_field_value(fields, "realtor_name"):
                loan.realtor_agent = str(value)
                updated_fields.append("realtor_agent")

            if value := get_field_value(fields, "title_company"):
                loan.title_company = str(value)
                updated_fields.append("title_company")

            if value := get_field_value(fields, "closing_date"):
                if parsed := parse_date(value):
                    loan.closing_date = parsed
                    updated_fields.append("closing_date")
            elif value := get_field_value(fields, "closing_scheduled_date"):
                if parsed := parse_date(value):
                    loan.closing_date = parsed
                    updated_fields.append("closing_date")

            if value := get_field_value(fields, "rate_lock_date"):
                if parsed := parse_date(value):
                    loan.lock_date = parsed
                    updated_fields.append("lock_date")

            if value := get_field_value(fields, "lock_expiration"):
                if parsed := parse_date(value):
                    loan.lock_expiration_date = parsed
                    updated_fields.append("lock_expiration_date")

            if value := get_field_value(fields, "appraisal_ordered_date"):
                if parsed := parse_date(value):
                    loan.appraisal_ordered_date = parsed
                    updated_fields.append("appraisal_ordered_date")

            if value := get_field_value(fields, "appraisal_scheduled_date"):
                if parsed := parse_date(value):
                    loan.appraisal_scheduled_date = parsed
                    updated_fields.append("appraisal_scheduled_date")

            if value := get_field_value(fields, "appraisal_completed_date"):
                if parsed := parse_date(value):
                    loan.appraisal_completed_date = parsed
                    updated_fields.append("appraisal_completed_date")

            if value := get_field_value(fields, "appraisal_value"):
                loan.appraisal_value = float(value)
                updated_fields.append("appraisal_value")

            if value := get_field_value(fields, "initial_disclosures_sent_date"):
                if parsed := parse_date(value):
                    loan.initial_disclosures_sent_date = parsed
                    updated_fields.append("initial_disclosures_sent_date")

            if value := get_field_value(fields, "initial_disclosures_signed_date"):
                if parsed := parse_date(value):
                    loan.initial_disclosures_signed_date = parsed
                    updated_fields.append("initial_disclosures_signed_date")

            if value := get_field_value(fields, "cd_received_signed_date"):
                if parsed := parse_date(value):
                    loan.cd_received_signed_date = parsed
                    updated_fields.append("cd_received_signed_date")

            if value := get_field_value(fields, "final_closing_package_sent_date"):
                if parsed := parse_date(value):
                    loan.final_closing_package_sent_date = parsed
                    updated_fields.append("final_closing_package_sent_date")
                    if loan.stage != LoanStage.FUNDED:
                        loan.stage = LoanStage.CTC
                        updated_fields.append("stage->CTC")

            if value := get_field_value(fields, "borrower_name"):
                if not loan.borrower_name or loan.borrower_name.strip() == "":
                    loan.borrower_name = str(value)
                    updated_fields.append("borrower_name")

            if value := get_field_value(fields, "milestone", min_confidence=0.85):
                milestone = str(value).lower()
                if "clearto" in milestone or "ctc" in milestone:
                    loan.stage = LoanStage.CTC
                    updated_fields.append("stage->CTC")
                elif "approved" in milestone:
                    loan.stage = LoanStage.APPROVED
                    updated_fields.append("stage->APPROVED")
                elif "processing" in milestone:
                    loan.stage = LoanStage.PROCESSING
                    updated_fields.append("stage->PROCESSING")
                elif "u/w" in milestone or "underwriting" in milestone or "received" in milestone:
                    loan.stage = LoanStage.UW_RECEIVED
                    updated_fields.append("stage->UW_RECEIVED")
                elif "submitted" in milestone:
                    loan.stage = LoanStage.SUBMITTED
                    updated_fields.append("stage->SUBMITTED")
                elif "funded" in milestone:
                    loan.stage = LoanStage.FUNDED
                    loan.funded_date = datetime.now(timezone.utc)
                    updated_fields.append("stage->FUNDED")

            loan.updated_at = datetime.now(timezone.utc)

            db.commit()
            logger.info(f"✅ Applied {len(updated_fields)} fields to loan {loan.loan_number}: {', '.join(updated_fields)}")

            # Wire to SLA tracking — detect stage changes from email parsing
            new_stage = loan.stage
            if new_stage and hasattr(new_stage, 'value'):
                new_stage = new_stage.value
            if new_stage and new_stage != _dre_old_stage:
                try:
                    from services.sla_tracking_service import track_loan_stage_change
                    track_loan_stage_change(
                        db, loan.id, _dre_old_stage, new_stage,
                        loan_number=loan.loan_number,
                        organization_id=getattr(loan, "organization_id", None),
                    )
                except Exception as e_sla:
                    logger.warning(f"SLA tracking hook failed for DRE loan {loan.id}: {e_sla}")

            tasks_created = create_milestone_tasks(loan, updated_fields, db)
            if tasks_created:
                logger.info(f"📋 Created {len(tasks_created)} tasks for loan {loan.loan_number}: {tasks_created}")
            return True

        elif extracted_data.match_entity_type == "lead" and extracted_data.match_entity_id:
            lead = db.query(Lead).filter(Lead.id == extracted_data.match_entity_id).first()
            if not lead:
                logger.warning(f"Lead {extracted_data.match_entity_id} not found for data application - approving without applying data")
                return True

            logger.info(f"Applying extracted data to lead {lead.id} ({lead.name})")

            if value := get_field_value(fields, "borrower_name"):
                lead.name = str(value)
                updated_fields.append("name")
            elif get_field_value(fields, "first_name") or get_field_value(fields, "last_name"):
                first = get_field_value(fields, "first_name") or ""
                last = get_field_value(fields, "last_name") or ""
                full_name = f"{first} {last}".strip()
                if full_name:
                    lead.name = full_name
                    updated_fields.append("name")

            if value := get_field_value(fields, "email"):
                lead.email = str(value)
                updated_fields.append("email")
            elif value := get_field_value(fields, "borrower_email"):
                lead.email = str(value)
                updated_fields.append("email")

            if value := get_field_value(fields, "phone"):
                lead.phone = str(value)
                updated_fields.append("phone")
            elif value := get_field_value(fields, "borrower_phone"):
                lead.phone = str(value)
                updated_fields.append("phone")

            if value := get_field_value(fields, "credit_score"):
                lead.credit_score = int(value)
                updated_fields.append("credit_score")

            if value := get_field_value(fields, "loan_amount"):
                lead.loan_amount = float(value)
                updated_fields.append("loan_amount")
            elif value := get_field_value(fields, "amount"):
                lead.loan_amount = float(value)
                updated_fields.append("loan_amount")

            if value := get_field_value(fields, "property_address"):
                lead.property_address = str(value)
                updated_fields.append("property_address")

            if value := get_field_value(fields, "program"):
                lead.loan_type = str(value)
                updated_fields.append("loan_type")

            if value := get_field_value(fields, "application_started_date"):
                if parsed := parse_date(value):
                    lead.application_started_date = parsed
                    updated_fields.append("application_started_date")

            if value := get_field_value(fields, "application_completed_date"):
                if parsed := parse_date(value):
                    lead.application_completed_date = parsed
                    updated_fields.append("application_completed_date")
                    db.execute(text("UPDATE leads SET stage = :stage WHERE id = :id"),
                               {"stage": LeadStage.APPLICATION.name, "id": lead.id})
                    updated_fields.append("stage->APPLICATION")

            if value := get_field_value(fields, "credit_pulled_date"):
                if parsed := parse_date(value):
                    lead.credit_pulled_date = parsed
                    updated_fields.append("credit_pulled_date")

            if value := get_field_value(fields, "preapproval_issued_date"):
                if parsed := parse_date(value):
                    lead.preapproval_issued_date = parsed
                    updated_fields.append("preapproval_issued_date")
                    db.execute(text("UPDATE leads SET stage = :stage WHERE id = :id"),
                               {"stage": LeadStage.PRE_APPROVED.name, "id": lead.id})
                    updated_fields.append("stage->PRE_APPROVED")

            lead.updated_at = datetime.now(timezone.utc)

            db.commit()
            logger.info(f"✅ Applied {len(updated_fields)} fields to lead {lead.name}: {', '.join(updated_fields)}")

            tasks_created = create_lead_milestone_tasks(lead, updated_fields, db)
            if tasks_created:
                logger.info(f"📋 Created {len(tasks_created)} tasks for lead {lead.name}: {tasks_created}")
            return True

        elif extracted_data.match_entity_type == "partner" and extracted_data.match_entity_id:
            partner = db.query(ReferralPartner).filter(ReferralPartner.id == extracted_data.match_entity_id).first()
            if not partner:
                logger.warning(f"Partner {extracted_data.match_entity_id} not found for data application")
                return True

            logger.info(f"Applying extracted data to partner {partner.id} ({partner.name})")

            if value := get_field_value(fields, "partner_name"):
                partner.name = str(value)
                updated_fields.append("name")
            elif value := get_field_value(fields, "agent_name"):
                partner.name = str(value)
                updated_fields.append("name")
            elif value := get_field_value(fields, "realtor_name"):
                partner.name = str(value)
                updated_fields.append("name")

            if value := get_field_value(fields, "partner_email"):
                partner.email = str(value)
                updated_fields.append("email")
            elif value := get_field_value(fields, "agent_email"):
                partner.email = str(value)
                updated_fields.append("email")

            if value := get_field_value(fields, "partner_phone"):
                partner.phone = str(value)
                updated_fields.append("phone")
            elif value := get_field_value(fields, "agent_phone"):
                partner.phone = str(value)
                updated_fields.append("phone")

            if value := get_field_value(fields, "partner_company"):
                partner.company = str(value)
                updated_fields.append("company")
            elif value := get_field_value(fields, "brokerage"):
                partner.company = str(value)
                updated_fields.append("company")

            partner.last_interaction = datetime.now(timezone.utc)
            updated_fields.append("last_interaction")

            db.commit()
            logger.info(f"✅ Applied {len(updated_fields)} fields to partner {partner.name}: {', '.join(updated_fields)}")
            return True

        elif extracted_data.match_entity_type == "portfolio" and extracted_data.match_entity_id:
            try:
                client = db.query(MUMClient).filter(MUMClient.id == extracted_data.match_entity_id).first()
                if not client:
                    logger.warning(f"Portfolio client {extracted_data.match_entity_id} not found")
                    return True

                logger.info(f"Applying extracted data to portfolio client {client.id} ({client.name})")

                if value := get_field_value(fields, "borrower_name"):
                    client.name = str(value)
                    updated_fields.append("name")

                if value := get_field_value(fields, "borrower_email"):
                    client.email = str(value)
                    updated_fields.append("email")
                elif value := get_field_value(fields, "email"):
                    client.email = str(value)
                    updated_fields.append("email")

                if value := get_field_value(fields, "borrower_phone"):
                    client.phone = str(value)
                    updated_fields.append("phone")
                elif value := get_field_value(fields, "phone"):
                    client.phone = str(value)
                    updated_fields.append("phone")

                db.commit()
                logger.info(f"✅ Applied {len(updated_fields)} fields to portfolio client {client.name}: {', '.join(updated_fields)}")
            except Exception as e:
                logger.warning(f"Portfolio client update failed: {e}")
            return True

        logger.info("No matched entity to apply data to")
        return True

    except Exception as e:
        logger.error(f"Apply extracted data error: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return False


# ============================================================================
# MICROSOFT OAUTH & EMAIL SYNC FUNCTIONS
# ============================================================================

def get_encryption_key():
    """Get encryption key from SECRET_KEY"""
    key_material = _SECRET_KEY.encode()[:32].ljust(32, b'0')
    return base64.urlsafe_b64encode(key_material)


def encrypt_token(token: str) -> str:
    """Encrypt a token for secure storage"""
    from cryptography.fernet import Fernet
    f = Fernet(get_encryption_key())
    return f.encrypt(token.encode()).decode()


def decrypt_token(encrypted_token: str) -> str:
    """Decrypt a stored token"""
    from cryptography.fernet import Fernet
    f = Fernet(get_encryption_key())
    return f.decrypt(encrypted_token.encode()).decode()


async def validate_microsoft_token(oauth_record, db: Session) -> dict:
    """Validate Microsoft OAuth token before use, auto-refreshing if needed.

    Enterprise Readiness Check 7.15: Email OAuth Validation

    This function should be called before any Microsoft Graph API operation
    to ensure the access token is valid. It checks:
      1. Token existence (access_token and refresh_token are present)
      2. Token expiry (refreshes proactively if within 5 minutes of expiry)
      3. Token usability (makes a lightweight /me call to verify)

    Args:
        oauth_record: MicrosoftOAuthToken record from the database.
        db: Database session for persisting refreshed tokens.

    Returns:
        dict with keys:
            valid (bool): Whether the token is ready for use.
            access_token (str|None): Decrypted access token if valid.
            error (str|None): Error description if not valid.
            needs_reauth (bool): True if user must re-authenticate entirely.
            refreshed (bool): True if the token was refreshed during validation.
    """
    _ensure_models()

    # 1. Check token existence
    if not oauth_record:
        return {
            "valid": False,
            "access_token": None,
            "error": "No OAuth record found",
            "needs_reauth": True,
            "refreshed": False,
        }

    if not oauth_record.access_token:
        return {
            "valid": False,
            "access_token": None,
            "error": "No access token stored",
            "needs_reauth": True,
            "refreshed": False,
        }

    if not oauth_record.refresh_token:
        return {
            "valid": False,
            "access_token": None,
            "error": "No refresh token stored - full re-authentication required",
            "needs_reauth": True,
            "refreshed": False,
        }

    # 2. Check token expiry and refresh proactively
    refreshed = False
    if oauth_record.token_expires_at:
        token_expiry = oauth_record.token_expires_at
        if token_expiry.tzinfo is None:
            token_expiry = token_expiry.replace(tzinfo=timezone.utc)

        if token_expiry < datetime.now(timezone.utc) + timedelta(minutes=5):
            logger.info(f"Microsoft token for user {oauth_record.user_id} expiring soon, refreshing proactively...")
            refresh_result = await refresh_microsoft_token(oauth_record, db)
            if not refresh_result.get("success"):
                return {
                    "valid": False,
                    "access_token": None,
                    "error": refresh_result.get("error", "Token refresh failed"),
                    "needs_reauth": refresh_result.get("needs_reauth", False),
                    "refreshed": False,
                }
            db.refresh(oauth_record)
            refreshed = True

    # 3. Decrypt and verify token usability with a lightweight Graph API call
    try:
        access_token = decrypt_token(oauth_record.access_token)
    except Exception as e:
        logger.error(f"Failed to decrypt Microsoft token for user {oauth_record.user_id}: {e}")
        return {
            "valid": False,
            "access_token": None,
            "error": "Token decryption failed - may need re-authentication",
            "needs_reauth": True,
            "refreshed": refreshed,
        }

    try:
        # Lightweight validation: call /me endpoint (minimal data, fast response)
        verify_response = requests.get(
            "https://graph.microsoft.com/v1.0/me?$select=id",
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=10,
        )

        if verify_response.status_code == 200:
            logger.debug(f"Microsoft token validated for user {oauth_record.user_id}")
            return {
                "valid": True,
                "access_token": access_token,
                "error": None,
                "needs_reauth": False,
                "refreshed": refreshed,
            }
        elif verify_response.status_code == 401:
            # Token is invalid despite not being expired: try one refresh
            if not refreshed:
                logger.info(f"Microsoft token invalid (401) for user {oauth_record.user_id}, attempting refresh...")
                refresh_result = await refresh_microsoft_token(oauth_record, db)
                if refresh_result.get("success"):
                    db.refresh(oauth_record)
                    access_token = decrypt_token(oauth_record.access_token)
                    return {
                        "valid": True,
                        "access_token": access_token,
                        "error": None,
                        "needs_reauth": False,
                        "refreshed": True,
                    }
                else:
                    return {
                        "valid": False,
                        "access_token": None,
                        "error": refresh_result.get("error", "Token refresh failed after 401"),
                        "needs_reauth": refresh_result.get("needs_reauth", True),
                        "refreshed": False,
                    }
            else:
                return {
                    "valid": False,
                    "access_token": None,
                    "error": "Token invalid after refresh - user must re-authenticate",
                    "needs_reauth": True,
                    "refreshed": True,
                }
        else:
            # Non-401 error (e.g., 403, 5xx): treat token as potentially valid
            # but the Graph API is having issues
            logger.warning(
                f"Microsoft token validation returned {verify_response.status_code} "
                f"for user {oauth_record.user_id} - treating as valid (non-auth error)"
            )
            return {
                "valid": True,
                "access_token": access_token,
                "error": None,
                "needs_reauth": False,
                "refreshed": refreshed,
            }

    except requests.Timeout:
        # Network timeout: token might be fine, Graph API is slow
        logger.warning(f"Microsoft token validation timed out for user {oauth_record.user_id}")
        return {
            "valid": True,
            "access_token": access_token,
            "error": None,
            "needs_reauth": False,
            "refreshed": refreshed,
        }
    except Exception as e:
        logger.error(f"Microsoft token validation error for user {oauth_record.user_id}: {e}")
        # Return the token anyway if we have it; caller can handle API errors
        return {
            "valid": True,
            "access_token": access_token,
            "error": f"Validation check failed: {str(e)[:100]}",
            "needs_reauth": False,
            "refreshed": refreshed,
        }


async def refresh_microsoft_token(oauth_record, db: Session) -> dict:
    """Refresh an expired Microsoft access token."""
    _ensure_models()
    try:
        refresh_token = decrypt_token(oauth_record.refresh_token)

        token_url = "https://login.microsoftonline.com/common/oauth2/v2.0/token"

        client_id = os.getenv("MICROSOFT_CLIENT_ID")
        client_secret = os.getenv("MICROSOFT_CLIENT_SECRET")

        if not client_id or not client_secret:
            logger.error("Microsoft OAuth credentials not configured")
            return {"success": False, "error": "Microsoft OAuth credentials not configured"}

        data = {
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
            "scope": "https://graph.microsoft.com/Mail.Read https://graph.microsoft.com/Mail.Send https://graph.microsoft.com/Calendars.Read offline_access"
        }

        response = requests.post(token_url, data=data)

        if response.status_code == 200:
            token_data = response.json()

            oauth_record.access_token = encrypt_token(token_data["access_token"])
            oauth_record.refresh_token = encrypt_token(token_data["refresh_token"])
            oauth_record.token_expires_at = datetime.now(timezone.utc) + timedelta(seconds=token_data["expires_in"])
            oauth_record.updated_at = datetime.now(timezone.utc)

            db.commit()
            logger.info(f"Refreshed Microsoft token for user {oauth_record.user_id}")
            return {"success": True}
        else:
            error_data = response.json() if response.headers.get('content-type', '').startswith('application/json') else {}
            error_code = error_data.get("error", "")
            error_desc = error_data.get("error_description", response.text)

            needs_reauth = error_code in ["invalid_grant", "interaction_required", "consent_required"]

            logger.error(f"Failed to refresh Microsoft token: {error_code} - {error_desc}")
            return {
                "success": False,
                "error": error_desc,
                "needs_reauth": needs_reauth,
                "error_code": error_code
            }

    except Exception as e:
        logger.error(f"Error refreshing Microsoft token: {e}")
        return {"success": False, "error": "Internal server error"}


async def fetch_microsoft_emails(oauth_record, db: Session, limit: int = 50):
    """Fetch emails from Microsoft Graph API.

    Uses validate_microsoft_token() (Check 7.15) to ensure the token is
    valid before making Graph API calls.
    """
    try:
        # Validate token before use (Check 7.15)
        validation = await validate_microsoft_token(oauth_record, db)
        if not validation.get("valid"):
            return {
                "error": validation.get("error", "Token validation failed"),
                "needs_reauth": validation.get("needs_reauth", False)
            }

        access_token = validation["access_token"]

        folder = oauth_record.sync_folder or "Inbox"
        graph_url = f"https://graph.microsoft.com/v1.0/me/mailFolders/{folder}/messages?$top={limit}&$orderby=receivedDateTime desc"

        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        }

        response = requests.get(graph_url, headers=headers)

        if response.status_code == 401:
            logger.info("Got 401 from Microsoft API, attempting token refresh...")
            refresh_result = await refresh_microsoft_token(oauth_record, db)
            if not refresh_result.get("success"):
                return {
                    "error": refresh_result.get("error", "Failed to refresh token"),
                    "needs_reauth": refresh_result.get("needs_reauth", True)
                }
            db.refresh(oauth_record)
            access_token = decrypt_token(oauth_record.access_token)
            headers["Authorization"] = f"Bearer {access_token}"
            response = requests.get(graph_url, headers=headers)

        if response.status_code == 200:
            emails_data = response.json()
            emails = emails_data.get("value", [])

            logger.info(f"Fetched {len(emails)} emails from Microsoft for user {oauth_record.user_id} (folder: {folder})")
            if len(emails) == 0:
                logger.warning(f"Microsoft API returned 0 emails for folder '{folder}'. API response keys: {list(emails_data.keys())}")

            oauth_record.last_sync_at = datetime.now(timezone.utc)
            db.commit()

            return {"emails": emails, "count": len(emails)}
        else:
            error_detail = response.text
            logger.error(f"Failed to fetch Microsoft emails: {response.status_code} - {error_detail}")
            if response.status_code == 401 or response.status_code == 403:
                return {"error": "Authentication failed", "needs_reauth": True}
            return {"error": f"Microsoft API error: {response.status_code} - {error_detail[:200]}"}

    except Exception as e:
        logger.error(f"Error fetching Microsoft emails: {e}")
        return {"error": "Internal server error"}


async def delete_microsoft_email(oauth_record, message_id: str, db: Session):
    """Move an email to trash in Microsoft 365/Outlook.

    Uses validate_microsoft_token() (Check 7.15) to ensure the token is
    valid before making Graph API calls.
    """
    try:
        # Validate token before use (Check 7.15)
        validation = await validate_microsoft_token(oauth_record, db)
        if not validation.get("valid"):
            return {
                "success": False,
                "error": validation.get("error", "Token validation failed"),
                "needs_reauth": validation.get("needs_reauth", False)
            }

        access_token = validation["access_token"]

        graph_url = f"https://graph.microsoft.com/v1.0/me/messages/{message_id}/move"

        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        }

        body = {"destinationId": "deleteditems"}

        response = requests.post(graph_url, headers=headers, json=body)

        if response.status_code == 401:
            logger.info("Got 401 from Microsoft API on delete, attempting token refresh...")
            refresh_result = await refresh_microsoft_token(oauth_record, db)
            if not refresh_result.get("success"):
                return {
                    "success": False,
                    "error": refresh_result.get("error", "Failed to refresh token"),
                    "needs_reauth": refresh_result.get("needs_reauth", True)
                }
            db.refresh(oauth_record)
            access_token = decrypt_token(oauth_record.access_token)
            headers["Authorization"] = f"Bearer {access_token}"
            response = requests.post(graph_url, headers=headers, json=body)

        if response.status_code == 200 or response.status_code == 201:
            logger.info(f"Successfully moved email {message_id} to trash for user {oauth_record.user_id}")
            return {"success": True, "message_id": message_id}
        elif response.status_code == 404:
            logger.warning(f"Email {message_id} not found - may have already been deleted")
            return {"success": True, "message_id": message_id, "note": "already_deleted"}
        else:
            error_detail = response.text
            logger.error(f"Failed to delete Microsoft email: {response.status_code} - {error_detail}")
            if response.status_code == 401 or response.status_code == 403:
                return {"success": False, "error": "Authentication failed", "needs_reauth": True}
            return {"success": False, "error": f"Microsoft API error: {response.status_code}"}

    except Exception as e:
        logger.error(f"Error deleting Microsoft email: {e}")
        return {"success": False, "error": "Internal server error"}


async def process_microsoft_email_to_dre(email_data: dict, user_id: int, db: Session):
    """Process a Microsoft Graph email and ingest into DRE"""
    _ensure_models()
    try:
        message_id = email_data.get("id", "")
        subject = email_data.get("subject", "")
        sender = email_data.get("from", {}).get("emailAddress", {}).get("address", "")
        recipients = [r.get("emailAddress", {}).get("address", "") for r in email_data.get("toRecipients", [])]
        received_at = email_data.get("receivedDateTime", "")

        if message_id:
            existing_event = db.query(IncomingDataEvent).filter(
                IncomingDataEvent.external_message_id == message_id,
                IncomingDataEvent.user_id == user_id
            ).first()

            if existing_event:
                logger.debug(f"Email {message_id} already processed (event {existing_event.id}), skipping")
                return {"status": "skipped", "reason": "already_processed", "event_id": existing_event.id}

        body = email_data.get("body", {})
        body_content = body.get("content", "")
        content_type = body.get("contentType", "text")

        if content_type == "html":
            raw_html = body_content
            try:
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(body_content, 'html.parser')
                for script in soup(["script", "style"]):
                    script.decompose()
                raw_text = soup.get_text(separator='\n', strip=True)
            except Exception as e:
                logger.exception(f"Failed to parse HTML body with BeautifulSoup: {e}")
                raw_text = re.sub(r'<[^>]+>', '', body_content)
                raw_text = raw_text.replace('&nbsp;', ' ').replace('&amp;', '&')
        else:
            raw_text = body_content
            raw_html = None

        parsed_received_at = datetime.now(timezone.utc)
        if received_at:
            try:
                parsed_received_at = datetime.fromisoformat(received_at.replace('Z', '+00:00'))
            except ValueError:
                try:
                    from email.utils import parsedate_to_datetime
                    parsed_received_at = parsedate_to_datetime(received_at)
                except Exception as e:
                    logger.exception(f"Could not parse date '{received_at}': {e}")
                    parsed_received_at = datetime.now(timezone.utc)

        db_event = IncomingDataEvent(
            source="microsoft365",
            external_message_id=message_id,
            raw_text=raw_text,
            raw_html=raw_html,
            subject=subject,
            sender=sender,
            recipients=recipients,
            received_at=parsed_received_at,
            user_id=user_id,
            processed=False
        )
        db.add(db_event)
        db.commit()
        db.refresh(db_event)

        logger.info(f"Ingested NEW Microsoft email {db_event.id} from {sender} (msg_id: {message_id[:20]}...)")

        # Queue to Email Intelligence system
        try:
            from routes.email_intelligence_routes import queue_email_for_intelligence
            intel_email_data = {
                "email_provider": "microsoft365",
                "provider_message_id": message_id,
                "thread_id": email_data.get("conversationId"),
                "from_email": sender,
                "from_name": email_data.get("from", {}).get("emailAddress", {}).get("name", ""),
                "to_emails": recipients,
                "cc_emails": [r.get("emailAddress", {}).get("address", "") for r in email_data.get("ccRecipients", [])],
                "subject": subject,
                "body_preview": raw_text[:500] if raw_text else "",
                "body_full": raw_text,
                "body_html": raw_html,
                "sent_date": email_data.get("sentDateTime"),
                "received_date": received_at,
                "has_attachments": email_data.get("hasAttachments", False),
                "direction": "inbound"
            }
            await queue_email_for_intelligence(
                db=db,
                user_id=user_id,
                email_data=intel_email_data,
                auto_analyze=True,
                source="microsoft365"
            )
            logger.debug(f"Queued email {message_id[:20]}... to Email Intelligence")
        except Exception as intel_error:
            logger.warning(f"Email Intelligence queue error: {intel_error}")

        ai_provider = os.getenv("AI_PROVIDER", "openai").lower()

        content = raw_text or raw_html or ""

        if ai_provider == "claude":
            from ai_providers.claude_parser import get_claude_parser

            logger.info(f"🤖 Using Claude parser for email {db_event.id}")

            claude_email_data = {
                "id": message_id,
                "subject": subject,
                "from_email": sender,
                "body_text": raw_text,
                "body_html": raw_html,
                "received_at": received_at
            }

            parser = get_claude_parser()
            profile_type = parser.classify_email(claude_email_data)

            logger.info(f"📧 Email classified as: {profile_type}")

            if profile_type == "unrelated":
                db_event.processed = True
                db.commit()
                logger.info(f"Skipped unrelated email (Claude): {subject[:50]}")
                return {"status": "skipped", "reason": "Email classified as unrelated to mortgage business"}

            parsed_result = await parser.parse_email(
                claude_email_data,
                profile_type,
                current_profile=None
            )

            extracted_fields = parsed_result.get('extracted_fields', {})
            confidence_scores = parsed_result.get('confidence_scores', {})

            fields = {}
            for field_name, field_value in extracted_fields.items():
                confidence = confidence_scores.get(field_name, 95) / 100.0
                fields[field_name] = {
                    "value": field_value,
                    "confidence": confidence
                }

            avg_confidence = parsed_result.get('overall_confidence', 0) / 100.0
            classification = {
                "category": profile_type,
                "subcategory": parsed_result.get('email_summary', ''),
                "confidence": avg_confidence
            }

            logger.info(f"✅ Claude extracted {len(fields)} fields with {avg_confidence*100:.1f}% confidence")
        else:
            logger.info(f"⚙️  Using legacy OpenAI parser for email {db_event.id}")
            classification = classify_email_content(content, subject)
            fields = extract_loan_fields(content, classification["category"]) if classification["category"] != "unrelated" and classification["confidence"] >= 0.3 else {}
            avg_confidence = classification["confidence"]

        if classification["category"] == "unrelated":
            db_event.processed = True
            db.commit()
            logger.info(f"Skipped unrelated email: {subject[:50]}")
            return {"status": "skipped", "reason": "Email classified as unrelated to mortgage business"}

        if not fields:
            fields = extract_loan_fields(content, classification["category"])

        if ai_provider == "claude":
            pass
        else:
            confidences = [field.get("confidence", 0.0) for field in fields.values()] if fields else []
            avg_confidence = sum(confidences) / len(confidences) if confidences else classification["confidence"]

        entity_match = match_entity(fields, db, user_id) if fields else {"entity_type": None, "entity_id": None, "confidence": 0.0}

        learned_pattern = None
        sender_domain = sender.split("@")[1] if "@" in sender else ""
        email_intent = classification.get("category", "")

        try:
            pattern_result = db.execute(text("""
                SELECT id, pattern_type, pattern_value, response_type, response_config,
                       confidence_score, auto_execute_threshold, approval_count
                FROM email_response_patterns
                WHERE user_id = :user_id
                  AND is_active = true
                  AND (
                      (pattern_type = 'sender_domain' AND pattern_value = :domain)
                      OR (pattern_type = 'sender_email' AND pattern_value = :email)
                      OR (pattern_type = 'email_intent' AND pattern_value = :intent)
                  )
                ORDER BY confidence_score DESC, approval_count DESC
                LIMIT 1
            """), {
                "user_id": user_id,
                "domain": sender_domain,
                "email": sender.lower(),
                "intent": email_intent,
            })
            row = pattern_result.fetchone()
            if row and row.confidence_score and float(row.confidence_score) >= 0.90 and row.approval_count >= 3:
                learned_pattern = {
                    "id": row.id,
                    "pattern_type": row.pattern_type,
                    "response_type": row.response_type,
                    "confidence_score": float(row.confidence_score),
                    "approval_count": row.approval_count
                }
                logger.info(f"Found learned pattern {row.id} ({row.pattern_type}={row.pattern_value}) with {row.approval_count} approvals")
        except Exception as pattern_error:
            logger.warning(f"Could not check learned patterns: {pattern_error}")

        status = "needs_review"
        auto_complete_reason = None

        if learned_pattern:
            status = "auto_approved"
            auto_complete_reason = f"Learned pattern: {learned_pattern['pattern_type']} ({learned_pattern['approval_count']} prior approvals)"
            logger.info(f"Auto-completing email based on learned pattern: {auto_complete_reason}")
        elif fields and avg_confidence > 0.85 and entity_match["confidence"] > 0.90:
            status = "auto_approved"
            auto_complete_reason = "High AI confidence with entity match"
        elif fields and avg_confidence >= 0.60 and entity_match["confidence"] >= 0.50:
            status = "pending_review"

        extracted = ExtractedData(
            event_id=db_event.id,
            category=classification["category"],
            subcategory=classification.get("subcategory"),
            fields=fields or {},
            match_entity_type=entity_match["entity_type"],
            match_entity_id=entity_match["entity_id"],
            match_confidence=entity_match["confidence"],
            ai_confidence=avg_confidence,
            status=status
        )
        db.add(extracted)
        db_event.processed = True
        db.commit()

        if status == "auto_approved":
            if apply_extracted_data(extracted, db):
                extracted.status = "applied"
                db.commit()
                logger.info(f"Auto-applied extraction from email {db_event.id} - Reason: {auto_complete_reason or 'High confidence'}")

                if learned_pattern:
                    try:
                        db.execute(text("""
                            UPDATE email_response_patterns
                            SET last_matched_at = NOW(),
                                last_approved_at = NOW()
                            WHERE id = :pattern_id
                        """), {"pattern_id": learned_pattern["id"]})
                        db.commit()
                    except Exception as update_error:
                        logger.warning(f"Could not update pattern stats: {update_error}")

        return {"status": "success", "event_id": db_event.id}

    except Exception as e:
        logger.error(f"Error processing Microsoft email: {e}")
        db.rollback()
        return {"status": "error", "error": "Internal server error"}
