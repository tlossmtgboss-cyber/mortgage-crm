# Load Testing Suite

This directory contains load testing configurations for the Mortgage CRM.

## Tools

- **k6**: Modern load testing tool with JavaScript scripting
- **Locust**: Python-based load testing framework (alternative)

## Quick Start

### Using k6

```bash
# Install k6
brew install k6  # macOS
# or
sudo apt install k6  # Ubuntu

# Run basic load test
k6 run k6/loan-application-test.js

# Run with custom VUs and duration
k6 run --vus 100 --duration 5m k6/loan-application-test.js

# Run with environment variables
k6 run -e BASE_URL=https://api.staging.mortgagecrm.com \
       -e AUTH_TOKEN=your-token \
       k6/loan-application-test.js

# Run with cloud output (k6 cloud)
k6 cloud k6/loan-application-test.js
```

### Using Locust

```bash
# Install locust
pip install locust

# Run locust
locust -f locust/locustfile.py --host=https://api.mortgagecrm.com

# Headless mode
locust -f locust/locustfile.py \
       --host=https://api.mortgagecrm.com \
       --users 100 \
       --spawn-rate 10 \
       --run-time 5m \
       --headless
```

## Test Scenarios

### 1. Smoke Test
Quick validation that the system works under minimal load.
```bash
k6 run --vus 5 --duration 1m k6/loan-application-test.js
```

### 2. Load Test
Normal expected load to validate performance.
```bash
k6 run --vus 50 --duration 10m k6/loan-application-test.js
```

### 3. Stress Test
Push the system beyond normal capacity.
```bash
k6 run --vus 200 --duration 15m k6/loan-application-test.js
```

### 4. Spike Test
Sudden traffic spike simulation.
```bash
k6 run k6/spike-test.js
```

### 5. Soak Test
Extended duration test for memory leaks and stability.
```bash
k6 run --vus 50 --duration 2h k6/loan-application-test.js
```

## Performance Targets (SLOs)

| Metric | Target | Critical |
|--------|--------|----------|
| API Response Time (p95) | < 500ms | < 1000ms |
| API Response Time (p99) | < 1000ms | < 2000ms |
| Error Rate | < 0.1% | < 1% |
| Throughput | > 500 req/s | > 200 req/s |
| Availability | 99.9% | 99% |

## CI/CD Integration

Add to your GitHub Actions workflow:

```yaml
- name: Run Load Tests
  uses: grafana/k6-action@v0.3.0
  with:
    filename: infrastructure/load-testing/k6/loan-application-test.js
    flags: --vus 50 --duration 5m
```

## Monitoring During Tests

View real-time metrics in Grafana:
- Dashboard: `Mortgage CRM - Load Testing`
- URL: https://grafana.mortgagecrm.com/d/load-testing

## Test Data Management

Load tests use synthetic data with `load_test` source tag.
Clean up after testing:
```sql
DELETE FROM leads WHERE source = 'load_test';
DELETE FROM loans WHERE lead_id IN (SELECT id FROM leads WHERE source = 'load_test');
```
