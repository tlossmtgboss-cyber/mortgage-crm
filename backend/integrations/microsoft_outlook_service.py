"""
Microsoft Outlook OAuth Integration
Handles OAuth authentication for Outlook Calendar and Outlook Email via Microsoft Graph API
"""
import os
import logging
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
import requests
from urllib.parse import urlencode

logger = logging.getLogger(__name__)

# Microsoft Graph OAuth scopes for Calendar and Email
OUTLOOK_CALENDAR_SCOPES = [
    "offline_access",
    "User.Read",
    "Calendars.ReadWrite",
    "Calendars.Read.Shared",
]

OUTLOOK_EMAIL_SCOPES = [
    "offline_access",
    "User.Read",
    "Mail.ReadWrite",
    "Mail.Send",
]

# Combined scopes for users who connect both
OUTLOOK_ALL_SCOPES = list(set(OUTLOOK_CALENDAR_SCOPES + OUTLOOK_EMAIL_SCOPES))


class MicrosoftOutlookClient:
    """Microsoft Outlook API client for OAuth and Calendar/Email operations"""

    def __init__(self):
        self.client_id = os.getenv("MICROSOFT_CLIENT_ID", "")
        self.client_secret = os.getenv("MICROSOFT_CLIENT_SECRET", "")
        self.tenant_id = os.getenv("MICROSOFT_TENANT_ID", "common")  # 'common' for multi-tenant
        self.redirect_uri = os.getenv(
            "MICROSOFT_REDIRECT_URI",
            "https://api.perenniaai.com/oauth/microsoft/callback"
        )

        # Microsoft OAuth endpoints - using 'common' for multi-tenant support
        self.auth_url = f"https://login.microsoftonline.com/{self.tenant_id}/oauth2/v2.0/authorize"
        self.token_url = f"https://login.microsoftonline.com/{self.tenant_id}/oauth2/v2.0/token"
        self.api_base_url = "https://graph.microsoft.com/v1.0"

        self.enabled = bool(self.client_id and self.client_secret)
        self.last_token_error = None  # Set by exchange_code_for_token on failure

        if self.enabled:
            logger.info("Microsoft Outlook API initialized successfully")
        else:
            logger.warning("Microsoft Outlook API credentials not configured")

    def get_authorization_url(self, state: str = None, integration_type: str = "calendar") -> str:
        """
        Generate Microsoft OAuth authorization URL

        Args:
            state: Optional state parameter for CSRF protection
            integration_type: 'calendar', 'email', or 'all' to determine scopes
        """
        # Choose scopes based on integration type
        if integration_type == "email":
            scopes = OUTLOOK_EMAIL_SCOPES
        elif integration_type == "all":
            scopes = OUTLOOK_ALL_SCOPES
        else:
            scopes = OUTLOOK_CALENDAR_SCOPES

        params = {
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "response_type": "code",
            "scope": " ".join(scopes),
            "response_mode": "query",
            "prompt": "consent",  # Force consent to ensure we get refresh token
        }

        if state:
            params["state"] = state

        return f"{self.auth_url}?{urlencode(params)}"

    def exchange_code_for_token(self, code: str) -> Optional[Dict[str, Any]]:
        """Exchange authorization code for access token.

        Returns token dict on success, or None on failure.
        On failure, self.last_token_error is set with the error details.
        """
        self.last_token_error = None

        if not self.enabled:
            self.last_token_error = "Microsoft OAuth not configured (missing client_id or client_secret)"
            logger.error(self.last_token_error)
            return None

        try:
            data = {
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "code": code,
                "grant_type": "authorization_code",
                "redirect_uri": self.redirect_uri,
            }

            response = requests.post(
                self.token_url,
                data=data,
                headers={"Content-Type": "application/x-www-form-urlencoded"}
            )

            if response.status_code != 200:
                error_data = {}
                try:
                    error_data = response.json()
                except Exception:
                    pass
                error_code = error_data.get("error", "unknown")
                error_desc = error_data.get("error_description", response.text[:200])
                logger.error(f"Microsoft token exchange failed [{response.status_code}]: {error_code} - {error_desc}")

                # Map common AADSTS errors to user-friendly messages
                if "AADSTS7000215" in str(error_desc):
                    self.last_token_error = "Microsoft client secret has expired. Generate a new secret in Azure Portal > App registrations > Certificates & secrets."
                elif "AADSTS50011" in str(error_desc):
                    self.last_token_error = "Redirect URI mismatch. Check Azure AD app registration redirect URIs."
                elif "AADSTS70008" in str(error_desc):
                    self.last_token_error = "Authorization code expired. Please try connecting again."
                elif "AADSTS54005" in str(error_desc):
                    self.last_token_error = "Authorization code already used. Please try connecting again."
                elif "AADSTS700016" in str(error_desc):
                    self.last_token_error = "Application not found in Azure AD. Check MICROSOFT_CLIENT_ID."
                else:
                    self.last_token_error = f"Microsoft error: {error_desc[:200]}"
                return None

            token_data = response.json()
            logger.info("Successfully exchanged code for Microsoft access token")

            # Calculate expiration time
            expires_in = token_data.get("expires_in", 3600)
            expires_at = datetime.utcnow() + timedelta(seconds=expires_in)

            return {
                "access_token": token_data.get("access_token"),
                "refresh_token": token_data.get("refresh_token"),
                "expires_in": expires_in,
                "expires_at": expires_at.isoformat(),
                "token_type": token_data.get("token_type", "Bearer"),
                "scope": token_data.get("scope"),
            }

        except Exception as e:
            self.last_token_error = f"Token exchange error: {str(e)}"
            logger.error(f"Error exchanging code for token: {e}")
            return None

    def refresh_access_token(self, refresh_token: str) -> Optional[Dict[str, Any]]:
        """Refresh an expired access token"""
        if not self.enabled:
            return None

        try:
            data = {
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "refresh_token": refresh_token,
                "grant_type": "refresh_token",
            }

            response = requests.post(
                self.token_url,
                data=data,
                headers={"Content-Type": "application/x-www-form-urlencoded"}
            )
            response.raise_for_status()

            token_data = response.json()
            logger.info("Successfully refreshed Microsoft access token")

            expires_in = token_data.get("expires_in", 3600)
            expires_at = datetime.utcnow() + timedelta(seconds=expires_in)

            return {
                "access_token": token_data.get("access_token"),
                "refresh_token": token_data.get("refresh_token"),
                "expires_in": expires_in,
                "expires_at": expires_at.isoformat(),
                "token_type": token_data.get("token_type", "Bearer"),
            }

        except Exception as e:
            logger.error(f"Error refreshing Microsoft access token: {e}")
            return None

    def get_user_info(self, access_token: str) -> Optional[Dict[str, Any]]:
        """Get current user info from Microsoft Graph"""
        return self._make_request("GET", "/me", access_token)

    def _make_request(
        self,
        method: str,
        endpoint: str,
        access_token: str,
        data: Dict = None,
        params: Dict = None
    ) -> Optional[Dict[str, Any]]:
        """Make an authenticated API request"""
        try:
            headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json"
            }

            url = f"{self.api_base_url}{endpoint}"

            response = requests.request(
                method=method,
                url=url,
                headers=headers,
                json=data,
                params=params
            )
            response.raise_for_status()

            return response.json() if response.text else {}

        except requests.exceptions.HTTPError as e:
            logger.error(f"Microsoft Graph API error: {e.response.text}")
            return None
        except Exception as e:
            logger.error(f"Microsoft request error: {e}")
            return None

    # Calendar operations
    def list_calendars(self, access_token: str) -> Optional[Dict[str, Any]]:
        """List user's calendars"""
        return self._make_request("GET", "/me/calendars", access_token)

    def list_events(
        self,
        access_token: str,
        calendar_id: str = None,
        start_time: datetime = None,
        end_time: datetime = None,
        top: int = 50
    ) -> Optional[Dict[str, Any]]:
        """List calendar events"""
        endpoint = f"/me/calendars/{calendar_id}/events" if calendar_id else "/me/events"

        params = {"$top": top, "$orderby": "start/dateTime"}

        if start_time and end_time:
            params["$filter"] = (
                f"start/dateTime ge '{start_time.isoformat()}' and "
                f"end/dateTime le '{end_time.isoformat()}'"
            )

        return self._make_request("GET", endpoint, access_token, params=params)

    def create_event(
        self,
        access_token: str,
        subject: str,
        start_time: datetime,
        end_time: datetime,
        attendees: List[str] = None,
        location: str = None,
        body: str = None,
        is_online_meeting: bool = False,
        calendar_id: str = None
    ) -> Optional[Dict[str, Any]]:
        """Create a calendar event"""
        endpoint = f"/me/calendars/{calendar_id}/events" if calendar_id else "/me/events"

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

        if is_online_meeting:
            event_data["isOnlineMeeting"] = True
            event_data["onlineMeetingProvider"] = "teamsForBusiness"

        return self._make_request("POST", endpoint, access_token, data=event_data)

    def update_event(
        self,
        access_token: str,
        event_id: str,
        updates: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Update an existing event"""
        return self._make_request("PATCH", f"/me/events/{event_id}", access_token, data=updates)

    def delete_event(self, access_token: str, event_id: str) -> bool:
        """Delete a calendar event"""
        try:
            response = requests.delete(
                f"{self.api_base_url}/me/events/{event_id}",
                headers={"Authorization": f"Bearer {access_token}"}
            )
            return response.status_code == 204
        except Exception as e:
            logger.error(f"Error deleting event: {e}")
            return False

    # Email operations
    def list_messages(
        self,
        access_token: str,
        folder: str = "inbox",
        top: int = 25,
        filter_unread: bool = False
    ) -> Optional[Dict[str, Any]]:
        """List email messages"""
        params = {
            "$top": top,
            "$orderby": "receivedDateTime desc",
            "$select": "id,subject,from,toRecipients,receivedDateTime,bodyPreview,hasAttachments,isRead"
        }

        if filter_unread:
            params["$filter"] = "isRead eq false"

        return self._make_request("GET", f"/me/mailFolders/{folder}/messages", access_token, params=params)

    def get_message(self, access_token: str, message_id: str) -> Optional[Dict[str, Any]]:
        """Get a specific email message"""
        return self._make_request("GET", f"/me/messages/{message_id}", access_token)

    def send_message(
        self,
        access_token: str,
        to_recipients: List[str],
        subject: str,
        body: str,
        cc_recipients: List[str] = None,
        is_html: bool = True
    ) -> bool:
        """Send an email message"""
        message_data = {
            "message": {
                "subject": subject,
                "body": {
                    "contentType": "HTML" if is_html else "Text",
                    "content": body
                },
                "toRecipients": [
                    {"emailAddress": {"address": email}} for email in to_recipients
                ]
            }
        }

        if cc_recipients:
            message_data["message"]["ccRecipients"] = [
                {"emailAddress": {"address": email}} for email in cc_recipients
            ]

        result = self._make_request("POST", "/me/sendMail", access_token, data=message_data)
        return result is not None

    def delete_message(self, access_token: str, message_id: str) -> bool:
        """Delete an email message"""
        try:
            response = requests.delete(
                f"{self.api_base_url}/me/messages/{message_id}",
                headers={"Authorization": f"Bearer {access_token}"}
            )
            return response.status_code == 204
        except Exception as e:
            logger.error(f"Error deleting message: {e}")
            return False

    def mark_message_as_read(self, access_token: str, message_id: str) -> bool:
        """Mark an email message as read"""
        result = self._make_request(
            "PATCH",
            f"/me/messages/{message_id}",
            access_token,
            data={"isRead": True}
        )
        return result is not None


# Global instance
microsoft_outlook_client = MicrosoftOutlookClient()
