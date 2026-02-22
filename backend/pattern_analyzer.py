"""
Pattern Analyzer - Tracks and surfaces historical patterns and insights
Analyzes CRM data to identify trends, bottlenecks, and opportunities
"""
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import text

logger = logging.getLogger(__name__)


class PatternAnalyzer:
    """
    Analyzes historical CRM data to identify patterns.
    Teaches the AI about user behavior, lead velocity, and success factors.
    """

    # Configuration
    ANALYSIS_WINDOW_DAYS = 90  # Look back period for pattern analysis
    MIN_SAMPLES = 3  # Minimum samples to consider a pattern valid
    STALE_LEAD_DAYS = 14  # Days without activity = stale

    @staticmethod
    def analyze_user_patterns(db: Session, user_id: int) -> Dict[str, Any]:
        """
        Comprehensive pattern analysis for a user.
        Returns insights about lead velocity, sticking points, close rates, etc.
        """
        try:
            db.rollback()  # Clear any previous failed transaction
        except Exception as e:
            logger.warning(f"Error during pre-analysis rollback: {e}")

        logger.info(f"Analyzing patterns for user {user_id}")

        try:
            patterns = {
                "lead_velocity": PatternAnalyzer._calculate_lead_velocity(db, user_id),
                "sticking_points": PatternAnalyzer._identify_sticking_points(db, user_id),
                "close_rates_by_type": PatternAnalyzer._calculate_close_rates_by_type(db, user_id),
                "top_lead_sources": PatternAnalyzer._identify_top_lead_sources(db, user_id),
                "activity_patterns": PatternAnalyzer._analyze_activity_patterns(db, user_id),
                "pipeline_health": PatternAnalyzer._assess_pipeline_health(db, user_id),
                "recommendations": []  # Will be populated based on other patterns
            }

            # Generate recommendations based on patterns
            patterns["recommendations"] = PatternAnalyzer._generate_recommendations(patterns)

            return patterns

        except Exception as e:
            logger.error(f"Error analyzing patterns: {e}")
            try:
                db.rollback()
            except Exception as e:
                logger.warning(f"Error during post-failure rollback: {e}")
            return {}

    @staticmethod
    def _calculate_lead_velocity(db: Session, user_id: int) -> Dict[str, Any]:
        """
        Calculate how fast leads move through the pipeline.
        Returns average days in each stage.
        """
        try:
            # Calculate average time leads spend in each stage
            result = db.execute(text("""
                WITH stage_times AS (
                    SELECT
                        stage,
                        EXTRACT(EPOCH FROM (NOW() - created_at))/86400 as days_in_stage,
                        preapproval_amount
                    FROM leads
                    WHERE owner_id = :user_id
                    AND stage NOT IN ('CLOSED_WON', 'CLOSED_LOST')
                    AND created_at > NOW() - INTERVAL :window
                )
                SELECT
                    stage,
                    COUNT(*) as count,
                    AVG(days_in_stage) as avg_days,
                    SUM(preapproval_amount) as total_value
                FROM stage_times
                WHERE stage IS NOT NULL
                GROUP BY stage
                ORDER BY avg_days DESC
            """), {"user_id": user_id, "window": f"{PatternAnalyzer.ANALYSIS_WINDOW_DAYS} days"})

            velocity = {}
            for row in result:
                stage = str(row[0]) if row[0] else "Unknown"
                velocity[stage] = {
                    "count": row[1],
                    "avg_days": round(float(row[2]), 1) if row[2] else 0,
                    "total_value": float(row[3]) if row[3] else 0
                }

            return velocity

        except Exception as e:
            logger.error(f"Error calculating lead velocity: {e}")
            return {}

    @staticmethod
    def _identify_sticking_points(db: Session, user_id: int) -> List[Dict[str, Any]]:
        """
        Where do leads get stuck? Identify bottlenecks.
        """
        try:
            result = db.execute(text("""
                SELECT
                    l.id,
                    l.name,
                    l.stage,
                    l.preapproval_amount,
                    l.created_at,
                    EXTRACT(EPOCH FROM (NOW() - l.created_at))/86400 as days_stale
                FROM leads l
                WHERE l.owner_id = :user_id
                AND l.stage NOT IN ('CLOSED_WON', 'CLOSED_LOST')
                AND l.created_at < NOW() - INTERVAL :stale_days
                ORDER BY l.created_at ASC
                LIMIT 20
            """), {
                "user_id": user_id,
                "stale_days": f"{PatternAnalyzer.STALE_LEAD_DAYS} days"
            })

            stale_leads = []
            for row in result:
                stale_leads.append({
                    "id": row[0],
                    "name": row[1],
                    "stage": str(row[2]) if row[2] else "Unknown",
                    "loan_amount": float(row[3]) if row[3] else 0,
                    "created_at": row[4].isoformat() if row[4] else None,
                    "days_stale": round(float(row[5]), 1) if row[5] else 0
                })

            # Group by stage to show bottlenecks
            stage_counts = {}
            for lead in stale_leads:
                stage = lead["stage"]
                if stage not in stage_counts:
                    stage_counts[stage] = {
                        "count": 0,
                        "total_value": 0,
                        "examples": []
                    }
                stage_counts[stage]["count"] += 1
                stage_counts[stage]["total_value"] += lead["loan_amount"]
                if len(stage_counts[stage]["examples"]) < 3:
                    stage_counts[stage]["examples"].append({
                        "name": lead["name"],
                        "days_stale": lead["days_stale"],
                        "loan_amount": lead["loan_amount"]
                    })

            # Convert to list sorted by count
            bottlenecks = [
                {
                    "stage": stage,
                    "stuck_count": data["count"],
                    "total_value_stuck": data["total_value"],
                    "examples": data["examples"]
                }
                for stage, data in sorted(stage_counts.items(), key=lambda x: x[1]["count"], reverse=True)
            ]

            return bottlenecks

        except Exception as e:
            logger.error(f"Error identifying sticking points: {e}")
            return []

    @staticmethod
    def _calculate_close_rates_by_type(db: Session, user_id: int) -> Dict[str, Any]:
        """
        Close rates by loan type.
        """
        try:
            result = db.execute(text("""
                SELECT
                    loan_type,
                    COUNT(*) as total,
                    COUNT(*) FILTER (WHERE stage = 'CLOSED_WON') as won,
                    AVG(preapproval_amount) as avg_amount
                FROM leads
                WHERE owner_id = :user_id
                AND created_at > NOW() - INTERVAL :window
                AND loan_type IS NOT NULL
                GROUP BY loan_type
                HAVING COUNT(*) >= :min_samples
                ORDER BY COUNT(*) DESC
            """), {
                "user_id": user_id,
                "window": f"{PatternAnalyzer.ANALYSIS_WINDOW_DAYS} days",
                "min_samples": PatternAnalyzer.MIN_SAMPLES
            })

            close_rates = {}
            for row in result:
                loan_type = row[0] or "Unknown"
                total = row[1]
                won = row[2]
                close_rate = (won / total * 100) if total > 0 else 0

                close_rates[loan_type] = {
                    "total_leads": total,
                    "closed_won": won,
                    "close_rate_pct": round(close_rate, 1),
                    "avg_loan_amount": float(row[3]) if row[3] else 0
                }

            return close_rates

        except Exception as e:
            logger.error(f"Error calculating close rates: {e}")
            return {}

    @staticmethod
    def _identify_top_lead_sources(db: Session, user_id: int) -> List[Dict[str, Any]]:
        """
        Identify which lead sources perform best.
        """
        try:
            result = db.execute(text("""
                SELECT
                    source,
                    COUNT(*) as total_leads,
                    COUNT(*) FILTER (WHERE stage = 'CLOSED_WON') as won_leads,
                    AVG(preapproval_amount) as avg_amount,
                    SUM(preapproval_amount) as total_volume
                FROM leads
                WHERE owner_id = :user_id
                AND created_at > NOW() - INTERVAL :window
                AND source IS NOT NULL
                GROUP BY source
                HAVING COUNT(*) >= :min_samples
                ORDER BY COUNT(*) FILTER (WHERE stage = 'CLOSED_WON') DESC, COUNT(*) DESC
                LIMIT 10
            """), {
                "user_id": user_id,
                "window": f"{PatternAnalyzer.ANALYSIS_WINDOW_DAYS} days",
                "min_samples": PatternAnalyzer.MIN_SAMPLES
            })

            sources = []
            for row in result:
                total = row[1]
                won = row[2]
                close_rate = (won / total * 100) if total > 0 else 0

                sources.append({
                    "source": row[0] or "Unknown",
                    "total_leads": total,
                    "won_leads": won,
                    "close_rate_pct": round(close_rate, 1),
                    "avg_loan_amount": float(row[3]) if row[3] else 0,
                    "total_volume": float(row[4]) if row[4] else 0
                })

            return sources

        except Exception as e:
            logger.error(f"Error identifying top lead sources: {e}")
            return []

    @staticmethod
    def _analyze_activity_patterns(db: Session, user_id: int) -> Dict[str, Any]:
        """
        Analyze user activity patterns - when are they most productive?
        """
        try:
            # Get activity counts by day of week
            result = db.execute(text("""
                SELECT
                    EXTRACT(DOW FROM created_at) as day_of_week,
                    COUNT(*) as activity_count
                FROM activities
                WHERE user_id = :user_id
                AND created_at > NOW() - INTERVAL '30 days'
                GROUP BY day_of_week
                ORDER BY day_of_week
            """), {"user_id": user_id})

            days = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]
            daily_activity = {}
            for row in result:
                day_idx = int(row[0])
                daily_activity[days[day_idx]] = row[1]

            # Find most and least active days
            if daily_activity:
                most_active = max(daily_activity, key=daily_activity.get)
                least_active = min(daily_activity, key=daily_activity.get)
            else:
                most_active = None
                least_active = None

            return {
                "by_day": daily_activity,
                "most_active_day": most_active,
                "least_active_day": least_active
            }

        except Exception as e:
            logger.error(f"Error analyzing activity patterns: {e}")
            return {}

    @staticmethod
    def _assess_pipeline_health(db: Session, user_id: int) -> Dict[str, Any]:
        """
        Assess overall pipeline health with key metrics.
        """
        try:
            # Get pipeline metrics
            result = db.execute(text("""
                SELECT
                    COUNT(*) as total_leads,
                    COUNT(*) FILTER (WHERE stage = 'CLOSED_WON') as won,
                    COUNT(*) FILTER (WHERE stage = 'CLOSED_LOST') as lost,
                    COUNT(*) FILTER (WHERE stage NOT IN ('CLOSED_WON', 'CLOSED_LOST')) as active,
                    SUM(preapproval_amount) FILTER (WHERE stage NOT IN ('CLOSED_WON', 'CLOSED_LOST')) as active_pipeline_value,
                    SUM(preapproval_amount) FILTER (WHERE stage = 'CLOSED_WON') as won_value,
                    AVG(preapproval_amount) FILTER (WHERE stage = 'CLOSED_WON') as avg_deal_size
                FROM leads
                WHERE owner_id = :user_id
                AND created_at > NOW() - INTERVAL :window
            """), {"user_id": user_id, "window": f"{PatternAnalyzer.ANALYSIS_WINDOW_DAYS} days"})

            row = result.fetchone()
            if not row:
                return {}

            total = row[0] or 0
            won = row[1] or 0
            lost = row[2] or 0
            closed = won + lost

            win_rate = (won / closed * 100) if closed > 0 else 0

            return {
                "total_leads": total,
                "active_leads": row[3] or 0,
                "won": won,
                "lost": lost,
                "win_rate_pct": round(win_rate, 1),
                "active_pipeline_value": float(row[4]) if row[4] else 0,
                "closed_won_value": float(row[5]) if row[5] else 0,
                "avg_deal_size": float(row[6]) if row[6] else 0
            }

        except Exception as e:
            logger.error(f"Error assessing pipeline health: {e}")
            return {}

    @staticmethod
    def _generate_recommendations(patterns: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Generate actionable recommendations based on patterns.
        """
        recommendations = []

        # Check for sticking points
        sticking_points = patterns.get("sticking_points", [])
        if sticking_points:
            worst_bottleneck = sticking_points[0]
            if worst_bottleneck["stuck_count"] >= 3:
                recommendations.append({
                    "type": "STICKING_POINT",
                    "priority": "HIGH",
                    "title": f"Bottleneck in {worst_bottleneck['stage']}",
                    "message": f"You have {worst_bottleneck['stuck_count']} leads stuck in {worst_bottleneck['stage']} "
                               f"stage worth ${worst_bottleneck['total_value_stuck']:,.0f}. "
                               f"Consider reaching out to move them forward.",
                    "action": "Review and follow up with stuck leads"
                })

        # Check lead velocity for slow stages
        lead_velocity = patterns.get("lead_velocity", {})
        for stage, velocity in lead_velocity.items():
            if velocity.get("avg_days", 0) > 30:  # More than 30 days average
                recommendations.append({
                    "type": "SLOW_VELOCITY",
                    "priority": "MEDIUM",
                    "title": f"Slow progress in {stage}",
                    "message": f"Leads are taking {velocity['avg_days']:.0f} days on average in {stage} stage. "
                               f"This is slower than optimal. Consider process improvements.",
                    "action": "Review workflow for this stage"
                })

        # Identify best lead sources
        top_sources = patterns.get("top_lead_sources", [])
        if top_sources:
            best_source = top_sources[0]
            if best_source["close_rate_pct"] > 30:  # Greater than 30% close rate
                recommendations.append({
                    "type": "TOP_SOURCE",
                    "priority": "LOW",
                    "title": f"Strong performance from {best_source['source']}",
                    "message": f"Your {best_source['source']} leads have a {best_source['close_rate_pct']:.0f}% close rate. "
                               f"Consider investing more in this channel.",
                    "action": "Increase focus on top-performing lead sources"
                })

        # Check pipeline health
        pipeline = patterns.get("pipeline_health", {})
        if pipeline:
            win_rate = pipeline.get("win_rate_pct", 0)
            if win_rate < 20:
                recommendations.append({
                    "type": "LOW_WIN_RATE",
                    "priority": "HIGH",
                    "title": "Low win rate detected",
                    "message": f"Your win rate is {win_rate:.0f}%, which is below the target of 20%. "
                               f"Review your qualification process and follow-up cadence.",
                    "action": "Improve lead qualification and follow-up"
                })
            elif win_rate > 50:
                recommendations.append({
                    "type": "HIGH_WIN_RATE",
                    "priority": "LOW",
                    "title": "Excellent win rate!",
                    "message": f"Your win rate is {win_rate:.0f}%, which is excellent. "
                               f"Consider taking on more leads to grow volume.",
                    "action": "Increase lead generation"
                })

        # Sort by priority
        priority_order = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
        recommendations.sort(key=lambda x: priority_order.get(x["priority"], 3))

        return recommendations

    @staticmethod
    def format_patterns_for_claude(patterns: Dict[str, Any]) -> str:
        """
        Format pattern analysis as text for Claude's context.
        """
        if not patterns:
            return ""

        lines = ["\n=== PATTERN ANALYSIS & INSIGHTS ===\n"]

        # Pipeline Health Summary
        pipeline = patterns.get("pipeline_health", {})
        if pipeline:
            lines.append("PIPELINE HEALTH:")
            lines.append(f"  - Active Leads: {pipeline.get('active_leads', 0)}")
            lines.append(f"  - Win Rate: {pipeline.get('win_rate_pct', 0):.1f}%")
            lines.append(f"  - Active Pipeline Value: ${pipeline.get('active_pipeline_value', 0):,.0f}")
            lines.append(f"  - Avg Deal Size: ${pipeline.get('avg_deal_size', 0):,.0f}")

        # Sticking Points
        sticking_points = patterns.get("sticking_points", [])
        if sticking_points:
            lines.append("\nBOTTLENECKS (Stale Leads):")
            for point in sticking_points[:3]:
                lines.append(f"  - {point['stage']}: {point['stuck_count']} stuck (${point['total_value_stuck']:,.0f})")

        # Lead Velocity
        velocity = patterns.get("lead_velocity", {})
        if velocity:
            lines.append("\nLEAD VELOCITY (Avg Days in Stage):")
            for stage, data in sorted(velocity.items(), key=lambda x: x[1].get("avg_days", 0), reverse=True)[:5]:
                lines.append(f"  - {stage}: {data['avg_days']:.0f} days ({data['count']} leads)")

        # Close Rates by Type
        close_rates = patterns.get("close_rates_by_type", {})
        if close_rates:
            lines.append("\nCLOSE RATES BY LOAN TYPE:")
            for loan_type, data in sorted(close_rates.items(), key=lambda x: x[1].get("close_rate_pct", 0), reverse=True):
                lines.append(f"  - {loan_type}: {data['close_rate_pct']:.0f}% ({data['total_leads']} leads)")

        # Top Lead Sources
        sources = patterns.get("top_lead_sources", [])
        if sources:
            lines.append("\nTOP LEAD SOURCES:")
            for source in sources[:3]:
                lines.append(f"  - {source['source']}: {source['close_rate_pct']:.0f}% close rate, "
                           f"{source['total_leads']} leads")

        # Recommendations
        recommendations = patterns.get("recommendations", [])
        if recommendations:
            lines.append("\nAI RECOMMENDATIONS:")
            for rec in recommendations[:3]:
                priority = rec.get("priority", "MEDIUM")
                lines.append(f"  [{priority}] {rec['title']}")
                lines.append(f"     → {rec['message']}")

        lines.append("\n=== END PATTERN ANALYSIS ===")

        return "\n".join(lines)


# Convenience function for direct use
def analyze_patterns(db: Session, user_id: int) -> Dict[str, Any]:
    """Analyze patterns for a user"""
    return PatternAnalyzer.analyze_user_patterns(db, user_id)


def format_patterns(patterns: Dict[str, Any]) -> str:
    """Format patterns for AI context"""
    return PatternAnalyzer.format_patterns_for_claude(patterns)
