"""
API Key Scope Enforcement
Enterprise Readiness Check 4.11

Provides scope-based access control for API keys. Each API key can be
assigned a set of scopes that limit what resources it can access.

Usage:
    from auth.api_key_scopes import validate_scopes, AVAILABLE_SCOPES

    # Check if API key has required scopes
    if not validate_scopes(["read:leads"], api_key.scopes):
        raise HTTPException(403, "Insufficient API key scopes")
"""

AVAILABLE_SCOPES = [
    "read:leads", "write:leads",
    "read:loans", "write:loans",
    "read:contacts", "write:contacts",
    "read:documents", "write:documents",
    "read:reports",
    "admin:users", "admin:settings",
]


def validate_scopes(required_scopes: list, api_key_scopes: list) -> bool:
    """
    Check if API key has all required scopes.

    Args:
        required_scopes: List of scopes required for the operation.
        api_key_scopes: List of scopes assigned to the API key.

    Returns:
        True if all required scopes are present (or no scopes required).
    """
    if not required_scopes:
        return True
    if not api_key_scopes:
        return False
    # Wildcard scope grants all access
    if "*" in api_key_scopes:
        return True
    return all(scope in api_key_scopes for scope in required_scopes)


def get_scope_description(scope: str) -> str:
    """Get a human-readable description for a scope."""
    descriptions = {
        "read:leads": "Read lead records",
        "write:leads": "Create, update, and delete lead records",
        "read:loans": "Read loan records",
        "write:loans": "Create, update, and delete loan records",
        "read:contacts": "Read contact records",
        "write:contacts": "Create, update, and delete contact records",
        "read:documents": "Read and download documents",
        "write:documents": "Upload and manage documents",
        "read:reports": "Access reports and analytics",
        "admin:users": "Manage user accounts",
        "admin:settings": "Manage system settings",
    }
    return descriptions.get(scope, scope)
