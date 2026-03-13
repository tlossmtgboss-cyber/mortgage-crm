"""
AUS (Automated Underwriting System) Submission Model

Tracks DU (Desktop Underwriter) and LPA (Loan Product Advisor) submissions
for each loan, including findings, conditions, income variance analysis,
and raw API responses.

Usage:
    from database.models.aus_submission import AUSSubmission

    submission = db.query(AUSSubmission).filter(
        AUSSubmission.loan_id == loan_id,
        AUSSubmission.organization_id == org_id,
    ).order_by(AUSSubmission.submitted_at.desc()).first()
"""

from datetime import datetime, timezone

from sqlalchemy import (
    Column,
    DateTime,
    Index,
    Integer,
    JSON,
    String,
    Text,
)

from db import Base


__all__ = [
    "AUSSubmission",
]


class AUSSubmission(Base):
    """Record of a loan submission to an Automated Underwriting System.

    Each row represents one submission to DU or LPA. A loan may have multiple
    submissions (initial, resubmission after conditions cleared, etc.).

    Fields:
        aus_type: "DU" or "LPA"
        case_id: The case/file ID returned by the AUS
        recommendation: "Approve/Eligible", "Refer", "Caution", "Out of Scope"
        risk_class: Risk classification from the AUS (e.g., "Accept", "Refer with Caution")
        conditions: JSON list of AUS conditions (each with id, category, description, status)
        findings: JSON list of AUS findings (each with id, code, message, severity)
        income_data_submitted: JSON snapshot of income data we sent
        income_data_returned: JSON snapshot of income data the AUS calculated
        income_variance: JSON variance report comparing our income to AUS income
        submission_status: "submitted", "complete", "error"
        raw_response: Full JSON response from the AUS API (for debugging)
    """
    __tablename__ = "aus_submissions"
    __table_args__ = (
        Index("ix_aus_submissions_org_loan", "organization_id", "loan_id"),
        Index("ix_aus_submissions_case_id", "case_id"),
        Index("ix_aus_submissions_aus_type", "aus_type"),
        Index("ix_aus_submissions_status", "submission_status"),
    )

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, nullable=False, index=True)  # ref organizations.id
    loan_id = Column(Integer, nullable=False, index=True)  # ref loans.id

    # AUS identification
    aus_type = Column(String(10), nullable=False)  # "DU" or "LPA"
    case_id = Column(String(50), nullable=True, index=True)  # AUS-assigned case/file ID

    # AUS decision
    recommendation = Column(String(50), nullable=True)  # Approve/Eligible, Refer, Caution, Out of Scope
    risk_class = Column(String(20), nullable=True)  # Accept, Refer with Caution, etc.

    # Structured findings and conditions (JSON arrays)
    conditions = Column(JSON, nullable=True)  # [{condition_id, category, description, status}, ...]
    findings = Column(JSON, nullable=True)  # [{finding_id, code, message, severity}, ...]

    # Income data snapshots for variance analysis
    income_data_submitted = Column(JSON, nullable=True)  # What we sent to the AUS
    income_data_returned = Column(JSON, nullable=True)  # What the AUS calculated
    income_variance = Column(JSON, nullable=True)  # Variance report (nullable — only set after compare)

    # Submission lifecycle
    submission_status = Column(String(20), nullable=False, default="submitted")  # submitted, complete, error
    error_message = Column(Text, nullable=True)  # Error details if submission_status == "error"

    # Timestamps
    submitted_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)

    # Who submitted
    submitted_by_user_id = Column(Integer, nullable=True)  # ref users.id

    # Full API response (for debugging and audit)
    raw_response = Column(JSON, nullable=True)

    # Audit
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    def __repr__(self):
        return (
            f"<AUSSubmission id={self.id} aus_type={self.aus_type} "
            f"case_id={self.case_id!r} recommendation={self.recommendation!r} "
            f"status={self.submission_status}>"
        )
