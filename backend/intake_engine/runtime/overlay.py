"""
LO Coaching Overlay Engine
Provides contextual guidance to loan officers during intake
"""

from typing import Any, Dict, List, Optional
from .models import Session, Flag, TruthBand


class OverlayContent:
    """Content for a coaching overlay"""
    def __init__(
        self,
        overlay_id: str,
        title: str,
        subtitle: Optional[str] = None,
        message: str = "",
        actions: List[Dict] = None,
        priority: str = "medium",
        dismissible: bool = True,
        auto_dismiss_after: Optional[int] = None,
    ):
        self.overlay_id = overlay_id
        self.title = title
        self.subtitle = subtitle
        self.message = message
        self.actions = actions or []
        self.priority = priority
        self.dismissible = dismissible
        self.auto_dismiss_after = auto_dismiss_after

    def to_dict(self) -> Dict[str, Any]:
        return {
            "overlay_id": self.overlay_id,
            "title": self.title,
            "subtitle": self.subtitle,
            "message": self.message,
            "actions": self.actions,
            "priority": self.priority,
            "dismissible": self.dismissible,
            "auto_dismiss_after": self.auto_dismiss_after,
        }


class CoachingOverlayEngine:
    """Manages LO coaching overlays during intake"""

    def __init__(self, coaching_config: Dict[str, Any], i18n: Dict[str, Any] = None):
        self.config = coaching_config
        self.overlays = coaching_config.get("overlays", {})
        self.triggers = coaching_config.get("triggers", [])
        self.i18n = i18n or {}

    def check_triggers(
        self,
        session: Session,
        event_type: str,
        context: Dict[str, Any] = None,
    ) -> Optional[OverlayContent]:
        """Check if any overlay should be triggered"""
        context = context or {}

        for trigger in self.triggers:
            if self._matches_trigger(trigger, session, event_type, context):
                overlay_id = trigger.get("show_overlay")
                if overlay_id:
                    return self.get_overlay(overlay_id, session, context)

        return None

    def _matches_trigger(
        self,
        trigger: Dict[str, Any],
        session: Session,
        event_type: str,
        context: Dict[str, Any],
    ) -> bool:
        """Check if trigger conditions are met"""
        # Check event type
        if trigger.get("on_event") and trigger["on_event"] != event_type:
            return False

        conditions = trigger.get("when", {})

        # Check flag conditions
        if "flag_present" in conditions:
            if not session.has_flag(conditions["flag_present"]):
                return False

        if "any_flag_present" in conditions:
            if not any(session.has_flag(f) for f in conditions["any_flag_present"]):
                return False

        # Check score conditions
        if "truth_score_below" in conditions:
            if session.scores.underwriting_truth_score >= conditions["truth_score_below"]:
                return False

        if "truth_band" in conditions:
            if session.scores.truth_band != conditions["truth_band"]:
                return False

        if "hesitation_band" in conditions:
            if session.scores.hesitation_band != conditions["hesitation_band"]:
                return False

        # Check question conditions
        if "question_id" in conditions:
            if context.get("question_id") != conditions["question_id"]:
                return False

        if "question_category" in conditions:
            if context.get("question_category") != conditions["question_category"]:
                return False

        # Check section conditions
        if "section" in conditions:
            if session.current_section != conditions["section"]:
                return False

        # Check answer conditions
        if "answer_value" in conditions:
            qid = conditions.get("question_id", context.get("question_id"))
            expected = conditions["answer_value"]
            actual = session.get_answer(qid)
            if actual != expected:
                return False

        return True

    def get_overlay(
        self,
        overlay_id: str,
        session: Session,
        context: Dict[str, Any] = None,
    ) -> Optional[OverlayContent]:
        """Get overlay content by ID"""
        context = context or {}
        overlay_def = self.overlays.get(overlay_id)

        if not overlay_def:
            return None

        # Get localized content
        title = self._get_text(overlay_def.get("title_key"), overlay_def.get("title", ""))
        subtitle = self._get_text(overlay_def.get("subtitle_key"), overlay_def.get("subtitle"))
        message = self._get_text(overlay_def.get("message_key"), overlay_def.get("message", ""))

        # Format message with context
        message = self._format_message(message, session, context)

        # Get actions
        actions = []
        for action_def in overlay_def.get("actions", []):
            action = {
                "id": action_def.get("id"),
                "label": self._get_text(action_def.get("label_key"), action_def.get("label", "")),
                "action_type": action_def.get("type", "button"),
                "style": action_def.get("style", "primary"),
            }
            if "navigate_to" in action_def:
                action["navigate_to"] = action_def["navigate_to"]
            if "trigger_event" in action_def:
                action["trigger_event"] = action_def["trigger_event"]
            actions.append(action)

        return OverlayContent(
            overlay_id=overlay_id,
            title=title,
            subtitle=subtitle,
            message=message,
            actions=actions,
            priority=overlay_def.get("priority", "medium"),
            dismissible=overlay_def.get("dismissible", True),
            auto_dismiss_after=overlay_def.get("auto_dismiss_after"),
        )

    def get_proactive_coaching(
        self,
        session: Session,
        current_question_id: str = None,
    ) -> List[OverlayContent]:
        """Get proactive coaching suggestions based on session state"""
        suggestions = []

        # Check for truth score concerns
        if session.scores.truth_band in [TruthBand.RED, TruthBand.ORANGE]:
            overlay = self.get_overlay("COACH_TRUTH_RECOVERY", session)
            if overlay:
                suggestions.append(overlay)

        # Check for high hesitation
        if session.scores.hesitation_band == "high":
            overlay = self.get_overlay("COACH_VERIFY_NEXT", session)
            if overlay:
                suggestions.append(overlay)

        # Check for specific flags
        flag_overlays = {
            "FLAG_DECLARATIONS_YES_NO_DETAIL": "COACH_DECLARATIONS_DETAILS",
            "FLAG_INCOME_INCONSISTENCY": "COACH_INCOME_VERIFICATION",
            "FLAG_ASSETS_LOW_FOR_PRICE": "COACH_ASSETS_DISCUSSION",
            "FLAG_DTI_EXCEEDS_TYPICAL": "COACH_DTI_DISCUSSION",
        }

        for flag in session.flags:
            if flag.code in flag_overlays:
                overlay = self.get_overlay(flag_overlays[flag.code], session)
                if overlay:
                    suggestions.append(overlay)

        return suggestions

    def get_next_best_question_hint(
        self,
        session: Session,
        available_questions: List[str],
    ) -> Optional[Dict[str, Any]]:
        """Get hint for next best question to ask"""
        # Prioritize questions that could improve truth score
        priority_categories = ["income", "assets", "employment"]

        for category in priority_categories:
            for qid in available_questions:
                q_def = self.config.get("question_priorities", {}).get(qid, {})
                if q_def.get("category") == category:
                    return {
                        "question_id": qid,
                        "reason": f"Verifying {category} can improve application quality",
                        "priority": "high",
                    }

        # Default to first available
        if available_questions:
            return {
                "question_id": available_questions[0],
                "reason": "Continue with intake flow",
                "priority": "normal",
            }

        return None

    def _get_text(self, key: Optional[str], default: str = "") -> str:
        """Get localized text by key"""
        if not key:
            return default

        # Look up in i18n
        parts = key.split(".")
        value = self.i18n
        for part in parts:
            if isinstance(value, dict):
                value = value.get(part)
            else:
                return default

        return value if isinstance(value, str) else default

    def _format_message(
        self,
        message: str,
        session: Session,
        context: Dict[str, Any],
    ) -> str:
        """Format message with session/context values"""
        replacements = {
            "{borrower_name}": self._get_borrower_name(session),
            "{truth_score}": str(round(session.scores.underwriting_truth_score, 1)),
            "{readiness_score}": str(round(session.scores.lo_readiness_score, 1)),
            "{current_section}": session.current_section,
            "{hesitation_band}": session.scores.hesitation_band,
        }

        for key, value in replacements.items():
            message = message.replace(key, value)

        for key, value in context.items():
            message = message.replace(f"{{{key}}}", str(value))

        return message

    def _get_borrower_name(self, session: Session) -> str:
        """Get borrower's first name from session"""
        name = session.get_answer("Q_ID_0200")
        if isinstance(name, dict):
            return name.get("first", "the borrower")
        return name or "the borrower"


def create_overlay_engine(
    coaching_config: Dict[str, Any],
    i18n: Dict[str, Any] = None,
) -> CoachingOverlayEngine:
    """Factory function to create overlay engine"""
    return CoachingOverlayEngine(coaching_config, i18n)
