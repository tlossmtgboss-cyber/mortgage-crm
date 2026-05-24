"""
Guideline Chart Service

Aggregates structured_rules across UnderwritingGuideline records
to produce comparison chart data for the 25 chart categories.
"""

import json
import logging
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# -------------------------------------------------------------------------
# Chart catalog — the 25 comparison chart categories
# -------------------------------------------------------------------------

CHART_CATALOG: List[Dict] = [
    {"id": "program_eligibility", "name": "Program Eligibility Matrix", "tag": "Master Chart"},
    {"id": "credit_score", "name": "Credit Score Matrix", "tag": "AI Pre-Underwriting"},
    {"id": "dti", "name": "DTI Matrix", "tag": "Most-Used"},
    {"id": "ltv", "name": "Down Payment / LTV Matrix", "tag": None},
    {"id": "occupancy", "name": "Occupancy Matrix", "tag": None},
    {"id": "property_type", "name": "Property Type Matrix", "tag": "AI Eligibility"},
    {"id": "self_employment", "name": "Self-Employment Matrix", "tag": "High Complexity"},
    {"id": "income_type", "name": "Income Type Matrix", "tag": "Foundational"},
    {"id": "asset_documentation", "name": "Asset Documentation Matrix", "tag": None},
    {"id": "reserve_requirements", "name": "Reserve Requirement Matrix", "tag": None},
    {"id": "gift_funds", "name": "Gift Fund Matrix", "tag": "High Ops Value"},
    {"id": "credit_event_waiting", "name": "Credit Event Waiting Period Matrix", "tag": None},
    {"id": "condo", "name": "Condo Matrix", "tag": "Critical"},
    {"id": "manual_underwrite", "name": "Manual Underwrite Matrix", "tag": None},
    {"id": "aus_findings", "name": "AUS Findings Comparison", "tag": "AI Gold"},
    {"id": "investor_overlay", "name": "Investor Overlay Matrix", "tag": "Pricing Engine"},
    {"id": "document_requirements", "name": "Document Requirement Matrix", "tag": "Smart Docs"},
    {"id": "condition_library", "name": "Condition Library Matrix", "tag": "Massive Value"},
    {"id": "appraisal", "name": "Appraisal Requirement Matrix", "tag": None},
    {"id": "escrow_insurance", "name": "Escrow / Insurance / Tax Matrix", "tag": "Coastal Markets"},
    {"id": "non_qm", "name": "Non-QM Matrix", "tag": "Separate Paradigm"},
    {"id": "ai_risk_flags", "name": "AI Risk Flag Matrix", "tag": "Differentiator"},
    {"id": "borrower_strategy", "name": "Borrower Strategy Comparison", "tag": "Beats Every LOS"},
    {"id": "decision_trees", "name": "Underwriter Decision Tree Charts", "tag": "AI Orchestration"},
    {"id": "edge_cases", "name": "Loan Scenario Edge-Case Charts", "tag": "Enterprise Value"},
]

# Quick lookup by chart ID
_CATALOG_BY_ID: Dict[str, Dict] = {c["id"]: c for c in CHART_CATALOG}


class GuidelineChartService:
    """
    Aggregates structured_rules across guidelines for comparison chart data.
    """

    def __init__(self, db: Session, redis=None):
        self._db = db
        self._redis = redis

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_chart_catalog(self) -> List[Dict]:
        """Return the static list of all 25 chart categories."""
        return list(CHART_CATALOG)

    async def get_comparison(self, topic: str, tenant_id: int) -> Dict:
        """
        Aggregate structured_rules for a specific chart topic across all
        active guidelines belonging to the given tenant.

        Returns a dict with topic metadata and a list of program entries
        sorted by overlay_priority (company overlays first).
        """
        # Resolve topic name from catalog
        catalog_entry = _CATALOG_BY_ID.get(topic)
        topic_name = catalog_entry["name"] if catalog_entry else topic

        # --- Redis cache check ---
        cache_key = f"guideline:chart:{tenant_id}:{topic}"
        if self._redis is not None:
            try:
                cached = await self._redis.get(cache_key)
                if cached is not None:
                    return json.loads(cached)
            except Exception:
                logger.warning("Redis cache read failed for %s", cache_key, exc_info=True)

        # --- Query guidelines ---
        from models.call_monitoring_models import UnderwritingGuideline

        from sqlalchemy import or_ as _or

        guidelines = (
            self._db.query(UnderwritingGuideline)
            .filter(
                UnderwritingGuideline.is_active.is_(True),
                UnderwritingGuideline.structured_rules.isnot(None),
                _or(UnderwritingGuideline.organization_id == None, UnderwritingGuideline.organization_id == tenant_id),
            )
            .all()
        )

        programs = []
        for g in guidelines:
            rules = g.structured_rules or {}
            chart_data = rules.get("chart_data")
            if not isinstance(chart_data, dict):
                continue

            topic_data = chart_data.get(topic)
            if topic_data is None:
                continue

            programs.append(
                {
                    "program": g.loan_program,
                    "guideline_name": g.name,
                    "guideline_type": g.guideline_type,
                    "overlay_priority": g.overlay_priority or 4,
                    "data": topic_data,
                }
            )

        # Sort by overlay_priority ascending (company = 1 first, agency = 4 last)
        programs.sort(key=lambda p: p["overlay_priority"])

        result = {
            "topic": topic,
            "topic_name": topic_name,
            "programs": programs,
        }

        # --- Redis cache write ---
        if self._redis is not None:
            try:
                await self._redis.set(cache_key, json.dumps(result), ex=3600)
            except Exception:
                logger.warning("Redis cache write failed for %s", cache_key, exc_info=True)

        return result
