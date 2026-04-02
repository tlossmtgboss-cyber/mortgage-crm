"""
Weekly Digest Service for Profitability Intelligence.
Generates and sends automated executive email summaries.
"""

import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import date, datetime, timedelta, timezone
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session

from services.ai_insights_service import AIInsightsService
from services.profitability_service import ProfitabilityService
from sqlalchemy.exc import SQLAlchemyError


class WeeklyDigestService:
    """Service for generating and sending weekly profitability digests."""

    def __init__(self, db: Session, organization_id: int):
        self.db = db
        self.organization_id = organization_id
        self.ai_service = AIInsightsService(db, organization_id)
        self.profitability_service = ProfitabilityService(db, organization_id)

    def generate_digest(self, month: Optional[date] = None) -> Dict[str, Any]:
        """Generate the weekly digest content."""
        if not month:
            month = date.today().replace(day=1)

        # Get AI-generated digest
        digest = self.ai_service.generate_executive_digest(month)

        # Get additional metrics
        metrics = self.profitability_service.get_dashboard_metrics(month)
        recommendations = self.ai_service.generate_smart_recommendations(month)
        anomalies = self.ai_service.detect_anomalies(month)

        return {
            "subject": digest["subject"],
            "content": digest["content"],
            "metrics": metrics,
            "recommendations": recommendations[:3],  # Top 3
            "anomalies": [a for a in anomalies if a.get("severity") in ["critical", "warning"]][:3],
            "generated_at": datetime.now(timezone.utc).isoformat()
        }

    def format_html_email(self, digest: Dict[str, Any]) -> str:
        """Format the digest as HTML email."""
        metrics = digest.get("metrics", {})
        recommendations = digest.get("recommendations", [])
        anomalies = digest.get("anomalies", [])

        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif; line-height: 1.6; color: #333; }}
                .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                .header {{ background: linear-gradient(135deg, #d97757 0%, #c56545 100%); color: white; padding: 20px; border-radius: 8px 8px 0 0; }}
                .header h1 {{ margin: 0; font-size: 24px; }}
                .header p {{ margin: 8px 0 0 0; opacity: 0.9; }}
                .content {{ background: #f8fafc; padding: 20px; }}
                .metrics-grid {{ display: grid; grid-template-columns: repeat(2, 1fr); gap: 12px; margin-bottom: 20px; }}
                .metric-card {{ background: white; padding: 16px; border-radius: 8px; text-align: center; }}
                .metric-value {{ font-size: 24px; font-weight: 700; color: #111827; }}
                .metric-label {{ font-size: 12px; color: #6b7280; text-transform: uppercase; }}
                .section {{ background: white; padding: 16px; border-radius: 8px; margin-bottom: 16px; }}
                .section h3 {{ margin: 0 0 12px 0; font-size: 16px; color: #111827; }}
                .recommendation {{ padding: 12px; background: #f3f4f6; border-radius: 6px; margin-bottom: 8px; border-left: 3px solid #d97757; }}
                .recommendation h4 {{ margin: 0 0 4px 0; font-size: 14px; }}
                .recommendation p {{ margin: 0; font-size: 13px; color: #6b7280; }}
                .alert {{ padding: 12px; border-radius: 6px; margin-bottom: 8px; }}
                .alert.critical {{ background: #fef2f2; border-left: 3px solid #dc2626; }}
                .alert.warning {{ background: #fffbeb; border-left: 3px solid #f59e0b; }}
                .footer {{ text-align: center; padding: 16px; font-size: 12px; color: #9ca3af; }}
                .positive {{ color: #059669; }}
                .negative {{ color: #dc2626; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>Perennia AI Profitability Insights</h1>
                    <p>Week of {date.today().strftime('%B %d, %Y')}</p>
                </div>

                <div class="content">
                    <!-- Key Metrics -->
                    <div class="metrics-grid">
                        <div class="metric-card">
                            <div class="metric-value">${metrics.get('net_profit', 0):,.0f}</div>
                            <div class="metric-label">Net Profit</div>
                        </div>
                        <div class="metric-card">
                            <div class="metric-value">{metrics.get('profit_margin', 0):.1f}%</div>
                            <div class="metric-label">Profit Margin</div>
                        </div>
                        <div class="metric-card">
                            <div class="metric-value">${metrics.get('cost_per_loan', 0):,.0f}</div>
                            <div class="metric-label">Cost Per Loan</div>
                        </div>
                        <div class="metric-card">
                            <div class="metric-value">{metrics.get('loans_closed', 0)}</div>
                            <div class="metric-label">Loans Closed</div>
                        </div>
                    </div>

                    <!-- Alerts -->
                    {self._format_alerts_html(anomalies)}

                    <!-- AI Insights -->
                    <div class="section">
                        <h3>AI Insights</h3>
                        <div style="white-space: pre-wrap; font-size: 13px;">
{digest.get('content', 'No insights available.')}
                        </div>
                    </div>

                    <!-- Top Recommendations -->
                    {self._format_recommendations_html(recommendations)}
                </div>

                <div class="footer">
                    <p>Generated by Perennia AI AI | {datetime.now().strftime('%B %d, %Y at %I:%M %p')}</p>
                    <p><a href="https://perenniaai.com/profitability">View Full Dashboard</a></p>
                </div>
            </div>
        </body>
        </html>
        """
        return html

    def _format_alerts_html(self, anomalies: List[Dict]) -> str:
        """Format anomalies as HTML alerts."""
        if not anomalies:
            return ""

        alerts_html = '<div class="section"><h3>Alerts</h3>'
        for anomaly in anomalies:
            severity = anomaly.get("severity", "warning")
            alerts_html += f'''
                <div class="alert {severity}">
                    <strong>{anomaly.get("type", "Alert")}</strong>
                    <p>{anomaly.get("description", "")}</p>
                </div>
            '''
        alerts_html += '</div>'
        return alerts_html

    def _format_recommendations_html(self, recommendations: List[Dict]) -> str:
        """Format recommendations as HTML."""
        if not recommendations:
            return ""

        rec_html = '<div class="section"><h3>Top Recommendations</h3>'
        for rec in recommendations:
            rec_html += f'''
                <div class="recommendation">
                    <h4>{rec.get("title", "Recommendation")}</h4>
                    <p>{rec.get("action", "")}</p>
                    <p><strong>Impact:</strong> {rec.get("impact", "")}</p>
                </div>
            '''
        rec_html += '</div>'
        return rec_html

    def send_digest(
        self,
        recipients: List[str],
        digest: Optional[Dict[str, Any]] = None,
        month: Optional[date] = None
    ) -> Dict[str, Any]:
        """Send the weekly digest email to recipients."""
        if not digest:
            digest = self.generate_digest(month)

        html_content = self.format_html_email(digest)

        # Email configuration
        smtp_server = os.getenv("SMTP_SERVER", "smtp.gmail.com")
        smtp_port = int(os.getenv("SMTP_PORT", "587"))
        smtp_user = os.getenv("SMTP_USER")
        smtp_password = os.getenv("SMTP_PASSWORD")
        from_email = os.getenv("FROM_EMAIL", smtp_user)

        if not smtp_user or not smtp_password:
            return {
                "status": "error",
                "message": "SMTP credentials not configured",
                "digest": digest
            }

        # Create message
        msg = MIMEMultipart('alternative')
        msg['Subject'] = digest["subject"]
        msg['From'] = from_email
        msg['To'] = ", ".join(recipients)

        # Attach HTML content
        html_part = MIMEText(html_content, 'html')
        msg.attach(html_part)

        # Send email
        try:
            with smtplib.SMTP(smtp_server, smtp_port) as server:
                server.starttls()
                server.login(smtp_user, smtp_password)
                server.sendmail(from_email, recipients, msg.as_string())

            return {
                "status": "sent",
                "recipients": recipients,
                "subject": digest["subject"],
                "sent_at": datetime.now(timezone.utc).isoformat()
            }
        except Exception as e:
            return {
                "status": "error",
                "message": "Internal server error",
                "digest": digest
            }

    def schedule_weekly_digest(
        self,
        recipients: List[str],
        day_of_week: int = 0,  # 0 = Monday
        hour: int = 8
    ) -> Dict[str, Any]:
        """
        Get scheduling information for the weekly digest.
        Note: Actual scheduling should be done via cron job or task scheduler.
        """
        return {
            "schedule": {
                "day_of_week": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"][day_of_week],
                "hour": f"{hour:02d}:00",
                "timezone": "UTC"
            },
            "recipients": recipients,
            "cron_expression": f"0 {hour} * * {day_of_week}",
            "next_run": self._get_next_run_date(day_of_week, hour).isoformat()
        }

    def _get_next_run_date(self, day_of_week: int, hour: int) -> datetime:
        """Calculate the next run date for the digest."""
        now = datetime.now(timezone.utc)
        days_ahead = day_of_week - now.weekday()
        if days_ahead <= 0:  # Target day already happened this week
            days_ahead += 7
        next_date = now + timedelta(days=days_ahead)
        return next_date.replace(hour=hour, minute=0, second=0, microsecond=0)
