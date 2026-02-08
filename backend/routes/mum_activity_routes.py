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
    User, Lead, Loan, MUMClient, Activity, Task,
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
        for key, value in scores.items():
            if hasattr(lead, key):
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

        for key, value in scores.items():
            if hasattr(loan, key):
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

        for key, value in scores.items():
            if hasattr(client, key):
                setattr(client, key, value)

        db.commit()
        db.refresh(client)

        return scores

    # ============================================================================
    # FUNDED LOAN -> MUM CLIENT CONVERSION
    # ============================================================================

    def copy_loan_to_mum_client(loan: Loan, db: Session, user_id: int) -> Optional[MUMClient]:
        """
        When a loan reaches FUNDED status, copy it to the MUM (Mortgages Under Management)
        portfolio as a new client. This kicks off the post-close retention process.

        Returns the created MUMClient or None if one already exists.
        """
        from datetime import timedelta

        # Use a savepoint so we can rollback just the MUM client creation without affecting the loan update
        savepoint = db.begin_nested()
        try:
            # Check if MUM client already exists for this loan
            existing = db.query(MUMClient).filter(MUMClient.loan_number == loan.loan_number).first()
            if existing:
                logger.info(f"MUM client already exists for loan {loan.loan_number}")
                savepoint.commit()
                return existing

            # Calculate days since funding
            funded_date = loan.funded_date or loan.closing_date or datetime.now(timezone.utc)
            if not funded_date.tzinfo:
                funded_date = funded_date.replace(tzinfo=timezone.utc)
            days_since = (datetime.now(timezone.utc) - funded_date).days

            # Get loan amount with fallback to 0 if not set
            loan_amount = loan.amount or 0.0
            loan_rate = loan.rate or 0.0

            # Estimate property value (assume 80% LTV if not available)
            estimated_property_value = loan.appraisal_value or (loan_amount * 1.25 if loan_amount else 0.0)

            # Create MUM client from loan data
            mum_client = MUMClient(
                client_name=loan.borrower_name or "Unknown Borrower",
                email=loan.borrower_email,
                phone=loan.borrower_phone,
                loan_number=loan.loan_number,
                original_close_date=funded_date,
                closing_date=funded_date,
                first_payment_date=funded_date + timedelta(days=45),  # Estimate first payment ~45 days after close
                days_since_funding=days_since,
                original_rate=loan_rate,
                current_rate=loan_rate,
                interest_rate=loan_rate,
                original_loan_amount=loan_amount,
                current_loan_amount=loan_amount,
                appraisal_value_at_closing=estimated_property_value or 0.0,
                current_property_value=estimated_property_value or 0.0,
                loan_balance=loan_amount,
                refinance_opportunity=False,
                engagement_score=100,  # Start with high engagement for new funded loans
                status="Active",
                notes=f"Auto-created from funded loan on {datetime.now(timezone.utc).strftime('%Y-%m-%d')}. Program: {loan.program or 'N/A'}",
                # Copy team members
                loan_officer=loan.loan_officer_name,
                loan_officer_email=loan.loan_officer_email,
                processor=loan.processor,
                processor_email=loan.processor_email,
                underwriter=loan.underwriter,
                underwriter_email=loan.underwriter_email,
                closer=loan.closer,
                closer_email=loan.closer_email,
                user_id=user_id
            )

            db.add(mum_client)
            db.flush()  # Get the ID without committing

            logger.info(f"Created MUM client {mum_client.id} from funded loan {loan.loan_number} ({loan.borrower_name})")

            # Create post-close welcome task using Task model
            welcome_task = Task(
                title=f"Post-Close Welcome Call - {loan.borrower_name or 'Borrower'}",
                description=f"""Congratulations! {loan.borrower_name or 'Borrower'}'s loan has funded!

    Action items:
    1. Make welcome call to congratulate and thank them
    2. Set up annual mortgage review (AMR) reminder
    3. Request Google/Zillow review
    4. Ask for referrals
    5. Add to retention marketing campaigns

    Loan Details:
    - Loan #: {loan.loan_number}
    - Program: {loan.program or 'N/A'}
    - Amount: ${loan_amount:,.2f}
    - Rate: {loan_rate}%
    - Close Date: {funded_date.strftime('%Y-%m-%d')}""",
                priority="high",
                loan_id=loan.id,
                owner_id=user_id,
                related_contact_name=loan.borrower_name,
                related_type="post_close",
                due_date=datetime.now(timezone.utc) + timedelta(days=1),  # Due tomorrow
                status="pending"
            )
            db.add(welcome_task)

            # Create AMR reminder task for 11 months from now
            amr_task = Task(
                title=f"Annual Mortgage Review Due - {loan.borrower_name or 'Borrower'}",
                description=f"""Annual Mortgage Review (AMR) is coming up for {loan.borrower_name or 'Borrower'}.

    Review items:
    1. Check current market rates vs their rate ({loan_rate}%)
    2. Evaluate refinance opportunities
    3. Review home value appreciation
    4. Discuss any life changes affecting mortgage needs
    5. Explore HELOC/cash-out options if applicable

    Original Loan:
    - Loan #: {loan.loan_number}
    - Original Amount: ${loan_amount:,.2f}
    - Rate: {loan_rate}%""",
                priority="medium",
                loan_id=loan.id,
                owner_id=user_id,
                related_contact_name=loan.borrower_name,
                related_type="amr",
                due_date=datetime.now(timezone.utc) + timedelta(days=335),  # ~11 months
                status="pending"
            )
            db.add(amr_task)

            logger.info(f"Created post-close tasks for MUM client {mum_client.id}")

            # Commit the savepoint
            savepoint.commit()
            return mum_client

        except Exception as e:
            logger.error(f"Error creating MUM client from loan {loan.loan_number}: {e}")
            import traceback
            logger.error(traceback.format_exc())
            # Rollback only the savepoint, not the entire transaction (preserves loan status update)
            savepoint.rollback()
            return None


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
        loan = db.query(Loan).filter(Loan.id == loan_id).first()
        if not loan:
            raise HTTPException(status_code=404, detail="Loan not found")

        # Check if already funded or mark as funded
        if loan.stage != LoanStage.FUNDED:
            loan.stage = LoanStage.FUNDED
            loan.funded_date = datetime.now(timezone.utc)
            logger.info(f"Marking loan {loan.loan_number} as FUNDED")

        mum_client = copy_loan_to_mum_client(loan, db, current_user.id)
        if not mum_client:
            raise HTTPException(status_code=500, detail="Failed to create MUM client")

        db.commit()

        return {
            "status": "success",
            "message": f"Loan {loan.loan_number} converted to MUM client",
            "loan_id": loan.id,
            "mum_client_id": mum_client.id,
            "borrower_name": loan.borrower_name
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
            raise HTTPException(status_code=500, detail=f"Error creating MUM client: {str(e)}")

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
