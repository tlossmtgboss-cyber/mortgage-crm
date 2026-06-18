"""
API Key Scope Enforcement Dependency
Enterprise Readiness Check 4.11

Provides a FastAPI dependency that enforces API key scopes on endpoints.
When a request is authenticated via API key (sk_...), this checks that
the key has the required scope for the endpoint being accessed.

Usage in routes:
    from auth.scope_enforcement import require_scope

    @router.get("/api/v1/leads")
    async def get_leads(
        current_user=Depends(get_current_user),
        _scope=Depends(require_scope("read:leads")),
    ):
        ...

    @router.post("/api/v1/leads")
    async def create_lead(
        current_user=Depends(get_current_user),
        _scope=Depends(require_scope("write:leads")),
    ):
        ...

For JWT-authenticated requests (not API keys), scopes are not checked
since JWT tokens represent full user sessions with role-based access.
"""

import logging
import re
from datetime import datetime, timezone
from typing import Optional

from fastapi import Depends, HTTPException, Request, status

from auth.api_key_scopes import validate_scopes

logger = logging.getLogger(__name__)

# Endpoint pattern -> required scopes mapping
# Used for automatic scope enforcement when require_scope() is not explicitly applied.
ENDPOINT_SCOPE_MAP = {
    # Leads
    r"^/api/v1/leads$": {"GET": ["read:leads"], "POST": ["write:leads"]},
    r"^/api/v1/leads/\d+$": {"GET": ["read:leads"], "PUT": ["write:leads"], "PATCH": ["write:leads"], "DELETE": ["write:leads"]},
    r"^/api/v1/leads/search": {"GET": ["read:leads"], "POST": ["read:leads"]},

    # Loans
    r"^/api/v1/loans$": {"GET": ["read:loans"], "POST": ["write:loans"]},
    r"^/api/v1/loans/\d+$": {"GET": ["read:loans"], "PUT": ["write:loans"], "PATCH": ["write:loans"], "DELETE": ["write:loans"]},

    # Contacts
    r"^/api/v1/contacts": {"GET": ["read:contacts"], "POST": ["write:contacts"], "PUT": ["write:contacts"], "PATCH": ["write:contacts"], "DELETE": ["write:contacts"]},

    # Documents
    r"^/api/v1/documents": {"GET": ["read:documents"], "POST": ["write:documents"], "PUT": ["write:documents"], "DELETE": ["write:documents"]},

    # Reports
    r"^/api/v1/reports": {"GET": ["read:reports"]},
    r"^/api/v1/analytics": {"GET": ["read:reports"]},

    # Admin
    r"^/api/v1/admin/users": {"GET": ["admin:users"], "POST": ["admin:users"], "PUT": ["admin:users"], "PATCH": ["admin:users"], "DELETE": ["admin:users"]},
    r"^/api/v1/admin/settings": {"GET": ["admin:settings"], "POST": ["admin:settings"], "PUT": ["admin:settings"]},

    # Scheduler — appointments
    r"^/api/v1/scheduler/appointments$": {"GET": ["read:appointments"], "POST": ["write:appointments"]},
    r"^/api/v1/scheduler/appointments/\d+$": {"GET": ["read:appointments"], "PUT": ["write:appointments"], "PATCH": ["write:appointments"], "DELETE": ["write:appointments"]},
    r"^/api/v1/scheduler/appointments/\d+/cancel$": {"POST": ["write:appointments"]},
    r"^/api/v1/scheduler/appointments/\d+/timeline$": {"GET": ["read:appointments"]},
    r"^/api/v1/scheduler/appointments/\d+/audit-trail$": {"GET": ["read:appointments"]},
    r"^/api/v1/scheduler/appointments/export": {"GET": ["read:appointments"]},

    # Scheduler — availability / slots
    r"^/api/v1/scheduler/availability$": {"GET": ["read:appointments"]},
    r"^/api/v1/scheduler/availability/slots$": {"POST": ["write:appointments"]},
    r"^/api/v1/scheduler/availability/slots/\d+$": {"DELETE": ["write:appointments"]},
    r"^/api/v1/scheduler/available-slots$": {"POST": ["read:appointments"]},

    # Scheduler — webhooks
    r"^/api/v1/scheduler/webhooks$": {"GET": ["webhooks:manage"], "POST": ["webhooks:manage"]},
    r"^/api/v1/scheduler/webhooks/\d+$": {"DELETE": ["webhooks:manage"]},
    r"^/api/v1/scheduler/webhooks/\d+/test$": {"POST": ["webhooks:manage"]},
    r"^/api/v1/scheduler/webhooks/\d+/deliveries$": {"GET": ["webhooks:manage"]},
}


def require_scope(*required_scopes: str):
    """
    FastAPI dependency that checks API key scopes.

    If the request uses API key auth, validates that the key has all
    required scopes. JWT-authenticated requests pass through without
    scope checks.

    Args:
        *required_scopes: One or more scope strings required for the endpoint.

    Returns:
        A FastAPI dependency function.
    """
    scopes_list = list(required_scopes)

    async def _check_scope(request: Request):
        # Only enforce scopes for API key auth
        api_key_obj = getattr(request.state, "_api_key_obj", None)
        if api_key_obj is None:
            # Not API key auth (JWT), skip scope check
            return True

        key_scopes = api_key_obj.scopes or []

        if not validate_scopes(scopes_list, key_scopes):
            logger.warning(
                f"API key scope denied: key={api_key_obj.name}, "
                f"required={scopes_list}, has={key_scopes}"
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"API key lacks required scope(s): {', '.join(scopes_list)}",
            )

        return True

    return _check_scope


def check_endpoint_scopes(
    request: Request,
    api_key_scopes: list,
) -> bool:
    """
    Check if an API key has the required scopes for the current endpoint.

    This is called from the get_current_user function for automatic enforcement.

    Args:
        request: The current FastAPI request.
        api_key_scopes: Scopes assigned to the API key.

    Returns:
        True if allowed, False if denied.
    """
    if not api_key_scopes:
        # No scopes assigned = legacy key with full access (backward compat)
        return True

    # Wildcard grants all access
    if "*" in api_key_scopes:
        return True

    path = request.url.path
    method = request.method.upper()

    for pattern, method_scopes in ENDPOINT_SCOPE_MAP.items():
        if re.match(pattern, path):
            required = method_scopes.get(method)
            if required:
                if not validate_scopes(required, api_key_scopes):
                    logger.warning(
                        f"API key scope denied: path={path}, method={method}, "
                        f"required={required}, has={api_key_scopes}"
                    )
                    return False
            break

    return True
