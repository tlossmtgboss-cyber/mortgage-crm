"""CIE LangGraph pipeline — the core processing graph.

Nodes:
    normalize  → provider adapter turns raw payload into NormalizedCall
    extract    → delegates to existing UnifiedExtractionEngine
    score      → 6-dimension scoring via single batched LLM call
    compliance → evaluates TRID, fair lending, consent flags
    actions    → generates tasks + draft messages
    assemble   → combines everything into the final report row

The compiled graph is exported as `cie_pipeline`.
"""
from __future__ import annotations

import json
import logging
import os
import time
from typing import Any, TypedDict

from langgraph.graph import END, StateGraph

from engine.config import cie_settings
from engine.sources import get_adapter
from engine.sources.base import NormalizedCall
from services.call_intelligence.pii_utils import redact_transcript_for_llm
from engine.scorers import (
    DimensionScore,
    ScoringResult,
    score_transcript,
)
from engine.conversion import ConversionPrediction, predict_conversion

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Pipeline state
# ---------------------------------------------------------------------------

class CIEPipelineState(TypedDict, total=False):
    # Input
    provider: str
    raw_payload: dict[str, Any]

    # After normalize
    normalized: dict[str, Any]
    transcript: str
    messages: list[dict[str, str]]
    duration_seconds: int | None

    # After extract
    extraction: dict[str, Any]

    # After score
    scores: dict[str, float]
    score_details: list[dict[str, Any]]
    cis_composite: float

    # After compliance
    compliance_flags: list[dict[str, Any]]

    # After actions
    summary: str
    summary_bullets: list[str]
    opportunities: list[dict[str, Any]]
    risks: list[dict[str, Any]]
    objections: list[dict[str, Any]]
    coaching_suggestions: list[dict[str, Any]]
    generated_tasks: list[dict[str, Any]]
    draft_messages: list[dict[str, Any]]

    # After conversion
    conversion_probability: float
    conversion_ci_low: float
    conversion_ci_high: float

    # After assemble
    primary_intent: str
    intent_confidence: float
    report: dict[str, Any]

    # Metadata
    llm_model_used: str
    pipeline_version: str
    processing_time_ms: int
    error: str | None


# ---------------------------------------------------------------------------
# Node implementations
# ---------------------------------------------------------------------------

def _get_anthropic_client():
    import anthropic
    return anthropic.AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))


async def normalize_node(state: CIEPipelineState) -> CIEPipelineState:
    adapter = get_adapter(state["provider"])
    nc: NormalizedCall = adapter.normalize(state["raw_payload"])
    return {
        "normalized": {
            "external_call_id": nc.external_call_id,
            "provider": nc.provider,
            "direction": nc.direction,
            "phone_from": nc.phone_from,
            "phone_to": nc.phone_to,
            "started_at": nc.started_at.isoformat() if nc.started_at else None,
            "ended_at": nc.ended_at.isoformat() if nc.ended_at else None,
            "duration_seconds": nc.duration_seconds,
            "recording_url": nc.recording_url,
        },
        "transcript": nc.transcript or "",
        "messages": nc.messages,
        "duration_seconds": nc.duration_seconds,
    }


async def extract_node(state: CIEPipelineState) -> CIEPipelineState:
    """Delegate to the existing UnifiedExtractionEngine for data extraction."""
    transcript = state.get("transcript", "")
    if not transcript:
        return {"extraction": {}}

    try:
        from services.call_intelligence.unified_extractor import (
            UnifiedExtractionEngine,
        )
        from services.call_intelligence.llm_client import AnthropicClient

        client = AnthropicClient()
        engine = UnifiedExtractionEngine(client)
        result = await engine.extract(transcript, call_id="cie-pipeline")
        return {
            "extraction": {
                "total": result.total_extractions,
                "high_confidence": result.high_confidence_count,
                "identity": {k: {"value": v.value, "confidence": v.confidence} for k, v in result.identity.items()},
                "property": {k: {"value": v.value, "confidence": v.confidence} for k, v in result.property_info.items()},
                "financial": {k: {"value": v.value, "confidence": v.confidence} for k, v in result.financial.items()},
                "intent": {k: {"value": v.value, "confidence": v.confidence} for k, v in result.intent.items()},
            },
        }
    except Exception as e:
        logger.exception("CIE extract node failed")
        return {"extraction": {"error": str(e)}}


async def score_node(state: CIEPipelineState) -> CIEPipelineState:
    transcript = state.get("transcript", "")
    if not transcript:
        return {"scores": {}, "score_details": [], "cis_composite": 0.0}

    client = _get_anthropic_client()
    result: ScoringResult = await score_transcript(transcript, client)

    if result.error:
        logger.error("CIE scoring error: %s", result.error)
        return {"scores": {}, "score_details": [], "cis_composite": 0.0}

    scores = {d.name: d.score for d in result.dimensions}
    details = [{"name": d.name, "score": d.score, "evidence": d.evidence} for d in result.dimensions]
    return {
        "scores": scores,
        "score_details": details,
        "cis_composite": result.cis_composite,
    }


async def compliance_node(state: CIEPipelineState) -> CIEPipelineState:
    """Evaluate compliance flags — consent, TRID, fair lending."""
    transcript = state.get("transcript", "")
    flags: list[dict[str, Any]] = []

    # Recording consent check
    try:
        from services.call_intelligence.recording_consent import (
            detect_disclosure_in_transcript,
            requires_two_party_consent,
        )

        normalized = state.get("normalized", {})
        # Try to detect borrower state from extraction
        extraction = state.get("extraction", {})
        borrower_state = None
        prop = extraction.get("property", {})
        if isinstance(prop, dict):
            state_ext = prop.get("state", {})
            if isinstance(state_ext, dict):
                borrower_state = state_ext.get("value")

        needs_consent = requires_two_party_consent(borrower_state)
        disclosure_found = False
        if transcript:
            result = detect_disclosure_in_transcript(transcript[:3000])
            disclosure_found = result.get("detected", False)

        if needs_consent and not disclosure_found:
            flags.append({
                "type": "recording_consent",
                "severity": "high",
                "message": "Two-party consent state detected but no recording disclosure found in transcript",
                "state": borrower_state,
            })
        elif needs_consent and disclosure_found:
            flags.append({
                "type": "recording_consent",
                "severity": "pass",
                "message": "Recording disclosure detected in two-party consent state",
            })
    except Exception as e:
        logger.warning("CIE compliance consent check failed: %s", e)

    # TRID timing check (if rate/fee discussed)
    if transcript:
        trid_keywords = ["closing cost", "APR", "annual percentage", "loan estimate", "good faith"]
        mentioned = [k for k in trid_keywords if k.lower() in transcript.lower()]
        if mentioned:
            flags.append({
                "type": "trid_disclosure",
                "severity": "info",
                "message": f"TRID-related topics discussed: {', '.join(mentioned)}",
                "keywords": mentioned,
            })

    # Fair lending check — flag if protected-class language detected
    fair_lending_terms = ["race", "religion", "national origin", "familial status", "handicap", "disability"]
    found_terms = [t for t in fair_lending_terms if t.lower() in transcript.lower()]
    if found_terms:
        flags.append({
            "type": "fair_lending",
            "severity": "warning",
            "message": f"Protected-class language detected: {', '.join(found_terms)}. Review for fair lending compliance.",
            "terms": found_terms,
        })

    return {"compliance_flags": flags}


async def actions_node(state: CIEPipelineState) -> CIEPipelineState:
    """Generate summary, opportunities, risks, coaching, tasks, and draft messages."""
    transcript = state.get("transcript", "")
    if not transcript:
        return {
            "summary": "",
            "summary_bullets": [],
            "opportunities": [],
            "risks": [],
            "objections": [],
            "coaching_suggestions": [],
            "generated_tasks": [],
            "draft_messages": [],
        }

    client = _get_anthropic_client()
    redacted, _pii_stats = redact_transcript_for_llm(transcript)

    prompt = f"""\
Analyze this mortgage call transcript and return a JSON object with ALL of the
following keys. Return ONLY valid JSON, no markdown fences.

{{
  "summary": "<2-3 sentence plain-text summary>",
  "summary_bullets": ["<bullet 1>", "<bullet 2>", ...],
  "primary_intent": "<one of: purchase_inquiry, refinance, preapproval, rate_check, status_update, document_followup, general_inquiry, complaint>",
  "intent_confidence": <float 0.0-1.0>,
  "opportunities": [{{"label": "...", "description": "...", "priority": "high|medium|low"}}],
  "risks": [{{"label": "...", "description": "...", "severity": "high|medium|low"}}],
  "objections": [{{"objection": "...", "lo_response": "...", "effectiveness": "strong|adequate|weak"}}],
  "coaching_suggestions": [{{"area": "...", "suggestion": "...", "example": "..."}}],
  "generated_tasks": [{{"title": "...", "owner": "lo|borrower", "priority": "high|medium|low", "due_days": <1-30>}}],
  "draft_messages": [{{"channel": "sms|email", "recipient": "borrower", "body": "..."}}]
}}

TRANSCRIPT:
{redacted[:12000]}"""

    try:
        from agents.anthropic_client import cached_system_block
        response = await client.messages.create(
            model=cie_settings.PRIMARY_MODEL,
            max_tokens=2048,
            messages=[{"role": "user", "content": prompt}],
            system=cached_system_block("You are a mortgage call analyst. Extract structured insights. Return valid JSON only."),
        )
        raw = response.content[0].text.strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1] if "\n" in raw else raw[3:]
        if raw.endswith("```"):
            raw = raw[:-3]
        raw = raw.strip()

        data = json.loads(raw)
        return {
            "summary": data.get("summary", ""),
            "summary_bullets": data.get("summary_bullets", []),
            "primary_intent": data.get("primary_intent", "general_inquiry"),
            "intent_confidence": float(data.get("intent_confidence", 0.5)),
            "opportunities": data.get("opportunities", []),
            "risks": data.get("risks", []),
            "objections": data.get("objections", []),
            "coaching_suggestions": data.get("coaching_suggestions", []),
            "generated_tasks": data.get("generated_tasks", []),
            "draft_messages": data.get("draft_messages", []),
        }
    except Exception as e:
        logger.exception("CIE actions node failed")
        return {
            "summary": f"[Analysis failed: {type(e).__name__}]",
            "summary_bullets": [],
            "opportunities": [],
            "risks": [],
            "objections": [],
            "coaching_suggestions": [],
            "generated_tasks": [],
            "draft_messages": [],
        }


async def assemble_node(state: CIEPipelineState) -> CIEPipelineState:
    """Combine all upstream results into the final report dict and compute conversion."""
    scores = state.get("scores", {})
    duration = state.get("duration_seconds")

    has_next_step = bool(state.get("generated_tasks"))
    conv = predict_conversion(
        scores=scores,
        duration_seconds=duration,
        has_next_step=has_next_step,
    )

    report = {
        "cis_composite": state.get("cis_composite", 0.0),
        "scores": state.get("score_details", []),
        "summary": state.get("summary", ""),
        "summary_bullets": state.get("summary_bullets", []),
        "primary_intent": state.get("primary_intent", ""),
        "intent_confidence": state.get("intent_confidence", 0.0),
        "conversion_probability": conv.probability,
        "conversion_ci_low": conv.ci_low,
        "conversion_ci_high": conv.ci_high,
        "conversion_factors": conv.key_factors,
        "opportunities": state.get("opportunities", []),
        "risks": state.get("risks", []),
        "objections": state.get("objections", []),
        "compliance_flags": state.get("compliance_flags", []),
        "coaching_suggestions": state.get("coaching_suggestions", []),
        "generated_tasks": state.get("generated_tasks", []),
        "draft_messages": state.get("draft_messages", []),
        "extraction": state.get("extraction", {}),
    }

    return {
        "conversion_probability": conv.probability,
        "conversion_ci_low": conv.ci_low,
        "conversion_ci_high": conv.ci_high,
        "report": report,
        "llm_model_used": cie_settings.PRIMARY_MODEL,
        "pipeline_version": "1.0.0",
    }


# ---------------------------------------------------------------------------
# Graph construction
# ---------------------------------------------------------------------------

def build_pipeline() -> StateGraph:
    g = StateGraph(CIEPipelineState)
    g.add_node("normalize", normalize_node)
    g.add_node("extract", extract_node)
    g.add_node("score", score_node)
    g.add_node("compliance", compliance_node)
    g.add_node("actions", actions_node)
    g.add_node("assemble", assemble_node)

    g.set_entry_point("normalize")
    g.add_edge("normalize", "extract")
    g.add_edge("normalize", "score")
    g.add_edge("extract", "compliance")
    g.add_edge("score", "actions")
    g.add_edge("compliance", "assemble")
    g.add_edge("actions", "assemble")
    g.add_edge("assemble", END)
    return g


cie_pipeline = build_pipeline().compile()
