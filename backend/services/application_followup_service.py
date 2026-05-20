"""
Application Follow-up Questions Service

Generates AI-powered follow-up questions based on applicant answers
to gather additional details for complex situations.
"""

import os
import json
import logging
from typing import Dict, List, Optional, Any
from anthropic import Anthropic

logger = logging.getLogger(__name__)

# Complex situation triggers and their follow-up contexts
COMPLEX_TRIGGERS = {
    "self_employed": {
        "trigger_values": ["yes", "self_employed", "business_owner", "side_business"],
        "context": "self-employment income",
        "needed_info": ["business type", "years in business", "ownership percentage", "business structure (LLC, S-Corp, etc.)"],
    },
    "gift_funds": {
        "trigger_values": ["yes", True],
        "context": "gift funds for down payment",
        "needed_info": ["donor relationship", "gift amount", "whether donor lives with applicant"],
    },
    "bankruptcy": {
        "trigger_values": ["yes", True],
        "context": "bankruptcy history",
        "needed_info": ["type of bankruptcy (Chapter 7, 13)", "discharge date", "any outstanding judgments"],
    },
    "foreclosure": {
        "trigger_values": ["yes", True],
        "context": "foreclosure history",
        "needed_info": ["when it occurred", "circumstances", "any deficiency balance"],
    },
    "multiple_properties": {
        "trigger_values": ["yes", True, "2", "3", "4", "5+"],
        "context": "owning multiple properties",
        "needed_info": ["number of properties", "rental income", "how properties are financed"],
    },
    "non_traditional_income": {
        "trigger_values": ["commission", "bonus", "overtime", "rental", "investment", "retirement", "social_security", "alimony", "child_support"],
        "context": "non-traditional income sources",
        "needed_info": ["income consistency", "how long receiving", "documentation available"],
    },
    "job_gap": {
        "trigger_values": ["less_than_2_years", "gap", "recently_started"],
        "context": "employment history gap or recent job change",
        "needed_info": ["reason for gap", "previous employment", "current job stability"],
    },
    "co_borrower": {
        "trigger_values": ["yes", True, "2"],
        "context": "having a co-borrower",
        "needed_info": ["co-borrower relationship", "whether they will occupy the property", "their employment status"],
    },
    "investment_property": {
        "trigger_values": ["investment", "rental", "non_owner_occupied"],
        "context": "investment/rental property purchase",
        "needed_info": ["investment experience", "expected rental income", "property management plans"],
    },
    "large_deposit": {
        "trigger_values": ["yes", True],
        "context": "large recent deposits",
        "needed_info": ["source of deposit", "amount", "documentation available"],
    },
}


class ApplicationFollowupService:
    """Service for generating AI-powered follow-up questions."""

    def __init__(self):
        self.client = None
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if api_key:
            self.client = Anthropic(api_key=api_key)

    def check_triggers(
        self,
        field_name: str,
        field_value: Any,
        all_answers: Optional[Dict[str, Any]] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Check if a field value triggers follow-up questions.

        Returns trigger info if follow-up is needed, None otherwise.
        """
        if field_value is None:
            return None

        # Normalize value for comparison
        value_str = str(field_value).lower().strip()

        # Check each trigger
        for trigger_key, trigger_config in COMPLEX_TRIGGERS.items():
            # Check if field name matches trigger
            if trigger_key in field_name.lower() or field_name.lower() in trigger_key:
                # Check if value matches trigger values
                for trigger_val in trigger_config["trigger_values"]:
                    if str(trigger_val).lower() == value_str or value_str in str(trigger_val).lower():
                        return {
                            "trigger": trigger_key,
                            "context": trigger_config["context"],
                            "needed_info": trigger_config["needed_info"],
                            "field_name": field_name,
                            "field_value": field_value,
                        }

        # Special case: check for specific field patterns
        if "income" in field_name.lower() and "type" in field_name.lower():
            for trigger_val in COMPLEX_TRIGGERS["non_traditional_income"]["trigger_values"]:
                if trigger_val in value_str:
                    return {
                        "trigger": "non_traditional_income",
                        "context": COMPLEX_TRIGGERS["non_traditional_income"]["context"],
                        "needed_info": COMPLEX_TRIGGERS["non_traditional_income"]["needed_info"],
                        "field_name": field_name,
                        "field_value": field_value,
                    }

        return None

    def generate_followup_questions(
        self,
        trigger_info: Dict[str, Any],
        application_type: str = "purchase",
        existing_answers: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        Generate follow-up questions for a triggered complex situation.

        Returns a list of question objects with id, question, type, and options.
        """
        if not self.client:
            # Fallback to template-based questions if no AI
            return self._get_template_questions(trigger_info)

        try:
            prompt = f"""You are a helpful mortgage application assistant. The applicant just indicated they have {trigger_info['context']}.

Generate 2-3 brief, friendly follow-up questions to gather the necessary information for their mortgage application. Keep questions conversational and non-intimidating.

Information we need to gather:
{json.dumps(trigger_info['needed_info'], indent=2)}

Application type: {application_type}
Their answer: {trigger_info['field_name']} = {trigger_info['field_value']}

Return a JSON array of questions in this format:
[
  {{
    "id": "unique_id",
    "question": "The question text",
    "type": "text" | "select" | "radio",
    "options": ["option1", "option2"] // only for select/radio types
  }}
]

Keep questions brief (under 100 characters). Be warm and helpful in tone."""

            from services.llm_gateway import llm_gateway
            llm_result = llm_gateway.complete_sync(
                intent="onboarding",
                system_prompt="You generate follow-up questions for mortgage applications. Return valid JSON arrays.",
                messages=[{"role": "user", "content": prompt}],
                max_tokens_override=500,
            )

            content = llm_result.text

            # Extract JSON from response
            import re
            json_match = re.search(r'\[.*\]', content, re.DOTALL)
            if json_match:
                questions = json.loads(json_match.group())
                # Add trigger context to each question
                for q in questions:
                    q["trigger"] = trigger_info["trigger"]
                    q["context"] = trigger_info["context"]
                return questions

        except Exception as e:
            logger.warning(f"AI question generation failed: {e}, using templates")

        # Fallback to templates
        return self._get_template_questions(trigger_info)

    def _get_template_questions(self, trigger_info: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Get template-based follow-up questions when AI is unavailable."""

        trigger = trigger_info["trigger"]

        templates = {
            "self_employed": [
                {
                    "id": "business_type",
                    "question": "What type of business do you own or operate?",
                    "type": "text",
                    "placeholder": "e.g., Consulting, Retail, Construction"
                },
                {
                    "id": "years_in_business",
                    "question": "How many years have you been in this business?",
                    "type": "select",
                    "options": ["Less than 1 year", "1-2 years", "2-5 years", "5+ years"]
                },
                {
                    "id": "ownership_percentage",
                    "question": "What percentage of the business do you own?",
                    "type": "select",
                    "options": ["Less than 25%", "25-50%", "51-99%", "100%"]
                },
            ],
            "gift_funds": [
                {
                    "id": "donor_relationship",
                    "question": "What is your relationship to the gift donor?",
                    "type": "select",
                    "options": ["Parent", "Grandparent", "Sibling", "Other family member", "Domestic partner"]
                },
                {
                    "id": "gift_amount",
                    "question": "Approximately how much is the gift amount?",
                    "type": "text",
                    "placeholder": "e.g., $25,000"
                },
            ],
            "bankruptcy": [
                {
                    "id": "bankruptcy_type",
                    "question": "What type of bankruptcy was filed?",
                    "type": "select",
                    "options": ["Chapter 7", "Chapter 13", "Chapter 11", "Not sure"]
                },
                {
                    "id": "bankruptcy_discharge_date",
                    "question": "When was the bankruptcy discharged?",
                    "type": "text",
                    "placeholder": "e.g., March 2020"
                },
            ],
            "foreclosure": [
                {
                    "id": "foreclosure_date",
                    "question": "When did the foreclosure occur?",
                    "type": "text",
                    "placeholder": "e.g., 2019"
                },
                {
                    "id": "foreclosure_circumstances",
                    "question": "What were the circumstances?",
                    "type": "select",
                    "options": ["Job loss", "Medical issues", "Divorce", "Market conditions", "Other"]
                },
            ],
            "multiple_properties": [
                {
                    "id": "property_count",
                    "question": "How many properties do you currently own?",
                    "type": "select",
                    "options": ["2", "3", "4", "5 or more"]
                },
                {
                    "id": "rental_properties",
                    "question": "Are any of these rental properties?",
                    "type": "radio",
                    "options": ["Yes", "No"]
                },
            ],
            "non_traditional_income": [
                {
                    "id": "income_duration",
                    "question": "How long have you been receiving this income?",
                    "type": "select",
                    "options": ["Less than 1 year", "1-2 years", "2+ years"]
                },
                {
                    "id": "income_consistency",
                    "question": "Is this income consistent each month/year?",
                    "type": "radio",
                    "options": ["Yes, very consistent", "Somewhat variable", "Highly variable"]
                },
            ],
            "job_gap": [
                {
                    "id": "gap_reason",
                    "question": "What was the reason for the employment gap?",
                    "type": "select",
                    "options": ["Education/Training", "Family care", "Medical leave", "Career transition", "Other"]
                },
                {
                    "id": "current_job_stability",
                    "question": "Is your current position permanent?",
                    "type": "radio",
                    "options": ["Yes, permanent", "Contract/Temporary", "Probationary period"]
                },
            ],
            "co_borrower": [
                {
                    "id": "coborrower_relationship",
                    "question": "What is your relationship to the co-borrower?",
                    "type": "select",
                    "options": ["Spouse", "Domestic partner", "Parent", "Sibling", "Other"]
                },
                {
                    "id": "coborrower_occupancy",
                    "question": "Will the co-borrower live in the property?",
                    "type": "radio",
                    "options": ["Yes", "No"]
                },
            ],
            "investment_property": [
                {
                    "id": "investment_experience",
                    "question": "Have you owned rental properties before?",
                    "type": "radio",
                    "options": ["Yes", "No, this is my first"]
                },
                {
                    "id": "expected_rent",
                    "question": "What's the expected monthly rent?",
                    "type": "text",
                    "placeholder": "e.g., $2,500"
                },
            ],
            "large_deposit": [
                {
                    "id": "deposit_source",
                    "question": "What was the source of this deposit?",
                    "type": "select",
                    "options": ["Sale of asset", "Gift", "Bonus/Commission", "Tax refund", "Other"]
                },
                {
                    "id": "deposit_amount",
                    "question": "What was the approximate deposit amount?",
                    "type": "text",
                    "placeholder": "e.g., $10,000"
                },
            ],
        }

        questions = templates.get(trigger, [])

        # Add trigger context to each question
        for q in questions:
            q["trigger"] = trigger
            q["context"] = trigger_info.get("context", "")

        return questions

    def get_all_triggers(self) -> Dict[str, Dict[str, Any]]:
        """Return all available triggers and their configurations."""
        return COMPLEX_TRIGGERS


# Singleton instance
application_followup_service = ApplicationFollowupService()
