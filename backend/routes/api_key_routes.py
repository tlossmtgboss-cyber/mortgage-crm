"""
API Key & Contact Search Routes
Extracted from inline_legacy_routes.py.

Includes:
- Contact search (leads + users autocomplete)
- API key CRUD (create, list, revoke)

Lines ~18775-18896 from inline_legacy_routes.py.
"""
from fastapi import Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from sqlalchemy import func, or_
from typing import List
import logging

logger = logging.getLogger(__name__)

# Import models
from database.models import User, Lead, ApiKey

# Import schemas
from schemas.core import ApiKeyCreate, ApiKeyResponse


def register_api_key_routes(app, get_db, get_current_user, **kwargs):
    """Register API key and contact search routes.

    Optional kwargs:
        generate_api_key: function that returns a new API key string
    """
    generate_api_key = kwargs.get('generate_api_key')

    # ============================================================================
    # CONTACT SEARCH
    # ============================================================================

    @app.get("/api/v1/contacts/search")
    async def search_contacts(
        q: str = Query(..., min_length=1),
        limit: int = Query(10, le=50),
        db: Session = Depends(get_db),
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
            raise HTTPException(status_code=500, detail=str(e))

    # ============================================================================
    # API KEY MANAGEMENT
    # ============================================================================

    @app.post("/api/v1/api-keys", response_model=ApiKeyResponse)
    async def create_api_key_endpoint(
        key_data: ApiKeyCreate,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
    ):
        """Generate a new API key for the current user"""
        try:
            # Generate a secure API key
            api_key_string = generate_api_key()

            logger.info(f"Attempting to create API key '{key_data.name}' for user {current_user.email}")

            # Create the API key record
            new_api_key = ApiKey(
                key=api_key_string,
                name=key_data.name,
                user_id=current_user.id
            )

            db.add(new_api_key)
            db.commit()
            db.refresh(new_api_key)

            logger.info(f"API key created successfully for user {current_user.email}: {key_data.name}")
            return new_api_key
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to create API key: {str(e)}")
            logger.exception(e)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to create API key: {str(e)}"
            )

    @app.get("/api/v1/api-keys", response_model=List[ApiKeyResponse])
    async def list_api_keys(
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
    ):
        """List all API keys for the current user"""
        api_keys = db.query(ApiKey).filter(
            ApiKey.user_id == current_user.id
        ).all()
        return api_keys

    @app.delete("/api/v1/api-keys/{key_id}")
    async def revoke_api_key(
        key_id: int,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
    ):
        """Revoke (deactivate) an API key"""
        api_key = db.query(ApiKey).filter(
            ApiKey.id == key_id,
            ApiKey.user_id == current_user.id
        ).first()

        if not api_key:
            raise HTTPException(status_code=404, detail="API key not found")

        api_key.is_active = False
        db.commit()

        logger.info(f"API key revoked for user {current_user.email}: {api_key.name}")
        return {"message": "API key revoked successfully"}
