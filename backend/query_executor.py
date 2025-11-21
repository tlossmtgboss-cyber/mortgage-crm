"""
Query Executor - Executes dynamic analytical queries for AI
Allows AI to answer complex questions about pipeline, performance, and trends
"""
import logging
from typing import Dict, Any, List
from sqlalchemy.orm import Session
from sqlalchemy import text
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class QueryExecutor:
    """
    Executes predefined analytical queries based on AI requests
    All queries are parameterized and safe from SQL injection
    """

    @staticmethod
    def execute_query(
        db: Session,
        query_type: str,
        params: Dict[str, Any],
        user_id: int
    ) -> Dict[str, Any]:
        """
        Execute a predefined query with parameters

        Args:
            db: Database session
            query_type: Type of query to execute
            params: Query parameters
            user_id: User making the request
        """
        try:
            db.rollback()  # Clear any failed transactions
        except:
            pass

        logger.info(f"Executing {query_type} for user {user_id} with params {params}")

        # Route to appropriate query method
        query_methods = {
            "pipeline_analysis": QueryExecutor._query_pipeline_analysis,
            "lead_source_performance": QueryExecutor._query_lead_source_performance,
            "conversion_funnel": QueryExecutor._query_conversion_funnel,
            "loan_type_performance": QueryExecutor._query_loan_type_performance,
            "monthly_trends": QueryExecutor._query_monthly_trends,
            "stale_leads_report": QueryExecutor._query_stale_leads,
            "high_value_opportunities": QueryExecutor._query_high_value_opportunities,
            "activity_summary": QueryExecutor._query_activity_summary,
        }

        query_func = query_methods.get(query_type)
        if not query_func:
            raise ValueError(f"Unknown query type: {query_type}")

        try:
            result = query_func(db, params, user_id)
            return {
                "success": True,
                "query_type": query_type,
                "data": result,
                "count": len(result) if isinstance(result, list) else 1
            }
        except Exception as e:
            logger.error(f"Query execution error: {e}")
            try:
                db.rollback()
            except:
                pass
            return {
                "success": False,
                "error": str(e),
                "query_type": query_type
            }

    @staticmethod
    def _query_pipeline_analysis(db: Session, params: Dict, user_id: int) -> List[Dict]:
        """Detailed pipeline analysis by stage"""
        result = db.execute(text("""
            SELECT
                stage,
                COUNT(*) as lead_count,
                COALESCE(SUM(preapproval_amount), 0) as total_value,
                COALESCE(AVG(preapproval_amount), 0) as avg_loan_amount,
                ROUND(AVG(EXTRACT(EPOCH FROM (NOW() - created_at))/86400)::numeric, 1) as avg_age_days
            FROM leads
            WHERE owner_id = :user_id
            GROUP BY stage
            ORDER BY total_value DESC
        """), {"user_id": user_id})

        return [
            {
                "stage": str(row[0]) if row[0] else "Unknown",
                "lead_count": row[1],
                "total_value": float(row[2]),
                "avg_loan_amount": float(row[3]),
                "avg_age_days": float(row[4]) if row[4] else 0
            }
            for row in result
        ]

    @staticmethod
    def _query_lead_source_performance(db: Session, params: Dict, user_id: int) -> List[Dict]:
        """Analyze performance by lead source"""
        date_range = params.get("date_range_days", 90)

        result = db.execute(text("""
            SELECT
                COALESCE(source, 'Unknown') as source,
                COUNT(*) as total_leads,
                0 as closed_won,
                ROUND(
                    (0::numeric /
                     NULLIF(COUNT(*), 0) * 100), 1
                ) as close_rate_pct,
                0 as total_revenue,
                0 as avg_deal_size
            FROM leads
            WHERE owner_id = :user_id
            AND created_at > NOW() - INTERVAL :date_range
            GROUP BY source
            HAVING COUNT(*) >= 2
            ORDER BY total_revenue DESC
        """), {"user_id": user_id, "date_range": f"{date_range} days"})

        return [
            {
                "source": row[0],
                "total_leads": row[1],
                "closed_won": row[2],
                "close_rate_pct": float(row[3]) if row[3] else 0,
                "total_revenue": float(row[4]),
                "avg_deal_size": float(row[5])
            }
            for row in result
        ]

    @staticmethod
    def _query_conversion_funnel(db: Session, params: Dict, user_id: int) -> List[Dict]:
        """Analyze conversion rates through pipeline stages"""
        result = db.execute(text("""
            WITH stage_counts AS (
                SELECT
                    COUNT(*) FILTER (WHERE stage IN ('New', 'Prospect', 'Application Started', 'Pre-Approved', 'Pre-Approved')) as total_leads,
                    COUNT(*) FILTER (WHERE stage IN ('Prospect', 'Application Started', 'Pre-Approved', 'Pre-Approved')) as reached_prospect,
                    COUNT(*) FILTER (WHERE stage IN ('Application Started', 'Pre-Approved', 'Pre-Approved')) as reached_application,
                    COUNT(*) FILTER (WHERE stage IN ('Pre-Approved', 'Pre-Approved')) as reached_preapproved,
                    0 as closed_won
                FROM leads
                WHERE owner_id = :user_id
            )
            SELECT * FROM stage_counts
        """), {"user_id": user_id})

        row = result.fetchone()
        if not row:
            return []

        total = row[0] or 1
        return [
            {"stage": "New → Prospect", "count": row[1], "rate_pct": round(row[1] / total * 100, 1)},
            {"stage": "Prospect → Application", "count": row[2], "rate_pct": round(row[2] / max(row[1], 1) * 100, 1)},
            {"stage": "Application → Pre-Approved", "count": row[3], "rate_pct": round(row[3] / max(row[2], 1) * 100, 1)},
            {"stage": "Pre-Approved → CLOSED_WON", "count": row[4], "rate_pct": round(row[4] / max(row[3], 1) * 100, 1)},
        ]

    @staticmethod
    def _query_loan_type_performance(db: Session, params: Dict, user_id: int) -> List[Dict]:
        """Performance breakdown by loan type"""
        result = db.execute(text("""
            SELECT
                COALESCE(loan_type, 'Unknown') as loan_type,
                COUNT(*) as total_leads,
                0 as closed_won,
                0 as closed_lost,
                ROUND(
                    (0::numeric /
                     NULLIF(COUNT(*) FILTER (WHERE stage IN ('Pre-Approved', 'New')), 0) * 100), 1
                ) as win_rate_pct,
                COALESCE(SUM(preapproval_amount), 0) as total_volume,
                COALESCE(AVG(preapproval_amount), 0) as avg_loan_amount
            FROM leads
            WHERE owner_id = :user_id
            GROUP BY loan_type
            ORDER BY total_volume DESC
        """), {"user_id": user_id})

        return [
            {
                "loan_type": row[0],
                "total_leads": row[1],
                "closed_won": row[2],
                "closed_lost": row[3],
                "win_rate_pct": float(row[4]) if row[4] else 0,
                "total_volume": float(row[5]),
                "avg_loan_amount": float(row[6])
            }
            for row in result
        ]

    @staticmethod
    def _query_monthly_trends(db: Session, params: Dict, user_id: int) -> List[Dict]:
        """Monthly trends for leads and closings"""
        months = params.get("months", 6)

        result = db.execute(text("""
            SELECT
                TO_CHAR(DATE_TRUNC('month', created_at), 'YYYY-MM') as month,
                COUNT(*) as new_leads,
                0 as closed_won,
                0 as revenue
            FROM leads
            WHERE owner_id = :user_id
            AND created_at > NOW() - INTERVAL :months
            GROUP BY DATE_TRUNC('month', created_at)
            ORDER BY month DESC
        """), {"user_id": user_id, "months": f"{months} months"})

        return [
            {
                "month": row[0],
                "new_leads": row[1],
                "closed_won": row[2],
                "revenue": float(row[3])
            }
            for row in result
        ]

    @staticmethod
    def _query_stale_leads(db: Session, params: Dict, user_id: int) -> List[Dict]:
        """Find stale leads that need attention"""
        stale_days = params.get("stale_days", 14)
        limit = params.get("limit", 20)

        result = db.execute(text("""
            SELECT
                id,
                name,
                stage,
                loan_type,
                preapproval_amount,
                created_at,
                ROUND(EXTRACT(EPOCH FROM (NOW() - created_at))/86400) as days_since_created
            FROM leads
            WHERE owner_id = :user_id
            
            AND created_at < NOW() - INTERVAL :stale_days
            ORDER BY created_at ASC
            LIMIT :limit
        """), {"user_id": user_id, "stale_days": f"{stale_days} days", "limit": limit})

        return [
            {
                "id": row[0],
                "name": row[1],
                "stage": str(row[2]) if row[2] else "Unknown",
                "loan_type": row[3],
                "loan_amount": float(row[4]) if row[4] else 0,
                "created_at": row[5].isoformat() if row[5] else None,
                "days_stale": int(row[6]) if row[6] else 0
            }
            for row in result
        ]

    @staticmethod
    def _query_high_value_opportunities(db: Session, params: Dict, user_id: int) -> List[Dict]:
        """Find high-value leads in pipeline"""
        min_amount = params.get("min_amount", 500000)
        limit = params.get("limit", 20)

        result = db.execute(text("""
            SELECT
                id,
                name,
                stage,
                loan_type,
                preapproval_amount,
                email,
                phone,
                created_at
            FROM leads
            WHERE owner_id = :user_id
            
            AND preapproval_amount >= :min_amount
            ORDER BY preapproval_amount DESC
            LIMIT :limit
        """), {"user_id": user_id, "min_amount": min_amount, "limit": limit})

        return [
            {
                "id": row[0],
                "name": row[1],
                "stage": str(row[2]) if row[2] else "Unknown",
                "loan_type": row[3],
                "loan_amount": float(row[4]) if row[4] else 0,
                "email": row[5],
                "phone": row[6],
                "created_at": row[7].isoformat() if row[7] else None
            }
            for row in result
        ]

    @staticmethod
    def _query_activity_summary(db: Session, params: Dict, user_id: int) -> List[Dict]:
        """Summary of recent activities"""
        days = params.get("days", 30)

        result = db.execute(text("""
            SELECT
                activity_type,
                COUNT(*) as count,
                COUNT(DISTINCT lead_id) as unique_leads
            FROM activities
            WHERE user_id = :user_id
            AND created_at > NOW() - INTERVAL :days
            GROUP BY activity_type
            ORDER BY count DESC
        """), {"user_id": user_id, "days": f"{days} days"})

        return [
            {
                "activity_type": row[0],
                "count": row[1],
                "unique_leads": row[2]
            }
            for row in result
        ]

    @staticmethod
    def format_query_results_for_claude(query_type: str, result: Dict[str, Any]) -> str:
        """Format query results as text for Claude"""
        if not result.get("success"):
            return f"Query failed: {result.get('error', 'Unknown error')}"

        data = result.get("data", [])
        if not data:
            return f"No data found for {query_type}"

        lines = [f"\n=== {query_type.upper().replace('_', ' ')} RESULTS ===\n"]

        if query_type == "pipeline_analysis":
            lines.append("Pipeline by Stage:")
            for item in data:
                lines.append(f"  {item['stage']}: {item['lead_count']} leads, "
                           f"${item['total_value']:,.0f} total, "
                           f"avg {item['avg_age_days']:.0f} days old")

        elif query_type == "lead_source_performance":
            lines.append("Lead Source Performance:")
            for item in data:
                lines.append(f"  {item['source']}: {item['total_leads']} leads, "
                           f"{item['close_rate_pct']:.1f}% close rate, "
                           f"${item['total_revenue']:,.0f} revenue")

        elif query_type == "conversion_funnel":
            lines.append("Conversion Funnel:")
            for item in data:
                lines.append(f"  {item['stage']}: {item['count']} leads ({item['rate_pct']:.1f}%)")

        elif query_type == "loan_type_performance":
            lines.append("Performance by Loan Type:")
            for item in data:
                lines.append(f"  {item['loan_type']}: {item['total_leads']} leads, "
                           f"{item['win_rate_pct']:.1f}% win rate, "
                           f"${item['total_volume']:,.0f} volume")

        elif query_type == "monthly_trends":
            lines.append("Monthly Trends:")
            for item in data:
                lines.append(f"  {item['month']}: {item['new_leads']} new, "
                           f"{item['closed_won']} closed, "
                           f"${item['revenue']:,.0f} revenue")

        elif query_type == "stale_leads_report":
            lines.append(f"Stale Leads ({len(data)} found):")
            for item in data[:10]:
                lines.append(f"  {item['name']} ({item['stage']}): "
                           f"${item['loan_amount']:,.0f}, "
                           f"{item['days_stale']} days stale")

        elif query_type == "high_value_opportunities":
            lines.append(f"High Value Opportunities ({len(data)} found):")
            for item in data[:10]:
                lines.append(f"  {item['name']}: ${item['loan_amount']:,.0f} "
                           f"({item['loan_type']}, {item['stage']})")

        else:
            # Generic formatting
            lines.append(f"Results ({len(data)} records):")
            for item in data[:10]:
                lines.append(f"  {item}")

        lines.append("\n=== END QUERY RESULTS ===")
        return "\n".join(lines)


# Convenience function
def execute_query(db: Session, query_type: str, params: Dict, user_id: int) -> Dict:
    """Execute a query"""
    return QueryExecutor.execute_query(db, query_type, params, user_id)


def format_results(query_type: str, result: Dict) -> str:
    """Format results for AI"""
    return QueryExecutor.format_query_results_for_claude(query_type, result)
