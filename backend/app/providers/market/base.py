"""Market data provider contract.

Nothing outside `app/providers/market` knows which vendor supplies data.
Providers return plain, validated Pydantic objects; missing values stay
`None` (never invented).
"""

from __future__ import annotations

import abc
import time
from collections.abc import Callable, Sequence
from datetime import date, datetime
from typing import TypeVar

from pydantic import BaseModel, Field


class ProviderError(Exception):
    """Base provider failure."""

    transient = True


class ProviderUnavailable(ProviderError):
    pass


class ProviderRateLimited(ProviderError):
    pass


class SymbolNotFound(ProviderError):
    transient = False


class CapabilityUnavailable(ProviderError):
    """The provider (or the current plan) cannot supply this data."""

    transient = False


class ProviderQuote(BaseModel):
    symbol: str
    provider: str
    price: float = Field(gt=0)
    prev_close: float | None = Field(default=None, gt=0)
    open: float | None = None
    high: float | None = None
    low: float | None = None
    volume: int | None = Field(default=None, ge=0)
    currency: str = "USD"
    market_timestamp: datetime
    is_realtime: bool = True


class ProviderBar(BaseModel):
    date: date
    open: float | None = None
    high: float | None = None
    low: float | None = None
    close: float = Field(gt=0)
    volume: int | None = None


class ProviderEvent(BaseModel):
    symbol: str
    external_id: str
    event_type: str
    headline: str
    summary: str | None = None
    source: str | None = None
    url: str | None = None
    event_time: datetime
    significance: float = Field(ge=0, le=1)


class ProviderProfile(BaseModel):
    symbol: str
    name: str
    exchange: str | None = None
    currency: str = "USD"
    market: str = "US"
    sector: str | None = None
    industry: str | None = None
    sector_benchmark: str | None = None
    kind: str = "EQUITY"


class VolumeInfo(BaseModel):
    current: int | None
    average_daily: float | None


class MarketDataProvider(abc.ABC):
    name: str
    reliability: float = 0.9
    is_realtime: bool = True

    @abc.abstractmethod
    def get_quote(self, symbol: str) -> ProviderQuote: ...

    def get_quotes(self, symbols: Sequence[str]) -> dict[str, ProviderQuote | ProviderError]:
        out: dict[str, ProviderQuote | ProviderError] = {}
        for s in symbols:
            try:
                out[s] = self.get_quote(s)
            except SymbolNotFound as exc:
                out[s] = exc
        return out

    @abc.abstractmethod
    def get_historical_prices(self, symbol: str, days: int = 90) -> list[ProviderBar]: ...

    def get_volume(self, symbol: str) -> VolumeInfo:
        quote = self.get_quote(symbol)
        try:
            bars = self.get_historical_prices(symbol, 30)
        except CapabilityUnavailable:
            bars = []
        vols = [b.volume for b in bars[-20:] if b.volume]
        return VolumeInfo(current=quote.volume, average_daily=(sum(vols) / len(vols)) if vols else None)

    @abc.abstractmethod
    def get_events(self, symbol: str, since: datetime) -> list[ProviderEvent]: ...

    @abc.abstractmethod
    def get_profile(self, symbol: str) -> ProviderProfile: ...

    def get_sector(self, symbol: str) -> str | None:
        return self.get_profile(symbol).sector

    def search(self, query: str) -> list[ProviderProfile]:
        return []


T = TypeVar("T")


def with_retry(fn: Callable[[], T], retries: int = 2, base_delay: float = 0.25) -> T:
    """Retry transient provider errors with exponential backoff."""
    attempt = 0
    while True:
        try:
            return fn()
        except ProviderError as exc:
            if not exc.transient or attempt >= retries:
                raise
            time.sleep(base_delay * (2**attempt))
            attempt += 1
