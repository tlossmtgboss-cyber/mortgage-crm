"""Admin routes for managing state disclosure requirements."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional

router = APIRouter(prefix="/api/v1/admin/state-disclosures", tags=["State Disclosures"])


def register_state_disclosure_routes(app, get_db):
    """Register state disclosure admin routes."""

    @router.get("")
    async def list_state_disclosures(
        state: Optional[str] = Query(None, description="Filter by state code (e.g., CA)"),
        category: Optional[str] = Query(None, description="Filter by category"),
        db: Session = Depends(get_db),
    ):
        from database.models.state_disclosure import StateDisclosure
        query = db.query(StateDisclosure)
        if state:
            query = query.filter(StateDisclosure.state_code == state.upper())
        if category:
            query = query.filter(StateDisclosure.category == category)
        results = query.order_by(StateDisclosure.state_code, StateDisclosure.category).all()
        return {
            "count": len(results),
            "disclosures": [
                {
                    "id": r.id,
                    "state_code": r.state_code,
                    "state_name": r.state_name,
                    "category": r.category,
                    "requirement": r.requirement,
                    "applies_to_loan_types": r.applies_to_loan_types,
                    "regulatory_reference": r.regulatory_reference,
                    "effective_date": r.effective_date.isoformat() if r.effective_date else None,
                }
                for r in results
            ],
        }

    @router.put("/{disclosure_id}")
    async def update_state_disclosure(
        disclosure_id: int,
        requirement: Optional[str] = None,
        regulatory_reference: Optional[str] = None,
        db: Session = Depends(get_db),
    ):
        from database.models.state_disclosure import StateDisclosure
        disc = db.query(StateDisclosure).filter(StateDisclosure.id == disclosure_id).first()
        if not disc:
            raise HTTPException(status_code=404, detail="Disclosure not found")
        if requirement is not None:
            disc.requirement = requirement
        if regulatory_reference is not None:
            disc.regulatory_reference = regulatory_reference
        db.commit()
        return {"status": "updated", "id": disc.id}

    @router.get("/states")
    async def list_available_states(db: Session = Depends(get_db)):
        from database.models.state_disclosure import StateDisclosure
        from sqlalchemy import func as sqlfunc
        states = (
            db.query(
                StateDisclosure.state_code,
                StateDisclosure.state_name,
                sqlfunc.count().label("count"),
            )
            .group_by(StateDisclosure.state_code, StateDisclosure.state_name)
            .order_by(StateDisclosure.state_code)
            .all()
        )
        return {
            "count": len(states),
            "states": [
                {"code": s.state_code, "name": s.state_name, "requirements": s.count}
                for s in states
            ],
        }

    app.include_router(router)
