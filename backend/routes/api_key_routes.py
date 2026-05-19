"""
Contact Search Routes
Extracted from inline_legacy_routes.py.

Includes:
- Contact search (leads + users autocomplete)

Note: API key CRUD endpoints are now handled by:
- api_gateway_routes.py (database-backed, enterprise-grade)
- api_keys_settings_routes.py (legacy in-memory implementation)

Lines ~18775-18896 from inline_legacy_routes.py.
"""
from fastapi import Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, or_
import logging
from sqlalchemy.ext.asyncio import AsyncSession
from db import get_async_db
from sqlalchemy import select

logger = logging.getLogger(__name__)

# Import models
from database.models import User, Lead


def register_api_key_routes(app, get_db, get_current_user, **kwargs):
    """Register contact search routes.

    Note: API key CRUD is handled by api_keys_settings_routes.py.
    """

    # ============================================================================
    # CONTACT SEARCH
    # ============================================================================

    @app.get("/api/v1/contacts/search")
    async def search_contacts(
        q: str = Query(..., min_length=1),
        limit: int = Query(10, le=50),
        db: AsyncSession = Depends(get_async_db),
        current_user: User = Depends(get_current_user)
    ):
        """Search contacts for CC autocomplete - searches leads, users, and contacts"""
        try:
            results = []
            search_term = f"%{q.lower()}%"

            # Search leads by name and email
            leads = db.query(Lead).filter(
                or_(
                    func.lower(Lead.name).like(search_term),
                    func.lower(Lead.email).like(search_term)
                )
            ).limit(limit // 2).all()

            for lead in leads:
                if lead.email:
                    results.append({
                        "id": f"lead_{lead.id}",
                        "name": lead.name or "",
                        "email": lead.email,
                        "type": "lead"
                    })

            # Search users (team members)
            users = db.query(User).filter(
                or_(
                    func.lower(User.full_name).like(search_term),
                    func.lower(User.email).like(search_term)
                ),
                User.is_active == True
            ).limit(limit // 2).all()

            for user in users:
                results.append({
                    "id": f"user_{user.id}",
                    "name": user.full_name or user.email.split('@')[0],
                    "email": user.email,
                    "type": "user"
                })

            return {"results": results[:limit], "total": len(results)}

        except Exception as e:
            logger.error(f"Error searching contacts: {e}")
            raise HTTPException(status_code=500, detail="Internal server error")
