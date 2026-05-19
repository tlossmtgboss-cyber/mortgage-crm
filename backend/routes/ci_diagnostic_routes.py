"""
Call Intelligence Diagnostic Routes

Admin-only endpoints for testing the CI pipeline end-to-end.
Requires X-API-Key header (CSRF-exempt) for access.
"""

import logging
import os
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import AsyncSession

from db import get_async_db

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/ci-diagnostic",
    tags=["call-intelligence", "diagnostic"],
)

ADMIN_API_KEY = os.getenv("ADMIN_API_KEY", "")


def _require_admin(x_api_key: str = Header(None)):
    if not ADMIN_API_KEY or x_api_key != ADMIN_API_KEY:
        raise HTTPException(status_code=403, detail="Admin access required")


class TranscribeTestRequest(BaseModel):
    recording_url: str = Field(..., description="URL to an audio file (mp3, wav, etc.)")
    organization_id: int = Field(..., description="Org ID for CI processing")
    loan_id: Optional[int] = Field(None, description="Loan ID (optional)")
    call_id: Optional[str] = Field(None, description="Call ID override (auto-generated if omitted)")


class TranscriptTestRequest(BaseModel):
    transcript: str = Field(..., description="Raw transcript text to process")
    organization_id: int = Field(..., description="Org ID for CI processing")
    loan_id: Optional[int] = Field(None, description="Loan ID (optional)")
    call_id: Optional[str] = Field(None, description="Call ID override (auto-generated if omitted)")


class PipelineStatusResponse(BaseModel):
    deepgram_available: bool
    whisper_available: bool
    ci_import_ok: bool
    ci_llm_provider: str
    mistral_key_set: bool
    anthropic_key_set: bool
    openai_key_set: bool


@router.get("/status", dependencies=[Depends(_require_admin)])
async def ci_pipeline_status() -> PipelineStatusResponse:
    """Check whether all CI pipeline dependencies are available."""
    from services.media.transcription_service import (
        TranscriptionService,
        WhisperTranscriptionService,
    )

    deepgram = TranscriptionService()
    whisper = WhisperTranscriptionService()

    ci_ok = False
    try:
        from services.call_intelligence.integration import CallIntelligenceIntegration
        ci_ok = True
    except ImportError:
        pass

    return PipelineStatusResponse(
        deepgram_available=deepgram.enabled,
        whisper_available=whisper.enabled,
        ci_import_ok=ci_ok,
        ci_llm_provider=os.getenv("CI_LLM_PROVIDER", "anthropic"),
        mistral_key_set=bool(os.getenv("MISTRAL_API_KEY")),
        anthropic_key_set=bool(os.getenv("ANTHROPIC_API_KEY")),
        openai_key_set=bool(os.getenv("OPENAI_API_KEY")),
    )


@router.post("/transcribe-test", dependencies=[Depends(_require_admin)])
async def transcribe_test(
    body: TranscribeTestRequest,
    db: AsyncSession = Depends(get_async_db),
):
    """Transcribe a recording URL and run CI extraction.

    This is the same flow as the Telnyx recording handler but triggered
    manually for testing. Returns the full result synchronously.
    """
    import uuid
    from services.media.transcription_service import (
        get_transcription_service,
        TranscriptionService,
    )

    svc = get_transcription_service()
    if svc is None:
        raise HTTPException(
            status_code=503,
            detail="No transcription service available (set DEEPGRAM_API_KEY or OPENAI_API_KEY)",
        )

    # Step 1: Transcribe
    try:
        if isinstance(svc, TranscriptionService):
            transcript_result = svc.transcribe_url(body.recording_url)
        else:
            import tempfile
            import httpx

            async with httpx.AsyncClient(timeout=120) as client:
                resp = await client.get(body.recording_url)
                resp.raise_for_status()

            with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
                tmp.write(resp.content)
                tmp_path = tmp.name

            try:
                transcript_result = svc.transcribe_file(tmp_path)
            finally:
                import os as _os
                try:
                    _os.unlink(tmp_path)
                except OSError:
                    pass
    except Exception as e:
        logger.exception("Transcription failed: %s", e)
        return {
            "success": False,
            "stage": "transcription",
            "error": str(e),
        }

    full_text = transcript_result.get("full_text", "").strip()
    if not full_text:
        return {
            "success": False,
            "stage": "transcription",
            "error": "Transcription returned empty text",
            "raw": transcript_result,
        }

    # Step 2: Run CI extraction
    call_id = body.call_id or f"diag-{uuid.uuid4().hex[:12]}"

    try:
        from services.call_intelligence.integration import CallIntelligenceIntegration

        integration = CallIntelligenceIntegration(db)
        ci_result = await integration.process_completed_call(
            call_id=call_id,
            loan_id=body.loan_id,
            organization_id=body.organization_id,
            transcript=full_text,
            call_type="diagnostic_test",
            call_metadata={
                "source": "ci_diagnostic",
                "recording_url": body.recording_url,
                "word_count": transcript_result.get("word_count", 0),
                "confidence": transcript_result.get("confidence", 0.0),
            },
        )
    except Exception as e:
        logger.exception("CI processing failed: %s", e)
        return {
            "success": False,
            "stage": "ci_processing",
            "error": str(e),
            "transcript_preview": full_text[:500],
            "word_count": transcript_result.get("word_count", 0),
        }

    return {
        "success": ci_result.get("success", False),
        "call_id": call_id,
        "transcript_preview": full_text[:500],
        "word_count": transcript_result.get("word_count", 0),
        "transcript_confidence": transcript_result.get("confidence", 0.0),
        "speakers_detected": transcript_result.get("speakers_detected", 0),
        "ci_result": ci_result,
    }


@router.post("/extract-test", dependencies=[Depends(_require_admin)])
async def extract_test(
    body: TranscriptTestRequest,
    db: AsyncSession = Depends(get_async_db),
):
    """Run CI extraction on raw transcript text (skips transcription).

    Use this to test the Mistral extraction pipeline with sample
    mortgage conversation text when no real recordings are available.
    """
    import uuid

    if not body.transcript.strip():
        return {"success": False, "error": "Empty transcript"}

    call_id = body.call_id or f"diag-{uuid.uuid4().hex[:12]}"
    word_count = len(body.transcript.split())

    try:
        from services.call_intelligence.integration import CallIntelligenceIntegration

        integration = CallIntelligenceIntegration(db)
        ci_result = await integration.process_completed_call(
            call_id=call_id,
            loan_id=body.loan_id,
            organization_id=body.organization_id,
            transcript=body.transcript,
            call_type="diagnostic_test",
            call_metadata={"source": "ci_diagnostic_extract_test"},
        )
    except Exception as e:
        logger.exception("CI extraction failed: %s", e)
        return {
            "success": False,
            "stage": "ci_processing",
            "error": str(e),
            "word_count": word_count,
        }

    return {
        "success": ci_result.get("success", False),
        "call_id": call_id,
        "word_count": word_count,
        "ci_result": ci_result,
    }
