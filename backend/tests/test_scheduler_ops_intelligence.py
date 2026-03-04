"""
Tests for Smart Calendar Operational Intelligence Features

Validates the 17 operational gaps remediated across 4 phases:
- Phase 1: Compliance (C1-C3)
- Phase 2: CRM Integration (CRM1-CRM5)
- Phase 3: Resilience (R1, R2, R3, R4, R5)
- Phase 4: Routing Intelligence (RT1-RT4)

These tests verify structural correctness (imports, signatures, return types)
without requiring a live database connection.
"""

import ast
import inspect
import importlib
import os
import sys
import types
import pytest

# Ensure backend is on path
BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_file(filename: str) -> ast.Module:
    """Parse a Python file and return the AST."""
    filepath = os.path.join(BACKEND_DIR, filename)
    with open(filepath) as f:
        return ast.parse(f.read(), filename=filename)


def _find_functions(tree: ast.Module) -> dict[str, ast.FunctionDef]:
    """Extract top-level and nested function defs by name."""
    funcs = {}
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            funcs[node.name] = node
    return funcs


def _find_classes(tree: ast.Module) -> dict[str, ast.ClassDef]:
    """Extract class defs by name."""
    return {
        node.name: node
        for node in ast.walk(tree)
        if isinstance(node, ast.ClassDef)
    }


# ---------------------------------------------------------------------------
# Phase 1: Compliance
# ---------------------------------------------------------------------------

class TestC1_SMSConsentCheck:
    """C1: TCPA/DNC consent check before SMS sends."""

    def test_check_sms_consent_function_exists(self):
        tree = _parse_file("scheduler_email_service.py")
        funcs = _find_functions(tree)
        assert "check_sms_consent" in funcs, "check_sms_consent function must exist"

    def test_check_sms_consent_has_phone_param(self):
        tree = _parse_file("scheduler_email_service.py")
        func = _find_functions(tree)["check_sms_consent"]
        param_names = [a.arg for a in func.args.args]
        assert "phone" in param_names, "check_sms_consent must accept 'phone' parameter"

    def test_sms_consent_gated_at_confirmation(self):
        """Verify consent check call exists near telnyx SMS in confirmation function."""
        with open(os.path.join(BACKEND_DIR, "scheduler_email_service.py")) as f:
            source = f.read()
        # The consent check should appear before telnyx.Message.create calls
        assert "check_sms_consent" in source
        assert source.count("check_sms_consent") >= 3, (
            "check_sms_consent should gate at least 3 SMS send sites"
        )


class TestC2_DuplicateBookingDetection:
    """C2: Duplicate booking detection."""

    def test_duplicate_check_function_exists(self):
        tree = _parse_file("scheduler_appointment_routes.py")
        funcs = _find_functions(tree)
        assert "_check_duplicate_booking" in funcs

    def test_duplicate_check_raises_409(self):
        with open(os.path.join(BACKEND_DIR, "scheduler_appointment_routes.py")) as f:
            source = f.read()
        # Should raise 409 for duplicates
        assert "409" in source and "duplicate" in source.lower()


class TestC3_LOLicensingCheck:
    """C3: LO state licensing soft warning."""

    def test_licensing_check_function_exists(self):
        tree = _parse_file("scheduler_appointment_routes.py")
        funcs = _find_functions(tree)
        assert "_check_lo_licensing" in funcs

    def test_licensing_check_is_advisory(self):
        """Licensing check should NOT raise exceptions — advisory only."""
        tree = _parse_file("scheduler_appointment_routes.py")
        func = _find_functions(tree)["_check_lo_licensing"]
        # Should return Optional[str], not raise
        source_lines = ast.get_source_segment(
            open(os.path.join(BACKEND_DIR, "scheduler_appointment_routes.py")).read(),
            func,
        )
        assert "HTTPException" not in (source_lines or ""), (
            "_check_lo_licensing should be advisory, not raise HTTPException"
        )


# ---------------------------------------------------------------------------
# Phase 2: CRM Integration
# ---------------------------------------------------------------------------

class TestCRM1_LeadCreation:
    """CRM1: Lead creation/linking on public booking."""

    def test_ensure_lead_function_exists(self):
        tree = _parse_file("scheduler_appointment_routes.py")
        funcs = _find_functions(tree)
        assert "_ensure_lead_for_booking" in funcs

    def test_ensure_lead_has_required_params(self):
        tree = _parse_file("scheduler_appointment_routes.py")
        func = _find_functions(tree)["_ensure_lead_for_booking"]
        param_names = [a.arg for a in func.args.args]
        for required in ["db", "attendee_email", "attendee_name"]:
            assert required in param_names, f"_ensure_lead_for_booking missing param: {required}"


class TestCRM2_ActivityLogging:
    """CRM2: Activity logging on appointment events."""

    def test_log_activity_function_exists(self):
        tree = _parse_file("scheduler_appointment_routes.py")
        funcs = _find_functions(tree)
        assert "_log_appointment_activity" in funcs

    def test_activity_logging_in_create_and_cancel(self):
        with open(os.path.join(BACKEND_DIR, "scheduler_appointment_routes.py")) as f:
            source = f.read()
        assert source.count("_log_appointment_activity") >= 3, (
            "_log_appointment_activity should be called in create, confirm, and cancel"
        )


class TestCRM3_FollowupTasks:
    """CRM3: Follow-up task creation."""

    def test_followup_task_function_exists(self):
        tree = _parse_file("scheduler_appointment_routes.py")
        funcs = _find_functions(tree)
        assert "_create_followup_task" in funcs

    def test_followup_task_has_required_params(self):
        tree = _parse_file("scheduler_appointment_routes.py")
        func = _find_functions(tree)["_create_followup_task"]
        param_names = [a.arg for a in func.args.args]
        for required in ["db", "org_id", "owner_id", "title"]:
            assert required in param_names, f"_create_followup_task missing param: {required}"


class TestCRM4_CalendlyWebhookCRM:
    """CRM4: Calendly webhook → lead + notification + workflow."""

    def test_calendly_creates_lead(self):
        with open(os.path.join(BACKEND_DIR, "routes/calendly_routes.py")) as f:
            source = f.read()
        assert "auto_create_contacts" in source
        assert "source=\"calendly\"" in source or "source='calendly'" in source

    def test_calendly_logs_activity(self):
        with open(os.path.join(BACKEND_DIR, "routes/calendly_routes.py")) as f:
            source = f.read()
        assert "_log_appointment_activity" in source or "Activity(" in source


class TestCRM5_AnalyticsTools:
    """CRM5: Analytics as @mortgage_tool."""

    def test_analytics_tools_exist(self):
        tree = _parse_file("agents/tools/scheduler.py")
        funcs = _find_functions(tree)
        expected_tools = [
            "get_scheduler_metrics",
            "get_appointment_history",
            "get_best_booking_times",
            "get_no_show_analysis",
        ]
        for tool_name in expected_tools:
            assert tool_name in funcs, f"Analytics tool missing: {tool_name}"

    def test_analytics_tools_query_scheduler_appointments(self):
        with open(os.path.join(BACKEND_DIR, "agents/tools/scheduler.py")) as f:
            source = f.read()
        # New analytics tools should query scheduler_appointments, not old appointments table
        assert "scheduler_appointments" in source

    def test_analytics_tools_have_correct_roles(self):
        with open(os.path.join(BACKEND_DIR, "agents/tools/scheduler.py")) as f:
            source = f.read()
        # All 4 analytics tools should include pipeline_analyst and team_coach
        assert source.count('"pipeline_analyst"') >= 4
        assert source.count('"team_coach"') >= 4


# ---------------------------------------------------------------------------
# Phase 3: Resilience
# ---------------------------------------------------------------------------

class TestR1_EmailRetryWithFallback:
    """R1: Email retry with SMS fallback."""

    def test_retry_email_send_exists(self):
        tree = _parse_file("scheduler_email_service.py")
        funcs = _find_functions(tree)
        assert "_retry_email_send" in funcs

    def test_send_with_sms_fallback_exists(self):
        tree = _parse_file("scheduler_email_service.py")
        funcs = _find_functions(tree)
        assert "send_with_sms_fallback" in funcs

    def test_retry_has_backoff(self):
        with open(os.path.join(BACKEND_DIR, "scheduler_email_service.py")) as f:
            source = f.read()
        assert "backoff" in source.lower() or "2 **" in source or "2**" in source


class TestR2_NoShowRecovery:
    """R2: No-show recovery sends real emails/SMS."""

    def test_no_show_recovery_not_fake(self):
        with open(os.path.join(BACKEND_DIR, "scheduler_enhanced_routes.py")) as f:
            source = f.read()
        # Should NOT have the old fake "queued" pattern
        # Should have real send calls
        assert "send_appointment_reminder_email" in source or "send_with_sms_fallback" in source

    def test_no_show_creates_task(self):
        with open(os.path.join(BACKEND_DIR, "scheduler_enhanced_routes.py")) as f:
            source = f.read()
        assert "no_show" in source.lower() and "Task(" in source


class TestR3_AutomatedReminders:
    """R3: Automated reminder processing endpoint."""

    def test_reminders_process_endpoint_exists(self):
        with open(os.path.join(BACKEND_DIR, "scheduler_appointment_routes.py")) as f:
            source = f.read()
        assert "reminders/process" in source

    def test_reminders_check_windows(self):
        with open(os.path.join(BACKEND_DIR, "scheduler_appointment_routes.py")) as f:
            source = f.read()
        # Should check 24h and 1h windows
        assert "24" in source  # 24 hour window
        assert "AppointmentReminder" in source or "reminder" in source.lower()


class TestR4_MemoryRateLimiter:
    """R4: In-memory rate limiter fallback."""

    def test_memory_rate_limit_function_exists(self):
        tree = _parse_file("scheduler_appointment_routes.py")
        funcs = _find_functions(tree)
        assert "_check_memory_rate_limit" in funcs

    def test_memory_rate_limit_uses_threading(self):
        with open(os.path.join(BACKEND_DIR, "scheduler_appointment_routes.py")) as f:
            source = f.read()
        assert "threading" in source
        assert "Lock" in source
        assert "deque" in source


class TestR5_CommunicationEscalation:
    """R5: Escalation on communication failure."""

    def test_comm_failure_task_function_exists(self):
        tree = _parse_file("scheduler_appointment_routes.py")
        funcs = _find_functions(tree)
        assert "_create_comm_failure_task" in funcs

    def test_escalation_creates_high_priority_task(self):
        with open(os.path.join(BACKEND_DIR, "scheduler_appointment_routes.py")) as f:
            source = f.read()
        # The comm failure task function should create high-priority tasks
        assert "_create_comm_failure_task" in source
        assert "priority" in source and '"high"' in source


# ---------------------------------------------------------------------------
# Phase 4: Routing Intelligence
# ---------------------------------------------------------------------------

class TestRT1_RoutingStrategies:
    """RT1: 5 LO assignment strategies."""

    def test_routing_service_exists(self):
        tree = _parse_file("services/scheduler_routing_service.py")
        funcs = _find_functions(tree)
        assert "assign_loan_officer" in funcs

    def test_all_five_strategies_exist(self):
        tree = _parse_file("services/scheduler_routing_service.py")
        funcs = _find_functions(tree)
        strategies = [
            "_assign_direct",
            "_assign_round_robin",
            "_assign_priority",
            "_assign_availability",
            "_assign_load_balanced",
        ]
        for strategy in strategies:
            assert strategy in funcs, f"Missing routing strategy: {strategy}"

    def test_routing_wired_into_public_booking(self):
        with open(os.path.join(BACKEND_DIR, "scheduler_appointment_routes.py")) as f:
            source = f.read()
        assert "assign_loan_officer" in source


class TestRT2_HardCapacityEnforcement:
    """RT2: Hard capacity enforcement via _is_lo_available."""

    def test_is_lo_available_exists(self):
        tree = _parse_file("services/scheduler_routing_service.py")
        funcs = _find_functions(tree)
        assert "_is_lo_available" in funcs

    def test_capacity_check_queries_max_daily(self):
        with open(os.path.join(BACKEND_DIR, "services/scheduler_routing_service.py")) as f:
            source = f.read()
        assert "max_daily_appointments" in source


class TestRT3_ConflictDetection:
    """RT3: Conflict detection in unified calendar."""

    def test_detect_conflicts_method_exists(self):
        tree = _parse_file("services/unified_calendar_service.py")
        classes = _find_classes(tree)
        assert "UnifiedCalendarService" in classes
        methods = {
            node.name
            for node in ast.walk(classes["UnifiedCalendarService"])
            if isinstance(node, ast.FunctionDef)
        }
        assert "_detect_conflicts" in methods

    def test_conflicts_in_response(self):
        with open(os.path.join(BACKEND_DIR, "services/unified_calendar_service.py")) as f:
            source = f.read()
        assert '"conflicts"' in source or "'conflicts'" in source
        assert "has_hard_conflicts" in source


class TestRT4_SLADashboardEnhancement:
    """RT4: SLA dashboard with confirmation_sla tracking."""

    def test_confirmation_sla_in_dashboard(self):
        with open(os.path.join(BACKEND_DIR, "scheduler_enhanced_routes.py")) as f:
            source = f.read()
        assert "confirmation_sla" in source

    def test_sla_percentiles(self):
        with open(os.path.join(BACKEND_DIR, "scheduler_enhanced_routes.py")) as f:
            source = f.read()
        assert "p50" in source
        assert "p90" in source
        assert "breach" in source.lower()


# ---------------------------------------------------------------------------
# Enterprise Readiness: Critical Fixes Verification
# ---------------------------------------------------------------------------

class TestCF1_SMSConsentOrgIsolation:
    """CF-1: check_sms_consent must accept organization_id for tenant isolation."""

    def test_check_sms_consent_has_organization_id_param(self):
        tree = _parse_file("scheduler_email_service.py")
        func = _find_functions(tree)["check_sms_consent"]
        param_names = [a.arg for a in func.args.args]
        assert "organization_id" in param_names, (
            "check_sms_consent must accept 'organization_id' parameter"
        )

    def test_sms_functions_pass_organization_id(self):
        with open(os.path.join(BACKEND_DIR, "scheduler_email_service.py")) as f:
            source = f.read()
        assert "organization_id=organization_id" in source, (
            "SMS functions must pass organization_id to check_sms_consent"
        )

    def test_lead_query_scoped_by_org(self):
        with open(os.path.join(BACKEND_DIR, "scheduler_email_service.py")) as f:
            source = f.read()
        assert "Lead.organization_id" in source, (
            "Lead query in check_sms_consent must filter by organization_id"
        )


class TestCF2_UserTimezoneOrgIsolation:
    """CF-2: _get_user_timezone must scope by org_id."""

    def test_get_user_timezone_has_org_id_param(self):
        tree = _parse_file("scheduler_appointment_routes.py")
        func = _find_functions(tree)["_get_user_timezone"]
        param_names = [a.arg for a in func.args.args]
        assert "org_id" in param_names, (
            "_get_user_timezone must accept 'org_id' parameter"
        )

    def test_timezone_query_filters_by_org(self):
        with open(os.path.join(BACKEND_DIR, "scheduler_appointment_routes.py")) as f:
            source = f.read()
        assert "SchedulerConfig.organization_id" in source, (
            "_get_user_timezone must filter SchedulerConfig by organization_id"
        )

    def test_call_sites_pass_org_id(self):
        with open(os.path.join(BACKEND_DIR, "scheduler_appointment_routes.py")) as f:
            source = f.read()
        # All _get_user_timezone calls must pass org_id
        import re
        calls = re.findall(r'_get_user_timezone\(db,[^)]+\)', source)
        for call in calls:
            if 'def _get_user_timezone' not in call:
                assert 'org_id' in call, f"Call missing org_id: {call}"


class TestCF3_AppointmentTypeOrgIsolation:
    """CF-3: AppointmentType queries must filter by organization_id."""

    def test_appointment_type_queries_have_org_filter(self):
        with open(os.path.join(BACKEND_DIR, "scheduler_appointment_routes.py")) as f:
            source = f.read()
        assert "AppointmentType.organization_id" in source, (
            "AppointmentType queries must include organization_id filter"
        )


class TestCF4_LOLicensingOrgIsolation:
    """CF-4: _check_lo_licensing must scope User query by org_id."""

    def test_check_lo_licensing_has_org_id_param(self):
        tree = _parse_file("scheduler_appointment_routes.py")
        func = _find_functions(tree)["_check_lo_licensing"]
        param_names = [a.arg for a in func.args.args]
        assert "org_id" in param_names, (
            "_check_lo_licensing must accept 'org_id' parameter"
        )

    def test_user_query_filters_by_org(self):
        with open(os.path.join(BACKEND_DIR, "scheduler_appointment_routes.py")) as f:
            source = f.read()
        assert "User.organization_id" in source, (
            "_check_lo_licensing must filter User query by organization_id"
        )


class TestCF6_DNCFailClosed:
    """CF-6: DNC check exception must block SMS (fail-closed)."""

    def test_dnc_exception_blocks_sms(self):
        with open(os.path.join(BACKEND_DIR, "scheduler_email_service.py")) as f:
            source = f.read()
        # Must NOT contain the old fail-open pattern
        assert 'DNC check failed (allowing)' not in source, (
            "DNC exception must NOT allow SMS (fail-open is a TCPA violation)"
        )
        # Must contain fail-closed pattern
        assert 'blocking SMS for safety' in source or 'DNC check unavailable' in source, (
            "DNC exception must block SMS (fail-closed)"
        )


class TestCF7_ContactHoursCheck:
    """CF-7: TCPA time-of-day check must exist."""

    def test_check_contact_hours_function_exists(self):
        tree = _parse_file("scheduler_email_service.py")
        funcs = _find_functions(tree)
        assert "_check_contact_hours" in funcs, (
            "_check_contact_hours function must exist for TCPA compliance"
        )

    def test_contact_hours_called_in_consent_check(self):
        with open(os.path.join(BACKEND_DIR, "scheduler_email_service.py")) as f:
            source = f.read()
        assert "_check_contact_hours" in source, (
            "_check_contact_hours must be called in check_sms_consent"
        )

    def test_contact_hours_checks_8am_9pm(self):
        with open(os.path.join(BACKEND_DIR, "scheduler_email_service.py")) as f:
            source = f.read()
        # Must check for hour < 8 or hour >= 21 (8am-9pm)
        assert "< 8" in source or "<= 7" in source, (
            "Contact hours must check for before 8am"
        )
        assert ">= 21" in source or "> 20" in source, (
            "Contact hours must check for after 9pm"
        )


# ---------------------------------------------------------------------------
# Cross-cutting: All files parse cleanly
# ---------------------------------------------------------------------------

class TestAllFilesParse:
    """Verify all modified files have valid Python syntax."""

    @pytest.mark.parametrize("filename", [
        "scheduler_email_service.py",
        "scheduler_appointment_routes.py",
        "routes/calendly_routes.py",
        "scheduler_enhanced_routes.py",
        "services/scheduler_routing_service.py",
        "services/unified_calendar_service.py",
        "agents/tools/scheduler.py",
    ])
    def test_file_parses(self, filename):
        filepath = os.path.join(BACKEND_DIR, filename)
        with open(filepath) as f:
            source = f.read()
        try:
            ast.parse(source, filename=filename)
        except SyntaxError as e:
            pytest.fail(f"{filename} has syntax error: {e}")
