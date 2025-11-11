"""
RingCentral Integration Service
Provides click-to-call and SMS functionality via RingCentral API
"""
import os
import logging
from typing import Optional, Dict, Any, List
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

try:
    from ringcentral import SDK
    RINGCENTRAL_AVAILABLE = True
except ImportError:
    RINGCENTRAL_AVAILABLE = False
    logger.warning("RingCentral SDK not installed. Run: pip install ringcentral")


class RingCentralService:
    """Service for RingCentral phone and SMS integration"""

    def __init__(self):
        self.enabled = False
        self.client = None
        self.platform = None
        self.from_number = None

        # Get credentials from environment
        self.client_id = os.getenv("RINGCENTRAL_CLIENT_ID")
        self.client_secret = os.getenv("RINGCENTRAL_CLIENT_SECRET")
        self.server_url = os.getenv("RINGCENTRAL_SERVER_URL", "https://platform.ringcentral.com")
        self.username = os.getenv("RINGCENTRAL_USERNAME")  # Your RingCentral phone number
        self.extension = os.getenv("RINGCENTRAL_EXTENSION", "")
        self.password = os.getenv("RINGCENTRAL_PASSWORD")  # Your RingCentral password
        self.from_number = os.getenv("RINGCENTRAL_PHONE_NUMBER")

        # Check if all required credentials are present
        has_credentials = all([
            self.client_id,
            self.client_secret,
            self.username,
            self.password,
            self.from_number,
            RINGCENTRAL_AVAILABLE
        ])

        if has_credentials:
            try:
                # Initialize RingCentral SDK
                self.client = SDK(
                    self.client_id,
                    self.client_secret,
                    self.server_url
                )
                self.platform = self.client.platform()

                # Login to RingCentral
                self.platform.login(
                    jwt=None,
                    username=self.username,
                    extension=self.extension,
                    password=self.password
                )

                self.enabled = True
                logger.info("RingCentral integration initialized successfully")
            except Exception as e:
                logger.error(f"Failed to initialize RingCentral: {str(e)}")
                self.enabled = False
        else:
            missing = []
            if not RINGCENTRAL_AVAILABLE:
                missing.append("RingCentral SDK")
            if not self.client_id:
                missing.append("RINGCENTRAL_CLIENT_ID")
            if not self.client_secret:
                missing.append("RINGCENTRAL_CLIENT_SECRET")
            if not self.username:
                missing.append("RINGCENTRAL_USERNAME")
            if not self.password:
                missing.append("RINGCENTRAL_PASSWORD")
            if not self.from_number:
                missing.append("RINGCENTRAL_PHONE_NUMBER")

            logger.warning(f"RingCentral not configured. Missing: {', '.join(missing)}")

    async def make_call(self, to_number: str, caller_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Initiate a RingOut call (click-to-call)

        Args:
            to_number: Phone number to call (E.164 format recommended)
            caller_id: Optional caller ID to display

        Returns:
            Dict with call session information
        """
        if not self.enabled:
            raise Exception("RingCentral service is not enabled")

        try:
            # Clean phone number
            to_number = self._format_phone_number(to_number)
            from_number = caller_id or self.from_number

            # Make RingOut call
            response = self.platform.post('/restapi/v1.0/account/~/extension/~/ring-out', {
                'from': {'phoneNumber': from_number},
                'to': {'phoneNumber': to_number},
                'playPrompt': False  # Skip prompt, connect immediately
            })

            call_data = response.json()

            logger.info(f"Call initiated to {to_number}, session ID: {call_data.get('id')}")

            return {
                "success": True,
                "session_id": call_data.get("id"),
                "status": call_data.get("status", {}).get("callStatus"),
                "from_number": from_number,
                "to_number": to_number,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }

        except Exception as e:
            logger.error(f"Failed to make call: {str(e)}")
            raise Exception(f"Failed to initiate call: {str(e)}")

    async def send_sms(self, to_number: str, message: str) -> Dict[str, Any]:
        """
        Send SMS message via RingCentral

        Args:
            to_number: Recipient phone number
            message: Message text (max 1000 characters for SMS)

        Returns:
            Dict with message information
        """
        if not self.enabled:
            raise Exception("RingCentral service is not enabled")

        try:
            # Clean phone number
            to_number = self._format_phone_number(to_number)

            # Send SMS
            response = self.platform.post('/restapi/v1.0/account/~/extension/~/sms', {
                'from': {'phoneNumber': self.from_number},
                'to': [{'phoneNumber': to_number}],
                'text': message
            })

            sms_data = response.json()

            logger.info(f"SMS sent to {to_number}, message ID: {sms_data.get('id')}")

            return {
                "success": True,
                "message_id": sms_data.get("id"),
                "status": sms_data.get("messageStatus"),
                "from_number": self.from_number,
                "to_number": to_number,
                "message": message,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }

        except Exception as e:
            logger.error(f"Failed to send SMS: {str(e)}")
            raise Exception(f"Failed to send SMS: {str(e)}")

    async def get_call_log(self, date_from: Optional[datetime] = None, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Get call history from RingCentral

        Args:
            date_from: Optional start date for call log
            limit: Maximum number of calls to return

        Returns:
            List of call records
        """
        if not self.enabled:
            raise Exception("RingCentral service is not enabled")

        try:
            params = {
                'view': 'Detailed',
                'perPage': limit
            }

            if date_from:
                params['dateFrom'] = date_from.isoformat()

            response = self.platform.get('/restapi/v1.0/account/~/extension/~/call-log', params)
            data = response.json()

            calls = []
            for record in data.get('records', []):
                calls.append({
                    "id": record.get("id"),
                    "direction": record.get("direction"),  # Inbound/Outbound
                    "type": record.get("type"),  # Voice/Fax
                    "action": record.get("action"),  # Phone Call/Missed Call/etc
                    "result": record.get("result"),  # Call Connected/Voicemail/etc
                    "from_number": record.get("from", {}).get("phoneNumber"),
                    "from_name": record.get("from", {}).get("name"),
                    "to_number": record.get("to", {}).get("phoneNumber"),
                    "to_name": record.get("to", {}).get("name"),
                    "duration": record.get("duration"),
                    "start_time": record.get("startTime"),
                    "recording": record.get("recording")
                })

            return calls

        except Exception as e:
            logger.error(f"Failed to get call log: {str(e)}")
            raise Exception(f"Failed to get call log: {str(e)}")

    async def get_sms_history(self, date_from: Optional[datetime] = None, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Get SMS message history from RingCentral

        Args:
            date_from: Optional start date for message history
            limit: Maximum number of messages to return

        Returns:
            List of SMS records
        """
        if not self.enabled:
            raise Exception("RingCentral service is not enabled")

        try:
            params = {
                'messageType': 'SMS',
                'perPage': limit
            }

            if date_from:
                params['dateFrom'] = date_from.isoformat()

            response = self.platform.get('/restapi/v1.0/account/~/extension/~/message-store', params)
            data = response.json()

            messages = []
            for record in data.get('records', []):
                messages.append({
                    "id": record.get("id"),
                    "direction": record.get("direction"),  # Inbound/Outbound
                    "type": record.get("type"),  # SMS/MMS
                    "from_number": record.get("from", {}).get("phoneNumber"),
                    "from_name": record.get("from", {}).get("name"),
                    "to_numbers": [t.get("phoneNumber") for t in record.get("to", [])],
                    "subject": record.get("subject"),
                    "message": record.get("subject"),  # Message text is in subject field
                    "read_status": record.get("readStatus"),
                    "creation_time": record.get("creationTime"),
                    "last_modified_time": record.get("lastModifiedTime")
                })

            return messages

        except Exception as e:
            logger.error(f"Failed to get SMS history: {str(e)}")
            raise Exception(f"Failed to get SMS history: {str(e)}")

    def _format_phone_number(self, phone: str) -> str:
        """Format phone number for RingCentral (E.164 format preferred)"""
        # Remove all non-digit characters
        digits = ''.join(filter(str.isdigit, phone))

        # If it's a 10-digit US number, add +1
        if len(digits) == 10:
            return f"+1{digits}"

        # If it already has country code
        if len(digits) == 11 and digits.startswith('1'):
            return f"+{digits}"

        # Otherwise return as-is with + prefix
        if not phone.startswith('+'):
            return f"+{digits}"

        return phone

    def get_status(self) -> Dict[str, Any]:
        """Get RingCentral service status"""
        return {
            "enabled": self.enabled,
            "from_number": self.from_number if self.enabled else None,
            "server_url": self.server_url if self.enabled else None,
            "authenticated": self.platform.auth().access_token() is not None if (self.enabled and self.platform) else False
        }


# Global instance
ringcentral_client = RingCentralService()
