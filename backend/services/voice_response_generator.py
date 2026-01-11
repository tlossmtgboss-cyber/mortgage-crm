"""
Voice Response Generator Service

Generates voice-optimized responses for the conversational AI workflow.
Responses are designed to be natural and concise for TTS output.
"""
import os
import logging
import aiohttp
import base64
from typing import Optional, List, Dict, Any

from models.voice_workflow_models import (
    WorkflowType,
    PreApprovalWorkflowState,
    VoiceResponseContext,
    ApplicantVoiceContext,
    RealtorVoiceContext,
)

logger = logging.getLogger(__name__)


class VoiceResponseGenerator:
    """Generate voice-optimized responses and convert to audio"""

    def __init__(self):
        self.elevenlabs_api_key = os.getenv("ELEVENLABS_API_KEY")
        self.voice_id = os.getenv("ELEVENLABS_VOICE_ID", "21m00Tcm4TlvDq8ikWAM")  # Default voice
        self.model_id = "eleven_turbo_v2"

    async def generate_response(
        self,
        workflow_type: WorkflowType,
        current_state: str,
        slots: Dict[str, Any],
        available_options: Optional[List[Dict[str, Any]]] = None,
        error_message: Optional[str] = None,
    ) -> str:
        """
        Generate a voice-friendly text response based on workflow state.

        Args:
            workflow_type: The type of workflow
            current_state: Current state in the workflow
            slots: Collected slot values
            available_options: Available options for selection states
            error_message: Error message to include if any

        Returns:
            Voice-friendly text response
        """
        if workflow_type == WorkflowType.PRE_APPROVAL_LETTER:
            return self._generate_pre_approval_response(
                current_state, slots, available_options, error_message
            )
        else:
            return "I'm not sure how to help with that workflow yet."

    def _generate_pre_approval_response(
        self,
        current_state: str,
        slots: Dict[str, Any],
        available_options: Optional[List[Dict[str, Any]]] = None,
        error_message: Optional[str] = None,
    ) -> str:
        """Generate response for pre-approval letter workflow"""

        # Handle error first
        if error_message:
            return f"I ran into an issue. {error_message} Would you like to try again?"

        # Intent detected - starting the workflow
        if current_state == PreApprovalWorkflowState.INTENT_DETECTED.value:
            return "I'll help you send a pre-approval letter. Let me find your active applicants."

        # Select applicant state
        if current_state == PreApprovalWorkflowState.SELECT_APPLICANT.value:
            return self._generate_select_applicant_response(available_options)

        # Review terms state
        if current_state == PreApprovalWorkflowState.REVIEW_TERMS.value:
            return self._generate_review_terms_response(slots)

        # Add property state
        if current_state == PreApprovalWorkflowState.ADD_PROPERTY.value:
            return "Would you like to add a property address to the letter?"

        # Select realtor state
        if current_state == PreApprovalWorkflowState.SELECT_REALTOR.value:
            return self._generate_select_realtor_response(available_options)

        # Final confirmation state
        if current_state == PreApprovalWorkflowState.FINAL_CONFIRMATION.value:
            return self._generate_final_confirmation_response(slots)

        # Executing state
        if current_state == PreApprovalWorkflowState.EXECUTING.value:
            return "Generating and sending the pre-approval letter now..."

        # Completed state
        if current_state == PreApprovalWorkflowState.COMPLETED.value:
            realtor_name = slots.get("realtor_name", "the realtor")
            return f"Done! The pre-approval letter has been sent to {realtor_name}."

        # Cancelled state
        if current_state == PreApprovalWorkflowState.CANCELLED.value:
            return "Pre-approval letter cancelled. Is there anything else you need?"

        return "I'm not sure what to do next. Can you tell me more?"

    def _generate_select_applicant_response(
        self,
        available_options: Optional[List[Dict[str, Any]]] = None,
    ) -> str:
        """Generate applicant selection prompt"""
        if not available_options:
            return "I couldn't find any active applicants. Would you like me to check again?"

        if len(available_options) == 1:
            opt = available_options[0]
            name = opt.get("name", "the applicant")
            amount = self._format_currency(opt.get("loan_amount", 0))
            loan_type = opt.get("loan_type", "loan")
            return f"I found one active applicant: {name} with a {amount} {loan_type}. Is this correct?"

        # Multiple applicants - limit to 5 for voice
        options_to_present = available_options[:5]
        descriptions = []
        for opt in options_to_present:
            name = opt.get("name", "Unknown")
            amount = self._format_currency(opt.get("loan_amount", 0))
            loan_type = opt.get("loan_type", "loan")
            descriptions.append(f"{name} with a {amount} {loan_type}")

        if len(descriptions) <= 3:
            options_text = ", ".join(descriptions[:-1]) + f", and {descriptions[-1]}"
        else:
            options_text = ", ".join(descriptions[:3])
            remaining = len(available_options) - 3
            if remaining > 0:
                options_text += f", and {remaining} more"

        return f"I found {len(available_options)} applicants. {options_text}. Which one needs the letter?"

    def _generate_review_terms_response(self, slots: Dict[str, Any]) -> str:
        """Generate loan terms review prompt"""
        name = slots.get("applicant_name", "The applicant")
        amount = self._format_currency(slots.get("pre_approved_amount", 0))
        loan_type = slots.get("loan_type", "conventional")
        rate = slots.get("interest_rate")

        # Build the response
        response = f"{name} is pre-approved for {amount} on a {loan_type}"

        if rate:
            response += f" at {rate}%"

        response += ". Would you like to make any changes?"

        return response

    def _generate_select_realtor_response(
        self,
        available_options: Optional[List[Dict[str, Any]]] = None,
    ) -> str:
        """Generate realtor selection prompt"""
        if not available_options:
            return "Which realtor should I send this to? You can say their name or email."

        if len(available_options) <= 3:
            descriptions = []
            for opt in available_options:
                name = opt.get("name", "Unknown")
                company = opt.get("company")
                if company:
                    descriptions.append(f"{name} at {company}")
                else:
                    descriptions.append(name)

            options_text = ", ".join(descriptions[:-1])
            if len(descriptions) > 1:
                options_text += f", or {descriptions[-1]}"
            else:
                options_text = descriptions[0]

            return f"I see you work with {options_text}. Which realtor should receive this letter?"

        return "Which realtor should I send this to?"

    def _generate_final_confirmation_response(self, slots: Dict[str, Any]) -> str:
        """Generate final confirmation prompt"""
        applicant_name = slots.get("applicant_name", "the applicant")
        amount = self._format_currency(slots.get("pre_approved_amount", 0))
        realtor_name = slots.get("realtor_name", "the realtor")
        realtor_company = slots.get("realtor_company")
        property_address = slots.get("property_address")

        # Build confirmation text
        realtor_full = realtor_name
        if realtor_company:
            realtor_full = f"{realtor_name} at {realtor_company}"

        response = f"I'll send a pre-approval letter for {applicant_name} for {amount}"

        if property_address:
            response += f" at {property_address}"

        response += f" to {realtor_full}. Send it now?"

        return response

    def _format_currency(self, amount: float) -> str:
        """Format amount as voice-friendly currency"""
        if amount >= 1000000:
            return f"${amount/1000000:.2f} million".rstrip('0').rstrip('.')
        elif amount >= 1000:
            return f"${amount/1000:.0f} thousand"
        else:
            return f"${amount:,.0f}"

    async def text_to_speech(self, text: str) -> Optional[bytes]:
        """
        Convert text to speech using ElevenLabs API.

        Args:
            text: The text to convert to speech

        Returns:
            Audio bytes in MP3 format, or None on error
        """
        if not self.elevenlabs_api_key:
            logger.warning("ElevenLabs API key not configured")
            return None

        try:
            url = f"https://api.elevenlabs.io/v1/text-to-speech/{self.voice_id}"

            headers = {
                "Accept": "audio/mpeg",
                "Content-Type": "application/json",
                "xi-api-key": self.elevenlabs_api_key,
            }

            payload = {
                "text": text,
                "model_id": self.model_id,
                "voice_settings": {
                    "stability": 0.5,
                    "similarity_boost": 0.75,
                    "style": 0.0,
                    "use_speaker_boost": True,
                }
            }

            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload, headers=headers) as response:
                    if response.status == 200:
                        audio_data = await response.read()
                        logger.info(f"Generated {len(audio_data)} bytes of audio for: {text[:50]}...")
                        return audio_data
                    else:
                        error_text = await response.text()
                        logger.error(f"ElevenLabs API error: {response.status} - {error_text}")
                        return None

        except Exception as e:
            logger.error(f"TTS error: {e}")
            return None

    async def generate_response_with_audio(
        self,
        workflow_type: WorkflowType,
        current_state: str,
        slots: Dict[str, Any],
        available_options: Optional[List[Dict[str, Any]]] = None,
        error_message: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Generate both text response and audio.

        Returns:
            Dict with 'text' and optional 'audio_base64' keys
        """
        text = await self.generate_response(
            workflow_type=workflow_type,
            current_state=current_state,
            slots=slots,
            available_options=available_options,
            error_message=error_message,
        )

        result = {"text": text, "audio_base64": None}

        # Generate audio
        audio_bytes = await self.text_to_speech(text)
        if audio_bytes:
            result["audio_base64"] = base64.b64encode(audio_bytes).decode("utf-8")

        return result


# =============================================================================
# Confirmation and Clarification Responses
# =============================================================================

class VoiceConfirmationResponses:
    """Pre-defined confirmation and clarification responses"""

    @staticmethod
    def confirm_selection(item_name: str) -> str:
        return f"Got it, {item_name}."

    @staticmethod
    def confirm_modification(field: str, new_value: str) -> str:
        return f"I've updated the {field} to {new_value}."

    @staticmethod
    def clarify_selection(options: List[str]) -> str:
        if len(options) <= 3:
            return f"Did you mean {', '.join(options[:-1])}, or {options[-1]}?"
        return "I'm not sure which one you meant. Could you be more specific?"

    @staticmethod
    def clarify_amount() -> str:
        return "What amount would you like to use?"

    @staticmethod
    def clarify_address() -> str:
        return "What's the property address?"

    @staticmethod
    def acknowledge_skip() -> str:
        return "Okay, skipping that step."

    @staticmethod
    def acknowledge_cancel() -> str:
        return "Okay, I'll cancel this. Is there anything else you need?"

    @staticmethod
    def error_no_match() -> str:
        return "I couldn't find a match for that. Could you try again?"

    @staticmethod
    def error_invalid_input() -> str:
        return "I didn't understand that. Could you say it differently?"


# Singleton instance
_response_generator: Optional[VoiceResponseGenerator] = None


def get_response_generator() -> VoiceResponseGenerator:
    """Get or create the response generator singleton"""
    global _response_generator
    if _response_generator is None:
        _response_generator = VoiceResponseGenerator()
    return _response_generator
