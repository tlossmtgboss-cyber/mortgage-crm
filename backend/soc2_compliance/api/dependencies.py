"""
SOC 2 API Dependencies — Bridge to the main app's auth and DB systems.

NOTE: The SOC 2 services use async SQLAlchemy (AsyncSession), while the main app
uses sync sessions. Full SOC 2 API endpoint functionality requires either:
1. A PostgreSQL database with soc2_* tables created (via migrations/soc2_tables.sql)
2. An async session factory added to the app

For now, these dependencies wire up auth so routes register correctly.
The compliance scan script can be run independently against a PostgreSQL DB.
"""
import logging

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

logger = logging.getLogger("soc2.api.dependencies")


def get_soc2_db():
    """
    Get database session for SOC 2 endpoints.
    Uses the main app's sync session factory.
    """
    from db import get_db as _get_db
    yield from _get_db()


async def get_current_admin_user(request: Request, db: Session = Depends(get_soc2_db)):
    """
    Get authenticated user with admin role verification.
    SOC 2 compliance endpoints require admin privileges.
    """
    from auth.dependencies import get_current_user as _get_current_user
    user = await _get_current_user(request, db)

    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")

    user_role = getattr(user, "role", None)
    if user_role not in ("Platform Admin", "Site Admin", "Admin"):
        raise HTTPException(
            status_code=403,
            detail="SOC 2 compliance endpoints require admin role"
        )

    return user
