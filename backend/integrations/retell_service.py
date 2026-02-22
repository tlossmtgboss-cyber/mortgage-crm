"""
Retell AI Service

Comprehensive integration with Retell AI for voice agents.
Replaces ElevenLabs + legacy telephony stack with unified voice platform.

Features:
- Agent management (create, update, delete)
- Phone number management
- Call initiation and management
- Webhook handling
- LLM configuration
"""

import os
import httpx
import logging
from typing import Optional, Dict, Any, List
from datetime import datetime
from enum import Enum
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# Retell AI API Configuration
RETELL_API_BASE = "https://api.retellai.com"
RETELL_API_KEY = os.getenv("RETELL_API_KEY")


class RetellVoice(str, Enum):
    """Available Retell AI voices."""
    # Female voices
    EMMA = "11labs-Emma"
    DOROTHY = "11labs-Dorothy"
    MATILDA = "11labs-Matilda"
    RACHEL = "11labs-Rachel"
    # Male voices
    ADAM = "11labs-Adam"
    JOSH = "11labs-Josh"
    MICHAEL = "11labs-Michael"
    CHRIS = "11labs-Chris"
    # OpenAI voices
    ALLOY = "openai-Alloy"
    ECHO = "openai-Echo"
    NOVA = "openai-Nova"
    SHIMMER = "openai-Shimmer"


class RetellLLMType(str, Enum):
    """Supported LLM types."""
    RETELL_DEFAULT = "retell-llm"
    CUSTOM_LLM = "custom-llm"
    OPENAI = "openai"


class AgentConfig(BaseModel):
    """Configuration for creating/updating a Retell agent."""
    agent_name: str
    voice_id: str = RetellVoice.EMMA.value
    response_engine: Dict[str, Any] = Field(default_factory=dict)
    llm_websocket_url: Optional[str] = None

    # Voice settings
    voice_temperature: float = 0.7
    voice_speed: float = 1.0

    # Behavior settings
    interruption_sensitivity: float = 0.5
    enable_backchannel: bool = True
    backchannel_frequency: float = 0.5

    # Turn detection
    end_call_after_silence_ms: int = 30000
    max_call_duration_ms: int = 3600000  # 1 hour

    # Metadata
    metadata: Dict[str, Any] = Field(default_factory=dict)


class CallConfig(BaseModel):
    """Configuration for initiating a call."""
    agent_id: str
    to_number: str
    from_number: Optional[str] = None

    # Dynamic variables for the agent
    dynamic_variables: Dict[str, str] = Field(default_factory=dict)

    # Call settings
    drop_if_machine_detected: bool = False

    # Metadata
    metadata: Dict[str, Any] = Field(default_factory=dict)


class PhoneNumberConfig(BaseModel):
    """Configuration for phone numbers."""
    agent_id: str
    area_code: Optional[int] = None
    inbound_agent_id: Optional[str] = None
    outbound_agent_id: Optional[str] = None


class RetellClient:
    """
    Retell AI API Client.

    Provides methods for managing agents, phone numbers, and calls.
    """

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or RETELL_API_KEY
        if not self.api_key:
            logger.warning("No Retell API key configured")

        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    async def _request(
        self,
        method: str,
        endpoint: str,
        data: Optional[Dict] = None,
        params: Optional[Dict] = None,
    ) -> Dict[str, Any]:
        """Make an API request to Retell AI."""
        url = f"{RETELL_API_BASE}{endpoint}"

        async with httpx.AsyncClient() as client:
            try:
                response = await client.request(
                    method=method,
                    url=url,
                    headers=self.headers,
                    json=data,
                    params=params,
                    timeout=30.0,
                )

                if response.status_code >= 400:
                    error_text = response.text
                    logger.error(f"Retell API error: {response.status_code} - {error_text}")
                    raise RetellAPIError(
                        status_code=response.status_code,
                        message=error_text,
                    )

                return response.json() if response.text else {}

            except httpx.RequestError as e:
                logger.error(f"Retell API request failed: {e}")
                raise RetellAPIError(message=str(e))

    # ==================== Agent Management ====================

    async def create_agent(self, config: AgentConfig) -> Dict[str, Any]:
        """
        Create a new Retell AI agent.

        Args:
            config: Agent configuration

        Returns:
            Created agent data including agent_id
        """
        payload = {
            "agent_name": config.agent_name,
            "voice_id": config.voice_id,
            "voice_temperature": config.voice_temperature,
            "voice_speed": config.voice_speed,
            "interruption_sensitivity": config.interruption_sensitivity,
            "enable_backchannel": config.enable_backchannel,
            "backchannel_frequency": config.backchannel_frequency,
            "end_call_after_silence_ms": config.end_call_after_silence_ms,
            "max_call_duration_ms": config.max_call_duration_ms,
        }

        # Add response engine (LLM config)
        if config.response_engine:
            payload["response_engine"] = config.response_engine
        elif config.llm_websocket_url:
            payload["llm_websocket_url"] = config.llm_websocket_url

        if config.metadata:
            payload["metadata"] = config.metadata

        return await self._request("POST", "/create-agent", data=payload)

    async def get_agent(self, agent_id: str) -> Dict[str, Any]:
        """Get agent details."""
        return await self._request("GET", f"/get-agent/{agent_id}")

    async def list_agents(self) -> List[Dict[str, Any]]:
        """List all agents."""
        return await self._request("GET", "/list-agents")

    async def update_agent(self, agent_id: str, config: Dict[str, Any]) -> Dict[str, Any]:
        """Update an existing agent."""
        return await self._request("PATCH", f"/update-agent/{agent_id}", data=config)

    async def delete_agent(self, agent_id: str) -> None:
        """Delete an agent."""
        await self._request("DELETE", f"/delete-agent/{agent_id}")

    # ==================== Phone Number Management ====================

    async def create_phone_number(
        self,
        agent_id: str,
        area_code: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Create/purchase a new phone number and attach to agent.

        Args:
            agent_id: Agent to attach the number to
            area_code: Optional area code preference

        Returns:
            Phone number details
        """
        payload = {"agent_id": agent_id}
        if area_code:
            payload["area_code"] = area_code

        return await self._request("POST", "/create-phone-number", data=payload)

    async def import_phone_number(
        self,
        phone_number: str,
        agent_id: str,
        termination_uri: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Import an existing phone number (from Telnyx, etc).

        Args:
            phone_number: E.164 formatted phone number
            agent_id: Agent to attach the number to
            termination_uri: SIP termination URI for the number

        Returns:
            Phone number details
        """
        payload = {
            "phone_number": phone_number,
            "agent_id": agent_id,
        }
        if termination_uri:
            payload["termination_uri"] = termination_uri

        return await self._request("POST", "/import-phone-number", data=payload)

    async def get_phone_number(self, phone_number: str) -> Dict[str, Any]:
        """Get phone number details."""
        return await self._request("GET", f"/get-phone-number/{phone_number}")

    async def list_phone_numbers(self) -> List[Dict[str, Any]]:
        """List all phone numbers."""
        return await self._request("GET", "/list-phone-numbers")

    async def update_phone_number(
        self,
        phone_number: str,
        agent_id: Optional[str] = None,
        inbound_agent_id: Optional[str] = None,
        outbound_agent_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Update phone number configuration."""
        payload = {}
        if agent_id:
            payload["agent_id"] = agent_id
        if inbound_agent_id:
            payload["inbound_agent_id"] = inbound_agent_id
        if outbound_agent_id:
            payload["outbound_agent_id"] = outbound_agent_id

        return await self._request("PATCH", f"/update-phone-number/{phone_number}", data=payload)

    async def delete_phone_number(self, phone_number: str) -> None:
        """Delete/release a phone number."""
        await self._request("DELETE", f"/delete-phone-number/{phone_number}")

    # ==================== Call Management ====================

    async def create_call(self, config: CallConfig) -> Dict[str, Any]:
        """
        Initiate an outbound call.

        Args:
            config: Call configuration

        Returns:
            Call details including call_id
        """
        payload = {
            "agent_id": config.agent_id,
            "to_number": config.to_number,
        }

        if config.from_number:
            payload["from_number"] = config.from_number

        if config.dynamic_variables:
            payload["retell_llm_dynamic_variables"] = config.dynamic_variables

        if config.drop_if_machine_detected:
            payload["drop_if_machine_detected"] = True

        if config.metadata:
            payload["metadata"] = config.metadata

        return await self._request("POST", "/create-phone-call", data=payload)

    async def get_call(self, call_id: str) -> Dict[str, Any]:
        """Get call details."""
        return await self._request("GET", f"/get-call/{call_id}")

    async def list_calls(
        self,
        filter_criteria: Optional[Dict[str, Any]] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """List calls with optional filtering."""
        params = {"limit": limit}
        if filter_criteria:
            params.update(filter_criteria)

        return await self._request("GET", "/list-calls", params=params)

    async def end_call(self, call_id: str) -> Dict[str, Any]:
        """End an active call."""
        return await self._request("POST", f"/end-call/{call_id}")

    async def transfer_call(
        self,
        call_id: str,
        transfer_to: str,
    ) -> Dict[str, Any]:
        """Transfer an active call to another number."""
        return await self._request(
            "POST",
            f"/transfer-call/{call_id}",
            data={"transfer_to": transfer_to},
        )

    # ==================== LLM Management ====================

    async def create_retell_llm(
        self,
        general_prompt: str,
        begin_message: Optional[str] = None,
        general_tools: Optional[List[Dict]] = None,
        states: Optional[List[Dict]] = None,
    ) -> Dict[str, Any]:
        """
        Create a Retell LLM configuration.

        Args:
            general_prompt: System prompt for the LLM
            begin_message: First message when call starts
            general_tools: Tools available to the LLM
            states: State machine configuration

        Returns:
            LLM configuration including llm_id
        """
        payload = {
            "general_prompt": general_prompt,
        }

        if begin_message:
            payload["begin_message"] = begin_message

        if general_tools:
            payload["general_tools"] = general_tools

        if states:
            payload["states"] = states

        return await self._request("POST", "/create-retell-llm", data=payload)

    async def get_retell_llm(self, llm_id: str) -> Dict[str, Any]:
        """Get LLM configuration."""
        return await self._request("GET", f"/get-retell-llm/{llm_id}")

    async def update_retell_llm(self, llm_id: str, config: Dict[str, Any]) -> Dict[str, Any]:
        """Update LLM configuration."""
        return await self._request("PATCH", f"/update-retell-llm/{llm_id}", data=config)

    async def delete_retell_llm(self, llm_id: str) -> None:
        """Delete LLM configuration."""
        await self._request("DELETE", f"/delete-retell-llm/{llm_id}")

    # ==================== Webhook Verification ====================

    @staticmethod
    def verify_webhook_signature(
        payload: bytes,
        signature: str,
        api_key: str,
    ) -> bool:
        """
        Verify webhook signature from Retell AI.

        Args:
            payload: Raw request body
            signature: X-Retell-Signature header
            api_key: Your Retell API key

        Returns:
            True if signature is valid
        """
        import hmac
        import hashlib

        expected_signature = hmac.new(
            api_key.encode(),
            payload,
            hashlib.sha256,
        ).hexdigest()

        return hmac.compare_digest(signature, expected_signature)

    # ==================== Voice Catalog ====================

    async def list_voices(self) -> List[Dict[str, Any]]:
        """List available voices."""
        return await self._request("GET", "/list-voices")


class RetellAPIError(Exception):
    """Exception for Retell API errors."""

    def __init__(self, message: str, status_code: Optional[int] = None):
        self.message = message
        self.status_code = status_code
        super().__init__(self.message)


# ==================== AI Receptionist Prompt Templates ====================

AI_RECEPTIONIST_PROMPT = """You are Sam, the AI receptionist for {company_name}, a mortgage company.

Your role is to:
1. Greet callers warmly and professionally
2. Identify their needs (new loan inquiry, existing loan status, payment questions, etc.)
3. Qualify leads by gathering basic information
4. Route calls to the appropriate department or schedule callbacks
5. Answer common questions about the mortgage process

Company Information:
- Company: {company_name}
- Hours: {business_hours}
- Website: {website}

Caller Information (if available):
{caller_info}

Guidelines:
- Be warm, professional, and empathetic
- Keep responses concise for natural phone conversation
- If you don't know something, offer to connect them with a specialist
- For new loan inquiries, gather: name, phone, email, property type, loan purpose, estimated amount
- For existing customers, verify identity before sharing loan details
- Always offer to schedule a callback if the caller prefers

Transfer Extensions:
- Sales/New Loans: Press 1 or say "sales"
- Loan Status: Press 2 or say "status"
- Payments: Press 3 or say "payments"
- General Support: Press 0 or say "support"
"""

MARKETING_ASSISTANT_PROMPT = """You are {agent_name}, an AI assistant for {company_name}, reaching out to {client_name}.

Purpose of this call: {call_purpose}

Your goals:
1. Introduce yourself and {company_name}
2. {specific_goal}
3. Gather relevant information
4. Schedule a follow-up if interested
5. Be respectful of their time

Information about the client:
{client_info}

Guidelines:
- Be conversational and friendly, not pushy
- If they're not interested, thank them and end the call politely
- If they're interested, gather their availability for a follow-up
- Keep the call under 3 minutes unless they want to continue
- If they ask to be removed from the list, acknowledge and end the call

Key talking points:
{talking_points}
"""


# ==================== Helper Functions ====================

def get_retell_client(api_key: Optional[str] = None) -> RetellClient:
    """Get a configured Retell client."""
    return RetellClient(api_key=api_key)


async def create_ai_receptionist_agent(
    company_name: str,
    business_hours: str = "Monday-Friday, 9 AM - 6 PM",
    website: str = "",
    voice_id: str = RetellVoice.EMMA.value,
    api_key: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Create a pre-configured AI Receptionist agent.

    Args:
        company_name: Name of the company
        business_hours: Business hours string
        website: Company website
        voice_id: Retell voice ID
        api_key: Optional API key override

    Returns:
        Created agent data
    """
    client = get_retell_client(api_key)

    # Create the LLM configuration
    prompt = AI_RECEPTIONIST_PROMPT.format(
        company_name=company_name,
        business_hours=business_hours,
        website=website,
        caller_info="No caller information available yet.",
    )

    llm = await client.create_retell_llm(
        general_prompt=prompt,
        begin_message=f"Hello, thank you for calling {company_name}. This is Sam, how may I help you today?",
    )

    # Create the agent
    config = AgentConfig(
        agent_name=f"{company_name} AI Receptionist",
        voice_id=voice_id,
        response_engine={"type": "retell-llm", "llm_id": llm["llm_id"]},
        interruption_sensitivity=0.6,
        enable_backchannel=True,
        metadata={
            "type": "ai_receptionist",
            "company": company_name,
        },
    )

    return await client.create_agent(config)


async def create_marketing_agent(
    company_name: str,
    agent_name: str = "Alex",
    voice_id: str = RetellVoice.ADAM.value,
    api_key: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Create a pre-configured Marketing Assistant agent.

    Args:
        company_name: Name of the company
        agent_name: Name for the AI agent
        voice_id: Retell voice ID
        api_key: Optional API key override

    Returns:
        Created agent data
    """
    client = get_retell_client(api_key)

    # Create the LLM configuration with placeholder variables
    prompt = MARKETING_ASSISTANT_PROMPT.format(
        agent_name=agent_name,
        company_name=company_name,
        client_name="{{client_name}}",
        call_purpose="{{call_purpose}}",
        specific_goal="{{specific_goal}}",
        client_info="{{client_info}}",
        talking_points="{{talking_points}}",
    )

    llm = await client.create_retell_llm(
        general_prompt=prompt,
        begin_message=f"Hi, this is {agent_name} from {company_name}. Is this {{{{client_name}}}}?",
    )

    # Create the agent
    config = AgentConfig(
        agent_name=f"{company_name} Marketing Assistant",
        voice_id=voice_id,
        response_engine={"type": "retell-llm", "llm_id": llm["llm_id"]},
        interruption_sensitivity=0.5,
        enable_backchannel=True,
        metadata={
            "type": "marketing_assistant",
            "company": company_name,
        },
    )

    return await client.create_agent(config)
