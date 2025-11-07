"""
Microsoft Graph API Integration
Handles Teams, Outlook Email, and Calendar sync
"""
import os
import logging
from typing import Optional, List, Dict, Any
from datetime import datetime
from msal import ConfidentialClientApplication
import requests

logger = logging.getLogger(__name__)


class MicrosoftGraphClient:
    """Microsoft Graph API client for Teams, Email, and Calendar"""

    def __init__(self):
        self.client_id = os.getenv("MICROSOFT_CLIENT_ID", "")
        self.client_secret = os.getenv("MICROSOFT_CLIENT_SECRET", "")
        self.tenant_id = os.getenv("MICROSOFT_TENANT_ID", "")
        self.redirect_uri = os.getenv("MICROSOFT_REDIRECT_URI", "http://localhost:8000/auth/microsoft/callback")

        self.authority = f"https://login.microsoftonline.com/{self.tenant_id}"
        self.scopes = [
            "https://graph.microsoft.com/.default"
        ]

        if self.client_id and self.client_secret and self.tenant_id:
            self.app = ConfidentialClientApplication(
                client_id=self.client_id,
                client_credential=self.client_secret,
                authority=self.authority
            )
            self.enabled = True
            logger.info("Microsoft Graph API initialized successfully")
        else:
            self.app = None
            self.enabled = False
            logger.warning("Microsoft Graph API credentials not configured")

    def get_access_token(self) -> Optional[str]:
        """Get access token for Microsoft Graph API"""
        if not self.enabled:
            return None

        try:
            result = self.app.acquire_token_for_client(scopes=self.scopes)
            if "access_token" in result:
                return result["access_token"]
            else:
                logger.error(f"Failed to get access token: {result.get('error_description')}")
                return None
        except Exception as e:
            logger.error(f"Error getting access token: {e}")
            return None

    async def send_teams_message(
        self,
        channel_id: str,
        message: str,
        user_email: Optional[str] = None
    ) -> bool:
        """Send a message to Teams channel or user"""
        token = self.get_access_token()
        if not token:
            return False

        try:
            headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json"
            }

            if user_email:
                # Send direct message to user
                # First, get user ID
                user_response = requests.get(
                    f"https://graph.microsoft.com/v1.0/users/{user_email}",
                    headers=headers
                )
                if user_response.status_code != 200:
                    logger.error(f"Failed to get user: {user_response.text}")
                    return False

                user_id = user_response.json()["id"]

                # Create chat or send message
                chat_data = {
                    "chatType": "oneOnOne",
                    "members": [
                        {
                            "@odata.type": "#microsoft.graph.aadUserConversationMember",
                            "roles": ["owner"],
                            "user@odata.bind": f"https://graph.microsoft.com/v1.0/users('{user_id}')"
                        }
                    ]
                }

                chat_response = requests.post(
                    "https://graph.microsoft.com/v1.0/chats",
                    headers=headers,
                    json=chat_data
                )

                if chat_response.status_code in [200, 201]:
                    chat_id = chat_response.json()["id"]

                    # Send message to chat
                    message_data = {
                        "body": {
                            "content": message
                        }
                    }

                    message_response = requests.post(
                        f"https://graph.microsoft.com/v1.0/chats/{chat_id}/messages",
                        headers=headers,
                        json=message_data
                    )

                    return message_response.status_code in [200, 201]
            else:
                # Send to channel
                message_data = {
                    "body": {
                        "content": message
                    }
                }

                response = requests.post(
                    f"https://graph.microsoft.com/v1.0/teams/{channel_id}/channels/general/messages",
                    headers=headers,
                    json=message_data
                )

                return response.status_code in [200, 201]

        except Exception as e:
            logger.error(f"Error sending Teams message: {e}")
            return False

    async def send_email(
        self,
        to_email: str,
        subject: str,
        body: str,
        from_email: Optional[str] = None
    ) -> bool:
        """Send email via Outlook"""
        token = self.get_access_token()
        if not token:
            return False

        try:
            headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json"
            }

            # Use configured from_email or default
            sender = from_email or os.getenv("MICROSOFT_FROM_EMAIL", "me")

            message_data = {
                "message": {
                    "subject": subject,
                    "body": {
                        "contentType": "HTML",
                        "content": body
                    },
                    "toRecipients": [
                        {
                            "emailAddress": {
                                "address": to_email
                            }
                        }
                    ]
                }
            }

            response = requests.post(
                f"https://graph.microsoft.com/v1.0/users/{sender}/sendMail",
                headers=headers,
                json=message_data
            )

            return response.status_code in [200, 202]

        except Exception as e:
            logger.error(f"Error sending email: {e}")
            return False

    async def get_emails(
        self,
        user_email: str,
        folder: str = "inbox",
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """Get emails from Outlook"""
        token = self.get_access_token()
        if not token:
            return []

        try:
            headers = {
                "Authorization": f"Bearer {token}"
            }

            response = requests.get(
                f"https://graph.microsoft.com/v1.0/users/{user_email}/mailFolders/{folder}/messages?$top={limit}&$orderby=receivedDateTime desc",
                headers=headers
            )

            if response.status_code == 200:
                messages = response.json().get("value", [])
                return [{
                    "id": msg["id"],
                    "subject": msg.get("subject", ""),
                    "from": msg.get("from", {}).get("emailAddress", {}).get("address", ""),
                    "body": msg.get("body", {}).get("content", ""),
                    "received_at": msg.get("receivedDateTime", ""),
                    "has_attachments": msg.get("hasAttachments", False)
                } for msg in messages]

            return []

        except Exception as e:
            logger.error(f"Error getting emails: {e}")
            return []

    async def create_calendar_event(
        self,
        user_email: str,
        subject: str,
        start_time: datetime,
        end_time: datetime,
        attendees: List[str] = None,
        location: str = None,
        body: str = None
    ) -> Optional[str]:
        """Create calendar event in Outlook"""
        token = self.get_access_token()
        if not token:
            return None

        try:
            headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json"
            }

            event_data = {
                "subject": subject,
                "start": {
                    "dateTime": start_time.isoformat(),
                    "timeZone": "UTC"
                },
                "end": {
                    "dateTime": end_time.isoformat(),
                    "timeZone": "UTC"
                }
            }

            if attendees:
                event_data["attendees"] = [
                    {
                        "emailAddress": {"address": email},
                        "type": "required"
                    } for email in attendees
                ]

            if location:
                event_data["location"] = {"displayName": location}

            if body:
                event_data["body"] = {"contentType": "HTML", "content": body}

            response = requests.post(
                f"https://graph.microsoft.com/v1.0/users/{user_email}/events",
                headers=headers,
                json=event_data
            )

            if response.status_code in [200, 201]:
                return response.json().get("id")

            return None

        except Exception as e:
            logger.error(f"Error creating calendar event: {e}")
            return None

    async def sync_calendar_events(
        self,
        user_email: str,
        start_date: datetime,
        end_date: datetime
    ) -> List[Dict[str, Any]]:
        """Sync calendar events from Outlook"""
        token = self.get_access_token()
        if not token:
            return []

        try:
            headers = {
                "Authorization": f"Bearer {token}"
            }

            # Build filter query
            filter_query = f"start/dateTime ge '{start_date.isoformat()}' and end/dateTime le '{end_date.isoformat()}'"

            response = requests.get(
                f"https://graph.microsoft.com/v1.0/users/{user_email}/calendar/events?$filter={filter_query}",
                headers=headers
            )

            if response.status_code == 200:
                events = response.json().get("value", [])
                return [{
                    "id": evt["id"],
                    "subject": evt.get("subject", ""),
                    "start": evt.get("start", {}).get("dateTime", ""),
                    "end": evt.get("end", {}).get("dateTime", ""),
                    "location": evt.get("location", {}).get("displayName", ""),
                    "attendees": [a.get("emailAddress", {}).get("address", "") for a in evt.get("attendees", [])]
                } for evt in events]

            return []

        except Exception as e:
            logger.error(f"Error syncing calendar: {e}")
            return []


# Global instance
graph_client = MicrosoftGraphClient()
