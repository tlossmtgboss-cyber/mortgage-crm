"""
FredCompositeSource — the free-tier production primary.

Combines three public, free, properly-licensed signals into a daily
8-product rate observation:

  1. MORTGAGE30US (Freddie Mac PMMS, weekly Thursday)   — 30-yr fixed anchor
  2. MORTGAGE15US (Freddie Mac PMMS, weekly Thursday)   — 15-yr fixed anchor
  3. DGS10        (10-yr Treasury, daily business days) — daily movement signal

From these we produce:
  - 30_fixed   = PMMS anchor + (DGS10_today - DGS10_at_anchor)
  - 15_fixed   = PMMS_15_anchor + same Treasury delta * 0.85
                 (15-yr is less Treasury-sensitive than 30-yr empirically)
  - 30_jumbo   = 30_fixed + JUMBO_SPREAD_BPS    (configurable)
  - 30_fha     = 30_fixed + FHA_SPREAD_BPS      (typically negative)
  - 30_va      = 30_fixed + VA_SPREAD_BPS       (typically negative)
  - 7_6_sofr_arm = 30_fixed + ARM_SPREAD_BPS    (typically negative)

EVERY emitted observation records its full provenance in raw_payload:
  - which FRED series it came from
  - what the anchor PMMS rate and date were
  - what the Treasury delta was
  - what spread (if any) was applied
  - whether it's 'authoritative' (PMMS), 'treasury_estimated', or 'spread_derived'

That provenance is the contract that lets a regulator (or an LO, or QA)
replay the calculation from any historical row.

PRICING ENGINE DISCLAIMER (Security insisted this comment exists):
  The rates this source emits are SIGNALS for refi-opportunity detection,
  not quotes. The LO must use the licensed pricing engine (BytePro / their
  rate sheet) to quote an actual rate to a borrower. Aria's outreach
  message must not state the Perennia rate as a guaranteed quote — only
  as a "current market is favorable" signal.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import httpx

from ..models import Product, RawRateObservation, SourceFetchResult, SourceName
from .base import (
    HttpSourceError,
    ParseSourceError,
    RateSource,
    SourceTimeoutError,
)

logger = logging.getLogger(__name__)

FRED_API = "https://api.stlouisfed.org/fred/series/observations"

# Series IDs documented at https://fred.stlouisfed.org/
SERIES_PMMS_30YR = "MORTGAGE30US"   # weekly Thursday
SERIES_PMMS_15YR = "MORTGAGE15US"   # weekly Thursday
SERIES_DGS10 = "DGS10"              # daily business days


# ---------------------------------------------------------------------------
# Spread defaults
# ---------------------------------------------------------------------------
# These are starting values calibrated against typical 2025-2026 market data.
# LOs override these per-product/per-LO via the rate_margins admin UI as they
# see actual pricing-engine output for their region/product mix.
#
# All values in basis points. Negative means cheaper than 30-yr fixed.
DEFAULT_DERIVED_SPREADS_BPS: dict[Product, int] = {
    Product.THIRTY_JUMBO: 4,            # Slightly above conventional in 2026
    Product.THIRTY_FHA: -48,            # FHA typically below conventional
    Product.THIRTY_VA: -46,             # VA typically below conventional
    Product.ARM_7_6_SOFR: -16,          # ARM typically below 30-yr fixed
}

# How sensitive each PMMS product is to Treasury moves between PMMS refreshes.
# 1.0 = moves 1:1 with the 10-yr Treasury. Empirically the 30-yr fixed is
# very close to 1.0; the 15-yr fixed is closer to 0.85.
TREASURY_SENSITIVITY: dict[Product, Decimal] = {
    Product.THIRTY_FIXED: Decimal("1.00"),
    Product.FIFTEEN_FIXED: Decimal("0.85"),
}


class FredCompositeSource(RateSource):
    """
    Free-tier production source. Requires a FREE FRED API key.

    Set FRED_API_KEY in Railway secrets. Get one at
    https://fred.stlouisfed.org/docs/api/api_key.html (no card, no contract).
    """

    async def fetch(self) -> SourceFetchResult:
        if not self.config.api_key:
            raise HttpSourceError(
                "FRED_API_KEY not configured. Get a free key at "
                "https://fred.stlouisfed.org/docs/api/api_key.html"
            )

        started = datetime.now(timezone.utc)

        # ----- 1. Pull the three primary series -----
        pmms_30 = await self._latest_observation(SERIES_PMMS_30YR)
        pmms_15 = await self._latest_observation(SERIES_PMMS_15YR)
        dgs10_today = await self._latest_observation(SERIES_DGS10)

        # 10-yr Treasury value at the date of the most recent PMMS release
        dgs10_anchor = await self._observation_near(SERIES_DGS10, target_date=pmms_30["date"])

        finished = datetime.now(timezone.utc)
        duration_ms = int((finished - started).total_seconds() * 1000)

        # ----- 2. Compute the Treasury delta (today vs the PMMS anchor day) -----
        treasury_delta_pp = _to_decimal(dgs10_today["value"]) - _to_decimal(dgs10_anchor["value"])
        # treasury_delta_pp is in percentage points (e.g. Decimal("0.13") = 13 bps)

        observed_at = _date_to_utc_eod(dgs10_today["date"])

        observations: list[RawRateObservation] = []

        # ----- 3. 30-year fixed: PMMS anchor + sensitivity * Treasury delta -----
        thirty_rate, thirty_payload = _compose(
            anchor_label="MORTGAGE30US",
            anchor_value=_to_decimal(pmms_30["value"]),
            anchor_date=pmms_30["date"],
            treasury_delta=treasury_delta_pp,
            treasury_today=_to_decimal(dgs10_today["value"]),
            treasury_at_anchor=_to_decimal(dgs10_anchor["value"]),
            sensitivity=TREASURY_SENSITIVITY[Product.THIRTY_FIXED],
            kind="treasury_estimated",
        )
        observations.append(_obs(Product.THIRTY_FIXED, thirty_rate, observed_at, thirty_payload))

        # ----- 4. 15-year fixed: same pattern, lower Treasury sensitivity -----
        fifteen_rate, fifteen_payload = _compose(
            anchor_label="MORTGAGE15US",
            anchor_value=_to_decimal(pmms_15["value"]),
            anchor_date=pmms_15["date"],
            treasury_delta=treasury_delta_pp,
            treasury_today=_to_decimal(dgs10_today["value"]),
            treasury_at_anchor=_to_decimal(dgs10_anchor["value"]),
            sensitivity=TREASURY_SENSITIVITY[Product.FIFTEEN_FIXED],
            kind="treasury_estimated",
        )
        observations.append(_obs(Product.FIFTEEN_FIXED, fifteen_rate, observed_at, fifteen_payload))

        # ----- 5. Derived products from 30-year fixed + spread -----
        for product, spread_bps in DEFAULT_DERIVED_SPREADS_BPS.items():
            derived_rate = (thirty_rate + Decimal(spread_bps) / Decimal("100")).quantize(Decimal("0.0001"))
            payload = {
                "kind": "spread_derived",
                "derivation": {
                    "base_product": Product.THIRTY_FIXED.value,
                    "base_rate": str(thirty_rate),
                    "spread_bps": spread_bps,
                    "spread_source": "default_constant",
                    "note": (
                        "This product's rate is derived from the 30-yr fixed using a "
                        "configurable industry-standard spread. It is an approximation "
                        "intended for refi-trigger detection only. The LO's pricing "
                        "engine quotes the actual rate to the borrower."
                    ),
                },
                "based_on": thirty_payload,
            }
            observations.append(_obs(product, derived_rate, observed_at, payload))

        return SourceFetchResult(
            source=SourceName.FRED,
            fetched_at=finished,
            fetch_duration_ms=duration_ms,
            observations=observations,
            missing_products=[
                Product.TWENTY_FIXED,
                Product.TEN_FIXED,
            ],
        )

    # ------------------------------------------------------------------ #
    # FRED API plumbing                                                  #
    # ------------------------------------------------------------------ #
    async def _latest_observation(self, series_id: str) -> dict:
        """Return the most recent non-missing observation for a series."""
        params = {
            "series_id": series_id,
            "file_type": "json",
            "sort_order": "desc",
            "limit": 10,            # last 10; some days have '.' (missing)
        }
        data = await self._get(FRED_API, params)
        for obs in data.get("observations", []):
            if obs.get("value") not in (".", "", None):
                return obs
        raise ParseSourceError(f"no valid observations returned for {series_id}")

    async def _observation_near(self, series_id: str, target_date: str) -> dict:
        """
        Return the DGS10 observation on `target_date` if it exists, otherwise
        the most recent observation on or before that date. (PMMS publishes
        Thursday; Treasury also publishes Thursday; usually exact match.)
        """
        target = datetime.fromisoformat(target_date).date()
        start = (target - timedelta(days=7)).isoformat()
        end = target.isoformat()
        params = {
            "series_id": series_id,
            "file_type": "json",
            "observation_start": start,
            "observation_end": end,
            "sort_order": "desc",
            "limit": 10,
        }
        data = await self._get(FRED_API, params)
        for obs in data.get("observations", []):
            if obs.get("value") not in (".", "", None):
                return obs
        raise ParseSourceError(
            f"no valid {series_id} observation within 7 days of {target_date}"
        )

    async def _get(self, url: str, params: dict) -> dict:
        headers = {"Authorization": f"Bearer {self.config.api_key}"}
        try:
            async with self._client() as client:
                resp = await client.get(url, params=params, headers=headers)
        except httpx.TimeoutException as exc:
            raise SourceTimeoutError(str(exc)) from exc
        except httpx.HTTPError as exc:
            raise HttpSourceError(str(exc)) from exc

        if resp.status_code != 200:
            raise HttpSourceError(f"FRED returned HTTP {resp.status_code}: {resp.text[:200]}")
        try:
            return resp.json()
        except ValueError as exc:
            raise ParseSourceError(f"non-JSON response: {exc}") from exc


# ---------------------------------------------------------------------------
# Helpers — kept at module level so they're easy to unit-test
# ---------------------------------------------------------------------------
def _to_decimal(s: str | float | Decimal) -> Decimal:
    return Decimal(str(s)).quantize(Decimal("0.0001"))


def _date_to_utc_eod(date_str: str) -> datetime:
    """Parse a YYYY-MM-DD string and return that day at 16:00 UTC."""
    d = datetime.fromisoformat(date_str)
    return d.replace(hour=16, minute=0, second=0, microsecond=0, tzinfo=timezone.utc)


def _obs(product: Product, rate: Decimal, observed_at: datetime, payload: dict) -> RawRateObservation:
    return RawRateObservation(
        source=SourceName.FRED,
        product=product,
        rate=rate,
        points=Decimal("0.000"),
        change_pct=None,
        observed_at=observed_at,
        raw_payload=payload,
    )


def _compose(
    *,
    anchor_label: str,
    anchor_value: Decimal,
    anchor_date: str,
    treasury_delta: Decimal,
    treasury_today: Decimal,
    treasury_at_anchor: Decimal,
    sensitivity: Decimal,
    kind: str,
) -> tuple[Decimal, dict]:
    """
    Apply the spread model: anchor + sensitivity * treasury_delta.
    Returns (final_rate, provenance_payload).
    """
    adjusted = (anchor_value + sensitivity * treasury_delta).quantize(Decimal("0.0001"))
    payload = {
        "kind": kind,
        "anchor": {
            "series": anchor_label,
            "value": str(anchor_value),
            "date": anchor_date,
        },
        "treasury": {
            "series": "DGS10",
            "value_today": str(treasury_today),
            "value_at_anchor": str(treasury_at_anchor),
            "delta_pp": str(treasury_delta),
        },
        "sensitivity": str(sensitivity),
        "formula": "anchor + sensitivity * (DGS10_today - DGS10_at_anchor)",
        "computed_rate": str(adjusted),
    }
    return adjusted, payload
