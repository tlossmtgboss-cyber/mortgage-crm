"""
Salesforce Sync Service
Handles synchronization of data from Salesforce to the CRM
"""
import os
import re
import logging
import hashlib
import hmac
from datetime import datetime
from typing import Dict, Any, Optional, List, Tuple
from dataclasses import dataclass, field
from enum import Enum

from sqlalchemy import text
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from requests.exceptions import RequestException

logger = logging.getLogger(__name__)

# =============================================================================
# API VERSION: Use consistent version across all Salesforce API calls
# =============================================================================
try:
    from integrations.salesforce_service import SALESFORCE_API_VERSION
except ImportError:
    SALESFORCE_API_VERSION = "v58.0"  # Fallback to stable version


# =============================================================================
# SECURITY: Salesforce ID Validation
# =============================================================================

# Salesforce IDs are either 15 or 18 characters, alphanumeric only
SALESFORCE_ID_PATTERN = re.compile(r'^[a-zA-Z0-9]{15}(?:[a-zA-Z0-9]{3})?$')


def validate_salesforce_id(salesforce_id: str) -> str:
    """
    Validate and sanitize a Salesforce ID to prevent SOQL injection.

    Salesforce IDs are always 15 or 18 characters, alphanumeric only.

    Args:
        salesforce_id: The ID to validate

    Returns:
        The validated ID (unchanged if valid)

    Raises:
        ValueError: If the ID format is invalid
    """
    if not salesforce_id:
        raise ValueError("Salesforce ID cannot be empty")

    # Strip whitespace
    clean_id = salesforce_id.strip()

    # Validate format
    if not SALESFORCE_ID_PATTERN.match(clean_id):
        raise ValueError(
            f"Invalid Salesforce ID format: '{salesforce_id[:20]}...' - "
            "must be 15 or 18 alphanumeric characters"
        )

    return clean_id


def validate_salesforce_object_name(object_name: str) -> str:
    """
    Validate Salesforce object name to prevent SOQL injection.

    Object names contain only alphanumeric, underscores, and must end with __c for custom.

    Args:
        object_name: The object name to validate

    Returns:
        The validated object name

    Raises:
        ValueError: If the object name format is invalid
    """
    if not object_name:
        raise ValueError("Salesforce object name cannot be empty")

    # Object names: alphanumeric and underscores only
    if not re.match(r'^[a-zA-Z][a-zA-Z0-9_]*$', object_name):
        raise ValueError(f"Invalid Salesforce object name: '{object_name}'")

    return object_name

# Import SLA trigger service (lazy loaded to avoid circular imports)
_sla_trigger_service = None

def get_sla_trigger_service(db: Session):
    """Get SLA trigger service instance."""
    global _sla_trigger_service
    try:
        from services.salesforce_sla_trigger_service import SalesforceSLATriggerService
        return SalesforceSLATriggerService(db)
    except ImportError:
        logger.warning("SLA trigger service not available")
        return None


class SyncStatus(str, Enum):
    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED = "failed"
    SKIPPED = "skipped"


class SyncDirection(str, Enum):
    INBOUND = "inbound"  # Salesforce -> CRM
    OUTBOUND = "outbound"  # CRM -> Salesforce


@dataclass
class SyncResult:
    """Result of a sync operation."""
    status: SyncStatus
    records_processed: int = 0
    records_created: int = 0
    records_updated: int = 0
    records_failed: int = 0
    errors: List[str] = field(default_factory=list)
    created_loan_ids: List[int] = field(default_factory=list)
    updated_loan_ids: List[int] = field(default_factory=list)


# Default field mappings for MtgPlanner_CRM__Transaction_Property__c
# Format: salesforce_field -> (crm_field, transform_type)
DEFAULT_FIELD_MAPPING = {
    # Core identifiers
    "Id": ("salesforce_id", None),
    "Name": ("loan_number", None),

    # Loan details
    "MtgPlanner_CRM__Loan_Amount__c": ("amount", "decimal"),
    "MtgPlanner_CRM__Loan_Type__c": ("loan_type", None),
    "MtgPlanner_CRM__Loan_Program__c": ("program", None),
    "MtgPlanner_CRM__Interest_Rate__c": ("interest_rate", "decimal"),
    "MtgPlanner_CRM__Lender__c": ("lender", None),

    # Property info
    "MtgPlanner_CRM__Property_Address__c": ("property_address", None),
    "MtgPlanner_CRM__Property_City__c": ("property_city", None),
    "MtgPlanner_CRM__Property_State__c": ("property_state", None),
    "MtgPlanner_CRM__Property_Zip__c": ("property_zip", None),
    "MtgPlanner_CRM__Purchase_Price__c": ("purchase_price", "decimal"),
    "MtgPlanner_CRM__Down_Payment__c": ("down_payment", "decimal"),

    # Borrower info
    "MtgPlanner_CRM__Borrower_Name__c": ("borrower_name", None),
    "MtgPlanner_CRM__Borrower_First_Name__c": ("borrower_first_name", None),
    "MtgPlanner_CRM__Borrower_Last_Name__c": ("borrower_last_name", None),
    "MtgPlanner_CRM__Borrower_Email__c": ("borrower_email", None),
    "MtgPlanner_CRM__Borrower_Phone__c": ("borrower_phone", None),

    # Co-borrower
    "MtgPlanner_CRM__CoBorrower_Name__c": ("coborrower_name", None),
    "MtgPlanner_CRM__CoBorrower_Email__c": ("co_borrower_email", None),

    # Status and dates
    "MtgPlanner_CRM__Status__c": ("stage", "stage_mapping"),
    "MtgPlanner_CRM__Stage__c": ("stage", "stage_mapping"),

    # ============================================================
    # JUNGO CUSTOM BYTE MAPPINGS - All 33 Date Fields
    # ============================================================

    # Lead & Application Phase
    "MtgPlanner_CRM__Prospect_Date__c": ("prospect_date", "date"),
    "MtgPlanner_CRM__Application_Date__c": ("application_date", "date"),
    "MtgPlanner_CRM__LE_Pending_Date__c": ("le_pending_date", "date"),
    "MtgPlanner_CRM__Credit_Only_Date__c": ("credit_only_date", "date"),
    "MtgPlanner_CRM__File_Received_Date__c": ("file_received_date", "date"),
    "MtgPlanner_CRM__Loan_Pre_Approval_Date__c": ("preapproval_date", "date"),

    # Lock Phase
    "MtgPlanner_CRM__Lock_Date__c": ("lock_date", "date"),
    "MtgPlanner_CRM__Lock_Expiration__c": ("lock_expiration_date", "date"),

    # Processing & Underwriting Phase
    "MtgPlanner_CRM__UW_Received_Date__c": ("uw_received_date", "date"),
    "MtgPlanner_CRM__Conditions_For_Review_Date__c": ("conditions_for_review_date", "date"),
    "MtgPlanner_CRM__Suspended_Date__c": ("suspended_date", "date"),
    "MtgPlanner_CRM__Loan_Approved_Date__c": ("loan_approved_date", "date"),
    "MtgPlanner_CRM__Approved_Not_Accepted_Date__c": ("approved_not_accepted_date", "date"),
    "MtgPlanner_CRM__Approval_Expires_Date__c": ("approval_expires_date", "date"),

    # Appraisal Phase
    "MtgPlanner_CRM__Appraisal_Ordered_Date__c": ("appraisal_ordered_date", "date"),
    "MtgPlanner_CRM__Appraisal_Scheduled_Date__c": ("appraisal_scheduled_date", "date"),
    "MtgPlanner_CRM__Appraisal_Completed_Date__c": ("appraisal_completed_date", "date"),
    "MtgPlanner_CRM__Appraisal_Received_Date__c": ("appraisal_received_date", "date"),
    "MtgPlanner_CRM__Appraisal_Docs_Expire_Date__c": ("appraisal_docs_expire_date", "date"),

    # Title & Insurance Phase
    "MtgPlanner_CRM__Title_Ordered_Date__c": ("title_ordered_date", "date"),
    "MtgPlanner_CRM__Title_Received_Date__c": ("title_received_date", "date"),
    "MtgPlanner_CRM__Insurance_Ordered_Date__c": ("insurance_ordered_date", "date"),
    "MtgPlanner_CRM__Insurance_Received_Date__c": ("insurance_received_date", "date"),

    # Closing Disclosure Phase
    "MtgPlanner_CRM__CD_Requested_Date__c": ("cd_requested_date", "date"),
    "MtgPlanner_CRM__CD_Sent_To_Borrower_Date__c": ("cd_sent_to_borrower_date", "date"),
    "MtgPlanner_CRM__CD_Acknowledged_Date__c": ("cd_acknowledged_date", "date"),

    # Clear to Close & Docs Phase
    "MtgPlanner_CRM__Clear_To_Close_Date__c": ("clear_to_close_date", "date"),
    "MtgPlanner_CRM__Docs_Ordered_Date__c": ("docs_ordered_date", "date"),
    "MtgPlanner_CRM__Docs_Out_Date__c": ("docs_out_date", "date"),
    "MtgPlanner_CRM__Credit_Docs_Expire_Date__c": ("credit_docs_expire_date", "date"),

    # Funding Phase
    "MtgPlanner_CRM__Scheduled_Closing_Date__c": ("scheduled_closing_date", "date"),
    "MtgPlanner_CRM__Scheduled_Funding_Date__c": ("scheduled_funding_date", "date"),
    "MtgPlanner_CRM__Funds_Ordered_Date__c": ("funds_ordered_date", "date"),
    "MtgPlanner_CRM__Funds_Sent_Date__c": ("funds_sent_date", "date"),
    "MtgPlanner_CRM__Funded_Date__c": ("funded_date", "date"),
    "MtgPlanner_CRM__Closing_Date__c": ("closing_date", "date"),
    "MtgPlanner_CRM__First_Payment_Date__c": ("first_payment_date", "date"),

    # Post-Closing
    "MtgPlanner_CRM__Investor_Purchased_Date__c": ("investor_purchased_date", "date"),

    # Status Changes
    "MtgPlanner_CRM__Withdrawn_Date__c": ("withdrawn_date", "date"),
    "MtgPlanner_CRM__Contract_Date__c": ("contract_received_date", "date"),

    # ============================================================
    # PROPERTY DETAILS
    # ============================================================
    "MtgPlanner_CRM__Property_Type__c": ("property_type", None),
    "MtgPlanner_CRM__Occupancy_Type__c": ("occupancy_type", None),
    "MtgPlanner_CRM__Property_County__c": ("property_county", None),
    "MtgPlanner_CRM__Property_Ownership_Type__c": ("property_ownership_type", None),
    "MtgPlanner_CRM__Property_Units__c": ("property_units", "integer"),
    "MtgPlanner_CRM__Appraised_Value__c": ("appraisal_value", "decimal"),

    # ============================================================
    # 1ST LOAN DETAILS
    # ============================================================
    "MtgPlanner_CRM__Rate_Type_1st_TD__c": ("rate_type", None),
    "MtgPlanner_CRM__Note_Rate__c": ("interest_rate", "decimal"),
    "MtgPlanner_CRM__Property_Tax_1st_TD__c": ("property_tax", "decimal"),
    "MtgPlanner_CRM__Est_Prepaid_Int_1st_TD__c": ("estimated_prepaid_interest", "decimal"),
    "MtgPlanner_CRM__Hazard_Ins_1st_TD__c": ("hazard_insurance", "decimal"),
    "MtgPlanner_CRM__Origination_1st_TD__c": ("origination_fee", "decimal"),
    "MtgPlanner_CRM__Mortgage_Ins_1st_TD__c": ("mortgage_insurance", "decimal"),
    "MtgPlanner_CRM__HOA_1st_TD__c": ("hoa_amount", "decimal"),
    "MtgPlanner_CRM__Points_1st_TD__c": ("points", "decimal"),
    "MtgPlanner_CRM__Index_1st_TD__c": ("index_rate", "decimal"),
    "MtgPlanner_CRM__Margin_1st_TD__c": ("margin", "decimal"),
    "MtgPlanner_CRM__Monthly_Payment_1st_TD__c": ("monthly_payment", "decimal"),
    "MtgPlanner_CRM__Loan_Date_1st_TD__c": ("loan_date", "date"),
    "MtgPlanner_CRM__AUS_DU_Run_Date_1st_TD__c": ("aus_du_run_date", "date"),
    "MtgPlanner_CRM__Lender_State_Elig_1st_TD__c": ("lender_state_eligibility", None),

    # ============================================================
    # LTV / CLTV
    # ============================================================
    "MtgPlanner_CRM__LTV__c": ("ltv", "decimal"),
    "MtgPlanner_CRM__CLTV__c": ("cltv", "decimal"),

    # ============================================================
    # LOAN PURPOSE & ADDITIONAL INFO
    # ============================================================
    "MtgPlanner_CRM__Loan_Purpose__c": ("loan_purpose", None),
    "MtgPlanner_CRM__File_State__c": ("file_state", None),
    "MtgPlanner_CRM__Account__c": ("borrower_account", None),

    # ============================================================
    # 2ND LOAN DETAILS
    # ============================================================
    "MtgPlanner_CRM__Loan_Amount_2nd_TD__c": ("second_loan_amount", "decimal"),
    "MtgPlanner_CRM__Rate_2nd_TD__c": ("second_loan_rate", "decimal"),
    "MtgPlanner_CRM__Monthly_Payment_2nd_TD__c": ("second_loan_payment", "decimal"),

    # ============================================================
    # PRESENT VS PROPOSED
    # ============================================================
    "MtgPlanner_CRM__Present_Total_Expenses__c": ("present_housing_expense", "decimal"),
    "MtgPlanner_CRM__Proposed_Total_Expenses__c": ("proposed_housing_expense", "decimal"),
    "MtgPlanner_CRM__Present_Monthly_Payment__c": ("present_monthly_payment", "decimal"),
    "MtgPlanner_CRM__Proposed_Monthly_Payment_1st_TD__c": ("proposed_monthly_payment", "decimal"),

    # Timestamps
    "CreatedDate": ("created_at", "datetime"),
    "LastModifiedDate": ("updated_at", "datetime"),
}

# =============================================================================
# SECURITY: Allowed loan fields whitelist for dynamic SQL
# Generated from DEFAULT_FIELD_MAPPING to prevent SQL injection via field names
# =============================================================================
ALLOWED_LOAN_FIELDS = frozenset(
    crm_field for crm_field, _ in DEFAULT_FIELD_MAPPING.values()
) | {
    # Additional fields that may be set programmatically
    "organization_id",
    "loan_officer_id",
    "salesforce_id",
    "salesforce_last_synced_at",
    "salesforce_sync_status",
    "salesforce_raw_stage",
    "sla_status",
    "created_at",
    "updated_at",
}


def validate_loan_field_name(field_name: str) -> str:
    """
    Validate a loan field name against the whitelist.

    Args:
        field_name: The field name to validate

    Returns:
        The validated field name

    Raises:
        ValueError: If the field name is not in the whitelist
    """
    if field_name not in ALLOWED_LOAN_FIELDS:
        raise ValueError(f"Invalid loan field name: '{field_name}' - not in allowed fields")
    return field_name


# Stage mapping from Salesforce values to CRM LoanStage enum
# Covers: standard SF stages, mortgage-specific stages, and Encompass milestones
STAGE_MAPPING = {
    # --- Application / Early ---
    "New": "APPLICATION",
    "Application": "APPLICATION",
    "Application Received": "APPLICATION",
    "Started": "APPLICATION",
    "File Started": "APPLICATION",
    "Disclosed": "DISCLOSED",
    "LE Sent": "DISCLOSED",
    # --- Processing ---
    "Submitted": "PROCESSING",
    "Processing": "PROCESSING",
    "Processed": "PROCESSING",
    "In Processing": "PROCESSING",
    "Contract Received": "PROCESSING",
    "Submitted to Processing": "PROCESSING",
    "Loan in Process": "PROCESSING",
    "Document Collection": "PROCESSING",
    "Documents Requested": "PROCESSING",
    "Documents Received": "PROCESSING",
    "Appraisal Ordered": "PROCESSING",
    "Appraisal Received": "PROCESSING",
    "Insurance Ordered": "PROCESSING",
    "Insurance Received": "PROCESSING",
    "Title Ordered": "PROCESSING",
    "Title Received": "PROCESSING",
    # --- Submitted to UW ---
    "Submitted to UW": "SUBMITTED",
    "Submitted to Underwriting": "SUBMITTED",
    # --- Underwriting ---
    "Underwriting": "UNDERWRITING",
    "In Underwriting": "UNDERWRITING",
    "UW Review": "UW_RECEIVED",
    "Underwriting Decision": "UW_RECEIVED",
    "UW Received": "UW_RECEIVED",
    "Received": "UW_RECEIVED",
    # --- Approval ---
    "Conditionally Approved": "CONDITIONAL_APPROVAL",
    "Conditional Approval": "CONDITIONAL_APPROVAL",
    "Cond. Approved": "CONDITIONAL_APPROVAL",
    "Approved with Conditions": "CONDITIONAL_APPROVAL",
    "Conditions Cleared": "APPROVED",
    "Approved": "APPROVED",
    # --- Clear to Close / Closing ---
    "Clear to Close": "CLEAR_TO_CLOSE",
    "CTC": "CLEAR_TO_CLOSE",
    "Closing": "CLOSING",
    "Closing Scheduled": "CLOSING",
    "Closing Date": "CLOSING",
    "Docs Drawing": "DOCS",
    "Doc Preparation": "DOCS",
    "Closing Docs Out": "DOCS_OUT",
    "Docs Out": "DOCS_OUT",
    "Docs Signing": "DOCS_OUT",
    "Docs Signed": "DOCS_OUT",
    # --- Funded ---
    "Funded": "FUNDED",
    "Loan Funded": "FUNDED",
    "Closed": "FUNDED",
    "Closed Won": "FUNDED",
    "Post-Closing": "FUNDED",
    "Purchased": "FUNDED",
    "Completed": "FUNDED",
    "File Complete": "FUNDED",
    # --- Terminal / Special ---
    "Cancelled": "CANCELLED",
    "Withdrawn": "WITHDRAWN",
    "Denied": "DENIED",
    "Rejected": "DENIED",
    "Dead": "DEAD",
    "Inactive": "DEAD",
    "Does Not Qualify": "DOES_NOT_QUALIFY",
    "Suspended": "SUSPENDED",
    "Nurture": "NURTURE",
}

# Reverse stage mapping (CRM stage -> Salesforce status)
REVERSE_STAGE_MAPPING = {
    "APPLICATION": "Application",
    "DISCLOSED": "Disclosed",
    "PROCESSING": "Processing",
    "SUBMITTED": "Submitted",
    "UNDERWRITING": "Underwriting",
    "UW_RECEIVED": "UW Received",
    "CONDITIONAL_APPROVAL": "Conditional Approval",
    "APPROVED": "Approved",
    "CTC": "Clear to Close",
    "CLEAR_TO_CLOSE": "Clear to Close",
    "CLOSING": "Closing Scheduled",
    "DOCS": "Docs Out",
    "DOCS_OUT": "Docs Out",
    "FUNDED": "Funded",
    "CANCELLED": "Cancelled",
    "DENIED": "Denied",
    "DEAD": "Dead",
    "WITHDRAWN": "Withdrawn",
    "DOES_NOT_QUALIFY": "Does Not Qualify",
    "SUSPENDED": "Suspended",
    "NURTURE": "Nurture",
}

# Default outbound field mappings (CRM field -> Salesforce field)
# Only include fields that should be pushed to Salesforce
DEFAULT_OUTBOUND_MAPPING = {
    # Loan details
    "loan_amount": ("MtgPlanner_CRM__Loan_Amount__c", "decimal"),
    "amount": ("MtgPlanner_CRM__Loan_Amount__c", "decimal"),
    "loan_type": ("MtgPlanner_CRM__Loan_Type__c", None),
    "program": ("MtgPlanner_CRM__Loan_Program__c", None),
    "interest_rate": ("MtgPlanner_CRM__Interest_Rate__c", "decimal"),
    "lender": ("MtgPlanner_CRM__Lender__c", None),

    # Property info
    "property_address": ("MtgPlanner_CRM__Property_Address__c", None),
    "property_city": ("MtgPlanner_CRM__Property_City__c", None),
    "property_state": ("MtgPlanner_CRM__Property_State__c", None),
    "property_zip": ("MtgPlanner_CRM__Property_Zip__c", None),
    "purchase_price": ("MtgPlanner_CRM__Purchase_Price__c", "decimal"),
    "down_payment": ("MtgPlanner_CRM__Down_Payment__c", "decimal"),

    # Borrower info
    "borrower_name": ("MtgPlanner_CRM__Borrower_Name__c", None),
    "borrower_first_name": ("MtgPlanner_CRM__Borrower_First_Name__c", None),
    "borrower_last_name": ("MtgPlanner_CRM__Borrower_Last_Name__c", None),
    "borrower_email": ("MtgPlanner_CRM__Borrower_Email__c", None),
    "borrower_phone": ("MtgPlanner_CRM__Borrower_Phone__c", None),

    # Co-borrower
    "coborrower_name": ("MtgPlanner_CRM__CoBorrower_Name__c", None),
    "co_borrower_email": ("MtgPlanner_CRM__CoBorrower_Email__c", None),

    # Status and dates
    "stage": ("MtgPlanner_CRM__Status__c", "reverse_stage_mapping"),
    "status": ("MtgPlanner_CRM__Status__c", "reverse_stage_mapping"),
    "closing_date": ("MtgPlanner_CRM__Closing_Date__c", "date_to_string"),
    "lock_date": ("MtgPlanner_CRM__Lock_Date__c", "date_to_string"),
    "lock_expiration_date": ("MtgPlanner_CRM__Lock_Expiration__c", "date_to_string"),
    "application_date": ("MtgPlanner_CRM__Application_Date__c", "date_to_string"),
}


class SalesforceSyncService:
    """Service for syncing Salesforce data to the CRM."""

    def __init__(self, db: Session, user_id: Optional[int] = None, organization_id: int = 1):
        self.db = db
        self.user_id = user_id
        self.organization_id = organization_id
        self.webhook_secret = os.getenv("SALESFORCE_WEBHOOK_SECRET", "")
        self._field_mappings = None

    def verify_webhook_signature(self, payload: bytes, signature: str) -> bool:
        """Verify HMAC signature from Salesforce webhook."""
        if not self.webhook_secret:
            # SECURITY: Only skip verification in explicit development mode
            environment = os.getenv("ENVIRONMENT", "production").lower()
            if environment in ("development", "dev", "local", "test"):
                logger.warning("SALESFORCE_WEBHOOK_SECRET not set - skipping signature verification (dev mode)")
                return True
            else:
                # In production, reject unverified webhooks
                logger.error("SECURITY: SALESFORCE_WEBHOOK_SECRET not set in production - rejecting webhook")
                return False

        expected_signature = hmac.new(
            self.webhook_secret.encode(),
            payload,
            hashlib.sha256
        ).hexdigest()

        return hmac.compare_digest(signature, expected_signature)

    def get_field_mappings(self) -> Dict[str, Tuple[str, Optional[str]]]:
        """Get field mappings, preferring database config over defaults."""
        if self._field_mappings is not None:
            return self._field_mappings

        # Try to load custom mappings from database
        try:
            result = self.db.execute(text("""
                SELECT salesforce_field, crm_field, transform_type
                FROM salesforce_field_mappings
                WHERE organization_id = :org_id
                  AND salesforce_object = 'MtgPlanner_CRM__Transaction_Property__c'
                  AND is_active = true
            """), {"org_id": self.organization_id})

            custom_mappings = {}
            for row in result.fetchall():
                custom_mappings[row[0]] = (row[1], row[2])

            if custom_mappings:
                self._field_mappings = custom_mappings
                logger.info(f"Loaded {len(custom_mappings)} custom field mappings")
                return self._field_mappings
        except SQLAlchemyError as e:
            logger.warning(f"Database error loading custom field mappings: {e}")
        except (ValueError, TypeError) as e:
            logger.warning(f"Data error in custom field mappings: {e}")

        # Fall back to default mappings
        self._field_mappings = DEFAULT_FIELD_MAPPING
        return self._field_mappings

    def transform_value(self, value: Any, transform_type: Optional[str]) -> Any:
        """Transform a Salesforce value to CRM format."""
        from decimal import Decimal as _Decimal, InvalidOperation

        if value is None:
            return None

        if transform_type is None:
            return value

        if transform_type == "decimal":
            try:
                return float(_Decimal(str(value))) if value else None
            except (ValueError, TypeError, InvalidOperation):
                return None

        if transform_type == "integer":
            try:
                return int(value) if value else None
            except (ValueError, TypeError):
                return None

        if transform_type == "date":
            if isinstance(value, str):
                try:
                    # Handle Salesforce date format (YYYY-MM-DD)
                    return datetime.strptime(value[:10], "%Y-%m-%d").date()
                except ValueError:
                    return None
            return value

        if transform_type == "datetime":
            if isinstance(value, str):
                try:
                    # Handle Salesforce datetime format (ISO 8601)
                    # Remove 'Z' suffix and parse
                    clean_value = value.replace("Z", "+00:00")
                    if "." in clean_value:
                        return datetime.fromisoformat(clean_value.split(".")[0])
                    return datetime.fromisoformat(clean_value[:19])
                except ValueError:
                    return None
            return value

        if transform_type == "stage_mapping":
            # Map Salesforce status to CRM stage (None if unmapped, so reconciliation can flag it)
            mapped = STAGE_MAPPING.get(str(value))
            if mapped is None:
                logger.warning(f"Unmapped Salesforce stage value: '{value}'")
            return mapped

        if transform_type == "boolean":
            if isinstance(value, bool):
                return value
            if isinstance(value, str):
                return value.lower() in ("true", "yes", "1")
            return bool(value)

        return value

    def map_salesforce_to_loan(self, sf_record: Dict[str, Any]) -> Dict[str, Any]:
        """Map a Salesforce record to CRM loan fields."""
        field_mappings = self.get_field_mappings()
        loan_data = {}

        for sf_field, (crm_field, transform_type) in field_mappings.items():
            if sf_field in sf_record:
                value = sf_record[sf_field]
                transformed_value = self.transform_value(value, transform_type)
                if transformed_value is not None:
                    loan_data[crm_field] = transformed_value

        # Capture raw Salesforce stage before any mapping (for reconciliation audit)
        raw_stage = sf_record.get("MtgPlanner_CRM__Status__c") or sf_record.get("MtgPlanner_CRM__Stage__c")
        if raw_stage:
            loan_data["salesforce_raw_stage"] = str(raw_stage)

        # Set sync metadata
        loan_data["salesforce_last_synced_at"] = datetime.utcnow()
        loan_data["salesforce_sync_status"] = "synced"

        # Ensure required fields have defaults
        if "loan_number" not in loan_data and "salesforce_id" in loan_data:
            loan_data["loan_number"] = f"SF-{loan_data['salesforce_id'][-8:]}"

        if "stage" not in loan_data:
            # Don't silently default to APPLICATION — let upsert_loan() decide:
            # For UPDATES: preserve the existing stage (don't overwrite)
            # For CREATES: APPLICATION is a reasonable default
            loan_data["_stage_unmapped"] = True
            logger.warning(
                f"No stage mapped from Salesforce record "
                f"(raw stage: {loan_data.get('salesforce_raw_stage', 'unknown')})"
            )

        return loan_data

    def upsert_loan(self, loan_data: Dict[str, Any]) -> Tuple[Optional[int], str]:
        """
        Create or update a loan based on salesforce_id.

        Returns:
            Tuple of (loan_id, action) where action is 'created', 'updated', or 'error'
        """
        salesforce_id = loan_data.get("salesforce_id")
        if not salesforce_id:
            return None, "error"

        try:
            # Check if loan exists and get current data for comparison
            # Scoped to loan_officer_id for multi-tenant isolation
            if self.user_id:
                existing = self.db.execute(text("""
                    SELECT id, closing_date, lock_date, lock_expiration_date,
                           application_date, contract_received_date, stage, funded_date
                    FROM loans WHERE salesforce_id = :sf_id AND loan_officer_id = :user_id
                """), {"sf_id": salesforce_id, "user_id": self.user_id}).fetchone()
            else:
                existing = self.db.execute(text("""
                    SELECT id, closing_date, lock_date, lock_expiration_date,
                           application_date, contract_received_date, stage, funded_date
                    FROM loans WHERE salesforce_id = :sf_id
                """), {"sf_id": salesforce_id}).fetchone()

            old_data = {}

            # Handle unmapped stage sentinel: for UPDATES, preserve existing stage;
            # for CREATES, default to APPLICATION
            stage_unmapped = loan_data.pop("_stage_unmapped", False)
            if stage_unmapped:
                if existing:
                    # UPDATE: don't overwrite the existing stage with a guess
                    loan_data.pop("stage", None)
                else:
                    # CREATE: APPLICATION is a reasonable default for new records
                    loan_data["stage"] = "APPLICATION"

            if existing:
                # Capture old data for SLA trigger comparison
                old_data = {
                    "closing_date": existing[1],
                    "lock_date": existing[2],
                    "lock_expiration_date": existing[3],
                    "application_date": existing[4],
                    "contract_received_date": existing[5],
                    "stage": existing[6],
                    "funded_date": existing[7],
                }

                # Pre-write stage validation: check transition BEFORE writing
                new_stage = loan_data.get("stage")
                old_stage_value = old_data.get("stage")
                if new_stage and old_stage_value and new_stage != old_stage_value:
                    try:
                        from services.loan_reconciliation_service import LoanReconciliationService
                        pre_recon = LoanReconciliationService(self.db)
                        pre_check = pre_recon.reconcile(existing[0], old_data, loan_data)

                        if pre_check.action.value == 'FLAG_FOR_REVIEW':
                            logger.warning(
                                f"Pre-write validation blocked stage change "
                                f"{old_stage_value} -> {new_stage} on loan {existing[0]}: "
                                f"flagged for review (raw SF stage: {loan_data.get('salesforce_raw_stage')})"
                            )
                            loan_data.pop("stage", None)
                        elif pre_check.is_backward_movement:
                            logger.warning(
                                f"Pre-write validation blocked backward stage move "
                                f"{old_stage_value} -> {new_stage} on loan {existing[0]}"
                            )
                            loan_data.pop("stage", None)
                    except ImportError:
                        pass  # Reconciliation service not available, proceed as-is
                    except Exception as e:
                        logger.warning(f"Pre-write stage validation error for loan {existing[0]}: {e}")

                # Update existing loan
                loan_id = existing[0]
                update_fields = []
                params = {"loan_id": loan_id}

                for field, value in loan_data.items():
                    if field != "salesforce_id":  # Don't update the ID
                        # SECURITY: Validate field name against whitelist to prevent SQL injection
                        try:
                            validate_loan_field_name(field)
                            update_fields.append(f"{field} = :{field}")
                            params[field] = value
                        except ValueError as e:
                            logger.warning(f"Skipping invalid field in loan update: {e}")
                            continue

                if update_fields:
                    self.db.execute(text(f"""
                        UPDATE loans
                        SET {", ".join(update_fields)}, updated_at = CURRENT_TIMESTAMP
                        WHERE id = :loan_id
                    """), params)
                    self.db.commit()

                logger.info(f"Updated loan {loan_id} from Salesforce {salesforce_id}")

                # Trigger SLA workflows based on changed date fields
                self._trigger_sla_workflows(loan_id, old_data, loan_data)

                return loan_id, "updated"
            else:
                # Create new loan
                # SECURITY: Validate all field names against whitelist before INSERT
                validated_data = {}
                for field, value in loan_data.items():
                    try:
                        validate_loan_field_name(field)
                        validated_data[field] = value
                    except ValueError as e:
                        logger.warning(f"Skipping invalid field in loan insert: {e}")
                        continue

                fields = list(validated_data.keys())
                placeholders = [f":{f}" for f in fields]

                # Add organization and owner
                if self.organization_id:
                    fields.append("organization_id")
                    placeholders.append(":organization_id")
                    validated_data["organization_id"] = self.organization_id

                if self.user_id:
                    fields.append("loan_officer_id")
                    placeholders.append(":loan_officer_id")
                    validated_data["loan_officer_id"] = self.user_id

                result = self.db.execute(text(f"""
                    INSERT INTO loans ({", ".join(fields)})
                    VALUES ({", ".join(placeholders)})
                    RETURNING id
                """), validated_data)
                self.db.commit()

                loan_id = result.fetchone()[0]
                logger.info(f"Created loan {loan_id} from Salesforce {salesforce_id}")

                # Trigger SLA workflows for new loans
                self._trigger_sla_workflows(loan_id, {}, loan_data)

                return loan_id, "created"

        except SQLAlchemyError as e:
            logger.error(f"Error upserting loan from Salesforce {salesforce_id}: {e}")
            self.db.rollback()
            return None, "error"

    def _trigger_sla_workflows(
        self,
        loan_id: int,
        old_data: Dict[str, Any],
        new_data: Dict[str, Any]
    ):
        """
        Trigger SLA workflows based on changed date fields from Salesforce sync.

        This is the post-sync hook that connects Salesforce updates to SLA task generation.
        Now also creates tasks in the main tasks table with SLA tracking columns.
        Also tracks date field updates for reconciliation.
        """
        # Track date updates for reconciliation
        try:
            from services.date_reconciliation_service import DateReconciliationService, DateUpdate

            service = DateReconciliationService(self.db, self.user_id or 1)

            # Get loan stage to determine if it's closed
            loan_stage = new_data.get("stage")

            # Track date field changes
            sf_id = new_data.get("salesforce_id", "")
            updates = service.track_date_updates(sf_id, old_data, new_data, loan_id)

            # Process each date update
            for update in updates:
                service.process_date_update(update, loan_id, loan_stage)

        except (ImportError, AttributeError) as e:
            # Service not available - this is expected in some environments
            logger.debug(f"Date reconciliation service not available: {e}")
        except (SQLAlchemyError, ValueError) as e:
            # Database or data errors in date tracking - log but don't fail sync
            logger.warning(f"Date reconciliation error for loan {loan_id}: {type(e).__name__}: {e}")
        except Exception as e:
            # Unexpected error - log with full context but don't fail sync
            logger.warning(f"Unexpected date reconciliation error for loan {loan_id}: {type(e).__name__}: {e}")

        try:
            sla_service = get_sla_trigger_service(self.db)
            if not sla_service:
                return

            result = sla_service.process_sync_result(
                entity_type="loan",
                entity_id=loan_id,
                old_data=old_data,
                new_data=new_data,
                sync_source="salesforce"
            )

            if result.get("workflows_triggered"):
                logger.info(
                    f"Salesforce sync triggered {len(result['workflows_triggered'])} "
                    f"SLA workflows for loan {loan_id}"
                )

            if result.get("errors"):
                for error in result["errors"]:
                    logger.warning(f"SLA trigger warning for loan {loan_id}: {error}")

        except (ImportError, AttributeError) as e:
            # SLA service not available - this is expected in some environments
            logger.debug(f"SLA trigger service not available: {e}")
        except SQLAlchemyError as e:
            # Database error in SLA trigger - log but don't fail sync
            logger.error(f"Database error in SLA workflows for loan {loan_id}: {e}")
        except Exception as e:
            # Unexpected error - log with type but don't fail sync
            logger.error(f"Error triggering SLA workflows for loan {loan_id}: {type(e).__name__}: {e}")

        # Also create SLA tasks in the main tasks table (single source of truth)
        try:
            import asyncio
            from services.sla_task_hook_service import SLATaskHookService

            # Determine which SLA fields changed
            sla_trigger_fields = {
                'application_date', 'uw_received_date', 'conditions_for_review_date',
                'loan_approved_date', 'clear_to_close_date', 'scheduled_closing_date',
                'funded_date', 'appraisal_ordered_date', 'cd_sent_to_borrower_date',
                'lock_date', 'lock_expiration_date', 'prospect_date', 'preapproval_date',
                'contract_received_date', 'closing_date'
            }

            changed_fields = set()
            for field in sla_trigger_fields:
                old_val = old_data.get(field)
                new_val = new_data.get(field)
                if old_val is None and new_val is not None:
                    changed_fields.add(field)

            if changed_fields:
                # Get loan owner for task assignment
                loan_owner = self.db.execute(
                    text("SELECT loan_officer_id FROM loans WHERE id = :loan_id"),
                    {"loan_id": loan_id}
                ).fetchone()
                owner_id = loan_owner[0] if loan_owner and loan_owner[0] else 1

                # Fire async task creation (non-blocking)
                asyncio.create_task(SLATaskHookService.on_loan_updated(
                    loan_id=loan_id,
                    changed_fields=changed_fields,
                    user_id=owner_id,
                    old_stage=old_data.get("stage"),
                    new_stage=new_data.get("stage"),
                ))

                logger.info(
                    f"Salesforce sync triggered SLA task creation for loan {loan_id}: "
                    f"fields={changed_fields}"
                )

        except Exception as e:
            # Don't fail the sync if task creation fails
            logger.error(f"Error creating SLA tasks for loan {loan_id}: {e}")

        # Loan State Reconciliation: validate transition, audit, and route (MUM/archive/pause)
        try:
            from services.loan_reconciliation_service import LoanReconciliationService
            recon_service = LoanReconciliationService(self.db)
            recon_result = recon_service.reconcile(loan_id, old_data, new_data)

            logger.info(
                f"Loan {loan_id} reconciliation: action={recon_result.action.value}, "
                f"{recon_result.old_stage}→{recon_result.new_stage}"
                + (f", warnings={recon_result.warnings}" if recon_result.warnings else "")
            )

            # Note: Stage revert is no longer needed here — pre-write validation
            # in upsert_loan() now strips invalid stage changes BEFORE they reach the DB.
            # Disposition tasks are still created for auditing/LO review.
            if recon_result.should_create_disposition and recon_result.disposition_task_id:
                logger.info(
                    f"Disposition task {recon_result.disposition_task_id} created for "
                    f"loan {loan_id} (stage validated pre-write)"
                )

            # Promote to MUM only when reconciliation says so
            if recon_result.should_promote_mum:
                try:
                    from services.mum_promotion_service import maybe_promote_loan_to_mum_by_raw_data
                    mum_id = maybe_promote_loan_to_mum_by_raw_data(
                        db=self.db,
                        loan_id=loan_id,
                        user_id=self.user_id or 1,
                        loan_data=new_data,
                        old_data=old_data,
                    )
                    if mum_id:
                        logger.info(f"Reconciliation promoted loan {loan_id} to MUM client {mum_id}")
                except Exception as e:
                    logger.warning(f"MUM promotion failed for loan {loan_id}: {e}")

        except ImportError:
            # Reconciliation service not available — fall back to direct MUM promotion
            logger.debug("Loan reconciliation service not available, falling back to direct MUM promotion")
            try:
                from services.mum_promotion_service import maybe_promote_loan_to_mum_by_raw_data
                mum_id = maybe_promote_loan_to_mum_by_raw_data(
                    db=self.db,
                    loan_id=loan_id,
                    user_id=self.user_id or 1,
                    loan_data=new_data,
                    old_data=old_data,
                )
                if mum_id:
                    logger.info(f"Fallback: auto-promoted loan {loan_id} to MUM client {mum_id}")
            except Exception as e:
                logger.warning(f"MUM promotion failed for loan {loan_id}: {e}")
        except Exception as e:
            # Unexpected reconciliation error — fall back to direct MUM promotion
            logger.warning(f"Reconciliation error for loan {loan_id}: {e}, falling back to direct MUM promotion")
            try:
                from services.mum_promotion_service import maybe_promote_loan_to_mum_by_raw_data
                mum_id = maybe_promote_loan_to_mum_by_raw_data(
                    db=self.db,
                    loan_id=loan_id,
                    user_id=self.user_id or 1,
                    loan_data=new_data,
                    old_data=old_data,
                )
                if mum_id:
                    logger.info(f"Fallback: auto-promoted loan {loan_id} to MUM client {mum_id}")
            except Exception as e2:
                logger.warning(f"MUM promotion fallback also failed for loan {loan_id}: {e2}")

    def process_webhook(self, payload: Dict[str, Any]) -> SyncResult:
        """
        Process a webhook payload from Salesforce.

        Expected payload format:
        {
            "records": [
                {
                    "Id": "a0B...",
                    "Name": "Loan-001",
                    "MtgPlanner_CRM__Loan_Amount__c": 350000,
                    ...
                }
            ],
            "event_type": "created" | "updated" | "deleted"
        }
        """
        result = SyncResult(status=SyncStatus.SUCCESS)

        records = payload.get("records", [])
        if not records:
            # Single record format
            if "Id" in payload:
                records = [payload]
            else:
                result.status = SyncStatus.SKIPPED
                return result

        result.records_processed = len(records)

        for sf_record in records:
            try:
                loan_data = self.map_salesforce_to_loan(sf_record)
                loan_id, action = self.upsert_loan(loan_data)

                if action == "created":
                    result.records_created += 1
                    result.created_loan_ids.append(loan_id)
                elif action == "updated":
                    result.records_updated += 1
                    result.updated_loan_ids.append(loan_id)
                else:
                    result.records_failed += 1
                    result.errors.append(f"Failed to upsert record {sf_record.get('Id', 'unknown')}")
                    # Create reconciliation task for failed record
                    self._create_reconciliation_task_for_failed_record(sf_record, loan_data)

            except Exception as e:
                result.records_failed += 1
                result.errors.append(f"Error processing record: {str(e)}")
                logger.error(f"Error processing Salesforce record: {e}")
                # Create reconciliation task for exception
                self._create_reconciliation_task_for_failed_record(sf_record, {}, str(e))

        # Determine overall status
        if result.records_failed == result.records_processed:
            result.status = SyncStatus.FAILED
        elif result.records_failed > 0:
            result.status = SyncStatus.PARTIAL

        # Log sync event
        self.log_sync_event(result, payload)

        return result

    def full_sync(self, access_token: str, instance_url: str) -> SyncResult:
        """
        Perform a full sync from Salesforce.
        Fetches all records from MtgPlanner_CRM__Transaction_Property__c.
        """
        from integrations.salesforce_service import salesforce_client

        result = SyncResult(status=SyncStatus.SUCCESS)

        try:
            # Query all transaction properties
            soql = """
                SELECT Id, Name, CreatedDate, LastModifiedDate,
                       MtgPlanner_CRM__Loan_Amount__c, MtgPlanner_CRM__Loan_Type__c,
                       MtgPlanner_CRM__Property_Address__c, MtgPlanner_CRM__Property_City__c,
                       MtgPlanner_CRM__Property_State__c, MtgPlanner_CRM__Property_Zip__c,
                       MtgPlanner_CRM__Borrower_Name__c, MtgPlanner_CRM__Borrower_Email__c,
                       MtgPlanner_CRM__Borrower_Phone__c, MtgPlanner_CRM__Status__c,
                       MtgPlanner_CRM__Closing_Date__c, MtgPlanner_CRM__Purchase_Price__c
                FROM MtgPlanner_CRM__Transaction_Property__c
                ORDER BY LastModifiedDate DESC
            """

            query_result = salesforce_client.query(access_token, instance_url, soql)

            if not query_result:
                result.status = SyncStatus.FAILED
                result.errors.append("Failed to query Salesforce")
                return result

            records = query_result.get("records", [])
            result.records_processed = len(records)

            for sf_record in records:
                try:
                    loan_data = self.map_salesforce_to_loan(sf_record)
                    loan_id, action = self.upsert_loan(loan_data)

                    if action == "created":
                        result.records_created += 1
                        result.created_loan_ids.append(loan_id)
                    elif action == "updated":
                        result.records_updated += 1
                        result.updated_loan_ids.append(loan_id)
                    else:
                        result.records_failed += 1

                except Exception as e:
                    result.records_failed += 1
                    result.errors.append(str(e))

            if result.records_failed == result.records_processed:
                result.status = SyncStatus.FAILED
            elif result.records_failed > 0:
                result.status = SyncStatus.PARTIAL

        except Exception as e:
            result.status = SyncStatus.FAILED
            result.errors.append(f"Full sync failed: {str(e)}")
            logger.error(f"Full sync error: {e}")

        return result

    def log_sync_event(self, result: SyncResult, payload: Optional[Dict] = None, direction: str = "inbound"):
        """Log a sync event to the database."""
        try:
            payload_summary = None
            if payload:
                # Store summary, not full payload
                records = payload.get("records", [payload] if "Id" in payload else [])
                payload_summary = {
                    "record_count": len(records),
                    "salesforce_ids": [r.get("Id") for r in records[:10]],  # First 10 IDs
                    "event_type": payload.get("event_type", "webhook"),
                }

            self.db.execute(text("""
                INSERT INTO salesforce_sync_logs
                (sync_type, direction, status, records_processed, records_created,
                 records_updated, records_failed, error_message, payload_summary,
                 started_at, completed_at, user_id, organization_id)
                VALUES
                (:sync_type, :direction, :status, :processed, :created, :updated,
                 :failed, :errors, :payload, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP,
                 :user_id, :org_id)
            """), {
                "sync_type": "push" if direction == "outbound" else "webhook",
                "direction": direction,
                "status": result.status.value,
                "processed": result.records_processed,
                "created": result.records_created,
                "updated": result.records_updated,
                "failed": result.records_failed,
                "errors": "; ".join(result.errors) if result.errors else None,
                "payload": str(payload_summary) if payload_summary else None,
                "user_id": self.user_id,
                "org_id": self.organization_id,
            })
            self.db.commit()
        except SQLAlchemyError as e:
            logger.error(f"Failed to log sync event: {e}")

    def _create_reconciliation_task_for_failed_record(
        self,
        sf_record: Dict[str, Any],
        loan_data: Dict[str, Any],
        error_message: str = ""
    ):
        """
        Create a reconciliation task when a Salesforce record fails to import.

        This allows the user to manually review and fix import issues.
        """
        try:
            from services.date_reconciliation_service import DateReconciliationService, DateUpdate

            sf_id = sf_record.get("Id", "")
            borrower_name = (
                sf_record.get("MtgPlanner_CRM__Borrower_Name__c") or
                loan_data.get("borrower_name") or
                sf_record.get("Name", "")
            )
            loan_number = (
                sf_record.get("Name") or
                loan_data.get("loan_number", "")
            )
            borrower_email = (
                sf_record.get("MtgPlanner_CRM__Borrower_Email__c") or
                loan_data.get("borrower_email")
            )

            # Extract key info for the task
            title = f"Import Failed - {borrower_name or loan_number or sf_id[:8]}"

            description = f"""A Salesforce record could not be imported into the CRM.

**Salesforce Record ID:** {sf_id}
**Error:** {error_message or 'Upsert failed'}

**Record Information:**
- Borrower Name: {borrower_name or 'Not available'}
- Loan Number: {loan_number or 'Not available'}
- Email: {borrower_email or 'Not available'}

**Action Required:**
1. Review the error and fix any data issues
2. Import the record manually or re-run the sync
3. Ensure all required fields are populated in Salesforce

**Quick Actions:**
- [Retry Import] - Attempt to import this record again
- [Create Loan Manually] - Create a loan record and link it
"""

            self.db.execute(text("""
                INSERT INTO tasks (
                    title, description, status, priority, source,
                    entity_type, owner_id, created_by_id, created_at, updated_at
                ) VALUES (
                    :title, :description, 'pending', 'high', 'Salesforce Date Sync',
                    'reconciliation', :owner_id, :owner_id, NOW(), NOW()
                )
            """), {
                "title": title,
                "description": description,
                "owner_id": self.user_id or 1,
            })
            self.db.commit()

            logger.info(f"Created reconciliation task for failed Salesforce import: {sf_id}")

        except Exception as e:
            # Don't fail the sync if task creation fails
            logger.warning(f"Could not create reconciliation task for failed import: {e}")

    # =========================================================================
    # OUTBOUND SYNC METHODS (CRM -> Salesforce)
    # =========================================================================

    def transform_value_outbound(self, value: Any, transform_type: Optional[str]) -> Any:
        """Transform a CRM value to Salesforce format."""
        if value is None:
            return None

        if transform_type is None:
            return value

        if transform_type == "decimal":
            try:
                return float(value) if value else None
            except (ValueError, TypeError):
                return None

        if transform_type == "date_to_string":
            # Convert date object to Salesforce date string (YYYY-MM-DD)
            if hasattr(value, 'strftime'):
                return value.strftime("%Y-%m-%d")
            if isinstance(value, str):
                return value[:10] if len(value) >= 10 else value
            return None

        if transform_type == "datetime_to_string":
            # Convert datetime to ISO format for Salesforce
            if hasattr(value, 'isoformat'):
                return value.isoformat()
            return str(value) if value else None

        if transform_type == "reverse_stage_mapping":
            # Map CRM stage to Salesforce status
            stage_str = str(value).upper() if value else "APPLICATION"
            return REVERSE_STAGE_MAPPING.get(stage_str, "Application")

        if transform_type == "boolean":
            return bool(value)

        return value

    def get_outbound_field_mappings(self) -> Dict[str, Tuple[str, Optional[str]]]:
        """Get outbound field mappings (CRM -> Salesforce)."""
        # Try to load custom outbound mappings from database
        try:
            result = self.db.execute(text("""
                SELECT crm_field, salesforce_field, transform_type
                FROM salesforce_field_mappings
                WHERE organization_id = :org_id
                  AND salesforce_object = 'MtgPlanner_CRM__Transaction_Property__c'
                  AND is_active = true
                  AND direction = 'outbound'
            """), {"org_id": self.organization_id})

            custom_mappings = {}
            for row in result.fetchall():
                custom_mappings[row[0]] = (row[1], row[2])

            if custom_mappings:
                logger.info(f"Loaded {len(custom_mappings)} custom outbound field mappings")
                return custom_mappings
        except Exception as e:
            logger.warning(f"Could not load custom outbound field mappings: {e}")

        return DEFAULT_OUTBOUND_MAPPING

    def map_loan_to_salesforce(self, loan_data: Dict[str, Any]) -> Dict[str, Any]:
        """Map CRM loan fields to Salesforce record format."""
        field_mappings = self.get_outbound_field_mappings()
        sf_record = {}

        for crm_field, (sf_field, transform_type) in field_mappings.items():
            if crm_field in loan_data:
                value = loan_data[crm_field]
                transformed_value = self.transform_value_outbound(value, transform_type)
                if transformed_value is not None:
                    sf_record[sf_field] = transformed_value

        return sf_record

    def push_loan(
        self,
        loan_id: int,
        access_token: str,
        instance_url: str,
        sf_object: str = "MtgPlanner_CRM__Transaction_Property__c"
    ) -> Tuple[bool, str, Optional[str]]:
        """
        Push a single loan to Salesforce.

        Returns:
            Tuple of (success, action, salesforce_id)
            action is 'created', 'updated', or 'error'
        """
        import requests

        try:
            # Fetch loan data
            result = self.db.execute(text("""
                SELECT * FROM loans WHERE id = :loan_id
            """), {"loan_id": loan_id})

            row = result.fetchone()
            if not row:
                return False, "error", f"Loan {loan_id} not found"

            # Convert row to dict
            loan_data = dict(row._mapping)

            # Map to Salesforce format
            sf_record = self.map_loan_to_salesforce(loan_data)

            if not sf_record:
                return False, "error", "No fields to sync"

            # Check if loan already has a Salesforce ID
            salesforce_id = loan_data.get("salesforce_id")

            headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json"
            }

            if salesforce_id:
                # Update existing record
                url = f"{instance_url}/services/data/{SALESFORCE_API_VERSION}/sobjects/{sf_object}/{salesforce_id}"
                response = requests.patch(url, headers=headers, json=sf_record, timeout=30)

                if response.status_code == 204:
                    # Update sync metadata in CRM
                    self._update_loan_sync_status(loan_id, salesforce_id, "synced")
                    logger.info(f"Updated Salesforce record {salesforce_id} for loan {loan_id}")
                    return True, "updated", salesforce_id
                else:
                    error_msg = response.text
                    logger.error(f"Failed to update Salesforce record: {error_msg}")
                    return False, "error", error_msg
            else:
                # Create new record
                url = f"{instance_url}/services/data/{SALESFORCE_API_VERSION}/sobjects/{sf_object}"
                response = requests.post(url, headers=headers, json=sf_record, timeout=30)

                if response.status_code == 201:
                    result_data = response.json()
                    new_sf_id = result_data.get("id")

                    # Update CRM loan with Salesforce ID
                    self._update_loan_sync_status(loan_id, new_sf_id, "synced")
                    logger.info(f"Created Salesforce record {new_sf_id} for loan {loan_id}")
                    return True, "created", new_sf_id
                else:
                    error_msg = response.text
                    logger.error(f"Failed to create Salesforce record: {error_msg}")
                    return False, "error", error_msg

        except RequestException as e:
            logger.error(f"Error pushing loan {loan_id} to Salesforce: {e}")
            return False, "error", str(e)

    def _update_loan_sync_status(self, loan_id: int, salesforce_id: str, status: str):
        """Update loan sync status in the database."""
        try:
            self.db.execute(text("""
                UPDATE loans
                SET salesforce_id = :sf_id,
                    salesforce_last_synced_at = CURRENT_TIMESTAMP,
                    salesforce_sync_status = :status,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = :loan_id
            """), {
                "sf_id": salesforce_id,
                "status": status,
                "loan_id": loan_id
            })
            self.db.commit()
        except SQLAlchemyError as e:
            logger.error(f"Failed to update loan sync status: {e}")
            self.db.rollback()

    def push_loans_batch(
        self,
        loan_ids: List[int],
        access_token: str,
        instance_url: str,
        sf_object: str = "MtgPlanner_CRM__Transaction_Property__c"
    ) -> SyncResult:
        """
        Push multiple loans to Salesforce.

        Args:
            loan_ids: List of loan IDs to push
            access_token: Salesforce OAuth access token
            instance_url: Salesforce instance URL
            sf_object: Salesforce object to push to

        Returns:
            SyncResult with details of the operation
        """
        result = SyncResult(status=SyncStatus.SUCCESS)
        result.records_processed = len(loan_ids)

        for loan_id in loan_ids:
            try:
                success, action, sf_id_or_error = self.push_loan(
                    loan_id, access_token, instance_url, sf_object
                )

                if success:
                    if action == "created":
                        result.records_created += 1
                        result.created_loan_ids.append(loan_id)
                    elif action == "updated":
                        result.records_updated += 1
                        result.updated_loan_ids.append(loan_id)
                else:
                    result.records_failed += 1
                    result.errors.append(f"Loan {loan_id}: {sf_id_or_error}")

            except Exception as e:
                result.records_failed += 1
                result.errors.append(f"Loan {loan_id}: {str(e)}")
                logger.error(f"Error pushing loan {loan_id}: {e}")

        # Determine overall status
        if result.records_failed == result.records_processed:
            result.status = SyncStatus.FAILED
        elif result.records_failed > 0:
            result.status = SyncStatus.PARTIAL

        # Log the sync event
        self.log_sync_event(result, {"loan_ids": loan_ids}, direction="outbound")

        return result

    def get_pushable_loans(self, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Get loans that can be pushed to Salesforce.
        Returns loans that have been modified since last sync or never synced.
        """
        try:
            result = self.db.execute(text("""
                SELECT id, loan_number, stage, borrower_name,
                       salesforce_id, salesforce_last_synced_at, updated_at
                FROM loans
                WHERE organization_id = :org_id
                  AND (
                      salesforce_id IS NULL
                      OR salesforce_last_synced_at IS NULL
                      OR updated_at > salesforce_last_synced_at
                  )
                ORDER BY updated_at DESC
                LIMIT :limit
            """), {"org_id": self.organization_id, "limit": limit})

            loans = []
            for row in result.fetchall():
                loans.append({
                    "id": row[0],
                    "loan_number": row[1],
                    "stage": row[2],
                    "borrower_name": row[3],
                    "salesforce_id": row[4],
                    "last_synced_at": row[5].isoformat() if row[5] else None,
                    "updated_at": row[6].isoformat() if row[6] else None,
                    "needs_sync": True
                })

            return loans
        except Exception as e:
            logger.error(f"Error getting pushable loans: {e}")
            return []

    # =========================================================================
    # INBOUND SYNC FOR SINGLE RECORD (Pull from Salesforce)
    # =========================================================================

    def pull_loan(
        self,
        loan_id: int,
        access_token: str,
        instance_url: str,
        sf_object: str = "MtgPlanner_CRM__Transaction_Property__c"
    ) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
        """
        Pull/refresh a single loan from Salesforce.

        Args:
            loan_id: CRM loan ID
            access_token: Salesforce OAuth access token
            instance_url: Salesforce instance URL
            sf_object: Salesforce object type

        Returns:
            Tuple of (success, message, updated_data)
        """
        import requests

        try:
            # Get loan's Salesforce ID
            result = self.db.execute(text("""
                SELECT salesforce_id FROM loans WHERE id = :loan_id
            """), {"loan_id": loan_id})

            row = result.fetchone()
            if not row:
                return False, f"Loan {loan_id} not found", None

            salesforce_id = row[0]
            if not salesforce_id:
                return False, "Loan has no Salesforce ID - cannot pull", None

            # SECURITY: Validate inputs to prevent SOQL injection
            try:
                salesforce_id = validate_salesforce_id(salesforce_id)
                sf_object = validate_salesforce_object_name(sf_object)
            except ValueError as e:
                logger.error(f"SOQL injection attempt blocked: {e}")
                return False, f"Invalid Salesforce ID or object name: {e}", None

            # Build SOQL query to fetch the record
            field_mappings = self.get_field_mappings()
            sf_fields = list(field_mappings.keys())
            field_list = ", ".join(sf_fields)

            soql = f"SELECT {field_list} FROM {sf_object} WHERE Id = '{salesforce_id}'"

            headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json"
            }

            # Execute SOQL query
            import urllib.parse
            encoded_soql = urllib.parse.quote(soql)
            url = f"{instance_url}/services/data/{SALESFORCE_API_VERSION}/query/?q={encoded_soql}"

            response = requests.get(url, headers=headers, timeout=30)

            if response.status_code != 200:
                error_msg = response.text
                logger.error(f"Failed to query Salesforce: {error_msg}")
                return False, f"Salesforce query failed: {error_msg}", None

            result_data = response.json()
            records = result_data.get("records", [])

            if not records:
                return False, f"Record {salesforce_id} not found in Salesforce", None

            sf_record = records[0]

            # Map Salesforce record to CRM format
            loan_data = self.map_salesforce_to_loan(sf_record)

            # Update the loan in CRM
            loan_id_result, action = self.upsert_loan(loan_data)

            if action == "error":
                return False, "Failed to update loan in CRM", None

            return True, f"Loan refreshed from Salesforce", loan_data

        except Exception as e:
            logger.error(f"Error pulling loan {loan_id} from Salesforce: {e}")
            return False, str(e), None

    def pull_loan_by_salesforce_id(
        self,
        salesforce_id: str,
        access_token: str,
        instance_url: str,
        sf_object: str = "MtgPlanner_CRM__Transaction_Property__c"
    ) -> Tuple[bool, str, Optional[int]]:
        """
        Pull a loan from Salesforce by its Salesforce ID.
        Creates or updates the loan in CRM.

        Returns:
            Tuple of (success, message, loan_id)
        """
        import requests

        try:
            # SECURITY: Validate inputs to prevent SOQL injection
            try:
                salesforce_id = validate_salesforce_id(salesforce_id)
                sf_object = validate_salesforce_object_name(sf_object)
            except ValueError as e:
                logger.error(f"SOQL injection attempt blocked: {e}")
                return False, f"Invalid Salesforce ID or object name: {e}", None

            # Build SOQL query to fetch the record
            field_mappings = self.get_field_mappings()
            sf_fields = list(field_mappings.keys())
            field_list = ", ".join(sf_fields)

            soql = f"SELECT {field_list} FROM {sf_object} WHERE Id = '{salesforce_id}'"

            headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json"
            }

            # Execute SOQL query
            import urllib.parse
            encoded_soql = urllib.parse.quote(soql)
            url = f"{instance_url}/services/data/{SALESFORCE_API_VERSION}/query/?q={encoded_soql}"

            response = requests.get(url, headers=headers, timeout=30)

            if response.status_code != 200:
                error_msg = response.text
                logger.error(f"Failed to query Salesforce: {error_msg}")
                return False, f"Salesforce query failed: {error_msg}", None

            result_data = response.json()
            records = result_data.get("records", [])

            if not records:
                return False, f"Record {salesforce_id} not found in Salesforce", None

            sf_record = records[0]

            # Map Salesforce record to CRM format
            loan_data = self.map_salesforce_to_loan(sf_record)

            # Upsert the loan
            loan_id, action = self.upsert_loan(loan_data)

            if action == "error":
                return False, "Failed to upsert loan in CRM", None

            return True, f"Loan {action} from Salesforce", loan_id

        except Exception as e:
            logger.error(f"Error pulling loan from Salesforce: {e}")
            return False, str(e), None


# Singleton instance
_sync_service = None


def get_salesforce_sync_service(db: Session, user_id: Optional[int] = None, organization_id: int = 1) -> SalesforceSyncService:
    """Get or create the Salesforce sync service."""
    return SalesforceSyncService(db, user_id, organization_id)
