"""
Contact Card Team CRUD routes.

Manages the default team roster that appears on borrower-facing vCard
contact cards sent via MMS after application completion.
"""

import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

_security = HTTPBearer(auto_error=False)


async def _require_auth(
    credentials: HTTPAuthorizationCredentials = Depends(_security),
):
    if not credentials:
        raise HTTPException(status_code=401, detail="Not authenticated")
    from auth.dependencies import get_current_user_flexible
    from database import get_db as db_getter
    db = next(db_getter())
    try:
        user = await get_current_user_flexible(token=credentials.credentials, request=None, db=db)
        if not user:
            raise HTTPException(status_code=401, detail="Invalid token")
        return user
    finally:
        db.close()


router = APIRouter(
    prefix="/api/v1/settings/contact-card",
    tags=["Contact Card"],
)


class ContactCardMemberIn(BaseModel):
    name: str
    role_label: str
    phone: Optional[str] = None
    email: Optional[str] = None
    user_id: Optional[int] = None
    sort_order: int = 0
    is_active: bool = True


class ContactCardMemberOut(BaseModel):
    id: int
    name: str
    role_label: str
    phone: Optional[str] = None
    email: Optional[str] = None
    user_id: Optional[int] = None
    sort_order: int
    is_active: bool

    class Config:
        from_attributes = True


@router.get("/members", response_model=List[ContactCardMemberOut])
async def list_members(user=Depends(_require_auth)):
    from database.models.contact_card import ContactCardMember
    from database import get_db as db_getter
    db: Session = next(db_getter())
    try:
        org_id = getattr(user, "organization_id", None)
        if not org_id:
            return []
        rows = (
            db.query(ContactCardMember)
            .filter(ContactCardMember.organization_id == org_id)
            .order_by(ContactCardMember.sort_order, ContactCardMember.id)
            .all()
        )
        return [ContactCardMemberOut.model_validate(r) for r in rows]
    finally:
        db.close()


@router.post("/members", response_model=ContactCardMemberOut, status_code=201)
async def add_member(body: ContactCardMemberIn, user=Depends(_require_auth)):
    from database.models.contact_card import ContactCardMember
    from database import get_db as db_getter
    db: Session = next(db_getter())
    try:
        org_id = getattr(user, "organization_id", None)
        if not org_id:
            raise HTTPException(status_code=400, detail="No organization")
        member = ContactCardMember(
            organization_id=org_id,
            user_id=body.user_id,
            name=body.name,
            role_label=body.role_label,
            phone=body.phone,
            email=body.email,
            sort_order=body.sort_order,
            is_active=body.is_active,
        )
        db.add(member)
        db.commit()
        db.refresh(member)
        return ContactCardMemberOut.model_validate(member)
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.exception("Failed to add contact card member")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()


@router.put("/members/{member_id}", response_model=ContactCardMemberOut)
async def update_member(member_id: int, body: ContactCardMemberIn, user=Depends(_require_auth)):
    from database.models.contact_card import ContactCardMember
    from database import get_db as db_getter
    db: Session = next(db_getter())
    try:
        org_id = getattr(user, "organization_id", None)
        member = db.query(ContactCardMember).filter(
            ContactCardMember.id == member_id,
            ContactCardMember.organization_id == org_id,
        ).first()
        if not member:
            raise HTTPException(status_code=404, detail="Member not found")
        member.name = body.name
        member.role_label = body.role_label
        member.phone = body.phone
        member.email = body.email
        member.user_id = body.user_id
        member.sort_order = body.sort_order
        member.is_active = body.is_active
        db.commit()
        db.refresh(member)
        return ContactCardMemberOut.model_validate(member)
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.exception("Failed to update contact card member")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()


@router.delete("/members/{member_id}", status_code=204)
async def delete_member(member_id: int, user=Depends(_require_auth)):
    from database.models.contact_card import ContactCardMember
    from database import get_db as db_getter
    db: Session = next(db_getter())
    try:
        org_id = getattr(user, "organization_id", None)
        member = db.query(ContactCardMember).filter(
            ContactCardMember.id == member_id,
            ContactCardMember.organization_id == org_id,
        ).first()
        if not member:
            raise HTTPException(status_code=404, detail="Member not found")
        db.delete(member)
        db.commit()
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()
