"""
Manager Dashboard Service - Aggregates team performance and intelligence data

Provides insights for managers including:
- Team performance overview
- Coaching priorities across team
- Compliance monitoring
- Competitive intelligence aggregation
- Best practices identification
"""

from datetime import datetime, timedelta, timezone
from typing import Dict, Any, List, Optional
from sqlalchemy import func, desc, and_
from sqlalchemy.orm import Session
from collections import defaultdict


class ManagerDashboardService:
    """Service for aggregating manager-level analytics and intelligence"""

    def __init__(self, db: Session, models: Dict[str, Any]):
        self.db = db
        self.models = models

    async def get_team_overview(
        self,
        team_member_ids: List[int],
        days: int = 30
    ) -> Dict[str, Any]:
        """Get comprehensive team performance overview"""

        cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)

        ParticipantAnalytics = self.models.get("ParticipantAnalytics")
        CoachingRecommendation = self.models.get("CoachingRecommendation")
        MortgageIntelligence = self.models.get("MortgageIntelligence")
        MeetingRecording = self.models.get("MeetingRecording")
        MeetingParticipant = self.models.get("MeetingParticipant")

        if not all([ParticipantAnalytics, MeetingRecording, MeetingParticipant]):
            return {"error": "Required models not available"}

        # Get all analytics for team members in date range
        analytics_query = (
            self.db.query(ParticipantAnalytics)
            .join(MeetingParticipant, ParticipantAnalytics.participant_id == MeetingParticipant.id)
            .filter(
                MeetingParticipant.user_id.in_(team_member_ids),
                ParticipantAnalytics.created_at >= cutoff_date
            )
        )

        team_analytics = analytics_query.all()

        # Calculate team averages
        team_averages = self._calculate_team_averages(team_analytics)

        # Get performance distribution
        performance_distribution = self._calculate_performance_distribution(team_analytics)

        # Identify top performers
        top_performers = await self._identify_top_performers(
            team_member_ids, team_analytics, days
        )

        # Get coaching priorities
        coaching_priorities = []
        if CoachingRecommendation:
            coaching_priorities = await self._aggregate_coaching_priorities(
                team_analytics, CoachingRecommendation
            )

        # Get compliance summary
        compliance_summary = {"total_risks": 0, "high_severity": 0, "risk_types": {}}
        if MortgageIntelligence:
            compliance_summary = await self._get_compliance_summary(
                team_member_ids, cutoff_date, MortgageIntelligence, MeetingRecording
            )

        # Get competitor landscape
        competitor_landscape = {}
        if MortgageIntelligence:
            competitor_landscape = await self._get_competitor_landscape(
                team_member_ids, cutoff_date, MortgageIntelligence, MeetingRecording
            )

        # Get concern trends
        concern_trends = {}
        if MortgageIntelligence:
            concern_trends = await self._get_concern_trends(
                team_member_ids, cutoff_date, MortgageIntelligence, MeetingRecording
            )

        # Identify best practices
        best_practices = await self._identify_best_practices(team_analytics)

        return {
            "period": {
                "days": days,
                "start_date": cutoff_date.isoformat(),
                "end_date": datetime.now(timezone.utc).isoformat()
            },
            "team_size": len(team_member_ids),
            "total_recordings_analyzed": len(set(a.recording_id for a in team_analytics)),
            "team_averages": team_averages,
            "performance_distribution": performance_distribution,
            "top_performers": top_performers,
            "coaching_priorities": coaching_priorities,
            "compliance_summary": compliance_summary,
            "competitor_landscape": competitor_landscape,
            "concern_trends": concern_trends,
            "best_practices": best_practices
        }

    def _calculate_team_averages(
        self,
        analytics: List[Any]
    ) -> Dict[str, float]:
        """Calculate average metrics across the team"""

        if not analytics:
            return {
                "talk_listen_ratio": 0,
                "engagement_score": 0,
                "question_rate": 0,
                "interruption_rate": 0,
                "positive_sentiment": 0,
                "speaking_pace": 0
            }

        total = len(analytics)

        return {
            "talk_listen_ratio": sum(a.talk_listen_ratio or 0 for a in analytics) / total,
            "engagement_score": sum(a.engagement_score or 0 for a in analytics) / total,
            "question_rate": sum(a.question_count or 0 for a in analytics) / total,
            "interruption_rate": sum(a.interruption_count or 0 for a in analytics) / total,
            "positive_sentiment": sum(a.sentiment_positive_pct or 0 for a in analytics) / total,
            "speaking_pace": sum(a.speaking_pace_wpm or 0 for a in analytics) / total
        }

    def _calculate_performance_distribution(
        self,
        analytics: List[Any]
    ) -> Dict[str, int]:
        """Categorize team members by performance tier"""

        distribution = {
            "excellent": 0,
            "good": 0,
            "needs_improvement": 0,
            "critical": 0
        }

        for a in analytics:
            score = a.engagement_score or 0
            if score >= 0.8:
                distribution["excellent"] += 1
            elif score >= 0.6:
                distribution["good"] += 1
            elif score >= 0.4:
                distribution["needs_improvement"] += 1
            else:
                distribution["critical"] += 1

        return distribution

    async def _identify_top_performers(
        self,
        team_member_ids: List[int],
        analytics: List[Any],
        days: int
    ) -> List[Dict[str, Any]]:
        """Identify top performers based on multiple metrics"""

        MeetingParticipant = self.models.get("MeetingParticipant")
        if not MeetingParticipant:
            return []

        # Group analytics by user
        user_analytics = defaultdict(list)
        for a in analytics:
            participant = self.db.query(MeetingParticipant).filter(
                MeetingParticipant.id == a.participant_id
            ).first()
            if participant and participant.user_id:
                user_analytics[participant.user_id].append(a)

        # Calculate composite scores for each user
        user_scores = []
        for user_id, user_data in user_analytics.items():
            if not user_data:
                continue

            avg_engagement = sum(a.engagement_score or 0 for a in user_data) / len(user_data)
            avg_questions = sum(a.question_count or 0 for a in user_data) / len(user_data)
            avg_sentiment = sum(a.sentiment_positive_pct or 0 for a in user_data) / len(user_data)

            # Composite score weighted by engagement (50%), questions (25%), sentiment (25%)
            composite = (avg_engagement * 0.5) + (avg_questions * 0.025) + (avg_sentiment * 0.25)

            user_scores.append({
                "user_id": user_id,
                "recordings_analyzed": len(user_data),
                "avg_engagement": round(avg_engagement, 3),
                "avg_questions_per_call": round(avg_questions, 1),
                "avg_positive_sentiment": round(avg_sentiment, 3),
                "composite_score": round(composite, 3)
            })

        # Sort by composite score and return top 5
        user_scores.sort(key=lambda x: x["composite_score"], reverse=True)
        return user_scores[:5]

    async def _aggregate_coaching_priorities(
        self,
        analytics: List[Any],
        CoachingRecommendation: Any
    ) -> List[Dict[str, Any]]:
        """Aggregate coaching needs across the team"""

        analytics_ids = [a.id for a in analytics]

        if not analytics_ids:
            return []

        # Get all coaching recommendations for these analytics
        recommendations = (
            self.db.query(CoachingRecommendation)
            .filter(
                CoachingRecommendation.analytics_id.in_(analytics_ids),
                CoachingRecommendation.is_acknowledged == False
            )
            .all()
        )

        # Aggregate by category
        category_counts = defaultdict(lambda: {"count": 0, "high_priority": 0, "examples": []})

        for rec in recommendations:
            cat = rec.category
            category_counts[cat]["count"] += 1
            if rec.priority == "high":
                category_counts[cat]["high_priority"] += 1
            if len(category_counts[cat]["examples"]) < 2:
                category_counts[cat]["examples"].append(rec.recommendation)

        # Convert to sorted list
        priorities = [
            {
                "category": cat,
                "team_members_affected": data["count"],
                "high_priority_count": data["high_priority"],
                "example_recommendations": data["examples"]
            }
            for cat, data in category_counts.items()
        ]

        priorities.sort(key=lambda x: (x["high_priority_count"], x["team_members_affected"]), reverse=True)
        return priorities[:10]

    async def _get_compliance_summary(
        self,
        team_member_ids: List[int],
        cutoff_date: datetime,
        MortgageIntelligence: Any,
        MeetingRecording: Any
    ) -> Dict[str, Any]:
        """Summarize compliance risks across team"""

        # Get all intelligence records for team in date range
        intelligence_records = (
            self.db.query(MortgageIntelligence)
            .join(MeetingRecording, MortgageIntelligence.recording_id == MeetingRecording.id)
            .filter(
                MeetingRecording.user_id.in_(team_member_ids),
                MortgageIntelligence.created_at >= cutoff_date
            )
            .all()
        )

        total_risks = 0
        high_severity = 0
        risk_types = defaultdict(int)
        recent_incidents = []

        for intel in intelligence_records:
            if intel.compliance_risks:
                for risk in intel.compliance_risks:
                    total_risks += 1
                    risk_types[risk.get("risk_type", "unknown")] += 1

                    if risk.get("severity") in ["high", "critical"]:
                        high_severity += 1
                        if len(recent_incidents) < 5:
                            recent_incidents.append({
                                "recording_id": intel.recording_id,
                                "risk_type": risk.get("risk_type"),
                                "severity": risk.get("severity"),
                                "context": risk.get("context", "")[:100],
                                "timestamp": risk.get("timestamp")
                            })

        return {
            "total_risks": total_risks,
            "high_severity": high_severity,
            "risk_types": dict(risk_types),
            "recent_high_severity_incidents": recent_incidents,
            "recordings_with_risks": len([i for i in intelligence_records if i.compliance_risks])
        }

    async def _get_competitor_landscape(
        self,
        team_member_ids: List[int],
        cutoff_date: datetime,
        MortgageIntelligence: Any,
        MeetingRecording: Any
    ) -> Dict[str, Any]:
        """Aggregate competitor mentions across team"""

        intelligence_records = (
            self.db.query(MortgageIntelligence)
            .join(MeetingRecording, MortgageIntelligence.recording_id == MeetingRecording.id)
            .filter(
                MeetingRecording.user_id.in_(team_member_ids),
                MortgageIntelligence.created_at >= cutoff_date
            )
            .all()
        )

        competitor_totals = defaultdict(int)
        competitor_contexts = defaultdict(list)

        for intel in intelligence_records:
            if intel.competitor_mentions and intel.competitor_mentions.get("summary"):
                for competitor, data in intel.competitor_mentions["summary"].items():
                    competitor_totals[competitor] += data.get("count", 0)
                    if data.get("contexts"):
                        competitor_contexts[competitor].extend(data["contexts"][:2])

        # Build ranked list
        ranked = [
            {
                "competitor": comp,
                "total_mentions": count,
                "sample_contexts": competitor_contexts[comp][:3]
            }
            for comp, count in competitor_totals.items()
        ]
        ranked.sort(key=lambda x: x["total_mentions"], reverse=True)

        return {
            "total_competitor_mentions": sum(competitor_totals.values()),
            "unique_competitors": len(competitor_totals),
            "top_competitors": ranked[:10]
        }

    async def _get_concern_trends(
        self,
        team_member_ids: List[int],
        cutoff_date: datetime,
        MortgageIntelligence: Any,
        MeetingRecording: Any
    ) -> Dict[str, Any]:
        """Identify trending borrower concerns across team"""

        intelligence_records = (
            self.db.query(MortgageIntelligence)
            .join(MeetingRecording, MortgageIntelligence.recording_id == MeetingRecording.id)
            .filter(
                MeetingRecording.user_id.in_(team_member_ids),
                MortgageIntelligence.created_at >= cutoff_date
            )
            .all()
        )

        concern_counts = defaultdict(int)
        concern_severities = defaultdict(lambda: {"high": 0, "medium": 0, "low": 0})

        for intel in intelligence_records:
            if intel.borrower_concerns:
                for concern in intel.borrower_concerns:
                    concern_type = concern.get("concern_type", "unknown")
                    concern_counts[concern_type] += 1
                    severity = concern.get("severity", "medium")
                    concern_severities[concern_type][severity] += 1

        # Build trending concerns list
        trends = [
            {
                "concern_type": concern_type,
                "total_occurrences": count,
                "severity_breakdown": dict(concern_severities[concern_type])
            }
            for concern_type, count in concern_counts.items()
        ]
        trends.sort(key=lambda x: x["total_occurrences"], reverse=True)

        return {
            "total_concerns_detected": sum(concern_counts.values()),
            "trending_concerns": trends[:10]
        }

    async def _identify_best_practices(
        self,
        analytics: List[Any]
    ) -> List[Dict[str, Any]]:
        """Identify best practices from top performing calls"""

        best_practices = []

        # Find calls with high engagement
        high_engagement = [a for a in analytics if (a.engagement_score or 0) >= 0.8]
        if high_engagement:
            avg_questions = sum(a.question_count or 0 for a in high_engagement) / len(high_engagement)
            avg_ratio = sum(a.talk_listen_ratio or 0 for a in high_engagement) / len(high_engagement)

            best_practices.append({
                "practice": "High Engagement Calls",
                "metric": f"{len(high_engagement)} calls with 80%+ engagement",
                "insight": f"These calls average {avg_questions:.1f} questions and {avg_ratio:.2f} talk-listen ratio"
            })

        # Find calls with optimal talk-listen ratio
        balanced_calls = [a for a in analytics if 0.4 <= (a.talk_listen_ratio or 0) <= 0.6]
        if balanced_calls:
            avg_engagement = sum(a.engagement_score or 0 for a in balanced_calls) / len(balanced_calls)
            best_practices.append({
                "practice": "Balanced Conversations",
                "metric": f"{len(balanced_calls)} calls with 40-60% talk ratio",
                "insight": f"Balanced calls show {avg_engagement*100:.0f}% average engagement"
            })

        # Find calls with high question counts
        high_question_calls = [a for a in analytics if (a.question_count or 0) >= 10]
        if high_question_calls:
            avg_sentiment = sum(a.sentiment_positive_pct or 0 for a in high_question_calls) / len(high_question_calls)
            best_practices.append({
                "practice": "Discovery-Focused Calls",
                "metric": f"{len(high_question_calls)} calls with 10+ questions",
                "insight": f"High-question calls show {avg_sentiment*100:.0f}% positive sentiment"
            })

        # Find calls with high positive sentiment
        positive_calls = [a for a in analytics if (a.sentiment_positive_pct or 0) >= 0.6]
        if positive_calls:
            avg_engagement = sum(a.engagement_score or 0 for a in positive_calls) / len(positive_calls)
            best_practices.append({
                "practice": "Positive Client Interactions",
                "metric": f"{len(positive_calls)} calls with 60%+ positive sentiment",
                "insight": f"Positive calls achieve {avg_engagement*100:.0f}% engagement scores"
            })

        return best_practices

    async def get_individual_comparison(
        self,
        user_id: int,
        team_member_ids: List[int],
        days: int = 30
    ) -> Dict[str, Any]:
        """Compare individual performance against team averages"""

        cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)

        ParticipantAnalytics = self.models.get("ParticipantAnalytics")
        MeetingParticipant = self.models.get("MeetingParticipant")

        if not all([ParticipantAnalytics, MeetingParticipant]):
            return {"error": "Required models not available"}

        # Get individual analytics
        individual_analytics = (
            self.db.query(ParticipantAnalytics)
            .join(MeetingParticipant, ParticipantAnalytics.participant_id == MeetingParticipant.id)
            .filter(
                MeetingParticipant.user_id == user_id,
                ParticipantAnalytics.created_at >= cutoff_date
            )
            .all()
        )

        # Get team analytics (excluding individual)
        team_analytics = (
            self.db.query(ParticipantAnalytics)
            .join(MeetingParticipant, ParticipantAnalytics.participant_id == MeetingParticipant.id)
            .filter(
                MeetingParticipant.user_id.in_([m for m in team_member_ids if m != user_id]),
                ParticipantAnalytics.created_at >= cutoff_date
            )
            .all()
        )

        individual_avg = self._calculate_team_averages(individual_analytics)
        team_avg = self._calculate_team_averages(team_analytics)

        # Calculate deltas
        comparison = {}
        for metric in individual_avg:
            ind_val = individual_avg[metric]
            team_val = team_avg[metric]
            delta = ind_val - team_val if team_val else 0

            comparison[metric] = {
                "individual": round(ind_val, 3),
                "team_average": round(team_val, 3),
                "delta": round(delta, 3),
                "percentile": self._calculate_percentile(ind_val, [getattr(a, metric.replace('_', '_'), 0) or 0 for a in team_analytics])
            }

        return {
            "user_id": user_id,
            "period_days": days,
            "recordings_analyzed": len(individual_analytics),
            "comparison": comparison
        }

    def _calculate_percentile(self, value: float, all_values: List[float]) -> int:
        """Calculate percentile rank for a value"""
        if not all_values:
            return 50

        count_below = sum(1 for v in all_values if v < value)
        return int((count_below / len(all_values)) * 100)

    async def get_leaderboard(
        self,
        team_member_ids: List[int],
        days: int = 30,
        metric: str = "engagement_score"
    ) -> List[Dict[str, Any]]:
        """Get team leaderboard for specific metric"""

        cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)

        ParticipantAnalytics = self.models.get("ParticipantAnalytics")
        MeetingParticipant = self.models.get("MeetingParticipant")

        if not all([ParticipantAnalytics, MeetingParticipant]):
            return []

        # Get all analytics grouped by user
        analytics = (
            self.db.query(ParticipantAnalytics)
            .join(MeetingParticipant, ParticipantAnalytics.participant_id == MeetingParticipant.id)
            .filter(
                MeetingParticipant.user_id.in_(team_member_ids),
                ParticipantAnalytics.created_at >= cutoff_date
            )
            .all()
        )

        # Group by user and calculate averages
        user_data = defaultdict(list)
        for a in analytics:
            participant = self.db.query(MeetingParticipant).filter(
                MeetingParticipant.id == a.participant_id
            ).first()
            if participant and participant.user_id:
                user_data[participant.user_id].append(a)

        # Calculate metric averages
        leaderboard = []
        for user_id, user_analytics in user_data.items():
            if metric == "engagement_score":
                avg = sum(a.engagement_score or 0 for a in user_analytics) / len(user_analytics)
            elif metric == "question_count":
                avg = sum(a.question_count or 0 for a in user_analytics) / len(user_analytics)
            elif metric == "positive_sentiment":
                avg = sum(a.sentiment_positive_pct or 0 for a in user_analytics) / len(user_analytics)
            elif metric == "talk_listen_ratio":
                avg = sum(a.talk_listen_ratio or 0 for a in user_analytics) / len(user_analytics)
            else:
                avg = 0

            leaderboard.append({
                "user_id": user_id,
                "metric_value": round(avg, 3),
                "recordings_analyzed": len(user_analytics)
            })

        leaderboard.sort(key=lambda x: x["metric_value"], reverse=True)

        # Add rank
        for idx, entry in enumerate(leaderboard):
            entry["rank"] = idx + 1

        return leaderboard


def get_manager_dashboard_service(db: Session, models: Dict[str, Any]) -> ManagerDashboardService:
    """Factory function to create ManagerDashboardService instance"""
    return ManagerDashboardService(db, models)
