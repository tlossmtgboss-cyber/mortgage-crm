"""
Conversation AI Learning Service
Analyzes conversations to improve AI responses through continuous learning
Supports fine-tuning data generation, knowledge gap identification, and model versioning

Persistence: All training examples, interaction patterns, and learned data are
persisted to PostgreSQL via the LearningExample, LearningPattern, and
AgentFeedback models.  A small in-memory cache (configurable size) keeps
hot data fast, but the DB is always the source of truth.
"""
import logging
from typing import Optional, Dict, Any, List, Tuple
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass, field
from enum import Enum
import json
import hashlib
import threading

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# In-memory cache size limits
# ---------------------------------------------------------------------------
_TRAINING_EXAMPLE_CACHE_SIZE = 20
_PATTERN_CACHE_TTL_SECONDS = 300  # 5 minutes


class ConversationOutcome(str, Enum):
    """Outcomes of AI conversations"""
    SUCCESS = "success"
    PARTIAL_SUCCESS = "partial_success"
    FAILURE = "failure"
    ESCALATED = "escalated"
    ABANDONED = "abandoned"
    UNKNOWN = "unknown"


class FailureReason(str, Enum):
    """Reasons for conversation failures"""
    KNOWLEDGE_GAP = "knowledge_gap"
    MISUNDERSTANDING = "misunderstanding"
    WRONG_ANSWER = "wrong_answer"
    HALLUCINATION = "hallucination"
    INAPPROPRIATE_TONE = "inappropriate_tone"
    SLOW_RESPONSE = "slow_response"
    TECHNICAL_ERROR = "technical_error"
    CALLER_FRUSTRATION = "caller_frustration"
    COMPLEX_QUERY = "complex_query"
    OUT_OF_SCOPE = "out_of_scope"


class LearningDataType(str, Enum):
    """Types of learning data"""
    POSITIVE_EXAMPLE = "positive_example"
    NEGATIVE_EXAMPLE = "negative_example"
    KNOWLEDGE_UPDATE = "knowledge_update"
    CORRECTION = "correction"
    NEW_INTENT = "new_intent"


@dataclass
class ConversationAnalysis:
    """Analysis of a conversation for learning purposes"""
    conversation_id: str
    timestamp: datetime
    outcome: ConversationOutcome
    quality_score: float  # 0-1
    caller_satisfaction: Optional[float] = None  # 0-5
    failure_reasons: List[FailureReason] = field(default_factory=list)
    knowledge_gaps_identified: List[str] = field(default_factory=list)
    successful_responses: List[Dict] = field(default_factory=list)
    failed_responses: List[Dict] = field(default_factory=list)
    extracted_intents: List[str] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)


@dataclass
class TrainingExample:
    """Training example for fine-tuning"""
    id: str
    data_type: LearningDataType
    input_text: str
    expected_output: str
    actual_output: Optional[str] = None
    context: Dict[str, Any] = field(default_factory=dict)
    source_conversation_id: Optional[str] = None
    quality_score: float = 1.0
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    reviewed: bool = False
    approved: bool = False


@dataclass
class KnowledgeGap:
    """Identified knowledge gap in the AI system"""
    id: str
    topic: str
    description: str
    frequency: int = 1  # How often this gap has been encountered
    example_queries: List[str] = field(default_factory=list)
    suggested_content: Optional[str] = None
    priority: str = "medium"  # low, medium, high, critical
    status: str = "open"  # open, in_progress, resolved
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    resolved_at: Optional[datetime] = None


@dataclass
class ModelVersion:
    """AI model version tracking"""
    version: str
    base_model: str
    fine_tuned: bool = False
    training_examples_count: int = 0
    performance_metrics: Dict[str, float] = field(default_factory=dict)
    deployed_at: Optional[datetime] = None
    status: str = "draft"  # draft, testing, deployed, retired
    notes: str = ""


# ---------------------------------------------------------------------------
# Mapping helpers: dataclass <-> DB model
# ---------------------------------------------------------------------------

def _data_type_to_example_type(data_type: LearningDataType) -> str:
    """Map LearningDataType enum to the example_type string stored in DB."""
    mapping = {
        LearningDataType.POSITIVE_EXAMPLE: "positive",
        LearningDataType.NEGATIVE_EXAMPLE: "negative",
        LearningDataType.KNOWLEDGE_UPDATE: "few_shot",
        LearningDataType.CORRECTION: "correction",
        LearningDataType.NEW_INTENT: "positive",
    }
    return mapping.get(data_type, "positive")


def _example_type_to_data_type(example_type: str) -> LearningDataType:
    """Map DB example_type string back to LearningDataType enum."""
    mapping = {
        "positive": LearningDataType.POSITIVE_EXAMPLE,
        "negative": LearningDataType.NEGATIVE_EXAMPLE,
        "few_shot": LearningDataType.KNOWLEDGE_UPDATE,
        "correction": LearningDataType.CORRECTION,
    }
    return mapping.get(example_type, LearningDataType.POSITIVE_EXAMPLE)


class ConversationAILearningService:
    """
    Service for continuous AI learning and improvement

    Features:
    - Analyze conversations to identify successes and failures
    - Generate fine-tuning datasets
    - Track knowledge gaps
    - Manage model versions
    - Provide improvement recommendations
    - Persist all learning data to PostgreSQL (LearningExample, LearningPattern)
    - Record and query user feedback (AgentFeedback)
    - Provide few-shot examples for prompt injection
    """

    def __init__(self, db_session=None, ai_client=None):
        self.db = db_session
        self.ai_client = ai_client

        # In-memory caches (backed by DB)
        self._training_examples: List[TrainingExample] = []
        self._knowledge_gaps: Dict[str, KnowledgeGap] = {}
        self._model_versions: Dict[str, ModelVersion] = {}

        # Pattern cache with TTL
        self._pattern_cache: Dict[str, Any] = {}
        self._pattern_cache_loaded_at: Optional[datetime] = None

        # Thread lock for cache access
        self._cache_lock = threading.Lock()

    # ------------------------------------------------------------------
    # DB session helpers
    # ------------------------------------------------------------------

    def _get_session(self):
        """
        Return the injected db_session if available, otherwise create a
        fresh one from SessionLocal.  Callers that create a fresh session
        MUST close it (use _safe_session context manager).
        """
        if self.db is not None:
            return self.db, False  # (session, is_owned)
        try:
            from db import SessionLocal
            return SessionLocal(), True
        except Exception as e:
            logger.warning("Cannot create DB session: %s", e)
            return None, False

    def _close_if_owned(self, session, owned: bool):
        """Close session only if we created it ourselves."""
        if owned and session is not None:
            try:
                session.close()
            except Exception as _exc:  # noqa: BLE001
                pass

    # ------------------------------------------------------------------
    # DB persistence helpers
    # ------------------------------------------------------------------

    def _persist_training_example(self, example: TrainingExample) -> None:
        """Write a TrainingExample dataclass to the learning_examples table."""
        session, owned = self._get_session()
        if session is None:
            return
        try:
            from database.models.learning_example import LearningExample as LearningExampleModel

            db_record = LearningExampleModel(
                example_type=_data_type_to_example_type(example.data_type),
                intent=example.context.get("intents", [None])[0]
                    if isinstance(example.context.get("intents"), list)
                    else example.context.get("intent"),
                agent_role=example.context.get("agent_role"),
                query_text=example.input_text,
                expected_response=example.expected_output,
                actual_response=example.actual_output,
                correction_notes=example.context.get("correction_reason"),
                quality_score=round(example.quality_score * 100, 2),  # 0-1 -> 0-100
                is_active=True,
                usage_count=0,
            )
            session.add(db_record)
            session.commit()
            logger.debug("Persisted training example %s to DB", example.id)
        except Exception as e:
            logger.warning("Failed to persist training example %s: %s", example.id, e)
            try:
                session.rollback()
            except Exception as _exc:  # noqa: BLE001
                pass
        finally:
            self._close_if_owned(session, owned)

    def _persist_knowledge_gap_as_pattern(self, gap: KnowledgeGap) -> None:
        """Write/upsert a KnowledgeGap as a LearningPattern record."""
        session, owned = self._get_session()
        if session is None:
            return
        try:
            from database.models.learning_example import LearningPattern as LearningPatternModel

            existing = (
                session.query(LearningPatternModel)
                .filter(
                    LearningPatternModel.pattern_type == "knowledge_gap",
                    LearningPatternModel.pattern_key == gap.id,
                )
                .first()
            )

            if existing:
                existing.occurrence_count = gap.frequency
                existing.last_seen_at = datetime.now(timezone.utc)
                existing.confidence = min(1.0, gap.frequency / 20.0)
                existing.extra_metadata = {
                    "topic": gap.topic,
                    "description": gap.description,
                    "priority": gap.priority,
                    "status": gap.status,
                    "example_queries": gap.example_queries[-5:],
                }
            else:
                record = LearningPatternModel(
                    pattern_type="knowledge_gap",
                    pattern_key=gap.id,
                    pattern_value=gap.description,
                    confidence=min(1.0, gap.frequency / 20.0),
                    occurrence_count=gap.frequency,
                    last_seen_at=datetime.now(timezone.utc),
                    is_active=True,
                    extra_metadata={
                        "topic": gap.topic,
                        "priority": gap.priority,
                        "status": gap.status,
                        "example_queries": gap.example_queries[-5:],
                    },
                )
                session.add(record)

            session.commit()
        except Exception as e:
            logger.warning("Failed to persist knowledge gap %s: %s", gap.id, e)
            try:
                session.rollback()
            except Exception as _exc:  # noqa: BLE001
                pass
        finally:
            self._close_if_owned(session, owned)

    def _persist_interaction_pattern(
        self,
        pattern_type: str,
        pattern_key: str,
        pattern_value: str,
        metadata: Optional[Dict] = None,
    ) -> None:
        """Upsert an interaction pattern in the learning_patterns table."""
        session, owned = self._get_session()
        if session is None:
            return
        try:
            from database.models.learning_example import LearningPattern as LearningPatternModel

            existing = (
                session.query(LearningPatternModel)
                .filter(
                    LearningPatternModel.pattern_type == pattern_type,
                    LearningPatternModel.pattern_key == pattern_key,
                )
                .first()
            )

            if existing:
                existing.occurrence_count = (existing.occurrence_count or 0) + 1
                existing.last_seen_at = datetime.now(timezone.utc)
                if metadata:
                    existing.extra_metadata = {**(existing.extra_metadata or {}), **metadata}
            else:
                record = LearningPatternModel(
                    pattern_type=pattern_type,
                    pattern_key=pattern_key,
                    pattern_value=pattern_value,
                    confidence=1.0,
                    occurrence_count=1,
                    last_seen_at=datetime.now(timezone.utc),
                    is_active=True,
                    extra_metadata=metadata,
                )
                session.add(record)

            session.commit()

            # Invalidate pattern cache
            self._pattern_cache_loaded_at = None
        except Exception as e:
            logger.warning(
                "Failed to persist interaction pattern %s/%s: %s",
                pattern_type, pattern_key, e,
            )
            try:
                session.rollback()
            except Exception as _exc:  # noqa: BLE001
                pass
        finally:
            self._close_if_owned(session, owned)

    def _load_training_examples_from_db(
        self,
        data_type: Optional[LearningDataType] = None,
        min_quality: float = 0.0,
        approved_only: bool = False,
        limit: int = 1000,
    ) -> List[Dict[str, Any]]:
        """Load training examples from the DB, returning dicts in fine-tuning format."""
        session, owned = self._get_session()
        if session is None:
            return []
        try:
            from database.models.learning_example import LearningExample as LearningExampleModel

            query = session.query(LearningExampleModel).filter(
                LearningExampleModel.is_active == True,  # noqa: E712
            )

            if data_type:
                db_type = _data_type_to_example_type(data_type)
                query = query.filter(LearningExampleModel.example_type == db_type)

            if min_quality > 0:
                # Convert 0-1 scale to 0-100 for DB comparison
                query = query.filter(
                    LearningExampleModel.quality_score >= round(min_quality * 100, 2)
                )

            # "approved" in the dataclass maps to quality_score >= 80 and is_active
            # since the DB model doesn't have separate approved/reviewed columns
            if approved_only:
                query = query.filter(
                    LearningExampleModel.quality_score >= 80.0,
                )

            query = query.order_by(LearningExampleModel.quality_score.desc())
            query = query.limit(limit)

            rows = query.all()

            results = []
            for row in rows:
                results.append({
                    "id": row.id,
                    "messages": [
                        {"role": "user", "content": row.query_text or ""},
                        {"role": "assistant", "content": row.expected_response or ""},
                    ],
                    "context": {
                        "intent": row.intent,
                        "agent_role": row.agent_role,
                        "example_type": row.example_type,
                    },
                    "quality_score": float(row.quality_score or 0) / 100.0,
                })
            return results
        except Exception as e:
            logger.warning("Failed to load training examples from DB: %s", e)
            return []
        finally:
            self._close_if_owned(session, owned)

    def _load_knowledge_gaps_from_db(
        self,
        status: Optional[str] = None,
        priority: Optional[str] = None,
        min_frequency: int = 1,
    ) -> List[KnowledgeGap]:
        """Load knowledge gaps (stored as LearningPattern type='knowledge_gap') from DB."""
        session, owned = self._get_session()
        if session is None:
            return []
        try:
            from database.models.learning_example import LearningPattern as LearningPatternModel

            query = (
                session.query(LearningPatternModel)
                .filter(
                    LearningPatternModel.pattern_type == "knowledge_gap",
                    LearningPatternModel.is_active == True,  # noqa: E712
                    LearningPatternModel.occurrence_count >= min_frequency,
                )
            )

            rows = query.all()

            gaps = []
            for row in rows:
                meta = row.extra_metadata or {}
                gap_status = meta.get("status", "open")
                gap_priority = meta.get("priority", "medium")

                if status and gap_status != status:
                    continue
                if priority and gap_priority != priority:
                    continue

                gaps.append(KnowledgeGap(
                    id=row.pattern_key,
                    topic=meta.get("topic", row.pattern_value[:100]),
                    description=row.pattern_value,
                    frequency=row.occurrence_count or 1,
                    example_queries=meta.get("example_queries", []),
                    priority=gap_priority,
                    status=gap_status,
                    created_at=row.created_at or datetime.now(timezone.utc),
                ))

            # Sort by priority and frequency
            priority_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
            gaps.sort(key=lambda g: (priority_order.get(g.priority, 4), -g.frequency))

            return gaps
        except Exception as e:
            logger.warning("Failed to load knowledge gaps from DB: %s", e)
            return []
        finally:
            self._close_if_owned(session, owned)

    # ------------------------------------------------------------------
    # Cache management
    # ------------------------------------------------------------------

    def _add_to_example_cache(self, example: TrainingExample) -> None:
        """Add a training example to the in-memory cache, evicting oldest if full."""
        with self._cache_lock:
            self._training_examples.append(example)
            if len(self._training_examples) > _TRAINING_EXAMPLE_CACHE_SIZE:
                self._training_examples = self._training_examples[-_TRAINING_EXAMPLE_CACHE_SIZE:]

    def _load_patterns_if_stale(self) -> Dict[str, Any]:
        """Load patterns from DB if cache is stale (older than TTL)."""
        now = datetime.now(timezone.utc)
        if (
            self._pattern_cache_loaded_at is not None
            and (now - self._pattern_cache_loaded_at).total_seconds() < _PATTERN_CACHE_TTL_SECONDS
        ):
            return self._pattern_cache

        session, owned = self._get_session()
        if session is None:
            return self._pattern_cache

        try:
            from database.models.learning_example import LearningPattern as LearningPatternModel

            rows = (
                session.query(LearningPatternModel)
                .filter(
                    LearningPatternModel.is_active == True,  # noqa: E712
                    LearningPatternModel.pattern_type != "knowledge_gap",
                )
                .order_by(LearningPatternModel.occurrence_count.desc())
                .limit(200)
                .all()
            )

            cache = {}
            for row in rows:
                key = f"{row.pattern_type}:{row.pattern_key}"
                cache[key] = {
                    "pattern_type": row.pattern_type,
                    "pattern_key": row.pattern_key,
                    "pattern_value": row.pattern_value,
                    "occurrence_count": row.occurrence_count,
                    "confidence": float(row.confidence or 0),
                    "last_seen_at": row.last_seen_at,
                    "metadata": row.extra_metadata,
                }

            with self._cache_lock:
                self._pattern_cache = cache
                self._pattern_cache_loaded_at = now

            return cache
        except Exception as e:
            logger.warning("Failed to load patterns from DB: %s", e)
            return self._pattern_cache
        finally:
            self._close_if_owned(session, owned)

    # ==================================================================
    # PUBLIC API — Original methods, now DB-backed
    # ==================================================================

    def analyze_conversation(
        self,
        conversation_id: str,
        messages: List[Dict[str, str]],
        outcome: ConversationOutcome,
        caller_satisfaction: Optional[float] = None,
        metadata: Optional[Dict] = None
    ) -> ConversationAnalysis:
        """
        Analyze a conversation for learning opportunities

        Args:
            conversation_id: Unique conversation ID
            messages: List of message dicts with 'role' and 'content'
            outcome: Final outcome of the conversation
            caller_satisfaction: Caller satisfaction score (0-5)
            metadata: Additional context (call duration, transfer, etc.)

        Returns:
            ConversationAnalysis with findings and recommendations
        """
        analysis = ConversationAnalysis(
            conversation_id=conversation_id,
            timestamp=datetime.now(timezone.utc),
            outcome=outcome,
            quality_score=0.0,
            caller_satisfaction=caller_satisfaction
        )

        # Analyze message pairs
        ai_messages = [m for m in messages if m.get("role") == "assistant"]
        user_messages = [m for m in messages if m.get("role") == "user"]

        # Calculate quality score
        quality_factors = []

        # Factor 1: Outcome-based
        outcome_scores = {
            ConversationOutcome.SUCCESS: 1.0,
            ConversationOutcome.PARTIAL_SUCCESS: 0.7,
            ConversationOutcome.ESCALATED: 0.5,
            ConversationOutcome.FAILURE: 0.2,
            ConversationOutcome.ABANDONED: 0.1,
            ConversationOutcome.UNKNOWN: 0.5
        }
        quality_factors.append(outcome_scores.get(outcome, 0.5))

        # Factor 2: Satisfaction-based
        if caller_satisfaction is not None:
            quality_factors.append(caller_satisfaction / 5.0)

        # Factor 3: Response quality indicators
        response_quality = self._assess_response_quality(ai_messages)
        quality_factors.append(response_quality)

        analysis.quality_score = sum(quality_factors) / len(quality_factors)

        # Identify failure reasons
        if outcome in [ConversationOutcome.FAILURE, ConversationOutcome.ABANDONED]:
            analysis.failure_reasons = self._identify_failure_reasons(messages, metadata)

        # Identify knowledge gaps
        analysis.knowledge_gaps_identified = self._identify_knowledge_gaps(messages)

        # Extract successful responses for positive training
        if analysis.quality_score >= 0.7:
            analysis.successful_responses = self._extract_successful_responses(messages)

        # Extract failed responses for analysis
        if analysis.quality_score < 0.5:
            analysis.failed_responses = self._extract_failed_responses(messages)

        # Extract intents for intent classification improvement
        analysis.extracted_intents = self._extract_intents(user_messages)

        # Generate recommendations
        analysis.recommendations = self._generate_recommendations(analysis)

        # Store knowledge gaps (in-memory + DB)
        for gap in analysis.knowledge_gaps_identified:
            self._record_knowledge_gap(gap, conversation_id, user_messages)

        # Generate training examples from successful conversations (in-memory + DB)
        if analysis.quality_score >= 0.8:
            self._generate_training_examples(conversation_id, messages, analysis)

        # Persist intent patterns to DB
        for intent in analysis.extracted_intents:
            self._persist_interaction_pattern(
                pattern_type="intent_mapping",
                pattern_key=intent,
                pattern_value=f"Detected in conversation {conversation_id}",
                metadata={
                    "conversation_id": conversation_id,
                    "outcome": outcome.value,
                    "quality_score": analysis.quality_score,
                },
            )

        logger.info(
            f"Analyzed conversation {conversation_id}: "
            f"outcome={outcome.value}, quality={analysis.quality_score:.2f}, "
            f"gaps={len(analysis.knowledge_gaps_identified)}"
        )

        return analysis

    def get_training_dataset(
        self,
        data_type: Optional[LearningDataType] = None,
        min_quality: float = 0.8,
        approved_only: bool = True,
        limit: int = 1000
    ) -> List[Dict[str, Any]]:
        """
        Get training examples for fine-tuning.

        Queries DB first. Falls back to in-memory cache if DB is unavailable.
        """
        # Try DB first
        db_results = self._load_training_examples_from_db(
            data_type=data_type,
            min_quality=min_quality,
            approved_only=approved_only,
            limit=limit,
        )
        if db_results:
            return db_results

        # Fallback to in-memory cache
        examples = self._training_examples

        if data_type:
            examples = [e for e in examples if e.data_type == data_type]

        if min_quality > 0:
            examples = [e for e in examples if e.quality_score >= min_quality]

        if approved_only:
            examples = [e for e in examples if e.approved]

        examples = examples[:limit]

        return [
            {
                "id": ex.id,
                "messages": [
                    {"role": "user", "content": ex.input_text},
                    {"role": "assistant", "content": ex.expected_output}
                ],
                "context": ex.context,
                "quality_score": ex.quality_score
            }
            for ex in examples
        ]

    def get_knowledge_gaps(
        self,
        status: Optional[str] = None,
        priority: Optional[str] = None,
        min_frequency: int = 1
    ) -> List[KnowledgeGap]:
        """
        Get identified knowledge gaps.

        Queries DB first. Falls back to in-memory cache if DB is unavailable.
        """
        # Try DB first
        db_gaps = self._load_knowledge_gaps_from_db(
            status=status,
            priority=priority,
            min_frequency=min_frequency,
        )
        if db_gaps:
            return db_gaps

        # Fallback to in-memory cache
        gaps = list(self._knowledge_gaps.values())

        if status:
            gaps = [g for g in gaps if g.status == status]

        if priority:
            gaps = [g for g in gaps if g.priority == priority]

        gaps = [g for g in gaps if g.frequency >= min_frequency]

        priority_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        gaps.sort(key=lambda g: (priority_order.get(g.priority, 4), -g.frequency))

        return gaps

    def resolve_knowledge_gap(
        self,
        gap_id: str,
        resolution_content: str,
        add_to_knowledge_base: bool = True
    ) -> bool:
        """
        Mark a knowledge gap as resolved.

        Updates both in-memory cache and DB.
        """
        # Update in-memory
        in_memory_found = gap_id in self._knowledge_gaps
        if in_memory_found:
            gap = self._knowledge_gaps[gap_id]
            gap.status = "resolved"
            gap.resolved_at = datetime.now(timezone.utc)
            gap.suggested_content = resolution_content

        # Update DB
        db_found = self._resolve_knowledge_gap_in_db(gap_id, resolution_content)

        if not in_memory_found and not db_found:
            return False

        if add_to_knowledge_base:
            topic = ""
            input_text = ""
            if in_memory_found:
                gap = self._knowledge_gaps[gap_id]
                topic = gap.topic
                input_text = gap.example_queries[0] if gap.example_queries else gap.topic
            else:
                input_text = gap_id
                topic = gap_id

            example = TrainingExample(
                id=f"KG-{gap_id}",
                data_type=LearningDataType.KNOWLEDGE_UPDATE,
                input_text=input_text,
                expected_output=resolution_content,
                context={"knowledge_gap_id": gap_id, "topic": topic},
                quality_score=1.0,
                reviewed=True,
                approved=True
            )
            self._add_to_example_cache(example)
            self._persist_training_example(example)

        logger.info(f"Resolved knowledge gap: {gap_id}")
        return True

    def _resolve_knowledge_gap_in_db(self, gap_id: str, resolution_content: str) -> bool:
        """Mark a knowledge gap pattern as resolved in the DB."""
        session, owned = self._get_session()
        if session is None:
            return False
        try:
            from database.models.learning_example import LearningPattern as LearningPatternModel

            pattern = (
                session.query(LearningPatternModel)
                .filter(
                    LearningPatternModel.pattern_type == "knowledge_gap",
                    LearningPatternModel.pattern_key == gap_id,
                )
                .first()
            )

            if not pattern:
                return False

            meta = pattern.extra_metadata or {}
            meta["status"] = "resolved"
            meta["resolved_at"] = datetime.now(timezone.utc).isoformat()
            meta["resolution_content"] = resolution_content
            pattern.extra_metadata = meta
            session.commit()
            return True
        except Exception as e:
            logger.warning("Failed to resolve knowledge gap %s in DB: %s", gap_id, e)
            try:
                session.rollback()
            except Exception as _exc:  # noqa: BLE001
                pass
            return False
        finally:
            self._close_if_owned(session, owned)

    def add_correction(
        self,
        original_query: str,
        incorrect_response: str,
        correct_response: str,
        explanation: Optional[str] = None,
        source_conversation_id: Optional[str] = None
    ) -> TrainingExample:
        """
        Add a correction for an incorrect AI response.

        Persists to both in-memory cache and DB.
        """
        import uuid
        example_id = f"CORR-{str(uuid.uuid4())[:8].upper()}"

        example = TrainingExample(
            id=example_id,
            data_type=LearningDataType.CORRECTION,
            input_text=original_query,
            expected_output=correct_response,
            actual_output=incorrect_response,
            context={
                "correction_reason": explanation,
                "original_response": incorrect_response
            },
            source_conversation_id=source_conversation_id,
            quality_score=1.0,
            reviewed=True,
            approved=True  # Corrections are pre-approved
        )

        self._add_to_example_cache(example)
        self._persist_training_example(example)

        logger.info(f"Added correction: {example_id}")
        return example

    def get_improvement_report(
        self,
        days: int = 30
    ) -> Dict[str, Any]:
        """
        Get AI improvement report for the specified period.

        Queries DB for data, falls back to in-memory cache.
        """
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)

        # Try DB-backed report
        db_report = self._build_improvement_report_from_db(days, cutoff)
        if db_report:
            return db_report

        # Fallback to in-memory
        recent_examples = [
            e for e in self._training_examples
            if e.created_at >= cutoff
        ]

        recent_gaps = [
            g for g in self._knowledge_gaps.values()
            if g.created_at >= cutoff
        ]

        total_examples = len(recent_examples)
        approved_examples = len([e for e in recent_examples if e.approved])
        corrections_count = len([e for e in recent_examples if e.data_type == LearningDataType.CORRECTION])

        open_gaps = len([g for g in recent_gaps if g.status == "open"])
        resolved_gaps = len([g for g in recent_gaps if g.status == "resolved"])

        gap_topics = {}
        for gap in recent_gaps:
            topic = gap.topic
            if topic not in gap_topics:
                gap_topics[topic] = 0
            gap_topics[topic] += gap.frequency

        top_gap_topics = sorted(
            gap_topics.items(),
            key=lambda x: x[1],
            reverse=True
        )[:10]

        by_type = {}
        for dtype in LearningDataType:
            by_type[dtype.value] = len([
                e for e in recent_examples if e.data_type == dtype
            ])

        return {
            "period_days": days,
            "summary": {
                "total_training_examples": total_examples,
                "approved_examples": approved_examples,
                "pending_review": total_examples - approved_examples,
                "corrections_added": corrections_count,
                "knowledge_gaps_identified": len(recent_gaps),
                "knowledge_gaps_resolved": resolved_gaps,
                "knowledge_gaps_open": open_gaps
            },
            "training_data_by_type": by_type,
            "top_knowledge_gap_topics": [
                {"topic": topic, "frequency": freq}
                for topic, freq in top_gap_topics
            ],
            "recommendations": self._generate_improvement_recommendations(
                recent_examples, recent_gaps
            ),
            "model_status": self._get_model_status()
        }

    def _build_improvement_report_from_db(
        self, days: int, cutoff: datetime
    ) -> Optional[Dict[str, Any]]:
        """Build improvement report from DB data."""
        session, owned = self._get_session()
        if session is None:
            return None
        try:
            from database.models.learning_example import (
                LearningExample as LearningExampleModel,
                LearningPattern as LearningPatternModel,
            )
            from sqlalchemy import func

            # Count training examples by type
            type_counts = (
                session.query(
                    LearningExampleModel.example_type,
                    func.count(LearningExampleModel.id),
                )
                .filter(LearningExampleModel.created_at >= cutoff)
                .group_by(LearningExampleModel.example_type)
                .all()
            )

            total_examples = sum(c for _, c in type_counts)
            if total_examples == 0:
                return None  # Fall back to in-memory

            type_map = dict(type_counts)

            # Count approved (quality >= 80)
            approved_count = (
                session.query(func.count(LearningExampleModel.id))
                .filter(
                    LearningExampleModel.created_at >= cutoff,
                    LearningExampleModel.quality_score >= 80.0,
                )
                .scalar()
            ) or 0

            # Count knowledge gaps
            gap_patterns = (
                session.query(LearningPatternModel)
                .filter(
                    LearningPatternModel.pattern_type == "knowledge_gap",
                    LearningPatternModel.created_at >= cutoff,
                )
                .all()
            )

            open_gaps = 0
            resolved_gaps = 0
            gap_topics = {}
            for gp in gap_patterns:
                meta = gp.extra_metadata or {}
                st = meta.get("status", "open")
                if st == "resolved":
                    resolved_gaps += 1
                else:
                    open_gaps += 1
                topic = meta.get("topic", gp.pattern_value[:50])
                gap_topics[topic] = gap_topics.get(topic, 0) + (gp.occurrence_count or 1)

            top_gap_topics = sorted(
                gap_topics.items(), key=lambda x: x[1], reverse=True
            )[:10]

            corrections_count = type_map.get("correction", 0)

            by_type = {}
            for dtype in LearningDataType:
                db_key = _data_type_to_example_type(dtype)
                by_type[dtype.value] = type_map.get(db_key, 0)

            return {
                "period_days": days,
                "summary": {
                    "total_training_examples": total_examples,
                    "approved_examples": approved_count,
                    "pending_review": total_examples - approved_count,
                    "corrections_added": corrections_count,
                    "knowledge_gaps_identified": len(gap_patterns),
                    "knowledge_gaps_resolved": resolved_gaps,
                    "knowledge_gaps_open": open_gaps,
                },
                "training_data_by_type": by_type,
                "top_knowledge_gap_topics": [
                    {"topic": topic, "frequency": freq}
                    for topic, freq in top_gap_topics
                ],
                "recommendations": self._generate_improvement_recommendations([], []),
                "model_status": self._get_model_status(),
            }
        except Exception as e:
            logger.warning("Failed to build improvement report from DB: %s", e)
            return None
        finally:
            self._close_if_owned(session, owned)

    def create_model_version(
        self,
        version: str,
        base_model: str,
        notes: str = ""
    ) -> ModelVersion:
        """Create a new model version for tracking"""
        model = ModelVersion(
            version=version,
            base_model=base_model,
            notes=notes,
            status="draft"
        )

        self._model_versions[version] = model

        logger.info(f"Created model version: {version}")
        return model

    def prepare_fine_tuning_job(
        self,
        model_version: str,
        min_examples: int = 100
    ) -> Optional[Dict[str, Any]]:
        """Prepare a fine-tuning job for a model version"""
        if model_version not in self._model_versions:
            logger.error(f"Model version {model_version} not found")
            return None

        dataset = self.get_training_dataset(
            approved_only=True,
            min_quality=0.8
        )

        if len(dataset) < min_examples:
            logger.warning(
                f"Insufficient training data: {len(dataset)} < {min_examples}"
            )
            return None

        model = self._model_versions[model_version]
        model.training_examples_count = len(dataset)
        model.status = "preparing"

        return {
            "model_version": model_version,
            "base_model": model.base_model,
            "training_examples": len(dataset),
            "dataset": dataset,
            "estimated_cost": self._estimate_fine_tuning_cost(len(dataset)),
            "validation_split": 0.1,
            "hyperparameters": {
                "n_epochs": 3,
                "batch_size": "auto",
                "learning_rate_multiplier": "auto"
            }
        }

    def record_model_performance(
        self,
        model_version: str,
        metrics: Dict[str, float]
    ) -> bool:
        """Record performance metrics for a model version"""
        if model_version not in self._model_versions:
            return False

        model = self._model_versions[model_version]
        model.performance_metrics = metrics

        logger.info(f"Recorded metrics for {model_version}: {metrics}")
        return True

    def deploy_model_version(self, model_version: str) -> bool:
        """Mark a model version as deployed"""
        if model_version not in self._model_versions:
            return False

        for version, model in self._model_versions.items():
            if model.status == "deployed":
                model.status = "retired"

        model = self._model_versions[model_version]
        model.status = "deployed"
        model.deployed_at = datetime.now(timezone.utc)

        logger.info(f"Deployed model version: {model_version}")
        return True

    # ==================================================================
    # NEW PUBLIC API — Feedback integration and few-shot retrieval
    # ==================================================================

    def record_feedback(
        self,
        conversation_id: str,
        message_index: Optional[int],
        rating: str,
        feedback_text: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
        organization_id: Optional[int] = None,
        user_id: Optional[int] = None,
    ) -> Optional[int]:
        """
        Record user feedback on an AI response.

        Creates an AgentFeedback record in the DB and, depending on rating,
        generates a LearningExample (positive or negative).

        Args:
            conversation_id: The conversation this feedback belongs to.
            message_index: Index of the message within the conversation.
            rating: 'positive', 'negative', or 'neutral'.
            feedback_text: Optional free-text feedback from the user.
            context: Dict with optional keys: agent_role, intent,
                     query_text, response_text, tools_used,
                     response_time_ms, token_count.
            organization_id: Tenant ID.
            user_id: User who gave the feedback.

        Returns:
            The AgentFeedback.id if persisted, else None.
        """
        session, owned = self._get_session()
        if session is None:
            logger.warning("record_feedback: no DB session available")
            return None

        ctx = context or {}
        feedback_id = None

        try:
            from database.models.agent_feedback import AgentFeedback as AgentFeedbackModel
            from database.models.learning_example import LearningExample as LearningExampleModel

            fb = AgentFeedbackModel(
                organization_id=organization_id or 0,
                user_id=user_id or 0,
                conversation_id=conversation_id,
                message_index=message_index,
                rating=rating,
                feedback_text=feedback_text,
                agent_role=ctx.get("agent_role"),
                intent=ctx.get("intent"),
                query_text=ctx.get("query_text"),
                response_text=ctx.get("response_text"),
                tools_used=ctx.get("tools_used"),
                response_time_ms=ctx.get("response_time_ms"),
                token_count=ctx.get("token_count"),
            )
            session.add(fb)
            session.flush()  # Get the ID
            feedback_id = fb.id

            # Create corresponding LearningExample
            query_text = ctx.get("query_text", "")
            response_text = ctx.get("response_text", "")

            if query_text and rating in ("positive", "negative"):
                example_type = "positive" if rating == "positive" else "negative"
                quality = 90.0 if rating == "positive" else 20.0

                le = LearningExampleModel(
                    organization_id=organization_id,
                    example_type=example_type,
                    intent=ctx.get("intent"),
                    agent_role=ctx.get("agent_role"),
                    query_text=query_text,
                    expected_response=response_text if rating == "positive" else None,
                    actual_response=response_text if rating == "negative" else None,
                    correction_notes=feedback_text if rating == "negative" else None,
                    feedback_id=feedback_id,
                    quality_score=quality,
                    is_active=True,
                    usage_count=0,
                )
                session.add(le)

            session.commit()
            logger.info(
                "Recorded feedback %s (rating=%s) for conversation %s",
                feedback_id, rating, conversation_id,
            )
            return feedback_id

        except Exception as e:
            logger.warning("Failed to record feedback: %s", e)
            try:
                session.rollback()
            except Exception as _exc:  # noqa: BLE001
                pass
            return None
        finally:
            self._close_if_owned(session, owned)

    def get_improvement_suggestions(
        self,
        agent_role: str,
        days: int = 30,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """
        Query recent negative feedback for a given agent role and return
        actionable improvement suggestions grouped by common patterns.

        Args:
            agent_role: The agent role to analyze.
            days: Lookback window in days.
            limit: Max suggestions to return.

        Returns:
            List of dicts with keys: pattern, count, sample_feedback, suggestion.
        """
        session, owned = self._get_session()
        if session is None:
            return []

        try:
            from database.models.agent_feedback import AgentFeedback as AgentFeedbackModel
            from sqlalchemy import func

            cutoff = datetime.now(timezone.utc) - timedelta(days=days)

            # Get recent negative feedback for this role
            rows = (
                session.query(AgentFeedbackModel)
                .filter(
                    AgentFeedbackModel.agent_role == agent_role,
                    AgentFeedbackModel.rating == "negative",
                    AgentFeedbackModel.created_at >= cutoff,
                )
                .order_by(AgentFeedbackModel.created_at.desc())
                .limit(200)
                .all()
            )

            if not rows:
                return []

            # Group by intent (most common dimension for patterns)
            by_intent: Dict[str, List] = {}
            for row in rows:
                key = row.intent or "unknown"
                if key not in by_intent:
                    by_intent[key] = []
                by_intent[key].append(row)

            suggestions = []
            for intent, feedback_rows in sorted(
                by_intent.items(), key=lambda x: -len(x[1])
            ):
                count = len(feedback_rows)
                sample_texts = [
                    r.feedback_text for r in feedback_rows[:3]
                    if r.feedback_text
                ]
                sample_queries = [
                    r.query_text for r in feedback_rows[:3]
                    if r.query_text
                ]

                # Generate suggestion based on pattern
                if count >= 5:
                    suggestion = (
                        f"High-frequency failure (n={count}) on intent '{intent}'. "
                        f"Review prompt instructions and tool descriptions for this intent."
                    )
                elif sample_texts:
                    suggestion = (
                        f"Users report: {'; '.join(sample_texts[:2])}. "
                        f"Consider adding training examples or adjusting the system prompt."
                    )
                else:
                    suggestion = (
                        f"Recurring negative feedback (n={count}) on intent '{intent}'. "
                        f"Investigate response quality."
                    )

                suggestions.append({
                    "pattern": intent,
                    "count": count,
                    "sample_feedback": sample_texts[:3],
                    "sample_queries": sample_queries[:3],
                    "suggestion": suggestion,
                })

                if len(suggestions) >= limit:
                    break

            return suggestions

        except Exception as e:
            logger.warning("Failed to get improvement suggestions: %s", e)
            return []
        finally:
            self._close_if_owned(session, owned)

    def get_few_shot_examples(
        self,
        intent: str,
        agent_role: Optional[str] = None,
        limit: int = 3,
    ) -> List[Dict[str, Any]]:
        """
        Retrieve high-quality examples for few-shot prompt injection.

        Queries LearningExample records where type is 'positive' or 'few_shot',
        filtered by intent and optionally agent_role.  Orders by quality_score
        DESC, usage_count ASC (prefer high quality, less used).  Updates
        usage_count and last_used_at on selected examples.

        Args:
            intent: The intent to match (e.g. 'check_pipeline').
            agent_role: Optional agent role filter.
            limit: Number of examples to return (default 3).

        Returns:
            List of dicts with keys: query, response, quality_score.
        """
        session, owned = self._get_session()
        if session is None:
            return []

        try:
            from database.models.learning_example import LearningExample as LearningExampleModel

            query = (
                session.query(LearningExampleModel)
                .filter(
                    LearningExampleModel.is_active == True,  # noqa: E712
                    LearningExampleModel.example_type.in_(["positive", "few_shot"]),
                    LearningExampleModel.intent == intent,
                )
            )

            if agent_role:
                query = query.filter(LearningExampleModel.agent_role == agent_role)

            query = query.order_by(
                LearningExampleModel.quality_score.desc(),
                LearningExampleModel.usage_count.asc(),
            )

            rows = query.limit(limit).all()

            results = []
            now = datetime.now(timezone.utc)

            for row in rows:
                results.append({
                    "query": row.query_text,
                    "response": row.expected_response or row.actual_response or "",
                    "quality_score": float(row.quality_score or 0) / 100.0,
                })

                # Update usage tracking
                row.usage_count = (row.usage_count or 0) + 1
                row.last_used_at = now

            if rows:
                try:
                    session.commit()
                except Exception as e:
                    logger.debug("Failed to update usage counts: %s", e)
                    try:
                        session.rollback()
                    except Exception as _exc:  # noqa: BLE001
                        pass

            return results

        except Exception as e:
            logger.warning("Failed to get few-shot examples: %s", e)
            return []
        finally:
            self._close_if_owned(session, owned)

    # ==================================================================
    # Private helper methods
    # ==================================================================

    def _assess_response_quality(self, ai_messages: List[Dict]) -> float:
        """Assess quality of AI responses"""
        if not ai_messages:
            return 0.5

        quality_scores = []

        for msg in ai_messages:
            content = msg.get("content", "")
            score = 1.0

            # Penalize very short responses
            if len(content) < 50:
                score -= 0.2

            # Penalize very long responses
            if len(content) > 1000:
                score -= 0.1

            # Check for uncertainty markers
            uncertainty_markers = ["i'm not sure", "i don't know", "i cannot", "i'm unable"]
            for marker in uncertainty_markers:
                if marker in content.lower():
                    score -= 0.15

            # Check for apologies (may indicate problems)
            if "sorry" in content.lower() or "apologize" in content.lower():
                score -= 0.1

            quality_scores.append(max(0.0, min(1.0, score)))

        return sum(quality_scores) / len(quality_scores)

    def _identify_failure_reasons(
        self,
        messages: List[Dict],
        metadata: Optional[Dict]
    ) -> List[FailureReason]:
        """Identify reasons for conversation failure"""
        reasons = []

        ai_messages = [m for m in messages if m.get("role") == "assistant"]
        user_messages = [m for m in messages if m.get("role") == "user"]

        # Check for knowledge gaps
        uncertainty_phrases = ["don't have information", "not sure", "cannot answer", "outside my knowledge"]
        for msg in ai_messages:
            content = msg.get("content", "").lower()
            for phrase in uncertainty_phrases:
                if phrase in content:
                    reasons.append(FailureReason.KNOWLEDGE_GAP)
                    break

        # Check for repeated questions (misunderstanding)
        if len(user_messages) > 3:
            queries = [m.get("content", "").lower() for m in user_messages]
            for i, q in enumerate(queries[:-1]):
                for next_q in queries[i+1:]:
                    if self._similarity(q, next_q) > 0.7:
                        reasons.append(FailureReason.MISUNDERSTANDING)
                        break

        # Check for frustration indicators
        frustration_markers = ["this isn't helping", "you're not understanding", "can I speak to someone", "human"]
        for msg in user_messages:
            content = msg.get("content", "").lower()
            for marker in frustration_markers:
                if marker in content:
                    reasons.append(FailureReason.CALLER_FRUSTRATION)
                    break

        # Check metadata for technical issues
        if metadata:
            if metadata.get("response_time_ms", 0) > 5000:
                reasons.append(FailureReason.SLOW_RESPONSE)
            if metadata.get("error_occurred"):
                reasons.append(FailureReason.TECHNICAL_ERROR)

        return list(set(reasons))  # Deduplicate

    def _identify_knowledge_gaps(self, messages: List[Dict]) -> List[str]:
        """Identify knowledge gaps from conversation"""
        gaps = []

        ai_messages = [m for m in messages if m.get("role") == "assistant"]
        user_messages = [m for m in messages if m.get("role") == "user"]

        gap_indicators = [
            "don't have specific information",
            "unable to provide",
            "would need to check",
            "not in my knowledge",
            "beyond my current knowledge"
        ]

        for i, msg in enumerate(ai_messages):
            content = msg.get("content", "").lower()
            for indicator in gap_indicators:
                if indicator in content:
                    if i < len(user_messages):
                        query = user_messages[i].get("content", "")
                        gaps.append(f"Unable to answer: {query[:100]}")
                    break

        return gaps

    def _extract_successful_responses(self, messages: List[Dict]) -> List[Dict]:
        """Extract successful response pairs for training"""
        pairs = []

        user_msgs = [m for m in messages if m.get("role") == "user"]
        ai_msgs = [m for m in messages if m.get("role") == "assistant"]

        for i in range(min(len(user_msgs), len(ai_msgs))):
            pairs.append({
                "input": user_msgs[i].get("content", ""),
                "output": ai_msgs[i].get("content", ""),
                "position": i
            })

        return pairs

    def _extract_failed_responses(self, messages: List[Dict]) -> List[Dict]:
        """Extract failed response pairs for analysis"""
        pairs = self._extract_successful_responses(messages)
        for pair in pairs:
            pair["needs_correction"] = True
        return pairs

    def _extract_intents(self, user_messages: List[Dict]) -> List[str]:
        """Extract user intents from messages"""
        intents = []

        intent_keywords = {
            "rate_inquiry": ["rate", "interest", "apr", "points"],
            "application_status": ["status", "application", "where is", "update"],
            "document_request": ["document", "need to submit", "upload", "paperwork"],
            "appointment_booking": ["schedule", "appointment", "meet", "call back"],
            "loan_amount": ["how much", "qualify", "approved for", "afford"],
            "general_inquiry": ["question", "help", "information", "explain"]
        }

        for msg in user_messages:
            content = msg.get("content", "").lower()
            for intent, keywords in intent_keywords.items():
                if any(kw in content for kw in keywords):
                    intents.append(intent)

        return list(set(intents))

    def _generate_recommendations(self, analysis: ConversationAnalysis) -> List[str]:
        """Generate improvement recommendations"""
        recommendations = []

        if FailureReason.KNOWLEDGE_GAP in analysis.failure_reasons:
            recommendations.append(
                "Add content to knowledge base for: " +
                ", ".join(analysis.knowledge_gaps_identified[:3])
            )

        if FailureReason.MISUNDERSTANDING in analysis.failure_reasons:
            recommendations.append(
                "Improve intent classification for ambiguous queries"
            )

        if FailureReason.CALLER_FRUSTRATION in analysis.failure_reasons:
            recommendations.append(
                "Review escalation triggers - consider lowering threshold"
            )

        if analysis.quality_score < 0.5:
            recommendations.append(
                "Review this conversation for training data corrections"
            )

        if len(analysis.extracted_intents) > 3:
            recommendations.append(
                "Complex multi-intent query - consider improving query decomposition"
            )

        return recommendations

    def _record_knowledge_gap(
        self,
        gap_description: str,
        conversation_id: str,
        user_messages: List[Dict]
    ):
        """Record or update a knowledge gap (in-memory + DB)"""
        import uuid

        gap_hash = hashlib.md5(gap_description.lower().encode()).hexdigest()[:12]

        if gap_hash in self._knowledge_gaps:
            gap = self._knowledge_gaps[gap_hash]
            gap.frequency += 1
            if user_messages:
                gap.example_queries.append(user_messages[0].get("content", "")[:200])
                gap.example_queries = gap.example_queries[-10:]
        else:
            gap = KnowledgeGap(
                id=gap_hash,
                topic=gap_description[:100],
                description=gap_description,
                example_queries=[
                    user_messages[0].get("content", "")[:200]
                ] if user_messages else [],
                priority="medium"
            )
            self._knowledge_gaps[gap_hash] = gap

        # Update priority based on frequency
        if gap.frequency >= 10:
            gap.priority = "critical"
        elif gap.frequency >= 5:
            gap.priority = "high"

        # Persist to DB
        self._persist_knowledge_gap_as_pattern(gap)

    def _generate_training_examples(
        self,
        conversation_id: str,
        messages: List[Dict],
        analysis: ConversationAnalysis
    ):
        """Generate training examples from successful conversation (in-memory + DB)"""
        import uuid

        for resp in analysis.successful_responses:
            example = TrainingExample(
                id=f"TE-{str(uuid.uuid4())[:8].upper()}",
                data_type=LearningDataType.POSITIVE_EXAMPLE,
                input_text=resp["input"],
                expected_output=resp["output"],
                context={"intents": analysis.extracted_intents},
                source_conversation_id=conversation_id,
                quality_score=analysis.quality_score,
                reviewed=False,
                approved=False
            )
            self._add_to_example_cache(example)
            self._persist_training_example(example)

    def _generate_improvement_recommendations(
        self,
        examples: List[TrainingExample],
        gaps: List[KnowledgeGap]
    ) -> List[str]:
        """Generate overall improvement recommendations"""
        recommendations = []

        corrections = len([e for e in examples if e.data_type == LearningDataType.CORRECTION])
        if examples and corrections > len(examples) * 0.1:
            recommendations.append(
                f"High correction rate ({corrections} corrections). "
                "Consider reviewing base model prompts."
            )

        pending = len([e for e in examples if not e.reviewed])
        if pending > 50:
            recommendations.append(
                f"{pending} training examples pending review. "
                "Schedule review session to improve training data."
            )

        critical_gaps = [g for g in gaps if g.priority == "critical"]
        if critical_gaps:
            recommendations.append(
                f"{len(critical_gaps)} critical knowledge gaps need immediate attention: "
                f"{', '.join(g.topic[:30] for g in critical_gaps[:3])}"
            )

        approved = len([e for e in examples if e.approved])
        if approved >= 100:
            recommendations.append(
                f"Sufficient training data ({approved} examples). "
                "Consider scheduling a fine-tuning job."
            )

        return recommendations

    def _get_model_status(self) -> Dict[str, Any]:
        """Get current model deployment status"""
        deployed = None
        for version, model in self._model_versions.items():
            if model.status == "deployed":
                deployed = {
                    "version": version,
                    "deployed_at": model.deployed_at.isoformat() if model.deployed_at else None,
                    "performance_metrics": model.performance_metrics
                }
                break

        return {
            "deployed_version": deployed,
            "total_versions": len(self._model_versions),
            "versions": [
                {
                    "version": v.version,
                    "status": v.status,
                    "base_model": v.base_model
                }
                for v in self._model_versions.values()
            ]
        }

    def _estimate_fine_tuning_cost(self, example_count: int) -> float:
        """Estimate fine-tuning cost"""
        tokens_per_example = 500
        total_tokens = example_count * tokens_per_example
        cost_per_1k = 0.008

        return (total_tokens / 1000) * cost_per_1k * 3  # 3 epochs

    def _similarity(self, text1: str, text2: str) -> float:
        """Calculate simple text similarity"""
        words1 = set(text1.lower().split())
        words2 = set(text2.lower().split())

        if not words1 or not words2:
            return 0.0

        intersection = words1.intersection(words2)
        union = words1.union(words2)

        return len(intersection) / len(union)


# Create singleton instance
conversation_ai_learning_service = ConversationAILearningService()
