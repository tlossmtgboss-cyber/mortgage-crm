"""
Follow Up Boss API Client Service
Perennia AI - Mortgage CRM

Provides API client for Follow Up Boss CRM integration:
- Authentication via API key (Basic Auth)
- People (leads) management
- Notes management
- Events/activities
- Stage management
"""

import os
import logging
import hashlib
import hmac
import secrets
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any, Tuple
from base64 import b64encode

import requests
from requests.auth import HTTPBasicAuth

from cryptography.fernet import Fernet

logger = logging.getLogger(__name__)


# =============================================================================
# ENCRYPTION UTILITIES
# =============================================================================

def get_encryption_key() -> bytes:
    """Get or generate encryption key for API keys."""
    key = os.getenv("FUB_ENCRYPTION_KEY")
    if not key:
        # Fall back to SECRET_KEY if FUB-specific key not set
        secret = os.getenv("SECRET_KEY", "")
        # Derive a valid Fernet key from SECRET_KEY
        key = b64encode(hashlib.sha256(secret.encode()).digest())
    else:
        key = key.encode() if isinstance(key, str) else key
    return key


def encrypt_api_key(api_key: str) -> str:
    """Encrypt API key for storage."""
    f = Fernet(get_encryption_key())
    return f.encrypt(api_key.encode()).decode()


def decrypt_api_key(encrypted_key: str) -> str:
    """Decrypt stored API key."""
    f = Fernet(get_encryption_key())
    return f.decrypt(encrypted_key.encode()).decode()


def generate_webhook_secret() -> str:
    """Generate a random webhook secret."""
    return secrets.token_hex(32)


# =============================================================================
# FOLLOW UP BOSS API CLIENT
# =============================================================================

class FollowUpBossClient:
    """
    Client for Follow Up Boss API.

    API Documentation: https://docs.followupboss.com/reference/getting-started
    Auth: Basic Auth with API key as username, empty password
    Required Headers: X-System, X-System-Key (identifies the integration)
    Rate Limit: 250 requests per 10-second sliding window (global),
                25 PUT /people per 10-second window
    """

    BASE_URL = "https://api.followupboss.com/v1"
    SYSTEM_NAME = "PerenniaAI"
    SYSTEM_KEY = os.getenv("FUB_SYSTEM_KEY", "")

    def __init__(self, api_key: str):
        """
        Initialize FUB client.

        Args:
            api_key: Follow Up Boss API key (fka_XXXX format)
        """
        self.api_key = api_key
        self.session = requests.Session()
        self.session.auth = HTTPBasicAuth(api_key, "")
        self.session.headers.update({
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "PerenniaCRM/1.0",
            "X-System": self.SYSTEM_NAME,
            "X-System-Key": self.SYSTEM_KEY,
        })

    # =========================================================================
    # HTTP METHODS
    # =========================================================================

    def _request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict] = None,
        json_data: Optional[Dict] = None,
        _retry_count: int = 0
    ) -> Dict[str, Any]:
        """
        Make HTTP request to FUB API with rate limit handling.

        Args:
            method: HTTP method (GET, POST, PUT, DELETE)
            endpoint: API endpoint (without base URL)
            params: Query parameters
            json_data: JSON body data

        Returns:
            Response JSON data

        Raises:
            requests.HTTPError: On API errors (after retries exhausted)
        """
        import time

        url = f"{self.BASE_URL}/{endpoint.lstrip('/')}"
        max_retries = 3

        try:
            response = self.session.request(
                method=method,
                url=url,
                params=params,
                json=json_data,
                timeout=30
            )

            # Log request for debugging
            logger.debug(f"FUB API {method} {endpoint}: {response.status_code}")

            # Handle rate limiting (429)
            if response.status_code == 429:
                if _retry_count >= max_retries:
                    logger.error(f"FUB API rate limit exceeded after {max_retries} retries: {endpoint}")
                    response.raise_for_status()

                retry_after = int(response.headers.get("Retry-After", 10))
                logger.warning(f"FUB API rate limited on {method} {endpoint}, waiting {retry_after}s (attempt {_retry_count + 1}/{max_retries})")
                time.sleep(retry_after)
                return self._request(method, endpoint, params, json_data, _retry_count + 1)

            response.raise_for_status()

            # Handle empty responses
            if response.status_code == 204 or not response.content:
                return {}

            return response.json()

        except requests.exceptions.HTTPError as e:
            logger.error(f"FUB API error: {e.response.status_code} - {e.response.text}")
            raise
        except requests.exceptions.RequestException as e:
            logger.error(f"FUB API request failed: {e}")
            raise

    def _get(self, endpoint: str, params: Optional[Dict] = None) -> Dict:
        """GET request."""
        return self._request("GET", endpoint, params=params)

    def _post(self, endpoint: str, data: Dict) -> Dict:
        """POST request."""
        return self._request("POST", endpoint, json_data=data)

    def _put(self, endpoint: str, data: Dict) -> Dict:
        """PUT request."""
        return self._request("PUT", endpoint, json_data=data)

    def _delete(self, endpoint: str) -> Dict:
        """DELETE request."""
        return self._request("DELETE", endpoint)

    # =========================================================================
    # AUTHENTICATION / USER INFO
    # =========================================================================

    def verify_credentials(self) -> Tuple[bool, Optional[Dict]]:
        """
        Verify API credentials are valid.

        Returns:
            Tuple of (is_valid, user_info)
        """
        try:
            user = self.get_current_user()
            return True, user
        except requests.HTTPError as e:
            if e.response.status_code == 401:
                return False, None
            raise

    def get_current_user(self) -> Dict:
        """
        Get current authenticated user info.

        Returns:
            User object with id, email, name, etc.
        """
        return self._get("me")

    # =========================================================================
    # PEOPLE (LEADS)
    # =========================================================================

    def get_people(
        self,
        limit: int = 100,
        offset: int = 0,
        sort: str = "-created",
        assigned_to: Optional[int] = None,
        updated_since: Optional[datetime] = None,
        stage: Optional[str] = None,
        search: Optional[str] = None
    ) -> Dict:
        """
        Get list of people (leads).

        Args:
            limit: Max results (1-500)
            offset: Pagination offset
            sort: Sort field (prefix - for descending)
            assigned_to: Filter by assigned user ID
            updated_since: Only records updated after this time
            stage: Filter by stage name
            search: Search query

        Returns:
            Dict with 'people' list and '_metadata' pagination info
        """
        params = {
            "limit": min(limit, 500),
            "offset": offset,
            "sort": sort
        }

        if assigned_to:
            params["assignedUserId"] = assigned_to
        if updated_since:
            params["updatedAfter"] = updated_since.isoformat()
        if stage:
            params["stage"] = stage
        if search:
            params["q"] = search

        return self._get("people", params)

    def get_person(self, person_id: int) -> Dict:
        """
        Get single person by ID.

        Args:
            person_id: FUB person ID

        Returns:
            Person object
        """
        return self._get(f"people/{person_id}")

    def create_person(self, data: Dict) -> Dict:
        """
        Create new person.

        Args:
            data: Person data with fields like firstName, lastName, emails, etc.

        Returns:
            Created person object
        """
        return self._post("people", data)

    def update_person(self, person_id: int, data: Dict) -> Dict:
        """
        Update existing person.

        Args:
            person_id: FUB person ID
            data: Fields to update

        Returns:
            Updated person object
        """
        return self._put(f"people/{person_id}", data)

    def search_people(self, query: str, limit: int = 20) -> List[Dict]:
        """
        Search people by name, email, or phone.

        Args:
            query: Search query
            limit: Max results

        Returns:
            List of matching people
        """
        result = self.get_people(search=query, limit=limit)
        return result.get("people", [])

    def get_people_by_email(self, email: str) -> Optional[Dict]:
        """
        Find person by email address.

        Args:
            email: Email to search

        Returns:
            Person object if found, None otherwise
        """
        people = self.search_people(email, limit=5)
        for person in people:
            for email_obj in person.get("emails", []):
                if email_obj.get("value", "").lower() == email.lower():
                    return person
        return None

    # =========================================================================
    # NOTES
    # =========================================================================

    def get_notes(
        self,
        person_id: Optional[int] = None,
        limit: int = 100,
        offset: int = 0
    ) -> Dict:
        """
        Get notes, optionally filtered by person.

        Args:
            person_id: Filter by person ID
            limit: Max results
            offset: Pagination offset

        Returns:
            Dict with 'notes' list
        """
        params = {"limit": limit, "offset": offset}
        if person_id:
            params["personId"] = person_id

        return self._get("notes", params)

    def create_note(
        self,
        person_id: int,
        body: str,
        subject: Optional[str] = None,
        is_html: bool = False
    ) -> Dict:
        """
        Create note for a person.

        Args:
            person_id: Person to attach note to
            body: Note content
            subject: Optional subject/title
            is_html: Whether body contains HTML

        Returns:
            Created note object
        """
        data = {
            "personId": person_id,
            "body": body,
            "isHtml": is_html
        }
        if subject:
            data["subject"] = subject

        return self._post("notes", data)

    # =========================================================================
    # EVENTS / ACTIVITIES
    # =========================================================================

    def get_events(
        self,
        person_id: Optional[int] = None,
        event_type: Optional[str] = None,
        limit: int = 100,
        offset: int = 0
    ) -> Dict:
        """
        Get events/activities.

        Args:
            person_id: Filter by person
            event_type: Filter by event type (Call, Email, etc.)
            limit: Max results
            offset: Pagination offset

        Returns:
            Dict with 'events' list
        """
        params = {"limit": limit, "offset": offset}
        if person_id:
            params["personId"] = person_id
        if event_type:
            params["type"] = event_type

        return self._get("events", params)

    def create_event(
        self,
        person_id: int,
        event_type: str,
        description: str,
        source: str = "Perennia CRM"
    ) -> Dict:
        """
        Create event/activity for a person.

        Args:
            person_id: Person ID
            event_type: Event type (Call, Email, Meeting, etc.)
            description: Event description
            source: Source system name

        Returns:
            Created event object
        """
        data = {
            "personId": person_id,
            "type": event_type,
            "description": description,
            "source": source
        }

        return self._post("events", data)

    # =========================================================================
    # STAGES
    # =========================================================================

    def get_stages(self) -> List[Dict]:
        """
        Get list of stages configured in FUB.

        Returns:
            List of stage objects with id, name, etc.
        """
        result = self._get("stages")
        return result.get("stages", [])

    # =========================================================================
    # USERS
    # =========================================================================

    def get_users(self) -> List[Dict]:
        """
        Get list of users in FUB account.

        Returns:
            List of user objects
        """
        result = self._get("users")
        return result.get("users", [])

    def get_user(self, user_id: int) -> Dict:
        """
        Get single user by ID.

        Args:
            user_id: FUB user ID

        Returns:
            User object
        """
        return self._get(f"users/{user_id}")

    # =========================================================================
    # WEBHOOKS
    # =========================================================================

    def get_webhooks(self) -> List[Dict]:
        """
        Get list of registered webhooks.

        Returns:
            List of webhook objects
        """
        result = self._get("webhooks")
        return result.get("webhooks", [])

    def create_webhook(
        self,
        url: str,
        event: str,
        secret: Optional[str] = None
    ) -> Dict:
        """
        Create/register a webhook.

        Args:
            url: Webhook URL to receive events
            event: Event type to subscribe to (people.created, etc.)
            secret: Secret for signature validation

        Returns:
            Created webhook object
        """
        data = {
            "url": url,
            "event": event
        }
        if secret:
            data["secret"] = secret

        return self._post("webhooks", data)

    def delete_webhook(self, webhook_id: int) -> Dict:
        """
        Delete a webhook.

        Args:
            webhook_id: Webhook ID to delete

        Returns:
            Empty dict on success
        """
        return self._delete(f"webhooks/{webhook_id}")


# =============================================================================
# WEBHOOK SIGNATURE VALIDATION
# =============================================================================

def validate_webhook_signature(
    payload: bytes,
    signature: str,
    secret: str
) -> bool:
    """
    Validate FUB webhook signature.

    FUB uses HMAC-SHA256 for webhook signatures.

    Args:
        payload: Raw request body bytes
        signature: X-FUB-Signature header value
        secret: Webhook secret

    Returns:
        True if signature is valid
    """
    if not signature or not secret:
        return False

    expected = hmac.new(
        secret.encode(),
        payload,
        hashlib.sha256
    ).hexdigest()

    return hmac.compare_digest(signature, expected)


# =============================================================================
# DATA TRANSFORMATION HELPERS
# =============================================================================

def extract_email(person: Dict) -> Optional[str]:
    """Extract primary email from FUB person."""
    emails = person.get("emails", [])
    if emails and isinstance(emails, list):
        for email in emails:
            if email.get("isPrimary") or email.get("value"):
                return email.get("value")
    return None


def extract_phone(person: Dict) -> Optional[str]:
    """Extract primary phone from FUB person."""
    phones = person.get("phones", [])
    if phones and isinstance(phones, list):
        for phone in phones:
            if phone.get("isPrimary") or phone.get("value"):
                return phone.get("value")
    return None


def format_emails_for_fub(email: str) -> List[Dict]:
    """Format email for FUB API."""
    if not email:
        return []
    return [{"value": email, "isPrimary": True}]


def format_phones_for_fub(phone: str) -> List[Dict]:
    """Format phone for FUB API."""
    if not phone:
        return []
    return [{"value": phone, "isPrimary": True}]


def compute_sync_hash(data: Dict) -> str:
    """
    Compute hash of data for change detection.

    Args:
        data: Dict to hash

    Returns:
        MD5 hash string
    """
    import json
    # Sort keys for consistent hashing
    normalized = json.dumps(data, sort_keys=True, default=str)
    return hashlib.md5(normalized.encode()).hexdigest()
