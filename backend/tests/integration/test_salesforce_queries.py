"""
Unit-style integration tests for the Salesforce SOQL helpers.

Targets backend/services/salesforce/_queries.py — SAFE_SOQL_IDENTIFIER regex,
identifier validation, string + email sanitization (injection guard).
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


pytestmark = pytest.mark.integration


_BACKEND_DIR = Path(__file__).resolve().parents[2]


def _load_queries():
    target = _BACKEND_DIR / "services" / "salesforce" / "_queries.py"
    if not target.exists():
        pytest.skip("salesforce/_queries.py missing")
    spec = importlib.util.spec_from_file_location("_perennia_sf_queries", str(target))
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


_q = _load_queries()


# ---------------------------------------------------------------------------
# Test 1: Standard Salesforce identifiers pass validation
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "ident", ["Account", "Opportunity", "Lead", "Contact", "Id", "Name"]
)
def test_standard_identifiers_validated(ident):
    assert _q._validate_soql_identifier(ident) == ident


# ---------------------------------------------------------------------------
# Test 2: Custom __c fields pass validation
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "ident", ["My_Field__c", "Custom__c", "Lead_Source__c", "Branch__c"]
)
def test_custom_c_fields_validated(ident):
    assert _q._validate_soql_identifier(ident) == ident


# ---------------------------------------------------------------------------
# Test 3: SOQL injection attempts in identifier are rejected
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "bad",
    [
        "Account WHERE 1=1",            # space + clause
        "Account'; DROP",                # quote + semicolon
        "Account OR 1=1",                # spaces
        "Account--comment",              # SQL comment
        "1Account",                      # starts with digit
        "Account-Name",                  # hyphen
        "",                              # empty string
    ],
)
def test_injection_identifiers_rejected(bad):
    with pytest.raises(ValueError):
        _q._validate_soql_identifier(bad)


# ---------------------------------------------------------------------------
# Test 4: SAFE_SOQL_IDENTIFIER regex compiles and is anchored
# ---------------------------------------------------------------------------

def test_regex_anchored_and_compiled():
    # Pattern must be anchored at both ends — otherwise "Account; DROP" would
    # match the "Account" prefix and bypass the check.
    assert _q.SAFE_SOQL_IDENTIFIER.pattern.startswith("^")
    assert _q.SAFE_SOQL_IDENTIFIER.pattern.endswith("$")


# ---------------------------------------------------------------------------
# Test 5: SOQL string sanitization escapes single quotes
# ---------------------------------------------------------------------------

def test_sanitize_soql_string_escapes_quotes():
    out = _q._sanitize_soql_string("O'Brien")
    # Must escape the apostrophe so SOQL doesn't treat it as a terminator
    assert "\\'" in out


# ---------------------------------------------------------------------------
# Test 6: SOQL string sanitization escapes backslashes BEFORE quotes
# ---------------------------------------------------------------------------

def test_sanitize_soql_string_escapes_backslash():
    out = _q._sanitize_soql_string("path\\with\\slash")
    # Both backslashes should be doubled
    assert "\\\\" in out


# ---------------------------------------------------------------------------
# Test 7: Control characters cause sanitizer to return empty
# ---------------------------------------------------------------------------

def test_sanitize_soql_string_rejects_control_chars():
    assert _q._sanitize_soql_string("hello\x00world") == ""
    assert _q._sanitize_soql_string("line1\x1fline2") == ""


# ---------------------------------------------------------------------------
# Test 8: Email sanitizer accepts well-formed addresses, rejects junk
# ---------------------------------------------------------------------------

def test_sanitize_soql_email_validates_format():
    # Valid email passes through sanitization
    assert _q._sanitize_soql_email("user@example.com") == "user@example.com"
    # Missing @ → rejected
    assert _q._sanitize_soql_email("not-an-email") == ""
    # Missing TLD → rejected
    assert _q._sanitize_soql_email("user@no-tld") == ""
    # Empty / non-string → empty
    assert _q._sanitize_soql_email("") == ""
    assert _q._sanitize_soql_email(None) == ""  # type: ignore[arg-type]
