"""
Phase Transition Validator - Production-Ready

Ensures phase transitions meet ALL criteria to prevent:
- Premature CTA presentation
- Skipping trust-building steps
- Poor borrower experience
"""

import logging
from typing import List, Tuple, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class TransitionResult:
    """Result of phase transition validation"""
    allowed: bool
    reason: str
    target_phase: int
    recommendation: Optional[str] = None


class PhaseTransitionValidator:
    """Ensures phase transitions meet ALL criteria"""

    # Phase requirements configuration
    PHASE_REQUIREMENTS = {
        2: {  # Reassure → Educate
            'min_turns': 2,
            'min_intent_score': 0,
            'min_signals': 0,
            'description': 'User asks follow-up or seeks clarification',
            'failure_message': 'Continue building rapport before educating'
        },
        3: {  # Educate → Personalize
            'min_turns': 3,
            'min_intent_score': 30,
            'min_signals': 1,
            'description': 'Sufficient context to personalize',
            'failure_message': 'Need more context before personalizing'
        },
        4: {  # Personalize → Earned CTA
            'min_turns': 4,
            'min_intent_score': 50,
            'min_signals': 2,
            'description': 'High intent + sufficient context',
            'failure_message': 'Trust not yet earned for CTA'
        }
    }

    # Explicit CTA request phrases (user bypasses normal flow)
    EXPLICIT_CTA_PHRASES = [
        'i want to apply',
        'ready to apply',
        "let's start",
        "let's do it",
        'call me now',
        'call me',
        'talk to someone',
        'talk to tim',
        'speak with',
        'schedule a call',
        'schedule now',
        'sign me up',
        'get started',
        'i want to talk',
        'can you call me'
    ]

    @classmethod
    def can_transition_to(
        cls,
        target_phase: int,
        current_turn: int,
        intent_score: int,
        signal_count: int,
        user_message: Optional[str] = None
    ) -> TransitionResult:
        """
        Validate if transition to target phase is allowed.

        Args:
            target_phase: Phase to transition to (2, 3, or 4)
            current_turn: Current conversation turn count
            intent_score: Current intent score (0-100)
            signal_count: Number of detected intent signals
            user_message: Latest user message (for explicit CTA detection)

        Returns:
            TransitionResult with allowed status and reason
        """
        if target_phase not in cls.PHASE_REQUIREMENTS:
            return TransitionResult(
                allowed=False,
                reason=f"Invalid target phase: {target_phase}",
                target_phase=target_phase
            )

        # Check for explicit user CTA request (bypass normal rules)
        if user_message and target_phase == 4:
            if cls._is_explicit_cta_request(user_message):
                return TransitionResult(
                    allowed=True,
                    reason="User explicitly requested to proceed",
                    target_phase=target_phase,
                    recommendation="Honor user's explicit request"
                )

        req = cls.PHASE_REQUIREMENTS[target_phase]

        # Check turn count
        if current_turn < req['min_turns']:
            return TransitionResult(
                allowed=False,
                reason=f"Need {req['min_turns']} turns, have {current_turn}",
                target_phase=target_phase,
                recommendation=req['failure_message']
            )

        # Check intent score
        if intent_score < req['min_intent_score']:
            return TransitionResult(
                allowed=False,
                reason=f"Intent score {intent_score} < {req['min_intent_score']}",
                target_phase=target_phase,
                recommendation=req['failure_message']
            )

        # Check signal count
        if signal_count < req['min_signals']:
            return TransitionResult(
                allowed=False,
                reason=f"Need {req['min_signals']} signals, have {signal_count}",
                target_phase=target_phase,
                recommendation=req['failure_message']
            )

        return TransitionResult(
            allowed=True,
            reason=req['description'],
            target_phase=target_phase
        )

    @classmethod
    def _is_explicit_cta_request(cls, message: str) -> bool:
        """Check if user explicitly requested to proceed/call/apply"""
        message_lower = message.lower()
        return any(phrase in message_lower for phrase in cls.EXPLICIT_CTA_PHRASES)

    @classmethod
    def should_revert_phase(
        cls,
        current_phase: int,
        cta_declined_count: int,
        last_message_sentiment: Optional[str] = None
    ) -> Tuple[bool, int]:
        """
        Check if we should revert to an earlier phase.

        Returns:
            Tuple of (should_revert, new_phase)
        """
        # If CTA declined, revert to Phase 2 to rebuild trust
        if current_phase >= 4 and cta_declined_count >= 1:
            logger.info(f"Reverting from phase {current_phase} to 2 after CTA decline")
            return True, 2

        # If user seems frustrated/confused, revert to reassure
        if last_message_sentiment == 'anxious' and current_phase > 1:
            logger.info(f"Reverting to phase 1 due to user anxiety")
            return True, 1

        return False, current_phase

    @classmethod
    def get_phase_name(cls, phase: int) -> str:
        """Get human-readable phase name"""
        names = {
            1: "Reassure & Orient",
            2: "Educate with Tradeoffs",
            3: "Personalize via Micro-Commitments",
            4: "Earned Next Step"
        }
        return names.get(phase, f"Phase {phase}")

    @classmethod
    def get_phase_objective(cls, phase: int) -> str:
        """Get the objective for a phase"""
        objectives = {
            1: "Create emotional safety and acknowledge the borrower's situation",
            2: "Demonstrate expertise by educating with honest tradeoffs",
            3: "Earn permission by gathering personalized information",
            4: "Present ONE logical next step based on earned trust"
        }
        return objectives.get(phase, "Continue the conversation")

    @classmethod
    def calculate_phase_progress(
        cls,
        current_phase: int,
        turn_count: int,
        intent_score: int,
        signal_count: int
    ) -> dict:
        """
        Calculate progress toward next phase.

        Returns dict with progress indicators for UI display.
        """
        if current_phase >= 4:
            return {
                'current_phase': current_phase,
                'next_phase': None,
                'progress_percentage': 100,
                'missing': []
            }

        next_phase = current_phase + 1
        req = cls.PHASE_REQUIREMENTS.get(next_phase, {})

        missing = []
        met = []

        # Check each requirement
        if turn_count < req.get('min_turns', 0):
            missing.append(f"turns ({turn_count}/{req['min_turns']})")
        else:
            met.append('turns')

        if intent_score < req.get('min_intent_score', 0):
            missing.append(f"intent ({intent_score}/{req['min_intent_score']})")
        else:
            met.append('intent')

        if signal_count < req.get('min_signals', 0):
            missing.append(f"signals ({signal_count}/{req['min_signals']})")
        else:
            met.append('signals')

        # Calculate overall progress
        total_requirements = 3
        met_count = len(met)
        progress = int((met_count / total_requirements) * 100)

        return {
            'current_phase': current_phase,
            'current_phase_name': cls.get_phase_name(current_phase),
            'next_phase': next_phase,
            'next_phase_name': cls.get_phase_name(next_phase),
            'progress_percentage': progress,
            'requirements_met': met,
            'requirements_missing': missing
        }


class CTASelector:
    """Deterministic CTA selection based on borrower readiness"""

    @staticmethod
    def select_cta(
        intent_signals: List[str],
        urgency: str,
        phase: int,
        conversation_context: Optional[str] = None,
        cta_declined_count: int = 0
    ) -> Tuple[Optional[str], Optional[str]]:
        """
        Select appropriate CTA based on borrower state.

        Args:
            intent_signals: List of detected signal types
            urgency: 'low', 'medium', or 'high'
            phase: Current phase number
            conversation_context: Recent message content
            cta_declined_count: Number of times CTA was declined

        Returns:
            Tuple of (cta_type, framing_text) or (None, None)
        """
        # Don't offer CTA if not in phase 4
        if phase < 4:
            return None, None

        # Back off if declined too many times
        if cta_declined_count >= 2:
            return None, None

        signal_set = set(intent_signals)

        # APPLICATION FIRST - Most qualified borrowers
        application_signals = {
            'property', 'price', 'down_payment',
            'timeline', 'loan_type', 'credit_concern'
        }
        matching_app_signals = signal_set.intersection(application_signals)

        if len(matching_app_signals) >= 3:
            return 'application', (
                "Based on what you've shared, you're in a good position to see real numbers. "
                "The application takes about 10 minutes and gives you clarity without obligation."
            )

        # CALL NOW - Urgency or confusion
        urgency_indicators = {'urgency', 'recommendation_request'}
        has_urgency = any(sig in signal_set for sig in urgency_indicators)

        # Check for explicit call request
        if conversation_context:
            call_phrases = ['call me', 'talk to', 'speak with', 'phone call']
            if any(phrase in conversation_context.lower() for phrase in call_phrases):
                return 'call_now', (
                    "Happy to connect you right away. Tap 'Call Now' and you'll be connected "
                    "in about 30 seconds."
                )

        if urgency == 'high' or has_urgency:
            return 'call_now', (
                "If it would help to talk through this, you can speak with Tim right now. "
                "Tap 'Call Now' and he'll pick up if available."
            )

        # SCHEDULE - Default for exploratory borrowers
        if cta_declined_count == 1:
            # More subtle after first decline
            return 'schedule', (
                "No pressure at all. When you're ready, a quick call can help clarify your options."
            )

        return 'schedule', (
            "A short strategy call can help put this into context. "
            "No obligation - just clarity on your specific situation."
        )

    @staticmethod
    def get_cta_button_config(cta_type: str) -> dict:
        """Get button configuration for CTA type"""
        configs = {
            'call_now': {
                'label': 'Call Tim Now',
                'icon': 'phone',
                'color': 'primary',
                'action': 'initiate_call'
            },
            'schedule': {
                'label': 'Schedule a Call',
                'icon': 'calendar',
                'color': 'secondary',
                'action': 'open_scheduler'
            },
            'application': {
                'label': 'Start Application',
                'icon': 'document',
                'color': 'success',
                'action': 'open_application'
            }
        }
        return configs.get(cta_type, {})
