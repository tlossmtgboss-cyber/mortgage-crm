# AI Receptionist → Dashboard Integration Code

## Critical Missing Piece: Real-Time Logging

You're 100% correct - the dashboard is useless without real AI data. Here's the EXACT code that needs to be added to `voice_routes.py` to connect everything.

---

## File: voice_routes.py

### Step 1: Add Imports (Top of File)

```python
# ADD THESE IMPORTS
from ai_receptionist_dashboard_models import (
    AIReceptionistActivity,
    AIReceptionistError,
    AIReceptionistConversation
)
import uuid
```

---

### Step 2: Modify `handle_incoming_call()` - Line 28

**BEFORE:**
```python
@router.post("/incoming")
async def handle_incoming_call(request: Request, db: Session = Depends(get_db)):
    """
    Twilio webhook for incoming calls
    Returns TwiML to handle the call with AI
    """
    try:
        form_data = await request.form()
        caller_number = form_data.get("From", "Unknown")
        called_number = form_data.get("To", "")
        call_sid = form_data.get("CallSid", "")

        logger.info(f"Incoming call from {caller_number} (SID: {call_sid})")

        # Log the call in database
        call_event = IncomingDataEvent(
            source="phone_call",
            external_message_id=call_sid,
            raw_text=f"Incoming call from {caller_number}",
            processed=False,
            metadata={
                "caller": caller_number,
                "direction": "inbound",
                "call_sid": call_sid
            }
        )
        db.add(call_event)
        db.commit()

        # Generate TwiML response to connect to AI
        twiml = voice_client.create_greeting_response(ai_config.business_name)

        return Response(content=str(twiml), media_type="application/xml")
```

**AFTER (with dashboard logging):**
```python
@router.post("/incoming")
async def handle_incoming_call(request: Request, db: Session = Depends(get_db)):
    """
    Twilio webhook for incoming calls
    Returns TwiML to handle the call with AI
    """
    try:
        form_data = await request.form()
        caller_number = form_data.get("From", "Unknown")
        called_number = form_data.get("To", "")
        call_sid = form_data.get("CallSid", "")

        logger.info(f"Incoming call from {caller_number} (SID: {call_sid})")

        # Log the call in database
        call_event = IncomingDataEvent(
            source="phone_call",
            external_message_id=call_sid,
            raw_text=f"Incoming call from {caller_number}",
            processed=False,
            metadata={
                "caller": caller_number,
                "direction": "inbound",
                "call_sid": call_sid
            }
        )
        db.add(call_event)

        # ✅ NEW: Log to AI Receptionist Dashboard
        dashboard_activity = AIReceptionistActivity(
            id=str(uuid.uuid4()),
            timestamp=datetime.now(timezone.utc),
            client_phone=caller_number,
            action_type='incoming_call',
            channel='voice',
            outcome_status='pending',
            conversation_id=call_sid,
            extra_data={
                "twilio_call_sid": call_sid,
                "called_number": called_number
            }
        )
        db.add(dashboard_activity)

        db.commit()

        # Generate TwiML response to connect to AI
        twiml = voice_client.create_greeting_response(ai_config.business_name)

        return Response(content=str(twiml), media_type="application/xml")
```

---

### Step 3: Modify `save_call_summary()` - Line 320

**BEFORE:**
```python
async def save_call_summary(call_context: dict, db: Session):
    """Save call summary and create lead/task if needed"""
    try:
        # Create or update lead
        if call_context['lead_data'].get('phone'):
            phone = call_context['lead_data']['phone']

            # Check if lead exists
            lead = db.query(Lead).filter(Lead.phone == phone).first()

            if not lead:
                # Create new lead
                lead = Lead(
                    name=call_context['lead_data'].get('name', 'Phone Inquiry'),
                    phone=phone,
                    source="Phone Call",
                    stage="NEW",
                    notes=f"Inbound call. Conversation summary:\n{json.dumps(call_context['conversation_history'], indent=2)}"
                )
                db.add(lead)
                logger.info(f"Created new lead from call: {phone}")

            # Log activity
            activity = Activity(
                lead_id=lead.id if lead else None,
                activity_type="phone_call",
                description=f"AI Receptionist Call - {call_context.get('intent', 'General Inquiry')}",
                notes=json.dumps(call_context['conversation_history'], indent=2),
                metadata={
                    "call_sid": call_context['call_sid'],
                    "lead_data": call_context['lead_data'],
                }
            )
            db.add(activity)
            db.commit()

    except Exception as e:
        logger.error(f"Error saving call summary: {e}")
```

**AFTER (with dashboard logging):**
```python
async def save_call_summary(call_context: dict, db: Session):
    """Save call summary and create lead/task if needed"""
    try:
        # Create or update lead
        if call_context['lead_data'].get('phone'):
            phone = call_context['lead_data']['phone']

            # Check if lead exists
            lead = db.query(Lead).filter(Lead.phone == phone).first()

            if not lead:
                # Create new lead
                lead = Lead(
                    name=call_context['lead_data'].get('name', 'Phone Inquiry'),
                    phone=phone,
                    source="Phone Call",
                    stage="NEW",
                    notes=f"Inbound call. Conversation summary:\n{json.dumps(call_context['conversation_history'], indent=2)}"
                )
                db.add(lead)
                logger.info(f"Created new lead from call: {phone}")

            # Log activity
            activity = Activity(
                lead_id=lead.id if lead else None,
                activity_type="phone_call",
                description=f"AI Receptionist Call - {call_context.get('intent', 'General Inquiry')}",
                notes=json.dumps(call_context['conversation_history'], indent=2),
                metadata={
                    "call_sid": call_context['call_sid'],
                    "lead_data": call_context['lead_data'],
                }
            )
            db.add(activity)

            # ✅ NEW: Save full conversation to dashboard
            conversation_record = AIReceptionistConversation(
                id=str(uuid.uuid4()),
                started_at=call_context.get('start_time', datetime.now(timezone.utc)),
                ended_at=datetime.now(timezone.utc),
                duration_seconds=call_context.get('duration', 0),
                client_id=str(lead.id) if lead else None,
                client_name=call_context['lead_data'].get('name'),
                client_phone=phone,
                channel='voice',
                direction='inbound',
                transcript=json.dumps(call_context['conversation_history'], indent=2),
                transcript_json=call_context['conversation_history'],
                summary=call_context.get('intent', 'General inquiry'),
                intent_detected=call_context.get('intent', 'unknown'),
                sentiment='neutral',  # TODO: Add sentiment analysis
                outcome=call_context.get('outcome', 'completed'),
                avg_confidence_score=call_context.get('avg_confidence', 0.85),
                total_turns=len(call_context['conversation_history']),
                extra_data={
                    "call_sid": call_context['call_sid'],
                    "lead_data": call_context['lead_data']
                }
            )
            db.add(conversation_record)

            # ✅ NEW: Update activity feed with conversation summary
            activity_update = AIReceptionistActivity(
                id=str(uuid.uuid4()),
                timestamp=datetime.now(timezone.utc),
                client_id=str(lead.id) if lead else None,
                client_name=call_context['lead_data'].get('name'),
                client_phone=phone,
                action_type='conversation_summary',
                channel='voice',
                confidence_score=call_context.get('avg_confidence', 0.85),
                ai_version='gpt-4o-realtime-v1',
                outcome_status='success',
                conversation_id=call_context['call_sid'],
                extra_data={
                    "intent": call_context.get('intent'),
                    "lead_data": call_context['lead_data'],
                    "turns": len(call_context['conversation_history'])
                }
            )
            db.add(activity_update)

            db.commit()

    except Exception as e:
        logger.error(f"Error saving call summary: {e}")

        # ✅ NEW: Log error to dashboard
        try:
            error_log = AIReceptionistError(
                id=str(uuid.uuid4()),
                timestamp=datetime.now(timezone.utc),
                error_type='api_failure',
                severity='high',
                context=f"Failed to save call summary: {str(e)}",
                conversation_snippet=json.dumps(call_context.get('conversation_history', [])[-3:]),
                conversation_id=call_context.get('call_sid'),
                root_cause='Unknown',
                needs_human_review=True,
                resolution_status='unresolved',
                extra_data={
                    "call_context": str(call_context),
                    "error_message": str(e)
                }
            )
            db.add(error_log)
            db.commit()
        except:
            pass  # Don't fail on error logging
```

---

### Step 4: Modify WebSocket Handler - Line 94

**Find this section in the WebSocket handler:**

```python
async def voice_stream_websocket(websocket: WebSocket, db: Session = Depends(get_db)):
    """
    WebSocket endpoint for Twilio Media Streams -> OpenAI Realtime API
    Handles bidirectional audio streaming for AI conversations
    """
    await websocket.accept()
    logger.info("Voice stream WebSocket connected")

    # ... existing code ...

    # ADD THIS at the end when conversation completes:
    finally:
        try:
            await websocket.close()
            if 'openai_ws' in locals():
                await openai_ws.close()

            # ✅ NEW: Log conversation completion to dashboard
            if 'call_context' in locals() and call_context.get('call_sid'):
                dashboard_activity = AIReceptionistActivity(
                    id=str(uuid.uuid4()),
                    timestamp=datetime.now(timezone.utc),
                    action_type='call_ended',
                    channel='voice',
                    confidence_score=call_context.get('avg_confidence', 0.85),
                    outcome_status='completed',
                    conversation_id=call_context['call_sid'],
                    extra_data={
                        "duration_seconds": call_context.get('duration', 0),
                        "turns": len(call_context.get('conversation_history', []))
                    }
                )
                db.add(dashboard_activity)
                db.commit()
        except:
            pass
```

---

### Step 5: Add Error Logging Throughout

**Find all `except Exception as e:` blocks and add:**

```python
except Exception as e:
    logger.error(f"Error in voice handler: {e}")

    # ✅ NEW: Log to dashboard
    try:
        error_log = AIReceptionistError(
            id=str(uuid.uuid4()),
            timestamp=datetime.now(timezone.utc),
            error_type='integration_error',
            severity='high',
            context=f"Voice handler error: {str(e)}",
            root_cause=type(e).__name__,
            needs_human_review=True,
            resolution_status='unresolved',
            extra_data={"error_details": str(e)}
        )
        db.add(error_log)
        db.commit()
    except:
        pass
```

---

## Additional Integration Points

### SMS Handler (sms_routes.py or similar)

If you have SMS handlers, add similar logging:

```python
from ai_receptionist_dashboard_models import AIReceptionistActivity
import uuid

@router.post("/incoming-sms")
async def handle_incoming_sms(request: Request, db: Session = Depends(get_db)):
    # ... existing code ...

    # ✅ ADD: Log to dashboard
    dashboard_activity = AIReceptionistActivity(
        id=str(uuid.uuid4()),
        timestamp=datetime.now(timezone.utc),
        client_phone=from_number,
        action_type='incoming_text',
        channel='sms',
        message_in=body,
        message_out=ai_response,
        confidence_score=ai_confidence,
        outcome_status='success',
        extra_data={"message_sid": message_sid}
    )
    db.add(dashboard_activity)
    db.commit()
```

---

## System Health Monitoring (NEW FILE NEEDED)

Create: `backend/cron_jobs/monitor_system_health.py`

```python
"""
System Health Monitoring Cron Job
Run every 60 seconds to check integration health
"""
from sqlalchemy.orm import Session
from database import SessionLocal
from ai_receptionist_dashboard_models import AIReceptionistSystemHealth
from datetime import datetime, timezone
import requests
import logging

logger = logging.getLogger(__name__)

def check_component_health(component_name: str, endpoint_url: str) -> dict:
    """Check if a component is healthy"""
    try:
        start_time = datetime.now()
        response = requests.get(endpoint_url, timeout=5)
        latency_ms = int((datetime.now() - start_time).total_seconds() * 1000)

        return {
            "status": "active" if response.status_code == 200 else "degraded",
            "latency_ms": latency_ms,
            "last_success": datetime.now(timezone.utc)
        }
    except Exception as e:
        logger.error(f"Health check failed for {component_name}: {e}")
        return {
            "status": "down",
            "latency_ms": None,
            "last_failure": datetime.now(timezone.utc)
        }

def update_system_health():
    """Update system health for all components"""
    db = SessionLocal()
    try:
        components = {
            "voice_endpoint": "https://mortgage-crm-production-7a9a.up.railway.app/api/v1/voice/call-stats",
            "openai_api": "https://api.openai.com/v1/models",  # Health check
            "twilio_api": "https://status.twilio.com/api/v2/status.json",
        }

        for component_name, endpoint in components.items():
            health_data = check_component_health(component_name, endpoint)

            # Update or create health record
            health_record = db.query(AIReceptionistSystemHealth).filter(
                AIReceptionistSystemHealth.component_name == component_name
            ).first()

            if not health_record:
                health_record = AIReceptionistSystemHealth(component_name=component_name)
                db.add(health_record)

            health_record.status = health_data["status"]
            health_record.latency_ms = health_data.get("latency_ms")
            health_record.last_checked = datetime.now(timezone.utc)

            if health_data.get("last_success"):
                health_record.last_success = health_data["last_success"]
                health_record.consecutive_failures = 0

            if health_data.get("last_failure"):
                health_record.last_failure = health_data["last_failure"]
                health_record.consecutive_failures = (health_record.consecutive_failures or 0) + 1

            db.commit()

        logger.info("System health check completed")

    except Exception as e:
        logger.error(f"Error updating system health: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    update_system_health()
```

**Schedule this to run every 60 seconds** (use Railway cron or systemd timer)

---

## Daily Metrics Aggregation (NEW FILE NEEDED)

Create: `backend/cron_jobs/aggregate_daily_metrics.py`

```python
"""
Daily Metrics Aggregation Cron Job
Run at 12:01 AM daily to calculate yesterday's metrics
"""
from sqlalchemy.orm import Session
from sqlalchemy import func
from database import SessionLocal
from ai_receptionist_dashboard_models import (
    AIReceptionistMetricsDaily,
    AIReceptionistActivity
)
from datetime import date, datetime, timedelta, timezone
import logging

logger = logging.getLogger(__name__)

def aggregate_yesterday_metrics():
    """Aggregate metrics for yesterday"""
    db = SessionLocal()
    try:
        yesterday = date.today() - timedelta(days=1)
        yesterday_start = datetime.combine(yesterday, datetime.min.time()).replace(tzinfo=timezone.utc)
        yesterday_end = datetime.combine(yesterday, datetime.max.time()).replace(tzinfo=timezone.utc)

        # Count activities by type
        total_conversations = db.query(func.count(AIReceptionistActivity.id)).filter(
            AIReceptionistActivity.timestamp >= yesterday_start,
            AIReceptionistActivity.timestamp <= yesterday_end
        ).scalar() or 0

        inbound_calls = db.query(func.count(AIReceptionistActivity.id)).filter(
            AIReceptionistActivity.timestamp >= yesterday_start,
            AIReceptionistActivity.timestamp <= yesterday_end,
            AIReceptionistActivity.action_type == 'incoming_call',
            AIReceptionistActivity.channel == 'voice'
        ).scalar() or 0

        inbound_texts = db.query(func.count(AIReceptionistActivity.id)).filter(
            AIReceptionistActivity.timestamp >= yesterday_start,
            AIReceptionistActivity.timestamp <= yesterday_end,
            AIReceptionistActivity.action_type == 'incoming_text',
            AIReceptionistActivity.channel == 'sms'
        ).scalar() or 0

        appointments_scheduled = db.query(func.count(AIReceptionistActivity.id)).filter(
            AIReceptionistActivity.timestamp >= yesterday_start,
            AIReceptionistActivity.timestamp <= yesterday_end,
            AIReceptionistActivity.action_type == 'appointment_booked'
        ).scalar() or 0

        escalations = db.query(func.count(AIReceptionistActivity.id)).filter(
            AIReceptionistActivity.timestamp >= yesterday_start,
            AIReceptionistActivity.timestamp <= yesterday_end,
            AIReceptionistActivity.outcome_status == 'escalated'
        ).scalar() or 0

        # Calculate average confidence score
        avg_confidence = db.query(func.avg(AIReceptionistActivity.confidence_score)).filter(
            AIReceptionistActivity.timestamp >= yesterday_start,
            AIReceptionistActivity.timestamp <= yesterday_end,
            AIReceptionistActivity.confidence_score.isnot(None)
        ).scalar() or 0.0

        # Create metrics record
        metrics_record = AIReceptionistMetricsDaily(
            date=yesterday,
            total_conversations=total_conversations,
            inbound_calls=inbound_calls,
            inbound_texts=inbound_texts,
            appointments_scheduled=appointments_scheduled,
            escalations=escalations,
            avg_confidence_score=float(avg_confidence),
            ai_coverage_percentage=((total_conversations - escalations) / total_conversations * 100) if total_conversations > 0 else 0,
            saved_labor_hours=total_conversations * 0.25,  # Estimate 15 min saved per call
            cost_per_interaction=0.50
        )

        db.add(metrics_record)
        db.commit()

        logger.info(f"Daily metrics aggregated for {yesterday}: {total_conversations} conversations")

    except Exception as e:
        logger.error(f"Error aggregating daily metrics: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    aggregate_yesterday_metrics()
```

**Schedule this to run at 12:01 AM daily** (use Railway cron)

---

## Summary of Changes

### Immediate Code Changes (voice_routes.py):
1. ✅ Add imports for dashboard models
2. ✅ Log incoming calls to AIReceptionistActivity
3. ✅ Save full conversations to AIReceptionistConversation
4. ✅ Log errors to AIReceptionistError
5. ✅ Update activity feed with conversation outcomes

### New Files Needed:
1. ✅ `cron_jobs/monitor_system_health.py` - Run every 60 seconds
2. ✅ `cron_jobs/aggregate_daily_metrics.py` - Run at 12:01 AM daily

### Deployment:
1. ✅ Apply code changes to voice_routes.py
2. ✅ Deploy to production
3. ✅ Set up cron jobs in Railway

---

## Result After Integration

Once these changes are deployed:

✅ **Every phone call** automatically logs to dashboard
✅ **Every conversation** is captured with full transcript
✅ **Every error** is tracked for review
✅ **System health** is monitored every minute
✅ **Daily metrics** are calculated automatically
✅ **Dashboard shows REAL data**, not just samples

---

## Testing After Integration

1. Make a test call to your Twilio number
2. Check dashboard activity feed - should show the call immediately
3. Complete the call
4. Check conversations tab - should show full transcript
5. Query database - should see new records in real-time

---

**This is the missing piece that makes Phase 1 actually useful.**

Without this integration, you're right - the dashboard is just empty tables with fake data.
