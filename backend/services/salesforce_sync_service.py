"""
Salesforce Sync Service
Handles synchronization of data from Salesforce to the CRM
"""
import os
import logging
import hashlib
import hmac
from datetime import datetime
from typing import Dict, Any, Optional, List, Tuple
from dataclasses import dataclass, field
from enum import Enum

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


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
    "MtgPlanner_CRM__Closing_Date__c": ("closing_date", "date"),
    "MtgPlanner_CRM__Lock_Date__c": ("lock_date", "date"),
    "MtgPlanner_CRM__Lock_Expiration__c": ("lock_expiration_date", "date"),
    "MtgPlanner_CRM__Application_Date__c": ("application_date", "date"),
    "MtgPlanner_CRM__Contract_Date__c": ("contract_received_date", "date"),

    # Timestamps
    "CreatedDate": ("created_at", "datetime"),
    "LastModifiedDate": ("updated_at", "datetime"),
}

# Stage mapping from Salesforce values to CRM LoanStage enum
STAGE_MAPPING = {
    # Salesforce status -> CRM stage
    "New": "APPLICATION",
    "Application": "APPLICATION",
    "Submitted": "PROCESSING",
    "Processing": "PROCESSING",
    "In Processing": "PROCESSING",
    "Underwriting": "UNDERWRITING",
    "In Underwriting": "UNDERWRITING",
    "Conditionally Approved": "APPROVED",
    "Approved": "APPROVED",
    "Clear to Close": "CLEAR_TO_CLOSE",
    "CTC": "CLEAR_TO_CLOSE",
    "Docs Out": "CLEAR_TO_CLOSE",
    "Docs Signed": "CLEAR_TO_CLOSE",
    "Funded": "FUNDED",
    "Closed": "FUNDED",
    "Cancelled": "CANCELLED",
    "Withdrawn": "CANCELLED",
    "Denied": "DENIED",
    "Rejected": "DENIED",
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
            # In development, allow without signature verification
            logger.warning("SALESFORCE_WEBHOOK_SECRET not set - skipping signature verification")
            return True

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
        except Exception as e:
            logger.warning(f"Could not load custom field mappings: {e}")

        # Fall back to default mappings
        self._field_mappings = DEFAULT_FIELD_MAPPING
        return self._field_mappings

    def transform_value(self, value: Any, transform_type: Optional[str]) -> Any:
        """Transform a Salesforce value to CRM format."""
        if value is None:
            return None

        if transform_type is None:
            return value

        if transform_type == "decimal":
            try:
                return float(value) if value else None
            except (ValueError, TypeError):
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
            # Map Salesforce status to CRM stage
            return STAGE_MAPPING.get(str(value), "APPLICATION")

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

        # Set sync metadata
        loan_data["salesforce_last_synced_at"] = datetime.utcnow()
        loan_data["salesforce_sync_status"] = "synced"

        # Ensure required fields have defaults
        if "loan_number" not in loan_data and "salesforce_id" in loan_data:
            loan_data["loan_number"] = f"SF-{loan_data['salesforce_id'][-8:]}"

        if "stage" not in loan_data:
            loan_data["stage"] = "APPLICATION"

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
            # Check if loan exists
            existing = self.db.execute(text("""
                SELECT id FROM loans WHERE salesforce_id = :sf_id
            """), {"sf_id": salesforce_id}).fetchone()

            if existing:
                # Update existing loan
                loan_id = existing[0]
                update_fields = []
                params = {"loan_id": loan_id}

                for field, value in loan_data.items():
                    if field != "salesforce_id":  # Don't update the ID
                        update_fields.append(f"{field} = :{field}")
                        params[field] = value

                if update_fields:
                    self.db.execute(text(f"""
                        UPDATE loans
                        SET {", ".join(update_fields)}, updated_at = CURRENT_TIMESTAMP
                        WHERE id = :loan_id
                    """), params)
                    self.db.commit()

                logger.info(f"Updated loan {loan_id} from Salesforce {salesforce_id}")
                return loan_id, "updated"
            else:
                # Create new loan
                # Build insert statement dynamically based on available fields
                fields = list(loan_data.keys())
                placeholders = [f":{f}" for f in fields]

                # Add organization and owner
                if self.organization_id:
                    fields.append("organization_id")
                    placeholders.append(":organization_id")
                    loan_data["organization_id"] = self.organization_id

                if self.user_id:
                    fields.append("loan_officer_id")
                    placeholders.append(":loan_officer_id")
                    loan_data["loan_officer_id"] = self.user_id

                result = self.db.execute(text(f"""
                    INSERT INTO loans ({", ".join(fields)})
                    VALUES ({", ".join(placeholders)})
                    RETURNING id
                """), loan_data)
                self.db.commit()

                loan_id = result.fetchone()[0]
                logger.info(f"Created loan {loan_id} from Salesforce {salesforce_id}")
                return loan_id, "created"

        except Exception as e:
            logger.error(f"Error upserting loan from Salesforce {salesforce_id}: {e}")
            self.db.rollback()
            return None, "error"

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

            except Exception as e:
                result.records_failed += 1
                result.errors.append(f"Error processing record: {str(e)}")
                logger.error(f"Error processing Salesforce record: {e}")

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

    def log_sync_event(self, result: SyncResult, payload: Optional[Dict] = None):
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
                ('webhook', 'inbound', :status, :processed, :created, :updated,
                 :failed, :errors, :payload, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP,
                 :user_id, :org_id)
            """), {
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
        except Exception as e:
            logger.error(f"Failed to log sync event: {e}")


# Singleton instance
_sync_service = None


def get_salesforce_sync_service(db: Session, user_id: Optional[int] = None, organization_id: int = 1) -> SalesforceSyncService:
    """Get or create the Salesforce sync service."""
    return SalesforceSyncService(db, user_id, organization_id)
