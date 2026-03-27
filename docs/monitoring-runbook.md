# Perennia AI — Production Monitoring Runbook

## Service Architecture

| Component | Host | Purpose |
|-----------|------|---------|
| Backend API | Railway (api.perenniaai.com) | FastAPI application |
| Frontend SPA | Vercel (app.perenniaai.com) | React 18 application |
| Database | Railway PostgreSQL | Primary data store |
| Cache | Railway Redis | Session cache, rate limiting, Celery broker |
| Workers | Railway (Celery) | Background tasks, briefing generation |

## Monitoring Stack

### DataDog APM
- **Env vars**: `DD_API_KEY`, `DD_APP_KEY`, `DD_SERVICE=mortgage-crm`, `DD_ENV`
- **Init**: `backend/datadog_monitoring.py` → `setup_datadog_monitoring(app)`
- **Traces**: All FastAPI endpoints auto-instrumented via ddtrace
- **Custom metrics**: `business_metrics` module for pipeline/agent tracking

### Sentry Error Tracking
- **Env var**: `SENTRY_DSN`
- **Init**: `backend/production_hardening.py` → `sentry_sdk.init()`
- **Integrations**: FastAPI, SQLAlchemy, Logging (errors auto-captured)
- **PII**: `send_default_pii=False` — no PII sent to Sentry
- **Sampling**: 10% traces in production, 100% in development

## Health Endpoints

| Endpoint | Purpose | Expected Response |
|----------|---------|-------------------|
| `GET /` | Root info | `{"status": "operational"}` |
| `GET /health` | Basic health (DB check) | `{"status": "healthy"}` or 503 |
| `GET /health/ready` | Readiness probe (DB + Redis) | `{"status": "ready"}` or 503 |
| `GET /ready` | Alias for `/health/ready` | Same as above |
| `GET /health/detailed` | Full system status | Detailed component health |

## Key Metrics to Monitor

### API Performance
| Metric | Warning | Critical | Action |
|--------|---------|----------|--------|
| p95 latency | > 500ms | > 2000ms | Check slow queries, N+1 patterns |
| p99 latency | > 2000ms | > 5000ms | Scale workers, check connection pool |
| Error rate (5xx) | > 0.5% | > 2% | Check Sentry, review recent deploys |
| Request throughput | < 10 RPS | < 5 RPS | Check DNS, load balancer, deployment |

### Database
| Metric | Warning | Critical | Action |
|--------|---------|----------|--------|
| Connection pool utilization | > 70% | > 90% | Increase pool_size in db.py |
| Slow queries (> 1s) | > 5/min | > 20/min | Add indexes, optimize queries |
| Deadlocks | Any | > 3/min | Review concurrent write patterns |
| DB size growth | > 1GB/week | > 5GB/week | Check for runaway logging, add retention |

### Background Workers (Celery)
| Metric | Warning | Critical | Action |
|--------|---------|----------|--------|
| Queue depth | > 100 tasks | > 500 tasks | Scale workers, check for stuck tasks |
| Task failure rate | > 5% | > 15% | Check Sentry for task errors |
| Briefing generation time | > 30s | > 60s | Check LLM API latency |
| Worker heartbeat | Missing > 2 min | Missing > 5 min | Restart workers, check Redis |

### AI Agents
| Metric | Warning | Critical | Action |
|--------|---------|----------|--------|
| Agent response time | > 5s | > 15s | Check LLM provider status |
| Token budget per query | > 15K | > 20K | Review prompt sizes, context length |
| Agent error rate | > 5% | > 10% | Check API keys, rate limits |
| Hallucination flags | Any | > 3/day | Review RAG pipeline, embedding freshness |

### Voice/Telephony
| Metric | Warning | Critical | Action |
|--------|---------|----------|--------|
| Telnyx API errors | > 1% | > 5% | Check API key, account balance |
| SMS delivery rate | < 95% | < 90% | Check phone number reputation |
| Voice workflow expiry rate | > 20% | > 40% | Adjust DEFAULT_EXPIRY_HOURS |
| Webhook processing time | > 2s | > 5s | Check webhook handler performance |

## Alert Configuration

### DataDog Monitors (Recommended)
```yaml
# API Health
- name: "API Error Rate High"
  type: metric alert
  query: "avg(last_5m):sum:trace.fastapi.request.errors{service:mortgage-crm} / sum:trace.fastapi.request.hits{service:mortgage-crm} > 0.02"
  critical: 0.02
  warning: 0.005

# Database
- name: "Database Connection Pool Saturated"
  type: metric alert
  query: "avg(last_5m):avg:postgresql.connections{service:mortgage-crm} > 18"
  critical: 18
  warning: 14

# Worker Health
- name: "Celery Queue Depth"
  type: metric alert
  query: "avg(last_10m):avg:celery.queue.length{service:mortgage-crm} > 500"
  critical: 500
  warning: 100
```

### Sentry Alert Rules (Recommended)
- **New issue**: Notify on first occurrence of any new error
- **Regression**: Alert when a resolved issue re-occurs
- **Spike**: Alert when error frequency exceeds 10x baseline in 1 hour
- **Unhandled**: All unhandled exceptions → immediate PagerDuty/Slack

## Escalation Procedures

### Severity 1 — Service Down
1. Check Railway deployment status
2. Check `/health` endpoint
3. Review Railway logs for crash loops
4. If DB down: Check Railway PostgreSQL dashboard
5. Escalate to on-call engineer

### Severity 2 — Degraded Performance
1. Check DataDog APM for slow endpoints
2. Check `pg_stat_activity` for long-running queries
3. Check Redis memory usage
4. Review recent deploys for regression

### Severity 3 — Feature Broken
1. Check Sentry for related errors
2. Review feature-specific logs
3. Check integration health (Twilio, Telnyx, Salesforce, Encompass)

## Railway Environment Variables Checklist

| Variable | Purpose | Required |
|----------|---------|----------|
| `DATABASE_URL` | PostgreSQL connection | Yes |
| `REDIS_URL` | Redis connection | Yes |
| `SECRET_KEY` | JWT signing | Yes |
| `DD_API_KEY` | DataDog APM | Recommended |
| `DD_APP_KEY` | DataDog dashboards | Optional |
| `SENTRY_DSN` | Error tracking | Recommended |
| `SENDGRID_API_KEY` | Email delivery | Yes (for briefings) |
| `TELNYX_API_KEY` | SMS/telephony | Yes (for voice features) |
| `OPENAI_API_KEY` | AI agents | Yes |
| `ENVIRONMENT` | production/staging/dev | Yes |
