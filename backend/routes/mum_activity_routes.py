"""
MUM Client & Activity Routes
Extracted from inline_legacy_routes.py.

Includes:
- Referral score calculation endpoints (leads, loans, MUM clients)
- Funded loan -> MUM client conversion (helper + endpoint)
- MUM clients CRUD
- Activities CRUD

Lines ~20814-21293 from inline_legacy_routes.py.
"""
from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime, timedelta, timezone
from typing import List, Optional
import logging

logger = logging.getLogger(__name__)

# Import models
from database.models import (
    User, Lead, Loan, MUMClient, Activity,
)

# Import enums
from database.enums import LoanStage

# Import schemas
from schemas.core import (
    MUMClientCreate, MUMClientUpdate, MUMClientResponse,
    ActivityCreate, ActivityResponse,
)

# Import permission helpers
from routes.permission_core_routes import (
    require_permission_or_403,
    filter_mum_clients_by_permissions,
    check_resource_access,
)


def register_mum_activity_routes(app, get_db, get_current_user, get_current_user_flexible, **kwargs):
    """Register MUM client and activity routes.

    Required args:
        get_current_user_flexible: Auth dependency (Bearer + X-API-Key)

    Optional kwargs:
        calculate_referral_scores: function to calculate referral scores from data dict
    """
    calculate_referral_scores = kwargs.get('calculate_referral_scores')

    # ============================================================================
    # REFERRAL SCORE CALCULATION
    # ============================================================================

    @app.post("/api/v1/leads/{lead_id}/calculate-referral-scores")
    async def calculate_lead_referral_scores(lead_id: int, data: dict, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
        """Calculate AI-based referral intelligence scores for a lead"""
        lead = db.query(Lead).filter(Lead.id == lead_id).first()
        if not lead:
            raise HTTPException(status_code=404, detail="Lead not found")

        # Calculate scores based on employment data
        scores = calculate_referral_scores(data)

        # Update lead with calculated scores
        _protected = {'id', 'organization_id', 'created_at', 'updated_at', 'user_id'}
        for key, value in scores.items():
            if hasattr(lead, key) and key not in _protected:
                setattr(lead, key, value)

        db.commit()
        db.refresh(lead)

        return scores

    @app.post("/api/v1/loans/{loan_id}/calculate-referral-scores")
    async def calculate_loan_referral_scores(loan_id: int, data: dict, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
        """Calculate AI-based referral intelligence scores for a loan"""
        loan = db.query(Loan).filter(Loan.id == loan_id).first()
        if not loan:
            raise HTTPException(status_code=404, detail="Loan not found")

        scores = calculate_referral_scores(data)

        _protected = {'id', 'organization_id', 'created_at', 'updated_at', 'user_id'}
        for key, value in scores.items():
            if hasattr(loan, key) and key not in _protected:
                setattr(loan, key, value)

        db.commit()
        db.refresh(loan)

        return scores

    @app.post("/api/v1/mum/{client_id}/calculate-referral-scores")
    async def calculate_mum_referral_scores(client_id: int, data: dict, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
        """Calculate AI-based referral intelligence scores for a MUM client"""
        client = db.query(MUMClient).filter(MUMClient.id == client_id).first()
        if not client:
            raise HTTPException(status_code=404, detail="MUM client not found")

        scores = calculate_referral_scores(data)

        _protected = {'id', 'organization_id', 'created_at', 'updated_at', 'user_id'}
        for key, value in scores.items():
            if hasattr(client, key) and key not in _protected:
                setattr(client, key, value)

        db.commit()
        db.refresh(client)

        return scores

    # ============================================================================
    # FUNDED LOAN -> MUM CLIENT CONVERSION
    # ============================================================================

    @app.post("/api/v1/loans/{loan_id}/convert-to-mum")
    async def convert_loan_to_mum_client(
        loan_id: int,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
    ):
        """
        Manually convert a funded loan to MUM client.
        Use this for existing funded loans that weren't auto-converted.
        """
        from services.mum_promotion_service import maybe_promote_loan_to_mum

        loan = db.query(Loan).filter(Loan.id == loan_id).first()
        if not loan:
            raise HTTPException(status_code=404, detail="Loan not found")

        # Check if already funded or mark as funded
        if loan.stage != LoanStage.FUNDED:
            loan.stage = LoanStage.FUNDED
            loan.funded_date = datetime.now(timezone.utc)
            logger.info(f"Marking loan {loan.loan_number} as FUNDED")

        mum_client_id = maybe_promote_loan_to_mum(db, loan.id, current_user.id)
        if not mum_client_id:
            raise HTTPException(status_code=500, detail="Failed to create MUM client")

        db.commit()

        return {
            "status": "success",
            "message": f"Loan {loan.loan_number} converted to MUM client",
            "loan_id": loan.id,
            "mum_client_id": mum_client_id,
            "borrower_name": loan.borrower_name
        }


    # ============================================================================
    # BATCH MUM PROMOTION (catch-up for existing funded loans)
    # ============================================================================

    @app.post("/api/v1/mum-clients/batch-promote")
    async def batch_promote_funded_loans(
        dry_run: bool = False,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
    ):
        """
        Batch-promote all funded loans that don't yet have a MUM client.
        Use ?dry_run=true to preview without making changes.
        """
        from sqlalchemy import text
        from services.mum_promotion_service import maybe_promote_loan_to_mum

        # Find all funded loans without a matching MUM client
        eligible = db.execute(text("""
            SELECT l.id, l.loan_number, l.borrower_name, l.stage,
                   l.funded_date, l.closing_date
            FROM loans l
            LEFT JOIN mum_clients mc ON mc.loan_number = l.loan_number
            WHERE mc.id IS NULL
              AND (
                l.funded_date IS NOT NULL
                OR l.closing_date IS NOT NULL
                OR UPPER(l.stage::text) = 'FUNDED'
              )
            ORDER BY COALESCE(l.funded_date, l.closing_date) DESC
        """)).fetchall()

        if dry_run:
            preview = []
            for row in eligible:
                preview.append({
                    "loan_id": row[0],
                    "loan_number": row[1],
                    "borrower_name": row[2],
                    "stage": row[3],
                    "funded_date": str(row[4]) if row[4] else None,
                    "closing_date": str(row[5]) if row[5] else None,
                })
            return {
                "dry_run": True,
                "eligible_count": len(eligible),
                "loans": preview,
            }

        promoted = 0
        skipped = 0
        errors = []

        for row in eligible:
            loan_id = row[0]
            try:
                mum_id = maybe_promote_loan_to_mum(db, loan_id, current_user.id)
                if mum_id:
                    promoted += 1
                else:
                    skipped += 1
            except Exception as e:
                errors.append({"loan_id": loan_id, "error": "Internal server error"})
                logger.error(f"Batch promote error for loan {loan_id}: {e}")

        # Repair existing MUM clients: fix user_id and organization_id from their linked loan
        repaired = 0
        try:
            repair_rows = db.execute(text("""
                SELECT mc.id, l.loan_officer_id, l.organization_id
                FROM mum_clients mc
                JOIN loans l ON l.loan_number = mc.loan_number
                WHERE mc.organization_id IS DISTINCT FROM l.organization_id
                   OR (l.loan_officer_id IS NOT NULL AND mc.user_id != l.loan_officer_id)
            """)).fetchall()
            for r in repair_rows:
                mc_id, lo_id, org_id = r[0], r[1], r[2]
                updates = {"org_id": org_id, "mc_id": mc_id}
                if lo_id:
                    db.execute(text("""
                        UPDATE mum_clients
                        SET user_id = :lo_id, organization_id = :org_id
                        WHERE id = :mc_id
                    """), {**updates, "lo_id": lo_id})
                else:
                    db.execute(text("""
                        UPDATE mum_clients
                        SET organization_id = :org_id
                        WHERE id = :mc_id
                    """), updates)
                repaired += 1
            if repaired:
                logger.info(f"Repaired user_id/organization_id on {repaired} MUM clients")
        except Exception as e:
            logger.warning(f"MUM client repair step failed: {e}")

        db.commit()

        return {
            "dry_run": False,
            "promoted": promoted,
            "skipped": skipped,
            "repaired": repaired,
            "errors": errors,
            "total_eligible": len(eligible),
        }


    # ============================================================================
    # MUM CLIENTS CRUD
    # ============================================================================

    @app.post("/api/v1/mum-clients/", response_model=MUMClientResponse, status_code=201)
    async def create_mum_client(client: MUMClientCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
        # PHASE 3: Check create permission
        require_permission_or_403(current_user.id, 'clients.create', db)

        try:
            existing = db.query(MUMClient).filter(MUMClient.loan_number == client.loan_number).first()
            if existing:
                raise HTTPException(status_code=400, detail="Loan number already exists in MUM clients")

            # Calculate days since funding - make timezone-aware if needed
            original_close_dt = client.original_close_date if client.original_close_date.tzinfo else client.original_close_date.replace(tzinfo=timezone.utc)
            days_since = (datetime.now(timezone.utc) - original_close_dt).days

            # Create MUM client with explicit field assignment
            # Map to actual database column names (several have NOT NULL constraints)
            # Use loan_balance * 1.2 as estimated property value for appraisal values
            estimated_property_value = client.loan_balance * 1.2  # Assume 80% LTV
            db_client = MUMClient(
                client_name=client.name,  # Map to 'client_name' column (NOT NULL)
                email=client.email,
                phone=client.phone,
                loan_number=client.loan_number,
                original_close_date=client.original_close_date,
                closing_date=client.original_close_date,                # NOT NULL in DB
                original_rate=client.original_rate,
                interest_rate=client.original_rate,                     # NOT NULL in DB
                original_loan_amount=client.loan_balance,               # NOT NULL in DB
                current_loan_amount=client.loan_balance,                # NOT NULL in DB
                appraisal_value_at_closing=estimated_property_value,    # NOT NULL in DB
                current_property_value=estimated_property_value,        # NOT NULL in DB
                loan_balance=client.loan_balance,
                status=client.status or "Active",
                notes=client.notes,
                days_since_funding=days_since,
                user_id=current_user.id
            )

            db.add(db_client)
            db.commit()
            db.refresh(db_client)

            logger.info(f"MUM client created: {db_client.name}")
            return db_client
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error creating MUM client: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            db.rollback()
            raise HTTPException(status_code=500, detail="Error creating MUM client")

    @app.get("/api/v1/mum-clients/")
    async def get_mum_clients(skip: int = 0, limit: int = 100, db: Session = Depends(get_db), current_user: User = Depends(get_current_user_flexible)):
        """List MUM clients with permission-based filtering (PHASE 5: supports impersonation)"""
        # PHASE 3: Apply permission-based filtering
        query = db.query(MUMClient)
        query = filter_mum_clients_by_permissions(query, current_user, db)
        clients = query.order_by(MUMClient.created_at.desc()).offset(skip).limit(limit).all()

        # Enhance MUM clients with AI intelligence
        enhanced_clients = []
        for client in clients:
            client_dict = {
                "id": client.id,
                "name": client.name,
                "loan_number": client.loan_number,
                "original_close_date": client.original_close_date,
                "days_since_funding": client.days_since_funding,
                "original_rate": client.original_rate,
                "current_rate": client.current_rate,
                "loan_balance": client.loan_balance,
                "refinance_opportunity": client.refinance_opportunity,
                "estimated_savings": client.estimated_savings,
                "engagement_score": client.engagement_score,
                "status": client.status,
                "last_contact": client.last_contact,
                "created_at": client.created_at
            }

            # Add AI intent classification for MUM clients (Client for Life)
            client_dict["client_intent"] = "Client for Life Opportunity"
            if client.refinance_opportunity:
                client_dict["client_intent_description"] = f"Refinance opportunity with estimated savings of ${client.estimated_savings:,.2f}" if client.estimated_savings else "Refinance opportunity detected"
            else:
                client_dict["client_intent_description"] = "Maintain client relationship for future opportunities"

            # Generate recommended action for MUM clients
            if client.refinance_opportunity and client.estimated_savings and client.estimated_savings > 0:
                client_dict["recommended_action"] = {
                    "title": "Contact for Refinance Opportunity",
                    "description": f"AI recommends reaching out to {client.name} about refinancing. They could save approximately ${client.estimated_savings:,.2f} based on current market rates.",
                    "action_type": "outreach",
                    "action_value": "refinance_contact",
                    "learning_status": "Learning from your client engagement patterns"
                }
            elif client.days_since_funding and client.days_since_funding > 365:
                client_dict["recommended_action"] = {
                    "title": "Annual Check-in",
                    "description": f"AI recommends an annual check-in with {client.name}. It's been {client.days_since_funding} days since their loan closed.",
                    "action_type": "outreach",
                    "action_value": "annual_checkin",
                    "learning_status": "Learning from your client engagement patterns"
                }
            else:
                client_dict["recommended_action"] = {
                    "title": "Maintain Relationship",
                    "description": f"AI recommends continuing to nurture relationship with {client.name} for future opportunities.",
                    "action_type": "nurture",
                    "action_value": "relationship_maintenance",
                    "learning_status": "Learning from your client engagement patterns"
                }

            enhanced_clients.append(client_dict)

        return enhanced_clients

    @app.get("/api/v1/mum-clients/{client_id}", response_model=MUMClientResponse)
    async def get_mum_client(client_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user_flexible)):
        """Get single MUM client with permission filtering (PHASE 5: supports impersonation)"""
        # Apply permission filter to the query
        query = db.query(MUMClient).filter(MUMClient.id == client_id)
        query = filter_mum_clients_by_permissions(query, current_user, db)
        client = query.first()
        if not client:
            raise HTTPException(status_code=404, detail="MUM client not found or access denied")
        return client

    @app.patch("/api/v1/mum-clients/{client_id}", response_model=MUMClientResponse)
    async def update_mum_client(client_id: int, client_update: MUMClientUpdate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user_flexible)):
        """Update MUM client with permission checks (PHASE 5: supports impersonation)"""
        # Apply permission filter to find the client
        query = db.query(MUMClient).filter(MUMClient.id == client_id)
        query = filter_mum_clients_by_permissions(query, current_user, db)
        client = query.first()
        if not client:
            raise HTTPException(status_code=404, detail="MUM client not found or access denied")

        # Permission check: must have clients.edit_all or (clients.edit_own and be the owner)
        check_resource_access(current_user.id, client.user_id or current_user.id, 'clients.edit_all', 'clients.edit_own', db)

        for key, value in client_update.dict(exclude_unset=True).items():
            setattr(client, key, value)

        # Check for refinance opportunity
        if client.current_rate and client.original_rate:
            if client.original_rate - client.current_rate >= 0.5:
                client.refinance_opportunity = True
                # Rough calculation
                client.estimated_savings = (client.loan_balance or 0) * (client.original_rate - client.current_rate) / 100

        db.commit()
        db.refresh(client)

        logger.info(f"MUM client updated: {client.name}")
        return client

    @app.delete("/api/v1/mum-clients/{client_id}", status_code=204)
    async def delete_mum_client(client_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user_flexible)):
        """Delete MUM client with permission checks (PHASE 5: supports impersonation)"""
        # Permission check: must have clients.delete permission
        require_permission_or_403(current_user.id, 'clients.delete', db)

        # Apply permission filter to find the client
        query = db.query(MUMClient).filter(MUMClient.id == client_id)
        query = filter_mum_clients_by_permissions(query, current_user, db)
        client = query.first()
        if not client:
            raise HTTPException(status_code=404, detail="MUM client not found or access denied")

        db.delete(client)
        db.commit()
        logger.info(f"MUM client deleted: {client.name}")
        return None


    # ============================================================================
    # ACTIVITIES CRUD
    # ============================================================================

    @app.post("/api/v1/activities/", response_model=ActivityResponse, status_code=201)
    async def create_activity(activity: ActivityCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
        db_activity = Activity(
            **activity.model_dump(),
            user_id=current_user.id
        )

        db.add(db_activity)
        db.commit()
        db.refresh(db_activity)

        # Update last_contact on lead if applicable
        if activity.lead_id:
            lead = db.query(Lead).filter(Lead.id == activity.lead_id).first()
            if lead:
                lead.last_contact = datetime.now(timezone.utc)
                db.commit()

        # Update last_contact on MUM client if applicable
        if activity.mum_client_id:
            mum_client = db.query(MUMClient).filter(MUMClient.id == activity.mum_client_id).first()
            if mum_client:
                mum_client.last_contact = datetime.now(timezone.utc)
                db.commit()

        logger.info(f"Activity created: {db_activity.type.value}")
        return db_activity

    @app.get("/api/v1/activities/", response_model=List[ActivityResponse])
    async def get_activities(
        skip: int = 0,
        limit: int = 100,
        lead_id: Optional[int] = None,
        loan_id: Optional[int] = None,
        mum_client_id: Optional[int] = None,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)
    ):
        query = db.query(Activity).filter(Activity.user_id == current_user.id)

        if lead_id:
            query = query.filter(Activity.lead_id == lead_id)
        if loan_id:
            query = query.filter(Activity.loan_id == loan_id)
        if mum_client_id:
            query = query.filter(Activity.mum_client_id == mum_client_id)

        activities = query.order_by(Activity.created_at.desc()).offset(skip).limit(limit).all()
        return activities

    @app.delete("/api/v1/activities/{activity_id}", status_code=204)
    async def delete_activity(activity_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
        activity = db.query(Activity).filter(Activity.id == activity_id, Activity.user_id == current_user.id).first()
        if not activity:
            raise HTTPException(status_code=404, detail="Activity not found")

        db.delete(activity)
        db.commit()
        logger.info(f"Activity deleted: {activity.type.value}")
        return None
