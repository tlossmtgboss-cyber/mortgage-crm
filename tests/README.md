# Pipeline360 Testing Suite

Comprehensive testing suite for the Pipeline360 Mortgage CRM application.

## Quick Start

```bash
# Run all tests against production
./tests/functional_tests.sh

# Run with test API key (bypasses IP restrictions)
TEST_API_KEY=your-key ./tests/functional_tests.sh
```

## Environment Configuration

### Test API Key

To run tests against environments with IP restrictions, set the `TEST_API_KEY`:

```bash
# Set in server .env
TEST_API_KEY=your-secure-random-key

# Use when running tests
TEST_API_KEY=your-secure-random-key ./tests/security_tests.sh
```

### Environment-Based Security

The security middleware behaves differently based on environment:

| Environment | IP Restrictions | Test API Key | Notes |
|-------------|-----------------|--------------|-------|
| development | None | N/A | All requests allowed |
| staging | Logged only | Supported | Relaxed for testing |
| production | Strict whitelist | Supported | Only whitelisted IPs |

## Test Scripts

### 1. Functional Tests (`functional_tests.sh`)

End-to-end tests for all major API endpoints.

```bash
./tests/functional_tests.sh [API_URL]

# Examples
./tests/functional_tests.sh https://staging-api.example.com
TEST_API_KEY=key ./tests/functional_tests.sh https://api.example.com
```

**Tests:**
- Authentication (login/token)
- Loans CRUD operations
- Leads CRUD operations
- Tasks CRUD operations
- Contacts CRUD operations
- Analytics endpoints
- AI Orchestrator
- Video clips (UVIP)
- Video meetings
- Reconciliation
- Financial Intelligence
- Unified Tasks

### 2. Security Tests (`security_tests.sh`)

Security vulnerability testing.

```bash
./tests/security_tests.sh [API_URL]

# Examples
./tests/security_tests.sh https://staging-api.example.com
TEST_API_KEY=key ./tests/security_tests.sh https://api.example.com
```

**Tests:**
- Unauthenticated request rejection
- Invalid token rejection
- Malformed token rejection
- Valid authentication
- XSS in query parameters
- SQL injection attempts
- Path traversal attempts
- Large payload handling
- Rate limiting
- CORS configuration
- Health endpoint accessibility
- Error handling (no stack trace leaks)

### 3. Load Tests (`load_test.py`)

Concurrent user simulation for performance testing.

```bash
python tests/load_test.py [API_URL] [options]

# Options
--users N       Number of concurrent users (default: 20)
--requests N    Requests per user (default: 5)
--token TOKEN   Auth token (fetches if not provided)
--api-key KEY   Test API key for IP bypass

# Examples
python tests/load_test.py --users 50 --requests 10
TEST_API_KEY=key python tests/load_test.py https://api.example.com
python tests/load_test.py --api-key your-key https://api.example.com
```

**Metrics:**
- Total requests & success rate
- Response times (avg, median, min, max)
- Percentiles (P95, P99)
- Requests per second
- Per-endpoint statistics

**Performance Targets:**
- EXCELLENT: avg < 0.5s, success > 99%
- GOOD: avg < 1.0s, success > 95%
- ACCEPTABLE: avg < 2.0s, success > 90%

### 4. Health Monitor (`health_monitor.sh`)

System health monitoring.

```bash
./tests/health_monitor.sh [API_URL] [--continuous]

# Examples
./tests/health_monitor.sh                           # Single check
./tests/health_monitor.sh --continuous              # Every 5 minutes
TEST_API_KEY=key ./tests/health_monitor.sh https://api.example.com
```

**Checks:**
- Basic health endpoint
- Detailed health (component status)
- Authentication endpoint
- API response time
- Documentation availability

## CI/CD Integration

### GitHub Actions Example

```yaml
name: Test Suite

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3

      - name: Run Security Tests
        env:
          TEST_API_KEY: ${{ secrets.TEST_API_KEY }}
        run: ./tests/security_tests.sh ${{ vars.STAGING_URL }}

      - name: Run Functional Tests
        env:
          TEST_API_KEY: ${{ secrets.TEST_API_KEY }}
        run: ./tests/functional_tests.sh ${{ vars.STAGING_URL }}

      - name: Run Load Tests
        env:
          TEST_API_KEY: ${{ secrets.TEST_API_KEY }}
        run: python tests/load_test.py ${{ vars.STAGING_URL }} --users 20 --requests 5
```

### Pre-deployment Checklist

1. **Security Tests**: All must pass
2. **Functional Tests**: All core endpoints must work
3. **Load Tests**: Must meet performance targets
4. **Health Check**: All systems healthy

## Staging Environment

Create a `.env.staging` file:

```bash
# Environment
ENVIRONMENT=staging

# Database (use separate staging DB)
DATABASE_URL=postgresql://user:pass@host:5432/mortgage_crm_staging

# Security (relaxed for staging)
TEST_API_KEY=your-staging-test-key
ADMIN_IP_1=your-office-ip
ADMIN_IP_2=your-vpn-ip

# External Services (staging keys)
OPENAI_API_KEY=sk-staging-key
ANTHROPIC_API_KEY=sk-ant-staging-key

# Monitoring (staging project)
SENTRY_DSN=https://staging-key@sentry.io/project
```

## Troubleshooting

### "Access denied" (403)

This indicates IP whitelist blocking. Solutions:
1. Use `TEST_API_KEY` environment variable
2. Add your IP to `ADMIN_IP_X` variables
3. Test against staging environment

### "Rate limit exceeded" (429)

The API has rate limiting:
- 60 requests/minute per IP
- 1000 requests/hour per IP

Wait or use different IP for testing.

### "Authentication failed"

Check:
1. Demo credentials are enabled
2. Token endpoint is accessible
3. Test API key is valid (if using)

### Slow Response Times

Possible causes:
- Cold start (Railway spins down idle instances)
- Database connection pooling
- External API calls (AI, integrations)

Run health check first to warm up the instance.
