"""
Performance Tracking for AI Agents

Tracks and analyzes agent performance including:
- Token usage and cost optimization
- Latency metrics
- Conversion rates
- A/B test results
- Quality scoring
"""

from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import logging
import os
import uuid
from sqlalchemy import select, func, and_, text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class PerformanceTracker:
    """
    Track and analyze agent performance.

    Provides insights for optimization:
    - Token usage trends
    - Response quality metrics
    - Conversion funnel analysis
    - A/B test evaluation
    """

    # Token costs (approximate, update as needed)
    TOKEN_COSTS = {
        "claude-sonnet-4-20250514": {"input": 0.003, "output": 0.015},  # per 1K tokens
        "claude-opus-4-20250514": {"input": 0.015, "output": 0.075},
        "gpt-4-turbo": {"input": 0.01, "output": 0.03},
        "gpt-3.5-turbo": {"input": 0.0005, "output": 0.0015},
    }

    def __init__(self, db_session: Optional[AsyncSession] = None):
        """
        Initialize performance tracker.

        Args:
            db_session: Optional database session for persistence
        """
        self.db_session = db_session
        self._in_memory_executions: List[Dict] = []
        self._in_memory_outcomes: List[Dict] = []

    async def log_execution(self, data: Dict[str, Any]) -> str:
        """
        Log an agent execution.

        Args:
            data: Execution data including:
                - agent_id: Agent identifier
                - conversation_id: Conversation UUID
                - user_id: User UUID (optional)
                - stage: Conversation stage
                - prompt_tokens: Input tokens
                - completion_tokens: Output tokens
                - latency_ms: Response time in milliseconds
                - response: Response text (optional)
                - model_used: AI model used (optional)
                - metadata: Additional metadata (optional)

        Returns:
            Execution ID
        """
        execution_id = str(uuid.uuid4())
        execution = {
            "id": execution_id,
            "agent_id": data.get("agent_id"),
            "conversation_id": data.get("conversation_id"),
            "user_id": data.get("user_id"),
            "stage": data.get("stage", "unknown"),
            "prompt_tokens": data.get("prompt_tokens", 0),
            "completion_tokens": data.get("completion_tokens", 0),
            "total_tokens": data.get("prompt_tokens", 0) + data.get("completion_tokens", 0),
            "latency_ms": data.get("latency_ms", 0),
            "model_used": data.get("model_used", os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-20250514")),
            "response_text": data.get("response"),
            "metadata": data.get("metadata", {}),
            "executed_at": datetime.utcnow(),
        }

        # Store in memory (or database if session available)
        if self.db_session:
            await self._persist_execution(execution)
        else:
            self._in_memory_executions.append(execution)

        # Log summary
        logger.info(
            f"Execution logged: agent={data.get('agent_id')} "
            f"tokens={execution['total_tokens']} "
            f"latency={execution['latency_ms']}ms"
        )

        return execution_id

    async def log_outcome(self, data: Dict[str, Any]) -> str:
        """
        Log a conversation outcome.

        Args:
            data: Outcome data including:
                - conversation_id: Conversation UUID
                - agent_id: Agent UUID
                - user_id: User UUID (optional)
                - outcome_type: qualified/booked/rejected/no_response
                - total_messages: Message count
                - qualification_complete: Boolean
                - booking_made: Boolean
                - revenue_generated: Decimal (optional)
                - metrics: Additional metrics dict (optional)

        Returns:
            Outcome ID
        """
        outcome_id = str(uuid.uuid4())
        outcome = {
            "id": outcome_id,
            "conversation_id": data.get("conversation_id"),
            "agent_id": data.get("agent_id"),
            "user_id": data.get("user_id"),
            "outcome_type": data.get("outcome_type", "unknown"),
            "total_messages": data.get("total_messages", 0),
            "agent_messages": data.get("agent_messages", 0),
            "user_messages": data.get("user_messages", 0),
            "qualification_complete": data.get("qualification_complete", False),
            "booking_made": data.get("booking_made", False),
            "revenue_generated": data.get("revenue_generated"),
            "metrics": data.get("metrics", {}),
            "created_at": datetime.utcnow(),
            "completed_at": datetime.utcnow(),
        }

        if self.db_session:
            await self._persist_outcome(outcome)
        else:
            self._in_memory_outcomes.append(outcome)

        logger.info(
            f"Outcome logged: agent={data.get('agent_id')} "
            f"type={outcome['outcome_type']} "
            f"booking={outcome['booking_made']}"
        )

        return outcome_id

    async def _fetch_executions_from_db(self, agent_id: str, start_date: datetime) -> List[Dict]:
        """Fetch executions from database."""
        if not self.db_session:
            return []

        try:
            query = text("""
                SELECT conversation_id, agent_id, stage, prompt_tokens, completion_tokens,
                       total_tokens, latency_ms, model_used, created_at
                FROM agent_executions
                WHERE agent_id = :agent_id AND created_at >= :start_date
                ORDER BY created_at DESC
            """)
            result = await self.db_session.execute(query, {
                "agent_id": agent_id,
                "start_date": start_date
            })
            rows = result.fetchall()
            return [
                {
                    "conversation_id": row[0],
                    "agent_id": row[1],
                    "stage": row[2],
                    "prompt_tokens": row[3] or 0,
                    "completion_tokens": row[4] or 0,
                    "total_tokens": row[5] or 0,
                    "latency_ms": row[6] or 0,
                    "model_used": row[7],
                    "executed_at": row[8],
                }
                for row in rows
            ]
        except Exception as e:
            logger.error(f"Failed to fetch executions from database: {e}")
            return []

    async def _fetch_outcomes_from_db(self, agent_id: str, start_date: datetime) -> List[Dict]:
        """Fetch outcomes from database."""
        if not self.db_session:
            return []

        try:
            query = text("""
                SELECT conversation_id, agent_id, user_id, outcome_type,
                       total_messages, agent_messages, user_messages,
                       qualification_complete, booking_made, revenue_generated,
                       created_at, completed_at
                FROM conversation_outcomes
                WHERE agent_id = :agent_id AND created_at >= :start_date
                ORDER BY created_at DESC
            """)
            result = await self.db_session.execute(query, {
                "agent_id": agent_id,
                "start_date": start_date
            })
            rows = result.fetchall()
            return [
                {
                    "conversation_id": row[0],
                    "agent_id": row[1],
                    "user_id": row[2],
                    "outcome_type": row[3],
                    "total_messages": row[4] or 0,
                    "agent_messages": row[5] or 0,
                    "user_messages": row[6] or 0,
                    "qualification_complete": row[7],
                    "booking_made": row[8],
                    "revenue_generated": float(row[9]) if row[9] else 0,
                    "created_at": row[10],
                    "completed_at": row[11],
                }
                for row in rows
            ]
        except Exception as e:
            logger.error(f"Failed to fetch outcomes from database: {e}")
            return []

    async def get_agent_metrics(
        self,
        agent_id: str,
        days: int = 30
    ) -> Dict[str, Any]:
        """
        Get comprehensive performance metrics for an agent.

        Args:
            agent_id: Agent identifier
            days: Number of days to analyze

        Returns:
            Dictionary with performance metrics
        """
        start_date = datetime.utcnow() - timedelta(days=days)

        # Try to fetch from database first, fall back to in-memory
        if self.db_session:
            executions = await self._fetch_executions_from_db(agent_id, start_date)
            outcomes = await self._fetch_outcomes_from_db(agent_id, start_date)
        else:
            executions = []
            outcomes = []

        # Combine with in-memory data
        executions.extend([
            e for e in self._in_memory_executions
            if e.get("agent_id") == agent_id and e.get("executed_at", datetime.min) >= start_date
        ])
        outcomes.extend([
            o for o in self._in_memory_outcomes
            if o.get("agent_id") == agent_id and o.get("created_at", datetime.min) >= start_date
        ])

        if not outcomes:
            return self._empty_metrics(agent_id, days)

        # Calculate metrics
        total_convs = len(outcomes)
        qualified = sum(1 for o in outcomes if o.get("qualification_complete"))
        booked = sum(1 for o in outcomes if o.get("booking_made"))
        responded = sum(1 for o in outcomes if o.get("total_messages", 0) > 1)

        # Token metrics
        total_tokens = sum(e.get("total_tokens", 0) for e in executions)
        avg_tokens = total_tokens / len(executions) if executions else 0

        # Latency metrics
        latencies = [e.get("latency_ms", 0) for e in executions if e.get("latency_ms")]
        avg_latency = sum(latencies) / len(latencies) if latencies else 0

        # Cost estimation
        total_cost = self._calculate_cost(executions)

        # Revenue
        total_revenue = sum(
            float(o.get("revenue_generated") or 0)
            for o in outcomes
        )

        return {
            "agent_id": agent_id,
            "period_days": days,
            "total_conversations": total_convs,
            "response_rate": round(responded / total_convs * 100, 1) if total_convs > 0 else 0,
            "qualification_rate": round(qualified / total_convs * 100, 1) if total_convs > 0 else 0,
            "booking_rate": round(booked / total_convs * 100, 1) if total_convs > 0 else 0,
            "pull_through_rate": round(booked / qualified * 100, 1) if qualified > 0 else 0,
            "token_metrics": {
                "total_tokens": total_tokens,
                "avg_tokens_per_execution": int(avg_tokens),
                "estimated_cost_usd": round(total_cost, 2),
            },
            "latency_metrics": {
                "avg_latency_ms": int(avg_latency),
                "p95_latency_ms": int(sorted(latencies)[int(len(latencies) * 0.95)] if latencies else 0),
            },
            "revenue": {
                "total_generated": round(total_revenue, 2),
                "avg_per_booking": round(total_revenue / booked, 2) if booked > 0 else 0,
            },
            "funnel": {
                "conversations": total_convs,
                "responded": responded,
                "qualified": qualified,
                "booked": booked,
            },
        }

    async def get_stage_breakdown(
        self,
        agent_id: str,
        days: int = 30
    ) -> Dict[str, Any]:
        """
        Get performance breakdown by conversation stage.

        Returns metrics for each stage to identify bottlenecks.
        """
        start_date = datetime.utcnow() - timedelta(days=days)

        # Fetch from database and combine with in-memory
        if self.db_session:
            executions = await self._fetch_executions_from_db(agent_id, start_date)
        else:
            executions = []

        executions.extend([
            e for e in self._in_memory_executions
            if e.get("agent_id") == agent_id and e.get("executed_at", datetime.min) >= start_date
        ])

        # Group by stage
        by_stage: Dict[str, List[Dict]] = {}
        for e in executions:
            stage = e.get("stage", "unknown")
            if stage not in by_stage:
                by_stage[stage] = []
            by_stage[stage].append(e)

        breakdown = {}
        for stage, stage_executions in by_stage.items():
            tokens = [e.get("total_tokens", 0) for e in stage_executions]
            latencies = [e.get("latency_ms", 0) for e in stage_executions]

            breakdown[stage] = {
                "count": len(stage_executions),
                "avg_tokens": int(sum(tokens) / len(tokens)) if tokens else 0,
                "avg_latency_ms": int(sum(latencies) / len(latencies)) if latencies else 0,
                "total_cost": round(self._calculate_cost(stage_executions), 2),
            }

        return {
            "agent_id": agent_id,
            "period_days": days,
            "stages": breakdown,
        }

    async def compare_agents(
        self,
        agent_ids: List[str],
        days: int = 30
    ) -> Dict[str, Any]:
        """
        Compare performance across multiple agents.
        """
        comparison = {}
        for agent_id in agent_ids:
            comparison[agent_id] = await self.get_agent_metrics(agent_id, days)

        return {
            "period_days": days,
            "agents": comparison,
            "best_performer": max(
                comparison.items(),
                key=lambda x: x[1].get("booking_rate", 0)
            )[0] if comparison else None,
        }

    async def get_token_trends(
        self,
        agent_id: str,
        days: int = 30,
        interval: str = "daily"
    ) -> Dict[str, Any]:
        """
        Get token usage trends over time.
        """
        start_date = datetime.utcnow() - timedelta(days=days)

        # Fetch from database and combine with in-memory
        if self.db_session:
            executions = await self._fetch_executions_from_db(agent_id, start_date)
        else:
            executions = []

        executions.extend([
            e for e in self._in_memory_executions
            if e.get("agent_id") == agent_id and e.get("executed_at", datetime.min) >= start_date
        ])

        # Group by day
        by_day: Dict[str, List[Dict]] = {}
        for e in executions:
            day_key = e.get("executed_at", datetime.utcnow()).strftime("%Y-%m-%d")
            if day_key not in by_day:
                by_day[day_key] = []
            by_day[day_key].append(e)

        trends = []
        for day, day_executions in sorted(by_day.items()):
            tokens = sum(e.get("total_tokens", 0) for e in day_executions)
            trends.append({
                "date": day,
                "total_tokens": tokens,
                "execution_count": len(day_executions),
                "avg_tokens": int(tokens / len(day_executions)) if day_executions else 0,
            })

        return {
            "agent_id": agent_id,
            "period_days": days,
            "trends": trends,
        }

    def _calculate_cost(self, executions: List[Dict]) -> float:
        """Calculate estimated cost for executions"""
        total_cost = 0.0
        for e in executions:
            model = e.get("model_used", os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-20250514"))
            costs = self.TOKEN_COSTS.get(model, self.TOKEN_COSTS.get(os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-20250514"), self.TOKEN_COSTS["claude-sonnet-4-20250514"]))

            input_cost = (e.get("prompt_tokens", 0) / 1000) * costs["input"]
            output_cost = (e.get("completion_tokens", 0) / 1000) * costs["output"]
            total_cost += input_cost + output_cost

        return total_cost

    def _empty_metrics(self, agent_id: str, days: int) -> Dict[str, Any]:
        """Return empty metrics structure"""
        return {
            "agent_id": agent_id,
            "period_days": days,
            "total_conversations": 0,
            "response_rate": 0,
            "qualification_rate": 0,
            "booking_rate": 0,
            "pull_through_rate": 0,
            "token_metrics": {
                "total_tokens": 0,
                "avg_tokens_per_execution": 0,
                "estimated_cost_usd": 0,
            },
            "latency_metrics": {
                "avg_latency_ms": 0,
                "p95_latency_ms": 0,
            },
            "revenue": {
                "total_generated": 0,
                "avg_per_booking": 0,
            },
            "funnel": {
                "conversations": 0,
                "responded": 0,
                "qualified": 0,
                "booked": 0,
            },
        }

    async def _persist_execution(self, execution: Dict) -> None:
        """Persist execution to database using agent_executions table."""
        if not self.db_session:
            self._in_memory_executions.append(execution)
            return

        try:
            # Convert metadata to JSON string for storage
            import json
            metadata_json = json.dumps(execution.get("metadata", {}))

            # Insert into agent_executions table
            query = text("""
                INSERT INTO agent_executions (
                    conversation_id, agent_id, stage, prompt_tokens, completion_tokens,
                    total_tokens, latency_ms, model_used, response_text, metadata, created_at
                ) VALUES (
                    :conversation_id, :agent_id, :stage, :prompt_tokens, :completion_tokens,
                    :total_tokens, :latency_ms, :model_used, :response_text, :metadata, :created_at
                )
            """)

            await self.db_session.execute(query, {
                "conversation_id": execution.get("conversation_id"),
                "agent_id": execution.get("agent_id"),
                "stage": execution.get("stage", "unknown"),
                "prompt_tokens": execution.get("prompt_tokens", 0),
                "completion_tokens": execution.get("completion_tokens", 0),
                "total_tokens": execution.get("total_tokens", 0),
                "latency_ms": execution.get("latency_ms", 0),
                "model_used": execution.get("model_used"),
                "response_text": execution.get("response_text"),
                "metadata": metadata_json,
                "created_at": execution.get("executed_at", datetime.utcnow()),
            })
            await self.db_session.commit()

            logger.debug(f"Persisted execution {execution.get('id')} to database")

        except Exception as e:
            logger.error(f"Failed to persist execution to database: {e}")
            # Fall back to in-memory storage
            self._in_memory_executions.append(execution)

    async def _persist_outcome(self, outcome: Dict) -> None:
        """Persist outcome to database using conversation_outcomes table."""
        if not self.db_session:
            self._in_memory_outcomes.append(outcome)
            return

        try:
            import json
            metrics_json = json.dumps(outcome.get("metrics", {}))

            query = text("""
                INSERT INTO conversation_outcomes (
                    conversation_id, agent_id, user_id, outcome_type,
                    total_messages, agent_messages, user_messages,
                    qualification_complete, booking_made, revenue_generated,
                    metrics, created_at, completed_at
                ) VALUES (
                    :conversation_id, :agent_id, :user_id, :outcome_type,
                    :total_messages, :agent_messages, :user_messages,
                    :qualification_complete, :booking_made, :revenue_generated,
                    :metrics, :created_at, :completed_at
                )
            """)

            await self.db_session.execute(query, {
                "conversation_id": outcome.get("conversation_id"),
                "agent_id": outcome.get("agent_id"),
                "user_id": outcome.get("user_id"),
                "outcome_type": outcome.get("outcome_type", "unknown"),
                "total_messages": outcome.get("total_messages", 0),
                "agent_messages": outcome.get("agent_messages", 0),
                "user_messages": outcome.get("user_messages", 0),
                "qualification_complete": outcome.get("qualification_complete", False),
                "booking_made": outcome.get("booking_made", False),
                "revenue_generated": outcome.get("revenue_generated"),
                "metrics": metrics_json,
                "created_at": outcome.get("created_at", datetime.utcnow()),
                "completed_at": outcome.get("completed_at"),
            })
            await self.db_session.commit()

            logger.debug(f"Persisted outcome {outcome.get('id')} to database")

        except Exception as e:
            logger.error(f"Failed to persist outcome to database: {e}")
            # Fall back to in-memory storage
            self._in_memory_outcomes.append(outcome)


class ABTestTracker:
    """
    Track A/B test experiments for agent optimization.
    """

    def __init__(self, db_session: Optional[AsyncSession] = None):
        self.db_session = db_session
        self._tests: Dict[str, Dict] = {}

    async def create_test(
        self,
        test_name: str,
        agent_id: str,
        variant_a_config: Dict[str, Any],
        variant_b_config: Dict[str, Any],
        traffic_split: float = 0.5
    ) -> str:
        """
        Create a new A/B test.

        Args:
            test_name: Name of the test
            agent_id: Agent to test
            variant_a_config: Configuration for variant A
            variant_b_config: Configuration for variant B
            traffic_split: Percentage of traffic to variant A (0.0-1.0)

        Returns:
            Test ID
        """
        test_id = str(uuid.uuid4())
        self._tests[test_id] = {
            "id": test_id,
            "test_name": test_name,
            "agent_id": agent_id,
            "status": "active",
            "variant_a_config": variant_a_config,
            "variant_b_config": variant_b_config,
            "traffic_split": traffic_split,
            "variant_a_conversations": 0,
            "variant_b_conversations": 0,
            "variant_a_conversions": 0,
            "variant_b_conversions": 0,
            "created_at": datetime.utcnow(),
            "started_at": datetime.utcnow(),
        }

        logger.info(f"A/B test created: {test_name} ({test_id})")
        return test_id

    def get_variant(self, test_id: str) -> str:
        """
        Get which variant to use for a new conversation.

        Returns 'A' or 'B' based on traffic split.
        """
        import random

        test = self._tests.get(test_id)
        if not test or test.get("status") != "active":
            return "A"

        return "A" if random.random() < test["traffic_split"] else "B"

    async def record_result(
        self,
        test_id: str,
        variant: str,
        converted: bool
    ) -> None:
        """Record a test result"""
        test = self._tests.get(test_id)
        if not test:
            return

        if variant == "A":
            test["variant_a_conversations"] += 1
            if converted:
                test["variant_a_conversions"] += 1
        else:
            test["variant_b_conversations"] += 1
            if converted:
                test["variant_b_conversions"] += 1

    async def get_results(self, test_id: str) -> Dict[str, Any]:
        """Get test results with statistical analysis"""
        test = self._tests.get(test_id)
        if not test:
            return {}

        a_convs = test["variant_a_conversations"]
        b_convs = test["variant_b_conversations"]
        a_converted = test["variant_a_conversions"]
        b_converted = test["variant_b_conversions"]

        a_rate = a_converted / a_convs if a_convs > 0 else 0
        b_rate = b_converted / b_convs if b_convs > 0 else 0

        # Simple significance calculation (for proper stats, use scipy)
        min_sample = 100
        is_significant = a_convs >= min_sample and b_convs >= min_sample

        winner = None
        if is_significant:
            if a_rate > b_rate * 1.05:  # 5% lift threshold
                winner = "A"
            elif b_rate > a_rate * 1.05:
                winner = "B"

        return {
            "test_id": test_id,
            "test_name": test["test_name"],
            "status": test["status"],
            "variant_a": {
                "conversations": a_convs,
                "conversions": a_converted,
                "conversion_rate": round(a_rate * 100, 2),
            },
            "variant_b": {
                "conversations": b_convs,
                "conversions": b_converted,
                "conversion_rate": round(b_rate * 100, 2),
            },
            "lift_percent": round((b_rate - a_rate) / a_rate * 100, 2) if a_rate > 0 else 0,
            "is_significant": is_significant,
            "winner": winner,
            "recommendation": self._get_recommendation(winner, is_significant, a_rate, b_rate),
        }

    def _get_recommendation(
        self,
        winner: Optional[str],
        is_significant: bool,
        a_rate: float,
        b_rate: float
    ) -> str:
        """Generate recommendation based on test results"""
        if not is_significant:
            return "Continue testing - insufficient data for significance"

        if winner == "A":
            return f"Variant A wins with {round((a_rate - b_rate) / b_rate * 100, 1)}% lift. Consider rolling out."
        elif winner == "B":
            return f"Variant B wins with {round((b_rate - a_rate) / a_rate * 100, 1)}% lift. Consider rolling out."
        else:
            return "No clear winner - consider testing different variations"

    async def end_test(self, test_id: str) -> None:
        """End an A/B test"""
        test = self._tests.get(test_id)
        if test:
            test["status"] = "completed"
            test["ended_at"] = datetime.utcnow()
            logger.info(f"A/B test ended: {test['test_name']} ({test_id})")
