"""
AI Insights Service for Profitability Intelligence.
Uses Claude to analyze profitability data and provide intelligent insights,
natural language queries, and recommendations.

Caching Strategy:
- Natural language queries: 1 hour TTL (data changes frequently)
- Recommendations: 6 hours TTL (strategic, changes less often)
- Hiring analysis: 24 hours TTL (based on monthly data)
- Executive digest: 24 hours TTL (weekly report)
- Anomaly detection: 1 hour TTL (needs fresh data)
- Scenario comparison: 6 hours TTL (planning scenarios)

Estimated savings: $10k-15k/month at scale
"""

import os
import json
from datetime import date, datetime, timezone
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
import anthropic

from services.profitability_service import ProfitabilityService
from services.llm_cache_service import llm_cache, LLMCacheService
from models.profitability import (
    ProfitabilityInsight, EmployeeCost, ProfitabilityRole,
    RevenueRecord, Expense
)


class AIInsightsService:
    """AI-powered insights and analysis for profitability data."""

    def __init__(self, db: Session, organization_id: int):
        self.db = db
        self.organization_id = organization_id
        self.profitability_service = ProfitabilityService(db, organization_id)
        self.client = anthropic.Anthropic(
            api_key=os.getenv("ANTHROPIC_API_KEY")
        )

    @llm_cache.cached(ttl=LLMCacheService.TTL_MEDIUM, prefix="insights:query")
    def query_natural_language(self, question: str, month: Optional[date] = None) -> Dict[str, Any]:
        """
        Answer natural language questions about profitability.
        Cached for 1 hour (data changes frequently).

        Examples:
        - "Who are my top 3 loan officers by ROI?"
        - "Should we hire another processor?"
        - "What's causing our cost per loan to increase?"
        """
        if not month:
            month = date.today().replace(day=1)

        # Gather comprehensive context
        context = self._build_context(month)

        system_prompt = """You are an AI financial analyst for a mortgage company.
You have access to detailed profitability data including:
- Employee costs and performance (ROI, loans processed, revenue generated)
- Role-level profitability analysis
- Cost trends and expense breakdowns
- Revenue metrics and profit margins

Provide clear, actionable insights based on the data. Include specific numbers and percentages.
When making recommendations, explain the reasoning and expected impact.
Format currency values as $X,XXX. Format percentages as X.X%.
Be concise but thorough. Use bullet points for clarity."""

        user_prompt = f"""Based on the following profitability data for {month.strftime('%B %Y')}, please answer this question:

{question}

PROFITABILITY DATA:
{json.dumps(context, indent=2, default=str)}

Provide a clear, data-driven answer with specific metrics and actionable recommendations where appropriate."""

        response = self.client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1500,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}]
        )

        return {
            "question": question,
            "answer": response.content[0].text,
            "data_context": {
                "month": month.strftime("%Y-%m"),
                "total_employees": context["summary"]["total_employees"],
                "total_revenue": context["summary"]["total_revenue"],
                "total_expenses": context["summary"]["total_expenses"]
            },
            "generated_at": datetime.now(timezone.utc).isoformat()
        }

    @llm_cache.cached(ttl=LLMCacheService.TTL_LONG, prefix="insights:recommendations")
    def generate_smart_recommendations(self, month: Optional[date] = None) -> List[Dict[str, Any]]:
        """Generate AI-powered recommendations based on profitability data.
        Cached for 6 hours (strategic insights, changes less often)."""
        if not month:
            month = date.today().replace(day=1)

        context = self._build_context(month)

        system_prompt = """You are an AI business analyst providing strategic recommendations for a mortgage company.
Generate 3-5 specific, actionable recommendations based on the profitability data.
Each recommendation should include:
1. A clear title (5-8 words)
2. The specific action to take
3. Expected financial impact with numbers
4. Priority level (high/medium/low)
5. Brief rationale

Focus on:
- Cost reduction opportunities
- Revenue growth potential
- Staffing optimization
- Process improvements
- Risk mitigation

Return your response as a JSON array with objects containing: title, action, impact, priority, rationale"""

        user_prompt = f"""Analyze this profitability data for {month.strftime('%B %Y')} and generate strategic recommendations:

{json.dumps(context, indent=2, default=str)}

Return a JSON array of recommendation objects."""

        response = self.client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=2000,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}]
        )

        # Parse JSON from response
        try:
            response_text = response.content[0].text
            # Extract JSON if wrapped in markdown
            if "```json" in response_text:
                response_text = response_text.split("```json")[1].split("```")[0]
            elif "```" in response_text:
                response_text = response_text.split("```")[1].split("```")[0]

            recommendations = json.loads(response_text)
        except (json.JSONDecodeError, IndexError):
            recommendations = [{
                "title": "Analysis Generated",
                "action": response.content[0].text,
                "impact": "See details above",
                "priority": "medium",
                "rationale": "AI-generated analysis"
            }]

        return recommendations

    @llm_cache.cached(ttl=LLMCacheService.TTL_DAILY, prefix="insights:hiring")
    def analyze_hiring_decision(
        self,
        role_name: str,
        salary: float,
        month: Optional[date] = None
    ) -> Dict[str, Any]:
        """Analyze whether to hire for a specific role.
        Cached for 24 hours (based on monthly data)."""
        if not month:
            month = date.today().replace(day=1)

        context = self._build_context(month)

        # Find role data
        role_data = next(
            (r for r in context["role_profitability"] if r["role_name"].lower() == role_name.lower()),
            None
        )

        system_prompt = """You are an AI financial advisor analyzing a hiring decision for a mortgage company.
Provide a comprehensive analysis including:
1. Cost analysis (fully loaded cost including benefits, taxes, etc.)
2. Expected revenue contribution based on existing role performance
3. Break-even timeline
4. ROI projection
5. Clear recommendation with confidence level

Use specific numbers from the data. Be realistic about ramp-up time for new hires.
Typical mortgage industry metrics:
- Benefits add 25-35% to base salary
- New LOs take 3-6 months to ramp up
- New processors take 1-2 months to ramp up"""

        user_prompt = f"""Should we hire a new {role_name} at ${salary:,.0f}/year?

Current {role_name} Performance:
{json.dumps(role_data, indent=2, default=str) if role_data else "No existing data for this role"}

Overall Company Metrics for {month.strftime('%B %Y')}:
{json.dumps(context["summary"], indent=2, default=str)}

Provide a detailed hiring analysis with ROI projections."""

        response = self.client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1500,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}]
        )

        return {
            "role": role_name,
            "proposed_salary": salary,
            "analysis": response.content[0].text,
            "current_role_metrics": role_data,
            "generated_at": datetime.now(timezone.utc).isoformat()
        }

    @llm_cache.cached(ttl=LLMCacheService.TTL_DAILY, prefix="insights:digest")
    def generate_executive_digest(self, month: Optional[date] = None) -> Dict[str, Any]:
        """Generate a weekly executive digest email content.
        Cached for 24 hours (weekly report)."""
        if not month:
            month = date.today().replace(day=1)

        context = self._build_context(month)
        gaps_gains = self.profitability_service.identify_gaps_and_gains(month)

        system_prompt = """You are an AI executive assistant creating a weekly profitability digest for mortgage company leadership.

Create a professional, scannable email digest with:
1. Executive Summary (3 bullet points with key metrics)
2. Key Wins (what's going well)
3. Areas of Concern (what needs attention)
4. AI Insights (2-3 data-driven observations)
5. Recommended Actions (prioritized list)

Use emojis sparingly for visual scanning (✅ ⚠️ 📈 📉 💡).
Format numbers clearly: $X,XXX for currency, X.X% for percentages.
Keep it concise - executives are busy. Total length should be readable in 2 minutes."""

        user_prompt = f"""Generate an executive digest for the week of {month.strftime('%B %d, %Y')}:

PROFITABILITY DATA:
{json.dumps(context, indent=2, default=str)}

GAPS & GAINS ANALYSIS:
{json.dumps(gaps_gains, indent=2, default=str)}

Create a professional executive digest email."""

        response = self.client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=2000,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}]
        )

        return {
            "subject": f"Perennia AI Profitability Insights - Week of {month.strftime('%b %d')}",
            "content": response.content[0].text,
            "summary": context["summary"],
            "generated_at": datetime.now(timezone.utc).isoformat()
        }

    @llm_cache.cached(ttl=LLMCacheService.TTL_MEDIUM, prefix="insights:anomalies")
    def detect_anomalies(self, month: Optional[date] = None) -> List[Dict[str, Any]]:
        """Detect unusual patterns or anomalies in profitability data.
        Cached for 1 hour (needs fresh data)."""
        if not month:
            month = date.today().replace(day=1)

        context = self._build_context(month)

        system_prompt = """You are an AI anomaly detection system for mortgage company profitability.
Identify unusual patterns, outliers, or concerning trends in the data.

For each anomaly found, provide:
1. Type (cost_spike, performance_drop, revenue_anomaly, trend_deviation, etc.)
2. Severity (critical/warning/info)
3. Description of the anomaly
4. Affected metric/entity
5. Suggested investigation steps

Return as a JSON array. Only include genuine anomalies - don't force findings if data looks normal."""

        user_prompt = f"""Analyze this profitability data for anomalies ({month.strftime('%B %Y')}):

{json.dumps(context, indent=2, default=str)}

Return a JSON array of anomaly objects, or empty array if no anomalies detected."""

        response = self.client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1500,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}]
        )

        try:
            response_text = response.content[0].text
            if "```json" in response_text:
                response_text = response_text.split("```json")[1].split("```")[0]
            elif "```" in response_text:
                response_text = response_text.split("```")[1].split("```")[0]

            anomalies = json.loads(response_text)
        except (json.JSONDecodeError, IndexError):
            anomalies = []

        return anomalies

    @llm_cache.cached(ttl=LLMCacheService.TTL_LONG, prefix="insights:scenarios")
    def compare_scenarios(
        self,
        scenarios: List[Dict[str, Any]],
        month: Optional[date] = None
    ) -> Dict[str, Any]:
        """Compare multiple scenarios and provide AI recommendation.
        Cached for 6 hours (planning scenarios)."""
        if not month:
            month = date.today().replace(day=1)

        context = self._build_context(month)

        system_prompt = """You are an AI financial analyst comparing business scenarios for a mortgage company.
Analyze each scenario and provide:
1. Pros and cons of each option
2. Risk assessment
3. Expected ROI comparison
4. Clear recommendation with reasoning
5. Sensitivity analysis (what could change the recommendation)

Be specific with numbers. Consider both short-term and long-term impacts."""

        user_prompt = f"""Compare these scenarios based on current data ({month.strftime('%B %Y')}):

SCENARIOS:
{json.dumps(scenarios, indent=2, default=str)}

CURRENT DATA:
{json.dumps(context["summary"], indent=2, default=str)}

Provide a detailed comparison and recommendation."""

        response = self.client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=2000,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}]
        )

        return {
            "scenarios_analyzed": len(scenarios),
            "analysis": response.content[0].text,
            "generated_at": datetime.now(timezone.utc).isoformat()
        }

    def _build_context(self, month: date) -> Dict[str, Any]:
        """Build comprehensive context for AI analysis."""
        # Get all profitability data
        metrics = self.profitability_service.get_dashboard_metrics(month)
        role_profitability = self.profitability_service.get_role_profitability(month)
        employee_performance = self.profitability_service.get_employee_performance(month, limit=20)
        trends = self.profitability_service.get_trends(months=6)

        # Get employee details
        employees = self.db.query(EmployeeCost).filter(
            EmployeeCost.organization_id == self.organization_id,
            EmployeeCost.is_active == True
        ).all()

        # Calculate summary stats
        total_employees = len(employees)
        total_monthly_cost = sum(e.monthly_cost for e in employees)

        return {
            "summary": {
                "month": month.strftime("%Y-%m"),
                "total_employees": total_employees,
                "total_monthly_employee_cost": total_monthly_cost,
                "total_revenue": metrics.get("total_revenue", 0),
                "total_expenses": metrics.get("total_expenses", 0),
                "profit_margin": metrics.get("profit_margin", 0),
                "cost_per_loan": metrics.get("cost_per_loan", 0),
                "revenue_per_loan": metrics.get("revenue_per_loan", 0),
                "loans_closed": metrics.get("loans_closed", 0),
                "break_even_loans": metrics.get("break_even_loans", 0)
            },
            "role_profitability": role_profitability,
            "top_performers": employee_performance[:10] if employee_performance else [],
            "trends": trends,
            "metrics": metrics
        }

    def save_insight(
        self,
        insight_type: str,
        title: str,
        description: str,
        severity: str = "info",
        data_json: Optional[Dict] = None
    ) -> ProfitabilityInsight:
        """Save an AI-generated insight to the database."""
        insight = ProfitabilityInsight(
            organization_id=self.organization_id,
            insight_type=insight_type,
            title=title,
            description=description,
            severity=severity,
            data_json=data_json or {}
        )
        self.db.add(insight)
        self.db.commit()
        self.db.refresh(insight)
        return insight
