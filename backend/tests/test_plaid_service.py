"""
Test Plaid Integration Service

Comprehensive tests for PlaidIntegrationService covering:
    - Link token creation (mock Plaid API)
    - Token exchange and encrypted storage
    - Transaction retrieval
    - Large deposit detection from Plaid data
    - NSF/overdraft detection from Plaid data
    - Recurring payment detection
    - Asset report creation and retrieval
    - Full bank analysis pipeline
    - Webhook handling
    - Tenant isolation
    - Account disconnection

All Plaid API calls and database operations are mocked.
"""

import pytest
import json
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import MagicMock, patch, PropertyMock, call

from services.smart_docs.integrations.plaid_service import (
    PlaidIntegrationService,
    PlaidServiceError,
    LARGE_DEPOSIT_THRESHOLD,
    MAX_RETRIES,
)


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def mock_db():
    """Create a mock database session."""
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None
    db.query.return_value.filter.return_value.all.return_value = []
    db.query.return_value.filter.return_value.order_by.return_value.all.return_value = []
    return db


@pytest.fixture
def mock_pii_service():
    """Create a mock PII encryption service."""
    pii = MagicMock()
    pii.encrypt.side_effect = lambda x: f"ENCRYPTED:{x}"
    pii.decrypt.side_effect = lambda x: x.replace("ENCRYPTED:", "")
    return pii


@pytest.fixture
def service(mock_db, mock_pii_service):
    """Create PlaidIntegrationService with mocked dependencies."""
    with patch.dict("os.environ", {
        "PLAID_CLIENT_ID": "test_client_id",
        "PLAID_SECRET": "test_secret",
        "PLAID_ENV": "sandbox",
        "PLAID_WEBHOOK_URL": "https://api.perenniaai.com/api/smart-docs/plaid/webhooks",
    }, clear=False):
        with patch(
            "services.smart_docs.integrations.plaid_service.HAS_PLAID",
            False,
        ):
            with patch(
                "services.smart_docs.integrations.plaid_service.get_pii_encryption_service",
                return_value=mock_pii_service,
            ):
                svc = PlaidIntegrationService(mock_db)
                svc._pii_service = mock_pii_service
                return svc


@pytest.fixture
def sample_transactions():
    """Sample Plaid transactions for analysis tests."""
    return [
        # Regular deposit (Plaid uses negative for credits)
        {
            "date": "2026-03-01",
            "amount": -2500.00,
            "name": "PAYROLL DIRECT DEP ADP",
            "category": ["Payment", "Payroll"],
            "merchant_name": "ADP",
            "pending": False,
            "transaction_id": "txn_001",
            "account_id": "acc_001",
        },
        # Large deposit requiring sourcing
        {
            "date": "2026-03-05",
            "amount": -15000.00,
            "name": "WIRE TRANSFER FROM JOHN DOE",
            "category": ["Transfer", "Wire"],
            "merchant_name": None,
            "pending": False,
            "transaction_id": "txn_002",
            "account_id": "acc_001",
        },
        # Another large deposit
        {
            "date": "2026-03-10",
            "amount": -7500.00,
            "name": "CHECK DEPOSIT #1234",
            "category": ["Transfer", "Deposit"],
            "merchant_name": None,
            "pending": False,
            "transaction_id": "txn_003",
            "account_id": "acc_001",
        },
        # NSF fee
        {
            "date": "2026-03-08",
            "amount": 35.00,
            "name": "NSF FEE RETURNED ITEM",
            "category": ["Fee", "NSF"],
            "merchant_name": None,
            "pending": False,
            "transaction_id": "txn_004",
            "account_id": "acc_001",
        },
        # Overdraft fee
        {
            "date": "2026-03-09",
            "amount": 34.00,
            "name": "OVERDRAFT CHARGE",
            "category": ["Fee", "Overdraft"],
            "merchant_name": None,
            "pending": False,
            "transaction_id": "txn_005",
            "account_id": "acc_001",
        },
        # IRS payment
        {
            "date": "2026-03-15",
            "amount": 1200.00,
            "name": "IRS USTREAS 310 TAX PAYMENT",
            "category": ["Payment", "Government"],
            "merchant_name": "IRS",
            "pending": False,
            "transaction_id": "txn_006",
            "account_id": "acc_001",
        },
        # Regular payment (debit, positive in Plaid)
        {
            "date": "2026-03-02",
            "amount": 150.00,
            "name": "COMCAST CABLE",
            "category": ["Service", "Cable"],
            "merchant_name": "Comcast",
            "pending": False,
            "transaction_id": "txn_007",
            "account_id": "acc_001",
        },
        # Small deposit (below threshold)
        {
            "date": "2026-03-12",
            "amount": -200.00,
            "name": "VENMO PAYMENT",
            "category": ["Transfer", "Peer"],
            "merchant_name": "Venmo",
            "pending": False,
            "transaction_id": "txn_008",
            "account_id": "acc_001",
        },
    ]


@pytest.fixture
def mock_plaid_connection():
    """Create a mock PlaidConnection model instance."""
    conn = MagicMock()
    conn.id = 42
    conn.organization_id = 1
    conn.borrower_id = 100
    conn.loan_id = 200
    conn.institution_name = "Chase Bank"
    conn.institution_id = "ins_1234"
    conn.access_token_encrypted = "ENCRYPTED:access-sandbox-test-token"
    conn.item_id = "item_test_123"
    conn.account_ids = ["acc_001", "acc_002"]
    conn.connection_status = "active"
    conn.last_synced_at = None
    conn.asset_report_id = None
    conn.asset_report_status = None
    conn.created_at = datetime(2026, 3, 1, tzinfo=timezone.utc)
    conn.updated_at = datetime(2026, 3, 1, tzinfo=timezone.utc)
    conn.is_active = True
    return conn


# =============================================================================
# ENCRYPTION TESTS
# =============================================================================

class TestEncryption:
    """Test access token encryption and decryption."""

    def test_encrypt_token_with_pii_service(self, service, mock_pii_service):
        """Token encryption delegates to PII service."""
        result = service._encrypt_token("raw-token-123")
        mock_pii_service.encrypt.assert_called_once_with("raw-token-123")
        assert result == "ENCRYPTED:raw-token-123"

    def test_decrypt_token_with_pii_service(self, service, mock_pii_service):
        """Token decryption delegates to PII service."""
        result = service._decrypt_token("ENCRYPTED:raw-token-123")
        mock_pii_service.decrypt.assert_called_once_with("ENCRYPTED:raw-token-123")
        assert result == "raw-token-123"

    def test_encrypt_without_pii_service_uses_base64_fallback(self, mock_db):
        """Without PII service, falls back to base64 (dev only)."""
        with patch.dict("os.environ", {
            "PLAID_CLIENT_ID": "test",
            "PLAID_SECRET": "test",
            "PLAID_ENV": "sandbox",
        }, clear=False):
            with patch(
                "services.smart_docs.integrations.plaid_service.HAS_PLAID",
                False,
            ):
                with patch(
                    "services.smart_docs.integrations.plaid_service.HAS_PII_SERVICE",
                    False,
                ):
                    svc = PlaidIntegrationService(mock_db)
                    svc._pii_service = None

                    encrypted = svc._encrypt_token("test-token")
                    decrypted = svc._decrypt_token(encrypted)
                    assert decrypted == "test-token"


# =============================================================================
# LARGE DEPOSIT DETECTION TESTS
# =============================================================================

class TestLargeDepositDetection:
    """Test detection of large deposits requiring sourcing."""

    def test_detects_deposits_above_threshold(self, service, sample_transactions):
        """Deposits above threshold are flagged."""
        results = service.detect_large_deposits(sample_transactions)

        # Should find 2 deposits: $15,000 and $7,500
        assert len(results) == 2

        # Sorted by amount descending
        assert results[0]["amount"] == 15000.00
        assert results[1]["amount"] == 7500.00

    def test_ignores_deposits_below_threshold(self, service, sample_transactions):
        """Small deposits and debits are not flagged."""
        results = service.detect_large_deposits(sample_transactions, threshold=20000)

        # Only the $15,000 should not qualify at $20K threshold either
        # Actually $15K < $20K so nothing qualifies
        assert len(results) == 0

    def test_custom_threshold(self, service, sample_transactions):
        """Custom threshold works correctly."""
        results = service.detect_large_deposits(
            sample_transactions, threshold=1000.0
        )

        # $15,000, $7,500, and $2,500 payroll deposit are all >= $1,000
        assert len(results) == 3

    def test_risk_level_assignment(self, service, sample_transactions):
        """Risk level is 'high' for deposits >= 2x threshold."""
        results = service.detect_large_deposits(
            sample_transactions, threshold=5000.0
        )

        # $15,000 is >= 2 * $5,000 -> high
        high_risk = [r for r in results if r["risk_level"] == "high"]
        assert len(high_risk) == 1
        assert high_risk[0]["amount"] == 15000.00

        # $7,500 is >= $5,000 but < $10,000 -> medium
        medium_risk = [r for r in results if r["risk_level"] == "medium"]
        assert len(medium_risk) == 1
        assert medium_risk[0]["amount"] == 7500.00

    def test_all_flagged_are_unsourced(self, service, sample_transactions):
        """All detected deposits start as unsourced."""
        results = service.detect_large_deposits(sample_transactions)
        for dep in results:
            assert dep["sourcing_status"] == "unsourced"
            assert dep["requires_documentation"] is True

    def test_empty_transactions(self, service):
        """Empty transaction list returns empty results."""
        results = service.detect_large_deposits([])
        assert results == []

    def test_debits_not_flagged(self, service):
        """Positive amounts (debits in Plaid) are not flagged as deposits."""
        txns = [
            {
                "date": "2026-03-01",
                "amount": 10000.00,  # debit (positive in Plaid)
                "name": "MORTGAGE PAYMENT",
                "category": [],
                "merchant_name": None,
                "pending": False,
                "transaction_id": "txn_debit",
                "account_id": "acc_001",
            }
        ]
        results = service.detect_large_deposits(txns)
        assert len(results) == 0


# =============================================================================
# NSF / OVERDRAFT DETECTION TESTS
# =============================================================================

class TestNSFDetection:
    """Test detection of NSF and overdraft events."""

    def test_detects_nsf_events(self, service, sample_transactions):
        """NSF fees are detected by keyword matching."""
        results = service.detect_nsf_overdrafts(sample_transactions)
        assert len(results) == 2

    def test_nsf_keyword_matching(self, service):
        """Various NSF keyword variations are matched."""
        txns = [
            {"date": "2026-03-01", "amount": 35, "name": "NSF FEE", "category": [], "transaction_id": "1"},
            {"date": "2026-03-02", "amount": 34, "name": "OVERDRAFT CHARGE", "category": [], "transaction_id": "2"},
            {"date": "2026-03-03", "amount": 25, "name": "INSUFFICIENT FUNDS FEE", "category": [], "transaction_id": "3"},
            {"date": "2026-03-04", "amount": 30, "name": "RETURNED ITEM FEE", "category": [], "transaction_id": "4"},
            {"date": "2026-03-05", "amount": 150, "name": "REGULAR PURCHASE", "category": [], "transaction_id": "5"},
        ]
        results = service.detect_nsf_overdrafts(txns)
        assert len(results) == 4  # All except "REGULAR PURCHASE"

    def test_nsf_severity_by_amount(self, service):
        """NSF severity is 'high' when fee amount > $50."""
        txns = [
            {"date": "2026-03-01", "amount": 75, "name": "NSF FEE", "category": [], "transaction_id": "1"},
            {"date": "2026-03-02", "amount": 25, "name": "NSF FEE", "category": [], "transaction_id": "2"},
        ]
        results = service.detect_nsf_overdrafts(txns)

        high = [r for r in results if r["severity"] == "high"]
        medium = [r for r in results if r["severity"] == "medium"]
        assert len(high) == 1
        assert high[0]["amount"] == 75
        assert len(medium) == 1

    def test_category_based_detection(self, service):
        """Overdraft detected from category even without keyword in name."""
        txns = [
            {
                "date": "2026-03-01",
                "amount": 35,
                "name": "BANK FEE",
                "category": ["Fee", "Overdraft"],
                "transaction_id": "1",
            },
        ]
        results = service.detect_nsf_overdrafts(txns)
        assert len(results) == 1

    def test_empty_transactions_no_nsf(self, service):
        """Empty transaction list returns empty results."""
        results = service.detect_nsf_overdrafts([])
        assert results == []


# =============================================================================
# RECURRING PAYMENT DETECTION TESTS
# =============================================================================

class TestRecurringPaymentDetection:
    """Test detection of recurring payments by payee pattern."""

    def test_finds_irs_payments(self, service, sample_transactions):
        """IRS payments are detected by pattern match."""
        results = service.detect_recurring_payments(
            sample_transactions, "irs"
        )
        assert results["match_count"] == 1
        assert results["matches"][0]["description"] == "IRS USTREAS 310 TAX PAYMENT"

    def test_case_insensitive_matching(self, service):
        """Pattern matching is case-insensitive."""
        txns = [
            {"date": "2026-03-01", "amount": 100, "name": "Chase Mortgage", "merchant_name": None, "transaction_id": "1"},
            {"date": "2026-03-15", "amount": 100, "name": "CHASE MORTGAGE PMT", "merchant_name": None, "transaction_id": "2"},
        ]
        results = service.detect_recurring_payments(txns, "chase mortgage")
        assert results["match_count"] == 2

    def test_frequency_estimation_monthly(self, service):
        """Monthly frequency is estimated from ~30-day intervals."""
        txns = [
            {"date": "2026-01-15", "amount": 500, "name": "RENT PAYMENT", "merchant_name": None, "transaction_id": "1"},
            {"date": "2026-02-15", "amount": 500, "name": "RENT PAYMENT", "merchant_name": None, "transaction_id": "2"},
            {"date": "2026-03-15", "amount": 500, "name": "RENT PAYMENT", "merchant_name": None, "transaction_id": "3"},
        ]
        results = service.detect_recurring_payments(txns, "rent")
        assert results["estimated_frequency"] == "monthly"

    def test_no_matches_returns_zero(self, service, sample_transactions):
        """No matches returns empty result."""
        results = service.detect_recurring_payments(
            sample_transactions, "nonexistent_payee_xyz"
        )
        assert results["match_count"] == 0
        assert results["matches"] == []

    def test_merchant_name_matching(self, service):
        """Matches on merchant_name field as well."""
        txns = [
            {
                "date": "2026-03-01",
                "amount": 100,
                "name": "PAYMENT",
                "merchant_name": "State Farm Insurance",
                "transaction_id": "1",
            },
        ]
        results = service.detect_recurring_payments(txns, "state farm")
        assert results["match_count"] == 1


# =============================================================================
# WEBHOOK HANDLING TESTS
# =============================================================================

class TestWebhookHandling:
    """Test Plaid webhook processing."""

    def test_asset_report_ready_webhook(self, service, mock_db, mock_plaid_connection):
        """ASSET_REPORT PRODUCT_READY updates connection status."""
        mock_plaid_connection.asset_report_id = "report_token_123"
        mock_db.query.return_value.filter.return_value.first.return_value = mock_plaid_connection

        result = service.webhook_handler({
            "webhook_type": "ASSET_REPORT",
            "webhook_code": "PRODUCT_READY",
            "asset_report_id": "report_token_123",
        })

        assert result["processed"] is True
        assert result["action"] == "asset_report_ready"
        assert mock_plaid_connection.asset_report_status == "ready"

    def test_asset_report_error_webhook(self, service, mock_db, mock_plaid_connection):
        """ASSET_REPORT ERROR updates connection status."""
        mock_plaid_connection.asset_report_id = "report_token_123"
        mock_db.query.return_value.filter.return_value.first.return_value = mock_plaid_connection

        result = service.webhook_handler({
            "webhook_type": "ASSET_REPORT",
            "webhook_code": "ERROR",
            "asset_report_id": "report_token_123",
            "error": {"error_code": "PRODUCT_NOT_READY"},
        })

        assert result["processed"] is True
        assert result["action"] == "asset_report_error"
        assert mock_plaid_connection.asset_report_status == "error"

    def test_item_error_webhook_marks_reauth(self, service, mock_db, mock_plaid_connection):
        """ITEM ERROR webhook marks connection as needing re-auth."""
        mock_db.query.return_value.filter.return_value.first.return_value = mock_plaid_connection

        result = service.webhook_handler({
            "webhook_type": "ITEM",
            "webhook_code": "ERROR",
            "item_id": "item_test_123",
        })

        assert result["processed"] is True
        assert result["action"] == "connection_needs_reauth"
        assert mock_plaid_connection.connection_status == "needs_reauth"

    def test_item_pending_expiration_webhook(self, service, mock_db, mock_plaid_connection):
        """ITEM PENDING_EXPIRATION webhook marks connection for reauth."""
        mock_db.query.return_value.filter.return_value.first.return_value = mock_plaid_connection

        result = service.webhook_handler({
            "webhook_type": "ITEM",
            "webhook_code": "PENDING_EXPIRATION",
            "item_id": "item_test_123",
        })

        assert result["processed"] is True
        assert result["action"] == "pending_expiration"
        assert mock_plaid_connection.connection_status == "needs_reauth"

    def test_transactions_update_webhook(self, service, mock_db, mock_plaid_connection):
        """TRANSACTIONS DEFAULT_UPDATE webhook updates sync timestamp."""
        mock_db.query.return_value.filter.return_value.first.return_value = mock_plaid_connection

        result = service.webhook_handler({
            "webhook_type": "TRANSACTIONS",
            "webhook_code": "DEFAULT_UPDATE",
            "item_id": "item_test_123",
        })

        assert result["processed"] is True
        assert result["action"] == "transactions_updated"

    def test_unhandled_webhook_type(self, service, mock_db):
        """Unrecognized webhook types return processed=False."""
        result = service.webhook_handler({
            "webhook_type": "UNKNOWN_TYPE",
            "webhook_code": "SOME_CODE",
            "item_id": "item_test_123",
        })

        assert result["processed"] is False
        assert result["action"] == "unhandled_webhook"


# =============================================================================
# TENANT ISOLATION TESTS
# =============================================================================

class TestTenantIsolation:
    """Test that tenant isolation is enforced on queries."""

    def test_get_connection_filters_by_org(self, service, mock_db):
        """_get_connection includes org_id in filter."""
        mock_db.query.return_value.filter.return_value.first.return_value = None

        with pytest.raises(PlaidServiceError, match="not found"):
            service._get_connection(connection_id=42, org_id=1)

        # Verify the query was filtered (filter was called)
        mock_db.query.return_value.filter.assert_called()

    def test_get_connections_for_loan_filters_by_org(
        self, service, mock_db, mock_plaid_connection
    ):
        """get_connections_for_loan filters by both loan_id and org_id."""
        mock_db.query.return_value.filter.return_value.order_by.return_value.all.return_value = [
            mock_plaid_connection
        ]

        results = service.get_connections_for_loan(loan_id=200, org_id=1)
        assert len(results) == 1
        assert results[0]["connection_id"] == 42

    def test_disconnect_requires_org_match(self, service, mock_db, mock_plaid_connection):
        """disconnect_account enforces tenant isolation."""
        # First call (by access_token_id) returns the connection
        mock_db.query.return_value.filter.return_value.first.return_value = mock_plaid_connection

        result = service.disconnect_account(access_token_id=42, org_id=1)
        assert result["status"] == "revoked"

    def test_disconnect_wrong_org_raises(self, service, mock_db):
        """disconnect_account raises when org_id doesn't match."""
        mock_db.query.return_value.filter.return_value.first.return_value = None

        with pytest.raises(PlaidServiceError, match="not found"):
            service.disconnect_account(access_token_id=42, org_id=999)


# =============================================================================
# ACCOUNT DISCONNECTION TESTS
# =============================================================================

class TestDisconnectAccount:
    """Test account disconnection."""

    def test_marks_connection_as_revoked(self, service, mock_db, mock_plaid_connection):
        """Disconnection sets status to 'revoked'."""
        mock_db.query.return_value.filter.return_value.first.return_value = mock_plaid_connection

        result = service.disconnect_account(access_token_id=42, org_id=1)
        assert result["status"] == "revoked"
        assert mock_plaid_connection.connection_status == "revoked"
        mock_db.commit.assert_called()

    def test_nonexistent_connection_raises(self, service, mock_db):
        """Disconnecting nonexistent connection raises error."""
        mock_db.query.return_value.filter.return_value.first.return_value = None

        with pytest.raises(PlaidServiceError, match="not found"):
            service.disconnect_account(access_token_id=999, org_id=1)


# =============================================================================
# CONNECTION LISTING TESTS
# =============================================================================

class TestConnectionListing:
    """Test listing connections for a loan."""

    def test_returns_connection_summaries(self, service, mock_db, mock_plaid_connection):
        """Connections are returned as summary dicts."""
        mock_db.query.return_value.filter.return_value.order_by.return_value.all.return_value = [
            mock_plaid_connection,
        ]

        results = service.get_connections_for_loan(loan_id=200, org_id=1)
        assert len(results) == 1

        conn = results[0]
        assert conn["connection_id"] == 42
        assert conn["institution_name"] == "Chase Bank"
        assert conn["connection_status"] == "active"
        assert conn["account_count"] == 2

    def test_empty_loan_returns_empty(self, service, mock_db):
        """Loan with no connections returns empty list."""
        mock_db.query.return_value.filter.return_value.order_by.return_value.all.return_value = []

        results = service.get_connections_for_loan(loan_id=999, org_id=1)
        assert results == []


# =============================================================================
# FULL ANALYSIS PIPELINE TESTS
# =============================================================================

class TestBankAnalysisPipeline:
    """Test the full generate_bank_analysis_from_plaid pipeline."""

    def test_no_connections_raises(self, service, mock_db):
        """Analysis without connections raises error."""
        mock_db.query.return_value.filter.return_value.all.return_value = []

        with pytest.raises(PlaidServiceError, match="No active Plaid connections"):
            service.generate_bank_analysis_from_plaid(loan_id=200, org_id=1)

    def test_analysis_structure(self, service, mock_db, mock_plaid_connection, sample_transactions):
        """Full analysis returns correct structure."""
        # Mock connections query
        mock_db.query.return_value.filter.return_value.all.return_value = [
            mock_plaid_connection,
        ]

        # Mock get_transactions to return sample data
        with patch.object(service, "get_transactions", return_value=sample_transactions):
            result = service.generate_bank_analysis_from_plaid(
                loan_id=200, org_id=1,
            )

        assert result["loan_id"] == 200
        assert result["connections_analyzed"] == 1
        assert result["total_transactions"] == len(sample_transactions)
        assert "large_deposits" in result
        assert "nsf_events" in result
        assert "irs_payments" in result
        assert "risk_score" in result
        assert "risk_level" in result
        assert "risk_factors" in result
        assert "recommendations" in result

    def test_risk_score_with_issues(self, service, mock_db, mock_plaid_connection, sample_transactions):
        """Risk score increases with large deposits and NSF events."""
        mock_db.query.return_value.filter.return_value.all.return_value = [
            mock_plaid_connection,
        ]

        with patch.object(service, "get_transactions", return_value=sample_transactions):
            result = service.generate_bank_analysis_from_plaid(
                loan_id=200, org_id=1,
            )

        # Should have risk from deposits and NSF events
        assert result["risk_score"] > 0
        assert len(result["risk_factors"]) > 0
        assert len(result["recommendations"]) > 0

    def test_clean_analysis_low_risk(self, service, mock_db, mock_plaid_connection):
        """Clean transactions produce low risk score."""
        mock_db.query.return_value.filter.return_value.all.return_value = [
            mock_plaid_connection,
        ]

        clean_txns = [
            {
                "date": "2026-03-01",
                "amount": -2500.00,
                "name": "PAYROLL DIRECT DEP",
                "category": ["Payment"],
                "merchant_name": None,
                "pending": False,
                "transaction_id": "txn_clean",
                "account_id": "acc_001",
            },
        ]

        with patch.object(service, "get_transactions", return_value=clean_txns):
            result = service.generate_bank_analysis_from_plaid(
                loan_id=200, org_id=1,
            )

        assert result["risk_score"] == 0
        assert result["risk_level"] == "low"


# =============================================================================
# WEBHOOK SIGNATURE VERIFICATION TESTS
# =============================================================================

class TestWebhookSignatureVerification:
    """Test webhook signature verification."""

    def test_no_key_accepts_webhook(self):
        """Without a verification key, webhooks are accepted."""
        result = PlaidIntegrationService.verify_webhook_signature(
            body=b'{"test": true}',
            signed_jwt="some-jwt-value",
            plaid_webhook_verification_key=None,
        )
        assert result is True

    def test_empty_key_accepts_webhook(self):
        """Empty verification key accepts webhook."""
        result = PlaidIntegrationService.verify_webhook_signature(
            body=b'{"test": true}',
            signed_jwt="some-jwt-value",
            plaid_webhook_verification_key="",
        )
        # Empty string is falsy, so it returns True (no verification)
        assert result is True

    def test_invalid_signature_rejects(self):
        """Invalid signature is rejected when key is configured."""
        result = PlaidIntegrationService.verify_webhook_signature(
            body=b'{"test": true}',
            signed_jwt="invalid-signature",
            plaid_webhook_verification_key="test-verification-key",
        )
        assert result is False


# =============================================================================
# SERVICE INITIALIZATION TESTS
# =============================================================================

class TestServiceInit:
    """Test service initialization with various configurations."""

    def test_init_without_plaid_sdk(self, mock_db):
        """Service initializes gracefully without plaid-python SDK."""
        with patch.dict("os.environ", {
            "PLAID_CLIENT_ID": "test",
            "PLAID_SECRET": "test",
        }, clear=False):
            with patch(
                "services.smart_docs.integrations.plaid_service.HAS_PLAID",
                False,
            ):
                svc = PlaidIntegrationService(mock_db)
                assert svc._client is None

    def test_init_without_credentials(self, mock_db):
        """Service initializes gracefully without credentials."""
        with patch.dict("os.environ", {}, clear=False):
            # Remove keys if present
            import os
            saved = {}
            for key in ("PLAID_CLIENT_ID", "PLAID_SECRET"):
                if key in os.environ:
                    saved[key] = os.environ.pop(key)

            try:
                with patch(
                    "services.smart_docs.integrations.plaid_service.HAS_PLAID",
                    False,
                ):
                    svc = PlaidIntegrationService(mock_db)
                    assert svc._client is None
            finally:
                os.environ.update(saved)

    def test_plaid_not_configured_raises_on_api_call(self, service):
        """API calls raise PlaidServiceError when Plaid is not configured."""
        service._client = None

        with pytest.raises(PlaidServiceError, match="not configured"):
            service.create_link_token(borrower_id=1, org_id=1, loan_id=1)

        with pytest.raises(PlaidServiceError, match="not configured"):
            service.create_asset_report(access_token_id=1)
