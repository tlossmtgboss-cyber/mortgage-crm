"""
Slack OAuth Integration
Handles OAuth authentication and messaging operations for Slack
"""
import os
import logging
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
import requests
from urllib.parse import urlencode

logger = logging.getLogger(__name__)

# Slack OAuth scopes
SLACK_SCOPES = [
    "channels:read",
    "channels:write",
    "chat:write",
    "users:read",
    "users:read.email",
    "team:read",
    "im:write",
    "im:read",
]

# Bot scopes for app-level access
SLACK_BOT_SCOPES = [
    "channels:read",
    "chat:write",
    "users:read",
    "team:read",
]


class SlackClient:
    """Slack API client for OAuth and messaging operations"""

    def __init__(self):
        self.client_id = os.getenv("SLACK_CLIENT_ID", "")
        self.client_secret = os.getenv("SLACK_CLIENT_SECRET", "")
        self.redirect_uri = os.getenv(
            "SLACK_REDIRECT_URI",
            "https://app.perenniaai.com/api/v1/slack/callback"
        )

        self.auth_url = "https://slack.com/oauth/v2/authorize"
        self.token_url = "https://slack.com/api/oauth.v2.access"
        self.api_base_url = "https://slack.com/api"

        self.enabled = bool(self.client_id and self.client_secret)

        if self.enabled:
            logger.info("Slack API initialized successfully")
        else:
            logger.warning("Slack API credentials not configured")

    def get_authorization_url(self, state: str = None) -> str:
        """Generate Slack OAuth authorization URL"""
        params = {
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "scope": ",".join(SLACK_SCOPES),
            "user_scope": ",".join(SLACK_SCOPES),
        }

        if state:
            params["state"] = state

        return f"{self.auth_url}?{urlencode(params)}"

    def exchange_code_for_token(self, code: str) -> Optional[Dict[str, Any]]:
        """Exchange authorization code for access token"""
        if not self.enabled:
            return None

        try:
            data = {
                "code": code,
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "redirect_uri": self.redirect_uri,
            }

            response = requests.post(
                self.token_url,
                data=data,
                headers={"Content-Type": "application/x-www-form-urlencoded"}
            )
            response.raise_for_status()

            token_data = response.json()

            if not token_data.get("ok"):
                logger.error(f"Slack token exchange error: {token_data.get('error')}")
                return None

            logger.info("Successfully exchanged code for Slack access token")

            # Slack tokens don't expire by default, but we set a long expiry
            expires_at = datetime.now(timezone.utc) + timedelta(days=365)

            # Get user token if available
            authed_user = token_data.get("authed_user", {})

            return {
                "access_token": token_data.get("access_token"),
                "user_access_token": authed_user.get("access_token"),
                "refresh_token": token_data.get("refresh_token"),
                "expires_at": expires_at.isoformat(),
                "token_type": token_data.get("token_type", "bearer"),
                "scope": token_data.get("scope"),
                "team_id": token_data.get("team", {}).get("id"),
                "team_name": token_data.get("team", {}).get("name"),
                "bot_user_id": token_data.get("bot_user_id"),
                "user_id": authed_user.get("id"),
            }

        except requests.exceptions.HTTPError as e:
            logger.error(f"Slack token exchange HTTP error: {e.response.text}")
            return None
        except Exception as e:
            logger.error(f"Error exchanging code for token: {e}")
            return None

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

            url = f"{self.api_base_url}/{endpoint}"

            response = requests.request(
                method=method,
                url=url,
                headers=headers,
                json=data,
                params=params
            )
            response.raise_for_status()

            result = response.json()
            if not result.get("ok"):
                logger.error(f"Slack API error: {result.get('error')}")
                return None

            return result

        except requests.exceptions.HTTPError as e:
            logger.error(f"Slack API HTTP error: {e.response.text}")
            return None
        except Exception as e:
            logger.error(f"Slack request error: {e}")
            return None

    # User and team operations
    def get_user_info(self, access_token: str, user_id: str = None) -> Optional[Dict[str, Any]]:
        """Get user info from Slack"""
        if user_id:
            return self._make_request("GET", "users.info", access_token, params={"user": user_id})
        return self._make_request("GET", "users.identity", access_token)

    def get_team_info(self, access_token: str) -> Optional[Dict[str, Any]]:
        """Get team/workspace info"""
        return self._make_request("GET", "team.info", access_token)

    def list_users(self, access_token: str, limit: int = 100) -> Optional[Dict[str, Any]]:
        """List users in the workspace"""
        return self._make_request("GET", "users.list", access_token, params={"limit": limit})

    # Channel operations
    def list_channels(self, access_token: str, limit: int = 100) -> Optional[Dict[str, Any]]:
        """List channels in the workspace"""
        return self._make_request(
            "GET",
            "conversations.list",
            access_token,
            params={"limit": limit, "types": "public_channel,private_channel"}
        )

    def get_channel_info(self, access_token: str, channel_id: str) -> Optional[Dict[str, Any]]:
        """Get channel information"""
        return self._make_request("GET", "conversations.info", access_token, params={"channel": channel_id})

    # Messaging operations
    def send_message(
        self,
        access_token: str,
        channel: str,
        text: str,
        blocks: List[Dict] = None,
        thread_ts: str = None
    ) -> Optional[Dict[str, Any]]:
        """Send a message to a channel or user"""
        data = {
            "channel": channel,
            "text": text,
        }

        if blocks:
            data["blocks"] = blocks
        if thread_ts:
            data["thread_ts"] = thread_ts

        return self._make_request("POST", "chat.postMessage", access_token, data=data)

    def send_direct_message(
        self,
        access_token: str,
        user_id: str,
        text: str,
        blocks: List[Dict] = None
    ) -> Optional[Dict[str, Any]]:
        """Send a direct message to a user"""
        # First open a DM channel
        dm_response = self._make_request(
            "POST",
            "conversations.open",
            access_token,
            data={"users": user_id}
        )

        if not dm_response or not dm_response.get("channel"):
            return None

        channel_id = dm_response["channel"]["id"]
        return self.send_message(access_token, channel_id, text, blocks)

    def update_message(
        self,
        access_token: str,
        channel: str,
        ts: str,
        text: str,
        blocks: List[Dict] = None
    ) -> Optional[Dict[str, Any]]:
        """Update an existing message"""
        data = {
            "channel": channel,
            "ts": ts,
            "text": text,
        }

        if blocks:
            data["blocks"] = blocks

        return self._make_request("POST", "chat.update", access_token, data=data)

    def delete_message(
        self,
        access_token: str,
        channel: str,
        ts: str
    ) -> Optional[Dict[str, Any]]:
        """Delete a message"""
        return self._make_request(
            "POST",
            "chat.delete",
            access_token,
            data={"channel": channel, "ts": ts}
        )

    # Notification helper
    def send_notification(
        self,
        access_token: str,
        channel_or_user: str,
        title: str,
        message: str,
        color: str = "#36a64f",
        fields: List[Dict] = None
    ) -> Optional[Dict[str, Any]]:
        """Send a rich notification with attachment"""
        blocks = [
            {
                "type": "header",
                "text": {"type": "plain_text", "text": title}
            },
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": message}
            }
        ]

        if fields:
            field_block = {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*{f['title']}*\n{f['value']}"}
                    for f in fields
                ]
            }
            blocks.append(field_block)

        return self.send_message(access_token, channel_or_user, message, blocks=blocks)


# Global instance
slack_client = SlackClient()
