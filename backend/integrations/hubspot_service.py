"""
HubSpot OAuth Integration
Handles CRM sync and API access for HubSpot
"""
import os
import logging
import secrets
from typing import Optional, Dict, Any
from datetime import datetime, timedelta
import requests
from urllib.parse import urlencode

logger = logging.getLogger(__name__)


class HubSpotClient:
    """HubSpot API client for CRM integration"""

    def __init__(self):
        self.client_id = os.getenv("HUBSPOT_CLIENT_ID", "")
        self.client_secret = os.getenv("HUBSPOT_CLIENT_SECRET", "")
        self.redirect_uri = os.getenv(
            "HUBSPOT_REDIRECT_URI",
            "https://app.perenniaai.com/api/v1/hubspot/callback"
        )

        self.auth_url = "https://app.hubspot.com/oauth/authorize"
        self.token_url = "https://api.hubapi.com/oauth/v1/token"
        self.api_base_url = "https://api.hubapi.com"

        # Scopes for CRM access
        self.scopes = [
            "crm.objects.contacts.read",
            "crm.objects.contacts.write",
            "crm.objects.deals.read",
            "crm.objects.deals.write",
            "crm.objects.companies.read",
            "crm.objects.companies.write",
        ]

        self.enabled = bool(self.client_id and self.client_secret)

        if self.enabled:
            logger.info("HubSpot API initialized successfully")
        else:
            logger.warning("HubSpot API credentials not configured")

    def get_authorization_url(self, state: str = None) -> str:
        """Generate HubSpot OAuth authorization URL"""
        params = {
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "scope": " ".join(self.scopes),
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
                "grant_type": "authorization_code",
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "redirect_uri": self.redirect_uri,
                "code": code
            }

            response = requests.post(
                self.token_url,
                data=data,
                headers={"Content-Type": "application/x-www-form-urlencoded"}
            )
            response.raise_for_status()

            token_data = response.json()
            logger.info("Successfully exchanged code for HubSpot access token")

            # Calculate expiration time
            expires_in = token_data.get("expires_in", 21600)  # Default 6 hours
            expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)

            return {
                "access_token": token_data.get("access_token"),
                "refresh_token": token_data.get("refresh_token"),
                "expires_in": expires_in,
                "expires_at": expires_at.isoformat(),
                "token_type": token_data.get("token_type", "bearer"),
            }

        except requests.exceptions.HTTPError as e:
            logger.error(f"HubSpot token exchange HTTP error: {e.response.text}")
            return None
        except Exception as e:
            logger.error(f"Error exchanging code for token: {e}")
            return None

    def refresh_access_token(self, refresh_token: str) -> Optional[Dict[str, Any]]:
        """Refresh an expired access token"""
        if not self.enabled:
            return None

        try:
            data = {
                "grant_type": "refresh_token",
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "refresh_token": refresh_token
            }

            response = requests.post(
                self.token_url,
                data=data,
                headers={"Content-Type": "application/x-www-form-urlencoded"}
            )
            response.raise_for_status()

            token_data = response.json()
            logger.info("Successfully refreshed HubSpot access token")

            expires_in = token_data.get("expires_in", 21600)
            expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)

            return {
                "access_token": token_data.get("access_token"),
                "refresh_token": token_data.get("refresh_token"),
                "expires_in": expires_in,
                "expires_at": expires_at.isoformat(),
                "token_type": token_data.get("token_type", "bearer"),
            }

        except Exception as e:
            logger.error(f"Error refreshing HubSpot access token: {e}")
            return None

    def get_access_token_info(self, access_token: str) -> Optional[Dict[str, Any]]:
        """Get information about an access token"""
        try:
            response = requests.get(
                f"{self.api_base_url}/oauth/v1/access-tokens/{access_token}"
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Error getting token info: {e}")
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
            logger.error(f"HubSpot API error: {e.response.text}")
            return None
        except Exception as e:
            logger.error(f"HubSpot request error: {e}")
            return None

    # Contact operations
    def get_contacts(
        self,
        access_token: str,
        limit: int = 100,
        after: str = None
    ) -> Optional[Dict[str, Any]]:
        """Get contacts from HubSpot"""
        params = {"limit": limit}
        if after:
            params["after"] = after

        return self._make_request(
            "GET",
            "/crm/v3/objects/contacts",
            access_token,
            params=params
        )

    def create_contact(
        self,
        access_token: str,
        properties: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Create a new contact in HubSpot"""
        return self._make_request(
            "POST",
            "/crm/v3/objects/contacts",
            access_token,
            data={"properties": properties}
        )

    def update_contact(
        self,
        access_token: str,
        contact_id: str,
        properties: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Update an existing contact"""
        return self._make_request(
            "PATCH",
            f"/crm/v3/objects/contacts/{contact_id}",
            access_token,
            data={"properties": properties}
        )

    def get_contact(
        self,
        access_token: str,
        contact_id: str
    ) -> Optional[Dict[str, Any]]:
        """Get a specific contact by ID"""
        return self._make_request(
            "GET",
            f"/crm/v3/objects/contacts/{contact_id}",
            access_token
        )

    # Deal operations
    def get_deals(
        self,
        access_token: str,
        limit: int = 100,
        after: str = None
    ) -> Optional[Dict[str, Any]]:
        """Get deals from HubSpot"""
        params = {"limit": limit}
        if after:
            params["after"] = after

        return self._make_request(
            "GET",
            "/crm/v3/objects/deals",
            access_token,
            params=params
        )

    def create_deal(
        self,
        access_token: str,
        properties: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Create a new deal in HubSpot"""
        return self._make_request(
            "POST",
            "/crm/v3/objects/deals",
            access_token,
            data={"properties": properties}
        )

    def update_deal(
        self,
        access_token: str,
        deal_id: str,
        properties: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Update an existing deal"""
        return self._make_request(
            "PATCH",
            f"/crm/v3/objects/deals/{deal_id}",
            access_token,
            data={"properties": properties}
        )

    # Company operations
    def get_companies(
        self,
        access_token: str,
        limit: int = 100,
        after: str = None
    ) -> Optional[Dict[str, Any]]:
        """Get companies from HubSpot"""
        params = {"limit": limit}
        if after:
            params["after"] = after

        return self._make_request(
            "GET",
            "/crm/v3/objects/companies",
            access_token,
            params=params
        )

    def search_contacts(
        self,
        access_token: str,
        query: str,
        properties: list = None
    ) -> Optional[Dict[str, Any]]:
        """Search contacts by email or name"""
        data = {
            "query": query,
            "limit": 100
        }
        if properties:
            data["properties"] = properties

        return self._make_request(
            "POST",
            "/crm/v3/objects/contacts/search",
            access_token,
            data=data
        )


# Global instance
hubspot_client = HubSpotClient()
