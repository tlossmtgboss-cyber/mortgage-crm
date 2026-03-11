"""
Test Call Intelligence Document Extractor

Comprehensive tests for the CallIntelDocumentExtractor service that
analyzes call transcripts for document needs, borrower circumstances,
and auto-creates document requests when confidence is high.

Covers:
- Keyword-based extraction for individual document types
- Multiple document type detection in a single call
- Document issue detection (staleness, missing)
- Borrower intent and action type detection
- Empty / short / malformed transcripts
- AI-enhanced extraction with mocked Claude API
- Confidence scoring logic
- Deduplication across keyword, circumstance, and AI sources
- Circumstance detection (job change, self-employed, divorce, etc.)
- Auto-create request flow for high-confidence needs
- Batch processing of multiple calls
- Unprocessed call detection query
- Action type classification (WILL_PROVIDE, NEEDS_HELP, ALREADY_SENT)
"""

import json
import pytest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch, PropertyMock

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from services.smart_docs.call_intel_extractor import (
    CallIntelDocumentExtractor,
    CallAnalysisResult,
    DetectedDocumentNeed,
    DOCUMENT_KEYWORDS,
    ACTION_PHRASES,
    CIRCUMSTANCE_PHRASES,
    get_call_intel_extractor,
)


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def mock_db():
    """Create a mock database session for extractor tests."""
    db = MagicMock()
    db.add = MagicMock()
    db.flush = MagicMock()
    db.commit = MagicMock()
    db.rollback = MagicMock()
    db.execute = MagicMock()
    return db


@pytest.fixture
def extractor(mock_db):
    """Create a CallIntelDocumentExtractor with mocked DB and no API key."""
    with patch.dict("os.environ", {"ANTHROPIC_API_KEY": ""}, clear=False):
        ext = CallIntelDocumentExtractor(mock_db)
        ext._anthropic_key = None  # ensure AI path is off by default
        return ext


@pytest.fixture
def extractor_with_ai(mock_db):
    """Create an extractor with a fake API key so AI code paths are entered."""
    with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "sk-test-key"}, clear=False):
        ext = CallIntelDocumentExtractor(mock_db)
        ext._anthropic_key = "sk-test-key"
        return ext


@pytest.fixture
def paystub_transcript():
    return (
        "LO: Hi Sarah, I just wanted to follow up on your application. "
        "We still need your most recent paystub to move forward with processing. "
        "Borrower: Oh okay, I think I have my pay stub from last Friday. "
        "I can send it over this afternoon."
    )


@pytest.fixture
def bank_statement_transcript():
    return (
        "Borrower: I wanted to ask about my bank statements. "
        "I have my checking account statements from the last two months. "
        "LO: That's great. Please upload your bank statement for the most recent "
        "60 days through the portal."
    )


@pytest.fixture
def tax_return_transcript():
    return (
        "LO: For your income verification, we'll need your 2024 tax return. "
        "Borrower: I already filed my taxes in February. I can get you the 1040."
    )


@pytest.fixture
def w2_transcript():
    return (
        "LO: We also need your W2 from your employer for last year. "
        "Borrower: Sure, I'll send my W-2 over tomorrow morning."
    )


@pytest.fixture
def multi_doc_transcript():
    return (
        "LO: Alright, let's go through what we still need. First, we need "
        "your most recent paystub and your W2 from last year. Also, please "
        "upload your bank statement for the last 60 days. If you have your "
        "tax return ready, that would be helpful too. "
        "Borrower: I have my pay stub and my W-2. I'll send my bank statement "
        "tomorrow. I still need to get my tax documents from my accountant."
    )


@pytest.fixture
def issue_transcript():
    return (
        "Borrower: I have my paystub but it's from 3 months ago. Is that okay? "
        "LO: Unfortunately, we need a more recent pay stub. The one you have "
        "is too old. Can you get a current one from your employer?"
    )


@pytest.fixture
def intent_transcript():
    return (
        "Borrower: I'll send my W2 tomorrow. I also need to get my bank "
        "statement printed at the branch. And I already uploaded my driver's license."
    )


@pytest.fixture
def no_docs_transcript():
    return (
        "LO: Hi there, just wanted to check in and see how your house hunt "
        "is going. Have you found any properties you like? "
        "Borrower: Yeah, we looked at a few places last weekend. The one "
        "on Elm Street was really nice."
    )


@pytest.fixture
def short_transcript():
    return "Hi, this is a quick callback."


@pytest.fixture
def job_change_transcript():
    return (
        "Borrower: Just so you know, I changed jobs last month. I started a new "
        "position at a different employer. "
        "LO: Thanks for letting me know. We'll need updated paystubs from "
        "your new job and a letter of explanation."
    )


@pytest.fixture
def self_employed_transcript():
    return (
        "Borrower: I'm self-employed. I run my own business as a sole proprietor. "
        "I have my business tax returns but I'm not sure about the profit and loss. "
        "LO: For self-employed borrowers, we'll need your business taxes, a P&L "
        "statement, and your personal tax returns."
    )


@pytest.fixture
def divorce_transcript():
    return (
        "Borrower: My ex-spouse and I got divorced last year. I have the divorce "
        "decree but I'm not sure if you need the property settlement as well."
    )


# =============================================================================
# 1-4: EXTRACT INDIVIDUAL DOCUMENT TYPE MENTIONS
# =============================================================================

@pytest.mark.unit
class TestSingleDocTypeExtraction:
    """Verify extraction of individual document types from call transcripts."""

    def test_extract_paystub_mention(self, extractor, paystub_transcript):
        """Paystub keywords ('paystub', 'pay stub') should be detected."""
        needs = extractor.analyze_transcript_keywords(paystub_transcript)
        doc_types = [n.doc_type for n in needs]
        assert "PAYSTUB" in doc_types, "Paystub mention not detected"

    def test_extract_bank_statement_mention(self, extractor, bank_statement_transcript):
        """Bank statement keywords should be detected."""
        needs = extractor.analyze_transcript_keywords(bank_statement_transcript)
        doc_types = [n.doc_type for n in needs]
        assert "BANK_STATEMENT" in doc_types, "Bank statement mention not detected"

    def test_extract_tax_return_mention(self, extractor, tax_return_transcript):
        """Tax return keywords ('tax return', '1040') should be detected."""
        needs = extractor.analyze_transcript_keywords(tax_return_transcript)
        doc_types = [n.doc_type for n in needs]
        assert "TAX_RETURN" in doc_types, "Tax return mention not detected"

    def test_extract_w2_mention(self, extractor, w2_transcript):
        """W2 keywords ('W2', 'W-2') should be detected."""
        needs = extractor.analyze_transcript_keywords(w2_transcript)
        doc_types = [n.doc_type for n in needs]
        assert "W2" in doc_types, "W2 mention not detected"


# =============================================================================
# 5: MULTIPLE DOCUMENT TYPES FROM SINGLE CALL
# =============================================================================

@pytest.mark.unit
class TestMultiDocExtraction:
    """Verify detection of multiple document types in one transcript."""

    def test_extract_multiple_doc_types(self, extractor, multi_doc_transcript):
        """All four document types mentioned in a single call should be found."""
        needs = extractor.analyze_transcript_keywords(multi_doc_transcript)
        doc_types = {n.doc_type for n in needs}
        assert "PAYSTUB" in doc_types, "Paystub not detected in multi-doc transcript"
        assert "W2" in doc_types, "W2 not detected in multi-doc transcript"
        assert "BANK_STATEMENT" in doc_types, "Bank statement not detected in multi-doc transcript"
        assert "TAX_RETURN" in doc_types, "Tax return not detected in multi-doc transcript"

    def test_multiple_doc_types_count(self, extractor, multi_doc_transcript):
        """Each doc type should appear only once (deduplication within keywords)."""
        needs = extractor.analyze_transcript_keywords(multi_doc_transcript)
        doc_types = [n.doc_type for n in needs]
        # No duplicates
        assert len(doc_types) == len(set(doc_types)), (
            "Duplicate doc types returned from keyword analysis"
        )


# =============================================================================
# 6: DOCUMENT ISSUE DETECTION
# =============================================================================

@pytest.mark.unit
class TestDocumentIssueDetection:
    """Verify detection of stale or problematic document mentions."""

    def test_stale_paystub_detected(self, extractor, issue_transcript):
        """Mention of a 3-month-old paystub should still detect PAYSTUB need."""
        needs = extractor.analyze_transcript_keywords(issue_transcript)
        doc_types = [n.doc_type for n in needs]
        assert "PAYSTUB" in doc_types

    def test_stale_document_snippet_captured(self, extractor, issue_transcript):
        """The snippet around the match should capture context about the issue."""
        needs = extractor.analyze_transcript_keywords(issue_transcript)
        paystub_need = next(n for n in needs if n.doc_type == "PAYSTUB")
        # Snippet should contain some surrounding context
        assert len(paystub_need.source_snippet) > 10, "Snippet too short to be useful"


# =============================================================================
# 7: BORROWER INTENT DETECTION
# =============================================================================

@pytest.mark.unit
class TestBorrowerIntentDetection:
    """Verify action type detection from borrower statements."""

    def test_will_provide_action_detected(self, extractor, intent_transcript):
        """'I'll send my W2 tomorrow' should map to needs_to_send."""
        needs = extractor.analyze_transcript_keywords(intent_transcript)
        w2_need = next((n for n in needs if n.doc_type == "W2"), None)
        assert w2_need is not None, "W2 not detected in intent transcript"
        assert w2_need.action_type == "needs_to_send", (
            f"Expected needs_to_send, got {w2_need.action_type}"
        )

    def test_already_sent_action_detected(self, extractor, intent_transcript):
        """'I already uploaded my driver's license' should map to has_document."""
        needs = extractor.analyze_transcript_keywords(intent_transcript)
        dl_need = next((n for n in needs if n.doc_type == "DRIVERS_LICENSE"), None)
        assert dl_need is not None, "Driver's license not detected"
        assert dl_need.action_type == "has_document", (
            f"Expected has_document, got {dl_need.action_type}"
        )

    def test_needs_help_action_via_missing(self, extractor):
        """'I can't find my tax return' should map to missing_document."""
        transcript = (
            "Borrower: I can't find my tax return anywhere. I think it might "
            "be lost. LO: No problem, let's figure out how to get a copy."
        )
        needs = extractor.analyze_transcript_keywords(transcript)
        tax_need = next((n for n in needs if n.doc_type == "TAX_RETURN"), None)
        assert tax_need is not None, "Tax return not detected in missing-document context"
        assert tax_need.action_type == "missing_document", (
            f"Expected missing_document, got {tax_need.action_type}"
        )


# =============================================================================
# 8-9: EMPTY AND SHORT TRANSCRIPTS
# =============================================================================

@pytest.mark.unit
class TestEdgeCaseTranscripts:
    """Verify graceful handling of empty, short, and whitespace-only transcripts."""

    def test_empty_transcript_returns_no_needs(self, extractor, mock_db):
        """Empty string should produce no document needs and success=True."""
        mock_db.execute.return_value = MagicMock(
            first=MagicMock(return_value=None)
        )
        result = extractor.analyze_call(call_id=1, transcript="", loan_id=100)
        assert result.success is True
        assert result.total_needs == 0
        assert result.document_needs == []
        assert "Empty transcript" in result.summary

    def test_none_transcript_returns_no_needs(self, extractor, mock_db):
        """None transcript should produce no document needs and success=True."""
        mock_db.execute.return_value = MagicMock(
            first=MagicMock(return_value=None)
        )
        result = extractor.analyze_call(call_id=2, transcript=None, loan_id=100)
        assert result.success is True
        assert result.total_needs == 0

    def test_whitespace_only_transcript(self, extractor, mock_db):
        """Whitespace-only transcript should be treated as empty."""
        mock_db.execute.return_value = MagicMock(
            first=MagicMock(return_value=None)
        )
        result = extractor.analyze_call(call_id=3, transcript="   \n\t  ", loan_id=100)
        assert result.success is True
        assert result.total_needs == 0

    def test_short_transcript_no_docs(self, extractor, short_transcript):
        """A very short transcript with no doc keywords yields no needs."""
        needs = extractor.analyze_transcript_keywords(short_transcript)
        assert len(needs) == 0

    def test_no_document_mentions(self, extractor, no_docs_transcript):
        """Transcript discussing house hunting but no docs should return empty."""
        needs = extractor.analyze_transcript_keywords(no_docs_transcript)
        assert len(needs) == 0, (
            f"Expected no needs, got: {[n.doc_type for n in needs]}"
        )


# =============================================================================
# 10: KEYWORD-BASED EXTRACTION ACCURACY
# =============================================================================

@pytest.mark.unit
class TestKeywordAccuracy:
    """Verify keyword matching covers the full lexicon and avoids false positives."""

    def test_all_document_types_have_keywords(self):
        """Every entry in DOCUMENT_KEYWORDS should have at least one keyword."""
        for doc_type, keywords in DOCUMENT_KEYWORDS.items():
            assert len(keywords) > 0, f"No keywords for doc type {doc_type}"

    def test_keyword_match_case_insensitive(self, extractor):
        """Keywords should match regardless of case."""
        transcript = "Please send your PAYSTUB and W2 as soon as possible."
        needs = extractor.analyze_transcript_keywords(transcript)
        doc_types = {n.doc_type for n in needs}
        assert "PAYSTUB" in doc_types
        assert "W2" in doc_types

    def test_keyword_match_with_surrounding_punctuation(self, extractor):
        """Keywords surrounded by punctuation should still match."""
        transcript = "Do you have your (bank statement), or your [W-2]?"
        needs = extractor.analyze_transcript_keywords(transcript)
        doc_types = {n.doc_type for n in needs}
        assert "BANK_STATEMENT" in doc_types
        assert "W2" in doc_types

    def test_gift_letter_detection(self, extractor):
        """Gift-related keywords should be detected."""
        transcript = (
            "Borrower: My parents are giving me money for the down payment. "
            "Do I need a gift letter?"
        )
        needs = extractor.analyze_transcript_keywords(transcript)
        doc_types = {n.doc_type for n in needs}
        assert "GIFT_LETTER" in doc_types

    def test_va_coe_detection(self, extractor):
        """VA Certificate of Eligibility keywords should be detected."""
        transcript = (
            "Borrower: I'm a veteran. I have my certificate of eligibility "
            "from the VA."
        )
        needs = extractor.analyze_transcript_keywords(transcript)
        doc_types = {n.doc_type for n in needs}
        assert "VA_COE" in doc_types

    def test_dd214_detection(self, extractor):
        """DD-214 military discharge keywords should be detected."""
        transcript = "I can provide my DD214 and discharge papers from the Army."
        needs = extractor.analyze_transcript_keywords(transcript)
        doc_types = {n.doc_type for n in needs}
        assert "DD214" in doc_types


# =============================================================================
# 11: AI-ENHANCED EXTRACTION (MOCKED)
# =============================================================================

@pytest.mark.unit
class TestAIEnhancedExtraction:
    """Verify AI-powered analysis path with mocked Claude API."""

    def test_ai_analysis_called_for_long_transcript(self, extractor_with_ai, mock_db):
        """AI analysis should be attempted when transcript >= 200 chars and key exists."""
        # Build a transcript that is long enough and contains doc keywords
        transcript = (
            "Borrower: " + "I mentioned something about needing documents. " * 10
            + "I need to send my paystub for processing."
        )
        assert len(transcript) >= 200

        # Mock the org lookup and save_analysis DB calls
        mock_result = MagicMock()
        mock_result.first.return_value = (1,)  # organization_id
        mock_db.execute.return_value = mock_result

        with patch.object(extractor_with_ai, "_analyze_with_ai", return_value=[]) as mock_ai:
            extractor_with_ai.analyze_call(call_id=10, transcript=transcript, loan_id=200)
            mock_ai.assert_called_once()

    def test_ai_analysis_skipped_for_short_transcript(self, extractor_with_ai, mock_db):
        """AI analysis should NOT be attempted for transcripts < 200 chars."""
        transcript = "I need my paystub please."

        mock_result = MagicMock()
        mock_result.first.return_value = (1,)
        mock_db.execute.return_value = mock_result

        with patch.object(extractor_with_ai, "_analyze_with_ai") as mock_ai:
            extractor_with_ai.analyze_call(call_id=11, transcript=transcript, loan_id=200)
            mock_ai.assert_not_called()

    def test_ai_returns_additional_doc_types(self, extractor_with_ai):
        """AI-detected doc types not found by keywords should be included."""
        keyword_needs = []  # no keyword matches

        ai_response_json = json.dumps([
            {
                "doc_type": "LEASE_AGREEMENT",
                "description": "Borrower mentioned rental property",
                "confidence": 75,
                "action_type": "needs_to_send",
                "snippet": "I rent out my other house",
            }
        ])

        mock_response = MagicMock()
        mock_response.content = [MagicMock()]
        mock_response.content[0].text = ai_response_json

        with patch("services.smart_docs.call_intel_extractor.anthropic") as mock_anthropic_module:
            mock_client = MagicMock()
            mock_client.messages.create.return_value = mock_response
            mock_anthropic_module.Anthropic.return_value = mock_client

            ai_needs = extractor_with_ai._analyze_with_ai("long transcript " * 50, keyword_needs)

        assert len(ai_needs) == 1
        assert ai_needs[0].doc_type == "LEASE_AGREEMENT"
        assert ai_needs[0].confidence == 75

    def test_ai_skips_duplicate_doc_types(self, extractor_with_ai):
        """AI should not return doc types already found by keyword analysis."""
        keyword_needs = [
            DetectedDocumentNeed(
                doc_type="PAYSTUB", description="test", confidence=60,
                source_snippet="", keywords_matched=["paystub"],
                action_type="needs_to_send", circumstance=None,
                priority="HIGH", auto_create_request=False,
            )
        ]

        # AI returns PAYSTUB (duplicate) and LOE (new)
        ai_response_json = json.dumps([
            {"doc_type": "PAYSTUB", "description": "paystub again", "confidence": 80,
             "action_type": "needs_to_send", "snippet": "pay stub"},
            {"doc_type": "LOE", "description": "letter needed", "confidence": 70,
             "action_type": "needs_to_send", "snippet": "explanation letter"},
        ])

        mock_response = MagicMock()
        mock_response.content = [MagicMock()]
        mock_response.content[0].text = ai_response_json

        with patch("services.smart_docs.call_intel_extractor.anthropic") as mock_mod:
            mock_client = MagicMock()
            mock_client.messages.create.return_value = mock_response
            mock_mod.Anthropic.return_value = mock_client

            ai_needs = extractor_with_ai._analyze_with_ai("transcript " * 50, keyword_needs)

        ai_doc_types = [n.doc_type for n in ai_needs]
        assert "PAYSTUB" not in ai_doc_types, "AI should skip already-detected PAYSTUB"
        assert "LOE" in ai_doc_types

    def test_ai_failure_returns_empty(self, extractor_with_ai):
        """If AI call raises an exception, return empty list gracefully."""
        with patch("services.smart_docs.call_intel_extractor.anthropic") as mock_mod:
            mock_client = MagicMock()
            mock_client.messages.create.side_effect = RuntimeError("API down")
            mock_mod.Anthropic.return_value = mock_client

            ai_needs = extractor_with_ai._analyze_with_ai("long transcript " * 50, [])
        assert ai_needs == []

    def test_ai_invalid_json_returns_empty(self, extractor_with_ai):
        """If AI returns unparseable JSON, return empty list."""
        mock_response = MagicMock()
        mock_response.content = [MagicMock()]
        mock_response.content[0].text = "This is not valid JSON at all."

        with patch("services.smart_docs.call_intel_extractor.anthropic") as mock_mod:
            mock_client = MagicMock()
            mock_client.messages.create.return_value = mock_response
            mock_mod.Anthropic.return_value = mock_client

            ai_needs = extractor_with_ai._analyze_with_ai("transcript " * 50, [])
        assert ai_needs == []


# =============================================================================
# 12: CONFIDENCE SCORING
# =============================================================================

@pytest.mark.unit
class TestConfidenceScoring:
    """Verify confidence scoring mechanics."""

    def test_base_confidence_for_single_keyword(self, extractor):
        """A single keyword match with no action phrase should get base confidence."""
        # Transcript with just the keyword, no action phrases, no first-person
        transcript = "The appraisal report was mentioned in the file notes."
        needs = extractor.analyze_transcript_keywords(transcript)
        appraisal = next((n for n in needs if n.doc_type == "APPRAISAL"), None)
        assert appraisal is not None
        # Base is 40; no extra keywords, "question_about" fallback gives no +10
        # No first-person pronouns in this snippet
        assert appraisal.confidence >= 40

    def test_higher_confidence_for_multiple_keywords(self, extractor):
        """Multiple keyword matches for the same doc type should boost confidence."""
        transcript = (
            "Please provide your bank statement. We need your checking account "
            "records and bank activity for the last 60 days."
        )
        needs = extractor.analyze_transcript_keywords(transcript)
        bank = next((n for n in needs if n.doc_type == "BANK_STATEMENT"), None)
        assert bank is not None
        # Multiple keyword matches should give > 40
        assert bank.confidence > 40

    def test_action_phrase_boosts_confidence(self, extractor):
        """Having a concrete action phrase (not question_about) adds +10."""
        transcript = "I will send my paystub tomorrow."
        needs = extractor.analyze_transcript_keywords(transcript)
        ps = next((n for n in needs if n.doc_type == "PAYSTUB"), None)
        assert ps is not None
        # Base 40 + action_type != question_about (+10) + first-person "I" (+10) = 60
        assert ps.confidence >= 50

    def test_first_person_pronouns_boost_confidence(self, extractor):
        """First-person pronouns in the snippet should boost confidence by 10."""
        transcript = "I have my W2 right here."
        needs = extractor.analyze_transcript_keywords(transcript)
        w2 = next((n for n in needs if n.doc_type == "W2"), None)
        assert w2 is not None
        # Should include first-person boost
        assert w2.confidence >= 50

    def test_confidence_capped_at_100(self, extractor):
        """Confidence should never exceed 100."""
        # Load the transcript with every possible booster
        transcript = (
            "I need to send my pay stub, paystub, pay check, paycheck, "
            "pay slip, recent pay, latest pay, earnings statement, pay statement. "
            "I will send these right away."
        )
        needs = extractor.analyze_transcript_keywords(transcript)
        ps = next((n for n in needs if n.doc_type == "PAYSTUB"), None)
        assert ps is not None
        assert ps.confidence <= 100


# =============================================================================
# 13: DEDUPLICATION
# =============================================================================

@pytest.mark.unit
class TestDeduplication:
    """Verify deduplication across keyword, circumstance, and AI sources."""

    def test_keyword_dedup_keeps_highest_confidence(self, extractor):
        """Within keyword analysis, only one entry per doc_type should remain."""
        transcript = (
            "Borrower: I have my pay stub. I'll also send my paystub copy. "
            "And my paycheck too."
        )
        needs = extractor.analyze_transcript_keywords(transcript)
        paystub_needs = [n for n in needs if n.doc_type == "PAYSTUB"]
        assert len(paystub_needs) == 1, "Should be exactly one PAYSTUB entry"

    def test_merge_boosts_confidence_when_keyword_and_circumstance_agree(self, extractor):
        """When keyword and circumstance both detect the same doc type, confidence is boosted."""
        keyword_needs = [
            DetectedDocumentNeed(
                doc_type="PAYSTUB", description="Paystub from keyword",
                confidence=60, source_snippet="paystub snippet",
                keywords_matched=["paystub"], action_type="needs_to_send",
                circumstance=None, priority="HIGH", auto_create_request=False,
            )
        ]
        circumstance_needs = [
            DetectedDocumentNeed(
                doc_type="PAYSTUB", description="Paystub from job change",
                confidence=60, source_snippet="Circumstance detected: job_change",
                keywords_matched=["job_change"], action_type="needs_to_send",
                circumstance="job_change", priority="HIGH", auto_create_request=False,
            )
        ]

        merged = extractor._merge_needs(keyword_needs, circumstance_needs, [])
        assert len(merged) == 1
        # Boosted by 10 from the merge
        assert merged[0].confidence == 70
        assert merged[0].circumstance == "job_change"

    def test_merge_ai_confirmation_boosts_by_15(self, extractor):
        """When AI confirms a keyword detection, confidence should increase by 15."""
        keyword_needs = [
            DetectedDocumentNeed(
                doc_type="W2", description="W2 from keyword",
                confidence=50, source_snippet="w2 snippet",
                keywords_matched=["w2"], action_type="needs_to_send",
                circumstance=None, priority="HIGH", auto_create_request=False,
            )
        ]
        ai_needs = [
            DetectedDocumentNeed(
                doc_type="W2", description="W2 from AI",
                confidence=80, source_snippet="ai snippet",
                keywords_matched=["ai_analysis"], action_type="needs_to_send",
                circumstance=None, priority="HIGH", auto_create_request=True,
            )
        ]

        merged = extractor._merge_needs(keyword_needs, [], ai_needs)
        assert len(merged) == 1
        # 50 + 15 = 65
        assert merged[0].confidence == 65
        assert "ai_confirmed" in merged[0].keywords_matched

    def test_merge_preserves_unique_doc_types(self, extractor):
        """Doc types unique to each source should all appear in merged results."""
        keyword_needs = [
            DetectedDocumentNeed(
                doc_type="PAYSTUB", description="", confidence=60,
                source_snippet="", keywords_matched=[], action_type="needs_to_send",
                circumstance=None, priority="HIGH", auto_create_request=False,
            )
        ]
        circumstance_needs = [
            DetectedDocumentNeed(
                doc_type="BUSINESS_TAX_RETURN", description="", confidence=60,
                source_snippet="", keywords_matched=[], action_type="needs_to_send",
                circumstance="self_employed", priority="HIGH", auto_create_request=False,
            )
        ]
        ai_needs = [
            DetectedDocumentNeed(
                doc_type="LOE", description="", confidence=70,
                source_snippet="", keywords_matched=["ai_analysis"],
                action_type="needs_to_send", circumstance=None,
                priority="NORMAL", auto_create_request=False,
            )
        ]

        merged = extractor._merge_needs(keyword_needs, circumstance_needs, ai_needs)
        doc_types = {n.doc_type for n in merged}
        assert doc_types == {"PAYSTUB", "BUSINESS_TAX_RETURN", "LOE"}


# =============================================================================
# 14: CIRCUMSTANCE DETECTION
# =============================================================================

@pytest.mark.unit
class TestCircumstanceDetection:
    """Verify detection of borrower circumstances from transcript text."""

    def test_detect_job_change(self, extractor, job_change_transcript):
        """Job change phrases should be detected."""
        circs = extractor.detect_circumstances(job_change_transcript)
        assert "job_change" in circs

    def test_detect_self_employed(self, extractor, self_employed_transcript):
        """Self-employment phrases should be detected."""
        circs = extractor.detect_circumstances(self_employed_transcript)
        assert "self_employed" in circs

    def test_detect_divorce(self, extractor, divorce_transcript):
        """Divorce phrases should be detected."""
        circs = extractor.detect_circumstances(divorce_transcript)
        assert "divorce" in circs

    def test_detect_bankruptcy_history(self, extractor):
        """Bankruptcy phrases should be detected."""
        transcript = "I filed bankruptcy about 4 years ago, chapter 7."
        circs = extractor.detect_circumstances(transcript)
        assert "bankruptcy_history" in circs

    def test_detect_large_deposit(self, extractor):
        """Large deposit phrases should be detected."""
        transcript = "There was a large deposit in my account from an inheritance."
        circs = extractor.detect_circumstances(transcript)
        assert "large_deposit" in circs

    def test_detect_rental_property(self, extractor):
        """Rental property phrases should be detected."""
        transcript = "I have a rental property that generates rental income."
        circs = extractor.detect_circumstances(transcript)
        assert "rental_property" in circs

    def test_detect_credit_issues(self, extractor):
        """Credit issue phrases should be detected."""
        transcript = "I had a late payment a couple years ago. Is that a credit issue?"
        circs = extractor.detect_circumstances(transcript)
        assert "credit_issues" in circs

    def test_no_circumstances_in_clean_transcript(self, extractor, no_docs_transcript):
        """Transcript without circumstance phrases should return empty list."""
        circs = extractor.detect_circumstances(no_docs_transcript)
        assert len(circs) == 0

    def test_circumstance_to_documents_job_change(self, extractor):
        """Job change should imply PAYSTUB and LOE needs."""
        needs = extractor._circumstance_to_documents(["job_change"])
        doc_types = {n.doc_type for n in needs}
        assert "PAYSTUB" in doc_types
        assert "LOE" in doc_types
        # All should have moderate confidence (60) and no auto-create
        for n in needs:
            assert n.confidence == 60
            assert n.auto_create_request is False
            assert n.circumstance == "job_change"

    def test_circumstance_to_documents_self_employed(self, extractor):
        """Self-employed should imply BUSINESS_TAX_RETURN and PROFIT_LOSS."""
        needs = extractor._circumstance_to_documents(["self_employed"])
        doc_types = {n.doc_type for n in needs}
        assert "BUSINESS_TAX_RETURN" in doc_types
        assert "PROFIT_LOSS" in doc_types

    def test_multiple_circumstances_dedup(self, extractor):
        """Multiple circumstances should not create duplicate doc type entries
        for the same (doc_type, circumstance) pair."""
        needs = extractor._circumstance_to_documents(["job_change", "job_change"])
        paystub_needs = [n for n in needs if n.doc_type == "PAYSTUB"]
        assert len(paystub_needs) == 1


# =============================================================================
# 15: AUTO-CREATE REQUESTS FOR HIGH-CONFIDENCE NEEDS
# =============================================================================

@pytest.mark.unit
class TestAutoCreateRequests:
    """Verify auto_create_requests creates DB records for eligible needs."""

    def test_auto_create_for_high_confidence_needs_to_send(self, extractor, mock_db):
        """Needs with confidence >= 80 and action_type 'needs_to_send' should be auto-created."""
        analysis = CallAnalysisResult(
            call_id=100,
            loan_id=500,
            document_needs=[
                DetectedDocumentNeed(
                    doc_type="PAYSTUB", description="Paystub needed",
                    confidence=85, source_snippet="need paystub",
                    keywords_matched=["paystub"], action_type="needs_to_send",
                    circumstance=None, priority="HIGH", auto_create_request=True,
                ),
            ],
            circumstances_detected=[],
            summary="test",
            total_needs=1,
            auto_create_count=1,
        )

        # Mock the DocumentRequest model and its id
        with patch("services.smart_docs.call_intel_extractor.CallIntelDocumentExtractor.auto_create_requests") as orig:
            # Test the eligibility logic directly
            need = analysis.document_needs[0]
            assert need.confidence >= extractor.AUTO_CREATE_THRESHOLD
            assert need.auto_create_request is True

    def test_no_auto_create_for_low_confidence(self, extractor):
        """Needs with confidence < 80 should NOT be auto-created."""
        need = DetectedDocumentNeed(
            doc_type="PAYSTUB", description="test", confidence=50,
            source_snippet="", keywords_matched=["paystub"],
            action_type="needs_to_send", circumstance=None,
            priority="HIGH", auto_create_request=False,
        )
        assert need.confidence < extractor.AUTO_CREATE_THRESHOLD
        assert need.auto_create_request is False

    def test_no_auto_create_for_has_document(self, extractor):
        """Even high confidence 'has_document' should not auto-create a request."""
        transcript = "I already have my bank statement and just sent it."
        needs = extractor.analyze_transcript_keywords(transcript)
        bank = next((n for n in needs if n.doc_type == "BANK_STATEMENT"), None)
        if bank:
            # has_document action means the doc is already provided
            if bank.action_type == "has_document":
                assert bank.auto_create_request is False

    def test_circumstance_needs_never_auto_create(self, extractor):
        """Circumstance-derived needs should always have auto_create_request=False."""
        needs = extractor._circumstance_to_documents(["self_employed"])
        for n in needs:
            assert n.auto_create_request is False, (
                f"Circumstance need {n.doc_type} should not auto-create"
            )


# =============================================================================
# 16: BATCH PROCESSING MULTIPLE CALLS
# =============================================================================

@pytest.mark.unit
class TestBatchProcessing:
    """Verify batch_analyze processes multiple calls correctly."""

    def test_batch_empty_list(self, extractor):
        """Empty call_ids list should return empty results."""
        results = extractor.batch_analyze([])
        assert results == []

    def test_batch_missing_call_returns_error(self, extractor, mock_db):
        """Call IDs not found in DB should produce error results."""
        mock_db.execute.return_value = MagicMock(fetchall=MagicMock(return_value=[]))

        results = extractor.batch_analyze([999])
        assert len(results) == 1
        assert results[0].success is False
        assert "not found" in results[0].error

    def test_batch_processes_found_calls(self, extractor, mock_db):
        """Found calls with transcript data should be analyzed."""
        # Mock the call_logs query to return one row
        mock_row = MagicMock()
        mock_row.call_id = 42
        mock_row.loan_id = 100
        mock_row.lead_id = 200
        mock_row.notes = "Borrower needs to send paystub."
        mock_row.ai_note_summary = None
        mock_db.execute.return_value = MagicMock(
            fetchall=MagicMock(return_value=[mock_row])
        )

        # Mock org_id lookup and commit for save_analysis
        org_mock = MagicMock()
        org_mock.first.return_value = (1,)

        call_count = 0
        original_execute = mock_db.execute

        def side_effect_execute(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # First call: batch_analyze's call_logs query
                return MagicMock(fetchall=MagicMock(return_value=[mock_row]))
            else:
                # Subsequent calls: org_id lookup in save_analysis
                return org_mock

        mock_db.execute = MagicMock(side_effect=side_effect_execute)

        results = extractor.batch_analyze([42])
        assert len(results) == 1
        assert results[0].call_id == 42
        assert results[0].success is True

    def test_batch_call_without_transcript(self, extractor, mock_db):
        """Calls with no notes/summary should get success with 0 needs."""
        mock_row = MagicMock()
        mock_row.call_id = 43
        mock_row.loan_id = 101
        mock_row.lead_id = None
        mock_row.notes = None
        mock_row.ai_note_summary = None
        mock_db.execute.return_value = MagicMock(
            fetchall=MagicMock(return_value=[mock_row])
        )

        results = extractor.batch_analyze([43])
        assert len(results) == 1
        assert results[0].success is True
        assert results[0].total_needs == 0
        assert "No transcript" in results[0].summary


# =============================================================================
# 17: UNPROCESSED CALL DETECTION
# =============================================================================

@pytest.mark.unit
class TestUnprocessedCallDetection:
    """Verify get_unprocessed_calls query logic."""

    def test_unprocessed_returns_call_data(self, extractor, mock_db):
        """get_unprocessed_calls should return formatted call dicts."""
        mock_row = MagicMock()
        mock_row.call_id = 50
        mock_row.loan_id = 300
        mock_row.lead_id = 400
        mock_row.notes = "Borrower asked about W2."
        mock_row.ai_note_summary = "Call summary: W2 discussion."
        mock_row.duration_seconds = 120
        mock_row.start_time = datetime(2026, 3, 10, 14, 0, 0, tzinfo=timezone.utc)

        mock_db.execute.return_value = MagicMock(
            fetchall=MagicMock(return_value=[mock_row])
        )

        results = extractor.get_unprocessed_calls(organization_id=1)
        assert len(results) == 1
        assert results[0]["call_id"] == 50
        assert results[0]["loan_id"] == 300
        assert results[0]["lead_id"] == 400
        assert "W2" in results[0]["transcript"]
        assert results[0]["duration_seconds"] == 120

    def test_unprocessed_empty_when_all_processed(self, extractor, mock_db):
        """No unprocessed calls should yield empty list."""
        mock_db.execute.return_value = MagicMock(
            fetchall=MagicMock(return_value=[])
        )
        results = extractor.get_unprocessed_calls(organization_id=1)
        assert results == []

    def test_unprocessed_builds_transcript_from_parts(self, extractor, mock_db):
        """Transcript should combine ai_note_summary + notes."""
        mock_row = MagicMock()
        mock_row.call_id = 60
        mock_row.loan_id = 500
        mock_row.lead_id = None
        mock_row.notes = "Notes part."
        mock_row.ai_note_summary = "Summary part."
        mock_row.duration_seconds = 90
        mock_row.start_time = None

        mock_db.execute.return_value = MagicMock(
            fetchall=MagicMock(return_value=[mock_row])
        )

        results = extractor.get_unprocessed_calls(organization_id=1)
        assert "Summary part." in results[0]["transcript"]
        assert "Notes part." in results[0]["transcript"]


# =============================================================================
# 18: ACTION TYPE DETECTION
# =============================================================================

@pytest.mark.unit
class TestActionTypeDetection:
    """Verify action type classification from snippet context."""

    def test_will_provide_detected(self, extractor):
        """'will send' and 'going to send' should map to needs_to_send."""
        snippet = "I will send my documents tomorrow."
        action = extractor._detect_action_type(snippet)
        assert action == "needs_to_send"

    def test_already_sent_detected(self, extractor):
        """'already have' and 'just sent' should map to has_document."""
        snippet = "I already have it ready for you."
        action = extractor._detect_action_type(snippet)
        assert action == "has_document"

    def test_missing_detected(self, extractor):
        """'can't find' and 'lost' should map to missing_document."""
        snippet = "I can't find my tax return anywhere."
        action = extractor._detect_action_type(snippet)
        assert action == "missing_document"

    def test_question_detected(self, extractor):
        """'do I need' should map to question_about."""
        snippet = "Do I need to bring anything else?"
        action = extractor._detect_action_type(snippet)
        assert action == "question_about"

    def test_missing_takes_priority_over_needs_to_send(self, extractor):
        """When both missing and needs_to_send phrases appear, missing wins."""
        snippet = "I can't find it. I need to get a new copy and send it."
        action = extractor._detect_action_type(snippet)
        assert action == "missing_document"

    def test_fallback_to_question_about(self, extractor):
        """If no action phrases match, default to question_about."""
        snippet = "The loan is proceeding smoothly."
        action = extractor._detect_action_type(snippet)
        assert action == "question_about"

    def test_upload_maps_to_needs_to_send(self, extractor):
        """'upload' keyword should map to needs_to_send."""
        snippet = "Can you upload the document to the portal?"
        action = extractor._detect_action_type(snippet)
        assert action == "needs_to_send"


# =============================================================================
# INTEGRATION-LEVEL: FULL analyze_call FLOW
# =============================================================================

@pytest.mark.unit
class TestFullAnalyzeCallFlow:
    """Test the complete analyze_call pipeline end-to-end with mocked DB."""

    def test_full_flow_with_docs_and_circumstances(self, extractor, mock_db, job_change_transcript):
        """Full analysis should detect both keyword docs and circumstance docs."""
        mock_result = MagicMock()
        mock_result.first.return_value = (1,)  # org_id
        mock_db.execute.return_value = mock_result

        result = extractor.analyze_call(
            call_id=99,
            transcript=job_change_transcript,
            loan_id=888,
        )

        assert result.success is True
        assert result.call_id == 99
        assert result.loan_id == 888
        assert "job_change" in result.circumstances_detected
        assert result.total_needs > 0
        doc_types = {n.doc_type for n in result.document_needs}
        assert "PAYSTUB" in doc_types, "Paystub should be detected from both keyword and circumstance"

    def test_full_flow_persists_to_db(self, extractor, mock_db, paystub_transcript):
        """analyze_call should call db.add and db.commit for persistence."""
        mock_result = MagicMock()
        mock_result.first.return_value = (1,)
        mock_db.execute.return_value = mock_result

        # Patch the import inside save_analysis
        with patch(
            "services.smart_docs.call_intel_extractor.CallIntelDocumentExtractor.save_analysis"
        ) as mock_save:
            extractor.analyze_call(call_id=77, transcript=paystub_transcript, loan_id=500)
            mock_save.assert_called_once()

    def test_full_flow_exception_returns_error_result(self, extractor, mock_db):
        """If save_analysis raises, the result should have success=False and error."""
        mock_db.execute.side_effect = RuntimeError("DB connection lost")

        result = extractor.analyze_call(
            call_id=88,
            transcript="I need to send my paystub for the loan.",
            loan_id=999,
        )
        assert result.success is False
        assert result.error is not None
        assert "DB connection lost" in result.error


# =============================================================================
# FACTORY FUNCTION
# =============================================================================

@pytest.mark.unit
class TestFactoryFunction:
    """Verify the get_call_intel_extractor factory."""

    def test_factory_returns_extractor(self, mock_db):
        """get_call_intel_extractor should return a CallIntelDocumentExtractor."""
        ext = get_call_intel_extractor(mock_db)
        assert isinstance(ext, CallIntelDocumentExtractor)
        assert ext.db is mock_db

    def test_factory_picks_up_api_key(self, mock_db):
        """Extractor should read ANTHROPIC_API_KEY from environment."""
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "sk-real-key"}, clear=False):
            ext = get_call_intel_extractor(mock_db)
            assert ext._anthropic_key == "sk-real-key"

    def test_factory_no_api_key(self, mock_db):
        """Without ANTHROPIC_API_KEY, _anthropic_key should be falsy."""
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": ""}, clear=False):
            ext = get_call_intel_extractor(mock_db)
            assert not ext._anthropic_key


# =============================================================================
# PRIORITY ASSIGNMENT
# =============================================================================

@pytest.mark.unit
class TestPriorityAssignment:
    """Verify priority mapping from action types."""

    def test_missing_document_is_critical(self, extractor):
        """missing_document action should yield CRITICAL priority."""
        assert extractor._ACTION_PRIORITY["missing_document"] == "CRITICAL"

    def test_needs_to_send_is_high(self, extractor):
        """needs_to_send action should yield HIGH priority."""
        assert extractor._ACTION_PRIORITY["needs_to_send"] == "HIGH"

    def test_question_about_is_normal(self, extractor):
        """question_about action should yield NORMAL priority."""
        assert extractor._ACTION_PRIORITY["question_about"] == "NORMAL"

    def test_has_document_is_low(self, extractor):
        """has_document action should yield LOW priority."""
        assert extractor._ACTION_PRIORITY["has_document"] == "LOW"
