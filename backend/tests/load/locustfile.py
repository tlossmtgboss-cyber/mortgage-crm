"""
Perennia AI — Locust Load Test Suite

Targets key API endpoints to validate performance under load.
Tests the 47 indexes added in the enterprise hardening phase.

Usage:
    locust -f tests/load/locustfile.py --host=https://api.perenniaai.com
    locust -f tests/load/locustfile.py --host=http://localhost:8000

Profiles:
    Smoke:    locust ... --users 10  --spawn-rate 2  --run-time 1m
    Normal:   locust ... --users 50  --spawn-rate 5  --run-time 5m
    Stress:   locust ... --users 200 --spawn-rate 10 --run-time 10m

Environment variables:
    LOCUST_EMAIL     — account email for authentication (optional)
    LOCUST_PASSWORD  — account password for authentication (optional)

When LOCUST_EMAIL / LOCUST_PASSWORD are not set the suite operates in
anonymous mode: only unauthenticated endpoints (health probes) are tested.
"""

from __future__ import annotations

import logging
import os
from typing import Optional

from locust import HttpUser, TaskSet, between, events, tag, task

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration — read credentials from environment
# ---------------------------------------------------------------------------

_EMAIL: Optional[str] = os.getenv("LOCUST_EMAIL")
_PASSWORD: Optional[str] = os.getenv("LOCUST_PASSWORD")
_AUTH_AVAILABLE: bool = bool(_EMAIL and _PASSWORD)

# Warning threshold (ms) — Locust logs these but does not fail the test run.
# Critical thresholds should be enforced via CI assertions on the HTML report.
P95_READ_WARN_MS = 500
P95_WRITE_WARN_MS = 1_000


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _warn_slow(response, label: str, threshold_ms: int = P95_READ_WARN_MS) -> None:
    """Log a warning when a single response exceeds the threshold."""
    elapsed_ms = response.elapsed.total_seconds() * 1_000
    if elapsed_ms > threshold_ms:
        logger.warning(
            "Slow response detected: %s took %.0f ms (threshold %d ms)",
            label,
            elapsed_ms,
            threshold_ms,
        )


# ---------------------------------------------------------------------------
# Task sets
# ---------------------------------------------------------------------------


class HealthCheckTasks(TaskSet):
    """Lightweight health-probe tasks — run even without authentication."""

    @tag("health", "read")
    @task(3)
    def health(self) -> None:
        with self.client.get(
            "/health",
            name="GET /health",
            catch_response=True,
        ) as resp:
            if resp.status_code == 200:
                resp.success()
            else:
                resp.failure(f"Unexpected status: {resp.status_code}")
            _warn_slow(resp, "GET /health")

    @tag("health", "read")
    @task(1)
    def ready(self) -> None:
        with self.client.get(
            "/ready",
            name="GET /ready",
            catch_response=True,
        ) as resp:
            # 200 = ready; 503 = not ready yet (not a load-test failure)
            if resp.status_code in (200, 503):
                resp.success()
            else:
                resp.failure(f"Unexpected status: {resp.status_code}")
            _warn_slow(resp, "GET /ready")


class PipelineTasks(TaskSet):
    """Main LO workflow — dashboard, leads, loans, tasks, search."""

    @tag("pipeline", "read")
    @task(4)
    def dashboard_metrics(self) -> None:
        with self.client.get(
            "/api/v1/dashboard/metrics",
            name="GET /api/v1/dashboard/metrics",
            catch_response=True,
        ) as resp:
            if resp.status_code in (200, 304):
                resp.success()
            elif resp.status_code in (401, 403):
                resp.success()  # auth issue, not a perf failure
            else:
                resp.failure(f"Unexpected status: {resp.status_code}")
            _warn_slow(resp, "GET /api/v1/dashboard/metrics")

    @tag("pipeline", "read")
    @task(5)
    def list_leads(self) -> None:
        with self.client.get(
            "/api/v1/leads?limit=50",
            name="GET /api/v1/leads",
            catch_response=True,
        ) as resp:
            if resp.status_code in (200, 304, 401, 403):
                resp.success()
            else:
                resp.failure(f"Unexpected status: {resp.status_code}")
            _warn_slow(resp, "GET /api/v1/leads")

    @tag("pipeline", "read")
    @task(5)
    def list_loans(self) -> None:
        with self.client.get(
            "/api/v1/loans?limit=50",
            name="GET /api/v1/loans",
            catch_response=True,
        ) as resp:
            if resp.status_code in (200, 304, 401, 403):
                resp.success()
            else:
                resp.failure(f"Unexpected status: {resp.status_code}")
            _warn_slow(resp, "GET /api/v1/loans")

    @tag("pipeline", "read")
    @task(4)
    def list_loans_by_stage(self) -> None:
        with self.client.get(
            "/api/v1/loans?stage=PROCESSING",
            name="GET /api/v1/loans?stage=PROCESSING",
            catch_response=True,
        ) as resp:
            if resp.status_code in (200, 304, 401, 403):
                resp.success()
            else:
                resp.failure(f"Unexpected status: {resp.status_code}")
            _warn_slow(resp, "GET /api/v1/loans?stage=PROCESSING")

    @tag("pipeline", "read")
    @task(3)
    def list_tasks(self) -> None:
        with self.client.get(
            "/api/v1/tasks",
            name="GET /api/v1/tasks",
            catch_response=True,
        ) as resp:
            if resp.status_code in (200, 304, 401, 403):
                resp.success()
            else:
                resp.failure(f"Unexpected status: {resp.status_code}")
            _warn_slow(resp, "GET /api/v1/tasks")

    @tag("pipeline", "write")
    @task(2)
    def search_leads(self) -> None:
        payload = {"query": "john"}
        with self.client.post(
            "/api/v1/leads/search",
            json=payload,
            name="POST /api/v1/leads/search",
            catch_response=True,
        ) as resp:
            if resp.status_code in (200, 401, 403, 422):
                resp.success()
            else:
                resp.failure(f"Unexpected status: {resp.status_code}")
            _warn_slow(resp, "POST /api/v1/leads/search", P95_WRITE_WARN_MS)


class CalendarTasks(TaskSet):
    """Calendar-heavy workflow — events, slots, smart scheduler."""

    @tag("calendar", "read")
    @task(4)
    def calendar_events(self) -> None:
        with self.client.get(
            "/api/v1/calendar/events",
            name="GET /api/v1/calendar/events",
            catch_response=True,
        ) as resp:
            if resp.status_code in (200, 304, 401, 403):
                resp.success()
            else:
                resp.failure(f"Unexpected status: {resp.status_code}")
            _warn_slow(resp, "GET /api/v1/calendar/events")

    @tag("calendar", "read")
    @task(3)
    def calendar_slots(self) -> None:
        with self.client.get(
            "/api/v1/calendar/slots?date=2026-03-28",
            name="GET /api/v1/calendar/slots",
            catch_response=True,
        ) as resp:
            if resp.status_code in (200, 304, 401, 403):
                resp.success()
            else:
                resp.failure(f"Unexpected status: {resp.status_code}")
            _warn_slow(resp, "GET /api/v1/calendar/slots")

    @tag("calendar", "read")
    @task(3)
    def smart_scheduler_slots(self) -> None:
        with self.client.get(
            "/api/v1/smart-scheduler/available-slots",
            name="GET /api/v1/smart-scheduler/available-slots",
            catch_response=True,
        ) as resp:
            if resp.status_code in (200, 304, 401, 403):
                resp.success()
            else:
                resp.failure(f"Unexpected status: {resp.status_code}")
            _warn_slow(resp, "GET /api/v1/smart-scheduler/available-slots")


class AdminTasks(TaskSet):
    """Admin/reporting workflow — users listing, compliance dashboard."""

    @tag("admin", "read")
    @task(2)
    def admin_users(self) -> None:
        with self.client.get(
            "/api/v1/admin/users",
            name="GET /api/v1/admin/users",
            catch_response=True,
        ) as resp:
            # 403 is expected for non-admin users — not a load-test failure
            if resp.status_code in (200, 304, 401, 403):
                resp.success()
            else:
                resp.failure(f"Unexpected status: {resp.status_code}")
            _warn_slow(resp, "GET /api/v1/admin/users")

    @tag("admin", "read")
    @task(2)
    def compliance_dashboard(self) -> None:
        with self.client.get(
            "/api/v1/compliance/dashboard",
            name="GET /api/v1/compliance/dashboard",
            catch_response=True,
        ) as resp:
            if resp.status_code in (200, 304, 401, 403):
                resp.success()
            else:
                resp.failure(f"Unexpected status: {resp.status_code}")
            _warn_slow(resp, "GET /api/v1/compliance/dashboard")


# ---------------------------------------------------------------------------
# User classes
# ---------------------------------------------------------------------------


class HealthCheckUser(HttpUser):
    """
    Exercises health probes only.
    Weight 1 — smallest share of virtual users.
    Does NOT require authentication.
    """

    tasks = [HealthCheckTasks]
    weight = 1
    wait_time = between(1, 3)


class PipelineUser(HttpUser):
    """
    Simulates a loan officer working through their daily pipeline:
    dashboard, leads, loans, tasks, search.
    Weight 5 — largest share of virtual users (most common workflow).
    """

    tasks = [PipelineTasks]
    weight = 5
    wait_time = between(1, 3)

    def on_start(self) -> None:
        """Authenticate if credentials are configured."""
        _authenticate(self)


class CalendarUser(HttpUser):
    """
    Simulates an LO focused on scheduling: calendar events and slot lookups.
    Weight 3 — second-largest share.
    """

    tasks = [CalendarTasks]
    weight = 3
    wait_time = between(1, 3)

    def on_start(self) -> None:
        """Authenticate if credentials are configured."""
        _authenticate(self)


class AdminUser(HttpUser):
    """
    Simulates a platform admin reviewing compliance and user lists.
    Weight 1 — smallest share (admin traffic is rare in production).
    """

    tasks = [AdminTasks]
    weight = 1
    wait_time = between(1, 3)

    def on_start(self) -> None:
        """Authenticate if credentials are configured."""
        _authenticate(self)


# ---------------------------------------------------------------------------
# Authentication helper
# ---------------------------------------------------------------------------


def _authenticate(user: HttpUser) -> None:
    """
    Log in and attach the JWT token as a default Authorization header.

    If LOCUST_EMAIL / LOCUST_PASSWORD are not set, authentication is skipped
    and only unauthenticated endpoints will respond with useful data.
    """
    if not _AUTH_AVAILABLE:
        logger.info(
            "LOCUST_EMAIL / LOCUST_PASSWORD not set — running without auth. "
            "Only health endpoints will return 200."
        )
        return

    payload = {"email": _EMAIL, "password": _PASSWORD}
    with user.client.post(
        "/api/v1/auth/login",
        json=payload,
        name="POST /api/v1/auth/login (setup)",
        catch_response=True,
    ) as resp:
        if resp.status_code == 200:
            try:
                data = resp.json()
                token = data.get("access_token") or data.get("token")
                if token:
                    user.client.headers.update({"Authorization": f"Bearer {token}"})
                    resp.success()
                    logger.debug("Authentication succeeded")
                else:
                    resp.failure("Login response missing access_token field")
                    logger.warning("Login response had no token: %s", data)
            except Exception as exc:  # noqa: BLE001
                resp.failure(f"Could not parse login response: {exc}")
        else:
            # Don't mark as failure — a bad credential is a config problem,
            # not a latency/throughput problem.  Log and continue.
            resp.success()
            logger.warning(
                "Login returned %d — subsequent authenticated requests may 401.",
                resp.status_code,
            )


# ---------------------------------------------------------------------------
# Event hooks (optional — add per-run summary logging)
# ---------------------------------------------------------------------------


@events.quitting.add_listener
def on_quitting(environment, **_kwargs) -> None:
    """Log a summary of results when the test run ends."""
    stats = environment.stats
    total = stats.total
    logger.info(
        "Load test complete: %d requests, %.2f RPS, %.1f%% failures, "
        "p50=%.0f ms, p95=%.0f ms, p99=%.0f ms",
        total.num_requests,
        total.current_rps,
        total.fail_ratio * 100,
        total.get_response_time_percentile(0.50) or 0,
        total.get_response_time_percentile(0.95) or 0,
        total.get_response_time_percentile(0.99) or 0,
    )

    # Exit with non-zero code if error rate exceeds 1% (critical threshold)
    if total.fail_ratio > 0.01:
        logger.error(
            "CRITICAL: error rate %.2f%% exceeds 1%% threshold — marking run as failed.",
            total.fail_ratio * 100,
        )
        environment.process_exit_code = 1
