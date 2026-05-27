"""CIE Scorers — 6 dimensions + composite CIS via a single LLM call.

Each dimension returns a 0–100 score with evidence. The composite
Call Intelligence Score (CIS) is a weighted average configured in
engine.config.CIESettings.SCORE_WEIGHTS.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any

from engine.config import cie_settings
from services.call_intelligence.pii_utils import redact_transcript_for_llm

logger = logging.getLogger(__name__)

SCORING_PROMPT = """\
You are a mortgage call quality analyst. Given the transcript below, score
the loan officer on six dimensions. For each dimension, return a score from
0-100 and a one-sentence evidence justification.

Dimensions:
1. **engagement** – Did the LO actively listen, ask clarifying questions, and
   keep the borrower engaged?
2. **information_quality** – Was the information shared accurate, complete,
   and relevant to the borrower's situation?
3. **objection_handling** – How effectively did the LO address hesitations,
   concerns, or objections?
4. **compliance** – Did the LO follow TRID, fair lending, consent, and
   regulatory disclosure requirements?
5. **rapport** – Did the LO build trust and a personal connection with the
   borrower?
6. **closing_effectiveness** – Did the LO guide the conversation toward a
   clear next step or commitment?

Return ONLY valid JSON with this exact schema:
{
  "engagement": {"score": <int 0-100>, "evidence": "<string>"},
  "information_quality": {"score": <int 0-100>, "evidence": "<string>"},
  "objection_handling": {"score": <int 0-100>, "evidence": "<string>"},
  "compliance": {"score": <int 0-100>, "evidence": "<string>"},
  "rapport": {"score": <int 0-100>, "evidence": "<string>"},
  "closing_effectiveness": {"score": <int 0-100>, "evidence": "<string>"}
}

TRANSCRIPT:
"""


@dataclass
class DimensionScore:
    name: str
    score: float
    evidence: str = ""


@dataclass
class ScoringResult:
    dimensions: list[DimensionScore] = field(default_factory=list)
    cis_composite: float = 0.0
    raw_response: str = ""
    error: str | None = None


def compute_composite(dimensions: list[DimensionScore]) -> float:
    """Weighted average using configured weights."""
    weights = cie_settings.SCORE_WEIGHTS
    total_weight = 0.0
    weighted_sum = 0.0
    for d in dimensions:
        w = weights.get(d.name, 0.0)
        weighted_sum += d.score * w
        total_weight += w
    if total_weight == 0:
        return 0.0
    return round(weighted_sum / total_weight, 1)


def parse_scoring_response(raw: str) -> list[DimensionScore]:
    """Parse the LLM's JSON response into DimensionScore objects."""
    data = json.loads(raw)
    dims: list[DimensionScore] = []
    for name in [
        "engagement", "information_quality", "objection_handling",
        "compliance", "rapport", "closing_effectiveness",
    ]:
        entry = data.get(name, {})
        score = float(entry.get("score", 0))
        evidence = str(entry.get("evidence", ""))
        dims.append(DimensionScore(name=name, score=max(0, min(100, score)), evidence=evidence))
    return dims


MAX_TRANSCRIPT_CHARS = 12_000


async def score_transcript(transcript: str, client: Any) -> ScoringResult:
    """Score a transcript using a single batched LLM call.

    Args:
        transcript: Full call transcript text.
        client: Anthropic AsyncAnthropic client instance.

    Returns:
        ScoringResult with 6 dimensions and composite CIS.
    """
    try:
        redacted, _pii_stats = redact_transcript_for_llm(transcript)
        redacted = redacted[:MAX_TRANSCRIPT_CHARS]
        response = await client.messages.create(
            model=cie_settings.PRIMARY_MODEL,
            max_tokens=1024,
            messages=[{"role": "user", "content": SCORING_PROMPT + redacted}],
        )
        raw = response.content[0].text

        # Strip markdown fences if present
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned[3:]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
        cleaned = cleaned.strip()

        dims = parse_scoring_response(cleaned)
        cis = compute_composite(dims)
        return ScoringResult(dimensions=dims, cis_composite=cis, raw_response=raw)

    except Exception as e:
        logger.exception("CIE scoring failed")
        return ScoringResult(error=str(e), raw_response="")
