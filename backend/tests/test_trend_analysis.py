import pytest
from unittest.mock import patch
from services.trend_email import render_trend_report_html


def test_render_trend_report_html_notable_changes():
    insights = [
        {
            "domain": "leads",
            "metric": "new_lead_count",
            "label": "New Leads",
            "current_value": 50,
            "prior_value": 30,
            "delta_pct": 66.7,
            "direction": "up",
            "significance": 66.7,
            "context": "Web source drove the increase",
            "is_positive": True,
            "unit": "count",
        },
        {
            "domain": "loans",
            "metric": "funded_volume",
            "label": "Funded Volume",
            "current_value": 2500000,
            "prior_value": 2000000,
            "delta_pct": 25.0,
            "direction": "up",
            "significance": 25.0,
            "context": "",
            "is_positive": True,
            "unit": "currency",
        },
    ]
    html = render_trend_report_html(
        insights=insights,
        period_label="Apr 7 – May 7, 2026 vs Mar 8 – Apr 7, 2026",
        time_window="month",
    )
    assert "Notable Changes" in html
    assert "New Leads" in html
    assert "66.7%" in html
    assert "Funded Volume" in html
    assert "&lt;html" in html or "<html" in html


def test_render_empty_insights():
    html = render_trend_report_html(
        insights=[],
        period_label="test period",
        time_window="month",
    )
    assert "No significant trends" in html


# ---------------------------------------------------------------------------
# trend_analysis helpers
# ---------------------------------------------------------------------------

from agents.tools.trend_analysis import _get_period_dates, _make_insight, _owner_filter


def test_get_period_dates_month():
    start, end, prior_start, prior_end = _get_period_dates("month")
    from datetime import datetime, timedelta
    now = datetime.now()
    assert end == now.strftime("%Y-%m-%d")
    expected_start = (now - timedelta(days=30)).strftime("%Y-%m-%d")
    assert start == expected_start


def test_get_period_dates_week():
    start, end, prior_start, prior_end = _get_period_dates("week")
    from datetime import datetime, timedelta
    now = datetime.now()
    expected_start = (now - timedelta(days=7)).strftime("%Y-%m-%d")
    assert start == expected_start


def test_make_insight_up():
    ins = _make_insight("leads", "new_leads", "New Leads", 50, 30, True, "count")
    assert ins["direction"] == "up"
    assert ins["delta_pct"] == pytest.approx(66.67, abs=0.1)
    assert ins["is_positive"] is True


def test_make_insight_zero_prior():
    ins = _make_insight("leads", "new_leads", "New Leads", 10, 0, True, "count")
    assert ins["direction"] == "up"
    assert ins["delta_pct"] == 100.0


def test_make_insight_down_bad():
    ins = _make_insight("leads", "new_leads", "New Leads", 20, 50, True, "count")
    assert ins["direction"] == "down"
    assert ins["is_positive"] is False


def test_make_insight_flat():
    ins = _make_insight("leads", "x", "X", 100, 99, True, "count")
    assert ins["direction"] == "flat"


def test_owner_filter_lo():
    sql, params = _owner_filter("sales", 42, "owner_id")
    assert "owner_id" in sql
    assert params["scope_user_id"] == 42


def test_owner_filter_admin():
    sql, params = _owner_filter("admin", 42, "owner_id")
    assert sql == ""
    assert params == {}
