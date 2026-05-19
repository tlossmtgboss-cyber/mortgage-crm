"""
Continuous Learning Meta-Agent
Autonomous agent that monitors AI performance and orchestrates continuous improvement
Analyzes patterns, identifies opportunities, and triggers optimization actions
"""
import logging
from typing import Optional, Dict, Any, List, Tuple
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass, field
from enum import Enum
import json
import uuid
from collections import Counter

from sqlalchemy import desc
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Lazy model imports — avoid circular-import at module load time
# ---------------------------------------------------------------------------
_models_loaded = False
_AgentFeedback = None
_LearningPattern = None
_PromptOptimization = None
_LearningExample = None


def _ensure_models():
    """Import DB models on first use to avoid circular imports."""
    global _models_loaded, _AgentFeedback, _LearningPattern, _PromptOptimization, _LearningExample
    if _models_loaded:
        return
    try:
        from database.models.agent_feedback import AgentFeedback
        from database.models.learning_example import (
            LearningPattern, PromptOptimization, LearningExample,
        )
        _AgentFeedback = AgentFeedback
        _LearningPattern = LearningPattern
        _PromptOptimization = PromptOptimization
        _LearningExample = LearningExample
        _models_loaded = True
    except Exception as e:
        logger.warning(f"Could not import learning models: {e}")


def _get_session():
    """Fallback: create a fresh DB session when none was injected."""
    try:
        from db import SessionLocal
        return SessionLocal()
    except Exception as e:
        logger.warning(f"Could not create fallback DB session: {e}")
        return None


class ImprovementAction(str, Enum):
    """Types of improvement actions the meta-agent can take"""
    KNOWLEDGE_BASE_UPDATE = "knowledge_base_update"
    PROMPT_OPTIMIZATION = "prompt_optimization"
    AB_TEST_CREATION = "ab_test_creation"
    ESCALATION_THRESHOLD_ADJUSTMENT = "escalation_adjustment"
    FINE_TUNING_TRIGGER = "fine_tuning_trigger"
    ALERT_HUMAN_REVIEW = "alert_human_review"
    INTENT_CLASSIFIER_UPDATE = "intent_update"
    RESPONSE_TEMPLATE_UPDATE = "template_update"


class ActionPriority(str, Enum):
    """Priority levels for improvement actions"""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


@dataclass
class PerformanceMetrics:
    """Aggregated performance metrics for analysis"""
    period_start: datetime
    period_end: datetime
    total_conversations: int = 0
    successful_conversations: int = 0
    failed_conversations: int = 0
    escalated_conversations: int = 0
    avg_satisfaction_score: float = 0.0
    avg_response_time_ms: float = 0.0
    booking_conversion_rate: float = 0.0
    first_call_resolution_rate: float = 0.0
    knowledge_gap_encounters: int = 0
    repeat_caller_rate: float = 0.0


@dataclass
class ImprovementOpportunity:
    """Identified improvement opportunity"""
    id: str
    action_type: ImprovementAction
    priority: ActionPriority
    title: str
    description: str
    impact_estimate: str
    confidence: float  # 0-1
    evidence: List[Dict] = field(default_factory=list)
    suggested_implementation: Optional[str] = None
    auto_executable: bool = False
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    status: str = "identified"  # identified, approved, executing, completed, rejected


@dataclass
class LearningCycleReport:
    """Report from a learning cycle run"""
    cycle_id: str
    started_at: datetime
    completed_at: datetime
    metrics_analyzed: PerformanceMetrics
    opportunities_identified: List[ImprovementOpportunity]
    actions_taken: List[Dict]
    recommendations: List[str]
    next_cycle_scheduled: datetime


class ContinuousLearningMetaAgent:
    """
    Meta-Agent for continuous AI improvement

    Responsibilities:
    - Monitor AI performance across all conversations
    - Identify patterns in failures and successes
    - Automatically suggest/trigger improvements
    - Orchestrate A/B tests based on insights
    - Manage the learning feedback loop
    - Alert humans when needed
    """

    # Risk levels for auto-apply decisions
    LOW_RISK_TYPES = {"few_shot", "tool_description"}
    HIGH_RISK_TYPES = {"system_prompt", "intent_pattern"}

    def __init__(
        self,
        db_session=None,
        ai_learning_service=None,
        voice_ab_service=None,
        ai_client=None
    ):
        self.db = db_session
        self.ai_learning = ai_learning_service
        self.voice_ab = voice_ab_service
        self.ai_client = ai_client

        self._opportunities: Dict[str, ImprovementOpportunity] = {}
        self._cycle_history: List[LearningCycleReport] = []
        self._thresholds = {
            "min_success_rate": 0.75,
            "max_escalation_rate": 0.15,
            "min_satisfaction": 3.5,
            "max_knowledge_gap_rate": 0.10,
            "min_booking_conversion": 0.20
        }

    def _get_db(self) -> Optional[Session]:
        """Return the injected session, or create a fallback."""
        if self.db is not None:
            return self.db
        return _get_session()

    def _close_fallback(self, session: Optional[Session]):
        """Close a session only if it was a fallback (not the injected one)."""
        if session is not None and session is not self.db:
            try:
                session.close()
            except Exception as _exc:  # noqa: BLE001
                pass

    def run_learning_cycle(
        self,
        period_hours: int = 24
    ) -> LearningCycleReport:
        """
        Run a complete learning cycle

        Analyzes recent performance, identifies opportunities,
        and takes automated actions where appropriate.

        Args:
            period_hours: Hours of data to analyze

        Returns:
            Learning cycle report
        """
        cycle_id = f"LC-{str(uuid.uuid4())[:8].upper()}"

        started_at = datetime.now(timezone.utc)
        period_start = started_at - timedelta(hours=period_hours)

        logger.info(f"Starting learning cycle {cycle_id} for last {period_hours} hours")

        # Step 1: Gather metrics
        metrics = self._gather_performance_metrics(period_start, started_at)

        # Step 2: Analyze and identify opportunities
        opportunities = self._analyze_and_identify_opportunities(metrics)

        # Step 3: Take automated actions (in-memory opportunity execution)
        actions_taken = self._execute_auto_actions(opportunities)

        # Step 4: Persist learning — analyze negative feedback, create patterns
        #         and prompt optimizations in the DB
        improvement_results = self._run_execute_improvements_for_all_orgs(
            period_start, started_at
        )
        if improvement_results:
            actions_taken.append({
                "action": "execute_improvements",
                "orgs_processed": len(improvement_results),
                "results": improvement_results,
            })

        # Step 5: Generate recommendations
        recommendations = self._generate_recommendations(metrics, opportunities)

        completed_at = datetime.now(timezone.utc)

        # Create report
        report = LearningCycleReport(
            cycle_id=cycle_id,
            started_at=started_at,
            completed_at=completed_at,
            metrics_analyzed=metrics,
            opportunities_identified=opportunities,
            actions_taken=actions_taken,
            recommendations=recommendations,
            next_cycle_scheduled=completed_at + timedelta(hours=period_hours)
        )

        self._cycle_history.append(report)

        logger.info(
            f"Learning cycle {cycle_id} completed: "
            f"{len(opportunities)} opportunities, {len(actions_taken)} actions taken"
        )

        return report

    def get_performance_dashboard(self) -> Dict[str, Any]:
        """
        Get real-time performance dashboard data

        Returns comprehensive view of AI performance and improvement status
        """
        # Get recent metrics
        now = datetime.now(timezone.utc)
        day_metrics = self._gather_performance_metrics(
            now - timedelta(hours=24), now
        )
        week_metrics = self._gather_performance_metrics(
            now - timedelta(days=7), now
        )

        # Calculate trends
        trends = self._calculate_trends(day_metrics, week_metrics)

        # Get active opportunities
        active_opportunities = [
            {
                "id": opp.id,
                "title": opp.title,
                "priority": opp.priority.value,
                "action_type": opp.action_type.value,
                "status": opp.status,
                "confidence": opp.confidence
            }
            for opp in self._opportunities.values()
            if opp.status in ["identified", "approved", "executing"]
        ]

        # Get recent cycle results
        recent_cycles = self._cycle_history[-5:] if self._cycle_history else []

        return {
            "timestamp": now.isoformat(),
            "current_metrics": {
                "success_rate": day_metrics.successful_conversations / max(day_metrics.total_conversations, 1) * 100,
                "escalation_rate": day_metrics.escalated_conversations / max(day_metrics.total_conversations, 1) * 100,
                "avg_satisfaction": day_metrics.avg_satisfaction_score,
                "booking_conversion": day_metrics.booking_conversion_rate * 100,
                "knowledge_gap_rate": day_metrics.knowledge_gap_encounters / max(day_metrics.total_conversations, 1) * 100
            },
            "thresholds": self._thresholds,
            "threshold_violations": self._check_threshold_violations(day_metrics),
            "trends": trends,
            "active_opportunities": active_opportunities,
            "total_opportunities": len(self._opportunities),
            "recent_cycles": [
                {
                    "cycle_id": c.cycle_id,
                    "completed_at": c.completed_at.isoformat(),
                    "opportunities_found": len(c.opportunities_identified),
                    "actions_taken": len(c.actions_taken)
                }
                for c in recent_cycles
            ],
            "health_score": self._calculate_health_score(day_metrics)
        }

    def analyze_failed_conversations(
        self,
        conversations: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Analyze a batch of failed conversations for patterns

        Args:
            conversations: List of failed conversation data

        Returns:
            Analysis with patterns and recommendations
        """
        if not conversations:
            return {"message": "No conversations to analyze"}

        # Group failures by reason
        failure_reasons = {}
        topics = {}
        time_patterns = {}

        for conv in conversations:
            # Analyze failure reasons
            reasons = conv.get("failure_reasons", [])
            for reason in reasons:
                if reason not in failure_reasons:
                    failure_reasons[reason] = 0
                failure_reasons[reason] += 1

            # Analyze topics
            topic = conv.get("topic", "unknown")
            if topic not in topics:
                topics[topic] = 0
            topics[topic] += 1

            # Analyze time patterns
            hour = conv.get("hour", 0)
            time_bucket = f"{hour:02d}:00-{(hour+1):02d}:00"
            if time_bucket not in time_patterns:
                time_patterns[time_bucket] = 0
            time_patterns[time_bucket] += 1

        # Sort by frequency
        sorted_reasons = sorted(failure_reasons.items(), key=lambda x: x[1], reverse=True)
        sorted_topics = sorted(topics.items(), key=lambda x: x[1], reverse=True)
        peak_failure_times = sorted(time_patterns.items(), key=lambda x: x[1], reverse=True)[:3]

        # Generate insights
        insights = []

        if sorted_reasons:
            top_reason = sorted_reasons[0]
            insights.append(
                f"Most common failure reason: {top_reason[0]} ({top_reason[1]} occurrences, "
                f"{top_reason[1]/len(conversations)*100:.1f}%)"
            )

        if sorted_topics:
            top_topic = sorted_topics[0]
            insights.append(
                f"Most problematic topic: {top_topic[0]} ({top_topic[1]} failures)"
            )

        if peak_failure_times:
            insights.append(
                f"Peak failure times: {', '.join(t[0] for t in peak_failure_times)}"
            )

        # Generate recommendations
        recommendations = self._generate_failure_recommendations(
            sorted_reasons, sorted_topics
        )

        return {
            "total_analyzed": len(conversations),
            "failure_reasons": dict(sorted_reasons),
            "topics": dict(sorted_topics),
            "time_patterns": time_patterns,
            "peak_failure_times": peak_failure_times,
            "insights": insights,
            "recommendations": recommendations
        }

    def suggest_ab_test(
        self,
        based_on_opportunity_id: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Suggest an A/B test based on identified opportunities

        Args:
            based_on_opportunity_id: Specific opportunity to base test on

        Returns:
            A/B test suggestion or None
        """
        opportunity = None

        if based_on_opportunity_id:
            opportunity = self._opportunities.get(based_on_opportunity_id)
        else:
            # Find best opportunity for A/B testing
            candidates = [
                opp for opp in self._opportunities.values()
                if opp.action_type in [
                    ImprovementAction.PROMPT_OPTIMIZATION,
                    ImprovementAction.RESPONSE_TEMPLATE_UPDATE
                ]
                and opp.status == "identified"
                and opp.confidence >= 0.6
            ]

            if candidates:
                # Sort by priority and confidence
                priority_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
                candidates.sort(
                    key=lambda x: (priority_order.get(x.priority.value, 4), -x.confidence)
                )
                opportunity = candidates[0]

        if not opportunity:
            return None

        # Generate test suggestion based on opportunity type
        if opportunity.action_type == ImprovementAction.PROMPT_OPTIMIZATION:
            return self._suggest_prompt_ab_test(opportunity)
        elif opportunity.action_type == ImprovementAction.RESPONSE_TEMPLATE_UPDATE:
            return self._suggest_template_ab_test(opportunity)

        return None

    def approve_opportunity(self, opportunity_id: str) -> bool:
        """
        Approve an improvement opportunity for execution

        Args:
            opportunity_id: Opportunity to approve

        Returns:
            Success status
        """
        if opportunity_id not in self._opportunities:
            return False

        opportunity = self._opportunities[opportunity_id]
        opportunity.status = "approved"

        logger.info(f"Approved opportunity: {opportunity.title}")

        # If auto-executable, queue for execution
        if opportunity.auto_executable:
            self._queue_for_execution(opportunity)

        return True

    def reject_opportunity(
        self,
        opportunity_id: str,
        reason: str
    ) -> bool:
        """
        Reject an improvement opportunity

        Args:
            opportunity_id: Opportunity to reject
            reason: Rejection reason

        Returns:
            Success status
        """
        if opportunity_id not in self._opportunities:
            return False

        opportunity = self._opportunities[opportunity_id]
        opportunity.status = "rejected"

        logger.info(f"Rejected opportunity: {opportunity.title} - {reason}")
        return True

    def set_threshold(self, metric: str, value: float) -> bool:
        """
        Update a performance threshold

        Args:
            metric: Threshold metric name
            value: New threshold value

        Returns:
            Success status
        """
        if metric not in self._thresholds:
            return False

        self._thresholds[metric] = value
        logger.info(f"Updated threshold: {metric} = {value}")
        return True

    def get_knowledge_base_suggestions(self) -> List[Dict[str, Any]]:
        """
        Get AI-generated suggestions for knowledge base updates

        Returns:
            List of knowledge base update suggestions
        """
        # Get knowledge gaps from learning service
        if not self.ai_learning:
            return []

        gaps = self.ai_learning.get_knowledge_gaps(status="open", min_frequency=3)

        suggestions = []
        for gap in gaps:
            suggestion = {
                "gap_id": gap.id,
                "topic": gap.topic,
                "frequency": gap.frequency,
                "priority": gap.priority,
                "example_queries": gap.example_queries[:3],
                "suggested_content": self._generate_content_suggestion(gap),
                "auto_generatable": gap.frequency >= 5
            }
            suggestions.append(suggestion)

        return suggestions

    # -----------------------------------------------------------------------
    # Execution methods — actually persist learning and apply improvements
    # -----------------------------------------------------------------------

    def execute_improvements(self, org_id: int) -> Dict[str, Any]:
        """
        Main execution method.

        1. Query recent AgentFeedback (last 7 days)
        2. Identify patterns in negative feedback
        3. Create LearningPattern records
        4. Create PromptOptimization suggestions based on patterns
        5. Auto-apply low-risk optimizations (few-shot examples, tool descriptions)
        6. Flag high-risk changes for manual review
        7. Return summary

        Args:
            org_id: Organization to run improvements for

        Returns:
            Summary dict of actions taken
        """
        _ensure_models()
        session = self._get_db()
        if session is None or _AgentFeedback is None:
            return {"status": "skipped", "reason": "no db session or models unavailable"}

        now = datetime.now(timezone.utc)
        week_ago = now - timedelta(days=7)
        summary: Dict[str, Any] = {
            "org_id": org_id,
            "executed_at": now.isoformat(),
            "patterns_created": 0,
            "patterns_updated": 0,
            "optimizations_created": 0,
            "optimizations_auto_applied": 0,
            "optimizations_flagged_for_review": 0,
            "errors": [],
        }

        try:
            # Step 1 — fetch recent negative feedback
            negatives = (
                session.query(_AgentFeedback)
                .filter(
                    _AgentFeedback.organization_id == org_id,
                    _AgentFeedback.rating == "negative",
                    _AgentFeedback.created_at >= week_ago,
                )
                .all()
            )

            if not negatives:
                summary["status"] = "no_negative_feedback"
                return summary

            # Step 2 — identify patterns in negative feedback
            role_counts: Counter = Counter()
            intent_counts: Counter = Counter()
            role_intents: Dict[str, Counter] = {}

            for fb in negatives:
                role = fb.agent_role or "unknown"
                intent = fb.intent or "unknown"
                role_counts[role] += 1
                intent_counts[intent] += 1
                role_intents.setdefault(role, Counter())[intent] += 1

            # Step 3 — persist discovered patterns
            for role, count in role_counts.items():
                pattern_key = f"negative_feedback:{role}"
                created, updated = self._upsert_pattern(
                    session=session,
                    org_id=org_id,
                    pattern_type="error_pattern",
                    pattern_key=pattern_key,
                    pattern_value=json.dumps({
                        "agent_role": role,
                        "negative_count_7d": count,
                        "top_intents": dict(role_intents.get(role, Counter()).most_common(5)),
                    }),
                    increment=count,
                )
                if created:
                    summary["patterns_created"] += 1
                elif updated:
                    summary["patterns_updated"] += 1

            for intent, count in intent_counts.most_common(20):
                pattern_key = f"failing_intent:{intent}"
                created, updated = self._upsert_pattern(
                    session=session,
                    org_id=org_id,
                    pattern_type="intent_mapping",
                    pattern_key=pattern_key,
                    pattern_value=json.dumps({
                        "intent": intent,
                        "negative_count_7d": count,
                    }),
                    increment=count,
                )
                if created:
                    summary["patterns_created"] += 1
                elif updated:
                    summary["patterns_updated"] += 1

            # Step 4 & 5 — create PromptOptimization suggestions
            for role, count in role_counts.most_common(10):
                if count < 2:
                    continue  # only act on repeated issues

                top_intent = role_intents.get(role, Counter()).most_common(1)
                top_intent_name = top_intent[0][0] if top_intent else "general"

                # Decide risk level
                opt_type = "few_shot" if count < 5 else "system_prompt"
                is_low_risk = opt_type in self.LOW_RISK_TYPES

                reason = (
                    f"Agent '{role}' received {count} negative feedback items in 7 days. "
                    f"Most-affected intent: {top_intent_name}."
                )
                suggestion = (
                    f"Add few-shot examples for intent '{top_intent_name}' showing correct behavior"
                    if is_low_risk
                    else f"Review and revise system prompt for '{role}' — high negative feedback rate"
                )

                opt = self._persist_prompt_optimization(
                    agent_role=role,
                    optimization_type=opt_type,
                    previous_value=None,
                    new_value=suggestion,
                    reason=reason,
                    auto_apply=is_low_risk,
                    session_override=session,
                )
                if opt:
                    summary["optimizations_created"] += 1
                    if is_low_risk:
                        summary["optimizations_auto_applied"] += 1
                    else:
                        summary["optimizations_flagged_for_review"] += 1

            session.commit()
            summary["status"] = "completed"

        except Exception as e:
            logger.exception(f"execute_improvements failed for org {org_id}: {e}")
            summary["status"] = "error"
            summary["errors"].append(str(e))
            try:
                session.rollback()
            except Exception as _exc:  # noqa: BLE001
                pass
        finally:
            self._close_fallback(session)

        return summary

    def apply_prompt_optimization(self, optimization_id: int) -> Dict[str, Any]:
        """
        Mark a PromptOptimization as applied.

        Args:
            optimization_id: PK of the PromptOptimization record

        Returns:
            Status dict
        """
        _ensure_models()
        session = self._get_db()
        if session is None or _PromptOptimization is None:
            return {"success": False, "reason": "no db session"}

        try:
            opt = session.query(_PromptOptimization).filter_by(id=optimization_id).first()
            if not opt:
                return {"success": False, "reason": "not found"}
            if opt.applied_at is not None and opt.rolled_back_at is None:
                return {"success": False, "reason": "already applied"}

            opt.is_active = True
            opt.applied_at = datetime.now(timezone.utc)
            opt.rolled_back_at = None
            session.commit()
            logger.info(f"Applied prompt optimization {optimization_id}")
            return {"success": True, "optimization_id": optimization_id}
        except Exception as e:
            logger.exception(f"Error applying optimization {optimization_id}: {e}")
            try:
                session.rollback()
            except Exception as _exc:  # noqa: BLE001
                pass
            return {"success": False, "reason": str(e)}
        finally:
            self._close_fallback(session)

    def rollback_prompt_optimization(self, optimization_id: int) -> Dict[str, Any]:
        """
        Rollback (deactivate) a previously applied PromptOptimization.

        Args:
            optimization_id: PK of the PromptOptimization record

        Returns:
            Status dict
        """
        _ensure_models()
        session = self._get_db()
        if session is None or _PromptOptimization is None:
            return {"success": False, "reason": "no db session"}

        try:
            opt = session.query(_PromptOptimization).filter_by(id=optimization_id).first()
            if not opt:
                return {"success": False, "reason": "not found"}
            if opt.rolled_back_at is not None:
                return {"success": False, "reason": "already rolled back"}

            opt.is_active = False
            opt.rolled_back_at = datetime.now(timezone.utc)
            session.commit()
            logger.info(f"Rolled back prompt optimization {optimization_id}")
            return {"success": True, "optimization_id": optimization_id}
        except Exception as e:
            logger.exception(f"Error rolling back optimization {optimization_id}: {e}")
            try:
                session.rollback()
            except Exception as _exc:  # noqa: BLE001
                pass
            return {"success": False, "reason": str(e)}
        finally:
            self._close_fallback(session)

    def evaluate_optimization_impact(self, days: int = 7) -> Dict[str, Any]:
        """
        Evaluate whether applied optimizations improved feedback scores.

        Compares average feedback scores before vs after each optimization's
        applied_at timestamp.

        Args:
            days: Window (in days) before and after the optimization to compare

        Returns:
            Dict mapping optimization_id -> impact assessment
        """
        _ensure_models()
        session = self._get_db()
        if session is None or _PromptOptimization is None or _AgentFeedback is None:
            return {"status": "skipped", "reason": "no db session or models unavailable"}

        try:
            applied = (
                session.query(_PromptOptimization)
                .filter(
                    _PromptOptimization.is_active == True,  # noqa: E712
                    _PromptOptimization.applied_at.isnot(None),
                )
                .all()
            )

            results = {}
            for opt in applied:
                window = timedelta(days=days)
                before_start = opt.applied_at - window
                after_end = opt.applied_at + window

                # Before scores
                before_rows = (
                    session.query(_AgentFeedback)
                    .filter(
                        _AgentFeedback.agent_role == opt.agent_role,
                        _AgentFeedback.created_at >= before_start,
                        _AgentFeedback.created_at < opt.applied_at,
                    )
                    .all()
                )

                # After scores
                after_rows = (
                    session.query(_AgentFeedback)
                    .filter(
                        _AgentFeedback.agent_role == opt.agent_role,
                        _AgentFeedback.created_at >= opt.applied_at,
                        _AgentFeedback.created_at <= after_end,
                    )
                    .all()
                )

                sat_map = {"positive": 5.0, "neutral": 3.0, "negative": 1.0}

                def avg_score(rows):
                    if not rows:
                        return None
                    return sum(sat_map.get(r.rating, 3.0) for r in rows) / len(rows)

                score_before = avg_score(before_rows)
                score_after = avg_score(after_rows)

                # Persist measured scores back to the optimization record
                if score_before is not None:
                    opt.feedback_score_before = score_before
                if score_after is not None:
                    opt.feedback_score_after = score_after

                improvement = None
                if score_before is not None and score_after is not None:
                    improvement = round(score_after - score_before, 2)

                results[opt.id] = {
                    "agent_role": opt.agent_role,
                    "optimization_type": opt.optimization_type,
                    "applied_at": opt.applied_at.isoformat() if opt.applied_at else None,
                    "score_before": round(score_before, 2) if score_before is not None else None,
                    "score_after": round(score_after, 2) if score_after is not None else None,
                    "improvement": improvement,
                    "before_sample_size": len(before_rows),
                    "after_sample_size": len(after_rows),
                    "recommendation": (
                        "keep" if improvement is not None and improvement >= 0
                        else "consider_rollback" if improvement is not None
                        else "insufficient_data"
                    ),
                }

            session.commit()
            return {"status": "completed", "optimizations": results}

        except Exception as e:
            logger.exception(f"Error evaluating optimization impact: {e}")
            try:
                session.rollback()
            except Exception as _exc:  # noqa: BLE001
                pass
            return {"status": "error", "reason": str(e)}
        finally:
            self._close_fallback(session)

    def generate_weekly_report(self, org_id: int) -> Dict[str, Any]:
        """
        Generate a weekly summary of learning activity for an org.

        Returns:
            Dict with patterns, optimizations, feedback trends
        """
        _ensure_models()
        session = self._get_db()
        if session is None:
            return {"status": "skipped", "reason": "no db session"}

        now = datetime.now(timezone.utc)
        week_ago = now - timedelta(days=7)

        report: Dict[str, Any] = {
            "org_id": org_id,
            "period_start": week_ago.isoformat(),
            "period_end": now.isoformat(),
            "generated_at": now.isoformat(),
        }

        try:
            # Feedback summary
            if _AgentFeedback is not None:
                fb_rows = (
                    session.query(_AgentFeedback)
                    .filter(
                        _AgentFeedback.organization_id == org_id,
                        _AgentFeedback.created_at >= week_ago,
                    )
                    .all()
                )
                total = len(fb_rows)
                positive = sum(1 for r in fb_rows if r.rating == "positive")
                negative = sum(1 for r in fb_rows if r.rating == "negative")
                report["feedback"] = {
                    "total": total,
                    "positive": positive,
                    "negative": negative,
                    "neutral": total - positive - negative,
                    "positive_rate": round(positive / max(total, 1), 3),
                }
            else:
                report["feedback"] = None

            # Patterns discovered/updated this week
            if _LearningPattern is not None:
                new_patterns = (
                    session.query(_LearningPattern)
                    .filter(
                        _LearningPattern.organization_id == org_id,
                        _LearningPattern.created_at >= week_ago,
                    )
                    .count()
                )
                updated_patterns = (
                    session.query(_LearningPattern)
                    .filter(
                        _LearningPattern.organization_id == org_id,
                        _LearningPattern.updated_at >= week_ago,
                        _LearningPattern.created_at < week_ago,
                    )
                    .count()
                )
                top_patterns = (
                    session.query(_LearningPattern)
                    .filter(
                        _LearningPattern.organization_id == org_id,
                        _LearningPattern.is_active == True,  # noqa: E712
                    )
                    .order_by(desc(_LearningPattern.occurrence_count))
                    .limit(10)
                    .all()
                )
                report["patterns"] = {
                    "new_this_week": new_patterns,
                    "updated_this_week": updated_patterns,
                    "top_patterns": [
                        {
                            "id": p.id,
                            "type": p.pattern_type,
                            "key": p.pattern_key,
                            "occurrences": p.occurrence_count,
                            "confidence": float(p.confidence) if p.confidence else None,
                        }
                        for p in top_patterns
                    ],
                }
            else:
                report["patterns"] = None

            # Prompt optimizations this week
            if _PromptOptimization is not None:
                opts = (
                    session.query(_PromptOptimization)
                    .filter(_PromptOptimization.created_at >= week_ago)
                    .all()
                )
                applied = [o for o in opts if o.applied_at is not None]
                rolled_back = [o for o in opts if o.rolled_back_at is not None]
                pending = [o for o in opts if o.applied_at is None and o.rolled_back_at is None]
                report["optimizations"] = {
                    "created": len(opts),
                    "applied": len(applied),
                    "rolled_back": len(rolled_back),
                    "pending_review": len(pending),
                    "details": [
                        {
                            "id": o.id,
                            "agent_role": o.agent_role,
                            "type": o.optimization_type,
                            "reason": o.reason,
                            "is_active": o.is_active,
                            "applied_at": o.applied_at.isoformat() if o.applied_at else None,
                        }
                        for o in opts
                    ],
                }
            else:
                report["optimizations"] = None

            report["status"] = "completed"

        except Exception as e:
            logger.exception(f"Error generating weekly report for org {org_id}: {e}")
            report["status"] = "error"
            report["error"] = str(e)
        finally:
            self._close_fallback(session)

        return report

    # Private helper methods

    def _run_execute_improvements_for_all_orgs(
        self,
        period_start: datetime,
        period_end: datetime,
    ) -> List[Dict[str, Any]]:
        """Run execute_improvements() for every active org that had feedback."""
        _ensure_models()
        session = self._get_db()
        if session is None or _AgentFeedback is None:
            return []

        results = []
        try:
            # Find orgs with recent negative feedback
            org_ids = [
                row[0]
                for row in (
                    session.query(_AgentFeedback.organization_id)
                    .filter(
                        _AgentFeedback.created_at >= period_start,
                        _AgentFeedback.created_at <= period_end,
                        _AgentFeedback.rating == "negative",
                        _AgentFeedback.organization_id.isnot(None),
                    )
                    .distinct()
                    .all()
                )
            ]
            for org_id in org_ids:
                try:
                    result = self.execute_improvements(org_id)
                    results.append(result)
                except Exception as e:
                    logger.warning(f"execute_improvements failed for org {org_id}: {e}")
                    results.append({"org_id": org_id, "status": "error", "error": str(e)})
        except Exception as e:
            logger.exception(f"Error finding orgs for execute_improvements: {e}")
        finally:
            self._close_fallback(session)

        return results

    def _gather_performance_metrics(
        self,
        start: datetime,
        end: datetime,
        org_id: Optional[int] = None,
    ) -> PerformanceMetrics:
        """Gather performance metrics for a period from AgentFeedback rows."""
        _ensure_models()
        session = self._get_db()

        # If we can't query the DB, return safe defaults
        if session is None or _AgentFeedback is None:
            return PerformanceMetrics(
                period_start=start,
                period_end=end,
            )

        try:
            q = session.query(_AgentFeedback).filter(
                _AgentFeedback.created_at >= start,
                _AgentFeedback.created_at <= end,
            )
            if org_id is not None:
                q = q.filter(_AgentFeedback.organization_id == org_id)

            rows = q.all()
            total = len(rows)

            if total == 0:
                return PerformanceMetrics(period_start=start, period_end=end)

            positive = sum(1 for r in rows if r.rating == "positive")
            negative = sum(1 for r in rows if r.rating == "negative")
            neutral = total - positive - negative

            # response_time_ms average
            times = [r.response_time_ms for r in rows if r.response_time_ms is not None]
            avg_time = sum(times) / len(times) if times else 0.0

            # Satisfaction proxy: positive=5, neutral=3, negative=1
            sat_map = {"positive": 5.0, "neutral": 3.0, "negative": 1.0}
            sat_scores = [sat_map.get(r.rating, 3.0) for r in rows]
            avg_sat = sum(sat_scores) / len(sat_scores)

            # Knowledge gap: count feedback where the response indicated a gap
            # (agent_role contains "unknown" intent or feedback text mentions gap)
            knowledge_gaps = sum(
                1 for r in rows
                if (r.intent or "").lower() in ("unknown", "unrecognized", "")
                or "knowledge" in (r.comment or "").lower()
                or "don't know" in (r.comment or "").lower()
            )

            # Booking/conversion: check if any conversations led to a booked
            # appointment within the period (uses activities table if available)
            booking_rate = 0.0
            try:
                from database.models import Lead
                booked = (
                    session.query(Lead)
                    .filter(
                        Lead.stage.in_(["Appointment Set", "Consultation"]),
                        Lead.updated_at >= start,
                        Lead.updated_at <= end,
                    )
                )
                if org_id is not None:
                    from database.models import User
                    booked = booked.join(User, User.id == Lead.owner_id).filter(
                        User.organization_id == org_id
                    )
                booked_count = booked.count()
                booking_rate = booked_count / max(total, 1)
            except Exception as _exc:  # noqa: BLE001
                pass  # Booking data unavailable — leave at 0

            # Escalation: count feedback flagged as escalated
            escalated = sum(
                1 for r in rows
                if getattr(r, "escalated", False)
                or (r.rating == "negative" and "escalat" in (r.comment or "").lower())
            )

            return PerformanceMetrics(
                period_start=start,
                period_end=end,
                total_conversations=total,
                successful_conversations=positive,
                failed_conversations=negative,
                escalated_conversations=escalated,
                avg_satisfaction_score=avg_sat,
                avg_response_time_ms=avg_time,
                booking_conversion_rate=booking_rate,
                first_call_resolution_rate=0.0,
                knowledge_gap_encounters=knowledge_gaps,
                repeat_caller_rate=0.0,
            )
        except Exception as e:
            logger.exception(f"Error gathering performance metrics: {e}")
            return PerformanceMetrics(period_start=start, period_end=end)
        finally:
            self._close_fallback(session)

    def _analyze_and_identify_opportunities(
        self,
        metrics: PerformanceMetrics
    ) -> List[ImprovementOpportunity]:
        """Analyze metrics and identify improvement opportunities"""
        opportunities = []

        # Check success rate
        success_rate = metrics.successful_conversations / max(metrics.total_conversations, 1)
        if success_rate < self._thresholds["min_success_rate"]:
            opp = ImprovementOpportunity(
                id=f"OPP-{str(uuid.uuid4())[:8].upper()}",
                action_type=ImprovementAction.PROMPT_OPTIMIZATION,
                priority=ActionPriority.HIGH,
                title="Low Success Rate Detected",
                description=f"Success rate ({success_rate:.1%}) is below threshold ({self._thresholds['min_success_rate']:.1%})",
                impact_estimate="Improving success rate by 10% could reduce escalations by 30%",
                confidence=0.8,
                evidence=[{"metric": "success_rate", "value": success_rate}]
            )
            opportunities.append(opp)
            self._opportunities[opp.id] = opp

        # Check escalation rate
        escalation_rate = metrics.escalated_conversations / max(metrics.total_conversations, 1)
        if escalation_rate > self._thresholds["max_escalation_rate"]:
            opp = ImprovementOpportunity(
                id=f"OPP-{str(uuid.uuid4())[:8].upper()}",
                action_type=ImprovementAction.ESCALATION_THRESHOLD_ADJUSTMENT,
                priority=ActionPriority.MEDIUM,
                title="High Escalation Rate",
                description=f"Escalation rate ({escalation_rate:.1%}) exceeds threshold ({self._thresholds['max_escalation_rate']:.1%})",
                impact_estimate="Reducing unnecessary escalations could save 20+ hours/month",
                confidence=0.7,
                evidence=[{"metric": "escalation_rate", "value": escalation_rate}],
                auto_executable=True
            )
            opportunities.append(opp)
            self._opportunities[opp.id] = opp

        # Check satisfaction
        if metrics.avg_satisfaction_score < self._thresholds["min_satisfaction"]:
            opp = ImprovementOpportunity(
                id=f"OPP-{str(uuid.uuid4())[:8].upper()}",
                action_type=ImprovementAction.RESPONSE_TEMPLATE_UPDATE,
                priority=ActionPriority.HIGH,
                title="Low Satisfaction Score",
                description=f"Average satisfaction ({metrics.avg_satisfaction_score:.1f}) below threshold ({self._thresholds['min_satisfaction']})",
                impact_estimate="Improving satisfaction correlates with 15% higher conversion",
                confidence=0.75,
                evidence=[{"metric": "satisfaction", "value": metrics.avg_satisfaction_score}]
            )
            opportunities.append(opp)
            self._opportunities[opp.id] = opp

        # Check knowledge gaps
        gap_rate = metrics.knowledge_gap_encounters / max(metrics.total_conversations, 1)
        if gap_rate > self._thresholds["max_knowledge_gap_rate"]:
            opp = ImprovementOpportunity(
                id=f"OPP-{str(uuid.uuid4())[:8].upper()}",
                action_type=ImprovementAction.KNOWLEDGE_BASE_UPDATE,
                priority=ActionPriority.MEDIUM,
                title="Frequent Knowledge Gaps",
                description=f"Knowledge gap rate ({gap_rate:.1%}) exceeds threshold",
                impact_estimate="Filling knowledge gaps could improve success rate by 8-12%",
                confidence=0.85,
                evidence=[{"metric": "knowledge_gap_rate", "value": gap_rate}],
                auto_executable=False
            )
            opportunities.append(opp)
            self._opportunities[opp.id] = opp

        # Check booking conversion
        if metrics.booking_conversion_rate < self._thresholds["min_booking_conversion"]:
            opp = ImprovementOpportunity(
                id=f"OPP-{str(uuid.uuid4())[:8].upper()}",
                action_type=ImprovementAction.AB_TEST_CREATION,
                priority=ActionPriority.HIGH,
                title="Low Booking Conversion",
                description=f"Booking conversion ({metrics.booking_conversion_rate:.1%}) below target ({self._thresholds['min_booking_conversion']:.1%})",
                impact_estimate="A/B testing booking scripts could improve conversion by 20-30%",
                confidence=0.7,
                suggested_implementation="Create A/B test for booking call-to-action variations",
                evidence=[{"metric": "booking_conversion", "value": metrics.booking_conversion_rate}]
            )
            opportunities.append(opp)
            self._opportunities[opp.id] = opp

        return opportunities

    def _execute_auto_actions(
        self,
        opportunities: List[ImprovementOpportunity]
    ) -> List[Dict]:
        """Execute automatic improvement actions and persist records."""
        _ensure_models()
        actions_taken = []

        for opp in opportunities:
            if not opp.auto_executable or opp.status != "identified":
                continue

            # Execute based on action type
            if opp.action_type == ImprovementAction.ESCALATION_THRESHOLD_ADJUSTMENT:
                result = self._auto_adjust_escalation()
                if result:
                    actions_taken.append({
                        "opportunity_id": opp.id,
                        "action": "escalation_adjustment",
                        "result": result,
                    })
                    opp.status = "completed"

            elif opp.action_type == ImprovementAction.PROMPT_OPTIMIZATION:
                opt_record = self._persist_prompt_optimization(
                    agent_role=opp.evidence[0].get("agent_role", "general") if opp.evidence else "general",
                    optimization_type="system_prompt",
                    previous_value=None,
                    new_value=opp.suggested_implementation,
                    reason=opp.description,
                    auto_apply=opp.auto_executable,
                )
                if opt_record:
                    actions_taken.append({
                        "opportunity_id": opp.id,
                        "action": "prompt_optimization_created",
                        "optimization_id": opt_record.id,
                        "auto_applied": opp.auto_executable,
                    })
                    opp.status = "completed"

        return actions_taken

    def _generate_recommendations(
        self,
        metrics: PerformanceMetrics,
        opportunities: List[ImprovementOpportunity]
    ) -> List[str]:
        """Generate human-readable recommendations"""
        recommendations = []

        # Priority-based recommendations
        critical = [o for o in opportunities if o.priority == ActionPriority.CRITICAL]
        high = [o for o in opportunities if o.priority == ActionPriority.HIGH]

        if critical:
            recommendations.append(
                f"URGENT: {len(critical)} critical issues require immediate attention"
            )

        if high:
            recommendations.append(
                f"HIGH PRIORITY: {len(high)} significant improvement opportunities identified"
            )

        # Specific recommendations based on metrics
        if metrics.avg_response_time_ms > 3000:
            recommendations.append(
                "Response times are slow (>3s). Consider optimizing prompts or caching."
            )

        if metrics.repeat_caller_rate > 0.20:
            recommendations.append(
                "High repeat caller rate suggests unresolved issues. Review first-call resolution."
            )

        # Fine-tuning readiness
        if self.ai_learning:
            dataset = self.ai_learning.get_training_dataset(approved_only=True, limit=1)
            if len(dataset) >= 100:
                recommendations.append(
                    "Sufficient training data available. Consider scheduling fine-tuning job."
                )

        return recommendations

    def _check_threshold_violations(self, metrics: PerformanceMetrics) -> List[Dict]:
        """Check which thresholds are being violated"""
        violations = []

        success_rate = metrics.successful_conversations / max(metrics.total_conversations, 1)
        if success_rate < self._thresholds["min_success_rate"]:
            violations.append({
                "metric": "success_rate",
                "current": success_rate,
                "threshold": self._thresholds["min_success_rate"],
                "severity": "high"
            })

        escalation_rate = metrics.escalated_conversations / max(metrics.total_conversations, 1)
        if escalation_rate > self._thresholds["max_escalation_rate"]:
            violations.append({
                "metric": "escalation_rate",
                "current": escalation_rate,
                "threshold": self._thresholds["max_escalation_rate"],
                "severity": "medium"
            })

        if metrics.avg_satisfaction_score < self._thresholds["min_satisfaction"]:
            violations.append({
                "metric": "satisfaction",
                "current": metrics.avg_satisfaction_score,
                "threshold": self._thresholds["min_satisfaction"],
                "severity": "high"
            })

        return violations

    def _calculate_trends(
        self,
        day_metrics: PerformanceMetrics,
        week_metrics: PerformanceMetrics
    ) -> Dict[str, Any]:
        """Calculate metric trends"""
        def calc_change(current, previous):
            if previous == 0:
                return 0
            return ((current - previous) / previous) * 100

        day_success = day_metrics.successful_conversations / max(day_metrics.total_conversations, 1)
        week_success = week_metrics.successful_conversations / max(week_metrics.total_conversations, 1)

        return {
            "success_rate": {
                "direction": "up" if day_success > week_success else "down",
                "change_percent": calc_change(day_success, week_success)
            },
            "satisfaction": {
                "direction": "up" if day_metrics.avg_satisfaction_score > week_metrics.avg_satisfaction_score else "down",
                "change_percent": calc_change(
                    day_metrics.avg_satisfaction_score,
                    week_metrics.avg_satisfaction_score
                )
            },
            "booking_conversion": {
                "direction": "up" if day_metrics.booking_conversion_rate > week_metrics.booking_conversion_rate else "down",
                "change_percent": calc_change(
                    day_metrics.booking_conversion_rate,
                    week_metrics.booking_conversion_rate
                )
            }
        }

    def _calculate_health_score(self, metrics: PerformanceMetrics) -> float:
        """Calculate overall AI health score (0-100)"""
        scores = []

        # Success rate component (40%)
        success_rate = metrics.successful_conversations / max(metrics.total_conversations, 1)
        scores.append(min(success_rate / self._thresholds["min_success_rate"], 1.0) * 40)

        # Satisfaction component (30%)
        sat_ratio = metrics.avg_satisfaction_score / 5.0
        scores.append(sat_ratio * 30)

        # Low escalation component (15%)
        escalation_rate = metrics.escalated_conversations / max(metrics.total_conversations, 1)
        esc_score = max(0, 1 - (escalation_rate / self._thresholds["max_escalation_rate"]))
        scores.append(esc_score * 15)

        # Conversion component (15%)
        conv_ratio = min(metrics.booking_conversion_rate / self._thresholds["min_booking_conversion"], 1.0)
        scores.append(conv_ratio * 15)

        return sum(scores)

    def _generate_failure_recommendations(
        self,
        reasons: List[Tuple[str, int]],
        topics: List[Tuple[str, int]]
    ) -> List[str]:
        """Generate recommendations based on failure analysis"""
        recommendations = []

        reason_actions = {
            "knowledge_gap": "Update knowledge base with missing information",
            "misunderstanding": "Improve intent classification and clarification prompts",
            "wrong_answer": "Review and correct training data for affected topics",
            "hallucination": "Add guardrails and fact-checking for sensitive topics",
            "caller_frustration": "Lower escalation threshold and improve empathy responses",
            "slow_response": "Optimize prompts and consider response caching",
            "out_of_scope": "Add clear scope boundaries and handoff procedures"
        }

        for reason, count in reasons[:3]:
            if reason in reason_actions:
                recommendations.append(
                    f"{reason_actions[reason]} (affects {count} conversations)"
                )

        if topics:
            top_topics = [t[0] for t in topics[:3]]
            recommendations.append(
                f"Focus knowledge base improvements on: {', '.join(top_topics)}"
            )

        return recommendations

    def _suggest_prompt_ab_test(
        self,
        opportunity: ImprovementOpportunity
    ) -> Dict[str, Any]:
        """Generate prompt A/B test suggestion"""
        return {
            "test_type": "prompt_optimization",
            "based_on_opportunity": opportunity.id,
            "name": f"Prompt Test - {opportunity.title}",
            "description": f"A/B test to address: {opportunity.description}",
            "variants": [
                {
                    "name": "Control - Current Prompt",
                    "is_control": True,
                    "traffic_allocation": 50,
                    "config": {"use_current": True}
                },
                {
                    "name": "Treatment - Optimized Prompt",
                    "traffic_allocation": 50,
                    "config": {
                        "modifications": [
                            "Add more specific instructions",
                            "Include clarification prompts",
                            "Improve context handling"
                        ]
                    }
                }
            ],
            "primary_metric": "success_rate",
            "min_sample_size": 200,
            "expected_duration_days": 7
        }

    def _suggest_template_ab_test(
        self,
        opportunity: ImprovementOpportunity
    ) -> Dict[str, Any]:
        """Generate response template A/B test suggestion"""
        return {
            "test_type": "response_template",
            "based_on_opportunity": opportunity.id,
            "name": f"Response Test - {opportunity.title}",
            "description": f"A/B test to address: {opportunity.description}",
            "variants": [
                {
                    "name": "Control - Current Templates",
                    "is_control": True,
                    "traffic_allocation": 50
                },
                {
                    "name": "Treatment - Enhanced Templates",
                    "traffic_allocation": 50,
                    "config": {
                        "modifications": [
                            "More empathetic tone",
                            "Clearer call-to-actions",
                            "Better information structure"
                        ]
                    }
                }
            ],
            "primary_metric": "caller_satisfaction",
            "min_sample_size": 150,
            "expected_duration_days": 5
        }

    def _auto_adjust_escalation(self) -> Optional[Dict]:
        """Automatically adjust escalation threshold"""
        # This would integrate with the actual escalation system
        current_threshold = 0.3  # Example
        new_threshold = current_threshold * 0.9  # Reduce by 10%

        logger.info(f"Auto-adjusted escalation threshold: {current_threshold} -> {new_threshold}")

        return {
            "previous_threshold": current_threshold,
            "new_threshold": new_threshold,
            "adjustment_reason": "High escalation rate detected"
        }

    def _queue_for_execution(self, opportunity: ImprovementOpportunity):
        """Queue an opportunity for execution"""
        opportunity.status = "executing"
        logger.info(f"Queued for execution: {opportunity.title}")

    def _generate_content_suggestion(self, gap) -> str:
        """Generate content suggestion for a knowledge gap"""
        return f"Suggested content to address '{gap.topic}': [AI would generate appropriate content based on example queries]"

    # -----------------------------------------------------------------------
    # DB persistence helpers
    # -----------------------------------------------------------------------

    def _upsert_pattern(
        self,
        session: Session,
        org_id: int,
        pattern_type: str,
        pattern_key: str,
        pattern_value: str,
        increment: int = 1,
    ) -> Tuple[bool, bool]:
        """
        Insert or update a LearningPattern record.

        Returns:
            (created, updated) — exactly one is True on success, both False on error
        """
        if _LearningPattern is None:
            return False, False

        try:
            existing = (
                session.query(_LearningPattern)
                .filter_by(
                    organization_id=org_id,
                    pattern_type=pattern_type,
                    pattern_key=pattern_key,
                )
                .first()
            )

            now = datetime.now(timezone.utc)

            if existing:
                existing.occurrence_count = (existing.occurrence_count or 0) + increment
                existing.pattern_value = pattern_value
                existing.last_seen_at = now
                # Confidence grows with occurrences but caps at 1.0
                new_conf = min(1.0, 0.3 + 0.05 * existing.occurrence_count)
                existing.confidence = new_conf
                return False, True
            else:
                record = _LearningPattern(
                    organization_id=org_id,
                    pattern_type=pattern_type,
                    pattern_key=pattern_key,
                    pattern_value=pattern_value,
                    occurrence_count=increment,
                    confidence=min(1.0, 0.3 + 0.05 * increment),
                    last_seen_at=now,
                    is_active=True,
                )
                session.add(record)
                return True, False

        except Exception as e:
            logger.exception(f"Error upserting pattern {pattern_key}: {e}")
            return False, False

    def _persist_prompt_optimization(
        self,
        agent_role: str,
        optimization_type: str,
        previous_value: Optional[str],
        new_value: Optional[str],
        reason: str,
        auto_apply: bool = False,
        session_override: Optional[Session] = None,
    ) -> Optional[Any]:
        """
        Create a PromptOptimization record in the DB.

        If auto_apply is True, sets applied_at immediately.

        Args:
            agent_role: Target agent
            optimization_type: one of system_prompt, few_shot, tool_description, intent_pattern
            previous_value: The old prompt/config text (nullable)
            new_value: The suggested new text
            reason: Why this optimization is proposed
            auto_apply: Whether to mark as applied immediately
            session_override: Use this session instead of self._get_db()

        Returns:
            The created PromptOptimization ORM object, or None on failure
        """
        if _PromptOptimization is None:
            _ensure_models()
            if _PromptOptimization is None:
                return None

        session = session_override or self._get_db()
        if session is None:
            return None

        owns_session = session is not session_override and session is not self.db

        try:
            now = datetime.now(timezone.utc)
            opt = _PromptOptimization(
                agent_role=agent_role,
                optimization_type=optimization_type,
                previous_value=previous_value,
                new_value=new_value,
                reason=reason,
                is_active=auto_apply,
                applied_at=now if auto_apply else None,
            )
            session.add(opt)

            # If we own the session, commit; otherwise let the caller commit
            if owns_session:
                session.commit()

            # Flush to get the ID even if caller will commit later
            session.flush()
            logger.info(
                f"Created PromptOptimization id={opt.id} role={agent_role} "
                f"type={optimization_type} auto_applied={auto_apply}"
            )
            return opt

        except Exception as e:
            logger.exception(f"Error persisting prompt optimization: {e}")
            if owns_session:
                try:
                    session.rollback()
                except Exception as _exc:  # noqa: BLE001
                    pass
            return None
        finally:
            if owns_session:
                self._close_fallback(session)


# Create singleton instance
continuous_learning_meta_agent = ContinuousLearningMetaAgent()
