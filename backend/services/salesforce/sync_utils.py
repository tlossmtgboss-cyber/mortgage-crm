"""
Salesforce Sync Utilities
Shared constants, exceptions, result types, and helper functions used across sync sub-modules.
"""
import hashlib
import json
import logging
import re
from datetime import datetime
from typing import Optional, List, Dict, Any

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# Consistent Salesforce REST API version across all requests (Fix 7)
SF_API_VERSION = "v60.0"

# Regex for validating SOQL identifiers (object names, field names).
# Allows standard and custom fields like MyField__c, Account, etc.
SAFE_SOQL_IDENTIFIER = re.compile(r'^[A-Za-z][A-Za-z0-9_]*(__[a-zA-Z])?$')


class SalesforceTokenExpiredError(Exception):
    """Raised when a Salesforce API call returns 401 INVALID_SESSION_ID."""
    pass


class SyncResult:
    """Result of a sync operation"""
    def __init__(self):
        self.success = False
        self.records_processed = 0
        self.records_succeeded = 0
        self.records_failed = 0
        self.errors: List[Dict[str, str]] = []
        self.duration_ms = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            'success': self.success,
            'records_processed': self.records_processed,
            'records_succeeded': self.records_succeeded,
            'records_failed': self.records_failed,
            'errors': self.errors,
            'duration_ms': self.duration_ms
        }


def _validate_soql_identifier(value: str, context: str = "identifier") -> str:
    """Validate that a value is a safe SOQL identifier (object name or field name).

    Raises ValueError if the value contains characters that could enable SOQL injection.
    """
    if not value or not SAFE_SOQL_IDENTIFIER.match(value):
        raise ValueError(f"Invalid SOQL {context}: {value!r}")
    return value


def _sanitize_soql_string(value: str) -> str:
    """Escape a string value for safe interpolation into SOQL queries.

    Prevents SOQL injection by escaping special characters.
    Also validates basic format for email addresses.
    """
    if not value or not isinstance(value, str):
        return ''
    # Strip whitespace and reject values with control characters
    value = value.strip()
    if re.search(r'[\x00-\x1f\x7f]', value):
        return ''
    # SOQL escaping: single quotes, backslashes
    value = value.replace('\\', '\\\\')
    value = value.replace("'", "\\'")
    return value


def _sanitize_soql_email(email: str) -> str:
    """Sanitize and validate an email for SOQL interpolation."""
    if not email or not isinstance(email, str):
        return ''
    email = email.strip()
    # Basic email format validation
    if not re.match(r'^[^@\s]+@[^@\s]+\.[^@\s]+$', email):
        logger.warning("Invalid email format rejected for SOQL query")
        return ''
    return _sanitize_soql_string(email)


def _get_org_id_for_user(db: Session, user_id: int, _cache: dict = {}) -> Optional[int]:
    """Get organization_id for a user, cached per (user_id, session) to avoid repeated queries.

    Fix 8: The same SELECT organization_id FROM users WHERE id = :user_id query
    was running for every single record. This caches the result for the lifetime
    of the sync operation (keyed by session identity so it doesn't leak across requests).
    """
    cache_key = (user_id, id(db))
    if cache_key in _cache:
        return _cache[cache_key]

    row = db.execute(text(
        "SELECT organization_id FROM users WHERE id = :uid"
    ), {"uid": user_id}).fetchone()
    org_id = row[0] if row else None
    _cache[cache_key] = org_id

    # Limit cache size to prevent memory leaks in long-running processes
    if len(_cache) > 1000:
        _cache.clear()

    return org_id


def generate_sync_hash(data: Dict[str, Any]) -> str:
    """Generate MD5 hash for change detection"""
    data_string = json.dumps(data, sort_keys=True, default=str)
    return hashlib.md5(data_string.encode()).hexdigest()
