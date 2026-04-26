"""
Perennia AI - Team Coaching Tools
Tools for the Team Coach agent to analyze and improve LO performance.
"""

from datetime import datetime, date, timedelta
from typing import Optional, List, Dict, Any
from decimal import Decimal

from .base import (
    mortgage_tool, ToolResult, ToolError,
    execute_query, execute_single, get_db,
    format_currency, format_percentage, format_date, days_between,
    calculate_percentage_change,
    SLA_TARGETS,
)


# Performance benchmarks
PERFORMANCE_BENCHMARKS = {
    "volume_monthly": {"top": 5000000, "good": 2500000, "avg": 1500000, "low": 500000},
    "units_monthly": {"top": 12, "good": 8, "avg": 5, "low": 2},
    "conversion_rate": {"top": 35, "good": 25, "avg": 18, "low": 10},
    "speed_to_lead_min": {"top": 3, "good": 10, "avg": 30, "low": 60},
    "customer_satisfaction": {"top": 4.8, "good": 4.5, "avg": 4.0, "low": 3.5},
    "pull_through": {"top": 85, "good": 75, "avg": 65, "low": 50},
}


@mortgage_tool(
    name="get_lo_metrics",
    description="Get comprehensive performance metrics for a loan officer",
    agent_roles=["team_coach", "profitability_analyst"],
    risk_level="LOW",
    examples=[
        "get_lo_metrics(lo_id='LO123')",
        "get_lo_metrics(lo_id='LO123', date_range=60)",
    ],
)
def get_lo_metrics(
    lo_id: str,
    date_range: int = 30,
    compare_to_team: bool = True,
) -> ToolResult:
    """
    Get comprehensive performance metrics for a loan officer.
    """
    # Get LO info
    lo = execute_single("""
        SELECT
            u.id, COALESCE(es.full_name, u.email) AS name, u.email, u.hire_date,
            b.name as branch_name,
            COALESCE(ms.full_name, m.email) as manager_name
        FROM users u
        LEFT JOIN email_signatures es ON es.user_id = u.id
        LEFT JOIN branches b ON b.id = u.branch_id
        LEFT JOIN users m ON m.id = u.manager_id
        LEFT JOIN email_signatures ms ON ms.user_id = m.id
        WHERE u.id = :lo_id
    """, {"lo_id": lo_id})

    if not lo:
        return ToolResult.no_data(f"Loan officer {lo_id} not found")

    # Production metrics
    production = execute_single("""
        SELECT
            COUNT(*) as total_apps,
            COUNT(CASE WHEN stage = 'Funded' THEN 1 END) as funded,
            COUNT(CASE WHEN stage NOT IN ('Disclosed', 'Processing', 'Submitted', 'UW Received', 'Approved', 'Suspended', 'CTC', 'Docs Out', 'Funded') THEN 1 END) as fallout,
            SUM(CASE WHEN stage = 'Funded' THEN loan_amount END) as funded_volume,
            AVG(CASE WHEN stage = 'Funded' THEN loan_amount END) as avg_loan_size
        FROM loans
        WHERE loan_officer_id = :lo_id
            AND created_at >= CURRENT_DATE - :date_range
    """, {"lo_id": lo_id, "date_range": date_range})

    # Speed metrics
    speed = execute_single("""
        SELECT
            AVG(EXTRACT(EPOCH FROM first_contact_at - created_at) / 60) as avg_speed_to_lead,
            AVG(EXTRACT(DAY FROM funded_date - created_at)) as avg_cycle_time
        FROM loans
        WHERE loan_officer_id = :lo_id
            AND created_at >= CURRENT_DATE - :date_range
            AND first_contact_at IS NOT NULL
    """, {"lo_id": lo_id, "date_range": date_range})

    # Customer satisfaction
    satisfaction = execute_single("""
        SELECT
            AVG(rating) as avg_rating,
            COUNT(*) as review_count,
            COUNT(CASE WHEN rating >= 4 THEN 1 END) as positive_reviews
        FROM customer_reviews
        WHERE loan_officer_id = :lo_id
            AND created_at >= CURRENT_DATE - :date_range
    """, {"lo_id": lo_id, "date_range": date_range})

    # Calculate KPIs
    funded = production["funded"] or 0
    total = production["total_apps"] or 0
    fallout = production["fallout"] or 0

    conversion_rate = (funded / total * 100) if total > 0 else 0
    pull_through = (funded / (funded + fallout) * 100) if (funded + fallout) > 0 else 0
    funded_volume = float(production["funded_volume"] or 0)

    # Rate against benchmarks
    metrics = {
        "production": {
            "total_applications": total,
            "funded_loans": funded,
            "fallout": fallout,
            "funded_volume": funded_volume,
            "volume_formatted": format_currency(funded_volume),
            "avg_loan_size": float(production["avg_loan_size"] or 0),
            "avg_loan_formatted": format_currency(production["avg_loan_size"] or 0),
        },
        "conversion": {
            "conversion_rate": round(conversion_rate, 1),
            "pull_through_rate": round(pull_through, 1),
        },
        "speed": {
            "avg_speed_to_lead_min": round(float(speed["avg_speed_to_lead"] or 0), 1),
            "avg_cycle_time_days": round(float(speed["avg_cycle_time"] or 0), 1),
        },
        "customer": {
            "avg_rating": round(float(satisfaction["avg_rating"] or 0), 2),
            "review_count": satisfaction["review_count"] or 0,
            "positive_pct": round((satisfaction["positive_reviews"] or 0) / satisfaction["review_count"] * 100, 1) if satisfaction["review_count"] else 0,
        },
    }

    # Performance ratings
    ratings = {
        "volume": _rate_performance(funded_volume * (30 / date_range), "volume_monthly"),
        "units": _rate_performance(funded * (30 / date_range), "units_monthly"),
        "conversion": _rate_performance(conversion_rate, "conversion_rate"),
        "speed_to_lead": _rate_performance(speed["avg_speed_to_lead"] or 60, "speed_to_lead_min"),
        "satisfaction": _rate_performance(satisfaction["avg_rating"] or 0, "customer_satisfaction"),
        "pull_through": _rate_performance(pull_through, "pull_through"),
    }

    # Team comparison
    team_comparison = None
    if compare_to_team:
        team = execute_single("""
            SELECT
                AVG(funded_count) as avg_funded,
                AVG(funded_volume) as avg_volume,
                AVG(conversion_rate) as avg_conversion
            FROM (
                SELECT
                    loan_officer_id,
                    COUNT(CASE WHEN stage = 'Funded' THEN 1 END) as funded_count,
                    SUM(CASE WHEN stage = 'Funded' THEN loan_amount END) as funded_volume,
                    COUNT(CASE WHEN stage = 'Funded' THEN 1 END)::float /
                        NULLIF(COUNT(*), 0) * 100 as conversion_rate
                FROM loans
                WHERE created_at >= CURRENT_DATE - :date_range
                GROUP BY loan_officer_id
            ) team_metrics
        """, {"date_range": date_range})

        if team:
            team_comparison = {
                "volume_vs_team": round(calculate_percentage_change(float(team["avg_volume"] or 1), funded_volume), 1),
                "units_vs_team": round(calculate_percentage_change(float(team["avg_funded"] or 1), funded), 1),
                "conversion_vs_team": round(conversion_rate - float(team["avg_conversion"] or 0), 1),
            }

    data = {
        "lo_id": lo_id,
        "lo_info": {
            "name": lo["name"],
            "email": lo["email"],
            "branch": lo["branch_name"],
            "manager": lo["manager_name"],
            "tenure_days": days_between(lo["hire_date"]) if lo.get("hire_date") else None,
        },
        "period_days": date_range,
        "metrics": metrics,
        "ratings": ratings,
        "team_comparison": team_comparison,
        "overall_rating": _calculate_overall_rating(ratings),
        "strengths": [k for k, v in ratings.items() if v in ("top", "good")],
        "improvement_areas": [k for k, v in ratings.items() if v in ("low", "below_avg")],
    }

    return ToolResult.success(
        data=data,
        message=f"{lo['name']}: {funded} loans, {format_currency(funded_volume)}, {data['overall_rating']} performer",
    )


def _rate_performance(value: float, metric: str) -> str:
    """Rate a metric against benchmarks."""
    benchmarks = PERFORMANCE_BENCHMARKS.get(metric, {})

    # Lower is better for speed metrics
    lower_is_better = metric in ("speed_to_lead_min",)

    if lower_is_better:
        if value <= benchmarks.get("top", 0):
            return "top"
        elif value <= benchmarks.get("good", 0):
            return "good"
        elif value <= benchmarks.get("avg", 0):
            return "average"
        else:
            return "below_avg"
    else:
        if value >= benchmarks.get("top", float("inf")):
            return "top"
        elif value >= benchmarks.get("good", float("inf")):
            return "good"
        elif value >= benchmarks.get("avg", float("inf")):
            return "average"
        elif value >= benchmarks.get("low", float("inf")):
            return "below_avg"
        else:
            return "low"


def _calculate_overall_rating(ratings: Dict[str, str]) -> str:
    """Calculate overall performance rating."""
    score_map = {"top": 5, "good": 4, "average": 3, "below_avg": 2, "low": 1}
    scores = [score_map.get(r, 3) for r in ratings.values()]
    avg_score = sum(scores) / len(scores) if scores else 3

    if avg_score >= 4.5:
        return "top"
    elif avg_score >= 3.5:
        return "strong"
    elif avg_score >= 2.5:
        return "solid"
    else:
        return "developing"


@mortgage_tool(
    name="compare_to_peers",
    description="Compare LO performance to peers",
    agent_roles=["team_coach"],
    risk_level="LOW",
)
def compare_to_peers(
    lo_id: str,
    peer_group: str = "branch",
    date_range: int = 30,
) -> ToolResult:
    """
    Compare LO to peer group (branch, region, company).
    """
    # Get LO's branch for filtering
    lo = execute_single("""
        SELECT u.branch_id, COALESCE(es.full_name, u.email) AS name
        FROM users u LEFT JOIN email_signatures es ON es.user_id = u.id
        WHERE u.id = :lo_id
    """, {"lo_id": lo_id})

    if not lo:
        return ToolResult.no_data(f"LO {lo_id} not found")

    # Build peer filter
    peer_filter = ""
    params = {"lo_id": lo_id, "date_range": date_range}

    if peer_group == "branch" and lo.get("branch_id"):
        peer_filter = "AND u.branch_id = :branch_id"
        params["branch_id"] = lo["branch_id"]

    peers = execute_query(f"""
        SELECT
            u.id as lo_id,
            COALESCE(es.full_name, u.email) as lo_name,
            COUNT(CASE WHEN l.stage = 'Funded' THEN 1 END) as funded,
            SUM(CASE WHEN l.stage = 'Funded' THEN l.loan_amount END) as volume,
            COUNT(CASE WHEN l.stage = 'Funded' THEN 1 END)::float /
                NULLIF(COUNT(*), 0) * 100 as conversion,
            AVG(EXTRACT(EPOCH FROM l.first_contact_at - l.created_at) / 60) as speed_to_lead
        FROM users u
        LEFT JOIN email_signatures es ON es.user_id = u.id
        LEFT JOIN loans l ON l.loan_officer_id = u.id
            AND l.created_at >= CURRENT_DATE - :date_range
        WHERE u.role = 'loan_officer'
            AND u.is_active = true
            {peer_filter}
        GROUP BY u.id, COALESCE(es.full_name, u.email)
        HAVING COUNT(*) > 0
        ORDER BY volume DESC NULLS LAST
    """, params)

    if not peers:
        return ToolResult.no_data("No peer data available")

    # Find LO's position
    lo_data = next((p for p in peers if p["lo_id"] == lo_id), None)

    if not lo_data:
        return ToolResult.no_data(f"No data for LO {lo_id}")

    # Calculate rankings
    by_volume = sorted(peers, key=lambda x: float(x["volume"] or 0), reverse=True)
    by_units = sorted(peers, key=lambda x: x["funded"] or 0, reverse=True)
    by_conversion = sorted(peers, key=lambda x: float(x["conversion"] or 0), reverse=True)
    by_speed = sorted(peers, key=lambda x: float(x["speed_to_lead"] or 999))

    lo_rankings = {
        "volume": next((i + 1 for i, p in enumerate(by_volume) if p["lo_id"] == lo_id), None),
        "units": next((i + 1 for i, p in enumerate(by_units) if p["lo_id"] == lo_id), None),
        "conversion": next((i + 1 for i, p in enumerate(by_conversion) if p["lo_id"] == lo_id), None),
        "speed_to_lead": next((i + 1 for i, p in enumerate(by_speed) if p["lo_id"] == lo_id), None),
    }

    total_peers = len(peers)

    # Calculate percentiles
    percentiles = {
        k: round((1 - (v - 1) / total_peers) * 100, 1) if v else None
        for k, v in lo_rankings.items()
    }

    # Group averages
    peer_avg = {
        "volume": sum(float(p["volume"] or 0) for p in peers) / total_peers,
        "units": sum(p["funded"] or 0 for p in peers) / total_peers,
        "conversion": sum(float(p["conversion"] or 0) for p in peers) / total_peers,
    }

    data = {
        "lo_id": lo_id,
        "lo_name": lo["name"],
        "peer_group": peer_group,
        "peer_count": total_peers,
        "rankings": {
            "by_volume": f"{lo_rankings['volume']}/{total_peers}",
            "by_units": f"{lo_rankings['units']}/{total_peers}",
            "by_conversion": f"{lo_rankings['conversion']}/{total_peers}",
            "by_speed": f"{lo_rankings['speed_to_lead']}/{total_peers}",
        },
        "percentiles": percentiles,
        "vs_peer_average": {
            "volume": round(calculate_percentage_change(peer_avg["volume"], float(lo_data["volume"] or 0)), 1),
            "units": round(calculate_percentage_change(peer_avg["units"], lo_data["funded"] or 0), 1),
            "conversion": round((float(lo_data["conversion"] or 0)) - peer_avg["conversion"], 1),
        },
        "leaderboard": {
            "top_by_volume": [{"name": p["lo_name"], "value": format_currency(p["volume"])} for p in by_volume[:5]],
            "top_by_conversion": [{"name": p["lo_name"], "value": f"{float(p['conversion'] or 0):.1f}%"} for p in by_conversion[:5]],
        },
    }

    avg_percentile = sum(p for p in percentiles.values() if p) / len([p for p in percentiles.values() if p])
    position = "top quartile" if avg_percentile >= 75 else "above average" if avg_percentile >= 50 else "below average"

    return ToolResult.success(
        data=data,
        message=f"{lo['name']}: {position} vs {peer_group} peers (volume rank {lo_rankings['volume']}/{total_peers})",
    )


@mortgage_tool(
    name="identify_training_needs",
    description="Identify training and development needs for an LO",
    agent_roles=["team_coach"],
    risk_level="LOW",
)
def identify_training_needs(
    lo_id: str,
    date_range: int = 90,
) -> ToolResult:
    """
    Analyze performance to identify training opportunities.
    """
    # Get comprehensive metrics
    metrics_result = get_lo_metrics(lo_id, date_range, compare_to_team=True)
    if metrics_result.status.value != "success":
        return metrics_result

    metrics = metrics_result.data
    ratings = metrics.get("ratings", {})

    # Analyze specific areas
    training_needs = []

    # Speed to lead
    stl = metrics.get("metrics", {}).get("speed", {}).get("avg_speed_to_lead_min", 0)
    if stl > 15:
        training_needs.append({
            "area": "Speed to Lead",
            "priority": "high" if stl > 30 else "medium",
            "current": f"{stl:.0f} minutes",
            "target": "Under 5 minutes",
            "recommended_training": [
                "Lead response workflow optimization",
                "Mobile CRM app usage",
                "Lead notification setup",
            ],
            "impact": "Each minute of delay reduces conversion by 5%",
        })

    # Conversion rate
    conversion = metrics.get("metrics", {}).get("conversion", {}).get("conversion_rate", 0)
    if conversion < 20:
        training_needs.append({
            "area": "Lead Conversion",
            "priority": "high",
            "current": f"{conversion:.1f}%",
            "target": "25%+",
            "recommended_training": [
                "Consultative selling techniques",
                "Needs discovery questioning",
                "Objection handling",
                "Follow-up cadence best practices",
            ],
            "impact": "5% conversion improvement = significant revenue increase",
        })

    # Pull-through rate
    pull_through = metrics.get("metrics", {}).get("conversion", {}).get("pull_through_rate", 0)
    if pull_through < 70:
        training_needs.append({
            "area": "Pull-Through Rate",
            "priority": "high" if pull_through < 60 else "medium",
            "current": f"{pull_through:.1f}%",
            "target": "75%+",
            "recommended_training": [
                "Pre-qualification best practices",
                "Document collection efficiency",
                "Borrower communication cadence",
                "Setting realistic expectations",
            ],
            "impact": "Reducing fallout saves time and improves profitability",
        })

    # Customer satisfaction
    satisfaction = metrics.get("metrics", {}).get("customer", {}).get("avg_rating", 0)
    if satisfaction < 4.5 and satisfaction > 0:
        training_needs.append({
            "area": "Customer Experience",
            "priority": "medium",
            "current": f"{satisfaction:.1f}/5.0",
            "target": "4.5+",
            "recommended_training": [
                "Communication skills workshop",
                "Proactive status updates",
                "Managing expectations",
                "Handling difficult conversations",
            ],
            "impact": "Higher ratings lead to more referrals",
        })

    # Average loan size
    avg_loan = metrics.get("metrics", {}).get("production", {}).get("avg_loan_size", 0)
    team_avg_loan = 400000  # Benchmark
    if avg_loan < team_avg_loan * 0.8:
        training_needs.append({
            "area": "Loan Size Optimization",
            "priority": "low",
            "current": format_currency(avg_loan),
            "target": format_currency(team_avg_loan),
            "recommended_training": [
                "Market positioning strategies",
                "Targeting higher-value segments",
                "Refinance opportunity identification",
            ],
            "impact": "Higher average loan size improves efficiency",
        })

    # Calculate development plan
    by_priority = {
        "high": [t for t in training_needs if t["priority"] == "high"],
        "medium": [t for t in training_needs if t["priority"] == "medium"],
        "low": [t for t in training_needs if t["priority"] == "low"],
    }

    data = {
        "lo_id": lo_id,
        "lo_name": metrics.get("lo_info", {}).get("name"),
        "overall_rating": metrics.get("overall_rating"),
        "strengths": metrics.get("strengths", []),
        "training_needs": training_needs,
        "by_priority": by_priority,
        "development_plan": {
            "immediate_focus": by_priority["high"][:2] if by_priority["high"] else by_priority["medium"][:1],
            "next_quarter": by_priority["medium"] if by_priority["high"] else by_priority["low"],
            "ongoing": by_priority["low"],
        },
    }

    return ToolResult.success(
        data=data,
        message=f"Training analysis: {len(by_priority['high'])} high-priority, {len(by_priority['medium'])} medium, {len(by_priority['low'])} low",
    )


@mortgage_tool(
    name="generate_coaching_plan",
    description="Generate a personalized coaching plan for an LO",
    agent_roles=["team_coach"],
    risk_level="MEDIUM",
)
def generate_coaching_plan(
    lo_id: str,
    focus_areas: Optional[List[str]] = None,
    duration_weeks: int = 4,
) -> ToolResult:
    """
    Generate a structured coaching plan.
    """
    # Get training needs first
    needs_result = identify_training_needs(lo_id)
    if needs_result.status.value != "success":
        return needs_result

    needs_data = needs_result.data
    training_needs = needs_data.get("training_needs", [])

    # Filter by focus areas if specified
    if focus_areas:
        training_needs = [t for t in training_needs if t["area"].lower() in [f.lower() for f in focus_areas]]

    # Generate weekly plan
    weekly_activities = []

    # Week 1: Assessment and baseline
    week1 = {
        "week": 1,
        "theme": "Assessment & Baseline",
        "activities": [
            {"type": "meeting", "description": "Initial coaching session - review metrics and set goals"},
            {"type": "shadowing", "description": "Manager shadows 2-3 lead calls"},
            {"type": "self_study", "description": "Review recorded calls for self-assessment"},
        ],
        "metrics_to_track": ["Speed to lead", "Lead contact rate"],
        "success_criteria": "Baseline established for all focus areas",
    }
    weekly_activities.append(week1)

    # Week 2-3: Skill building
    for i, week_num in enumerate([2, 3]):
        focus = training_needs[i % len(training_needs)] if training_needs else None

        week = {
            "week": week_num,
            "theme": f"Skill Building: {focus['area']}" if focus else "Skill Building",
            "activities": [
                {"type": "training", "description": focus["recommended_training"][0] if focus else "General skills workshop"},
                {"type": "practice", "description": "Role-play exercises with manager"},
                {"type": "application", "description": "Apply new techniques on live leads"},
            ],
            "metrics_to_track": [focus["area"]] if focus else ["Overall performance"],
            "success_criteria": f"Improve {focus['area']} by 10%" if focus else "Demonstrate new skills",
        }
        weekly_activities.append(week)

    # Week 4: Review and next steps
    week4 = {
        "week": 4,
        "theme": "Review & Momentum",
        "activities": [
            {"type": "meeting", "description": "Progress review - compare to baseline"},
            {"type": "celebration", "description": "Recognize improvements"},
            {"type": "planning", "description": "Set 30-60-90 day goals"},
        ],
        "metrics_to_track": ["All focus area metrics"],
        "success_criteria": "Measurable improvement in target areas",
    }
    weekly_activities.append(week4)

    # Goals
    goals = []
    for need in training_needs[:3]:
        goals.append({
            "area": need["area"],
            "current": need["current"],
            "target_4_week": need["target"],
            "milestones": [
                f"Week 1: Establish baseline for {need['area']}",
                f"Week 2: Begin implementing new techniques",
                f"Week 4: Achieve {need['target']}",
            ],
        })

    data = {
        "lo_id": lo_id,
        "lo_name": needs_data.get("lo_name"),
        "duration_weeks": duration_weeks,
        "focus_areas": [t["area"] for t in training_needs[:3]],
        "goals": goals,
        "weekly_plan": weekly_activities,
        "check_ins": {
            "frequency": "Weekly",
            "duration": "30 minutes",
            "format": "1:1 with manager",
        },
        "resources_needed": [
            "Call recording access",
            "Role-play partner",
            "Training materials for focus areas",
        ],
    }

    return ToolResult.success(
        data=data,
        message=f"Coaching plan generated: {duration_weeks} weeks focusing on {len(goals)} areas",
    )


@mortgage_tool(
    name="track_improvement",
    description="Track LO improvement over time",
    agent_roles=["team_coach"],
    risk_level="LOW",
)
def track_improvement(
    lo_id: str,
    metric: str = "all",
    periods: int = 4,
    period_type: str = "weekly",
) -> ToolResult:
    """
    Track improvement trajectory for an LO.
    """
    # Calculate period parameters
    if period_type == "weekly":
        period_days = 7
    elif period_type == "monthly":
        period_days = 30
    else:
        period_days = 7

    period_expr = f"DATE_TRUNC('{period_type[:4]}', created_at)"

    trends = execute_query(f"""
        SELECT
            {period_expr} as period,
            COUNT(*) as total_apps,
            COUNT(CASE WHEN stage = 'Funded' THEN 1 END) as funded,
            SUM(CASE WHEN stage = 'Funded' THEN loan_amount END) as volume,
            COUNT(CASE WHEN stage = 'Funded' THEN 1 END)::float /
                NULLIF(COUNT(*), 0) * 100 as conversion_rate,
            AVG(EXTRACT(EPOCH FROM first_contact_at - created_at) / 60) as avg_stl
        FROM loans
        WHERE loan_officer_id = :lo_id
            AND created_at >= CURRENT_DATE - :total_days
        GROUP BY {period_expr}
        ORDER BY period DESC
        LIMIT :periods
    """, {
        "lo_id": lo_id,
        "total_days": period_days * periods,
        "periods": periods,
    })

    if not trends or len(trends) < 2:
        return ToolResult.no_data(f"Insufficient data for trend analysis")

    # Reverse to chronological order
    trends = list(reversed(trends))

    # Calculate improvements
    first_period = trends[0]
    last_period = trends[-1]

    improvements = {}
    if first_period["funded"] and last_period["funded"]:
        improvements["units"] = {
            "start": first_period["funded"],
            "end": last_period["funded"],
            "change": last_period["funded"] - first_period["funded"],
            "pct_change": calculate_percentage_change(first_period["funded"], last_period["funded"]),
        }

    if first_period["volume"] and last_period["volume"]:
        improvements["volume"] = {
            "start": format_currency(first_period["volume"]),
            "end": format_currency(last_period["volume"]),
            "change": float(last_period["volume"]) - float(first_period["volume"]),
            "pct_change": calculate_percentage_change(float(first_period["volume"]), float(last_period["volume"])),
        }

    if first_period["conversion_rate"] and last_period["conversion_rate"]:
        improvements["conversion"] = {
            "start": f"{float(first_period['conversion_rate']):.1f}%",
            "end": f"{float(last_period['conversion_rate']):.1f}%",
            "change": float(last_period["conversion_rate"]) - float(first_period["conversion_rate"]),
        }

    # Trend direction
    trend_data = []
    for t in trends:
        trend_data.append({
            "period": format_date(t["period"]) if t["period"] else None,
            "funded": t["funded"],
            "volume": float(t["volume"] or 0),
            "conversion": round(float(t["conversion_rate"] or 0), 1),
            "speed_to_lead": round(float(t["avg_stl"] or 0), 1),
        })

    # Calculate trajectory
    trajectory = "improving" if sum(1 for i in improvements.values() if i.get("pct_change", 0) > 0) > len(improvements) / 2 else "declining"

    data = {
        "lo_id": lo_id,
        "period_type": period_type,
        "periods_analyzed": len(trends),
        "improvements": improvements,
        "trend_data": trend_data,
        "trajectory": trajectory,
        "momentum": {
            "recent_vs_prior": round(
                calculate_percentage_change(
                    float(trends[-2]["volume"] or 1),
                    float(trends[-1]["volume"] or 0)
                ), 1
            ) if len(trends) >= 2 else None,
        },
    }

    return ToolResult.success(
        data=data,
        message=f"Trend: {trajectory} over {len(trends)} {period_type} periods",
    )


@mortgage_tool(
    name="get_best_practices",
    description="Get best practices from top performers",
    agent_roles=["team_coach"],
    risk_level="LOW",
)
def get_best_practices(
    metric: str = "conversion",
    branch_id: Optional[str] = None,
) -> ToolResult:
    """
    Analyze top performers to identify best practices.
    """
    # Get top 5 performers for the metric
    params = {"date_range": 90}
    branch_filter = ""
    if branch_id:
        branch_filter = "AND l.branch_id = :branch_id"
        params["branch_id"] = branch_id

    metric_order = {
        "conversion": "conversion_rate DESC",
        "volume": "volume DESC",
        "speed": "avg_stl ASC",
    }.get(metric, "volume DESC")

    top_performers = execute_query(f"""
        SELECT
            l.loan_officer_id,
            COALESCE(es.full_name, u.email) AS name,
            COUNT(CASE WHEN l.stage = 'Funded' THEN 1 END) as funded,
            SUM(CASE WHEN l.stage = 'Funded' THEN l.loan_amount END) as volume,
            COUNT(CASE WHEN l.stage = 'Funded' THEN 1 END)::float /
                NULLIF(COUNT(*), 0) * 100 as conversion_rate,
            AVG(EXTRACT(EPOCH FROM l.first_contact_at - l.created_at) / 60) as avg_stl
        FROM loans l
        JOIN users u ON u.id = l.loan_officer_id
        LEFT JOIN email_signatures es ON es.user_id = u.id
        WHERE l.created_at >= CURRENT_DATE - :date_range
            {branch_filter}
        GROUP BY l.loan_officer_id, COALESCE(es.full_name, u.email)
        HAVING COUNT(*) >= 10
        ORDER BY {metric_order}
        LIMIT 5
    """, params)

    if not top_performers:
        return ToolResult.no_data("Not enough data to identify best practices")

    # Analyze patterns from top performers
    top_ids = [p["loan_officer_id"] for p in top_performers]

    # Activity patterns
    activity_patterns = execute_query("""
        SELECT
            activity_type,
            COUNT(*) / COUNT(DISTINCT l.loan_officer_id) as avg_per_lo,
            AVG(CASE WHEN outcome = 'contacted' THEN 1 ELSE 0 END) * 100 as contact_rate
        FROM lead_activities la
        JOIN loans l ON l.loan_officer_id = la.user_id
        WHERE l.loan_officer_id = ANY(:top_ids)
            AND la.created_at >= CURRENT_DATE - 90
        GROUP BY activity_type
        ORDER BY avg_per_lo DESC
    """, {"top_ids": top_ids})

    # Follow-up patterns
    followup_patterns = execute_query("""
        SELECT
            attempt_number,
            COUNT(*) as attempts,
            AVG(CASE WHEN outcome = 'contacted' THEN 1 ELSE 0 END) * 100 as success_rate
        FROM (
            SELECT
                la.*,
                ROW_NUMBER() OVER (PARTITION BY la.lead_id ORDER BY la.created_at) as attempt_number
            FROM lead_activities la
            JOIN loans l ON l.loan_officer_id = la.user_id
            WHERE l.loan_officer_id = ANY(:top_ids)
                AND la.activity_type IN ('call', 'email', 'sms')
        ) numbered
        GROUP BY attempt_number
        ORDER BY attempt_number
        LIMIT 10
    """, {"top_ids": top_ids})

    best_practices = [
        {
            "category": "Speed",
            "practice": f"Top performers respond in under {round(float(top_performers[0]['avg_stl'] or 5), 0)} minutes",
            "impact": "First responder wins 35-50% of the time",
        },
        {
            "category": "Persistence",
            "practice": "Average 6-8 contact attempts before moving on",
            "impact": "80% of deals close after the 5th touchpoint",
        },
        {
            "category": "Multi-channel",
            "practice": "Use call + text + email in first hour",
            "impact": "Multi-channel outreach increases contact rate by 30%",
        },
    ]

    # Add data-driven practices from activity analysis
    if activity_patterns:
        top_activity = activity_patterns[0]
        best_practices.append({
            "category": "Activity Mix",
            "practice": f"Top performers average {round(float(top_activity['avg_per_lo']), 1)} {top_activity['activity_type']} activities",
            "impact": f"Achieves {round(float(top_activity['contact_rate']), 1)}% contact rate",
        })

    data = {
        "metric_analyzed": metric,
        "top_performers": [
            {
                "name": p["name"],
                "metric_value": f"{float(p['conversion_rate']):.1f}%" if metric == "conversion" else format_currency(p["volume"]),
            }
            for p in top_performers
        ],
        "best_practices": best_practices,
        "activity_patterns": [
            {
                "type": a["activity_type"],
                "avg_per_lo": round(float(a["avg_per_lo"]), 1),
                "contact_rate": f"{float(a['contact_rate']):.1f}%",
            }
            for a in (activity_patterns or [])[:5]
        ],
        "followup_insights": [
            {
                "attempt": f["attempt_number"],
                "success_rate": f"{float(f['success_rate']):.1f}%",
            }
            for f in (followup_patterns or [])
        ],
    }

    return ToolResult.success(
        data=data,
        message=f"Best practices identified from {len(top_performers)} top performers",
    )


@mortgage_tool(
    name="get_performance_trends",
    description="Get team-wide performance trends",
    agent_roles=["team_coach", "pipeline_analyst"],
    risk_level="LOW",
)
def get_performance_trends(
    branch_id: Optional[str] = None,
    period: str = "weekly",
    num_periods: int = 12,
) -> ToolResult:
    """
    Get team performance trends over time.
    """
    period_expr = f"DATE_TRUNC('{period[:5]}', created_at)"

    params = {"num_periods": num_periods}
    branch_filter = ""
    if branch_id:
        branch_filter = "AND branch_id = :branch_id"
        params["branch_id"] = branch_id

    trends = execute_query(f"""
        SELECT
            {period_expr} as period,
            COUNT(DISTINCT loan_officer_id) as active_los,
            COUNT(*) as total_apps,
            COUNT(CASE WHEN stage = 'Funded' THEN 1 END) as funded,
            SUM(CASE WHEN stage = 'Funded' THEN loan_amount END) as volume,
            AVG(CASE WHEN stage = 'Funded' THEN loan_amount END) as avg_loan,
            COUNT(CASE WHEN stage = 'Funded' THEN 1 END)::float /
                NULLIF(COUNT(*), 0) * 100 as conversion
        FROM loans
        WHERE created_at >= CURRENT_DATE - INTERVAL ':num_periods {period}s'
            {branch_filter}
        GROUP BY {period_expr}
        ORDER BY period DESC
        LIMIT :num_periods
    """, params)

    if not trends:
        return ToolResult.no_data("No trend data available")

    # Reverse for chronological order
    trends = list(reversed(trends))

    period_data = [
        {
            "period": format_date(t["period"]) if t["period"] else None,
            "active_los": t["active_los"],
            "applications": t["total_apps"],
            "funded": t["funded"],
            "volume": float(t["volume"] or 0),
            "volume_formatted": format_currency(t["volume"] or 0),
            "avg_loan": float(t["avg_loan"] or 0),
            "conversion": round(float(t["conversion"] or 0), 1),
        }
        for t in trends
    ]

    # Calculate overall trajectory
    if len(period_data) >= 2:
        first_half = period_data[:len(period_data)//2]
        second_half = period_data[len(period_data)//2:]

        first_avg_volume = sum(p["volume"] for p in first_half) / len(first_half)
        second_avg_volume = sum(p["volume"] for p in second_half) / len(second_half)

        trajectory = "growing" if second_avg_volume > first_avg_volume * 1.05 else "declining" if second_avg_volume < first_avg_volume * 0.95 else "stable"
    else:
        trajectory = "insufficient_data"

    data = {
        "period_type": period,
        "num_periods": len(period_data),
        "periods": period_data,
        "trajectory": trajectory,
        "totals": {
            "total_applications": sum(p["applications"] for p in period_data),
            "total_funded": sum(p["funded"] for p in period_data),
            "total_volume": sum(p["volume"] for p in period_data),
            "total_formatted": format_currency(sum(p["volume"] for p in period_data)),
        },
    }

    return ToolResult.success(
        data=data,
        message=f"Team trend: {trajectory} over {len(period_data)} {period} periods",
    )


@mortgage_tool(
    name="set_performance_goals",
    description="Set and track performance goals for an LO",
    agent_roles=["team_coach"],
    risk_level="MEDIUM",
)
def set_performance_goals(
    lo_id: str,
    goals: Optional[Dict[str, float]] = None,
    timeframe_days: int = 30,
) -> ToolResult:
    """
    Set performance goals based on current baseline.
    """
    # Get current metrics for baseline
    metrics_result = get_lo_metrics(lo_id, date_range=30)
    if metrics_result.status.value != "success":
        return metrics_result

    current = metrics_result.data.get("metrics", {})

    # Default goal improvements
    improvement_targets = {
        "funded_units": 1.1,       # 10% more units
        "volume": 1.15,            # 15% more volume
        "conversion_rate": 1.05,   # 5 ppt improvement
        "speed_to_lead": 0.8,      # 20% faster
    }

    # Calculate recommended goals
    recommended_goals = {}

    funded = current.get("production", {}).get("funded_loans", 0)
    recommended_goals["funded_units"] = {
        "current": funded,
        "target": round(funded * improvement_targets["funded_units"]),
        "stretch": round(funded * 1.25),
    }

    volume = current.get("production", {}).get("funded_volume", 0)
    recommended_goals["volume"] = {
        "current": volume,
        "target": round(volume * improvement_targets["volume"]),
        "stretch": round(volume * 1.3),
        "formatted": {
            "current": format_currency(volume),
            "target": format_currency(volume * improvement_targets["volume"]),
            "stretch": format_currency(volume * 1.3),
        },
    }

    conversion = current.get("conversion", {}).get("conversion_rate", 0)
    recommended_goals["conversion_rate"] = {
        "current": conversion,
        "target": round(min(conversion * 1.1, 35), 1),
        "stretch": round(min(conversion * 1.2, 40), 1),
    }

    stl = current.get("speed", {}).get("avg_speed_to_lead_min", 30)
    recommended_goals["speed_to_lead_minutes"] = {
        "current": stl,
        "target": round(max(stl * 0.7, 5), 1),
        "stretch": 5,
    }

    # Apply custom goals if provided
    if goals:
        for key, value in goals.items():
            if key in recommended_goals:
                recommended_goals[key]["custom_target"] = value

    # Save goals to database
    from sqlalchemy import text
    with get_db() as db:
        # Check for existing active goals
        existing = execute_single("""
            SELECT id FROM performance_goals
            WHERE lo_id = :lo_id AND status = 'active'
        """, {"lo_id": lo_id})

        if existing:
            # Archive existing
            db.execute(text("""
                UPDATE performance_goals
                SET status = 'archived', updated_at = CURRENT_TIMESTAMP
                WHERE lo_id = :lo_id AND status = 'active'
            """), {"lo_id": lo_id})

        # Create new goals
        import json
        db.execute(text("""
            INSERT INTO performance_goals
                (lo_id, goals_json, baseline_json, timeframe_days, status, created_at)
            VALUES
                (:lo_id, :goals, :baseline, :timeframe, 'active', CURRENT_TIMESTAMP)
        """), {
            "lo_id": lo_id,
            "goals": json.dumps(recommended_goals),
            "baseline": json.dumps(current),
            "timeframe": timeframe_days,
        })

    data = {
        "lo_id": lo_id,
        "lo_name": metrics_result.data.get("lo_info", {}).get("name"),
        "timeframe_days": timeframe_days,
        "goals": recommended_goals,
        "baseline": current,
        "check_in_dates": [
            format_date(date.today() + timedelta(days=timeframe_days // 4)),
            format_date(date.today() + timedelta(days=timeframe_days // 2)),
            format_date(date.today() + timedelta(days=3 * timeframe_days // 4)),
            format_date(date.today() + timedelta(days=timeframe_days)),
        ],
    }

    return ToolResult.success(
        data=data,
        message=f"Goals set for {timeframe_days} days: {len(recommended_goals)} metrics tracked",
    )
