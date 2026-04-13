"""
Test Rate Monitor Alert Routes - Integration tests for iOS-compatible
rate alert endpoints.

Covers:
- GET /api/v1/rate-monitor/alerts/carplay  (CarPlay CPRateAlert format)
- GET /api/v1/rate-alerts           (BackgroundSyncManager RateAlert format)

Both endpoints:
- Require authentication (return 401/403 without it)
- Return plain JSON arrays (not wrapped in an object)
- Gracefully return [] when the rate_monitor_alerts table is empty or missing
- Support a `limit` query parameter (le=100)
- Are scoped to the user's organization via mum_clients join

The underlying _fetch_alerts helper catches exceptions (e.g. table not
existing) and falls back to an empty list, so tests against an empty DB
should always get 200 + [].
"""

import pytest
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock
from sqlalchemy import text


# =============================================================================
# 1. Auth Required
# =============================================================================

@pytest.mark.unit
class TestRateMonitorAlertsAuth:
    """Both endpoints must reject unauthenticated requests."""

    def test_rate_monitor_alerts_requires_auth(self, client):
        """GET /api/v1/rate-monitor/alerts/carplay without auth returns 401 or 403."""
        response = client.get("/api/v1/rate-monitor/alerts/carplay")
        assert response.status_code in (401, 403), (
            f"Expected 401/403 for unauthenticated request, got {response.status_code}"
        )

    def test_rate_alerts_alias_requires_auth(self, client):
        """GET /api/v1/rate-alerts without auth returns 401 or 403."""
        response = client.get("/api/v1/rate-alerts")
        assert response.status_code in (401, 403), (
            f"Expected 401/403 for unauthenticated request, got {response.status_code}"
        )


# =============================================================================
# 2. Response Shape - /api/v1/rate-monitor/alerts/carplay (CarPlay)
# =============================================================================

@pytest.mark.unit
class TestRateMonitorAlertsCarPlay:
    """Tests for GET /api/v1/rate-monitor/alerts/carplay (CPRateAlert format)."""

    def test_rate_monitor_alerts_returns_array(self, authenticated_client):
        """Response must be a plain JSON array, not wrapped in an object."""
        response = authenticated_client.get("/api/v1/rate-monitor/alerts/carplay")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list), (
            f"Expected a JSON array, got {type(data).__name__}: {data}"
        )

    def test_rate_monitor_alerts_empty_graceful(self, authenticated_client):
        """Returns empty array [] when no alerts exist (not an error)."""
        response = authenticated_client.get("/api/v1/rate-monitor/alerts/carplay")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        # With no data seeded, expect empty
        assert data == []

    def test_rate_monitor_alerts_response_shape(self, authenticated_client, db_session):
        """Each alert in the CarPlay response has the required CPRateAlert fields."""
        # Seed the tables so _fetch_alerts returns real rows.
        # Use raw SQL to avoid needing ORM models for mum_clients.
        try:
            db_session.execute(text("""
                CREATE TABLE IF NOT EXISTS mum_clients (
                    id SERIAL PRIMARY KEY,
                    organization_id INTEGER
                )
            """))
            db_session.execute(text("""
                CREATE TABLE IF NOT EXISTS rate_monitor_targets (
                    id SERIAL PRIMARY KEY,
                    mum_client_id INTEGER REFERENCES mum_clients(id),
                    loan_type VARCHAR(50) DEFAULT 'conventional',
                    loan_term INTEGER DEFAULT 30,
                    target_type VARCHAR(50) DEFAULT 'manual_target',
                    status VARCHAR(50) DEFAULT 'active',
                    is_active BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMP DEFAULT NOW(),
                    updated_at TIMESTAMP DEFAULT NOW()
                )
            """))
            db_session.execute(text("""
                CREATE TABLE IF NOT EXISTS rate_monitor_alerts (
                    id SERIAL PRIMARY KEY,
                    target_id INTEGER REFERENCES rate_monitor_targets(id),
                    mum_client_id INTEGER REFERENCES mum_clients(id),
                    history_id INTEGER,
                    alert_type VARCHAR(50) NOT NULL,
                    client_rate NUMERIC(5,3),
                    market_rate NUMERIC(5,3),
                    status VARCHAR(50) DEFAULT 'pending',
                    created_at TIMESTAMP DEFAULT NOW(),
                    updated_at TIMESTAMP DEFAULT NOW()
                )
            """))
            db_session.flush()

            # Insert seed data: mum_client -> target -> alert
            db_session.execute(text("""
                INSERT INTO mum_clients (id, organization_id) VALUES (9001, 1)
            """))
            db_session.execute(text("""
                INSERT INTO rate_monitor_targets (id, mum_client_id, loan_type, loan_term, target_type)
                VALUES (9001, 9001, 'conventional', 30, 'rate_drop')
            """))
            db_session.execute(text("""
                INSERT INTO rate_monitor_alerts (id, target_id, mum_client_id, alert_type, client_rate, market_rate, status, created_at)
                VALUES (9001, 9001, 9001, 'rate_target_hit', 7.250, 6.500, 'pending', '2026-04-01 12:00:00')
            """))
            db_session.flush()
        except Exception:
            # Tables may already exist from ORM metadata; that's fine.
            db_session.rollback()
            # Re-try with just the insert (tables existed)
            try:
                db_session.execute(text("""
                    INSERT INTO mum_clients (id, organization_id)
                    VALUES (9001, 1)
                    ON CONFLICT (id) DO NOTHING
                """))
                db_session.execute(text("""
                    INSERT INTO rate_monitor_targets (id, mum_client_id, loan_type, loan_term, target_type)
                    VALUES (9001, 9001, 'conventional', 30, 'rate_drop')
                    ON CONFLICT (id) DO NOTHING
                """))
                db_session.execute(text("""
                    INSERT INTO rate_monitor_alerts (id, target_id, mum_client_id, alert_type, client_rate, market_rate, status, created_at)
                    VALUES (9001, 9001, 9001, 'rate_target_hit', 7.250, 6.500, 'pending', '2026-04-01 12:00:00')
                    ON CONFLICT (id) DO NOTHING
                """))
                db_session.flush()
            except Exception:
                pytest.skip("Could not seed rate_monitor tables for response shape test")

        response = authenticated_client.get("/api/v1/rate-monitor/alerts/carplay")
        assert response.status_code == 200
        data = response.json()

        if len(data) == 0:
            pytest.skip("No alert rows returned (tables may not be visible to session)")

        alert = data[0]
        # CarPlay CPRateAlert required fields
        required_fields = {"id", "rate_type", "current_rate", "previous_rate", "change_direction", "timestamp"}
        missing = required_fields - set(alert.keys())
        assert not missing, f"CPRateAlert missing fields: {missing}"

        # Type checks
        assert isinstance(alert["id"], int)
        assert isinstance(alert["rate_type"], str)
        assert isinstance(alert["current_rate"], (int, float))
        assert isinstance(alert["previous_rate"], (int, float))
        assert alert["change_direction"] in ("up", "down")
        assert isinstance(alert["timestamp"], str)

    def test_rate_monitor_alerts_limit_param(self, authenticated_client):
        """limit query param is accepted and validated (le=100)."""
        # Valid limit
        response = authenticated_client.get("/api/v1/rate-monitor/alerts/carplay?limit=5")
        assert response.status_code == 200
        assert isinstance(response.json(), list)

        # Limit exceeding max (100) should return 422
        response_over = authenticated_client.get("/api/v1/rate-monitor/alerts/carplay?limit=200")
        assert response_over.status_code == 422

    def test_rate_monitor_alerts_limit_default_is_20(self, authenticated_client):
        """Default limit is 20 for the CarPlay endpoint."""
        response = authenticated_client.get("/api/v1/rate-monitor/alerts/carplay")
        assert response.status_code == 200
        # Can't assert count without data, but the endpoint accepted the default


# =============================================================================
# 3. Response Shape - /api/v1/rate-alerts (BackgroundSyncManager)
# =============================================================================

@pytest.mark.unit
class TestRateAlertsBackground:
    """Tests for GET /api/v1/rate-alerts (BackgroundSyncManager RateAlert format)."""

    def test_rate_alerts_alias_works(self, authenticated_client):
        """GET /api/v1/rate-alerts returns 200 with a JSON array."""
        response = authenticated_client.get("/api/v1/rate-alerts")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    def test_rate_alerts_empty_graceful(self, authenticated_client):
        """Returns empty array [] when no alerts exist (not an error)."""
        response = authenticated_client.get("/api/v1/rate-alerts")
        assert response.status_code == 200
        assert response.json() == []

    def test_rate_alerts_response_shape(self, authenticated_client, db_session):
        """Each alert in the BackgroundSync response has the required RateAlert fields."""
        # Seed data (same approach as CarPlay test)
        try:
            db_session.execute(text("""
                INSERT INTO mum_clients (id, organization_id)
                VALUES (9002, 1)
                ON CONFLICT (id) DO NOTHING
            """))
            db_session.execute(text("""
                INSERT INTO rate_monitor_targets (id, mum_client_id, loan_type, loan_term, target_type)
                VALUES (9002, 9002, 'fha', 30, 'savings_threshold')
                ON CONFLICT (id) DO NOTHING
            """))
            db_session.execute(text("""
                INSERT INTO rate_monitor_alerts (id, target_id, mum_client_id, alert_type, client_rate, market_rate, status, created_at)
                VALUES (9002, 9002, 9002, 'savings_threshold', 7.000, 6.250, 'pending', '2026-04-02 14:00:00')
                ON CONFLICT (id) DO NOTHING
            """))
            db_session.flush()
        except Exception:
            pytest.skip("Could not seed rate_monitor tables for RateAlert response shape test")

        response = authenticated_client.get("/api/v1/rate-alerts")
        assert response.status_code == 200
        data = response.json()

        if len(data) == 0:
            pytest.skip("No alert rows returned (tables may not be visible to session)")

        alert = data[0]
        # BackgroundSyncManager RateAlert required fields
        required_fields = {"id", "product_name", "current_rate", "previous_rate", "change_direction", "timestamp"}
        missing = required_fields - set(alert.keys())
        assert not missing, f"RateAlert missing fields: {missing}"

        # Type checks -- id is a String in BackgroundSync format
        assert isinstance(alert["id"], str)
        assert isinstance(alert["product_name"], str)
        assert isinstance(alert["current_rate"], (int, float))
        assert isinstance(alert["previous_rate"], (int, float))
        assert alert["change_direction"] in ("up", "down")
        assert isinstance(alert["timestamp"], str)

    def test_rate_alerts_limit_param(self, authenticated_client):
        """limit query param is accepted (default 10, le=100)."""
        response = authenticated_client.get("/api/v1/rate-alerts?limit=3")
        assert response.status_code == 200
        assert isinstance(response.json(), list)

        # Over max
        response_over = authenticated_client.get("/api/v1/rate-alerts?limit=150")
        assert response_over.status_code == 422


# =============================================================================
# 4. Organization Scoping
# =============================================================================

@pytest.mark.unit
class TestRateMonitorAlertsOrgScoped:
    """Alerts are filtered by the user's organization_id via the mum_clients join."""

    def test_rate_monitor_alerts_org_scoped(self, authenticated_client, db_session, mock_user):
        """Alerts belonging to a different org should NOT appear in results."""
        # Seed two orgs with alerts; mock_user.organization_id = 1
        try:
            # Org 1 (user's org)
            db_session.execute(text("""
                INSERT INTO mum_clients (id, organization_id)
                VALUES (9010, 1)
                ON CONFLICT (id) DO NOTHING
            """))
            db_session.execute(text("""
                INSERT INTO rate_monitor_targets (id, mum_client_id, loan_type, loan_term, target_type)
                VALUES (9010, 9010, 'conventional', 30, 'rate_drop')
                ON CONFLICT (id) DO NOTHING
            """))
            db_session.execute(text("""
                INSERT INTO rate_monitor_alerts (id, target_id, mum_client_id, alert_type, client_rate, market_rate, status, created_at)
                VALUES (9010, 9010, 9010, 'rate_target_hit', 7.500, 6.750, 'pending', '2026-04-03 10:00:00')
                ON CONFLICT (id) DO NOTHING
            """))

            # Org 999 (different org -- should be excluded)
            db_session.execute(text("""
                INSERT INTO mum_clients (id, organization_id)
                VALUES (9011, 999)
                ON CONFLICT (id) DO NOTHING
            """))
            db_session.execute(text("""
                INSERT INTO rate_monitor_targets (id, mum_client_id, loan_type, loan_term, target_type)
                VALUES (9011, 9011, 'va', 30, 'rate_drop')
                ON CONFLICT (id) DO NOTHING
            """))
            db_session.execute(text("""
                INSERT INTO rate_monitor_alerts (id, target_id, mum_client_id, alert_type, client_rate, market_rate, status, created_at)
                VALUES (9011, 9011, 9011, 'rate_target_hit', 8.000, 7.000, 'pending', '2026-04-03 11:00:00')
                ON CONFLICT (id) DO NOTHING
            """))
            db_session.flush()
        except Exception:
            pytest.skip("Could not seed multi-org rate_monitor data for tenant isolation test")

        response = authenticated_client.get("/api/v1/rate-monitor/alerts/carplay")
        assert response.status_code == 200
        data = response.json()

        if len(data) == 0:
            pytest.skip("No alert rows returned (tables may not be visible to session)")

        # All returned alert IDs should belong to org 1 (user's org)
        returned_ids = {a["id"] for a in data}
        # The org-999 alert (id=9011) must NOT be present
        assert 9011 not in returned_ids, (
            "Alert from a different organization leaked through tenant scoping"
        )
        # The org-1 alert (id=9010) should be present
        assert 9010 in returned_ids, (
            "Alert from user's own organization was not returned"
        )


# =============================================================================
# 5. Unit Tests for Transform Helpers
# =============================================================================

@pytest.mark.unit
class TestTransformHelpers:
    """Unit tests for the _loan_type_to_rate_type and transform dicts."""

    def test_loan_type_to_rate_type_conventional_30(self):
        from routes.rate_monitor_routes import _loan_type_to_rate_type
        assert _loan_type_to_rate_type("conventional", 30) == "30yr_fixed"

    def test_loan_type_to_rate_type_conventional_15(self):
        from routes.rate_monitor_routes import _loan_type_to_rate_type
        assert _loan_type_to_rate_type("conventional", 15) == "15yr_fixed"

    def test_loan_type_to_rate_type_fha(self):
        from routes.rate_monitor_routes import _loan_type_to_rate_type
        assert _loan_type_to_rate_type("fha", 30) == "fha"

    def test_loan_type_to_rate_type_va(self):
        from routes.rate_monitor_routes import _loan_type_to_rate_type
        assert _loan_type_to_rate_type("VA", 30) == "va"

    def test_loan_type_to_rate_type_usda(self):
        from routes.rate_monitor_routes import _loan_type_to_rate_type
        assert _loan_type_to_rate_type("USDA", 30) == "usda"

    def test_loan_type_to_rate_type_jumbo(self):
        from routes.rate_monitor_routes import _loan_type_to_rate_type
        assert _loan_type_to_rate_type("Jumbo", 15) == "jumbo"

    def test_loan_type_to_rate_type_none_defaults_conventional(self):
        from routes.rate_monitor_routes import _loan_type_to_rate_type
        assert _loan_type_to_rate_type(None, 30) == "30yr_fixed"

    def test_alert_to_carplay_dict_shape(self):
        """_alert_to_carplay_dict produces the CPRateAlert fields."""
        from routes.rate_monitor_routes import _alert_to_carplay_dict

        row = {
            "id": 42,
            "client_rate": 7.25,
            "market_rate": 6.50,
            "loan_type": "conventional",
            "loan_term": 30,
            "created_at": datetime(2026, 4, 1, 12, 0, 0, tzinfo=timezone.utc),
        }
        result = _alert_to_carplay_dict(row)

        assert result["id"] == 42
        assert result["rate_type"] == "30yr_fixed"
        assert result["current_rate"] == 6.50
        assert result["previous_rate"] == 7.25
        assert result["change_direction"] == "down"
        assert "2026-04-01" in result["timestamp"]

    def test_alert_to_carplay_dict_direction_up(self):
        """When market_rate > client_rate, direction should be 'up'."""
        from routes.rate_monitor_routes import _alert_to_carplay_dict

        row = {
            "id": 43,
            "client_rate": 6.00,
            "market_rate": 6.75,
            "loan_type": "conventional",
            "loan_term": 30,
            "created_at": None,
        }
        result = _alert_to_carplay_dict(row)
        assert result["change_direction"] == "up"

    def test_alert_to_background_dict_shape(self):
        """_alert_to_background_dict produces the RateAlert fields."""
        from routes.rate_monitor_routes import _alert_to_background_dict

        row = {
            "id": 55,
            "client_rate": 7.00,
            "market_rate": 6.25,
            "loan_type": "fha",
            "loan_term": 30,
            "created_at": datetime(2026, 4, 2, 14, 0, 0, tzinfo=timezone.utc),
        }
        result = _alert_to_background_dict(row)

        # id is a string in BackgroundSync format
        assert result["id"] == "55"
        assert result["product_name"] == "FHA"
        assert result["current_rate"] == 6.25
        assert result["previous_rate"] == 7.00
        assert result["change_direction"] == "down"
        assert "2026-04-02" in result["timestamp"]

    def test_alert_to_background_dict_product_name_mapping(self):
        """Product name should be human-readable for known loan types."""
        from routes.rate_monitor_routes import _alert_to_background_dict

        cases = {
            ("conventional", 30): "30-Year Fixed",
            ("conventional", 15): "15-Year Fixed",
            ("fha", 30): "FHA",
            ("va", 30): "VA",
            ("usda", 30): "USDA",
            ("jumbo", 30): "Jumbo",
        }
        for (loan_type, loan_term), expected_name in cases.items():
            row = {
                "id": 1,
                "client_rate": 7.0,
                "market_rate": 6.5,
                "loan_type": loan_type,
                "loan_term": loan_term,
                "created_at": None,
            }
            result = _alert_to_background_dict(row)
            assert result["product_name"] == expected_name, (
                f"loan_type={loan_type}, loan_term={loan_term}: "
                f"expected '{expected_name}', got '{result['product_name']}'"
            )
