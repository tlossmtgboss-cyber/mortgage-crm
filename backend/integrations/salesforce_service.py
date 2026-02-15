"""
Salesforce OAuth Integration
Handles CRM sync and API access
"""
import os
import re
import logging
import secrets
import hashlib
import base64
from typing import Optional, Dict, Any, Tuple
from datetime import datetime, timedelta
import requests
from urllib.parse import urlencode

logger = logging.getLogger(__name__)

_SF_INSTANCE_URL_PATTERN = re.compile(r'^https://[a-zA-Z0-9\-]+\.salesforce\.com$')


def _validate_salesforce_url(instance_url: str) -> str:
    if not _SF_INSTANCE_URL_PATTERN.match(instance_url):
        raise ValueError("Invalid Salesforce instance URL")
    return instance_url


# Salesforce API version - centralized for easy updates
# See https://developer.salesforce.com/docs/atlas.en-us.api_rest.meta/api_rest/api_versions.htm
SALESFORCE_API_VERSION = "v58.0"

# Database-backed PKCE store with TTL
# Falls back to in-memory if database not available
_pkce_store_memory: Dict[str, Tuple[str, datetime]] = {}  # state -> (verifier, expires_at)
PKCE_TTL_MINUTES = 10  # PKCE verifiers expire after 10 minutes
PKCE_CLEANUP_INTERVAL_MINUTES = 5  # Run cleanup every 5 minutes
_last_pkce_cleanup: Optional[datetime] = None  # Track last cleanup time


def _should_run_pkce_cleanup() -> bool:
    """
    Determine if PKCE cleanup should run based on time elapsed.
    Uses deterministic time-based check instead of random probability.
    """
    global _last_pkce_cleanup
    now = datetime.utcnow()

    if _last_pkce_cleanup is None:
        _last_pkce_cleanup = now
        return True  # First time, run cleanup

    elapsed = (now - _last_pkce_cleanup).total_seconds() / 60
    if elapsed >= PKCE_CLEANUP_INTERVAL_MINUTES:
        _last_pkce_cleanup = now
        return True

    return False


def _get_db_session():
    """Get database session for PKCE storage."""
    try:
        from database import get_db
        return next(get_db())
    except Exception as e:
        logger.debug(f"Database not available for PKCE storage: {e}")
        return None


def _store_pkce_verifier(state: str, verifier: str) -> None:
    """Store PKCE verifier with TTL, using database if available."""
    expires_at = datetime.utcnow() + timedelta(minutes=PKCE_TTL_MINUTES)

    db = _get_db_session()
    if db:
        try:
            from sqlalchemy import text
            # Clean up expired entries periodically (time-based, not random)
            if _should_run_pkce_cleanup():
                db.execute(text("""
                    DELETE FROM oauth_pkce_store WHERE expires_at < :now
                """), {"now": datetime.utcnow()})
                logger.debug("PKCE cleanup: removed expired entries")

            # Store the verifier
            db.execute(text("""
                INSERT INTO oauth_pkce_store (state, code_verifier, expires_at, created_at)
                VALUES (:state, :verifier, :expires_at, :created_at)
                ON CONFLICT (state) DO UPDATE SET
                    code_verifier = EXCLUDED.code_verifier,
                    expires_at = EXCLUDED.expires_at
            """), {
                "state": state,
                "verifier": verifier,
                "expires_at": expires_at,
                "created_at": datetime.utcnow()
            })
            db.commit()
            logger.info(f"Stored PKCE verifier in database for state: {state[:20]}...")
            return
        except (ImportError, AttributeError) as e:
            logger.warning(f"SQLAlchemy not available for PKCE storage: {e}")
        except Exception as e:
            # Catch database errors specifically but allow fallback to memory
            logger.warning(f"Database error storing PKCE, using memory fallback: {type(e).__name__}: {e}")
            try:
                db.rollback()
            except Exception:
                pass  # Rollback may fail if connection is broken
        finally:
            try:
                db.close()
            except Exception:
                pass  # Close may fail if connection is broken

    # Fallback to memory storage
    _pkce_store_memory[state] = (verifier, expires_at)
    logger.info(f"Stored PKCE verifier in memory for state: {state[:20]}...")


def _get_pkce_verifier(state: str) -> Optional[str]:
    """Retrieve and delete PKCE verifier."""
    db = _get_db_session()
    if db:
        try:
            from sqlalchemy import text
            result = db.execute(text("""
                DELETE FROM oauth_pkce_store
                WHERE state = :state AND expires_at > :now
                RETURNING code_verifier
            """), {"state": state, "now": datetime.utcnow()}).fetchone()
            db.commit()

            if result:
                logger.info(f"Retrieved PKCE verifier from database for state: {state[:20]}...")
                return result[0]
            else:
                logger.warning(f"No valid PKCE verifier found in database for state: {state[:20]}...")
                return None
        except (ImportError, AttributeError) as e:
            logger.warning(f"SQLAlchemy not available for PKCE retrieval: {e}")
        except Exception as e:
            # Catch database errors specifically but allow fallback to memory
            logger.warning(f"Database error retrieving PKCE, checking memory: {type(e).__name__}: {e}")
            try:
                db.rollback()
            except Exception:
                pass
        finally:
            try:
                db.close()
            except Exception:
                pass

    # Fallback to memory storage
    stored = _pkce_store_memory.pop(state, None)
    if stored:
        verifier, expires_at = stored
        if datetime.utcnow() < expires_at:
            logger.info(f"Retrieved PKCE verifier from memory for state: {state[:20]}...")
            return verifier
        else:
            logger.warning(f"PKCE verifier expired in memory for state: {state[:20]}...")
    else:
        logger.warning(f"No PKCE verifier found in memory for state: {state[:20]}...")
    return None


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

    def _generate_pkce(self) -> Tuple[str, str]:
        """Generate PKCE code verifier and challenge"""
        # Generate a random code verifier (43-128 characters)
        code_verifier = secrets.token_urlsafe(64)

        # Create code challenge using S256 method
        code_challenge_bytes = hashlib.sha256(code_verifier.encode('utf-8')).digest()
        code_challenge = base64.urlsafe_b64encode(code_challenge_bytes).rstrip(b'=').decode('utf-8')

        return code_verifier, code_challenge

    def get_authorization_url(self, state: str = None) -> str:
        """Generate Salesforce OAuth authorization URL with PKCE"""
        # Generate PKCE parameters
        code_verifier, code_challenge = self._generate_pkce()

        # Store the code verifier for later use in token exchange
        # Use state as key (or generate a unique key if no state)
        pkce_key = state or secrets.token_urlsafe(16)
        _store_pkce_verifier(pkce_key, code_verifier)

        # Request only scopes that are enabled in the Connected App
        # If no scope specified, Salesforce uses the scopes configured in the Connected App
        params = {
            "response_type": "code",
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
        }
        # Don't specify scope - let Salesforce use the default scopes from Connected App config

        if state:
            params["state"] = state

        return f"{self.auth_url}?{urlencode(params)}"

    def get_code_verifier(self, state: str) -> Optional[str]:
        """Retrieve stored code verifier for token exchange"""
        return _get_pkce_verifier(state)

    def exchange_code_for_token(self, code: str, code_verifier: str = None) -> Optional[Dict[str, Any]]:
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

            # Include code_verifier for PKCE
            if code_verifier:
                data["code_verifier"] = code_verifier
                logger.info("Including PKCE code_verifier in token exchange")

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

    def query(self, access_token: str, instance_url: str, soql_query: str, raise_for_401: bool = False) -> Optional[Dict[str, Any]]:
        """
        Execute a SOQL query.

        Args:
            access_token: Salesforce access token
            instance_url: Salesforce instance URL
            soql_query: SOQL query string
            raise_for_401: If True, re-raises HTTPError for 401 responses (for auto-refresh)

        Returns:
            Query results or None on error
        """
        try:
            _validate_salesforce_url(instance_url)
        except ValueError:
            logger.error(f"Invalid Salesforce instance URL in query")
            return None
        try:
            headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json"
            }

            url = f"{instance_url}/services/data/{SALESFORCE_API_VERSION}/query/"
            params = {"q": soql_query}

            response = requests.get(url, headers=headers, params=params)
            response.raise_for_status()

            return response.json()

        except requests.exceptions.HTTPError as e:
            if raise_for_401 and e.response is not None and e.response.status_code == 401:
                raise  # Re-raise for auto-refresh handling
            logger.error(f"HTTP error executing SOQL query: {e}")
            return None

        except Exception as e:
            logger.error(f"Error executing SOQL query: {e}")
            return None

    def create_record(
        self,
        access_token: str,
        instance_url: str,
        sobject_type: str,
        data: Dict[str, Any],
        raise_for_401: bool = False
    ) -> Optional[Dict[str, Any]]:
        """
        Create a new Salesforce record.

        Args:
            raise_for_401: If True, re-raises HTTPError for 401 responses (for auto-refresh)
        """
        try:
            _validate_salesforce_url(instance_url)
        except ValueError:
            logger.error(f"Invalid Salesforce instance URL in create_record")
            return None
        try:
            headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json"
            }

            url = f"{instance_url}/services/data/{SALESFORCE_API_VERSION}/sobjects/{sobject_type}/"

            response = requests.post(url, headers=headers, json=data)
            response.raise_for_status()

            return response.json()

        except requests.exceptions.HTTPError as e:
            if raise_for_401 and e.response is not None and e.response.status_code == 401:
                raise
            logger.error(f"HTTP error creating Salesforce record: {e}")
            return None

        except Exception as e:
            logger.error(f"Error creating Salesforce record: {e}")
            return None

    def update_record(
        self,
        access_token: str,
        instance_url: str,
        sobject_type: str,
        record_id: str,
        data: Dict[str, Any],
        raise_for_401: bool = False
    ) -> bool:
        """
        Update an existing Salesforce record.

        Args:
            raise_for_401: If True, re-raises HTTPError for 401 responses (for auto-refresh)
        """
        try:
            _validate_salesforce_url(instance_url)
        except ValueError:
            logger.error(f"Invalid Salesforce instance URL in update_record")
            return False
        try:
            headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json"
            }

            url = f"{instance_url}/services/data/{SALESFORCE_API_VERSION}/sobjects/{sobject_type}/{record_id}"

            response = requests.patch(url, headers=headers, json=data)
            response.raise_for_status()

            return True

        except requests.exceptions.HTTPError as e:
            if raise_for_401 and e.response is not None and e.response.status_code == 401:
                raise
            logger.error(f"HTTP error updating Salesforce record: {e}")
            return False

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
            _validate_salesforce_url(instance_url)
        except ValueError:
            logger.error(f"Invalid Salesforce instance URL in get_record")
            return None
        try:
            headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json"
            }

            url = f"{instance_url}/services/data/{SALESFORCE_API_VERSION}/sobjects/{sobject_type}/{record_id}"

            response = requests.get(url, headers=headers)
            response.raise_for_status()

            return response.json()

        except Exception as e:
            logger.error(f"Error getting Salesforce record: {e}")
            return None


# Global instance
salesforce_client = SalesforceClient()
