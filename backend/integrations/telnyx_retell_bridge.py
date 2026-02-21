"""
Telnyx-Retell Bridge Service

Connects Telnyx phone numbers with Retell AI voice agents.

Flow:
- Inbound: Telnyx receives call → SIP forward → Retell handles AI conversation
- Outbound: Retell initiates → SIP termination → Telnyx places call

Configuration:
1. Get Retell SIP endpoint from Retell dashboard
2. Configure Telnyx TeXML app to forward to Retell SIP
3. Import Telnyx number into Retell with termination URI
"""

import os
import logging
from typing import Optional, Dict, Any, List
from datetime import datetime
from pydantic import BaseModel, Field
import httpx

try:
    from utils.pii_mask import mask_phone
except ImportError:
    mask_phone = lambda x: x[:3] + "***" + x[-2:] if x and len(x) > 5 else "***"

logger = logging.getLogger(__name__)

# Telnyx API Configuration
TELNYX_API_BASE = "https://api.telnyx.com/v2"


class TelnyxRetellConfig(BaseModel):
    """Configuration for connecting a Telnyx number to Retell."""
    telnyx_phone_number: str = Field(..., description="E.164 format phone number from Telnyx")
    retell_agent_id: str = Field(..., description="Retell AI agent ID")

    # SIP Configuration
    retell_sip_endpoint: Optional[str] = Field(
        None,
        description="Retell SIP endpoint (e.g., sip:agent_xxx@retell.ai)"
    )
    telnyx_termination_sip_uri: Optional[str] = Field(
        None,
        description="Telnyx SIP termination URI for outbound calls"
    )

    # Optional settings
    inbound_agent_id: Optional[str] = Field(None, description="Agent for inbound calls")
    outbound_agent_id: Optional[str] = Field(None, description="Agent for outbound calls")


class TelnyxSIPCredential(BaseModel):
    """Telnyx SIP credential for Retell."""
    sip_username: str
    sip_password: str
    sip_realm: str = "sip.telnyx.com"
    termination_uri: str  # Full SIP URI for outbound


class TelnyxRetellBridge:
    """
    Bridge service for connecting Telnyx telephony with Retell AI.
    """

    def __init__(self, telnyx_api_key: str, retell_api_key: str):
        if not telnyx_api_key:
            raise ValueError("Telnyx API key is required but was empty or None")
        if not retell_api_key:
            raise ValueError("Retell API key is required but was empty or None")

        self.telnyx_api_key = telnyx_api_key
        self.retell_api_key = retell_api_key

        self.telnyx_headers = {
            "Authorization": f"Bearer {telnyx_api_key}",
            "Content-Type": "application/json",
        }

        self.retell_headers = {
            "Authorization": f"Bearer {retell_api_key}",
            "Content-Type": "application/json",
        }

    # ==================== Telnyx Phone Number Operations ====================

    async def list_telnyx_numbers(self) -> List[Dict[str, Any]]:
        """List all Telnyx phone numbers available for Retell connection."""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{TELNYX_API_BASE}/phone_numbers",
                headers=self.telnyx_headers,
                params={"page[size]": 100},
                timeout=30.0,
            )

            if response.status_code != 200:
                logger.error(f"Failed to list Telnyx numbers: {response.text}")
                raise Exception(f"Telnyx API error: {response.text}")

            data = response.json()
            return data.get("data", [])

    async def get_telnyx_number_details(self, phone_number: str) -> Dict[str, Any]:
        """Get details of a specific Telnyx phone number."""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{TELNYX_API_BASE}/phone_numbers/{phone_number}",
                headers=self.telnyx_headers,
                timeout=30.0,
            )

            if response.status_code != 200:
                raise Exception(f"Failed to get number details: {response.text}")

            return response.json().get("data", {})

    # ==================== Telnyx SIP Connection Setup ====================

    async def create_sip_connection(self, connection_name: str) -> Dict[str, Any]:
        """
        Create a Telnyx SIP Connection for Retell integration.

        This creates the SIP trunk that Retell will use for outbound calls.
        """
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{TELNYX_API_BASE}/sip_connections",
                headers=self.telnyx_headers,
                json={
                    "connection_name": connection_name,
                    "active": True,
                    "transport_protocol": "UDP",
                    "default_on_hold_comfort_noise_enabled": True,
                    "encrypted_media": "SRTP",
                },
                timeout=30.0,
            )

            if response.status_code not in [200, 201]:
                raise Exception(f"Failed to create SIP connection: {response.text}")

            return response.json().get("data", {})

    async def get_sip_connections(self) -> List[Dict[str, Any]]:
        """List all Telnyx SIP connections."""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{TELNYX_API_BASE}/sip_connections",
                headers=self.telnyx_headers,
                timeout=30.0,
            )

            if response.status_code != 200:
                raise Exception(f"Failed to list SIP connections: {response.text}")

            return response.json().get("data", [])

    async def create_credential_connection(
        self,
        connection_name: str,
        user_name: str,
        password: str,
    ) -> Dict[str, Any]:
        """
        Create a Credential Connection for SIP authentication.

        This allows Retell to authenticate when making outbound calls via Telnyx.
        """
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{TELNYX_API_BASE}/credential_connections",
                headers=self.telnyx_headers,
                json={
                    "connection_name": connection_name,
                    "active": True,
                    "user_name": user_name,
                    "password": password,
                    "sip_uri_calling_preference": "unrestricted",
                    "default_on_hold_comfort_noise_enabled": True,
                },
                timeout=30.0,
            )

            if response.status_code not in [200, 201]:
                raise Exception(f"Failed to create credential connection: {response.text}")

            return response.json().get("data", {})

    async def create_outbound_voice_profile(
        self,
        name: str,
        connection_id: str,
    ) -> Dict[str, Any]:
        """
        Create an Outbound Voice Profile for the SIP connection.

        This is required to route outbound calls through Telnyx.
        """
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{TELNYX_API_BASE}/outbound_voice_profiles",
                headers=self.telnyx_headers,
                json={
                    "name": name,
                    "traffic_type": "conversational",
                    "service_plan": "global",
                    "concurrent_call_limit": 10,
                    "enabled": True,
                    "primary_outbound_voice_profile_id": None,
                },
                timeout=30.0,
            )

            if response.status_code not in [200, 201]:
                raise Exception(f"Failed to create voice profile: {response.text}")

            return response.json().get("data", {})

    # ==================== Retell Import Operations ====================

    async def import_number_to_retell(
        self,
        phone_number: str,
        agent_id: str,
        termination_uri: str,
        inbound_agent_id: Optional[str] = None,
        outbound_agent_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Import a Telnyx phone number into Retell AI.

        Args:
            phone_number: E.164 format number
            agent_id: Default agent for the number
            termination_uri: Telnyx SIP URI for outbound calls
            inbound_agent_id: Optional different agent for inbound
            outbound_agent_id: Optional different agent for outbound
        """
        payload = {
            "phone_number": phone_number,
            "termination_uri": termination_uri,
        }

        # Set agent IDs
        if inbound_agent_id and outbound_agent_id:
            payload["inbound_agent_id"] = inbound_agent_id
            payload["outbound_agent_id"] = outbound_agent_id
        else:
            payload["agent_id"] = agent_id

        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://api.retellai.com/v2/phone-number/import",
                headers=self.retell_headers,
                json=payload,
                timeout=30.0,
            )

            if response.status_code not in [200, 201]:
                raise Exception(f"Failed to import number to Retell: {response.text}")

            return response.json()

    # ==================== TeXML App Configuration ====================

    async def create_texml_app_for_retell(
        self,
        app_name: str,
        retell_sip_endpoint: str,
        webhook_url: str,
    ) -> Dict[str, Any]:
        """
        Create a TeXML application that forwards calls to Retell.

        The TeXML app will use SIP to forward incoming calls to Retell's endpoint.
        """
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{TELNYX_API_BASE}/texml_applications",
                headers=self.telnyx_headers,
                json={
                    "friendly_name": app_name,
                    "active": True,
                    "voice_url": webhook_url,
                    "voice_fallback_url": webhook_url,
                    "voice_method": "POST",
                    "status_callback": webhook_url,
                    "status_callback_method": "POST",
                    "inbound": True,
                    "outbound": True,
                },
                timeout=30.0,
            )

            if response.status_code not in [200, 201]:
                raise Exception(f"Failed to create TeXML app: {response.text}")

            return response.json().get("data", {})

    async def update_number_connection(
        self,
        phone_number_id: str,
        connection_id: str,
    ) -> Dict[str, Any]:
        """
        Associate a phone number with a TeXML application or SIP connection.
        """
        async with httpx.AsyncClient() as client:
            response = await client.patch(
                f"{TELNYX_API_BASE}/phone_numbers/{phone_number_id}",
                headers=self.telnyx_headers,
                json={
                    "connection_id": connection_id,
                },
                timeout=30.0,
            )

            if response.status_code != 200:
                raise Exception(f"Failed to update number: {response.text}")

            return response.json().get("data", {})

    # ==================== Full Setup Workflow ====================

    async def setup_telnyx_retell_connection(
        self,
        phone_number: str,
        retell_agent_id: str,
        connection_name: str = "Retell AI Connection",
        sip_username: Optional[str] = None,
        sip_password: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Complete setup workflow to connect a Telnyx number with Retell AI.

        Steps:
        1. Create/get SIP credential connection on Telnyx
        2. Get Telnyx termination URI
        3. Import number to Retell with termination URI
        4. Return configuration details

        Args:
            phone_number: Telnyx phone number to connect
            retell_agent_id: Retell agent to handle calls
            connection_name: Name for the SIP connection
            sip_username: Optional SIP auth username
            sip_password: Optional SIP auth password
        """
        import secrets

        # Generate credentials if not provided
        if not sip_username:
            sip_username = f"retell_{phone_number.replace('+', '')}"
        if not sip_password:
            sip_password = secrets.token_urlsafe(24)

        setup_result = {
            "phone_number": phone_number,
            "retell_agent_id": retell_agent_id,
            "steps_completed": [],
            "configuration": {},
        }

        try:
            # Step 1: Create credential connection
            logger.info(f"Creating SIP credential connection: {connection_name}")
            cred_conn = await self.create_credential_connection(
                connection_name=connection_name,
                user_name=sip_username,
                password=sip_password,
            )
            setup_result["steps_completed"].append("credential_connection_created")
            setup_result["configuration"]["credential_connection_id"] = cred_conn.get("id")

            # Step 2: Build termination URI
            # Format: sip:username@sip.telnyx.com
            termination_uri = f"sip:{sip_username}@sip.telnyx.com"
            setup_result["configuration"]["termination_uri"] = termination_uri
            setup_result["configuration"]["sip_username"] = sip_username
            setup_result["configuration"]["sip_password"] = sip_password
            setup_result["steps_completed"].append("termination_uri_configured")

            # Step 3: Import number to Retell
            logger.info(f"Importing {mask_phone(phone_number)} to Retell with agent {retell_agent_id}")
            retell_import = await self.import_number_to_retell(
                phone_number=phone_number,
                agent_id=retell_agent_id,
                termination_uri=termination_uri,
            )
            setup_result["steps_completed"].append("retell_import_complete")
            setup_result["configuration"]["retell_phone_number_id"] = retell_import.get("phone_number")

            # Step 4: Get Retell SIP endpoint for inbound forwarding
            # Note: Retell provides a SIP endpoint per agent that Telnyx should forward to
            retell_sip_endpoint = f"sip:{retell_agent_id}@inbound.retellai.com"
            setup_result["configuration"]["retell_sip_endpoint"] = retell_sip_endpoint
            setup_result["steps_completed"].append("configuration_complete")

            setup_result["success"] = True
            setup_result["message"] = (
                f"Successfully connected {phone_number} to Retell agent. "
                f"Configure Telnyx to forward inbound calls to: {retell_sip_endpoint}"
            )

            # Instructions for manual Telnyx configuration
            setup_result["next_steps"] = [
                f"1. In Telnyx Portal, go to your TeXML application",
                f"2. Set the Voice URL to forward to: {retell_sip_endpoint}",
                f"3. Or use the Dial SIP verb in your TeXML to forward to Retell",
                f"4. Outbound calls will route through: {termination_uri}",
            ]

        except Exception as e:
            logger.exception(f"Failed to setup Telnyx-Retell connection: {e}")
            setup_result["success"] = False
            setup_result["error"] = str(e)

        return setup_result

    def generate_texml_for_retell(
        self,
        retell_agent_id: str,
        caller_id: Optional[str] = None,
    ) -> str:
        """
        Generate TeXML to forward incoming calls to Retell AI.

        This TeXML can be used as the response from your voice webhook.
        """
        # Retell's SIP endpoint format
        retell_sip = f"sip:{retell_agent_id}@inbound.retellai.com"

        texml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Dial>
        <Sip>{retell_sip}</Sip>
    </Dial>
</Response>"""

        return texml


# ==================== Helper Functions ====================

def get_bridge_for_user(
    telnyx_api_key: str,
    retell_api_key: str,
) -> TelnyxRetellBridge:
    """Create a bridge instance with user credentials.

    Raises ValueError if either key is missing/empty.
    """
    return TelnyxRetellBridge(
        telnyx_api_key=telnyx_api_key,
        retell_api_key=retell_api_key,
    )
