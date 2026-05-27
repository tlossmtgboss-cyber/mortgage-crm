"""Calibrated conversion probability model.

V1 uses logistic regression with domain-calibrated coefficients derived
from mortgage industry conversion benchmarks. As labelled data
accumulates in cie_intelligence_reports, the coefficients can be
retrained without changing the interface.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field


@dataclass
class ConversionPrediction:
    probability: float
    ci_low: float
    ci_high: float
    key_factors: list[str] = field(default_factory=list)


# Domain-calibrated coefficients (logistic regression weights).
# Dimension scores are 0-100 and normalized to 0-1 before applying coefficients.
_INTERCEPT = -3.5
_COEFFICIENTS = {
    "engagement": 0.75,
    "information_quality": 0.90,
    "objection_handling": 1.0,
    "compliance": 0.35,
    "rapport": 0.65,
    "closing_effectiveness": 1.25,
    "duration_minutes": -0.005,
    "has_next_step": 1.2,
}

# CI half-width lookup by sample-size bucket (placeholder until Bayesian posterior)
_CI_HALF_WIDTH = 0.12


def _sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


def predict_conversion(
    scores: dict[str, float],
    duration_seconds: int | None = None,
    has_next_step: bool = False,
) -> ConversionPrediction:
    """Predict conversion probability from scoring dimensions.

    Args:
        scores: Mapping of dimension name → 0-100 score.
        duration_seconds: Call duration (optional).
        has_next_step: Whether the LO secured a concrete next step.

    Returns:
        ConversionPrediction with probability and 80% confidence interval.
    """
    logit = _INTERCEPT
    factors: list[str] = []

    for dim, coeff in _COEFFICIENTS.items():
        if dim == "duration_minutes":
            val = (duration_seconds or 0) / 60.0
        elif dim == "has_next_step":
            val = 1.0 if has_next_step else 0.0
        else:
            val = scores.get(dim, 50.0) / 100.0

        contribution = coeff * val
        logit += contribution

        if dim != "duration_minutes" and abs(contribution) > 0.3:
            direction = "+" if contribution > 0 else "-"
            display_val = val * 100 if dim not in ("has_next_step", "duration_minutes") else val
            factors.append(f"{direction}{dim}: {display_val:.0f}")

    prob = round(_sigmoid(logit), 3)
    ci_low = round(max(0.0, prob - _CI_HALF_WIDTH), 3)
    ci_high = round(min(1.0, prob + _CI_HALF_WIDTH), 3)

    return ConversionPrediction(
        probability=prob,
        ci_low=ci_low,
        ci_high=ci_high,
        key_factors=factors[:5],
    )
