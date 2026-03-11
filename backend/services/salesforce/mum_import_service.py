"""
Shared MUM (Market Update Mailing / Mortgage Under Management) import service.

Consolidates previously duplicated MUM import logic from multiple locations:
- salesforce_data_routes.py: import_funded_loans_to_mum, _run_import_job
- salesforce_integration_routes.py: sync_funded_loans_to_mum_clients,
  full_sync_pipeline, admin_sync_all_profiles, admin_test_sync_simple,
  import_funded_loans_to_mum_debug

All copies shared the same core pattern: find funded loans not already in
mum_clients, map loan fields to mum_client columns, insert.

Usage:
    from services.salesforce.mum_import_service import MumImportService

    service = MumImportService(db, user_id=current_user.id)
    result = service.import_funded_loans()
    # result = {"created": 5, "skipped": 0, "errors": [], "total_eligible": 5}
"""
import logging
from typing import Dict, List, Any, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

logger = logging.getLogger(__name__)


# Stage patterns that indicate a loan is funded/closed
_FUNDED_STAGE_FILTERS = """
    (l.stage::text ILIKE '%%fund%%'
     OR (l.stage::text ILIKE '%%closed%%' AND l.stage::text NOT ILIKE '%%disclosed%%')
     OR l.stage::text ILIKE '%%won%%'
     OR l.stage::text ILIKE '%%ship%%'
     OR l.funded_date IS NOT NULL)
"""


class MumImportService:
    """Service for importing funded loans to MUM (Mortgage Under Management) clients.

    This is the single authoritative implementation. All routes that need to
    sync funded loans into the mum_clients table should use this service.
    """

    def __init__(self, db: Session, user_id: Optional[int] = None):
        """
        Args:
            db: SQLAlchemy database session
            user_id: User ID to associate with created MUM records (optional;
                     if None, records are created without user_id)
        """
        self.db = db
        self.user_id = user_id

    def ensure_salesforce_id_column(self) -> bool:
        """Ensure the salesforce_id column exists on the mum_clients table.

        Returns True if the column already existed or was successfully created.
        """
        try:
            check = self.db.execute(text("""
                SELECT column_name FROM information_schema.columns
                WHERE table_name = 'mum_clients' AND column_name = 'salesforce_id'
            """)).fetchone()
            if not check:
                self.db.execute(text(
                    "ALTER TABLE mum_clients ADD COLUMN salesforce_id VARCHAR(100)"
                ))
                self.db.execute(text(
                    "CREATE INDEX IF NOT EXISTS idx_mum_clients_salesforce_id "
                    "ON mum_clients(salesforce_id)"
                ))
                self.db.commit()
                logger.info("Added salesforce_id column to mum_clients")
            return True
        except SQLAlchemyError as e:
            logger.warning(f"Could not ensure salesforce_id column: {e}")
            return False

    def import_funded_loans(
        self,
        include_salesforce_id: bool = True,
        commit: bool = True,
    ) -> Dict[str, Any]:
        """Import funded loans into the mum_clients table using atomic INSERT...SELECT.

        This uses a single atomic SQL statement to avoid the per-row rollback bug
        where db.rollback() inside a loop destroys ALL previous uncommitted inserts.

        The query resolves client names via multiple fallback strategies:
        1. l.borrower_name (skip if it looks like a Salesforce ID)
        2. Matched lead by email
        3. Matched lead by loan_number
        4. Matched lead by salesforce_id
        5. Fallback: 'Client - {loan_number}'

        Args:
            include_salesforce_id: If True, include salesforce_id column in insert.
                Set to True when Salesforce sync context is available.
            commit: If True, commit the transaction. Set to False if the caller
                manages the transaction.

        Returns:
            Dict with keys: created, total_eligible, errors
        """
        result = {
            "created": 0,
            "total_eligible": 0,
            "errors": [],
        }

        try:
            # Count eligible loans first
            count = self.db.execute(text(f"""
                SELECT COUNT(*) FROM loans l
                WHERE {_FUNDED_STAGE_FILTERS}
                AND l.loan_number IS NOT NULL
                AND NOT EXISTS (
                    SELECT 1 FROM mum_clients m WHERE m.loan_number = l.loan_number
                )
            """)).scalar()
            result["total_eligible"] = count or 0

            if count == 0:
                return result

            # Ensure salesforce_id column exists if we need it
            if include_salesforce_id:
                self.ensure_salesforce_id_column()

            # Build the INSERT...SELECT statement
            # Columns that are NOT NULL in the mum_clients table:
            #   client_name, closing_date, first_payment_date, interest_rate,
            #   original_loan_amount, current_loan_amount,
            #   appraisal_value_at_closing, current_property_value
            sf_id_col = ", salesforce_id" if include_salesforce_id else ""
            sf_id_val = ", l.salesforce_id" if include_salesforce_id else ""
            user_id_col = ", user_id" if self.user_id else ""
            user_id_val = ", :user_id" if self.user_id else ""

            params = {}
            if self.user_id:
                params["user_id"] = self.user_id

            insert_result = self.db.execute(text(f"""
                INSERT INTO mum_clients (
                    client_name, loan_number, original_close_date,
                    original_rate, loan_balance,
                    original_loan_amount, current_loan_amount,
                    interest_rate, appraisal_value_at_closing,
                    current_property_value, closing_date, first_payment_date,
                    status, engagement_score, created_at
                    {sf_id_col}{user_id_col}
                )
                SELECT
                    COALESCE(
                        NULLIF(
                            CASE WHEN l.borrower_name ~ '^[0-9a-zA-Z]{{15,18}}$'
                                 THEN NULL
                                 ELSE l.borrower_name
                            END,
                            ''
                        ),
                        NULLIF(TRIM(COALESCE(le.first_name, '') || ' ' || COALESCE(le.last_name, '')), ''),
                        NULLIF(TRIM(COALESCE(le2.first_name, '') || ' ' || COALESCE(le2.last_name, '')), ''),
                        NULLIF(TRIM(COALESCE(le3.first_name, '') || ' ' || COALESCE(le3.last_name, '')), ''),
                        'Client - ' || l.loan_number
                    ),
                    l.loan_number,
                    COALESCE(l.funded_date, l.closing_date, CURRENT_DATE),
                    COALESCE(l.rate, 0),
                    COALESCE(l.amount, 0),
                    COALESCE(l.amount, 0),
                    COALESCE(l.amount, 0),
                    COALESCE(l.rate, 0),
                    COALESCE(l.appraisal_value, l.amount * 1.25, 0),
                    COALESCE(l.appraisal_value, l.amount * 1.25, 0),
                    COALESCE(l.closing_date, l.funded_date, CURRENT_DATE),
                    COALESCE(l.funded_date, l.closing_date, CURRENT_DATE),
                    'active',
                    50,
                    CURRENT_TIMESTAMP
                    {sf_id_val}{user_id_val}
                FROM loans l
                LEFT JOIN leads le ON le.email = l.borrower_email AND le.email IS NOT NULL
                LEFT JOIN leads le2 ON le2.loan_number = l.loan_number AND le2.loan_number IS NOT NULL
                LEFT JOIN leads le3 ON le3.salesforce_id = l.salesforce_id AND le3.salesforce_id IS NOT NULL
                WHERE {_FUNDED_STAGE_FILTERS}
                AND l.loan_number IS NOT NULL
                AND NOT EXISTS (
                    SELECT 1 FROM mum_clients m WHERE m.loan_number = l.loan_number
                )
            """), params)

            result["created"] = insert_result.rowcount

            if commit:
                self.db.commit()

            logger.info(
                f"MUM import complete: {result['created']} created from "
                f"{result['total_eligible']} eligible (user_id={self.user_id})"
            )

        except SQLAlchemyError as e:
            logger.exception("MUM import failed")
            if commit:
                try:
                    self.db.rollback()
                except Exception:
                    pass
            result["errors"].append(str(e))

        return result

    def import_single_loan(
        self,
        loan_number: str,
        client_name: Optional[str] = None,
        salesforce_id: Optional[str] = None,
        commit: bool = True,
    ) -> Dict[str, Any]:
        """Import a single loan to MUM by loan number.

        Useful for on-demand import when a specific loan is funded.

        Args:
            loan_number: The loan number to import
            client_name: Override client name (optional)
            salesforce_id: Salesforce record ID (optional)
            commit: If True, commit the transaction

        Returns:
            Dict with keys: created (bool), error (str or None)
        """
        try:
            # Check if already exists
            existing = self.db.execute(
                text("SELECT id FROM mum_clients WHERE loan_number = :ln"),
                {"ln": loan_number}
            ).fetchone()

            if existing:
                return {"created": False, "error": None, "message": "Already exists"}

            # Get loan data
            loan = self.db.execute(text("""
                SELECT l.loan_number, l.borrower_name, l.amount, l.rate,
                       l.funded_date, l.closing_date, l.appraisal_value,
                       l.salesforce_id
                FROM loans l
                WHERE l.loan_number = :ln
            """), {"ln": loan_number}).fetchone()

            if not loan:
                return {"created": False, "error": f"Loan {loan_number} not found"}

            name = client_name or loan.borrower_name or f"Client - {loan_number}"
            sf_id = salesforce_id or loan.salesforce_id
            close_date = loan.funded_date or loan.closing_date
            rate = loan.rate or 0
            amount = loan.amount or 0
            appraisal = loan.appraisal_value or (amount * 1.25 if amount else 0)

            params = {
                "name": name,
                "ln": loan_number,
                "close_date": close_date,
                "rate": rate,
                "amount": amount,
                "appraisal": appraisal,
                "sf_id": sf_id,
            }
            if self.user_id:
                params["user_id"] = self.user_id

            user_id_col = ", user_id" if self.user_id else ""
            user_id_val = ", :user_id" if self.user_id else ""

            self.db.execute(text(f"""
                INSERT INTO mum_clients (
                    client_name, loan_number, original_close_date,
                    original_rate, loan_balance,
                    original_loan_amount, current_loan_amount,
                    interest_rate, appraisal_value_at_closing,
                    current_property_value, closing_date, first_payment_date,
                    status, engagement_score, salesforce_id, created_at
                    {user_id_col}
                ) VALUES (
                    :name, :ln, COALESCE(:close_date, CURRENT_DATE),
                    :rate, :amount,
                    :amount, :amount,
                    :rate, :appraisal,
                    :appraisal, COALESCE(:close_date, CURRENT_DATE),
                    COALESCE(:close_date, CURRENT_DATE),
                    'active', 50, :sf_id, CURRENT_TIMESTAMP
                    {user_id_val}
                )
            """), params)

            if commit:
                self.db.commit()

            logger.info(f"Imported single MUM client: {name} ({loan_number})")
            return {"created": True, "error": None}

        except SQLAlchemyError as e:
            logger.exception(f"Failed to import single MUM client: {loan_number}")
            if commit:
                try:
                    self.db.rollback()
                except Exception:
                    pass
            return {"created": False, "error": str(e)}
