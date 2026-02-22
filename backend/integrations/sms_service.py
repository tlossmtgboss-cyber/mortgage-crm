"""
SMS Service — Telnyx Provider

Sends and manages SMS messages via the Telnyx HTTP API.
No SDK dependency required — uses direct HTTP requests.
"""
import os
import logging
from typing import Optional, List, Dict, Any

logger = logging.getLogger(__name__)


class SMSClient:
    """Telnyx SMS client for text messaging"""

    def __init__(self):
        self.provider = "telnyx"
        self.enabled = False
        self._telnyx_api_key = os.getenv("TELNYX_API_KEY", "")
        self.from_number = os.getenv("TELNYX_PHONE_NUMBER", "")
        self.messaging_profile_id = os.getenv("TELNYX_MESSAGING_PROFILE_ID", "")

        if self._telnyx_api_key and self.from_number:
            self.enabled = True
            logger.info(f"Telnyx SMS initialized. From: {self.from_number}, API key: {self._telnyx_api_key[:8]}...")
        else:
            missing = []
            if not self._telnyx_api_key:
                missing.append("TELNYX_API_KEY")
            if not self.from_number:
                missing.append("TELNYX_PHONE_NUMBER")
            logger.warning(f"Telnyx SMS not configured — missing: {', '.join(missing)}")

    async def send_sms(
        self,
        to_number: str,
        message: str,
        media_url: Optional[str] = None,
        from_number: Optional[str] = None
    ) -> Optional[str]:
        """
        Send SMS message via Telnyx HTTP API.
        Returns message ID if successful, None otherwise.
        """
        if not self.enabled:
            logger.warning("Telnyx not enabled, cannot send SMS")
            return None

        # Ensure phone number is in E.164 format
        if not to_number.startswith("+"):
            to_number = f"+1{to_number}"

        from_num = from_number or self.from_number

        try:
            import requests

            payload = {
                "from": from_num,
                "to": to_number,
                "text": message,
            }

            if self.messaging_profile_id:
                payload["messaging_profile_id"] = self.messaging_profile_id

            if media_url:
                payload["media_urls"] = [media_url]

            response = requests.post(
                "https://api.telnyx.com/v2/messages",
                headers={
                    "Authorization": f"Bearer {self._telnyx_api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=10,
            )

            if response.status_code in (200, 201, 202):
                data = response.json()
                message_id = data.get("data", {}).get("id", "")
                logger.info(f"Telnyx SMS sent to {to_number}. ID: {message_id}")
                return message_id
            else:
                error_body = response.text[:500]
                logger.error(f"Telnyx SMS failed: HTTP {response.status_code} — {error_body}")
                logger.error(f"  Request: from={from_num}, to={to_number}, profile={self.messaging_profile_id}")
                return None

        except Exception as e:
            logger.error(f"Telnyx error sending SMS to {to_number}: {e}", exc_info=True)
            return None

    async def send_bulk_sms(
        self,
        recipients: List[Dict[str, str]],
        message_template: str
    ) -> Dict[str, Any]:
        """
        Send SMS to multiple recipients.
        recipients: List of dicts with 'phone' and optional 'name' keys.
        Returns dict with success/failure counts.
        """
        results = {
            "sent": 0,
            "failed": 0,
            "message_ids": []
        }

        for recipient in recipients:
            phone = recipient.get("phone")
            name = recipient.get("name", "")

            message = message_template.replace("{name}", name) if name else message_template

            msg_id = await self.send_sms(phone, message)

            if msg_id:
                results["sent"] += 1
                results["message_ids"].append(msg_id)
            else:
                results["failed"] += 1

        return results

    async def get_message_status(self, message_id: str) -> Optional[Dict[str, Any]]:
        """Get status of a sent message via Telnyx HTTP API"""
        if not self.enabled:
            return None

        try:
            import requests

            response = requests.get(
                f"https://api.telnyx.com/v2/messages/{message_id}",
                headers={"Authorization": f"Bearer {self._telnyx_api_key}"},
                timeout=10,
            )

            if response.status_code == 200:
                msg = response.json().get("data", {})
                to_list = msg.get("to", [])
                from_obj = msg.get("from", {})
                return {
                    "id": msg.get("id"),
                    "status": to_list[0].get("status") if to_list else "unknown",
                    "to": to_list[0].get("phone_number") if to_list else None,
                    "from": from_obj.get("phone_number") if from_obj else None,
                    "body": msg.get("text"),
                    "date_sent": msg.get("sent_at"),
                    "error_code": None,
                    "error_message": None,
                }
            else:
                logger.error(f"Telnyx status check failed: {response.status_code}")
                return None

        except Exception as e:
            logger.error(f"Error fetching Telnyx message status: {e}")
            return None


# SMS Templates (provider-agnostic)
class SMSTemplates:
    """Pre-defined SMS message templates"""

    @staticmethod
    def task_created(client_name: str, task_description: str) -> str:
        return f"Hi {client_name}, we've created a new task: {task_description}. We'll keep you updated!"

    @staticmethod
    def status_update(client_name: str, new_status: str) -> str:
        return f"Hi {client_name}, your loan status has been updated to: {new_status}."

    @staticmethod
    def document_request(client_name: str, document_name: str) -> str:
        return f"Hi {client_name}, please upload {document_name} to move forward with your application. Reply if you have questions!"

    @staticmethod
    def appointment_reminder(client_name: str, appointment_time: str) -> str:
        return f"Hi {client_name}, reminder: You have an appointment scheduled for {appointment_time}. See you then!"

    @staticmethod
    def welcome_message(client_name: str, loan_officer: str) -> str:
        return f"Hi {client_name}! Welcome to our mortgage process. I'm {loan_officer}, your loan officer. I'll keep you updated every step of the way!"

    @staticmethod
    def closing_congratulations(client_name: str) -> str:
        return f"Congratulations {client_name}! Your loan has closed. Thank you for choosing us!"


# Global instance - lazy initialization
_sms_client = None


def get_sms_client() -> SMSClient:
    """Get or create the global SMS client instance"""
    global _sms_client
    if _sms_client is None:
        _sms_client = SMSClient()
    return _sms_client


# Backwards compatibility - direct instance
sms_client = None


def _init_sms_client():
    """Initialize the global sms_client on first use"""
    global sms_client
    if sms_client is None:
        sms_client = get_sms_client()
    return sms_client
