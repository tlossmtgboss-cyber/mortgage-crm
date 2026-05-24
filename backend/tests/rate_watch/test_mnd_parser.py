"""
MND HTML parser tests — schema drift detection in particular.

These tests use synthetic HTML fixtures that mirror the structure of
the real page. The actual page is not hit in tests (per Data Engineer:
never let CI depend on a third-party HTML page being up).
"""
from __future__ import annotations

from decimal import Decimal

import pytest

from app.services.rate_watch.models import Product, SourceName
from app.services.rate_watch.sources.base import SchemaDriftError, SourceConfig
from app.services.rate_watch.sources.mnd_html import MNDHtmlSource


def _config() -> SourceConfig:
    return SourceConfig(
        name=SourceName.MND_HTML,
        user_agent="PerenniaAI-RateWatch-Test/1.0",
        timeout_seconds=10.0,
        max_retries=1,
        base_backoff_seconds=0.1,
    )


# Synthetic HTML matching the screenshot the user provided.
GOOD_HTML = """
<html><body>
<div class="rates-summary">
  <table>
    <thead>
      <tr>
        <th>Mortgage Rates</th><th>Rate</th><th>Points</th><th>Change</th>
      </tr>
    </thead>
    <tbody>
      <tr><td>30 Yr. Fixed</td><td>6.65%</td><td>0.00</td><td>+0.13%</td></tr>
      <tr><td>15 Yr. Fixed</td><td>6.10%</td><td>0.00</td><td>+0.06%</td></tr>
      <tr><td>30 Yr. Jumbo</td><td>6.69%</td><td>0.00</td><td>+0.04%</td></tr>
      <tr><td>7/6 SOFR ARM</td><td>6.49%</td><td>0.00</td><td>+0.20%</td></tr>
      <tr><td>30 Yr. FHA</td><td>6.17%</td><td>0.00</td><td>+0.18%</td></tr>
      <tr><td>30 Yr. VA</td><td>6.19%</td><td>0.00</td><td>+0.18%</td></tr>
    </tbody>
  </table>
  <div class="date">5/15/26</div>
</div>
</body></html>
"""


class TestParser:
    def test_parses_user_screenshot_exactly(self):
        source = MNDHtmlSource(_config())
        observations = source._parse(GOOD_HTML)

        by_product = {o.product: o for o in observations}
        assert by_product[Product.THIRTY_FIXED].rate == Decimal("6.6500")
        assert by_product[Product.FIFTEEN_FIXED].rate == Decimal("6.1000")
        assert by_product[Product.THIRTY_JUMBO].rate == Decimal("6.6900")
        assert by_product[Product.ARM_7_6_SOFR].rate == Decimal("6.4900")
        assert by_product[Product.THIRTY_FHA].rate == Decimal("6.1700")
        assert by_product[Product.THIRTY_VA].rate == Decimal("6.1900")

    def test_parses_change_pct(self):
        source = MNDHtmlSource(_config())
        observations = source._parse(GOOD_HTML)
        thirty = next(o for o in observations if o.product == Product.THIRTY_FIXED)
        assert thirty.change_pct == Decimal("0.1300")

    def test_observed_at_uses_date_on_page(self):
        source = MNDHtmlSource(_config())
        observations = source._parse(GOOD_HTML)
        # All observations from same page share the same observed_at.
        assert len({o.observed_at for o in observations}) == 1
        any_obs = observations[0]
        assert any_obs.observed_at.year == 2026
        assert any_obs.observed_at.month == 5

    def test_missing_rates_table_raises_schema_drift(self):
        source = MNDHtmlSource(_config())
        with pytest.raises(SchemaDriftError):
            source._parse("<html><body>no table here</body></html>")

    def test_unexpected_headers_raises_schema_drift(self):
        bad = """
        <html><body><table>
          <thead><tr><th>Loan Type</th><th>APR</th><th>Fees</th></tr></thead>
          <tbody><tr><td>30 Yr Fixed</td><td>6.65%</td><td>$500</td></tr></tbody>
        </table></body></html>
        """
        source = MNDHtmlSource(_config())
        with pytest.raises(SchemaDriftError, match="Could not locate"):
            # 'rate' / 'points' / 'change' are not all in headers, so table not found.
            source._parse(bad)

    def test_no_thirty_year_fixed_raises_schema_drift(self):
        """30-yr fixed is the headline product. If it's missing, something's wrong."""
        bad = """
        <html><body><table>
          <thead><tr><th>Mortgage Rates</th><th>Rate</th><th>Points</th><th>Change</th></tr></thead>
          <tbody>
            <tr><td>15 Yr. Fixed</td><td>6.10%</td><td>0.00</td><td>+0.06%</td></tr>
          </tbody>
        </table></body></html>
        """
        source = MNDHtmlSource(_config())
        with pytest.raises(SchemaDriftError, match="30-year fixed missing"):
            source._parse(bad)

    def test_extra_rows_ignored_not_drifted(self):
        """An ad row or sidebar shouldn't trip the parser."""
        with_extra = GOOD_HTML.replace(
            "</tbody>",
            "<tr><td colspan='4'>Sponsored: Mortgage broker ad</td></tr></tbody>",
        )
        source = MNDHtmlSource(_config())
        observations = source._parse(with_extra)
        assert len(observations) == 6  # the 6 rates, ad row dropped

    def test_label_variations_tolerated(self):
        """Whitespace and capitalization variation shouldn't break matching."""
        variant = GOOD_HTML.replace("30 Yr. Fixed", "30  YR FIXED")
        source = MNDHtmlSource(_config())
        observations = source._parse(variant)
        assert any(o.product == Product.THIRTY_FIXED for o in observations)
