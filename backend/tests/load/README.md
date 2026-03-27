# Perennia AI — Load Test Suite

Locust-based load tests targeting key API endpoints.
Validates performance of the 47 database indexes added during the enterprise hardening phase.

## Prerequisites

```bash
pip install locust
```

Locust requires Python 3.8+. It is already included in `backend/requirements.txt` as a dev dependency.

## Configuration

Authentication is optional. When omitted, only the health-probe endpoints are tested in a meaningful way (all other endpoints will return 401/403, which the suite handles gracefully).

```bash
export LOCUST_EMAIL="your@email.com"
export LOCUST_PASSWORD="yourpassword"
```

## Usage

All commands are run from the `backend/` directory.

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
# Open http://localhost:8089 to configure and start the test
```

### Local development target

```bash
locust -f tests/load/locustfile.py --host=http://localhost:8000 --headless --users 10 --spawn-rate 2 --run-time 1m
```

## User classes and traffic weights

| Class | Weight | Task set | Description |
|---|---|---|---|
| `HealthCheckUser` | 1 | `HealthCheckTasks` | `GET /health`, `GET /ready` — no auth required |
| `PipelineUser` | 5 | `PipelineTasks` | Dashboard, leads, loans, tasks, search — primary LO workflow |
| `CalendarUser` | 3 | `CalendarTasks` | Calendar events, slots, smart-scheduler availability |
| `AdminUser` | 1 | `AdminTasks` | Admin user list, compliance dashboard |

With 50 virtual users the weights resolve to approximately: 5 HealthCheck, 25 Pipeline, 15 Calendar, 5 Admin.

## Endpoints under test

| Endpoint | Method | Tag | Slow-warning threshold |
|---|---|---|---|
| `/health` | GET | health | 500 ms |
| `/ready` | GET | health | 500 ms |
| `/api/v1/dashboard/metrics` | GET | pipeline | 500 ms |
| `/api/v1/leads?limit=50` | GET | pipeline | 500 ms |
| `/api/v1/loans?limit=50` | GET | pipeline | 500 ms |
| `/api/v1/loans?stage=PROCESSING` | GET | pipeline | 500 ms |
| `/api/v1/tasks` | GET | pipeline | 500 ms |
| `/api/v1/leads/search` | POST | pipeline | 1 000 ms |
| `/api/v1/calendar/events` | GET | calendar | 500 ms |
| `/api/v1/calendar/slots` | GET | calendar | 500 ms |
| `/api/v1/smart-scheduler/available-slots` | GET | calendar | 500 ms |
| `/api/v1/admin/users` | GET | admin | 500 ms |
| `/api/v1/compliance/dashboard` | GET | admin | 500 ms |

## How to read results

After a headless run, open the generated HTML report in your browser. Key columns:

- **RPS** — requests per second; higher is better.
- **Failures** — any non-2xx/non-expected response that was explicitly marked as failure.
- **Median / 95%ile / 99%ile** — response time percentiles in milliseconds.

The suite also logs a plain-text summary at the end of each run (visible in `--headless` stdout).

## Target thresholds

| Metric | Warning | Critical |
|---|---|---|
| p95 latency (read endpoints) | > 500 ms | > 2 000 ms |
| p95 latency (write endpoints) | > 1 000 ms | > 3 000 ms |
| Error rate | > 0.1% | > 1% |
| Throughput | < 50 RPS | < 20 RPS |

The suite will exit with code `1` when the error rate exceeds the **Critical** threshold (1%).
Slow-response warnings are logged to stdout but do not cause a non-zero exit — treat them as signals for investigation rather than hard failures.

## Tags

Use `--tags` to run a subset of tasks:

```bash
# Health probes only
locust -f tests/load/locustfile.py --host=... --tags health

# Pipeline workflow only
locust -f tests/load/locustfile.py --host=... --tags pipeline

# Calendar endpoints only
locust -f tests/load/locustfile.py --host=... --tags calendar
```

## CI integration

Add the smoke profile to your CI pipeline:

```yaml
- name: Smoke load test
  env:
    LOCUST_EMAIL: ${{ secrets.LOAD_TEST_EMAIL }}
    LOCUST_PASSWORD: ${{ secrets.LOAD_TEST_PASSWORD }}
  run: |
    locust -f backend/tests/load/locustfile.py \
      --host=${{ env.API_URL }} \
      --headless --users 10 --spawn-rate 2 --run-time 1m
```

The non-zero exit code on critical error rate will fail the CI step automatically.
