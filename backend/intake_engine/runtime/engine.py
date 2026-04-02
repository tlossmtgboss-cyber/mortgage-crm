"""
Intake Engine Core
Main orchestrator for conversational loan intake
"""

import json
import os
import yaml
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .models import (
    Session, Party, PartyType, SessionStatus, AnswerMeta,
    Flag, FlagCategory, FlagSeverity, EventType, Question,
    NextQuestion, AnswerResponse, SessionCompleteResponse,
    SLATask, HesitationBand, TruthBand
)
from .storage import SessionStorage
from .validation import ValidationEngine, create_validation_engine
from .hesitation import HesitationEngine, create_hesitation_engine
from .scoring import ScoringEngine, create_scoring_engine
from .overlay import CoachingOverlayEngine, create_overlay_engine
from .sla import SLAEngine, create_sla_engine
from .urla_builder import URLABuilder, create_urla_builder


class IntakeEngine:
    """
    Core intake engine that orchestrates:
    - Question sequencing
    - Answer validation
    - Hesitation detection
    - Truth/Readiness scoring
    - LO coaching overlays
    - SLA task creation
    - URLA payload generation
    """

    def __init__(
        self,
        config_path: str = None,
        redis_url: str = None,
        postgres_url: str = None,
    ):
        self.config_path = config_path or self._get_default_config_path()

        # Load all configuration
        self._load_configuration()

        # Initialize storage
        self.storage = SessionStorage(
            redis_url=redis_url,
            postgres_url=postgres_url,
            session_ttl=self.app_config.get("session", {}).get("ttl_seconds", 3600),
            enable_audit=self.app_config.get("audit", {}).get("enabled", True),
            enable_pii_redaction=self.app_config.get("pii", {}).get("redaction_enabled", True),
        )

        # Initialize engines
        self.validation_engine = create_validation_engine(self.validation_rules)
        self.hesitation_engine = create_hesitation_engine(self.hesitation_config)
        self.scoring_engine = create_scoring_engine(
            self.truth_score_config,
            self.readiness_config,
            self.questions,
        )
        self.overlay_engine = create_overlay_engine(self.coaching_config, self.i18n)
        self.sla_engine = create_sla_engine(self.sla_config)
        self.urla_builder = create_urla_builder(self.questions, self.value_sets)

    def _get_default_config_path(self) -> str:
        """Get default path to config directory"""
        return str(Path(__file__).parent.parent)

    def _load_configuration(self):
        """Load all configuration files"""
        base_path = Path(self.config_path)

        # Load app configuration
        self.app_config = self._load_yaml(base_path / "config" / "app_versions.yaml")

        # Load engine configurations
        self.sequencing_config = self._load_yaml(base_path / "engine" / "sequencing_engine.yaml")
        self.validation_rules = self._load_yaml(base_path / "engine" / "validation_rules.yaml")
        self.hesitation_config = self._load_yaml(base_path / "engine" / "hesitation_detection.yaml")
        self.truth_score_config = self._load_yaml(base_path / "engine" / "truth_score_model.yaml")
        self.readiness_config = self._load_yaml(base_path / "engine" / "readiness_score_model.yaml")
        self.coaching_config = self._load_yaml(base_path / "engine" / "lo_coaching_overlay.yaml")

        # Load SLA hooks
        self.sla_config = self._load_yaml(base_path / "config" / "sla_hooks.yaml")

        # Load question bank
        self.questions = self._load_questions(base_path / "question_bank")

        # Load i18n
        self.i18n = self._load_i18n(base_path / "i18n")

        # Load value sets
        self.value_sets = self._load_json(base_path / "schemas" / "value_sets.json")

        # Build section order (check both root level and nested)
        self.section_order = self.sequencing_config.get("global_order", []) or \
                            self.sequencing_config.get("sequencing_engine", {}).get("global_order", [])

        # Build question sequence
        self.section_questions = self._build_section_questions()

    def _load_yaml(self, path: Path) -> Dict[str, Any]:
        """Load YAML file"""
        try:
            with open(path, 'r') as f:
                return yaml.safe_load(f) or {}
        except FileNotFoundError:
            return {}

    def _load_json(self, path: Path) -> Dict[str, Any]:
        """Load JSON file"""
        try:
            with open(path, 'r') as f:
                return json.load(f)
        except FileNotFoundError:
            return {}

    def _load_questions(self, path: Path) -> Dict[str, Any]:
        """Load all question bank files"""
        questions = {}
        if path.exists():
            for file in path.glob("*.json"):
                data = self._load_json(file)
                # Handle both formats: list at top level or dict with "questions" key
                if isinstance(data, list):
                    for q in data:
                        if "question_id" in q:
                            questions[q["question_id"]] = q
                elif isinstance(data, dict) and "questions" in data:
                    for q in data["questions"]:
                        questions[q["question_id"]] = q
        return questions

    def _load_i18n(self, path: Path, locale: str = "en-US") -> Dict[str, Any]:
        """Load i18n files for locale"""
        i18n = {}

        # Load prompts - extract just the prompts dict from the file
        prompts_file = path / f"prompts.{locale}.json"
        if prompts_file.exists():
            prompts_data = self._load_json(prompts_file)
            # File structure: {"locale": "...", "prompts": {...}}
            i18n["prompts"] = prompts_data.get("prompts", prompts_data)

        # Load micro whys - extract just the micro_whys dict from the file
        whys_file = path / f"micro_whys.{locale}.json"
        if whys_file.exists():
            whys_data = self._load_json(whys_file)
            # File structure: {"locale": "...", "micro_whys": {...}}
            i18n["micro_whys"] = whys_data.get("micro_whys", whys_data)

        # Load language pack
        pack_file = path / "language_pack.yaml"
        if pack_file.exists():
            i18n["language_pack"] = self._load_yaml(pack_file)

        return i18n

    def _build_section_questions(self) -> Dict[str, List[str]]:
        """Build mapping of sections to questions from sequencing config"""
        sections = {}
        # Use sections from sequencing_engine.yaml
        config_sections = self.sequencing_config.get("sections", {})
        for section_id, section_config in config_sections.items():
            sections[section_id] = section_config.get("questions", [])

        # Fallback: build from urla_section if no sections defined
        if not sections:
            for qid, q_def in self.questions.items():
                section = q_def.get("urla_section", "OTHER")
                if section not in sections:
                    sections[section] = []
                sections[section].append(qid)
        return sections

    # =========================================================================
    # Session Management
    # =========================================================================

    def create_session(
        self,
        loan_id: str = None,
        borrower_id: str = None,
        mode: str = "intake_prequal",
        locale: str = "en-US",
    ) -> Session:
        """Create a new intake session"""
        session = Session(
            loan_id=loan_id,
            borrower_id=borrower_id,
            mode=mode,
            locale=locale,
            current_section=self.section_order[0] if self.section_order else "LANGUAGE",
        )

        # Add primary borrower party
        session.add_party(PartyType.PRIMARY)

        # Save session
        self.storage.save_session(session)

        # Create audit event
        self.storage.create_event(
            session_id=session.session_id,
            event_type=EventType.SESSION_STARTED,
            payload={
                "mode": mode,
                "locale": locale,
                "loan_id": loan_id,
            },
        )

        return session

    def get_session(self, session_id: str) -> Optional[Session]:
        """Get existing session"""
        return self.storage.get_session(session_id)

    def resume_session(self, session_id: str) -> Optional[Session]:
        """Resume a paused session"""
        session = self.storage.get_session(session_id)
        if session and session.status == SessionStatus.PAUSED:
            session.status = SessionStatus.ACTIVE
            self.storage.save_session(session)

            self.storage.create_event(
                session_id=session_id,
                event_type=EventType.SESSION_RESUMED,
                payload={"resumed_at": datetime.now(timezone.utc).isoformat()},
            )

        return session

    # =========================================================================
    # Question Sequencing
    # =========================================================================

    def get_next_question(
        self,
        session: Session,
        party_id: str = None,
    ) -> Optional[NextQuestion]:
        """Get the next question to ask based on session state"""
        # Get current section questions
        section = session.current_section
        section_questions = self.section_questions.get(section, [])

        # Find first unanswered question in current section
        for qid in section_questions:
            q_def = self.questions.get(qid)
            if not q_def:
                continue

            # Check if already answered
            if q_def.get("party_aware") and party_id:
                if session.get_answer(qid, party_id) is not None:
                    continue
            else:
                if session.get_answer(qid) is not None:
                    continue

            # Check if question should be skipped
            if qid in session.skipped_questions:
                continue

            # Check triggers (branching logic)
            if not self._check_triggers(q_def, session, party_id):
                continue

            # Found next question
            return self._build_next_question(qid, q_def, session, party_id)

        # Current section complete - move to next
        current_idx = self.section_order.index(section) if section in self.section_order else 0
        if current_idx < len(self.section_order) - 1:
            next_section = self.section_order[current_idx + 1]
            session.current_section = next_section
            self.storage.save_session(session)

            self.storage.create_event(
                session_id=session.session_id,
                event_type=EventType.SECTION_CHANGED,
                payload={"from": section, "to": next_section},
            )

            # Recursively get next question in new section
            return self.get_next_question(session, party_id)

        # All sections complete
        return None

    def _check_triggers(
        self,
        q_def: Dict[str, Any],
        session: Session,
        party_id: str = None,
    ) -> bool:
        """Check if question triggers (show conditions) are met"""
        triggers = q_def.get("triggers", [])

        if not triggers:
            return True  # No triggers = always show

        for trigger in triggers:
            trigger_type = trigger.get("type")

            if trigger_type == "show_if":
                # Show if condition is met
                condition = trigger.get("condition", {})
                if not self._evaluate_trigger_condition(condition, session, party_id):
                    return False

            elif trigger_type == "skip_if":
                # Skip if condition is met
                condition = trigger.get("condition", {})
                if self._evaluate_trigger_condition(condition, session, party_id):
                    return False

        return True

    def _evaluate_trigger_condition(
        self,
        condition: Dict[str, Any],
        session: Session,
        party_id: str = None,
    ) -> bool:
        """Evaluate a trigger condition"""
        field = condition.get("field")
        op = condition.get("operator", "eq")
        value = condition.get("value")

        if not field:
            return True

        # Get field value
        actual = session.get_answer(field, party_id) or session.get_answer(field)

        if op == "eq":
            return actual == value
        elif op == "neq":
            return actual != value
        elif op == "in":
            return actual in value
        elif op == "not_in":
            return actual not in value
        elif op == "exists":
            return actual is not None and actual != ""
        elif op == "not_exists":
            return actual is None or actual == ""
        elif op == "gt":
            return actual is not None and actual > value
        elif op == "gte":
            return actual is not None and actual >= value
        elif op == "lt":
            return actual is not None and actual < value
        elif op == "lte":
            return actual is not None and actual <= value

        return True

    def _build_next_question(
        self,
        question_id: str,
        q_def: Dict[str, Any],
        session: Session,
        party_id: str = None,
    ) -> NextQuestion:
        """Build NextQuestion response"""
        # Get localized prompt
        prompt_key = q_def.get("prompt_key", question_id)
        prompt_value = self.i18n.get("prompts", {}).get(prompt_key, "")
        # Handle both string and dict formats in i18n files
        if isinstance(prompt_value, dict):
            prompt = prompt_value.get("text", q_def.get("prompt", ""))
        else:
            prompt = prompt_value or q_def.get("prompt", "")

        # Build options if applicable
        options = None
        if q_def.get("options"):
            options = q_def["options"]
        elif q_def.get("options_from_value_set"):
            value_set = self.value_sets.get(q_def["options_from_value_set"], [])
            options = [{"value": v, "label": v} for v in value_set]

        # Build context
        context = {
            "section": session.current_section,
            "party_id": party_id,
            "micro_why": self._get_micro_why(question_id),
        }

        return NextQuestion(
            question_id=question_id,
            prompt=prompt,
            answer_types=q_def.get("answer_types", ["text"]),
            ui=q_def.get("ui", {}),
            options=options,
            context=context,
        )

    def _get_micro_why(self, question_id: str) -> Optional[str]:
        """Get micro-why explanation for a question"""
        micro_whys = self.i18n.get("micro_whys", {})
        return micro_whys.get(question_id, {}).get("text")

    # =========================================================================
    # Answer Processing
    # =========================================================================

    def submit_answer(
        self,
        session: Session,
        question_id: str,
        value: Any,
        party_id: str = None,
        response_time_ms: int = 0,
        device_rtt_ms: int = 0,
        edits_in_window: int = 0,
    ) -> AnswerResponse:
        """Process an answer submission"""
        q_def = self.questions.get(question_id)
        if not q_def:
            return AnswerResponse(
                accepted=False,
                validation_errors=[{"code": "UNKNOWN_QUESTION", "message": "Question not found"}],
            )

        # Validate answer
        validation_result = self.validation_engine.validate_answer(
            question_id, value, session, q_def
        )

        if not validation_result.valid:
            # Log validation error event
            self.storage.create_event(
                session_id=session.session_id,
                event_type=EventType.VALIDATION_ERROR,
                payload={
                    "question_id": question_id,
                    "errors": validation_result.errors,
                },
                party_id=party_id,
            )

            return AnswerResponse(
                accepted=False,
                validation_errors=validation_result.errors,
            )

        # Detect hesitation
        hedges = []
        if isinstance(value, str):
            hedges = self.hesitation_engine.detect_hedges(value)

        hesitation_result = self.hesitation_engine.analyze_response(
            question_id=question_id,
            value=value,
            response_time_ms=response_time_ms,
            device_rtt_ms=device_rtt_ms,
            session=session,
            question_index=session.signals.questions_answered,
            answer_type=q_def.get("answer_types", ["text"])[0],
            edits_in_window=edits_in_window,
        )

        # Create answer metadata
        meta = AnswerMeta(
            party_id=party_id,
            confidence=1.0 - hesitation_result.confidence_adjustment,
            evidence_source="memory",
            response_time_ms=response_time_ms,
            hedges_detected=hedges,
            uncertainty_expressed=hesitation_result.band == HesitationBand.HIGH,
        )

        # Store answer
        session.set_answer(question_id, value, party_id, meta)

        # Update session signals
        self.hesitation_engine.update_session_signals(
            session,
            response_time_ms,
            edits_count=edits_in_window,
            hedges=hedges,
        )

        # Update hesitation score
        session.scores.hesitation_score = max(
            session.scores.hesitation_score,
            hesitation_result.score
        )
        session.scores.hesitation_band = hesitation_result.band

        # Add hesitation flags
        for flag in hesitation_result.flags:
            session.add_flag(flag)

        # Run cross-field validation
        inconsistencies, consistency_flags = self.validation_engine.validate_cross_field(
            session, party_id
        )
        for flag in consistency_flags:
            session.add_flag(flag)

        # Recompute scores
        scoring_result = self.scoring_engine.compute_scores(session, party_id)
        session.scores.underwriting_truth_score = scoring_result.truth_score
        session.scores.truth_band = scoring_result.truth_band
        session.scores.lo_readiness_score = scoring_result.readiness_score
        session.scores.score_breakdown = scoring_result.breakdown

        for flag in scoring_result.flags:
            session.add_flag(flag)

        # Save session
        self.storage.save_session(session)

        # Log answer event
        self.storage.create_event(
            session_id=session.session_id,
            event_type=EventType.ANSWER_SUBMITTED,
            payload={
                "question_id": question_id,
                "hesitation_score": hesitation_result.score,
            },
            party_id=party_id,
        )

        # Check for coaching overlay
        overlay = None
        if hesitation_result.overlay:
            overlay_content = self.overlay_engine.get_overlay(
                hesitation_result.overlay, session, {"question_id": question_id}
            )
            if overlay_content:
                overlay = overlay_content.to_dict()
                session.active_overlay = hesitation_result.overlay

        # Get next question
        next_q = self.get_next_question(session, party_id)

        # Build response
        return AnswerResponse(
            accepted=True,
            validation_errors=[],
            flags_added=[f.code for f in hesitation_result.flags + scoring_result.flags],
            scores={
                "truth_score": scoring_result.truth_score,
                "truth_band": scoring_result.truth_band,
                "readiness_score": scoring_result.readiness_score,
                "hesitation_score": hesitation_result.score,
            },
            next=next_q,
            overlay=overlay,
        )

    # =========================================================================
    # Session Completion
    # =========================================================================

    def complete_session(
        self,
        session: Session,
    ) -> SessionCompleteResponse:
        """Complete the intake session"""
        # Final score computation
        scoring_result = self.scoring_engine.compute_scores(session)
        session.scores.underwriting_truth_score = scoring_result.truth_score
        session.scores.truth_band = scoring_result.truth_band
        session.scores.lo_readiness_score = scoring_result.readiness_score

        # Build URLA payload
        urla_payload = self.urla_builder.build(session)

        # Validate URLA payload
        urla_validation = self.urla_builder.validate_payload(urla_payload)

        # Create SLA tasks
        sla_tasks = self.sla_engine.evaluate_hooks(session, "session_complete")
        for task in sla_tasks:
            self.storage.create_task(task)

        # Update session status
        session.status = SessionStatus.COMPLETE
        session.completed_at = datetime.now(timezone.utc)
        self.storage.save_session(session)

        # Log completion event
        self.storage.create_event(
            session_id=session.session_id,
            event_type=EventType.SESSION_COMPLETED,
            payload={
                "truth_score": scoring_result.truth_score,
                "truth_band": scoring_result.truth_band,
                "readiness_score": scoring_result.readiness_score,
                "sla_tasks_created": len(sla_tasks),
            },
        )

        # Log URLA generation
        self.storage.create_event(
            session_id=session.session_id,
            event_type=EventType.URLA_GENERATED,
            payload={
                "valid": urla_validation["valid"],
                "issues_count": len(urla_validation.get("issues", [])),
            },
        )

        # Determine redirect
        redirect = None
        if scoring_result.truth_band in [TruthBand.RED, TruthBand.ORANGE]:
            redirect = "/review/high-risk"
        elif scoring_result.readiness_score < 70:
            redirect = "/review/incomplete"
        else:
            redirect = "/application/review"

        return SessionCompleteResponse(
            status="complete",
            urla_payload=urla_payload,
            scores={
                "truth_score": scoring_result.truth_score,
                "truth_band": scoring_result.truth_band,
                "readiness_score": scoring_result.readiness_score,
                "breakdown": {
                    "completeness": scoring_result.breakdown.completeness,
                    "internal_consistency": scoring_result.breakdown.internal_consistency,
                    "evidence_alignment": scoring_result.breakdown.evidence_alignment,
                    "behavioral_confidence": scoring_result.breakdown.behavioral_confidence,
                },
            },
            flags=[{"code": f.code, "severity": f.severity, "message": f.message} for f in session.flags],
            sla_tasks_created=[{
                "code": t.code,
                "title": t.title,
                "priority": t.priority,
                "assignee_role": t.assignee_role,
            } for t in sla_tasks],
            redirect=redirect,
        )

    # =========================================================================
    # Party Management
    # =========================================================================

    def add_party(
        self,
        session: Session,
        party_type: PartyType,
        display_name: str = None,
    ) -> Party:
        """Add a new party (co-borrower, NBS) to session"""
        party = session.add_party(party_type, display_name)
        self.storage.save_session(session)

        self.storage.create_event(
            session_id=session.session_id,
            event_type=EventType.PARTY_ADDED,
            payload={
                "party_id": party.party_id,
                "party_type": party_type,
                "display_name": display_name,
            },
        )

        return party

    # =========================================================================
    # Coaching & Overlays
    # =========================================================================

    def get_coaching_suggestions(self, session: Session) -> List[Dict]:
        """Get proactive coaching suggestions for LO"""
        overlays = self.overlay_engine.get_proactive_coaching(session)
        return [o.to_dict() for o in overlays]

    def dismiss_overlay(self, session: Session, overlay_id: str):
        """Dismiss an active overlay"""
        if session.active_overlay == overlay_id:
            session.active_overlay = None
            self.storage.save_session(session)

    # =========================================================================
    # Audit & Verification
    # =========================================================================

    def get_audit_trail(self, session_id: str) -> List[Dict]:
        """Get audit trail for session"""
        events = self.storage.get_events(session_id)
        return [
            {
                "event_id": e.event_id,
                "event_type": e.event_type,
                "created_at": e.created_at.isoformat(),
                "party_id": e.party_id,
                "pii_redacted": e.pii_redacted,
            }
            for e in events
        ]

    def verify_audit_chain(self, session_id: str) -> bool:
        """Verify integrity of audit chain"""
        return self.storage.verify_event_chain(session_id)


def create_engine(
    config_path: str = None,
    redis_url: str = None,
    postgres_url: str = None,
) -> IntakeEngine:
    """Factory function to create intake engine"""
    return IntakeEngine(config_path, redis_url, postgres_url)
