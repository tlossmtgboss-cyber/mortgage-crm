# Perennia AI — Load Test Suite

Locust-based load tests simulating loan officer workflows against the Perennia API.

## Prerequisites

```bash
pip install locust
```

## Configuration

Set credentials to test authenticated endpoints. Without these, only health probes run meaningfully.

```bash
export LOCUST_EMAIL="your@email.com"
export LOCUST_PASSWORD="yourpassword"
```

## Usage

All commands run from the `backend/` directory.

### Headless (CI) mode

#### Smoke — quick sanity check (1 minute)

```bash
locust -f tests/load/locustfile.py \
  --host=https://api.perenniaai.com \
  --headless \
  --users 10 \
  --spawn-rate 2 \
  --run-time 1m \
  --html=tests/load/smoke-report.html
```

#### Normal — sustained load (5 minutes)

```bash
locust -f tests/load/locustfile.py \
  --host=https://api.perenniaai.com \
  --headless \
  --users 50 \
  --spawn-rate 5 \
  --run-time 5m \
  --html=tests/load/normal-report.html
```

#### Stress — peak load (10 minutes)

```bash
locust -f tests/load/locustfile.py \
  --host=https://api.perenniaai.com \
  --headless \
  --users 200 \
  --spawn-rate 10 \
  --run-time 10m \
  --html=tests/load/stress-report.html
```

### Interactive (web UI) mode

```bash
locust -f tests/load/locustfile.py --host=https://api.perenniaai.com
# Open http://localhost:8089
```

### Local development

```bash
locust -f tests/load/locustfile.py \
  --host=http://localhost:8000 \
  --headless \
  --users 10 \
  --spawn-rate 2 \
  --run-time 1m
```

## User classes

| Class | Weight | Description |
|---|---|---|
| `LoanOfficerUser` | 10 | Primary LO workflow: leads (50%), dashboard (20%), tasks (15%), AI chat (10%), notifications (5%) |
| `LoanPipelineUser` | 3 | Loan-focused LO: loan list, stage filters, dashboard |
| `HealthCheckUser` | 1 | Health probes only (`/health`, `/health/live`) — no auth |

With 200 virtual users the weights resolve to approximately: 143 LoanOfficer, 43 LoanPipeline, 14 HealthCheck.

## Endpoints under test

| Endpoint | Method | Weight | Auth |
|---|---|---|---|
| `/health` | GET | — | No |
| `/health/live` | GET | — | No |
| `/api/v1/leads/` | GET | 50% | Yes |
| `/api/v1/dashboard/metrics` | GET | 20% | Yes |
| `/api/v1/tasks/` | GET | 15% | Yes |
| `/api/v1/ai/chat` | POST | 10% | Yes |
| `/api/v1/notifications/` | GET | 5% | Yes |
| `/api/v1/loans/` | GET | — | Yes |
| `/api/v1/loans/?stage=PROCESSING` | GET | — | Yes |

## Thresholds (enforced in CI)

| Metric | Threshold | Action |
|---|---|---|
| p95 latency | > 800 ms | Exit code 1 |
| Error rate | > 0.5% | Exit code 1 |

The suite exits non-zero when any threshold is breached, failing the CI step automatically.

## Tags

Run a subset of tasks with `--tags`:

```bash
# Pipeline only
locust -f tests/load/locustfile.py --host=... --tags pipeline

# AI chat only
locust -f tests/load/locustfile.py --host=... --tags ai

# Health probes only
locust -f tests/load/locustfile.py --host=... --tags health
```

## CI integration

The nightly load test workflow runs automatically via `.github/workflows/load-test.yml`. It targets staging with 200 users for 5 minutes and fails if p95 > 800ms or error rate > 0.5%.
