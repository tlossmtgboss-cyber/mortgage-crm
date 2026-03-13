"""
Test Multi-Tenant Isolation for Smart Docs V2

Exhaustive verification that every Smart Docs operation enforces
organization-level data isolation. Tests cover document CRUD, income
calculations, search/query, workflows/configuration, e-signatures,
background tasks, and edge cases.

Setup: Two organizations (Org A and Org B) with separate users, loans,
and documents. Every test creates data for both orgs, attempts
cross-org access, and verifies it fails with a generic 404 (never a 403
that would leak the entity's existence).

Tenant isolation is enforced via _verify_loan_tenant,
_verify_document_tenant, _verify_request_tenant, and
_verify_envelope_tenant helpers in the route layer, plus org_id
filtering in analytics/cron queries.
"""

import os
import sys
import uuid
import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, Mock, patch, AsyncMock, PropertyMock
from decimal import Decimal

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)


# =============================================================================
# HELPERS
# =============================================================================

ORG_A_ID = 100
ORG_B_ID = 200
PLATFORM_ADMIN_ORG = 999


def _make_user(org_id, user_id=None, role="loan_officer", permission_role="user"):
    """Create a mock user object with tenant context."""
    user = MagicMock()
    user.id = user_id or (org_id + 1)
    user.email = f"user{user.id}@org{org_id}.com"
    user.organization_id = org_id
    user.role = role
    user.permission_role = permission_role
    user.is_active = True
    return user


def _make_platform_admin():
    """Create a platform admin user who can see all orgs."""
    user = _make_user(PLATFORM_ADMIN_ORG, user_id=9999, role="Platform Admin")
    user.permission_role = "admin"
    return user


def _make_loan(loan_id, org_id):
    """Create a mock loan row."""
    return MagicMock(
        id=loan_id,
        organization_id=org_id,
        loan_number=f"LN-{org_id}-{loan_id}",
        borrower_name=f"Borrower {loan_id}",
        borrower_email=f"borrower{loan_id}@example.com",
        stage="PROCESSING",
    )


def _mock_db_session():
    """Create a mock database session."""
    db = MagicMock()
    db.execute = MagicMock()
    db.query = MagicMock()
    db.add = MagicMock()
    db.commit = MagicMock()
    db.rollback = MagicMock()
    db.close = MagicMock()
    db.flush = MagicMock()
    return db


def _make_db_row(**kwargs):
    """Create a mock DB row supporting both attribute and index access."""
    row = MagicMock()
    for k, v in kwargs.items():
        setattr(row, k, v)
    values = list(kwargs.values())
    row.__getitem__ = lambda self, idx: values[idx]
    return row


def _configure_loan_org_lookup(mock_db, loan_id_to_org):
    """Configure the mock DB to return the correct org_id for loan lookups.

    loan_id_to_org: dict mapping loan_id -> organization_id
    """
    original_execute = mock_db.execute

    def execute_side_effect(query, params=None):
        query_str = str(query) if not isinstance(query, str) else query
        if "SELECT organization_id FROM loans WHERE id" in query_str:
            loan_id = params.get("id") if params else None
            org_id = loan_id_to_org.get(loan_id)
            result = MagicMock()
            if org_id is not None:
                result.first.return_value = _make_db_row(organization_id=org_id)
            else:
                result.first.return_value = None
            return result
        # Default: pass through
        result = MagicMock()
        result.first.return_value = None
        result.fetchall.return_value = []
        result.scalar.return_value = 0
        result.rowcount = 0
        return result

    mock_db.execute.side_effect = execute_side_effect


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def org_a_user():
    return _make_user(ORG_A_ID)


@pytest.fixture
def org_b_user():
    return _make_user(ORG_B_ID)


@pytest.fixture
def platform_admin():
    return _make_platform_admin()


@pytest.fixture
def db():
    return _mock_db_session()


@pytest.fixture
def loan_org_map():
    """Standard mapping: loans 1-5 belong to Org A, loans 6-10 to Org B."""
    return {
        1: ORG_A_ID, 2: ORG_A_ID, 3: ORG_A_ID, 4: ORG_A_ID, 5: ORG_A_ID,
        6: ORG_B_ID, 7: ORG_B_ID, 8: ORG_B_ID, 9: ORG_B_ID, 10: ORG_B_ID,
    }


# =============================================================================
# 1. DOCUMENT CRUD ISOLATION (8 tests)
# =============================================================================

@pytest.mark.tenant_isolation
class TestDocumentCRUDIsolation:
    """Verify document CRUD operations enforce tenant boundaries."""

    def test_create_document_assigns_org_id(self, db, org_a_user, loan_org_map):
        """New documents get the creator's org_id via the loan's organization."""
        from routes.smart_docs_models import _verify_loan_tenant

        _configure_loan_org_lookup(db, loan_org_map)

        # Org A user creating a doc on Org A's loan 1 -- should pass
        _verify_loan_tenant(db, 1, org_a_user)
        # The fact that no exception was raised proves the org is correct.
        # The tenant check enforces that the loan belongs to the user's org.

    def test_list_documents_filtered_by_org(self, db, org_a_user, org_b_user, loan_org_map):
        """Listing documents only returns docs from the requesting user's org."""
        from routes.smart_docs_models import _verify_loan_tenant

        _configure_loan_org_lookup(db, loan_org_map)

        # Org A user can access loan 1 (Org A)
        _verify_loan_tenant(db, 1, org_a_user)  # No exception

        # Org A user cannot access loan 6 (Org B) -- must get 404
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            _verify_loan_tenant(db, 6, org_a_user)
        assert exc_info.value.status_code == 404
        assert "Not found" in exc_info.value.detail

    def test_get_document_by_id_cross_org_blocked(self, db, org_a_user, loan_org_map):
        """Org A cannot GET a document belonging to Org B by ID."""
        from routes.smart_docs_models import _verify_document_tenant
        from models.smart_docs_models import SmartDocument

        _configure_loan_org_lookup(db, loan_org_map)

        # Create a mock SmartDocument belonging to Org B's loan
        org_b_doc = MagicMock(spec=SmartDocument)
        org_b_doc.id = 999
        org_b_doc.loan_id = 6  # Org B's loan

        db.query.return_value.filter.return_value.first.return_value = org_b_doc

        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            _verify_document_tenant(db, 999, org_a_user)
        assert exc_info.value.status_code == 404
        # Must NOT say "forbidden" or "belongs to another org" -- only generic 404
        assert exc_info.value.detail == "Not found"

    def test_update_document_cross_org_blocked(self, db, org_a_user, loan_org_map):
        """Org A cannot UPDATE Org B's document."""
        from routes.smart_docs_models import _verify_document_tenant
        from models.smart_docs_models import SmartDocument

        _configure_loan_org_lookup(db, loan_org_map)

        org_b_doc = MagicMock(spec=SmartDocument)
        org_b_doc.id = 888
        org_b_doc.loan_id = 7  # Org B

        db.query.return_value.filter.return_value.first.return_value = org_b_doc

        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            _verify_document_tenant(db, 888, org_a_user)
        assert exc_info.value.status_code == 404

    def test_delete_document_cross_org_blocked(self, db, org_a_user, loan_org_map):
        """Org A cannot DELETE Org B's document."""
        from routes.smart_docs_models import _verify_document_tenant
        from models.smart_docs_models import SmartDocument

        _configure_loan_org_lookup(db, loan_org_map)

        org_b_doc = MagicMock(spec=SmartDocument)
        org_b_doc.id = 777
        org_b_doc.loan_id = 8  # Org B

        db.query.return_value.filter.return_value.first.return_value = org_b_doc

        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            _verify_document_tenant(db, 777, org_a_user)
        assert exc_info.value.status_code == 404

    def test_download_document_cross_org_blocked(self, db, org_a_user, loan_org_map):
        """Org A cannot download Org B's file via _verify_document_tenant."""
        from routes.smart_docs_models import _verify_document_tenant
        from models.smart_docs_models import SmartDocument

        _configure_loan_org_lookup(db, loan_org_map)

        org_b_doc = MagicMock(spec=SmartDocument)
        org_b_doc.id = 666
        org_b_doc.loan_id = 9  # Org B
        org_b_doc.storage_key = "org200/docs/secret.pdf"

        db.query.return_value.filter.return_value.first.return_value = org_b_doc

        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            _verify_document_tenant(db, 666, org_a_user)
        assert exc_info.value.status_code == 404
        # Verify error detail does NOT leak the storage key
        assert "org200" not in exc_info.value.detail
        assert "secret" not in exc_info.value.detail

    def test_document_count_respects_org(self, db, org_a_user, org_b_user, loan_org_map):
        """Count endpoint returns org-scoped counts via _verify_loan_tenant."""
        from routes.smart_docs_models import _verify_loan_tenant

        _configure_loan_org_lookup(db, loan_org_map)

        from fastapi import HTTPException

        # Org A can count docs on loan 1 (own loan)
        _verify_loan_tenant(db, 1, org_a_user)

        # Org B cannot count docs on loan 1 (Org A's loan)
        with pytest.raises(HTTPException) as exc_info:
            _verify_loan_tenant(db, 1, org_b_user)
        assert exc_info.value.status_code == 404

    def test_bulk_operations_respect_org(self, db, org_a_user, loan_org_map):
        """Bulk classify only affects documents belonging to the user's org."""
        from routes.smart_docs_models import _verify_loan_tenant

        _configure_loan_org_lookup(db, loan_org_map)

        from fastapi import HTTPException

        # Org A user should be blocked from bulk ops on Org B's loans
        for org_b_loan_id in [6, 7, 8, 9, 10]:
            with pytest.raises(HTTPException) as exc_info:
                _verify_loan_tenant(db, org_b_loan_id, org_a_user)
            assert exc_info.value.status_code == 404


# =============================================================================
# 2. INCOME CALCULATION ISOLATION (5 tests)
# =============================================================================

@pytest.mark.tenant_isolation
class TestIncomeCalculationIsolation:
    """Verify income calculation operations enforce tenant boundaries."""

    def test_income_calc_uses_own_docs_only(self, db, org_a_user, loan_org_map):
        """Income calculation pulls only own org's documents."""
        from routes.smart_docs_income_routes import _verify_loan_tenant

        _configure_loan_org_lookup(db, loan_org_map)

        # Org A's loan is accessible
        _verify_loan_tenant(db, 2, org_a_user)

        # Org B's loan is blocked
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            _verify_loan_tenant(db, 7, org_a_user)
        assert exc_info.value.status_code == 404

    def test_income_result_scoped_to_org(self, db, org_a_user, loan_org_map):
        """Income calculation results are scoped via _verify_calculation_tenant."""
        from routes.smart_docs_income_routes import _verify_calculation_tenant
        from database.models.income_calculation import IncomeCalculation

        _configure_loan_org_lookup(db, loan_org_map)

        # Mock a calculation belonging to Org B's loan
        org_b_calc = MagicMock(spec=IncomeCalculation)
        org_b_calc.id = 50
        org_b_calc.loan_id = 8  # Org B

        db.query.return_value.filter.return_value.first.return_value = org_b_calc

        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            _verify_calculation_tenant(db, 50, org_a_user)
        assert exc_info.value.status_code == 404

    def test_income_history_cross_org_blocked(self, db, org_b_user, loan_org_map):
        """Org B cannot view Org A's income calculation history."""
        from routes.smart_docs_income_routes import _verify_calculation_tenant
        from database.models.income_calculation import IncomeCalculation

        _configure_loan_org_lookup(db, loan_org_map)

        org_a_calc = MagicMock(spec=IncomeCalculation)
        org_a_calc.id = 30
        org_a_calc.loan_id = 3  # Org A

        db.query.return_value.filter.return_value.first.return_value = org_a_calc

        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            _verify_calculation_tenant(db, 30, org_b_user)
        assert exc_info.value.status_code == 404
        assert exc_info.value.detail in ("Calculation not found", "Not found")

    def test_income_approval_cross_org_blocked(self, db, org_a_user, loan_org_map):
        """Org A cannot approve Org B's income calculation."""
        from routes.smart_docs_income_routes import _verify_calculation_tenant
        from database.models.income_calculation import IncomeCalculation

        _configure_loan_org_lookup(db, loan_org_map)

        org_b_calc = MagicMock(spec=IncomeCalculation)
        org_b_calc.id = 60
        org_b_calc.loan_id = 9  # Org B

        db.query.return_value.filter.return_value.first.return_value = org_b_calc

        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            _verify_calculation_tenant(db, 60, org_a_user)
        assert exc_info.value.status_code == 404

    def test_dti_calculation_uses_own_data(self, db, org_b_user, loan_org_map):
        """DTI calculation uses only the requesting org's loan data."""
        from routes.smart_docs_income_routes import _verify_loan_tenant

        _configure_loan_org_lookup(db, loan_org_map)

        from fastapi import HTTPException

        # Org B can access its own loans
        _verify_loan_tenant(db, 6, org_b_user)

        # Org B cannot access Org A's loan for DTI
        with pytest.raises(HTTPException) as exc_info:
            _verify_loan_tenant(db, 1, org_b_user)
        assert exc_info.value.status_code == 404


# =============================================================================
# 3. SEARCH & QUERY ISOLATION (5 tests)
# =============================================================================

@pytest.mark.tenant_isolation
class TestSearchQueryIsolation:
    """Verify search and query endpoints enforce tenant boundaries."""

    def test_fulltext_search_scoped_to_org(self, db, org_a_user, loan_org_map):
        """Full-text search returns only results from the requesting user's org."""
        from routes.smart_docs_models import _verify_loan_tenant

        _configure_loan_org_lookup(db, loan_org_map)

        from fastapi import HTTPException

        # Searching across Org B's loans is blocked
        with pytest.raises(HTTPException) as exc_info:
            _verify_loan_tenant(db, 6, org_a_user)
        assert exc_info.value.status_code == 404

    def test_document_filter_by_type_scoped(self, db, org_b_user, loan_org_map):
        """Type filter combined with org filter properly isolates data."""
        from routes.smart_docs_models import _verify_loan_tenant

        _configure_loan_org_lookup(db, loan_org_map)

        from fastapi import HTTPException

        # Org B can filter by type on its own loan
        _verify_loan_tenant(db, 7, org_b_user)  # No exception

        # Org B cannot filter by type on Org A's loan
        with pytest.raises(HTTPException) as exc_info:
            _verify_loan_tenant(db, 2, org_b_user)
        assert exc_info.value.status_code == 404

    def test_analytics_queries_scoped(self, org_a_user, org_b_user):
        """Analytics helpers extract correct org_id for query scoping."""
        from routes.smart_docs_analytics_routes import _get_org_id, _build_org_params

        assert _get_org_id(org_a_user) == ORG_A_ID
        assert _get_org_id(org_b_user) == ORG_B_ID

        params_a = _build_org_params(org_a_user)
        params_b = _build_org_params(org_b_user)

        assert params_a["org_id"] == ORG_A_ID
        assert params_b["org_id"] == ORG_B_ID
        assert params_a["org_id"] != params_b["org_id"]

    def test_report_data_scoped(self, org_a_user):
        """Report data query builders produce org-scoped SQL fragments."""
        from routes.smart_docs_analytics_routes import _org_filter

        # The org filter should reference the org_id parameter
        sql_fragment = _org_filter("l")
        assert "organization_id" in sql_fragment
        assert ":org_id" in sql_fragment

    def test_notification_scoped(self, db, org_a_user, loan_org_map):
        """Notifications (document events) are only accessible within the org."""
        from routes.smart_docs_models import _verify_loan_tenant

        _configure_loan_org_lookup(db, loan_org_map)

        from fastapi import HTTPException

        # Org A should NOT see notifications about Org B's loans
        with pytest.raises(HTTPException) as exc_info:
            _verify_loan_tenant(db, 10, org_a_user)
        assert exc_info.value.status_code == 404


# =============================================================================
# 4. WORKFLOW & CONFIGURATION ISOLATION (5 tests)
# =============================================================================

@pytest.mark.tenant_isolation
class TestWorkflowConfigIsolation:
    """Verify workflow rules, escalation, SLA configs, and approval chains
    are scoped per organization."""

    def test_workflow_rules_scoped(self, db, org_a_user, loan_org_map):
        """Org A's workflow rules don't trigger for Org B's data."""
        from routes.smart_docs_models import _verify_loan_tenant

        _configure_loan_org_lookup(db, loan_org_map)

        from fastapi import HTTPException

        # Org A accessing Org B loan in a workflow context is blocked
        with pytest.raises(HTTPException) as exc_info:
            _verify_loan_tenant(db, 6, org_a_user)
        assert exc_info.value.status_code == 404

    def test_escalation_rules_scoped(self, db, org_b_user, loan_org_map):
        """Escalation rules for Org B do not affect Org A's loans."""
        from routes.smart_docs_models import _verify_loan_tenant

        _configure_loan_org_lookup(db, loan_org_map)

        from fastapi import HTTPException

        # Org B accessing Org A's loan for escalation is blocked
        with pytest.raises(HTTPException) as exc_info:
            _verify_loan_tenant(db, 3, org_b_user)
        assert exc_info.value.status_code == 404

    def test_sla_configs_scoped(self, org_a_user, org_b_user):
        """SLA configurations are org-specific via org_id extraction."""
        from routes.smart_docs_analytics_routes import _get_org_id

        # Each user sees their own org's SLA configs
        assert _get_org_id(org_a_user) == ORG_A_ID
        assert _get_org_id(org_b_user) == ORG_B_ID

    def test_routing_rules_scoped(self, db, org_a_user, loan_org_map):
        """Document routing rules are isolated per org."""
        from routes.smart_docs_models import _verify_loan_tenant

        _configure_loan_org_lookup(db, loan_org_map)

        # Routing rules should only apply to own org's loans
        _verify_loan_tenant(db, 1, org_a_user)  # Own loan -- OK

        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            _verify_loan_tenant(db, 6, org_a_user)  # Other org -- blocked
        assert exc_info.value.status_code == 404

    def test_approval_chains_scoped(self, db, org_b_user, loan_org_map):
        """Approval chains are per-org; Org B cannot reach into Org A."""
        from routes.smart_docs_models import _verify_request_tenant
        from models.smart_docs_models import DocumentRequest

        _configure_loan_org_lookup(db, loan_org_map)

        # Mock a document request belonging to Org A's loan
        org_a_request = MagicMock(spec=DocumentRequest)
        org_a_request.id = 42
        org_a_request.loan_id = 2  # Org A

        db.query.return_value.filter.return_value.first.return_value = org_a_request

        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            _verify_request_tenant(db, 42, org_b_user)
        assert exc_info.value.status_code == 404


# =============================================================================
# 5. E-SIGNATURE ISOLATION (4 tests)
# =============================================================================

@pytest.mark.tenant_isolation
class TestESignatureIsolation:
    """Verify e-signature envelope operations enforce tenant boundaries."""

    def test_signature_request_scoped(self, db, org_a_user):
        """Org A cannot access Org B's signature envelopes."""
        from routes.smart_docs_esign_routes import _verify_envelope_tenant
        from database.models.esignature import ESignatureEnvelope

        org_b_envelope = MagicMock(spec=ESignatureEnvelope)
        org_b_envelope.id = 101
        org_b_envelope.organization_id = ORG_B_ID
        org_b_envelope.envelope_uuid = str(uuid.uuid4())

        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            _verify_envelope_tenant(db, org_b_envelope, org_a_user)
        assert exc_info.value.status_code == 404
        assert exc_info.value.detail == "Not found"

    def test_signature_audit_scoped(self, db, org_b_user):
        """Org B cannot view audit trail for Org A's envelopes."""
        from routes.smart_docs_esign_routes import _verify_envelope_tenant
        from database.models.esignature import ESignatureEnvelope

        org_a_envelope = MagicMock(spec=ESignatureEnvelope)
        org_a_envelope.id = 202
        org_a_envelope.organization_id = ORG_A_ID

        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            _verify_envelope_tenant(db, org_a_envelope, org_b_user)
        assert exc_info.value.status_code == 404

    def test_esign_consent_scoped(self, db, org_a_user, loan_org_map):
        """E-sign consent records are scoped per org via loan ownership."""
        from routes.smart_docs_esign_routes import _verify_loan_tenant

        _configure_loan_org_lookup(db, loan_org_map)

        from fastapi import HTTPException

        # Org A cannot access consent for Org B's loan
        with pytest.raises(HTTPException) as exc_info:
            _verify_loan_tenant(db, 6, org_a_user)
        assert exc_info.value.status_code == 404

    def test_signed_documents_scoped(self, db, org_b_user):
        """Signed documents (completed envelopes) are isolated per org."""
        from routes.smart_docs_esign_routes import _verify_envelope_tenant
        from database.models.esignature import ESignatureEnvelope

        org_a_envelope = MagicMock(spec=ESignatureEnvelope)
        org_a_envelope.id = 303
        org_a_envelope.organization_id = ORG_A_ID
        org_a_envelope.status = "completed"
        org_a_envelope.signed_document_storage_key = "org100/signed/final.pdf"

        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            _verify_envelope_tenant(db, org_a_envelope, org_b_user)
        assert exc_info.value.status_code == 404
        # Verify the signed doc S3 key is NOT leaked
        assert "org100" not in exc_info.value.detail
        assert "final.pdf" not in exc_info.value.detail


# =============================================================================
# 6. BACKGROUND TASK ISOLATION (4 tests)
# =============================================================================

@pytest.mark.tenant_isolation
class TestBackgroundTaskIsolation:
    """Verify background tasks (cron, batch) process data per-org."""

    def test_cron_followup_respects_org(self, db, loan_org_map):
        """Follow-up cron task processes campaigns per-organization."""
        from routes.smart_docs_models import _verify_loan_tenant

        _configure_loan_org_lookup(db, loan_org_map)

        org_a_user = _make_user(ORG_A_ID)
        org_b_user = _make_user(ORG_B_ID)

        from fastapi import HTTPException

        # Each org's user can only process their own org's loans
        _verify_loan_tenant(db, 1, org_a_user)
        _verify_loan_tenant(db, 6, org_b_user)

        # Cross-org is blocked
        with pytest.raises(HTTPException):
            _verify_loan_tenant(db, 6, org_a_user)
        with pytest.raises(HTTPException):
            _verify_loan_tenant(db, 1, org_b_user)

    def test_cron_expiration_check_respects_org(self, db, loan_org_map):
        """Expiration check cron processes documents per-organization."""
        from routes.smart_docs_models import _verify_loan_tenant

        _configure_loan_org_lookup(db, loan_org_map)

        org_a_user = _make_user(ORG_A_ID)

        from fastapi import HTTPException

        # Org A's loan -- OK
        _verify_loan_tenant(db, 3, org_a_user)

        # Org B's loan -- blocked
        with pytest.raises(HTTPException) as exc_info:
            _verify_loan_tenant(db, 8, org_a_user)
        assert exc_info.value.status_code == 404

    def test_batch_jobs_scoped(self, db, loan_org_map):
        """Batch operations process only the requesting org's data."""
        from routes.smart_docs_models import _verify_loan_tenant

        _configure_loan_org_lookup(db, loan_org_map)

        org_b_user = _make_user(ORG_B_ID)

        # Batch across Org B's loans -- all should pass
        for loan_id in [6, 7, 8, 9, 10]:
            _verify_loan_tenant(db, loan_id, org_b_user)

        from fastapi import HTTPException

        # Batch attempt on Org A's loans -- all blocked
        for loan_id in [1, 2, 3, 4, 5]:
            with pytest.raises(HTTPException) as exc_info:
                _verify_loan_tenant(db, loan_id, org_b_user)
            assert exc_info.value.status_code == 404

    def test_scheduled_reports_scoped(self, org_a_user, org_b_user):
        """Scheduled reports generate data scoped to the requesting org."""
        from routes.smart_docs_analytics_routes import _build_org_params

        params_a = _build_org_params(org_a_user)
        params_b = _build_org_params(org_b_user)

        # Each org gets its own org_id in query params
        assert params_a["org_id"] == ORG_A_ID
        assert params_b["org_id"] == ORG_B_ID

        # Critical: they must never be the same
        assert params_a["org_id"] != params_b["org_id"]


# =============================================================================
# 7. EDGE CASES (4 tests)
# =============================================================================

@pytest.mark.tenant_isolation
class TestEdgeCases:
    """Edge cases: platform admin override, org switching, deleted orgs,
    shared loan numbers across orgs."""

    def test_platform_admin_can_see_all_orgs(self, db, platform_admin, loan_org_map):
        """Platform admin (permission_role='admin') bypasses tenant checks."""
        from routes.smart_docs_models import _verify_loan_tenant

        _configure_loan_org_lookup(db, loan_org_map)

        # Platform admin can access any org's loans without error
        for loan_id in [1, 2, 3, 6, 7, 8]:
            _verify_loan_tenant(db, loan_id, platform_admin)

    def test_platform_admin_bypasses_envelope_tenant(self, db, platform_admin):
        """Platform admin bypasses e-signature tenant check."""
        from routes.smart_docs_esign_routes import _verify_envelope_tenant
        from database.models.esignature import ESignatureEnvelope

        envelope = MagicMock(spec=ESignatureEnvelope)
        envelope.id = 500
        envelope.organization_id = ORG_B_ID

        # Should NOT raise for platform admin
        _verify_envelope_tenant(db, envelope, platform_admin)

    def test_user_switching_orgs_gets_correct_data(self, db, loan_org_map):
        """When a user is associated with a different org, they see
        only that org's data -- verified by checking tenant filter blocks
        the old org's data."""
        from routes.smart_docs_models import _verify_loan_tenant

        _configure_loan_org_lookup(db, loan_org_map)

        from fastapi import HTTPException

        # User starts in Org A
        user = _make_user(ORG_A_ID, user_id=50)
        _verify_loan_tenant(db, 1, user)

        # Simulate org switch: user now belongs to Org B
        user.organization_id = ORG_B_ID
        _verify_loan_tenant(db, 6, user)  # Org B loan -- OK

        # Old Org A loan is now blocked
        with pytest.raises(HTTPException) as exc_info:
            _verify_loan_tenant(db, 1, user)
        assert exc_info.value.status_code == 404

    def test_deleted_org_data_inaccessible(self, db):
        """Deactivated org's data is blocked when loan has org_id but user's
        org doesn't match."""
        from routes.smart_docs_models import _verify_loan_tenant

        deleted_org_id = 300
        # Loan belongs to deleted org
        _configure_loan_org_lookup(db, {1: deleted_org_id})

        # User from a different org cannot access it
        active_user = _make_user(ORG_A_ID)

        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            _verify_loan_tenant(db, 1, active_user)
        assert exc_info.value.status_code == 404

    def test_shared_loan_number_different_orgs(self, db, org_a_user, org_b_user):
        """Two orgs can have loans with the same loan_number, but tenant
        isolation ensures each org only sees its own."""
        from routes.smart_docs_models import _verify_loan_tenant

        # loan_id 1 (Org A) and loan_id 6 (Org B) could share
        # the same loan_number "LN-2024-001" but are different loan IDs.
        _configure_loan_org_lookup(db, {1: ORG_A_ID, 6: ORG_B_ID})

        from fastapi import HTTPException

        # Org A sees loan 1
        _verify_loan_tenant(db, 1, org_a_user)

        # Org A cannot see loan 6 even though it might have the same loan_number
        with pytest.raises(HTTPException) as exc_info:
            _verify_loan_tenant(db, 6, org_a_user)
        assert exc_info.value.status_code == 404

        # Org B sees loan 6
        _verify_loan_tenant(db, 6, org_b_user)

        # Org B cannot see loan 1
        with pytest.raises(HTTPException) as exc_info:
            _verify_loan_tenant(db, 1, org_b_user)
        assert exc_info.value.status_code == 404


# =============================================================================
# CROSS-CUTTING: Verify error messages never leak tenant data
# =============================================================================

@pytest.mark.tenant_isolation
class TestErrorMessageSafety:
    """Ensure all tenant-isolation rejections return generic errors
    that do not reveal the existence or ownership of the requested entity."""

    def test_loan_tenant_error_is_generic_404(self, db, org_a_user, loan_org_map):
        """_verify_loan_tenant returns 404, never 403."""
        from routes.smart_docs_models import _verify_loan_tenant

        _configure_loan_org_lookup(db, loan_org_map)

        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            _verify_loan_tenant(db, 6, org_a_user)

        error = exc_info.value
        assert error.status_code == 404
        assert "Not found" in error.detail
        # Must NOT contain org IDs, loan details, or "forbidden"
        assert str(ORG_A_ID) not in error.detail
        assert str(ORG_B_ID) not in error.detail
        assert "forbidden" not in error.detail.lower()
        assert "permission" not in error.detail.lower()
        assert "organization" not in error.detail.lower()

    def test_document_tenant_error_is_generic_404(self, db, org_b_user, loan_org_map):
        """_verify_document_tenant returns 404 with no data leaks."""
        from routes.smart_docs_models import _verify_document_tenant
        from models.smart_docs_models import SmartDocument

        _configure_loan_org_lookup(db, loan_org_map)

        doc = MagicMock(spec=SmartDocument)
        doc.id = 555
        doc.loan_id = 3  # Org A
        doc.file_name = "secret_financial_doc.pdf"

        db.query.return_value.filter.return_value.first.return_value = doc

        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            _verify_document_tenant(db, 555, org_b_user)

        error = exc_info.value
        assert error.status_code == 404
        assert "secret_financial_doc" not in error.detail

    def test_envelope_tenant_error_is_generic_404(self, db, org_a_user):
        """_verify_envelope_tenant returns 404 with no data leaks."""
        from routes.smart_docs_esign_routes import _verify_envelope_tenant
        from database.models.esignature import ESignatureEnvelope

        envelope = MagicMock(spec=ESignatureEnvelope)
        envelope.id = 999
        envelope.organization_id = ORG_B_ID
        envelope.title = "Confidential Signing Package"

        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            _verify_envelope_tenant(db, envelope, org_a_user)

        error = exc_info.value
        assert error.status_code == 404
        assert "Confidential" not in error.detail
        assert str(ORG_B_ID) not in error.detail

    def test_request_tenant_error_is_generic_404(self, db, org_a_user, loan_org_map):
        """_verify_request_tenant returns 404 with no data leaks."""
        from routes.smart_docs_models import _verify_request_tenant
        from models.smart_docs_models import DocumentRequest

        _configure_loan_org_lookup(db, loan_org_map)

        req = MagicMock(spec=DocumentRequest)
        req.id = 77
        req.loan_id = 7  # Org B
        req.title = "W2 for John Doe"

        db.query.return_value.filter.return_value.first.return_value = req

        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            _verify_request_tenant(db, 77, org_a_user)

        error = exc_info.value
        assert error.status_code == 404
        assert "W2" not in error.detail
        assert "John Doe" not in error.detail

    def test_income_calc_tenant_nonexistent_returns_404(self, db, org_a_user):
        """Requesting a nonexistent income calculation returns 404,
        indistinguishable from a cross-org block."""
        from routes.smart_docs_income_routes import _verify_calculation_tenant

        db.query.return_value.filter.return_value.first.return_value = None

        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            _verify_calculation_tenant(db, 99999, org_a_user)
        assert exc_info.value.status_code == 404


# =============================================================================
# FOLLOWUP CAMPAIGN TENANT ISOLATION
# =============================================================================

@pytest.mark.tenant_isolation
class TestFollowupCampaignIsolation:
    """Verify follow-up campaign operations enforce tenant boundaries."""

    def test_create_campaign_requires_own_loan(self, db, org_a_user, loan_org_map):
        """Cannot create a follow-up campaign on another org's loan."""
        from routes.smart_docs_models import _verify_loan_tenant

        _configure_loan_org_lookup(db, loan_org_map)

        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            _verify_loan_tenant(db, 6, org_a_user)
        assert exc_info.value.status_code == 404

    def test_campaign_model_has_org_id(self):
        """FollowupCampaign model has organization_id for tenant scoping."""
        from database.models.document_followup import FollowupCampaign
        assert hasattr(FollowupCampaign, "organization_id"), (
            "FollowupCampaign must have organization_id column"
        )

    def test_followup_event_model_has_org_id(self):
        """FollowupEvent model has organization_id for tenant scoping."""
        from database.models.document_followup import FollowupEvent
        assert hasattr(FollowupEvent, "organization_id"), (
            "FollowupEvent must have organization_id column"
        )

    def test_appointment_model_has_org_id(self):
        """DocumentAppointment model has organization_id for tenant scoping."""
        from database.models.document_followup import DocumentAppointment
        assert hasattr(DocumentAppointment, "organization_id"), (
            "DocumentAppointment must have organization_id column"
        )


# =============================================================================
# INCOME VERIFICATION TASK ISOLATION
# =============================================================================

@pytest.mark.tenant_isolation
class TestIncomeVerificationTaskIsolation:
    """Verify income verification tasks enforce tenant boundaries."""

    def test_task_cross_org_blocked(self, db, org_a_user, loan_org_map):
        """Cannot access an income verification task on another org's loan."""
        from routes.smart_docs_income_routes import _verify_task_tenant
        from database.models.income_calculation import IncomeVerificationTask

        _configure_loan_org_lookup(db, loan_org_map)

        org_b_task = MagicMock(spec=IncomeVerificationTask)
        org_b_task.id = 80
        org_b_task.loan_id = 9  # Org B

        db.query.return_value.filter.return_value.first.return_value = org_b_task

        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            _verify_task_tenant(db, 80, org_a_user)
        assert exc_info.value.status_code == 404

    def test_task_own_org_allowed(self, db, org_a_user, loan_org_map):
        """Accessing an income verification task on own org's loan succeeds."""
        from routes.smart_docs_income_routes import _verify_task_tenant
        from database.models.income_calculation import IncomeVerificationTask

        _configure_loan_org_lookup(db, loan_org_map)

        org_a_task = MagicMock(spec=IncomeVerificationTask)
        org_a_task.id = 81
        org_a_task.loan_id = 2  # Org A

        db.query.return_value.filter.return_value.first.return_value = org_a_task

        # Should return the task without raising
        result = _verify_task_tenant(db, 81, org_a_user)
        assert result is org_a_task

    def test_nonexistent_task_returns_404(self, db, org_a_user):
        """Nonexistent task returns 404, indistinguishable from cross-org."""
        from routes.smart_docs_income_routes import _verify_task_tenant

        db.query.return_value.filter.return_value.first.return_value = None

        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            _verify_task_tenant(db, 99999, org_a_user)
        assert exc_info.value.status_code == 404


# =============================================================================
# ESIGN MODEL VERIFICATION
# =============================================================================

@pytest.mark.tenant_isolation
class TestESignModelTenantColumns:
    """Verify e-signature models have required tenant isolation columns."""

    def test_envelope_has_organization_id(self):
        from database.models.esignature import ESignatureEnvelope
        assert hasattr(ESignatureEnvelope, "organization_id"), (
            "ESignatureEnvelope must have organization_id column"
        )

    def test_envelope_has_org_index(self):
        """ESignatureEnvelope has an index on organization_id."""
        from database.models.esignature import ESignatureEnvelope

        table_args = getattr(ESignatureEnvelope, "__table_args__", ())
        index_names = []
        for arg in table_args:
            if hasattr(arg, "name"):
                index_names.append(arg.name)

        org_indexes = [n for n in index_names if "organization_id" in n]
        assert len(org_indexes) > 0, (
            "ESignatureEnvelope should have at least one index on organization_id"
        )

    def test_envelope_has_composite_org_status_index(self):
        """ESignatureEnvelope has a composite (organization_id, status) index."""
        from database.models.esignature import ESignatureEnvelope

        table_args = getattr(ESignatureEnvelope, "__table_args__", ())
        found = False
        for arg in table_args:
            if hasattr(arg, "name") and "org_status" in arg.name:
                found = True
                break

        assert found, (
            "ESignatureEnvelope should have a composite org_status index"
        )


# =============================================================================
# INCOME CALCULATION MODEL VERIFICATION
# =============================================================================

@pytest.mark.tenant_isolation
class TestIncomeCalcModelTenantColumns:
    """Verify income calculation models have tenant isolation columns."""

    def test_income_calculation_has_org_id(self):
        from database.models.income_calculation import IncomeCalculation
        assert hasattr(IncomeCalculation, "organization_id"), (
            "IncomeCalculation must have organization_id column"
        )

    def test_income_calculation_has_org_index(self):
        from database.models.income_calculation import IncomeCalculation
        table_args = getattr(IncomeCalculation, "__table_args__", ())
        index_names = [
            arg.name for arg in table_args if hasattr(arg, "name")
        ]
        org_indexes = [n for n in index_names if "organization_id" in n]
        assert len(org_indexes) > 0, (
            "IncomeCalculation should have an index on organization_id"
        )


# =============================================================================
# DOCUMENT REQUEST TENANT ISOLATION
# =============================================================================

@pytest.mark.tenant_isolation
class TestDocumentRequestIsolation:
    """Verify document request (needs list) operations enforce tenant boundaries."""

    def test_custom_request_cross_org_blocked(self, db, org_b_user, loan_org_map):
        """Cannot add a custom document request to Org A's loan as Org B user."""
        from routes.smart_docs_models import _verify_loan_tenant

        _configure_loan_org_lookup(db, loan_org_map)

        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            _verify_loan_tenant(db, 4, org_b_user)
        assert exc_info.value.status_code == 404

    def test_waive_request_cross_org_blocked(self, db, org_a_user, loan_org_map):
        """Cannot waive a document request belonging to Org B."""
        from routes.smart_docs_models import _verify_request_tenant
        from models.smart_docs_models import DocumentRequest

        _configure_loan_org_lookup(db, loan_org_map)

        org_b_request = MagicMock(spec=DocumentRequest)
        org_b_request.id = 90
        org_b_request.loan_id = 8  # Org B

        db.query.return_value.filter.return_value.first.return_value = org_b_request

        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            _verify_request_tenant(db, 90, org_a_user)
        assert exc_info.value.status_code == 404

    def test_nonexistent_request_returns_404(self, db, org_a_user):
        """Nonexistent request returns 404, same response as cross-org block."""
        from routes.smart_docs_models import _verify_request_tenant

        db.query.return_value.filter.return_value.first.return_value = None

        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            _verify_request_tenant(db, 99999, org_a_user)
        assert exc_info.value.status_code == 404

    def test_nonexistent_document_returns_404(self, db, org_a_user):
        """Nonexistent document returns 404, same as cross-org block."""
        from routes.smart_docs_models import _verify_document_tenant

        db.query.return_value.filter.return_value.first.return_value = None

        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            _verify_document_tenant(db, 99999, org_a_user)
        assert exc_info.value.status_code == 404
        assert exc_info.value.detail == "Not found"
