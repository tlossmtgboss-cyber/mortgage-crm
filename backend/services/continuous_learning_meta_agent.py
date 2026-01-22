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

logger = logging.getLogger(__name__)


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
        import uuid
        cycle_id = f"LC-{str(uuid.uuid4())[:8].upper()}"

        started_at = datetime.now(timezone.utc)
        period_start = started_at - timedelta(hours=period_hours)

        logger.info(f"Starting learning cycle {cycle_id} for last {period_hours} hours")

        # Step 1: Gather metrics
        metrics = self._gather_performance_metrics(period_start, started_at)

        # Step 2: Analyze and identify opportunities
        opportunities = self._analyze_and_identify_opportunities(metrics)

        # Step 3: Take automated actions
        actions_taken = self._execute_auto_actions(opportunities)

        # Step 4: Generate recommendations
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

    # Private helper methods

    def _gather_performance_metrics(
        self,
        start: datetime,
        end: datetime
    ) -> PerformanceMetrics:
        """Gather performance metrics for a period"""
        # In production, this would query the database
        # For now, return sample metrics
        return PerformanceMetrics(
            period_start=start,
            period_end=end,
            total_conversations=100,
            successful_conversations=75,
            failed_conversations=15,
            escalated_conversations=10,
            avg_satisfaction_score=4.2,
            avg_response_time_ms=1500,
            booking_conversion_rate=0.28,
            first_call_resolution_rate=0.72,
            knowledge_gap_encounters=8,
            repeat_caller_rate=0.15
        )

    def _analyze_and_identify_opportunities(
        self,
        metrics: PerformanceMetrics
    ) -> List[ImprovementOpportunity]:
        """Analyze metrics and identify improvement opportunities"""
        import uuid
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
        """Execute automatic improvement actions"""
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
                        "result": result
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


# Create singleton instance
continuous_learning_meta_agent = ContinuousLearningMetaAgent()
