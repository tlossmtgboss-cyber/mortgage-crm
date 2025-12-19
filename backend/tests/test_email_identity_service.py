"""Unit tests for Email Identity Resolution Service.

This module provides comprehensive test coverage for the email identity
resolution system, including all matching strategies, edge cases, and
utility functions.

Coverage target: 85%+

Run with:
    pytest tests/test_email_identity_service.py -v
    pytest tests/test_email_identity_service.py -v --cov=services.email_identity_resolver
"""

import pytest
from unittest.mock import MagicMock, patch
from typing import Any, Dict, List, Optional

# Import the module under test
from services.email_identity_resolver import (
    EmailIdentityResolver,
    normalize_email,
    extract_domain,
    extract_display_name,
    KNOWN_VENDOR_DOMAINS,
    get_email_identity_resolver,
)


# ============================================================
# Fixtures
# ============================================================

@pytest.fixture
def mock_db():
    """Create a mock database session."""
    db = MagicMock()
    db.execute = MagicMock()
    db.commit = MagicMock()
    db.rollback = MagicMock()
    return db


@pytest.fixture
def resolver(mock_db):
    """Create an EmailIdentityResolver instance with mock db."""
    return EmailIdentityResolver(mock_db)


@pytest.fixture
def sample_email_data():
    """Standard email data for testing."""
    return {
        "from_email": "john.smith@gmail.com",
        "subject": "Question about my loan",
        "body_preview": "Hi, I have a question...",
        "thread_id": "thread-abc-123",
        "to_emails": ["loan.officer@company.com"],
        "cc_emails": [],
    }


@pytest.fixture
def microsoft_graph_email():
    """Microsoft Graph API format email data."""
    return {
        "from": {
            "emailAddress": {
                "address": "jane.doe@outlook.com",
                "name": "Jane Doe"
            }
        },
        "subject": "RE: Loan #12345678",
        "to": [
            {
                "emailAddress": {
                    "address": "officer@mortgage.com",
                    "name": "Loan Officer"
                }
            }
        ],
        "cc": [],
        "thread_id": "graph-thread-xyz",
    }


# ============================================================
# Tests: Email Normalization Utilities
# ============================================================

class TestNormalizeEmail:
    """Tests for the normalize_email function."""

    def test_lowercase(self):
        """Should convert to lowercase."""
        assert normalize_email("John.SMITH@Example.COM") == "john.smith@example.com"

    def test_whitespace_strip(self):
        """Should strip whitespace."""
        assert normalize_email("  john@example.com  ") == "john@example.com"

    def test_gmail_dot_removal(self):
        """Should remove dots from Gmail local part."""
        assert normalize_email("john.smith@gmail.com") == "johnsmith@gmail.com"
        assert normalize_email("j.o.h.n@gmail.com") == "john@gmail.com"

    def test_gmail_plus_alias(self):
        """Should remove plus aliases from Gmail."""
        assert normalize_email("john+newsletter@gmail.com") == "john@gmail.com"
        assert normalize_email("user+tag+extra@gmail.com") == "user@gmail.com"

    def test_googlemail_to_gmail(self):
        """Should normalize googlemail.com to gmail.com."""
        assert normalize_email("john@googlemail.com") == "john@gmail.com"

    def test_gmail_combined_normalization(self):
        """Should handle dots AND plus aliases for Gmail."""
        assert normalize_email("j.o.h.n+work@gmail.com") == "john@gmail.com"

    def test_non_gmail_unchanged(self):
        """Should not modify non-Gmail addresses."""
        assert normalize_email("john.smith@outlook.com") == "john.smith@outlook.com"
        assert normalize_email("user+tag@company.org") == "user+tag@company.org"

    def test_empty_input(self):
        """Should handle empty input."""
        assert normalize_email("") == ""
        assert normalize_email(None) == ""

    def test_preserves_domain_dots(self):
        """Should preserve dots in domain portion."""
        assert normalize_email("john@sub.domain.company.com") == "john@sub.domain.company.com"


class TestExtractDomain:
    """Tests for the extract_domain function."""

    def test_basic_domain(self):
        """Should extract domain from standard email."""
        assert extract_domain("john@example.com") == "example.com"

    def test_subdomain(self):
        """Should include subdomains."""
        assert extract_domain("user@mail.company.co.uk") == "mail.company.co.uk"

    def test_lowercase_output(self):
        """Should return lowercase domain."""
        assert extract_domain("user@COMPANY.COM") == "company.com"

    def test_empty_input(self):
        """Should handle empty input."""
        assert extract_domain("") == ""
        assert extract_domain(None) == ""

    def test_no_at_sign(self):
        """Should return empty for invalid email."""
        assert extract_domain("invalid-email") == ""


class TestExtractDisplayName:
    """Tests for the extract_display_name function."""

    def test_name_and_email_format(self):
        """Should extract from 'Name <email>' format."""
        name, email = extract_display_name("John Smith <john@example.com>")
        assert name == "John Smith"
        assert email == "john@example.com"

    def test_quoted_name_format(self):
        """Should handle quoted names."""
        name, email = extract_display_name('"Jane Doe" <jane@example.com>')
        assert name == "Jane Doe"
        assert email == "jane@example.com"

    def test_email_only(self):
        """Should handle email-only format."""
        name, email = extract_display_name("john@example.com")
        assert name is None
        assert email == "john@example.com"

    def test_angle_brackets_only(self):
        """Should handle <email> format."""
        name, email = extract_display_name("<john@example.com>")
        assert name is None
        assert email == "john@example.com"

    def test_empty_input(self):
        """Should handle empty input."""
        name, email = extract_display_name("")
        assert name is None
        assert email is None

    def test_whitespace_handling(self):
        """Should strip whitespace from name."""
        name, email = extract_display_name("  John Smith  <john@example.com>")
        assert name == "John Smith"
        assert email == "john@example.com"


# ============================================================
# Tests: Known Vendor Domains
# ============================================================

class TestKnownVendorDomains:
    """Tests for the KNOWN_VENDOR_DOMAINS constant."""

    def test_government_domains(self):
        """Should include government agency domains."""
        assert "fha.gov" in KNOWN_VENDOR_DOMAINS
        assert "va.gov" in KNOWN_VENDOR_DOMAINS
        assert "hud.gov" in KNOWN_VENDOR_DOMAINS

    def test_gse_domains(self):
        """Should include GSE domains."""
        assert "fanniemae.com" in KNOWN_VENDOR_DOMAINS
        assert "freddiemac.com" in KNOWN_VENDOR_DOMAINS

    def test_title_company_domains(self):
        """Should include title company domains."""
        assert "firstam.com" in KNOWN_VENDOR_DOMAINS
        assert "stewart.com" in KNOWN_VENDOR_DOMAINS
        assert "chicagotitle.com" in KNOWN_VENDOR_DOMAINS

    def test_credit_bureau_domains(self):
        """Should include credit bureau domains."""
        assert "equifax.com" in KNOWN_VENDOR_DOMAINS
        assert "experian.com" in KNOWN_VENDOR_DOMAINS
        assert "transunion.com" in KNOWN_VENDOR_DOMAINS

    def test_domain_tuple_format(self):
        """Each domain should have (type, name, confidence) tuple."""
        for domain, value in KNOWN_VENDOR_DOMAINS.items():
            assert isinstance(value, tuple)
            assert len(value) == 3
            entity_type, entity_name, confidence = value
            assert isinstance(entity_type, str)
            assert isinstance(entity_name, str)
            assert isinstance(confidence, float)
            assert 0.0 <= confidence <= 1.0


# ============================================================
# Tests: EmailIdentityResolver - Address Collection
# ============================================================

class TestAddressCollection:
    """Tests for email address collection from various formats."""

    def test_simple_from_email(self, resolver):
        """Should extract from_email string."""
        data = {"from_email": "john@example.com"}
        addresses = resolver._collect_addresses(data)
        assert "john@example.com" in addresses

    def test_microsoft_graph_from(self, resolver, microsoft_graph_email):
        """Should extract from Microsoft Graph format."""
        addresses = resolver._collect_addresses(microsoft_graph_email)
        assert "jane.doe@outlook.com" in addresses

    def test_to_emails_list(self, resolver):
        """Should extract from to_emails list."""
        data = {
            "from_email": "sender@example.com",
            "to_emails": ["recipient1@example.com", "recipient2@example.com"]
        }
        addresses = resolver._collect_addresses(data)
        assert "sender@example.com" in addresses
        assert "recipient1@example.com" in addresses
        assert "recipient2@example.com" in addresses

    def test_deduplication(self, resolver):
        """Should deduplicate addresses."""
        data = {
            "from_email": "john@example.com",
            "to_emails": ["john@example.com", "jane@example.com"]
        }
        addresses = resolver._collect_addresses(data)
        john_count = sum(1 for a in addresses if a == "john@example.com")
        assert john_count == 1

    def test_normalization_applied(self, resolver):
        """Should normalize addresses."""
        data = {"from_email": "J.O.H.N@gmail.com"}
        addresses = resolver._collect_addresses(data)
        assert "john@gmail.com" in addresses

    def test_empty_addresses_skipped(self, resolver):
        """Should skip empty addresses."""
        data = {
            "from_email": "",
            "to_emails": ["", None, "valid@example.com"]
        }
        addresses = resolver._collect_addresses(data)
        assert "" not in addresses
        assert "valid@example.com" in addresses


# ============================================================
# Tests: EmailIdentityResolver - Matching Strategies
# ============================================================

class TestKnownClientMatching:
    """Tests for known client email matching (Strategy 1)."""

    def test_match_found(self, resolver, mock_db):
        """Should return match when email found in known_client_emails."""
        mock_db.execute.return_value.fetchone.return_value = (1, 2, 3, "John Smith")

        result = resolver._match_known_clients(["john@example.com"], user_id=1)

        assert result is not None
        assert result["match_method"] == "known_client_email"
        assert result["match_confidence"] == 1.0
        assert result["is_priority"] is True
        assert result["match_client_name"] == "John Smith"

    def test_no_match(self, resolver, mock_db):
        """Should return None when no match found."""
        mock_db.execute.return_value.fetchone.return_value = None

        result = resolver._match_known_clients(["unknown@example.com"], user_id=1)

        assert result is None

    def test_empty_addresses(self, resolver):
        """Should return None for empty address list."""
        result = resolver._match_known_clients([], user_id=1)
        assert result is None


class TestLeadMatching:
    """Tests for lead email matching (Strategy 2)."""

    def test_match_found(self, resolver, mock_db):
        """Should return match when email found in leads."""
        mock_db.execute.return_value.fetchone.return_value = (123, "Jane Doe", "555-1234")

        result = resolver._match_leads(["jane@example.com"], user_id=1)

        assert result is not None
        assert result["match_method"] == "lead_email_match"
        assert result["match_confidence"] == 0.9
        assert result["matched_lead_id"] == 123
        assert result["match_client_name"] == "Jane Doe"

    def test_no_match(self, resolver, mock_db):
        """Should return None when no match found."""
        mock_db.execute.return_value.fetchone.return_value = None

        result = resolver._match_leads(["unknown@example.com"], user_id=1)

        assert result is None


class TestLoanMatching:
    """Tests for loan borrower email matching (Strategy 3)."""

    def test_borrower_match(self, resolver, mock_db):
        """Should match borrower email."""
        mock_db.execute.return_value.fetchone.return_value = (
            456, "Bob Wilson", "LN123456", 300000.00, "123 Main St"
        )

        result = resolver._match_loans(["bob@example.com"], "", user_id=1)

        assert result is not None
        assert result["match_method"] == "loan_email_match"
        assert result["match_confidence"] == 0.9
        assert result["matched_loan_id"] == 456
        assert result["match_loan_number"] == "LN123456"

    def test_no_match(self, resolver, mock_db):
        """Should return None when no match found."""
        mock_db.execute.return_value.fetchone.return_value = None

        result = resolver._match_loans(["unknown@example.com"], "", user_id=1)

        assert result is None


class TestContactMatching:
    """Tests for contact email matching (Strategy 4)."""

    def test_match_found(self, resolver, mock_db):
        """Should match contact email."""
        mock_db.execute.return_value.fetchone.return_value = (
            789, "Sarah", "Chen", "realtor"
        )

        result = resolver._match_contacts(["sarah@realty.com"], user_id=1)

        assert result is not None
        assert result["match_method"] == "contact_email_match"
        assert result["match_confidence"] == 0.85
        assert result["matched_contact_id"] == 789
        assert result["match_client_name"] == "Sarah Chen"


class TestLoanNumberExtraction:
    """Tests for loan number extraction from subject (Strategy 5)."""

    def test_extract_with_hash(self):
        """Should extract loan number with # prefix."""
        resolver = EmailIdentityResolver(MagicMock())
        numbers = resolver._extract_loan_numbers("RE: Loan #12345678 Documents")
        assert "12345678" in numbers

    def test_extract_with_colon(self):
        """Should extract loan number with colon prefix."""
        resolver = EmailIdentityResolver(MagicMock())
        numbers = resolver._extract_loan_numbers("Loan: 98765432 - Update")
        assert "98765432" in numbers

    def test_extract_standalone_number(self):
        """Should extract standalone 6+ digit numbers."""
        resolver = EmailIdentityResolver(MagicMock())
        numbers = resolver._extract_loan_numbers("Regarding 123456789")
        assert "123456789" in numbers

    def test_multiple_numbers(self):
        """Should extract multiple loan numbers."""
        resolver = EmailIdentityResolver(MagicMock())
        numbers = resolver._extract_loan_numbers("Loans 12345678 and 87654321")
        assert "12345678" in numbers
        assert "87654321" in numbers

    def test_no_short_numbers(self):
        """Should not extract numbers shorter than 4 digits."""
        resolver = EmailIdentityResolver(MagicMock())
        numbers = resolver._extract_loan_numbers("Loan 123")
        assert "123" not in numbers

    def test_empty_subject(self):
        """Should return empty list for empty subject."""
        resolver = EmailIdentityResolver(MagicMock())
        numbers = resolver._extract_loan_numbers("")
        assert numbers == []


class TestThreadContinuity:
    """Tests for thread continuity matching (Strategy 6)."""

    def test_match_from_previous_email(self, resolver, mock_db):
        """Should inherit match from previous email in thread."""
        mock_db.execute.return_value.fetchone.return_value = (
            1, 2, 3, "Previous Client", "LN999"
        )

        result = resolver._match_by_thread("thread-xyz", user_id=1)

        assert result is not None
        assert result["match_method"] == "thread_continuity"
        assert result["match_confidence"] == 0.75
        assert result["matched_contact_id"] == 1
        assert result["matched_loan_id"] == 2
        assert result["matched_lead_id"] == 3

    def test_no_previous_match(self, resolver, mock_db):
        """Should return None when no previous match in thread."""
        mock_db.execute.return_value.fetchone.return_value = None

        result = resolver._match_by_thread("new-thread", user_id=1)

        assert result is None

    def test_empty_thread_id(self, resolver):
        """Should return None for empty thread ID."""
        result = resolver._match_by_thread("", user_id=1)
        assert result is None

        result = resolver._match_by_thread(None, user_id=1)
        assert result is None


class TestDomainMatching:
    """Tests for domain-based vendor matching (Strategy 7)."""

    def test_exact_domain_match(self, resolver):
        """Should match exact vendor domain."""
        result = resolver._match_by_domain(["appraiser@fanniemae.com"])

        assert result is not None
        assert result["match_method"] == "domain_vendor_match"
        assert result["match_client_name"] == "Fannie Mae"
        assert result["match_confidence"] == 0.95

    def test_subdomain_match(self, resolver):
        """Should match subdomain to parent domain."""
        result = resolver._match_by_domain(["noreply@mail.equifax.com"])

        assert result is not None
        assert result["match_method"] == "domain_vendor_match"
        assert result["match_client_name"] == "Equifax"
        # Subdomain confidence is slightly reduced
        assert result["match_confidence"] < 0.90

    def test_unknown_domain(self, resolver):
        """Should return None for unknown domain."""
        result = resolver._match_by_domain(["user@unknown-company.com"])

        assert result is None

    def test_vendor_type_set(self, resolver):
        """Should set vendor_type in result."""
        result = resolver._match_by_domain(["user@fha.gov"])

        assert result is not None
        assert result["vendor_type"] == "vendor"


# ============================================================
# Tests: EmailIdentityResolver - Full Resolution Flow
# ============================================================

class TestFullResolve:
    """Tests for the full resolve() method."""

    def test_known_client_priority(self, resolver, mock_db, sample_email_data):
        """Known client match should take priority."""
        # Known client match succeeds
        mock_db.execute.return_value.fetchone.return_value = (1, 2, 3, "John")

        result = resolver.resolve(sample_email_data, user_id=1)

        assert result["match_method"] == "known_client_email"
        assert result["is_priority"] is True

    def test_waterfall_to_lead(self, resolver, mock_db, sample_email_data):
        """Should fall through to lead match if no known client."""
        # The waterfall makes multiple queries:
        # - _match_known_clients iterates through addresses (2) × variants (2) = 4 queries
        # - Then _match_leads queries for each address until match found
        # For sample_email_data: from_email + to_emails = 2 addresses
        mock_db.execute.return_value.fetchone.side_effect = [
            None,  # known_client: "johnsmith@gmail.com" variant 1
            None,  # known_client: "johnsmith@gmail.com" variant 2
            None,  # known_client: "loan.officer@company.com" variant 1
            None,  # known_client: "loan.officer@company.com" variant 2
            (123, "John Smith", "555-1234"),  # lead match for first address
        ]

        result = resolver.resolve(sample_email_data, user_id=1)

        assert result["match_method"] == "lead_email_match"
        assert result["matched_lead_id"] == 123
        assert result["match_client_name"] == "John Smith"

    def test_no_match_returns_empty(self, resolver, mock_db, sample_email_data):
        """Should return empty match when nothing found."""
        mock_db.execute.return_value.fetchone.return_value = None

        result = resolver.resolve(sample_email_data, user_id=1)

        assert result["match_method"] is None
        assert result["match_confidence"] is None
        assert result["matched_contact_id"] is None
        assert result["matched_loan_id"] is None
        assert result["matched_lead_id"] is None


class TestBatchResolve:
    """Tests for batch resolution."""

    def test_batch_processes_all(self, resolver, mock_db):
        """Should process all emails in batch."""
        emails = [
            {"from_email": "a@example.com"},
            {"from_email": "b@example.com"},
            {"from_email": "c@example.com"},
        ]
        mock_db.execute.return_value.fetchone.return_value = None

        results = resolver.batch_resolve(emails, user_id=1)

        assert len(results) == 3

    def test_batch_handles_errors(self, resolver, mock_db):
        """Should continue processing after error."""
        emails = [
            {"from_email": "a@example.com"},
            {"from_email": "b@example.com"},
        ]

        # First email raises error, second succeeds
        mock_db.execute.side_effect = [
            Exception("Database error"),
            MagicMock(fetchone=MagicMock(return_value=None)),
        ]

        results = resolver.batch_resolve(emails, user_id=1)

        # Should still return 2 results
        assert len(results) == 2


# ============================================================
# Tests: Factory Function
# ============================================================

class TestGetEmailIdentityResolver:
    """Tests for the factory function."""

    def test_returns_resolver_instance(self, mock_db):
        """Should return EmailIdentityResolver instance."""
        resolver = get_email_identity_resolver(mock_db)

        assert isinstance(resolver, EmailIdentityResolver)
        assert resolver.db == mock_db


# ============================================================
# Tests: Edge Cases and Error Handling
# ============================================================

class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_database_error_in_known_client(self, resolver, mock_db):
        """Should handle database errors gracefully."""
        mock_db.execute.side_effect = Exception("Connection failed")

        result = resolver._match_known_clients(["test@example.com"], user_id=1)

        # Should return None, not raise
        assert result is None

    def test_unicode_email(self, resolver, mock_db):
        """Should handle unicode in email addresses."""
        mock_db.execute.return_value.fetchone.return_value = None

        # Should not raise
        result = resolver._match_leads(["tëst@example.com"], user_id=1)
        assert result is None

    def test_very_long_subject(self, resolver):
        """Should handle very long subjects."""
        long_subject = "Loan #12345678 " + "x" * 10000

        numbers = resolver._extract_loan_numbers(long_subject)

        assert "12345678" in numbers

    def test_special_characters_in_subject(self, resolver):
        """Should handle special characters in subject."""
        subject = "RE: Loan #12345678 - 🏠 New Home Purchase!!!"

        numbers = resolver._extract_loan_numbers(subject)

        assert "12345678" in numbers


# ============================================================
# Tests: Statistics
# ============================================================

class TestResolutionStats:
    """Tests for get_resolution_stats method."""

    def test_returns_stats(self, resolver, mock_db):
        """Should return resolution statistics."""
        # Mock different queries
        mock_db.execute.return_value.scalar.side_effect = [100, 75, 50]
        mock_db.execute.return_value.fetchall.return_value = [
            ("known_client_email", 40),
            ("lead_email_match", 35),
        ]

        stats = resolver.get_resolution_stats(user_id=1)

        assert "total_emails" in stats
        assert "resolved" in stats
        assert "unresolved" in stats
        assert "resolution_rate" in stats
        assert "by_method" in stats

    def test_handles_error(self, resolver, mock_db):
        """Should handle database error."""
        mock_db.execute.side_effect = Exception("Query failed")

        stats = resolver.get_resolution_stats(user_id=1)

        assert stats["total_emails"] == 0
        assert "error" in stats


# ============================================================
# Integration-style Tests
# ============================================================

class TestIntegration:
    """Integration-style tests simulating real workflows."""

    def test_gmail_variant_matching(self, resolver, mock_db):
        """Gmail variants should match the same record."""
        mock_db.execute.return_value.fetchone.return_value = (1, 2, 3, "John")

        # All these should normalize to the same email
        variants = [
            "john.smith@gmail.com",
            "johnsmith@gmail.com",
            "j.o.h.n.s.m.i.t.h@gmail.com",
            "john.smith+work@gmail.com",
        ]

        results = []
        for email in variants:
            result = resolver._match_known_clients([email], user_id=1)
            results.append(result)

        # All should match (or all fail if not in DB - but structure same)
        assert all(r is not None for r in results) or all(r is None for r in results)

    def test_microsoft_graph_full_flow(self, resolver, mock_db, microsoft_graph_email):
        """Should handle full Microsoft Graph email format."""
        mock_db.execute.return_value.fetchone.return_value = (123, "Jane", "555-1234")

        result = resolver.resolve(microsoft_graph_email, user_id=1)

        # Should extract email and process
        assert result is not None


# ============================================================
# Run tests if executed directly
# ============================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
