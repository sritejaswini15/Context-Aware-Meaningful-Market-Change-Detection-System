"""Builds the configured provider chain. The only place vendors are named."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from functools import lru_cache

from app.core.cache import get_cache
from app.core.config import get_settings
from app.providers.market.base import (
    MarketDataProvider,
    ProviderBar,
    ProviderError,
    ProviderEvent,
    ProviderProfile,
    ProviderQuote,
)


class CachingProvider(MarketDataProvider):
    """Short-lived quote cache in front of network providers (rate-limit friendly)."""

    def __init__(self, inner: MarketDataProvider, ttl: int):
        self.inner = inner
        self.name = inner.name
        self.reliability = inner.reliability
        self.is_realtime = inner.is_realtime
        self.ttl = ttl

    def get_quote(self, symbol: str) -> ProviderQuote:
        cache = get_cache()
        key = f"quote:{self.name}:{symbol}"
        hit = cache.get_json(key)
        if hit:
            return ProviderQuote.model_validate(hit)
        quote = self.inner.get_quote(symbol)
        cache.set_json(key, quote.model_dump(mode="json"), self.ttl)
        return quote

    def get_quotes(self, symbols: Sequence[str]) -> dict[str, ProviderQuote | ProviderError]:
        return MarketDataProvider.get_quotes(self, symbols)

    def get_historical_prices(self, symbol: str, days: int = 90) -> list[ProviderBar]:
        return self.inner.get_historical_prices(symbol, days)

    def get_events(self, symbol: str, since: datetime) -> list[ProviderEvent]:
        return self.inner.get_events(symbol, since)

    def get_profile(self, symbol: str) -> ProviderProfile:
        return self.inner.get_profile(symbol)

    def search(self, query: str) -> list[ProviderProfile]:
        return self.inner.search(query)


@lru_cache
def get_market_providers() -> tuple[MarketDataProvider, ...]:
    from app.providers.market.mock import MockProvider
    from app.services.demo.state import current_scenario

    settings = get_settings()
    providers: list[MarketDataProvider] = []
    for name in settings.market_provider_list:
        if name == "mock":
            providers.append(MockProvider("primary", scenario_source=current_scenario))
        elif name == "mock-reference":
            providers.append(MockProvider("reference", scenario_source=current_scenario))
        elif name == "finnhub":
            from app.providers.market.finnhub import FinnhubProvider

            if settings.finnhub_api_key:
                providers.append(
                    CachingProvider(
                        FinnhubProvider(settings.finnhub_api_key, timeout=settings.provider_timeout_seconds),
                        settings.quote_cache_ttl_seconds,
                    )
                )
        else:
            raise ValueError(f"Unknown market provider '{name}'")
    if not providers:  # never leave the product without a data path
        providers.append(MockProvider("primary", scenario_source=current_scenario))
    return tuple(providers)


def primary_provider() -> MarketDataProvider:
    return get_market_providers()[0]
