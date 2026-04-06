"""
Listing Partner Agent — Domain 7 Marketing Sub-Agent

Sends listing-side partner (realtor) updates on every loan milestone.
Ensures realtors stay informed within 15 minutes of stage changes,
generates co-branded updates, and tracks partner communication history.

Milestones tracked:
    - Application received
    - Appraisal ordered
    - Clear to close
    - Closed/Funded

Usage:
    from services.marketing.listing_partner_agent import ListingPartnerAgent

    agent = ListingPartnerAgent()
    result = await agent.send_milestone_notification(
        loan_id=42,
        milestone="application_received",
        db=session,
    )
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import and_
from sqlalchemy.orm import Session

from database.models.lead_loan import Loan
from database.models.referral import ReferralPartner, LoanTeamMember
from database.models.communication import Activity
from database.models.security import Notification
from database.models.core import User
from database.enums import ActivityType

logger = logging.getLogger(__name__)

# Milestone definitions mapping internal keys to display info and
# the corresponding loan stage(s) that trigger them.
MILESTONE_DEFINITIONS: Dict[str, Dict[str, Any]] = {
    "application_received": {
        "label": "Application Received",
        "stages": ["APPLICATION"],
        "template": (
            "Great news! {borrower_name}'s loan application has been received "
            "and is now in processing. Loan #{loan_number}."
        ),
        "priority": "normal",
    },
    "appraisal_ordered": {
        "label": "Appraisal Ordered",
        "stages": ["PROCESSING", "SUBMITTED"],
        "template": (
            "Update on {borrower_name}'s loan #{loan_number}: the appraisal has been ordered. "
            "We'll keep you posted on the results."
        ),
        "priority": "normal",
    },
    "clear_to_close": {
        "label": "Clear to Close",
        "stages": ["CTC", "CLEAR_TO_CLOSE"],
        "template": (
            "Exciting news! {borrower_name}'s loan #{loan_number} is Clear to Close. "
            "We're on track for the closing date. Let's coordinate final details."
        ),
        "priority": "high",
    },
    "closed": {
        "label": "Closed / Funded",
        "stages": ["FUNDED"],
        "template": (
            "Congratulations! {borrower_name}'s loan #{loan_number} has funded. "
            "Thank you for the partnership — looking forward to the next one!"
        ),
        "priority": "high",
    },
}

# SLA: notifications should be sent within this many minutes of a stage change
NOTIFICATION_SLA_MINUTES = 15


class ListingPartnerAgent:
    """Sends listing-side partner (realtor) updates on loan milestones.

    Monitors stage transitions, identifies the listing-side partner
    (realtor) on a loan, and dispatches timely co-branded notifications.
    """

    def __init__(self) -> None:
        self.agent_name = "listing_partner"
        self.agent_version = "1.0"

    # ------------------------------------------------------------------
    # Milestone notification
    # ------------------------------------------------------------------

    async def send_milestone_notification(
        self,
        loan_id: int,
        milestone: str,
        db: Session,
    ) -> Dict[str, Any]:
        """Send a milestone notification to the listing-side partner within 15 min.

        Args:
            loan_id: Loan record ID.
            milestone: Key from MILESTONE_DEFINITIONS.
            db: SQLAlchemy session.

        Returns:
            dict with notification status, partner info, and message sent.
        """
        try:
            if milestone not in MILESTONE_DEFINITIONS:
                return {
                    "success": False,
                    "error": f"Unknown milestone '{milestone}'. Valid: {list(MILESTONE_DEFINITIONS.keys())}",
                }

            milestone_def = MILESTONE_DEFINITIONS[milestone]

            # Fetch loan
            loan = db.query(Loan).filter(Loan.id == loan_id).first()
            if not loan:
                return {"success": False, "error": f"Loan {loan_id} not found."}

            # Find partner
            partner_info = await self.get_partner_for_loan(loan_id, db)
            if not partner_info.get("success") or not partner_info.get("partner"):
                logger.warning(
                    "No listing partner found for loan %d — skipping milestone notification",
                    loan_id,
                )
                return {
                    "success": False,
                    "error": "No listing partner associated with this loan.",
                    "loan_id": loan_id,
                    "milestone": milestone,
                }

            partner = partner_info["partner"]

            # Generate message
            message = await self.generate_co_branded_update(
                loan_id=loan_id,
                partner_id=partner["id"],
                milestone=milestone,
                db=db,
            )

            # Create notification for the partner
            notification = Notification(
                organization_id=loan.organization_id,
                title=f"Milestone: {milestone_def['label']}",
                message=message,
                type="partner_milestone",
                created_at=datetime.now(timezone.utc),
            )
            db.add(notification)

            # Log activity on the loan
            activity = Activity(
                organization_id=loan.organization_id,
                type=ActivityType.NOTE,
                content=(
                    f"Partner notification sent — {milestone_def['label']} "
                    f"to {partner.get('name', 'Unknown')} ({partner.get('email', 'N/A')})"
                ),
                loan_id=loan_id,
                created_at=datetime.now(timezone.utc),
            )
            db.add(activity)
            db.commit()

            logger.info(
                "Milestone notification sent: loan=%d, milestone=%s, partner=%s",
                loan_id,
                milestone,
                partner.get("name"),
            )

            return {
                "success": True,
                "loan_id": loan_id,
                "milestone": milestone,
                "partner": partner,
                "message": message,
                "priority": milestone_def["priority"],
                "sent_at": datetime.now(timezone.utc).isoformat(),
            }

        except Exception as e:
            logger.exception(
                "Failed to send milestone notification for loan %d: %s", loan_id, e
            )
            db.rollback()
            return {"success": False, "error": str(e)}

    # ------------------------------------------------------------------
    # Partner lookup
    # ------------------------------------------------------------------

    async def get_partner_for_loan(
        self,
        loan_id: int,
        db: Session,
    ) -> Dict[str, Any]:
        """Find the listing-side partner (realtor) for a loan.

        Checks LoanTeamMember first (role='Realtor'), then falls back
        to the loan's realtor_agent field, then the originating lead's
        referral partner.

        Args:
            loan_id: Loan record ID.
            db: SQLAlchemy session.

        Returns:
            dict with partner info or error.
        """
        try:
            loan = db.query(Loan).filter(Loan.id == loan_id).first()
            if not loan:
                return {"success": False, "error": f"Loan {loan_id} not found."}

            # Strategy 1: LoanTeamMember with realtor role
            team_member = (
                db.query(LoanTeamMember)
                .filter(
                    and_(
                        LoanTeamMember.loan_id == loan_id,
                        LoanTeamMember.role.ilike("%realtor%"),
                    )
                )
                .first()
            )

            if team_member:
                partner_data = {
                    "id": team_member.referral_partner_id or team_member.id,
                    "name": team_member.name,
                    "email": team_member.email,
                    "phone": team_member.phone,
                    "company": team_member.company,
                    "source": "loan_team_member",
                }
                return {"success": True, "partner": partner_data}

            # Strategy 2: Loan.realtor_agent field (free-text name)
            if loan.realtor_agent:
                partner_data = {
                    "id": None,
                    "name": loan.realtor_agent,
                    "email": None,
                    "phone": None,
                    "company": None,
                    "source": "loan_realtor_field",
                }
                return {"success": True, "partner": partner_data}

            # Strategy 3: No partner found
            return {"success": True, "partner": None}

        except Exception as e:
            logger.exception("Failed to find partner for loan %d: %s", loan_id, e)
            return {"success": False, "error": str(e)}

    # ------------------------------------------------------------------
    # Co-branded update generation
    # ------------------------------------------------------------------

    async def generate_co_branded_update(
        self,
        loan_id: int,
        partner_id: Optional[int],
        milestone: str,
        db: Session,
    ) -> str:
        """Generate a co-branded milestone update message.

        Merges loan details with partner branding into the milestone template.

        Args:
            loan_id: Loan record ID.
            partner_id: Partner/team-member ID (may be None).
            milestone: Key from MILESTONE_DEFINITIONS.
            db: SQLAlchemy session.

        Returns:
            Formatted message string.
        """
        try:
            loan = db.query(Loan).filter(Loan.id == loan_id).first()
            if not loan:
                return f"Update for loan {loan_id}: {milestone}"

            milestone_def = MILESTONE_DEFINITIONS.get(milestone)
            if not milestone_def:
                return f"Loan #{loan.loan_number} — milestone update: {milestone}"

            # Fetch LO name for co-branding
            lo_name = loan.loan_officer_name or "Your Loan Officer"
            if not loan.loan_officer_name and loan.loan_officer_id:
                lo = db.query(User).filter(User.id == loan.loan_officer_id).first()
                if lo:
                    lo_name = lo.full_name or lo.email

            # Fetch partner name for co-branding
            partner_name = "Partner"
            if partner_id:
                rp = db.query(ReferralPartner).filter(ReferralPartner.id == partner_id).first()
                if rp:
                    partner_name = rp.name
                else:
                    tm = db.query(LoanTeamMember).filter(LoanTeamMember.id == partner_id).first()
                    if tm:
                        partner_name = tm.name

            # Fill template
            message = milestone_def["template"].format(
                borrower_name=loan.borrower_name or "the borrower",
                loan_number=loan.loan_number or "N/A",
            )

            # Append co-branding footer
            message += f"\n\n— {lo_name} & {partner_name}"

            return message

        except Exception as e:
            logger.exception(
                "Failed to generate co-branded update for loan %d: %s", loan_id, e
            )
            return f"Milestone update for loan {loan_id}: {milestone}"

    # ------------------------------------------------------------------
    # Bulk milestone check (for scheduled runs)
    # ------------------------------------------------------------------

    async def check_pending_milestones(
        self,
        org_id: int,
        db: Session,
    ) -> Dict[str, Any]:
        """Scan active loans for milestone notifications that haven't been sent.

        Intended to be called on a schedule (e.g., every 5 minutes) to
        catch any stage changes and dispatch partner notifications within
        the 15-minute SLA.

        Args:
            org_id: Organization ID.
            db: SQLAlchemy session.

        Returns:
            dict with list of notifications dispatched.
        """
        try:
            dispatched: List[Dict[str, Any]] = []

            for milestone_key, milestone_def in MILESTONE_DEFINITIONS.items():
                target_stages = milestone_def["stages"]

                # Find loans in target stages that may need notification
                loans = (
                    db.query(Loan)
                    .filter(
                        and_(
                            Loan.organization_id == org_id,
                            Loan.stage.in_(target_stages),
                            Loan.stage_changed_at.isnot(None),
                        )
                    )
                    .all()
                )

                for loan in loans:
                    # Check if stage changed within the SLA window
                    if not loan.stage_changed_at:
                        continue

                    age_minutes = (
                        datetime.now(timezone.utc) - loan.stage_changed_at.replace(tzinfo=timezone.utc)
                    ).total_seconds() / 60

                    if age_minutes > NOTIFICATION_SLA_MINUTES:
                        continue

                    # Check if we already sent this notification
                    existing = (
                        db.query(Activity)
                        .filter(
                            and_(
                                Activity.loan_id == loan.id,
                                Activity.content.ilike(f"%{milestone_def['label']}%"),
                                Activity.content.ilike("%partner notification%"),
                            )
                        )
                        .first()
                    )

                    if existing:
                        continue

                    result = await self.send_milestone_notification(
                        loan_id=loan.id,
                        milestone=milestone_key,
                        db=db,
                    )

                    if result.get("success"):
                        dispatched.append({
                            "loan_id": loan.id,
                            "milestone": milestone_key,
                            "partner": result.get("partner", {}).get("name"),
                        })

            logger.info(
                "Milestone check complete for org %d: %d notifications dispatched",
                org_id,
                len(dispatched),
            )

            return {
                "success": True,
                "org_id": org_id,
                "dispatched": dispatched,
                "count": len(dispatched),
            }

        except Exception as e:
            logger.exception("Milestone check failed for org %d: %s", org_id, e)
            return {"success": False, "error": str(e)}
