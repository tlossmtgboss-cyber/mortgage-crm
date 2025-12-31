"""
Hesitation Detection Engine
Analyzes behavioral signals to detect borrower uncertainty
"""

import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
from .models import Session, Signals, HesitationBand, Flag, FlagCategory, FlagSeverity


class HesitationResult:
    """Result of hesitation analysis"""
    def __init__(
        self,
        score: float,
        band: HesitationBand,
        signals_detected: List[Dict],
        confidence_adjustment: float = 0.0,
        flags: List[Flag] = None,
        overlay: Optional[str] = None,
    ):
        self.score = score
        self.band = band
        self.signals_detected = signals_detected
        self.confidence_adjustment = confidence_adjustment
        self.flags = flags or []
        self.overlay = overlay


class HesitationEngine:
    """Detects hesitation and uncertainty signals"""

    # Hedge phrases to detect
    HEDGE_PHRASES = [
        "not sure", "i think", "maybe", "around", "approximately",
        "guess", "about", "roughly", "probably", "might be",
        "could be", "somewhere around",
    ]

    # Strong uncertainty phrases
    UNCERTAINTY_PHRASES = [
        "i don't know", "no idea", "not certain", "hard to say",
        "let me think", "i need to check", "i'll have to look",
    ]

    def __init__(self, hesitation_config: Dict[str, Any]):
        self.config = hesitation_config
        self.signals = hesitation_config.get("signals", [])
        self.outputs = hesitation_config.get("outputs", {})
        self.actions = hesitation_config.get("actions", {})
        self.question_sensitivity = hesitation_config.get("question_sensitivity", {})
        self.false_positive_filters = hesitation_config.get("false_positive_filters", [])

        # Get thresholds
        thresholds = self.outputs.get("hesitation_score", {}).get("thresholds", {})
        self.threshold_mild = thresholds.get("mild", 0.35)
        self.threshold_moderate = thresholds.get("moderate", 0.55)
        self.threshold_high = thresholds.get("high", 0.75)

    def analyze_response(
        self,
        question_id: str,
        value: Any,
        response_time_ms: int,
        device_rtt_ms: int,
        session: Session,
        question_index: int = 0,
        answer_type: str = None,
        device_type: str = None,
        edits_in_window: int = 0,
        back_navigations: int = 0,
        skip_attempted: bool = False,
    ) -> HesitationResult:
        """Analyze a single response for hesitation signals"""
        signals_detected = []
        total_weight = 0.0

        # Apply latency normalization
        if self.config.get("latency_normalization", {}).get("enabled", True):
            effective_response_ms = max(0, response_time_ms - (2 * device_rtt_ms))
        else:
            effective_response_ms = response_time_ms

        # Get question-specific threshold adjustment
        threshold_adj = self._get_question_sensitivity(question_id)

        # Check each signal
        for signal in self.signals:
            signal_id = signal.get("id")
            signal_type = signal.get("type")
            weight = signal.get("weight", 0)
            rule = signal.get("rule", {})

            # Check if signal should be filtered
            if self._should_filter_signal(signal_id, question_id, question_index, answer_type, device_type):
                continue

            detected = False

            if signal_type == "timing":
                threshold = rule.get("response_time_ms_gte", 18000)
                if effective_response_ms >= threshold:
                    detected = True
                    signals_detected.append({
                        "signal_id": signal_id,
                        "type": signal_type,
                        "weight": weight,
                        "value": effective_response_ms,
                        "threshold": threshold,
                    })

            elif signal_type == "behavior":
                # Check edit count
                if "edits_count_gte" in rule:
                    if edits_in_window >= rule["edits_count_gte"]:
                        detected = True
                        signals_detected.append({
                            "signal_id": signal_id,
                            "type": signal_type,
                            "weight": weight,
                            "value": edits_in_window,
                            "threshold": rule["edits_count_gte"],
                        })

                # Check back navigation
                if "back_navigation_count_gte" in rule:
                    if back_navigations >= rule["back_navigation_count_gte"]:
                        detected = True
                        signals_detected.append({
                            "signal_id": signal_id,
                            "type": signal_type,
                            "weight": weight,
                            "value": back_navigations,
                        })

                # Check skip attempt
                if rule.get("skip_attempted") and skip_attempted:
                    detected = True
                    signals_detected.append({
                        "signal_id": signal_id,
                        "type": signal_type,
                        "weight": weight,
                    })

                # Check range selection
                if rule.get("selected_range") and self._is_range_selection(value):
                    detected = True
                    signals_detected.append({
                        "signal_id": signal_id,
                        "type": signal_type,
                        "weight": weight,
                    })

            elif signal_type == "nlp":
                # Check for hedge/uncertainty language
                if isinstance(value, str):
                    text_lower = value.lower()
                    contains_any = rule.get("contains_any", [])

                    for phrase in contains_any:
                        if phrase in text_lower:
                            detected = True
                            signals_detected.append({
                                "signal_id": signal_id,
                                "type": signal_type,
                                "weight": weight,
                                "phrase": phrase,
                            })
                            break

            if detected:
                total_weight += weight

        # Apply threshold adjustment for question sensitivity
        adjusted_score = min(1.0, max(0.0, total_weight - threshold_adj))

        # Determine band
        band = self._determine_band(adjusted_score)

        # Get confidence adjustment and actions
        confidence_adjustment = 0.0
        flags = []
        overlay = None

        if band == HesitationBand.MODERATE:
            actions = self.actions.get("when_moderate", [])
            for action in actions:
                if "lower_confidence" in action:
                    confidence_adjustment = action["lower_confidence"]
                if "add_flag" in action:
                    flags.append(Flag(
                        code=action["add_flag"],
                        category=FlagCategory.TRUTH,
                        severity=FlagSeverity.WARN,
                        triggered_by=question_id,
                    ))
                if "coaching_overlay" in action:
                    overlay = action["coaching_overlay"]

        elif band == HesitationBand.HIGH:
            actions = self.actions.get("when_high", [])
            for action in actions:
                if "lower_confidence" in action:
                    confidence_adjustment = action["lower_confidence"]
                if "add_flag" in action:
                    flags.append(Flag(
                        code=action["add_flag"],
                        category=FlagCategory.TRUTH,
                        severity=FlagSeverity.HIGH,
                        triggered_by=question_id,
                    ))
                if "coaching_overlay" in action:
                    overlay = action["coaching_overlay"]

        return HesitationResult(
            score=adjusted_score,
            band=band,
            signals_detected=signals_detected,
            confidence_adjustment=confidence_adjustment,
            flags=flags,
            overlay=overlay,
        )

    def _determine_band(self, score: float) -> HesitationBand:
        """Determine hesitation band from score"""
        if score >= self.threshold_high:
            return HesitationBand.HIGH
        elif score >= self.threshold_moderate:
            return HesitationBand.MODERATE
        elif score >= self.threshold_mild:
            return HesitationBand.MILD
        return HesitationBand.NONE

    def _get_question_sensitivity(self, question_id: str) -> float:
        """Get threshold adjustment for question sensitivity"""
        high_sens = self.question_sensitivity.get("high_sensitivity", {})
        low_sens = self.question_sensitivity.get("low_sensitivity", {})

        if question_id in high_sens.get("questions", []) or question_id in high_sens:
            return high_sens.get("threshold_adjustment", 0.1)

        if question_id in low_sens.get("questions", []) or question_id in low_sens:
            return low_sens.get("threshold_adjustment", -0.15)

        return 0.0

    def _should_filter_signal(
        self,
        signal_id: str,
        question_id: str,
        question_index: int,
        answer_type: Optional[str],
        device_type: Optional[str],
    ) -> bool:
        """Check if signal should be filtered out (false positive prevention)"""
        for fp_filter in self.false_positive_filters:
            rule = fp_filter.get("rule", {})
            ignore_signals = rule.get("ignore_signals", [])

            if signal_id not in ignore_signals:
                continue

            # Check filter conditions
            if "question_index" in rule and question_index == rule["question_index"]:
                return True

            if "answer_type" in rule and answer_type == rule["answer_type"]:
                return True

            if "device_type" in rule and device_type == rule["device_type"]:
                # Apply threshold adjustment instead of ignoring
                pass

        return False

    def _is_range_selection(self, value: Any) -> bool:
        """Check if value represents a range selection"""
        if isinstance(value, str):
            # Check for range patterns like "50000-75000" or "50k-75k"
            return bool(re.match(r"^\d+k?\s*[-–]\s*\d+k?$", value.lower()))
        return False

    def detect_hedges(self, text: str) -> List[str]:
        """Extract hedge phrases from text"""
        if not isinstance(text, str):
            return []

        text_lower = text.lower()
        found = []

        for phrase in self.HEDGE_PHRASES:
            if phrase in text_lower:
                found.append(phrase)

        for phrase in self.UNCERTAINTY_PHRASES:
            if phrase in text_lower:
                found.append(phrase)

        return found

    def update_session_signals(
        self,
        session: Session,
        response_time_ms: int,
        edits_count: int = 0,
        hedges: List[str] = None,
        uncertainty_expressed: bool = False,
    ) -> Signals:
        """Update session-level behavioral signals"""
        signals = session.signals

        # Update response time
        signals.response_time_ms = response_time_ms
        total_answers = signals.questions_answered + 1
        signals.avg_response_time_ms = (
            (signals.avg_response_time_ms * signals.questions_answered + response_time_ms)
            / total_answers
        )

        # Update edits
        signals.edits_count += edits_count

        # Update hedges
        if hedges:
            signals.hedges.extend(hedges)

        # Update uncertainty count
        if uncertainty_expressed:
            signals.uncertainty_count += 1

        # Update question count
        signals.questions_answered = total_answers

        return signals


def create_hesitation_engine(hesitation_config: Dict[str, Any]) -> HesitationEngine:
    """Factory function to create hesitation engine"""
    return HesitationEngine(hesitation_config)
