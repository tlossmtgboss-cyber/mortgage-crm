"""
Perennia AI -- Load Test Configuration & SLA Targets (PERF-006)

Centralizes performance SLA targets and load test profiles used by
both Locust (tests/load/locustfile.py) and CI/CD pipelines.

SLA Targets
-----------
These values define the contractual performance envelope for the API.
They are used by:
  - Locust's quitting hook to fail CI builds that violate SLAs
  - Monitoring dashboards (Datadog, internal /health/query-stats)
  - Capacity planning reviews

Load Profiles
-------------
Three profiles are defined for different testing contexts:
  - smoke:   Quick validation after deploy (10 users, 1 min)
  - normal:  Standard regression baseline (50 users, 5 min)
  - stress:  Ceiling-finding / capacity planning (200 users, 10 min)

Usage
-----
    from tests.load_test_config import SLA_TARGETS, LOAD_PROFILES

    # In locust quitting hook:
    if p95 > SLA_TARGETS["read_p95_ms"]:
        environment.process_exit_code = 1

    # CLI convenience:
    python -m tests.load_test_config          # prints config as JSON
    python -m tests.load_test_config k6       # prints k6 script to stdout
"""

from __future__ import annotations

import json
import sys
from typing import Any, Dict

# =========================================================================
# SLA Targets
# =========================================================================

SLA_TARGETS: Dict[str, Any] = {
    # -- Latency --
    "read_p95_ms": 500,         # GET endpoints: 95th percentile < 500ms
    "write_p95_ms": 1000,       # POST/PUT/PATCH/DELETE: p95 < 1000ms
    "p99_ms": 2000,             # All endpoints: 99th percentile < 2000ms

    # -- Availability --
    "error_rate_max": 0.001,    # < 0.1% error rate (5xx responses)

    # -- Concurrency --
    "max_concurrent_users": 100,

    # -- Throughput --
    "min_rps": 20,              # Minimum sustained requests/second at 100 users

    # -- Database --
    "query_p95_ms": 200,        # SQL query p95 < 200ms
    "pool_utilization_warn": 70,  # Warn at 70% pool utilization
    "pool_utilization_crit": 90,  # Critical at 90% pool utilization
}

# =========================================================================
# Load Test Profiles
# =========================================================================

LOAD_PROFILES: Dict[str, Dict[str, Any]] = {
    "smoke": {
        "description": "Quick post-deploy validation",
        "users": 10,
        "spawn_rate": 2,
        "run_time": "1m",
        "locust_cmd": (
            "locust -f tests/load/locustfile.py "
            "--host=https://api.perenniaai.com "
            "--headless --users 10 --spawn-rate 2 --run-time 1m"
        ),
    },
    "normal": {
        "description": "Standard regression baseline",
        "users": 50,
        "spawn_rate": 5,
        "run_time": "5m",
        "locust_cmd": (
            "locust -f tests/load/locustfile.py "
            "--host=https://api.perenniaai.com "
            "--headless --users 50 --spawn-rate 5 --run-time 5m"
        ),
    },
    "stress": {
        "description": "Ceiling-finding / capacity planning",
        "users": 200,
        "spawn_rate": 10,
        "run_time": "10m",
        "locust_cmd": (
            "locust -f tests/load/locustfile.py "
            "--host=https://api.perenniaai.com "
            "--headless --users 200 --spawn-rate 10 --run-time 10m"
        ),
    },
}

# =========================================================================
# k6 Script Generator
# =========================================================================

K6_SCRIPT = """\
// Perennia AI -- k6 Load Test Script (auto-generated from load_test_config.py)
//
// Usage:
//   k6 run --vus 50 --duration 5m backend/tests/k6_load_test.js
//   K6_EMAIL=user@example.com K6_PASSWORD=secret k6 run backend/tests/k6_load_test.js
//
// Environment variables:
//   K6_EMAIL    -- account email for authentication
//   K6_PASSWORD -- account password for authentication
//   K6_BASE_URL -- API base URL (default: https://api.perenniaai.com)

import http from 'k6/http';
import { check, sleep } from 'k6';
import { Rate, Trend } from 'k6/metrics';

// SLA thresholds (must match load_test_config.py)
const READ_P95_MS  = %(read_p95_ms)d;
const WRITE_P95_MS = %(write_p95_ms)d;
const P99_MS       = %(p99_ms)d;
const ERROR_RATE   = %(error_rate_max).4f;

export const options = {
  stages: [
    { duration: '30s', target: 20 },   // ramp up
    { duration: '3m',  target: %(max_concurrent_users)d },  // hold at target
    { duration: '30s', target: 0 },    // ramp down
  ],
  thresholds: {
    'http_req_duration{type:read}':  [`p(95)<${READ_P95_MS}`],
    'http_req_duration{type:write}': [`p(95)<${WRITE_P95_MS}`],
    'http_req_duration':             [`p(99)<${P99_MS}`],
    'http_req_failed':               [`rate<${ERROR_RATE}`],
  },
};

const BASE_URL = __ENV.K6_BASE_URL || 'https://api.perenniaai.com';
const EMAIL    = __ENV.K6_EMAIL    || '';
const PASSWORD = __ENV.K6_PASSWORD || '';

const readLatency  = new Trend('read_latency',  true);
const writeLatency = new Trend('write_latency', true);
const errorRate    = new Rate('error_rate');

let authToken = '';

export function setup() {
  if (!EMAIL || !PASSWORD) {
    console.warn('K6_EMAIL/K6_PASSWORD not set -- running unauthenticated');
    return {};
  }
  const res = http.post(`${BASE_URL}/api/v1/account/start`, JSON.stringify({
    x1: EMAIL,
    x2: PASSWORD,
  }), { headers: { 'Content-Type': 'application/json' } });

  const body = res.json();
  const token = body.access_token || body.token || (body.data && body.data.access_token) || '';
  return { token };
}

export default function(data) {
  const headers = { 'Content-Type': 'application/json' };
  if (data.token) {
    headers['Authorization'] = `Bearer ${data.token}`;
  }

  // --- Read endpoints (80%% of traffic) ---

  // Pipeline / leads list (50%%)
  const leadsRes = http.get(`${BASE_URL}/api/v1/leads/`, {
    headers,
    tags: { type: 'read', name: 'GET /api/v1/leads/' },
  });
  readLatency.add(leadsRes.timings.duration);
  check(leadsRes, { 'leads 2xx': (r) => r.status >= 200 && r.status < 400 });
  errorRate.add(leadsRes.status >= 500);
  sleep(1);

  // Dashboard metrics (20%%)
  if (Math.random() < 0.4) {
    const dashRes = http.get(`${BASE_URL}/api/v1/dashboard/metrics`, {
      headers,
      tags: { type: 'read', name: 'GET /api/v1/dashboard/metrics' },
    });
    readLatency.add(dashRes.timings.duration);
    errorRate.add(dashRes.status >= 500);
    sleep(1);
  }

  // Task list (15%%)
  if (Math.random() < 0.3) {
    const taskRes = http.get(`${BASE_URL}/api/v1/tasks/`, {
      headers,
      tags: { type: 'read', name: 'GET /api/v1/tasks/' },
    });
    readLatency.add(taskRes.timings.duration);
    errorRate.add(taskRes.status >= 500);
    sleep(1);
  }

  // Health probe
  if (Math.random() < 0.1) {
    const healthRes = http.get(`${BASE_URL}/health`, {
      tags: { type: 'read', name: 'GET /health' },
    });
    readLatency.add(healthRes.timings.duration);
    errorRate.add(healthRes.status >= 500);
  }

  // --- Write endpoint (10%% of traffic) ---
  if (Math.random() < 0.1) {
    const chatRes = http.post(`${BASE_URL}/api/v1/ai/chat`, JSON.stringify({
      message: 'show my pipeline',
    }), {
      headers,
      tags: { type: 'write', name: 'POST /api/v1/ai/chat' },
    });
    writeLatency.add(chatRes.timings.duration);
    errorRate.add(chatRes.status >= 500);
    sleep(2);
  }

  sleep(Math.random() * 3 + 1);  // think time: 1-4s
}
""" % SLA_TARGETS


# =========================================================================
# CLI entry point
# =========================================================================

def _print_config() -> None:
    """Print configuration as formatted JSON."""
    output = {
        "sla_targets": SLA_TARGETS,
        "load_profiles": LOAD_PROFILES,
    }
    print(json.dumps(output, indent=2))


def _print_k6_script() -> None:
    """Print a k6 load test script to stdout."""
    print(K6_SCRIPT)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "k6":
        _print_k6_script()
    else:
        _print_config()
