"""
RateSource — abstract base for any upstream rate provider.

The whole Rate Watch system depends on this contract and nothing else
about the upstream. To add a new provider:

  1. Subclass RateSource.
  2. Implement fetch() — return SourceFetchResult.
  3. Register the class name in `config.SOURCE_REGISTRY`.
  4. Set RATE_WATCH_PRIMARY_SOURCE=<name> in Railway env.

That's it. Ingestion worker, calculator, evaluator, dashboard,
match engine — none of them change.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

import httpx

from ..models import SourceFetchResult, SourceName


class RateSourceError(Exception):
    """Base class for source-level errors. Subclasses map to ErrorKind."""


class HttpSourceError(RateSourceError):
    """Upstream returned non-2xx or network failed."""


class ParseSourceError(RateSourceError):
    """Response received but couldn't be parsed."""


class SchemaDriftError(RateSourceError):
    """Response parsed but the shape changed — page DOM changed, API field added/removed."""


class RateLimitedError(RateSourceError):
    """Upstream told us to slow down (429 or RateLimit-Remaining=0)."""


class SourceTimeoutError(RateSourceError):
    """Request didn't complete in the configured budget."""


@dataclass(frozen=True)
class SourceConfig:
    """Per-source config knobs. Loaded from env + secrets manager."""

    name: SourceName
    user_agent: str
    timeout_seconds: float
    max_retries: int
    base_backoff_seconds: float
    api_key: str | None = None
    endpoint: str | None = None


class RateSource(ABC):
    """
    Implementations:
      - MNDHtmlSource          (contingent, dev/staging only)
      - OptimalBlueSource      (production primary; stub today)
      - FredSource             (sanity / cross-check / fallback)

    Contract:
      - fetch() must NEVER swallow errors. Raise the right RateSourceError subclass.
      - fetch() must NEVER block longer than self.config.timeout_seconds.
      - fetch() must populate raw_payload on each observation for forensics.
      - fetch() must be idempotent — calling it twice in a row must not have side effects.
    """

    def __init__(self, config: SourceConfig):
        self.config = config

    @property
    def name(self) -> SourceName:
        return self.config.name

    @abstractmethod
    async def fetch(self) -> SourceFetchResult:
        """Pull the latest rates. Raises RateSourceError on failure."""
        ...

    def _client(self) -> httpx.AsyncClient:
        """Standard httpx client with our UA and timeout."""
        return httpx.AsyncClient(
            headers={"User-Agent": self.config.user_agent},
            timeout=httpx.Timeout(self.config.timeout_seconds, connect=5.0),
            follow_redirects=True,
        )
