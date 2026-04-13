"""
Tests for aria/tools/crm_tools.py — CRM Data Bridge for Aria.

Covers borrower lookup (by ID, name, email), active loan retrieval,
user lookup, contact resolution, and multi-tenant isolation.
All DB access is mocked via asyncio.to_thread and SessionLocal.
"""

import pytest
from datetime import datetime
from unittest.mock import MagicMock, patch

# ---------------------------------------------------------------------------
# Helpers — fake DB row tuples matching the SELECT column order in crm_tools
# ---------------------------------------------------------------------------

def _make_lead_row(
    id=1, name="John Smith", email="john@example.com", phone="555-0100",
    stage="APPLICATION", loan_number="LN-001", loan_amount=350000.0,
    property_address="123 Main St", organization_id="org-1",
):
    """Return a tuple matching the leads SELECT columns."""
    return (id, name, email, phone, stage, loan_number, loan_amount,
            property_address, organization_id)


def _make_loan_row(
    id=10, loan_number="LN-001", loan_amount=350000.0,
    loan_type="Conventional", stage="PROCESSING", rate=6.5,
    property_address="123 Main St", purchase_price=400000.0,
    updated_at=None, owner_id="user-1",
):
    updated_at = updated_at or datetime(2026, 4, 1, 12, 0)
    return (id, loan_number, loan_amount, loan_type, stage, rate,
            property_address, purchase_price, updated_at, owner_id)


def _make_user_row(
    id="user-1", email="lo@example.com", first_name="Jane", last_name="Doe",
    phone="555-0200", organization_id="org-1", role="loan_officer",
    nmls_number="123456",
):
    return (id, email, first_name, last_name, phone, organization_id,
            role, nmls_number)


def _make_user_contact_row(
    id="user-2", email="peer@example.com", first_name="Bob",
    last_name="Jones", phone="555-0300",
):
    return (id, email, first_name, last_name, phone)


# ---------------------------------------------------------------------------
# Fixture: mock SessionLocal so no real DB connection is needed.
# asyncio.to_thread is patched to just call the function synchronously.
# ---------------------------------------------------------------------------

def _build_mock_session(execute_side_effect):
    """
    Build a mock SessionLocal that returns a session whose .execute()
    uses the given side_effect callable/list.
    """
    mock_session = MagicMock()
    mock_session.execute = MagicMock(side_effect=execute_side_effect)
    mock_session.close = MagicMock()

    mock_session_local = MagicMock(return_value=mock_session)
    return mock_session_local, mock_session


async def _sync_to_thread(fn):
    """Replace asyncio.to_thread — just call the function directly."""
    return fn()


# ===========================================================================
# get_borrower tests
# ===========================================================================

@pytest.mark.asyncio
async def test_get_borrower_by_numeric_id():
    """Numeric identifier triggers direct ID lookup and returns lead dict."""
    lead_row = _make_lead_row(id=42, name="Alice Wonderland")
    result_proxy = MagicMock()
    result_proxy.fetchone.return_value = lead_row

    mock_sl, mock_sess = _build_mock_session(lambda stmt, params=None: result_proxy)

    with patch("aria.tools.crm_tools.SessionLocal", mock_sl), \
         patch("aria.tools.crm_tools.asyncio.to_thread", _sync_to_thread):
        from aria.tools.crm_tools import CRMTools
        tools = CRMTools()
        result = await tools.get_borrower("42", "org-1")

    assert result is not None
    assert result["id"] == 42
    assert result["full_name"] == "Alice Wonderland"
    assert result["organization_id"] == "org-1"
    mock_sess.close.assert_called_once()


@pytest.mark.asyncio
async def test_get_borrower_by_name_fuzzy_search():
    """Non-numeric identifier falls through to name LIKE search."""
    lead_row = _make_lead_row(id=7, name="Carlos Rivera", email="carlos@test.com")

    call_count = 0

    def _execute(stmt, params=None):
        nonlocal call_count
        call_count += 1
        proxy = MagicMock()
        if call_count == 1:
            # First call is the name LIKE query (ID parse fails for non-numeric)
            proxy.fetchone.return_value = lead_row
        else:
            proxy.fetchone.return_value = None
        return proxy

    mock_sl, mock_sess = _build_mock_session(_execute)

    with patch("aria.tools.crm_tools.SessionLocal", mock_sl), \
         patch("aria.tools.crm_tools.asyncio.to_thread", _sync_to_thread):
        from aria.tools.crm_tools import CRMTools
        tools = CRMTools()
        result = await tools.get_borrower("carlos", "org-1")

    assert result is not None
    assert result["full_name"] == "Carlos Rivera"
    assert result["email"] == "carlos@test.com"


@pytest.mark.asyncio
async def test_get_borrower_by_email():
    """If ID and name search both miss, falls through to email lookup."""
    lead_row = _make_lead_row(id=9, name="Diana Prince", email="diana@test.com")

    call_count = 0

    def _execute(stmt, params=None):
        nonlocal call_count
        call_count += 1
        proxy = MagicMock()
        if call_count == 1:
            # "diana@test.com" is non-numeric so int() raises ValueError;
            # first actual execute is the name ILIKE query → miss
            proxy.fetchone.return_value = None
        else:
            # Second execute: email match
            proxy.fetchone.return_value = lead_row
        return proxy

    mock_sl, mock_sess = _build_mock_session(_execute)

    with patch("aria.tools.crm_tools.SessionLocal", mock_sl), \
         patch("aria.tools.crm_tools.asyncio.to_thread", _sync_to_thread):
        from aria.tools.crm_tools import CRMTools
        tools = CRMTools()
        result = await tools.get_borrower("diana@test.com", "org-1")

    assert result is not None
    assert result["email"] == "diana@test.com"
    # int() parse skipped (non-numeric), name ILIKE miss, email hit = 2 execute calls
    assert call_count == 2


@pytest.mark.asyncio
async def test_get_borrower_returns_none_when_not_found():
    """All lookup strategies miss — returns None."""
    def _execute(stmt, params=None):
        proxy = MagicMock()
        proxy.fetchone.return_value = None
        return proxy

    mock_sl, mock_sess = _build_mock_session(_execute)

    with patch("aria.tools.crm_tools.SessionLocal", mock_sl), \
         patch("aria.tools.crm_tools.asyncio.to_thread", _sync_to_thread):
        from aria.tools.crm_tools import CRMTools
        tools = CRMTools()
        result = await tools.get_borrower("nobody@nowhere.com", "org-1")

    assert result is None


# ===========================================================================
# get_active_loan tests
# ===========================================================================

@pytest.mark.asyncio
async def test_get_active_loan_returns_loan():
    """Returns the most recent active loan for a borrower."""
    loan_row = _make_loan_row(id=20, loan_number="LN-555", stage="UNDERWRITING")
    result_proxy = MagicMock()
    result_proxy.fetchone.return_value = loan_row

    mock_sl, mock_sess = _build_mock_session(lambda stmt, params=None: result_proxy)

    with patch("aria.tools.crm_tools.SessionLocal", mock_sl), \
         patch("aria.tools.crm_tools.asyncio.to_thread", _sync_to_thread):
        from aria.tools.crm_tools import CRMTools
        tools = CRMTools()
        result = await tools.get_active_loan(42, "org-1")

    assert result is not None
    assert result["id"] == 20
    assert result["loan_number"] == "LN-555"
    assert result["stage"] == "UNDERWRITING"
    assert result["loan_amount"] == 350000.0
    assert result["rate"] == 6.5
    assert result["last_activity_at"] == "2026-04-01T12:00:00"
    mock_sess.close.assert_called_once()


@pytest.mark.asyncio
async def test_get_active_loan_returns_none_when_no_loan():
    """No loan found for borrower — returns None."""
    def _execute(stmt, params=None):
        proxy = MagicMock()
        proxy.fetchone.return_value = None
        return proxy

    mock_sl, mock_sess = _build_mock_session(_execute)

    with patch("aria.tools.crm_tools.SessionLocal", mock_sl), \
         patch("aria.tools.crm_tools.asyncio.to_thread", _sync_to_thread):
        from aria.tools.crm_tools import CRMTools
        tools = CRMTools()
        result = await tools.get_active_loan(999, "org-1")

    assert result is None


@pytest.mark.asyncio
async def test_get_active_loan_falls_back_to_any_loan():
    """First query (non-terminal) misses; fallback query returns a funded loan."""
    funded_loan = _make_loan_row(id=30, stage="FUNDED")

    call_count = 0

    def _execute(stmt, params=None):
        nonlocal call_count
        call_count += 1
        proxy = MagicMock()
        if call_count == 1:
            proxy.fetchone.return_value = None  # No active loan
        else:
            proxy.fetchone.return_value = funded_loan  # Fallback finds funded
        return proxy

    mock_sl, mock_sess = _build_mock_session(_execute)

    with patch("aria.tools.crm_tools.SessionLocal", mock_sl), \
         patch("aria.tools.crm_tools.asyncio.to_thread", _sync_to_thread):
        from aria.tools.crm_tools import CRMTools
        tools = CRMTools()
        result = await tools.get_active_loan(42, "org-1")

    assert result is not None
    assert result["stage"] == "FUNDED"
    assert call_count == 2


# ===========================================================================
# get_user tests
# ===========================================================================

@pytest.mark.asyncio
async def test_get_user_returns_user_by_id():
    """Returns user dict with computed full_name and default title."""
    user_row = _make_user_row(id="user-77", first_name="Jane", last_name="Doe")
    result_proxy = MagicMock()
    result_proxy.fetchone.return_value = user_row

    mock_sl, mock_sess = _build_mock_session(lambda stmt, params=None: result_proxy)

    with patch("aria.tools.crm_tools.SessionLocal", mock_sl), \
         patch("aria.tools.crm_tools.asyncio.to_thread", _sync_to_thread):
        from aria.tools.crm_tools import CRMTools
        tools = CRMTools()
        result = await tools.get_user("user-77")

    assert result is not None
    assert result["id"] == "user-77"
    assert result["full_name"] == "Jane Doe"
    assert result["email"] == "lo@example.com"
    assert result["title"] == "Loan Officer"
    assert result["role"] == "loan_officer"
    assert result["nmls_number"] == "123456"
    mock_sess.close.assert_called_once()


@pytest.mark.asyncio
async def test_get_user_returns_none_when_not_found():
    """Non-existent user ID returns None."""
    result_proxy = MagicMock()
    result_proxy.fetchone.return_value = None

    mock_sl, mock_sess = _build_mock_session(lambda stmt, params=None: result_proxy)

    with patch("aria.tools.crm_tools.SessionLocal", mock_sl), \
         patch("aria.tools.crm_tools.asyncio.to_thread", _sync_to_thread):
        from aria.tools.crm_tools import CRMTools
        tools = CRMTools()
        result = await tools.get_user("nonexistent")

    assert result is None


# ===========================================================================
# resolve_contact tests
# ===========================================================================

@pytest.mark.asyncio
async def test_resolve_contact_finds_borrower_by_name():
    """resolve_contact checks leads first; returns borrower-typed contact."""
    lead_row = _make_lead_row(id=5, name="Emily Chen", email="emily@test.com",
                               phone="555-0500")

    def _execute(stmt, params=None):
        proxy = MagicMock()
        proxy.fetchone.return_value = lead_row
        return proxy

    mock_sl, mock_sess = _build_mock_session(_execute)

    with patch("aria.tools.crm_tools.SessionLocal", mock_sl), \
         patch("aria.tools.crm_tools.asyncio.to_thread", _sync_to_thread):
        from aria.tools.crm_tools import CRMTools
        tools = CRMTools()
        result = await tools.resolve_contact("emily", "org-1")

    assert result is not None
    assert result["type"] == "borrower"
    assert result["name"] == "Emily Chen"
    assert result["email"] == "emily@test.com"


@pytest.mark.asyncio
async def test_resolve_contact_falls_back_to_user():
    """If no lead matches, resolve_contact searches users table."""
    user_contact_row = _make_user_contact_row(
        id="user-9", first_name="Mike", last_name="Taylor",
        email="mike@company.com", phone="555-0900",
    )

    # Track which query is being executed
    call_count = 0

    def _execute(stmt, params=None):
        nonlocal call_count
        call_count += 1
        proxy = MagicMock()
        if call_count <= 2:
            # "mike" is non-numeric so int() raises ValueError;
            # get_borrower makes 2 execute calls: name ILIKE miss + email miss
            proxy.fetchone.return_value = None
        else:
            # User query in resolve_contact succeeds (call 3)
            proxy.fetchone.return_value = user_contact_row
        return proxy

    mock_sl, mock_sess = _build_mock_session(_execute)

    with patch("aria.tools.crm_tools.SessionLocal", mock_sl), \
         patch("aria.tools.crm_tools.asyncio.to_thread", _sync_to_thread):
        from aria.tools.crm_tools import CRMTools
        tools = CRMTools()
        result = await tools.resolve_contact("mike", "org-1")

    assert result is not None
    assert result["type"] == "user"
    assert result["name"] == "Mike Taylor"
    assert result["email"] == "mike@company.com"


@pytest.mark.asyncio
async def test_resolve_contact_returns_none_when_not_found():
    """Neither leads nor users match — returns None."""
    def _execute(stmt, params=None):
        proxy = MagicMock()
        proxy.fetchone.return_value = None
        return proxy

    mock_sl, mock_sess = _build_mock_session(_execute)

    with patch("aria.tools.crm_tools.SessionLocal", mock_sl), \
         patch("aria.tools.crm_tools.asyncio.to_thread", _sync_to_thread):
        from aria.tools.crm_tools import CRMTools
        tools = CRMTools()
        result = await tools.resolve_contact("ghost", "org-1")

    assert result is None


# ===========================================================================
# Multi-tenant isolation
# ===========================================================================

@pytest.mark.asyncio
async def test_get_borrower_passes_org_id_in_query():
    """Verify org_id is bound as a parameter in every leads query."""
    captured_params = []

    def _execute(stmt, params=None):
        if params:
            captured_params.append(dict(params))
        proxy = MagicMock()
        proxy.fetchone.return_value = None
        return proxy

    mock_sl, mock_sess = _build_mock_session(_execute)

    with patch("aria.tools.crm_tools.SessionLocal", mock_sl), \
         patch("aria.tools.crm_tools.asyncio.to_thread", _sync_to_thread):
        from aria.tools.crm_tools import CRMTools
        tools = CRMTools()
        await tools.get_borrower("test@example.com", "org-TENANT-42")

    # Non-numeric identifier: name query + email query (2 calls minimum)
    assert len(captured_params) >= 2
    for params in captured_params:
        assert params.get("org") == "org-TENANT-42", (
            f"org_id missing or wrong in query params: {params}"
        )


@pytest.mark.asyncio
async def test_get_active_loan_passes_org_id_in_query():
    """Verify org_id is bound in active loan queries."""
    captured_params = []

    def _execute(stmt, params=None):
        if params:
            captured_params.append(dict(params))
        proxy = MagicMock()
        proxy.fetchone.return_value = None
        return proxy

    mock_sl, mock_sess = _build_mock_session(_execute)

    with patch("aria.tools.crm_tools.SessionLocal", mock_sl), \
         patch("aria.tools.crm_tools.asyncio.to_thread", _sync_to_thread):
        from aria.tools.crm_tools import CRMTools
        tools = CRMTools()
        await tools.get_active_loan(1, "org-TENANT-99")

    # Both active and fallback queries should include org
    assert len(captured_params) >= 1
    for params in captured_params:
        assert params.get("org") == "org-TENANT-99", (
            f"org_id missing or wrong in loan query params: {params}"
        )


@pytest.mark.asyncio
async def test_resolve_contact_user_query_includes_org_id():
    """When resolve_contact falls through to user search, org_id is included."""
    captured_params = []

    def _execute(stmt, params=None):
        if params:
            captured_params.append(dict(params))
        proxy = MagicMock()
        proxy.fetchone.return_value = None
        return proxy

    mock_sl, mock_sess = _build_mock_session(_execute)

    with patch("aria.tools.crm_tools.SessionLocal", mock_sl), \
         patch("aria.tools.crm_tools.asyncio.to_thread", _sync_to_thread):
        from aria.tools.crm_tools import CRMTools
        tools = CRMTools()
        await tools.resolve_contact("ghost", "org-ISOLATION")

    # The last captured params should be from the user query in resolve_contact
    user_query_params = captured_params[-1]
    assert user_query_params.get("org") == "org-ISOLATION", (
        f"org_id missing from user search query: {user_query_params}"
    )


# ===========================================================================
# _lead_to_dict helper
# ===========================================================================

def test_lead_to_dict_extracts_last_name():
    """_lead_to_dict splits full name to get last_name."""
    from aria.tools.crm_tools import _lead_to_dict
    row = _make_lead_row(name="Maria Elena Garcia")
    result = _lead_to_dict(row)
    assert result["last_name"] == "Garcia"


def test_lead_to_dict_handles_none_name():
    """_lead_to_dict handles None name gracefully."""
    from aria.tools.crm_tools import _lead_to_dict
    row = _make_lead_row(name=None, loan_amount=None)
    result = _lead_to_dict(row)
    assert result["full_name"] == ""
    assert result["last_name"] == ""
    assert result["loan_amount"] == 0
