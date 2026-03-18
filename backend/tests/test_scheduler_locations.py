"""
Tests for scheduler location routes.

Covers:
  - GET    /locations              List active locations for the org
  - POST   /locations              Create a new location
  - PUT    /locations/{id}         Update a location
  - DELETE /locations/{id}         Soft-delete (deactivate) a location
  - PUT    /locations/{id}/default Set a location as the org default

Edge cases: auth required (401), missing location (404), invalid location_type,
tenant isolation (different org_id), and default location management.
"""

import pytest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch, AsyncMock
from fastapi import HTTPException

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class MockUser:
    def __init__(self, id=1, organization_id=1, role="loan_officer", email="lo@test.com"):
        self.id = id
        self.organization_id = organization_id
        self.role = role
        self.permission_role = role
        self.email = email


class MockLocation:
    """Minimal appointment location mock."""
    def __init__(self, **kwargs):
        self.id = kwargs.get("id", 10)
        self.organization_id = kwargs.get("organization_id", 1)
        self.user_id = kwargs.get("user_id", None)
        self.name = kwargs.get("name", "Main Office")
        self.location_type = kwargs.get("location_type", "office")
        self.address_line1 = kwargs.get("address_line1", "123 Main St")
        self.address_line2 = kwargs.get("address_line2", None)
        self.city = kwargs.get("city", "Austin")
        self.state = kwargs.get("state", "TX")
        self.zip_code = kwargs.get("zip_code", "78701")
        self.meeting_url = kwargs.get("meeting_url", None)
        self.phone_number = kwargs.get("phone_number", None)
        self.instructions = kwargs.get("instructions", "Park in rear lot")
        self.is_default = kwargs.get("is_default", False)
        self.is_active = kwargs.get("is_active", True)
        self.created_at = kwargs.get("created_at", datetime(2026, 1, 15, tzinfo=timezone.utc))
        self.updated_at = kwargs.get("updated_at", datetime(2026, 3, 1, tzinfo=timezone.utc))


def _mock_db_query_chain(results=None):
    """Create a mock DB query chain that returns the given results."""
    query_mock = MagicMock()
    query_mock.filter = MagicMock(return_value=query_mock)
    query_mock.order_by = MagicMock(return_value=query_mock)
    query_mock.all = MagicMock(return_value=results or [])
    query_mock.first = MagicMock(return_value=results[0] if results else None)
    return query_mock


# ---------------------------------------------------------------------------
# Tests: Serialization Helper
# ---------------------------------------------------------------------------

class TestSerializeLocation:
    """Tests for _serialize_location helper."""

    def test_serialize_all_fields(self):
        """Serialization should include all expected fields."""
        from routes.scheduler.locations import _serialize_location

        loc = MockLocation()
        result = _serialize_location(loc)

        assert result["id"] == 10
        assert result["name"] == "Main Office"
        assert result["location_type"] == "office"
        assert result["address_line1"] == "123 Main St"
        assert result["city"] == "Austin"
        assert result["state"] == "TX"
        assert result["zip_code"] == "78701"
        assert result["is_default"] is False
        assert result["is_active"] is True
        assert result["created_at"] is not None

    def test_serialize_none_timestamps(self):
        """None timestamps should serialize as None."""
        from routes.scheduler.locations import _serialize_location

        loc = MockLocation(created_at=None, updated_at=None)
        result = _serialize_location(loc)

        assert result["created_at"] is None
        assert result["updated_at"] is None


# ---------------------------------------------------------------------------
# Tests: Validation Helper
# ---------------------------------------------------------------------------

class TestValidateLocationType:
    """Tests for _validate_location_type helper."""

    def test_valid_types_accepted(self):
        """Valid location types should not raise."""
        from routes.scheduler.locations import _validate_location_type

        for lt in ("office", "virtual", "phone", "borrower_home"):
            _validate_location_type(lt)  # Should not raise

    def test_invalid_type_raises_400(self):
        """Invalid location type should raise HTTPException 400."""
        from routes.scheduler.locations import _validate_location_type

        with pytest.raises(HTTPException) as exc_info:
            _validate_location_type("warehouse")
        assert exc_info.value.status_code == 400
        assert "Invalid location_type" in exc_info.value.detail


# ---------------------------------------------------------------------------
# Tests: GET /locations
# ---------------------------------------------------------------------------

class TestListLocations:
    """Tests for GET /locations."""

    @pytest.mark.asyncio
    async def test_list_locations_requires_auth(self):
        """Unauthenticated requests should return 401."""
        from routes.scheduler.locations import list_locations

        with patch("routes.scheduler.locations.get_current_user",
                   new_callable=AsyncMock,
                   side_effect=HTTPException(status_code=401, detail="Not authenticated")):
            with pytest.raises(HTTPException) as exc_info:
                await list_locations(MagicMock(), False, MagicMock())
            assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_list_locations_happy_path(self):
        """Authenticated user gets their org's locations."""
        from routes.scheduler.locations import list_locations

        user = MockUser()
        loc1 = MockLocation(id=10, name="Main Office", is_default=True)
        loc2 = MockLocation(id=11, name="Virtual Room", location_type="virtual")

        db = MagicMock()
        query_mock = _mock_db_query_chain([loc1, loc2])
        db.query = MagicMock(return_value=query_mock)

        with patch("routes.scheduler.locations.get_current_user",
                   new_callable=AsyncMock, return_value=user):
            result = await list_locations(MagicMock(), False, db)

        assert result["total"] == 2
        assert len(result["locations"]) == 2
        assert result["locations"][0]["name"] == "Main Office"

    @pytest.mark.asyncio
    async def test_list_locations_empty(self):
        """No locations should return empty list with total 0."""
        from routes.scheduler.locations import list_locations

        user = MockUser()
        db = MagicMock()
        query_mock = _mock_db_query_chain([])
        db.query = MagicMock(return_value=query_mock)

        with patch("routes.scheduler.locations.get_current_user",
                   new_callable=AsyncMock, return_value=user):
            result = await list_locations(MagicMock(), False, db)

        assert result["total"] == 0
        assert result["locations"] == []


# ---------------------------------------------------------------------------
# Tests: POST /locations
# ---------------------------------------------------------------------------

class TestCreateLocation:
    """Tests for POST /locations."""

    @pytest.mark.asyncio
    async def test_create_location_requires_auth(self):
        """Unauthenticated requests should return 401."""
        from routes.scheduler.locations import create_location, LocationCreate

        body = LocationCreate(name="Test Office", location_type="office")

        with patch("routes.scheduler.locations.get_current_user",
                   new_callable=AsyncMock,
                   side_effect=HTTPException(status_code=401, detail="Not authenticated")):
            with pytest.raises(HTTPException) as exc_info:
                await create_location(body, MagicMock(), MagicMock())
            assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_create_location_happy_path(self):
        """Creating a location should return the new location."""
        from routes.scheduler.locations import create_location, LocationCreate

        user = MockUser()
        body = LocationCreate(
            name="Downtown Office",
            location_type="office",
            address_line1="456 Oak Ave",
            city="Austin",
            state="TX",
            zip_code="78702",
        )

        db = MagicMock()
        # db.add, db.commit, db.refresh are called
        created_loc = MockLocation(
            id=20, name="Downtown Office", location_type="office",
            address_line1="456 Oak Ave", city="Austin", state="TX", zip_code="78702",
        )
        db.refresh = MagicMock(side_effect=lambda x: None)

        with patch("routes.scheduler.locations.get_current_user",
                   new_callable=AsyncMock, return_value=user), \
             patch("routes.scheduler.locations.AppointmentLocation",
                   side_effect=lambda **kwargs: MockLocation(**kwargs)) as MockModel:
            # Patch the model import inside the function
            with patch("database.models.appointment_location.AppointmentLocation",
                       create=True):
                result = await create_location(body, MagicMock(), db)

        assert result["message"] == "Location created"
        assert "location" in result
        db.add.assert_called_once()
        db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_location_invalid_type_raises_400(self):
        """Invalid location_type should return 400."""
        from routes.scheduler.locations import create_location, LocationCreate

        user = MockUser()
        body = LocationCreate(name="Test", location_type="warehouse")

        with patch("routes.scheduler.locations.get_current_user",
                   new_callable=AsyncMock, return_value=user):
            with pytest.raises(HTTPException) as exc_info:
                await create_location(body, MagicMock(), MagicMock())
            assert exc_info.value.status_code == 400


# ---------------------------------------------------------------------------
# Tests: PUT /locations/{location_id}
# ---------------------------------------------------------------------------

class TestUpdateLocation:
    """Tests for PUT /locations/{id}."""

    @pytest.mark.asyncio
    async def test_update_location_not_found(self):
        """Updating a nonexistent location should return 404."""
        from routes.scheduler.locations import update_location, LocationUpdate

        user = MockUser()
        body = LocationUpdate(name="Updated Name")

        db = MagicMock()
        query_mock = _mock_db_query_chain([])  # No results = not found
        db.query = MagicMock(return_value=query_mock)

        with patch("routes.scheduler.locations.get_current_user",
                   new_callable=AsyncMock, return_value=user):
            with pytest.raises(HTTPException) as exc_info:
                await update_location(999, body, MagicMock(), db)
            assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_update_location_happy_path(self):
        """Valid update should apply changes and return updated location."""
        from routes.scheduler.locations import update_location, LocationUpdate

        user = MockUser()
        body = LocationUpdate(name="Renamed Office")

        existing = MockLocation(id=10, name="Old Name")
        db = MagicMock()
        query_mock = _mock_db_query_chain([existing])
        db.query = MagicMock(return_value=query_mock)

        with patch("routes.scheduler.locations.get_current_user",
                   new_callable=AsyncMock, return_value=user):
            result = await update_location(10, body, MagicMock(), db)

        assert result["message"] == "Location updated"
        db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_location_tenant_isolation(self):
        """Location belonging to a different org should return 404."""
        from routes.scheduler.locations import update_location, LocationUpdate

        user = MockUser(organization_id=1)
        body = LocationUpdate(name="Hacked Name")

        # The query filters by org_id, so this returns empty for wrong org
        db = MagicMock()
        query_mock = _mock_db_query_chain([])
        db.query = MagicMock(return_value=query_mock)

        with patch("routes.scheduler.locations.get_current_user",
                   new_callable=AsyncMock, return_value=user):
            with pytest.raises(HTTPException) as exc_info:
                await update_location(10, body, MagicMock(), db)
            assert exc_info.value.status_code == 404


# ---------------------------------------------------------------------------
# Tests: DELETE /locations/{location_id}
# ---------------------------------------------------------------------------

class TestDeleteLocation:
    """Tests for DELETE /locations/{id}."""

    @pytest.mark.asyncio
    async def test_delete_location_not_found(self):
        """Deleting a nonexistent location should return 404."""
        from routes.scheduler.locations import delete_location

        user = MockUser()
        db = MagicMock()
        query_mock = _mock_db_query_chain([])
        db.query = MagicMock(return_value=query_mock)

        with patch("routes.scheduler.locations.get_current_user",
                   new_callable=AsyncMock, return_value=user):
            with pytest.raises(HTTPException) as exc_info:
                await delete_location(999, MagicMock(), db)
            assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_location_soft_deletes(self):
        """Deleting should set is_active=False and is_default=False."""
        from routes.scheduler.locations import delete_location

        user = MockUser()
        loc = MockLocation(id=10, is_active=True, is_default=True)

        db = MagicMock()
        query_mock = _mock_db_query_chain([loc])
        db.query = MagicMock(return_value=query_mock)

        with patch("routes.scheduler.locations.get_current_user",
                   new_callable=AsyncMock, return_value=user):
            result = await delete_location(10, MagicMock(), db)

        assert result["message"] == "Location deactivated"
        assert result["id"] == 10
        assert loc.is_active is False
        assert loc.is_default is False
        db.commit.assert_called_once()


# ---------------------------------------------------------------------------
# Tests: PUT /locations/{location_id}/default
# ---------------------------------------------------------------------------

class TestSetDefaultLocation:
    """Tests for PUT /locations/{id}/default."""

    @pytest.mark.asyncio
    async def test_set_default_not_found(self):
        """Setting default on nonexistent location should return 404."""
        from routes.scheduler.locations import set_default_location

        user = MockUser()
        db = MagicMock()
        query_mock = _mock_db_query_chain([])
        db.query = MagicMock(return_value=query_mock)

        with patch("routes.scheduler.locations.get_current_user",
                   new_callable=AsyncMock, return_value=user):
            with pytest.raises(HTTPException) as exc_info:
                await set_default_location(999, MagicMock(), db)
            assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_set_default_happy_path(self):
        """Setting default should set is_default=True and return the location."""
        from routes.scheduler.locations import set_default_location

        user = MockUser()
        loc = MockLocation(id=10, name="Main Office", is_default=False)

        db = MagicMock()
        query_mock = _mock_db_query_chain([loc])
        db.query = MagicMock(return_value=query_mock)

        with patch("routes.scheduler.locations.get_current_user",
                   new_callable=AsyncMock, return_value=user), \
             patch("routes.scheduler.locations._clear_default"):
            result = await set_default_location(10, MagicMock(), db)

        assert "is now the default" in result["message"]
        assert loc.is_default is True
        db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_set_default_requires_auth(self):
        """Unauthenticated requests should fail with 401."""
        from routes.scheduler.locations import set_default_location

        with patch("routes.scheduler.locations.get_current_user",
                   new_callable=AsyncMock,
                   side_effect=HTTPException(status_code=401, detail="Not authenticated")):
            with pytest.raises(HTTPException) as exc_info:
                await set_default_location(10, MagicMock(), MagicMock())
            assert exc_info.value.status_code == 401
