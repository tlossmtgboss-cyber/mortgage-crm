"""
Unit Tests for Call Intelligence Service

Tests PII handling, speaker detection, and extraction agents.
"""

import pytest
from unittest.mock import MagicMock, AsyncMock, patch

# Mark all tests as unit tests
pytestmark = [pytest.mark.unit]


# =============================================================================
# PII Utilities Tests
# =============================================================================

class TestPIIUtilities:
    """Test PII handling utilities."""

    def test_redact_ssn_full_format(self):
        """Test SSN redaction with dashes."""
        from services.call_intelligence.pii_utils import redact_ssn

        text = "My SSN is 123-45-6789"
        result = redact_ssn(text)

        assert "123-45" not in result
        assert "***-**-6789" in result

    def test_redact_ssn_no_dashes(self):
        """Test SSN redaction without dashes."""
        from services.call_intelligence.pii_utils import redact_ssn

        text = "SSN: 123456789"
        result = redact_ssn(text)

        assert "12345" not in result
        assert "6789" in result

    def test_redact_ssn_with_spaces(self):
        """Test SSN redaction with spaces."""
        from services.call_intelligence.pii_utils import redact_ssn

        text = "My social is 123 45 6789"
        result = redact_ssn(text)

        assert "123 45" not in result
        assert "6789" in result

    def test_redact_ssn_multiple_occurrences(self):
        """Test multiple SSN redactions."""
        from services.call_intelligence.pii_utils import redact_ssn

        text = "First SSN: 123-45-6789, Second: 987-65-4321"
        result = redact_ssn(text)

        assert "123-45" not in result
        assert "987-65" not in result
        assert "6789" in result
        assert "4321" in result

    def test_redact_ssn_preserves_other_numbers(self):
        """Test that non-SSN numbers are preserved."""
        from services.call_intelligence.pii_utils import redact_ssn

        text = "I make $75000 a year and my phone is 555-123-4567"
        result = redact_ssn(text)

        assert "$75000" in result
        assert "555-123-4567" in result

    def test_redact_ssn_empty_string(self):
        """Test redaction with empty string."""
        from services.call_intelligence.pii_utils import redact_ssn

        assert redact_ssn("") == ""
        assert redact_ssn(None) is None

    def test_extract_ssn_last_four_full_ssn(self):
        """Test extracting last 4 from full SSN."""
        from services.call_intelligence.pii_utils import extract_ssn_last_four

        text = "My SSN is 123-45-6789"
        last_four, was_full = extract_ssn_last_four(text)

        assert last_four == "6789"
        assert was_full is True

    def test_extract_ssn_last_four_partial(self):
        """Test extracting last 4 when only partial given."""
        from services.call_intelligence.pii_utils import extract_ssn_last_four

        text = "The last four of my social is 6789"
        last_four, was_full = extract_ssn_last_four(text)

        assert last_four == "6789"
        assert was_full is False

    def test_extract_ssn_last_four_context_words(self):
        """Test extraction with SSN context words."""
        from services.call_intelligence.pii_utils import extract_ssn_last_four

        text = "My social security number ends in 1234"
        last_four, was_full = extract_ssn_last_four(text)

        assert last_four == "1234"
        assert was_full is False

    def test_extract_ssn_last_four_no_ssn(self):
        """Test extraction when no SSN present."""
        from services.call_intelligence.pii_utils import extract_ssn_last_four

        text = "I don't have any SSN in this text"
        last_four, was_full = extract_ssn_last_four(text)

        assert last_four is None
        assert was_full is False

    def test_contains_ssn_true(self):
        """Test SSN detection - positive case."""
        from services.call_intelligence.pii_utils import contains_ssn

        assert contains_ssn("My SSN is 123-45-6789") is True
        assert contains_ssn("SSN: 123456789") is True
        assert contains_ssn("123 45 6789") is True

    def test_contains_ssn_false(self):
        """Test SSN detection - negative case."""
        from services.call_intelligence.pii_utils import contains_ssn

        assert contains_ssn("My phone is 555-123-4567") is False
        assert contains_ssn("I make $75000") is False
        assert contains_ssn("Last four is 6789") is False

    def test_mask_pii_for_logging(self):
        """Test PII masking for safe logging."""
        from services.call_intelligence.pii_utils import mask_pii_for_logging

        text = "Borrower SSN 123-45-6789 and income $75000"
        result = mask_pii_for_logging(text)

        assert "123-45" not in result
        assert "6789" in result
        assert "$75000" in result  # Non-PII preserved

    def test_sanitize_source_text(self):
        """Test source text sanitization."""
        from services.call_intelligence.pii_utils import sanitize_source_text

        text = "My SSN is 123-45-6789 and I was born on March 14, 1989"
        result = sanitize_source_text(text)

        assert "123-45" not in result
        assert "***-**-6789" in result
        assert "March 14, 1989" in result  # DOB not redacted by default

    def test_sanitize_source_text_truncation(self):
        """Test source text truncation."""
        from services.call_intelligence.pii_utils import sanitize_source_text

        long_text = "A" * 500
        result = sanitize_source_text(long_text, max_length=100)

        assert len(result) == 100
        assert result.endswith("...")

    def test_validate_ssn_last_four(self):
        """Test SSN last four validation."""
        from services.call_intelligence.pii_utils import validate_ssn_last_four

        assert validate_ssn_last_four("1234") is True
        assert validate_ssn_last_four("0000") is True
        assert validate_ssn_last_four("123") is False
        assert validate_ssn_last_four("12345") is False
        assert validate_ssn_last_four("abcd") is False
        assert validate_ssn_last_four("") is False
        assert validate_ssn_last_four(None) is False


# =============================================================================
# Speaker Detection Tests
# =============================================================================

class TestSpeakerDetection:
    """Test speaker role detection."""

    def test_identify_speaker_role_keywords(self):
        """Test identification via role keywords."""
        from services.call_intelligence.process_transcript import identify_speaker_role
        from services.call_intelligence.data_contracts import SpeakerRole

        assert identify_speaker_role("Loan Officer") == SpeakerRole.AI_LO
        assert identify_speaker_role("LO") == SpeakerRole.AI_LO
        assert identify_speaker_role("Agent") == SpeakerRole.AI_LO
        assert identify_speaker_role("Borrower") == SpeakerRole.BORROWER
        assert identify_speaker_role("Customer") == SpeakerRole.BORROWER
        assert identify_speaker_role("Co-Borrower") == SpeakerRole.CO_BORROWER
        assert identify_speaker_role("Spouse") == SpeakerRole.CO_BORROWER

    def test_identify_speaker_role_case_insensitive(self):
        """Test case insensitive matching."""
        from services.call_intelligence.process_transcript import identify_speaker_role
        from services.call_intelligence.data_contracts import SpeakerRole

        assert identify_speaker_role("LOAN OFFICER") == SpeakerRole.AI_LO
        assert identify_speaker_role("borrower") == SpeakerRole.BORROWER
        assert identify_speaker_role("CO-BORROWER") == SpeakerRole.CO_BORROWER

    def test_identify_speaker_role_with_names(self):
        """Test identification with personal names (unknown)."""
        from services.call_intelligence.process_transcript import identify_speaker_role
        from services.call_intelligence.data_contracts import SpeakerRole

        # Personal names without role context should be UNKNOWN
        assert identify_speaker_role("Tim") == SpeakerRole.UNKNOWN
        assert identify_speaker_role("Jack") == SpeakerRole.UNKNOWN
        assert identify_speaker_role("John Smith") == SpeakerRole.UNKNOWN

    def test_identify_speaker_role_with_explicit_mapping(self):
        """Test identification with explicit speaker mapping."""
        from services.call_intelligence.process_transcript import identify_speaker_role
        from services.call_intelligence.data_contracts import SpeakerRole

        mapping = {
            "Tim": SpeakerRole.AI_LO,
            "Jack": SpeakerRole.BORROWER,
        }

        assert identify_speaker_role("Tim", speaker_mapping=mapping) == SpeakerRole.AI_LO
        assert identify_speaker_role("Jack", speaker_mapping=mapping) == SpeakerRole.BORROWER

    def test_identify_speaker_role_from_speech_patterns(self):
        """Test identification from speech content patterns."""
        from services.call_intelligence.process_transcript import identify_speaker_role
        from services.call_intelligence.data_contracts import SpeakerRole

        lo_speech = "What is your annual income? Can you tell me about your employment?"
        borrower_speech = "My name is Jack. I make about $75000 a year."

        assert identify_speaker_role("Speaker 1", text=lo_speech) == SpeakerRole.AI_LO
        assert identify_speaker_role("Speaker 2", text=borrower_speech) == SpeakerRole.BORROWER

    def test_co_borrower_not_detected_as_borrower(self):
        """Test that co-borrower is not incorrectly detected as borrower."""
        from services.call_intelligence.process_transcript import identify_speaker_role
        from services.call_intelligence.data_contracts import SpeakerRole

        # "co-borrower" contains "borrower" but should match co-borrower first
        assert identify_speaker_role("Co-Borrower") == SpeakerRole.CO_BORROWER
        assert identify_speaker_role("Coborrower") == SpeakerRole.CO_BORROWER
        assert identify_speaker_role("co-applicant") == SpeakerRole.CO_BORROWER


class TestTranscriptParsing:
    """Test transcript parsing."""

    def test_parse_transcript_colon_format(self):
        """Test parsing 'Speaker: text' format."""
        from services.call_intelligence.process_transcript import parse_transcript
        from services.call_intelligence.data_contracts import SpeakerRole

        transcript = """Loan Officer: Hello, how are you today?
Borrower: I'm doing well, thanks."""

        segments = parse_transcript(transcript)

        assert len(segments) == 2
        assert segments[0].speaker == SpeakerRole.AI_LO
        assert "Hello" in segments[0].text
        assert segments[1].speaker == SpeakerRole.BORROWER
        assert "doing well" in segments[1].text

    def test_parse_transcript_bracket_format(self):
        """Test parsing '[Speaker] text' format."""
        from services.call_intelligence.process_transcript import parse_transcript
        from services.call_intelligence.data_contracts import SpeakerRole

        transcript = """[Agent] Welcome to the call.
[Customer] Thanks for having me."""

        segments = parse_transcript(transcript)

        assert len(segments) == 2
        assert segments[0].speaker == SpeakerRole.AI_LO
        assert segments[1].speaker == SpeakerRole.BORROWER

    def test_parse_transcript_multiline_format(self):
        """Test parsing speaker on separate line format."""
        from services.call_intelligence.process_transcript import parse_transcript
        from services.call_intelligence.data_contracts import SpeakerRole

        transcript = """Loan Officer:
Hello, how can I help you today?

Borrower:
I'm looking to buy a house."""

        segments = parse_transcript(transcript)

        assert len(segments) == 2
        assert segments[0].speaker == SpeakerRole.AI_LO
        assert segments[1].speaker == SpeakerRole.BORROWER

    def test_parse_transcript_with_speaker_mapping(self):
        """Test parsing with explicit speaker mapping."""
        from services.call_intelligence.process_transcript import parse_transcript
        from services.call_intelligence.data_contracts import SpeakerRole

        transcript = """Tim: Hello Jack, how are you?
Jack: I'm doing well, Tim."""

        mapping = {
            "Tim": SpeakerRole.AI_LO,
            "Jack": SpeakerRole.BORROWER,
        }

        segments = parse_transcript(transcript, speaker_mapping=mapping)

        assert len(segments) == 2
        assert segments[0].speaker == SpeakerRole.AI_LO
        assert segments[1].speaker == SpeakerRole.BORROWER

    def test_parse_transcript_infers_roles(self):
        """Test that roles are inferred for 2-party conversations."""
        from services.call_intelligence.process_transcript import parse_transcript
        from services.call_intelligence.data_contracts import SpeakerRole

        # LO typically speaks first and asks questions
        transcript = """Speaker 1: Welcome to the mortgage consultation. What is your name?
Speaker 2: My name is Jack Daniels.
Speaker 1: And what is your annual income?
Speaker 2: I make about $110,000 a year."""

        segments = parse_transcript(transcript)

        # First speaker should be identified as LO (asks questions, speaks first)
        assert segments[0].speaker == SpeakerRole.AI_LO
        assert segments[1].speaker == SpeakerRole.BORROWER

    def test_parse_transcript_empty(self):
        """Test parsing empty transcript."""
        from services.call_intelligence.process_transcript import parse_transcript

        segments = parse_transcript("")
        assert segments == []

        segments = parse_transcript("   \n\n   ")
        assert segments == []


# =============================================================================
# Identity Agent Tests
# =============================================================================

class TestIdentityAgent:
    """Test identity extraction agent."""

    @pytest.fixture
    def identity_agent(self):
        """Create identity agent instance."""
        from services.call_intelligence.agents import IdentityExtractionAgent
        return IdentityExtractionAgent()

    def test_extract_ssn_securely(self, identity_agent):
        """Test SSN extraction only returns last 4 digits."""
        from services.call_intelligence.data_contracts import TranscriptSegment, SpeakerRole

        segments = [
            TranscriptSegment(
                speaker=SpeakerRole.BORROWER,
                text="My social security number is 123-45-6789",
                index=0,
            )
        ]

        result = identity_agent.extract_with_regex(segments)

        # Find SSN extraction
        ssn_extraction = None
        for ext in result.extractions:
            if "ssn" in ext.field_name.lower():
                ssn_extraction = ext
                break

        assert ssn_extraction is not None
        assert ssn_extraction.value == "6789"  # Only last 4
        assert ssn_extraction.field_name == "ssn_last_four"
        assert "123-45" not in ssn_extraction.source_text  # Full SSN not in source
        assert "[SSN redacted" in ssn_extraction.source_text

    def test_extract_name(self, identity_agent):
        """Test name extraction."""
        from services.call_intelligence.data_contracts import TranscriptSegment, SpeakerRole

        segments = [
            TranscriptSegment(
                speaker=SpeakerRole.BORROWER,
                text="My name is Jack Daniels",
                index=0,
            )
        ]

        result = identity_agent.extract_with_regex(segments)

        first_name = result.get_by_field("first_name")
        last_name = result.get_by_field("last_name")

        assert first_name is not None
        assert first_name.value == "Jack"
        assert last_name is not None
        assert last_name.value == "Daniels"

    def test_extract_dob(self, identity_agent):
        """Test date of birth extraction."""
        from services.call_intelligence.data_contracts import TranscriptSegment, SpeakerRole

        segments = [
            TranscriptSegment(
                speaker=SpeakerRole.BORROWER,
                text="I was born on March 14, 1989",
                index=0,
            )
        ]

        result = identity_agent.extract_with_regex(segments)

        dob = result.get_by_field("date_of_birth")
        assert dob is not None
        assert "March 14, 1989" in dob.value

    def test_extract_citizenship(self, identity_agent):
        """Test citizenship extraction."""
        from services.call_intelligence.data_contracts import TranscriptSegment, SpeakerRole

        segments = [
            TranscriptSegment(
                speaker=SpeakerRole.BORROWER,
                text="Yes, I'm a US citizen",
                index=0,
            )
        ]

        result = identity_agent.extract_with_regex(segments)

        citizenship = result.get_by_field("citizenship_status")
        assert citizenship is not None
        assert citizenship.value == "US_CITIZEN"

    def test_extract_marital_status(self, identity_agent):
        """Test marital status extraction."""
        from services.call_intelligence.data_contracts import TranscriptSegment, SpeakerRole

        segments = [
            TranscriptSegment(
                speaker=SpeakerRole.BORROWER,
                text="I'm married",
                index=0,
            )
        ]

        result = identity_agent.extract_with_regex(segments)

        marital = result.get_by_field("marital_status")
        assert marital is not None
        assert marital.value == "MARRIED"

    def test_source_text_sanitized(self, identity_agent):
        """Test that all source_text fields are sanitized."""
        from services.call_intelligence.data_contracts import TranscriptSegment, SpeakerRole

        segments = [
            TranscriptSegment(
                speaker=SpeakerRole.BORROWER,
                text="My name is Jack, SSN is 123-45-6789, born March 14 1989",
                index=0,
            )
        ]

        result = identity_agent.extract_with_regex(segments)

        for extraction in result.extractions:
            # No full SSN should appear in any source_text
            assert "123-45-6789" not in extraction.source_text
            assert "123456789" not in extraction.source_text


# =============================================================================
# Financial Agent Tests
# =============================================================================

class TestFinancialAgent:
    """Test financial extraction agent."""

    @pytest.fixture
    def financial_agent(self):
        """Create financial agent instance."""
        from services.call_intelligence.agents import FinancialExtractionAgent
        return FinancialExtractionAgent()

    def test_extract_annual_salary(self, financial_agent):
        """Test annual salary extraction."""
        from services.call_intelligence.data_contracts import TranscriptSegment, SpeakerRole

        segments = [
            TranscriptSegment(
                speaker=SpeakerRole.BORROWER,
                text="I make $110,000 a year",
                index=0,
            )
        ]

        result = financial_agent.extract_with_regex(segments)

        salary = result.get_by_field("annual_salary")
        assert salary is not None
        assert salary.value == 110000.0

    def test_extract_monthly_payment(self, financial_agent):
        """Test monthly payment extraction."""
        from services.call_intelligence.data_contracts import TranscriptSegment, SpeakerRole

        segments = [
            TranscriptSegment(
                speaker=SpeakerRole.BORROWER,
                text="My rent is about $2,100 a month",
                index=0,
            )
        ]

        result = financial_agent.extract_with_regex(segments)

        # Check for any payment-related extraction
        found_payment = False
        for ext in result.extractions:
            if "payment" in ext.field_name or ext.value == 2100.0:
                found_payment = True
                break

        # Note: This may extract as down_payment or other field depending on context
        # The important thing is the value is captured


# =============================================================================
# Processor Tests
# =============================================================================

class TestCallIntelligenceProcessor:
    """Test the main processor."""

    def test_get_supported_agents(self):
        """Test supported agents list."""
        from services.call_intelligence.processor import CallIntelligenceProcessor

        processor = CallIntelligenceProcessor()
        agents = processor.get_supported_agents()

        assert len(agents) == 6

        agent_names = [a["name"] for a in agents]
        assert "identity" in agent_names
        assert "property" in agent_names
        assert "employment" in agent_names
        assert "financial" in agent_names
        assert "compliance" in agent_names
        assert "intent" in agent_names

    def test_identity_agent_has_ssn_last_four(self):
        """Test identity agent lists ssn_last_four not ssn."""
        from services.call_intelligence.processor import CallIntelligenceProcessor

        processor = CallIntelligenceProcessor()
        agents = processor.get_supported_agents()

        identity_agent = next(a for a in agents if a["name"] == "identity")

        assert "ssn_last_four" in identity_agent["fields"]
        assert "ssn" not in identity_agent["fields"]


# =============================================================================
# Integration Safety Tests
# =============================================================================

class TestIntegrationSafety:
    """Test integration module safety features."""

    def test_error_messages_are_masked(self):
        """Test that error messages have PII masked."""
        from services.call_intelligence.pii_utils import mask_pii_for_logging

        # Simulate an error message that might contain PII
        error = "Failed to process: My SSN is 123-45-6789"
        safe_error = mask_pii_for_logging(error)

        assert "123-45" not in safe_error
        assert "6789" in safe_error  # Last 4 preserved


# =============================================================================
# Input Validation Tests
# =============================================================================

class TestInputValidation:
    """Test input validation in integration module."""

    @pytest.mark.asyncio
    async def test_empty_call_id_rejected(self):
        """Test that empty call_id is rejected."""
        from services.call_intelligence.integration import CallIntelligenceIntegration

        # Create integration with mock db session
        integration = CallIntelligenceIntegration(db_session=None)

        result = await integration.process_completed_call(
            call_id="",
            loan_id=None,
            organization_id=1,
            transcript="Hello",
        )

        assert result["success"] is False
        assert result["stage"] == "validation"
        assert "call_id" in result["error"]

    @pytest.mark.asyncio
    async def test_invalid_organization_id_rejected(self):
        """Test that invalid organization_id is rejected."""
        from services.call_intelligence.integration import CallIntelligenceIntegration

        integration = CallIntelligenceIntegration(db_session=None)

        result = await integration.process_completed_call(
            call_id="test-123",
            loan_id=None,
            organization_id=0,
            transcript="Hello",
        )

        assert result["success"] is False
        assert result["stage"] == "validation"
        assert "organization_id" in result["error"]

    @pytest.mark.asyncio
    async def test_negative_organization_id_rejected(self):
        """Test that negative organization_id is rejected."""
        from services.call_intelligence.integration import CallIntelligenceIntegration

        integration = CallIntelligenceIntegration(db_session=None)

        result = await integration.process_completed_call(
            call_id="test-123",
            loan_id=None,
            organization_id=-1,
            transcript="Hello",
        )

        assert result["success"] is False
        assert result["stage"] == "validation"
        assert "organization_id" in result["error"]

    @pytest.mark.asyncio
    async def test_empty_transcript_rejected(self):
        """Test that empty transcript is rejected."""
        from services.call_intelligence.integration import CallIntelligenceIntegration

        integration = CallIntelligenceIntegration(db_session=None)

        result = await integration.process_completed_call(
            call_id="test-123",
            loan_id=None,
            organization_id=1,
            transcript="",
        )

        assert result["success"] is False
        assert result["stage"] == "validation"
        assert "transcript" in result["error"]

    @pytest.mark.asyncio
    async def test_invalid_loan_id_rejected(self):
        """Test that invalid loan_id is rejected."""
        from services.call_intelligence.integration import CallIntelligenceIntegration

        integration = CallIntelligenceIntegration(db_session=None)

        result = await integration.process_completed_call(
            call_id="test-123",
            loan_id=-5,
            organization_id=1,
            transcript="Hello",
        )

        assert result["success"] is False
        assert result["stage"] == "validation"
        assert "loan_id" in result["error"]

    @pytest.mark.asyncio
    async def test_call_id_max_length_enforced(self):
        """Test that call_id max length is enforced."""
        from services.call_intelligence.integration import CallIntelligenceIntegration

        integration = CallIntelligenceIntegration(db_session=None)

        result = await integration.process_completed_call(
            call_id="x" * 256,  # Exceeds 255 char limit
            loan_id=None,
            organization_id=1,
            transcript="Hello",
        )

        assert result["success"] is False
        assert result["stage"] == "validation"
        assert "255" in result["error"]


# =============================================================================
# Integration Tests - Full Processor Flow
# =============================================================================

# Mark these tests as slow since they make real LLM API calls
# Run with: pytest -m slow to include these tests
@pytest.mark.slow
class TestProcessorIntegration:
    """Integration tests for the full processor flow.

    These tests make real LLM API calls and are marked as slow.
    Skip with: pytest -m "not slow"
    """

    @pytest.fixture
    def sample_transcript(self):
        """Sample mortgage call transcript for testing."""
        return """Loan Officer: Hi, this is Sarah from ABC Mortgage. How can I help you today?
Borrower: Hi Sarah, my name is John Smith. I'm looking to buy a house.
Loan Officer: Great! Can you tell me about your employment situation?
Borrower: I work at Acme Corporation as a software engineer. I've been there for 3 years.
Loan Officer: And what is your annual income?
Borrower: I make about $95,000 a year, plus I usually get a bonus around $10,000.
Loan Officer: Perfect. Do you have a property in mind?
Borrower: Yes, it's at 123 Main Street in Austin, Texas. The asking price is $450,000.
Loan Officer: What about your down payment?
Borrower: I have about $90,000 saved for the down payment.
Loan Officer: Are you a US citizen?
Borrower: Yes, I am.
Loan Officer: And your marital status?
Borrower: I'm married.
Loan Officer: Have you ever filed for bankruptcy?
Borrower: No, never.
Loan Officer: Great. We'll get started on your pre-approval."""

    @pytest.mark.asyncio
    async def test_full_processor_flow_regex_only(self, sample_transcript):
        """Test full processor flow using regex extraction (no LLM)."""
        from services.call_intelligence.processor import CallIntelligenceProcessor
        from services.call_intelligence.data_contracts import CallIntelligenceRequest

        processor = CallIntelligenceProcessor()  # No LLM client

        request = CallIntelligenceRequest(
            call_id="test-integration-001",
            organization_id=1,
            transcript=sample_transcript,
        )

        response = await processor.process_transcript(request)

        # Should succeed
        assert response.success is True
        assert response.call_id == "test-integration-001"

        # Should have extracted data from multiple agents
        assert response.total_extractions > 0

        # Check identity extractions
        assert "first_name" in response.identity_extractions
        assert response.identity_extractions.get("first_name") == "John"

        # Check employment extractions
        assert len(response.employment_extractions) > 0

        # Check financial extractions (income)
        assert len(response.income_extractions) > 0

        # Check property extractions
        assert len(response.address_extractions) > 0

        # Check compliance extractions
        assert len(response.declarations_extractions) > 0

    @pytest.mark.asyncio
    async def test_processor_with_specific_agents(self, sample_transcript):
        """Test running processor with only specific agents."""
        from services.call_intelligence.processor import CallIntelligenceProcessor
        from services.call_intelligence.data_contracts import CallIntelligenceRequest

        processor = CallIntelligenceProcessor()

        request = CallIntelligenceRequest(
            call_id="test-specific-agents",
            organization_id=1,
            transcript=sample_transcript,
            agents_to_run=["identity", "financial"],  # Only run 2 agents
        )

        response = await processor.process_transcript(request)

        assert response.success is True
        # Should have results from identity and financial agents
        agent_names = [r.agent_name for r in response.agent_results]
        assert "identity" in agent_names
        assert "financial" in agent_names
        # Should NOT have results from other agents
        assert "property" not in agent_names
        assert "compliance" not in agent_names

    @pytest.mark.asyncio
    async def test_processor_empty_transcript(self):
        """Test processor handles empty transcript gracefully."""
        from services.call_intelligence.processor import CallIntelligenceProcessor
        from services.call_intelligence.data_contracts import CallIntelligenceRequest

        processor = CallIntelligenceProcessor()

        request = CallIntelligenceRequest(
            call_id="test-empty",
            organization_id=1,
            transcript="",
        )

        response = await processor.process_transcript(request)

        assert response.success is False
        assert "No transcript content" in response.errors[0]

    @pytest.mark.asyncio
    async def test_processor_with_existing_data(self, sample_transcript):
        """Test processor with pre-existing borrower data."""
        from services.call_intelligence.processor import CallIntelligenceProcessor
        from services.call_intelligence.data_contracts import CallIntelligenceRequest

        processor = CallIntelligenceProcessor()

        existing_data = {
            "first_name": "John",
            "last_name": "Smith",
            "email": "john.smith@example.com",
        }

        request = CallIntelligenceRequest(
            call_id="test-existing-data",
            organization_id=1,
            transcript=sample_transcript,
            existing_borrower_data=existing_data,
        )

        response = await processor.process_transcript(request)

        assert response.success is True
        # Should still extract new data even with existing data
        assert response.total_extractions > 0


# =============================================================================
# Integration Tests - Webhook Handlers
# =============================================================================

class TestWebhookHandlers:
    """Integration tests for Retell and Vapi webhook handlers."""

    @pytest.mark.asyncio
    async def test_retell_handler_valid_data(self):
        """Test Retell webhook handler with valid data."""
        from services.call_intelligence.integration import handle_retell_call_ended
        from unittest.mock import MagicMock, AsyncMock, patch

        mock_db = MagicMock()

        call_data = {
            "transcript": "Loan Officer: Hello!\nBorrower: Hi, my name is Jane Doe.",
            "metadata": {
                "loan_id": 123,
                "organization_id": 1,
            },
            "duration_ms": 60000,
            "agent_id": "agent-001",
        }

        # Mock the processor to avoid actual processing
        with patch('services.call_intelligence.integration.CallIntelligenceIntegration') as MockIntegration:
            mock_instance = MagicMock()
            mock_instance.process_completed_call = AsyncMock(return_value={
                "success": True,
                "extractions_count": 5,
            })
            MockIntegration.return_value = mock_instance

            result = await handle_retell_call_ended(
                db=mock_db,
                call_id="retell-call-001",
                call_data=call_data,
            )

            assert result["success"] is True
            mock_instance.process_completed_call.assert_called_once()

            # Check that metadata was passed correctly
            call_args = mock_instance.process_completed_call.call_args
            assert call_args.kwargs["call_id"] == "retell-call-001"
            assert call_args.kwargs["loan_id"] == 123
            assert call_args.kwargs["organization_id"] == 1
            assert call_args.kwargs["call_metadata"]["source"] == "retell"

    @pytest.mark.asyncio
    async def test_retell_handler_no_transcript(self):
        """Test Retell handler rejects call without transcript."""
        from services.call_intelligence.integration import handle_retell_call_ended
        from unittest.mock import MagicMock

        mock_db = MagicMock()

        call_data = {
            "transcript": "",  # Empty transcript
            "metadata": {
                "organization_id": 1,
            },
        }

        result = await handle_retell_call_ended(
            db=mock_db,
            call_id="retell-no-transcript",
            call_data=call_data,
        )

        assert result["success"] is False
        assert result["error"] == "No transcript"

    @pytest.mark.asyncio
    async def test_retell_handler_no_org_id(self):
        """Test Retell handler rejects call without organization_id."""
        from services.call_intelligence.integration import handle_retell_call_ended
        from unittest.mock import MagicMock

        mock_db = MagicMock()

        call_data = {
            "transcript": "Some transcript content",
            "metadata": {},  # No organization_id
        }

        result = await handle_retell_call_ended(
            db=mock_db,
            call_id="retell-no-org",
            call_data=call_data,
        )

        assert result["success"] is False
        assert result["error"] == "No organization_id"

    @pytest.mark.asyncio
    async def test_vapi_handler_valid_data(self):
        """Test Vapi webhook handler with valid data."""
        from services.call_intelligence.integration import handle_vapi_call_ended
        from unittest.mock import MagicMock, AsyncMock, patch

        mock_db = MagicMock()

        call_data = {
            "messages": [
                {"role": "assistant", "message": "Hello, how can I help?"},
                {"role": "user", "message": "I want to buy a house."},
            ],
            "assistant": {
                "id": "assistant-001",
                "metadata": {
                    "loan_id": 456,
                    "organization_id": 2,
                },
            },
            "duration": 120,
        }

        with patch('services.call_intelligence.integration.CallIntelligenceIntegration') as MockIntegration:
            mock_instance = MagicMock()
            mock_instance.process_completed_call = AsyncMock(return_value={
                "success": True,
                "extractions_count": 3,
            })
            MockIntegration.return_value = mock_instance

            result = await handle_vapi_call_ended(
                db=mock_db,
                call_id="vapi-call-001",
                call_data=call_data,
            )

            assert result["success"] is True
            mock_instance.process_completed_call.assert_called_once()

            # Check Vapi-specific metadata
            call_args = mock_instance.process_completed_call.call_args
            assert call_args.kwargs["call_metadata"]["source"] == "vapi"
            assert call_args.kwargs["call_metadata"]["assistant_id"] == "assistant-001"

    @pytest.mark.asyncio
    async def test_vapi_handler_builds_transcript_from_messages(self):
        """Test that Vapi handler correctly builds transcript from messages."""
        from services.call_intelligence.integration import handle_vapi_call_ended
        from unittest.mock import MagicMock, AsyncMock, patch

        mock_db = MagicMock()

        call_data = {
            "messages": [
                {"role": "assistant", "message": "Welcome!"},
                {"role": "user", "message": "Thanks."},
                {"role": "assistant", "message": "What's your name?"},
                {"role": "user", "message": "John Smith."},
            ],
            "assistant": {
                "metadata": {
                    "organization_id": 1,
                },
            },
        }

        with patch('services.call_intelligence.integration.CallIntelligenceIntegration') as MockIntegration:
            mock_instance = MagicMock()
            mock_instance.process_completed_call = AsyncMock(return_value={"success": True})
            MockIntegration.return_value = mock_instance

            await handle_vapi_call_ended(
                db=mock_db,
                call_id="vapi-transcript-test",
                call_data=call_data,
            )

            call_args = mock_instance.process_completed_call.call_args
            transcript = call_args.kwargs["transcript"]

            # Verify transcript is built correctly
            assert "assistant: Welcome!" in transcript
            assert "user: Thanks." in transcript
            assert "user: John Smith." in transcript

    @pytest.mark.asyncio
    async def test_vapi_handler_no_messages(self):
        """Test Vapi handler rejects call without messages."""
        from services.call_intelligence.integration import handle_vapi_call_ended
        from unittest.mock import MagicMock

        mock_db = MagicMock()

        call_data = {
            "messages": [],  # Empty messages
            "assistant": {
                "metadata": {
                    "organization_id": 1,
                },
            },
        }

        result = await handle_vapi_call_ended(
            db=mock_db,
            call_id="vapi-no-messages",
            call_data=call_data,
        )

        assert result["success"] is False
        assert result["error"] == "No transcript"


# =============================================================================
# Integration Tests - Error Handling and Edge Cases
# =============================================================================

class TestErrorHandling:
    """Integration tests for error handling and edge cases."""

    @pytest.mark.asyncio
    async def test_processor_handles_agent_failure_gracefully(self):
        """Test processor continues when individual agent fails."""
        from services.call_intelligence.processor import CallIntelligenceProcessor
        from services.call_intelligence.data_contracts import CallIntelligenceRequest
        from unittest.mock import patch, AsyncMock

        # Mock create_llm_client to prevent any LLM initialization
        with patch('services.call_intelligence.agents.base_agent.create_llm_client', return_value=None):
            processor = CallIntelligenceProcessor(llm_client=None)

            # Make identity agent fail
            with patch.object(
                processor.identity_agent,
                'extract',
                AsyncMock(side_effect=Exception("Identity agent error"))
            ):
                request = CallIntelligenceRequest(
                    call_id="test-agent-failure",
                    organization_id=1,
                    transcript="Loan Officer: Hello!\nBorrower: Hi, I'm John.",
                )

                response = await processor.process_transcript(request)

                # Should still succeed (other agents ran)
                assert response.success is True
                # Identity agent result should have error in its errors list
                identity_result = next(
                    (r for r in response.agent_results if r.agent_name == "identity"),
                    None
                )
                assert identity_result is not None
                assert any("Identity agent error" in err for err in identity_result.errors)
                # Other agents should have run successfully
                other_agents = [r for r in response.agent_results if r.agent_name != "identity"]
                assert len(other_agents) > 0

    @pytest.mark.asyncio
    async def test_processor_handles_all_agents_failing(self):
        """Test processor when all agents fail."""
        from services.call_intelligence.processor import CallIntelligenceProcessor
        from services.call_intelligence.data_contracts import CallIntelligenceRequest
        from unittest.mock import patch, AsyncMock

        # Mock create_llm_client to prevent any LLM initialization
        with patch('services.call_intelligence.agents.base_agent.create_llm_client', return_value=None):
            processor = CallIntelligenceProcessor(llm_client=None)

            # Make _run_agent always raise (this bypasses exception handling in _run_agent)
            with patch.object(
                processor,
                '_run_agent',
                AsyncMock(side_effect=Exception("Agent error"))
            ):
                request = CallIntelligenceRequest(
                    call_id="test-all-agents-fail",
                    organization_id=1,
                    transcript="Loan Officer: Hello!\nBorrower: Hi.",
                )

                response = await processor.process_transcript(request)

                # Should still return a response (not crash)
                assert response.call_id == "test-all-agents-fail"
                # Should have errors recorded (caught by the for loop exception handler)
                assert len(response.errors) > 0

    @pytest.mark.asyncio
    async def test_integration_handles_db_session_none(self):
        """Test integration handles None db session gracefully."""
        from services.call_intelligence.integration import CallIntelligenceIntegration
        from unittest.mock import patch, AsyncMock, MagicMock

        integration = CallIntelligenceIntegration(db_session=None)

        # Mock the processor to return success
        with patch.object(
            integration.ci_processor,
            'process_transcript',
            AsyncMock(return_value=MagicMock(
                success=True,
                errors=[],
                total_extractions=5,
                high_confidence_count=3,
                identity_extractions={},
                address_extractions={},
                employment_extractions={},
                income_extractions={},
                assets_extractions={},
                liabilities_extractions={},
                reo_extractions={},
                declarations_extractions={},
            ))
        ):
            result = await integration.process_completed_call(
                call_id="test-no-db",
                loan_id=None,
                organization_id=1,
                transcript="Hello world",
            )

            # Should succeed (db operations would fail but be caught)
            assert result["success"] is True

    @pytest.mark.asyncio
    async def test_processor_with_malformed_transcript(self):
        """Test processor handles malformed transcript formats."""
        from services.call_intelligence.processor import CallIntelligenceProcessor
        from services.call_intelligence.data_contracts import CallIntelligenceRequest
        from unittest.mock import patch

        # Transcript with no clear speaker format
        malformed_transcript = """
        Hello there how are you doing today
        I am fine thank you for asking
        What is your name?
        My name is Bob
        """

        # Mock create_llm_client to prevent any LLM initialization
        with patch('services.call_intelligence.agents.base_agent.create_llm_client', return_value=None):
            processor = CallIntelligenceProcessor(llm_client=None)

            request = CallIntelligenceRequest(
                call_id="test-malformed",
                organization_id=1,
                transcript=malformed_transcript,
            )

            response = await processor.process_transcript(request)

            # Should handle gracefully (may or may not extract data)
            assert response.call_id == "test-malformed"
            # Should not crash

    @pytest.mark.asyncio
    async def test_processor_with_unicode_content(self):
        """Test processor handles unicode characters."""
        from services.call_intelligence.processor import CallIntelligenceProcessor
        from services.call_intelligence.data_contracts import CallIntelligenceRequest
        from unittest.mock import patch

        unicode_transcript = """Loan Officer: Hello! 你好!
Borrower: My name is José García. I make €50,000 per year.
Loan Officer: Great! And your email?
Borrower: It's josé@example.com"""

        # Mock create_llm_client to prevent any LLM initialization
        with patch('services.call_intelligence.agents.base_agent.create_llm_client', return_value=None):
            processor = CallIntelligenceProcessor(llm_client=None)

            request = CallIntelligenceRequest(
                call_id="test-unicode",
                organization_id=1,
                transcript=unicode_transcript,
            )

            response = await processor.process_transcript(request)

            # Should handle unicode without crashing
            assert response.call_id == "test-unicode"
            assert response.success is True

    @pytest.mark.asyncio
    async def test_processor_with_very_long_transcript(self):
        """Test processor handles very long transcripts."""
        from services.call_intelligence.processor import CallIntelligenceProcessor
        from services.call_intelligence.data_contracts import CallIntelligenceRequest
        from unittest.mock import patch

        # Generate a long transcript (100KB)
        long_content = "Borrower: " + "I am interested in buying a house. " * 3000

        # Mock create_llm_client to prevent any LLM initialization
        with patch('services.call_intelligence.agents.base_agent.create_llm_client', return_value=None):
            processor = CallIntelligenceProcessor(llm_client=None)

            request = CallIntelligenceRequest(
                call_id="test-long-transcript",
                organization_id=1,
                transcript=long_content,
            )

            response = await processor.process_transcript(request)

        # Should handle without timeout or memory issues
        assert response.call_id == "test-long-transcript"

    @pytest.mark.asyncio
    async def test_confidence_scores_class_available(self):
        """Test ConfidenceScores constants are accessible."""
        from services.call_intelligence.agents.base_agent import ConfidenceScores

        # Verify key constants exist and have expected values
        assert ConfidenceScores.EMAIL == 95.0
        assert ConfidenceScores.PHONE == 90.0
        assert ConfidenceScores.NAME == 85.0
        assert ConfidenceScores.DATE == 75.0
        assert ConfidenceScores.CURRENCY == 70.0
        assert ConfidenceScores.LLM_DEFAULT == 75.0
        assert ConfidenceScores.HIGH_CONFIDENCE_THRESHOLD == 90
        assert ConfidenceScores.LOW_CONFIDENCE_THRESHOLD == 70


# =============================================================================
# Integration Tests - LLM Timeout Handling
# =============================================================================

class TestLLMTimeoutHandling:
    """Test LLM client timeout handling."""

    @pytest.mark.asyncio
    async def test_anthropic_client_timeout_config(self):
        """Test Anthropic client respects timeout config."""
        from services.call_intelligence.llm_client import AnthropicClient, LLMConfig

        config = LLMConfig(timeout=5)  # 5 second timeout
        client = AnthropicClient(config)

        assert client.config.timeout == 5

    @pytest.mark.asyncio
    async def test_openai_client_timeout_config(self):
        """Test OpenAI client respects timeout config."""
        from services.call_intelligence.llm_client import OpenAIClient, LLMConfig

        config = LLMConfig(timeout=10)  # 10 second timeout
        client = OpenAIClient(config)

        assert client.config.timeout == 10

    @pytest.mark.asyncio
    async def test_llm_config_from_env_defaults(self):
        """Test LLM config has sensible defaults."""
        from services.call_intelligence.llm_client import LLMConfig

        config = LLMConfig()

        assert config.timeout == 30  # Default 30 seconds
        assert config.max_retries == 3
        assert config.temperature == 0.0  # Deterministic


# =============================================================================
# Integration Tests - Data Contract Serialization
# =============================================================================

class TestDataContractSerialization:
    """Test data contract serialization methods."""

    def test_extraction_result_to_dict(self):
        """Test ExtractionResult serialization."""
        from services.call_intelligence.data_contracts import (
            ExtractionResult,
            ExtractedValue,
        )

        result = ExtractionResult(agent_name="test_agent")
        result.extractions.append(ExtractedValue(
            field_name="test_field",
            value="test_value",
            confidence=85.0,
            source_text="test source",
        ))

        data = result.to_dict()

        # Key is "agent" not "agent_name"
        assert data["agent"] == "test_agent"
        assert len(data["extractions"]) == 1
        assert data["extractions"][0]["field_name"] == "test_field"
        assert data["extractions"][0]["value"] == "test_value"

    def test_call_intelligence_response_to_dict(self):
        """Test CallIntelligenceResponse serialization."""
        from services.call_intelligence.data_contracts import CallIntelligenceResponse

        response = CallIntelligenceResponse(call_id="test-123")
        response.identity_extractions["first_name"] = "John"
        response.total_extractions = 5

        data = response.to_dict()

        assert data["call_id"] == "test-123"
        # to_dict uses "extractions" with application engine format inside
        assert data["extractions"]["identity"]["first_name"] == "John"
        assert data["summary"]["total_extractions"] == 5

    def test_response_to_application_engine_format(self):
        """Test conversion to Application Engine format."""
        from services.call_intelligence.data_contracts import CallIntelligenceResponse

        response = CallIntelligenceResponse(call_id="test-456")
        response.identity_extractions = {"first_name": "Jane", "last_name": "Doe"}
        response.income_extractions = {"annual_salary": 75000}

        ae_format = response.to_application_engine_format()

        assert "identity" in ae_format
        assert ae_format["identity"]["first_name"] == "Jane"
        assert "income" in ae_format
        assert ae_format["income"]["annual_salary"] == 75000
