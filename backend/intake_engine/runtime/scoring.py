"""
Scoring Engine for Intake
Computes Underwriting Truth Score and LO Readiness Score
"""

import logging
from typing import Any, Dict, List, Optional, Tuple
from .models import (
    Session, Scores, ScoreBreakdown, TruthBand, Flag,
    FlagCategory, FlagSeverity
)

logger = logging.getLogger(__name__)


class ScoringResult:
    """Result of score computation"""
    def __init__(
        self,
        truth_score: float,
        truth_band: TruthBand,
        readiness_score: float,
        breakdown: ScoreBreakdown,
        flags: List[Flag] = None,
        penalties_applied: List[Dict] = None,
        bonuses_applied: List[Dict] = None,
    ):
        self.truth_score = truth_score
        self.truth_band = truth_band
        self.readiness_score = readiness_score
        self.breakdown = breakdown
        self.flags = flags or []
        self.penalties_applied = penalties_applied or []
        self.bonuses_applied = bonuses_applied or []


class ScoringEngine:
    """Computes underwriting truth score and LO readiness score"""

    def __init__(
        self,
        truth_config: Dict[str, Any],
        readiness_config: Dict[str, Any],
        questions: Dict[str, Any],
    ):
        self.truth_config = truth_config
        self.readiness_config = readiness_config
        self.questions = questions

        # Extract truth score components
        self.components = truth_config.get("components", {})
        self.penalties = truth_config.get("penalties", [])
        self.bonuses = truth_config.get("bonuses", [])
        self.severity_mapping = truth_config.get("severity_mapping", {})

        # Extract readiness config
        self.readiness_sections = readiness_config.get("section_weights", {})
        self.gating_rules = readiness_config.get("gating_rules", [])

    def compute_scores(
        self,
        session: Session,
        party_id: Optional[str] = None,
    ) -> ScoringResult:
        """Compute both truth and readiness scores"""
        # Compute truth score components
        breakdown = self._compute_breakdown(session, party_id)

        # Apply component weights
        base_score = self._compute_weighted_score(breakdown)

        # Apply penalties
        penalties_applied = []
        penalty_total = 0
        flags = []

        for penalty in self.penalties:
            if self._check_penalty_condition(penalty, session, party_id):
                deduct = penalty.get("deduct", 0)
                penalty_total += deduct
                penalties_applied.append({
                    "id": penalty.get("id"),
                    "description": penalty.get("description"),
                    "deducted": deduct,
                })
                # Add flags if specified
                for flag_code in penalty.get("add_flags", []):
                    flags.append(Flag(
                        code=flag_code,
                        category=FlagCategory.TRUTH,
                        severity=FlagSeverity(penalty.get("severity", "warn")),
                        triggered_by=penalty.get("id"),
                    ))

        # Apply bonuses
        bonuses_applied = []
        bonus_total = 0

        for bonus in self.bonuses:
            if self._check_bonus_condition(bonus, session, party_id):
                add = bonus.get("add", 0)
                bonus_total += add
                bonuses_applied.append({
                    "id": bonus.get("id"),
                    "description": bonus.get("description"),
                    "added": add,
                })

        # Calculate final truth score
        truth_score = max(0, min(100, base_score - penalty_total + bonus_total))

        # Determine truth band
        truth_band = self._determine_truth_band(truth_score)

        # Compute readiness score
        readiness_score = self._compute_readiness_score(session, party_id)

        return ScoringResult(
            truth_score=round(truth_score, 1),
            truth_band=truth_band,
            readiness_score=round(readiness_score, 1),
            breakdown=breakdown,
            flags=flags,
            penalties_applied=penalties_applied,
            bonuses_applied=bonuses_applied,
        )

    def _compute_breakdown(
        self,
        session: Session,
        party_id: Optional[str] = None,
    ) -> ScoreBreakdown:
        """Compute individual score components"""
        breakdown = ScoreBreakdown()

        # Completeness (35%)
        breakdown.completeness = self._compute_completeness(session, party_id)

        # Internal Consistency (30%)
        breakdown.internal_consistency = self._compute_consistency(session, party_id)

        # Evidence Alignment (25%)
        breakdown.evidence_alignment = self._compute_evidence_alignment(session, party_id)

        # Behavioral Confidence (10%)
        breakdown.behavioral_confidence = self._compute_behavioral_confidence(session)

        return breakdown

    def _compute_weighted_score(self, breakdown: ScoreBreakdown) -> float:
        """Apply component weights to get base score"""
        weights = {
            "completeness": self.components.get("completeness", {}).get("weight", 0.35),
            "internal_consistency": self.components.get("internal_consistency", {}).get("weight", 0.30),
            "evidence_alignment": self.components.get("evidence_alignment", {}).get("weight", 0.25),
            "behavioral_confidence": self.components.get("behavioral_confidence", {}).get("weight", 0.10),
        }

        score = (
            breakdown.completeness * weights["completeness"] +
            breakdown.internal_consistency * weights["internal_consistency"] +
            breakdown.evidence_alignment * weights["evidence_alignment"] +
            breakdown.behavioral_confidence * weights["behavioral_confidence"]
        )

        return score * 100  # Convert to 0-100 scale

    def _compute_completeness(
        self,
        session: Session,
        party_id: Optional[str] = None,
    ) -> float:
        """Compute completeness score (0-1)"""
        required_questions = []
        answered_questions = []

        for qid, q_def in self.questions.items():
            if q_def.get("required", False):
                required_questions.append(qid)
                # Check if answered
                if q_def.get("party_aware"):
                    value = session.get_answer(qid, party_id)
                else:
                    value = session.get_answer(qid)

                if value is not None and value != "":
                    answered_questions.append(qid)

        if not required_questions:
            return 1.0

        return len(answered_questions) / len(required_questions)

    def _compute_consistency(
        self,
        session: Session,
        party_id: Optional[str] = None,
    ) -> float:
        """Compute internal consistency score (0-1)"""
        # Start with perfect consistency
        consistency = 1.0

        # Check for known inconsistencies from flags
        inconsistency_flags = [
            "FLAG_INCOME_INCONSISTENCY",
            "FLAG_ASSETS_LOW_FOR_PRICE",
            "FLAG_DTI_EXCEEDS_TYPICAL",
            "FLAG_ADDRESS_MISMATCH",
        ]

        for flag in session.flags:
            if flag.code in inconsistency_flags:
                consistency -= 0.15  # Deduct for each inconsistency

        # Check edit history - excessive edits reduce consistency
        edits_count = len(session.edits_history)
        if edits_count > 10:
            consistency -= 0.1
        elif edits_count > 5:
            consistency -= 0.05

        return max(0, consistency)

    def _compute_evidence_alignment(
        self,
        session: Session,
        party_id: Optional[str] = None,
    ) -> float:
        """Compute evidence alignment score (0-1)"""
        evidence_score = 0.5  # Start at neutral

        # Check for autofill usage (indicates verified data)
        for key, meta in session.answer_meta.items():
            if meta.evidence_source == "autofill":
                evidence_score += 0.1

        # Check for document intent signals
        # In production, this would check for Plaid linkage, document uploads, etc.

        # Cap at 1.0
        return min(1.0, evidence_score)

    def _compute_behavioral_confidence(self, session: Session) -> float:
        """Compute behavioral confidence score (0-1)"""
        # Inverse of hesitation score
        hesitation = session.scores.hesitation_score
        base_confidence = 1.0 - hesitation

        # Adjust for edit rate
        questions_answered = session.signals.questions_answered
        if questions_answered > 0:
            edit_rate = session.signals.edits_count / questions_answered
            if edit_rate > 0.5:
                base_confidence -= 0.2
            elif edit_rate > 0.25:
                base_confidence -= 0.1

        return max(0, base_confidence)

    def _check_penalty_condition(
        self,
        penalty: Dict[str, Any],
        session: Session,
        party_id: Optional[str] = None,
    ) -> bool:
        """Check if penalty condition is met"""
        when = penalty.get("when", {})

        # Check for flag presence
        if "flag_present" in when:
            return session.has_flag(when["flag_present"])

        # Check condition expression
        if "condition" in when:
            return self._evaluate_condition(when["condition"], session, party_id)

        # Check multiple conditions (AND logic)
        if "conditions" in when:
            return all(
                self._evaluate_condition(cond, session, party_id)
                for cond in when["conditions"]
            )

        return False

    def _check_bonus_condition(
        self,
        bonus: Dict[str, Any],
        session: Session,
        party_id: Optional[str] = None,
    ) -> bool:
        """Check if bonus condition is met"""
        when = bonus.get("when", {})

        if "condition" in when:
            return self._evaluate_condition(when["condition"], session, party_id)

        return False

    def _evaluate_condition(
        self,
        condition: str,
        session: Session,
        party_id: Optional[str] = None,
    ) -> bool:
        """Evaluate a condition expression"""
        # Simple expression evaluator for common patterns
        # In production, use a proper expression parser

        try:
            # Handle session.scores.X comparisons
            if "session.scores.hesitation_score" in condition:
                hesitation = session.scores.hesitation_score
                if ">=" in condition:
                    threshold = float(condition.split(">=")[1].strip())
                    return hesitation >= threshold
                elif "<" in condition:
                    threshold = float(condition.split("<")[1].strip())
                    return hesitation < threshold

            # Handle session.signals.X comparisons
            if "session.signals.edits_count" in condition:
                edits = session.signals.edits_count
                if ">=" in condition:
                    threshold = int(condition.split(">=")[1].strip())
                    return edits >= threshold

            # Handle answers.X comparisons
            if "answers." in condition:
                # Extract question ID and comparison
                import re
                match = re.search(r"answers\.(\w+)\s*(>|<|>=|<=|==|is null|is not null)", condition)
                if match:
                    qid = match.group(1)
                    op = match.group(2)
                    value = session.get_answer(qid, party_id)

                    if op == "is null":
                        return value is None or value == ""
                    elif op == "is not null":
                        return value is not None and value != ""
                    elif value is not None:
                        # Extract comparison value
                        val_match = re.search(r"(>|<|>=|<=|==)\s*(\d+|'[^']+'|\"[^\"]+\")", condition)
                        if val_match:
                            compare_val = val_match.group(2).strip("'\"")
                            try:
                                compare_val = float(compare_val)
                                value = float(value)
                            except (ValueError, TypeError):
                                pass

                            if op == ">":
                                return value > compare_val
                            elif op == "<":
                                return value < compare_val
                            elif op == ">=":
                                return value >= compare_val
                            elif op == "<=":
                                return value <= compare_val
                            elif op == "==":
                                return value == compare_val

            # Handle answer_meta checks
            if "session.answer_meta" in condition:
                if "evidence_source == 'autofill'" in condition:
                    # Check if any answer has autofill source
                    for key, meta in session.answer_meta.items():
                        if meta.evidence_source == "autofill":
                            return True
                    return False

        except Exception as e:
            logger.exception(f"Failed to evaluate bonus condition: {e}")

        return False

    def _determine_truth_band(self, score: float) -> TruthBand:
        """Determine truth band from score"""
        if score >= 90:
            return TruthBand.GREEN
        elif score >= 75:
            return TruthBand.LIGHT_GREEN
        elif score >= 55:
            return TruthBand.YELLOW
        elif score >= 35:
            return TruthBand.ORANGE
        else:
            return TruthBand.RED

    def _compute_readiness_score(
        self,
        session: Session,
        party_id: Optional[str] = None,
    ) -> float:
        """Compute LO readiness score (0-100)"""
        # Check gating rules first
        for gate in self.gating_rules:
            if not self._check_gate(gate, session, party_id):
                cap = gate.get("cap_readiness_at", 0)
                return cap

        # Compute section weights
        total_weight = 0
        earned_weight = 0

        for section, config in self.readiness_sections.items():
            weight = config.get("weight", 0)
            total_weight += weight

            # Check section completion
            required_fields = config.get("required_fields", [])
            if required_fields:
                completed = 0
                for field in required_fields:
                    value = session.get_answer(field, party_id)
                    if value is not None and value != "":
                        completed += 1
                section_completion = completed / len(required_fields)
            else:
                section_completion = 1.0 if section in session.current_section else 0.0

            earned_weight += weight * section_completion

        if total_weight == 0:
            return 0

        base_readiness = (earned_weight / total_weight) * 100

        # Apply readiness cap if truth score is low
        truth_score = session.scores.underwriting_truth_score
        if truth_score < 50:
            base_readiness = min(base_readiness, 60)
        elif truth_score < 70:
            base_readiness = min(base_readiness, 80)

        return base_readiness

    def _check_gate(
        self,
        gate: Dict[str, Any],
        session: Session,
        party_id: Optional[str] = None,
    ) -> bool:
        """Check if a gating rule passes"""
        gate_type = gate.get("type")
        condition = gate.get("condition", {})

        if gate_type == "consent_required":
            consent_key = condition.get("consent_key")
            if consent_key:
                consent = session.consents.get(consent_key)
                return consent is not None and consent.accepted
            return True

        elif gate_type == "fields_required":
            fields = condition.get("fields", [])
            for field in fields:
                value = session.get_answer(field, party_id)
                if value is None or value == "":
                    return False
            return True

        elif gate_type == "section_complete":
            section = condition.get("section")
            # Check if section is complete based on required questions
            return True  # Simplified - would check section completion

        return True


def create_scoring_engine(
    truth_config: Dict[str, Any],
    readiness_config: Dict[str, Any],
    questions: Dict[str, Any],
) -> ScoringEngine:
    """Factory function to create scoring engine"""
    return ScoringEngine(truth_config, readiness_config, questions)
