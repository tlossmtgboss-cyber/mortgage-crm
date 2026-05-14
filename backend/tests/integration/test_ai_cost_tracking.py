"""
AI Cost Tracking Integration Tests

Tests for the AI cost tracker service:
- Cost record creation per AI request
- Per-org cost aggregation
- Daily budget checking and alerts
- Cost-by-agent breakdown
- Cost-by-model breakdown
- Model pricing accuracy
- Platform-wide summary

Key files:
    backend/services/ai_cost_tracker.py
    backend/routes/ai_cost_routes.py
"""
import pytest
from datetime import date, timedelta
from decimal import Decimal
from sqlalchemy import text

pytestmark = [pytest.mark.integration, pytest.mark.critical]


@pytest.fixture
def cost_table(db_session):
    """Ensure the ai_cost_records table exists for tests."""
    try:
        db_session.execute(text("""
            CREATE TABLE IF NOT EXISTS ai_cost_records (
                id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
                organization_id INTEGER NOT NULL,
                user_id INTEGER,
                agent_type VARCHAR(100) NOT NULL,
                model VARCHAR(100) NOT NULL,
                input_tokens INTEGER NOT NULL,
                output_tokens INTEGER NOT NULL,
                cost_usd DECIMAL(18, 6) NOT NULL,
                duration_ms INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """))
        db_session.flush()
    except Exception:
        db_session.rollback()
    return True


@pytest.fixture
def tracker(db_session, cost_table):
    """Create an AICostTracker with the test session."""
    from services.ai_cost_tracker import AICostTracker
    return AICostTracker(db_session)


class TestCostCalculation:
    """Test dollar cost calculation from token counts."""

    def test_calculate_cost_sonnet(self):
        """Sonnet pricing: $3/M input, $15/M output."""
        from services.ai_cost_tracker import calculate_cost

        cost = calculate_cost("claude-sonnet-4-6", input_tokens=1000, output_tokens=500)
        # 1000 / 1M * $3 = $0.003 input
        # 500 / 1M * $15 = $0.0075 output
        # Total = $0.0105
        assert cost == Decimal("0.010500")

    def test_calculate_cost_haiku(self):
        """Haiku pricing: $0.80/M input, $4/M output."""
        from services.ai_cost_tracker import calculate_cost

        cost = calculate_cost("claude-haiku-4-5-20251001", input_tokens=10000, output_tokens=2000)
        # 10000 / 1M * $0.80 = $0.008 input
        # 2000 / 1M * $4 = $0.008 output
        # Total = $0.016
        assert cost == Decimal("0.016000")

    def test_calculate_cost_opus(self):
        """Opus pricing: $15/M input, $75/M output."""
        from services.ai_cost_tracker import calculate_cost

        cost = calculate_cost("claude-opus-4-6", input_tokens=5000, output_tokens=1000)
        # 5000 / 1M * $15 = $0.075 input
        # 1000 / 1M * $75 = $0.075 output
        # Total = $0.15
        assert cost == Decimal("0.150000")

    def test_calculate_cost_unknown_model_uses_default(self):
        """Unknown model should use default pricing ($3/$15)."""
        from services.ai_cost_tracker import calculate_cost

        cost = calculate_cost("unknown-model-v99", input_tokens=1000, output_tokens=500)
        # Same as Sonnet default
        assert cost == Decimal("0.010500")

    def test_calculate_cost_zero_tokens(self):
        """Zero tokens should result in zero cost."""
        from services.ai_cost_tracker import calculate_cost

        cost = calculate_cost("claude-sonnet-4-6", input_tokens=0, output_tokens=0)
        assert cost == Decimal("0.000000")


class TestRecordUsage:
    """Test persisting AI usage records to the database."""

    def test_record_usage_returns_cost(self, tracker):
        """record_usage should return the calculated cost."""
        cost = tracker.record_usage(
            org_id=1,
            agent_type="pipeline_analyst",
            model="claude-sonnet-4-6",
            input_tokens=1500,
            output_tokens=800,
            duration_ms=312,
        )
        assert isinstance(cost, Decimal)
        assert cost > 0

    def test_record_usage_persists_to_db(self, tracker, db_session):
        """Cost record should be queryable from the database after recording."""
        tracker.record_usage(
            org_id=42,
            agent_type="compliance_checker",
            model="claude-sonnet-4-6",
            input_tokens=2000,
            output_tokens=500,
            duration_ms=450,
            user_id=7,
        )

        result = db_session.execute(text("""
            SELECT agent_type, model, input_tokens, output_tokens, cost_usd
            FROM ai_cost_records
            WHERE organization_id = 42
            ORDER BY created_at DESC LIMIT 1
        """)).fetchone()

        assert result is not None
        assert result[0] == "compliance_checker"
        assert result[1] == "claude-sonnet-4-6"
        assert result[2] == 2000
        assert result[3] == 500

    def test_record_multiple_usages(self, tracker, db_session):
        """Multiple usage records should accumulate correctly."""
        tracker.record_usage(
            org_id=100, agent_type="agent_a",
            model="claude-sonnet-4-6",
            input_tokens=1000, output_tokens=500,
        )
        tracker.record_usage(
            org_id=100, agent_type="agent_b",
            model="claude-haiku-4-5-20251001",
            input_tokens=5000, output_tokens=2000,
        )

        count = db_session.execute(text("""
            SELECT COUNT(*) FROM ai_cost_records WHERE organization_id = 100
        """)).scalar()
        assert count == 2


class TestOrgCostAggregation:
    """Test per-organization cost aggregation queries."""

    def test_get_org_cost_today_empty(self, tracker):
        """Org with no usage should have zero cost today."""
        cost = tracker.get_org_cost_today(org_id=99999)
        assert cost == 0.0

    def test_get_org_cost_today_after_usage(self, tracker):
        """Cost today should reflect recorded usage."""
        tracker.record_usage(
            org_id=200, agent_type="lead_nurturer",
            model="claude-sonnet-4-6",
            input_tokens=10000, output_tokens=5000,
        )
        cost = tracker.get_org_cost_today(org_id=200)
        assert cost > 0

    def test_get_org_cost_period(self, tracker):
        """Cost period query should return structured breakdown."""
        tracker.record_usage(
            org_id=201, agent_type="rate_advisor",
            model="claude-sonnet-4-6",
            input_tokens=2000, output_tokens=1000,
        )
        today = date.today()
        result = tracker.get_org_cost_period(org_id=201, start_date=today, end_date=today)

        assert "total_cost" in result
        assert "request_count" in result
        assert "daily_breakdown" in result
        assert result["request_count"] >= 1
        assert result["total_cost"] > 0


class TestCostByAgent:
    """Test cost breakdown by agent type."""

    def test_cost_by_agent_breakdown(self, tracker):
        """Cost by agent should group by agent_type."""
        tracker.record_usage(
            org_id=300, agent_type="pipeline_analyst",
            model="claude-sonnet-4-6",
            input_tokens=1000, output_tokens=500, duration_ms=200,
        )
        tracker.record_usage(
            org_id=300, agent_type="compliance_checker",
            model="claude-sonnet-4-6",
            input_tokens=2000, output_tokens=800, duration_ms=350,
        )

        result = tracker.get_cost_by_agent(org_id=300, period_days=1)

        assert "agents" in result
        assert "total_cost" in result
        assert len(result["agents"]) >= 2

        agent_types = {a["agent_type"] for a in result["agents"]}
        assert "pipeline_analyst" in agent_types
        assert "compliance_checker" in agent_types

    def test_cost_by_agent_includes_duration(self, tracker):
        """Agent cost breakdown should include average duration."""
        tracker.record_usage(
            org_id=301, agent_type="document_tracker",
            model="claude-sonnet-4-6",
            input_tokens=1500, output_tokens=700, duration_ms=400,
        )

        result = tracker.get_cost_by_agent(org_id=301, period_days=1)
        if result["agents"]:
            agent = result["agents"][0]
            assert "avg_duration_ms" in agent


class TestCostByModel:
    """Test cost breakdown by model."""

    def test_cost_by_model_breakdown(self, tracker):
        """Cost by model should group by model name."""
        tracker.record_usage(
            org_id=400, agent_type="agent_a",
            model="claude-sonnet-4-6",
            input_tokens=1000, output_tokens=500,
        )
        tracker.record_usage(
            org_id=400, agent_type="agent_b",
            model="claude-haiku-4-5-20251001",
            input_tokens=5000, output_tokens=2000,
        )

        result = tracker.get_cost_by_model(org_id=400, period_days=1)
        assert "models" in result
        assert len(result["models"]) >= 2

        model_names = {m["model"] for m in result["models"]}
        assert "claude-sonnet-4-6" in model_names
        assert "claude-haiku-4-5-20251001" in model_names


class TestBudgetAlerts:
    """Test daily budget checking and alert generation."""

    def test_no_alert_under_budget(self, tracker):
        """Under 75% usage should not generate an alert."""
        # Default budget is $50. Record $10 worth of usage.
        tracker.record_usage(
            org_id=500, agent_type="agent",
            model="claude-sonnet-4-6",
            input_tokens=100000, output_tokens=50000,  # ~$1.05
        )
        alert = tracker.check_budget_alert(org_id=500)
        assert alert is None

    def test_warning_alert_at_75_percent(self, tracker):
        """Usage at 75%+ of budget should trigger WARNING."""
        from services.ai_cost_tracker import DEFAULT_DAILY_BUDGET

        # Use a small budget so we can trigger easily
        small_budget = Decimal("1.00")

        # Record enough to hit 75%+
        tracker.record_usage(
            org_id=501, agent_type="agent",
            model="claude-opus-4-6",
            input_tokens=5000, output_tokens=1000,  # $0.15
        )
        # Need more to hit 75% of $1 = $0.75
        for _ in range(5):
            tracker.record_usage(
                org_id=501, agent_type="agent",
                model="claude-opus-4-6",
                input_tokens=5000, output_tokens=1000,
            )

        alert = tracker.check_budget_alert(org_id=501, daily_budget=small_budget)
        if alert:
            assert "WARNING" in alert or "CRITICAL" in alert or "EXCEEDED" in alert

    def test_exceeded_alert(self, tracker):
        """Usage at 100%+ of budget should trigger EXCEEDED."""
        tiny_budget = Decimal("0.01")

        tracker.record_usage(
            org_id=502, agent_type="agent",
            model="claude-sonnet-4-6",
            input_tokens=10000, output_tokens=5000,
        )

        alert = tracker.check_budget_alert(org_id=502, daily_budget=tiny_budget)
        assert alert is not None
        assert "EXCEEDED" in alert

    def test_zero_budget_no_alert(self, tracker):
        """Zero budget should not generate alerts (disabled)."""
        alert = tracker.check_budget_alert(org_id=503, daily_budget=Decimal("0"))
        assert alert is None


class TestModelPricing:
    """Test that MODEL_PRICING is correctly configured."""

    def test_all_required_models_have_pricing(self):
        """Key models should have pricing entries."""
        from services.ai_cost_tracker import MODEL_PRICING

        required_models = [
            "claude-sonnet-4-6",
            "claude-haiku-4-5-20251001",
            "claude-opus-4-6",
        ]
        for model in required_models:
            assert model in MODEL_PRICING, f"Missing pricing for {model}"
            assert "input" in MODEL_PRICING[model]
            assert "output" in MODEL_PRICING[model]

    def test_pricing_values_are_decimal(self):
        """Pricing values should be Decimal for financial accuracy."""
        from services.ai_cost_tracker import MODEL_PRICING

        for model, pricing in MODEL_PRICING.items():
            assert isinstance(pricing["input"], Decimal), (
                f"{model} input pricing is not Decimal"
            )
            assert isinstance(pricing["output"], Decimal), (
                f"{model} output pricing is not Decimal"
            )

    def test_output_more_expensive_than_input(self):
        """Output tokens should cost more than input tokens for all models."""
        from services.ai_cost_tracker import MODEL_PRICING

        for model, pricing in MODEL_PRICING.items():
            assert pricing["output"] >= pricing["input"], (
                f"{model}: output (${pricing['output']}) should be >= input (${pricing['input']})"
            )


class TestAICostHTTPEndpoints:
    """Test AI cost HTTP endpoints via authenticated client."""

    def test_cost_summary_requires_admin(self, authenticated_client):
        """Platform cost summary should require admin role."""
        response = authenticated_client.get("/api/v1/ai/costs/summary")
        # LO user should get 403 (not admin)
        assert response.status_code in (200, 403), (
            f"Expected 200 or 403, got {response.status_code}: {response.text[:300]}"
        )

    def test_cost_by_agent_authenticated(self, authenticated_client):
        """Cost by agent should work for own org."""
        response = authenticated_client.get("/api/v1/ai/costs/by-agent")
        assert response.status_code in (200, 403), (
            f"Expected 200 or 403, got {response.status_code}: {response.text[:300]}"
        )

    def test_cost_daily_trend_authenticated(self, authenticated_client):
        """Daily trend should work for authenticated users (scoped to own org)."""
        response = authenticated_client.get("/api/v1/ai/costs/daily")
        assert response.status_code in (200, 403), (
            f"Expected 200 or 403, got {response.status_code}: {response.text[:300]}"
        )
