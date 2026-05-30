"""
Smart Document Collection - Call Intelligence Document Extractor

Extracts document needs from call intelligence data (call transcripts,
summaries, and notes). Integrates with the call intelligence system to
identify when borrowers mention documents during phone calls, and
automatically creates document requests when confidence is high.

Detection pipeline:
    1. Keyword-based analysis of transcript text
    2. Circumstance detection (job change, self-employment, etc.)
    3. Optional AI-powered semantic analysis via Claude
    4. Confidence scoring and priority assignment
    5. Auto-creation of smart_document_requests for high-confidence needs

Usage:
    from services.smart_docs.call_intel_extractor import get_call_intel_extractor

    extractor = get_call_intel_extractor(db)
    result = extractor.analyze_call(
        call_id=123,
        transcript="...",
        loan_id=456,
    )
"""

import logging
import os
import re
import json
from datetime import datetime, timezone
from typing import Optional, Dict, List, Tuple
from dataclasses import dataclass, field
from sqlalchemy.orm import Session
from sqlalchemy import text

from services.smart_docs.ai_resilience import resilient_ai_call

logger = logging.getLogger(__name__)

# =============================================================================
# DOCUMENT KEYWORD LEXICON
# =============================================================================

# Document-related keywords and phrases that indicate document needs.
# Keys correspond to DocType values in models/smart_docs_models.py.
DOCUMENT_KEYWORDS: Dict[str, List[str]] = {
    "PAYSTUB": [
        "paystub", "pay stub", "pay check", "paycheck", "pay slip",
        "recent pay", "latest pay", "earnings statement", "pay statement",
    ],
    "W2": [
        "w-2", "w2", "wage and tax", "annual tax form",
    ],
    "TAX_RETURN": [
        "tax return", "1040", "tax filing", "taxes", "filed taxes",
        "last year's taxes", "tax documents",
    ],
    "BANK_STATEMENT": [
        "bank statement", "account statement", "bank records",
        "checking account", "savings account", "bank activity",
    ],
    "DRIVERS_LICENSE": [
        "driver's license", "drivers license", "id", "identification",
        "photo id", "state id",
    ],
    "GIFT_LETTER": [
        "gift", "gift funds", "gift letter", "family gift",
        "money from parents", "down payment gift",
    ],
    "PURCHASE_CONTRACT": [
        "purchase contract", "contract", "offer accepted",
        "under contract", "purchase agreement", "sales contract",
    ],
    "APPRAISAL": [
        "appraisal", "home value", "property value",
        "appraiser", "appraisal report",
    ],
    "LOE": [
        "letter of explanation", "explain", "loe",
        "write a letter", "explanation letter",
    ],
    "BUSINESS_TAX_RETURN": [
        "business taxes", "business return", "corporate return",
        "business tax", "schedule c",
    ],
    "PROFIT_LOSS": [
        "profit and loss", "p&l", "profit loss statement",
        "business income", "business revenue",
    ],
    "LEASE_AGREEMENT": [
        "lease", "rental agreement", "lease agreement",
        "tenant", "rental income", "renters",
    ],
    "BANKRUPTCY_DISCHARGE": [
        "bankruptcy", "chapter 7", "chapter 13",
        "bankruptcy discharge", "bankruptcy papers",
    ],
    "HOMEOWNERS_INSURANCE": [
        "insurance", "homeowners insurance", "home insurance",
        "insurance policy", "insurance binder", "hazard insurance",
    ],
    "VA_COE": [
        "certificate of eligibility", "coe", "va eligibility",
        "va certificate",
    ],
    "DD214": [
        "dd214", "dd-214", "discharge papers", "military discharge",
        "service record",
    ],
}

# Contextual phrases indicating document-related actions
ACTION_PHRASES: Dict[str, List[str]] = {
    "needs_to_send": [
        "need to send", "needs to send", "will send", "going to send",
        "can you send", "please send", "email me", "upload",
        "get me", "provide", "bring in", "drop off",
    ],
    "has_document": [
        "i have", "i've got", "already have", "have it ready",
        "sending now", "just sent", "emailed", "uploaded",
    ],
    "missing_document": [
        "don't have", "can't find", "lost", "missing",
        "need to get", "haven't received", "waiting on",
        "still looking for", "trying to find",
    ],
    "question_about": [
        "do i need", "is that required", "what do you need",
        "what documents", "what paperwork", "anything else",
    ],
}

# Circumstance detection phrases
CIRCUMSTANCE_PHRASES: Dict[str, List[str]] = {
    "job_change": [
        "new job", "changed jobs", "started a new position",
        "just started", "recently hired", "switched companies",
        "left my job", "different employer",
    ],
    "self_employed": [
        "own business", "self-employed", "freelance", "contractor",
        "1099", "business owner", "my company", "llc", "sole proprietor",
    ],
    "divorce": [
        "divorced", "divorce", "separation", "ex-spouse",
        "divorce decree", "property settlement",
    ],
    "bankruptcy_history": [
        "filed bankruptcy", "had bankruptcy", "chapter 7",
        "chapter 13", "discharged",
    ],
    "rental_property": [
        "rental property", "investment property", "landlord",
        "rental income", "tenants", "rent out",
    ],
    "large_deposit": [
        "large deposit", "big deposit", "transferred money",
        "sold", "inheritance", "bonus", "severance",
    ],
    "credit_issues": [
        "late payment", "collections", "charge off",
        "credit issue", "credit problem", "bad credit",
    ],
}

# Pre-compile keyword patterns for performance.
# Each entry maps doc_type -> list of compiled regex patterns.
_COMPILED_DOC_PATTERNS: Dict[str, List[re.Pattern]] = {}
for _doc_type, _phrases in DOCUMENT_KEYWORDS.items():
    _COMPILED_DOC_PATTERNS[_doc_type] = [
        re.compile(r"\b" + re.escape(phrase) + r"\b", re.IGNORECASE)
        for phrase in _phrases
    ]

_COMPILED_ACTION_PATTERNS: Dict[str, List[re.Pattern]] = {}
for _action, _phrases in ACTION_PHRASES.items():
    _COMPILED_ACTION_PATTERNS[_action] = [
        re.compile(r"\b" + re.escape(phrase) + r"\b", re.IGNORECASE)
        for phrase in _phrases
    ]

_COMPILED_CIRCUMSTANCE_PATTERNS: Dict[str, List[re.Pattern]] = {}
for _circ, _phrases in CIRCUMSTANCE_PHRASES.items():
    _COMPILED_CIRCUMSTANCE_PATTERNS[_circ] = [
        re.compile(r"\b" + re.escape(phrase) + r"\b", re.IGNORECASE)
        for phrase in _phrases
    ]

# How many characters of context to capture around a keyword match
_SNIPPET_CONTEXT_CHARS = 120


# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class DetectedDocumentNeed:
    """A document need detected from call intelligence."""
    doc_type: str
    description: str
    confidence: int  # 0-100
    source_snippet: str
    keywords_matched: List[str]
    action_type: str  # needs_to_send, missing_document, question_about, has_document
    circumstance: Optional[str]
    priority: str  # CRITICAL, HIGH, NORMAL, LOW
    auto_create_request: bool


@dataclass
class CallAnalysisResult:
    """Result of analyzing a call for document needs."""
    call_id: int
    loan_id: int
    document_needs: List[DetectedDocumentNeed]
    circumstances_detected: List[str]
    summary: str
    total_needs: int
    auto_create_count: int
    success: bool = True
    error: Optional[str] = None


# =============================================================================
# EXTRACTOR SERVICE
# =============================================================================

class CallIntelDocumentExtractor:
    """
    Extracts document needs from call intelligence data.

    Analyzes:
    - Call transcripts for document mentions
    - Call summaries for circumstance changes
    - Call notes for action items

    Creates document requests automatically when confidence is high.
    Flags for LO review when confidence is medium.
    """

    # Confidence thresholds
    AUTO_CREATE_THRESHOLD = 80
    MEDIUM_CONFIDENCE_THRESHOLD = 50

    # Priority rules based on action type
    _ACTION_PRIORITY: Dict[str, str] = {
        "needs_to_send": "HIGH",
        "missing_document": "CRITICAL",
        "question_about": "NORMAL",
        "has_document": "LOW",
    }

    def __init__(self, db: Session):
        self.db = db
        self._anthropic_key = os.getenv("ANTHROPIC_API_KEY")

    # -----------------------------------------------------------------
    # PUBLIC API
    # -----------------------------------------------------------------

    def analyze_call(
        self,
        call_id: int,
        transcript: str,
        loan_id: int,
        lead_id: Optional[int] = None,
    ) -> CallAnalysisResult:
        """
        Main entry point: analyse a call transcript for document needs.

        Steps:
            1. Keyword analysis on the transcript text
            2. Circumstance detection (job change, self-employed, etc.)
            3. Map circumstances to implied document needs
            4. (Optional) AI-powered deep analysis via Claude
            5. Merge, deduplicate and score all detected needs
            6. Persist results to call_intel_document_needs table

        Returns:
            CallAnalysisResult with all detected needs.
        """
        if not transcript or not transcript.strip():
            return CallAnalysisResult(
                call_id=call_id,
                loan_id=loan_id,
                document_needs=[],
                circumstances_detected=[],
                summary="Empty transcript provided",
                total_needs=0,
                auto_create_count=0,
                success=True,
            )

        try:
            # Step 1 — keyword-based document detection
            keyword_needs = self.analyze_transcript_keywords(transcript)

            # Step 2 — detect borrower circumstances
            circumstances = self.detect_circumstances(transcript)

            # Step 3 — map circumstances to implied document needs
            circumstance_needs = self._circumstance_to_documents(circumstances)

            # Step 4 — AI analysis (if key is available and transcript is long enough)
            ai_needs: List[DetectedDocumentNeed] = []
            if self._anthropic_key and len(transcript) >= 200:
                try:
                    ai_needs = self._analyze_with_ai(transcript, keyword_needs)
                except Exception as e:
                    logger.warning("AI analysis failed, proceeding with keyword results: %s", e)

            # Step 5 — merge and deduplicate
            all_needs = self._merge_needs(keyword_needs, circumstance_needs, ai_needs)

            # Build summary
            auto_create_count = sum(
                1 for n in all_needs
                if n.confidence >= self.AUTO_CREATE_THRESHOLD and n.auto_create_request
            )
            summary_parts = []
            if all_needs:
                summary_parts.append(f"{len(all_needs)} document need(s) detected")
            if circumstances:
                summary_parts.append(f"circumstances: {', '.join(circumstances)}")
            if auto_create_count:
                summary_parts.append(f"{auto_create_count} eligible for auto-request")
            summary = "; ".join(summary_parts) if summary_parts else "No document needs detected"

            result = CallAnalysisResult(
                call_id=call_id,
                loan_id=loan_id,
                document_needs=all_needs,
                circumstances_detected=circumstances,
                summary=summary,
                total_needs=len(all_needs),
                auto_create_count=auto_create_count,
                success=True,
            )

            # Step 6 — persist
            self.save_analysis(result, lead_id=lead_id)

            return result

        except Exception as e:
            logger.exception("Call analysis failed for call_id=%s", call_id)
            return CallAnalysisResult(
                call_id=call_id,
                loan_id=loan_id,
                document_needs=[],
                circumstances_detected=[],
                summary="Analysis failed",
                total_needs=0,
                auto_create_count=0,
                success=False,
                error=str(e),
            )

    def analyze_transcript_keywords(self, transcript: str) -> List[DetectedDocumentNeed]:
        """
        Search transcript for DOCUMENT_KEYWORDS matches.

        For each match, determine the action type from ACTION_PHRASES context,
        score confidence based on keyword count and surrounding context, and
        return a list of DetectedDocumentNeed objects.
        """
        needs: List[DetectedDocumentNeed] = []
        # Track which doc types we've already detected to avoid duplicates
        seen_doc_types: Dict[str, DetectedDocumentNeed] = {}

        for doc_type, patterns in _COMPILED_DOC_PATTERNS.items():
            matched_keywords: List[str] = []
            best_snippet = ""
            best_match_pos = -1

            for pattern in patterns:
                match = pattern.search(transcript)
                if match:
                    matched_keywords.append(match.group(0))
                    if best_match_pos < 0:
                        best_match_pos = match.start()

            if not matched_keywords:
                continue

            # Extract context snippet around the first match
            if best_match_pos >= 0:
                start = max(0, best_match_pos - _SNIPPET_CONTEXT_CHARS)
                end = min(len(transcript), best_match_pos + _SNIPPET_CONTEXT_CHARS)
                best_snippet = transcript[start:end].strip()

            # Determine action type from surrounding context
            action_type = self._detect_action_type(best_snippet)

            # Score confidence:
            #   Base 40 for any match
            #   +15 per additional keyword match (max +30)
            #   +10 if a concrete action phrase was found
            #   +10 if the match is in a borrower-speech region (heuristic: short sentence)
            confidence = 40
            confidence += min(len(matched_keywords) - 1, 2) * 15
            if action_type != "question_about":
                confidence += 10
            # Heuristic: if snippet contains first-person pronouns, likely borrower speech
            if re.search(r"\b(i |i'|my |we )\b", best_snippet, re.IGNORECASE):
                confidence += 10
            confidence = min(confidence, 100)

            priority = self._ACTION_PRIORITY.get(action_type, "NORMAL")
            auto_create = (
                confidence >= self.AUTO_CREATE_THRESHOLD
                and action_type in ("needs_to_send", "missing_document")
            )

            need = DetectedDocumentNeed(
                doc_type=doc_type,
                description=f"{doc_type.replace('_', ' ').title()} mentioned during call",
                confidence=confidence,
                source_snippet=best_snippet,
                keywords_matched=matched_keywords,
                action_type=action_type,
                circumstance=None,
                priority=priority,
                auto_create_request=auto_create,
            )

            # Keep the higher-confidence detection per doc type
            if doc_type in seen_doc_types:
                if need.confidence > seen_doc_types[doc_type].confidence:
                    seen_doc_types[doc_type] = need
            else:
                seen_doc_types[doc_type] = need

        needs = list(seen_doc_types.values())
        # Sort by confidence descending
        needs.sort(key=lambda n: n.confidence, reverse=True)
        return needs

    def detect_circumstances(self, transcript: str) -> List[str]:
        """
        Search transcript for CIRCUMSTANCE_PHRASES.

        Returns a list of detected circumstance keys (e.g. 'job_change',
        'self_employed'). Each circumstance may imply additional document
        needs that are resolved by ``_circumstance_to_documents``.
        """
        detected: List[str] = []
        for circ_key, patterns in _COMPILED_CIRCUMSTANCE_PATTERNS.items():
            for pattern in patterns:
                if pattern.search(transcript):
                    detected.append(circ_key)
                    break  # one match per circumstance is enough
        return detected

    def auto_create_requests(self, analysis: CallAnalysisResult) -> List[int]:
        """
        For needs with confidence >= AUTO_CREATE_THRESHOLD and
        auto_create_request=True, create smart_document_requests records.

        Uses atomic_operation to ensure all request records and their
        corresponding need-linkage updates are committed together or
        rolled back together.

        Returns list of created request IDs.
        """
        from models.smart_docs_models import DocumentRequest, RequestStatus, RequestPriority, DocType
        from services.smart_docs.db_transaction import atomic_operation

        created_ids: List[int] = []

        eligible_needs = [
            need for need in analysis.document_needs
            if need.confidence >= self.AUTO_CREATE_THRESHOLD and need.auto_create_request
        ]

        if not eligible_needs:
            return created_ids

        try:
            with atomic_operation(self.db):
                for need in eligible_needs:
                    # Resolve DocType enum; skip if unknown
                    try:
                        doc_type_enum = DocType(need.doc_type)
                    except ValueError:
                        logger.warning("Unknown DocType '%s', skipping auto-create", need.doc_type)
                        continue

                    try:
                        priority_enum = RequestPriority(need.priority)
                    except ValueError:
                        priority_enum = RequestPriority.NORMAL

                    # Resolve organization_id from loan
                    _org_row = self.db.execute(
                        text("SELECT organization_id FROM loans WHERE id = :id"),
                        {"id": analysis.loan_id}
                    ).first()
                    _org_id = _org_row[0] if _org_row else None

                    request = DocumentRequest(
                        organization_id=_org_id,
                        loan_id=analysis.loan_id,
                        doc_type=doc_type_enum,
                        title=f"{need.doc_type.replace('_', ' ').title()} (from call)",
                        description=need.description,
                        instructions=f"Detected from call #{analysis.call_id}. Snippet: {need.source_snippet[:200]}",
                        priority=priority_enum,
                        status=RequestStatus.OPEN,
                    )
                    self.db.add(request)
                    self.db.flush()  # get the ID
                    created_ids.append(request.id)

                    # Link the need record to the created request
                    self.db.execute(
                        text("""
                            UPDATE call_intel_document_needs
                            SET linked_request_id = :request_id,
                                status = 'REQUEST_CREATED'
                            WHERE call_id = :call_id
                              AND detected_doc_type = :doc_type
                              AND linked_request_id IS NULL
                        """),
                        {
                            "request_id": request.id,
                            "call_id": analysis.call_id,
                            "doc_type": need.doc_type,
                        },
                    )
                # atomic_operation commits here

            logger.info(
                "Auto-created %d document requests from call %d",
                len(created_ids),
                analysis.call_id,
            )
        except Exception as e:
            # atomic_operation already rolled back; clear partial IDs
            logger.exception(
                "Failed to auto-create requests for call %d: %s",
                analysis.call_id, e,
            )
            created_ids.clear()
            raise

        return created_ids

    def save_analysis(
        self,
        result: CallAnalysisResult,
        lead_id: Optional[int] = None,
    ) -> None:
        """
        Persist each detected need to the call_intel_document_needs table.

        Uses atomic_operation to ensure all need records for a single call
        analysis are committed together.  If any record fails, every record
        from this batch is rolled back.
        """
        from database.models.document_intelligence import CallIntelDocumentNeed
        from services.smart_docs.db_transaction import atomic_operation

        # Look up organization_id from the loan
        org_id = None
        if result.loan_id:
            row = self.db.execute(
                text("SELECT organization_id FROM loans WHERE id = :lid"),
                {"lid": result.loan_id},
            ).first()
            if row:
                org_id = row[0]

        try:
            with atomic_operation(self.db):
                for need in result.document_needs:
                    record = CallIntelDocumentNeed(
                        organization_id=org_id,
                        loan_id=result.loan_id,
                        lead_id=lead_id,
                        call_id=result.call_id,
                        call_date=datetime.now(timezone.utc),
                        detected_doc_type=need.doc_type,
                        detected_doc_description=need.description,
                        detection_confidence=need.confidence,
                        source_transcript_snippet=need.source_snippet[:2000] if need.source_snippet else None,
                        keywords_matched=need.keywords_matched,
                        status="DETECTED",
                    )
                    self.db.add(record)
                # atomic_operation commits here
        except Exception as e:
            # atomic_operation already rolled back
            logger.exception("Failed to save call analysis for call_id=%s: %s", result.call_id, e)
            raise

    def get_unprocessed_calls(
        self,
        organization_id: int,
        limit: int = 50,
    ) -> List[Dict]:
        """
        Query for calls that haven't been analyzed yet.

        A call is considered unprocessed if it has notes/transcript content
        and no matching row in call_intel_document_needs.

        Returns list of dicts with call info and transcript/notes text.
        """
        rows = self.db.execute(
            text("""
                SELECT
                    cl.id AS call_id,
                    cl.loan_id,
                    cl.lead_id,
                    cl.notes,
                    cl.ai_note_summary,
                    cl.duration_seconds,
                    cl.start_time
                FROM call_logs cl
                LEFT JOIN call_intel_document_needs cidn
                    ON cidn.call_id = cl.id
                WHERE cl.organization_id = :org_id
                  AND cidn.id IS NULL
                  AND (cl.notes IS NOT NULL OR cl.ai_note_summary IS NOT NULL)
                  AND cl.duration_seconds > 30
                ORDER BY cl.start_time DESC
                LIMIT :lim
            """),
            {"org_id": organization_id, "lim": limit},
        ).fetchall()

        results: List[Dict] = []
        for row in rows:
            # Build the best available transcript text from notes + AI summary
            transcript_parts = []
            if row.ai_note_summary:
                transcript_parts.append(row.ai_note_summary)
            if row.notes:
                transcript_parts.append(row.notes)

            results.append({
                "call_id": row.call_id,
                "loan_id": row.loan_id,
                "lead_id": row.lead_id,
                "transcript": "\n\n".join(transcript_parts),
                "duration_seconds": row.duration_seconds,
                "start_time": row.start_time.isoformat() if row.start_time else None,
            })

        return results

    def batch_analyze(self, call_ids: List[int]) -> List[CallAnalysisResult]:
        """
        Analyze multiple calls. Used by cron job for processing new calls.

        Fetches call data from call_logs, runs analysis on each, and
        returns the list of results.
        """
        results: List[CallAnalysisResult] = []
        if not call_ids:
            return results

        rows = self.db.execute(
            text("""
                SELECT
                    id AS call_id,
                    loan_id,
                    lead_id,
                    notes,
                    ai_note_summary
                FROM call_logs
                WHERE id = ANY(:ids)
            """),
            {"ids": call_ids},
        ).fetchall()

        call_map = {row.call_id: row for row in rows}

        for call_id in call_ids:
            row = call_map.get(call_id)
            if not row:
                results.append(CallAnalysisResult(
                    call_id=call_id,
                    loan_id=0,
                    document_needs=[],
                    circumstances_detected=[],
                    summary=f"Call {call_id} not found",
                    total_needs=0,
                    auto_create_count=0,
                    success=False,
                    error=f"Call {call_id} not found in call_logs",
                ))
                continue

            # Build transcript from available text
            transcript_parts = []
            if row.ai_note_summary:
                transcript_parts.append(row.ai_note_summary)
            if row.notes:
                transcript_parts.append(row.notes)
            transcript = "\n\n".join(transcript_parts)

            if not transcript.strip():
                results.append(CallAnalysisResult(
                    call_id=call_id,
                    loan_id=row.loan_id or 0,
                    document_needs=[],
                    circumstances_detected=[],
                    summary="No transcript or notes available",
                    total_needs=0,
                    auto_create_count=0,
                    success=True,
                ))
                continue

            result = self.analyze_call(
                call_id=call_id,
                transcript=transcript,
                loan_id=row.loan_id or 0,
                lead_id=row.lead_id,
            )
            results.append(result)

        return results

    # -----------------------------------------------------------------
    # PRIVATE HELPERS
    # -----------------------------------------------------------------

    def _detect_action_type(self, snippet: str) -> str:
        """
        Determine which action type best matches the snippet context.

        Checks ACTION_PHRASES patterns against the snippet and returns
        the first matching action type, falling back to 'question_about'.
        """
        # Check in priority order: missing > needs_to_send > has_document > question_about
        priority_order = ["missing_document", "needs_to_send", "has_document", "question_about"]
        for action in priority_order:
            for pattern in _COMPILED_ACTION_PATTERNS[action]:
                if pattern.search(snippet):
                    return action
        return "question_about"

    def _circumstance_to_documents(
        self,
        circumstances: List[str],
    ) -> List[DetectedDocumentNeed]:
        """
        Map detected circumstances to implied document needs.

        Each circumstance implies specific documents that underwriters
        will require. These are generated with moderate confidence since
        they are inferred rather than explicitly mentioned.
        """
        mapping: Dict[str, List[Tuple[str, str, str]]] = {
            # circumstance -> [(doc_type, description, priority), ...]
            "job_change": [
                ("PAYSTUB", "Updated paystubs from new employer", "HIGH"),
                ("LOE", "Offer letter or verification of employment from new employer", "HIGH"),
            ],
            "self_employed": [
                ("BUSINESS_TAX_RETURN", "Business tax returns (2 years)", "HIGH"),
                ("PROFIT_LOSS", "Year-to-date profit and loss statement", "HIGH"),
                ("BALANCE_SHEET", "Current balance sheet", "NORMAL"),
            ],
            "divorce": [
                ("LOE", "Divorce decree", "CRITICAL"),
                ("LOE", "Property settlement agreement", "HIGH"),
            ],
            "bankruptcy_history": [
                ("BANKRUPTCY_DISCHARGE", "Bankruptcy discharge papers", "CRITICAL"),
            ],
            "rental_property": [
                ("LEASE_AGREEMENT", "Current lease agreements for rental properties", "HIGH"),
                ("TAX_RETURN", "Tax returns with Schedule E", "HIGH"),
            ],
            "large_deposit": [
                ("BANK_STATEMENT", "Bank statements showing source of large deposit", "HIGH"),
                ("GIFT_LETTER", "Gift letter if deposit is a gift (or LOE for other source)", "NORMAL"),
            ],
            "credit_issues": [
                ("LOE", "Letter of explanation for credit events", "HIGH"),
            ],
        }

        needs: List[DetectedDocumentNeed] = []
        seen_keys: set = set()  # (doc_type, circumstance) dedup key

        for circ in circumstances:
            doc_specs = mapping.get(circ, [])
            for doc_type, description, priority in doc_specs:
                dedup_key = (doc_type, circ)
                if dedup_key in seen_keys:
                    continue
                seen_keys.add(dedup_key)

                needs.append(DetectedDocumentNeed(
                    doc_type=doc_type,
                    description=description,
                    confidence=60,  # moderate — inferred from circumstance
                    source_snippet=f"Circumstance detected: {circ}",
                    keywords_matched=[circ],
                    action_type="needs_to_send",
                    circumstance=circ,
                    priority=priority,
                    auto_create_request=False,  # circumstance-based needs require LO confirmation
                ))

        return needs

    def _analyze_with_ai(
        self,
        transcript: str,
        keyword_results: List[DetectedDocumentNeed],
    ) -> List[DetectedDocumentNeed]:
        """
        Use Claude API for deeper semantic analysis of the transcript.

        The AI can catch nuanced document needs that keyword matching misses,
        such as indirect references ('I just closed on an investment property
        last month' implies rental docs may be needed).

        Results are merged with keyword results — AI may confirm existing
        detections or add new ones.
        """
        if not self._anthropic_key:
            return []

        import anthropic

        client = anthropic.Anthropic(api_key=self._anthropic_key)

        # Build context about what keywords already found
        already_found = [n.doc_type for n in keyword_results]
        already_context = (
            f"Keyword analysis already detected these document types: {', '.join(already_found)}. "
            if already_found
            else ""
        )

        prompt = f"""Analyze this mortgage call transcript for any document-related discussion.
{already_context}
Identify any ADDITIONAL document needs that may have been missed by keyword analysis.
Focus on:
- Indirect references to documents (e.g., mentioning a life event that implies a need)
- Documents the borrower or LO committed to providing
- Follow-up items related to documentation
- Circumstantial needs (job changes, property types, income sources)

Return a JSON array of objects. Each object should have:
- "doc_type": one of PAYSTUB, W2, TAX_RETURN, BANK_STATEMENT, DRIVERS_LICENSE, GIFT_LETTER, PURCHASE_CONTRACT, APPRAISAL, LOE, BUSINESS_TAX_RETURN, PROFIT_LOSS, LEASE_AGREEMENT, BANKRUPTCY_DISCHARGE, HOMEOWNERS_INSURANCE, VA_COE, DD214, OTHER
- "description": brief description of what was discussed
- "confidence": 0-100 score
- "action_type": one of needs_to_send, has_document, missing_document, question_about
- "snippet": the relevant portion of the transcript (keep short)

If no additional needs are found beyond what keyword analysis already detected, return an empty array: []

TRANSCRIPT:
{transcript[:6000]}"""

        try:
            response = resilient_ai_call(
                client=client,
                messages=[{"role": "user", "content": prompt}],
                model="claude-sonnet-4-6",
                max_tokens=1500,
                operation_name="call_intel_extraction",
                timeout=30.0,
            )

            if response is None:
                logger.warning(
                    "AI call intel extraction unavailable, using keyword-only results"
                )
                return []

            response_text = response.content[0].text.strip()

            # Extract JSON from the response (may be wrapped in markdown code block)
            json_match = re.search(r"\[.*\]", response_text, re.DOTALL)
            if not json_match:
                return []

            parsed = json.loads(json_match.group(0))
            if not isinstance(parsed, list):
                return []

            ai_needs: List[DetectedDocumentNeed] = []
            valid_doc_types = set(DOCUMENT_KEYWORDS.keys()) | {"OTHER"}

            for item in parsed:
                doc_type = item.get("doc_type", "OTHER")
                if doc_type not in valid_doc_types:
                    doc_type = "OTHER"

                # Skip if keyword analysis already found this doc type
                if doc_type in already_found:
                    continue

                confidence = min(max(int(item.get("confidence", 50)), 0), 100)
                action_type = item.get("action_type", "question_about")
                if action_type not in ACTION_PHRASES:
                    action_type = "question_about"

                priority = self._ACTION_PRIORITY.get(action_type, "NORMAL")

                ai_needs.append(DetectedDocumentNeed(
                    doc_type=doc_type,
                    description=item.get("description", f"{doc_type} detected by AI analysis"),
                    confidence=confidence,
                    source_snippet=item.get("snippet", "")[:500],
                    keywords_matched=["ai_analysis"],
                    action_type=action_type,
                    circumstance=None,
                    priority=priority,
                    auto_create_request=(
                        confidence >= self.AUTO_CREATE_THRESHOLD
                        and action_type in ("needs_to_send", "missing_document")
                    ),
                ))

            logger.info(
                "Call intel AI extraction completed | "
                "ai_needs_found=%d | keyword_needs_input=%d | "
                "transcript_length=%d",
                len(ai_needs),
                len(keyword_results),
                len(transcript),
            )
            return ai_needs

        except json.JSONDecodeError as e:
            logger.warning("Failed to parse AI response JSON: %s", e)
            return []
        except Exception as e:
            logger.warning("AI analysis request failed: %s", e)
            return []

    def _merge_needs(
        self,
        keyword_needs: List[DetectedDocumentNeed],
        circumstance_needs: List[DetectedDocumentNeed],
        ai_needs: List[DetectedDocumentNeed],
    ) -> List[DetectedDocumentNeed]:
        """
        Merge and deduplicate needs from all sources.

        When multiple sources detect the same doc_type, keep the one with
        the highest confidence score, boosting confidence if multiple
        sources agree.
        """
        best_by_type: Dict[str, DetectedDocumentNeed] = {}

        for need in keyword_needs:
            key = need.doc_type
            if key not in best_by_type or need.confidence > best_by_type[key].confidence:
                best_by_type[key] = need

        for need in circumstance_needs:
            key = need.doc_type
            if key in best_by_type:
                # Boost confidence if both keyword and circumstance agree
                existing = best_by_type[key]
                boosted = min(existing.confidence + 10, 100)
                best_by_type[key] = DetectedDocumentNeed(
                    doc_type=existing.doc_type,
                    description=existing.description,
                    confidence=boosted,
                    source_snippet=existing.source_snippet,
                    keywords_matched=existing.keywords_matched + need.keywords_matched,
                    action_type=existing.action_type,
                    circumstance=need.circumstance,
                    priority=existing.priority if existing.priority == "CRITICAL" else need.priority,
                    auto_create_request=existing.auto_create_request or (boosted >= self.AUTO_CREATE_THRESHOLD),
                )
            else:
                best_by_type[key] = need

        for need in ai_needs:
            key = need.doc_type
            if key in best_by_type:
                # AI confirms keyword/circumstance detection — boost confidence
                existing = best_by_type[key]
                boosted = min(existing.confidence + 15, 100)
                best_by_type[key] = DetectedDocumentNeed(
                    doc_type=existing.doc_type,
                    description=existing.description,
                    confidence=boosted,
                    source_snippet=existing.source_snippet,
                    keywords_matched=existing.keywords_matched + ["ai_confirmed"],
                    action_type=existing.action_type,
                    circumstance=existing.circumstance,
                    priority=existing.priority,
                    auto_create_request=existing.auto_create_request or (boosted >= self.AUTO_CREATE_THRESHOLD),
                )
            else:
                best_by_type[key] = need

        merged = list(best_by_type.values())
        merged.sort(key=lambda n: n.confidence, reverse=True)
        return merged


# =============================================================================
# SINGLETON FACTORY
# =============================================================================

def get_call_intel_extractor(db: Session) -> CallIntelDocumentExtractor:
    """Factory function to obtain a CallIntelDocumentExtractor instance."""
    return CallIntelDocumentExtractor(db)
