"""
Call Quality Assurance Service
Human review dashboard, AI performance scoring, and call quality ratings
Supports automated QA scoring and manual review workflows
"""
import logging
from typing import Optional, Dict, Any, List, Tuple
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass, field
from enum import Enum
import statistics

logger = logging.getLogger(__name__)


class QAStatus(str, Enum):
    """Status of QA review"""
    PENDING = "pending"
    IN_REVIEW = "in_review"
    REVIEWED = "reviewed"
    DISPUTED = "disputed"
    APPROVED = "approved"


class CallOutcome(str, Enum):
    """Outcome classification for calls"""
    SUCCESSFUL = "successful"
    PARTIAL_SUCCESS = "partial_success"
    ESCALATED = "escalated"
    ABANDONED = "abandoned"
    FAILED = "failed"
    VOICEMAIL = "voicemail"


class QACriteria(str, Enum):
    """Quality assurance scoring criteria"""
    GREETING_QUALITY = "greeting_quality"
    ACTIVE_LISTENING = "active_listening"
    PROBLEM_RESOLUTION = "problem_resolution"
    PRODUCT_KNOWLEDGE = "product_knowledge"
    COMMUNICATION_CLARITY = "communication_clarity"
    EMPATHY_RAPPORT = "empathy_rapport"
    COMPLIANCE_ADHERENCE = "compliance_adherence"
    CALL_CONTROL = "call_control"
    CLOSING_TECHNIQUE = "closing_technique"
    OVERALL_PROFESSIONALISM = "overall_professionalism"


@dataclass
class QAScorecard:
    """Scorecard for QA evaluation"""
    id: str
    call_id: str
    evaluated_by: Optional[str] = None  # User ID or "AI" for automated
    evaluation_type: str = "ai"  # ai, human, hybrid
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    # Individual scores (1-5 scale)
    scores: Dict[str, float] = field(default_factory=dict)

    # Weighted overall score
    overall_score: float = 0.0

    # Comments and feedback
    strengths: List[str] = field(default_factory=list)
    improvements: List[str] = field(default_factory=list)
    critical_issues: List[str] = field(default_factory=list)
    notes: str = ""

    # Status
    status: QAStatus = QAStatus.PENDING


@dataclass
class CallReview:
    """Call review record for human QA"""
    id: str
    call_id: str
    call_date: datetime
    duration_seconds: int
    caller_phone: str
    caller_name: Optional[str] = None
    outcome: CallOutcome = CallOutcome.SUCCESSFUL
    ai_score: Optional[float] = None
    human_score: Optional[float] = None
    assigned_reviewer: Optional[str] = None
    status: QAStatus = QAStatus.PENDING
    priority: int = 1  # 1=low, 2=medium, 3=high
    flags: List[str] = field(default_factory=list)
    transcript_url: Optional[str] = None
    recording_url: Optional[str] = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    reviewed_at: Optional[datetime] = None


@dataclass
class QABenchmark:
    """Performance benchmark for AI"""
    metric: str
    target: float
    current: float
    trend: str  # up, down, stable
    period_days: int


class CallQualityAssuranceService:
    """
    Service for call quality assurance and AI performance monitoring

    Features:
    - Automated AI call scoring
    - Human review workflow
    - Configurable scoring criteria with weights
    - Performance benchmarking
    - Calibration between AI and human scores
    - Dispute resolution workflow
    """

    def __init__(self, db_session=None, ai_client=None):
        self.db = db_session
        self.ai_client = ai_client
        self._scorecards: Dict[str, QAScorecard] = {}
        self._reviews: Dict[str, CallReview] = {}
        self._reviewers: Dict[str, Dict] = {}

        # Default criteria weights (must sum to 1.0)
        self._criteria_weights = {
            QACriteria.GREETING_QUALITY: 0.10,
            QACriteria.ACTIVE_LISTENING: 0.12,
            QACriteria.PROBLEM_RESOLUTION: 0.15,
            QACriteria.PRODUCT_KNOWLEDGE: 0.12,
            QACriteria.COMMUNICATION_CLARITY: 0.12,
            QACriteria.EMPATHY_RAPPORT: 0.10,
            QACriteria.COMPLIANCE_ADHERENCE: 0.12,
            QACriteria.CALL_CONTROL: 0.07,
            QACriteria.CLOSING_TECHNIQUE: 0.05,
            QACriteria.OVERALL_PROFESSIONALISM: 0.05
        }

        # Score thresholds
        self._thresholds = {
            "excellent": 4.5,
            "good": 4.0,
            "acceptable": 3.5,
            "needs_improvement": 3.0,
            "critical": 2.5
        }

    def score_call_automated(
        self,
        call_id: str,
        transcript: List[Dict[str, str]],
        metadata: Optional[Dict] = None
    ) -> QAScorecard:
        """
        Automatically score a call using AI analysis

        Args:
            call_id: Unique call ID
            transcript: List of messages with 'role' and 'content'
            metadata: Call metadata (duration, outcome, etc.)

        Returns:
            QAScorecard with AI-generated scores
        """
        import uuid
        scorecard_id = f"QA-{str(uuid.uuid4())[:8].upper()}"

        # Analyze transcript for each criteria
        scores = {}
        strengths = []
        improvements = []
        critical_issues = []

        # Greeting Quality
        scores[QACriteria.GREETING_QUALITY.value] = self._score_greeting(transcript)

        # Active Listening
        scores[QACriteria.ACTIVE_LISTENING.value] = self._score_active_listening(transcript)

        # Problem Resolution
        scores[QACriteria.PROBLEM_RESOLUTION.value] = self._score_problem_resolution(transcript, metadata)

        # Product Knowledge
        scores[QACriteria.PRODUCT_KNOWLEDGE.value] = self._score_product_knowledge(transcript)

        # Communication Clarity
        scores[QACriteria.COMMUNICATION_CLARITY.value] = self._score_communication_clarity(transcript)

        # Empathy & Rapport
        scores[QACriteria.EMPATHY_RAPPORT.value] = self._score_empathy(transcript)

        # Compliance Adherence
        compliance_score, compliance_issues = self._score_compliance(transcript)
        scores[QACriteria.COMPLIANCE_ADHERENCE.value] = compliance_score
        if compliance_issues:
            critical_issues.extend(compliance_issues)

        # Call Control
        scores[QACriteria.CALL_CONTROL.value] = self._score_call_control(transcript, metadata)

        # Closing Technique
        scores[QACriteria.CLOSING_TECHNIQUE.value] = self._score_closing(transcript, metadata)

        # Overall Professionalism
        scores[QACriteria.OVERALL_PROFESSIONALISM.value] = self._score_professionalism(transcript)

        # Calculate weighted overall score
        overall_score = sum(
            scores.get(criteria.value, 3.0) * weight
            for criteria, weight in self._criteria_weights.items()
        )

        # Generate feedback
        for criteria, score in scores.items():
            if score >= 4.5:
                strengths.append(f"Excellent {criteria.replace('_', ' ')}")
            elif score < 3.0:
                improvements.append(f"Improve {criteria.replace('_', ' ')}")

        scorecard = QAScorecard(
            id=scorecard_id,
            call_id=call_id,
            evaluated_by="AI",
            evaluation_type="ai",
            scores=scores,
            overall_score=round(overall_score, 2),
            strengths=strengths,
            improvements=improvements,
            critical_issues=critical_issues,
            status=QAStatus.REVIEWED
        )

        self._scorecards[scorecard_id] = scorecard

        logger.info(f"AI scored call {call_id}: {overall_score:.2f}")
        return scorecard

    def create_review_request(
        self,
        call_id: str,
        call_date: datetime,
        duration_seconds: int,
        caller_phone: str,
        caller_name: Optional[str] = None,
        outcome: CallOutcome = CallOutcome.SUCCESSFUL,
        ai_score: Optional[float] = None,
        priority: int = 1,
        flags: Optional[List[str]] = None,
        transcript_url: Optional[str] = None,
        recording_url: Optional[str] = None,
        assigned_reviewer: Optional[str] = None
    ) -> CallReview:
        """
        Create a human review request for a call

        Args:
            call_id: Call ID to review
            call_date: When the call occurred
            duration_seconds: Call duration
            caller_phone: Caller's phone
            caller_name: Caller's name if known
            outcome: Call outcome classification
            ai_score: AI-generated score (if available)
            priority: Review priority (1-3)
            flags: Any flags for special attention
            transcript_url: URL to transcript
            recording_url: URL to recording
            assigned_reviewer: Specific reviewer to assign

        Returns:
            CallReview record
        """
        import uuid
        review_id = f"REV-{str(uuid.uuid4())[:8].upper()}"

        review = CallReview(
            id=review_id,
            call_id=call_id,
            call_date=call_date,
            duration_seconds=duration_seconds,
            caller_phone=caller_phone,
            caller_name=caller_name,
            outcome=outcome,
            ai_score=ai_score,
            priority=priority,
            flags=flags or [],
            transcript_url=transcript_url,
            recording_url=recording_url,
            assigned_reviewer=assigned_reviewer
        )

        self._reviews[review_id] = review

        logger.info(f"Created review request: {review_id} for call {call_id}")
        return review

    def submit_human_review(
        self,
        review_id: str,
        reviewer_id: str,
        scores: Dict[str, float],
        strengths: Optional[List[str]] = None,
        improvements: Optional[List[str]] = None,
        critical_issues: Optional[List[str]] = None,
        notes: str = ""
    ) -> Optional[QAScorecard]:
        """
        Submit a human QA review

        Args:
            review_id: Review request ID
            reviewer_id: ID of the reviewer
            scores: Scores by criteria
            strengths: Identified strengths
            improvements: Areas for improvement
            critical_issues: Critical issues found
            notes: Additional reviewer notes

        Returns:
            QAScorecard with human scores
        """
        if review_id not in self._reviews:
            return None

        review = self._reviews[review_id]

        import uuid
        scorecard_id = f"QA-{str(uuid.uuid4())[:8].upper()}"

        # Calculate weighted overall
        overall_score = sum(
            scores.get(criteria.value, 3.0) * weight
            for criteria, weight in self._criteria_weights.items()
        )

        scorecard = QAScorecard(
            id=scorecard_id,
            call_id=review.call_id,
            evaluated_by=reviewer_id,
            evaluation_type="human",
            scores=scores,
            overall_score=round(overall_score, 2),
            strengths=strengths or [],
            improvements=improvements or [],
            critical_issues=critical_issues or [],
            notes=notes,
            status=QAStatus.REVIEWED
        )

        self._scorecards[scorecard_id] = scorecard

        # Update review record
        review.human_score = overall_score
        review.status = QAStatus.REVIEWED
        review.reviewed_at = datetime.now(timezone.utc)

        logger.info(f"Human review submitted: {review_id} - Score: {overall_score:.2f}")
        return scorecard

    def get_review_queue(
        self,
        reviewer_id: Optional[str] = None,
        status: Optional[QAStatus] = None,
        priority: Optional[int] = None,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """
        Get the review queue for human QA

        Args:
            reviewer_id: Filter by assigned reviewer
            status: Filter by status
            priority: Filter by priority
            limit: Maximum results

        Returns:
            List of reviews pending/in progress
        """
        reviews = list(self._reviews.values())

        if reviewer_id:
            reviews = [r for r in reviews if r.assigned_reviewer == reviewer_id]

        if status:
            reviews = [r for r in reviews if r.status == status]
        else:
            # Default: pending and in_review
            reviews = [r for r in reviews if r.status in [QAStatus.PENDING, QAStatus.IN_REVIEW]]

        if priority:
            reviews = [r for r in reviews if r.priority == priority]

        # Sort by priority (desc) and date (asc)
        reviews.sort(key=lambda r: (-r.priority, r.call_date))

        return [
            {
                "review_id": r.id,
                "call_id": r.call_id,
                "call_date": r.call_date.isoformat(),
                "duration_seconds": r.duration_seconds,
                "caller_name": r.caller_name,
                "outcome": r.outcome.value,
                "ai_score": r.ai_score,
                "priority": r.priority,
                "flags": r.flags,
                "status": r.status.value,
                "assigned_reviewer": r.assigned_reviewer,
                "has_transcript": r.transcript_url is not None,
                "has_recording": r.recording_url is not None
            }
            for r in reviews[:limit]
        ]

    def get_ai_performance_metrics(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """
        Get AI performance metrics based on QA scores

        Returns metrics on AI call handling quality
        """
        if not start_date:
            start_date = datetime.now(timezone.utc) - timedelta(days=30)
        if not end_date:
            end_date = datetime.now(timezone.utc)

        # Get AI scorecards in period
        ai_scorecards = [
            sc for sc in self._scorecards.values()
            if sc.evaluation_type == "ai" and start_date <= sc.created_at <= end_date
        ]

        if not ai_scorecards:
            return {
                "period": {"start": start_date.isoformat(), "end": end_date.isoformat()},
                "total_scored": 0,
                "message": "No AI scores in period"
            }

        # Calculate metrics
        overall_scores = [sc.overall_score for sc in ai_scorecards]

        # By criteria
        criteria_scores = {}
        for criteria in QACriteria:
            scores = [
                sc.scores.get(criteria.value, 0)
                for sc in ai_scorecards
                if criteria.value in sc.scores
            ]
            if scores:
                criteria_scores[criteria.value] = {
                    "avg": round(statistics.mean(scores), 2),
                    "min": round(min(scores), 2),
                    "max": round(max(scores), 2),
                    "std_dev": round(statistics.stdev(scores), 2) if len(scores) > 1 else 0
                }

        # Distribution
        distribution = {
            "excellent": len([s for s in overall_scores if s >= self._thresholds["excellent"]]),
            "good": len([s for s in overall_scores if self._thresholds["good"] <= s < self._thresholds["excellent"]]),
            "acceptable": len([s for s in overall_scores if self._thresholds["acceptable"] <= s < self._thresholds["good"]]),
            "needs_improvement": len([s for s in overall_scores if self._thresholds["needs_improvement"] <= s < self._thresholds["acceptable"]]),
            "critical": len([s for s in overall_scores if s < self._thresholds["needs_improvement"]])
        }

        # Common issues
        all_improvements = []
        all_critical = []
        for sc in ai_scorecards:
            all_improvements.extend(sc.improvements)
            all_critical.extend(sc.critical_issues)

        improvement_counts = {}
        for imp in all_improvements:
            improvement_counts[imp] = improvement_counts.get(imp, 0) + 1

        top_improvements = sorted(
            improvement_counts.items(),
            key=lambda x: x[1],
            reverse=True
        )[:5]

        return {
            "period": {"start": start_date.isoformat(), "end": end_date.isoformat()},
            "total_scored": len(ai_scorecards),
            "overall": {
                "avg_score": round(statistics.mean(overall_scores), 2),
                "min_score": round(min(overall_scores), 2),
                "max_score": round(max(overall_scores), 2),
                "median_score": round(statistics.median(overall_scores), 2)
            },
            "distribution": distribution,
            "by_criteria": criteria_scores,
            "top_improvement_areas": [{"area": area, "count": count} for area, count in top_improvements],
            "critical_issues_count": len(all_critical)
        }

    def get_calibration_report(self) -> Dict[str, Any]:
        """
        Get calibration report comparing AI vs human scores

        Helps identify if AI scoring needs adjustment
        """
        # Find calls with both AI and human scores
        call_scores = {}

        for sc in self._scorecards.values():
            if sc.call_id not in call_scores:
                call_scores[sc.call_id] = {}

            if sc.evaluation_type == "ai":
                call_scores[sc.call_id]["ai"] = sc.overall_score
                call_scores[sc.call_id]["ai_scores"] = sc.scores
            elif sc.evaluation_type == "human":
                call_scores[sc.call_id]["human"] = sc.overall_score
                call_scores[sc.call_id]["human_scores"] = sc.scores

        # Filter to calls with both
        dual_scored = {
            call_id: scores for call_id, scores in call_scores.items()
            if "ai" in scores and "human" in scores
        }

        if not dual_scored:
            return {
                "dual_scored_calls": 0,
                "message": "No calls with both AI and human scores"
            }

        # Calculate differences
        differences = []
        for call_id, scores in dual_scored.items():
            diff = scores["ai"] - scores["human"]
            differences.append({
                "call_id": call_id,
                "ai_score": scores["ai"],
                "human_score": scores["human"],
                "difference": round(diff, 2)
            })

        avg_diff = statistics.mean([d["difference"] for d in differences])
        abs_avg_diff = statistics.mean([abs(d["difference"]) for d in differences])

        # By criteria
        criteria_calibration = {}
        for criteria in QACriteria:
            ai_scores = []
            human_scores = []
            for scores in dual_scored.values():
                ai_s = scores.get("ai_scores", {}).get(criteria.value)
                human_s = scores.get("human_scores", {}).get(criteria.value)
                if ai_s is not None and human_s is not None:
                    ai_scores.append(ai_s)
                    human_scores.append(human_s)

            if ai_scores and human_scores:
                criteria_calibration[criteria.value] = {
                    "ai_avg": round(statistics.mean(ai_scores), 2),
                    "human_avg": round(statistics.mean(human_scores), 2),
                    "avg_difference": round(statistics.mean(ai_scores) - statistics.mean(human_scores), 2)
                }

        return {
            "dual_scored_calls": len(dual_scored),
            "overall_calibration": {
                "avg_difference": round(avg_diff, 2),  # Positive = AI scores higher
                "abs_avg_difference": round(abs_avg_diff, 2),
                "bias_direction": "AI scores higher" if avg_diff > 0.1 else "AI scores lower" if avg_diff < -0.1 else "Well calibrated"
            },
            "by_criteria": criteria_calibration,
            "sample_comparisons": differences[:10],
            "recommendation": self._get_calibration_recommendation(avg_diff, abs_avg_diff)
        }

    def get_benchmarks(self) -> List[QABenchmark]:
        """Get current QA benchmarks and targets"""
        # Calculate current metrics
        recent_scorecards = [
            sc for sc in self._scorecards.values()
            if sc.created_at >= datetime.now(timezone.utc) - timedelta(days=30)
        ]

        if not recent_scorecards:
            return []

        overall_scores = [sc.overall_score for sc in recent_scorecards]
        current_avg = statistics.mean(overall_scores)

        # Compare to previous period
        previous_scorecards = [
            sc for sc in self._scorecards.values()
            if datetime.now(timezone.utc) - timedelta(days=60) <= sc.created_at < datetime.now(timezone.utc) - timedelta(days=30)
        ]

        if previous_scorecards:
            previous_avg = statistics.mean([sc.overall_score for sc in previous_scorecards])
            trend = "up" if current_avg > previous_avg else "down" if current_avg < previous_avg else "stable"
        else:
            trend = "stable"

        benchmarks = [
            QABenchmark(
                metric="Overall Quality Score",
                target=4.0,
                current=round(current_avg, 2),
                trend=trend,
                period_days=30
            ),
            QABenchmark(
                metric="Excellent Rate",
                target=30.0,
                current=round(len([s for s in overall_scores if s >= 4.5]) / len(overall_scores) * 100, 1),
                trend=trend,
                period_days=30
            ),
            QABenchmark(
                metric="Critical Issues Rate",
                target=5.0,
                current=round(len([s for s in overall_scores if s < 2.5]) / len(overall_scores) * 100, 1),
                trend="down" if trend == "up" else "up" if trend == "down" else "stable",
                period_days=30
            )
        ]

        return benchmarks

    def dispute_score(
        self,
        scorecard_id: str,
        disputed_by: str,
        reason: str
    ) -> bool:
        """
        Dispute a QA scorecard

        Args:
            scorecard_id: Scorecard to dispute
            disputed_by: ID of person disputing
            reason: Reason for dispute

        Returns:
            Success status
        """
        if scorecard_id not in self._scorecards:
            return False

        scorecard = self._scorecards[scorecard_id]
        scorecard.status = QAStatus.DISPUTED
        scorecard.notes += f"\n\nDisputed by {disputed_by}: {reason}"

        logger.info(f"Scorecard disputed: {scorecard_id}")
        return True

    # Private scoring methods

    def _score_greeting(self, transcript: List[Dict]) -> float:
        """Score the greeting quality"""
        if not transcript:
            return 3.0

        first_ai = next((m for m in transcript if m.get("role") == "assistant"), None)
        if not first_ai:
            return 3.0

        content = first_ai.get("content", "").lower()
        score = 3.0

        # Check for key elements
        if any(word in content for word in ["thank", "welcome", "hello", "hi"]):
            score += 0.5
        if any(word in content for word in ["help", "assist", "how can i"]):
            score += 0.5
        if len(content) >= 30:  # Not too brief
            score += 0.5
        if len(content) <= 150:  # Not too long
            score += 0.5

        return min(5.0, score)

    def _score_active_listening(self, transcript: List[Dict]) -> float:
        """Score active listening indicators"""
        ai_messages = [m for m in transcript if m.get("role") == "assistant"]
        user_messages = [m for m in transcript if m.get("role") == "user"]

        if not ai_messages or not user_messages:
            return 3.0

        score = 3.0

        # Check for acknowledgment phrases
        acknowledgments = ["i understand", "i see", "got it", "that makes sense", "i hear you"]
        ack_count = sum(
            1 for m in ai_messages
            if any(ack in m.get("content", "").lower() for ack in acknowledgments)
        )

        if ack_count >= 2:
            score += 0.5
        if ack_count >= 4:
            score += 0.5

        # Check for clarifying questions
        clarifications = ["?", "could you tell me", "can you clarify", "what do you mean"]
        clar_count = sum(
            1 for m in ai_messages
            if any(clar in m.get("content", "").lower() for clar in clarifications)
        )

        if clar_count >= 1:
            score += 0.5
        if clar_count >= 2:
            score += 0.5

        return min(5.0, score)

    def _score_problem_resolution(self, transcript: List[Dict], metadata: Optional[Dict]) -> float:
        """Score problem resolution effectiveness"""
        score = 3.0

        if metadata:
            outcome = metadata.get("outcome", "")
            if outcome == "successful":
                score += 1.5
            elif outcome == "partial_success":
                score += 0.5
            elif outcome == "escalated":
                score += 0.0  # Neutral
            elif outcome in ["failed", "abandoned"]:
                score -= 1.0

        # Check for resolution language
        ai_messages = [m for m in transcript if m.get("role") == "assistant"]
        resolution_phrases = ["i've scheduled", "appointment is set", "i can help with that", "here's what we can do"]

        if any(
            any(phrase in m.get("content", "").lower() for phrase in resolution_phrases)
            for m in ai_messages
        ):
            score += 0.5

        return max(1.0, min(5.0, score))

    def _score_product_knowledge(self, transcript: List[Dict]) -> float:
        """Score product knowledge demonstration"""
        ai_messages = [m for m in transcript if m.get("role") == "assistant"]
        score = 3.5

        # Check for mortgage-specific terms
        knowledge_indicators = [
            "rate", "apr", "points", "closing costs", "down payment",
            "pre-approval", "underwriting", "conventional", "fha", "va",
            "ltv", "dti", "credit score", "refinance"
        ]

        knowledge_count = sum(
            1 for m in ai_messages
            if any(term in m.get("content", "").lower() for term in knowledge_indicators)
        )

        if knowledge_count >= 3:
            score += 0.5
        if knowledge_count >= 5:
            score += 0.5
        if knowledge_count >= 7:
            score += 0.5

        # Penalize uncertainty
        uncertainty = ["i'm not sure", "i don't know", "i cannot answer"]
        if any(
            any(u in m.get("content", "").lower() for u in uncertainty)
            for m in ai_messages
        ):
            score -= 0.5

        return max(1.0, min(5.0, score))

    def _score_communication_clarity(self, transcript: List[Dict]) -> float:
        """Score communication clarity"""
        ai_messages = [m for m in transcript if m.get("role") == "assistant"]
        score = 3.5

        for msg in ai_messages:
            content = msg.get("content", "")

            # Check message length (not too short, not too long)
            if 50 <= len(content) <= 300:
                score += 0.1

            # Check for structured responses (bullets, numbered lists)
            if any(marker in content for marker in ["1.", "2.", "•", "-"]):
                score += 0.2

        return max(1.0, min(5.0, score))

    def _score_empathy(self, transcript: List[Dict]) -> float:
        """Score empathy and rapport building"""
        ai_messages = [m for m in transcript if m.get("role") == "assistant"]
        score = 3.0

        empathy_phrases = [
            "i understand", "that must be", "i appreciate", "thank you for",
            "i'm here to help", "i can imagine", "that's a great question"
        ]

        empathy_count = sum(
            1 for m in ai_messages
            if any(phrase in m.get("content", "").lower() for phrase in empathy_phrases)
        )

        if empathy_count >= 2:
            score += 0.5
        if empathy_count >= 4:
            score += 0.5
        if empathy_count >= 6:
            score += 0.5

        # Check for personalization
        user_messages = [m for m in transcript if m.get("role") == "user"]
        if user_messages:
            first_user = user_messages[0].get("content", "")
            # If caller mentions name and AI uses it later
            # This is a simplified check
            if any("your" in m.get("content", "").lower() for m in ai_messages):
                score += 0.5

        return min(5.0, score)

    def _score_compliance(self, transcript: List[Dict]) -> Tuple[float, List[str]]:
        """Score compliance adherence and identify issues"""
        ai_messages = [m for m in transcript if m.get("role") == "assistant"]
        score = 4.0
        issues = []

        # Check for required disclosures (if applicable)
        required_disclosures = ["licensed", "nmls", "equal housing"]
        has_disclosure = any(
            any(disc in m.get("content", "").lower() for disc in required_disclosures)
            for m in ai_messages
        )

        # Check for prohibited language
        prohibited = ["guarantee", "promise", "definitely", "always"]
        has_prohibited = any(
            any(p in m.get("content", "").lower() for p in prohibited)
            for m in ai_messages
        )

        if has_prohibited:
            score -= 1.0
            issues.append("Used prohibited language (guarantees/promises)")

        # Check for proper qualifications
        if not has_disclosure and len(ai_messages) > 5:
            score -= 0.5
            issues.append("Missing licensing/compliance disclosures")

        return max(1.0, score), issues

    def _score_call_control(self, transcript: List[Dict], metadata: Optional[Dict]) -> float:
        """Score call control and efficiency"""
        score = 3.5

        if metadata:
            duration = metadata.get("duration_seconds", 0)
            # Optimal call duration: 2-5 minutes
            if 120 <= duration <= 300:
                score += 0.5
            elif duration > 600:  # Over 10 minutes
                score -= 0.5

        # Check for redirection/guidance
        ai_messages = [m for m in transcript if m.get("role") == "assistant"]
        guidance_phrases = ["let me help", "first, let's", "to get started", "the next step"]

        if any(
            any(phrase in m.get("content", "").lower() for phrase in guidance_phrases)
            for m in ai_messages
        ):
            score += 0.5

        return max(1.0, min(5.0, score))

    def _score_closing(self, transcript: List[Dict], metadata: Optional[Dict]) -> float:
        """Score closing technique"""
        if not transcript:
            return 3.0

        last_ai = None
        for msg in reversed(transcript):
            if msg.get("role") == "assistant":
                last_ai = msg
                break

        if not last_ai:
            return 3.0

        content = last_ai.get("content", "").lower()
        score = 3.0

        # Check for proper closing elements
        closing_phrases = [
            "thank you", "have a great", "is there anything else",
            "we look forward", "scheduled for", "confirmation"
        ]

        if any(phrase in content for phrase in closing_phrases):
            score += 1.0

        # Check for call to action
        if any(word in content for word in ["call", "visit", "contact", "email"]):
            score += 0.5

        return min(5.0, score)

    def _score_professionalism(self, transcript: List[Dict]) -> float:
        """Score overall professionalism"""
        ai_messages = [m for m in transcript if m.get("role") == "assistant"]
        score = 4.0

        # Check for professional language
        unprofessional = ["lol", "haha", "um", "uh", "like totally"]
        if any(
            any(u in m.get("content", "").lower() for u in unprofessional)
            for m in ai_messages
        ):
            score -= 1.0

        # Check for consistent tone
        # (Simplified - in production would use sentiment analysis)

        return max(1.0, min(5.0, score))

    def _get_calibration_recommendation(self, avg_diff: float, abs_avg_diff: float) -> str:
        """Get recommendation based on calibration analysis"""
        if abs_avg_diff < 0.2:
            return "AI scoring is well calibrated with human reviewers."
        elif abs_avg_diff < 0.5:
            if avg_diff > 0:
                return "AI tends to score slightly higher. Consider adjusting scoring thresholds down by 5-10%."
            else:
                return "AI tends to score slightly lower. Consider adjusting scoring thresholds up by 5-10%."
        else:
            if avg_diff > 0:
                return "Significant calibration gap - AI scores too high. Review scoring algorithms and consider retraining."
            else:
                return "Significant calibration gap - AI scores too low. Review scoring algorithms and consider retraining."


# Create singleton instance
call_quality_assurance_service = CallQualityAssuranceService()
