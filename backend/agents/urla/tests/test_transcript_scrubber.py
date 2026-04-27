"""Tests for URLA transcript PII scrubber."""
import pytest
from datetime import datetime, timezone

from agents.urla.transcript_scrubber import scrub_realtime, scrub_post_call
from agents.urla.models import CallTranscriptEntry


class TestScrubRealtime:
    def test_full_ssn_dashes(self):
        result = scrub_realtime("my SSN is 219-09-9999")
        assert "219" not in result
        assert "[SSN REDACTED]" in result

    def test_full_ssn_spaces(self):
        result = scrub_realtime("219 09 9999")
        assert "[SSN REDACTED]" in result

    def test_contextual_ssn(self):
        result = scrub_realtime("my social security number is 219 09 9999")
        assert "[SSN REDACTED]" in result

    def test_spoken_digits(self):
        result = scrub_realtime(
            "two one nine zero nine nine nine nine nine"
        )
        assert "[SSN REDACTED]" in result

    def test_spoken_digits_with_filler(self):
        result = scrub_realtime(
            "two one nine uh zero nine um nine nine nine nine"
        )
        assert "[SSN REDACTED]" in result

    def test_does_not_scrub_short_numbers(self):
        result = scrub_realtime("my zip is 29401")
        assert "29401" in result

    def test_does_not_scrub_dollar_amounts(self):
        result = scrub_realtime("the loan is $425,000")
        assert "$425,000" in result

    def test_preserves_normal_text(self):
        text = "I work at Acme Corporation as a software engineer"
        assert scrub_realtime(text) == text


class TestScrubPostCall:
    def _entry(self, text: str) -> CallTranscriptEntry:
        return CallTranscriptEntry(
            speaker="borrower",
            text=text,
            timestamp=datetime.now(timezone.utc),
        )

    def test_scrubs_dob_context(self):
        entries = [self._entry("I was born on January 15th, 1990")]
        scrub_post_call(entries)
        assert "[DOB REDACTED]" in entries[0].text

    def test_scrubs_dob_numeric(self):
        entries = [self._entry("01/15/1990 is my birthday")]
        scrub_post_call(entries)
        assert "[DOB REDACTED]" in entries[0].text

    def test_scrubs_account_context(self):
        entries = [self._entry("my account number is 1234567890")]
        scrub_post_call(entries)
        assert "[ACCOUNT REDACTED]" in entries[0].text

    def test_includes_layer1_patterns(self):
        entries = [self._entry("SSN is 219-09-9999")]
        scrub_post_call(entries)
        assert "[SSN REDACTED]" in entries[0].text

    def test_preserves_normal_text(self):
        entries = [self._entry("I want to buy a house")]
        scrub_post_call(entries)
        assert entries[0].text == "I want to buy a house"

    # ── M6: _LONG_DIGITS monetary false-positive tests ──────────────

    def test_dollar_sign_prefix_not_redacted(self):
        """$1234567890 should NOT be redacted as an account number."""
        entries = [self._entry("the property is worth $1234567890")]
        scrub_post_call(entries, current_section="SECTION_4A")
        assert "1234567890" in entries[0].text
        assert "[ACCOUNT REDACTED]" not in entries[0].text

    def test_monetary_keyword_value_not_redacted(self):
        """'property value 1234567890' should NOT be redacted."""
        entries = [self._entry("property value 1234567890")]
        scrub_post_call(entries, current_section="SECTION_4A")
        assert "1234567890" in entries[0].text
        assert "[ACCOUNT REDACTED]" not in entries[0].text

    def test_monetary_keyword_balance_not_redacted(self):
        """'current balance 1234567890' should NOT be redacted."""
        entries = [self._entry("current balance 1234567890")]
        scrub_post_call(entries, current_section="SECTION_4A")
        assert "1234567890" in entries[0].text
        assert "[ACCOUNT REDACTED]" not in entries[0].text

    def test_account_number_still_redacted(self):
        """'account number 1234567890' should still be redacted (by _ACCOUNT_CONTEXT)."""
        entries = [self._entry("account number 1234567890")]
        scrub_post_call(entries, current_section="SECTION_4A")
        assert "[ACCOUNT REDACTED]" in entries[0].text

    def test_bare_long_digits_still_redacted_in_pii_section(self):
        """Bare long digits without monetary context should still be redacted."""
        entries = [self._entry("please note 1234567890123")]
        scrub_post_call(entries, current_section="SECTION_2")
        assert "[ACCOUNT REDACTED]" in entries[0].text
        assert "1234567890123" not in entries[0].text

    def test_bare_long_digits_not_redacted_outside_pii_section(self):
        """Long digits outside PII-sensitive sections should not be redacted."""
        entries = [self._entry("reference 1234567890123")]
        scrub_post_call(entries, current_section="SECTION_7")
        assert "1234567890123" in entries[0].text
