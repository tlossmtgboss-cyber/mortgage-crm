"""
DRE Email Classifier — AI-powered email classification and field extraction.

Functions:
    classify_email_content  — Classify email category via OpenAI
    extract_loan_fields     — Extract structured fields from email text
    extract_borrower_from_subject — Regex fallback for borrower name in subject
    classify_email_intent   — Determine email intent from keywords
    generate_recommended_action — Suggest CRM action based on intent
"""
import re
import json
import logging
from typing import Dict, Any, Optional

from services.dre._base import get_openai_client

logger = logging.getLogger(__name__)


def classify_email_content(content: str, subject: str) -> Dict[str, Any]:
    """Use AI to classify email content and determine category"""
    _openai_client = get_openai_client()

    if not _openai_client:
        logger.warning("OpenAI client not initialized - using fallback classification")
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
                    "content": f"Subject: {subject}\n\nContent: {content[:1000]}"
                }
            ],
            response_format={"type": "json_object"},
            temperature=0.3
        )

        result = json.loads(response.choices[0].message.content)
        return result
    except Exception as e:
        logger.error(f"Email classification error: {e}")
        return {"category": "loan_update", "subcategory": "error", "confidence": 0.3}


def extract_loan_fields(content: str, category: str) -> Dict[str, Dict[str, Any]]:
    """Extract structured loan fields from email content"""
    _openai_client = get_openai_client()

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
                    "content": content[:3000]
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
