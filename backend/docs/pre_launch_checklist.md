# Perennia AI Chat System - Pre-Launch Checklist

## Overview
This checklist ensures a smooth production launch of the Perennia AI Chat System. Complete all items before go-live.

---

## 1. Database Setup

- [ ] Run schema migrations: `alembic upgrade head`
- [ ] Run chat tables migration: `psql -d mortgage_crm -f migrations/create_chat_state_machine_tables.sql`
- [ ] Run performance indexes: `psql -d mortgage_crm -f migrations/add_chat_performance_indexes.sql`
- [ ] Verify connection pooling: Check DB_POOL_SIZE in config
- [ ] Set up read replicas (if high traffic expected)
- [ ] Configure automated backups (daily + point-in-time recovery)
- [ ] Test database failover procedure
- [ ] Verify all 27 indexes created successfully

## 2. Redis Configuration

- [ ] Redis instance provisioned (AWS ElastiCache recommended)
- [ ] Persistence enabled (AOF + RDB)
- [ ] Memory limit set appropriately (minimum 1GB recommended)
- [ ] Eviction policy configured: `allkeys-lru`
- [ ] Monitor memory usage alerts
- [ ] Test Redis failover
- [ ] Verify connection from application

## 3. Environment Variables

Required environment variables:

```bash
# Application
ENVIRONMENT=production
VERSION=1.0.0
DEBUG=false

# Database
DATABASE_URL=postgresql://user:pass@host:5432/mortgage_crm
DB_POOL_SIZE=20

# Redis
REDIS_URL=redis://host:6379/0

# Anthropic AI
ANTHROPIC_API_KEY=sk-ant-...
ANTHROPIC_MODEL=claude-sonnet-4-20250514

# Twilio
TWILIO_ACCOUNT_SID=AC...
TWILIO_AUTH_TOKEN=...
TWILIO_PHONE_NUMBER=+1...
LO_PHONE_NUMBER=+1...

# URLs
BASE_URL=https://yourdomain.com
ALLOWED_ORIGINS=["https://yourdomain.com","https://app.yourdomain.com"]

# Circuit Breaker
CIRCUIT_BREAKER_FAILURE_THRESHOLD=5
CIRCUIT_BREAKER_RECOVERY_TIMEOUT=30

# Monitoring
SENTRY_DSN=https://...@sentry.io/...
LOG_LEVEL=INFO
```

- [ ] All secrets in secure vault (AWS Secrets Manager / Vault)
- [ ] Production .env file configured
- [ ] No hardcoded credentials in code
- [ ] API keys have appropriate permissions
- [ ] Backup .env stored securely

## 4. Anthropic API

- [ ] API key valid and has sufficient credits
- [ ] Rate limits understood (check tier)
- [ ] Billing alerts configured
- [ ] Monitor token usage
- [ ] Test API connectivity
- [ ] Circuit breaker properly configured

## 5. Twilio Setup

- [ ] Phone number provisioned
- [ ] TwiML webhook URLs registered:
  - `/api/v1/twilio/voice/incoming`
  - `/api/v1/twilio/voice/status`
  - `/api/v1/twilio/voice/connect`
- [ ] Webhook URLs use HTTPS
- [ ] Test inbound/outbound calls
- [ ] Configure call recording (compliance)
- [ ] Set up fallback URLs
- [ ] Monitor call quality metrics
- [ ] Whisper message configured for LO

## 6. Application Deployment

- [ ] Docker images built and tagged
- [ ] Container registry configured (ECR/Docker Hub)
- [ ] Health check endpoints tested:
  - `/health` - Basic health
  - `/health/detailed` - Full status
  - `/health/ready` - Kubernetes readiness
  - `/health/live` - Kubernetes liveness
- [ ] Load balancer configured
- [ ] SSL/TLS certificates installed
- [ ] Auto-scaling policies defined
- [ ] Resource limits set (CPU/memory)

## 7. Security

- [ ] HTTPS enforced (no HTTP)
- [ ] CORS properly configured
- [ ] Rate limiting enabled:
  - Chat messages: 60/min
  - Session creation: 10/hour
  - Call initiation: 3/hour
- [ ] Input validation on all endpoints
- [ ] SQL injection prevention verified
- [ ] XSS protection enabled
- [ ] Sensitive data detection active
- [ ] Security headers configured
- [ ] Penetration testing completed

## 8. Monitoring & Alerting

- [ ] Structured logging configured (JSON format)
- [ ] Log aggregation setup (CloudWatch/DataDog)
- [ ] Error tracking (Sentry)
- [ ] Uptime monitoring (Pingdom/UptimeRobot)
- [ ] Performance monitoring (APM)

### Alert Thresholds

| Metric | Warning | Critical |
|--------|---------|----------|
| Error rate | >3% | >5% |
| Call failure rate | >20% | >30% |
| P95 latency | >2s | >3s |
| Circuit breaker | - | OPEN |
| Cache hit rate | <60% | <40% |
| DB connection pool | >80% | >95% |
| Abandoned session rate | >50% | >70% |

- [ ] On-call rotation established
- [ ] Incident response playbook ready
- [ ] PagerDuty/Opsgenie configured

## 9. Performance Testing

- [ ] Load testing completed (100 concurrent users)
- [ ] Stress testing completed (identify breaking point)

### Latency Benchmarks

| Endpoint | Target P50 | Target P95 | Target P99 |
|----------|------------|------------|------------|
| Chat message | <1s | <2s | <3s |
| Session creation | <200ms | <500ms | <1s |
| Session recovery | <300ms | <600ms | <1s |
| Analytics queries | <1s | <3s | <5s |

- [ ] Database query performance verified
- [ ] Cache hit rate validated (target >60%)
- [ ] Memory leak testing completed
- [ ] Connection pool sizing validated

## 10. Functional Testing

### Conversation Flow
- [ ] All 4 phases tested (Reassure → Educate → Personalize → Earned CTA)
- [ ] Phase transitions validated
- [ ] Intent detection accuracy verified (>80% accuracy)
- [ ] CTA selection logic tested (CALL_NOW, SCHEDULE, APPLICATION)

### Call Flow
- [ ] Click-to-call flow tested end-to-end
- [ ] Whisper message plays for LO
- [ ] Call status callbacks work
- [ ] Fallback to voicemail tested

### Reliability Features
- [ ] Sensitive data blocking verified
- [ ] Session recovery tested (visitor_id, user_id, phone)
- [ ] Cross-device continuity tested
- [ ] Business hours gating tested
- [ ] Rate limiting tested
- [ ] Circuit breaker tested (force failures)
- [ ] Graceful degradation tested (kill Redis, simulate AI failure)

## 11. Data & Compliance

- [ ] TCPA compliance verified (call consent)
- [ ] Privacy policy updated
- [ ] Terms of service updated
- [ ] Data retention policy defined (default: 90 days for sessions)
- [ ] GDPR compliance reviewed (if applicable)
- [ ] PII handling procedures documented
- [ ] Data export/deletion procedures ready
- [ ] Audit logging enabled

## 12. Documentation

- [ ] API documentation generated (Swagger/OpenAPI)
- [ ] Operational playbooks finalized
- [ ] Architecture diagram updated
- [ ] Deployment guide written
- [ ] Troubleshooting guide written
- [ ] Runbook for common issues
- [ ] LO training materials prepared

## 13. Rollout Strategy

- [ ] Gradual rollout plan defined:
  - Day 1: 10% traffic
  - Day 2: 25% traffic
  - Day 3: 50% traffic
  - Day 5: 100% traffic
- [ ] Feature flags configured (if needed)
- [ ] Rollback procedure documented
- [ ] Monitoring dashboard ready

### Success Metrics

| Metric | Target |
|--------|--------|
| Phase 4 reach rate | >40% |
| CTA acceptance rate | >25% |
| Call connection rate | >70% |
| Average quality score | >70 |
| Session abandonment rate | <50% |

- [ ] A/B testing plan (if applicable)

## 14. Go-Live Day

### Morning of Launch
- [ ] All team members briefed
- [ ] Support team trained
- [ ] Escalation contacts confirmed
- [ ] Backup systems verified
- [ ] Communication plan ready

### Launch Sequence
```bash
# 1. Pre-launch validation
./scripts/pre_launch_checks.sh

# 2. Deploy database migrations
psql -d mortgage_crm -f migrations/create_chat_state_machine_tables.sql
psql -d mortgage_crm -f migrations/add_chat_performance_indexes.sql

# 3. Build and deploy containers
docker-compose -f docker-compose.chat-production.yml build
docker-compose -f docker-compose.chat-production.yml up -d

# 4. Verify health
curl https://yourdomain.com/health/detailed

# 5. Run smoke tests
python -m testing.chat_simulator --all

# 6. Monitor logs
docker-compose -f docker-compose.chat-production.yml logs -f api
```

- [ ] Status page prepared
- [ ] Initial traffic monitoring active
- [ ] War room setup (first 24 hours)

## 15. Post-Launch (First Week)

### Day 1
- [ ] Monitor error rates (<1%)
- [ ] Monitor latency (<2s P95)
- [ ] Review first 50 conversations
- [ ] Check cache hit rate (>60%)
- [ ] Verify call connections

### Days 2-3
- [ ] Daily metrics review
- [ ] Conversation quality spot-checks
- [ ] User feedback collection
- [ ] Bug fix prioritization

### Days 4-7
- [ ] Performance optimization
- [ ] Feature refinement based on usage
- [ ] Documentation updates
- [ ] Prepare weekly report

---

## Success Metrics Dashboard (First 30 Days)

### Engagement Metrics
- Sessions created: Target >1000/day
- Average session duration: Target >3 minutes
- Messages per session: Target >5
- Returning visitor rate: Target >20%

### Conversion Metrics
- Phase 4 reach rate: Target >40%
- CTA offered rate: Target >35%
- CTA acceptance rate: Target >25%
- Call connection rate: Target >70%
- Application starts: Target >50/day

### Quality Metrics
- Average quality score: Target >70
- Low engagement rate: Target <15%
- Borrower confusion rate: Target <5%
- Average intent score at CTA: Target >75

### Technical Metrics
- Uptime: Target >99.9%
- P95 latency: Target <2s
- Error rate: Target <1%
- Cache hit rate: Target >60%
- Circuit breaker opens: Target <5/day

---

## Emergency Contacts

| Role | Name | Phone | Email |
|------|------|-------|-------|
| Tech Lead | | | |
| DevOps | | | |
| Product Owner | | | |
| On-Call | | | |

---

## Rollback Procedure

If critical issues are found:

```bash
# 1. Pause traffic (via load balancer or feature flag)

# 2. Check logs for root cause
docker-compose -f docker-compose.chat-production.yml logs --tail=1000 api

# 3. Roll back to previous version
docker-compose -f docker-compose.chat-production.yml down
docker-compose -f docker-compose.chat-production.yml up -d --force-recreate

# 4. Verify rollback
curl https://yourdomain.com/health/detailed

# 5. Resume traffic

# 6. Post-mortem within 24 hours
```

---

*Last updated: 2024*
*Version: 1.0*
