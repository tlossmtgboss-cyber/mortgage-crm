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
