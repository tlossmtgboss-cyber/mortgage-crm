"""
Salesforce OAuth Integration
Handles CRM sync and API access
"""
import os
import logging
from typing import Optional, Dict, Any
from datetime import datetime
import requests
from urllib.parse import urlencode

logger = logging.getLogger(__name__)


class SalesforceClient:
    """Salesforce API client for CRM integration"""

    def __init__(self):
        self.client_id = os.getenv("SALESFORCE_CLIENT_ID", "")
        self.client_secret = os.getenv("SALESFORCE_CLIENT_SECRET", "")
        self.redirect_uri = os.getenv("SALESFORCE_REDIRECT_URI", "http://localhost:3000/integrations/salesforce/callback")
        self.domain = os.getenv("SALESFORCE_DOMAIN", "login.salesforce.com")  # or test.salesforce.com for sandbox

        self.auth_url = f"https://{self.domain}/services/oauth2/authorize"
        self.token_url = f"https://{self.domain}/services/oauth2/token"
        self.revoke_url = f"https://{self.domain}/services/oauth2/revoke"

        self.enabled = bool(self.client_id and self.client_secret)

        if self.enabled:
            logger.info("Salesforce API initialized successfully")
        else:
            logger.warning("Salesforce API credentials not configured")

    def get_authorization_url(self, state: str = None) -> str:
        """Generate Salesforce OAuth authorization URL"""
        params = {
            "response_type": "code",
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "scope": "api refresh_token offline_access",
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
                "code": code,
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "redirect_uri": self.redirect_uri
            }

            response = requests.post(self.token_url, data=data)
            response.raise_for_status()

            token_data = response.json()
            logger.info("Successfully exchanged code for Salesforce access token")

            return {
                "access_token": token_data.get("access_token"),
                "refresh_token": token_data.get("refresh_token"),
                "instance_url": token_data.get("instance_url"),
                "id": token_data.get("id"),
                "token_type": token_data.get("token_type"),
                "issued_at": token_data.get("issued_at"),
                "signature": token_data.get("signature")
            }

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
                "refresh_token": refresh_token,
                "client_id": self.client_id,
                "client_secret": self.client_secret
            }

            response = requests.post(self.token_url, data=data)
            response.raise_for_status()

            token_data = response.json()
            logger.info("Successfully refreshed Salesforce access token")

            return {
                "access_token": token_data.get("access_token"),
                "instance_url": token_data.get("instance_url"),
                "id": token_data.get("id"),
                "token_type": token_data.get("token_type"),
                "issued_at": token_data.get("issued_at"),
                "signature": token_data.get("signature")
            }

        except Exception as e:
            logger.error(f"Error refreshing access token: {e}")
            return None

    def revoke_token(self, token: str) -> bool:
        """Revoke an access or refresh token"""
        if not self.enabled:
            return False

        try:
            data = {"token": token}
            response = requests.post(self.revoke_url, data=data)
            response.raise_for_status()

            logger.info("Successfully revoked Salesforce token")
            return True

        except Exception as e:
            logger.error(f"Error revoking token: {e}")
            return False

    def get_user_info(self, access_token: str, id_url: str) -> Optional[Dict[str, Any]]:
        """Get user information from Salesforce"""
        try:
            headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json"
            }

            response = requests.get(id_url, headers=headers)
            response.raise_for_status()

            return response.json()

        except Exception as e:
            logger.error(f"Error getting user info: {e}")
            return None

    def query(self, access_token: str, instance_url: str, soql_query: str) -> Optional[Dict[str, Any]]:
        """Execute a SOQL query"""
        try:
            headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json"
            }

            url = f"{instance_url}/services/data/v58.0/query/"
            params = {"q": soql_query}

            response = requests.get(url, headers=headers, params=params)
            response.raise_for_status()

            return response.json()

        except Exception as e:
            logger.error(f"Error executing SOQL query: {e}")
            return None

    def create_record(
        self,
        access_token: str,
        instance_url: str,
        sobject_type: str,
        data: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Create a new Salesforce record"""
        try:
            headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json"
            }

            url = f"{instance_url}/services/data/v58.0/sobjects/{sobject_type}/"

            response = requests.post(url, headers=headers, json=data)
            response.raise_for_status()

            return response.json()

        except Exception as e:
            logger.error(f"Error creating Salesforce record: {e}")
            return None

    def update_record(
        self,
        access_token: str,
        instance_url: str,
        sobject_type: str,
        record_id: str,
        data: Dict[str, Any]
    ) -> bool:
        """Update an existing Salesforce record"""
        try:
            headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json"
            }

            url = f"{instance_url}/services/data/v58.0/sobjects/{sobject_type}/{record_id}"

            response = requests.patch(url, headers=headers, json=data)
            response.raise_for_status()

            return True

        except Exception as e:
            logger.error(f"Error updating Salesforce record: {e}")
            return False

    def get_record(
        self,
        access_token: str,
        instance_url: str,
        sobject_type: str,
        record_id: str
    ) -> Optional[Dict[str, Any]]:
        """Get a Salesforce record by ID"""
        try:
            headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json"
            }

            url = f"{instance_url}/services/data/v58.0/sobjects/{sobject_type}/{record_id}"

            response = requests.get(url, headers=headers)
            response.raise_for_status()

            return response.json()

        except Exception as e:
            logger.error(f"Error getting Salesforce record: {e}")
            return None


# Global instance
salesforce_client = SalesforceClient()
