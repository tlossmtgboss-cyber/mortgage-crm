"""
SOC 2 Type II Compliance — Constants & Enums
"""
from enum import Enum


class AuditAction(str, Enum):
    CREATE = "create"
    READ = "read"
    UPDATE = "update"
    DELETE = "delete"
    EXPORT = "export"
    LOGIN = "login"
    LOGOUT = "logout"
    LOGIN_FAILED = "login_failed"
    PASSWORD_CHANGE = "password_change"
    PASSWORD_RESET = "password_reset"
    MFA_ENABLED = "mfa_enabled"
    MFA_DISABLED = "mfa_disabled"
    PERMISSION_CHANGE = "permission_change"
    ACCOUNT_LOCKED = "account_locked"
    ACCOUNT_UNLOCKED = "account_unlocked"
    SESSION_EXPIRED = "session_expired"
    API_KEY_CREATED = "api_key_created"
    API_KEY_REVOKED = "api_key_revoked"
    DATA_EXPORT = "data_export"
    BULK_OPERATION = "bulk_operation"


class SeverityLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class IncidentStatus(str, Enum):
    OPEN = "open"
    INVESTIGATING = "investigating"
    CONTAINED = "contained"
    RESOLVED = "resolved"
    POST_MORTEM = "post_mortem"
    CLOSED = "closed"


class IncidentCategory(str, Enum):
    UNAUTHORIZED_ACCESS = "unauthorized_access"
    DATA_BREACH = "data_breach"
    MALWARE = "malware"
    PHISHING = "phishing"
    INSIDER_THREAT = "insider_threat"
    DENIAL_OF_SERVICE = "denial_of_service"
    DATA_LOSS = "data_loss"
    CONFIGURATION_ERROR = "configuration_error"
    VULNERABILITY_EXPLOIT = "vulnerability_exploit"
    POLICY_VIOLATION = "policy_violation"
    OTHER = "other"


class DataClassification(str, Enum):
    PUBLIC = "public"
    INTERNAL = "internal"
    CONFIDENTIAL = "confidential"
    RESTRICTED = "restricted"  # PII, financial data, SSN, etc.


class ChangeType(str, Enum):
    DEPLOYMENT = "deployment"
    CONFIGURATION = "configuration"
    DATABASE_MIGRATION = "database_migration"
    INFRASTRUCTURE = "infrastructure"
    SECURITY_PATCH = "security_patch"
    FEATURE = "feature"
    BUGFIX = "bugfix"
    ROLLBACK = "rollback"
    ACCESS_CHANGE = "access_change"
    POLICY_UPDATE = "policy_update"


class ChangeStatus(str, Enum):
    REQUESTED = "requested"
    APPROVED = "approved"
    REJECTED = "rejected"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    ROLLED_BACK = "rolled_back"


class ComplianceCheckStatus(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    WARNING = "warning"
    SKIPPED = "skipped"
    ERROR = "error"


class AgreementType(str, Enum):
    BAA = "baa"          # Business Associate Agreement (HIPAA)
    DPA = "dpa"          # Data Processing Agreement (GDPR/CCPA)
    BAA_AND_DPA = "baa_and_dpa"  # Combined BAA + DPA


class AgreementStatus(str, Enum):
    PENDING = "pending"          # Sent, awaiting signature
    SIGNED = "signed"            # Fully executed
    EXPIRED = "expired"          # Past expiry date
    NOT_REQUIRED = "not_required"  # Vendor does not process protected data
    UNDER_REVIEW = "under_review"  # Being reviewed/negotiated


class RetentionPolicy(str, Enum):
    AUDIT_LOGS = "audit_logs"          # 2 years minimum for SOC 2
    ACCESS_LOGS = "access_logs"        # 2 years
    INCIDENT_RECORDS = "incident_records"  # 3 years
    CHANGE_RECORDS = "change_records"  # 2 years
    PII_DATA = "pii_data"             # Per privacy policy / regulation
    LOAN_DATA = "loan_data"           # Per TRID/RESPA — typically 3-5 years
    FINANCIAL_RECORDS = "financial_records"  # 7 years


# Default retention periods in days
RETENTION_PERIODS = {
    RetentionPolicy.AUDIT_LOGS: 730,        # 2 years
    RetentionPolicy.ACCESS_LOGS: 730,        # 2 years
    RetentionPolicy.INCIDENT_RECORDS: 1095,  # 3 years
    RetentionPolicy.CHANGE_RECORDS: 730,     # 2 years
    RetentionPolicy.PII_DATA: 1095,          # 3 years (configurable)
    RetentionPolicy.LOAN_DATA: 1825,         # 5 years
    RetentionPolicy.FINANCIAL_RECORDS: 2555,  # 7 years
}

# Fields classified as PII for the mortgage domain
PII_FIELDS = {
    "ssn", "social_security_number", "tax_id", "ein",
    "bank_account", "bank_account_number", "routing_number",
    "credit_card", "credit_card_number",
    "date_of_birth", "dob",
    "income", "annual_income", "monthly_income",
    "credit_score",
    "drivers_license", "passport_number",
    "phone", "phone_number", "mobile",
    "email", "email_address",
    "home_address", "mailing_address",
    "employer_name", "employer_address",
}

# HTTP methods considered as write operations
WRITE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}

# Paths excluded from audit logging (health checks, static assets)
AUDIT_EXCLUDE_PATHS = {
    "/health",
    "/healthz",
    "/ready",
    "/metrics",
    "/favicon.ico",
    "/docs",
    "/openapi.json",
    "/redoc",
}
