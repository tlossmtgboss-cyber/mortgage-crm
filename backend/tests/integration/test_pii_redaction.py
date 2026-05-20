"""
Integration tests for PII masking and redaction.

Covers schemas.pii_masking (mask_ssn, mask_email, mask_phone, mask_dob,
mask_tax_id) and middleware.pii_log_filter (log redaction patterns).
"""
from __future__ import annotations

import importlib.util
import logging
import sys
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


_mask = _load("_pa_pii_mask", "schemas/pii_masking.py")
_filter = _load("_pa_pii_filter", "middleware/pii_log_filter.py")


# ---------------------------------------------------------------------------
# SSN masking
# ---------------------------------------------------------------------------

def test_mask_ssn_full_input():
    assert _mask.mask_ssn("123-45-6789") == "***-**-6789"


def test_mask_ssn_no_dashes():
    assert _mask.mask_ssn("123456789") == "***-**-6789"


def test_mask_ssn_none_passthrough():
    assert _mask.mask_ssn(None) is None


# ---------------------------------------------------------------------------
# Email masking
# ---------------------------------------------------------------------------

def test_mask_email_long_local():
    masked = _mask.mask_email("johndoe@example.com")
    assert masked.endswith("@example.com")
    assert masked.startswith("j")
    assert "johndoe" not in masked


def test_mask_email_short_local():
    masked = _mask.mask_email("jd@example.com")
    assert "example.com" in masked
    assert masked != "jd@example.com"


def test_mask_email_no_at_passthrough():
    assert _mask.mask_email("not-an-email") == "not-an-email"


# ---------------------------------------------------------------------------
# Phone masking
# ---------------------------------------------------------------------------

def test_mask_phone_us_format():
    assert _mask.mask_phone("(555) 123-4567") == "(***) ***-4567"


def test_mask_phone_plain_digits():
    assert _mask.mask_phone("5551234567") == "(***) ***-4567"


# ---------------------------------------------------------------------------
# DOB masking
# ---------------------------------------------------------------------------

def test_mask_dob_iso_keeps_year():
    masked = _mask.mask_dob("1990-05-14")
    assert masked.startswith("1990")
    assert "05" not in masked.split("1990")[1]


def test_mask_dob_us_keeps_year():
    assert _mask.mask_dob("05/14/1990") == "**/**/1990"


# ---------------------------------------------------------------------------
# Log filter redaction
# ---------------------------------------------------------------------------

def test_log_filter_redacts_ssn_in_message():
    record = logging.LogRecord(
        name="t", level=logging.INFO, pathname="x", lineno=1,
        msg="User SSN 123-45-6789 detected", args=None, exc_info=None,
    )
    filt = _filter.PIIRedactionFilter()
    filt.filter(record)
    assert "123-45-6789" not in record.msg
    assert "6789" in record.msg  # last 4 preserved


def test_log_filter_redacts_credit_card():
    record = logging.LogRecord(
        name="t", level=logging.INFO, pathname="x", lineno=1,
        msg="Card 4111-1111-1111-1234 charged", args=None, exc_info=None,
    )
    filt = _filter.PIIRedactionFilter()
    filt.filter(record)
    assert "4111-1111-1111" not in record.msg


def test_log_filter_redacts_routing_keyword():
    record = logging.LogRecord(
        name="t", level=logging.INFO, pathname="x", lineno=1,
        msg="routing 123456789 used", args=None, exc_info=None,
    )
    filt = _filter.PIIRedactionFilter()
    filt.filter(record)
    assert "123456789" not in record.msg


def test_log_filter_unicode_passthrough():
    record = logging.LogRecord(
        name="t", level=logging.INFO, pathname="x", lineno=1,
        msg="Café résumé — no PII here", args=None, exc_info=None,
    )
    filt = _filter.PIIRedactionFilter()
    assert filt.filter(record) is True
    assert "Café" in record.msg
