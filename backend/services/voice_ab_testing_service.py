"""
Voice A/B Testing Service
Extends A/B testing framework for voice-specific experiments
Supports testing greetings, scripts, voice personas, and call flows
"""
import logging
from typing import Optional, Dict, Any, List
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass, field
from enum import Enum
import hashlib
from sqlalchemy.exc import SQLAlchemyError

logger = logging.getLogger(__name__)


class VoiceExperimentType(str, Enum):
    """Types of voice experiments"""
    GREETING = "greeting"
    SCRIPT = "script"
    VOICE_PERSONA = "voice_persona"
    CALL_FLOW = "call_flow"
    RESPONSE_STYLE = "response_style"
    ESCALATION_THRESHOLD = "escalation_threshold"
    HOLD_MUSIC = "hold_music"
    TRANSFER_MESSAGE = "transfer_message"


class VoiceMetric(str, Enum):
    """Voice-specific metrics for A/B testing"""
    CALL_SUCCESS_RATE = "call_success_rate"
    BOOKING_CONVERSION = "booking_conversion"
    TRANSFER_RATE = "transfer_rate"
    AVERAGE_CALL_DURATION = "avg_call_duration"
    CALLER_SATISFACTION = "caller_satisfaction"
    FIRST_CALL_RESOLUTION = "first_call_resolution"
    VOICEMAIL_RATE = "voicemail_rate"
    CALLBACK_REQUEST_RATE = "callback_rate"
    ESCALATION_RATE = "escalation_rate"
    HANG_UP_RATE = "hang_up_rate"


@dataclass
class VoiceVariant:
    """Configuration for a voice experiment variant"""
    id: str
    name: str
    is_control: bool = False
    traffic_allocation: float = 50.0
    config: Dict[str, Any] = field(default_factory=dict)

    # Voice-specific config
    greeting_text: Optional[str] = None
    voice_id: Optional[str] = None  # ElevenLabs or OpenAI voice ID
    speech_rate: float = 1.0
    pitch_adjustment: float = 0.0
    script_template: Optional[str] = None
    call_flow_id: Optional[str] = None


@dataclass
class VoiceExperiment:
    """Voice A/B test experiment"""
    id: str
    name: str
    description: str
    experiment_type: VoiceExperimentType
    primary_metric: VoiceMetric
    secondary_metrics: List[VoiceMetric] = field(default_factory=list)
    variants: List[VoiceVariant] = field(default_factory=list)

    # Targeting
    target_percentage: float = 100.0
    target_phone_patterns: List[str] = field(default_factory=list)  # e.g., ["area_code:415", "state:CA"]
    target_time_windows: List[Dict] = field(default_factory=list)  # e.g., [{"start": "09:00", "end": "17:00"}]

    # Statistical requirements
    min_calls: int = 100
    confidence_level: float = 0.95

    # State
    status: str = "draft"
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None
    winning_variant_id: Optional[str] = None


@dataclass
class VoiceExperimentResult:
    """Result from a voice experiment call"""
    experiment_id: str
    variant_id: str
    call_id: str
    caller_phone: str
    timestamp: datetime

    # Outcome metrics
    call_success: bool = False
    booking_made: bool = False
    transferred: bool = False
    call_duration_seconds: int = 0
    satisfaction_score: Optional[float] = None
    voicemail_left: bool = False
    callback_requested: bool = False
    escalated: bool = False
    hang_up_early: bool = False

    # Context
    time_of_day: str = ""  # morning, afternoon, evening
    day_of_week: str = ""
    caller_state: Optional[str] = None


class VoiceABTestingService:
    """
    Service for managing voice-specific A/B tests

    Features:
    - Test different greetings and scripts
    - Compare voice personas (ElevenLabs, OpenAI voices)
    - Measure voice-specific metrics
    - Time-based and geographic targeting
    """

    def __init__(self, db_session=None):
        self.db = db_session
        self._experiments_cache: Dict[str, VoiceExperiment] = {}
        self._results_buffer: List[VoiceExperimentResult] = []

    def create_experiment(
        self,
        name: str,
        description: str,
        experiment_type: VoiceExperimentType,
        primary_metric: VoiceMetric,
        variants: List[Dict[str, Any]],
        secondary_metrics: Optional[List[VoiceMetric]] = None,
        target_percentage: float = 100.0,
        min_calls: int = 100,
        confidence_level: float = 0.95,
        target_phone_patterns: Optional[List[str]] = None,
        target_time_windows: Optional[List[Dict]] = None
    ) -> VoiceExperiment:
        """
        Create a new voice A/B test experiment

        Args:
            name: Experiment name
            description: Description of what's being tested
            experiment_type: Type of voice experiment
            primary_metric: Main metric to optimize
            variants: List of variant configurations
            secondary_metrics: Additional metrics to track
            target_percentage: % of calls to include
            min_calls: Minimum calls before declaring winner
            confidence_level: Statistical confidence required
            target_phone_patterns: Phone number targeting rules
            target_time_windows: Time-based targeting rules
        """
        import uuid
        experiment_id = f"VEX-{str(uuid.uuid4())[:8].upper()}"

        # Validate traffic allocation
        total_allocation = sum(v.get("traffic_allocation", 50.0) for v in variants)
        if abs(total_allocation - 100.0) > 0.01:
            raise ValueError(f"Traffic allocation must sum to 100%, got {total_allocation}")

        # Create variant objects
        variant_objects = []
        for i, v in enumerate(variants):
            variant = VoiceVariant(
                id=f"{experiment_id}-V{i}",
                name=v["name"],
                is_control=v.get("is_control", i == 0),
                traffic_allocation=v.get("traffic_allocation", 100.0 / len(variants)),
                config=v.get("config", {}),
                greeting_text=v.get("greeting_text"),
                voice_id=v.get("voice_id"),
                speech_rate=v.get("speech_rate", 1.0),
                pitch_adjustment=v.get("pitch_adjustment", 0.0),
                script_template=v.get("script_template"),
                call_flow_id=v.get("call_flow_id")
            )
            variant_objects.append(variant)

        experiment = VoiceExperiment(
            id=experiment_id,
            name=name,
            description=description,
            experiment_type=experiment_type,
            primary_metric=primary_metric,
            secondary_metrics=secondary_metrics or [],
            variants=variant_objects,
            target_percentage=target_percentage,
            target_phone_patterns=target_phone_patterns or [],
            target_time_windows=target_time_windows or [],
            min_calls=min_calls,
            confidence_level=confidence_level,
            status="draft"
        )

        # Store in database
        if self.db:
            self._persist_experiment(experiment)

        # Cache locally
        self._experiments_cache[experiment_id] = experiment

        logger.info(f"Created voice experiment: {name} ({experiment_id}) with {len(variants)} variants")
        return experiment

    def start_experiment(self, experiment_id: str) -> bool:
        """Start a voice experiment"""
        experiment = self._get_experiment(experiment_id)
        if not experiment:
            logger.error(f"Experiment {experiment_id} not found")
            return False

        if experiment.status != "draft":
            logger.error(f"Cannot start experiment - status is {experiment.status}")
            return False

        experiment.status = "running"
        experiment.started_at = datetime.now(timezone.utc)

        if self.db:
            self._update_experiment_status(experiment_id, "running", experiment.started_at)

        logger.info(f"Started voice experiment: {experiment.name}")
        return True

    def get_variant_for_call(
        self,
        experiment_id: str,
        caller_phone: str,
        call_context: Optional[Dict] = None
    ) -> Optional[VoiceVariant]:
        """
        Get the assigned variant for an incoming call

        Args:
            experiment_id: ID of the experiment
            caller_phone: Caller's phone number
            call_context: Additional context (time, location, etc.)

        Returns:
            VoiceVariant configuration or None
        """
        experiment = self._get_experiment(experiment_id)
        if not experiment or experiment.status != "running":
            return None

        # Check targeting rules
        if not self._should_include_call(experiment, caller_phone, call_context):
            return None

        # Deterministic assignment based on phone number hash
        variant = self._assign_variant(experiment, caller_phone)

        logger.debug(f"Assigned variant '{variant.name}' to caller {caller_phone[-4:]}****")
        return variant

    def get_active_variant_for_call(
        self,
        caller_phone: str,
        experiment_type: Optional[VoiceExperimentType] = None,
        call_context: Optional[Dict] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Get active experiment variant for a call (auto-detect experiment)

        Args:
            caller_phone: Caller's phone number
            experiment_type: Optional filter by experiment type
            call_context: Additional context

        Returns:
            Dict with experiment_id, variant config, or None
        """
        # Find running experiments
        running_experiments = [
            exp for exp in self._experiments_cache.values()
            if exp.status == "running"
        ]

        if experiment_type:
            running_experiments = [
                exp for exp in running_experiments
                if exp.experiment_type == experiment_type
            ]

        if not running_experiments:
            return None

        # Use first matching experiment (could be extended to support multiple)
        experiment = running_experiments[0]
        variant = self.get_variant_for_call(experiment.id, caller_phone, call_context)

        if not variant:
            return None

        return {
            "experiment_id": experiment.id,
            "experiment_name": experiment.name,
            "experiment_type": experiment.experiment_type.value,
            "variant_id": variant.id,
            "variant_name": variant.name,
            "is_control": variant.is_control,
            "config": variant.config,
            "greeting_text": variant.greeting_text,
            "voice_id": variant.voice_id,
            "speech_rate": variant.speech_rate,
            "script_template": variant.script_template
        }

    def record_call_result(
        self,
        experiment_id: str,
        variant_id: str,
        call_id: str,
        caller_phone: str,
        call_success: bool = False,
        booking_made: bool = False,
        transferred: bool = False,
        call_duration_seconds: int = 0,
        satisfaction_score: Optional[float] = None,
        voicemail_left: bool = False,
        callback_requested: bool = False,
        escalated: bool = False,
        hang_up_early: bool = False,
        caller_state: Optional[str] = None
    ) -> bool:
        """
        Record the result of a call in an experiment

        Args:
            experiment_id: Experiment ID
            variant_id: Assigned variant ID
            call_id: Unique call ID
            caller_phone: Caller phone number
            call_success: Was the call successful?
            booking_made: Was an appointment booked?
            transferred: Was the call transferred?
            call_duration_seconds: Total call duration
            satisfaction_score: Caller satisfaction (0-5)
            voicemail_left: Did caller leave voicemail?
            callback_requested: Did caller request callback?
            escalated: Was call escalated?
            hang_up_early: Did caller hang up early?
            caller_state: Caller's state (for geographic analysis)
        """
        now = datetime.now(timezone.utc)

        # Determine time of day
        hour = now.hour
        if hour < 12:
            time_of_day = "morning"
        elif hour < 17:
            time_of_day = "afternoon"
        else:
            time_of_day = "evening"

        result = VoiceExperimentResult(
            experiment_id=experiment_id,
            variant_id=variant_id,
            call_id=call_id,
            caller_phone=caller_phone,
            timestamp=now,
            call_success=call_success,
            booking_made=booking_made,
            transferred=transferred,
            call_duration_seconds=call_duration_seconds,
            satisfaction_score=satisfaction_score,
            voicemail_left=voicemail_left,
            callback_requested=callback_requested,
            escalated=escalated,
            hang_up_early=hang_up_early,
            time_of_day=time_of_day,
            day_of_week=now.strftime("%A"),
            caller_state=caller_state
        )

        # Buffer results for batch persistence
        self._results_buffer.append(result)

        # Persist if buffer is large enough
        if len(self._results_buffer) >= 10:
            self._flush_results()

        logger.info(
            f"Recorded result for experiment {experiment_id}: "
            f"call_success={call_success}, booking={booking_made}, duration={call_duration_seconds}s"
        )
        return True

    def get_experiment_analysis(self, experiment_id: str) -> Optional[Dict[str, Any]]:
        """
        Get statistical analysis of a voice experiment

        Returns comprehensive analysis including:
        - Per-variant metrics
        - Statistical significance
        - Winner recommendation
        - Time-based breakdowns
        """
        experiment = self._get_experiment(experiment_id)
        if not experiment:
            return None

        # Get all results
        results = self._get_experiment_results(experiment_id)
        if not results:
            return {
                "experiment_id": experiment_id,
                "experiment_name": experiment.name,
                "status": experiment.status,
                "total_calls": 0,
                "message": "No results yet"
            }

        # Calculate per-variant stats
        variant_stats = {}
        for variant in experiment.variants:
            variant_results = [r for r in results if r.variant_id == variant.id]

            if not variant_results:
                continue

            total = len(variant_results)
            variant_stats[variant.id] = {
                "variant_name": variant.name,
                "is_control": variant.is_control,
                "total_calls": total,
                "metrics": {
                    "call_success_rate": sum(1 for r in variant_results if r.call_success) / total * 100,
                    "booking_conversion": sum(1 for r in variant_results if r.booking_made) / total * 100,
                    "transfer_rate": sum(1 for r in variant_results if r.transferred) / total * 100,
                    "avg_call_duration": sum(r.call_duration_seconds for r in variant_results) / total,
                    "voicemail_rate": sum(1 for r in variant_results if r.voicemail_left) / total * 100,
                    "escalation_rate": sum(1 for r in variant_results if r.escalated) / total * 100,
                    "hang_up_rate": sum(1 for r in variant_results if r.hang_up_early) / total * 100,
                },
                "satisfaction": self._calculate_satisfaction_stats(variant_results)
            }

        # Calculate statistical significance
        significance = self._calculate_significance(variant_stats, experiment.primary_metric)

        # Determine winner
        winner = self._determine_winner(
            variant_stats,
            experiment.primary_metric,
            significance,
            experiment.min_calls
        )

        return {
            "experiment_id": experiment_id,
            "experiment_name": experiment.name,
            "experiment_type": experiment.experiment_type.value,
            "status": experiment.status,
            "started_at": experiment.started_at.isoformat() if experiment.started_at else None,
            "primary_metric": experiment.primary_metric.value,
            "total_calls": len(results),
            "min_calls_required": experiment.min_calls,
            "sufficient_sample": len(results) >= experiment.min_calls,
            "variant_stats": variant_stats,
            "significance": significance,
            "winner": winner,
            "time_breakdown": self._get_time_breakdown(results),
            "geographic_breakdown": self._get_geographic_breakdown(results)
        }

    def stop_experiment(
        self,
        experiment_id: str,
        declare_winner: bool = True
    ) -> Optional[Dict[str, Any]]:
        """
        Stop an experiment and optionally declare a winner

        Returns final analysis with recommendation
        """
        experiment = self._get_experiment(experiment_id)
        if not experiment:
            return None

        # Flush any buffered results
        self._flush_results()

        # Get final analysis
        analysis = self.get_experiment_analysis(experiment_id)

        experiment.status = "completed"
        experiment.ended_at = datetime.now(timezone.utc)

        if declare_winner and analysis and analysis.get("winner"):
            experiment.winning_variant_id = analysis["winner"]["variant_id"]

        if self.db:
            self._update_experiment_status(
                experiment_id, "completed",
                experiment.ended_at,
                experiment.winning_variant_id
            )

        logger.info(f"Stopped voice experiment: {experiment.name}")

        return {
            "experiment_id": experiment_id,
            "status": "completed",
            "final_analysis": analysis,
            "winning_variant_id": experiment.winning_variant_id
        }

    def get_greeting_variants(self) -> List[Dict[str, str]]:
        """Get sample greeting variants for A/B testing"""
        return [
            {
                "name": "Professional",
                "greeting_text": "Thank you for calling. This is the AI assistant for {company_name}. How may I help you today?"
            },
            {
                "name": "Warm & Friendly",
                "greeting_text": "Hi there! Thanks for calling {company_name}. I'm here to help you with your mortgage needs. What can I do for you today?"
            },
            {
                "name": "Direct & Efficient",
                "greeting_text": "Hello, {company_name}. How can I assist you?"
            },
            {
                "name": "Personalized",
                "greeting_text": "Good {time_of_day}! Welcome to {company_name}. I'm your virtual assistant, ready to help with any mortgage questions. What brings you in today?"
            }
        ]

    def get_voice_persona_variants(self) -> List[Dict[str, Any]]:
        """Get sample voice persona variants for A/B testing"""
        return [
            {
                "name": "Professional Female",
                "voice_id": "EXAVITQu4vr4xnSDxMaL",  # ElevenLabs Sarah
                "speech_rate": 1.0,
                "pitch_adjustment": 0.0
            },
            {
                "name": "Friendly Male",
                "voice_id": "ErXwobaYiN019PkySvjV",  # ElevenLabs Antoni
                "speech_rate": 1.05,
                "pitch_adjustment": -0.1
            },
            {
                "name": "Calm & Reassuring",
                "voice_id": "alloy",  # OpenAI alloy
                "speech_rate": 0.95,
                "pitch_adjustment": 0.0
            },
            {
                "name": "Energetic",
                "voice_id": "nova",  # OpenAI nova
                "speech_rate": 1.1,
                "pitch_adjustment": 0.1
            }
        ]

    # Private helper methods

    def _get_experiment(self, experiment_id: str) -> Optional[VoiceExperiment]:
        """Get experiment from cache or database"""
        if experiment_id in self._experiments_cache:
            return self._experiments_cache[experiment_id]

        if self.db:
            experiment = self._load_experiment_from_db(experiment_id)
            if experiment:
                self._experiments_cache[experiment_id] = experiment
            return experiment

        return None

    def _should_include_call(
        self,
        experiment: VoiceExperiment,
        caller_phone: str,
        call_context: Optional[Dict]
    ) -> bool:
        """Check if call should be included in experiment"""
        # Random sampling based on target_percentage
        if experiment.target_percentage < 100.0:
            hash_input = f"{experiment.id}:{caller_phone}"
            hash_value = int(hashlib.md5(hash_input.encode()).hexdigest(), 16)
            if (hash_value % 100) >= experiment.target_percentage:
                return False

        # Phone pattern targeting
        if experiment.target_phone_patterns and call_context:
            caller_area = call_context.get("area_code")
            caller_state = call_context.get("state")

            matched = False
            for pattern in experiment.target_phone_patterns:
                if pattern.startswith("area_code:") and caller_area:
                    if pattern.split(":")[1] == caller_area:
                        matched = True
                        break
                elif pattern.startswith("state:") and caller_state:
                    if pattern.split(":")[1].upper() == caller_state.upper():
                        matched = True
                        break

            if experiment.target_phone_patterns and not matched:
                return False

        # Time window targeting
        if experiment.target_time_windows:
            now = datetime.now()
            current_time = now.strftime("%H:%M")

            in_window = False
            for window in experiment.target_time_windows:
                start = window.get("start", "00:00")
                end = window.get("end", "23:59")
                if start <= current_time <= end:
                    in_window = True
                    break

            if not in_window:
                return False

        return True

    def _assign_variant(
        self,
        experiment: VoiceExperiment,
        caller_phone: str
    ) -> VoiceVariant:
        """Assign a variant to a caller using deterministic hashing"""
        # Deterministic assignment based on phone hash
        hash_input = f"{experiment.id}:{caller_phone}"
        hash_value = int(hashlib.md5(hash_input.encode()).hexdigest(), 16)
        random_value = (hash_value % 100000) / 1000.0  # 0-100

        # Select variant based on traffic allocation
        cumulative = 0.0
        selected_variant = experiment.variants[0]

        for variant in experiment.variants:
            cumulative += variant.traffic_allocation
            if random_value <= cumulative:
                selected_variant = variant
                break

        return selected_variant

    def _calculate_satisfaction_stats(self, results: List[VoiceExperimentResult]) -> Dict:
        """Calculate satisfaction statistics"""
        scores = [r.satisfaction_score for r in results if r.satisfaction_score is not None]
        if not scores:
            return {"avg": None, "count": 0}

        return {
            "avg": sum(scores) / len(scores),
            "min": min(scores),
            "max": max(scores),
            "count": len(scores)
        }

    def _calculate_significance(
        self,
        variant_stats: Dict,
        primary_metric: VoiceMetric
    ) -> Dict[str, Any]:
        """Calculate statistical significance between variants"""
        import math

        metric_key = primary_metric.value.replace("_rate", "_rate").replace("avg_", "avg_")

        # Find control variant
        control_stats = None
        control_id = None
        for vid, stats in variant_stats.items():
            if stats.get("is_control"):
                control_stats = stats
                control_id = vid
                break

        if not control_stats:
            return {"is_significant": False, "reason": "No control variant found"}

        # Compare each variant to control
        comparisons = {}
        for vid, stats in variant_stats.items():
            if vid == control_id:
                continue

            control_metric = control_stats["metrics"].get(metric_key, 0)
            variant_metric = stats["metrics"].get(metric_key, 0)

            control_n = control_stats["total_calls"]
            variant_n = stats["total_calls"]

            # Calculate lift
            if control_metric > 0:
                lift = ((variant_metric - control_metric) / control_metric) * 100
            else:
                lift = 0 if variant_metric == 0 else 100

            # Simple significance check (would use proper stats in production)
            # Using rough approximation based on sample size and effect size
            min_sample = min(control_n, variant_n)
            is_significant = min_sample >= 50 and abs(lift) >= 5

            comparisons[vid] = {
                "variant_name": stats["variant_name"],
                "control_value": round(control_metric, 2),
                "variant_value": round(variant_metric, 2),
                "lift_percent": round(lift, 2),
                "is_significant": is_significant
            }

        any_significant = any(c["is_significant"] for c in comparisons.values())

        return {
            "is_significant": any_significant,
            "metric_compared": metric_key,
            "comparisons": comparisons
        }

    def _determine_winner(
        self,
        variant_stats: Dict,
        primary_metric: VoiceMetric,
        significance: Dict,
        min_calls: int
    ) -> Optional[Dict]:
        """Determine winning variant"""
        if not significance.get("is_significant"):
            return None

        metric_key = primary_metric.value

        # Find best performing variant
        best_variant = None
        best_value = -1

        for vid, stats in variant_stats.items():
            if stats["total_calls"] < min_calls:
                continue

            value = stats["metrics"].get(metric_key, 0)
            if value > best_value:
                best_value = value
                best_variant = {
                    "variant_id": vid,
                    "variant_name": stats["variant_name"],
                    "metric_value": round(value, 2),
                    "total_calls": stats["total_calls"]
                }

        return best_variant

    def _get_time_breakdown(self, results: List[VoiceExperimentResult]) -> Dict:
        """Get results breakdown by time of day"""
        breakdown = {"morning": [], "afternoon": [], "evening": []}

        for result in results:
            if result.time_of_day in breakdown:
                breakdown[result.time_of_day].append(result)

        return {
            time: {
                "total_calls": len(calls),
                "success_rate": sum(1 for c in calls if c.call_success) / len(calls) * 100 if calls else 0,
                "booking_rate": sum(1 for c in calls if c.booking_made) / len(calls) * 100 if calls else 0
            }
            for time, calls in breakdown.items()
        }

    def _get_geographic_breakdown(self, results: List[VoiceExperimentResult]) -> Dict:
        """Get results breakdown by caller state"""
        by_state = {}

        for result in results:
            state = result.caller_state or "Unknown"
            if state not in by_state:
                by_state[state] = []
            by_state[state].append(result)

        return {
            state: {
                "total_calls": len(calls),
                "success_rate": sum(1 for c in calls if c.call_success) / len(calls) * 100 if calls else 0
            }
            for state, calls in by_state.items()
        }

    def _flush_results(self):
        """Flush buffered results to database"""
        if not self._results_buffer:
            return

        if self.db:
            self._persist_results(self._results_buffer)

        self._results_buffer = []

    def _persist_experiment(self, experiment: VoiceExperiment):
        """Persist experiment to database"""
        try:
            from sqlalchemy import text

            # Insert experiment
            self.db.execute(text("""
                INSERT INTO voice_experiments
                (id, name, description, experiment_type, primary_metric, secondary_metrics,
                 target_percentage, min_calls, confidence_level, status, created_at)
                VALUES (:id, :name, :desc, :type, :metric, :secondary, :target, :min, :conf, :status, :created)
            """), {
                "id": experiment.id,
                "name": experiment.name,
                "desc": experiment.description,
                "type": experiment.experiment_type.value,
                "metric": experiment.primary_metric.value,
                "secondary": ",".join(m.value for m in experiment.secondary_metrics),
                "target": experiment.target_percentage,
                "min": experiment.min_calls,
                "conf": experiment.confidence_level,
                "status": experiment.status,
                "created": datetime.now(timezone.utc)
            })

            # Insert variants
            for variant in experiment.variants:
                self.db.execute(text("""
                    INSERT INTO voice_experiment_variants
                    (id, experiment_id, name, is_control, traffic_allocation, config,
                     greeting_text, voice_id, speech_rate, script_template)
                    VALUES (:id, :exp_id, :name, :control, :traffic, :config, :greeting, :voice, :rate, :script)
                """), {
                    "id": variant.id,
                    "exp_id": experiment.id,
                    "name": variant.name,
                    "control": variant.is_control,
                    "traffic": variant.traffic_allocation,
                    "config": str(variant.config),
                    "greeting": variant.greeting_text,
                    "voice": variant.voice_id,
                    "rate": variant.speech_rate,
                    "script": variant.script_template
                })

            self.db.commit()
        except SQLAlchemyError as e:
            logger.error(f"Error persisting experiment: {e}")
            self.db.rollback()

    def _update_experiment_status(
        self,
        experiment_id: str,
        status: str,
        timestamp: datetime,
        winner_id: Optional[str] = None
    ):
        """Update experiment status in database"""
        try:
            from sqlalchemy import text

            if status == "running":
                self.db.execute(text("""
                    UPDATE voice_experiments
                    SET status = :status, started_at = :ts
                    WHERE id = :id
                """), {"id": experiment_id, "status": status, "ts": timestamp})
            else:
                self.db.execute(text("""
                    UPDATE voice_experiments
                    SET status = :status, ended_at = :ts, winning_variant_id = :winner
                    WHERE id = :id
                """), {"id": experiment_id, "status": status, "ts": timestamp, "winner": winner_id})

            self.db.commit()
        except SQLAlchemyError as e:
            logger.error(f"Error updating experiment status: {e}")
            self.db.rollback()

    def _persist_results(self, results: List[VoiceExperimentResult]):
        """Persist results to database"""
        try:
            from sqlalchemy import text

            for result in results:
                self.db.execute(text("""
                    INSERT INTO voice_experiment_results
                    (experiment_id, variant_id, call_id, caller_phone, timestamp,
                     call_success, booking_made, transferred, call_duration_seconds,
                     satisfaction_score, voicemail_left, callback_requested, escalated,
                     hang_up_early, time_of_day, day_of_week, caller_state)
                    VALUES (:exp, :var, :call, :phone, :ts, :success, :booking, :transfer,
                            :duration, :satisfaction, :voicemail, :callback, :escalated,
                            :hangup, :tod, :dow, :state)
                """), {
                    "exp": result.experiment_id,
                    "var": result.variant_id,
                    "call": result.call_id,
                    "phone": result.caller_phone,
                    "ts": result.timestamp,
                    "success": result.call_success,
                    "booking": result.booking_made,
                    "transfer": result.transferred,
                    "duration": result.call_duration_seconds,
                    "satisfaction": result.satisfaction_score,
                    "voicemail": result.voicemail_left,
                    "callback": result.callback_requested,
                    "escalated": result.escalated,
                    "hangup": result.hang_up_early,
                    "tod": result.time_of_day,
                    "dow": result.day_of_week,
                    "state": result.caller_state
                })

            self.db.commit()
        except SQLAlchemyError as e:
            logger.error(f"Error persisting results: {e}")
            self.db.rollback()

    def _load_experiment_from_db(self, experiment_id: str) -> Optional[VoiceExperiment]:
        """Load experiment from database"""
        # Implementation would load from database
        return None

    def _get_experiment_results(self, experiment_id: str) -> List[VoiceExperimentResult]:
        """Get all results for an experiment"""
        # Return buffered results for now (would also query database)
        return [r for r in self._results_buffer if r.experiment_id == experiment_id]


# Create singleton instance
voice_ab_testing_service = VoiceABTestingService()
