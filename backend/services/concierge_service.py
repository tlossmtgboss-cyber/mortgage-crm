"""
AI 1003 Concierge Service
Conversational interface for mortgage application using Claude
"""

import os
import json
import logging
from typing import Dict, Any, List, Optional
from agents.anthropic_client import get_anthropic_client

logger = logging.getLogger(__name__)

# 1003 Application fields organized by section
APPLICATION_SCHEMA = {
    "personal": {
        "fields": [
            "first_name", "last_name", "middle_name", "suffix",
            "email", "phone", "date_of_birth", "ssn",
            # ECOA: marital_status collected for property rights only, NOT for credit decisioning
            "marital_status", "dependents_count", "dependents_ages",
            "citizenship_status"
        ],
        "required": ["first_name", "last_name", "email", "phone"]
    },
    "co_borrower": {
        "fields": [
            "has_coborrower", "co_first_name", "co_last_name",
            "co_email", "co_phone", "co_date_of_birth", "co_ssn",
            "co_relationship"
        ],
        "required": []
    },
    "property": {
        "fields": [
            "loan_purpose", "property_type", "occupancy_type",
            "property_address", "property_city", "property_state",
            "property_zip", "property_county", "purchase_price",
            "down_payment", "down_payment_percentage"
        ],
        "required": ["loan_purpose", "property_type", "occupancy_type"]
    },
    "income": {
        "fields": [
            "employment_type", "employer_name", "employer_address",
            "employer_city", "employer_state", "employer_phone",
            "job_title", "years_employed", "months_employed",
            "annual_income", "monthly_bonus", "monthly_commission",
            "other_income", "other_income_source"
        ],
        "required": ["employment_type", "employer_name", "annual_income"]
    },
    "assets": {
        "fields": [
            "checking_balance", "savings_balance",
            "investment_value", "retirement_value",
            "other_assets", "gift_funds", "gift_source"
        ],
        "required": []
    },
    "liabilities": {
        "fields": [
            "monthly_rent_mortgage", "car_payment", "student_loans",
            "credit_card_payments", "child_support", "other_debts"
        ],
        "required": []
    },
    "declarations": {
        "fields": [
            "is_us_citizen", "permanent_resident", "has_bankruptcy",
            "bankruptcy_details", "has_foreclosure", "foreclosure_details",
            "has_lawsuit", "lawsuit_details", "has_delinquent_federal_debt",
            "will_occupy_property", "has_other_properties"
        ],
        "required": []
    }
}

STAGE_ORDER = ["greeting", "personal", "property", "income", "assets", "liabilities", "declarations", "review"]

SYSTEM_PROMPT = """You are Aria, a friendly and professional AI mortgage concierge helping borrowers complete their Uniform Residential Loan Application (Form 1003).

Your role is to:
1. Have a natural conversation to gather application information
2. Ask one or two questions at a time - don't overwhelm the borrower
3. Acknowledge their answers and confirm what you understood
4. Extract structured data from their responses
5. Be empathetic and reassuring - applying for a mortgage can be stressful
6. Explain terms if the borrower seems confused
7. Allow them to skip questions they're unsure about

Current conversation stage: {current_stage}

Data already collected:
{existing_data}

Fields still needed for this stage:
{missing_fields}

Guidelines:
- Keep responses concise but warm (2-4 sentences typically)
- Use **bold** for important terms or choices
- If the borrower provides information, acknowledge it specifically
- If they seem unsure, offer to explain or let them skip
- When you have enough info for a stage, naturally transition to the next one
- Don't ask for SSN or DOB until later in the conversation (after establishing rapport)

IMPORTANT: After each response, you MUST output a JSON block with:
1. Any data you extracted from their message
2. The suggested next stage (if transitioning)
3. Whether the application seems complete

Format your response as:
[Your conversational response to the borrower]

---DATA---
{
  "extracted_data": { ... },
  "next_stage": "stage_name" or null,
  "is_complete": true/false,
  "confidence": 0.0-1.0
}"""


class ConciergeService:
    """AI Concierge for conversational mortgage applications"""

    def __init__(self):
        self.client = get_anthropic_client()
        self.model = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-20250514")

    def _get_missing_fields(self, stage: str, existing_data: Dict) -> List[str]:
        """Get fields that haven't been collected yet for a stage"""
        if stage not in APPLICATION_SCHEMA:
            return []

        schema = APPLICATION_SCHEMA[stage]
        return [f for f in schema["fields"] if f not in existing_data or not existing_data[f]]

    def _format_existing_data(self, data: Dict) -> str:
        """Format existing data for the prompt"""
        if not data:
            return "None collected yet"

        formatted = []
        for key, value in data.items():
            if value:
                # Format key nicely
                nice_key = key.replace("_", " ").title()
                formatted.append(f"- {nice_key}: {value}")

        return "\n".join(formatted) if formatted else "None collected yet"

    def _parse_ai_response(self, response: str) -> tuple:
        """Parse AI response into conversational text and data"""
        if "---DATA---" in response:
            parts = response.split("---DATA---")
            conversation = parts[0].strip()
            try:
                data_json = parts[1].strip()
                data = json.loads(data_json)
                return conversation, data
            except (json.JSONDecodeError, IndexError) as e:
                logger.warning(f"Failed to parse AI data response: {e}")
                return conversation, {}
        return response.strip(), {}

    async def process_message(
        self,
        user_message: str,
        current_stage: str,
        extracted_data: Dict[str, Any],
        conversation_history: List[Dict[str, str]],
    ) -> Dict[str, Any]:
        """Process a user message and return AI response with extracted data"""

        try:
            # Build the system prompt with context
            missing_fields = self._get_missing_fields(current_stage, extracted_data)
            system = SYSTEM_PROMPT.format(
                current_stage=current_stage,
                existing_data=self._format_existing_data(extracted_data),
                missing_fields=", ".join(missing_fields) if missing_fields else "All fields collected"
            )

            # Build messages array
            messages = []
            for msg in conversation_history[-6:]:  # Last 6 messages for context
                messages.append({
                    "role": msg["role"],
                    "content": msg["content"]
                })

            # Add current message
            messages.append({
                "role": "user",
                "content": user_message
            })

            # Call Claude
            response = self.client.messages.create(
                model=self.model,
                max_tokens=1024,
                system=system,
                messages=messages
            )

            ai_text = response.content[0].text
            conversation, data = self._parse_ai_response(ai_text)

            # Determine next stage
            next_stage = data.get("next_stage", current_stage)
            if not next_stage or next_stage not in STAGE_ORDER:
                next_stage = current_stage

            return {
                "response": conversation,
                "extracted_data": data.get("extracted_data", {}),
                "next_stage": next_stage,
                "is_complete": data.get("is_complete", False),
                "confidence": data.get("confidence", 0.8),
            }

        except Exception as e:
            logger.error(f"Error in concierge service: {e}")
            return {
                "response": "I apologize, but I'm having a bit of trouble right now. Could you please repeat what you said?",
                "extracted_data": {},
                "next_stage": current_stage,
                "is_complete": False,
                "confidence": 0.0,
                "error": "Internal server error"
            }

    def validate_extracted_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Validate and clean extracted data"""
        cleaned = {}

        for key, value in data.items():
            if value is None or value == "":
                continue

            # Clean up common formats
            if key in ["phone", "co_phone", "employer_phone"]:
                # Remove non-digits
                cleaned_phone = "".join(c for c in str(value) if c.isdigit())
                if len(cleaned_phone) == 10:
                    cleaned[key] = cleaned_phone
                elif len(cleaned_phone) == 11 and cleaned_phone.startswith("1"):
                    cleaned[key] = cleaned_phone[1:]
                else:
                    cleaned[key] = value

            elif key in ["ssn", "co_ssn"]:
                # Remove dashes/spaces, encrypt before storing
                cleaned_ssn = "".join(c for c in str(value) if c.isdigit())
                if len(cleaned_ssn) == 9:
                    from encryption_utils import encrypt_value
                    cleaned[key] = encrypt_value(cleaned_ssn)
                    # Store last 4 unencrypted for display/matching
                    cleaned[f"{key}_last4"] = cleaned_ssn[-4:]

            elif key in ["annual_income", "monthly_bonus", "monthly_commission",
                        "other_income", "purchase_price", "down_payment",
                        "checking_balance", "savings_balance", "investment_value",
                        "retirement_value", "monthly_rent_mortgage", "car_payment",
                        "student_loans", "credit_card_payments", "child_support",
                        "other_debts"]:
                # Parse currency values
                try:
                    cleaned_value = str(value).replace("$", "").replace(",", "").strip()
                    cleaned[key] = float(cleaned_value)
                except ValueError:
                    cleaned[key] = value

            elif key in ["down_payment_percentage", "years_employed", "months_employed",
                        "dependents_count"]:
                # Parse numeric values
                try:
                    cleaned[key] = int(str(value).replace("%", "").strip())
                except ValueError:
                    cleaned[key] = value

            elif key in ["email", "co_email"]:
                # Lowercase emails
                cleaned[key] = str(value).lower().strip()

            elif key in ["property_state", "employer_state"]:
                # Uppercase state codes
                cleaned[key] = str(value).upper().strip()[:2]

            elif key in ["loan_purpose"]:
                # Normalize loan purpose
                value_lower = str(value).lower()
                if "purchase" in value_lower:
                    cleaned[key] = "purchase"
                elif "refi" in value_lower and "cash" in value_lower:
                    cleaned[key] = "cash_out_refinance"
                elif "refi" in value_lower:
                    cleaned[key] = "refinance"
                elif "construction" in value_lower:
                    cleaned[key] = "construction"
                else:
                    cleaned[key] = value

            elif key in ["property_type"]:
                # Normalize property type
                value_lower = str(value).lower()
                if "single" in value_lower or "sfr" in value_lower:
                    cleaned[key] = "single_family"
                elif "condo" in value_lower:
                    cleaned[key] = "condo"
                elif "town" in value_lower:
                    cleaned[key] = "townhouse"
                elif "multi" in value_lower or "2-4" in value_lower:
                    cleaned[key] = "multi_family"
                elif "manufactured" in value_lower or "mobile" in value_lower:
                    cleaned[key] = "manufactured"
                else:
                    cleaned[key] = value

            elif key in ["occupancy_type"]:
                # Normalize occupancy
                value_lower = str(value).lower()
                if "primary" in value_lower or "live" in value_lower:
                    cleaned[key] = "primary"
                elif "second" in value_lower or "vacation" in value_lower:
                    cleaned[key] = "secondary"
                elif "invest" in value_lower or "rental" in value_lower:
                    cleaned[key] = "investment"
                else:
                    cleaned[key] = value

            elif key in ["employment_type"]:
                # Normalize employment type
                value_lower = str(value).lower()
                if "w-2" in value_lower or "w2" in value_lower or "employee" in value_lower:
                    cleaned[key] = "w2"
                elif "self" in value_lower or "own" in value_lower or "business" in value_lower:
                    cleaned[key] = "self_employed"
                elif "1099" in value_lower or "contract" in value_lower:
                    cleaned[key] = "1099"
                elif "retire" in value_lower:
                    cleaned[key] = "retired"
                else:
                    cleaned[key] = value

            else:
                # Default - just clean whitespace
                if isinstance(value, str):
                    cleaned[key] = value.strip()
                else:
                    cleaned[key] = value

        return cleaned

    def get_completion_status(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Get completion status for each section"""
        status = {}
        total_required = 0
        total_completed = 0

        for stage, schema in APPLICATION_SCHEMA.items():
            required_fields = schema["required"]
            completed = sum(1 for f in required_fields if f in data and data[f])

            status[stage] = {
                "required": len(required_fields),
                "completed": completed,
                "percentage": round((completed / len(required_fields) * 100) if required_fields else 100),
                "missing": [f for f in required_fields if f not in data or not data[f]]
            }

            total_required += len(required_fields)
            total_completed += completed

        status["overall"] = {
            "total_required": total_required,
            "total_completed": total_completed,
            "percentage": round((total_completed / total_required * 100) if total_required else 100)
        }

        return status


# Singleton instance
concierge_service = ConciergeService()
