"""
Twilio SMS Integration
Handles sending and receiving SMS messages
"""
import os
import logging
from typing import Optional, List, Dict
from twilio.rest import Client
from twilio.base.exceptions import TwilioRestException

logger = logging.getLogger(__name__)


class TwilioSMSClient:
    """Twilio SMS client for text messaging"""

    def __init__(self):
        self.account_sid = os.getenv("TWILIO_ACCOUNT_SID", "")
        self.auth_token = os.getenv("TWILIO_AUTH_TOKEN", "")
        self.from_number = os.getenv("TWILIO_PHONE_NUMBER", "")

        if self.account_sid and self.auth_token and self.from_number:
            try:
                self.client = Client(self.account_sid, self.auth_token)
                self.enabled = True
                logger.info("Twilio SMS initialized successfully")
            except Exception as e:
                self.client = None
                self.enabled = False
                logger.error(f"Failed to initialize Twilio: {e}")
        else:
            self.client = None
            self.enabled = False
            logger.warning("Twilio SMS credentials not configured")

    async def send_sms(
        self,
        to_number: str,
        message: str,
        media_url: Optional[str] = None
    ) -> Optional[str]:
        """
        Send SMS message
        Returns message SID if successful, None otherwise
        """
        if not self.enabled:
            logger.warning("Twilio not enabled, cannot send SMS")
            return None

        try:
            # Ensure phone number is in E.164 format
            if not to_number.startswith("+"):
                to_number = f"+1{to_number}"  # Assume US number if no country code

            kwargs = {
                "body": message,
                "from_": self.from_number,
                "to": to_number
            }

            if media_url:
                kwargs["media_url"] = [media_url]

            message_obj = self.client.messages.create(**kwargs)

            logger.info(f"SMS sent successfully. SID: {message_obj.sid}")
            return message_obj.sid

        except TwilioRestException as e:
            logger.error(f"Twilio error sending SMS: {e}")
            return None
        except Exception as e:
            logger.error(f"Error sending SMS: {e}")
            return None

    async def send_bulk_sms(
        self,
        recipients: List[Dict[str, str]],
        message_template: str
    ) -> Dict[str, any]:
        """
        Send SMS to multiple recipients
        recipients: List of dicts with 'phone' and optional 'name' keys
        Returns dict with success/failure counts
        """
        results = {
            "sent": 0,
            "failed": 0,
            "message_sids": []
        }

        for recipient in recipients:
            phone = recipient.get("phone")
            name = recipient.get("name", "")

            # Personalize message if name is provided
            message = message_template.replace("{name}", name) if name else message_template

            sid = await self.send_sms(phone, message)

            if sid:
                results["sent"] += 1
                results["message_sids"].append(sid)
            else:
                results["failed"] += 1

        return results

    async def get_message_status(self, message_sid: str) -> Optional[Dict[str, any]]:
        """Get status of a sent message"""
        if not self.enabled:
            return None

        try:
            message = self.client.messages(message_sid).fetch()

            return {
                "sid": message.sid,
                "status": message.status,
                "to": message.to,
                "from": message.from_,
                "body": message.body,
                "date_sent": message.date_sent,
                "error_code": message.error_code,
                "error_message": message.error_message
            }

        except TwilioRestException as e:
            logger.error(f"Error fetching message status: {e}")
            return None

    async def get_recent_messages(
        self,
        phone_number: Optional[str] = None,
        limit: int = 20
    ) -> List[Dict[str, any]]:
        """Get recent messages, optionally filtered by phone number"""
        if not self.enabled:
            return []

        try:
            kwargs = {"limit": limit}
            if phone_number:
                if not phone_number.startswith("+"):
                    phone_number = f"+1{phone_number}"
                kwargs["to"] = phone_number

            messages = self.client.messages.list(**kwargs)

            return [{
                "sid": msg.sid,
                "to": msg.to,
                "from": msg.from_,
                "body": msg.body,
                "status": msg.status,
                "direction": msg.direction,
                "date_sent": msg.date_sent.isoformat() if msg.date_sent else None
            } for msg in messages]

        except TwilioRestException as e:
            logger.error(f"Error getting messages: {e}")
            return []


# SMS Templates
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


# Global instance
sms_client = TwilioSMSClient()
