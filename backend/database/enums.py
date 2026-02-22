"""
Database Enums

Centralized enum definitions for the Mortgage CRM database models.
Extracted from main.py as part of the architecture decomposition.

Usage:
    from database.enums import LeadStage, LoanStage, DocumentType

    # Use in models
    stage = Column(Enum(LeadStage), default=LeadStage.NEW)

    # Use in code
    if lead.stage == LeadStage.PRE_APPROVED:
        process_preapproval(lead)
"""

import enum


# ============================================================================
# LEAD & LOAN PIPELINE ENUMS
# ============================================================================

class LeadStage(str, enum.Enum):
    """Lead pipeline stages following PRD lifecycle"""
    NEW = "New"
    ATTEMPTED_CONTACT = "Attempted Contact"
    PROSPECT = "Prospect"
    APPLICATION = "Application"
    APPLICATION_STARTED = "APPLICATION_STARTED"  # Legacy value - maps to Application stage
    DOCUMENT_FULFILLMENT = "Document Fulfillment"  # Application submitted, collecting docs
    PRE_QUALIFIED = "Pre-Qualified"
    PRE_APPROVED = "Pre-Approved"
    UNDER_CONTRACT = "Under Contract"  # PRD: Executing a purchase
    LONG_TERM_NURTURE = "Long-Term Nurture"  # PRD: Not ready to transact
    CLOSED = "Closed"  # PRD: Loan funded (lead converted)
    AMR = "AMR"  # PRD: Annual Mortgage Review cycle
    REFERRAL_SOURCE = "Referral Source"  # PRD: Circle of Cash Flow
    WITHDRAWN = "Withdrawn"
    DOES_NOT_QUALIFY = "Does Not Qualify"
    CREDIT_REPAIR = "Credit Repair"
    DISCLOSED = "Disclosed"  # Lead converted to Active Loan
    FUNDED = "Funded"  # Loan funded - lead moves to MUM/Portfolio


class LoanStage(str, enum.Enum):
    """Loan processing pipeline stages"""
    APPLICATION = "APPLICATION"
    DISCLOSED = "DISCLOSED"
    PROCESSING = "PROCESSING"
    SUBMITTED = "SUBMITTED"
    UNDERWRITING = "UNDERWRITING"
    UW_RECEIVED = "UW_RECEIVED"
    CONDITIONAL_APPROVAL = "CONDITIONAL_APPROVAL"
    APPROVED = "APPROVED"
    SUSPENDED = "SUSPENDED"
    CTC = "CTC"
    CLEAR_TO_CLOSE = "CLEAR_TO_CLOSE"
    CLOSING = "CLOSING"
    DOCS = "DOCS"
    DOCS_OUT = "DOCS_OUT"
    FUNDED = "FUNDED"
    CANCELLED = "CANCELLED"
    DENIED = "DENIED"
    DEAD = "DEAD"
    NURTURE = "NURTURE"
    WITHDRAWN = "WITHDRAWN"
    DOES_NOT_QUALIFY = "DOES_NOT_QUALIFY"


# ============================================================================
# RATE LOCK INTELLIGENCE ENUMS (PRD Section 4.2)
# ============================================================================

class RateLockStatus(str, enum.Enum):
    """Rate lock status for borrowers - PRD Section 4.2"""
    NOT_ELIGIBLE = "Not Eligible"  # No property/loan structure yet
    ELIGIBLE_NO_LOCK = "Eligible - No Lock"  # Can lock but hasn't
    LOCKED = "Locked"  # Rate is locked
    FLOAT_MONITORING = "Float Monitoring"  # Actively floating, monitoring market
    LOCK_EXPIRING = "Lock Expiring"  # Lock expires within threshold
    LOCK_EXTENDED = "Lock Extended"  # Lock was extended
    LOCK_EXPIRED = "Lock Expired"  # Lock expired without closing


class RateLockRecommendation(str, enum.Enum):
    """AI recommendation for rate lock action - PRD Section 4.2"""
    LOCK_NOW = "Lock Now"  # Strong recommendation to lock
    FLOAT_AND_MONITOR = "Float and Monitor"  # Continue floating
    EXTEND_LOCK = "Extend Lock"  # Lock expiring, extend recommended
    RELOCK = "Relock"  # Lock expired or conditions changed
    EXPLORE_FLOAT_DOWN = "Explore Float-Down"  # Market improved, check float-down


class BuyingTimelineCategory(str, enum.Enum):
    """Buying timeline categories for touch frequency - PRD Section Power Play 2"""
    PLATINUM = "Platinum"  # Purchase < 3 months -> touch every 7 days
    GOLD = "Gold"  # Purchase 4-6 months -> every 14 days
    SILVER = "Silver"  # Purchase 7-9 months -> every 21 days
    GREEN = "Green"  # Purchase 10+ months -> monthly


class BorrowerRiskProfile(str, enum.Enum):
    """Borrower risk tolerance for rate lock decisions - PRD Section 4.1"""
    SAFETY_FIRST = "Safety First"  # Prefers certainty, lock early
    BALANCED = "Balanced"  # Willing to float short-term for savings
    AGGRESSIVE = "Aggressive"  # Will float longer for best rate


# ============================================================================
# TASK & ACTIVITY ENUMS
# ============================================================================

class TaskType(str, enum.Enum):
    """Task status/type categories"""
    HUMAN_NEEDED = "Human Needed"
    AWAITING_REVIEW = "Awaiting Review"
    IN_PROGRESS = "In Progress"
    COMPLETED = "Completed"


class ActivityType(str, enum.Enum):
    """Activity/touchpoint types"""
    EMAIL = "Email"
    CALL = "Call"
    MEETING = "Meeting"
    NOTE = "Note"
    SMS = "SMS"
    DOCUMENT = "Document"


# ============================================================================
# DOCUMENT & EMAIL INTAKE ENUMS
# ============================================================================

class EmailIntakeMatchStatus(str, enum.Enum):
    """Status of email-to-borrower matching"""
    MATCHED = "matched"  # Single clear match to borrower/loan
    MULTIPLE = "multiple"  # Multiple possible matches - needs selection
    UNMATCHED = "unmatched"  # No match found - needs manual assignment


class AttachmentClassificationStatus(str, enum.Enum):
    """Classification status for email attachments"""
    PENDING = "pending"  # Awaiting classification
    CLASSIFIED = "classified"  # Classified and attached to borrower
    DISCARDED = "discarded"  # Marked as irrelevant/junk


class DocumentType(str, enum.Enum):
    """Standard document types for mortgage files"""
    # Income Documents
    W2 = "W2"
    PAYSTUB = "Paystub"
    TAX_RETURN_1040 = "Tax Return (1040)"
    TAX_RETURN_1099 = "1099"
    PROFIT_LOSS = "Profit & Loss Statement"
    EMPLOYMENT_VERIFICATION = "Employment Verification"
    # Asset Documents
    BANK_STATEMENT = "Bank Statement"
    RETIREMENT_STATEMENT = "Retirement Account Statement"
    INVESTMENT_STATEMENT = "Investment Statement"
    GIFT_LETTER = "Gift Letter"
    # Credit Documents
    CREDIT_REPORT = "Credit Report"
    CREDIT_EXPLANATION = "Credit Explanation Letter"
    # Property Documents
    PURCHASE_CONTRACT = "Purchase Contract"
    ADDENDUM = "Contract Addendum"
    APPRAISAL = "Appraisal"
    TITLE_COMMITMENT = "Title Commitment"
    HOMEOWNERS_INSURANCE = "Homeowners Insurance"
    # Identity Documents
    DRIVERS_LICENSE = "Driver's License"
    PASSPORT = "Passport"
    SSN_CARD = "Social Security Card"
    # Disclosure Documents
    LOAN_ESTIMATE = "Loan Estimate"
    CLOSING_DISCLOSURE = "Closing Disclosure"
    INITIAL_DISCLOSURES = "Initial Disclosures"
    # E-Sign Documents
    E_CONSENT = "E-Consent Agreement"
    CREDIT_AUTHORIZATION = "Credit Authorization"
    FANNIE_MAE_34 = "Fannie Mae 3.4 File"
    APPLICATION_SUMMARY = "Application Summary"
    # Other
    DIVORCE_DECREE = "Divorce Decree"
    BANKRUPTCY_DISCHARGE = "Bankruptcy Discharge"
    MISC = "Miscellaneous"


class DocumentCategory(str, enum.Enum):
    """Document categories for organization"""
    INCOME = "Income"
    ASSETS = "Assets"
    CREDIT = "Credit"
    PROPERTY = "Property"
    IDENTITY = "Identity"
    DISCLOSURES = "Disclosures"
    APPLICATION = "Application"
    MISC = "Miscellaneous"


# ============================================================================
# USER & PERMISSION ENUMS
# ============================================================================

class InviteStatus(str, enum.Enum):
    """Employee invitation status"""
    PENDING = "pending"
    ACCEPTED = "accepted"
    EXPIRED = "expired"
    REVOKED = "revoked"


class PermissionLevel(str, enum.Enum):
    """Permission levels for resource access"""
    NONE = "none"
    VIEW = "view"
    EDIT = "edit"
    FULL = "full"


# ============================================================================
# DIALER / TELEPHONY ENUMS
# ============================================================================

class DialerSessionStatus(str, enum.Enum):
    """Power dialer session status"""
    ACTIVE = "active"
    PAUSED = "paused"
    STOPPED = "stopped"
    COMPLETED = "completed"


class DialerTaskStatus(str, enum.Enum):
    """Dialer task/call queue status"""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    NO_ANSWER = "no_answer"
    FAILED = "failed"
    SKIPPED = "skipped"


class CallOutcome(str, enum.Enum):
    """Call disposition outcomes"""
    INITIATED = "initiated"  # Call just started, outcome TBD
    COMPLETED = "completed"
    NO_ANSWER = "no_answer"
    BUSY = "busy"
    FAILED = "failed"
    SKIPPED = "skipped"


# ============================================================================
# BORROWER APPLICATION ENUMS
# ============================================================================

class SocialProvider(str, enum.Enum):
    """Social login providers for borrowers"""
    GOOGLE = "google"
    FACEBOOK = "facebook"
    LINKEDIN = "linkedin"
    APPLE = "apple"
    EMAIL = "email"


class ApplicationStatus(str, enum.Enum):
    """Status of the borrower application"""
    DRAFT = "draft"  # Started but not submitted
    IN_PROGRESS = "in_progress"  # Actively being worked on
    PENDING_DOCUMENTS = "pending_documents"  # Waiting for document uploads
    PENDING_COBORROWER = "pending_coborrower"  # Waiting for co-borrower to complete
    SUBMITTED = "submitted"  # Fully submitted for review
    UNDER_REVIEW = "under_review"  # Being reviewed by LO
    APPROVED = "approved"  # Application approved
    DENIED = "denied"  # Application denied
    EXPIRED = "expired"  # Token expired before completion


class ApplicationStep(str, enum.Enum):
    """Steps in the borrower application process"""
    PERSONAL_INFO = "personal_info"
    COBORROWER = "coborrower"
    PROPERTY = "property"
    INCOME = "income"
    ASSETS = "assets"
    LIABILITIES = "liabilities"
    DECLARATIONS = "declarations"
    DOCUMENTS = "documents"
    CREDIT_AUTH = "credit_auth"
    REVIEW = "review"


# ============================================================================
# AI / COACHING ENUMS
# ============================================================================

class CoachMode(str, enum.Enum):
    """AI Coach interaction modes"""
    daily_briefing = "daily_briefing"
    pipeline_audit = "pipeline_audit"
    focus_reset = "focus_reset"
    accountability = "accountability"
    tactical_advice = "tactical_advice"
    tough_love = "tough_love"
    teach_process = "teach_process"
    priority_guidance = "priority_guidance"


class BuyerType(str, enum.Enum):
    """Buyer type categories for calculator assignment"""
    FIRST_TIME = "first_time"
    REPEAT = "repeat"
    VACATION = "vacation"
    INVESTMENT = "investment"
    REFINANCE = "refinance"
    CUSTOM = "custom"


# ============================================================================
# EXPORTS
# ============================================================================

__all__ = [
    # Pipeline
    "LeadStage",
    "LoanStage",
    # Rate Lock
    "RateLockStatus",
    "RateLockRecommendation",
    "BuyingTimelineCategory",
    "BorrowerRiskProfile",
    # Tasks & Activities
    "TaskType",
    "ActivityType",
    # Documents
    "EmailIntakeMatchStatus",
    "AttachmentClassificationStatus",
    "DocumentType",
    "DocumentCategory",
    # Permissions
    "InviteStatus",
    "PermissionLevel",
    # Dialer
    "DialerSessionStatus",
    "DialerTaskStatus",
    "CallOutcome",
    # Borrower Application
    "SocialProvider",
    "ApplicationStatus",
    "ApplicationStep",
    # AI
    "CoachMode",
    # Calculator
    "BuyerType",
]
