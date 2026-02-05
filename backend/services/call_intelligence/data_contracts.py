"""
Data Contracts for Call Intelligence Service

Defines input/output formats for call transcript processing.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional, List, Dict, Any

logger = logging.getLogger(__name__)


class CallType(str, Enum):
    """Types of calls processed."""
    INITIAL_INTAKE = "initial_intake"
    FOLLOW_UP = "follow_up"
    DOCUMENT_REVIEW = "document_review"
    RATE_LOCK = "rate_lock"
    CLOSING_PREP = "closing_prep"
    OTHER = "other"


class SpeakerRole(str, Enum):
    """Role of speaker in transcript."""
    AI_LO = "ai_lo"           # AI Loan Officer
    BORROWER = "borrower"
    CO_BORROWER = "co_borrower"
    HUMAN_LO = "human_lo"     # Human Loan Officer
    UNKNOWN = "unknown"


class ExtractionConfidence(str, Enum):
    """Confidence level of extraction."""
    HIGH = "high"       # 90%+ - Clear statement
    MEDIUM = "medium"   # 70-90% - Implied or partial
    LOW = "low"         # <70% - Uncertain


class ExtractionMethod(str, Enum):
    """Method used for extraction."""
    UNIFIED = "unified"              # Single unified LLM call (6x efficient)
    PARALLEL_AGENTS = "parallel_agents"  # Legacy 6 parallel agent calls
    STREAMING = "streaming"          # Real-time streaming extraction
    REGEX_ONLY = "regex_only"        # Regex fallback (no LLM)


class BatchJobStatus(str, Enum):
    """Status of a batch processing job."""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    PARTIAL = "partial"  # Some requests succeeded, some failed


class ReviewStatus(str, Enum):
    """Status of a human review item."""
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    MODIFIED = "modified"


@dataclass
class TranscriptSegment:
    """A segment of the call transcript."""
    speaker: SpeakerRole
    text: str
    index: int = 0
    start_time: float = 0.0
    end_time: float = 0.0
    confidence: float = 1.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "speaker": self.speaker.value,
            "text": self.text,
            "index": self.index,
            "start_time": self.start_time,
            "end_time": self.end_time,
        }


@dataclass
class ExtractedValue:
    """A single extracted value with metadata."""
    field_name: str
    value: Any
    confidence: float  # 0-100
    source_text: str = ""  # The text it was extracted from
    segment_index: int = 0
    verified: bool = False
    verification_question: Optional[str] = None  # Question asked to verify
    extraction_method: str = "unknown"  # llm, regex, regex_fallback

    def __post_init__(self):
        """Validate field values after initialization."""
        # Clamp confidence to valid range with logging
        original_confidence = self.confidence
        if self.confidence < 0:
            self.confidence = 0.0
            logger.warning(
                f"Confidence {original_confidence} clamped to 0.0 for field '{self.field_name}'"
            )
        elif self.confidence > 100:
            self.confidence = 100.0
            logger.warning(
                f"Confidence {original_confidence} clamped to 100.0 for field '{self.field_name}'"
            )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "field_name": self.field_name,
            "value": self.value,
            "confidence": self.confidence,
            "source_text": self.source_text[:200] if self.source_text else "",
            "verified": self.verified,
            "extraction_method": self.extraction_method,
        }


@dataclass
class ExtractionResult:
    """Result from a single extraction agent."""
    agent_name: str
    extractions: List[ExtractedValue] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    processing_time_ms: int = 0

    def __post_init__(self):
        """Validate field values after initialization."""
        # Ensure processing_time_ms is non-negative
        if self.processing_time_ms < 0:
            self.processing_time_ms = 0

    def get_by_field(self, field_name: str) -> Optional[ExtractedValue]:
        """Get extraction by field name."""
        for ext in self.extractions:
            if ext.field_name == field_name:
                return ext
        return None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "agent": self.agent_name,
            "extractions": [e.to_dict() for e in self.extractions],
            "errors": self.errors,
            "warnings": self.warnings,
            "processing_time_ms": self.processing_time_ms,
        }


# Validation constants
MAX_CALL_ID_LENGTH = 255
MAX_TRANSCRIPT_SIZE = 500 * 1024  # 500KB


@dataclass
class CallIntelligenceRequest:
    """Request to process a call transcript."""
    call_id: str
    loan_id: Optional[int] = None
    organization_id: Optional[int] = None

    # Transcript data
    transcript: Optional[str] = None  # Full transcript as text
    segments: List[TranscriptSegment] = field(default_factory=list)

    # Call metadata
    call_type: CallType = CallType.INITIAL_INTAKE
    call_duration_seconds: int = 0
    call_timestamp: Optional[datetime] = None

    # Options
    agents_to_run: Optional[List[str]] = None  # None = all agents
    include_source_segments: bool = True
    min_confidence_threshold: float = 50.0

    # Context from previous calls/data
    existing_borrower_data: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        """Validate field values after initialization."""
        # Validate call_id length
        if len(self.call_id) > MAX_CALL_ID_LENGTH:
            raise ValueError(f"call_id exceeds maximum length of {MAX_CALL_ID_LENGTH} characters")

        # Validate transcript size
        if self.transcript and len(self.transcript) > MAX_TRANSCRIPT_SIZE:
            raise ValueError(f"transcript exceeds maximum size of {MAX_TRANSCRIPT_SIZE} bytes")

        # Clamp min_confidence_threshold to valid range
        if self.min_confidence_threshold < 0:
            self.min_confidence_threshold = 0.0
        elif self.min_confidence_threshold > 100:
            self.min_confidence_threshold = 100.0

        # Ensure call_duration_seconds is non-negative
        if self.call_duration_seconds < 0:
            self.call_duration_seconds = 0


@dataclass
class CallIntelligenceResponse:
    """Response from call intelligence processing."""
    call_id: str
    success: bool = True

    # Extracted data by category (maps to Application Engine modules)
    identity_extractions: Dict[str, Any] = field(default_factory=dict)
    address_extractions: Dict[str, Any] = field(default_factory=dict)
    employment_extractions: Dict[str, Any] = field(default_factory=dict)
    income_extractions: Dict[str, Any] = field(default_factory=dict)
    assets_extractions: Dict[str, Any] = field(default_factory=dict)
    liabilities_extractions: Dict[str, Any] = field(default_factory=dict)
    reo_extractions: Dict[str, Any] = field(default_factory=dict)
    declarations_extractions: Dict[str, Any] = field(default_factory=dict)

    # Loan intent/preferences
    intent_extractions: Dict[str, Any] = field(default_factory=dict)

    # Raw agent results
    agent_results: List[ExtractionResult] = field(default_factory=list)

    # Processing metadata
    total_extractions: int = 0
    high_confidence_count: int = 0
    low_confidence_count: int = 0
    processing_time_ms: int = 0
    processed_at: datetime = field(default_factory=datetime.utcnow)

    # Scalability fields (new)
    model_version: Optional[str] = None  # Model/prompt version for reproducibility
    pending_review_count: int = 0  # Count of extractions sent to human review
    batch_job_id: Optional[str] = None  # Batch job ID if processed as part of batch
    extraction_method: str = "unified"  # "unified", "parallel_agents", "streaming"

    # Errors
    errors: List[str] = field(default_factory=list)

    def to_application_engine_format(self) -> Dict[str, Dict[str, Any]]:
        """Convert to format expected by Application Engine."""
        return {
            "identity": self.identity_extractions,
            "address": self.address_extractions,
            "employment": self.employment_extractions,
            "income": self.income_extractions,
            "assets": self.assets_extractions,
            "liabilities": self.liabilities_extractions,
            "reo": self.reo_extractions,
            "declarations": self.declarations_extractions,
        }

    def to_dict(self) -> Dict[str, Any]:
        return {
            "call_id": self.call_id,
            "success": self.success,
            "extractions": self.to_application_engine_format(),
            "intent": self.intent_extractions,
            "summary": {
                "total_extractions": self.total_extractions,
                "high_confidence": self.high_confidence_count,
                "low_confidence": self.low_confidence_count,
            },
            "processing_time_ms": self.processing_time_ms,
            "processed_at": self.processed_at.isoformat(),
            "model_version": self.model_version,
            "pending_review_count": self.pending_review_count,
            "batch_job_id": self.batch_job_id,
            "extraction_method": self.extraction_method,
            "errors": self.errors,
        }


@dataclass
class BatchJob:
    """Represents a batch processing job."""
    batch_id: str
    total_requests: int
    completed: int = 0
    failed: int = 0
    status: str = "pending"  # pending, processing, completed, failed, partial
    created_at: datetime = field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None
    request_ids: List[str] = field(default_factory=list)
    results: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "batch_id": self.batch_id,
            "total_requests": self.total_requests,
            "completed": self.completed,
            "failed": self.failed,
            "status": self.status,
            "created_at": self.created_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "error_message": self.error_message,
            "progress_percent": round((self.completed + self.failed) / self.total_requests * 100, 1) if self.total_requests > 0 else 0,
        }


@dataclass
class ReviewQueueItem:
    """An extraction item in the human review queue."""
    review_id: str
    call_id: str
    loan_id: Optional[int]
    extraction_type: str  # identity, property, employment, etc.
    field_name: str
    extracted_value: Any
    confidence_score: float
    source_text: str
    status: str = "pending"  # pending, approved, rejected, modified
    reviewed_by: Optional[int] = None
    reviewed_at: Optional[datetime] = None
    reviewer_notes: Optional[str] = None
    final_value: Optional[Any] = None
    created_at: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "review_id": self.review_id,
            "call_id": self.call_id,
            "loan_id": self.loan_id,
            "extraction_type": self.extraction_type,
            "field_name": self.field_name,
            "extracted_value": self.extracted_value,
            "confidence_score": self.confidence_score,
            "source_text": self.source_text[:200] if self.source_text else "",
            "status": self.status,
            "reviewed_by": self.reviewed_by,
            "reviewed_at": self.reviewed_at.isoformat() if self.reviewed_at else None,
            "final_value": self.final_value,
            "created_at": self.created_at.isoformat(),
        }


@dataclass
class ReviewDecision:
    """Human review decision for an extraction."""
    review_id: str
    decision: str  # approved, rejected, modified
    reviewer_id: int
    final_value: Optional[Any] = None
    notes: Optional[str] = None
