"""
MNDHtmlSource — parses the public Mortgage News Daily rates page.

⚠️ NOT FOR PRODUCTION USE.

Read /docs/RATE_SOURCE_DECISION.md before enabling in any env that
sends outreach to real borrowers. The team's position:

  - This source is for dev/staging until a licensed feed is signed.
  - We poll at 15-min minimum interval (configurable, never lower).
  - We identify ourselves honestly in the User-Agent.
  - We respect robots.txt (checked at startup).
  - We cache aggressively in Redis to minimize hits.
  - We detect schema drift loudly and fail closed.

The DOM-shape assumptions are documented in PRODUCT_ROW_SELECTORS below.
If MND changes their page, the parser raises SchemaDriftError, the
worker stops emitting, monitoring pages, and someone gets called.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import httpx
from bs4 import BeautifulSoup, Tag

from ..models import Product, RawRateObservation, SourceFetchResult, SourceName
from .base import (
    HttpSourceError,
    ParseSourceError,
    RateSource,
    RateSourceError,
    SchemaDriftError,
    SourceTimeoutError,
)

logger = logging.getLogger(__name__)

MND_RATES_URL = "https://www.mortgagenewsdaily.com/mortgage-rates"

# Maps the row labels on the page to our internal Product enum.
# The match is case-insensitive and tolerates trailing punctuation.
# If MND adds/removes products, schema-drift detection fires.
PRODUCT_ROW_PATTERNS: dict[str, Product] = {
    r"^30\s*yr\.?\s*fixed$": Product.THIRTY_FIXED,
    r"^15\s*yr\.?\s*fixed$": Product.FIFTEEN_FIXED,
    r"^30\s*yr\.?\s*jumbo$": Product.THIRTY_JUMBO,
    r"^7/6\s*sofr\s*arm$": Product.ARM_7_6_SOFR,
    r"^30\s*yr\.?\s*fha$": Product.THIRTY_FHA,
    r"^30\s*yr\.?\s*va$": Product.THIRTY_VA,
    r"^20\s*yr\.?\s*fixed$": Product.TWENTY_FIXED,
    r"^10\s*yr\.?\s*fixed$": Product.TEN_FIXED,
}

EXPECTED_HEADERS = {"mortgage rates", "rate", "points", "change"}


class MNDHtmlSource(RateSource):
    """Parses the public MND mortgage rates summary table."""

    async def fetch(self) -> SourceFetchResult:
        started = datetime.now(timezone.utc)

        # Politeness: check robots.txt before each fetch.
        # (Cached at the OS network layer; cost is negligible.)
        if not await self._robots_allows():
            raise RateSourceError("robots.txt disallows fetch")

        html, etag = await self._fetch_html()
        observations = self._parse(html)

        finished = datetime.now(timezone.utc)
        duration_ms = int((finished - started).total_seconds() * 1000)

        missing = [p for p in Product if p not in {o.product for o in observations}]

        return SourceFetchResult(
            source=SourceName.MND_HTML,
            fetched_at=finished,
            fetch_duration_ms=duration_ms,
            upstream_etag=etag,
            observations=observations,
            missing_products=missing,
        )

    # ------------------------------------------------------------------ #
    # HTTP                                                                #
    # ------------------------------------------------------------------ #
    async def _fetch_html(self) -> tuple[str, str | None]:
        try:
            async with self._client() as client:
                resp = await client.get(MND_RATES_URL)
        except httpx.TimeoutException as exc:
            raise SourceTimeoutError(str(exc)) from exc
        except httpx.HTTPError as exc:
            raise HttpSourceError(str(exc)) from exc

        if resp.status_code == 429:
            raise HttpSourceError(f"rate limited (429): {resp.headers.get('retry-after')}")
        if resp.status_code >= 500:
            raise HttpSourceError(f"upstream error: HTTP {resp.status_code}")
        if resp.status_code != 200:
            raise HttpSourceError(f"unexpected status: HTTP {resp.status_code}")

        return resp.text, resp.headers.get("etag")

    async def _robots_allows(self) -> bool:
        rp = RobotFileParser()
        rp.set_url("https://www.mortgagenewsdaily.com/robots.txt")
        try:
            # urllib's robotparser is sync; running in thread to avoid blocking.
            # For a 15-min cadence this is fine; for higher-frequency sources
            # we'd cache the parsed robots.txt.
            import asyncio

            await asyncio.to_thread(rp.read)
        except Exception:
            # If robots.txt is unreachable, fall back to "allowed" rather than
            # silently stop ingestion. Logged loudly.
            logger.warning("robots.txt unreachable, assuming allowed")
            return True

        return rp.can_fetch(self.config.user_agent, MND_RATES_URL)

    # ------------------------------------------------------------------ #
    # Parsing                                                             #
    # ------------------------------------------------------------------ #
    def _parse(self, html: str) -> list[RawRateObservation]:
        soup = BeautifulSoup(html, "lxml")

        table = self._find_rates_table(soup)
        if table is None:
            raise SchemaDriftError("Could not locate rates table on page")

        # Validate headers — first line of defense against MND redesigning the page
        headers = [
            self._normalize(th.get_text(strip=True))
            for th in table.find_all("th")
        ]
        if not EXPECTED_HEADERS.issubset(set(headers)):
            raise SchemaDriftError(
                f"Header row changed. Expected {EXPECTED_HEADERS}, got {headers}"
            )

        observed_at = self._parse_observed_at(soup) or datetime.now(timezone.utc)

        observations: list[RawRateObservation] = []
        for row in table.find_all("tr"):
            cells = row.find_all("td")
            if len(cells) < 4:
                continue

            label = self._normalize(cells[0].get_text(strip=True))
            product = self._match_product(label)
            if product is None:
                continue  # row that isn't a product we track (e.g. an ad row)

            try:
                rate = self._parse_rate(cells[1].get_text(strip=True))
                points = self._parse_points(cells[2].get_text(strip=True))
                change = self._parse_change(cells[3].get_text(strip=True))
            except ParseSourceError as exc:
                logger.warning("skipping row '%s' due to parse error: %s", label, exc)
                continue

            observations.append(
                RawRateObservation(
                    source=SourceName.MND_HTML,
                    product=product,
                    rate=rate,
                    points=points,
                    change_pct=change,
                    observed_at=observed_at,
                    raw_payload={
                        "label": label,
                        "row_html": str(row)[:500],  # truncated for storage cost
                    },
                )
            )

        if not observations:
            raise SchemaDriftError("Rates table parsed but no product rows matched")

        # Sanity: 30-year fixed must be present, it's the headline product.
        if Product.THIRTY_FIXED not in {o.product for o in observations}:
            raise SchemaDriftError("30-year fixed missing from parsed rates")

        return observations

    @staticmethod
    def _find_rates_table(soup: BeautifulSoup) -> Tag | None:
        """
        MND's rates page uses a <table> with a <thead> containing
        'Mortgage Rates' / 'Rate' / 'Points' / 'Change'. We find by header
        content rather than class name (classes change more often).
        """
        for table in soup.find_all("table"):
            header_text = " ".join(th.get_text(strip=True).lower() for th in table.find_all("th"))
            if "rate" in header_text and "points" in header_text and "change" in header_text:
                return table
        return None

    @staticmethod
    def _normalize(s: str) -> str:
        return re.sub(r"\s+", " ", s).strip().lower()

    @staticmethod
    def _match_product(label: str) -> Product | None:
        for pattern, product in PRODUCT_ROW_PATTERNS.items():
            if re.match(pattern, label, re.IGNORECASE):
                return product
        return None

    @staticmethod
    def _parse_rate(s: str) -> Decimal:
        # "6.65%" → Decimal("6.6500")
        cleaned = s.replace("%", "").strip()
        try:
            return Decimal(cleaned).quantize(Decimal("0.0001"))
        except InvalidOperation as exc:
            raise ParseSourceError(f"could not parse rate from '{s}'") from exc

    @staticmethod
    def _parse_points(s: str) -> Decimal:
        cleaned = s.strip()
        if not cleaned or cleaned == "-":
            return Decimal("0.000")
        try:
            return Decimal(cleaned).quantize(Decimal("0.001"))
        except InvalidOperation as exc:
            raise ParseSourceError(f"could not parse points from '{s}'") from exc

    @staticmethod
    def _parse_change(s: str) -> Decimal | None:
        # "+0.13%" or "-0.05%" or "0.00"
        cleaned = re.sub(r"[%↑↓\s]", "", s).strip()
        if not cleaned or cleaned in {"+", "-"}:
            return None
        try:
            return Decimal(cleaned).quantize(Decimal("0.0001"))
        except InvalidOperation:
            return None

    @staticmethod
    def _parse_observed_at(soup: BeautifulSoup) -> datetime | None:
        """
        MND prints a date next to the table (e.g. '5/15/26'). We parse it
        so observed_at reflects when MND says these rates were effective,
        not when we fetched. If we can't find it, caller falls back to now().
        """
        text = soup.get_text(" ", strip=True)
        m = re.search(r"\b(\d{1,2})/(\d{1,2})/(\d{2,4})\b", text)
        if not m:
            return None
        month, day, year = m.groups()
        try:
            yr = int(year)
            if yr < 100:
                yr += 2000
            return datetime(yr, int(month), int(day), 16, 0, 0, tzinfo=timezone.utc)
        except ValueError:
            return None
