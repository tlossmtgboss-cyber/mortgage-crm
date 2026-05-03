"""
AI Agent Audit Trail

Structured audit logging for compliance (SOC 2, GLBA, mortgage regulations).
Records what the AI accessed, which tools it called, what data it returned,
and what actions it took — with correlation IDs for cross-service tracing.
"""

import logging
import os
import uuid
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# =============================================================================
# Correlation ID (request-scoped via ContextVar)
# =============================================================================

_request_id: ContextVar[Optional[str]] = ContextVar("_request_id", default=None)


def set_request_id(request_id: Optional[str] = None) -> str:
    """Set a correlation ID for the current request. Auto-generates if not provided."""
    rid = request_id or f"req_{uuid.uuid4().hex[:12]}"
    _request_id.set(rid)
    return rid


def get_request_id() -> Optional[str]:
    """Get the current correlation ID."""
    return _request_id.get()


def clear_request_id() -> None:
    """Clear the correlation ID."""
    _request_id.set(None)


# =============================================================================
# Audit Entry
# =============================================================================

@dataclass
class AuditEntry:
    """A single audit log entry for an AI orchestrator invocation."""
    request_id: str
    user_id: str
    organization_id: int
    intent: str
    user_message: str  # Truncated for storage
    response_text: str  # Truncated for storage
    model_used: str
    tokens_input: int = 0
    tokens_output: int = 0
    tools_called: List[str] = field(default_factory=list)
    tool_results_summary: Dict[str, str] = field(default_factory=dict)
    actions_executed: List[Dict[str, Any]] = field(default_factory=list)
    actions_pending: List[str] = field(default_factory=list)
    processing_time_ms: float = 0.0
    data_quality: str = "unknown"
    errors: List[str] = field(default_factory=list)
    pii_masked: bool = True
    hallucination_score: Optional[float] = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @staticmethod
    def _redact_pii(text: str) -> str:
        """Mask SSNs, full phone numbers, and account numbers before audit storage."""
        import re
        text = re.sub(r'\b\d{3}-\d{2}-\d{4}\b', '[REDACTED-SSN]', text)
        text = re.sub(r'\b(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b', '[REDACTED-PHONE]', text)
        text = re.sub(r'\b(?:account|acct|routing)[#:\s]*\d{4,}\b', '[REDACTED-ACCT]', text, flags=re.I)
        return text

    def to_db_params(self) -> Dict[str, Any]:
        """Convert to parameters for the ai_audit_log INSERT. PII is redacted."""
        import json
        return {
            "request_id": self.request_id,
            "action": self.intent or "chat",
            "input": self._redact_pii(self.user_message[:2000]),
            "output": self._redact_pii(self.response_text[:2000]),
            "user_id": self.user_id,
            "org_id": self.organization_id,
            "model": self.model_used,
            "tokens": self.tokens_input + self.tokens_output,
            "tools_json": json.dumps(self.tools_called),
            "actions_json": json.dumps(self.actions_executed),
            "processing_ms": self.processing_time_ms,
            "data_quality": self.data_quality,
            "errors_json": json.dumps(self.errors) if self.errors else None,
        }


# =============================================================================
# Audit Logger
# =============================================================================

class AuditLogger:
    """
    Structured audit logger for AI agent operations.

    Writes to both the ai_audit_log table (for queryable compliance records)
    and structured Python logging (for real-time monitoring / log aggregation).
    """

    # Columns that exist in the current ai_audit_log table
    _BASE_COLUMNS = {
        "action_type", "input_summary", "output_summary",
        "user_id", "organization_id", "model_used", "tokens_used",
        "created_at",
    }

    # Extended columns (added by migration)
    _EXTENDED_COLUMNS = {
        "request_id", "tools_used", "actions_taken",
        "processing_time_ms", "data_quality", "errors",
    }

    def __init__(self):
        self._has_extended_columns: Optional[bool] = None

    def log(self, entry: AuditEntry, db_session=None) -> None:
        """
        Write an audit entry to the database and structured log.

        Gracefully handles missing extended columns by falling back
        to base columns only.
        """
        # Always emit structured log (for log aggregation: DataDog, CloudWatch, etc.)
        self._emit_structured_log(entry)

        # Write to database if session is available
        if db_session is not None:
            self._write_to_db(entry, db_session)

    def _emit_structured_log(self, entry: AuditEntry) -> None:
        """Emit structured log entry for monitoring systems."""
        logger.info(
            f"[AUDIT] request_id={entry.request_id} "
            f"user={entry.user_id} org={entry.organization_id} "
            f"intent={entry.intent} "
            f"tools={','.join(entry.tools_called)} "
            f"tokens={entry.tokens_input + entry.tokens_output} "
            f"time_ms={entry.processing_time_ms:.0f} "
            f"quality={entry.data_quality} "
            f"errors={len(entry.errors)}"
        )

    def _write_to_db(self, entry: AuditEntry, db_session) -> None:
        """Write audit entry to ai_audit_log table."""
        try:
            from sqlalchemy import text as sa_text
            import json

            # Try extended insert first, fall back to base
            if self._has_extended_columns is not False:
                try:
                    db_session.execute(sa_text("""
                        INSERT INTO ai_audit_log
                            (action_type, input_summary, output_summary,
                             user_id, organization_id, model_used, tokens_used,
                             request_id, tools_used, actions_taken,
                             processing_time_ms, data_quality, errors,
                             created_at)
                        VALUES (:action, :input, :output,
                                :user_id, :org_id, :model, :tokens,
                                :request_id, :tools_json, :actions_json,
                                :processing_ms, :data_quality, :errors_json,
                                NOW())
                    """), entry.to_db_params())
                    db_session.flush()
                    self._has_extended_columns = True
                    return
                except Exception:
                    if self._has_extended_columns is None:
                        self._has_extended_columns = False
                        logger.info("[AUDIT] Extended columns not found, using base schema")

            # Fallback to base columns
            params = entry.to_db_params()
            db_session.execute(sa_text("""
                INSERT INTO ai_audit_log
                    (action_type, input_summary, output_summary, user_id,
                     organization_id, model_used, tokens_used, created_at)
                VALUES (:action, :input, :output, :user_id,
                        :org_id, :model, :tokens, NOW())
            """), params)
            db_session.flush()

        except Exception as audit_err:
            logger.error(f"[AUDIT] Failed to write audit log: {audit_err}")
            self._write_dead_letter(entry)

    @staticmethod
    def _write_dead_letter(entry: AuditEntry) -> None:
        """Fallback: write failed audit entry to a local file for later recovery."""
        try:
            import json
            dead_letter_path = os.path.join(
                os.getenv("AUDIT_DEAD_LETTER_DIR", "/tmp"),
                "audit_dead_letter.jsonl",
            )
            record = {
                "request_id": entry.request_id,
                "user_id": entry.user_id,
                "org_id": entry.organization_id,
                "intent": entry.intent,
                "timestamp": entry.timestamp.isoformat(),
                "tokens": entry.tokens_input + entry.tokens_output,
                "model": entry.model_used,
            }
            with open(dead_letter_path, "a") as f:
                f.write(json.dumps(record) + "\n")
            logger.info(f"[AUDIT] Dead-letter written to {dead_letter_path}")
        except Exception as dl_err:
            logger.critical(f"[AUDIT] Dead-letter write ALSO failed: {dl_err}")

    @staticmethod
    def extract_token_usage(llm_response: Any) -> tuple:
        """
        Extract input/output token counts from an Anthropic API response.

        Returns (input_tokens, output_tokens).
        """
        try:
            if hasattr(llm_response, 'usage'):
                usage = llm_response.usage
                return (
                    getattr(usage, 'input_tokens', 0),
                    getattr(usage, 'output_tokens', 0),
                )
            if isinstance(llm_response, dict) and 'usage' in llm_response:
                usage = llm_response['usage']
                return (
                    usage.get('input_tokens', 0),
                    usage.get('output_tokens', 0),
                )
        except Exception:
            pass
        return 0, 0


# Singleton
_audit_logger: Optional[AuditLogger] = None


def get_audit_logger() -> AuditLogger:
    """Get the singleton AuditLogger instance."""
    global _audit_logger
    if _audit_logger is None:
        _audit_logger = AuditLogger()
    return _audit_logger
