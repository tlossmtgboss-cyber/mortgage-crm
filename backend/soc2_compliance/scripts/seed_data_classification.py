"""
Seed Data Classification Registry — SOC 2 Trust Criteria C1/P1 Evidence.

Populates the soc2_data_classification table with all PII, financial, and
encrypted columns from the mortgage CRM schema.  Idempotent — uses
INSERT … ON CONFLICT DO UPDATE.

Usage:
    python -m soc2_compliance.scripts.seed_data_classification
"""
import logging
import os

from sqlalchemy import create_engine, text
from sqlalchemy.pool import NullPool

logger = logging.getLogger("soc2.seed_data_classification")

# ---------------------------------------------------------------------------
# Column registry — manually curated from SQLAlchemy model definitions.
# Each entry: (table, column, classification, is_pii, is_financial,
#              is_encrypted, retention_policy, retention_days,
#              regulatory_basis, description)
# ---------------------------------------------------------------------------

_RESTRICTED = "restricted"
_CONFIDENTIAL = "confidential"
_INTERNAL = "internal"

# Retention shortcuts
_GLBA = "GLBA"
_TRID = "TRID"
_CCPA = "CCPA"
_ECOA = "ECOA"

CLASSIFICATIONS = [
    # =====================================================================
    # leads
    # =====================================================================
    # PII
    ("leads", "first_name", _RESTRICTED, True, False, False, "pii_data", 1095, _CCPA, "Borrower first name"),
    ("leads", "last_name", _RESTRICTED, True, False, False, "pii_data", 1095, _CCPA, "Borrower last name"),
    ("leads", "email", _RESTRICTED, True, False, False, "pii_data", 1095, _CCPA, "Borrower email"),
    ("leads", "phone", _RESTRICTED, True, False, False, "pii_data", 1095, _CCPA, "Borrower phone"),
    ("leads", "co_applicant_name", _RESTRICTED, True, False, False, "pii_data", 1095, _CCPA, "Co-applicant name"),
    ("leads", "co_applicant_email", _RESTRICTED, True, False, False, "pii_data", 1095, _CCPA, "Co-applicant email"),
    ("leads", "co_applicant_phone", _RESTRICTED, True, False, False, "pii_data", 1095, _CCPA, "Co-applicant phone"),
    ("leads", "address", _RESTRICTED, True, False, False, "pii_data", 1095, _CCPA, "Borrower/property address"),
    ("leads", "city", _CONFIDENTIAL, True, False, False, "pii_data", 1095, _CCPA, "City"),
    ("leads", "state", _INTERNAL, False, False, False, None, None, None, "State code"),
    ("leads", "zip_code", _CONFIDENTIAL, True, False, False, "pii_data", 1095, _CCPA, "Zip code"),
    ("leads", "property_address", _RESTRICTED, True, False, False, "pii_data", 1095, _CCPA, "Property address"),
    ("leads", "employer_name", _RESTRICTED, True, False, False, "pii_data", 1095, _GLBA, "Employer name"),
    # Financial
    ("leads", "credit_score", _RESTRICTED, True, True, False, "financial_records", 2555, _GLBA, "Credit score"),
    ("leads", "annual_income", _RESTRICTED, True, True, False, "financial_records", 2555, _GLBA, "Annual income"),
    ("leads", "monthly_debts", _RESTRICTED, False, True, False, "financial_records", 2555, _GLBA, "Monthly debts"),
    ("leads", "debt_to_income", _RESTRICTED, False, True, False, "financial_records", 2555, _GLBA, "DTI ratio"),
    ("leads", "preapproval_amount", _RESTRICTED, False, True, False, "loan_data", 1825, _TRID, "Pre-approval amount"),
    ("leads", "loan_amount", _RESTRICTED, False, True, False, "loan_data", 1825, _TRID, "Loan amount"),
    ("leads", "interest_rate", _CONFIDENTIAL, False, True, False, "loan_data", 1825, _TRID, "Interest rate"),
    ("leads", "apr", _CONFIDENTIAL, False, True, False, "loan_data", 1825, _TRID, "APR"),
    ("leads", "points", _CONFIDENTIAL, False, True, False, "loan_data", 1825, _TRID, "Loan points"),
    ("leads", "appraisal_value", _RESTRICTED, False, True, False, "loan_data", 1825, _TRID, "Appraisal value"),
    ("leads", "property_value", _RESTRICTED, False, True, False, "loan_data", 1825, _TRID, "Property value"),
    ("leads", "down_payment", _CONFIDENTIAL, False, True, False, "loan_data", 1825, _TRID, "Down payment"),
    ("leads", "monthly_payment", _CONFIDENTIAL, False, True, False, "loan_data", 1825, _TRID, "Monthly payment"),
    ("leads", "property_tax", _CONFIDENTIAL, False, True, False, "loan_data", 1825, _TRID, "Property tax"),
    ("leads", "hazard_insurance", _CONFIDENTIAL, False, True, False, "loan_data", 1825, None, "Hazard insurance"),
    ("leads", "mortgage_insurance", _CONFIDENTIAL, False, True, False, "loan_data", 1825, None, "Mortgage insurance"),
    ("leads", "hoa_amount", _CONFIDENTIAL, False, True, False, "loan_data", 1825, None, "HOA amount"),
    ("leads", "origination_fee", _CONFIDENTIAL, False, True, False, "loan_data", 1825, _TRID, "Origination fee"),
    ("leads", "ltv", _CONFIDENTIAL, False, True, False, "loan_data", 1825, _TRID, "LTV ratio"),
    ("leads", "cltv", _CONFIDENTIAL, False, True, False, "loan_data", 1825, _TRID, "CLTV ratio"),

    # =====================================================================
    # loans
    # =====================================================================
    # PII
    ("loans", "borrower_name", _RESTRICTED, True, False, False, "pii_data", 1095, _CCPA, "Borrower name"),
    ("loans", "borrower_email", _RESTRICTED, True, False, False, "pii_data", 1095, _CCPA, "Borrower email"),
    ("loans", "borrower_phone", _RESTRICTED, True, False, False, "pii_data", 1095, _CCPA, "Borrower phone"),
    ("loans", "coborrower_name", _RESTRICTED, True, False, False, "pii_data", 1095, _CCPA, "Co-borrower name"),
    ("loans", "co_borrower_email", _RESTRICTED, True, False, False, "pii_data", 1095, _CCPA, "Co-borrower email"),
    ("loans", "property_address", _RESTRICTED, True, False, False, "pii_data", 1095, _CCPA, "Property address"),
    ("loans", "property_city", _CONFIDENTIAL, True, False, False, "pii_data", 1095, _CCPA, "Property city"),
    ("loans", "property_state", _INTERNAL, False, False, False, None, None, None, "Property state"),
    ("loans", "property_zip", _CONFIDENTIAL, True, False, False, "pii_data", 1095, _CCPA, "Property zip"),
    ("loans", "loan_officer_name", _INTERNAL, True, False, False, None, None, None, "LO name"),
    ("loans", "loan_officer_email", _INTERNAL, True, False, False, None, None, None, "LO email"),
    ("loans", "processor", _INTERNAL, True, False, False, None, None, None, "Processor name"),
    ("loans", "processor_email", _INTERNAL, True, False, False, None, None, None, "Processor email"),
    ("loans", "underwriter", _INTERNAL, True, False, False, None, None, None, "Underwriter name"),
    ("loans", "underwriter_email", _INTERNAL, True, False, False, None, None, None, "Underwriter email"),
    ("loans", "realtor_agent", _INTERNAL, True, False, False, None, None, None, "Realtor name"),
    ("loans", "closer", _INTERNAL, True, False, False, None, None, None, "Closer name"),
    ("loans", "closer_email", _INTERNAL, True, False, False, None, None, None, "Closer email"),
    # Financial
    ("loans", "amount", _RESTRICTED, False, True, False, "loan_data", 1825, _TRID, "Loan amount"),
    ("loans", "purchase_price", _RESTRICTED, False, True, False, "loan_data", 1825, _TRID, "Purchase price"),
    ("loans", "down_payment", _CONFIDENTIAL, False, True, False, "loan_data", 1825, _TRID, "Down payment"),
    ("loans", "rate", _CONFIDENTIAL, False, True, False, "loan_data", 1825, _TRID, "Interest rate"),
    ("loans", "appraisal_value", _RESTRICTED, False, True, False, "loan_data", 1825, _TRID, "Appraisal value"),
    ("loans", "monthly_payment", _CONFIDENTIAL, False, True, False, "loan_data", 1825, _TRID, "Monthly payment"),
    ("loans", "property_tax", _CONFIDENTIAL, False, True, False, "loan_data", 1825, _TRID, "Property tax"),
    ("loans", "hazard_insurance", _CONFIDENTIAL, False, True, False, "loan_data", 1825, None, "Hazard insurance"),
    ("loans", "mortgage_insurance", _CONFIDENTIAL, False, True, False, "loan_data", 1825, None, "Mortgage insurance"),
    ("loans", "hoa_amount", _CONFIDENTIAL, False, True, False, "loan_data", 1825, None, "HOA amount"),
    ("loans", "origination_fee", _CONFIDENTIAL, False, True, False, "loan_data", 1825, _TRID, "Origination fee"),
    ("loans", "points", _CONFIDENTIAL, False, True, False, "loan_data", 1825, _TRID, "Loan points"),
    ("loans", "ltv", _CONFIDENTIAL, False, True, False, "loan_data", 1825, _TRID, "LTV ratio"),
    ("loans", "cltv", _CONFIDENTIAL, False, True, False, "loan_data", 1825, _TRID, "CLTV ratio"),
    ("loans", "extension_cost_estimate", _CONFIDENTIAL, False, True, False, "loan_data", 1825, None, "Lock extension cost"),

    # =====================================================================
    # borrower_profiles
    # =====================================================================
    ("borrower_profiles", "email", _RESTRICTED, True, False, False, "pii_data", 1095, _CCPA, "Borrower email"),
    ("borrower_profiles", "first_name", _RESTRICTED, True, False, False, "pii_data", 1095, _CCPA, "Borrower first name"),
    ("borrower_profiles", "last_name", _RESTRICTED, True, False, False, "pii_data", 1095, _CCPA, "Borrower last name"),
    ("borrower_profiles", "consent_ip_address", _CONFIDENTIAL, True, False, False, "pii_data", 1095, _CCPA, "IP address of consent"),

    # =====================================================================
    # borrower_applications
    # =====================================================================
    # PII
    ("borrower_applications", "borrower_first_name", _RESTRICTED, True, False, False, "pii_data", 1095, _CCPA, "Applicant first name"),
    ("borrower_applications", "borrower_last_name", _RESTRICTED, True, False, False, "pii_data", 1095, _CCPA, "Applicant last name"),
    ("borrower_applications", "borrower_email", _RESTRICTED, True, False, False, "pii_data", 1095, _CCPA, "Applicant email"),
    ("borrower_applications", "borrower_phone", _RESTRICTED, True, False, False, "pii_data", 1095, _CCPA, "Applicant phone"),
    ("borrower_applications", "coborrower_email", _RESTRICTED, True, False, False, "pii_data", 1095, _CCPA, "Co-applicant email"),
    ("borrower_applications", "credit_auth_ssn_last4", _RESTRICTED, True, False, False, "pii_data", 1095, _GLBA, "SSN last 4 digits"),
    ("borrower_applications", "credit_auth_ip_address", _CONFIDENTIAL, True, False, False, "pii_data", 1095, None, "Credit auth IP address"),
    # Encrypted SSN
    ("borrower_applications", "ssn_encrypted", _RESTRICTED, True, True, True, "pii_data", 1095, _GLBA, "Full SSN (Fernet encrypted)"),
    ("borrower_applications", "co_ssn_encrypted", _RESTRICTED, True, True, True, "pii_data", 1095, _GLBA, "Co-applicant SSN (Fernet encrypted)"),
    # ECOA / HMDA demographic fields
    ("borrower_applications", "applicant_ethnicity", _RESTRICTED, True, False, False, "pii_data", 1095, _ECOA, "HMDA ethnicity"),
    ("borrower_applications", "applicant_race", _RESTRICTED, True, False, False, "pii_data", 1095, _ECOA, "HMDA race"),
    ("borrower_applications", "applicant_sex", _RESTRICTED, True, False, False, "pii_data", 1095, _ECOA, "HMDA sex"),
    ("borrower_applications", "applicant_age", _RESTRICTED, True, False, False, "pii_data", 1095, _ECOA, "HMDA age"),
    # Financial
    ("borrower_applications", "prequalification_amount", _RESTRICTED, False, True, False, "loan_data", 1825, _TRID, "Pre-qualification amount"),
    ("borrower_applications", "prequalification_rate", _CONFIDENTIAL, False, True, False, "loan_data", 1825, _TRID, "Pre-qualification rate"),
    ("borrower_applications", "prequalification_monthly_payment", _CONFIDENTIAL, False, True, False, "loan_data", 1825, _TRID, "Pre-qualification payment"),

    # =====================================================================
    # users (internal staff PII)
    # =====================================================================
    ("users", "email", _CONFIDENTIAL, True, False, False, "pii_data", 1095, _CCPA, "Employee email"),
    ("users", "first_name", _CONFIDENTIAL, True, False, False, "pii_data", 1095, _CCPA, "Employee first name"),
    ("users", "last_name", _CONFIDENTIAL, True, False, False, "pii_data", 1095, _CCPA, "Employee last name"),
    ("users", "phone", _CONFIDENTIAL, True, False, False, "pii_data", 1095, _CCPA, "Employee phone"),
    ("users", "nmls_number", _CONFIDENTIAL, True, False, False, "pii_data", 1095, None, "NMLS license number"),
    ("users", "mfa_secret", _RESTRICTED, False, False, True, None, None, None, "TOTP MFA secret (encrypted)"),

    # =====================================================================
    # subscription_plans (business financial)
    # =====================================================================
    ("subscription_plans", "price_monthly", _INTERNAL, False, True, False, "financial_records", 2555, None, "Monthly plan price"),
    ("subscription_plans", "price_yearly", _INTERNAL, False, True, False, "financial_records", 2555, None, "Yearly plan price"),
]


def seed_data_classification(engine=None):
    """
    Populate soc2_data_classification with all known sensitive columns.
    Uses INSERT … ON CONFLICT (table_name, column_name) DO UPDATE for idempotency.
    Returns count of rows upserted.
    """
    if engine is None:
        db_url = os.getenv("DATABASE_URL", "postgresql://localhost:5432/perennia")
        if db_url.startswith("postgres://"):
            db_url = db_url.replace("postgres://", "postgresql://", 1)
        engine = create_engine(db_url, poolclass=NullPool)

    upsert_sql = text("""
        INSERT INTO soc2_data_classification (
            table_name, column_name, classification,
            is_pii, is_financial, is_encrypted,
            access_restricted, authorized_roles,
            retention_policy, retention_days,
            regulatory_basis, description
        ) VALUES (
            :table_name, :column_name, :classification,
            :is_pii, :is_financial, :is_encrypted,
            :access_restricted, :authorized_roles,
            :retention_policy, :retention_days,
            :regulatory_basis, :description
        )
        ON CONFLICT (table_name, column_name) DO UPDATE SET
            classification = EXCLUDED.classification,
            is_pii = EXCLUDED.is_pii,
            is_financial = EXCLUDED.is_financial,
            is_encrypted = EXCLUDED.is_encrypted,
            access_restricted = EXCLUDED.access_restricted,
            retention_policy = EXCLUDED.retention_policy,
            retention_days = EXCLUDED.retention_days,
            regulatory_basis = EXCLUDED.regulatory_basis,
            description = EXCLUDED.description,
            updated_at = NOW()
    """)

    count = 0
    with engine.connect() as conn:
        # Check table exists first
        exists = conn.execute(text(
            "SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'soc2_data_classification')"
        )).fetchone()[0]

        if not exists:
            logger.error("soc2_data_classification table does not exist. Run deploy_soc2_tables first.")
            return 0

        for row in CLASSIFICATIONS:
            (table_name, column_name, classification,
             is_pii, is_financial, is_encrypted,
             retention_policy, retention_days,
             regulatory_basis, description) = row

            # Determine access-restricted flag and authorized roles
            access_restricted = classification in (_RESTRICTED, _CONFIDENTIAL)
            if classification == _RESTRICTED:
                authorized_roles = ["admin", "site_admin", "compliance_officer"]
            elif classification == _CONFIDENTIAL:
                authorized_roles = ["admin", "site_admin", "compliance_officer", "loan_officer"]
            else:
                authorized_roles = None

            conn.execute(upsert_sql, {
                "table_name": table_name,
                "column_name": column_name,
                "classification": classification,
                "is_pii": is_pii,
                "is_financial": is_financial,
                "is_encrypted": is_encrypted,
                "access_restricted": access_restricted,
                "authorized_roles": authorized_roles,
                "retention_policy": retention_policy,
                "retention_days": retention_days,
                "regulatory_basis": regulatory_basis,
                "description": description,
            })
            count += 1

        conn.commit()

    logger.info(f"Seeded {count} data classification entries")
    return count


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    count = seed_data_classification()
    print(f"Seeded {count} data classification entries across {len(set(r[0] for r in CLASSIFICATIONS))} tables")

    # Print summary
    pii_count = sum(1 for r in CLASSIFICATIONS if r[3])
    financial_count = sum(1 for r in CLASSIFICATIONS if r[4])
    encrypted_count = sum(1 for r in CLASSIFICATIONS if r[5])
    print(f"  PII columns: {pii_count}")
    print(f"  Financial columns: {financial_count}")
    print(f"  Encrypted columns: {encrypted_count}")
