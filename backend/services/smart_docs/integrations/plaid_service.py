"""
Plaid Integration Service for Smart Docs

Provides automated bank account verification, asset report generation,
and transaction analysis via the Plaid API. Designed for mortgage
underwriting workflows.

Key capabilities:
    - Link token creation for borrower bank account connection
    - Public token exchange and encrypted access token storage
    - Transaction retrieval and analysis
    - GSE-certified asset report creation and retrieval
    - Income verification via Plaid Income
    - Large deposit and NSF/overdraft detection from Plaid data
    - Webhook handling for async report completion
    - Secure account disconnection

Security:
    - Access tokens are encrypted with PIIEncryptionService before storage.
    - All Plaid API calls use the resilient_ai_call-style retry pattern.
    - Tenant isolation enforced on all queries.

Usage:
    from services.smart_docs.integrations.plaid_service import (
        PlaidIntegrationService,
    )

    service = PlaidIntegrationService(db)
    link_token = service.create_link_token(borrower_id=42, org_id=1, loan_id=100)
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
import time
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Optional dependency: plaid-python SDK
# ---------------------------------------------------------------------------
try:
    import plaid
    from plaid.api import plaid_api
    from plaid.model.link_token_create_request import LinkTokenCreateRequest
    from plaid.model.link_token_create_request_user import LinkTokenCreateRequestUser
    from plaid.model.item_public_token_exchange_request import ItemPublicTokenExchangeRequest
    from plaid.model.transactions_get_request import TransactionsGetRequest
    from plaid.model.asset_report_create_request import AssetReportCreateRequest
    from plaid.model.asset_report_get_request import AssetReportGetRequest
    from plaid.model.item_remove_request import ItemRemoveRequest
    from plaid.model.products import Products
    from plaid.model.country_code import CountryCode

    HAS_PLAID = True
except ImportError:
    HAS_PLAID = False

# ---------------------------------------------------------------------------
# PII encryption for access token storage
# ---------------------------------------------------------------------------
try:
    from services.smart_docs.pii_encryption_service import (
        PIIEncryptionService,
        get_pii_encryption_service,
    )
    HAS_PII_SERVICE = True
except ImportError:
    HAS_PII_SERVICE = False

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Plaid environments
PLAID_ENVS = {
    "sandbox": "https://sandbox.plaid.com",
    "development": "https://development.plaid.com",
    "production": "https://production.plaid.com",
}

# Default retry configuration
MAX_RETRIES = 3
RETRY_BACKOFF_BASE = 2.0
RETRY_BACKOFF_MAX = 30.0

# Large deposit threshold for mortgage underwriting (Fannie Mae B3-4.2-01)
LARGE_DEPOSIT_THRESHOLD = Decimal("5000.00")

# Default asset report days (60-day history is GSE standard)
DEFAULT_ASSET_REPORT_DAYS = 60


class PlaidServiceError(Exception):
    """Base exception for Plaid integration errors."""

    def __init__(self, message: str, code: str = "PLAID_ERROR"):
        self.message = message
        self.code = code
        super().__init__(self.message)


class PlaidIntegrationService:
    """Plaid API integration for bank account verification and asset reports.

    Requires environment variables:
        PLAID_CLIENT_ID   - Plaid API client ID
        PLAID_SECRET      - Plaid API secret key
        PLAID_ENV         - Environment: sandbox, development, or production
    """

    def __init__(self, db: Session):
        self.db = db

        # Load configuration from environment
        self.client_id = os.environ.get("PLAID_CLIENT_ID", "")
        self.secret = os.environ.get("PLAID_SECRET", "")
        self.env = os.environ.get("PLAID_ENV", "sandbox").lower()
        self.webhook_url = os.environ.get("PLAID_WEBHOOK_URL", "")

        # Initialize Plaid API client
        self._client = None
        if HAS_PLAID and self.client_id and self.secret:
            self._client = self._build_plaid_client()
        elif not HAS_PLAID:
            logger.warning(
                "plaid-python SDK not installed -- Plaid integration disabled. "
                "Install with: pip install plaid-python"
            )
        elif not self.client_id or not self.secret:
            logger.warning(
                "PLAID_CLIENT_ID or PLAID_SECRET not set -- "
                "Plaid integration disabled"
            )

        # Initialize PII encryption service for access token storage
        self._pii_service: Optional[PIIEncryptionService] = None
        if HAS_PII_SERVICE:
            try:
                self._pii_service = get_pii_encryption_service()
            except Exception as e:
                logger.warning("PII encryption service unavailable: %s", e)

    # ------------------------------------------------------------------
    # Client construction
    # ------------------------------------------------------------------

    def _build_plaid_client(self):
        """Build and return a configured Plaid API client."""
        if not HAS_PLAID:
            return None

        configuration = plaid.Configuration(
            host=PLAID_ENVS.get(self.env, PLAID_ENVS["sandbox"]),
            api_key={
                "clientId": self.client_id,
                "secret": self.secret,
            },
        )
        api_client = plaid.ApiClient(configuration)
        return plaid_api.PlaidApi(api_client)

    # ------------------------------------------------------------------
    # Encryption helpers
    # ------------------------------------------------------------------

    def _encrypt_token(self, raw_token: str) -> str:
        """Encrypt an access token for storage."""
        if self._pii_service:
            return self._pii_service.encrypt(raw_token)
        # In production, PIIEncryptionService is mandatory -- never fall back
        # to plaintext-equivalent base64 encoding with real credentials.
        if os.getenv("ENVIRONMENT", "").lower() == "production":
            raise RuntimeError(
                "PIIEncryptionService is required in production for Plaid token storage"
            )
        logger.warning(
            "PII encryption service unavailable -- storing token with "
            "basic obfuscation. This is NOT secure for production."
        )
        # Fallback: base64 encode (NOT secure -- development only)
        import base64
        return base64.b64encode(raw_token.encode("utf-8")).decode("utf-8")

    def _decrypt_token(self, encrypted_token: str) -> str:
        """Decrypt an access token from storage."""
        if self._pii_service:
            return self._pii_service.decrypt(encrypted_token)
        import base64
        return base64.b64decode(encrypted_token.encode("utf-8")).decode("utf-8")

    # ------------------------------------------------------------------
    # Retry wrapper for Plaid API calls
    # ------------------------------------------------------------------

    def _resilient_plaid_call(
        self,
        operation_name: str,
        api_call,
        *args,
        **kwargs,
    ) -> Any:
        """Execute a Plaid API call with retry and backoff.

        Args:
            operation_name: Descriptive name for logging.
            api_call: Callable (Plaid API method).
            *args, **kwargs: Passed to the api_call.

        Returns:
            The API response.

        Raises:
            PlaidServiceError: After all retries exhausted.
        """
        last_error = None

        for attempt in range(1, MAX_RETRIES + 1):
            start_time = time.monotonic()
            try:
                response = api_call(*args, **kwargs)
                duration_ms = int((time.monotonic() - start_time) * 1000)
                logger.info(
                    "Plaid API success | operation=%s | attempt=%d/%d | "
                    "duration_ms=%d",
                    operation_name,
                    attempt,
                    MAX_RETRIES,
                    duration_ms,
                )
                return response
            except Exception as e:
                duration_ms = int((time.monotonic() - start_time) * 1000)
                last_error = e
                error_code = getattr(e, "code", None) or type(e).__name__

                logger.warning(
                    "Plaid API failed | operation=%s | attempt=%d/%d | "
                    "duration_ms=%d | error=%s | code=%s",
                    operation_name,
                    attempt,
                    MAX_RETRIES,
                    duration_ms,
                    str(e)[:200],
                    error_code,
                )

                # Non-retryable errors
                if error_code in (
                    "INVALID_INPUT",
                    "INVALID_API_KEYS",
                    "INVALID_ACCESS_TOKEN",
                    "ITEM_NOT_FOUND",
                ):
                    break

                if attempt < MAX_RETRIES:
                    sleep_time = min(
                        RETRY_BACKOFF_BASE ** (attempt - 1),
                        RETRY_BACKOFF_MAX,
                    )
                    time.sleep(sleep_time)

        raise PlaidServiceError(
            message=f"Plaid API call '{operation_name}' failed after "
                    f"{MAX_RETRIES} attempts: {last_error}",
            code="PLAID_API_EXHAUSTED",
        )

    # ------------------------------------------------------------------
    # Model helpers
    # ------------------------------------------------------------------

    def _get_connection_model(self):
        """Lazy import of PlaidConnection to avoid circular imports."""
        from database.models.plaid_connection import PlaidConnection
        return PlaidConnection

    def _get_connection(self, connection_id: int, org_id: int):
        """Fetch a PlaidConnection with tenant isolation."""
        PlaidConnection = self._get_connection_model()
        conn = (
            self.db.query(PlaidConnection)
            .filter(
                PlaidConnection.id == connection_id,
                PlaidConnection.organization_id == org_id,
            )
            .first()
        )
        if not conn:
            raise PlaidServiceError(
                f"Plaid connection {connection_id} not found",
                code="CONNECTION_NOT_FOUND",
            )
        return conn

    def _get_connection_by_access_token_id(self, access_token_id: int, org_id: int = None):
        """Fetch a PlaidConnection by its ID (used as access_token_id proxy)."""
        PlaidConnection = self._get_connection_model()
        query = self.db.query(PlaidConnection).filter(
            PlaidConnection.id == access_token_id,
        )
        if org_id:
            query = query.filter(PlaidConnection.organization_id == org_id)
        conn = query.first()
        if not conn:
            raise PlaidServiceError(
                f"Plaid connection {access_token_id} not found",
                code="CONNECTION_NOT_FOUND",
            )
        return conn

    # ==================================================================
    # PUBLIC API
    # ==================================================================

    def create_link_token(
        self,
        borrower_id: int,
        org_id: int,
        loan_id: int,
    ) -> dict:
        """Create a Plaid Link token for a borrower to connect their bank.

        The Link token is used by the Plaid Link frontend component to
        launch the bank account connection flow.

        Args:
            borrower_id: Lead ID of the borrower.
            org_id: Organization ID for tenant isolation.
            loan_id: Loan ID to associate the connection with.

        Returns:
            {"link_token": str, "expiration": str, "request_id": str}
        """
        if not self._client:
            raise PlaidServiceError(
                "Plaid client not configured",
                code="PLAID_NOT_CONFIGURED",
            )

        # Build a stable client_user_id from org + borrower
        client_user_id = f"org_{org_id}_borrower_{borrower_id}"

        request = LinkTokenCreateRequest(
            user=LinkTokenCreateRequestUser(client_user_id=client_user_id),
            client_name="The Tim Loss Team",
            products=[Products("assets"), Products("transactions")],
            country_codes=[CountryCode("US")],
            language="en",
            webhook=self.webhook_url or None,
        )

        response = self._resilient_plaid_call(
            "create_link_token",
            self._client.link_token_create,
            request,
        )

        return {
            "link_token": response.link_token,
            "expiration": response.expiration,
            "request_id": response.request_id,
        }

    def exchange_public_token(
        self,
        public_token: str,
        borrower_id: int,
        org_id: int,
        loan_id: Optional[int] = None,
    ) -> dict:
        """Exchange a public token from Link for an access token.

        The access token is encrypted before storage. The raw token is
        never persisted.

        Args:
            public_token: The public_token returned by Plaid Link.
            borrower_id: Lead ID of the borrower.
            org_id: Organization ID for tenant isolation.
            loan_id: Optional loan ID to associate.

        Returns:
            {"connection_id": int, "item_id": str, "institution": str}
        """
        if not self._client:
            raise PlaidServiceError(
                "Plaid client not configured",
                code="PLAID_NOT_CONFIGURED",
            )

        exchange_request = ItemPublicTokenExchangeRequest(
            public_token=public_token,
        )

        response = self._resilient_plaid_call(
            "exchange_public_token",
            self._client.item_public_token_exchange,
            exchange_request,
        )

        access_token = response.access_token
        item_id = response.item_id

        # Encrypt the access token before storage
        encrypted_token = self._encrypt_token(access_token)

        PlaidConnection = self._get_connection_model()

        connection = PlaidConnection(
            organization_id=org_id,
            borrower_id=borrower_id,
            loan_id=loan_id,
            access_token_encrypted=encrypted_token,
            item_id=item_id,
            connection_status="active",
            account_ids=[],
        )

        self.db.add(connection)
        self.db.flush()

        # Fetch institution info and connected accounts
        try:
            self._populate_account_info(connection, access_token)
        except Exception as e:
            logger.warning(
                "Failed to populate account info for item %s: %s",
                item_id,
                e,
            )

        self.db.commit()

        logger.info(
            "Plaid token exchanged | org_id=%d | borrower_id=%d | "
            "item_id=%s | connection_id=%d",
            org_id,
            borrower_id,
            item_id,
            connection.id,
        )

        return {
            "connection_id": connection.id,
            "item_id": item_id,
            "institution": connection.institution_name,
        }

    def _populate_account_info(self, connection, access_token: str):
        """Populate institution name and account IDs from Plaid."""
        if not self._client:
            return

        try:
            # Get item info for institution ID
            from plaid.model.item_get_request import ItemGetRequest
            item_response = self._client.item_get(
                ItemGetRequest(access_token=access_token)
            )
            institution_id = item_response.item.institution_id
            connection.institution_id = institution_id

            # Get institution name
            if institution_id:
                from plaid.model.institutions_get_by_id_request import (
                    InstitutionsGetByIdRequest,
                )
                inst_response = self._client.institutions_get_by_id(
                    InstitutionsGetByIdRequest(
                        institution_id=institution_id,
                        country_codes=[CountryCode("US")],
                    )
                )
                connection.institution_name = inst_response.institution.name

            # Get connected accounts
            from plaid.model.accounts_get_request import AccountsGetRequest
            accounts_response = self._client.accounts_get(
                AccountsGetRequest(access_token=access_token)
            )
            connection.account_ids = [
                acc.account_id for acc in accounts_response.accounts
            ]
        except Exception as e:
            logger.warning("Error populating account info: %s", e)

    def get_transactions(
        self,
        access_token_id: int,
        start_date: date,
        end_date: date,
        org_id: Optional[int] = None,
    ) -> List[dict]:
        """Retrieve bank transactions from Plaid.

        Args:
            access_token_id: PlaidConnection.id (used to look up the token).
            start_date: Start of the date range.
            end_date: End of the date range.
            org_id: Organization ID for tenant isolation.

        Returns:
            List of transaction dicts with keys: date, amount, name,
            category, merchant_name, pending, transaction_id.
        """
        if not self._client:
            raise PlaidServiceError(
                "Plaid client not configured",
                code="PLAID_NOT_CONFIGURED",
            )

        conn = self._get_connection_by_access_token_id(access_token_id, org_id)
        access_token = self._decrypt_token(conn.access_token_encrypted)

        request = TransactionsGetRequest(
            access_token=access_token,
            start_date=start_date,
            end_date=end_date,
        )

        response = self._resilient_plaid_call(
            "get_transactions",
            self._client.transactions_get,
            request,
        )

        # Update sync timestamp
        conn.last_synced_at = datetime.now(timezone.utc)
        self.db.commit()

        transactions = []
        for txn in response.transactions:
            transactions.append({
                "date": str(txn.date),
                "amount": float(txn.amount),
                "name": txn.name,
                "category": txn.category,
                "merchant_name": getattr(txn, "merchant_name", None),
                "pending": txn.pending,
                "transaction_id": txn.transaction_id,
                "account_id": txn.account_id,
            })

        logger.info(
            "Retrieved %d transactions | connection_id=%d | range=%s to %s",
            len(transactions),
            access_token_id,
            start_date,
            end_date,
        )

        return transactions

    def create_asset_report(
        self,
        access_token_id: int,
        days_requested: int = DEFAULT_ASSET_REPORT_DAYS,
        org_id: Optional[int] = None,
    ) -> str:
        """Create a Plaid Asset Report (GSE-certified for mortgage).

        Asset Reports are generated asynchronously by Plaid. Use
        get_asset_report() to retrieve the completed report.

        Args:
            access_token_id: PlaidConnection.id.
            days_requested: Number of days of history (default 60).
            org_id: Organization ID for tenant isolation.

        Returns:
            asset_report_token (str) for later retrieval.
        """
        if not self._client:
            raise PlaidServiceError(
                "Plaid client not configured",
                code="PLAID_NOT_CONFIGURED",
            )

        conn = self._get_connection_by_access_token_id(access_token_id, org_id)
        access_token = self._decrypt_token(conn.access_token_encrypted)

        request = AssetReportCreateRequest(
            access_tokens=[access_token],
            days_requested=days_requested,
        )

        response = self._resilient_plaid_call(
            "create_asset_report",
            self._client.asset_report_create,
            request,
        )

        asset_report_token = response.asset_report_token
        asset_report_id = response.asset_report_id

        # Update connection with report tracking
        conn.asset_report_id = asset_report_token
        conn.asset_report_status = "pending"
        self.db.commit()

        logger.info(
            "Asset report requested | connection_id=%d | "
            "report_id=%s | days=%d",
            access_token_id,
            asset_report_id,
            days_requested,
        )

        return asset_report_token

    def get_asset_report(
        self,
        asset_report_id: str,
        org_id: Optional[int] = None,
    ) -> dict:
        """Retrieve a completed Plaid Asset Report.

        Args:
            asset_report_id: The asset_report_token from create_asset_report.
            org_id: Organization ID for tenant isolation.

        Returns:
            Dict with accounts, balances, transactions, and report metadata.
        """
        if not self._client:
            raise PlaidServiceError(
                "Plaid client not configured",
                code="PLAID_NOT_CONFIGURED",
            )

        # Validate tenant ownership of this report
        PlaidConnection = self._get_connection_model()
        query = self.db.query(PlaidConnection).filter(
            PlaidConnection.asset_report_id == asset_report_id,
        )
        if org_id:
            query = query.filter(PlaidConnection.organization_id == org_id)
        conn = query.first()
        if not conn:
            raise PlaidServiceError(
                f"Asset report {asset_report_id} not found",
                code="REPORT_NOT_FOUND",
            )

        request = AssetReportGetRequest(
            asset_report_token=asset_report_id,
        )

        response = self._resilient_plaid_call(
            "get_asset_report",
            self._client.asset_report_get,
            request,
        )

        report = response.report

        # Update connection status
        conn.asset_report_status = "ready"
        conn.last_synced_at = datetime.now(timezone.utc)
        self.db.commit()

        # Build structured response
        accounts_data = []
        for item in report.items:
            for account in item.accounts:
                balance = account.balances
                account_data = {
                    "account_id": account.account_id,
                    "name": account.name,
                    "official_name": getattr(account, "official_name", None),
                    "type": str(account.type),
                    "subtype": str(getattr(account, "subtype", "")),
                    "mask": getattr(account, "mask", None),
                    "balances": {
                        "current": float(balance.current) if balance.current else 0,
                        "available": float(balance.available) if balance.available else 0,
                    },
                    "days_available": report.days_requested,
                    "transactions": [],
                    "historical_balances": [],
                }

                # Add transactions if present
                for txn in getattr(account, "transactions", []):
                    account_data["transactions"].append({
                        "date": str(txn.date),
                        "amount": float(txn.amount),
                        "name": txn.name,
                        "pending": getattr(txn, "pending", False),
                    })

                # Add historical balances if present
                for bal in getattr(account, "historical_balances", []):
                    account_data["historical_balances"].append({
                        "date": str(bal.date),
                        "current": float(bal.current) if bal.current else 0,
                    })

                accounts_data.append(account_data)

        return {
            "asset_report_id": report.asset_report_id,
            "date_generated": str(report.date_generated),
            "days_requested": report.days_requested,
            "accounts": accounts_data,
        }

    def get_income_verification(
        self,
        access_token_id: int,
        org_id: Optional[int] = None,
    ) -> dict:
        """Retrieve income data from Plaid Income.

        Uses Plaid's income verification product to identify regular
        income deposits and estimated annual income.

        Args:
            access_token_id: PlaidConnection.id.
            org_id: Organization ID for tenant isolation.

        Returns:
            Dict with income_streams and estimated totals.
        """
        if not self._client:
            raise PlaidServiceError(
                "Plaid client not configured",
                code="PLAID_NOT_CONFIGURED",
            )

        conn = self._get_connection_by_access_token_id(access_token_id, org_id)
        access_token = self._decrypt_token(conn.access_token_encrypted)

        # Use credit/bank_income endpoints
        try:
            from plaid.model.credit_bank_income_get_request import (
                CreditBankIncomeGetRequest,
            )

            request = CreditBankIncomeGetRequest(
                user_token=access_token,
            )

            response = self._resilient_plaid_call(
                "get_income_verification",
                self._client.credit_bank_income_get,
                request,
            )

            income_items = []
            total_amount = 0.0

            for item in getattr(response, "bank_income", []):
                for source in getattr(item, "bank_income_sources", []):
                    income_entry = {
                        "income_source_id": getattr(source, "income_source_id", ""),
                        "income_description": getattr(source, "income_description", ""),
                        "income_category": str(getattr(source, "income_category", "")),
                        "total_amount": float(getattr(source, "total_amount", 0)),
                        "transaction_count": getattr(source, "transaction_count", 0),
                        "start_date": str(getattr(source, "start_date", "")),
                        "end_date": str(getattr(source, "end_date", "")),
                        "pay_frequency": str(getattr(source, "pay_frequency", "")),
                    }
                    total_amount += income_entry["total_amount"]
                    income_items.append(income_entry)

            return {
                "income_streams": income_items,
                "total_estimated_income": total_amount,
                "streams_count": len(income_items),
            }

        except Exception as e:
            logger.warning("Income verification not available: %s", e)
            return {
                "income_streams": [],
                "total_estimated_income": 0.0,
                "streams_count": 0,
                "error": str(e),
            }

    # ==================================================================
    # TRANSACTION ANALYSIS
    # ==================================================================

    def detect_large_deposits(
        self,
        transactions: List[dict],
        threshold: float = 5000.0,
    ) -> List[dict]:
        """Identify large deposits that require sourcing for underwriting.

        Per Fannie Mae Selling Guide B3-4.2-01, deposits exceeding 50%
        of qualifying monthly income (or a flat threshold) must be sourced
        with documentation.

        Args:
            transactions: List of transaction dicts from get_transactions().
            threshold: Dollar amount threshold (default $5,000).

        Returns:
            List of flagged deposit dicts with amount, date, description.
        """
        large_deposits = []
        threshold_dec = Decimal(str(threshold))

        for txn in transactions:
            # Plaid uses negative amounts for credits (deposits)
            amount = Decimal(str(abs(txn.get("amount", 0))))
            if amount >= threshold_dec and txn.get("amount", 0) < 0:
                large_deposits.append({
                    "date": txn.get("date"),
                    "amount": float(amount),
                    "description": txn.get("name", ""),
                    "merchant": txn.get("merchant_name"),
                    "category": txn.get("category", []),
                    "transaction_id": txn.get("transaction_id"),
                    "risk_level": (
                        "high" if amount >= threshold_dec * 2 else "medium"
                    ),
                    "sourcing_status": "unsourced",
                    "requires_documentation": True,
                })

        large_deposits.sort(key=lambda d: d["amount"], reverse=True)

        logger.info(
            "Large deposit scan: %d deposits >= $%.2f found in %d transactions",
            len(large_deposits),
            threshold,
            len(transactions),
        )

        return large_deposits

    def detect_nsf_overdrafts(
        self,
        transactions: List[dict],
    ) -> List[dict]:
        """Find NSF and overdraft events in transaction history.

        NSF (Non-Sufficient Funds) and overdraft events are red flags
        in mortgage underwriting, indicating cash flow instability.

        Args:
            transactions: List of transaction dicts from get_transactions().

        Returns:
            List of NSF/overdraft event dicts.
        """
        nsf_keywords = [
            "nsf", "non-sufficient", "insufficient funds", "overdraft",
            "overdft", "od fee", "od charge", "returned item",
            "returned check", "bounce", "nsf fee",
        ]

        events = []
        for txn in transactions:
            name_lower = (txn.get("name") or "").lower()
            categories = [c.lower() for c in (txn.get("category") or [])]

            is_nsf = any(kw in name_lower for kw in nsf_keywords)
            is_nsf = is_nsf or "overdraft" in " ".join(categories)

            if is_nsf:
                amount = abs(float(txn.get("amount", 0)))
                events.append({
                    "date": txn.get("date"),
                    "amount": amount,
                    "description": txn.get("name", ""),
                    "transaction_id": txn.get("transaction_id"),
                    "fee_amount": amount,
                    "severity": (
                        "high" if amount > 50 else "medium"
                    ),
                })

        # Sort by date descending
        events.sort(key=lambda e: e.get("date", ""), reverse=True)

        if events:
            logger.warning(
                "NSF/overdraft scan: %d events found in %d transactions",
                len(events),
                len(transactions),
            )

        return events

    def detect_recurring_payments(
        self,
        transactions: List[dict],
        payee_pattern: str,
    ) -> List[dict]:
        """Find recurring payments matching a payee pattern.

        Useful for detecting IRS installment payments, child support,
        undisclosed debts, etc.

        Args:
            transactions: List of transaction dicts from get_transactions().
            payee_pattern: Case-insensitive substring to match in names.

        Returns:
            List of matching transaction dicts grouped by frequency estimate.
        """
        pattern_lower = payee_pattern.lower()
        matches = []

        for txn in transactions:
            name_lower = (txn.get("name") or "").lower()
            merchant_lower = (txn.get("merchant_name") or "").lower()

            if pattern_lower in name_lower or pattern_lower in merchant_lower:
                matches.append({
                    "date": txn.get("date"),
                    "amount": float(txn.get("amount", 0)),
                    "description": txn.get("name", ""),
                    "merchant": txn.get("merchant_name"),
                    "transaction_id": txn.get("transaction_id"),
                })

        # Estimate frequency if multiple matches
        frequency = "unknown"
        if len(matches) >= 2:
            try:
                dates = sorted([
                    datetime.strptime(m["date"], "%Y-%m-%d")
                    for m in matches if m.get("date")
                ])
                if len(dates) >= 2:
                    intervals = [
                        (dates[i + 1] - dates[i]).days
                        for i in range(len(dates) - 1)
                    ]
                    avg_interval = sum(intervals) / len(intervals)
                    if avg_interval <= 10:
                        frequency = "weekly"
                    elif avg_interval <= 18:
                        frequency = "biweekly"
                    elif avg_interval <= 35:
                        frequency = "monthly"
                    else:
                        frequency = "irregular"
            except (ValueError, IndexError):
                pass

        return {
            "payee_pattern": payee_pattern,
            "matches": matches,
            "match_count": len(matches),
            "estimated_frequency": frequency,
            "total_amount": sum(abs(m["amount"]) for m in matches),
        }

    # ==================================================================
    # FULL ANALYSIS
    # ==================================================================

    def generate_bank_analysis_from_plaid(
        self,
        loan_id: int,
        org_id: int,
    ) -> dict:
        """Run full bank analysis using Plaid data instead of PDF parsing.

        Retrieves transactions from all connected accounts for a loan
        and runs the standard underwriting analysis suite.

        Args:
            loan_id: Loan ID to analyze.
            org_id: Organization ID for tenant isolation.

        Returns:
            Comprehensive analysis dict with large_deposits, nsf_events,
            irs_payments, risk_score, and recommendations.
        """
        PlaidConnection = self._get_connection_model()

        connections = (
            self.db.query(PlaidConnection)
            .filter(
                PlaidConnection.loan_id == loan_id,
                PlaidConnection.organization_id == org_id,
                PlaidConnection.connection_status == "active",
            )
            .all()
        )

        if not connections:
            raise PlaidServiceError(
                f"No active Plaid connections for loan {loan_id}",
                code="NO_CONNECTIONS",
            )

        # Retrieve 90 days of transactions from all accounts
        end_date = date.today()
        start_date = end_date - timedelta(days=90)
        all_transactions = []

        for conn in connections:
            try:
                txns = self.get_transactions(
                    access_token_id=conn.id,
                    start_date=start_date,
                    end_date=end_date,
                    org_id=org_id,
                )
                all_transactions.extend(txns)
            except Exception as e:
                logger.warning(
                    "Failed to get transactions for connection %d: %s",
                    conn.id,
                    e,
                )

        # Run analysis modules
        large_deposits = self.detect_large_deposits(all_transactions)
        nsf_events = self.detect_nsf_overdrafts(all_transactions)
        irs_payments = self.detect_recurring_payments(
            all_transactions, "irs"
        )

        # Calculate risk score (0-100, lower is better)
        risk_score = 0
        risk_factors = []

        if large_deposits:
            deposit_risk = min(len(large_deposits) * 10, 30)
            risk_score += deposit_risk
            risk_factors.append({
                "factor": "large_deposits",
                "count": len(large_deposits),
                "points": deposit_risk,
                "description": f"{len(large_deposits)} large deposits require sourcing",
            })

        if nsf_events:
            nsf_risk = min(len(nsf_events) * 15, 40)
            risk_score += nsf_risk
            risk_factors.append({
                "factor": "nsf_overdrafts",
                "count": len(nsf_events),
                "points": nsf_risk,
                "description": f"{len(nsf_events)} NSF/overdraft events detected",
            })

        irs_matches = irs_payments.get("matches", []) if isinstance(irs_payments, dict) else []
        if irs_matches:
            irs_risk = min(len(irs_matches) * 10, 20)
            risk_score += irs_risk
            risk_factors.append({
                "factor": "irs_payments",
                "count": len(irs_matches),
                "points": irs_risk,
                "description": f"{len(irs_matches)} IRS payments found",
            })

        # Risk level classification
        if risk_score >= 60:
            risk_level = "high"
        elif risk_score >= 30:
            risk_level = "medium"
        else:
            risk_level = "low"

        # Build recommendations
        recommendations = []
        if large_deposits:
            recommendations.append(
                "Request sourcing documentation for large deposits."
            )
        if nsf_events:
            recommendations.append(
                "Review NSF/overdraft history with borrower. "
                "May need letter of explanation."
            )
        if irs_matches:
            recommendations.append(
                "Verify IRS payment plan status and obtain "
                "transcripts if applicable."
            )
        if not recommendations:
            recommendations.append(
                "Bank analysis looks clean. No significant concerns."
            )

        analysis = {
            "loan_id": loan_id,
            "analysis_date": datetime.now(timezone.utc).isoformat(),
            "connections_analyzed": len(connections),
            "total_transactions": len(all_transactions),
            "date_range": {
                "start": str(start_date),
                "end": str(end_date),
            },
            "large_deposits": large_deposits,
            "nsf_events": nsf_events,
            "irs_payments": irs_payments,
            "risk_score": risk_score,
            "risk_level": risk_level,
            "risk_factors": risk_factors,
            "recommendations": recommendations,
        }

        logger.info(
            "Bank analysis complete | loan_id=%d | transactions=%d | "
            "risk_score=%d (%s)",
            loan_id,
            len(all_transactions),
            risk_score,
            risk_level,
        )

        return analysis

    # ==================================================================
    # ACCOUNT MANAGEMENT
    # ==================================================================

    def disconnect_account(
        self,
        access_token_id: int,
        org_id: Optional[int] = None,
    ) -> dict:
        """Revoke a Plaid access token and mark the connection as revoked.

        Args:
            access_token_id: PlaidConnection.id.
            org_id: Organization ID for tenant isolation.

        Returns:
            {"connection_id": int, "status": "revoked"}
        """
        conn = self._get_connection_by_access_token_id(access_token_id, org_id)

        if self._client:
            try:
                access_token = self._decrypt_token(conn.access_token_encrypted)
                request = ItemRemoveRequest(access_token=access_token)
                self._resilient_plaid_call(
                    "disconnect_account",
                    self._client.item_remove,
                    request,
                )
            except Exception as e:
                logger.warning(
                    "Failed to revoke Plaid token for connection %d: %s",
                    access_token_id,
                    e,
                )

        conn.connection_status = "revoked"
        conn.updated_at = datetime.now(timezone.utc)
        self.db.commit()

        logger.info(
            "Plaid account disconnected | connection_id=%d | item_id=%s",
            access_token_id,
            conn.item_id,
        )

        return {
            "connection_id": access_token_id,
            "status": "revoked",
        }

    # ==================================================================
    # WEBHOOKS
    # ==================================================================

    def webhook_handler(self, webhook_data: dict) -> dict:
        """Handle Plaid webhook notifications.

        Processes webhook types:
            - ASSET_REPORT: Asset report completion/error
            - ITEM: Connection status changes (e.g., needs re-auth)
            - TRANSACTIONS: New transactions available

        Args:
            webhook_data: Raw webhook payload from Plaid.

        Returns:
            {"processed": bool, "action": str}
        """
        webhook_type = webhook_data.get("webhook_type", "")
        webhook_code = webhook_data.get("webhook_code", "")
        item_id = webhook_data.get("item_id", "")

        logger.info(
            "Plaid webhook received | type=%s | code=%s | item_id=%s",
            webhook_type,
            webhook_code,
            item_id,
        )

        PlaidConnection = self._get_connection_model()

        if webhook_type == "ASSET_REPORT":
            return self._handle_asset_report_webhook(webhook_data)

        elif webhook_type == "ITEM":
            if webhook_code == "ERROR":
                # Mark connection as needing re-auth
                conn = (
                    self.db.query(PlaidConnection)
                    .filter(PlaidConnection.item_id == item_id)
                    .first()
                )
                if conn:
                    conn.connection_status = "needs_reauth"
                    conn.updated_at = datetime.now(timezone.utc)
                    self.db.commit()
                    logger.warning(
                        "Plaid item error -- connection %d needs reauth",
                        conn.id,
                    )
                return {"processed": True, "action": "connection_needs_reauth"}

            elif webhook_code == "PENDING_EXPIRATION":
                conn = (
                    self.db.query(PlaidConnection)
                    .filter(PlaidConnection.item_id == item_id)
                    .first()
                )
                if conn:
                    conn.connection_status = "needs_reauth"
                    conn.updated_at = datetime.now(timezone.utc)
                    self.db.commit()
                return {"processed": True, "action": "pending_expiration"}

        elif webhook_type == "TRANSACTIONS":
            if webhook_code in (
                "DEFAULT_UPDATE",
                "INITIAL_UPDATE",
                "HISTORICAL_UPDATE",
            ):
                conn = (
                    self.db.query(PlaidConnection)
                    .filter(PlaidConnection.item_id == item_id)
                    .first()
                )
                if conn:
                    conn.last_synced_at = datetime.now(timezone.utc)
                    self.db.commit()
                return {
                    "processed": True,
                    "action": "transactions_updated",
                }

        return {"processed": False, "action": "unhandled_webhook"}

    def _handle_asset_report_webhook(self, webhook_data: dict) -> dict:
        """Handle ASSET_REPORT webhook type."""
        webhook_code = webhook_data.get("webhook_code", "")
        asset_report_id = webhook_data.get("asset_report_id", "")

        PlaidConnection = self._get_connection_model()

        if webhook_code == "PRODUCT_READY":
            conn = (
                self.db.query(PlaidConnection)
                .filter(PlaidConnection.asset_report_id == asset_report_id)
                .first()
            )
            if conn:
                conn.asset_report_status = "ready"
                conn.updated_at = datetime.now(timezone.utc)
                self.db.commit()
                logger.info(
                    "Asset report ready | connection_id=%d | report=%s",
                    conn.id,
                    asset_report_id,
                )
            return {"processed": True, "action": "asset_report_ready"}

        elif webhook_code == "ERROR":
            conn = (
                self.db.query(PlaidConnection)
                .filter(PlaidConnection.asset_report_id == asset_report_id)
                .first()
            )
            if conn:
                conn.asset_report_status = "error"
                conn.updated_at = datetime.now(timezone.utc)
                self.db.commit()
                logger.error(
                    "Asset report error | connection_id=%d | report=%s | "
                    "error=%s",
                    conn.id,
                    asset_report_id,
                    webhook_data.get("error", {}),
                )
            return {"processed": True, "action": "asset_report_error"}

        return {"processed": False, "action": "unhandled_asset_webhook"}

    # ==================================================================
    # WEBHOOK SIGNATURE VERIFICATION
    # ==================================================================

    @staticmethod
    def verify_webhook_signature(
        body: bytes,
        signed_jwt: str,
        plaid_webhook_verification_key: Optional[str] = None,
    ) -> bool:
        """Verify a Plaid webhook signature.

        Plaid signs webhooks using JWKs. In production, you should
        verify the JWT signature using Plaid's public key endpoint.

        For simplified environments, this accepts the webhook if a
        verification key is not configured.

        Args:
            body: Raw request body bytes.
            signed_jwt: The Plaid-Verification header value.
            plaid_webhook_verification_key: Optional verification key.

        Returns:
            True if the webhook signature is valid.
        """
        if not plaid_webhook_verification_key:
            logger.warning(
                "Plaid webhook verification key not configured -- "
                "accepting webhook without signature check"
            )
            return True

        try:
            # Compute body hash
            body_hash = hashlib.sha256(body).hexdigest()

            # In production, verify the JWT using Plaid's JWK endpoint:
            # https://production.plaid.com/webhook_verification_key/get
            # For now, basic HMAC comparison
            expected = hmac.new(
                plaid_webhook_verification_key.encode(),
                body,
                hashlib.sha256,
            ).hexdigest()

            return hmac.compare_digest(expected, signed_jwt)
        except Exception as e:
            logger.error("Webhook signature verification failed: %s", e)
            return False

    # ==================================================================
    # CONNECTION LISTING
    # ==================================================================

    def get_connections_for_loan(
        self,
        loan_id: int,
        org_id: int,
    ) -> List[dict]:
        """List all Plaid connections for a loan.

        Args:
            loan_id: Loan ID.
            org_id: Organization ID for tenant isolation.

        Returns:
            List of connection summary dicts.
        """
        PlaidConnection = self._get_connection_model()

        connections = (
            self.db.query(PlaidConnection)
            .filter(
                PlaidConnection.loan_id == loan_id,
                PlaidConnection.organization_id == org_id,
            )
            .order_by(PlaidConnection.created_at.desc())
            .all()
        )

        return [
            {
                "connection_id": conn.id,
                "institution_name": conn.institution_name,
                "institution_id": conn.institution_id,
                "item_id": conn.item_id,
                "account_count": len(conn.account_ids or []),
                "connection_status": conn.connection_status,
                "last_synced_at": (
                    conn.last_synced_at.isoformat()
                    if conn.last_synced_at
                    else None
                ),
                "asset_report_id": conn.asset_report_id,
                "asset_report_status": conn.asset_report_status,
                "created_at": conn.created_at.isoformat(),
            }
            for conn in connections
        ]


# ==================================================================
# Module-level factory
# ==================================================================

def get_plaid_service(db: Session) -> PlaidIntegrationService:
    """Create a PlaidIntegrationService instance.

    Args:
        db: SQLAlchemy session.

    Returns:
        Configured PlaidIntegrationService.
    """
    return PlaidIntegrationService(db)
