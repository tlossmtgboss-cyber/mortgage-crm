"""
Tests for PII Redaction in Call Intelligence.

Verifies that sensitive borrower data is properly redacted
before being sent to external LLM APIs.
"""

import pytest
from services.call_intelligence.pii_utils import (
    redact_ssn,
    redact_dob,
    redact_phone,
    redact_email,
    redact_credit_card,
    redact_bank_account,
    redact_transcript_for_llm,
    get_redaction_warning_for_llm,
)


class TestSSNRedaction:
    """Tests for SSN redaction."""

    def test_redact_full_ssn_with_dashes(self):
        """Test redacting SSN in XXX-XX-XXXX format."""
        text = "My social security number is 123-45-6789"
        result = redact_ssn(text)
        assert "123-45" not in result
        assert "***-**-6789" in result

    def test_redact_full_ssn_with_spaces(self):
        """Test redacting SSN in XXX XX XXXX format."""
        text = "SSN is 123 45 6789"
        result = redact_ssn(text)
        assert "123 45" not in result
        assert "6789" in result

    def test_redact_full_ssn_no_separator(self):
        """Test redacting SSN in XXXXXXXXX format."""
        text = "Social is 123456789"
        result = redact_ssn(text)
        assert "123456789" not in result
        assert "6789" in result

    def test_multiple_ssns(self):
        """Test redacting multiple SSNs in same text."""
        text = "Borrower SSN 123-45-6789 and co-borrower 987-65-4321"
        result = redact_ssn(text)
        assert "123-45" not in result
        assert "987-65" not in result
        assert "6789" in result
        assert "4321" in result

    def test_no_ssn_unchanged(self):
        """Test text without SSN is unchanged."""
        text = "My name is John Smith and I work at Acme Corp"
        result = redact_ssn(text)
        assert result == text


class TestDOBRedaction:
    """Tests for date of birth redaction."""

    def test_redact_dob_with_context(self):
        """Test redacting DOB when preceded by birth-related words."""
        text = "I was born on 03/15/1985"
        result = redact_dob(text)
        assert "03/15/1985" not in result
        assert "[DOB REDACTED]" in result

    def test_redact_written_date(self):
        """Test redacting written date format."""
        text = "Date of birth is March 15, 1985"
        result = redact_dob(text)
        assert "March 15, 1985" not in result or "[DOB REDACTED]" in result

    def test_recent_date_not_redacted(self):
        """Test that recent dates (likely transaction dates) are not redacted."""
        text = "The closing date is 01/15/2025"
        result = redact_dob(text)
        # 2025 is not in birth date range, should not be redacted
        assert "01/15/2025" in result or "[DOB REDACTED]" not in result


class TestPhoneRedaction:
    """Tests for phone number redaction."""

    def test_redact_phone_with_dashes(self):
        """Test redacting phone in XXX-XXX-XXXX format."""
        text = "Call me at 555-123-4567"
        result = redact_phone(text)
        assert "555-123-4567" not in result
        assert "[PHONE]" in result

    def test_redact_phone_with_parens(self):
        """Test redacting phone in (XXX) XXX-XXXX format."""
        text = "My number is (555) 123-4567"
        result = redact_phone(text)
        assert "123-4567" not in result
        assert "[PHONE]" in result

    def test_redact_phone_no_separator(self):
        """Test redacting phone in XXXXXXXXXX format."""
        text = "Phone 5551234567"
        result = redact_phone(text)
        assert "5551234567" not in result
        assert "[PHONE]" in result


class TestEmailRedaction:
    """Tests for email redaction."""

    def test_redact_simple_email(self):
        """Test redacting simple email address."""
        text = "Email me at john.smith@example.com"
        result = redact_email(text)
        assert "john.smith@example.com" not in result
        assert "[EMAIL]" in result

    def test_redact_complex_email(self):
        """Test redacting email with plus and subdomain."""
        text = "Contact john+mortgage@mail.company.co.uk"
        result = redact_email(text)
        assert "@mail.company.co.uk" not in result
        assert "[EMAIL]" in result


class TestCreditCardRedaction:
    """Tests for credit card redaction."""

    def test_redact_visa(self):
        """Test redacting Visa card number."""
        text = "Card number 4111-1111-1111-1234"
        result = redact_credit_card(text)
        assert "4111-1111-1111" not in result
        assert "1234" in result

    def test_redact_amex(self):
        """Test redacting Amex card number."""
        text = "Amex 371234567890125"
        result = redact_credit_card(text)
        assert "371234567890" not in result


class TestBankAccountRedaction:
    """Tests for bank account redaction."""

    def test_redact_account_number(self):
        """Test redacting account number with keyword."""
        text = "Account number 12345678901"
        result = redact_bank_account(text)
        assert "12345678901" not in result or "****" in result


class TestTranscriptRedaction:
    """Tests for full transcript redaction."""

    def test_redact_transcript_multiple_pii(self):
        """Test redacting transcript with multiple PII types."""
        transcript = """
        Loan Officer: Can I get your social security number?
        Borrower: Sure, it's 123-45-6789
        Loan Officer: And your date of birth?
        Borrower: March 15, 1985
        Loan Officer: Best phone number to reach you?
        Borrower: 555-123-4567
        Loan Officer: And email?
        Borrower: john.smith@example.com
        """

        redacted, stats = redact_transcript_for_llm(transcript)

        # Verify SSN is redacted
        assert "123-45" not in redacted
        assert "6789" in redacted  # Last 4 preserved

        # Verify phone is redacted
        assert "555-123-4567" not in redacted
        assert "[PHONE]" in redacted

        # Verify email is redacted
        assert "john.smith@example.com" not in redacted
        assert "[EMAIL]" in redacted

        # Verify stats
        assert stats["ssn"] >= 1
        assert stats["phone"] >= 1
        assert stats["email"] >= 1
        assert stats["total"] >= 3

    def test_redact_transcript_no_pii(self):
        """Test transcript without PII returns unchanged."""
        transcript = """
        Loan Officer: How can I help you today?
        Borrower: I'm interested in buying a house.
        Loan Officer: Great! What price range are you looking at?
        Borrower: Around $400,000.
        """

        redacted, stats = redact_transcript_for_llm(transcript)

        assert stats["total"] == 0
        assert redacted.strip() == transcript.strip()

    def test_redact_transcript_preserves_names(self):
        """Test that names are preserved for extraction."""
        transcript = "Borrower: My name is John Smith and I work at Acme Corporation"

        redacted, stats = redact_transcript_for_llm(transcript)

        # Names should NOT be redacted
        assert "John Smith" in redacted
        assert "Acme Corporation" in redacted

    def test_redact_transcript_preserves_financial_data(self):
        """Test that non-PII financial data is preserved."""
        transcript = """
        Borrower: I make $120,000 per year
        Borrower: I have $50,000 in savings
        Borrower: The house costs $450,000
        """

        redacted, stats = redact_transcript_for_llm(transcript)

        # Financial amounts should be preserved
        assert "$120,000" in redacted
        assert "$50,000" in redacted
        assert "$450,000" in redacted


class TestRedactionWarning:
    """Tests for redaction warning message."""

    def test_warning_contains_placeholders(self):
        """Test warning explains redaction placeholders."""
        warning = get_redaction_warning_for_llm()

        assert "***-**-" in warning  # SSN placeholder
        assert "[DOB REDACTED]" in warning
        assert "[PHONE]" in warning
        assert "[EMAIL]" in warning

    def test_warning_mentions_confidence(self):
        """Test warning mentions confidence adjustment."""
        warning = get_redaction_warning_for_llm()

        assert "confidence" in warning.lower()


class TestRealWorldScenarios:
    """Tests for realistic mortgage call scenarios."""

    def test_prequal_call_redaction(self):
        """Test redaction of a realistic pre-qualification call."""
        transcript = """
        AI Loan Officer: Good morning! I'm here to help you with your mortgage pre-qualification. May I have your full name?
        Borrower: Yes, my name is Jennifer Martinez.
        AI Loan Officer: Thank you, Jennifer. And what's your date of birth?
        Borrower: It's April 22nd, 1988.
        AI Loan Officer: Great. For verification purposes, can you provide your social security number?
        Borrower: Sure, it's 456-78-9012.
        AI Loan Officer: Thank you. What's the best phone number to reach you?
        Borrower: My cell is 415-555-0199.
        AI Loan Officer: And your email address?
        Borrower: jennifer.martinez@gmail.com
        AI Loan Officer: Perfect. Now, let's talk about your employment. Where do you work?
        Borrower: I work at Google as a software engineer.
        AI Loan Officer: And what's your annual salary?
        Borrower: I make $185,000 base, plus about $50,000 in stock.
        """

        redacted, stats = redact_transcript_for_llm(transcript)

        # PII should be redacted
        assert "456-78" not in redacted
        assert "415-555-0199" not in redacted
        assert "jennifer.martinez@gmail.com" not in redacted

        # Non-PII should be preserved
        assert "Jennifer Martinez" in redacted
        assert "Google" in redacted
        assert "software engineer" in redacted
        assert "$185,000" in redacted
        assert "$50,000" in redacted

        # Stats should reflect redactions
        assert stats["ssn"] >= 1
        assert stats["phone"] >= 1
        assert stats["email"] >= 1

    def test_coborrower_call_redaction(self):
        """Test redaction when multiple borrowers share PII."""
        transcript = """
        Borrower: My social is 111-22-3333 and my wife's is 444-55-6666.
        Borrower: You can reach me at 555-111-2222 or her at 555-333-4444.
        Borrower: Our emails are john@email.com and jane@email.com.
        """

        redacted, stats = redact_transcript_for_llm(transcript)

        # All SSNs redacted
        assert "111-22" not in redacted
        assert "444-55" not in redacted

        # All phones redacted
        assert "555-111-2222" not in redacted
        assert "555-333-4444" not in redacted

        # All emails redacted
        assert "john@email.com" not in redacted
        assert "jane@email.com" not in redacted

        # Stats should show multiple
        assert stats["ssn"] >= 2
        assert stats["phone"] >= 2
        assert stats["email"] >= 2
