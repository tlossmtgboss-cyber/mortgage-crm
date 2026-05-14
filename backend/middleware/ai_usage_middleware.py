"""
AI Usage Tracking Middleware

Provides wrapped AI clients (Anthropic, OpenAI) that automatically track
token usage and costs per user for the Usage Intelligence system.

Usage:
    from middleware.ai_usage_middleware import AIUsageTracker

    tracker = AIUsageTracker(db_session)
    response = tracker.create_message(
        user_id=123,
        feature="chat",
        model="claude-sonnet-4-20250514",
        max_tokens=4096,
        system="You are helpful.",
        messages=[{"role": "user", "content": "Hello"}]
    )
"""

import os
import uuid
import time
import logging
from datetime import datetime, date, timezone
from decimal import Decimal
from typing import Dict, Any, Optional, List, Union
from contextlib import contextmanager

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


# =============================================================================
# AI MODEL PRICING (cached from database or defaults)
# =============================================================================

# Default pricing per 1M tokens (updated Jan 2025)
DEFAULT_PRICING = {
    # Anthropic
    "claude-opus-4-5-20251101": {"input": Decimal("75.00"), "output": Decimal("150.00")},
    "claude-sonnet-4-6": {"input": Decimal("3.00"), "output": Decimal("15.00")},
    "claude-sonnet-4-20250514": {"input": Decimal("3.00"), "output": Decimal("15.00")},
    "claude-haiku-4-5-20251001": {"input": Decimal("0.80"), "output": Decimal("4.00")},
    "claude-3-5-sonnet-20241022": {"input": Decimal("3.00"), "output": Decimal("15.00")},
    "claude-3-5-haiku-20241022": {"input": Decimal("0.80"), "output": Decimal("4.00")},
    # OpenAI
    "gpt-4o": {"input": Decimal("2.50"), "output": Decimal("10.00")},
    "gpt-4o-mini": {"input": Decimal("0.15"), "output": Decimal("0.60")},
    "gpt-4-turbo": {"input": Decimal("10.00"), "output": Decimal("30.00")},
    "o1": {"input": Decimal("15.00"), "output": Decimal("60.00")},
    "o1-mini": {"input": Decimal("1.10"), "output": Decimal("4.40")},
}


def get_model_pricing(db: Session, model_id: str) -> Dict[str, Decimal]:
    """
    Get pricing for a model from database or defaults.
    Returns dict with 'input' and 'output' prices per 1M tokens.
    """
    try:
        result = db.execute(text("""
            SELECT input_price_per_1m, output_price_per_1m
            FROM ai_model_pricing
            WHERE model_id = :model_id
            AND is_active = true
            ORDER BY effective_date DESC
            LIMIT 1
        """), {"model_id": model_id}).fetchone()

        if result:
            return {
                "input": Decimal(str(result[0])),
                "output": Decimal(str(result[1]))
            }
    except Exception as e:
        logger.warning(f"Failed to fetch pricing from database: {e}")

    # Fall back to defaults
    return DEFAULT_PRICING.get(model_id, {"input": Decimal("5.00"), "output": Decimal("15.00")})


def calculate_cost(
    input_tokens: int,
    output_tokens: int,
    pricing: Dict[str, Decimal]
) -> Dict[str, Decimal]:
    """
    Calculate cost in dollars based on token counts and pricing.
    Pricing is per 1M tokens.
    """
    input_cost = (Decimal(input_tokens) / Decimal("1000000")) * pricing["input"]
    output_cost = (Decimal(output_tokens) / Decimal("1000000")) * pricing["output"]

    return {
        "input_cost": input_cost,
        "output_cost": output_cost,
        "total_cost": input_cost + output_cost
    }


# =============================================================================
# AI USAGE TRACKER
# =============================================================================

class AIUsageTracker:
    """
    Wrapper for AI API calls that automatically tracks token usage and costs.
    Logs every call to ai_token_usage_log for precise cost tracking.
    """

    def __init__(
        self,
        db: Session,
        organization_id: int = 1,
        anthropic_api_key: Optional[str] = None,
        openai_api_key: Optional[str] = None
    ):
        self.db = db
        self.organization_id = organization_id
        self.anthropic_api_key = anthropic_api_key or os.getenv("ANTHROPIC_API_KEY")
        self.openai_api_key = openai_api_key or os.getenv("OPENAI_API_KEY")

        # Lazy-load clients
        self._anthropic_client = None
        self._openai_client = None

        # Cache pricing
        self._pricing_cache = {}

    @property
    def anthropic_client(self):
        """Lazy-load Anthropic client."""
        if self._anthropic_client is None and self.anthropic_api_key:
            import anthropic
            self._anthropic_client = anthropic.Anthropic(api_key=self.anthropic_api_key)
        return self._anthropic_client

    @property
    def openai_client(self):
        """Lazy-load OpenAI client."""
        if self._openai_client is None and self.openai_api_key:
            import openai
            self._openai_client = openai.OpenAI(api_key=self.openai_api_key)
        return self._openai_client

    def _get_pricing(self, model_id: str) -> Dict[str, Decimal]:
        """Get pricing with caching."""
        if model_id not in self._pricing_cache:
            self._pricing_cache[model_id] = get_model_pricing(self.db, model_id)
        return self._pricing_cache[model_id]

    def _log_usage(
        self,
        user_id: int,
        request_id: str,
        provider: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        feature: Optional[str] = None,
        session_id: Optional[str] = None,
        latency_ms: Optional[int] = None,
        metadata: Optional[Dict] = None
    ):
        """Log token usage to the database."""
        try:
            pricing = self._get_pricing(model)
            costs = calculate_cost(input_tokens, output_tokens, pricing)

            self.db.execute(text("""
                INSERT INTO ai_token_usage_log (
                    id, organization_id, user_id, request_id, timestamp,
                    provider, model, input_tokens, output_tokens, total_tokens,
                    input_cost, output_cost, total_cost,
                    feature, session_id, metadata_json, latency_ms
                ) VALUES (
                    :id, :organization_id, :user_id, :request_id, :timestamp,
                    :provider, :model, :input_tokens, :output_tokens, :total_tokens,
                    :input_cost, :output_cost, :total_cost,
                    :feature, :session_id, :metadata_json, :latency_ms
                )
            """), {
                "id": str(uuid.uuid4()),
                "organization_id": self.organization_id,
                "user_id": user_id,
                "request_id": request_id,
                "timestamp": datetime.now(timezone.utc),
                "provider": provider,
                "model": model,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "total_tokens": input_tokens + output_tokens,
                "input_cost": str(costs["input_cost"]),
                "output_cost": str(costs["output_cost"]),
                "total_cost": str(costs["total_cost"]),
                "feature": feature,
                "session_id": session_id,
                "metadata_json": metadata,
                "latency_ms": latency_ms
            })
            self.db.commit()

            logger.info(
                f"AI Usage logged: user={user_id}, model={model}, "
                f"tokens={input_tokens}/{output_tokens}, cost=${costs['total_cost']:.6f}"
            )

            # Also record to ai_cost_records for the cost tracking dashboard
            try:
                self.db.execute(text("""
                    INSERT INTO ai_cost_records (
                        id, organization_id, user_id, agent_type, model,
                        input_tokens, output_tokens, cost_usd, duration_ms,
                        created_at
                    ) VALUES (
                        gen_random_uuid(), :org_id, :user_id, :agent_type, :model,
                        :input_tokens, :output_tokens, :cost_usd, :duration_ms,
                        NOW()
                    )
                """), {
                    "org_id": self.organization_id,
                    "user_id": user_id,
                    "agent_type": feature or "unknown",
                    "model": model,
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "cost_usd": str(costs["total_cost"]),
                    "duration_ms": latency_ms,
                })
                self.db.commit()
            except Exception as cost_err:
                logger.debug(f"ai_cost_records insert skipped: {cost_err}")
                try:
                    self.db.rollback()
                except Exception:
                    pass

        except Exception as e:
            logger.error(f"Failed to log AI usage: {e}")
            # Don't fail the main request if logging fails
            try:
                self.db.rollback()
            except Exception as e2:
                logger.exception(f"Failed to rollback DB session after AI usage logging failure: {e2}")

    def create_message(
        self,
        user_id: int,
        model: str,
        max_tokens: int,
        messages: List[Dict[str, Any]],
        system: Optional[str] = None,
        feature: Optional[str] = None,
        session_id: Optional[str] = None,
        temperature: float = 0,
        **kwargs
    ):
        """
        Create a message using Anthropic API with automatic usage tracking.
        Returns the raw Anthropic response.
        """
        if not self.anthropic_client:
            raise ValueError("Anthropic API key not configured")

        request_id = str(uuid.uuid4())
        start_time = time.time()

        try:
            # Build request params
            params = {
                "model": model,
                "max_tokens": max_tokens,
                "messages": messages,
                "temperature": temperature,
                **kwargs
            }
            if system:
                params["system"] = system

            # Make the API call
            response = self.anthropic_client.messages.create(**params)

            # Calculate latency
            latency_ms = int((time.time() - start_time) * 1000)

            # Extract usage
            input_tokens = response.usage.input_tokens
            output_tokens = response.usage.output_tokens

            # Log usage
            self._log_usage(
                user_id=user_id,
                request_id=request_id,
                provider="anthropic",
                model=model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                feature=feature,
                session_id=session_id,
                latency_ms=latency_ms,
                metadata={
                    "max_tokens": max_tokens,
                    "temperature": temperature,
                    "stop_reason": response.stop_reason
                }
            )

            return response

        except Exception as e:
            # Log failed attempt with 0 tokens (for tracking failure rates)
            latency_ms = int((time.time() - start_time) * 1000)
            logger.error(f"Anthropic API call failed: {e}")

            self._log_usage(
                user_id=user_id,
                request_id=request_id,
                provider="anthropic",
                model=model,
                input_tokens=0,
                output_tokens=0,
                feature=feature,
                session_id=session_id,
                latency_ms=latency_ms,
                metadata={"error": "Internal server error", "status": "failed"}
            )

            raise

    def create_chat_completion(
        self,
        user_id: int,
        model: str,
        messages: List[Dict[str, Any]],
        feature: Optional[str] = None,
        session_id: Optional[str] = None,
        temperature: float = 0,
        max_tokens: Optional[int] = None,
        **kwargs
    ):
        """
        Create a chat completion using OpenAI API with automatic usage tracking.
        Returns the raw OpenAI response.
        """
        if not self.openai_client:
            raise ValueError("OpenAI API key not configured")

        request_id = str(uuid.uuid4())
        start_time = time.time()

        try:
            # Build request params
            params = {
                "model": model,
                "messages": messages,
                "temperature": temperature,
                **kwargs
            }
            if max_tokens:
                params["max_tokens"] = max_tokens

            # Make the API call
            response = self.openai_client.chat.completions.create(**params)

            # Calculate latency
            latency_ms = int((time.time() - start_time) * 1000)

            # Extract usage
            input_tokens = response.usage.prompt_tokens
            output_tokens = response.usage.completion_tokens

            # Log usage
            self._log_usage(
                user_id=user_id,
                request_id=request_id,
                provider="openai",
                model=model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                feature=feature,
                session_id=session_id,
                latency_ms=latency_ms,
                metadata={
                    "max_tokens": max_tokens,
                    "temperature": temperature,
                    "finish_reason": response.choices[0].finish_reason if response.choices else None
                }
            )

            return response

        except Exception as e:
            # Log failed attempt
            latency_ms = int((time.time() - start_time) * 1000)
            logger.error(f"OpenAI API call failed: {e}")

            self._log_usage(
                user_id=user_id,
                request_id=request_id,
                provider="openai",
                model=model,
                input_tokens=0,
                output_tokens=0,
                feature=feature,
                session_id=session_id,
                latency_ms=latency_ms,
                metadata={"error": "Internal server error", "status": "failed"}
            )

            raise


# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

def log_ai_usage(
    db: Session,
    user_id: int,
    provider: str,
    model: str,
    input_tokens: int,
    output_tokens: int,
    organization_id: int = 1,
    feature: Optional[str] = None,
    session_id: Optional[str] = None,
    latency_ms: Optional[int] = None,
    metadata: Optional[Dict] = None
) -> str:
    """
    Standalone function to log AI usage.
    Use this when you can't use AIUsageTracker but need to log usage.
    Returns the request_id.
    """
    request_id = str(uuid.uuid4())
    pricing = get_model_pricing(db, model)
    costs = calculate_cost(input_tokens, output_tokens, pricing)

    try:
        db.execute(text("""
            INSERT INTO ai_token_usage_log (
                id, organization_id, user_id, request_id, timestamp,
                provider, model, input_tokens, output_tokens, total_tokens,
                input_cost, output_cost, total_cost,
                feature, session_id, metadata_json, latency_ms
            ) VALUES (
                :id, :organization_id, :user_id, :request_id, :timestamp,
                :provider, :model, :input_tokens, :output_tokens, :total_tokens,
                :input_cost, :output_cost, :total_cost,
                :feature, :session_id, :metadata_json, :latency_ms
            )
        """), {
            "id": str(uuid.uuid4()),
            "organization_id": organization_id,
            "user_id": user_id,
            "request_id": request_id,
            "timestamp": datetime.now(timezone.utc),
            "provider": provider,
            "model": model,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": input_tokens + output_tokens,
            "input_cost": str(costs["input_cost"]),
            "output_cost": str(costs["output_cost"]),
            "total_cost": str(costs["total_cost"]),
            "feature": feature,
            "session_id": session_id,
            "metadata_json": metadata,
            "latency_ms": latency_ms
        })
        db.commit()

        logger.info(
            f"AI Usage logged: user={user_id}, model={model}, "
            f"tokens={input_tokens}/{output_tokens}, cost=${costs['total_cost']:.6f}"
        )

        # Also record to ai_cost_records for the cost tracking dashboard
        try:
            db.execute(text("""
                INSERT INTO ai_cost_records (
                    id, organization_id, user_id, agent_type, model,
                    input_tokens, output_tokens, cost_usd, duration_ms,
                    created_at
                ) VALUES (
                    gen_random_uuid(), :org_id, :user_id, :agent_type, :model,
                    :input_tokens, :output_tokens, :cost_usd, :duration_ms,
                    NOW()
                )
            """), {
                "org_id": organization_id,
                "user_id": user_id,
                "agent_type": feature or "unknown",
                "model": model,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "cost_usd": str(costs["total_cost"]),
                "duration_ms": latency_ms,
            })
            db.commit()
        except Exception as cost_err:
            logger.debug(f"ai_cost_records insert skipped: {cost_err}")
            try:
                db.rollback()
            except Exception:
                pass

        return request_id

    except Exception as e:
        logger.error(f"Failed to log AI usage: {e}")
        try:
            db.rollback()
        except Exception as e2:
            logger.exception(f"Failed to rollback DB session after AI usage logging failure: {e2}")
        return request_id


def get_user_daily_cost(db: Session, user_id: int, date_val: date = None) -> Dict[str, Any]:
    """Get total AI cost for a user on a specific date."""
    if date_val is None:
        date_val = date.today()

    result = db.execute(text("""
        SELECT
            COALESCE(SUM(input_tokens), 0) as input_tokens,
            COALESCE(SUM(output_tokens), 0) as output_tokens,
            COALESCE(SUM(total_cost), 0) as total_cost,
            COUNT(*) as request_count
        FROM ai_token_usage_log
        WHERE user_id = :user_id
        AND DATE(timestamp) = :date_val
    """), {"user_id": user_id, "date_val": date_val}).fetchone()

    return {
        "user_id": user_id,
        "date": str(date_val),
        "input_tokens": int(result[0]),
        "output_tokens": int(result[1]),
        "total_cost": float(result[2]),
        "request_count": int(result[3])
    }


def get_user_cost_summary(db: Session, user_id: int, days: int = 30) -> Dict[str, Any]:
    """Get cost summary for a user over the past N days."""
    result = db.execute(text("""
        SELECT
            DATE(timestamp) as usage_date,
            COALESCE(SUM(input_tokens), 0) as input_tokens,
            COALESCE(SUM(output_tokens), 0) as output_tokens,
            COALESCE(SUM(total_cost), 0) as total_cost,
            COUNT(*) as request_count
        FROM ai_token_usage_log
        WHERE user_id = :user_id
        AND timestamp >= CURRENT_DATE - :days
        GROUP BY DATE(timestamp)
        ORDER BY usage_date DESC
    """), {"user_id": user_id, "days": days}).fetchall()

    daily_costs = [
        {
            "date": str(row[0]),
            "input_tokens": int(row[1]),
            "output_tokens": int(row[2]),
            "total_cost": float(row[3]),
            "request_count": int(row[4])
        }
        for row in result
    ]

    total_cost = sum(d["total_cost"] for d in daily_costs)
    total_tokens = sum(d["input_tokens"] + d["output_tokens"] for d in daily_costs)

    return {
        "user_id": user_id,
        "days": days,
        "total_cost": total_cost,
        "total_tokens": total_tokens,
        "avg_daily_cost": total_cost / days if days > 0 else 0,
        "daily_breakdown": daily_costs
    }
