"""
Phase 3 API Routes - Advanced Features
======================================
Routes for:
- AI Receptionist Business Intelligence
- Conversational Insights
- Call Compliance
- Webhook Automation (Zapier/Make)
"""

import logging
from datetime import date, datetime, timedelta, timezone
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Query, Body
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field

from database import get_db
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from db import get_async_db

logger = logging.getLogger(__name__)

# ============================================================================
# ROUTERS
# ============================================================================

# Business Intelligence Router
bi_router = APIRouter(prefix="/api/v1/ai-receptionist/analytics", tags=["AI Receptionist Analytics"])

# Conversational Insights Router
insights_router = APIRouter(prefix="/api/v1/conversational-insights", tags=["Conversational Insights"])

# Call Compliance Router
compliance_router = APIRouter(prefix="/api/v1/compliance", tags=["Call Compliance"])

# Webhook Automation Router
webhook_router = APIRouter(prefix="/api/v1/webhooks", tags=["Webhook Automation"])


# ============================================================================
# PYDANTIC MODELS
# ============================================================================

class WebhookEndpointCreate(BaseModel):
    name: str = Field(..., description="Friendly name for the endpoint")
    url: str = Field(..., description="Target URL for webhook delivery")
    events: List[str] = Field(..., description="Events to subscribe to")
    headers: Optional[dict] = Field(default={}, description="Custom headers")


class WebhookEndpointUpdate(BaseModel):
    name: Optional[str] = None
    url: Optional[str] = None
    events: Optional[List[str]] = None
    status: Optional[str] = None
    headers: Optional[dict] = None


class ConsentRecordCreate(BaseModel):
    call_id: str
    phone_number: str
    state: str
    consent_obtained: bool
    disclosure_played: bool = True
    verbal_ack: bool = False


class DNCSRequest(BaseModel):
    phone_number: str
    reason: str = "customer_request"


# ============================================================================
# BUSINESS INTELLIGENCE ROUTES
# ============================================================================

@bi_router.get("/summary")
async def get_analytics_summary(
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    db: Session = Depends(get_db)
):
    """
    Get executive summary dashboard data.

    Returns comprehensive metrics including:
    - Headline KPIs with period comparison
    - Financial impact analysis
    - Conversion funnel
    - ROI breakdown
    - Performance benchmarks
    """
    try:
        from services.ai_receptionist_analytics_service import AIReceptionistAnalyticsService
        service = AIReceptionistAnalyticsService(db)
        return service.get_executive_summary(start_date, end_date)
    except Exception as e:
        logger.error(f"Error getting analytics summary: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@bi_router.get("/funnel")
async def get_conversion_funnel(
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    user_id: Optional[int] = Query(None),
    db: Session = Depends(get_db)
):
    """
    Get conversion funnel metrics.

    Tracks: Call → Engaged → Appointment → Application → Funded
    """
    try:
        from services.ai_receptionist_analytics_service import AIReceptionistAnalyticsService
        service = AIReceptionistAnalyticsService(db)
        funnel = service.get_conversion_funnel(start_date, end_date, user_id)
        return funnel.to_dict()
    except Exception as e:
        logger.error(f"Error getting conversion funnel: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@bi_router.get("/funnel/trend")
async def get_funnel_trend(
    days: int = Query(30, ge=1, le=365),
    granularity: str = Query("day", enum=["day", "week"]),
    db: Session = Depends(get_db)
):
    """Get conversion funnel trend over time."""
    try:
        from services.ai_receptionist_analytics_service import AIReceptionistAnalyticsService
        service = AIReceptionistAnalyticsService(db)
        return service.get_funnel_trend(days, granularity)
    except Exception as e:
        logger.error(f"Error getting funnel trend: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@bi_router.get("/roi")
async def get_roi_metrics(
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    platform_cost: float = Query(500.0, description="Monthly platform cost"),
    db: Session = Depends(get_db)
):
    """
    Calculate ROI for the AI Receptionist.

    Returns:
    - Cost breakdown (AI calls, platform)
    - Savings (labor, after-hours, missed leads)
    - Revenue attribution
    - Net ROI percentage
    """
    try:
        from services.ai_receptionist_analytics_service import AIReceptionistAnalyticsService
        service = AIReceptionistAnalyticsService(db)
        roi = service.calculate_roi(start_date, end_date, platform_cost)
        return roi.to_dict()
    except Exception as e:
        logger.error(f"Error calculating ROI: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@bi_router.get("/roi/trend")
async def get_roi_trend(
    months: int = Query(6, ge=1, le=24),
    db: Session = Depends(get_db)
):
    """Get monthly ROI trend."""
    try:
        from services.ai_receptionist_analytics_service import AIReceptionistAnalyticsService
        service = AIReceptionistAnalyticsService(db)
        return service.get_roi_trend(months)
    except Exception as e:
        logger.error(f"Error getting ROI trend: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@bi_router.get("/benchmarks")
async def get_performance_benchmarks(
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    db: Session = Depends(get_db)
):
    """
    Compare performance against industry benchmarks.

    Returns status indicators for each metric:
    - excellent: >20% above benchmark
    - good: at or above benchmark
    - needs_improvement: up to 20% below
    - critical: >20% below benchmark
    """
    try:
        from services.ai_receptionist_analytics_service import AIReceptionistAnalyticsService
        service = AIReceptionistAnalyticsService(db)
        benchmarks = service.get_performance_benchmarks(start_date, end_date)
        return [b.to_dict() for b in benchmarks]
    except Exception as e:
        logger.error(f"Error getting benchmarks: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


# ============================================================================
# CONVERSATIONAL INSIGHTS ROUTES
# ============================================================================

@insights_router.get("/summary")
async def get_insights_summary(
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db)
):
    """
    Get aggregated insights from recent conversations.

    Returns:
    - Intent distribution
    - Sentiment analysis
    - Objection frequency
    - Trending topics
    - Top questions asked
    """
    try:
        from services.conversational_insights_service import ConversationalInsightsService
        service = ConversationalInsightsService(db)
        summary = service.get_insights_summary(start_date, end_date, limit)
        return summary.to_dict()
    except Exception as e:
        logger.error(f"Error getting insights summary: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@insights_router.get("/trending-questions")
async def get_trending_questions(
    days: int = Query(7, ge=1, le=90),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db)
):
    """Get most frequently asked questions."""
    try:
        from services.conversational_insights_service import ConversationalInsightsService
        service = ConversationalInsightsService(db)
        return {"questions": service.get_trending_questions(days, limit)}
    except Exception as e:
        logger.error(f"Error getting trending questions: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@insights_router.get("/objections")
async def get_objection_analysis(
    days: int = Query(30, ge=1, le=365),
    db: Session = Depends(get_db)
):
    """
    Get detailed objection analysis with handling recommendations.

    Identifies common objections and provides suggested responses.
    """
    try:
        from services.conversational_insights_service import ConversationalInsightsService
        service = ConversationalInsightsService(db)
        return service.get_objection_analysis(days)
    except Exception as e:
        logger.error(f"Error getting objection analysis: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@insights_router.get("/sentiment/trend")
async def get_sentiment_trend(
    days: int = Query(30, ge=1, le=90),
    db: Session = Depends(get_db)
):
    """Get daily sentiment trend."""
    try:
        from services.conversational_insights_service import ConversationalInsightsService
        service = ConversationalInsightsService(db)
        return {"trend": service.get_sentiment_trend(days)}
    except Exception as e:
        logger.error(f"Error getting sentiment trend: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@insights_router.post("/analyze")
async def analyze_conversation(
    transcript: str = Body(..., embed=True),
    conversation_id: Optional[str] = Body(None, embed=True),
    db: Session = Depends(get_db)
):
    """
    Analyze a single conversation transcript.

    Returns intent, sentiment, objections, key questions, and topics.
    """
    try:
        from services.conversational_insights_service import ConversationalInsightsService
        service = ConversationalInsightsService(db)
        insight = service.analyze_conversation(transcript, conversation_id)
        return insight.to_dict()
    except Exception as e:
        logger.error(f"Error analyzing conversation: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


# ============================================================================
# CALL COMPLIANCE ROUTES
# ============================================================================

@compliance_router.get("/state/{state_code}")
async def get_state_requirements(
    state_code: str,
    db: Session = Depends(get_db)
):
    """
    Get recording consent requirements for a state.

    Returns consent type, disclosure script, and any special requirements.
    """
    try:
        from services.call_compliance_service import CallComplianceService
        service = CallComplianceService(db)
        return service.get_state_requirements(state_code)
    except Exception as e:
        logger.error(f"Error getting state requirements: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@compliance_router.get("/states/summary")
async def get_all_states_summary(db: Session = Depends(get_db)):
    """Get compliance summary for all states."""
    try:
        from services.call_compliance_service import CallComplianceService
        service = CallComplianceService(db)
        return service.get_state_compliance_summary()
    except Exception as e:
        logger.error(f"Error getting states summary: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@compliance_router.post("/pre-call-check")
async def pre_call_compliance_check(
    phone_number: str = Body(..., embed=True),
    caller_state: Optional[str] = Body(None, embed=True),
    db: Session = Depends(get_db)
):
    """
    Pre-call compliance check.

    Returns whether to proceed, required disclosures, and DNC status.
    """
    try:
        from services.call_compliance_service import CallComplianceService
        service = CallComplianceService(db)
        return service.check_call_compliance(phone_number, caller_state)
    except Exception as e:
        logger.error(f"Error in pre-call check: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@compliance_router.post("/consent/record")
async def record_consent(
    data: ConsentRecordCreate,
    db: Session = Depends(get_db)
):
    """Record consent status for a call (creates audit trail)."""
    try:
        from services.call_compliance_service import CallComplianceService
        service = CallComplianceService(db)
        record = service.record_consent(
            call_id=data.call_id,
            phone_number=data.phone_number,
            state=data.state,
            consent_obtained=data.consent_obtained,
            disclosure_played=data.disclosure_played,
            verbal_ack=data.verbal_ack
        )
        return record.to_dict()
    except Exception as e:
        logger.error(f"Error recording consent: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@compliance_router.post("/dnc/add")
async def add_to_dnc_list(
    data: DNCSRequest,
    db: Session = Depends(get_db)
):
    """Add phone number to Do-Not-Call list."""
    try:
        from services.call_compliance_service import CallComplianceService
        service = CallComplianceService(db)
        success = service.add_to_dnc_list(data.phone_number, data.reason)
        return {"success": success}
    except Exception as e:
        logger.error(f"Error adding to DNC: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@compliance_router.delete("/dnc/remove")
async def remove_from_dnc_list(
    phone_number: str,
    db: Session = Depends(get_db)
):
    """Remove phone number from Do-Not-Call list."""
    try:
        from services.call_compliance_service import CallComplianceService
        service = CallComplianceService(db)
        success = service.remove_from_dnc_list(phone_number)
        return {"success": success}
    except SQLAlchemyError as e:
        logger.error(f"Error removing from DNC: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@compliance_router.get("/report")
async def get_compliance_report(
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    db: Session = Depends(get_db)
):
    """
    Get compliance report for the specified period.

    Shows compliance rate, violations, and consent statistics.
    """
    try:
        from services.call_compliance_service import CallComplianceService
        service = CallComplianceService(db)
        report = service.get_compliance_report(start_date, end_date)
        return report.to_dict()
    except Exception as e:
        logger.error(f"Error getting compliance report: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


# ============================================================================
# WEBHOOK AUTOMATION ROUTES
# ============================================================================

@webhook_router.get("/endpoints")
async def list_webhook_endpoints(
    organization_id: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_async_db)
):
    """List all registered webhook endpoints."""
    try:
        from services.webhook_automation_service import webhook_service
        webhook_service.set_db(db)
        endpoints = webhook_service.list_endpoints(organization_id)
        return {"endpoints": [e.to_dict() for e in endpoints]}
    except Exception as e:
        logger.error(f"Error listing endpoints: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@webhook_router.post("/endpoints")
async def create_webhook_endpoint(
    data: WebhookEndpointCreate,
    db: AsyncSession = Depends(get_async_db)
):
    """
    Register a new webhook endpoint.

    Returns the endpoint details including the secret for signature verification.
    """
    try:
        from services.webhook_automation_service import webhook_service, WebhookEvent
        webhook_service.set_db(db)

        events = [WebhookEvent(e) for e in data.events]

        endpoint = webhook_service.register_endpoint(
            name=data.name,
            url=data.url,
            events=events,
            headers=data.headers
        )

        return {
            **endpoint.to_dict(),
            "secret": endpoint.secret  # Only returned on creation
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail="Invalid event type")
    except Exception as e:
        logger.error(f"Error creating endpoint: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@webhook_router.put("/endpoints/{endpoint_id}")
async def update_webhook_endpoint(
    endpoint_id: str,
    data: WebhookEndpointUpdate,
    db: AsyncSession = Depends(get_async_db)
):
    """Update an existing webhook endpoint."""
    try:
        from services.webhook_automation_service import webhook_service, WebhookEvent
        webhook_service.set_db(db)

        updates = data.dict(exclude_none=True)
        if "events" in updates:
            updates["events"] = [WebhookEvent(e) for e in updates["events"]]

        endpoint = webhook_service.update_endpoint(endpoint_id, **updates)
        if not endpoint:
            raise HTTPException(status_code=404, detail="Endpoint not found")

        return endpoint.to_dict()
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating endpoint: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@webhook_router.delete("/endpoints/{endpoint_id}")
async def delete_webhook_endpoint(
    endpoint_id: str,
    db: AsyncSession = Depends(get_async_db)
):
    """Delete a webhook endpoint."""
    try:
        from services.webhook_automation_service import webhook_service
        webhook_service.set_db(db)

        success = webhook_service.delete_endpoint(endpoint_id)
        if not success:
            raise HTTPException(status_code=404, detail="Endpoint not found")

        return {"success": True}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting endpoint: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@webhook_router.get("/events")
async def list_available_events():
    """List all available webhook events."""
    try:
        from services.webhook_automation_service import WebhookEvent
        return {
            "events": [
                {"name": e.value, "description": e.value.replace(".", " ").replace("_", " ").title()}
                for e in WebhookEvent
            ]
        }
    except Exception as e:
        logger.error(f"Error listing events: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@webhook_router.get("/events/{event}/sample")
async def get_event_sample_payload(event: str):
    """Get sample payload for a webhook event (useful for Zapier/Make setup)."""
    try:
        from services.webhook_automation_service import webhook_service, WebhookEvent
        event_type = WebhookEvent(event)
        return webhook_service.get_sample_payload(event_type)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid event type: {event}")
    except Exception as e:
        logger.error(f"Error getting sample payload: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@webhook_router.post("/test/{endpoint_id}")
async def test_webhook_endpoint(
    endpoint_id: str,
    db: AsyncSession = Depends(get_async_db)
):
    """Send a test webhook to an endpoint."""
    try:
        from services.webhook_automation_service import webhook_service, WebhookEvent
        webhook_service.set_db(db)

        endpoint = webhook_service.get_endpoint(endpoint_id)
        if not endpoint:
            raise HTTPException(status_code=404, detail="Endpoint not found")

        # Send test event
        delivery_ids = webhook_service.trigger_event(
            event=WebhookEvent.CALL_COMPLETED,
            payload={
                "test": True,
                "message": "This is a test webhook delivery",
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
        )

        return {
            "success": True,
            "delivery_ids": delivery_ids,
            "message": "Test webhook queued for delivery"
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error testing endpoint: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@webhook_router.get("/deliveries")
async def get_delivery_history(
    endpoint_id: Optional[str] = Query(None),
    event: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_async_db)
):
    """Get webhook delivery history."""
    try:
        from services.webhook_automation_service import webhook_service, WebhookEvent
        webhook_service.set_db(db)

        event_type = WebhookEvent(event) if event else None
        deliveries = webhook_service.get_delivery_history(endpoint_id, event_type, status, limit)
        return {"deliveries": deliveries}
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid event type: {event}")
    except Exception as e:
        logger.error(f"Error getting delivery history: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@webhook_router.get("/stats")
async def get_webhook_stats(db: AsyncSession = Depends(get_async_db)):
    """Get webhook delivery statistics."""
    try:
        from services.webhook_automation_service import webhook_service
        webhook_service.set_db(db)
        return webhook_service.get_delivery_stats()
    except Exception as e:
        logger.error(f"Error getting webhook stats: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


# Zapier-specific endpoints
@webhook_router.post("/zapier/subscribe")
async def zapier_subscribe(
    event: str = Query(...),
    target_url: str = Body(..., embed=True),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Zapier subscription endpoint.

    Called by Zapier when a user enables a trigger.
    """
    try:
        from services.webhook_automation_service import webhook_service, WebhookEvent
        webhook_service.set_db(db)

        event_type = WebhookEvent(event)

        endpoint = webhook_service.register_endpoint(
            name=f"Zapier - {event}",
            url=target_url,
            events=[event_type]
        )

        return {"id": endpoint.id}
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid event type: {event}")
    except Exception as e:
        logger.error(f"Error in Zapier subscribe: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@webhook_router.delete("/zapier/unsubscribe/{endpoint_id}")
async def zapier_unsubscribe(
    endpoint_id: str,
    db: AsyncSession = Depends(get_async_db)
):
    """
    Zapier unsubscription endpoint.

    Called by Zapier when a user disables a trigger.
    """
    try:
        from services.webhook_automation_service import webhook_service
        webhook_service.set_db(db)

        success = webhook_service.delete_endpoint(endpoint_id)
        return {"success": success}
    except Exception as e:
        logger.error(f"Error in Zapier unsubscribe: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
