"""
Portal Lifecycle Service - Manages loan lifecycle stages for the Perennia Portal.

Handles stage transitions, audit logging, and lifecycle state management
for the 8-stage mortgage journey.
"""

import logging
from typing import Optional, Dict, Any, List
from datetime import datetime, date, timezone
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_

from sqlalchemy.exc import SQLAlchemyError
from models.portal_models import (
    LifecycleStage, PortalLoan, LifecycleStateHistory,
    MilestoneInstance, MilestoneStatus, LoanActivityLog, RiskFlag
)

logger = logging.getLogger(__name__)


# Stage transition rules - defines valid transitions
VALID_TRANSITIONS = {
    LifecycleStage.PROSPECT: [LifecycleStage.LEAD],
    LifecycleStage.LEAD: [LifecycleStage.PREAPPROVAL, LifecycleStage.PROSPECT],
    LifecycleStage.PREAPPROVAL: [LifecycleStage.UNDER_CONTRACT, LifecycleStage.LEAD],
    LifecycleStage.UNDER_CONTRACT: [LifecycleStage.PROCESSING, LifecycleStage.PREAPPROVAL],
    LifecycleStage.PROCESSING: [LifecycleStage.CLEAR_TO_CLOSE, LifecycleStage.UNDER_CONTRACT],
    LifecycleStage.CLEAR_TO_CLOSE: [LifecycleStage.FUNDED, LifecycleStage.PROCESSING],
    LifecycleStage.FUNDED: [LifecycleStage.MUM],
    LifecycleStage.MUM: [LifecycleStage.ANNUAL_REFRESH, LifecycleStage.PREAPPROVAL],
    LifecycleStage.ANNUAL_REFRESH: [LifecycleStage.MUM, LifecycleStage.PREAPPROVAL],
}

# Stage display names and descriptions
STAGE_INFO = {
    LifecycleStage.PROSPECT: {
        "display_name": "Prospect",
        "description": "Initial contact, not yet engaged",
        "color": "#9CA3AF",  # Gray
    },
    LifecycleStage.LEAD: {
        "display_name": "Lead",
        "description": "Engaged, exploring options",
        "color": "#3B82F6",  # Blue
    },
    LifecycleStage.PREAPPROVAL: {
        "display_name": "Pre-Approval",
        "description": "Application submitted, awaiting approval",
        "color": "#8B5CF6",  # Purple
    },
    LifecycleStage.UNDER_CONTRACT: {
        "display_name": "Under Contract",
        "description": "Property under contract",
        "color": "#F59E0B",  # Amber
    },
    LifecycleStage.PROCESSING: {
        "display_name": "Processing",
        "description": "Loan being processed",
        "color": "#EC4899",  # Pink
    },
    LifecycleStage.CLEAR_TO_CLOSE: {
        "display_name": "Clear to Close",
        "description": "Approved and ready to close",
        "color": "#10B981",  # Green
    },
    LifecycleStage.FUNDED: {
        "display_name": "Funded",
        "description": "Loan has been funded",
        "color": "#059669",  # Emerald
    },
    LifecycleStage.MUM: {
        "display_name": "Member Until Maturity",
        "description": "Active loan in servicing",
        "color": "#6366F1",  # Indigo
    },
    LifecycleStage.ANNUAL_REFRESH: {
        "display_name": "Annual Refresh",
        "description": "Annual review in progress",
        "color": "#F97316",  # Orange
    },
}


class PortalLifecycleService:
    """Service for managing loan lifecycle stages."""

    def __init__(self, db: Session):
        self.db = db

    # =========================================================================
    # PORTAL LOAN MANAGEMENT
    # =========================================================================

    def get_portal_loan(self, loan_id: int) -> Optional[PortalLoan]:
        """Get or create portal loan record for a loan."""
        try:
            # First try to find by primary key id
            portal_loan = self.db.query(PortalLoan).filter(
                PortalLoan.id == loan_id
            ).first()

            # If not found by id, try by crm_deal_id
            if not portal_loan:
                portal_loan = self.db.query(PortalLoan).filter(
                    PortalLoan.crm_deal_id == loan_id
                ).first()

            if not portal_loan:
                # Create new portal loan with default stage
                portal_loan = PortalLoan(
                    crm_deal_id=loan_id,
                    lifecycle_stage=LifecycleStage.PROSPECT,
                )
                self.db.add(portal_loan)
                self.db.commit()
                self.db.refresh(portal_loan)
                logger.info(f"Created portal loan record for crm_deal_id={loan_id}")

            return portal_loan
        except SQLAlchemyError as e:
            # portal_loans table may not exist - rollback and return None
            logger.warning(f"Could not get/create portal loan for {loan_id}: {e}")
            self.db.rollback()
            return None

    def get_portal_loan_by_crm_deal_id(self, crm_loan_id: int) -> Optional[PortalLoan]:
        """Borrower (PURL) read-path resolver: match crm_deal_id ONLY.

        The borrower dashboard path must never resolve a PortalLoan by its
        primary key from a client-supplied integer. That path value is a CRM
        loan id (PURLLoan.main_loan_id); PortalLoan.id is a different id-space
        and PortalLoan carries no organization_id, so a foreign tenant's
        PortalLoan.id colliding with this borrower's CRM loan id would leak
        cross-tenant data (the `get_portal_loan` dual-precedence resolver hits
        `PortalLoan.id == loan_id` first). Ownership is already proven by the
        route guard against the org/workspace-scoped purl_loans table; here we
        only locate the matching PortalLoan by crm_deal_id, with NO id-match and
        NO lazy create (a borrower GET must never write).

        Returns None (caller -> 404) when no PortalLoan exists for this loan.
        """
        try:
            return (
                self.db.query(PortalLoan)
                .filter(PortalLoan.crm_deal_id == crm_loan_id)
                .first()
            )
        except SQLAlchemyError as e:
            logger.warning(
                f"Could not resolve portal loan by crm_deal_id={crm_loan_id}: {e}"
            )
            self.db.rollback()
            return None

    def get_portal_loan_by_token(self, access_token: str) -> Optional[PortalLoan]:
        """Get portal loan by partner access token."""
        from models.portal_models import PartnerAccessToken

        token = self.db.query(PartnerAccessToken).filter(
            and_(
                PartnerAccessToken.token == access_token,
                PartnerAccessToken.is_active == True,
                or_(
                    PartnerAccessToken.expires_at.is_(None),
                    PartnerAccessToken.expires_at > datetime.now(timezone.utc)
                )
            )
        ).first()

        if token:
            # Update last used
            token.last_used_at = datetime.now(timezone.utc)
            self.db.commit()
            return token.portal_loan

        return None

    # =========================================================================
    # LIFECYCLE STAGE MANAGEMENT
    # =========================================================================

    def get_current_stage(self, loan_id: int) -> Dict[str, Any]:
        """Get current lifecycle stage with details."""
        portal_loan = self.get_portal_loan(loan_id)

        # Handle case where portal_loans table doesn't exist
        if not portal_loan:
            return {
                "stage": "ACTIVE",
                "display_name": "Active",
                "description": "Loan is currently active",
                "color": "#10B981",
                "entered_at": None,
                "days_in_stage": 0,
            }

        stage = portal_loan.lifecycle_stage
        stage_info = STAGE_INFO.get(stage, {})

        return {
            "stage": stage.value,
            "display_name": stage_info.get("display_name", stage.value),
            "description": stage_info.get("description", ""),
            "color": stage_info.get("color", "#6B7280"),
            "entered_at": portal_loan.lifecycle_stage_entered_at.isoformat() if portal_loan.lifecycle_stage_entered_at else None,
            "days_in_stage": self._calculate_days_in_stage(portal_loan),
        }

    def get_stage_history(self, loan_id: int) -> List[Dict[str, Any]]:
        """Get lifecycle stage transition history."""
        history = self.db.query(LifecycleStateHistory).filter(
            LifecycleStateHistory.loan_id == loan_id
        ).order_by(LifecycleStateHistory.transitioned_at.desc()).all()

        return [
            {
                "from_stage": h.from_stage.value if h.from_stage else None,
                "to_stage": h.to_stage.value,
                "transitioned_at": h.transitioned_at.isoformat(),
                "transitioned_by": h.transitioned_by,
                "reason": h.reason,
                "metadata": h.metadata,
            }
            for h in history
        ]

    def transition_stage(
        self,
        loan_id: int,
        new_stage: LifecycleStage,
        transitioned_by: Optional[str] = None,
        reason: Optional[str] = None,
        metadata: Optional[Dict] = None,
        force: bool = False,
    ) -> Dict[str, Any]:
        """
        Transition a loan to a new lifecycle stage.

        Args:
            loan_id: The loan ID
            new_stage: The target lifecycle stage
            transitioned_by: User who initiated the transition
            reason: Reason for the transition
            metadata: Additional metadata to store
            force: Skip validation (admin only)

        Returns:
            Dict with success status and details
        """
        portal_loan = self.get_portal_loan(loan_id)
        current_stage = portal_loan.lifecycle_stage

        # Validate transition
        if not force:
            valid_targets = VALID_TRANSITIONS.get(current_stage, [])
            if new_stage not in valid_targets:
                return {
                    "success": False,
                    "error": f"Invalid transition from {current_stage.value} to {new_stage.value}",
                    "valid_transitions": [s.value for s in valid_targets],
                }

        # Record history
        history = LifecycleStateHistory(
            loan_id=loan_id,
            from_stage=current_stage,
            to_stage=new_stage,
            transitioned_by=transitioned_by,
            reason=reason,
            metadata=metadata or {},
        )
        self.db.add(history)

        # Update portal loan
        portal_loan.lifecycle_stage = new_stage
        portal_loan.lifecycle_stage_entered_at = datetime.now(timezone.utc)

        # Log activity
        self._log_activity(
            loan_id=loan_id,
            activity_type="stage_transition",
            description=f"Stage changed from {current_stage.value} to {new_stage.value}",
            metadata={
                "from_stage": current_stage.value,
                "to_stage": new_stage.value,
                "reason": reason,
            },
            actor=transitioned_by,
        )

        self.db.commit()

        logger.info(f"Loan {loan_id} transitioned from {current_stage.value} to {new_stage.value}")

        return {
            "success": True,
            "from_stage": current_stage.value,
            "to_stage": new_stage.value,
            "transitioned_at": datetime.now(timezone.utc).isoformat(),
        }

    def get_valid_transitions(self, loan_id: int) -> List[Dict[str, Any]]:
        """Get valid stage transitions from current stage."""
        portal_loan = self.get_portal_loan(loan_id)
        current_stage = portal_loan.lifecycle_stage
        valid_stages = VALID_TRANSITIONS.get(current_stage, [])

        return [
            {
                "stage": stage.value,
                "display_name": STAGE_INFO.get(stage, {}).get("display_name", stage.value),
                "description": STAGE_INFO.get(stage, {}).get("description", ""),
                "color": STAGE_INFO.get(stage, {}).get("color", "#6B7280"),
            }
            for stage in valid_stages
        ]

    # =========================================================================
    # ACTIVITY & HEARTBEAT
    # =========================================================================

    def record_heartbeat(
        self,
        loan_id: int,
        activity_type: str,
        description: str,
        metadata: Optional[Dict] = None,
        actor: Optional[str] = None,
        is_visible_to_borrower: bool = True,
    ) -> Dict[str, Any]:
        """Record an activity for the loan heartbeat feature."""
        activity = self._log_activity(
            loan_id=loan_id,
            activity_type=activity_type,
            description=description,
            metadata=metadata,
            actor=actor,
            is_visible_to_borrower=is_visible_to_borrower,
        )

        return {
            "activity_id": activity.id,
            "recorded_at": activity.created_at.isoformat(),
        }

    def get_recent_activity(
        self,
        loan_id: int,
        limit: int = 20,
        borrower_visible_only: bool = False,
    ) -> List[Dict[str, Any]]:
        """Get recent activity for loan heartbeat display."""
        # Get the portal loan to get the correct loan_id for activity log
        portal_loan = self.get_portal_loan(loan_id)
        resolved_id = portal_loan.id if portal_loan else loan_id

        try:
            query = self.db.query(LoanActivityLog).filter(
                LoanActivityLog.loan_id == resolved_id
            )

            if borrower_visible_only:
                query = query.filter(LoanActivityLog.visible_to_borrower == True)

            activities = query.order_by(
                LoanActivityLog.created_at.desc()
            ).limit(limit).all()

            return [
                {
                    "id": a.id,
                    "activity_type": a.activity_type,
                    "description": a.activity_description or a.activity_title,
                    "metadata": a.extra_data,
                    "actor": f"User {a.actor_id}" if a.actor_id else (a.actor_role.value if a.actor_role else None),
                    "created_at": a.created_at.isoformat() if a.created_at else None,
                }
                for a in activities
            ]
        except Exception as e:
            logger.warning(f"Could not get activity for loan {loan_id}: {e}")
            self.db.rollback()
            return []

    # =========================================================================
    # RISK RADAR
    # =========================================================================

    def add_risk_flag(
        self,
        loan_id: int,
        risk_type: str,
        severity: str,
        description: str,
        recommended_action: Optional[str] = None,
        auto_resolve_condition: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Add a risk flag to a loan."""
        risk_flag = RiskFlag(
            loan_id=loan_id,
            flag_type=risk_type,
            severity=severity,
            description=description,
            title=f"{risk_type} - {severity}",
            auto_resolve_condition=auto_resolve_condition,
            is_resolved=False,
        )
        self.db.add(risk_flag)
        self.db.commit()
        self.db.refresh(risk_flag)

        logger.info(f"Risk flag added to loan {loan_id}: {risk_type} ({severity})")

        return {
            "flag_id": risk_flag.id,
            "risk_type": risk_type,
            "severity": severity,
        }

    def resolve_risk_flag(
        self,
        flag_id: int,
        resolved_by: Optional[str] = None,
        resolution_notes: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Resolve a risk flag."""
        risk_flag = self.db.query(RiskFlag).filter(RiskFlag.id == flag_id).first()

        if not risk_flag:
            return {"success": False, "error": "Risk flag not found"}

        risk_flag.is_resolved = True
        risk_flag.resolved_at = datetime.now(timezone.utc)
        risk_flag.resolved_by = resolved_by
        risk_flag.resolution_notes = resolution_notes

        self.db.commit()

        return {"success": True, "resolved_at": risk_flag.resolved_at.isoformat()}

    def get_active_risks(self, loan_id: int) -> List[Dict[str, Any]]:
        """Get active risk flags for a loan."""
        try:
            risks = self.db.query(RiskFlag).filter(
                and_(
                    RiskFlag.loan_id == loan_id,
                    RiskFlag.is_resolved == False
                )
            ).order_by(
                RiskFlag.severity.desc(),
                RiskFlag.created_at.desc()
            ).all()

            return [
                {
                    "id": r.id,
                    "risk_type": r.risk_type,
                    "severity": r.severity,
                    "description": r.description,
                    "recommended_action": r.recommended_action,
                    "created_at": r.created_at.isoformat(),
                }
                for r in risks
            ]
        except Exception as e:
            logger.warning(f"Could not get risks for loan {loan_id}: {e}")
            self.db.rollback()
            return []

    # =========================================================================
    # PORTAL STATUS
    # =========================================================================

    def get_portal_status(self, loan_id: int) -> Dict[str, Any]:
        """Get comprehensive portal status for a loan."""
        portal_loan = self.get_portal_loan(loan_id)

        # Use portal_loan.id for milestone queries (not crm_deal_id)
        portal_loan_id = portal_loan.id if portal_loan else loan_id

        # Get milestone progress (with error handling for missing tables)
        total_milestones = 0
        completed_milestones = 0
        try:
            total_milestones = self.db.query(MilestoneInstance).filter(
                MilestoneInstance.loan_id == portal_loan_id
            ).count()

            completed_milestones = self.db.query(MilestoneInstance).filter(
                and_(
                    MilestoneInstance.loan_id == portal_loan_id,
                    MilestoneInstance.status == MilestoneStatus.COMPLETE
                )
            ).count()
        except SQLAlchemyError as e:
            logger.warning(f"Could not query milestones for {loan_id}: {e}")
            self.db.rollback()

        # Get active risks (with error handling for missing tables)
        active_risks = 0
        try:
            active_risks = self.db.query(RiskFlag).filter(
                and_(
                    RiskFlag.loan_id == portal_loan_id,
                    RiskFlag.is_resolved == False
                )
            ).count()
        except SQLAlchemyError as e:
            logger.warning(f"Could not query risks for {loan_id}: {e}")
            self.db.rollback()

        return {
            "loan_id": loan_id,
            "portal_enabled": portal_loan.is_active if portal_loan else True,
            "partner_portal_enabled": True,  # Default to enabled
            "lifecycle": self.get_current_stage(loan_id),
            "progress": {
                "total_milestones": total_milestones,
                "completed_milestones": completed_milestones,
                "progress_percent": round(
                    (completed_milestones / total_milestones * 100) if total_milestones > 0 else 0,
                    1
                ),
            },
            "risks": {
                "active_count": active_risks,
                "has_critical": active_risks > 0,  # Simplified; could check severity
            },
            "last_activity_at": portal_loan.updated_at.isoformat() if portal_loan and portal_loan.updated_at else None,
        }

    def enable_portal(self, loan_id: int, enable: bool = True) -> Dict[str, Any]:
        """Enable or disable the borrower portal for a loan."""
        portal_loan = self.get_portal_loan(loan_id)
        portal_loan.is_active = enable
        self.db.commit()

        return {"success": True, "portal_enabled": enable}

    def enable_partner_portal(self, loan_id: int, enable: bool = True) -> Dict[str, Any]:
        """Enable or disable the partner portal for a loan."""
        # Note: partner_portal_enabled is not in the current model
        # Just return success for now
        return {"success": True, "partner_portal_enabled": enable}

    # =========================================================================
    # HELPER METHODS
    # =========================================================================

    def _calculate_days_in_stage(self, portal_loan: PortalLoan) -> int:
        """Calculate days in current stage."""
        if not portal_loan.lifecycle_stage_entered_at:
            return 0
        delta = datetime.now(timezone.utc) - portal_loan.lifecycle_stage_entered_at
        return delta.days

    def _log_activity(
        self,
        loan_id: int,
        activity_type: str,
        description: str,
        metadata: Optional[Dict] = None,
        actor: Optional[str] = None,
        is_visible_to_borrower: bool = True,
    ) -> LoanActivityLog:
        """Internal method to log activity."""
        activity = LoanActivityLog(
            loan_id=loan_id,
            activity_type=activity_type,
            description=description,
            metadata=metadata or {},
            actor=actor,
            is_visible_to_borrower=is_visible_to_borrower,
        )
        self.db.add(activity)

        # Update timestamp on portal loan (triggers updated_at)
        portal_loan = self.db.query(PortalLoan).filter(
            or_(PortalLoan.id == loan_id, PortalLoan.crm_deal_id == loan_id)
        ).first()
        if portal_loan:
            # Touch the updated_at timestamp by updating lifecycle_stage_reason
            portal_loan.lifecycle_stage_reason = portal_loan.lifecycle_stage_reason or ""

        self.db.commit()
        self.db.refresh(activity)

        return activity
