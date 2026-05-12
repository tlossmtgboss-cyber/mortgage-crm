"""Borrower-facing team contact routes.

Returns the lending team assigned to the borrower's application so the
POS portal can display contact cards with schedule/message/call actions.

Auth: PURL token — borrower must own the application.
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from database import get_db
from database.models.core import User
from database.models.lead_loan import Loan
from database.models.pos import POSApplication
from middleware.purl_auth import check_purl_rate_limit

from ._helpers import resolve_application_for_borrower

logger = logging.getLogger("pos.team.routes")

router = APIRouter(
    prefix="/api/v1/pos/applications",
    tags=["POS - Team"],
    dependencies=[Depends(check_purl_rate_limit)],
)


class TeamMemberResponse(BaseModel):
    user_id: int
    name: str
    role: str
    email: Optional[str] = None
    phone: Optional[str] = None
    title: Optional[str] = None
    avatar_url: Optional[str] = None
    nmls: Optional[str] = None

    class Config:
        from_attributes = True


class TeamResponse(BaseModel):
    application_id: str
    members: list[TeamMemberResponse]


def _user_to_member(user: User, role: str) -> TeamMemberResponse:
    return TeamMemberResponse(
        user_id=user.id,
        name=user.full_name,
        role=role,
        email=user.email,
        phone=user.phone,
        title=user.title,
        avatar_url=user.headshot_url,
        nmls=user.nmls_id or user.nmls_number,
    )


@router.get(
    "/{application_id}/team",
    response_model=TeamResponse,
    summary="Get the lending team assigned to this application",
)
def get_team(
    application: POSApplication = Depends(resolve_application_for_borrower),
    db: Session = Depends(get_db),
) -> TeamResponse:
    members: list[TeamMemberResponse] = []
    seen_ids: set[int] = set()

    # 1. Primary loan officer from loan assignment
    if application.loan_id is not None:
        loan = db.get(Loan, application.loan_id)
        if loan and getattr(loan, "loan_officer_id", None):
            lo = db.get(User, loan.loan_officer_id)
            if lo:
                members.append(_user_to_member(lo, "Loan Officer"))
                seen_ids.add(lo.id)

    # 2. Workflow role assignments for this org
    try:
        rows = db.execute(text("""
            SELECT dra.user_id, r.name as role_name
            FROM default_role_assignments dra
            JOIN roles r ON r.id = dra.role_id
            WHERE dra.organization_id = :org_id
            ORDER BY r.name, dra.user_id
        """), {"org_id": application.organization_id}).fetchall()

        # Batch-fetch all users at once to avoid N+1 queries.
        user_role_map: dict[int, str] = {}
        for row in rows:
            uid = row[0]
            role_name = row[1]
            if uid not in seen_ids and uid not in user_role_map:
                user_role_map[uid] = role_name

        if user_role_map:
            users = (
                db.query(User)
                .filter(User.id.in_(list(user_role_map.keys())), User.is_active.is_(True))
                .all()
            )
            users_by_id = {u.id: u for u in users}
            for uid, role_name in user_role_map.items():
                user = users_by_id.get(uid)
                if user:
                    members.append(_user_to_member(user, role_name))
                    seen_ids.add(uid)
    except Exception as e:
        logger.warning("Failed to load workflow role assignments: %s", e)

    # 3. Fallback: if no members found, get org's active users
    if not members:
        org_users = (
            db.query(User)
            .filter(
                User.organization_id == application.organization_id,
                User.is_active.is_(True),
            )
            .order_by(User.id.asc())
            .limit(10)
            .all()
        )
        for user in org_users:
            if user.id not in seen_ids:
                role = user.title or user.current_role or "Team Member"
                members.append(_user_to_member(user, role))
                seen_ids.add(user.id)

    return TeamResponse(
        application_id=str(application.id),
        members=members,
    )
