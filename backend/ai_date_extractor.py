"""
AI Date Extractor
Extracts important dates from email content and triggers tasks based on those dates
"""
import os
import json
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional
import logging
from openai import OpenAI

logger = logging.getLogger(__name__)

# Initialize OpenAI client
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
openai_client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None


# Important date categories for each process
LEAD_DATE_CATEGORIES = {
    "first_contact_date": {
        "label": "First Contact Date",
        "description": "Date of initial contact with lead",
        "creates_task": False
    },
    "application_started_date": {
        "label": "Application Started",
        "description": "Date borrower started application",
        "creates_task": True,
        "task_template": "Follow up on application completion"
    },
    "application_submitted_date": {
        "label": "Application Submitted",
        "description": "Date application was submitted",
        "creates_task": True,
        "task_template": "Review submitted application"
    },
    "credit_pull_date": {
        "label": "Credit Pulled",
        "description": "Date credit report was pulled",
        "creates_task": False
    },
    "pre_approval_date": {
        "label": "Pre-Approval Issued",
        "description": "Date pre-approval letter was issued",
        "creates_task": True,
        "task_template": "Send pre-approval letter to borrower"
    },
    "pre_approval_expiration": {
        "label": "Pre-Approval Expiration",
        "description": "Date pre-approval expires",
        "creates_task": True,
        "task_template": "Renew pre-approval before expiration",
        "task_days_before": 7
    },
    "expected_closing_date": {
        "label": "Expected Closing Date",
        "description": "Expected date for loan closing",
        "creates_task": False
    }
}

LOAN_DATE_CATEGORIES = {
    "application_date": {
        "label": "Application Date",
        "description": "Official application date",
        "creates_task": False
    },
    "initial_disclosure_date": {
        "label": "Initial Disclosure",
        "description": "Date initial disclosures sent",
        "creates_task": True,
        "task_template": "Confirm borrower received disclosures"
    },
    "lock_date": {
        "label": "Rate Lock Date",
        "description": "Date interest rate was locked",
        "creates_task": True,
        "task_template": "Send rate lock confirmation"
    },
    "lock_expiration_date": {
        "label": "Lock Expiration",
        "description": "Date rate lock expires",
        "creates_task": True,
        "task_template": "Extend rate lock or close before expiration",
        "task_days_before": 10
    },
    "appraisal_ordered_date": {
        "label": "Appraisal Ordered",
        "description": "Date appraisal was ordered",
        "creates_task": True,
        "task_template": "Schedule appraisal inspection"
    },
    "appraisal_scheduled_date": {
        "label": "Appraisal Scheduled",
        "description": "Date appraisal inspection scheduled",
        "creates_task": True,
        "task_template": "Remind borrower of appraisal appointment"
    },
    "appraisal_completed_date": {
        "label": "Appraisal Completed",
        "description": "Date appraisal was completed",
        "creates_task": True,
        "task_template": "Review appraisal report"
    },
    "title_ordered_date": {
        "label": "Title Ordered",
        "description": "Date title search ordered",
        "creates_task": False
    },
    "hoi_ordered_date": {
        "label": "Homeowners Insurance Ordered",
        "description": "Date HOI was ordered/confirmed",
        "creates_task": True,
        "task_template": "Confirm HOI binder received"
    },
    "uw_submission_date": {
        "label": "Submitted to Underwriting",
        "description": "Date file submitted to underwriter",
        "creates_task": True,
        "task_template": "Follow up on underwriting review"
    },
    "approval_date": {
        "label": "Approval Date",
        "description": "Date loan was approved",
        "creates_task": True,
        "task_template": "Send approval notification to borrower"
    },
    "ctc_date": {
        "label": "Clear to Close",
        "description": "Date loan cleared to close",
        "creates_task": True,
        "task_template": "Schedule closing appointment"
    },
    "closing_date": {
        "label": "Closing Date",
        "description": "Scheduled closing date",
        "creates_task": True,
        "task_template": "Send closing reminder and checklist",
        "task_days_before": 3
    },
    "funding_date": {
        "label": "Funding Date",
        "description": "Date loan funds disbursed",
        "creates_task": True,
        "task_template": "Send welcome package and thank you"
    },
    "first_payment_due": {
        "label": "First Payment Due",
        "description": "Date of first mortgage payment",
        "creates_task": True,
        "task_template": "Remind borrower of first payment date",
        "task_days_before": 7
    }
}

MUM_DATE_CATEGORIES = {
    "original_close_date": {
        "label": "Original Close Date",
        "description": "Date original loan closed",
        "creates_task": False
    },
    "last_contact_date": {
        "label": "Last Contact",
        "description": "Date of last contact with client",
        "creates_task": False
    },
    "next_review_date": {
        "label": "Next Review Date",
        "description": "Scheduled next review date",
        "creates_task": True,
        "task_template": "Conduct portfolio review call"
    },
    "rate_watch_date": {
        "label": "Rate Watch Alert",
        "description": "Date to check rates for refinance opportunity",
        "creates_task": True,
        "task_template": "Check current rates vs client's rate"
    },
    "annual_review_date": {
        "label": "Annual Review",
        "description": "Annual portfolio review date",
        "creates_task": True,
        "task_template": "Schedule annual review call"
    },
    "referral_request_date": {
        "label": "Referral Request",
        "description": "Date to ask for referrals",
        "creates_task": True,
        "task_template": "Request referrals from satisfied client"
    }
}


def extract_dates_from_email(email_content: str, subject: str, process_type: str = "lead") -> Dict[str, any]:
    """
    Use AI to extract important dates from email content

    Args:
        email_content: Email body text
        subject: Email subject line
        process_type: "lead", "loan", or "mum"

    Returns:
        Dictionary of extracted dates with metadata
    """
    if not openai_client:
        logger.warning("OpenAI API not configured - cannot extract dates")
        return {}

    # Select appropriate date categories
    if process_type == "lead":
        categories = LEAD_DATE_CATEGORIES
    elif process_type == "loan":
        categories = LOAN_DATE_CATEGORIES
    elif process_type == "mum":
        categories = MUM_DATE_CATEGORIES
    else:
        logger.error(f"Invalid process_type: {process_type}")
        return {}

    # Build category descriptions for AI
    category_descriptions = "\n".join([
        f"- {key}: {info['description']}"
        for key, info in categories.items()
    ])

    system_prompt = f"""You are an AI that extracts important dates from mortgage-related emails.

Extract dates mentioned in the email and categorize them. Only extract dates that are explicitly mentioned or clearly implied.

Date Categories for {process_type.upper()} process:
{category_descriptions}

Return a JSON object with this structure:
{{
  "extracted_dates": {{
    "category_key": {{
      "date": "YYYY-MM-DD",
      "confidence": 0.0-1.0,
      "source_text": "exact text from email mentioning this date"
    }}
  }}
}}

Rules:
- Only include dates that are clearly mentioned or strongly implied
- Use ISO 8601 date format (YYYY-MM-DD)
- Confidence: 1.0 = explicit date, 0.7-0.9 = implied/estimated, <0.7 = uncertain
- If no relevant dates found, return empty extracted_dates object
- Parse relative dates like "next Tuesday" or "in 2 weeks" into actual dates
"""

    user_message = f"""Email Subject: {subject}

Email Content:
{email_content[:2000]}  # Limit to first 2000 chars

Extract all relevant dates and categorize them."""

    try:
        response = openai_client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message}
            ],
            temperature=0.3,
            response_format={"type": "json_object"}
        )

        result = json.loads(response.choices[0].message.content)
        extracted_dates = result.get("extracted_dates", {})

        # Add metadata from category definitions
        for key, date_info in extracted_dates.items():
            if key in categories:
                date_info["label"] = categories[key]["label"]
                date_info["creates_task"] = categories[key].get("creates_task", False)
                if "task_template" in categories[key]:
                    date_info["task_template"] = categories[key]["task_template"]
                if "task_days_before" in categories[key]:
                    date_info["task_days_before"] = categories[key]["task_days_before"]

        logger.info(f"Extracted {len(extracted_dates)} dates from email")
        return extracted_dates

    except Exception as e:
        logger.error(f"Error extracting dates from email: {e}")
        return {}


def merge_dates(existing_dates: Optional[Dict], new_dates: Dict) -> Dict:
    """
    Merge new extracted dates with existing dates

    Args:
        existing_dates: Current important_dates from database
        new_dates: Newly extracted dates

    Returns:
        Merged dates dictionary
    """
    if not existing_dates:
        existing_dates = {}

    for key, new_date_info in new_dates.items():
        # Only update if new date has higher confidence or existing doesn't exist
        if key not in existing_dates:
            existing_dates[key] = new_date_info
        else:
            existing_confidence = existing_dates[key].get("confidence", 0)
            new_confidence = new_date_info.get("confidence", 0)

            if new_confidence > existing_confidence:
                # Keep higher confidence date
                existing_dates[key] = new_date_info
                logger.info(f"Updated {key} with higher confidence date")

    return existing_dates


def get_upcoming_task_triggers(important_dates: Dict, current_date: datetime = None) -> List[Dict]:
    """
    Get list of tasks that should be created based on important dates

    Args:
        important_dates: Dictionary of important dates
        current_date: Current date (for testing), defaults to now

    Returns:
        List of task triggers with metadata
    """
    if current_date is None:
        current_date = datetime.now(timezone.utc)

    task_triggers = []

    for key, date_info in important_dates.items():
        if not date_info.get("creates_task", False):
            continue

        if "task_template" not in date_info:
            continue

        # Parse the date
        try:
            date_str = date_info.get("date")
            if not date_str:
                continue

            target_date = datetime.fromisoformat(date_str.replace("Z", "+00:00"))

            # Check if we need to create task
            days_before = date_info.get("task_days_before", 0)
            trigger_date = target_date - timedelta(days=days_before)

            # Create task if trigger date is today or in the past and not already created
            if trigger_date.date() <= current_date.date():
                if not date_info.get("task_created", False):
                    task_triggers.append({
                        "date_key": key,
                        "label": date_info.get("label", key),
                        "task_title": date_info.get("task_template"),
                        "due_date": target_date,
                        "confidence": date_info.get("confidence", 1.0)
                    })

        except Exception as e:
            logger.error(f"Error processing date trigger for {key}: {e}")
            continue

    return task_triggers
