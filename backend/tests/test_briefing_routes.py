"""
Unit tests for backend/routes/briefing_routes.py

Tests each endpoint by mocking DB queries and auth dependencies directly
against the route handler functions (no HTTP server required).
"""
from __future__ import annotations

import sys
import types
from datetime import date, datetime, timezone
from typing import Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Stubs: ensure FastAPI and route can be imported without the full app.
# SQLAlchemy, pydantic, etc. are assumed present in the test environment.
# We only stub out the heavy internal dependencies.
# ---------------------------------------------------------------------------

def _install_route_stubs():
    """Pre-install stubs needed by briefing_routes before importing it."""
    # tasks.morning_briefing_tasks stub
    tasks_stub = sys.modules.get("tasks", types.ModuleType("tasks"))
    tasks_stub.__path__ = []
    sys.modules.setdefault("tasks", tasks_stub)

    mbt_stub = types.ModuleType("tasks.morning_briefing_tasks")
    mock_gen = MagicMock(name="generate_user_briefing")
    mock_gen.apply_async = MagicMock()
    mbt_stub.generate_user_briefing = mock_gen
    sys.modules["tasks.morning_briefing_tasks"] = mbt_stub

    # services.morning_briefing_service stub
    svc_stub = types.ModuleType("services.morning_briefing_service")
    MockSvc = MagicMock(name="MorningBriefingService")
    MockSvc.determine_level.return_value = "individual"
    MockSvc.load_preferences.return_value = MagicMock(
        sections={}, thresholds={}, ai_tone="balanced"
    )
    svc_stub.MorningBriefingService = MockSvc
    sys.modules["services.morning_briefing_service"] = svc_stub

    # database.models.morning_briefing stub
    db_models_stub = sys.modules.get("database", types.ModuleType("database"))
    db_models_stub.__path__ = []
    sys.modules.setdefault("database", db_models_stub)

    db_models_pkg = sys.modules.get("database.models", types.ModuleType("database.models"))
    db_models_pkg.__path__ = []
    sys.modules.setdefault("database.models", db_models_pkg)

    mb_mod = types.ModuleType("database.models.morning_briefing")
    mb_mod.MorningBriefing = MagicMock(name="MorningBriefing_class")
    sys.modules["database.models.morning_briefing"] = mb_mod

    # database.models.User stub
    db_models_pkg.User = MagicMock(name="User_class")


_install_route_stubs()

# Safe to import routes now.
from routes.briefing_routes import (
    router,
    set_dependencies,
    get_today_briefing,
    get_briefing_history,
    generate_now,
    mark_viewed,
    get_preferences,
    update_preferences,
    BriefingPreferencesSchema,
    BriefingSections,
    BriefingThresholds,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_user(user_id=1, tz="America/Chicago", role="sales",
               briefing_enabled=True, briefing_hour=7,
               briefing_preferences=None):
    u = MagicMock(name="User")
    u.id = user_id
    u.permission_role = role
    u.timezone = tz
    u.briefing_enabled = briefing_enabled
    u.briefing_hour = briefing_hour
    u.briefing_preferences = briefing_preferences
    u.direct_reports = []
    return u


def _make_briefing(bid=1, bdate=date(2026, 3, 16), level="individual",
                   status="delivered", narrative="Good morning!",
                   briefing_data=None, team_data=None,
                   viewed_at=None, created_at=None):
    b = MagicMock(name="MorningBriefing")
    b.id = bid
    b.briefing_date = bdate
    b.briefing_level = level
    b.status = status
    b.ai_narrative = narrative
    b.briefing_data = briefing_data or {
        "pipeline": {"active_count": 3},
        "at_risk": [],
        "stale_leads": [],
        "appointments": [],
        "conditions": [],
        "yesterday": {},
    }
    b.team_data = team_data
    b.viewed_in_app_at = viewed_at
    b.created_at = created_at or datetime(2026, 3, 16, 7, 0, tzinfo=timezone.utc)
    return b


def _make_db():
    db = MagicMock(name="Session")
    return db


def _query_returning(db, first_result):
    """Configure db.query().filter().first() chain to return first_result."""
    q = MagicMock()
    q.filter.return_value.first.return_value = first_result
    q.filter.return_value.order_by.return_value.offset.return_value.limit.return_value.all.return_value = []
    db.query.return_value = q
    return q


def _query_returning_list(db, items):
    """Configure db.query() chain for paginated list queries."""
    q = MagicMock()
    q.filter.return_value.order_by.return_value.offset.return_value.limit.return_value.all.return_value = items
    q.filter.return_value.first.return_value = None
    db.query.return_value = q
    return q


# ---------------------------------------------------------------------------
# GET /today
# ---------------------------------------------------------------------------

class TestGetTodayBriefing:

    @pytest.mark.asyncio
    async def test_returns_204_when_no_briefing(self):
        db = _make_db()
        user = _make_user()
        _query_returning(db, None)

        MB = MagicMock(name="MB")
        MB.user_id = None
        MB.briefing_date = None

        with patch("routes.briefing_routes._get_deps",
                   return_value=(MB, MagicMock())):
            response = await get_today_briefing(db=db, current_user=user)

        from fastapi.responses import Response
        assert isinstance(response, Response)
        assert response.status_code == 204

    @pytest.mark.asyncio
    async def test_returns_briefing_data_when_found(self):
        db = _make_db()
        user = _make_user(tz="America/Chicago")
        bdate = datetime.now(__import__("zoneinfo").ZoneInfo("America/Chicago")).date()
        briefing = _make_briefing(bdate=bdate)
        _query_returning(db, briefing)

        MB = MagicMock(name="MB")
        MB.user_id = None
        MB.briefing_date = None

        with patch("routes.briefing_routes._get_deps",
                   return_value=(MB, MagicMock())):
            result = await get_today_briefing(db=db, current_user=user)

        assert isinstance(result, dict)
        assert result["id"] == 1
        assert result["status"] == "delivered"
        assert result["ai_narrative"] == "Good morning!"

    @pytest.mark.asyncio
    async def test_viewed_in_app_false_when_not_viewed(self):
        db = _make_db()
        user = _make_user()
        briefing = _make_briefing(viewed_at=None)
        _query_returning(db, briefing)

        with patch("routes.briefing_routes._get_deps",
                   return_value=(MagicMock(), MagicMock())):
            result = await get_today_briefing(db=db, current_user=user)

        assert result["viewed_in_app"] is False

    @pytest.mark.asyncio
    async def test_viewed_in_app_true_when_viewed(self):
        db = _make_db()
        user = _make_user()
        viewed_ts = datetime(2026, 3, 16, 8, 0, tzinfo=timezone.utc)
        briefing = _make_briefing(viewed_at=viewed_ts)
        _query_returning(db, briefing)

        with patch("routes.briefing_routes._get_deps",
                   return_value=(MagicMock(), MagicMock())):
            result = await get_today_briefing(db=db, current_user=user)

        assert result["viewed_in_app"] is True

    @pytest.mark.asyncio
    async def test_team_data_included_when_present(self):
        db = _make_db()
        user = _make_user()
        briefing = _make_briefing(team_data={"members": [{"name": "Alice"}]})
        _query_returning(db, briefing)

        with patch("routes.briefing_routes._get_deps",
                   return_value=(MagicMock(), MagicMock())):
            result = await get_today_briefing(db=db, current_user=user)

        assert result["team"] == {"members": [{"name": "Alice"}]}

    @pytest.mark.asyncio
    async def test_uses_user_timezone_for_today(self):
        """User in UTC+9 (Japan) — 'today' differs from UTC."""
        db = _make_db()
        user = _make_user(tz="Asia/Tokyo")

        from zoneinfo import ZoneInfo
        today_tokyo = datetime.now(ZoneInfo("Asia/Tokyo")).date()
        briefing = _make_briefing(bdate=today_tokyo)
        _query_returning(db, briefing)

        MB = MagicMock()
        MB.user_id = None
        MB.briefing_date = None

        with patch("routes.briefing_routes._get_deps", return_value=(MB, MagicMock())):
            result = await get_today_briefing(db=db, current_user=user)

        assert result["briefing_date"] == today_tokyo.isoformat()

    @pytest.mark.asyncio
    async def test_falls_back_to_chicago_for_invalid_tz(self):
        db = _make_db()
        user = _make_user(tz="Mars/Olympus")
        # Just assert it doesn't raise
        _query_returning(db, None)

        from fastapi.responses import Response
        with patch("routes.briefing_routes._get_deps",
                   return_value=(MagicMock(), MagicMock())):
            response = await get_today_briefing(db=db, current_user=user)

        assert isinstance(response, Response)
        assert response.status_code == 204


# ---------------------------------------------------------------------------
# GET /history
# ---------------------------------------------------------------------------

class TestGetBriefingHistory:

    @pytest.mark.asyncio
    async def test_returns_paginated_results(self):
        db = _make_db()
        user = _make_user()
        briefings = [_make_briefing(bid=i, bdate=date(2026, 3, 16 - i))
                     for i in range(1, 4)]
        _query_returning_list(db, briefings)

        with patch("routes.briefing_routes._get_deps",
                   return_value=(MagicMock(), MagicMock())):
            result = await get_briefing_history(page=1, per_page=10,
                                                db=db, current_user=user)

        assert result["page"] == 1
        assert result["per_page"] == 10
        assert len(result["items"]) == 3

    @pytest.mark.asyncio
    async def test_narrative_truncated_to_200_chars(self):
        db = _make_db()
        user = _make_user()
        long_text = "A" * 500
        briefings = [_make_briefing(narrative=long_text)]
        _query_returning_list(db, briefings)

        with patch("routes.briefing_routes._get_deps",
                   return_value=(MagicMock(), MagicMock())):
            result = await get_briefing_history(page=1, per_page=10,
                                                db=db, current_user=user)

        assert len(result["items"][0]["ai_narrative"]) == 200

    @pytest.mark.asyncio
    async def test_empty_history_returns_empty_list(self):
        db = _make_db()
        user = _make_user()
        _query_returning_list(db, [])

        with patch("routes.briefing_routes._get_deps",
                   return_value=(MagicMock(), MagicMock())):
            result = await get_briefing_history(page=1, per_page=10,
                                                db=db, current_user=user)

        assert result["items"] == []

    @pytest.mark.asyncio
    async def test_viewed_in_app_field_present(self):
        db = _make_db()
        user = _make_user()
        viewed_ts = datetime(2026, 3, 16, 8, 0, tzinfo=timezone.utc)
        briefings = [_make_briefing(viewed_at=viewed_ts)]
        _query_returning_list(db, briefings)

        with patch("routes.briefing_routes._get_deps",
                   return_value=(MagicMock(), MagicMock())):
            result = await get_briefing_history(page=1, per_page=10,
                                                db=db, current_user=user)

        assert result["items"][0]["viewed_in_app"] is True


# ---------------------------------------------------------------------------
# POST /generate-now
# ---------------------------------------------------------------------------

class TestGenerateNow:

    @pytest.mark.asyncio
    async def test_returns_202_accepted(self):
        db = _make_db()
        user = _make_user()
        _query_returning(db, None)  # no existing briefing

        mock_gen = MagicMock()
        mock_gen.apply_async = MagicMock()

        with patch("routes.briefing_routes._get_deps",
                   return_value=(MagicMock(), MagicMock())), \
             patch("routes.briefing_routes.MorningBriefingService") as MockSvc, \
             patch("routes.briefing_routes.generate_user_briefing", mock_gen):
            MockSvc.determine_level.return_value = "individual"
            response = await generate_now(force=False, db=db, current_user=user)

        from fastapi.responses import JSONResponse
        assert isinstance(response, JSONResponse)
        assert response.status_code == 202

    @pytest.mark.asyncio
    async def test_enqueues_task_with_correct_args(self):
        db = _make_db()
        user = _make_user(user_id=42, tz="America/New_York")
        _query_returning(db, None)

        mock_gen = MagicMock()

        with patch("routes.briefing_routes._get_deps",
                   return_value=(MagicMock(), MagicMock())), \
             patch("routes.briefing_routes.MorningBriefingService") as MockSvc, \
             patch("routes.briefing_routes.generate_user_briefing", mock_gen):
            MockSvc.determine_level.return_value = "manager"
            await generate_now(force=False, db=db, current_user=user)

        mock_gen.apply_async.assert_called_once()
        call_args = mock_gen.apply_async.call_args[1]["args"]
        assert call_args[0] == 42
        assert call_args[2] == "manager"

    @pytest.mark.asyncio
    async def test_returns_409_when_existing_no_force(self):
        from fastapi import HTTPException
        db = _make_db()
        user = _make_user()
        existing = _make_briefing()
        _query_returning(db, existing)

        with patch("routes.briefing_routes._get_deps",
                   return_value=(MagicMock(), MagicMock())), \
             patch("routes.briefing_routes.MorningBriefingService") as MockSvc:
            MockSvc.determine_level.return_value = "individual"
            with pytest.raises(HTTPException) as exc_info:
                await generate_now(force=False, db=db, current_user=user)

        assert exc_info.value.status_code == 409

    @pytest.mark.asyncio
    async def test_force_true_deletes_existing_and_regenerates(self):
        db = _make_db()
        user = _make_user(user_id=5)
        existing = _make_briefing(bid=99)
        _query_returning(db, existing)

        mock_gen = MagicMock()

        with patch("routes.briefing_routes._get_deps",
                   return_value=(MagicMock(), MagicMock())), \
             patch("routes.briefing_routes.MorningBriefingService") as MockSvc, \
             patch("routes.briefing_routes.generate_user_briefing", mock_gen):
            MockSvc.determine_level.return_value = "individual"
            response = await generate_now(force=True, db=db, current_user=user)

        db.delete.assert_called_once_with(existing)
        db.commit.assert_called_once()
        mock_gen.apply_async.assert_called_once()
        assert response.status_code == 202


# ---------------------------------------------------------------------------
# POST /{briefing_id}/viewed
# ---------------------------------------------------------------------------

class TestMarkViewed:

    @pytest.mark.asyncio
    async def test_marks_viewed_and_returns_ok(self):
        db = _make_db()
        user = _make_user(user_id=1)
        briefing = _make_briefing(bid=10, viewed_at=None)
        _query_returning(db, briefing)

        with patch("routes.briefing_routes._get_deps",
                   return_value=(MagicMock(), MagicMock())):
            result = await mark_viewed(briefing_id=10, db=db, current_user=user)

        assert result == {"status": "ok"}
        assert briefing.viewed_in_app_at is not None
        db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_raises_404_when_not_found(self):
        from fastapi import HTTPException
        db = _make_db()
        user = _make_user()
        _query_returning(db, None)

        with patch("routes.briefing_routes._get_deps",
                   return_value=(MagicMock(), MagicMock())):
            with pytest.raises(HTTPException) as exc_info:
                await mark_viewed(briefing_id=999, db=db, current_user=user)

        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_does_not_overwrite_existing_viewed_at(self):
        db = _make_db()
        user = _make_user()
        original_ts = datetime(2026, 3, 16, 8, 0, tzinfo=timezone.utc)
        briefing = _make_briefing(viewed_at=original_ts)
        _query_returning(db, briefing)

        with patch("routes.briefing_routes._get_deps",
                   return_value=(MagicMock(), MagicMock())):
            await mark_viewed(briefing_id=1, db=db, current_user=user)

        # viewed_in_app_at should remain unchanged, commit not called again
        assert briefing.viewed_in_app_at == original_ts
        db.commit.assert_not_called()


# ---------------------------------------------------------------------------
# GET /preferences
# ---------------------------------------------------------------------------

class TestGetPreferences:

    @pytest.mark.asyncio
    async def test_returns_all_preference_fields(self):
        db = _make_db()
        user = _make_user(briefing_enabled=True, briefing_hour=6,
                          tz="America/New_York")
        prefs = MagicMock()
        prefs.sections = {"pipeline": True, "at_risk": True}
        prefs.thresholds = {"at_risk_days": 10}
        prefs.ai_tone = "concise"

        with patch("routes.briefing_routes.MorningBriefingService") as MockSvc:
            MockSvc.load_preferences.return_value = prefs
            result = await get_preferences(db=db, current_user=user)

        assert result["briefing_enabled"] is True
        assert result["briefing_hour"] == 6
        assert result["timezone"] == "America/New_York"
        assert result["ai_tone"] == "concise"

    @pytest.mark.asyncio
    async def test_defaults_briefing_hour_to_7_when_none(self):
        db = _make_db()
        user = _make_user(briefing_hour=None)
        prefs = MagicMock()
        prefs.sections = {}
        prefs.thresholds = {}
        prefs.ai_tone = "balanced"

        with patch("routes.briefing_routes.MorningBriefingService") as MockSvc:
            MockSvc.load_preferences.return_value = prefs
            result = await get_preferences(db=db, current_user=user)

        assert result["briefing_hour"] == 7

    @pytest.mark.asyncio
    async def test_defaults_briefing_enabled_true_when_none(self):
        db = _make_db()
        user = _make_user(briefing_enabled=None)
        prefs = MagicMock()
        prefs.sections = {}
        prefs.thresholds = {}
        prefs.ai_tone = "balanced"

        with patch("routes.briefing_routes.MorningBriefingService") as MockSvc:
            MockSvc.load_preferences.return_value = prefs
            result = await get_preferences(db=db, current_user=user)

        assert result["briefing_enabled"] is True


# ---------------------------------------------------------------------------
# PUT /preferences
# ---------------------------------------------------------------------------

class TestUpdatePreferences:

    def _make_prefs_payload(self, enabled=True, hour=7,
                             ai_tone="balanced"):
        return BriefingPreferencesSchema(
            briefing_enabled=enabled,
            briefing_hour=hour,
            sections=BriefingSections(),
            thresholds=BriefingThresholds(),
            ai_tone=ai_tone,
        )

    @pytest.mark.asyncio
    async def test_persists_dedicated_columns(self):
        db = _make_db()
        user = _make_user()
        payload = self._make_prefs_payload(enabled=False, hour=9)

        loaded = MagicMock()
        loaded.sections = {}
        loaded.thresholds = {}
        loaded.ai_tone = "balanced"

        with patch("routes.briefing_routes.MorningBriefingService") as MockSvc:
            MockSvc.load_preferences.return_value = loaded
            await update_preferences(prefs=payload, db=db, current_user=user)

        assert user.briefing_enabled is False
        assert user.briefing_hour == 9
        db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_persists_jsonb_preferences(self):
        db = _make_db()
        user = _make_user()
        payload = self._make_prefs_payload(ai_tone="concise")

        loaded = MagicMock()
        loaded.sections = {}
        loaded.thresholds = {}
        loaded.ai_tone = "concise"

        with patch("routes.briefing_routes.MorningBriefingService") as MockSvc:
            MockSvc.load_preferences.return_value = loaded
            await update_preferences(prefs=payload, db=db, current_user=user)

        jsonb = user.briefing_preferences
        assert jsonb["ai_tone"] == "concise"
        assert "sections" in jsonb
        assert "thresholds" in jsonb

    @pytest.mark.asyncio
    async def test_returns_updated_values(self):
        db = _make_db()
        user = _make_user(briefing_hour=7, tz="America/Denver")
        payload = self._make_prefs_payload(hour=8, ai_tone="detailed")

        loaded = MagicMock()
        loaded.sections = {"pipeline": True}
        loaded.thresholds = {"at_risk_days": 10}
        loaded.ai_tone = "detailed"

        with patch("routes.briefing_routes.MorningBriefingService") as MockSvc:
            MockSvc.load_preferences.return_value = loaded
            result = await update_preferences(prefs=payload, db=db, current_user=user)

        assert result["briefing_hour"] == 8
        assert result["ai_tone"] == "detailed"
        assert result["timezone"] == "America/Denver"

    @pytest.mark.asyncio
    async def test_sections_stored_as_dict(self):
        db = _make_db()
        user = _make_user()
        sections = BriefingSections(pipeline=True, at_risk=False, stale_leads=True,
                                    appointments=True, conditions=False, yesterday=True)
        payload = BriefingPreferencesSchema(
            briefing_enabled=True, briefing_hour=7,
            sections=sections, thresholds=BriefingThresholds(), ai_tone="balanced",
        )

        loaded = MagicMock()
        loaded.sections = sections.model_dump()
        loaded.thresholds = {}
        loaded.ai_tone = "balanced"

        with patch("routes.briefing_routes.MorningBriefingService") as MockSvc:
            MockSvc.load_preferences.return_value = loaded
            await update_preferences(prefs=payload, db=db, current_user=user)

        stored_sections = user.briefing_preferences["sections"]
        assert stored_sections["at_risk"] is False
        assert stored_sections["pipeline"] is True


# ---------------------------------------------------------------------------
# Pydantic schema validation
# ---------------------------------------------------------------------------

class TestBriefingSchemas:

    def test_preferences_schema_defaults(self):
        p = BriefingPreferencesSchema()
        assert p.briefing_enabled is True
        assert p.briefing_hour == 7
        assert p.ai_tone == "balanced"

    def test_preferences_schema_hour_bounds(self):
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            BriefingPreferencesSchema(briefing_hour=24)
        with pytest.raises(ValidationError):
            BriefingPreferencesSchema(briefing_hour=-1)

    def test_preferences_schema_valid_hour_boundary(self):
        p = BriefingPreferencesSchema(briefing_hour=0)
        assert p.briefing_hour == 0
        p2 = BriefingPreferencesSchema(briefing_hour=23)
        assert p2.briefing_hour == 23

    def test_thresholds_at_risk_days_bounds(self):
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            BriefingThresholds(at_risk_days=0)
        with pytest.raises(ValidationError):
            BriefingThresholds(at_risk_days=31)

    def test_thresholds_stale_lead_days_bounds(self):
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            BriefingThresholds(stale_lead_days=0)
        with pytest.raises(ValidationError):
            BriefingThresholds(stale_lead_days=31)

    def test_invalid_ai_tone_rejected(self):
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            BriefingPreferencesSchema(ai_tone="aggressive")

    def test_all_valid_ai_tones_accepted(self):
        for tone in ("concise", "balanced", "detailed"):
            p = BriefingPreferencesSchema(ai_tone=tone)
            assert p.ai_tone == tone
