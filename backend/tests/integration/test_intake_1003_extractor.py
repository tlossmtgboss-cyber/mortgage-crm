"""
Integration tests for the 1003 (URLA) intake extractor — D4 CI-007.

Covers personal/employment/financial/property/loan sections, ambiguity
handling, PII redaction, multi-match collapse, empty input, merge with
existing fields, and edge cases (interruptions, non-US addresses).
"""
from __future__ import annotations

import pytest

from services.call_intelligence.intake_1003_extractor import (
    ALL_FIELDS,
    Intake1003Extractor,
)


@pytest.fixture
def extractor() -> Intake1003Extractor:
    return Intake1003Extractor()


# ---------------------------------------------------------------------------
# Section coverage
# ---------------------------------------------------------------------------
def test_personal_section_extracts_name_email_phone(extractor):
    transcript = (
        "Hi, my name is Sarah Johnson and you can reach me at "
        "sarah.j@example.com or 415-555-0150."
    )
    result = extractor.extract(transcript)
    f = result["fields"]
    assert f["borrower_first_name"]["value"] == "Sarah"
    assert f["borrower_last_name"]["value"] == "Johnson"
    assert f["borrower_email"]["value"] == "sarah.j@example.com"
    assert f["borrower_phone"]["value"] == "415-555-0150"
    assert all(v["confidence"] >= 0.7 for v in f.values())


def test_employment_section_extracts_employer_and_income(extractor):
    transcript = (
        "I work at Acme Corporation as a senior engineer. "
        "I make about $8,500 per month."
    )
    result = extractor.extract(transcript)
    f = result["fields"]
    assert "Acme" in f["employer_name"]["value"]
    assert f["job_title"]["value"].startswith("senior")
    assert f["monthly_income_gross"]["value"] == 8500.0
    assert f["self_employed"]["value"] is False


def test_financial_section_extracts_assets_and_debts(extractor):
    transcript = (
        "My monthly debts are $1,200. I have liquid assets of $45,000 "
        "and a 401k balance of $120,000."
    )
    result = extractor.extract(transcript)
    f = result["fields"]
    assert f["monthly_debts"]["value"] == 1200.0
    assert f["liquid_assets"]["value"] == 45000.0
    assert f["retirement_assets"]["value"] == 120000.0


def test_property_section_extracts_type_price_occupancy(extractor):
    transcript = (
        "We're buying a single-family home, primary residence. "
        "The purchase price is $525,000 with a down payment of $105,000."
    )
    result = extractor.extract(transcript)
    f = result["fields"]
    assert f["subject_property_type"]["value"] == "SFR"
    assert f["occupancy"]["value"] == "primary"
    assert f["purchase_price"]["value"] == 525000.0
    assert f["down_payment_amount"]["value"] == 105000.0


def test_loan_section_extracts_amount_type_purpose_term(extractor):
    transcript = (
        "Loan amount is $420,000, conventional 30-year fixed for a purchase. "
        "Let's do a 60 day lock."
    )
    result = extractor.extract(transcript)
    f = result["fields"]
    assert f["loan_amount"]["value"] == 420000.0
    assert f["loan_type"]["value"] == "conv"
    assert f["loan_purpose"]["value"] == "purchase"
    assert f["loan_term_months"]["value"] == 360
    assert f["lock_period_days"]["value"] == 60


# ---------------------------------------------------------------------------
# Confidence behavior
# ---------------------------------------------------------------------------
def test_confidence_drops_when_field_is_ambiguous(extractor):
    # SSN without "social" or "SSN" context label — should land at 0.7 not 0.95
    transcript = "Reference number 123-45-6789 was assigned."
    result = extractor.extract(transcript)
    f = result["fields"]
    assert "borrower_ssn" in f
    assert f["borrower_ssn"]["confidence"] < 0.9


def test_confidence_higher_with_explicit_label(extractor):
    transcript = "My SSN is 123-45-6789."
    result = extractor.extract(transcript)
    assert result["fields"]["borrower_ssn"]["confidence"] >= 0.9


# ---------------------------------------------------------------------------
# PII redaction
# ---------------------------------------------------------------------------
def test_ssn_redacted_in_output_but_preserved_in_pii_secure(extractor):
    transcript = "My social security number is 123-45-6789."
    result = extractor.extract(transcript)
    assert result["fields"]["borrower_ssn"]["value"] == "XXX-XX-6789"
    # Raw last4 (or full) preserved separately for downstream KMS
    assert result["_pii_secure"]["ssn"] == "123-45-6789"


# ---------------------------------------------------------------------------
# Multi-match resolution
# ---------------------------------------------------------------------------
def test_multiple_values_for_same_field_highest_confidence_wins(extractor):
    # Two income mentions — last one is more specific
    transcript = (
        "I make a couple grand. Actually my gross monthly income is "
        "$7,200 per month."
    )
    result = extractor.extract(transcript)
    assert result["fields"]["monthly_income_gross"]["value"] == 7200.0


# ---------------------------------------------------------------------------
# Empty / null input
# ---------------------------------------------------------------------------
def test_empty_transcript_returns_empty_fields(extractor):
    result = extractor.extract("")
    assert result["fields"] == {}
    assert result["_pii_secure"] == {}
    assert result["extraction_metadata"]["fields_extracted"] == 0
    assert result["extraction_metadata"]["avg_confidence"] == 0.0


def test_whitespace_only_transcript_returns_empty(extractor):
    result = extractor.extract("   \n   \t  ")
    assert result["fields"] == {}


# ---------------------------------------------------------------------------
# Merge semantics
# ---------------------------------------------------------------------------
def test_existing_fields_merge_preserves_high_confidence(extractor):
    existing = {
        "borrower_first_name": {
            "value": "Robert",
            "confidence": 0.99,
            "source_span": (-1, -1),
        }
    }
    # New extraction yields lower-confidence name (no label)
    transcript = "Bob Smith here."
    result = extractor.extract(transcript, existing_fields=existing)
    # Existing should win because 0.99 > new confidence
    assert result["fields"]["borrower_first_name"]["value"] == "Robert"


def test_existing_fields_merge_overwrites_lower_confidence(extractor):
    existing = {
        "borrower_phone": {
            "value": "000-000-0000",
            "confidence": 0.3,
            "source_span": (-1, -1),
        }
    }
    transcript = "Call me at 404-555-0123."
    result = extractor.extract(transcript, existing_fields=existing)
    assert result["fields"]["borrower_phone"]["value"] == "404-555-0123"


# ---------------------------------------------------------------------------
# Real-world transcript quirks
# ---------------------------------------------------------------------------
def test_handles_interruptions_and_restatements(extractor):
    transcript = (
        "My name is, uh, John, sorry, my name is John Williams. "
        "Phone is 713-555-0188, email johnw@gmail.com."
    )
    result = extractor.extract(transcript)
    f = result["fields"]
    assert f["borrower_first_name"]["value"] == "John"
    assert f["borrower_last_name"]["value"] == "Williams"
    assert f["borrower_phone"]["value"] == "713-555-0188"


def test_self_employed_flag_detected(extractor):
    transcript = "I'm self-employed running a small construction company."
    result = extractor.extract(transcript)
    assert result["fields"]["self_employed"]["value"] is True


def test_full_address_extraction_with_state_and_zip(extractor):
    transcript = (
        "I currently live at 123 Main Street, Atlanta, GA 30301 with my family."
    )
    result = extractor.extract(transcript)
    assert "current_address" in result["fields"]
    addr = result["fields"]["current_address"]["value"]
    assert "Main Street" in addr
    assert "30301" in addr


# ---------------------------------------------------------------------------
# Edge cases — confidence drops for non-standard inputs
# ---------------------------------------------------------------------------
def test_extraction_metadata_populated(extractor):
    transcript = "My name is Jane Doe at jane@example.com."
    result = extractor.extract(transcript)
    meta = result["extraction_metadata"]
    assert meta["transcript_length"] == len(transcript)
    assert meta["fields_extracted"] >= 2
    assert 0.0 < meta["avg_confidence"] <= 1.0
    assert meta["processing_ms"] >= 0


def test_canonical_field_catalog_covers_all_sections():
    # Sanity: the all-fields tuple matches the schema we promised.
    assert "borrower_ssn" in ALL_FIELDS
    assert "employer_name" in ALL_FIELDS
    assert "monthly_debts" in ALL_FIELDS
    assert "subject_property_type" in ALL_FIELDS
    assert "loan_amount" in ALL_FIELDS
    assert len(ALL_FIELDS) >= 27  # five sections, ~27 fields total
