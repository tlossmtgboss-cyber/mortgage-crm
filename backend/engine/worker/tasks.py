"""Celery task for CIE call processing pipeline."""
from __future__ import annotations

import asyncio
import copy
import logging
import time

from tasks.celery_app import celery_app

logger = logging.getLogger(__name__)

_loop = None


def _get_loop() -> asyncio.AbstractEventLoop:
    global _loop
    if _loop is None or _loop.is_closed():
        _loop = asyncio.new_event_loop()
    return _loop


@celery_app.task(
    name="engine.worker.tasks.process_call_pipeline",
    queue="ai_tasks",
    rate_limit="30/m",
    soft_time_limit=120,
    time_limit=150,
    max_retries=3,
    default_retry_delay=30,
    acks_late=True,
)
def process_call_pipeline(call_record_id: str) -> dict:
    """Load a CIE call record, run the LangGraph pipeline, and persist the report."""
    return _get_loop().run_until_complete(_run(call_record_id))


async def _run(call_record_id: str) -> dict:
    from db import SessionLocal
    from engine.models import CIECallRecord, CIEIntelligenceReport
    from engine.cipher import decrypt_field
    from engine.pipeline import cie_pipeline

    start = time.monotonic()

    db = SessionLocal()
    try:
        record = db.query(CIECallRecord).filter(CIECallRecord.id == call_record_id).first()
        if not record:
            logger.error("CIE: call record %s not found", call_record_id)
            return {"error": "not_found"}

        if record.processing_status == "completed":
            return {"status": "already_completed"}

        record.processing_status = "processing"
        db.commit()

        try:
            # Decrypt transcript for pipeline
            transcript = ""
            if record.transcript_encrypted:
                transcript = decrypt_field(record.transcript_encrypted)

            # Build pipeline input
            pipeline_input = {
                "provider": record.provider,
                "raw_payload": copy.deepcopy(record.raw_payload or {}),
            }

            # If transcript was encrypted, inject it directly
            if transcript:
                pipeline_input["raw_payload"].setdefault("message", {})
                if "messages" not in pipeline_input["raw_payload"].get("message", {}):
                    pipeline_input["raw_payload"]["message"]["_cie_transcript"] = transcript

            result = await cie_pipeline.ainvoke(pipeline_input)

            report_data = result.get("report", {})
            processing_time_ms = int((time.monotonic() - start) * 1000)

            # Persist intelligence report
            report = CIEIntelligenceReport(
                call_record_id=record.id,
                organization_id=record.organization_id,
                cis_composite=result.get("cis_composite"),
                primary_intent=result.get("primary_intent"),
                intent_confidence=result.get("intent_confidence"),
                conversion_probability=result.get("conversion_probability"),
                conversion_ci_low=result.get("conversion_ci_low"),
                conversion_ci_high=result.get("conversion_ci_high"),
                summary=result.get("summary"),
                summary_bullets=result.get("summary_bullets"),
                opportunities=report_data.get("opportunities"),
                risks=report_data.get("risks"),
                objections=report_data.get("objections"),
                compliance_flags=result.get("compliance_flags"),
                coaching_suggestions=report_data.get("coaching_suggestions"),
                generated_tasks=report_data.get("generated_tasks"),
                draft_messages=report_data.get("draft_messages"),
                llm_model_used=result.get("llm_model_used"),
                pipeline_version=result.get("pipeline_version"),
                processing_time_ms=processing_time_ms,
            )

            # Extract individual scores from score_details
            for detail in result.get("score_details", []):
                name = detail.get("name", "")
                score = detail.get("score")
                col_map = {
                    "engagement": "engagement_score",
                    "information_quality": "information_quality_score",
                    "objection_handling": "objection_handling_score",
                    "compliance": "compliance_score",
                    "rapport": "rapport_score",
                    "closing_effectiveness": "closing_effectiveness_score",
                }
                col = col_map.get(name)
                if col and score is not None:
                    setattr(report, col, float(score))

            db.add(report)
            record.processing_status = "completed"
            db.commit()

            logger.info(
                "CIE: pipeline completed for %s in %dms — CIS=%.1f",
                call_record_id, processing_time_ms, result.get("cis_composite", 0),
            )
            return {
                "status": "completed",
                "report_id": str(report.id),
                "processing_time_ms": processing_time_ms,
            }

        except Exception as e:
            logger.exception("CIE: pipeline failed for %s", call_record_id)
            record.processing_status = "failed"
            record.processing_error = str(e)[:500]
            db.commit()
            raise
    finally:
        db.close()
