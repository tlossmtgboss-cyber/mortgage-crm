"""
AI Metrics Service
Handles collection, storage, and retrieval of AI agent metrics.
"""

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import text

from .models import (
    AIMetricType,
    AIMetricEvent,
    ResponseTimeMetric,
    ToolExecutionMetric,
    UserFeedbackMetric,
    IntentClassificationMetric,
    QueryAnalytics,
    AgentPerformanceMetrics,
    BusinessMetrics,
    AIQualityMetrics,
    FeedbackType,
    HallucinationReport,
    HallucinationMetrics,
    ClaimType,
    VerificationStatus,
)

logger = logging.getLogger(__name__)


class AIMetricsService:
    """
    Service for tracking and analyzing AI agent metrics.

    Tracks:
    - Agent Performance: response times, tool success, errors, user satisfaction
    - Business Metrics: query patterns, tool usage, actions, engagement
    - AI Quality: intent accuracy, tool selection, response quality
    """

    # Table name for metrics storage
    TABLE_NAME = "ai_metrics"

    @staticmethod
    async def ensure_table_exists(db: Session) -> bool:
        """Create the metrics table if it doesn't exist."""
        try:
            result = db.execute(text("""
                SELECT table_name FROM information_schema.tables
                WHERE table_schema = 'public' AND table_name = 'ai_metrics'
            """))

            if not result.fetchone():
                db.execute(text("""
                    CREATE TABLE ai_metrics (
                        id SERIAL PRIMARY KEY,
                        metric_type VARCHAR(50) NOT NULL,
                        user_id INTEGER NOT NULL,
                        session_id UUID,
                        value FLOAT NOT NULL,
                        metadata JSONB,
                        created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL
                    )
                """))

                # Create indexes for efficient querying
                db.execute(text("CREATE INDEX idx_metrics_type_time ON ai_metrics(metric_type, created_at)"))
                db.execute(text("CREATE INDEX idx_metrics_user ON ai_metrics(user_id, created_at)"))
                db.execute(text("CREATE INDEX idx_metrics_session ON ai_metrics(session_id)"))

                db.commit()
                logger.info("Created ai_metrics table with indexes")
                return True
            return True

        except Exception as e:
            logger.error(f"Error ensuring metrics table exists: {e}")
            try:
                db.rollback()
            except Exception:
                pass
            return False

    @staticmethod
    async def record_metric(
        db: Session,
        metric_type: AIMetricType,
        user_id: int,
        value: float,
        session_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Record a single metric event."""
        try:
            metadata_json = json.dumps(metadata) if metadata else None

            db.execute(text("""
                INSERT INTO ai_metrics (metric_type, user_id, session_id, value, metadata, created_at)
                VALUES (
                    :metric_type,
                    :user_id,
                    CAST(:session_id AS UUID),
                    :value,
                    CAST(:metadata AS JSONB),
                    NOW()
                )
            """), {
                "metric_type": metric_type.value if isinstance(metric_type, AIMetricType) else metric_type,
                "user_id": user_id,
                "session_id": session_id,
                "value": value,
                "metadata": metadata_json
            })
            db.commit()
            return True

        except Exception as e:
            logger.error(f"Error recording metric: {e}")
            try:
                db.rollback()
            except Exception:
                pass
            return False

    @staticmethod
    async def record_response_time(
        db: Session,
        user_id: int,
        session_id: str,
        response_time: ResponseTimeMetric
    ) -> bool:
        """Record response time metrics with breakdown."""
        return await AIMetricsService.record_metric(
            db=db,
            metric_type=AIMetricType.RESPONSE_TIME,
            user_id=user_id,
            value=response_time.total_ms,
            session_id=session_id,
            metadata={
                "breakdown": {
                    "analyze_ms": response_time.analyze_ms,
                    "gather_ms": response_time.gather_ms,
                    "reason_ms": response_time.reason_ms,
                    "execute_ms": response_time.execute_ms,
                    "respond_ms": response_time.respond_ms
                },
                "query_type": response_time.query_type,
                "tools_used": response_time.tools_used
            }
        )

    @staticmethod
    async def record_tool_execution(
        db: Session,
        user_id: int,
        session_id: str,
        tool_metric: ToolExecutionMetric
    ) -> bool:
        """Record tool execution metrics."""
        return await AIMetricsService.record_metric(
            db=db,
            metric_type=AIMetricType.TOOL_EXECUTION,
            user_id=user_id,
            value=1.0 if tool_metric.success else 0.0,
            session_id=session_id,
            metadata={
                "tool_name": tool_metric.tool_name,
                "execution_time_ms": tool_metric.execution_time_ms,
                "success": tool_metric.success,
                "error_message": tool_metric.error_message,
                "input_summary": tool_metric.input_summary,
                "output_summary": tool_metric.output_summary
            }
        )

    @staticmethod
    async def record_user_feedback(
        db: Session,
        user_id: int,
        feedback: UserFeedbackMetric
    ) -> bool:
        """Record user feedback on AI response."""
        # Convert feedback to numeric value
        value_map = {
            FeedbackType.THUMBS_UP: 1.0,
            FeedbackType.THUMBS_DOWN: 0.0,
            FeedbackType.HELPFUL: 1.0,
            FeedbackType.NOT_HELPFUL: 0.0,
            FeedbackType.ACCURATE: 1.0,
            FeedbackType.INACCURATE: 0.0
        }
        value = value_map.get(feedback.feedback_type, 0.5)

        return await AIMetricsService.record_metric(
            db=db,
            metric_type=AIMetricType.USER_FEEDBACK,
            user_id=user_id,
            value=value,
            session_id=feedback.session_id,
            metadata={
                "feedback_type": feedback.feedback_type.value,
                "rating": feedback.rating,
                "comment": feedback.comment,
                "message_id": feedback.message_id,
                "query_type": feedback.query_type
            }
        )

    @staticmethod
    async def record_intent_classification(
        db: Session,
        user_id: int,
        session_id: str,
        intent_metric: IntentClassificationMetric
    ) -> bool:
        """Record intent classification for accuracy tracking."""
        return await AIMetricsService.record_metric(
            db=db,
            metric_type=AIMetricType.INTENT_CLASSIFICATION,
            user_id=user_id,
            value=intent_metric.confidence,
            session_id=session_id,
            metadata={
                "detected_intent": intent_metric.detected_intent,
                "user_confirmed": intent_metric.user_confirmed,
                "actual_intent": intent_metric.actual_intent
            }
        )

    @staticmethod
    async def record_query(
        db: Session,
        user_id: int,
        session_id: str,
        query_type: str,
        query_text: str
    ) -> bool:
        """Record a query for business analytics."""
        return await AIMetricsService.record_metric(
            db=db,
            metric_type=AIMetricType.QUERY_TYPE,
            user_id=user_id,
            value=1.0,
            session_id=session_id,
            metadata={
                "query_type": query_type,
                "query_length": len(query_text),
                "query_preview": query_text[:100] if query_text else None
            }
        )

    @staticmethod
    async def record_tool_usage(
        db: Session,
        user_id: int,
        session_id: str,
        tools_used: List[str]
    ) -> bool:
        """Record which tools were used in a query."""
        for tool in tools_used:
            await AIMetricsService.record_metric(
                db=db,
                metric_type=AIMetricType.TOOL_USAGE,
                user_id=user_id,
                value=1.0,
                session_id=session_id,
                metadata={"tool_name": tool}
            )
        return True

    @staticmethod
    async def record_action_executed(
        db: Session,
        user_id: int,
        session_id: str,
        action_type: str,
        success: bool,
        details: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Record an action executed by the AI."""
        return await AIMetricsService.record_metric(
            db=db,
            metric_type=AIMetricType.ACTION_EXECUTED,
            user_id=user_id,
            value=1.0 if success else 0.0,
            session_id=session_id,
            metadata={
                "action_type": action_type,
                "success": success,
                "details": details
            }
        )

    @staticmethod
    async def record_followup_click(
        db: Session,
        user_id: int,
        session_id: str,
        suggestion_text: str,
        suggestion_index: int
    ) -> bool:
        """Record when user clicks a follow-up suggestion."""
        return await AIMetricsService.record_metric(
            db=db,
            metric_type=AIMetricType.FOLLOWUP_CLICK,
            user_id=user_id,
            value=1.0,
            session_id=session_id,
            metadata={
                "suggestion_text": suggestion_text,
                "suggestion_index": suggestion_index
            }
        )

    @staticmethod
    async def record_node_error(
        db: Session,
        user_id: int,
        session_id: str,
        node_name: str,
        error_message: str,
        error_type: Optional[str] = None
    ) -> bool:
        """Record an error that occurred in a specific node."""
        return await AIMetricsService.record_metric(
            db=db,
            metric_type=AIMetricType.NODE_ERROR,
            user_id=user_id,
            value=1.0,
            session_id=session_id,
            metadata={
                "node_name": node_name,
                "error_message": error_message,
                "error_type": error_type
            }
        )

    # =========================================================================
    # HALLUCINATION TRACKING METHODS
    # =========================================================================

    @staticmethod
    async def record_hallucination_report(
        db: Session,
        user_id: int,
        report: HallucinationReport
    ) -> bool:
        """
        Record a complete hallucination report for an AI response.
        Records multiple metrics: faithfulness score, individual claims, and hallucination detection.
        """
        try:
            # Record the overall faithfulness score
            await AIMetricsService.record_metric(
                db=db,
                metric_type=AIMetricType.FAITHFULNESS_SCORE,
                user_id=user_id,
                value=report.faithfulness_score,
                session_id=report.session_id,
                metadata={
                    "message_id": report.message_id,
                    "total_claims": report.total_claims,
                    "verified_claims": report.verified_claims,
                    "unsupported_claims": report.unsupported_claims,
                    "contradicted_claims": report.contradicted_claims,
                    "partial_claims": report.partial_claims,
                    "hallucination_rate": report.hallucination_rate,
                    "confidence": report.confidence,
                    "tools_used": report.tools_used,
                    "analysis_time_ms": report.analysis_time_ms,
                }
            )

            # Record hallucination detection if any contradicted claims
            if report.contradicted_claims > 0:
                await AIMetricsService.record_metric(
                    db=db,
                    metric_type=AIMetricType.HALLUCINATION_DETECTED,
                    user_id=user_id,
                    value=report.contradicted_claims,
                    session_id=report.session_id,
                    metadata={
                        "message_id": report.message_id,
                        "hallucination_rate": report.hallucination_rate,
                        "contradicted_claims": [
                            {
                                "claim_id": r.claim_id,
                                "claim_text": r.claim_text[:200],
                                "claim_type": r.claim_type.value if hasattr(r.claim_type, 'value') else str(r.claim_type),
                                "expected_value": str(r.expected_value)[:100] if r.expected_value else None,
                                "claimed_value": str(r.claimed_value)[:100] if r.claimed_value else None,
                                "discrepancy": r.discrepancy[:200] if r.discrepancy else None,
                            }
                            for r in report.verification_results
                            if r.status == VerificationStatus.CONTRADICTED
                        ][:10]  # Limit to 10 for storage
                    }
                )

            # Record individual claim verifications (sample for high-volume)
            for result in report.verification_results[:20]:  # Limit per response
                metric_type = {
                    VerificationStatus.VERIFIED: AIMetricType.CLAIM_VERIFIED,
                    VerificationStatus.UNSUPPORTED: AIMetricType.CLAIM_UNSUPPORTED,
                    VerificationStatus.CONTRADICTED: AIMetricType.CLAIM_CONTRADICTED,
                }.get(result.status)

                if metric_type:
                    await AIMetricsService.record_metric(
                        db=db,
                        metric_type=metric_type,
                        user_id=user_id,
                        value=result.confidence,
                        session_id=report.session_id,
                        metadata={
                            "message_id": report.message_id,
                            "claim_id": result.claim_id,
                            "claim_type": result.claim_type.value if hasattr(result.claim_type, 'value') else str(result.claim_type),
                            "source_tool": result.source_tool,
                        }
                    )

            return True

        except Exception as e:
            logger.error(f"Error recording hallucination report: {e}")
            try:
                db.rollback()
            except Exception:
                pass
            return False

    @staticmethod
    async def get_hallucination_metrics(
        db: Session,
        days: int = 7,
        user_id: Optional[int] = None
    ) -> HallucinationMetrics:
        """Get aggregated hallucination metrics over a period."""
        try:
            period_start = datetime.now(timezone.utc) - timedelta(days=days)
            period_end = datetime.now(timezone.utc)

            user_filter = "AND user_id = :user_id" if user_id else ""
            params = {"days": days}
            if user_id:
                params["user_id"] = user_id

            # Get faithfulness scores
            faith_result = db.execute(text(f"""
                SELECT
                    AVG(value) as avg_faithfulness,
                    AVG((metadata->>'hallucination_rate')::float) as avg_hallucination_rate,
                    COUNT(*) as total_responses,
                    SUM((metadata->>'total_claims')::int) as total_claims,
                    SUM((metadata->>'verified_claims')::int) as verified_claims,
                    SUM((metadata->>'unsupported_claims')::int) as unsupported_claims,
                    SUM((metadata->>'contradicted_claims')::int) as contradicted_claims,
                    COUNT(CASE WHEN (metadata->>'contradicted_claims')::int > 0 THEN 1 END) as responses_with_hallucinations,
                    COUNT(CASE WHEN (metadata->>'contradicted_claims')::int = 0 THEN 1 END) as clean_responses
                FROM ai_metrics
                WHERE metric_type = 'faithfulness_score'
                AND created_at > NOW() - (INTERVAL '1 day' * :days)
                {user_filter}
            """), params)
            faith_row = faith_result.fetchone()

            # Get hallucination rate by claim type
            type_result = db.execute(text(f"""
                SELECT
                    metadata->>'claim_type' as claim_type,
                    COUNT(*) as total,
                    COUNT(CASE WHEN metric_type = 'claim_contradicted' THEN 1 END) as contradicted
                FROM ai_metrics
                WHERE metric_type IN ('claim_verified', 'claim_unsupported', 'claim_contradicted')
                AND created_at > NOW() - (INTERVAL '1 day' * :days)
                {user_filter}
                GROUP BY metadata->>'claim_type'
            """), params)
            hallucination_by_type = {}
            for row in type_result:
                claim_type = row[0] or 'unknown'
                total = row[1] or 1
                contradicted = row[2] or 0
                hallucination_by_type[claim_type] = contradicted / total if total > 0 else 0

            # Get hallucination rate by tool
            tool_result = db.execute(text(f"""
                SELECT
                    metadata->>'source_tool' as tool,
                    COUNT(*) as total,
                    COUNT(CASE WHEN metric_type = 'claim_contradicted' THEN 1 END) as contradicted
                FROM ai_metrics
                WHERE metric_type IN ('claim_verified', 'claim_unsupported', 'claim_contradicted')
                AND metadata->>'source_tool' IS NOT NULL
                AND created_at > NOW() - (INTERVAL '1 day' * :days)
                {user_filter}
                GROUP BY metadata->>'source_tool'
            """), params)
            hallucination_by_tool = {}
            for row in tool_result:
                tool = row[0] or 'unknown'
                total = row[1] or 1
                contradicted = row[2] or 0
                hallucination_by_tool[tool] = contradicted / total if total > 0 else 0

            # Calculate verification rate
            total_claims = faith_row[3] or 0
            verified = faith_row[4] or 0
            unsupported = faith_row[5] or 0
            contradicted = faith_row[6] or 0
            verifiable = verified + contradicted
            verification_rate = verifiable / total_claims if total_claims > 0 else 0

            return HallucinationMetrics(
                avg_faithfulness_score=faith_row[0] or 1.0,
                avg_hallucination_rate=faith_row[1] or 0.0,
                total_responses_analyzed=faith_row[2] or 0,
                total_claims_extracted=total_claims,
                verified_claims_count=verified,
                unsupported_claims_count=unsupported,
                contradicted_claims_count=contradicted,
                verification_rate=verification_rate,
                hallucination_by_type=hallucination_by_type,
                hallucination_by_tool=hallucination_by_tool,
                responses_with_hallucinations=faith_row[7] or 0,
                clean_responses=faith_row[8] or 0,
                period_start=period_start,
                period_end=period_end
            )

        except Exception as e:
            logger.error(f"Error getting hallucination metrics: {e}")
            try:
                db.rollback()
            except Exception:
                pass
            return HallucinationMetrics(
                avg_faithfulness_score=1.0,
                avg_hallucination_rate=0.0,
                total_responses_analyzed=0,
                total_claims_extracted=0,
                verified_claims_count=0,
                unsupported_claims_count=0,
                contradicted_claims_count=0,
                verification_rate=0.0,
                hallucination_by_type={},
                hallucination_by_tool={},
                responses_with_hallucinations=0,
                clean_responses=0,
                period_start=datetime.now(timezone.utc) - timedelta(days=days),
                period_end=datetime.now(timezone.utc)
            )

    # =========================================================================
    # ANALYTICS METHODS
    # =========================================================================

    @staticmethod
    async def get_agent_performance(
        db: Session,
        days: int = 7,
        user_id: Optional[int] = None
    ) -> AgentPerformanceMetrics:
        """Get aggregated agent performance metrics."""
        try:
            period_start = datetime.now(timezone.utc) - timedelta(days=days)
            period_end = datetime.now(timezone.utc)

            user_filter = "AND user_id = :user_id" if user_id else ""
            params = {"days": days}
            if user_id:
                params["user_id"] = user_id

            # Response time stats
            time_result = db.execute(text(f"""
                SELECT
                    AVG(value) as avg_time,
                    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY value) as p50,
                    PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY value) as p95,
                    PERCENTILE_CONT(0.99) WITHIN GROUP (ORDER BY value) as p99
                FROM ai_metrics
                WHERE metric_type = 'response_time'
                AND created_at > NOW() - (INTERVAL '1 day' * :days)
                {user_filter}
            """), params)
            time_row = time_result.fetchone()

            # Tool success rate
            tool_result = db.execute(text(f"""
                SELECT
                    COUNT(*) as total,
                    SUM(value) as successes
                FROM ai_metrics
                WHERE metric_type = 'tool_execution'
                AND created_at > NOW() - (INTERVAL '1 day' * :days)
                {user_filter}
            """), params)
            tool_row = tool_result.fetchone()

            # Error counts by node
            error_result = db.execute(text(f"""
                SELECT
                    metadata->>'node_name' as node_name,
                    COUNT(*) as error_count
                FROM ai_metrics
                WHERE metric_type = 'node_error'
                AND created_at > NOW() - (INTERVAL '1 day' * :days)
                {user_filter}
                GROUP BY metadata->>'node_name'
            """), params)
            errors_by_node = {row[0]: row[1] for row in error_result}

            # Total errors
            total_queries_result = db.execute(text(f"""
                SELECT COUNT(*) FROM ai_metrics
                WHERE metric_type = 'query_type'
                AND created_at > NOW() - (INTERVAL '1 day' * :days)
                {user_filter}
            """), params)
            total_queries = total_queries_result.scalar() or 1

            total_errors = sum(errors_by_node.values())
            error_rate = total_errors / total_queries if total_queries > 0 else 0

            # User feedback
            feedback_result = db.execute(text(f"""
                SELECT
                    SUM(CASE WHEN value = 1 THEN 1 ELSE 0 END) as positive,
                    SUM(CASE WHEN value = 0 THEN 1 ELSE 0 END) as negative
                FROM ai_metrics
                WHERE metric_type = 'user_feedback'
                AND created_at > NOW() - (INTERVAL '1 day' * :days)
                {user_filter}
            """), params)
            feedback_row = feedback_result.fetchone()

            positive = feedback_row[0] or 0
            negative = feedback_row[1] or 0
            total_feedback = positive + negative
            satisfaction_rate = positive / total_feedback if total_feedback > 0 else 0

            return AgentPerformanceMetrics(
                avg_response_time_ms=time_row[0] or 0,
                p50_response_time_ms=time_row[1] or 0,
                p95_response_time_ms=time_row[2] or 0,
                p99_response_time_ms=time_row[3] or 0,
                tool_success_rate=(tool_row[1] or 0) / (tool_row[0] or 1),
                error_rate=error_rate,
                errors_by_node=errors_by_node,
                thumbs_up_count=positive,
                thumbs_down_count=negative,
                satisfaction_rate=satisfaction_rate,
                period_start=period_start,
                period_end=period_end
            )

        except Exception as e:
            logger.error(f"Error getting agent performance: {e}")
            try:
                db.rollback()
            except Exception:
                pass
            return AgentPerformanceMetrics(
                avg_response_time_ms=0,
                p50_response_time_ms=0,
                p95_response_time_ms=0,
                p99_response_time_ms=0,
                tool_success_rate=0,
                error_rate=0,
                errors_by_node={},
                thumbs_up_count=0,
                thumbs_down_count=0,
                satisfaction_rate=0,
                period_start=datetime.now(timezone.utc) - timedelta(days=days),
                period_end=datetime.now(timezone.utc)
            )

    @staticmethod
    async def get_business_metrics(
        db: Session,
        days: int = 7
    ) -> BusinessMetrics:
        """Get business-level metrics."""
        try:
            period_start = datetime.now(timezone.utc) - timedelta(days=days)
            period_end = datetime.now(timezone.utc)

            # Total queries and unique users
            query_result = db.execute(text(f"""
                SELECT
                    COUNT(*) as total_queries,
                    COUNT(DISTINCT user_id) as unique_users
                FROM ai_metrics
                WHERE metric_type = 'query_type'
                AND created_at > NOW() - (INTERVAL '1 day' * :days)
            """))
            query_row = query_result.fetchone()
            total_queries = query_row[0] or 0
            unique_users = query_row[1] or 1

            # Most common queries
            common_result = db.execute(text(f"""
                SELECT
                    metadata->>'query_type' as query_type,
                    COUNT(*) as count
                FROM ai_metrics
                WHERE metric_type = 'query_type'
                AND created_at > NOW() - (INTERVAL '1 day' * :days)
                GROUP BY metadata->>'query_type'
                ORDER BY count DESC
                LIMIT 10
            """))
            most_common = [{"query_type": row[0], "count": row[1]} for row in common_result]

            # Tool usage ranking
            tool_result = db.execute(text(f"""
                SELECT
                    metadata->>'tool_name' as tool_name,
                    COUNT(*) as usage_count,
                    AVG(value) as success_rate
                FROM ai_metrics
                WHERE metric_type IN ('tool_usage', 'tool_execution')
                AND created_at > NOW() - (INTERVAL '1 day' * :days)
                GROUP BY metadata->>'tool_name'
                ORDER BY usage_count DESC
                LIMIT 20
            """))
            tool_ranking = [
                {"tool_name": row[0], "usage_count": row[1], "success_rate": row[2] or 1.0}
                for row in tool_result
            ]

            # Actions executed
            action_result = db.execute(text(f"""
                SELECT
                    COUNT(*) as total,
                    metadata->>'action_type' as action_type
                FROM ai_metrics
                WHERE metric_type = 'action_executed'
                AND created_at > NOW() - (INTERVAL '1 day' * :days)
                GROUP BY metadata->>'action_type'
            """))
            actions_by_type = {}
            total_actions = 0
            for row in action_result:
                actions_by_type[row[1] or 'unknown'] = row[0]
                total_actions += row[0]

            # Engagement (sessions per user, messages per session)
            engagement_result = db.execute(text(f"""
                SELECT
                    COUNT(DISTINCT session_id) as total_sessions,
                    COUNT(*) as total_messages
                FROM ai_metrics
                WHERE metric_type = 'query_type'
                AND created_at > NOW() - (INTERVAL '1 day' * :days)
            """))
            eng_row = engagement_result.fetchone()
            total_sessions = eng_row[0] or 1
            total_messages = eng_row[1] or 0

            return BusinessMetrics(
                total_queries=total_queries,
                unique_users=unique_users,
                queries_per_user=total_queries / unique_users if unique_users > 0 else 0,
                most_common_queries=most_common,
                tool_usage_ranking=tool_ranking,
                actions_executed=total_actions,
                actions_by_type=actions_by_type,
                engagement_metrics={
                    "total_sessions": total_sessions,
                    "messages_per_session": total_messages / total_sessions if total_sessions > 0 else 0,
                    "sessions_per_user": total_sessions / unique_users if unique_users > 0 else 0
                },
                period_start=period_start,
                period_end=period_end
            )

        except Exception as e:
            logger.error(f"Error getting business metrics: {e}")
            try:
                db.rollback()
            except Exception:
                pass
            return BusinessMetrics(
                total_queries=0,
                unique_users=0,
                queries_per_user=0,
                most_common_queries=[],
                tool_usage_ranking=[],
                actions_executed=0,
                actions_by_type={},
                engagement_metrics={},
                period_start=datetime.now(timezone.utc) - timedelta(days=days),
                period_end=datetime.now(timezone.utc)
            )

    @staticmethod
    async def get_ai_quality_metrics(
        db: Session,
        days: int = 7
    ) -> AIQualityMetrics:
        """Get AI quality metrics."""
        try:
            period_start = datetime.now(timezone.utc) - timedelta(days=days)
            period_end = datetime.now(timezone.utc)

            # Intent classification accuracy (based on user confirmations)
            intent_result = db.execute(text(f"""
                SELECT
                    AVG(value) as avg_confidence,
                    COUNT(CASE WHEN (metadata->>'user_confirmed')::boolean = true THEN 1 END) as confirmed_correct,
                    COUNT(CASE WHEN (metadata->>'user_confirmed')::boolean = false THEN 1 END) as confirmed_wrong,
                    COUNT(CASE WHEN metadata->>'user_confirmed' IS NOT NULL THEN 1 END) as total_confirmed
                FROM ai_metrics
                WHERE metric_type = 'intent_classification'
                AND created_at > NOW() - (INTERVAL '1 day' * :days)
            """))
            intent_row = intent_result.fetchone()

            intent_confidence = intent_row[0] or 0
            confirmed_correct = intent_row[1] or 0
            total_confirmed = intent_row[3] or 1
            intent_accuracy = confirmed_correct / total_confirmed if total_confirmed > 0 else 0

            # Tool selection accuracy (inferred from tool success)
            tool_result = db.execute(text(f"""
                SELECT AVG(value) FROM ai_metrics
                WHERE metric_type = 'tool_execution'
                AND created_at > NOW() - (INTERVAL '1 day' * :days)
            """))
            tool_accuracy = tool_result.scalar() or 0

            # Response quality (from feedback)
            quality_result = db.execute(text(f"""
                SELECT AVG(value) FROM ai_metrics
                WHERE metric_type = 'user_feedback'
                AND created_at > NOW() - (INTERVAL '1 day' * :days)
            """))
            response_quality = quality_result.scalar() or 0

            # Follow-up click-through rate
            followup_result = db.execute(text(f"""
                SELECT COUNT(*) FROM ai_metrics
                WHERE metric_type = 'followup_click'
                AND created_at > NOW() - (INTERVAL '1 day' * :days)
            """))
            followup_clicks = followup_result.scalar() or 0

            total_queries_result = db.execute(text(f"""
                SELECT COUNT(*) FROM ai_metrics
                WHERE metric_type = 'query_type'
                AND created_at > NOW() - (INTERVAL '1 day' * :days)
            """))
            total_queries = total_queries_result.scalar() or 1

            followup_rate = followup_clicks / total_queries if total_queries > 0 else 0

            # User corrections (wrong intent marked)
            corrections = intent_row[2] or 0

            return AIQualityMetrics(
                intent_accuracy=intent_accuracy,
                intent_confidence_avg=intent_confidence,
                tool_selection_accuracy=tool_accuracy,
                response_quality_avg=response_quality,
                followup_click_rate=followup_rate,
                user_corrections_count=corrections,
                period_start=period_start,
                period_end=period_end
            )

        except Exception as e:
            logger.error(f"Error getting AI quality metrics: {e}")
            try:
                db.rollback()
            except Exception:
                pass
            return AIQualityMetrics(
                intent_accuracy=0,
                intent_confidence_avg=0,
                tool_selection_accuracy=0,
                response_quality_avg=0,
                followup_click_rate=0,
                user_corrections_count=0,
                period_start=datetime.now(timezone.utc) - timedelta(days=days),
                period_end=datetime.now(timezone.utc)
            )

    @staticmethod
    async def get_response_time_breakdown(
        db: Session,
        days: int = 7,
        query_type: Optional[str] = None
    ) -> Dict[str, Any]:
        """Get detailed response time breakdown by query type."""
        try:
            type_filter = "AND metadata->>'query_type' = :query_type" if query_type else ""
            params = {"days": days}
            if query_type:
                params["query_type"] = query_type

            result = db.execute(text(f"""
                SELECT
                    metadata->>'query_type' as query_type,
                    AVG(value) as avg_total,
                    AVG((metadata->'breakdown'->>'analyze_ms')::float) as avg_analyze,
                    AVG((metadata->'breakdown'->>'gather_ms')::float) as avg_gather,
                    AVG((metadata->'breakdown'->>'reason_ms')::float) as avg_reason,
                    AVG((metadata->'breakdown'->>'execute_ms')::float) as avg_execute,
                    AVG((metadata->'breakdown'->>'respond_ms')::float) as avg_respond,
                    COUNT(*) as count
                FROM ai_metrics
                WHERE metric_type = 'response_time'
                AND created_at > NOW() - (INTERVAL '1 day' * :days)
                {type_filter}
                GROUP BY metadata->>'query_type'
                ORDER BY count DESC
            """), params)

            breakdown = []
            for row in result:
                breakdown.append({
                    "query_type": row[0],
                    "avg_total_ms": row[1] or 0,
                    "avg_analyze_ms": row[2] or 0,
                    "avg_gather_ms": row[3] or 0,
                    "avg_reason_ms": row[4] or 0,
                    "avg_execute_ms": row[5] or 0,
                    "avg_respond_ms": row[6] or 0,
                    "count": row[7]
                })

            return {
                "breakdown_by_query_type": breakdown,
                "period_days": days
            }

        except Exception as e:
            logger.error(f"Error getting response time breakdown: {e}")
            try:
                db.rollback()
            except Exception:
                pass
            return {"breakdown_by_query_type": [], "period_days": days}

    @staticmethod
    async def get_dashboard_summary(
        db: Session,
        days: int = 7
    ) -> Dict[str, Any]:
        """Get a comprehensive dashboard summary of all metrics."""
        try:
            performance = await AIMetricsService.get_agent_performance(db, days)
            business = await AIMetricsService.get_business_metrics(db, days)
            quality = await AIMetricsService.get_ai_quality_metrics(db, days)
            timing = await AIMetricsService.get_response_time_breakdown(db, days)
            hallucination = await AIMetricsService.get_hallucination_metrics(db, days)

            return {
                "agent_performance": performance.model_dump(),
                "business_metrics": business.model_dump(),
                "ai_quality": quality.model_dump(),
                "response_time_breakdown": timing,
                "hallucination_metrics": hallucination.model_dump(),
                "generated_at": datetime.now(timezone.utc).isoformat()
            }

        except Exception as e:
            logger.error(f"Error getting dashboard summary: {e}")
            return {
                "error": "Internal server error",
                "generated_at": datetime.now(timezone.utc).isoformat()
            }
