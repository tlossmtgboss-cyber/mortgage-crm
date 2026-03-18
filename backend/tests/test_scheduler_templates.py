"""
Tests for scheduler appointment template routes.

Covers:
  - GET    /templates                 List org's appointment templates
  - POST   /templates                 Create template
  - PUT    /templates/{id}            Update template
  - DELETE /templates/{id}            Soft delete template
  - POST   /templates/{id}/duplicate  Clone template

Edge cases: auth required (401), not found (404), input validation (400),
max template cap, and default template management.
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


class MockTemplate:
    """Mock AppointmentTemplate ORM object."""
    def __init__(self, **kwargs):
        self.id = kwargs.get("id", 1)
        self.organization_id = kwargs.get("organization_id", 1)
        self.created_by = kwargs.get("created_by", 1)
        self.name = kwargs.get("name", "Discovery Call")
        self.description = kwargs.get("description", "Initial consultation")
        self.duration_minutes = kwargs.get("duration_minutes", 30)
        self.appointment_type = kwargs.get("appointment_type", "consultation")
        self.location_type = kwargs.get("location_type", "virtual")
        self.default_location = kwargs.get("default_location", "https://meet.example.com")
        self.buffer_before_minutes = kwargs.get("buffer_before_minutes", 5)
        self.buffer_after_minutes = kwargs.get("buffer_after_minutes", 10)
        self.intake_form_fields = kwargs.get("intake_form_fields", [])
        self.reminder_config = kwargs.get("reminder_config", {})
        self.is_active = kwargs.get("is_active", True)
        self.is_default = kwargs.get("is_default", False)
        self.sort_order = kwargs.get("sort_order", 0)
        self.deleted_at = kwargs.get("deleted_at", None)
        self.created_at = kwargs.get("created_at", datetime(2026, 1, 15, tzinfo=timezone.utc))
        self.updated_at = kwargs.get("updated_at", datetime(2026, 3, 1, tzinfo=timezone.utc))


def _mock_db_query_chain(results=None, single=None, count=0):
    """Create a mock DB query chain."""
    query_mock = MagicMock()
    query_mock.filter = MagicMock(return_value=query_mock)
    query_mock.order_by = MagicMock(return_value=query_mock)
    query_mock.all = MagicMock(return_value=results if results is not None else [])
    query_mock.first = MagicMock(return_value=single)
    query_mock.count = MagicMock(return_value=count)
    return query_mock


# ---------------------------------------------------------------------------
# Tests: Serialization Helper
# ---------------------------------------------------------------------------

class TestSerializeTemplate:
    """Tests for _serialize_template helper."""

    def test_serialize_all_fields(self):
        """Serialization should include all expected fields."""
        from routes.scheduler.templates import _serialize_template

        tmpl = MockTemplate()
        result = _serialize_template(tmpl)

        assert result["id"] == 1
        assert result["name"] == "Discovery Call"
        assert result["description"] == "Initial consultation"
        assert result["duration_minutes"] == 30
        assert result["location_type"] == "virtual"
        assert result["buffer_before_minutes"] == 5
        assert result["buffer_after_minutes"] == 10
        assert result["is_active"] is True
        assert result["is_default"] is False
        assert result["intake_form_fields"] == []
        assert result["reminder_config"] == {}
        assert result["created_at"] is not None

    def test_serialize_null_json_fields(self):
        """None intake_form_fields and reminder_config should serialize as [] and {}."""
        from routes.scheduler.templates import _serialize_template

        tmpl = MockTemplate(intake_form_fields=None, reminder_config=None)
        result = _serialize_template(tmpl)

        assert result["intake_form_fields"] == []
        assert result["reminder_config"] == {}


# ---------------------------------------------------------------------------
# Tests: GET /templates
# ---------------------------------------------------------------------------

class TestListTemplates:
    """Tests for GET /templates."""

    @pytest.mark.asyncio
    async def test_list_templates_requires_auth(self):
        """Unauthenticated requests should return 401."""
        from routes.scheduler.templates import list_appointment_templates

        with patch("routes.scheduler.templates.get_current_user",
                   new_callable=AsyncMock,
                   side_effect=HTTPException(status_code=401, detail="Not authenticated")):
            with pytest.raises(HTTPException) as exc_info:
                await list_appointment_templates(MagicMock(), False, MagicMock())
            assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_list_templates_happy_path(self):
        """Authenticated user gets their org's templates."""
        from routes.scheduler.templates import list_appointment_templates

        user = MockUser()
        t1 = MockTemplate(id=1, name="Discovery Call")
        t2 = MockTemplate(id=2, name="Follow-Up", duration_minutes=15)

        db = MagicMock()
        query_mock = _mock_db_query_chain(results=[t1, t2])
        db.query = MagicMock(return_value=query_mock)

        with patch("routes.scheduler.templates.get_current_user",
                   new_callable=AsyncMock, return_value=user):
            result = await list_appointment_templates(MagicMock(), False, db)

        assert result["total"] == 2
        assert len(result["templates"]) == 2
        assert result["templates"][0]["name"] == "Discovery Call"

    @pytest.mark.asyncio
    async def test_list_templates_empty(self):
        """No templates should return empty list."""
        from routes.scheduler.templates import list_appointment_templates

        user = MockUser()
        db = MagicMock()
        query_mock = _mock_db_query_chain(results=[])
        db.query = MagicMock(return_value=query_mock)

        with patch("routes.scheduler.templates.get_current_user",
                   new_callable=AsyncMock, return_value=user):
            result = await list_appointment_templates(MagicMock(), False, db)

        assert result["total"] == 0
        assert result["templates"] == []


# ---------------------------------------------------------------------------
# Tests: POST /templates
# ---------------------------------------------------------------------------

class TestCreateTemplate:
    """Tests for POST /templates."""

    @pytest.mark.asyncio
    async def test_create_template_requires_auth(self):
        """Unauthenticated requests should return 401."""
        from routes.scheduler.templates import create_appointment_template

        with patch("routes.scheduler.templates.get_current_user",
                   new_callable=AsyncMock,
                   side_effect=HTTPException(status_code=401, detail="Not authenticated")):
            with pytest.raises(HTTPException) as exc_info:
                await create_appointment_template(MagicMock(), MagicMock())
            assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_create_template_missing_name_returns_400(self):
        """Template with empty name should return 400."""
        from routes.scheduler.templates import create_appointment_template

        user = MockUser()

        request = MagicMock()
        request.json = AsyncMock(return_value={"name": "", "duration_minutes": 30})

        db = MagicMock()

        with patch("routes.scheduler.templates.get_current_user",
                   new_callable=AsyncMock, return_value=user):
            with pytest.raises(HTTPException) as exc_info:
                await create_appointment_template(request, db)
            assert exc_info.value.status_code == 400
            assert "name is required" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_create_template_invalid_duration_returns_400(self):
        """Duration outside 5-480 range should return 400."""
        from routes.scheduler.templates import create_appointment_template

        user = MockUser()

        request = MagicMock()
        request.json = AsyncMock(return_value={"name": "Test", "duration_minutes": 2})

        db = MagicMock()

        with patch("routes.scheduler.templates.get_current_user",
                   new_callable=AsyncMock, return_value=user):
            with pytest.raises(HTTPException) as exc_info:
                await create_appointment_template(request, db)
            assert exc_info.value.status_code == 400
            assert "duration_minutes" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_create_template_invalid_location_type_returns_400(self):
        """Invalid location_type should return 400."""
        from routes.scheduler.templates import create_appointment_template

        user = MockUser()

        request = MagicMock()
        request.json = AsyncMock(return_value={
            "name": "Test",
            "duration_minutes": 30,
            "location_type": "underwater",
        })

        db = MagicMock()

        with patch("routes.scheduler.templates.get_current_user",
                   new_callable=AsyncMock, return_value=user):
            with pytest.raises(HTTPException) as exc_info:
                await create_appointment_template(request, db)
            assert exc_info.value.status_code == 400
            assert "location_type" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_create_template_happy_path(self):
        """Valid template creation should succeed and return serialized template."""
        from routes.scheduler.templates import create_appointment_template

        user = MockUser()

        request = MagicMock()
        request.json = AsyncMock(return_value={
            "name": "Rate Lock Review",
            "duration_minutes": 30,
            "location_type": "virtual",
            "description": "Discuss rate lock options",
        })

        db = MagicMock()
        # count query for cap check
        count_query = MagicMock()
        count_query.filter = MagicMock(return_value=count_query)
        count_query.count = MagicMock(return_value=5)

        new_template = MockTemplate(
            id=10, name="Rate Lock Review", description="Discuss rate lock options",
            duration_minutes=30, location_type="virtual",
        )

        db.query = MagicMock(return_value=count_query)
        db.flush = MagicMock()

        with patch("routes.scheduler.templates.get_current_user",
                   new_callable=AsyncMock, return_value=user), \
             patch("routes.scheduler.templates._audit_log"), \
             patch("database.models.appointment_template.AppointmentTemplate",
                   return_value=new_template, create=True):
            result = await create_appointment_template(request, db)

        assert result["name"] == "Rate Lock Review"
        db.add.assert_called_once()
        db.commit.assert_called_once()


# ---------------------------------------------------------------------------
# Tests: PUT /templates/{template_id}
# ---------------------------------------------------------------------------

class TestUpdateTemplate:
    """Tests for PUT /templates/{id}."""

    @pytest.mark.asyncio
    async def test_update_template_not_found(self):
        """Updating a nonexistent template should return 404."""
        from routes.scheduler.templates import update_appointment_template

        user = MockUser()

        request = MagicMock()
        request.json = AsyncMock(return_value={"name": "Updated"})

        db = MagicMock()
        query_mock = _mock_db_query_chain(single=None)
        db.query = MagicMock(return_value=query_mock)

        with patch("routes.scheduler.templates.get_current_user",
                   new_callable=AsyncMock, return_value=user):
            with pytest.raises(HTTPException) as exc_info:
                await update_appointment_template(999, request, db)
            assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_update_template_empty_name_returns_400(self):
        """Update with empty name should return 400."""
        from routes.scheduler.templates import update_appointment_template

        user = MockUser()
        existing = MockTemplate(id=1)

        request = MagicMock()
        request.json = AsyncMock(return_value={"name": ""})

        db = MagicMock()
        query_mock = _mock_db_query_chain(single=existing)
        db.query = MagicMock(return_value=query_mock)

        with patch("routes.scheduler.templates.get_current_user",
                   new_callable=AsyncMock, return_value=user):
            with pytest.raises(HTTPException) as exc_info:
                await update_appointment_template(1, request, db)
            assert exc_info.value.status_code == 400
            assert "name cannot be empty" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_update_template_happy_path(self):
        """Valid update should apply changes and commit."""
        from routes.scheduler.templates import update_appointment_template

        user = MockUser()
        existing = MockTemplate(id=1, name="Old Name", duration_minutes=30)

        request = MagicMock()
        request.json = AsyncMock(return_value={
            "name": "New Name",
            "duration_minutes": 45,
        })

        db = MagicMock()
        query_mock = _mock_db_query_chain(single=existing)
        db.query = MagicMock(return_value=query_mock)

        with patch("routes.scheduler.templates.get_current_user",
                   new_callable=AsyncMock, return_value=user), \
             patch("routes.scheduler.templates._audit_log"):
            result = await update_appointment_template(1, request, db)

        assert existing.name == "New Name"
        assert existing.duration_minutes == 45
        db.commit.assert_called_once()


# ---------------------------------------------------------------------------
# Tests: DELETE /templates/{template_id}
# ---------------------------------------------------------------------------

class TestDeleteTemplate:
    """Tests for DELETE /templates/{id}."""

    @pytest.mark.asyncio
    async def test_delete_template_not_found(self):
        """Deleting a nonexistent template should return 404."""
        from routes.scheduler.templates import delete_appointment_template

        user = MockUser()

        db = MagicMock()
        query_mock = _mock_db_query_chain(single=None)
        db.query = MagicMock(return_value=query_mock)

        with patch("routes.scheduler.templates.get_current_user",
                   new_callable=AsyncMock, return_value=user):
            with pytest.raises(HTTPException) as exc_info:
                await delete_appointment_template(999, MagicMock(), db)
            assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_template_soft_deletes(self):
        """Deleting should set deleted_at and is_active=False."""
        from routes.scheduler.templates import delete_appointment_template

        user = MockUser()
        tmpl = MockTemplate(id=1, is_active=True, deleted_at=None)

        db = MagicMock()
        query_mock = _mock_db_query_chain(single=tmpl)
        db.query = MagicMock(return_value=query_mock)

        with patch("routes.scheduler.templates.get_current_user",
                   new_callable=AsyncMock, return_value=user), \
             patch("routes.scheduler.templates._audit_log"):
            result = await delete_appointment_template(1, MagicMock(), db)

        assert result["success"] is True
        assert result["deleted_id"] == 1
        assert tmpl.deleted_at is not None
        assert tmpl.is_active is False
        db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete_template_requires_auth(self):
        """Unauthenticated requests should return 401."""
        from routes.scheduler.templates import delete_appointment_template

        with patch("routes.scheduler.templates.get_current_user",
                   new_callable=AsyncMock,
                   side_effect=HTTPException(status_code=401, detail="Not authenticated")):
            with pytest.raises(HTTPException) as exc_info:
                await delete_appointment_template(1, MagicMock(), MagicMock())
            assert exc_info.value.status_code == 401


# ---------------------------------------------------------------------------
# Tests: POST /templates/{template_id}/duplicate
# ---------------------------------------------------------------------------

class TestDuplicateTemplate:
    """Tests for POST /templates/{id}/duplicate."""

    @pytest.mark.asyncio
    async def test_duplicate_template_not_found(self):
        """Duplicating a nonexistent template should return 404."""
        from routes.scheduler.templates import duplicate_appointment_template

        user = MockUser()

        db = MagicMock()
        query_mock = _mock_db_query_chain(single=None)
        db.query = MagicMock(return_value=query_mock)

        with patch("routes.scheduler.templates.get_current_user",
                   new_callable=AsyncMock, return_value=user):
            with pytest.raises(HTTPException) as exc_info:
                await duplicate_appointment_template(999, MagicMock(), db)
            assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_duplicate_template_happy_path(self):
        """Cloning should create a new template with 'Copy of' prefix."""
        from routes.scheduler.templates import duplicate_appointment_template

        user = MockUser()
        source = MockTemplate(
            id=1, name="Discovery Call", duration_minutes=30,
            location_type="virtual", description="Initial consultation",
            intake_form_fields=["name", "phone"],
            reminder_config={"email": True},
        )

        request = MagicMock()
        request.json = AsyncMock(side_effect=Exception("no body"))

        db = MagicMock()
        # First query: find source template
        source_query = _mock_db_query_chain(single=source)
        # Second query: count for cap check
        count_query = _mock_db_query_chain(count=5)

        db.query = MagicMock(side_effect=[source_query, count_query])
        db.flush = MagicMock()

        clone = MockTemplate(
            id=10, name="Copy of Discovery Call", duration_minutes=30,
            location_type="virtual", description="Initial consultation",
            is_default=False,
        )

        with patch("routes.scheduler.templates.get_current_user",
                   new_callable=AsyncMock, return_value=user), \
             patch("routes.scheduler.templates._audit_log"), \
             patch("database.models.appointment_template.AppointmentTemplate",
                   return_value=clone, create=True):
            result = await duplicate_appointment_template(1, request, db)

        assert result["name"] == "Copy of Discovery Call"
        assert result["is_default"] is False
        db.add.assert_called_once()
        db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_duplicate_with_custom_name(self):
        """Clone should use custom name from request body if provided."""
        from routes.scheduler.templates import duplicate_appointment_template

        user = MockUser()
        source = MockTemplate(id=1, name="Discovery Call")

        request = MagicMock()
        request.json = AsyncMock(return_value={"name": "My Custom Clone"})

        db = MagicMock()
        source_query = _mock_db_query_chain(single=source)
        count_query = _mock_db_query_chain(count=3)
        db.query = MagicMock(side_effect=[source_query, count_query])
        db.flush = MagicMock()

        clone = MockTemplate(id=11, name="My Custom Clone", is_default=False)

        with patch("routes.scheduler.templates.get_current_user",
                   new_callable=AsyncMock, return_value=user), \
             patch("routes.scheduler.templates._audit_log"), \
             patch("database.models.appointment_template.AppointmentTemplate",
                   return_value=clone, create=True):
            result = await duplicate_appointment_template(1, request, db)

        assert result["name"] == "My Custom Clone"
