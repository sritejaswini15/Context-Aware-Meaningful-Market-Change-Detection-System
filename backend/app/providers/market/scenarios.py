"""Deterministic demo scenarios for the mock market.

A scenario = a *world* (how prices and volumes moved relative to the normal
reference state) + optional *faults* (stale feed, conflicting providers,
provider outage, AI outage). Every number is deterministic so the demo
behaves identically on every run.
"""

from __future__ import annotations

import zlib
from dataclasses import dataclass, field

from app.providers.market.universe import MARKET_BENCHMARK, SECTORS, UNIVERSE, Instrument


@dataclass(frozen=True)
class World:
    market: float
    sectors: dict[str, float] = field(default_factory=dict)
    overrides: dict[str, tuple[float, float]] = field(default_factory=dict)  # symbol -> (move %, volume x)
    volume_mult: float = 1.0
    idio: float = 0.25  # +/- idiosyncratic noise (%) for non-overridden equities


WORLDS: dict[str, World] = {
    "NORMAL": World(market=0.0, idio=0.0),
    "DROP": World(
        market=-0.3,
        sectors={"XLK": -0.7, "XLC": -0.3, "XLY": -0.2, "XLF": -0.2, "XLE": -0.4, "XLV": -0.1, "XLI": -0.3},
        overrides={"NVDA": (-4.8, 2.8)},
    ),
    "SURGE": World(
        market=0.2,
        sectors={"XLK": 0.4, "XLY": 0.3, "XLC": 0.3},
        overrides={"AAPL": (2.9, 1.9), "TSLA": (6.2, 2.4)},
    ),
    "BROAD_DROP": World(
        market=-3.9,
        sectors={
            "XLK": -4.2, "XLC": -4.0, "XLY": -4.4, "XLF": -3.8, "XLV": -2.6, "XLE": -3.1,
            "XLP": -1.9, "XLI": -3.7, "XLU": -1.6, "XLRE": -3.0, "XLB": -3.4,
        },
        overrides={"NVDA": (-4.8, 1.6), "AAPL": (-4.0, 1.5), "MSFT": (-4.3, 1.5), "TSLA": (-4.9, 1.6)},
        volume_mult=1.5,
        idio=0.4,
    ),
    "SECTOR": World(
        market=-0.2,
        sectors={"XLE": -3.6},
        overrides={"XOM": (-3.9, 1.7), "CVX": (-3.4, 1.6), "COP": (-4.1, 1.9)},
    ),
    "VOLUME": World(market=0.1, sectors={"XLK": 0.2}, overrides={"MSFT": (1.1, 3.4)}),
    "EVENT": World(market=0.3, sectors={"XLY": 0.4}, overrides={"AMZN": (5.6, 3.1)}),
}


@dataclass(frozen=True)
class Scenario:
    key: str
    title: str
    description: str
    expectation: str
    world: str
    faults: frozenset[str] = frozenset()


SCENARIOS: dict[str, Scenario] = {
    s.key: s
    for s in [
        Scenario("NORMAL_MOVEMENT", "Normal movement", "Ordinary, small moves across the market.",
                 "Nothing needs your attention: Knoww stays quiet.", "NORMAL"),
        Scenario("STOCK_SPECIFIC_DROP", "Stock-specific drop", "NVDA falls 4.8% on 2.8x volume while Technology is -0.7% and the market -0.3%.",
                 "NVDA is raised to HIGH attention; its peers stay quiet.", "DROP"),
        Scenario("STOCK_SPECIFIC_SURGE", "Stock-specific surge", "AAPL +2.9% and TSLA +6.2% while their sectors barely move.",
                 "TSLA rises to HIGH and AAPL to MEDIUM attention.", "SURGE"),
        Scenario("BROAD_MARKET_DROP", "Broad market decline", "The market falls 3.9%. NVDA is down 4.8%, close to Technology's -4.2%.",
                 "Large moves, but mostly market-driven: priorities are lowered.", "BROAD_DROP"),
        Scenario("SECTOR_MOVEMENT", "Sector decline", "Energy falls 3.6% while the market is flat.",
                 "Energy names get MEDIUM attention, labelled as sector-wide movement.", "SECTOR"),
        Scenario("VOLUME_SPIKE", "Volume spike", "MSFT trades 3.4x its normal volume with only a +1.1% move.",
                 "Volume alone is not enough to get HIGH attention. Raise sensitivity to see it reach MEDIUM.", "VOLUME"),
        Scenario("EVENT_DRIVEN", "Event-driven move", "AMZN +5.6% on 3.1x volume after an earnings release.",
                 "AMZN gets HIGH attention, with the earnings event as a factor.", "EVENT"),
        Scenario("STALE_DATA", "Stale data", "Feeds return prices that are 95 minutes old.",
                 "Prices are marked STALE, confidence drops and attention is capped.", "DROP", frozenset({"STALE"})),
        Scenario("CONFLICTING_DATA", "Conflicting providers", "Primary reports NVDA at $171.55; the reference feed says $178.40.",
                 "NVDA is marked CONFLICTED with reduced confidence. The conflict is stored and shown.", "DROP", frozenset({"CONFLICT"})),
        Scenario("PROVIDER_FAILURE", "Provider failure", "The primary market feed is down; a delayed fallback feed is used.",
                 "System health degrades, data is marked DELAYED, and the app keeps working.", "DROP", frozenset({"PRIMARY_DOWN"})),
        Scenario("AI_FAILURE", "AI failure", "The AI provider is unavailable.",
                 "Explanations fall back to deterministic text built from the same facts.", "DROP", frozenset({"AI_DOWN"})),
    ]
}
DEFAULT_SCENARIO = "NORMAL_MOVEMENT"


def _unit(seed: str) -> float:
    """Deterministic value in [-1, 1]."""
    return (zlib.crc32(seed.encode()) % 20001) / 10000 - 1


def normal_day_move(inst: Instrument) -> float:
    """Today's move in the normal reference state (defines prev_close)."""
    if inst.symbol == "NVDA":
        return 0.727  # prev close 178.90 -> 180.20, so "today" differs from "since you checked"
    if inst.symbol == MARKET_BENCHMARK:
        return 0.2
    return round(0.15 + 0.6 * _unit("day:" + inst.symbol), 3)


def prev_close(inst: Instrument) -> float:
    return round(inst.price / (1 + normal_day_move(inst) / 100), 2)


def world_move(symbol: str, world_key: str) -> tuple[float, float]:
    """(% move vs normal reference price, volume multiplier) for a symbol."""
    world = WORLDS[world_key]
    inst = UNIVERSE[symbol]
    if symbol in world.overrides:
        return world.overrides[symbol]
    vol_noise = 0.0 if world_key == "NORMAL" else 0.08 * _unit(f"v:{world_key}:{symbol}")
    vmult = round(world.volume_mult * (1 + vol_noise), 3)
    if symbol == MARKET_BENCHMARK:
        return world.market, vmult
    if inst.kind == "SECTOR_ETF":
        return world.sectors.get(symbol, world.market), vmult
    base = world.sectors.get(inst.benchmark or "", world.market)
    return round(base + world.idio * _unit(f"i:{world_key}:{symbol}"), 3), vmult


SCENARIO_EVENTS: dict[str, list[dict]] = {
    "EVENT_DRIVEN": [
        {"symbol": "AMZN", "event_type": "EARNINGS", "headline": "Amazon.com releases quarterly earnings results", "significance": 1.0},
    ],
    "SECTOR_MOVEMENT": [
        {"symbol": "XOM", "event_type": "NEWS", "headline": "Crude oil prices fall after a supply update", "significance": 0.4},
    ],
}

STATIC_EVENTS: list[dict] = [
    {"symbol": "NVDA", "event_type": "NEWS", "headline": "NVIDIA to present at an upcoming technology conference", "days_ago": 3, "significance": 0.3},
    {"symbol": "AAPL", "event_type": "NEWS", "headline": "Apple announces the date of its next product event", "days_ago": 2, "significance": 0.35},
    {"symbol": "MSFT", "event_type": "DIVIDEND", "headline": "Microsoft declares quarterly dividend", "days_ago": 5, "significance": 0.3},
    {"symbol": "AMZN", "event_type": "NEWS", "headline": "Amazon.com schedules its quarterly results announcement", "days_ago": 1, "significance": 0.4},
    {"symbol": "TSLA", "event_type": "NEWS", "headline": "Tesla publishes quarterly production and delivery figures", "days_ago": 4, "significance": 0.5},
    {"symbol": "JPM", "event_type": "NEWS", "headline": "JPMorgan Chase schedules its quarterly earnings call", "days_ago": 6, "significance": 0.3},
]

assert set(SECTORS) <= set(UNIVERSE)
