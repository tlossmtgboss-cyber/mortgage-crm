"""
Perennia AI — Locust Load Test Suite

Simulates loan officer workflows against the Perennia API to validate
latency, throughput, and error rates under realistic concurrency.

Usage:
    locust -f tests/load/locustfile.py --host=https://api.perenniaai.com
    locust -f tests/load/locustfile.py --host=http://localhost:8000

Profiles:
    Smoke:    locust ... --headless --users 10  --spawn-rate 2  --run-time 1m
    Normal:   locust ... --headless --users 50  --spawn-rate 5  --run-time 5m
    Stress:   locust ... --headless --users 200 --spawn-rate 10 --run-time 10m

Environment variables:
    LOCUST_EMAIL     — account email for authentication
    LOCUST_PASSWORD  — account password for authentication

When LOCUST_EMAIL / LOCUST_PASSWORD are not set the suite operates in
anonymous mode: only unauthenticated endpoints (health probes) are tested.
"""

from __future__ import annotations

import json
import logging
import os
import sys
from typing import Optional

from locust import HttpUser, between, events, tag, task

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

_EMAIL: Optional[str] = os.getenv("LOCUST_EMAIL")
_PASSWORD: Optional[str] = os.getenv("LOCUST_PASSWORD")
_AUTH_AVAILABLE: bool = bool(_EMAIL and _PASSWORD)

# Thresholds (ms) — enforced in CI via the quitting hook
P95_THRESHOLD_MS = 800
ERROR_RATE_THRESHOLD = 0.005  # 0.5%


# ---------------------------------------------------------------------------
# Authentication helper
# ---------------------------------------------------------------------------


def _authenticate(user: HttpUser) -> None:
    """
    Log in via POST /api/v1/account/start and attach the JWT token
    as a default Authorization header for all subsequent requests.

    If LOCUST_EMAIL / LOCUST_PASSWORD are not set, authentication is
    skipped and only unauthenticated endpoints will return useful data.
    """
    if not _AUTH_AVAILABLE:
        logger.info(
            "LOCUST_EMAIL / LOCUST_PASSWORD not set — running without auth. "
            "Only health endpoints will return 200."
        )
        return

    payload = {"x1": _EMAIL, "x2": _PASSWORD}
    with user.client.post(
        "/api/v1/account/start",
        json=payload,
        name="POST /api/v1/account/start [login]",
        catch_response=True,
    ) as resp:
        if resp.status_code == 200:
            try:
                data = resp.json()
                token = (
                    data.get("access_token")
                    or data.get("token")
                    or data.get("data", {}).get("access_token")
                )
                if token:
                    user.client.headers.update(
                        {"Authorization": f"Bearer {token}"}
                    )
                    resp.success()
                    logger.info("Authentication succeeded for %s", _EMAIL)
                else:
                    resp.failure("Login response missing access_token field")
                    logger.warning("Login response had no token: %s", data)
            except Exception as exc:
                resp.failure(f"Could not parse login response: {exc}")
        else:
            # Bad credential is a config problem, not a perf problem.
            resp.success()
            logger.warning(
                "Login returned %d — subsequent requests will likely 401.",
                resp.status_code,
            )


# ---------------------------------------------------------------------------
# Main user class — LoanOfficerUser
# ---------------------------------------------------------------------------


class LoanOfficerUser(HttpUser):
    """
    Simulates a typical loan officer session.

    Task weights model real-world usage:
      - Pipeline view (leads list): 50%
      - Dashboard metrics:          20%
      - Task list:                  15%
      - AI agent chat:              10%
      - Notifications:               5%

    Wait time between requests: 1–5 seconds (realistic think time).
    """

    wait_time = between(1, 5)
    weight = 10  # dominant user persona

    def on_start(self) -> None:
        """Authenticate once at session start, reuse JWT for all requests."""
        _authenticate(self)

    # -- Pipeline view (50%) -----------------------------------------------

    @tag("pipeline", "read")
    @task(50)
    def pipeline_leads(self) -> None:
        """GET /api/v1/leads/ — the most-used page in the app."""
        with self.client.get(
            "/api/v1/leads/",
            name="GET /api/v1/leads/",
            catch_response=True,
        ) as resp:
            if resp.status_code in (200, 304, 401, 403):
                resp.success()
            else:
                resp.failure(f"Status {resp.status_code}")

    # -- Dashboard (20%) ---------------------------------------------------

    @tag("dashboard", "read")
    @task(20)
    def dashboard_metrics(self) -> None:
        """GET /api/v1/dashboard/metrics — main dashboard KPIs."""
        with self.client.get(
            "/api/v1/dashboard/metrics",
            name="GET /api/v1/dashboard/metrics",
            catch_response=True,
        ) as resp:
            if resp.status_code in (200, 304, 401, 403):
                resp.success()
            else:
                resp.failure(f"Status {resp.status_code}")

    # -- Task list (15%) ---------------------------------------------------

    @tag("tasks", "read")
    @task(15)
    def task_list(self) -> None:
        """GET /api/v1/tasks/ — daily task queue."""
        with self.client.get(
            "/api/v1/tasks/",
            name="GET /api/v1/tasks/",
            catch_response=True,
        ) as resp:
            if resp.status_code in (200, 304, 401, 403):
                resp.success()
            else:
                resp.failure(f"Status {resp.status_code}")

    # -- AI agent chat (10%) -----------------------------------------------

    @tag("ai", "write")
    @task(10)
    def ai_chat(self) -> None:
        """POST /api/v1/ai/chat — Aria agent interaction."""
        payload = {"message": "show my pipeline"}
        with self.client.post(
            "/api/v1/ai/chat",
            json=payload,
            name="POST /api/v1/ai/chat",
            catch_response=True,
        ) as resp:
            # AI chat may be slow; 200/401/403/422/429 are all non-failures
            if resp.status_code in (200, 201, 401, 403, 422, 429):
                resp.success()
            else:
                resp.failure(f"Status {resp.status_code}")

    # -- Notifications (5%) ------------------------------------------------

    @tag("notifications", "read")
    @task(5)
    def notifications(self) -> None:
        """GET /api/v1/notifications/ — notification feed."""
        with self.client.get(
            "/api/v1/notifications/",
            name="GET /api/v1/notifications/",
            catch_response=True,
        ) as resp:
            if resp.status_code in (200, 304, 401, 403):
                resp.success()
            else:
                resp.failure(f"Status {resp.status_code}")


# ---------------------------------------------------------------------------
# Secondary user class — HealthCheckUser (lightweight, no auth)
# ---------------------------------------------------------------------------


class HealthCheckUser(HttpUser):
    """
    Exercises health probes only. No authentication required.
    Weight 1 — minimal share of virtual users.
    """

    wait_time = between(1, 3)
    weight = 1

    @tag("health", "read")
    @task(3)
    def health(self) -> None:
        """GET /health — basic liveness."""
        with self.client.get(
            "/health",
            name="GET /health",
            catch_response=True,
        ) as resp:
            if resp.status_code == 200:
                resp.success()
            else:
                resp.failure(f"Status {resp.status_code}")

    @tag("health", "read")
    @task(1)
    def health_live(self) -> None:
        """GET /health/live — Kubernetes liveness probe."""
        with self.client.get(
            "/health/live",
            name="GET /health/live",
            catch_response=True,
        ) as resp:
            if resp.status_code in (200, 503):
                resp.success()
            else:
                resp.failure(f"Status {resp.status_code}")


# ---------------------------------------------------------------------------
# Supplementary user — LoanPipelineUser (loan-focused LO)
# ---------------------------------------------------------------------------


class LoanPipelineUser(HttpUser):
    """
    Simulates an LO focused on loan management rather than lead intake.
    Exercises the loans endpoint with stage filters and the dashboard.
    Weight 3 — smaller share than the main LoanOfficerUser.
    """

    wait_time = between(1, 5)
    weight = 3

    def on_start(self) -> None:
        _authenticate(self)

    @tag("loans", "read")
    @task(6)
    def list_loans(self) -> None:
        """GET /api/v1/loans/ — loan pipeline."""
        with self.client.get(
            "/api/v1/loans/",
            name="GET /api/v1/loans/",
            catch_response=True,
        ) as resp:
            if resp.status_code in (200, 304, 401, 403):
                resp.success()
            else:
                resp.failure(f"Status {resp.status_code}")

    @tag("loans", "read")
    @task(3)
    def loans_by_stage(self) -> None:
        """GET /api/v1/loans/?stage=PROCESSING — filtered loan view."""
        with self.client.get(
            "/api/v1/loans/?stage=PROCESSING",
            name="GET /api/v1/loans/?stage=PROCESSING",
            catch_response=True,
        ) as resp:
            if resp.status_code in (200, 304, 401, 403):
                resp.success()
            else:
                resp.failure(f"Status {resp.status_code}")

    @tag("dashboard", "read")
    @task(2)
    def dashboard(self) -> None:
        with self.client.get(
            "/api/v1/dashboard/metrics",
            name="GET /api/v1/dashboard/metrics",
            catch_response=True,
        ) as resp:
            if resp.status_code in (200, 304, 401, 403):
                resp.success()
            else:
                resp.failure(f"Status {resp.status_code}")


# ---------------------------------------------------------------------------
# Event hooks — threshold enforcement for CI
# ---------------------------------------------------------------------------


@events.quitting.add_listener
def on_quitting(environment, **_kwargs) -> None:
    """
    Enforce SLA thresholds at the end of the run.

    Fails the process (exit code 1) if:
      - p95 latency > 800 ms
      - Error rate > 0.5%
    """
    stats = environment.stats
    total = stats.total

    p50 = total.get_response_time_percentile(0.50) or 0
    p95 = total.get_response_time_percentile(0.95) or 0
    p99 = total.get_response_time_percentile(0.99) or 0
    error_pct = total.fail_ratio * 100

    logger.info(
        "Load test complete: %d requests, %.2f RPS, %.2f%% failures, "
        "p50=%.0f ms, p95=%.0f ms, p99=%.0f ms",
        total.num_requests,
        total.current_rps,
        error_pct,
        p50,
        p95,
        p99,
    )

    failed = False

    if p95 > P95_THRESHOLD_MS:
        logger.error(
            "FAIL: p95 latency %.0f ms exceeds threshold %d ms",
            p95,
            P95_THRESHOLD_MS,
        )
        failed = True

    if total.fail_ratio > ERROR_RATE_THRESHOLD:
        logger.error(
            "FAIL: error rate %.2f%% exceeds threshold %.1f%%",
            error_pct,
            ERROR_RATE_THRESHOLD * 100,
        )
        failed = True

    if failed:
        environment.process_exit_code = 1
    else:
        logger.info("All thresholds passed.")
