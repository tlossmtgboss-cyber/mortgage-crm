"""
Auth-related exceptions and helpers for Salesforce sync.

OAuth token acquisition is delegated to `oauth_service.salesforce_oauth`;
this module hosts the sync-layer exception that signals a 401 from
Salesforce so callers can refresh and retry.
"""


class SalesforceTokenExpiredError(Exception):
    """Raised when a Salesforce API call returns 401 INVALID_SESSION_ID."""
    pass
