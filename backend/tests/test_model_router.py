import pytest
from agents.orchestration.model_router import ModelRouter


def test_haiku_tier_uses_haiku_model(monkeypatch):
    monkeypatch.delenv("ARIA_HAIKU_MODEL", raising=False)
    r = ModelRouter()
    client = r.get("haiku")
    assert "haiku" in client.model.lower()


def test_sonnet_tier_uses_sonnet_model(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_MODEL", raising=False)
    r = ModelRouter()
    client = r.get("sonnet")
    assert "sonnet" in client.model.lower()


def test_env_overrides_model_id(monkeypatch):
    monkeypatch.setenv("ARIA_HAIKU_MODEL", "claude-haiku-4-5-20251001")
    r = ModelRouter()
    assert r.get("haiku").model == "claude-haiku-4-5-20251001"


def test_clients_are_cached(monkeypatch):
    r = ModelRouter()
    assert r.get("haiku") is r.get("haiku")


def test_unknown_tier_raises():
    r = ModelRouter()
    with pytest.raises(ValueError):
        r.get("turbo")
