"""
Smart Docs Communication Analytics Service

Tracks and analyzes all document-related communications with borrowers.
Provides metrics on collection velocity, borrower engagement, channel
performance, LO/processor productivity, funnel analysis, cohort
comparisons, anomaly detection, and CSV report generation.

Data sources:
    - document_followup_events: outbound/inbound communication events
    - document_followup_campaigns: campaign lifecycle and progression
    - smart_document_requests: document request SLA and status
    - smart_documents: uploaded documents with review decisions
    - loans: loan context (stage, LO, org)

Usage:
    from services.smart_docs.communication_analytics_service import (
        CommunicationAnalyticsService,
        get_communication_analytics_service,
    )

    svc = get_communication_analytics_service(db, org_id=42)
    velocity = await svc.get_collection_velocity()
    engagement = await svc.get_borrower_engagement(borrower_id=7)
    report_csv = await svc.export_report("channel_performance", date_range)
"""

from __future__ import annotations

import csv
import io
import logging
import statistics
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import text as sa_text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


# =============================================================================
# DATE RANGE HELPER
# =============================================================================

@dataclass(frozen=True)
class DateRange:
    """Inclusive date range for analytics queries."""
    start: date
    end: date

    @classmethod
    def last_n_days(cls, days: int) -> "DateRange":
        today = date.today()
        return cls(start=today - timedelta(days=days), end=today)

    @classmethod
    def last_30_days(cls) -> "DateRange":
        return cls.last_n_days(30)

    @classmethod
    def last_90_days(cls) -> "DateRange":
        return cls.last_n_days(90)

    @property
    def span_days(self) -> int:
        return max((self.end - self.start).days, 1)

    def to_params(self, prefix: str = "") -> Dict[str, date]:
        p = "start_date" if not prefix else f"{prefix}_start"
        q = "end_date" if not prefix else f"{prefix}_end"
        return {p: self.start, q: self.end}


# =============================================================================
# RESULT DATACLASSES
# =============================================================================

class EngagementGrade(str, Enum):
    """Borrower engagement letter grade."""
    A = "A"
    B = "B"
    C = "C"
    D = "D"


@dataclass
class VelocityMetrics:
    """Document collection velocity metrics."""
    avg_hours_request_to_upload: float
    median_hours_request_to_upload: float
    p90_hours_request_to_upload: float
    total_requests: int
    total_uploaded: int
    upload_rate_pct: float
    by_doc_type: Dict[str, Dict[str, Any]] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "avg_hours_request_to_upload": round(self.avg_hours_request_to_upload, 1),
            "median_hours_request_to_upload": round(self.median_hours_request_to_upload, 1),
            "p90_hours_request_to_upload": round(self.p90_hours_request_to_upload, 1),
            "total_requests": self.total_requests,
            "total_uploaded": self.total_uploaded,
            "upload_rate_pct": round(self.upload_rate_pct, 1),
            "by_doc_type": self.by_doc_type,
        }


@dataclass
class EngagementScore:
    """Borrower engagement scoring result."""
    borrower_id: int
    loan_id: Optional[int]
    overall_score: int  # 0-100
    grade: EngagementGrade
    portal_login_score: int
    upload_promptness_score: int
    response_time_score: int
    communication_score: int
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "borrower_id": self.borrower_id,
            "loan_id": self.loan_id,
            "overall_score": self.overall_score,
            "grade": self.grade.value,
            "breakdown": {
                "portal_login": self.portal_login_score,
                "upload_promptness": self.upload_promptness_score,
                "response_time": self.response_time_score,
                "communication": self.communication_score,
            },
            "details": self.details,
        }


@dataclass
class ChannelMetrics:
    """Per-channel communication performance metrics."""
    channel: str
    sent_count: int
    delivered_count: int
    opened_count: int
    clicked_count: int
    bounced_count: int
    response_count: int
    delivery_rate_pct: float
    open_rate_pct: float
    click_rate_pct: float
    response_rate_pct: float
    avg_response_hours: Optional[float]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "channel": self.channel,
            "sent": self.sent_count,
            "delivered": self.delivered_count,
            "opened": self.opened_count,
            "clicked": self.clicked_count,
            "bounced": self.bounced_count,
            "responses": self.response_count,
            "delivery_rate_pct": round(self.delivery_rate_pct, 1),
            "open_rate_pct": round(self.open_rate_pct, 1),
            "click_rate_pct": round(self.click_rate_pct, 1),
            "response_rate_pct": round(self.response_rate_pct, 1),
            "avg_response_hours": (
                round(self.avg_response_hours, 1) if self.avg_response_hours is not None else None
            ),
        }


@dataclass
class ProductivityMetrics:
    """LO or processor document-collection productivity."""
    user_id: Optional[int]
    user_name: Optional[str]
    documents_collected: int
    avg_touches_per_document: float
    first_time_acceptance_rate_pct: float
    avg_condition_clearance_hours: float
    documents_per_day: float
    campaigns_completed: int
    campaigns_active: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            "user_id": self.user_id,
            "user_name": self.user_name,
            "documents_collected": self.documents_collected,
            "avg_touches_per_document": round(self.avg_touches_per_document, 2),
            "first_time_acceptance_rate_pct": round(self.first_time_acceptance_rate_pct, 1),
            "avg_condition_clearance_hours": round(self.avg_condition_clearance_hours, 1),
            "documents_per_day": round(self.documents_per_day, 2),
            "campaigns_completed": self.campaigns_completed,
            "campaigns_active": self.campaigns_active,
        }


@dataclass
class FunnelStage:
    """A single stage in the document collection funnel."""
    stage: str
    count: int
    pct_of_total: float
    drop_off_pct: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "stage": self.stage,
            "count": self.count,
            "pct_of_total": round(self.pct_of_total, 1),
            "drop_off_pct": round(self.drop_off_pct, 1),
        }


@dataclass
class FunnelData:
    """Full document collection funnel."""
    stages: List[FunnelStage]
    biggest_drop_off: Optional[str]
    overall_completion_pct: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "stages": [s.to_dict() for s in self.stages],
            "biggest_drop_off": self.biggest_drop_off,
            "overall_completion_pct": round(self.overall_completion_pct, 1),
        }


@dataclass
class AnomalyAlert:
    """Detected anomaly in communication or collection patterns."""
    metric: str
    current_value: float
    baseline_value: float
    deviation_pct: float
    severity: str  # "warning" or "critical"
    message: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "metric": self.metric,
            "current_value": round(self.current_value, 2),
            "baseline_value": round(self.baseline_value, 2),
            "deviation_pct": round(self.deviation_pct, 1),
            "severity": self.severity,
            "message": self.message,
        }


# =============================================================================
# REPORT TYPES
# =============================================================================

VALID_REPORT_TYPES = {
    "collection_velocity",
    "channel_performance",
    "lo_productivity",
    "funnel_analysis",
    "borrower_engagement",
    "communication_volume",
    "cohort_comparison",
}


# =============================================================================
# COMMUNICATION ANALYTICS SERVICE
# =============================================================================

class CommunicationAnalyticsService:
    """
    Async analytics service for document-related communications.

    All query methods enforce org_id tenant isolation. The service reads
    from followup events, campaigns, document requests, and smart documents
    tables to produce aggregate metrics.
    """

    def __init__(self, db: Session, org_id: int):
        if not org_id:
            raise ValueError("org_id is required for CommunicationAnalyticsService")
        self.db = db
        self.org_id = org_id

    # =========================================================================
    # 1. COLLECTION VELOCITY
    # =========================================================================

    async def get_collection_velocity(
        self,
        date_range: Optional[DateRange] = None,
        lo_id: Optional[int] = None,
        loan_type: Optional[str] = None,
    ) -> VelocityMetrics:
        """Calculate document collection velocity (time from request to upload).

        Measures how quickly borrowers provide requested documents by joining
        document requests to uploaded smart documents.

        Args:
            date_range: Period to analyze. Defaults to last 30 days.
            lo_id: Filter by loan officer.
            loan_type: Filter by loan type.

        Returns:
            VelocityMetrics with avg/median/p90 hours and per-doc-type breakdown.
        """
        dr = date_range or DateRange.last_30_days()
        params: Dict[str, Any] = {
            "org_id": self.org_id,
            **dr.to_params(),
        }

        lo_filter = ""
        if lo_id is not None:
            lo_filter = "AND l.loan_officer_id = :lo_id"
            params["lo_id"] = lo_id

        lt_filter = ""
        if loan_type:
            lt_filter = "AND l.loan_type = :loan_type"
            params["loan_type"] = loan_type

        # Get time-to-upload for each fulfilled request
        query = f"""
            SELECT
                sdr.id AS request_id,
                sdr.doc_type,
                sdr.created_at AS requested_at,
                MIN(sd.uploaded_at) AS first_upload_at,
                EXTRACT(EPOCH FROM (MIN(sd.uploaded_at) - sdr.created_at)) / 3600.0
                    AS hours_to_upload
            FROM smart_document_requests sdr
            JOIN loans l ON l.id = sdr.loan_id
            LEFT JOIN smart_documents sd
                ON sd.request_id = sdr.id
                AND sd.status NOT IN ('REJECTED')
            WHERE l.organization_id = :org_id
              AND sdr.created_at >= :start_date
              AND sdr.created_at <= :end_date + INTERVAL '1 day'
              AND sdr.is_active = true
              {lo_filter}
              {lt_filter}
            GROUP BY sdr.id, sdr.doc_type, sdr.created_at
        """
        rows = self.db.execute(sa_text(query), params).fetchall()

        total_requests = len(rows)
        fulfilled = [r for r in rows if r.first_upload_at is not None]
        hours_list = [
            float(r.hours_to_upload) for r in fulfilled
            if r.hours_to_upload is not None and r.hours_to_upload >= 0
        ]

        if not hours_list:
            return VelocityMetrics(
                avg_hours_request_to_upload=0.0,
                median_hours_request_to_upload=0.0,
                p90_hours_request_to_upload=0.0,
                total_requests=total_requests,
                total_uploaded=0,
                upload_rate_pct=0.0,
            )

        sorted_hours = sorted(hours_list)
        p90_idx = int(0.9 * (len(sorted_hours) - 1))

        # Per doc-type breakdown
        by_type: Dict[str, List[float]] = {}
        for r in fulfilled:
            if r.hours_to_upload is not None and r.hours_to_upload >= 0:
                dt = str(r.doc_type) if r.doc_type else "UNKNOWN"
                by_type.setdefault(dt, []).append(float(r.hours_to_upload))

        by_type_summary = {}
        for dt, vals in by_type.items():
            by_type_summary[dt] = {
                "count": len(vals),
                "avg_hours": round(statistics.mean(vals), 1),
                "median_hours": round(statistics.median(vals), 1),
            }

        return VelocityMetrics(
            avg_hours_request_to_upload=statistics.mean(hours_list),
            median_hours_request_to_upload=statistics.median(hours_list),
            p90_hours_request_to_upload=sorted_hours[p90_idx],
            total_requests=total_requests,
            total_uploaded=len(fulfilled),
            upload_rate_pct=(len(fulfilled) / total_requests * 100) if total_requests > 0 else 0.0,
            by_doc_type=by_type_summary,
        )

    # =========================================================================
    # 2. BORROWER ENGAGEMENT SCORING
    # =========================================================================

    async def get_borrower_engagement(
        self,
        borrower_id: int,
        loan_id: Optional[int] = None,
    ) -> EngagementScore:
        """Calculate engagement score for a borrower.

        Scores four dimensions (each 0-25, total 0-100):
        - Portal login frequency (approximated by portal_notification opens)
        - Document upload promptness vs SLA
        - Message response time
        - Overall communication volume

        Args:
            borrower_id: The borrower (lead) ID to score.
            loan_id: Optional loan filter.

        Returns:
            EngagementScore with grade and breakdown.
        """
        params: Dict[str, Any] = {
            "org_id": self.org_id,
            "borrower_id": borrower_id,
        }

        loan_filter = ""
        if loan_id is not None:
            loan_filter = "AND fc.loan_id = :loan_id"
            params["loan_id"] = loan_id

        # -- Portal engagement (portal notifications opened / sent) --
        query = f"""
            SELECT
                COUNT(*) FILTER (WHERE fe.event_type = 'portal_notification') AS sent,
                COUNT(*) FILTER (
                    WHERE fe.event_type = 'portal_notification'
                    AND fe.opened_at IS NOT NULL
                ) AS opened
            FROM document_followup_events fe
            JOIN document_followup_campaigns fc ON fc.id = fe.campaign_id
            WHERE fc.organization_id = :org_id
              AND fc.borrower_id = :borrower_id
              {loan_filter}
        """
        portal_stats = self.db.execute(sa_text(query), params).fetchone()

        portal_sent = portal_stats.sent or 0 if portal_stats else 0
        portal_opened = portal_stats.opened or 0 if portal_stats else 0
        portal_rate = (portal_opened / portal_sent) if portal_sent > 0 else 0.0

        # Score: 25 if >80% open rate, scales linearly
        portal_login_score = min(25, int(portal_rate * 100 * 25 / 80))

        # -- Upload promptness vs SLA --
        query = f"""
            SELECT
                sdr.sla_due_at,
                sdr.completed_at
            FROM smart_document_requests sdr
            JOIN loans l ON l.id = sdr.loan_id
            WHERE l.organization_id = :org_id
              AND sdr.is_active = true
              AND sdr.status IN ('ACCEPTED', 'PENDING_REVIEW')
              AND sdr.completed_at IS NOT NULL
              AND l.id IN (
                  SELECT DISTINCT loan_id FROM document_followup_campaigns
                  WHERE borrower_id = :borrower_id
              )
              {loan_filter.replace("fc.loan_id", "l.id") if loan_filter else ""}
        """
        promptness_rows = self.db.execute(sa_text(query), params).fetchall()

        on_time_count = 0
        total_completed = len(promptness_rows)
        for row in promptness_rows:
            if row.sla_due_at and row.completed_at:
                if row.completed_at <= row.sla_due_at:
                    on_time_count += 1
            else:
                on_time_count += 1  # no SLA = on time

        on_time_rate = (on_time_count / total_completed) if total_completed > 0 else 0.5
        upload_promptness_score = min(25, int(on_time_rate * 25))

        # -- Response time (borrower_responded events) --
        query = f"""
            SELECT
                AVG(
                    EXTRACT(EPOCH FROM (fe_resp.created_at - fe_out.created_at)) / 3600.0
                ) AS avg_response_hours
            FROM document_followup_events fe_resp
            JOIN document_followup_campaigns fc ON fc.id = fe_resp.campaign_id
            LEFT JOIN LATERAL (
                SELECT fe2.created_at
                FROM document_followup_events fe2
                WHERE fe2.campaign_id = fe_resp.campaign_id
                  AND fe2.event_type IN ('email_sent', 'sms_sent', 'portal_notification')
                  AND fe2.created_at < fe_resp.created_at
                ORDER BY fe2.created_at DESC
                LIMIT 1
            ) fe_out ON true
            WHERE fc.organization_id = :org_id
              AND fc.borrower_id = :borrower_id
              AND fe_resp.event_type IN ('borrower_responded', 'document_uploaded')
              {loan_filter}
        """
        response_rows = self.db.execute(sa_text(query), params).fetchone()

        avg_resp_hours = float(response_rows.avg_response_hours or 168) if response_rows else 168.0
        # Score: 25 if <4h, 20 if <12h, 15 if <24h, 10 if <48h, 5 if <96h, 0 beyond
        if avg_resp_hours <= 4:
            response_time_score = 25
        elif avg_resp_hours <= 12:
            response_time_score = 20
        elif avg_resp_hours <= 24:
            response_time_score = 15
        elif avg_resp_hours <= 48:
            response_time_score = 10
        elif avg_resp_hours <= 96:
            response_time_score = 5
        else:
            response_time_score = 0

        # -- Communication engagement (total interactions) --
        query = f"""
            SELECT
                COUNT(*) FILTER (
                    WHERE fe.event_type IN ('borrower_responded', 'document_uploaded')
                ) AS borrower_actions,
                COUNT(*) FILTER (
                    WHERE fe.opened_at IS NOT NULL OR fe.clicked_at IS NOT NULL
                ) AS engagements,
                COUNT(*) AS total_events
            FROM document_followup_events fe
            JOIN document_followup_campaigns fc ON fc.id = fe.campaign_id
            WHERE fc.organization_id = :org_id
              AND fc.borrower_id = :borrower_id
              {loan_filter}
        """
        comm_stats = self.db.execute(sa_text(query), params).fetchone()

        borrower_actions = comm_stats.borrower_actions or 0 if comm_stats else 0
        total_events = comm_stats.total_events or 0 if comm_stats else 0
        engagement_rate = (borrower_actions / total_events) if total_events > 0 else 0.0

        # Score: 25 if >50% engagement rate, scales linearly
        communication_score = min(25, int(engagement_rate * 100 * 25 / 50))

        overall = portal_login_score + upload_promptness_score + response_time_score + communication_score

        if overall >= 80:
            grade = EngagementGrade.A
        elif overall >= 60:
            grade = EngagementGrade.B
        elif overall >= 40:
            grade = EngagementGrade.C
        else:
            grade = EngagementGrade.D

        return EngagementScore(
            borrower_id=borrower_id,
            loan_id=loan_id,
            overall_score=overall,
            grade=grade,
            portal_login_score=portal_login_score,
            upload_promptness_score=upload_promptness_score,
            response_time_score=response_time_score,
            communication_score=communication_score,
            details={
                "portal_open_rate": round(portal_rate * 100, 1),
                "on_time_upload_rate": round(on_time_rate * 100, 1),
                "avg_response_hours": round(avg_resp_hours, 1),
                "borrower_actions": borrower_actions,
                "total_completed_requests": total_completed,
            },
        )

    # =========================================================================
    # 3. CHANNEL PERFORMANCE
    # =========================================================================

    async def get_channel_performance(
        self,
        date_range: Optional[DateRange] = None,
    ) -> List[ChannelMetrics]:
        """Compare communication effectiveness across channels.

        Channels: email, sms, call, portal, in_app, push.

        Args:
            date_range: Period to analyze. Defaults to last 30 days.

        Returns:
            List of ChannelMetrics sorted by response rate descending.
        """
        dr = date_range or DateRange.last_30_days()
        params: Dict[str, Any] = {
            "org_id": self.org_id,
            **dr.to_params(),
        }

        rows = self.db.execute(sa_text("""
            SELECT
                fe.channel,
                COUNT(*) AS sent,
                COUNT(*) FILTER (
                    WHERE fe.delivery_status IN ('delivered', 'opened', 'clicked')
                ) AS delivered,
                COUNT(*) FILTER (
                    WHERE fe.delivery_status IN ('opened', 'clicked')
                    OR fe.opened_at IS NOT NULL
                ) AS opened,
                COUNT(*) FILTER (
                    WHERE fe.delivery_status = 'clicked'
                    OR fe.clicked_at IS NOT NULL
                ) AS clicked,
                COUNT(*) FILTER (
                    WHERE fe.delivery_status = 'bounced'
                ) AS bounced,
                COUNT(*) FILTER (
                    WHERE fe.delivery_status = 'failed'
                ) AS failed
            FROM document_followup_events fe
            WHERE fe.organization_id = :org_id
              AND fe.created_at >= :start_date
              AND fe.created_at <= :end_date + INTERVAL '1 day'
              AND fe.channel IS NOT NULL
              AND fe.event_type IN (
                  'email_sent', 'sms_sent', 'portal_notification',
                  'in_app_notification', 'call_scheduled', 'call_completed'
              )
            GROUP BY fe.channel
            ORDER BY COUNT(*) DESC
        """), params).fetchall()

        # Count borrower responses per channel (responses within 48h of an outbound event)
        response_rows = self.db.execute(sa_text("""
            SELECT
                fe_out.channel,
                COUNT(DISTINCT fe_resp.id) AS responses,
                AVG(
                    EXTRACT(EPOCH FROM (fe_resp.created_at - fe_out.created_at)) / 3600.0
                ) AS avg_response_hours
            FROM document_followup_events fe_out
            JOIN document_followup_events fe_resp
                ON fe_resp.campaign_id = fe_out.campaign_id
                AND fe_resp.event_type IN ('borrower_responded', 'document_uploaded')
                AND fe_resp.created_at > fe_out.created_at
                AND fe_resp.created_at < fe_out.created_at + INTERVAL '48 hours'
            WHERE fe_out.organization_id = :org_id
              AND fe_out.created_at >= :start_date
              AND fe_out.created_at <= :end_date + INTERVAL '1 day'
              AND fe_out.channel IS NOT NULL
              AND fe_out.event_type IN (
                  'email_sent', 'sms_sent', 'portal_notification',
                  'in_app_notification', 'call_completed'
              )
            GROUP BY fe_out.channel
        """), params).fetchall()

        response_map: Dict[str, Tuple[int, Optional[float]]] = {}
        for rr in response_rows:
            response_map[rr.channel] = (
                rr.responses or 0,
                float(rr.avg_response_hours) if rr.avg_response_hours is not None else None,
            )

        results: List[ChannelMetrics] = []
        for row in rows:
            sent = row.sent or 0
            delivered = row.delivered or 0
            opened = row.opened or 0
            clicked = row.clicked or 0
            bounced = row.bounced or 0
            resp_count, resp_hours = response_map.get(row.channel, (0, None))

            results.append(ChannelMetrics(
                channel=row.channel,
                sent_count=sent,
                delivered_count=delivered,
                opened_count=opened,
                clicked_count=clicked,
                bounced_count=bounced,
                response_count=resp_count,
                delivery_rate_pct=(delivered / sent * 100) if sent > 0 else 0.0,
                open_rate_pct=(opened / sent * 100) if sent > 0 else 0.0,
                click_rate_pct=(clicked / sent * 100) if sent > 0 else 0.0,
                response_rate_pct=(resp_count / sent * 100) if sent > 0 else 0.0,
                avg_response_hours=resp_hours,
            ))

        # Sort by response rate descending
        results.sort(key=lambda m: m.response_rate_pct, reverse=True)
        return results

    # =========================================================================
    # 4. LO / PROCESSOR PRODUCTIVITY
    # =========================================================================

    async def get_lo_productivity(
        self,
        lo_id: Optional[int] = None,
        date_range: Optional[DateRange] = None,
    ) -> ProductivityMetrics:
        """Measure LO/processor document collection productivity.

        Args:
            lo_id: Specific loan officer ID. If None, aggregates across org.
            date_range: Period to analyze. Defaults to last 30 days.

        Returns:
            ProductivityMetrics with docs/day, touches/doc, acceptance rate.
        """
        dr = date_range or DateRange.last_30_days()
        params: Dict[str, Any] = {
            "org_id": self.org_id,
            **dr.to_params(),
        }

        lo_filter = ""
        if lo_id is not None:
            lo_filter = "AND l.loan_officer_id = :lo_id"
            params["lo_id"] = lo_id

        # Documents collected (accepted in period)
        query = f"""
            SELECT
                COUNT(*) AS docs_collected,
                COUNT(*) FILTER (
                    WHERE sd.decision = 'ACCEPT'
                    AND NOT EXISTS (
                        SELECT 1 FROM smart_documents sd2
                        WHERE sd2.request_id = sd.request_id
                          AND sd2.id < sd.id
                          AND sd2.decision = 'REJECT'
                    )
                ) AS first_time_accepts,
                COUNT(DISTINCT sd.request_id) AS unique_requests
            FROM smart_documents sd
            JOIN loans l ON l.id = sd.loan_id
            WHERE l.organization_id = :org_id
              AND sd.decision = 'ACCEPT'
              AND sd.reviewed_at >= :start_date
              AND sd.reviewed_at <= :end_date + INTERVAL '1 day'
              {lo_filter}
        """
        doc_stats = self.db.execute(sa_text(query), params).fetchone()

        docs_collected = doc_stats.docs_collected or 0 if doc_stats else 0
        first_time_accepts = doc_stats.first_time_accepts or 0 if doc_stats else 0
        unique_requests = doc_stats.unique_requests or 0 if doc_stats else 0

        # Average touches per document (events per campaign that resulted in upload)
        query = f"""
            SELECT
                AVG(event_count) AS avg_touches
            FROM (
                SELECT
                    fc.id,
                    COUNT(fe.id) AS event_count
                FROM document_followup_campaigns fc
                JOIN document_followup_events fe ON fe.campaign_id = fc.id
                JOIN loans l ON l.id = fc.loan_id
                WHERE fc.organization_id = :org_id
                  AND fc.borrower_responded = true
                  AND fc.created_at >= :start_date
                  AND fc.created_at <= :end_date + INTERVAL '1 day'
                  {lo_filter}
                GROUP BY fc.id
            ) sub
        """
        touches_result = self.db.execute(sa_text(query), params).fetchone()

        avg_touches = float(touches_result.avg_touches or 0) if touches_result else 0.0

        # Condition clearance speed (time from request creation to acceptance)
        query = f"""
            SELECT
                AVG(
                    EXTRACT(EPOCH FROM (sdr.completed_at - sdr.created_at)) / 3600.0
                ) AS avg_clearance_hours
            FROM smart_document_requests sdr
            JOIN loans l ON l.id = sdr.loan_id
            WHERE l.organization_id = :org_id
              AND sdr.status = 'ACCEPTED'
              AND sdr.completed_at IS NOT NULL
              AND sdr.completed_at >= :start_date
              AND sdr.completed_at <= :end_date + INTERVAL '1 day'
              {lo_filter}
        """
        clearance_result = self.db.execute(sa_text(query), params).fetchone()

        avg_clearance_hours = float(clearance_result.avg_clearance_hours or 0) if clearance_result else 0.0

        # Campaign counts
        query = f"""
            SELECT
                COUNT(*) FILTER (WHERE fc.status = 'completed') AS completed,
                COUNT(*) FILTER (WHERE fc.status = 'active') AS active
            FROM document_followup_campaigns fc
            JOIN loans l ON l.id = fc.loan_id
            WHERE fc.organization_id = :org_id
              AND fc.created_at >= :start_date
              AND fc.created_at <= :end_date + INTERVAL '1 day'
              {lo_filter}
        """
        campaign_stats = self.db.execute(sa_text(query), params).fetchone()

        span_days = dr.span_days

        # Resolve user name if lo_id provided
        user_name = None
        if lo_id is not None:
            name_row = self.db.execute(sa_text(
                "SELECT first_name, last_name FROM users WHERE id = :lo_id"
            ), {"lo_id": lo_id}).fetchone()
            if name_row:
                user_name = f"{name_row.first_name or ''} {name_row.last_name or ''}".strip()

        return ProductivityMetrics(
            user_id=lo_id,
            user_name=user_name,
            documents_collected=docs_collected,
            avg_touches_per_document=avg_touches,
            first_time_acceptance_rate_pct=(
                (first_time_accepts / docs_collected * 100) if docs_collected > 0 else 0.0
            ),
            avg_condition_clearance_hours=avg_clearance_hours,
            documents_per_day=(docs_collected / span_days) if span_days > 0 else 0.0,
            campaigns_completed=campaign_stats.completed or 0 if campaign_stats else 0,
            campaigns_active=campaign_stats.active or 0 if campaign_stats else 0,
        )

    # =========================================================================
    # 5. FUNNEL ANALYSIS
    # =========================================================================

    async def get_funnel_analysis(
        self,
        date_range: Optional[DateRange] = None,
    ) -> FunnelData:
        """Analyze the document collection funnel.

        Stages:
            requested -> reminder_sent -> uploaded -> reviewed -> approved

        Identifies the biggest drop-off point.

        Args:
            date_range: Period to analyze. Defaults to last 30 days.

        Returns:
            FunnelData with stage counts and drop-off percentages.
        """
        dr = date_range or DateRange.last_30_days()
        params: Dict[str, Any] = {
            "org_id": self.org_id,
            **dr.to_params(),
        }

        funnel = self.db.execute(sa_text("""
            SELECT
                COUNT(*) AS requested,
                COUNT(*) FILTER (
                    WHERE EXISTS (
                        SELECT 1 FROM document_followup_campaigns fc2
                        WHERE fc2.loan_id = sdr.loan_id
                          AND fc2.organization_id = :org_id
                          AND fc2.reminders_sent > 0
                          AND fc2.linked_request_ids::text LIKE '%%' || sdr.id::text || '%%'
                    )
                ) AS reminder_sent,
                COUNT(*) FILTER (
                    WHERE EXISTS (
                        SELECT 1 FROM smart_documents sd
                        WHERE sd.request_id = sdr.id
                    )
                ) AS uploaded,
                COUNT(*) FILTER (
                    WHERE EXISTS (
                        SELECT 1 FROM smart_documents sd
                        WHERE sd.request_id = sdr.id
                          AND sd.decision IS NOT NULL
                    )
                ) AS reviewed,
                COUNT(*) FILTER (
                    WHERE sdr.status = 'ACCEPTED'
                ) AS approved
            FROM smart_document_requests sdr
            JOIN loans l ON l.id = sdr.loan_id
            WHERE l.organization_id = :org_id
              AND sdr.created_at >= :start_date
              AND sdr.created_at <= :end_date + INTERVAL '1 day'
              AND sdr.is_active = true
        """), params).fetchone()

        stage_counts = [
            ("requested", funnel.requested or 0),
            ("reminder_sent", funnel.reminder_sent or 0),
            ("uploaded", funnel.uploaded or 0),
            ("reviewed", funnel.reviewed or 0),
            ("approved", funnel.approved or 0),
        ]

        total = stage_counts[0][1] if stage_counts else 0
        stages: List[FunnelStage] = []
        biggest_drop_off = None
        biggest_drop_off_pct = 0.0

        for i, (stage_name, count) in enumerate(stage_counts):
            pct_of_total = (count / total * 100) if total > 0 else 0.0
            if i == 0:
                drop_off = 0.0
            else:
                prev_count = stage_counts[i - 1][1]
                drop_off = (
                    ((prev_count - count) / prev_count * 100) if prev_count > 0 else 0.0
                )
                if drop_off > biggest_drop_off_pct:
                    biggest_drop_off_pct = drop_off
                    biggest_drop_off = f"{stage_counts[i - 1][0]} -> {stage_name}"

            stages.append(FunnelStage(
                stage=stage_name,
                count=count,
                pct_of_total=pct_of_total,
                drop_off_pct=drop_off,
            ))

        overall_completion = (
            (stage_counts[-1][1] / total * 100) if total > 0 else 0.0
        )

        return FunnelData(
            stages=stages,
            biggest_drop_off=biggest_drop_off,
            overall_completion_pct=overall_completion,
        )

    # =========================================================================
    # 6. TREND ANALYSIS
    # =========================================================================

    async def get_communication_trends(
        self,
        date_range: Optional[DateRange] = None,
        granularity: str = "week",
    ) -> Dict[str, Any]:
        """Get week-over-week or day-over-day communication volume trends.

        Args:
            date_range: Period to analyze. Defaults to last 90 days.
            granularity: "day" or "week".

        Returns:
            Dict with trend data points, period-over-period changes,
            and responsiveness trends.
        """
        dr = date_range or DateRange.last_90_days()
        params: Dict[str, Any] = {
            "org_id": self.org_id,
            **dr.to_params(),
        }

        if granularity == "day":
            trunc = "day"
        else:
            trunc = "week"

        # Communication volume by period
        query = f"""
            SELECT
                DATE_TRUNC(:trunc, fe.created_at)::date AS period,
                COUNT(*) FILTER (
                    WHERE fe.event_type IN ('email_sent', 'sms_sent', 'portal_notification',
                        'in_app_notification', 'call_scheduled', 'call_completed')
                ) AS outbound,
                COUNT(*) FILTER (
                    WHERE fe.event_type IN ('borrower_responded', 'document_uploaded')
                ) AS inbound,
                COUNT(*) AS total
            FROM document_followup_events fe
            WHERE fe.organization_id = :org_id
              AND fe.created_at >= :start_date
              AND fe.created_at <= :end_date + INTERVAL '1 day'
            GROUP BY DATE_TRUNC(:trunc, fe.created_at)::date
            ORDER BY period
        """
        volume_rows = self.db.execute(sa_text(query), {**params, "trunc": trunc}).fetchall()

        trends = []
        for i, row in enumerate(volume_rows):
            prev_total = volume_rows[i - 1].total if i > 0 else row.total
            change_pct = (
                ((row.total - prev_total) / prev_total * 100) if prev_total > 0 else 0.0
            )
            response_rate = (
                (row.inbound / row.outbound * 100) if row.outbound > 0 else 0.0
            )
            trends.append({
                "period": row.period.isoformat() if hasattr(row.period, "isoformat") else str(row.period),
                "outbound": row.outbound or 0,
                "inbound": row.inbound or 0,
                "total": row.total or 0,
                "change_pct": round(change_pct, 1),
                "response_rate_pct": round(response_rate, 1),
            })

        # Summary stats
        if trends:
            total_outbound = sum(t["outbound"] for t in trends)
            total_inbound = sum(t["inbound"] for t in trends)
            avg_volume = statistics.mean([t["total"] for t in trends])
        else:
            total_outbound = total_inbound = 0
            avg_volume = 0.0

        return {
            "granularity": granularity,
            "date_range": {
                "start": dr.start.isoformat(),
                "end": dr.end.isoformat(),
            },
            "total_outbound": total_outbound,
            "total_inbound": total_inbound,
            "avg_volume_per_period": round(avg_volume, 1),
            "trend_data": trends,
        }

    # =========================================================================
    # 7. COHORT ANALYSIS
    # =========================================================================

    async def get_cohort_comparison(
        self,
        cohort_type: str = "lo",
        date_range: Optional[DateRange] = None,
        limit: int = 20,
    ) -> Dict[str, Any]:
        """Compare performance across cohorts (LOs, branches, loan types).

        Args:
            cohort_type: One of "lo", "loan_type", "branch".
            date_range: Period to analyze. Defaults to last 90 days.
            limit: Maximum cohorts to return.

        Returns:
            Dict with cohort comparison data.
        """
        dr = date_range or DateRange.last_90_days()
        params: Dict[str, Any] = {
            "org_id": self.org_id,
            **dr.to_params(),
            "limit": limit,
        }

        if cohort_type == "lo":
            group_col = "l.loan_officer_id"
            name_join = """
                LEFT JOIN users u ON u.id = l.loan_officer_id
            """
            name_select = "CONCAT(u.first_name, ' ', u.last_name) AS cohort_name"
        elif cohort_type == "loan_type":
            group_col = "l.loan_type"
            name_join = ""
            name_select = "l.loan_type AS cohort_name"
        elif cohort_type == "branch":
            group_col = "l.branch_id"
            name_join = ""
            name_select = "COALESCE(CAST(l.branch_id AS TEXT), 'Unknown') AS cohort_name"
        else:
            return {"error": f"Invalid cohort_type: {cohort_type}"}

        query = f"""
            SELECT
                {group_col} AS cohort_id,
                {name_select},
                COUNT(DISTINCT sdr.id) AS total_requests,
                COUNT(DISTINCT sdr.id) FILTER (
                    WHERE sdr.status = 'ACCEPTED'
                ) AS completed_requests,
                AVG(
                    EXTRACT(EPOCH FROM (sdr.completed_at - sdr.created_at)) / 3600.0
                ) FILTER (
                    WHERE sdr.status = 'ACCEPTED' AND sdr.completed_at IS NOT NULL
                ) AS avg_completion_hours,
                COUNT(DISTINCT fc.id) AS campaigns_created,
                COUNT(DISTINCT fc.id) FILTER (
                    WHERE fc.borrower_responded = true
                ) AS campaigns_responded
            FROM smart_document_requests sdr
            JOIN loans l ON l.id = sdr.loan_id
            {name_join}
            LEFT JOIN document_followup_campaigns fc
                ON fc.loan_id = l.id
                AND fc.organization_id = :org_id
            WHERE l.organization_id = :org_id
              AND sdr.created_at >= :start_date
              AND sdr.created_at <= :end_date + INTERVAL '1 day'
              AND sdr.is_active = true
              AND {group_col} IS NOT NULL
            GROUP BY {group_col}, {name_select.split(' AS ')[0]}
            ORDER BY COUNT(DISTINCT sdr.id) FILTER (WHERE sdr.status = 'ACCEPTED') DESC
            LIMIT :limit
        """
        rows = self.db.execute(sa_text(query), params).fetchall()

        cohorts = []
        for row in rows:
            total_req = row.total_requests or 0
            completed = row.completed_requests or 0
            campaigns_created = row.campaigns_created or 0
            campaigns_responded = row.campaigns_responded or 0

            cohorts.append({
                "cohort_id": row.cohort_id,
                "cohort_name": row.cohort_name,
                "total_requests": total_req,
                "completed_requests": completed,
                "completion_rate_pct": round(
                    (completed / total_req * 100) if total_req > 0 else 0.0, 1
                ),
                "avg_completion_hours": round(
                    float(row.avg_completion_hours or 0), 1
                ),
                "campaigns_created": campaigns_created,
                "response_rate_pct": round(
                    (campaigns_responded / campaigns_created * 100)
                    if campaigns_created > 0 else 0.0, 1
                ),
            })

        return {
            "cohort_type": cohort_type,
            "date_range": {
                "start": dr.start.isoformat(),
                "end": dr.end.isoformat(),
            },
            "cohort_count": len(cohorts),
            "cohorts": cohorts,
        }

    # =========================================================================
    # 8. ANOMALY DETECTION
    # =========================================================================

    async def detect_anomalies(
        self,
        lookback_days: int = 7,
        baseline_days: int = 30,
    ) -> List[AnomalyAlert]:
        """Detect anomalies by comparing recent metrics to a baseline period.

        Compares the recent ``lookback_days`` window against the preceding
        ``baseline_days`` window. Flags deviations >30% as warnings and
        >50% as critical.

        Args:
            lookback_days: Recent window to evaluate.
            baseline_days: Preceding baseline window.

        Returns:
            List of AnomalyAlert objects, sorted by severity.
        """
        now = date.today()
        recent_range = DateRange(start=now - timedelta(days=lookback_days), end=now)
        baseline_end = now - timedelta(days=lookback_days)
        baseline_range = DateRange(
            start=baseline_end - timedelta(days=baseline_days),
            end=baseline_end,
        )

        alerts: List[AnomalyAlert] = []

        async def _check_metric(
            metric_name: str,
            recent_val: float,
            baseline_val: float,
            higher_is_worse: bool = True,
            label: str = "",
        ) -> None:
            if baseline_val == 0:
                return

            deviation = ((recent_val - baseline_val) / baseline_val) * 100
            abs_dev = abs(deviation)

            is_worse = (deviation > 0) if higher_is_worse else (deviation < 0)
            if not is_worse:
                return

            if abs_dev < 30:
                return

            severity = "critical" if abs_dev >= 50 else "warning"
            direction = "increased" if deviation > 0 else "decreased"

            alerts.append(AnomalyAlert(
                metric=metric_name,
                current_value=recent_val,
                baseline_value=baseline_val,
                deviation_pct=deviation,
                severity=severity,
                message=f"{label or metric_name} {direction} by {abs_dev:.0f}% vs baseline",
            ))

        # -- Check: bounce rate --
        for label, dr in [("recent", recent_range), ("baseline", baseline_range)]:
            rows = self.db.execute(sa_text("""
                SELECT
                    COUNT(*) AS total,
                    COUNT(*) FILTER (WHERE delivery_status = 'bounced') AS bounced
                FROM document_followup_events
                WHERE organization_id = :org_id
                  AND created_at >= :start_date
                  AND created_at <= :end_date + INTERVAL '1 day'
                  AND event_type IN ('email_sent', 'sms_sent')
            """), {"org_id": self.org_id, **dr.to_params()}).fetchone()

            total = rows.total or 0 if rows else 0
            bounced = rows.bounced or 0 if rows else 0
            if label == "recent":
                recent_bounce = (bounced / total * 100) if total > 0 else 0.0
            else:
                baseline_bounce = (bounced / total * 100) if total > 0 else 0.0

        await _check_metric("bounce_rate", recent_bounce, baseline_bounce, True, "Bounce rate")

        # -- Check: response rate --
        for label, dr in [("recent", recent_range), ("baseline", baseline_range)]:
            rows = self.db.execute(sa_text("""
                SELECT
                    COUNT(*) FILTER (
                        WHERE event_type IN ('email_sent', 'sms_sent', 'portal_notification')
                    ) AS outbound,
                    COUNT(*) FILTER (
                        WHERE event_type IN ('borrower_responded', 'document_uploaded')
                    ) AS responses
                FROM document_followup_events
                WHERE organization_id = :org_id
                  AND created_at >= :start_date
                  AND created_at <= :end_date + INTERVAL '1 day'
            """), {"org_id": self.org_id, **dr.to_params()}).fetchone()

            outbound = rows.outbound or 0 if rows else 0
            responses = rows.responses or 0 if rows else 0
            if label == "recent":
                recent_response = (responses / outbound * 100) if outbound > 0 else 0.0
            else:
                baseline_response = (responses / outbound * 100) if outbound > 0 else 0.0

        await _check_metric(
            "response_rate", recent_response, baseline_response,
            higher_is_worse=False, label="Response rate",
        )

        # -- Check: collection velocity --
        for label, dr in [("recent", recent_range), ("baseline", baseline_range)]:
            rows = self.db.execute(sa_text("""
                SELECT
                    AVG(
                        EXTRACT(EPOCH FROM (
                            COALESCE(sdr.completed_at, CURRENT_TIMESTAMP) - sdr.created_at
                        )) / 3600.0
                    ) AS avg_hours
                FROM smart_document_requests sdr
                JOIN loans l ON l.id = sdr.loan_id
                WHERE l.organization_id = :org_id
                  AND sdr.created_at >= :start_date
                  AND sdr.created_at <= :end_date + INTERVAL '1 day'
                  AND sdr.is_active = true
                  AND sdr.status = 'ACCEPTED'
                  AND sdr.completed_at IS NOT NULL
            """), {"org_id": self.org_id, **dr.to_params()}).fetchone()

            avg_h = float(rows.avg_hours or 0) if rows else 0.0
            if label == "recent":
                recent_velocity = avg_h
            else:
                baseline_velocity = avg_h

        await _check_metric(
            "collection_velocity_hours", recent_velocity, baseline_velocity,
            higher_is_worse=True, label="Collection velocity",
        )

        # -- Check: outbound volume --
        for label, dr in [("recent", recent_range), ("baseline", baseline_range)]:
            rows = self.db.execute(sa_text("""
                SELECT COUNT(*) AS cnt
                FROM document_followup_events
                WHERE organization_id = :org_id
                  AND created_at >= :start_date
                  AND created_at <= :end_date + INTERVAL '1 day'
                  AND event_type IN ('email_sent', 'sms_sent', 'portal_notification')
            """), {"org_id": self.org_id, **dr.to_params()}).fetchone()

            # Normalize to daily rate
            cnt = (rows.cnt or 0) if rows else 0
            daily = cnt / max(dr.span_days, 1)
            if label == "recent":
                recent_daily = daily
            else:
                baseline_daily = daily

        await _check_metric(
            "outbound_daily_volume", recent_daily, baseline_daily,
            higher_is_worse=False, label="Daily outbound volume",
        )

        alerts.sort(key=lambda a: (0 if a.severity == "critical" else 1, -abs(a.deviation_pct)))
        return alerts

    # =========================================================================
    # 9. REAL-TIME DASHBOARD DATA
    # =========================================================================

    async def get_dashboard_summary(self) -> Dict[str, Any]:
        """Get real-time dashboard summary for the organization.

        Returns a compact overview suitable for a dashboard widget:
        active campaigns, pending requests, recent uploads, SLA status,
        and today's communication activity.

        Returns:
            Dict with dashboard summary data.
        """
        params = {"org_id": self.org_id}

        # Active campaigns & pending requests
        pipeline = self.db.execute(sa_text("""
            SELECT
                (SELECT COUNT(*) FROM document_followup_campaigns
                 WHERE organization_id = :org_id AND status = 'active') AS active_campaigns,
                (SELECT COUNT(*) FROM smart_document_requests sdr
                 JOIN loans l ON l.id = sdr.loan_id
                 WHERE l.organization_id = :org_id
                   AND sdr.is_active = true
                   AND sdr.status = 'OPEN') AS pending_requests,
                (SELECT COUNT(*) FROM smart_document_requests sdr
                 JOIN loans l ON l.id = sdr.loan_id
                 WHERE l.organization_id = :org_id
                   AND sdr.is_active = true
                   AND sdr.status = 'PENDING_REVIEW') AS pending_review,
                (SELECT COUNT(*) FROM smart_document_requests sdr
                 JOIN loans l ON l.id = sdr.loan_id
                 WHERE l.organization_id = :org_id
                   AND sdr.is_active = true
                   AND sdr.status IN ('OPEN', 'PENDING_REVIEW')
                   AND sdr.sla_due_at < CURRENT_TIMESTAMP) AS sla_breached,
                (SELECT COUNT(*) FROM smart_document_requests sdr
                 JOIN loans l ON l.id = sdr.loan_id
                 WHERE l.organization_id = :org_id
                   AND sdr.is_active = true
                   AND sdr.status IN ('OPEN', 'PENDING_REVIEW')
                   AND sdr.sla_due_at >= CURRENT_TIMESTAMP
                   AND sdr.sla_due_at < CURRENT_TIMESTAMP + INTERVAL '24 hours') AS sla_at_risk
        """), params).fetchone()

        # Today's activity
        today_activity = self.db.execute(sa_text("""
            SELECT
                COUNT(*) FILTER (
                    WHERE event_type IN ('email_sent', 'sms_sent', 'portal_notification',
                        'in_app_notification', 'call_scheduled', 'call_completed')
                ) AS outbound_today,
                COUNT(*) FILTER (
                    WHERE event_type IN ('borrower_responded', 'document_uploaded')
                ) AS inbound_today
            FROM document_followup_events
            WHERE organization_id = :org_id
              AND created_at >= CURRENT_DATE
        """), params).fetchone()

        # Recent uploads (last 24h)
        recent_uploads = self.db.execute(sa_text("""
            SELECT COUNT(*) AS cnt
            FROM smart_documents sd
            JOIN loans l ON l.id = sd.loan_id
            WHERE l.organization_id = :org_id
              AND sd.uploaded_at >= CURRENT_TIMESTAMP - INTERVAL '24 hours'
        """), params).fetchone()

        return {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "org_id": self.org_id,
            "active_campaigns": pipeline.active_campaigns or 0 if pipeline else 0,
            "pending_requests": pipeline.pending_requests or 0 if pipeline else 0,
            "pending_review": pipeline.pending_review or 0 if pipeline else 0,
            "sla": {
                "breached": pipeline.sla_breached or 0 if pipeline else 0,
                "at_risk": pipeline.sla_at_risk or 0 if pipeline else 0,
            },
            "today": {
                "outbound_messages": today_activity.outbound_today or 0 if today_activity else 0,
                "inbound_responses": today_activity.inbound_today or 0 if today_activity else 0,
            },
            "uploads_last_24h": recent_uploads.cnt or 0 if recent_uploads else 0,
        }

    # =========================================================================
    # 10. EXPORT REPORTS
    # =========================================================================

    async def export_report(
        self,
        report_type: str,
        date_range: Optional[DateRange] = None,
        format: str = "csv",
    ) -> bytes:
        """Generate an exportable report as CSV bytes.

        Args:
            report_type: One of VALID_REPORT_TYPES.
            date_range: Period to analyze. Defaults to last 30 days.
            format: Output format. Currently only "csv" is supported.

        Returns:
            bytes of the CSV file content (UTF-8 encoded).

        Raises:
            ValueError: If report_type is invalid.
        """
        if report_type not in VALID_REPORT_TYPES:
            raise ValueError(
                f"Invalid report_type '{report_type}'. "
                f"Valid types: {', '.join(sorted(VALID_REPORT_TYPES))}"
            )

        dr = date_range or DateRange.last_30_days()

        if report_type == "collection_velocity":
            return await self._export_collection_velocity(dr)
        elif report_type == "channel_performance":
            return await self._export_channel_performance(dr)
        elif report_type == "lo_productivity":
            return await self._export_lo_productivity(dr)
        elif report_type == "funnel_analysis":
            return await self._export_funnel_analysis(dr)
        elif report_type == "borrower_engagement":
            return await self._export_borrower_engagement(dr)
        elif report_type == "communication_volume":
            return await self._export_communication_volume(dr)
        elif report_type == "cohort_comparison":
            return await self._export_cohort_comparison(dr)
        else:
            raise ValueError(f"Report type '{report_type}' not implemented")

    # -- Export helpers --------------------------------------------------------

    async def _export_collection_velocity(self, dr: DateRange) -> bytes:
        velocity = await self.get_collection_velocity(date_range=dr)
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([
            "Metric", "Value",
        ])
        writer.writerow(["Avg Hours Request to Upload", velocity.avg_hours_request_to_upload])
        writer.writerow(["Median Hours Request to Upload", velocity.median_hours_request_to_upload])
        writer.writerow(["P90 Hours Request to Upload", velocity.p90_hours_request_to_upload])
        writer.writerow(["Total Requests", velocity.total_requests])
        writer.writerow(["Total Uploaded", velocity.total_uploaded])
        writer.writerow(["Upload Rate %", velocity.upload_rate_pct])
        writer.writerow([])
        writer.writerow(["Doc Type", "Count", "Avg Hours", "Median Hours"])
        for dt, stats in velocity.by_doc_type.items():
            writer.writerow([dt, stats["count"], stats["avg_hours"], stats["median_hours"]])
        return output.getvalue().encode("utf-8")

    async def _export_channel_performance(self, dr: DateRange) -> bytes:
        channels = await self.get_channel_performance(date_range=dr)
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([
            "Channel", "Sent", "Delivered", "Opened", "Clicked", "Bounced",
            "Responses", "Delivery Rate %", "Open Rate %", "Click Rate %",
            "Response Rate %", "Avg Response Hours",
        ])
        for ch in channels:
            writer.writerow([
                ch.channel, ch.sent_count, ch.delivered_count, ch.opened_count,
                ch.clicked_count, ch.bounced_count, ch.response_count,
                ch.delivery_rate_pct, ch.open_rate_pct, ch.click_rate_pct,
                ch.response_rate_pct, ch.avg_response_hours or "",
            ])
        return output.getvalue().encode("utf-8")

    async def _export_lo_productivity(self, dr: DateRange) -> bytes:
        params: Dict[str, Any] = {
            "org_id": self.org_id,
            **dr.to_params(),
        }

        lo_rows = self.db.execute(sa_text("""
            SELECT DISTINCT l.loan_officer_id
            FROM loans l
            JOIN smart_document_requests sdr ON sdr.loan_id = l.id
            WHERE l.organization_id = :org_id
              AND sdr.created_at >= :start_date
              AND sdr.created_at <= :end_date + INTERVAL '1 day'
              AND l.loan_officer_id IS NOT NULL
        """), params).fetchall()

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([
            "LO Name", "Documents Collected", "Docs/Day",
            "Avg Touches/Doc", "First-Time Accept %",
            "Avg Clearance Hours", "Campaigns Completed", "Campaigns Active",
        ])

        for row in lo_rows:
            metrics = await self.get_lo_productivity(
                lo_id=row.loan_officer_id, date_range=dr,
            )
            writer.writerow([
                metrics.user_name or f"LO#{metrics.user_id}",
                metrics.documents_collected,
                round(metrics.documents_per_day, 2),
                round(metrics.avg_touches_per_document, 2),
                round(metrics.first_time_acceptance_rate_pct, 1),
                round(metrics.avg_condition_clearance_hours, 1),
                metrics.campaigns_completed,
                metrics.campaigns_active,
            ])

        return output.getvalue().encode("utf-8")

    async def _export_funnel_analysis(self, dr: DateRange) -> bytes:
        funnel = await self.get_funnel_analysis(date_range=dr)
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["Stage", "Count", "% of Total", "Drop-off %"])
        for stage in funnel.stages:
            writer.writerow([
                stage.stage, stage.count,
                round(stage.pct_of_total, 1), round(stage.drop_off_pct, 1),
            ])
        writer.writerow([])
        writer.writerow(["Biggest Drop-off", funnel.biggest_drop_off or "N/A"])
        writer.writerow(["Overall Completion %", round(funnel.overall_completion_pct, 1)])
        return output.getvalue().encode("utf-8")

    async def _export_borrower_engagement(self, dr: DateRange) -> bytes:
        """Export engagement scores for all borrowers with activity in the period."""
        params: Dict[str, Any] = {
            "org_id": self.org_id,
            **dr.to_params(),
        }

        borrower_rows = self.db.execute(sa_text("""
            SELECT DISTINCT fc.borrower_id, fc.loan_id
            FROM document_followup_campaigns fc
            WHERE fc.organization_id = :org_id
              AND fc.created_at >= :start_date
              AND fc.created_at <= :end_date + INTERVAL '1 day'
              AND fc.borrower_id IS NOT NULL
        """), params).fetchall()

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([
            "Borrower ID", "Loan ID", "Overall Score", "Grade",
            "Portal Login Score", "Upload Promptness Score",
            "Response Time Score", "Communication Score",
        ])

        for row in borrower_rows:
            try:
                eng = await self.get_borrower_engagement(
                    borrower_id=row.borrower_id,
                    loan_id=row.loan_id,
                )
                writer.writerow([
                    eng.borrower_id, eng.loan_id, eng.overall_score, eng.grade.value,
                    eng.portal_login_score, eng.upload_promptness_score,
                    eng.response_time_score, eng.communication_score,
                ])
            except Exception as e:
                logger.warning(
                    "Failed to score borrower %s for export: %s",
                    row.borrower_id, e,
                )

        return output.getvalue().encode("utf-8")

    async def _export_communication_volume(self, dr: DateRange) -> bytes:
        trends = await self.get_communication_trends(date_range=dr, granularity="day")
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([
            "Date", "Outbound", "Inbound", "Total",
            "Change %", "Response Rate %",
        ])
        for point in trends.get("trend_data", []):
            writer.writerow([
                point["period"], point["outbound"], point["inbound"],
                point["total"], point["change_pct"], point["response_rate_pct"],
            ])
        return output.getvalue().encode("utf-8")

    async def _export_cohort_comparison(self, dr: DateRange) -> bytes:
        data = await self.get_cohort_comparison(cohort_type="lo", date_range=dr)
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([
            "Cohort Name", "Total Requests", "Completed Requests",
            "Completion Rate %", "Avg Completion Hours",
            "Campaigns Created", "Response Rate %",
        ])
        for cohort in data.get("cohorts", []):
            writer.writerow([
                cohort["cohort_name"], cohort["total_requests"],
                cohort["completed_requests"], cohort["completion_rate_pct"],
                cohort["avg_completion_hours"], cohort["campaigns_created"],
                cohort["response_rate_pct"],
            ])
        return output.getvalue().encode("utf-8")

    # =========================================================================
    # COMMUNICATION EFFECTIVENESS (which messages drive uploads)
    # =========================================================================

    async def get_communication_effectiveness(
        self,
        date_range: Optional[DateRange] = None,
    ) -> Dict[str, Any]:
        """Determine which message types/templates most effectively drive uploads.

        Measures the conversion rate from outbound message to document upload
        within a 72-hour attribution window, grouped by template and channel.

        Args:
            date_range: Period to analyze. Defaults to last 30 days.

        Returns:
            Dict with per-template effectiveness metrics.
        """
        dr = date_range or DateRange.last_30_days()
        params: Dict[str, Any] = {
            "org_id": self.org_id,
            **dr.to_params(),
        }

        rows = self.db.execute(sa_text("""
            SELECT
                fe_out.channel,
                fe_out.template_used,
                COUNT(DISTINCT fe_out.id) AS messages_sent,
                COUNT(DISTINCT fe_upload.id) AS uploads_driven,
                AVG(
                    EXTRACT(EPOCH FROM (fe_upload.created_at - fe_out.created_at)) / 3600.0
                ) AS avg_hours_to_upload
            FROM document_followup_events fe_out
            LEFT JOIN document_followup_events fe_upload
                ON fe_upload.campaign_id = fe_out.campaign_id
                AND fe_upload.event_type = 'document_uploaded'
                AND fe_upload.created_at > fe_out.created_at
                AND fe_upload.created_at < fe_out.created_at + INTERVAL '72 hours'
            WHERE fe_out.organization_id = :org_id
              AND fe_out.created_at >= :start_date
              AND fe_out.created_at <= :end_date + INTERVAL '1 day'
              AND fe_out.event_type IN ('email_sent', 'sms_sent', 'portal_notification',
                  'in_app_notification', 'call_completed')
            GROUP BY fe_out.channel, fe_out.template_used
            ORDER BY COUNT(DISTINCT fe_upload.id)::float /
                NULLIF(COUNT(DISTINCT fe_out.id), 0) DESC NULLS LAST
        """), params).fetchall()

        effectiveness = []
        for row in rows:
            sent = row.messages_sent or 0
            uploads = row.uploads_driven or 0
            conversion_rate = (uploads / sent * 100) if sent > 0 else 0.0

            effectiveness.append({
                "channel": row.channel,
                "template": row.template_used or "unknown",
                "messages_sent": sent,
                "uploads_driven": uploads,
                "conversion_rate_pct": round(conversion_rate, 1),
                "avg_hours_to_upload": (
                    round(float(row.avg_hours_to_upload), 1)
                    if row.avg_hours_to_upload is not None else None
                ),
            })

        return {
            "date_range": {
                "start": dr.start.isoformat(),
                "end": dr.end.isoformat(),
            },
            "attribution_window_hours": 72,
            "effectiveness": effectiveness,
        }

    # =========================================================================
    # FIRST-CONTACT RESOLUTION RATE
    # =========================================================================

    async def get_first_contact_resolution_rate(
        self,
        date_range: Optional[DateRange] = None,
    ) -> Dict[str, Any]:
        """Calculate first-contact resolution rate.

        Measures how often the first outreach message in a campaign leads
        directly to a document upload without needing additional follow-ups.

        Args:
            date_range: Period to analyze. Defaults to last 30 days.

        Returns:
            Dict with FCR rate and breakdown.
        """
        dr = date_range or DateRange.last_30_days()
        params: Dict[str, Any] = {
            "org_id": self.org_id,
            **dr.to_params(),
        }

        result = self.db.execute(sa_text("""
            SELECT
                COUNT(*) AS total_campaigns,
                COUNT(*) FILTER (
                    WHERE fc.borrower_responded = true AND fc.reminders_sent <= 1
                ) AS first_contact_resolved,
                COUNT(*) FILTER (
                    WHERE fc.borrower_responded = true
                ) AS total_resolved
            FROM document_followup_campaigns fc
            WHERE fc.organization_id = :org_id
              AND fc.created_at >= :start_date
              AND fc.created_at <= :end_date + INTERVAL '1 day'
        """), params).fetchone()

        total = result.total_campaigns or 0 if result else 0
        fcr = result.first_contact_resolved or 0 if result else 0
        total_resolved = result.total_resolved or 0 if result else 0

        return {
            "date_range": {
                "start": dr.start.isoformat(),
                "end": dr.end.isoformat(),
            },
            "total_campaigns": total,
            "first_contact_resolved": fcr,
            "total_resolved": total_resolved,
            "fcr_rate_pct": round((fcr / total * 100) if total > 0 else 0.0, 1),
            "overall_resolution_rate_pct": round(
                (total_resolved / total * 100) if total > 0 else 0.0, 1,
            ),
        }


# =============================================================================
# FACTORY FUNCTION
# =============================================================================

def get_communication_analytics_service(
    db: Session,
    org_id: int,
) -> CommunicationAnalyticsService:
    """Create a CommunicationAnalyticsService instance.

    Args:
        db: SQLAlchemy session for the current request.
        org_id: Organization ID for tenant isolation.

    Returns:
        CommunicationAnalyticsService instance.
    """
    return CommunicationAnalyticsService(db=db, org_id=org_id)
