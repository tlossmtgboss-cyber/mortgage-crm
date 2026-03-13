"""
Document Chat / Q&A Service for Smart Docs V2

Enables conversational interaction with document content. Loan officers can
ask natural language questions about uploaded documents and receive AI-powered
answers with citations, confidence scores, and PII-filtered responses.

Capabilities:
    - Single-document Q&A with page/location references
    - Multi-document cross-referencing ("compare W-2 vs tax return income")
    - Pre-built analysis prompts (income consistency, red flags, etc.)
    - Conversation history per loan/user
    - Answer confidence scoring (high/medium/low)
    - PII filtering in responses (masks SSNs, account numbers)
    - Canned question templates per document type
    - Batch analysis mode across all loan documents
    - Token usage tracking and cost attribution
    - Circuit breaker integration via ai_resilience.py

Usage:
    from services.smart_docs.document_chat_service import DocumentChatService

    service = DocumentChatService(db=session, org_id=42, user_id=7)

    # Ask a question about a specific document
    response = await service.ask_question(
        document_ids=[101],
        question="What is the borrower's YTD gross income?",
    )

    # Run a pre-built analysis across a loan file
    result = await service.run_analysis(
        loan_id=500,
        analysis_type="income_consistency",
    )

    # Get suggested questions for a document
    suggestions = await service.get_suggested_questions(document_id=101)
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import time
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Sequence, Tuple

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Optional imports
# ---------------------------------------------------------------------------

try:
    from anthropic import Anthropic
    HAS_ANTHROPIC = True
except ImportError:
    HAS_ANTHROPIC = False

from services.smart_docs.ai_resilience import resilient_ai_call, _estimate_cost


# =============================================================================
# ENUMS
# =============================================================================

class Confidence(str, Enum):
    """Answer confidence level."""
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class AnalysisType(str, Enum):
    """Pre-built analysis types."""
    INCOME_CONSISTENCY = "income_consistency"
    ASSET_SUFFICIENCY = "asset_sufficiency"
    RED_FLAG_IDENTIFICATION = "red_flag_identification"
    CONDITION_CLEARANCE = "condition_clearance"
    EMPLOYMENT_VERIFICATION = "employment_verification"
    IDENTITY_VERIFICATION = "identity_verification"


# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class Citation:
    """Source reference for an answer."""
    document_id: int
    document_name: str
    doc_type: str
    page_number: Optional[int] = None
    relevant_text: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "document_id": self.document_id,
            "document_name": self.document_name,
            "doc_type": self.doc_type,
            "page_number": self.page_number,
            "relevant_text": self.relevant_text,
        }


@dataclass
class ChatMessage:
    """Single message in a conversation."""
    role: str  # "user" or "assistant"
    content: str
    citations: List[Citation] = field(default_factory=list)
    confidence: Optional[Confidence] = None
    timestamp: str = ""
    token_usage: Optional[Dict[str, int]] = None

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> Dict[str, Any]:
        result = {
            "role": self.role,
            "content": self.content,
            "timestamp": self.timestamp,
        }
        if self.role == "assistant":
            result["citations"] = [c.to_dict() for c in self.citations]
            result["confidence"] = self.confidence.value if self.confidence else None
            result["token_usage"] = self.token_usage
        return result


@dataclass
class ChatResponse:
    """Response from the document chat service."""
    answer: str
    citations: List[Citation]
    confidence: Confidence
    conversation_id: str
    token_usage: Dict[str, int]
    cost_estimate: float
    model_used: str
    duration_ms: int
    pii_redacted: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "answer": self.answer,
            "citations": [c.to_dict() for c in self.citations],
            "confidence": self.confidence.value,
            "conversation_id": self.conversation_id,
            "token_usage": self.token_usage,
            "cost_estimate": round(self.cost_estimate, 6),
            "model_used": self.model_used,
            "duration_ms": self.duration_ms,
            "pii_redacted": self.pii_redacted,
        }


@dataclass
class AnalysisResult:
    """Result from a pre-built analysis run."""
    analysis_type: str
    loan_id: int
    summary: str
    findings: List[Dict[str, Any]]
    recommendations: List[str]
    documents_analyzed: List[Dict[str, Any]]
    confidence: Confidence
    token_usage: Dict[str, int]
    cost_estimate: float
    model_used: str
    duration_ms: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            "analysis_type": self.analysis_type,
            "loan_id": self.loan_id,
            "summary": self.summary,
            "findings": self.findings,
            "recommendations": self.recommendations,
            "documents_analyzed": self.documents_analyzed,
            "confidence": self.confidence.value,
            "token_usage": self.token_usage,
            "cost_estimate": round(self.cost_estimate, 6),
            "model_used": self.model_used,
            "duration_ms": self.duration_ms,
        }


# =============================================================================
# PII FILTERING
# =============================================================================

class PIIFilter:
    """Filters PII from AI-generated responses.

    Masks SSNs, full account numbers, and other sensitive data that the AI
    model might echo back from document content.
    """

    PATTERNS: List[Tuple[re.Pattern, str]] = [
        # SSN: 123-45-6789 or 123 45 6789
        (
            re.compile(r"\b(\d{3})[-\s](\d{2})[-\s](\d{4})\b"),
            r"***-**-\3",
        ),
        # SSN: 9 consecutive digits (not timestamps)
        (
            re.compile(r"(?<![0-9\-])(\d{3})(\d{2})(\d{4})(?![0-9\-])"),
            r"***-**-\3",
        ),
        # Bank account numbers (keyword-anchored)
        (
            re.compile(
                r"(account\s*(?:number|#|no\.?)?[\s:]*)\d{4}(\d{4,13})",
                re.IGNORECASE,
            ),
            r"\1****\2",
        ),
        # Routing numbers (keyword-anchored)
        (
            re.compile(r"(routing\s*(?:number|#|no\.?)?[\s:]*)\d{9}", re.IGNORECASE),
            r"\1*********",
        ),
        # Credit card numbers
        (
            re.compile(r"\b\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b"),
            "****-****-****-****",
        ),
    ]

    @classmethod
    def redact(cls, text: str) -> Tuple[str, bool]:
        """Redact PII from text. Returns (redacted_text, was_redacted)."""
        redacted = False
        for pattern, replacement in cls.PATTERNS:
            new_text = pattern.sub(replacement, text)
            if new_text != text:
                redacted = True
                text = new_text
        return text, redacted


# =============================================================================
# CANNED QUESTION TEMPLATES
# =============================================================================

QUESTION_TEMPLATES: Dict[str, List[str]] = {
    "PAYSTUB": [
        "What is the borrower's current gross pay per period?",
        "What is the year-to-date (YTD) gross income?",
        "What is the pay frequency (weekly, biweekly, semi-monthly, monthly)?",
        "Are there any overtime, bonus, or commission earnings?",
        "What deductions are being taken (taxes, insurance, retirement)?",
        "What is the employer name and address?",
        "What is the pay period start and end date?",
        "Calculate the annualized gross income from this paystub.",
    ],
    "W2": [
        "What are the total wages, tips, and other compensation (Box 1)?",
        "What is the employer name and EIN?",
        "What tax year does this W-2 cover?",
        "What is the total federal income tax withheld?",
        "Are the social security wages consistent with Box 1 wages?",
        "Does this W-2 show any retirement plan contributions?",
    ],
    "TAX_RETURN": [
        "What is the adjusted gross income (AGI)?",
        "What is the filing status?",
        "What tax year is this return for?",
        "Are there any Schedule C (self-employment) losses?",
        "What are the total itemized or standard deductions?",
        "Is there rental income or loss on Schedule E?",
        "Are there any unreimbursed business expenses?",
    ],
    "BANK_STATEMENT": [
        "What is the ending balance?",
        "What is the beginning balance?",
        "Are there any NSF (non-sufficient funds) fees or overdrafts?",
        "What are the total deposits for this statement period?",
        "Are there any large or unusual deposits?",
        "What statement period does this cover?",
        "Are there regular payroll deposits? If so, what amounts?",
        "Are there any wire transfers or cash deposits over $5,000?",
    ],
    "INVESTMENT_STATEMENT": [
        "What is the total account value?",
        "What type of investment account is this (brokerage, IRA, 401k)?",
        "What is the cash/money market balance?",
        "What is the statement date?",
        "Are there any recent large withdrawals?",
    ],
    "PURCHASE_CONTRACT": [
        "What is the purchase price?",
        "What is the earnest money deposit amount?",
        "What is the expected closing date?",
        "What is the property address?",
        "Are there any seller concessions or credits?",
        "What contingencies are included?",
    ],
    "DRIVERS_LICENSE": [
        "What is the full name on the ID?",
        "What is the residential address listed?",
        "Is the ID currently valid (not expired)?",
        "What state issued this ID?",
    ],
    "PROFIT_LOSS": [
        "What is the net profit for the period?",
        "What is the gross revenue?",
        "What are the largest expense categories?",
        "What time period does this P&L cover?",
        "What is the business name?",
    ],
}

# Default questions for document types without specific templates
DEFAULT_QUESTION_TEMPLATES = [
    "What is the date on this document?",
    "Whose name appears on this document?",
    "What are the key figures or amounts shown?",
    "Summarize the main information in this document.",
]


# =============================================================================
# ANALYSIS PROMPTS
# =============================================================================

ANALYSIS_PROMPTS: Dict[str, str] = {
    AnalysisType.INCOME_CONSISTENCY: """You are a mortgage underwriting analyst reviewing income documents for consistency.

Analyze the following documents and check for:
1. Does the income on paystubs match the W-2 (pro-rated for the period)?
2. Does W-2 income align with tax return AGI (accounting for other income sources)?
3. Is the employer name consistent across all income documents?
4. Are there unexplained gaps or discrepancies in income amounts?
5. If self-employed, does the P&L net income align with tax return Schedule C?
6. Is there declining income year-over-year?

For each finding, rate severity as: CRITICAL, WARNING, or INFO.
Provide specific dollar amounts and percentages where applicable.""",

    AnalysisType.ASSET_SUFFICIENCY: """You are a mortgage underwriting analyst reviewing asset documents.

Analyze the following documents and check for:
1. Are there sufficient liquid assets for down payment and closing costs?
2. Are there any large deposits that need sourcing (deposits > 50% of monthly income)?
3. Are there any NSF fees or overdrafts in the last 2 months?
4. Is the average balance trending up, down, or stable?
5. Are there regular payroll deposits matching stated income?
6. Are there any concerning withdrawal patterns?

For each finding, rate severity as: CRITICAL, WARNING, or INFO.
Provide specific dollar amounts where applicable.""",

    AnalysisType.RED_FLAG_IDENTIFICATION: """You are a mortgage fraud detection analyst reviewing loan file documents.

Analyze the following documents and flag any red flags:
1. Name inconsistencies across documents
2. Address mismatches
3. Income figures that don't reconcile
4. Dates that don't make sense (future dates, gaps, overlaps)
5. Signs of document alteration (mentioned in OCR notes)
6. Unusually round numbers for income or assets
7. Employer information that seems inconsistent
8. Account numbers that appear altered
9. Missing or obscured information in key fields

Rate each red flag as: HIGH RISK, MEDIUM RISK, or LOW RISK.
Be specific about what triggered each flag and which documents are involved.""",

    AnalysisType.CONDITION_CLEARANCE: """You are a mortgage processor reviewing documents against common underwriting conditions.

For each document provided, determine if it could clear any of these common conditions:
1. Proof of income (paystubs covering most recent 30 days)
2. Proof of employment (employer name, hire date)
3. Proof of assets (bank statements covering most recent 2 months)
4. Proof of identity (valid government-issued photo ID)
5. Tax return transcripts (IRS Form 4506-T / tax returns)
6. Explanation letters (LOE for credit inquiries, gaps in employment, large deposits)
7. Insurance binder
8. Title commitment

For each condition, indicate: CLEARED, PARTIALLY MET, or NOT ADDRESSED.
Note any missing items needed to fully clear each condition.""",

    AnalysisType.EMPLOYMENT_VERIFICATION: """You are a mortgage processor verifying employment information across documents.

Analyze the following documents to verify:
1. Current employer name and address
2. Employment start date / length of employment
3. Job title or position
4. Current pay rate and pay frequency
5. Is the borrower W-2 employed, self-employed, or both?
6. Consistency of employer information across all documents

Identify any discrepancies or missing verification items.
Rate each finding as: VERIFIED, NEEDS VERIFICATION, or DISCREPANCY.""",

    AnalysisType.IDENTITY_VERIFICATION: """You are a mortgage compliance analyst verifying borrower identity across documents.

Analyze the following documents to verify:
1. Full legal name consistency across all documents
2. Current address consistency
3. Date of birth (if available)
4. ID document validity (expiration date)
5. Name variations or aliases that need explanation

Identify any discrepancies requiring an LOE (Letter of Explanation).
Rate each finding as: VERIFIED, NEEDS LOE, or DISCREPANCY.""",
}


# =============================================================================
# CONVERSATION STORE (in-memory with DB persistence)
# =============================================================================

class ConversationStore:
    """Manages conversation history with in-memory caching and DB persistence.

    Conversations are keyed by (org_id, conversation_id) for tenant isolation.
    The in-memory cache keeps recent conversations for fast access; DB provides
    durability across restarts.
    """

    # Class-level in-memory cache (cleared on restart)
    _cache: Dict[str, List[ChatMessage]] = {}
    _metadata: Dict[str, Dict[str, Any]] = {}

    # Maximum messages retained per conversation (older messages are summarized)
    MAX_MESSAGES_PER_CONVERSATION = 50

    # Maximum conversations cached in memory
    MAX_CACHED_CONVERSATIONS = 500

    @classmethod
    def _cache_key(cls, org_id: int, conversation_id: str) -> str:
        return f"{org_id}:{conversation_id}"

    @classmethod
    def create_conversation(
        cls,
        db: Session,
        org_id: int,
        user_id: int,
        document_ids: List[int],
        loan_id: Optional[int] = None,
    ) -> str:
        """Create a new conversation and return its ID."""
        conversation_id = uuid.uuid4().hex[:16]
        key = cls._cache_key(org_id, conversation_id)

        cls._metadata[key] = {
            "org_id": org_id,
            "user_id": user_id,
            "document_ids": document_ids,
            "loan_id": loan_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        cls._cache[key] = []

        # Persist to DB
        try:
            db.execute(
                text("""
                    INSERT INTO document_chat_conversations
                        (id, organization_id, user_id, loan_id, document_ids, created_at)
                    VALUES
                        (:id, :org_id, :user_id, :loan_id, :doc_ids, :created_at)
                """),
                {
                    "id": conversation_id,
                    "org_id": org_id,
                    "user_id": user_id,
                    "loan_id": loan_id,
                    "doc_ids": json.dumps(document_ids),
                    "created_at": datetime.now(timezone.utc),
                },
            )
            db.flush()
        except Exception as e:
            # Table may not exist yet; log and continue with in-memory only
            logger.warning(
                "Could not persist conversation to DB (table may not exist): %s",
                str(e)[:200],
            )

        # Evict oldest cached conversations if over limit
        if len(cls._cache) > cls.MAX_CACHED_CONVERSATIONS:
            oldest_key = next(iter(cls._cache))
            del cls._cache[oldest_key]
            cls._metadata.pop(oldest_key, None)

        logger.info(
            "Created conversation | conversation_id=%s | org_id=%s | "
            "user_id=%s | document_ids=%s",
            conversation_id, org_id, user_id, document_ids,
        )

        return conversation_id

    @classmethod
    def add_message(
        cls,
        db: Session,
        org_id: int,
        conversation_id: str,
        message: ChatMessage,
    ) -> None:
        """Add a message to a conversation."""
        key = cls._cache_key(org_id, conversation_id)

        if key not in cls._cache:
            # Try to load from DB
            cls._load_from_db(db, org_id, conversation_id)

        if key not in cls._cache:
            cls._cache[key] = []

        cls._cache[key].append(message)

        # Truncate if over limit
        if len(cls._cache[key]) > cls.MAX_MESSAGES_PER_CONVERSATION:
            cls._cache[key] = cls._cache[key][-cls.MAX_MESSAGES_PER_CONVERSATION:]

        # Persist message to DB
        try:
            db.execute(
                text("""
                    INSERT INTO document_chat_messages
                        (conversation_id, organization_id, role, content,
                         citations, confidence, token_usage, created_at)
                    VALUES
                        (:conv_id, :org_id, :role, :content,
                         :citations, :confidence, :token_usage, :created_at)
                """),
                {
                    "conv_id": conversation_id,
                    "org_id": org_id,
                    "role": message.role,
                    "content": message.content,
                    "citations": json.dumps(
                        [c.to_dict() for c in message.citations]
                    ) if message.citations else None,
                    "confidence": message.confidence.value if message.confidence else None,
                    "token_usage": json.dumps(message.token_usage) if message.token_usage else None,
                    "created_at": datetime.now(timezone.utc),
                },
            )
            db.flush()
        except Exception as e:
            logger.warning(
                "Could not persist message to DB: %s", str(e)[:200],
            )

    @classmethod
    def get_messages(
        cls,
        db: Session,
        org_id: int,
        conversation_id: str,
    ) -> List[ChatMessage]:
        """Get all messages for a conversation (org-isolated)."""
        key = cls._cache_key(org_id, conversation_id)

        if key not in cls._cache:
            cls._load_from_db(db, org_id, conversation_id)

        return cls._cache.get(key, [])

    @classmethod
    def get_api_messages(
        cls,
        db: Session,
        org_id: int,
        conversation_id: str,
        max_context_messages: int = 10,
    ) -> List[Dict[str, str]]:
        """Get conversation history formatted for the Anthropic API.

        Returns the most recent messages as {"role": ..., "content": ...} dicts.
        Limits context window to avoid token overflow.
        """
        messages = cls.get_messages(db, org_id, conversation_id)
        recent = messages[-max_context_messages:] if messages else []
        return [{"role": m.role, "content": m.content} for m in recent]

    @classmethod
    def _load_from_db(
        cls,
        db: Session,
        org_id: int,
        conversation_id: str,
    ) -> None:
        """Load conversation from database into cache."""
        key = cls._cache_key(org_id, conversation_id)
        try:
            rows = db.execute(
                text("""
                    SELECT role, content, citations, confidence, token_usage, created_at
                    FROM document_chat_messages
                    WHERE conversation_id = :conv_id
                      AND organization_id = :org_id
                    ORDER BY created_at ASC
                """),
                {"conv_id": conversation_id, "org_id": org_id},
            ).fetchall()

            messages = []
            for row in rows:
                citations = []
                if row.citations:
                    raw_citations = json.loads(row.citations) if isinstance(row.citations, str) else row.citations
                    citations = [
                        Citation(
                            document_id=c.get("document_id", 0),
                            document_name=c.get("document_name", ""),
                            doc_type=c.get("doc_type", ""),
                            page_number=c.get("page_number"),
                            relevant_text=c.get("relevant_text", ""),
                        )
                        for c in raw_citations
                    ]

                confidence = None
                if row.confidence:
                    try:
                        confidence = Confidence(row.confidence)
                    except ValueError:
                        confidence = Confidence.MEDIUM

                token_usage = None
                if row.token_usage:
                    token_usage = json.loads(row.token_usage) if isinstance(row.token_usage, str) else row.token_usage

                messages.append(ChatMessage(
                    role=row.role,
                    content=row.content,
                    citations=citations,
                    confidence=confidence,
                    timestamp=row.created_at.isoformat() if row.created_at else "",
                    token_usage=token_usage,
                ))

            cls._cache[key] = messages

        except Exception as e:
            logger.warning(
                "Could not load conversation from DB: %s", str(e)[:200],
            )
            cls._cache[key] = []


# =============================================================================
# DOCUMENT CHAT SERVICE
# =============================================================================

class DocumentChatService:
    """AI-powered document Q&A service for mortgage loan files.

    Provides conversational interaction with document content, including
    single-document questions, multi-document cross-referencing, and
    pre-built underwriting analysis prompts.

    All operations are scoped to org_id for tenant isolation.

    Args:
        db: SQLAlchemy session.
        org_id: Organization ID for tenant isolation.
        user_id: Authenticated user performing the query.
        model: AI model to use. Defaults to ANTHROPIC_MODEL env var.
    """

    # Maximum combined document text length sent to the AI model (characters)
    MAX_CONTEXT_LENGTH = 80_000

    # Maximum text per individual document
    MAX_DOC_TEXT_LENGTH = 25_000

    def __init__(
        self,
        db: Session,
        org_id: int,
        user_id: int,
        model: Optional[str] = None,
    ):
        if not org_id:
            raise ValueError("org_id is required for DocumentChatService")

        self.db = db
        self.org_id = org_id
        self.user_id = user_id
        self.model = model or os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-20250514")
        self._client: Optional[Any] = None

    @property
    def client(self) -> Any:
        """Lazily initialize the Anthropic client."""
        if self._client is None:
            if not HAS_ANTHROPIC:
                raise RuntimeError(
                    "anthropic package is not installed. "
                    "Install with: pip install anthropic"
                )
            self._client = Anthropic()
        return self._client

    # =========================================================================
    # PUBLIC API
    # =========================================================================

    async def ask_question(
        self,
        document_ids: List[int],
        question: str,
        conversation_id: Optional[str] = None,
    ) -> ChatResponse:
        """Ask a natural language question about one or more documents.

        Args:
            document_ids: List of smart_document IDs to query against.
            question: The user's question in natural language.
            conversation_id: Optional existing conversation ID for follow-ups.
                If None, a new conversation is created.

        Returns:
            ChatResponse with the answer, citations, and metadata.

        Raises:
            ValueError: If no document_ids provided or question is empty.
            RuntimeError: If Anthropic client is unavailable.
        """
        start_time = time.monotonic()

        if not document_ids:
            raise ValueError("At least one document_id is required")
        if not question or not question.strip():
            raise ValueError("Question cannot be empty")

        logger.info(
            "Document Q&A | org_id=%s | user_id=%s | doc_ids=%s | "
            "question_length=%d | conversation_id=%s",
            self.org_id, self.user_id, document_ids,
            len(question), conversation_id,
        )

        # Load document content with org isolation
        documents = self._load_documents(document_ids)
        if not documents:
            return ChatResponse(
                answer="No accessible documents found for the given IDs.",
                citations=[],
                confidence=Confidence.LOW,
                conversation_id=conversation_id or "",
                token_usage={"input_tokens": 0, "output_tokens": 0},
                cost_estimate=0.0,
                model_used=self.model,
                duration_ms=int((time.monotonic() - start_time) * 1000),
            )

        # Get or create conversation
        if conversation_id:
            # Verify conversation belongs to this org
            existing = ConversationStore.get_messages(
                self.db, self.org_id, conversation_id,
            )
            if existing is None:
                conversation_id = ConversationStore.create_conversation(
                    self.db, self.org_id, self.user_id, document_ids,
                )
        else:
            # Determine loan_id from documents
            loan_id = documents[0].get("loan_id") if documents else None
            conversation_id = ConversationStore.create_conversation(
                self.db, self.org_id, self.user_id, document_ids,
                loan_id=loan_id,
            )

        # Record user message
        user_message = ChatMessage(role="user", content=question)
        ConversationStore.add_message(
            self.db, self.org_id, conversation_id, user_message,
        )

        # Build context and call AI
        context = self._build_document_context(documents)
        conversation_history = ConversationStore.get_api_messages(
            self.db, self.org_id, conversation_id,
            max_context_messages=8,
        )

        system_prompt = self._build_qa_system_prompt(documents)

        # Build messages: conversation history already includes the current question
        messages = conversation_history

        # Call AI with circuit breaker
        response = resilient_ai_call(
            client=self.client,
            messages=messages,
            model=self.model,
            max_tokens=4096,
            operation_name="document_chat_qa",
            system=system_prompt,
            org_id=self.org_id,
        )

        if response is None:
            error_response = ChatResponse(
                answer="I'm sorry, I'm unable to process your question right now. "
                       "The AI service is temporarily unavailable. Please try again later.",
                citations=[],
                confidence=Confidence.LOW,
                conversation_id=conversation_id,
                token_usage={"input_tokens": 0, "output_tokens": 0},
                cost_estimate=0.0,
                model_used=self.model,
                duration_ms=int((time.monotonic() - start_time) * 1000),
            )
            return error_response

        # Extract response content and usage
        raw_answer = response.content[0].text if response.content else ""
        input_tokens = getattr(getattr(response, "usage", None), "input_tokens", 0)
        output_tokens = getattr(getattr(response, "usage", None), "output_tokens", 0)
        cost = _estimate_cost(self.model, input_tokens, output_tokens)

        # Parse citations from the response
        citations = self._extract_citations(raw_answer, documents)

        # Determine confidence
        confidence = self._assess_confidence(raw_answer, citations, documents)

        # Filter PII from the answer
        filtered_answer, pii_redacted = PIIFilter.redact(raw_answer)

        duration_ms = int((time.monotonic() - start_time) * 1000)
        token_usage = {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
        }

        # Record assistant message
        assistant_message = ChatMessage(
            role="assistant",
            content=filtered_answer,
            citations=citations,
            confidence=confidence,
            token_usage=token_usage,
        )
        ConversationStore.add_message(
            self.db, self.org_id, conversation_id, assistant_message,
        )

        # Log token usage for cost tracking
        self._log_token_usage(
            operation="document_chat_qa",
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost=cost,
            document_ids=document_ids,
            conversation_id=conversation_id,
        )

        logger.info(
            "Document Q&A complete | org_id=%s | conversation_id=%s | "
            "confidence=%s | input_tokens=%d | output_tokens=%d | "
            "cost=$%.4f | duration_ms=%d | pii_redacted=%s",
            self.org_id, conversation_id, confidence.value,
            input_tokens, output_tokens, cost, duration_ms, pii_redacted,
        )

        return ChatResponse(
            answer=filtered_answer,
            citations=citations,
            confidence=confidence,
            conversation_id=conversation_id,
            token_usage=token_usage,
            cost_estimate=cost,
            model_used=self.model,
            duration_ms=duration_ms,
            pii_redacted=pii_redacted,
        )

    async def run_analysis(
        self,
        loan_id: int,
        analysis_type: str,
    ) -> AnalysisResult:
        """Run a pre-built analysis across all documents for a loan.

        Args:
            loan_id: The loan ID to analyze documents for.
            analysis_type: One of the AnalysisType enum values.

        Returns:
            AnalysisResult with findings and recommendations.

        Raises:
            ValueError: If analysis_type is invalid.
        """
        start_time = time.monotonic()

        # Validate analysis type
        try:
            a_type = AnalysisType(analysis_type)
        except ValueError:
            valid_types = [t.value for t in AnalysisType]
            raise ValueError(
                f"Invalid analysis_type '{analysis_type}'. "
                f"Valid types: {valid_types}"
            )

        logger.info(
            "Running analysis | org_id=%s | loan_id=%s | type=%s",
            self.org_id, loan_id, analysis_type,
        )

        # Verify loan belongs to this org
        self._verify_loan_access(loan_id)

        # Load all documents for the loan
        documents = self._load_loan_documents(loan_id)
        if not documents:
            return AnalysisResult(
                analysis_type=analysis_type,
                loan_id=loan_id,
                summary="No documents found for this loan.",
                findings=[],
                recommendations=["Upload required documents to proceed with analysis."],
                documents_analyzed=[],
                confidence=Confidence.LOW,
                token_usage={"input_tokens": 0, "output_tokens": 0},
                cost_estimate=0.0,
                model_used=self.model,
                duration_ms=int((time.monotonic() - start_time) * 1000),
            )

        # Build analysis prompt
        analysis_prompt = ANALYSIS_PROMPTS.get(a_type, "")
        context = self._build_document_context(documents)

        system_prompt = f"""{analysis_prompt}

IMPORTANT RESPONSE FORMAT:
Respond with a JSON object containing:
{{
    "summary": "Brief overall assessment (2-3 sentences)",
    "findings": [
        {{
            "category": "category name",
            "severity": "CRITICAL|WARNING|INFO",
            "description": "What was found",
            "documents_involved": ["document names involved"],
            "specific_values": "Relevant numbers/values"
        }}
    ],
    "recommendations": ["Actionable recommendation 1", "Recommendation 2"],
    "overall_confidence": "high|medium|low"
}}

Respond with ONLY the JSON object, no additional text or markdown."""

        messages = [
            {
                "role": "user",
                "content": f"Analyze the following loan file documents:\n\n{context}",
            }
        ]

        response = resilient_ai_call(
            client=self.client,
            messages=messages,
            model=self.model,
            max_tokens=4096,
            operation_name=f"document_analysis_{analysis_type}",
            system=system_prompt,
            org_id=self.org_id,
        )

        if response is None:
            return AnalysisResult(
                analysis_type=analysis_type,
                loan_id=loan_id,
                summary="Analysis could not be completed. AI service is temporarily unavailable.",
                findings=[],
                recommendations=["Retry the analysis later."],
                documents_analyzed=[
                    {"id": d["id"], "name": d["file_name"], "doc_type": d.get("doc_type", "")}
                    for d in documents
                ],
                confidence=Confidence.LOW,
                token_usage={"input_tokens": 0, "output_tokens": 0},
                cost_estimate=0.0,
                model_used=self.model,
                duration_ms=int((time.monotonic() - start_time) * 1000),
            )

        raw_text = response.content[0].text if response.content else "{}"
        input_tokens = getattr(getattr(response, "usage", None), "input_tokens", 0)
        output_tokens = getattr(getattr(response, "usage", None), "output_tokens", 0)
        cost = _estimate_cost(self.model, input_tokens, output_tokens)

        # Parse structured response
        parsed = self._parse_analysis_response(raw_text)

        # PII-filter the summary and findings
        filtered_summary, _ = PIIFilter.redact(parsed.get("summary", ""))
        filtered_findings = []
        for finding in parsed.get("findings", []):
            desc, _ = PIIFilter.redact(finding.get("description", ""))
            vals, _ = PIIFilter.redact(str(finding.get("specific_values", "")))
            filtered_findings.append({
                "category": finding.get("category", ""),
                "severity": finding.get("severity", "INFO"),
                "description": desc,
                "documents_involved": finding.get("documents_involved", []),
                "specific_values": vals,
            })

        filtered_recommendations = []
        for rec in parsed.get("recommendations", []):
            filtered_rec, _ = PIIFilter.redact(rec)
            filtered_recommendations.append(filtered_rec)

        raw_confidence = parsed.get("overall_confidence", "medium")
        try:
            confidence = Confidence(raw_confidence)
        except ValueError:
            confidence = Confidence.MEDIUM

        duration_ms = int((time.monotonic() - start_time) * 1000)
        token_usage = {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
        }

        self._log_token_usage(
            operation=f"document_analysis_{analysis_type}",
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost=cost,
            loan_id=loan_id,
        )

        logger.info(
            "Analysis complete | org_id=%s | loan_id=%s | type=%s | "
            "findings=%d | confidence=%s | cost=$%.4f | duration_ms=%d",
            self.org_id, loan_id, analysis_type,
            len(filtered_findings), confidence.value, cost, duration_ms,
        )

        return AnalysisResult(
            analysis_type=analysis_type,
            loan_id=loan_id,
            summary=filtered_summary,
            findings=filtered_findings,
            recommendations=filtered_recommendations,
            documents_analyzed=[
                {"id": d["id"], "name": d["file_name"], "doc_type": d.get("doc_type", "")}
                for d in documents
            ],
            confidence=confidence,
            token_usage=token_usage,
            cost_estimate=cost,
            model_used=self.model,
            duration_ms=duration_ms,
        )

    async def get_conversation(
        self,
        conversation_id: str,
    ) -> List[ChatMessage]:
        """Retrieve conversation history (org-isolated).

        Args:
            conversation_id: The conversation to retrieve.

        Returns:
            List of ChatMessage objects in chronological order.
        """
        messages = ConversationStore.get_messages(
            self.db, self.org_id, conversation_id,
        )
        logger.info(
            "Retrieved conversation | org_id=%s | conversation_id=%s | messages=%d",
            self.org_id, conversation_id, len(messages),
        )
        return messages

    async def get_suggested_questions(
        self,
        document_id: int,
    ) -> List[str]:
        """Get suggested questions for a specific document based on its type.

        Args:
            document_id: The smart_document ID.

        Returns:
            List of suggested question strings.
        """
        # Load document metadata with org isolation
        doc = self._load_single_document(document_id)
        if not doc:
            return DEFAULT_QUESTION_TEMPLATES

        doc_type = doc.get("doc_type", "")
        if not doc_type:
            doc_type = doc.get("detected_doc_type", "")

        questions = QUESTION_TEMPLATES.get(doc_type, DEFAULT_QUESTION_TEMPLATES)

        logger.info(
            "Suggested questions | org_id=%s | document_id=%s | "
            "doc_type=%s | suggestions=%d",
            self.org_id, document_id, doc_type, len(questions),
        )

        return questions

    async def run_batch_analysis(
        self,
        loan_id: int,
    ) -> List[AnalysisResult]:
        """Run all applicable standard analyses across a loan's documents.

        Determines which analysis types are applicable based on the document
        types present in the loan file, then runs each relevant analysis.

        Args:
            loan_id: The loan to analyze.

        Returns:
            List of AnalysisResult for each applicable analysis type.
        """
        logger.info(
            "Starting batch analysis | org_id=%s | loan_id=%s",
            self.org_id, loan_id,
        )

        self._verify_loan_access(loan_id)

        # Load all docs to determine which analyses are applicable
        documents = self._load_loan_documents(loan_id)
        if not documents:
            return []

        doc_types_present = {d.get("doc_type", "") for d in documents}

        # Determine applicable analyses based on document types present
        applicable_analyses = []

        income_types = {"PAYSTUB", "W2", "TAX_RETURN", "BUSINESS_TAX_RETURN", "PROFIT_LOSS"}
        if doc_types_present & income_types:
            applicable_analyses.append(AnalysisType.INCOME_CONSISTENCY)
            applicable_analyses.append(AnalysisType.EMPLOYMENT_VERIFICATION)

        asset_types = {"BANK_STATEMENT", "INVESTMENT_STATEMENT"}
        if doc_types_present & asset_types:
            applicable_analyses.append(AnalysisType.ASSET_SUFFICIENCY)

        identity_types = {"DRIVERS_LICENSE"}
        if doc_types_present & identity_types:
            applicable_analyses.append(AnalysisType.IDENTITY_VERIFICATION)

        # Red flags and condition clearance are always applicable
        applicable_analyses.append(AnalysisType.RED_FLAG_IDENTIFICATION)
        applicable_analyses.append(AnalysisType.CONDITION_CLEARANCE)

        results = []
        for analysis_type in applicable_analyses:
            try:
                result = await self.run_analysis(loan_id, analysis_type.value)
                results.append(result)
            except Exception as e:
                logger.exception(
                    "Batch analysis failed for type %s | org_id=%s | loan_id=%s: %s",
                    analysis_type.value, self.org_id, loan_id, e,
                )

        logger.info(
            "Batch analysis complete | org_id=%s | loan_id=%s | "
            "analyses_run=%d | analyses_total=%d",
            self.org_id, loan_id, len(results), len(applicable_analyses),
        )

        return results

    # =========================================================================
    # PRIVATE HELPERS
    # =========================================================================

    def _verify_loan_access(self, loan_id: int) -> None:
        """Verify loan belongs to this organization."""
        from fastapi import HTTPException

        row = self.db.execute(
            text("SELECT organization_id FROM loans WHERE id = :loan_id"),
            {"loan_id": loan_id},
        ).fetchone()

        if not row:
            raise HTTPException(status_code=404, detail=f"Loan {loan_id} not found")

        if row.organization_id != self.org_id:
            logger.warning(
                "Tenant isolation violation in document chat: org %s attempted "
                "to access loan %s belonging to org %s",
                self.org_id, loan_id, row.organization_id,
            )
            raise HTTPException(status_code=404, detail=f"Loan {loan_id} not found")

    def _load_documents(self, document_ids: List[int]) -> List[Dict[str, Any]]:
        """Load document content with org-level isolation.

        Only returns documents that belong to loans in the current org.
        """
        if not document_ids:
            return []

        # Use parameterized query with IN clause
        placeholders = ", ".join(f":id_{i}" for i in range(len(document_ids)))
        params: Dict[str, Any] = {
            f"id_{i}": doc_id for i, doc_id in enumerate(document_ids)
        }
        params["org_id"] = self.org_id

        rows = self.db.execute(
            text(f"""
                SELECT
                    sd.id, sd.file_name, sd.original_filename,
                    sd.doc_type, sd.detected_doc_type,
                    sd.ocr_text, sd.extracted_dates,
                    sd.extracted_names, sd.extracted_employer,
                    sd.extraction_confidence, sd.page_count,
                    sd.loan_id, sd.borrower_id,
                    sd.status, sd.mime_type
                FROM smart_documents sd
                JOIN loans l ON l.id = sd.loan_id
                WHERE sd.id IN ({placeholders})
                  AND l.organization_id = :org_id
                ORDER BY sd.doc_type, sd.created_at DESC
            """),
            params,
        ).fetchall()

        documents = []
        for row in rows:
            doc = {
                "id": row.id,
                "file_name": row.file_name or row.original_filename or f"Document {row.id}",
                "doc_type": row.doc_type.value if row.doc_type else (row.detected_doc_type or "OTHER"),
                "ocr_text": (row.ocr_text or "")[:self.MAX_DOC_TEXT_LENGTH],
                "extracted_dates": row.extracted_dates,
                "extracted_names": row.extracted_names,
                "extracted_employer": row.extracted_employer,
                "extraction_confidence": row.extraction_confidence,
                "page_count": row.page_count,
                "loan_id": row.loan_id,
                "borrower_id": row.borrower_id,
                "status": row.status,
                "mime_type": row.mime_type,
            }
            documents.append(doc)

        if len(documents) < len(document_ids):
            logger.warning(
                "Some documents not found or not accessible | "
                "requested=%d | found=%d | org_id=%s",
                len(document_ids), len(documents), self.org_id,
            )

        return documents

    def _load_single_document(self, document_id: int) -> Optional[Dict[str, Any]]:
        """Load a single document with org isolation."""
        docs = self._load_documents([document_id])
        return docs[0] if docs else None

    def _load_loan_documents(self, loan_id: int) -> List[Dict[str, Any]]:
        """Load all documents for a loan with org isolation."""
        rows = self.db.execute(
            text("""
                SELECT sd.id
                FROM smart_documents sd
                JOIN loans l ON l.id = sd.loan_id
                WHERE sd.loan_id = :loan_id
                  AND l.organization_id = :org_id
                  AND sd.status NOT IN ('REJECTED', 'EXPIRED')
                ORDER BY sd.doc_type, sd.created_at DESC
            """),
            {"loan_id": loan_id, "org_id": self.org_id},
        ).fetchall()

        doc_ids = [row.id for row in rows]
        if not doc_ids:
            return []

        return self._load_documents(doc_ids)

    def _build_document_context(self, documents: List[Dict[str, Any]]) -> str:
        """Build a formatted context string from document contents.

        Structures each document's OCR text with clear boundaries and metadata
        so the AI model can cite specific documents in its response.
        """
        context_parts = []
        total_length = 0

        for doc in documents:
            ocr_text = doc.get("ocr_text", "")
            if not ocr_text:
                ocr_text = "[No text content extracted from this document]"

            # Truncate individual documents if needed
            remaining_budget = self.MAX_CONTEXT_LENGTH - total_length
            if remaining_budget <= 0:
                logger.warning(
                    "Context length limit reached, skipping document %s",
                    doc["id"],
                )
                break

            truncated_text = ocr_text[:remaining_budget]

            doc_header = (
                f"--- DOCUMENT: {doc['file_name']} ---\n"
                f"Document ID: {doc['id']}\n"
                f"Type: {doc['doc_type']}\n"
            )

            if doc.get("page_count"):
                doc_header += f"Pages: {doc['page_count']}\n"
            if doc.get("extracted_employer"):
                doc_header += f"Employer: {doc['extracted_employer']}\n"
            if doc.get("extracted_names"):
                names = doc["extracted_names"]
                if isinstance(names, list):
                    doc_header += f"Names: {', '.join(names)}\n"
                elif isinstance(names, str):
                    doc_header += f"Names: {names}\n"

            doc_section = f"{doc_header}\nCONTENT:\n{truncated_text}\n--- END DOCUMENT ---\n\n"

            context_parts.append(doc_section)
            total_length += len(doc_section)

        return "\n".join(context_parts)

    def _build_qa_system_prompt(self, documents: List[Dict[str, Any]]) -> str:
        """Build the system prompt for document Q&A."""
        doc_list = "\n".join(
            f"  - {d['file_name']} (ID: {d['id']}, Type: {d['doc_type']})"
            for d in documents
        )

        return f"""You are a knowledgeable mortgage document analyst assisting a loan officer.
You have access to the following documents from a loan file:
{doc_list}

INSTRUCTIONS:
1. Answer the user's question based ONLY on the content of the provided documents.
2. If the answer is not found in the documents, say so clearly. Do not make up information.
3. When citing information, reference the specific document by name and type.
4. If you can identify the page or section, mention it.
5. Include relevant numbers, dates, and amounts in your answer.
6. For financial calculations, show your work step by step.
7. If documents contain inconsistent information, point out the discrepancy.
8. Keep answers concise but thorough.

IMPORTANT PRIVACY RULES:
- Never output full Social Security Numbers. Use format ***-**-XXXX (last 4 only).
- Never output full bank account numbers. Mask all but last 4 digits.
- Never output full routing numbers.
- You may reference partial account numbers (last 4 digits) for identification.

CITATION FORMAT:
When referencing document content, use the format:
[Source: Document Name (Type)] or [Source: Document Name, Page X]"""

    def _extract_citations(
        self,
        answer: str,
        documents: List[Dict[str, Any]],
    ) -> List[Citation]:
        """Extract citations from the AI response.

        Looks for [Source: ...] patterns and also identifies which documents
        were referenced by name in the response.
        """
        citations = []
        seen_doc_ids: set = set()

        # Pattern 1: Explicit [Source: ...] citations
        source_pattern = re.compile(
            r"\[Source:\s*([^\]]+)\]",
            re.IGNORECASE,
        )

        for match in source_pattern.finditer(answer):
            source_text = match.group(1).strip()

            # Try to match to a specific document
            for doc in documents:
                doc_name = doc["file_name"]
                doc_type = doc["doc_type"]

                if (
                    doc_name.lower() in source_text.lower()
                    or doc_type.lower() in source_text.lower()
                ) and doc["id"] not in seen_doc_ids:
                    # Extract page number if present
                    page_match = re.search(r"[Pp]age\s*(\d+)", source_text)
                    page_number = int(page_match.group(1)) if page_match else None

                    citations.append(Citation(
                        document_id=doc["id"],
                        document_name=doc_name,
                        doc_type=doc_type,
                        page_number=page_number,
                        relevant_text=source_text,
                    ))
                    seen_doc_ids.add(doc["id"])
                    break

        # Pattern 2: Documents referenced by name in the answer text
        for doc in documents:
            if doc["id"] in seen_doc_ids:
                continue

            doc_name = doc["file_name"]
            doc_type = doc["doc_type"]

            # Check if the document name or type is mentioned in the answer
            name_lower = doc_name.lower()
            type_lower = doc_type.lower().replace("_", " ")

            if name_lower in answer.lower() or type_lower in answer.lower():
                citations.append(Citation(
                    document_id=doc["id"],
                    document_name=doc_name,
                    doc_type=doc_type,
                    relevant_text=f"Referenced in answer as {doc_type}",
                ))
                seen_doc_ids.add(doc["id"])

        return citations

    def _assess_confidence(
        self,
        answer: str,
        citations: List[Citation],
        documents: List[Dict[str, Any]],
    ) -> Confidence:
        """Assess the confidence level of the AI's answer.

        Factors:
        - Whether citations were found
        - Document extraction confidence
        - Presence of hedging language
        - Whether OCR text was available
        """
        # Start with medium confidence
        score = 50

        # Citations boost confidence
        if citations:
            score += 15
            if len(citations) >= 2:
                score += 10  # Multi-source corroboration

        # Document extraction quality
        avg_extraction_confidence = 0.0
        docs_with_text = 0
        for doc in documents:
            if doc.get("ocr_text"):
                docs_with_text += 1
                conf = doc.get("extraction_confidence")
                if conf is not None:
                    avg_extraction_confidence += float(conf)

        if docs_with_text > 0:
            avg_extraction_confidence /= docs_with_text
            if avg_extraction_confidence >= 80:
                score += 15
            elif avg_extraction_confidence >= 50:
                score += 5
        else:
            score -= 20  # No text content available

        # Hedging language reduces confidence
        hedging_phrases = [
            "i'm not sure", "i cannot determine", "unclear",
            "not found in the document", "unable to find",
            "no information", "cannot confirm", "may not be",
            "appears to be", "possibly", "it seems",
        ]
        answer_lower = answer.lower()
        hedging_count = sum(1 for phrase in hedging_phrases if phrase in answer_lower)
        score -= hedging_count * 10

        # Definitive language boosts confidence
        definitive_phrases = [
            "the document shows", "according to the",
            "the amount is", "the total is", "as stated in",
        ]
        definitive_count = sum(1 for phrase in definitive_phrases if phrase in answer_lower)
        score += definitive_count * 5

        # Clamp and classify
        score = max(0, min(100, score))

        if score >= 70:
            return Confidence.HIGH
        elif score >= 40:
            return Confidence.MEDIUM
        else:
            return Confidence.LOW

    def _parse_analysis_response(self, raw_text: str) -> Dict[str, Any]:
        """Parse the structured JSON response from an analysis prompt.

        Handles markdown code blocks and malformed JSON gracefully.
        """
        text = raw_text.strip()

        # Remove markdown code blocks if present
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*\n?", "", text)
            text = re.sub(r"\n?```\s*$", "", text)

        try:
            return json.loads(text)
        except json.JSONDecodeError:
            logger.warning(
                "Failed to parse analysis response as JSON, using fallback | "
                "org_id=%s | response_preview=%s",
                self.org_id, text[:200],
            )
            # Fallback: wrap raw text as a finding
            return {
                "summary": text[:500] if text else "Analysis could not be structured.",
                "findings": [],
                "recommendations": [],
                "overall_confidence": "low",
            }

    def _log_token_usage(
        self,
        operation: str,
        input_tokens: int,
        output_tokens: int,
        cost: float,
        document_ids: Optional[List[int]] = None,
        conversation_id: Optional[str] = None,
        loan_id: Optional[int] = None,
    ) -> None:
        """Log token usage for cost attribution and monitoring.

        Attempts to persist to the ai_usage_log table. Falls back to
        structured logging if the table does not exist.
        """
        try:
            self.db.execute(
                text("""
                    INSERT INTO ai_usage_log
                        (organization_id, user_id, operation, model,
                         input_tokens, output_tokens, estimated_cost_usd,
                         metadata, created_at)
                    VALUES
                        (:org_id, :user_id, :operation, :model,
                         :input_tokens, :output_tokens, :cost,
                         :metadata, :created_at)
                """),
                {
                    "org_id": self.org_id,
                    "user_id": self.user_id,
                    "operation": operation,
                    "model": self.model,
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "cost": cost,
                    "metadata": json.dumps({
                        "document_ids": document_ids,
                        "conversation_id": conversation_id,
                        "loan_id": loan_id,
                    }),
                    "created_at": datetime.now(timezone.utc),
                },
            )
            self.db.flush()
        except Exception as e:
            # Table may not exist; fall through to structured log
            logger.debug(
                "Could not persist usage to ai_usage_log: %s", str(e)[:100],
            )

        # Always log usage structurally for DataDog/monitoring
        logger.info(
            "AI token usage | operation=%s | org_id=%s | user_id=%s | "
            "model=%s | input_tokens=%d | output_tokens=%d | cost=$%.6f",
            operation, self.org_id, self.user_id,
            self.model, input_tokens, output_tokens, cost,
        )


# =============================================================================
# SERVICE FACTORY
# =============================================================================

def get_document_chat_service(
    db: Session,
    org_id: int,
    user_id: int,
    model: Optional[str] = None,
) -> DocumentChatService:
    """Factory function for DocumentChatService.

    Args:
        db: SQLAlchemy session.
        org_id: Organization ID.
        user_id: User ID.
        model: Optional AI model override.

    Returns:
        Configured DocumentChatService instance.
    """
    return DocumentChatService(
        db=db,
        org_id=org_id,
        user_id=user_id,
        model=model,
    )
