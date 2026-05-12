"""Role escalation prevention -- ensures users cannot assign roles above their own level."""

from fastapi import HTTPException, status


ROLE_HIERARCHY = {
    "platform_admin": 100,
    "site_admin": 90,
    "admin": 80,
    "leadership": 70,
    "management": 60,
    "branch_manager": 55,
    "regional_manager": 55,
    "team_lead": 50,
    "loan_officer": 40,
    "processor": 30,
    "sales": 20,
    "viewer": 10,
}


def check_role_escalation(assigner_role: str, target_role: str) -> bool:
    """Return True if the assignment is allowed (assigner >= target level).

    Both roles are normalized to lowercase before lookup.
    Unknown roles default to level 0 (denied by default).
    """
    assigner_level = ROLE_HIERARCHY.get((assigner_role or "").lower().strip(), 0)
    target_level = ROLE_HIERARCHY.get((target_role or "").lower().strip(), 0)
    return assigner_level >= target_level


def enforce_no_escalation(assigner_role: str, target_role: str) -> None:
    """Raise HTTP 403 if assigner_role < target_role in the hierarchy.

    Call this from any route that assigns or changes a user's role.
    """
    if not check_role_escalation(assigner_role, target_role):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                f"Role escalation denied: your role '{assigner_role}' "
                f"cannot assign the higher role '{target_role}'"
            ),
        )
