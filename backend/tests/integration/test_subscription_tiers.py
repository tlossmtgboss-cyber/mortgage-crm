"""
Integration tests for subscription tier configuration & feature gating.

Covers:
  - feature_tiers.FEATURE_TIERS: CORE/PREMIUM/EXPERIMENTAL classification
  - feature_tiers.get_tier() default behavior
  - feature_tiers.get_modules_by_tier()
  - subscription_models.SUBSCRIPTION_TIERS pricing + feature flags
  - subscription_models.FEATURE_ADDONS pricing
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration

_BACKEND_DIR = Path(__file__).resolve().parents[2]


def _load(name: str, rel_path: str):
    target = _BACKEND_DIR / rel_path
    if not target.exists():
        pytest.skip(f"{rel_path} missing")
    spec = importlib.util.spec_from_file_location(name, str(target))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


_ft = _load("_pa_feature_tiers", "feature_tiers.py")


# ---------------------------------------------------------------------------
# Feature tier classification
# ---------------------------------------------------------------------------

def test_leads_module_is_core_tier():
    assert _ft.get_tier("leads") == _ft.FeatureTier.CORE


def test_voice_workflows_is_premium():
    assert _ft.get_tier("voice_workflows") == _ft.FeatureTier.PREMIUM


def test_unknown_module_defaults_core():
    assert _ft.get_tier("never-heard-of-it") == _ft.FeatureTier.CORE


def test_core_modules_include_essentials():
    core = _ft.get_modules_by_tier(_ft.FeatureTier.CORE)
    for module in ("leads", "loans", "auth", "telephony"):
        assert module in core, f"{module} should be CORE"


def test_premium_modules_set_nonempty():
    premium = _ft.get_modules_by_tier(_ft.FeatureTier.PREMIUM)
    assert len(premium) >= 1


def test_feature_tier_enum_has_three_values():
    assert set(_ft.FeatureTier) == {
        _ft.FeatureTier.CORE,
        _ft.FeatureTier.PREMIUM,
        _ft.FeatureTier.EXPERIMENTAL,
    }


# ---------------------------------------------------------------------------
# Subscription tiers (best-effort import — subscription_models depends on Base)
# ---------------------------------------------------------------------------

if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))


def _maybe_load_sub_tiers():
    try:
        from subscription_models import SUBSCRIPTION_TIERS, FEATURE_ADDONS  # type: ignore
        return SUBSCRIPTION_TIERS, FEATURE_ADDONS
    except Exception:
        return None, None


_TIERS, _ADDONS = _maybe_load_sub_tiers()


def test_subscription_full_pipeline_tier_exists():
    if _TIERS is None:
        pytest.skip("subscription_models not importable")
    assert "full_pipeline" in _TIERS
    tier = _TIERS["full_pipeline"]
    assert tier["price_monthly"] > 0
    assert tier["features"]["leads"] is True


def test_subscription_addon_extra_sms_priced():
    if _ADDONS is None:
        pytest.skip("subscription_models not importable")
    addon = _ADDONS.get("extra_sms")
    assert addon is not None
    assert addon["price"] > 0
    assert addon["unit"] == "sms"


def test_subscription_tier_features_flag_shape():
    if _TIERS is None:
        pytest.skip("subscription_models not importable")
    for key, tier in _TIERS.items():
        assert "features" in tier, f"{key} missing features"
        assert "price_monthly" in tier
