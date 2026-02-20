"""
Co-Reference Resolution Service

Implements Module 2.3 gap: resolves pronouns and implicit references
in conversation ("it", "that loan", "the borrower", "them").

This is the #1 broken behavior identified in the gap analysis.

Usage:
    from services.coreference_resolution_service import CoreferenceResolver
    resolver = CoreferenceResolver(session_entities)
    resolved = resolver.resolve("Can you check it?")
"""

import re
import logging
from typing import Optional, Dict, List, Any, Tuple
from datetime import datetime

logger = logging.getLogger(__name__)


# ============================================================================
# PRONOUN / IMPLICIT REFERENCE PATTERNS
# ============================================================================

# Module 2.2 — Implicit Reference mappings
PRONOUN_PATTERNS = {
    # Pronouns -> entity type preferences (ordered by priority)
    r'\bit\b': ["loan", "email", "document", "lead", "task"],
    r'\bthat\b': ["loan", "email", "document", "lead", "task"],
    r'\bthis\b': ["loan", "email", "document", "lead", "task"],
    r'\bthem\b': ["documents", "leads", "contacts"],
    r'\bthey\b': ["borrower", "partner", "team_member"],
    r'\bhe\b': ["borrower", "partner", "team_member"],
    r'\bshe\b': ["borrower", "partner", "team_member"],
}

# Noun phrase -> entity type mappings
NOUN_PHRASE_PATTERNS = {
    r'\bthe loan\b': "loan",
    r'\bthe file\b': "loan",
    r'\bthe borrower\b': "borrower",
    r'\bthe client\b': "borrower",
    r'\bthe lead\b': "lead",
    r'\bmy pipeline\b': "pipeline",
    r'\bthe document[s]?\b': "document",
    r'\bthe email\b': "email",
    r'\bthe rate\b': "rate",
    r'\bthe task\b': "task",
    r'\bthe partner\b': "partner",
    r'\bthe realtor\b': "partner",
    r'\bthe agent\b': "partner",
}

# Temporal reference patterns
TEMPORAL_PATTERNS = {
    r'\byesterday\b': "yesterday",
    r'\blast week\b': "last_week",
    r'\bthis week\b': "this_week",
    r'\blast month\b': "last_month",
    r'\bthis month\b': "this_month",
    r'\bbefore closing\b': "before_closing",
    r'\btoday\b': "today",
}


class CoreferenceResolver:
    """Resolves pronouns and implicit references in conversation messages.

    Uses conversation entity history to determine what "it", "that",
    "the loan" etc. refer to.

    Module 2.3 Rules:
        - If unambiguous -> Apply silently, do NOT ask
        - If ambiguous -> Return clarification request
        - Scan BACKWARD through conversation for most recent matching entity
    """

    def __init__(self, session_entities: Optional[List[Dict]] = None):
        """Initialize with entities from current conversation session.

        Args:
            session_entities: List of extracted entities ordered by recency (most recent first).
                Each entity: {"type": "loan", "id": 123, "value": "LOAN-456789", "mentioned_at": "..."}
        """
        self.entities = session_entities or []

    def resolve(self, message: str) -> Dict[str, Any]:
        """Resolve all references in a message.

        Returns:
            {
                "original": "Can you check it?",
                "resolved_references": [
                    {"text": "it", "resolved_to": {"type": "loan", "id": 123, "value": "LOAN-456789"}, "confidence": 0.95}
                ],
                "needs_clarification": False,
                "clarification_question": None,
                "temporal_references": [{"text": "yesterday", "resolved_to": "2026-02-19"}]
            }
        """
        resolved_refs = []
        needs_clarification = False
        clarification_question = None

        # 1. Check noun phrases first (more specific)
        for pattern, entity_type in NOUN_PHRASE_PATTERNS.items():
            matches = re.finditer(pattern, message, re.IGNORECASE)
            for match in matches:
                entity = self._find_most_recent_entity(entity_type)
                if entity:
                    resolved_refs.append({
                        "text": match.group(),
                        "position": match.start(),
                        "resolved_to": entity,
                        "confidence": 0.9,
                        "method": "noun_phrase",
                    })

        # 2. Check pronouns (less specific, more ambiguous)
        for pattern, type_preferences in PRONOUN_PATTERNS.items():
            matches = re.finditer(pattern, message, re.IGNORECASE)
            for match in matches:
                # Skip if already resolved by noun phrase at same position
                if any(r["position"] == match.start() for r in resolved_refs):
                    continue

                # Try each preferred type in order
                entity = None
                for pref_type in type_preferences:
                    entity = self._find_most_recent_entity(pref_type)
                    if entity:
                        break

                if entity:
                    # Check for ambiguity — multiple recent entities of different types
                    candidates = self._find_candidates(type_preferences)
                    if len(candidates) > 1 and candidates[0]["type"] != candidates[1]["type"]:
                        # Ambiguous — need clarification (Module 2.3)
                        needs_clarification = True
                        clarification_question = (
                            f"Just to make sure — are you referring to "
                            f"{candidates[0]['value']} ({candidates[0]['type']}) "
                            f"or {candidates[1]['value']} ({candidates[1]['type']})?"
                        )
                    else:
                        resolved_refs.append({
                            "text": match.group(),
                            "position": match.start(),
                            "resolved_to": entity,
                            "confidence": 0.85 if len(candidates) <= 1 else 0.6,
                            "method": "pronoun_resolution",
                        })

        # 3. Resolve temporal references
        temporal_refs = self._resolve_temporal(message)

        return {
            "original": message,
            "resolved_references": resolved_refs,
            "temporal_references": temporal_refs,
            "needs_clarification": needs_clarification,
            "clarification_question": clarification_question,
        }

    def add_entity(self, entity: Dict[str, Any]):
        """Add a new entity to the session context (most recent first)."""
        self.entities.insert(0, {
            "type": entity.get("type"),
            "id": entity.get("id"),
            "value": entity.get("value"),
            "table": entity.get("table"),
            "mentioned_at": datetime.now().isoformat(),
        })

    def _find_most_recent_entity(self, entity_type: str) -> Optional[Dict]:
        """Find the most recently mentioned entity of a given type.

        Module 2.3: Scan BACKWARD through conversation for most recent matching entity.
        """
        for entity in self.entities:
            if entity.get("type") == entity_type:
                return entity
        return None

    def _find_candidates(self, type_preferences: List[str]) -> List[Dict]:
        """Find all candidate entities matching any of the preferred types."""
        candidates = []
        seen_types = set()
        for entity in self.entities:
            etype = entity.get("type")
            if etype in type_preferences and etype not in seen_types:
                candidates.append(entity)
                seen_types.add(etype)
            if len(candidates) >= 3:
                break
        return candidates

    def _resolve_temporal(self, message: str) -> List[Dict]:
        """Resolve temporal references to date ranges."""
        from datetime import date, timedelta

        today = date.today()
        temporal_map = {
            "yesterday": (today - timedelta(days=1), today - timedelta(days=1)),
            "today": (today, today),
            "last_week": (today - timedelta(days=today.weekday() + 7), today - timedelta(days=today.weekday() + 1)),
            "this_week": (today - timedelta(days=today.weekday()), today),
            "last_month": None,  # Computed below
            "this_month": (today.replace(day=1), today),
        }

        # Compute last month
        first_of_month = today.replace(day=1)
        last_month_end = first_of_month - timedelta(days=1)
        last_month_start = last_month_end.replace(day=1)
        temporal_map["last_month"] = (last_month_start, last_month_end)

        results = []
        for pattern, key in TEMPORAL_PATTERNS.items():
            if re.search(pattern, message, re.IGNORECASE):
                date_range = temporal_map.get(key)
                if date_range:
                    results.append({
                        "text": key.replace("_", " "),
                        "resolved_to": {
                            "start": date_range[0].isoformat(),
                            "end": date_range[1].isoformat(),
                        },
                    })

        return results

    def resolve_modification_request(self, message: str) -> Optional[Dict]:
        """Handle 'make it more [adjective]' type requests.

        Module 2.3: Find most recent CONTENT the agent produced,
        apply modification to THAT content, do NOT start over.
        """
        mod_patterns = [
            r'make (?:it|this) (?:more |less )?(\w+)',
            r'(?:more|less) (\w+)',
            r'can you (?:make it|rewrite it to be) (?:more |less )?(\w+)',
        ]

        for pattern in mod_patterns:
            match = re.search(pattern, message, re.IGNORECASE)
            if match:
                modifier = match.group(1)
                return {
                    "type": "content_modification",
                    "modifier": modifier,
                    "action": "modify_last_output",
                    "instruction": f"Apply '{modifier}' modification to the most recent agent output",
                }

        return None
