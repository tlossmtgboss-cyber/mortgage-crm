"""
Voice Slot Extractor Service

Uses Claude AI to extract structured slot data from voice transcripts.
Handles intent detection, fuzzy name matching, and ambiguity resolution.
"""
import os
import json
import logging
from typing import Optional, List, Dict, Any
from anthropic import Anthropic

from models.voice_workflow_models import (
    UserIntent,
    SlotExtractionResult,
    PreApprovalWorkflowState,
    WorkflowType,
)

logger = logging.getLogger(__name__)


class VoiceSlotExtractor:
    """Extract structured slots from voice transcripts using Claude"""

    def __init__(self):
        self.client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        self.model = "claude-sonnet-4-6"

    async def extract_slots(
        self,
        transcript: str,
        workflow_type: WorkflowType,
        current_state: str,
        current_slots: Dict[str, Any],
        available_options: Optional[List[Dict[str, Any]]] = None,
    ) -> SlotExtractionResult:
        """
        Extract slots and intent from a user's voice transcript.

        Args:
            transcript: The transcribed user speech
            workflow_type: The type of workflow being executed
            current_state: Current state in the workflow state machine
            current_slots: Already collected slot values
            available_options: List of options user can select from (for matching)

        Returns:
            SlotExtractionResult with intent, confidence, and extracted slots
        """
        try:
            # Build the extraction prompt based on workflow type and state
            system_prompt = self._build_system_prompt(workflow_type)
            user_prompt = self._build_user_prompt(
                transcript=transcript,
                current_state=current_state,
                current_slots=current_slots,
                available_options=available_options,
            )

            response = self.client.messages.create(
                model=self.model,
                max_tokens=1024,
                system=system_prompt,
                messages=[{"role": "user", "content": user_prompt}],
            )

            # Parse the JSON response
            response_text = response.content[0].text
            result = self._parse_extraction_response(response_text, available_options)

            logger.info(f"Slot extraction result: intent={result.intent}, slots={result.extracted_slots}")
            return result

        except Exception as e:
            logger.error(f"Slot extraction error: {e}")
            # Return a neutral result on error
            return SlotExtractionResult(
                intent=UserIntent.HELP,
                confidence=0.3,
                needs_clarification=True,
                clarification_question="I didn't quite catch that. Could you repeat what you said?",
            )

    def _build_system_prompt(self, workflow_type: WorkflowType) -> str:
        """Build system prompt for slot extraction"""
        return f"""You are a voice assistant helping a loan officer complete tasks.
Your job is to extract the user's intent and any slot values from their speech.

Current workflow: {workflow_type.value}

You must respond with valid JSON in this exact format:
{{
    "intent": "select|modify|confirm|cancel|skip|help|repeat|go_back",
    "confidence": 0.0-1.0,
    "extracted_slots": {{}},
    "needs_clarification": false,
    "clarification_question": null,
    "matched_option_index": null
}}

Intent definitions:
- "select": User is choosing an option (by name, number, or description)
- "modify": User wants to change a value (amount, address, etc.)
- "confirm": User is saying yes, correct, that's right, send it, etc.
- "cancel": User wants to stop/cancel the workflow
- "skip": User wants to skip the current optional step
- "help": User is confused or asking for help
- "repeat": User wants to hear options again
- "go_back": User wants to return to a previous step

For option matching:
- Match user's speech to available options using fuzzy matching
- Accept first names, last names, partial matches, or position numbers
- Set matched_option_index to the 0-based index of the matched option

For slot extraction:
- Extract specific values like names, amounts, addresses
- For amounts, normalize to numbers (e.g., "four fifty" -> 450000, "475 thousand" -> 475000)
- For addresses, extract as complete as possible

Always respond with valid JSON only, no markdown or explanation."""

    def _build_user_prompt(
        self,
        transcript: str,
        current_state: str,
        current_slots: Dict[str, Any],
        available_options: Optional[List[Dict[str, Any]]] = None,
    ) -> str:
        """Build user prompt with context"""
        prompt_parts = [
            f"Current state: {current_state}",
            f"User said: \"{transcript}\"",
        ]

        if current_slots:
            prompt_parts.append(f"Already collected: {json.dumps(current_slots)}")

        if available_options:
            options_text = "\n".join([
                f"{i+1}. {opt.get('name', opt.get('voice_description', str(opt)))}"
                for i, opt in enumerate(available_options)
            ])
            prompt_parts.append(f"Available options:\n{options_text}")

        # Add state-specific instructions
        state_instructions = self._get_state_instructions(current_state)
        if state_instructions:
            prompt_parts.append(f"Context: {state_instructions}")

        return "\n\n".join(prompt_parts)

    def _get_state_instructions(self, current_state: str) -> str:
        """Get state-specific extraction instructions"""
        instructions = {
            PreApprovalWorkflowState.SELECT_APPLICANT.value: (
                "User is selecting an applicant. Match to available options by name. "
                "Accept first name, last name, or full name matches."
            ),
            PreApprovalWorkflowState.REVIEW_TERMS.value: (
                "User is reviewing loan terms. They may confirm, request changes to "
                "amount/rate, or ask questions. Extract any modified values."
            ),
            PreApprovalWorkflowState.ADD_PROPERTY.value: (
                "User is being asked about adding a property address. They may say yes/no, "
                "skip, or provide an address directly."
            ),
            PreApprovalWorkflowState.SELECT_REALTOR.value: (
                "User is selecting a realtor. Match to available options or extract "
                "a new realtor name/email if provided."
            ),
            PreApprovalWorkflowState.FINAL_CONFIRMATION.value: (
                "User is confirming final details. Listen for yes/no, confirm/cancel, "
                "or last-minute changes."
            ),
        }
        return instructions.get(current_state, "")

    def _parse_extraction_response(
        self,
        response_text: str,
        available_options: Optional[List[Dict[str, Any]]] = None,
    ) -> SlotExtractionResult:
        """Parse Claude's JSON response into SlotExtractionResult"""
        try:
            # Try to extract JSON from response
            # Handle cases where Claude might wrap in markdown
            text = response_text.strip()
            if text.startswith("```"):
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
            text = text.strip()

            data = json.loads(text)

            return SlotExtractionResult(
                intent=UserIntent(data.get("intent", "help")),
                confidence=float(data.get("confidence", 0.5)),
                extracted_slots=data.get("extracted_slots", {}),
                needs_clarification=data.get("needs_clarification", False),
                clarification_question=data.get("clarification_question"),
                matched_option_index=data.get("matched_option_index"),
            )

        except json.JSONDecodeError as e:
            logger.warning(f"JSON parse error: {e}, response: {response_text[:200]}")
            return SlotExtractionResult(
                intent=UserIntent.HELP,
                confidence=0.3,
                needs_clarification=True,
                clarification_question="I'm having trouble understanding. Could you try again?",
            )
        except ValueError as e:
            logger.warning(f"Value error parsing response: {e}")
            return SlotExtractionResult(
                intent=UserIntent.HELP,
                confidence=0.3,
                needs_clarification=True,
                clarification_question="I didn't understand that. Could you say it differently?",
            )

    async def match_option_by_name(
        self,
        user_input: str,
        options: List[Dict[str, Any]],
        name_key: str = "name",
    ) -> Optional[int]:
        """
        Quick fuzzy match of user input to available options.
        Returns the index of the best match, or None if no match.
        """
        user_lower = user_input.lower().strip()

        # First, try exact matches
        for i, opt in enumerate(options):
            opt_name = opt.get(name_key, "").lower()
            if opt_name == user_lower:
                return i

        # Try first name match
        for i, opt in enumerate(options):
            opt_name = opt.get(name_key, "").lower()
            first_name = opt_name.split()[0] if opt_name else ""
            if first_name and first_name in user_lower:
                return i

        # Try last name match
        for i, opt in enumerate(options):
            opt_name = opt.get(name_key, "").lower()
            parts = opt_name.split()
            last_name = parts[-1] if parts else ""
            if last_name and last_name in user_lower:
                return i

        # Try number match ("the first one", "number 2", etc.)
        number_words = {
            "first": 0, "one": 0, "1": 0,
            "second": 1, "two": 1, "2": 1,
            "third": 2, "three": 2, "3": 2,
            "fourth": 3, "four": 3, "4": 3,
            "fifth": 4, "five": 4, "5": 4,
        }
        for word, idx in number_words.items():
            if word in user_lower and idx < len(options):
                return idx

        return None

    async def extract_amount_modification(self, transcript: str) -> Optional[float]:
        """Extract a modified amount from user speech"""
        # Quick extraction for common amount patterns
        import re

        # Handle "change to X" or "make it X"
        amount_patterns = [
            r"(?:change|make|set).+?(?:to|at)\s*\$?([\d,]+(?:,\d{3})*(?:\.\d{2})?)\s*(?:thousand|k)?",
            r"\$?([\d,]+(?:,\d{3})*(?:\.\d{2})?)\s*(?:thousand|k)?",
        ]

        for pattern in amount_patterns:
            match = re.search(pattern, transcript.lower())
            if match:
                amount_str = match.group(1).replace(",", "")
                try:
                    amount = float(amount_str)
                    # Handle "thousand" or "k"
                    if "thousand" in transcript.lower() or " k" in transcript.lower():
                        if amount < 1000:  # e.g., "475 thousand"
                            amount *= 1000
                    elif amount < 10000:  # Likely a shorthand like "475" for $475,000
                        amount *= 1000
                    return amount
                except ValueError:
                    pass

        return None

    async def extract_address(self, transcript: str) -> Optional[Dict[str, str]]:
        """Extract address components from user speech"""
        # Use Claude for complex address extraction
        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=256,
                system="""Extract address components from the user's speech.
Respond with JSON only:
{
    "street": "123 Oak Street",
    "city": "Springfield",
    "state": "IL",
    "zip": "62701"
}
Include only fields that are clearly mentioned. Use null for missing fields.""",
                messages=[{"role": "user", "content": f"User said: \"{transcript}\""}],
            )

            text = response.content[0].text.strip()
            if text.startswith("```"):
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
            text = text.strip()

            data = json.loads(text)
            # Filter out null values
            return {k: v for k, v in data.items() if v is not None}

        except Exception as e:
            logger.warning(f"Address extraction error: {e}")
            return None


# Singleton instance
_slot_extractor: Optional[VoiceSlotExtractor] = None


def get_slot_extractor() -> VoiceSlotExtractor:
    """Get or create the slot extractor singleton"""
    global _slot_extractor
    if _slot_extractor is None:
        _slot_extractor = VoiceSlotExtractor()
    return _slot_extractor
