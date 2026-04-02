"""
DocuSign OAuth Integration
Handles OAuth authentication and e-signature operations for DocuSign
"""
import os
import logging
import base64
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta, timezone
import requests
from urllib.parse import urlencode

logger = logging.getLogger(__name__)

# DocuSign OAuth scopes
DOCUSIGN_SCOPES = [
    "signature",
    "extended",
    "impersonation",
]


class DocuSignClient:
    """DocuSign API client for OAuth and e-signature operations"""

    def __init__(self):
        self.client_id = os.getenv("DOCUSIGN_CLIENT_ID", "")
        self.client_secret = os.getenv("DOCUSIGN_CLIENT_SECRET", "")
        self.redirect_uri = os.getenv(
            "DOCUSIGN_REDIRECT_URI",
            "https://app.perenniaai.com/api/v1/docusign/callback"
        )

        # Use demo environment by default, switch to production when ready
        self.environment = os.getenv("DOCUSIGN_ENVIRONMENT", "demo")

        if self.environment == "production":
            self.auth_url = "https://account.docusign.com/oauth/auth"
            self.token_url = "https://account.docusign.com/oauth/token"
            self.userinfo_url = "https://account.docusign.com/oauth/userinfo"
        else:
            self.auth_url = "https://account-d.docusign.com/oauth/auth"
            self.token_url = "https://account-d.docusign.com/oauth/token"
            self.userinfo_url = "https://account-d.docusign.com/oauth/userinfo"

        self.enabled = bool(self.client_id and self.client_secret)

        if self.enabled:
            logger.info(f"DocuSign API initialized successfully (environment: {self.environment})")
        else:
            logger.warning("DocuSign API credentials not configured")

    def _get_basic_auth_header(self) -> str:
        """Get Base64 encoded client credentials for Basic auth"""
        credentials = f"{self.client_id}:{self.client_secret}"
        return base64.b64encode(credentials.encode()).decode()

    def get_authorization_url(self, state: str = None) -> str:
        """Generate DocuSign OAuth authorization URL"""
        params = {
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "response_type": "code",
            "scope": " ".join(DOCUSIGN_SCOPES),
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
                "grant_type": "authorization_code",
            }

            response = requests.post(
                self.token_url,
                data=data,
                headers={
                    "Authorization": f"Basic {self._get_basic_auth_header()}",
                    "Content-Type": "application/x-www-form-urlencoded"
                }
            )
            response.raise_for_status()

            token_data = response.json()
            logger.info("Successfully exchanged code for DocuSign access token")

            # Calculate expiration time
            expires_in = token_data.get("expires_in", 28800)  # Default 8 hours
            expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)

            return {
                "access_token": token_data.get("access_token"),
                "refresh_token": token_data.get("refresh_token"),
                "expires_in": expires_in,
                "expires_at": expires_at.isoformat(),
                "token_type": token_data.get("token_type", "Bearer"),
                "scope": token_data.get("scope"),
            }

        except requests.exceptions.HTTPError as e:
            logger.error(f"DocuSign token exchange HTTP error: {e.response.text}")
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
                "refresh_token": refresh_token,
                "grant_type": "refresh_token",
            }

            response = requests.post(
                self.token_url,
                data=data,
                headers={
                    "Authorization": f"Basic {self._get_basic_auth_header()}",
                    "Content-Type": "application/x-www-form-urlencoded"
                }
            )
            response.raise_for_status()

            token_data = response.json()
            logger.info("Successfully refreshed DocuSign access token")

            expires_in = token_data.get("expires_in", 28800)
            expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)

            return {
                "access_token": token_data.get("access_token"),
                "refresh_token": token_data.get("refresh_token"),
                "expires_in": expires_in,
                "expires_at": expires_at.isoformat(),
                "token_type": token_data.get("token_type", "Bearer"),
            }

        except Exception as e:
            logger.error(f"Error refreshing DocuSign access token: {e}")
            return None

    def get_user_info(self, access_token: str) -> Optional[Dict[str, Any]]:
        """Get user info from DocuSign"""
        try:
            response = requests.get(
                self.userinfo_url,
                headers={"Authorization": f"Bearer {access_token}"}
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Error getting user info: {e}")
            return None

    def _get_api_base_url(self, access_token: str, account_id: str = None) -> Optional[str]:
        """Get the base URL for API calls based on user's account"""
        user_info = self.get_user_info(access_token)
        if not user_info:
            return None

        accounts = user_info.get("accounts", [])
        if not accounts:
            return None

        # Use specified account or default account
        account = None
        if account_id:
            account = next((a for a in accounts if a.get("account_id") == account_id), None)
        if not account:
            account = next((a for a in accounts if a.get("is_default")), accounts[0])

        return account.get("base_uri") + "/restapi"

    def _make_request(
        self,
        method: str,
        endpoint: str,
        access_token: str,
        account_id: str,
        data: Dict = None,
        params: Dict = None,
        files: Dict = None
    ) -> Optional[Dict[str, Any]]:
        """Make an authenticated API request"""
        try:
            base_url = self._get_api_base_url(access_token, account_id)
            if not base_url:
                logger.error("Could not determine DocuSign API base URL")
                return None

            headers = {
                "Authorization": f"Bearer {access_token}",
            }

            if not files:
                headers["Content-Type"] = "application/json"

            url = f"{base_url}/v2.1/accounts/{account_id}{endpoint}"

            response = requests.request(
                method=method,
                url=url,
                headers=headers,
                json=data if not files else None,
                params=params,
                files=files
            )
            response.raise_for_status()

            return response.json() if response.text else {}

        except requests.exceptions.HTTPError as e:
            logger.error(f"DocuSign API error: {e.response.text}")
            return None
        except Exception as e:
            logger.error(f"DocuSign request error: {e}")
            return None

    # Envelope (document) operations
    def list_envelopes(
        self,
        access_token: str,
        account_id: str,
        from_date: datetime = None,
        status: str = None,
        count: int = 100
    ) -> Optional[Dict[str, Any]]:
        """List envelopes (documents) for an account"""
        params = {"count": count}

        if from_date:
            params["from_date"] = from_date.isoformat()
        if status:
            params["status"] = status

        return self._make_request(
            "GET",
            "/envelopes",
            access_token,
            account_id,
            params=params
        )

    def get_envelope(
        self,
        access_token: str,
        account_id: str,
        envelope_id: str
    ) -> Optional[Dict[str, Any]]:
        """Get envelope details"""
        return self._make_request(
            "GET",
            f"/envelopes/{envelope_id}",
            access_token,
            account_id
        )

    def create_envelope(
        self,
        access_token: str,
        account_id: str,
        email_subject: str,
        documents: List[Dict],
        recipients: Dict,
        status: str = "sent"
    ) -> Optional[Dict[str, Any]]:
        """Create and optionally send an envelope"""
        envelope_data = {
            "emailSubject": email_subject,
            "documents": documents,
            "recipients": recipients,
            "status": status,
        }

        return self._make_request(
            "POST",
            "/envelopes",
            access_token,
            account_id,
            data=envelope_data
        )

    def send_envelope_for_signature(
        self,
        access_token: str,
        account_id: str,
        document_name: str,
        document_base64: str,
        signer_email: str,
        signer_name: str,
        email_subject: str,
        email_body: str = None
    ) -> Optional[Dict[str, Any]]:
        """Send a document for signature"""
        envelope_data = {
            "emailSubject": email_subject,
            "documents": [
                {
                    "documentBase64": document_base64,
                    "name": document_name,
                    "fileExtension": "pdf",
                    "documentId": "1"
                }
            ],
            "recipients": {
                "signers": [
                    {
                        "email": signer_email,
                        "name": signer_name,
                        "recipientId": "1",
                        "routingOrder": "1",
                        "tabs": {
                            "signHereTabs": [
                                {
                                    "anchorString": "/sn1/",
                                    "anchorUnits": "pixels",
                                    "anchorXOffset": "10",
                                    "anchorYOffset": "10"
                                }
                            ],
                            "dateSignedTabs": [
                                {
                                    "anchorString": "/ds1/",
                                    "anchorUnits": "pixels",
                                    "anchorXOffset": "10",
                                    "anchorYOffset": "10"
                                }
                            ]
                        }
                    }
                ]
            },
            "status": "sent"
        }

        if email_body:
            envelope_data["emailBlurb"] = email_body

        return self._make_request(
            "POST",
            "/envelopes",
            access_token,
            account_id,
            data=envelope_data
        )

    def void_envelope(
        self,
        access_token: str,
        account_id: str,
        envelope_id: str,
        void_reason: str
    ) -> Optional[Dict[str, Any]]:
        """Void an envelope"""
        return self._make_request(
            "PUT",
            f"/envelopes/{envelope_id}",
            access_token,
            account_id,
            data={"status": "voided", "voidedReason": void_reason}
        )

    def get_envelope_documents(
        self,
        access_token: str,
        account_id: str,
        envelope_id: str
    ) -> Optional[Dict[str, Any]]:
        """Get list of documents in an envelope"""
        return self._make_request(
            "GET",
            f"/envelopes/{envelope_id}/documents",
            access_token,
            account_id
        )

    def download_document(
        self,
        access_token: str,
        account_id: str,
        envelope_id: str,
        document_id: str
    ) -> Optional[bytes]:
        """Download a document from an envelope"""
        try:
            base_url = self._get_api_base_url(access_token, account_id)
            if not base_url:
                return None

            url = f"{base_url}/v2.1/accounts/{account_id}/envelopes/{envelope_id}/documents/{document_id}"

            response = requests.get(
                url,
                headers={"Authorization": f"Bearer {access_token}"}
            )
            response.raise_for_status()

            return response.content

        except Exception as e:
            logger.error(f"Error downloading document: {e}")
            return None

    # Template operations
    def list_templates(
        self,
        access_token: str,
        account_id: str,
        count: int = 100
    ) -> Optional[Dict[str, Any]]:
        """List available templates"""
        return self._make_request(
            "GET",
            "/templates",
            access_token,
            account_id,
            params={"count": count}
        )

    def create_envelope_from_template(
        self,
        access_token: str,
        account_id: str,
        template_id: str,
        email_subject: str,
        template_roles: List[Dict],
        status: str = "sent"
    ) -> Optional[Dict[str, Any]]:
        """Create an envelope from a template"""
        envelope_data = {
            "templateId": template_id,
            "emailSubject": email_subject,
            "templateRoles": template_roles,
            "status": status,
        }

        return self._make_request(
            "POST",
            "/envelopes",
            access_token,
            account_id,
            data=envelope_data
        )


# Global instance
docusign_client = DocuSignClient()
