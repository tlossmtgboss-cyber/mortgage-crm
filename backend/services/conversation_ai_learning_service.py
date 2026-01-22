"""
Conversation AI Learning Service
Analyzes conversations to improve AI responses through continuous learning
Supports fine-tuning data generation, knowledge gap identification, and model versioning
"""
import logging
from typing import Optional, Dict, Any, List, Tuple
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass, field
from enum import Enum
import json
import hashlib

logger = logging.getLogger(__name__)


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


class ConversationAILearningService:
    """
    Service for continuous AI learning and improvement

    Features:
    - Analyze conversations to identify successes and failures
    - Generate fine-tuning datasets
    - Track knowledge gaps
    - Manage model versions
    - Provide improvement recommendations
    """

    def __init__(self, db_session=None, ai_client=None):
        self.db = db_session
        self.ai_client = ai_client
        self._training_examples: List[TrainingExample] = []
        self._knowledge_gaps: Dict[str, KnowledgeGap] = {}
        self._model_versions: Dict[str, ModelVersion] = {}

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

        # Store knowledge gaps
        for gap in analysis.knowledge_gaps_identified:
            self._record_knowledge_gap(gap, conversation_id, user_messages)

        # Generate training examples from successful conversations
        if analysis.quality_score >= 0.8:
            self._generate_training_examples(conversation_id, messages, analysis)

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
        Get training examples for fine-tuning

        Args:
            data_type: Filter by data type
            min_quality: Minimum quality score
            approved_only: Only include approved examples
            limit: Maximum examples to return

        Returns:
            List of training examples in fine-tuning format
        """
        examples = self._training_examples

        if data_type:
            examples = [e for e in examples if e.data_type == data_type]

        if min_quality > 0:
            examples = [e for e in examples if e.quality_score >= min_quality]

        if approved_only:
            examples = [e for e in examples if e.approved]

        examples = examples[:limit]

        # Format for fine-tuning
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
        Get identified knowledge gaps

        Args:
            status: Filter by status (open, in_progress, resolved)
            priority: Filter by priority (low, medium, high, critical)
            min_frequency: Minimum occurrence frequency

        Returns:
            List of knowledge gaps
        """
        gaps = list(self._knowledge_gaps.values())

        if status:
            gaps = [g for g in gaps if g.status == status]

        if priority:
            gaps = [g for g in gaps if g.priority == priority]

        gaps = [g for g in gaps if g.frequency >= min_frequency]

        # Sort by priority and frequency
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
        Mark a knowledge gap as resolved

        Args:
            gap_id: Knowledge gap ID
            resolution_content: Content to address the gap
            add_to_knowledge_base: Whether to add content to knowledge base

        Returns:
            Success status
        """
        if gap_id not in self._knowledge_gaps:
            return False

        gap = self._knowledge_gaps[gap_id]
        gap.status = "resolved"
        gap.resolved_at = datetime.now(timezone.utc)
        gap.suggested_content = resolution_content

        if add_to_knowledge_base:
            # Create training example from resolution
            example = TrainingExample(
                id=f"KG-{gap_id}",
                data_type=LearningDataType.KNOWLEDGE_UPDATE,
                input_text=gap.example_queries[0] if gap.example_queries else gap.topic,
                expected_output=resolution_content,
                context={"knowledge_gap_id": gap_id, "topic": gap.topic},
                quality_score=1.0,
                reviewed=True,
                approved=True
            )
            self._training_examples.append(example)

        logger.info(f"Resolved knowledge gap: {gap.topic}")
        return True

    def add_correction(
        self,
        original_query: str,
        incorrect_response: str,
        correct_response: str,
        explanation: Optional[str] = None,
        source_conversation_id: Optional[str] = None
    ) -> TrainingExample:
        """
        Add a correction for an incorrect AI response

        Args:
            original_query: The user's query
            incorrect_response: The AI's incorrect response
            correct_response: The correct response
            explanation: Why the correction is needed
            source_conversation_id: Original conversation ID

        Returns:
            Created training example
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

        self._training_examples.append(example)

        logger.info(f"Added correction: {example_id}")
        return example

    def get_improvement_report(
        self,
        days: int = 30
    ) -> Dict[str, Any]:
        """
        Get AI improvement report for the specified period

        Args:
            days: Number of days to analyze

        Returns:
            Report with metrics, trends, and recommendations
        """
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)

        # Filter recent data
        recent_examples = [
            e for e in self._training_examples
            if e.created_at >= cutoff
        ]

        recent_gaps = [
            g for g in self._knowledge_gaps.values()
            if g.created_at >= cutoff
        ]

        # Calculate metrics
        total_examples = len(recent_examples)
        approved_examples = len([e for e in recent_examples if e.approved])
        corrections_count = len([e for e in recent_examples if e.data_type == LearningDataType.CORRECTION])

        open_gaps = len([g for g in recent_gaps if g.status == "open"])
        resolved_gaps = len([g for g in recent_gaps if g.status == "resolved"])

        # Group gaps by topic for analysis
        gap_topics = {}
        for gap in recent_gaps:
            topic = gap.topic
            if topic not in gap_topics:
                gap_topics[topic] = 0
            gap_topics[topic] += gap.frequency

        # Sort topics by frequency
        top_gap_topics = sorted(
            gap_topics.items(),
            key=lambda x: x[1],
            reverse=True
        )[:10]

        # Training data by type
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

    def create_model_version(
        self,
        version: str,
        base_model: str,
        notes: str = ""
    ) -> ModelVersion:
        """
        Create a new model version for tracking

        Args:
            version: Version identifier (e.g., "v1.2.0")
            base_model: Base model identifier
            notes: Version notes

        Returns:
            Created model version
        """
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
        """
        Prepare a fine-tuning job for a model version

        Args:
            model_version: Target model version
            min_examples: Minimum examples required

        Returns:
            Fine-tuning job configuration or None if insufficient data
        """
        if model_version not in self._model_versions:
            logger.error(f"Model version {model_version} not found")
            return None

        # Get approved training examples
        dataset = self.get_training_dataset(
            approved_only=True,
            min_quality=0.8
        )

        if len(dataset) < min_examples:
            logger.warning(
                f"Insufficient training data: {len(dataset)} < {min_examples}"
            )
            return None

        # Update model version
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
        """
        Record performance metrics for a model version

        Args:
            model_version: Model version
            metrics: Performance metrics dict

        Returns:
            Success status
        """
        if model_version not in self._model_versions:
            return False

        model = self._model_versions[model_version]
        model.performance_metrics = metrics

        logger.info(f"Recorded metrics for {model_version}: {metrics}")
        return True

    def deploy_model_version(self, model_version: str) -> bool:
        """
        Mark a model version as deployed

        Args:
            model_version: Model version to deploy

        Returns:
            Success status
        """
        if model_version not in self._model_versions:
            return False

        # Retire currently deployed version
        for version, model in self._model_versions.items():
            if model.status == "deployed":
                model.status = "retired"

        # Deploy new version
        model = self._model_versions[model_version]
        model.status = "deployed"
        model.deployed_at = datetime.now(timezone.utc)

        logger.info(f"Deployed model version: {model_version}")
        return True

    # Private helper methods

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
            # Look for similar repeated queries
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

        # Look for "I don't know" type responses
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
                    # Find the corresponding user query
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

        # Pair user queries with AI responses
        for i in range(min(len(user_msgs), len(ai_msgs))):
            pairs.append({
                "input": user_msgs[i].get("content", ""),
                "output": ai_msgs[i].get("content", ""),
                "position": i
            })

        return pairs

    def _extract_failed_responses(self, messages: List[Dict]) -> List[Dict]:
        """Extract failed response pairs for analysis"""
        # Similar to successful, but flagged for review
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
        """Record or update a knowledge gap"""
        import uuid

        # Create hash for deduplication
        gap_hash = hashlib.md5(gap_description.lower().encode()).hexdigest()[:12]

        if gap_hash in self._knowledge_gaps:
            # Update existing gap
            gap = self._knowledge_gaps[gap_hash]
            gap.frequency += 1
            if user_messages:
                gap.example_queries.append(user_messages[0].get("content", "")[:200])
                gap.example_queries = gap.example_queries[-10:]  # Keep last 10
        else:
            # Create new gap
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

    def _generate_training_examples(
        self,
        conversation_id: str,
        messages: List[Dict],
        analysis: ConversationAnalysis
    ):
        """Generate training examples from successful conversation"""
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
                approved=False  # Requires review
            )
            self._training_examples.append(example)

    def _generate_improvement_recommendations(
        self,
        examples: List[TrainingExample],
        gaps: List[KnowledgeGap]
    ) -> List[str]:
        """Generate overall improvement recommendations"""
        recommendations = []

        # Check correction rate
        corrections = len([e for e in examples if e.data_type == LearningDataType.CORRECTION])
        if corrections > len(examples) * 0.1:
            recommendations.append(
                f"High correction rate ({corrections} corrections). "
                "Consider reviewing base model prompts."
            )

        # Check pending reviews
        pending = len([e for e in examples if not e.reviewed])
        if pending > 50:
            recommendations.append(
                f"{pending} training examples pending review. "
                "Schedule review session to improve training data."
            )

        # Check critical gaps
        critical_gaps = [g for g in gaps if g.priority == "critical"]
        if critical_gaps:
            recommendations.append(
                f"{len(critical_gaps)} critical knowledge gaps need immediate attention: "
                f"{', '.join(g.topic[:30] for g in critical_gaps[:3])}"
            )

        # Check for fine-tuning readiness
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
        # Rough estimate based on OpenAI pricing
        # ~$0.008 per 1K tokens, average example ~500 tokens
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
