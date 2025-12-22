# Chat State Machine - Operational Playbooks

## Table of Contents
1. [Call Failure Troubleshooting](#playbook-1-call-failure-troubleshooting)
2. [Phase Progression Issues](#playbook-2-phase-progression-issues)
3. [High Abandonment Rate](#playbook-3-high-abandonment-recovery)
4. [Low CTA Acceptance](#playbook-4-low-cta-acceptance)
5. [Production Deployment Checklist](#production-checklist)
6. [Monitoring & Alerts](#monitoring-alerts)

---

## Playbook 1: Call Failure Troubleshooting

### Symptoms
- High call failure rate (>30%)
- Calls not connecting
- Borrowers reporting no ring
- `failed_calls_hour` alert triggered

### Diagnostic Steps

#### 1. Check Twilio Console
```
Navigate to: Twilio Console > Monitor > Logs > Calls
Filter by: last 1 hour
Look for: Error patterns, status codes
```

#### 2. Common Errors & Fixes

**Error: "Invalid phone number"**
- **Cause**: Phone validation failing
- **Fix**: Check phone number formatting in frontend
- **Code**: Check `twilio_click_to_call.py` phone normalization

**Error: "Webhook timeout"**
- **Cause**: TwiML webhooks not responding
- **Fix**:
  ```bash
  # Check API health
  curl https://yourdomain.com/health

  # Verify BASE_URL env var
  echo $BASE_URL
  ```

**Error: "Line busy" / "No answer"**
- **Cause**: LO phone unavailable
- **Fix**:
  - Verify `LO_PHONE_NUMBER` in env
  - Test direct call to LO number
  - Check LO availability schedule

**Error: "Blacklisted number"**
- **Cause**: Number on carrier blocklist
- **Fix**: Contact Twilio support for number verification

#### 3. Rate Limit Check
```bash
# Check Redis rate limit keys
redis-cli KEYS "fastapi-limiter:*"

# Check call volume
psql -c "SELECT COUNT(*) FROM call_requests WHERE created_at > NOW() - INTERVAL '1 hour'"
```

#### 4. Fallback Actions
- If failure rate > 30%: Enable SMS-only mode temporarily
- If outside business hours: Verify hours configuration
- Send alert to operations team via Slack/PagerDuty

### Resolution Verification
```bash
# Run test call
curl -X POST https://yourdomain.com/api/v1/calls/test \
  -H "Authorization: Bearer $API_KEY" \
  -d '{"phone": "+1555123456"}'
```

---

## Playbook 2: Phase Progression Issues

### Symptoms
- Sessions stuck in Phase 1 or 2
- Low Phase 4 conversion rate (<20%)
- Intent score not increasing
- `low_phase_4_rate` alert triggered

### Diagnostic Steps

#### 1. Review Stuck Sessions
```sql
-- Get sample stuck sessions
SELECT id, turn_count, intent_score, intent_signals, current_phase
FROM chat_sessions
WHERE current_phase = 1
  AND turn_count >= 5
  AND created_at > NOW() - INTERVAL '24 hours'
LIMIT 10;
```

#### 2. Analyze Intent Detection
```sql
-- Check which signals are being detected
SELECT
    signal->>'signal' as signal_type,
    COUNT(*) as count
FROM chat_sessions,
LATERAL jsonb_array_elements(intent_signals) as signal
WHERE created_at > NOW() - INTERVAL '24 hours'
GROUP BY signal->>'signal'
ORDER BY count DESC;
```

#### 3. Test Intent Detection Manually
```python
# Run in Python console
from backend.services.chat_session_manager import ChatSessionManager
from backend.services.enhanced_intent_detector import EnhancedIntentDetector

detector = EnhancedIntentDetector()
test_message = "I'm looking at a house for $350k in Charleston"
signals = detector.detect(test_message)
print(signals)  # Should detect: property, price, location
```

#### 4. Common Issues

**Issue: Keywords not matching**
- Check `INTENT_PATTERNS` in `chat_session_manager.py`
- Add missing keywords/variations
- Test regex patterns

**Issue: Thresholds too high**
- Review phase transition logic in `ChatSession.should_advance_phase()`
- Consider lowering `intent_score` requirements temporarily

**Issue: AI responses not asking questions**
- Review phase prompts in `chat_prompt_constructor.py`
- Ensure "QUESTIONS TO EXPLORE" section is present for Phase 3

### Fix Actions
1. Update `INTENT_PATTERNS` with missing keywords
2. Adjust phase transition thresholds if too aggressive
3. Refine system prompts for better question-asking
4. Run simulation tests after changes

---

## Playbook 3: High Abandonment Recovery

### Symptoms
- Many Phase 3/4 sessions going silent
- High intent scores but no CTA acceptance
- `abandoned_high_intent` alert triggered

### Immediate Actions

#### 1. Identify Abandoned Sessions
```python
from backend.services.abandoned_session_recovery import AbandonedSessionRecovery

recovery = AbandonedSessionRecovery(db)
abandoned = await recovery.find_abandoned_sessions(
    hours_inactive=2,
    min_intent_score=60
)
print(f"Found {len(abandoned)} abandoned sessions")
```

#### 2. Generate LO Follow-up Queue
```python
queue = await recovery.get_recovery_queue(limit=20)
for item in queue:
    print(f"Priority: {item['priority']}")
    print(f"Contact: {item['contact']}")
    print(f"Summary: {item['conversation_summary']}")
    print(f"Approach: {item['recovery_approach']}")
    print("---")
```

#### 3. Export for CRM
```sql
-- Export to CSV for LO follow-up
COPY (
    SELECT
        id,
        contact_name,
        contact_phone,
        contact_email,
        intent_score,
        current_phase,
        last_message_at,
        intent_signals
    FROM chat_sessions
    WHERE intent_score >= 70
      AND current_phase >= 3
      AND cta_accepted = false
      AND last_message_at < NOW() - INTERVAL '2 hours'
      AND last_message_at > NOW() - INTERVAL '7 days'
    ORDER BY intent_score DESC
) TO '/tmp/abandoned_leads.csv' WITH CSV HEADER;
```

### Process Improvements

#### Review CTA Timing
- Is CTA offered too early (aggressive)?
- Is CTA offered too late (missing opportunity)?
- Check average turn count when CTA is offered

#### Review CTA Messaging
- Is the CTA pressure-free?
- Does it offer alternatives?
- Add "Not ready yet? That's okay" messaging

#### Add Soft Exit Options
- "I can send you some information to review"
- "Feel free to come back when you're ready"

---

## Playbook 4: Low CTA Acceptance

### Symptoms
- CTAs being offered but not accepted
- CTA acceptance rate < 10%
- Users frequently declining

### Diagnostic Steps

#### 1. Analyze CTA Performance
```sql
SELECT
    cta_offered,
    COUNT(*) as offered,
    SUM(CASE WHEN cta_accepted THEN 1 ELSE 0 END) as accepted,
    ROUND(AVG(CASE WHEN cta_accepted THEN 1.0 ELSE 0.0 END) * 100, 2) as acceptance_rate
FROM chat_sessions
WHERE cta_offered IS NOT NULL
  AND created_at > NOW() - INTERVAL '7 days'
GROUP BY cta_offered;
```

#### 2. Review Decline Patterns
```sql
-- Find sessions with declines
SELECT
    id,
    current_phase,
    intent_score,
    cta_offered,
    cta_declined_count,
    turn_count
FROM chat_sessions
WHERE cta_declined_count > 0
  AND created_at > NOW() - INTERVAL '7 days'
ORDER BY created_at DESC
LIMIT 20;
```

#### 3. Read Actual Conversations
```sql
-- Get conversation leading to decline
SELECT
    role,
    content,
    cta_presented,
    cta_response
FROM chat_messages
WHERE session_id = '<session_id>'
ORDER BY created_at;
```

### Common Issues & Fixes

**Issue: CTA too aggressive**
- Adjust Phase 4 prompt to be softer
- Add more value proposition before asking

**Issue: Wrong CTA type offered**
- Review CTA selection logic in `get_cta_recommendation()`
- Match CTA to user's expressed preferences

**Issue: Bad timing (user still exploring)**
- Tighten phase advancement requirements
- Require higher intent score for CTA phase

**Issue: Missing business hours check**
- Verify `BusinessHoursService` is being called
- Offer "schedule" instead of "call_now" after hours

---

## Production Checklist

### Database
- [ ] Performance indexes created (`add_chat_performance_indexes.sql`)
- [ ] Backup strategy implemented (daily snapshots)
- [ ] Connection pooling configured (PgBouncer or built-in)
- [ ] Read replicas for analytics queries (if high traffic)
- [ ] Table partitioning for messages table (if >10M rows)

### API
- [ ] Rate limiting enabled (per IP, per session)
- [ ] CORS properly configured for microsite domains
- [ ] Health check endpoint functional
- [ ] Error logging to Sentry/CloudWatch
- [ ] Request timeouts set (30s for AI calls)
- [ ] Graceful shutdown handling

### Twilio
- [ ] Phone number provisioned
- [ ] Webhook URLs registered and verified
- [ ] TwiML bins created (if using)
- [ ] Call recording enabled (for compliance)
- [ ] Fallback SMS configured
- [ ] Geographic permissions set

### Security
- [ ] Sensitive data detection active
- [ ] HTTPS enforced
- [ ] API keys in secure vault (AWS Secrets Manager, etc.)
- [ ] Database credentials rotated
- [ ] GDPR compliance reviewed
- [ ] PII encryption at rest

### Monitoring
- [ ] Real-time dashboard deployed
- [ ] Alert thresholds configured
- [ ] On-call rotation established
- [ ] Playbooks documented (this file)
- [ ] Slack/PagerDuty integration

### Testing
- [ ] Load testing completed (100 concurrent chats)
- [ ] Conversation templates validated
- [ ] Call flow tested end-to-end
- [ ] Analytics queries performance tested
- [ ] Failover tested

---

## Monitoring & Alerts

### Key Metrics to Monitor

| Metric | Warning Threshold | Critical Threshold |
|--------|-------------------|-------------------|
| Call Failure Rate | > 20% | > 30% |
| Phase 4 Rate | < 25% | < 15% |
| CTA Acceptance Rate | < 15% | < 10% |
| Abandoned High-Intent | > 5/hour | > 10/hour |
| API Response Time | > 2s | > 5s |
| Active Sessions | 0 during business hours | N/A |

### Alert Configuration

```yaml
# alerts.yml
alerts:
  - name: call_failure_rate
    condition: "failure_rate > 0.30"
    severity: high
    channels: [slack, pagerduty]
    message: "Call failure rate at {value}% - check Twilio"

  - name: abandoned_high_intent
    condition: "count > 10"
    severity: medium
    channels: [slack]
    message: "{count} high-intent sessions abandoned - LO follow-up needed"

  - name: low_phase_4_rate
    condition: "rate < 0.15"
    severity: low
    channels: [slack]
    message: "Only {rate}% reaching Phase 4 - review intent detection"
```

### Daily Health Check

```bash
#!/bin/bash
# daily_health_check.sh

echo "=== Chat System Health Check ==="
echo "Date: $(date)"

# API Health
curl -s http://localhost:8000/health | jq .

# Session counts
psql -c "SELECT
    COUNT(*) as total_24h,
    COUNT(CASE WHEN cta_accepted THEN 1 END) as converted
FROM chat_sessions
WHERE created_at > NOW() - INTERVAL '24 hours'"

# Call success rate
psql -c "SELECT
    COUNT(*) as total,
    COUNT(CASE WHEN status = 'completed' THEN 1 END) as success,
    ROUND(COUNT(CASE WHEN status = 'completed' THEN 1 END)::numeric /
          NULLIF(COUNT(*), 0) * 100, 2) as rate
FROM call_requests
WHERE created_at > NOW() - INTERVAL '24 hours'"

echo "=== Check Complete ==="
```

---

## Support Contacts

- **Engineering On-Call**: #chat-oncall Slack channel
- **Twilio Support**: https://support.twilio.com
- **Anthropic Support**: support@anthropic.com
- **Database Admin**: dba@company.com

---

*Last Updated: December 2025*
*Version: 1.0*
