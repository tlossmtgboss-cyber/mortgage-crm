"""
Integration tests for backend/validation/common.py and backend/utils/validators.py.

Covers email, phone, SSN, NMLS, loan number, UUID, loan amount, interest rate,
credit score validation — canonical formats accepted, malformed inputs rejected.
"""
from __future__ import annotations

import importlib.util
import sys
from decimal import Decimal
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration

_BACKEND_DIR = Path(__file__).resolve().parents[2]


def _load(name: str, rel_path: str):
    target = _BACKEND_DIR / rel_path
    if not target.exists():
        pytest.skip(f"{rel_path} missing")
    spec = importlib.util.spec_from_file_location(name, str(target))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


_common = _load("_pa_validation_common", "validation/common.py")
_utils = _load("_pa_utils_validators", "utils/validators.py")


# ---------------------------------------------------------------------------
# Email
# ---------------------------------------------------------------------------

def test_email_canonical_accepted():
    assert _common.validate_email_format("john@example.com") == "john@example.com"


def test_email_uppercase_normalized():
    assert _common.validate_email_format("John@Example.COM") == "john@example.com"


def test_email_missing_raises():
    with pytest.raises(ValueError):
        _common.validate_email_format("")
    with pytest.raises(ValueError):
        _common.validate_email_format(None)


def test_email_malformed_double_dot_rejected():
    with pytest.raises(ValueError):
        _common.validate_email_format("john..doe@example.com")


def test_email_no_at_rejected():
    with pytest.raises(ValueError):
        _common.validate_email_format("notanemail")


# ---------------------------------------------------------------------------
# Phone
# ---------------------------------------------------------------------------

def test_phone_e164_accepted():
    assert _common.validate_phone_format("+15551234567") == "+15551234567"


def test_phone_us_10digit_prepends_country_code():
    assert _common.validate_phone_format("(555) 123-4567") == "+15551234567"


def test_phone_too_short_rejected():
    with pytest.raises(ValueError):
        _common.validate_phone_format("123")


# ---------------------------------------------------------------------------
# SSN
# ---------------------------------------------------------------------------

def test_ssn_9digit_accepted():
    assert _common.validate_ssn("123456789") == "123-45-6789"


def test_ssn_dashes_normalized():
    assert _common.validate_ssn("111-22-3333") == "111-22-3333"


def test_ssn_invalid_area_rejected():
    with pytest.raises(ValueError):
        _common.validate_ssn("666-12-3456")


def test_ssn_too_short_rejected():
    with pytest.raises(ValueError):
        _common.validate_ssn("12345")


# ---------------------------------------------------------------------------
# NMLS
# ---------------------------------------------------------------------------

def test_nmls_5digit_accepted():
    assert _utils.validate_nmls("12345") == "12345"


def test_nmls_strips_hash_prefix():
    assert _utils.validate_nmls("#123456") == "123456"


def test_nmls_strips_leading_zeros():
    assert _utils.validate_nmls("00012345") == "12345"


def test_nmls_too_short_rejected():
    with pytest.raises(ValueError):
        _utils.validate_nmls("123")


def test_nmls_too_long_rejected():
    with pytest.raises(ValueError):
        _utils.validate_nmls("1234567890123")


def test_nmls_non_numeric_rejected():
    with pytest.raises(ValueError):
        _utils.validate_nmls("abcdef")


def test_nmls_none_returns_none():
    assert _utils.validate_nmls(None) is None
    assert _utils.validate_nmls("") is None


# ---------------------------------------------------------------------------
# Loan amount
# ---------------------------------------------------------------------------

def test_loan_amount_within_range():
    result = _common.validate_loan_amount_decimal(250000)
    assert result == Decimal("250000.00")


def test_loan_amount_too_small_rejected():
    with pytest.raises(ValueError):
        _common.validate_loan_amount_decimal(500)


def test_loan_amount_too_large_rejected():
    with pytest.raises(ValueError):
        _common.validate_loan_amount_decimal(100_000_000)


# ---------------------------------------------------------------------------
# Interest rate
# ---------------------------------------------------------------------------

def test_interest_rate_valid():
    # validate_interest_rate normalizes to decimal (e.g. 6.75% -> 0.0675)
    result = _common.validate_interest_rate("6.75")
    assert isinstance(result, Decimal)
    assert Decimal("0") < result < Decimal("1")


def test_interest_rate_too_high_rejected():
    with pytest.raises(ValueError):
        _common.validate_interest_rate(50.0)


# ---------------------------------------------------------------------------
# Loan number
# ---------------------------------------------------------------------------

def test_loan_number_alphanumeric_accepted():
    assert _common.validate_loan_number("LOAN-2026-001") == "LOAN-2026-001"


def test_loan_number_empty_rejected():
    with pytest.raises(ValueError):
        _common.validate_loan_number("")


# ---------------------------------------------------------------------------
# UUID
# ---------------------------------------------------------------------------

def test_uuid_valid():
    uid = "550e8400-e29b-41d4-a716-446655440000"
    assert _common.validate_uuid(uid) == uid


def test_uuid_invalid_rejected():
    with pytest.raises(ValueError):
        _common.validate_uuid("not-a-uuid")


# ---------------------------------------------------------------------------
# Credit score
# ---------------------------------------------------------------------------

def test_credit_score_in_range():
    assert _common.validate_credit_score(720) == 720


def test_credit_score_too_low_rejected():
    with pytest.raises(ValueError):
        _common.validate_credit_score(200)


def test_credit_score_too_high_rejected():
    with pytest.raises(ValueError):
        _common.validate_credit_score(900)
