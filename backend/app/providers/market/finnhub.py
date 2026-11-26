"""Finnhub adapter (https://finnhub.io/docs/api).

Free-plan notes, handled explicitly instead of inventing values:
* `/quote` has no volume -> volume is `None` ("Volume unavailable").
* `/stock/candle` requires a paid plan -> history raises CapabilityUnavailable.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import httpx

from app.providers.market.base import (
    CapabilityUnavailable,
    MarketDataProvider,
    ProviderBar,
    ProviderError,
    ProviderEvent,
    ProviderProfile,
    ProviderQuote,
    ProviderRateLimited,
    ProviderUnavailable,
    SymbolNotFound,
)
from app.providers.market.universe import MARKET_BENCHMARK, SECTORS, UNIVERSE, sector_for_industry

BASE_URL = "https://finnhub.io/api/v1"


class FinnhubProvider(MarketDataProvider):
    name = "finnhub"
    reliability = 0.9
    is_realtime = True

    def __init__(self, api_key: str, timeout: float = 6.0, client: httpx.Client | None = None):
        if not api_key:
            raise ValueError("FINNHUB_API_KEY is required for the Finnhub provider")
        self._client = client or httpx.Client(base_url=BASE_URL, timeout=timeout, headers={"X-Finnhub-Token": api_key})

    def _get(self, path: str, **params):
        try:
            resp = self._client.get(path, params=params)
        except httpx.TimeoutException as exc:
            raise ProviderUnavailable(f"Finnhub timeout on {path}") from exc
        except httpx.HTTPError as exc:
            raise ProviderUnavailable(f"Finnhub network error: {type(exc).__name__}") from exc
        if resp.status_code == 429:
            raise ProviderRateLimited("Finnhub rate limit reached")
        if resp.status_code in (401, 403):
            raise CapabilityUnavailable(f"Finnhub denied {path} (plan or key)")
        if resp.status_code >= 500:
            raise ProviderUnavailable(f"Finnhub {resp.status_code}")
        if resp.status_code >= 400:
            raise ProviderError(f"Finnhub {resp.status_code} on {path}")
        return resp.json()

    def get_quote(self, symbol: str) -> ProviderQuote:
        data = self._get("/quote", symbol=symbol.upper())
        price, ts = data.get("c"), data.get("t")
        if not price or not ts:
            raise SymbolNotFound(symbol)
        return ProviderQuote(
            symbol=symbol.upper(),
            provider=self.name,
            price=float(price),
            prev_close=float(data["pc"]) if data.get("pc") else None,
            open=float(data["o"]) if data.get("o") else None,
            high=float(data["h"]) if data.get("h") else None,
            low=float(data["l"]) if data.get("l") else None,
            volume=None,
            market_timestamp=datetime.fromtimestamp(int(ts), UTC),
            is_realtime=True,
        )

    def get_historical_prices(self, symbol: str, days: int = 90) -> list[ProviderBar]:
        now = datetime.now(UTC)
        data = self._get(
            "/stock/candle",
            symbol=symbol.upper(),
            resolution="D",
            **{"from": int((now - timedelta(days=int(days * 1.5))).timestamp()), "to": int(now.timestamp())},
        )
        if data.get("s") != "ok":
            return []
        bars = []
        for t, o, h, low, c, v in zip(data["t"], data["o"], data["h"], data["l"], data["c"], data.get("v", []), strict=False):
            bars.append(ProviderBar(date=datetime.fromtimestamp(t, UTC).date(), open=o, high=h, low=low, close=c, volume=int(v) if v else None))
        return bars[-days:]

    def get_events(self, symbol: str, since: datetime) -> list[ProviderEvent]:
        sym = symbol.upper()
        start: date = since.date()
        end: date = datetime.now(UTC).date() + timedelta(days=1)
        events: list[ProviderEvent] = []
        try:
            cal = self._get("/calendar/earnings", symbol=sym, **{"from": start.isoformat(), "to": end.isoformat()})
            for row in cal.get("earningsCalendar", []) or []:
                hour = {"bmo": 12, "amc": 21}.get(row.get("hour") or "", 13)
                when = datetime.fromisoformat(row["date"]).replace(hour=hour, tzinfo=UTC)
                events.append(
                    ProviderEvent(
                        symbol=sym,
                        external_id=f"earn:{sym}:{row['date']}",
                        event_type="EARNINGS",
                        headline=f"{sym} quarterly earnings ({row.get('quarter') and 'Q' + str(row['quarter']) or 'scheduled'})",
                        source="Finnhub earnings calendar",
                        event_time=when,
                        significance=1.0,
                    )
                )
        except CapabilityUnavailable:
            pass
        news = self._get("/company-news", symbol=sym, **{"from": start.isoformat(), "to": end.isoformat()})
        for item in (news or [])[:15]:
            if not item.get("headline") or not item.get("datetime"):
                continue
            events.append(
                ProviderEvent(
                    symbol=sym,
                    external_id=f"news:{item.get('id') or item['url']}",
                    event_type="NEWS",
                    headline=item["headline"][:400],
                    summary=(item.get("summary") or None),
                    source=item.get("source"),
                    url=item.get("url"),
                    event_time=datetime.fromtimestamp(int(item["datetime"]), UTC),
                    significance=0.35,
                )
            )
        return [e for e in events if e.event_time >= since]

    def get_profile(self, symbol: str) -> ProviderProfile:
        sym = symbol.upper()
        known = UNIVERSE.get(sym)
        if known and known.kind != "EQUITY":
            return ProviderProfile(symbol=sym, name=known.name, exchange=known.exchange, sector=known.sector, kind=known.kind)
        data = self._get("/stock/profile2", symbol=sym)
        if not data or not data.get("name"):
            raise SymbolNotFound(sym)
        sector, etf = sector_for_industry(data.get("finnhubIndustry"))
        if known:  # prefer curated mapping where we have one
            sector, etf = known.sector, known.benchmark
        return ProviderProfile(
            symbol=sym,
            name=data["name"],
            exchange=data.get("exchange"),
            currency=data.get("currency") or "USD",
            market=data.get("country") or "US",
            sector=sector,
            industry=data.get("finnhubIndustry"),
            sector_benchmark=etf,
        )

    def search(self, query: str) -> list[ProviderProfile]:
        data = self._get("/search", q=query, exchange="US")
        out = []
        for row in data.get("result", [])[:15]:
            sym = row.get("symbol", "")
            if row.get("type") not in ("Common Stock", "ADR", "ETP") or "." in sym or sym in (MARKET_BENCHMARK, *SECTORS):
                continue
            out.append(ProviderProfile(symbol=sym, name=row.get("description") or sym))
        return out[:10]
