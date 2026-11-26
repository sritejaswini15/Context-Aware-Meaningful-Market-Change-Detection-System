"""Deterministic mock market. Two variants simulate two independent feeds:

* ``mock-primary``   - realtime, high reliability
* ``mock-reference`` - slightly lagged cross-check feed, lower reliability

Both read the active demo scenario through ``scenario_source``.
"""

from __future__ import annotations

import math
import random
import zlib
from collections.abc import Callable
from datetime import UTC, date, datetime, time, timedelta

from app.providers.market.base import (
    MarketDataProvider,
    ProviderBar,
    ProviderEvent,
    ProviderProfile,
    ProviderQuote,
    ProviderUnavailable,
    SymbolNotFound,
)
from app.providers.market.scenarios import (
    DEFAULT_SCENARIO,
    SCENARIO_EVENTS,
    SCENARIOS,
    STATIC_EVENTS,
    prev_close,
    world_move,
)
from app.providers.market.universe import UNIVERSE
from app.utils.market_hours import session_fraction

ScenarioSource = Callable[[], tuple[str, datetime]]


def _default_source() -> tuple[str, datetime]:
    return DEFAULT_SCENARIO, datetime(2026, 1, 1, tzinfo=UTC)


class MockProvider(MarketDataProvider):
    def __init__(self, variant: str = "primary", scenario_source: ScenarioSource | None = None, clock: Callable[[], datetime] | None = None):
        self.variant = variant
        self.name = "mock-primary" if variant == "primary" else "mock-reference"
        self.reliability = 0.95 if variant == "primary" else 0.80
        self.is_realtime = True
        self._scenario_source = scenario_source or _default_source
        self._clock = clock or (lambda: datetime.now(UTC))

    # ------------------------------------------------------------------
    def _scenario(self):
        key, activated_at = self._scenario_source()
        return SCENARIOS.get(key, SCENARIOS[DEFAULT_SCENARIO]), activated_at

    def get_quote(self, symbol: str) -> ProviderQuote:
        inst = UNIVERSE.get(symbol.upper())
        if inst is None:
            raise SymbolNotFound(symbol)
        scenario, _ = self._scenario()
        faults = scenario.faults
        if "PRIMARY_DOWN" in faults and self.variant == "primary":
            raise ProviderUnavailable("Simulated outage of the primary market feed")

        now = self._clock().replace(microsecond=0)
        move, vmult = world_move(inst.symbol, scenario.world)
        price = inst.price * (1 + move / 100)
        ts = now
        realtime = True
        if self.variant == "reference":
            # Independent feed: tiny rounding differences, slight lag.
            price *= 1 + 0.0002 * ((zlib.crc32(("ref" + inst.symbol).encode()) % 3) - 1)
            ts = now - timedelta(seconds=25)
            if "CONFLICT" in faults and inst.symbol == "NVDA":
                price = 178.40
                ts = now - timedelta(minutes=3)
            if "PRIMARY_DOWN" in faults:
                ts = now - timedelta(minutes=16)
                realtime = False
        if "STALE" in faults:
            ts = now - timedelta(minutes=95)

        pc = prev_close(inst)
        price = round(price, 2)
        open_ = round(pc * 1.001, 2)
        volume = int(inst.avg_volume * session_fraction(ts) * vmult)
        return ProviderQuote(
            symbol=inst.symbol,
            provider=self.name,
            price=price,
            prev_close=pc,
            open=open_,
            high=round(max(price, open_, pc) * 1.002, 2),
            low=round(min(price, open_, pc) * 0.998, 2),
            volume=volume,
            market_timestamp=ts,
            is_realtime=realtime,
        )

    def get_historical_prices(self, symbol: str, days: int = 90) -> list[ProviderBar]:
        inst = UNIVERSE.get(symbol.upper())
        if inst is None:
            raise SymbolNotFound(symbol)
        rng = random.Random(zlib.crc32(("hist" + inst.symbol).encode()))
        today = self._clock().date()
        dates: list[date] = []
        d = today - timedelta(days=1)
        while len(dates) < days:
            if d.weekday() < 5:
                dates.append(d)
            d -= timedelta(days=1)
        dates.reverse()
        sigma = inst.daily_vol_pct / 100
        closes = [prev_close(inst)]
        for _ in range(len(dates) - 1):
            r = rng.gauss(0.0004, sigma)
            closes.append(closes[-1] / (1 + r))
        closes.reverse()
        bars = []
        for dt, close in zip(dates, closes, strict=True):
            spread = abs(rng.gauss(0, sigma / 2))
            open_ = close * (1 + rng.gauss(0, sigma / 3))
            vol = int(inst.avg_volume * math.exp(rng.gauss(-0.03, 0.25)))
            bars.append(
                ProviderBar(
                    date=dt,
                    open=round(open_, 2),
                    high=round(max(open_, close) * (1 + spread), 2),
                    low=round(min(open_, close) * (1 - spread), 2),
                    close=round(close, 2),
                    volume=vol,
                )
            )
        # Normalise so the 20-day average equals the instrument's reference volume:
        # scenario volume multipliers then map 1:1 onto the volume ratio users see.
        recent = [b.volume for b in bars[-20:] if b.volume]
        if recent:
            factor = inst.avg_volume / (sum(recent) / len(recent))
            for b in bars:
                b.volume = int(b.volume * factor) if b.volume else b.volume
        return bars

    def get_events(self, symbol: str, since: datetime) -> list[ProviderEvent]:
        symbol = symbol.upper()
        if symbol not in UNIVERSE:
            raise SymbolNotFound(symbol)
        scenario, activated_at = self._scenario()
        events: list[ProviderEvent] = []
        today = self._clock().date()
        for ev in STATIC_EVENTS:
            if ev["symbol"] != symbol:
                continue
            when = datetime.combine(today - timedelta(days=ev["days_ago"]), time(13, 0), tzinfo=UTC)
            events.append(
                ProviderEvent(
                    symbol=symbol,
                    external_id=f"static:{symbol}:{ev['headline']}:{when.date()}",
                    event_type=ev["event_type"],
                    headline=ev["headline"],
                    source="Knoww demo feed (simulated)",
                    event_time=when,
                    significance=ev["significance"],
                )
            )
        for ev in SCENARIO_EVENTS.get(scenario.key, []):
            if ev["symbol"] != symbol:
                continue
            events.append(
                ProviderEvent(
                    symbol=symbol,
                    external_id=f"scenario:{scenario.key}:{symbol}:{activated_at.isoformat()}",
                    event_type=ev["event_type"],
                    headline=ev["headline"],
                    source="Knoww demo feed (simulated)",
                    event_time=activated_at,
                    significance=ev["significance"],
                )
            )
        return [e for e in events if e.event_time >= since]

    def get_profile(self, symbol: str) -> ProviderProfile:
        inst = UNIVERSE.get(symbol.upper())
        if inst is None:
            raise SymbolNotFound(symbol)
        return ProviderProfile(
            symbol=inst.symbol,
            name=inst.name,
            exchange=inst.exchange,
            sector=inst.sector,
            industry=None,
            sector_benchmark=inst.benchmark,
            kind=inst.kind,
        )

    def search(self, query: str) -> list[ProviderProfile]:
        q = query.strip().lower()
        if not q:
            return []
        hits = [i for i in UNIVERSE.values() if i.kind == "EQUITY" and (q in i.symbol.lower() or q in i.name.lower())]
        hits.sort(key=lambda i: (not i.symbol.lower().startswith(q), i.symbol))
        return [self.get_profile(i.symbol) for i in hits[:10]]
