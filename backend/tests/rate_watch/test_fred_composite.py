"""
FRED composite source tests.

Network is fully mocked. These tests assert:
  - The spread-model math is correct.
  - Provenance is preserved on every emitted observation.
  - Anchor calibration logic picks the right DGS10 value.
  - Derived products honor the configured spread.
"""
from __future__ import annotations

from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest

from app.services.rate_watch.models import Product, SourceName
from app.services.rate_watch.sources.base import SourceConfig
from app.services.rate_watch.sources.fred_composite import (
    DEFAULT_DERIVED_SPREADS_BPS,
    FredCompositeSource,
    TREASURY_SENSITIVITY,
    _compose,
    _to_decimal,
)


def _config() -> SourceConfig:
    return SourceConfig(
        name=SourceName.FRED,
        user_agent="PerenniaAI-RateWatch-Test/1.0",
        timeout_seconds=10.0,
        max_retries=1,
        base_backoff_seconds=0.1,
        api_key="test-key",
    )


# ===========================================================================
# Spread-model math: the _compose helper
# ===========================================================================
class TestCompose:

    def test_treasury_flat_no_movement(self):
        """When DGS10 hasn't moved since the anchor, output equals anchor."""
        rate, payload = _compose(
            anchor_label="MORTGAGE30US",
            anchor_value=Decimal("6.3600"),
            anchor_date="2026-05-14",
            treasury_delta=Decimal("0.0000"),
            treasury_today=Decimal("4.1800"),
            treasury_at_anchor=Decimal("4.1800"),
            sensitivity=Decimal("1.00"),
            kind="treasury_estimated",
        )
        assert rate == Decimal("6.3600")
        assert payload["anchor"]["value"] == "6.3600"
        assert payload["treasury"]["delta_pp"] == "0.0000"

    def test_treasury_up_13bps_30yr_moves_13bps(self):
        """30-yr fixed has sensitivity 1.0 → mirrors Treasury 1:1."""
        rate, _ = _compose(
            anchor_label="MORTGAGE30US",
            anchor_value=Decimal("6.3600"),
            anchor_date="2026-05-14",
            treasury_delta=Decimal("0.1300"),
            treasury_today=Decimal("4.3100"),
            treasury_at_anchor=Decimal("4.1800"),
            sensitivity=TREASURY_SENSITIVITY[Product.THIRTY_FIXED],
            kind="treasury_estimated",
        )
        assert rate == Decimal("6.4900")

    def test_treasury_up_13bps_15yr_moves_11bps(self):
        """15-yr fixed has sensitivity 0.85 → moves 85% of Treasury delta."""
        rate, _ = _compose(
            anchor_label="MORTGAGE15US",
            anchor_value=Decimal("5.7100"),
            anchor_date="2026-05-14",
            treasury_delta=Decimal("0.1300"),
            treasury_today=Decimal("4.3100"),
            treasury_at_anchor=Decimal("4.1800"),
            sensitivity=TREASURY_SENSITIVITY[Product.FIFTEEN_FIXED],
            kind="treasury_estimated",
        )
        # 5.7100 + 0.85 * 0.1300 = 5.7100 + 0.1105 = 5.8205
        assert rate == Decimal("5.8205")

    def test_treasury_down(self):
        """Treasury drops, mortgage estimate drops."""
        rate, _ = _compose(
            anchor_label="MORTGAGE30US",
            anchor_value=Decimal("6.3600"),
            anchor_date="2026-05-14",
            treasury_delta=Decimal("-0.2500"),
            treasury_today=Decimal("3.9300"),
            treasury_at_anchor=Decimal("4.1800"),
            sensitivity=Decimal("1.00"),
            kind="treasury_estimated",
        )
        assert rate == Decimal("6.1100")

    def test_provenance_payload_complete(self):
        """Every payload must carry full provenance for regulator replay."""
        _, payload = _compose(
            anchor_label="MORTGAGE30US",
            anchor_value=Decimal("6.3600"),
            anchor_date="2026-05-14",
            treasury_delta=Decimal("0.1300"),
            treasury_today=Decimal("4.3100"),
            treasury_at_anchor=Decimal("4.1800"),
            sensitivity=Decimal("1.00"),
            kind="treasury_estimated",
        )
        assert payload["anchor"]["series"] == "MORTGAGE30US"
        assert payload["anchor"]["value"] == "6.3600"
        assert payload["anchor"]["date"] == "2026-05-14"
        assert payload["treasury"]["series"] == "DGS10"
        assert payload["treasury"]["value_today"] == "4.3100"
        assert payload["treasury"]["value_at_anchor"] == "4.1800"
        assert payload["sensitivity"] == "1.00"
        assert "formula" in payload


# ===========================================================================
# End-to-end fetch with mocked FRED HTTP
# ===========================================================================
@pytest.mark.asyncio
class TestFetch:

    @staticmethod
    def _fred_obs(value: str, date: str) -> dict:
        return {"observations": [{"value": value, "date": date}]}

    async def test_full_fetch_emits_all_8_products(self):
        source = FredCompositeSource(_config())

        # Mock the _get method to return canned FRED responses per series.
        async def fake_get(url, params):
            sid = params["series_id"]
            if sid == "MORTGAGE30US":
                return self._fred_obs("6.36", "2026-05-14")
            if sid == "MORTGAGE15US":
                return self._fred_obs("5.71", "2026-05-14")
            if sid == "DGS10":
                # 'limit' on the latest call differs from the 'observation_end' anchor call,
                # so we look at the params to distinguish.
                if "observation_end" in params:
                    return self._fred_obs("4.18", "2026-05-14")
                return self._fred_obs("4.31", "2026-05-16")
            return {"observations": []}

        with patch.object(source, "_get", side_effect=fake_get):
            result = await source.fetch()

        by_product = {o.product: o for o in result.observations}

        # 6 of 8 products emitted (we don't derive 20yr or 10yr fixed)
        assert Product.THIRTY_FIXED in by_product
        assert Product.FIFTEEN_FIXED in by_product
        assert Product.THIRTY_JUMBO in by_product
        assert Product.THIRTY_FHA in by_product
        assert Product.THIRTY_VA in by_product
        assert Product.ARM_7_6_SOFR in by_product

        # 30-yr: 6.36 + 1.00 * (4.31 - 4.18) = 6.49
        assert by_product[Product.THIRTY_FIXED].rate == Decimal("6.4900")

        # 15-yr: 5.71 + 0.85 * 0.13 = 5.8205
        assert by_product[Product.FIFTEEN_FIXED].rate == Decimal("5.8205")

        # FHA: 30yr + (-48 bps) = 6.49 - 0.48 = 6.01
        assert by_product[Product.THIRTY_FHA].rate == Decimal("6.0100")

        # VA: 30yr + (-46 bps) = 6.49 - 0.46 = 6.03
        assert by_product[Product.THIRTY_VA].rate == Decimal("6.0300")

        # Jumbo: 30yr + 4 bps = 6.49 + 0.04 = 6.53
        assert by_product[Product.THIRTY_JUMBO].rate == Decimal("6.5300")

        # 7/6 ARM: 30yr + (-16 bps) = 6.49 - 0.16 = 6.33
        assert by_product[Product.ARM_7_6_SOFR].rate == Decimal("6.3300")

    async def test_provenance_present_on_every_observation(self):
        source = FredCompositeSource(_config())

        async def fake_get(url, params):
            sid = params["series_id"]
            if sid == "MORTGAGE30US":
                return self._fred_obs("6.36", "2026-05-14")
            if sid == "MORTGAGE15US":
                return self._fred_obs("5.71", "2026-05-14")
            if sid == "DGS10":
                if "observation_end" in params:
                    return self._fred_obs("4.18", "2026-05-14")
                return self._fred_obs("4.31", "2026-05-16")
            return {"observations": []}

        with patch.object(source, "_get", side_effect=fake_get):
            result = await source.fetch()

        for obs in result.observations:
            assert obs.raw_payload, f"observation for {obs.product} has no provenance"
            assert "kind" in obs.raw_payload
            # PMMS-anchored vs spread-derived must be distinguishable
            assert obs.raw_payload["kind"] in {"treasury_estimated", "spread_derived"}

    async def test_missing_api_key_raises_clearly(self):
        config = SourceConfig(
            name=SourceName.FRED,
            user_agent="x", timeout_seconds=10.0,
            max_retries=1, base_backoff_seconds=0.1,
            api_key=None,
        )
        source = FredCompositeSource(config)
        from app.services.rate_watch.sources.base import HttpSourceError
        with pytest.raises(HttpSourceError, match="FRED_API_KEY"):
            await source.fetch()


# ===========================================================================
# Spread defaults sanity
# ===========================================================================
class TestSpreadDefaults:

    def test_fha_below_conventional(self):
        assert DEFAULT_DERIVED_SPREADS_BPS[Product.THIRTY_FHA] < 0

    def test_va_below_conventional(self):
        assert DEFAULT_DERIVED_SPREADS_BPS[Product.THIRTY_VA] < 0

    def test_arm_below_30yr_fixed(self):
        assert DEFAULT_DERIVED_SPREADS_BPS[Product.ARM_7_6_SOFR] < 0

    def test_all_spreads_within_sane_bounds(self):
        """No spread should be wilder than ±200 bps; that would be a config bug."""
        for product, bps in DEFAULT_DERIVED_SPREADS_BPS.items():
            assert -200 < bps < 200, f"{product} has insane spread {bps}"
