"""
Call Intelligence Service

Processes call transcripts using AI agents to extract structured data
for the Application Engine.

The service includes 6 specialized AI agents:
1. Identity Agent - Names, SSN (last 4 only), DOB, contact info
2. Property Agent - Address, property details, purchase info
3. Employment Agent - Job history, employer details
4. Financial Agent - Income, assets, liabilities
5. Compliance Agent - Declarations, disclosures
6. Intent Agent - Loan purpose, timeline, preferences

SECURITY:
- SSN handling: Only last 4 digits are ever stored or transmitted
- All source_text fields are sanitized to remove PII
- Use pii_utils for any custom PII handling needs

Usage:
    from services.call_intelligence import CallIntelligenceProcessor

    processor = CallIntelligenceProcessor(db_session)
    result = await processor.process_transcript(
        call_id="call_123",
        transcript="..."
    )

    # Result contains extracted data for Application Engine
"""

from .processor import CallIntelligenceProcessor
from .agents import (
    IdentityExtractionAgent,
    PropertyExtractionAgent,
    EmploymentExtractionAgent,
    FinancialExtractionAgent,
    ComplianceExtractionAgent,
    IntentExtractionAgent,
    URLAExtractionAgent,
)
from .structured_diff import StructuredDiffComparator, DiffReport
from .data_contracts import (
    TranscriptSegment,
    ExtractionResult,
    CallIntelligenceRequest,
    CallIntelligenceResponse,
    CallOutcomeData,
    CallOutcome,
    NextAction,
    BorrowerSentiment,
)
from .pii_utils import (
    redact_ssn,
    extract_ssn_last_four,
    contains_ssn,
    mask_pii_for_logging,
    sanitize_source_text,
    redact_transcript_for_llm,
    redact_dob,
    redact_phone,
    redact_email,
)
from .extraction_validator import (
    ExtractionValidator,
    ValidationReport,
    AggregateReport,
    SAMPLE_TRANSCRIPTS,
)
from .metrics import (
    track_extraction,
    track_error,
    track_pii_redaction,
    collect_metrics,
    format_prometheus,
    get_metrics_handler,
    get_metrics_summary,
)
from .input_formats import (
    AudioSource,
    AudioProvider,
    TranscriptionConfig,
    TranscriptionProvider,
    TranscriptionResult,
    DocumentInput,
    DocumentType,
    parse_telnyx_webhook,
    parse_vonage_webhook,
)
from .email_templates import (
    TemplateManager,
    get_template_manager,
    EmailTemplate,
    SMSTemplate,
)
from .webhooks import (
    WebhookHandler,
    WebhookConfig,
    WebhookEventType,
    WebhookResult,
    create_webhook_handler,
)
from .review_service import HumanReviewService
from .recording_consent import (
    requires_two_party_consent,
    get_recording_disclosure,
    check_call_compliance,
    detect_disclosure_in_transcript,
    assess_recording_compliance,
    TWO_PARTY_STATES,
)

__all__ = [
    # Processor
    "CallIntelligenceProcessor",
    # Agents
    "IdentityExtractionAgent",
    "PropertyExtractionAgent",
    "EmploymentExtractionAgent",
    "FinancialExtractionAgent",
    "ComplianceExtractionAgent",
    "IntentExtractionAgent",
    # Data contracts
    "TranscriptSegment",
    "ExtractionResult",
    "CallIntelligenceRequest",
    "CallIntelligenceResponse",
    "CallOutcomeData",
    "CallOutcome",
    "NextAction",
    "BorrowerSentiment",
    # PII utilities
    "redact_ssn",
    "extract_ssn_last_four",
    "contains_ssn",
    "mask_pii_for_logging",
    "sanitize_source_text",
    "redact_transcript_for_llm",
    "redact_dob",
    "redact_phone",
    "redact_email",
    # Validation
    "ExtractionValidator",
    "ValidationReport",
    "AggregateReport",
    "SAMPLE_TRANSCRIPTS",
    # Metrics
    "track_extraction",
    "track_error",
    "track_pii_redaction",
    "collect_metrics",
    "format_prometheus",
    "get_metrics_handler",
    "get_metrics_summary",
    # Input formats
    "AudioSource",
    "AudioProvider",
    "TranscriptionConfig",
    "TranscriptionProvider",
    "TranscriptionResult",
    "DocumentInput",
    "DocumentType",
    "parse_telnyx_webhook",
    "parse_vonage_webhook",
    # Email templates
    "TemplateManager",
    "get_template_manager",
    "EmailTemplate",
    "SMSTemplate",
    # Webhooks
    "WebhookHandler",
    "WebhookConfig",
    "WebhookEventType",
    "WebhookResult",
    "create_webhook_handler",
    # Review service
    "HumanReviewService",
    # Recording consent
    "requires_two_party_consent",
    "get_recording_disclosure",
    "check_call_compliance",
    "detect_disclosure_in_transcript",
    "assess_recording_compliance",
    "TWO_PARTY_STATES",
]
