"""
Exclusion List Checker

Filters extracted items against the exclusion rules table.
Protected classes, emotional inferences, unverified financials,
proxy inference rules. Updated without a deploy via DB.
"""

import logging
from typing import Any, Dict, List, Optional
from sqlalchemy.orm import Session

logger = logging.getLogger("aria.exclusion")


class ExclusionResult:
    def __init__(self, excluded: bool, category: Optional[str] = None,
                 transformation: Optional[str] = None):
        self.excluded = excluded
        self.category = category
        self.transformation = transformation


class ExclusionChecker:
    def __init__(self, db: Session):
        self._db = db
        self._rules: Optional[List[Dict[str, Any]]] = None

    def _load_rules(self):
        if self._rules is not None:
            return
        from database.models.memory_topic_config import MemoryExclusionRule
        rows = (
            self._db.query(MemoryExclusionRule)
            .filter(MemoryExclusionRule.active == True)
            .all()
        )
        self._rules = [
            {
                "category": r.category,
                "pattern": r.pattern,
                "transformation": r.transformation,
            }
            for r in rows
        ]

    def get_exclusion_prompt_section(self) -> str:
        self._load_rules()
        lines = ["EXCLUSION RULES — reject any extracted item matching these categories:"]
        for rule in self._rules:
            line = f"- [{rule['category']}]: {rule['pattern']}"
            if rule["transformation"]:
                line += f" EXCEPTION: {rule['transformation']}"
            lines.append(line)
        return "\n".join(lines)

    def check(self, fact_text: str, fact_type: str, topic: str) -> ExclusionResult:
        self._load_rules()
        text_lower = fact_text.lower()

        for rule in self._rules:
            keywords = self._extract_keywords(rule["pattern"])
            if any(kw in text_lower for kw in keywords):
                if rule["transformation"]:
                    return ExclusionResult(
                        excluded=False,
                        category=rule["category"],
                        transformation=rule["transformation"],
                    )
                return ExclusionResult(excluded=True, category=rule["category"])

        return ExclusionResult(excluded=False)

    def _extract_keywords(self, pattern: str) -> list[str]:
        keywords = []
        for word in pattern.lower().replace(",", " ").split():
            word = word.strip(".:;()\"'")
            if len(word) >= 4 and word not in (
                "such", "that", "this", "with", "from", "about",
                "route", "instead", "inferences", "explicitly",
                "without", "statement", "described", "borrower",
            ):
                keywords.append(word)
        return keywords
