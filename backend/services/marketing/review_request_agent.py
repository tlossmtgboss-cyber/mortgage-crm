"""
Review Request Agent

Post-close Google/Zillow review request sequences for funded loans.
Implements a 3-touchpoint drip:
    - Day 1: Email with direct review link
    - Day 3: SMS follow-up
    - Day 7: Final email with gentle reminder

Tracks response rates per LO and org for performance reporting.

Usage:
    agent = ReviewRequestAgent()
    result = await agent.initiate_review_sequence(loan_id=42, borrower_id=7, db=session)
"""

import logging
import uuid
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session
from sqlalchemy import func, and_

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Lazy model imports
# ---------------------------------------------------------------------------
_models_loaded = False


def _ensure_models():
    global _models_loaded
    if _models_loaded:
        return
    global Loan, Lead, BorrowerProfile
    try:
        from database.models.lead_loan import Loan, Lead
    except ImportError:
        Loan = None
        Lead = None
    try:
        from database.models.borrower import BorrowerProfile
    except ImportError:
        BorrowerProfile = None
    _models_loaded = True


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# 3-step review request sequence
SEQUENCE_STEPS = [
    {
        "step": 1,
        "channel": "email",
        "delay_days": 1,
        "subject": "How was your experience?",
        "description": "Initial email with direct review links",
    },
    {
        "step": 2,
        "channel": "sms",
        "delay_days": 3,
        "subject": None,
        "description": "SMS follow-up with short link",
    },
    {
        "step": 3,
        "channel": "email",
        "delay_days": 7,
        "subject": "One last thing — your feedback matters",
        "description": "Final email with gentle reminder",
    },
]

# Review platforms
REVIEW_PLATFORMS = {
    "google": {
        "name": "Google Business",
        "url_template": "https://search.google.com/local/writereview?placeid={place_id}",
    },
    "zillow": {
        "name": "Zillow",
        "url_template": "https://www.zillow.com/lender-profile/{lender_id}/#reviews",
    },
}


class ReviewRequestAgent:
    """
    Manages post-close review request sequences. Initiates a 3-touchpoint
    drip when a loan reaches FUNDED status, tracks delivery and response
    rates, and provides org-level analytics.
    """

    def __init__(self):
        # In-memory sequence store; production would persist to DB
        self._sequences: Dict[str, Dict[str, Any]] = {}

    # ======================================================================
    # SEQUENCE INITIATION
    # ======================================================================

    async def initiate_review_sequence(
        self,
        loan_id: int,
        borrower_id: int,
        db: Session,
    ) -> dict:
        """
        Start a 3-step review request sequence for a funded loan.

        Validates that the loan is in FUNDED status and the borrower
        has contact information before creating the sequence.
        """
        _ensure_models()

        # Validate loan status
        loan_info = self._load_funded_loan(loan_id, db)
        if loan_info is None:
            return {
                "error": "Loan not found or not in FUNDED status",
                "loan_id": loan_id,
            }

        # Load borrower contact (email only — BorrowerProfile has NO phone column)
        borrower = self._load_borrower_contact(borrower_id, db)
        if borrower is None:
            # Fall back to lead email if borrower profile is missing
            borrower = self._load_lead_contact(loan_info.get("lead_id"), db)

        if borrower is None or not borrower.get("email"):
            return {
                "error": "No borrower contact information available",
                "loan_id": loan_id,
                "borrower_id": borrower_id,
            }

        # Create sequence record
        sequence_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)

        sequence = {
            "id": sequence_id,
            "loan_id": loan_id,
            "borrower_id": borrower_id,
            "borrower_email": borrower.get("email"),
            "borrower_first_name": borrower.get("first_name", ""),
            "org_id": loan_info.get("organization_id"),
            "lo_user_id": loan_info.get("user_id"),
            "status": "active",
            "current_step": 0,
            "total_steps": len(SEQUENCE_STEPS),
            "steps": [],
            "created_at": now.isoformat(),
            "review_submitted": False,
        }

        # Build step schedule
        for step_def in SEQUENCE_STEPS:
            send_at = now + timedelta(days=step_def["delay_days"])
            sequence["steps"].append({
                "step": step_def["step"],
                "channel": step_def["channel"],
                "send_at": send_at.isoformat(),
                "subject": step_def["subject"],
                "status": "scheduled",
                "sent_at": None,
                "opened": False,
                "clicked": False,
            })

        self._sequences[sequence_id] = sequence

        logger.info(
            "Review sequence %s initiated for loan %s (borrower %s)",
            sequence_id, loan_id, borrower_id,
        )

        return {
            "sequence_id": sequence_id,
            "loan_id": loan_id,
            "borrower_id": borrower_id,
            "status": "active",
            "steps_scheduled": len(SEQUENCE_STEPS),
            "first_send_at": sequence["steps"][0]["send_at"],
        }

    # ======================================================================
    # STEP PROCESSING
    # ======================================================================

    async def process_sequence_step(
        self,
        sequence_id: str,
        step_number: int,
        db: Session,
    ) -> dict:
        """
        Process a specific step in a review request sequence.

        Generates the appropriate content (email or SMS) and marks the
        step as sent. If the borrower has already submitted a review,
        the remaining steps are cancelled.
        """
        sequence = self._sequences.get(sequence_id)
        if sequence is None:
            return {"error": "Sequence not found", "sequence_id": sequence_id}

        if sequence.get("review_submitted"):
            return {
                "sequence_id": sequence_id,
                "step": step_number,
                "status": "cancelled",
                "reason": "Review already submitted",
            }

        # Find the step
        step = None
        for s in sequence.get("steps", []):
            if s["step"] == step_number:
                step = s
                break

        if step is None:
            return {"error": f"Step {step_number} not found in sequence"}

        if step["status"] == "sent":
            return {
                "sequence_id": sequence_id,
                "step": step_number,
                "status": "already_sent",
                "sent_at": step["sent_at"],
            }

        # Generate content based on channel
        now = datetime.now(timezone.utc)
        content = self._generate_step_content(sequence, step)

        # Mark as sent
        step["status"] = "sent"
        step["sent_at"] = now.isoformat()
        sequence["current_step"] = step_number

        logger.info(
            "Processed step %s of sequence %s via %s",
            step_number, sequence_id, step["channel"],
        )

        return {
            "sequence_id": sequence_id,
            "step": step_number,
            "channel": step["channel"],
            "status": "sent",
            "sent_at": now.isoformat(),
            "content": content,
        }

    # ======================================================================
    # ANALYTICS
    # ======================================================================

    async def get_review_stats(self, org_id: int, db: Session) -> dict:
        """
        Aggregate review request statistics for an organization.

        Metrics include:
        - Total sequences initiated
        - Completion rate (all 3 steps sent)
        - Review submission rate
        - Per-step open/click rates
        """
        _ensure_models()

        now = datetime.now(timezone.utc)

        # Filter sequences for this org
        org_sequences = [
            s for s in self._sequences.values()
            if s.get("org_id") == org_id
        ]

        total = len(org_sequences)
        if total == 0:
            # Also check DB for funded loans to estimate pipeline
            eligible = self._count_eligible_loans(org_id, db)
            return {
                "org_id": org_id,
                "total_sequences": 0,
                "eligible_funded_loans": eligible,
                "completion_rate": 0.0,
                "review_submission_rate": 0.0,
                "generated_at": now.isoformat(),
            }

        completed = sum(
            1 for s in org_sequences
            if s.get("current_step", 0) >= len(SEQUENCE_STEPS)
        )
        reviews_submitted = sum(
            1 for s in org_sequences if s.get("review_submitted")
        )

        # Per-step metrics
        step_metrics: List[Dict[str, Any]] = []
        for step_num in range(1, len(SEQUENCE_STEPS) + 1):
            sent = 0
            opened = 0
            clicked = 0
            for s in org_sequences:
                for step in s.get("steps", []):
                    if step["step"] == step_num and step["status"] == "sent":
                        sent += 1
                        if step.get("opened"):
                            opened += 1
                        if step.get("clicked"):
                            clicked += 1
            step_metrics.append({
                "step": step_num,
                "channel": SEQUENCE_STEPS[step_num - 1]["channel"],
                "sent": sent,
                "opened": opened,
                "clicked": clicked,
                "open_rate": round(opened / sent, 3) if sent > 0 else 0.0,
                "click_rate": round(clicked / sent, 3) if sent > 0 else 0.0,
            })

        return {
            "org_id": org_id,
            "total_sequences": total,
            "completed_sequences": completed,
            "reviews_submitted": reviews_submitted,
            "completion_rate": round(completed / total, 3) if total > 0 else 0.0,
            "review_submission_rate": round(reviews_submitted / total, 3) if total > 0 else 0.0,
            "step_metrics": step_metrics,
            "generated_at": now.isoformat(),
        }

    # ======================================================================
    # INTERNAL HELPERS
    # ======================================================================

    def _load_funded_loan(self, loan_id: int, db: Session) -> Optional[dict]:
        """Load a loan and verify it is in FUNDED status."""
        _ensure_models()
        if Loan is None:
            return None
        try:
            loan = db.query(Loan).filter(
                and_(Loan.id == loan_id, Loan.stage == "FUNDED")
            ).first()
            if loan is None:
                return None
            return {
                "id": loan.id,
                "stage": loan.stage,
                "organization_id": getattr(loan, "organization_id", None),
                "user_id": getattr(loan, "user_id", None),
                "lead_id": getattr(loan, "lead_id", None),
            }
        except Exception as e:
            logger.exception("Error loading loan %s: %s", loan_id, e)
            return None

    def _load_borrower_contact(self, borrower_id: int, db: Session) -> Optional[dict]:
        """
        Load borrower contact info. NOTE: BorrowerProfile has NO phone column;
        match on email only.
        """
        _ensure_models()
        if BorrowerProfile is None:
            return None
        try:
            bp = db.query(BorrowerProfile).filter(
                BorrowerProfile.id == borrower_id
            ).first()
            if bp is None:
                return None
            return {
                "id": bp.id,
                "email": bp.email,
                "first_name": getattr(bp, "first_name", ""),
                "last_name": getattr(bp, "last_name", ""),
            }
        except Exception as e:
            logger.exception("Error loading borrower %s: %s", borrower_id, e)
            return None

    def _load_lead_contact(self, lead_id: Optional[int], db: Session) -> Optional[dict]:
        """Fallback: load contact info from the Lead record."""
        _ensure_models()
        if Lead is None or lead_id is None:
            return None
        try:
            lead = db.query(Lead).filter(Lead.id == lead_id).first()
            if lead is None:
                return None
            return {
                "email": getattr(lead, "email", None),
                "first_name": getattr(lead, "first_name", ""),
                "last_name": getattr(lead, "last_name", ""),
            }
        except Exception as e:
            logger.exception("Error loading lead %s: %s", lead_id, e)
            return None

    def _generate_step_content(
        self, sequence: dict, step: dict,
    ) -> Dict[str, Any]:
        """Generate content for a specific sequence step."""
        first_name = sequence.get("borrower_first_name", "")
        greeting = f"Hi {first_name}" if first_name else "Hi there"

        channel = step.get("channel", "email")

        if channel == "email" and step["step"] == 1:
            return {
                "channel": "email",
                "subject": step.get("subject", "How was your experience?"),
                "body_html": (
                    f"<p>{greeting},</p>"
                    f"<p>Congratulations on closing your loan! I truly enjoyed working "
                    f"with you through this process.</p>"
                    f"<p>If you had a positive experience, I'd be grateful if you could "
                    f"take a moment to leave a review. It helps other families find the "
                    f"right mortgage professional.</p>"
                    f"<p><a href='{{{{google_review_url}}}}'>Leave a Google Review</a> | "
                    f"<a href='{{{{zillow_review_url}}}}'>Leave a Zillow Review</a></p>"
                    f"<p>Thank you for your trust,<br/>{{{{lo_name}}}}</p>"
                ),
            }
        elif channel == "sms":
            return {
                "channel": "sms",
                "body": (
                    f"{greeting}, congrats again on closing! If you have a moment, "
                    f"a quick review would mean the world: {{{{review_short_link}}}}"
                ),
            }
        elif channel == "email" and step["step"] == 3:
            return {
                "channel": "email",
                "subject": step.get("subject", "One last thing — your feedback matters"),
                "body_html": (
                    f"<p>{greeting},</p>"
                    f"<p>I hope you're settling into your new home! I wanted to reach "
                    f"out one more time — if you haven't had a chance to share your "
                    f"experience, a brief review would be incredibly helpful.</p>"
                    f"<p><a href='{{{{google_review_url}}}}'>Google</a> | "
                    f"<a href='{{{{zillow_review_url}}}}'>Zillow</a></p>"
                    f"<p>No pressure at all — I appreciate you either way!</p>"
                    f"<p>Warm regards,<br/>{{{{lo_name}}}}</p>"
                ),
            }

        return {"channel": channel, "body": "Review request touchpoint"}

    def _count_eligible_loans(self, org_id: int, db: Session) -> int:
        """Count funded loans in the org that are eligible for review sequences."""
        _ensure_models()
        if Loan is None:
            return 0
        try:
            count = db.query(func.count(Loan.id)).filter(
                and_(
                    Loan.organization_id == org_id,
                    Loan.stage == "FUNDED",
                )
            ).scalar() or 0
            return count
        except Exception as e:
            logger.exception("Error counting eligible loans for org %s: %s", org_id, e)
            return 0
