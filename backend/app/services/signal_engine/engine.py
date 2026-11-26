"""Meaningful Change Engine - deterministic, transparent, configurable.

score = price movement + relative performance + volume anomaly
        + event significance + watchlist priority          (0-100)

Every factor reports the points it awarded and why, so the score can be
audited line by line. See docs/MEANINGFUL_CHANGE_ENGINE.md.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from typing import Literal

ENGINE_VERSION = "1.0"

Attention = Literal["LOW", "MEDIUM", "HIGH"]


# --------------------------------------------------------------------------- config
@dataclass(frozen=True)
class EngineConfig:
    weights: dict[str, float] = field(
        default_factory=lambda: {
            "price_movement": 30,
            "relative_performance": 30,
            "volume_anomaly": 20,
            "event_significance": 15,
            "watchlist_priority": 5,
        }
    )
    # Price movement, in units of the stock's own daily volatility (sigma).
    price_sigma_floor: float = 0.25
    price_sigma_full: float = 2.0
    # ... or raw % when no volatility history exists.
    price_pct_floor: float = 0.4
    price_pct_full: float = 4.0
    # Relative performance: excess move vs sector (full weight) / market (half weight).
    relative_floor: float = 0.5
    relative_full: float = 4.0
    market_relative_weight: float = 0.5
    # How much of the price factor is removed when the market explains the move.
    market_dampening: float = 0.65
    # Volume ratio ramp.
    volume_floor: float = 1.1
    volume_full: float = 3.0
    # Volume can't carry a signal on its own.
    volume_gate_price_ratio: float = 0.15
    # HIGH attention needs real price evidence, not just volume/events.
    high_requires_price_points: float = 25
    thresholds: dict[str, tuple[int, int]] = field(
        default_factory=lambda: {"LOW": (75, 50), "BALANCED": (65, 40), "HIGH": (55, 30)}
    )  # sensitivity -> (HIGH >=, MEDIUM >=)


DEFAULT_CONFIG = EngineConfig()


# --------------------------------------------------------------------------- io
@dataclass
class EventFact:
    event_type: str
    headline: str
    significance: float
    event_time: str


@dataclass
class SignalInputs:
    symbol: str
    name: str
    change_pct: float  # since the user's checkpoint
    day_change_pct: float | None
    window_trading_days: float
    sector_name: str | None
    sector_change_pct: float | None  # same window as change_pct
    market_change_pct: float | None  # same window as change_pct
    volume_ratio: float | None
    daily_volatility_pct: float | None
    events: list[EventFact] = field(default_factory=list)
    priority: str = "NORMAL"
    data_status: str = "FRESH"  # LIVE | FRESH | DELAYED | STALE | CONFLICTED
    is_conflicted: bool = False
    conflict_spread_pct: float | None = None
    sources_count: int = 1


@dataclass
class Preferences:
    sensitivity: str = "BALANCED"
    include_volume: bool = True
    include_market_context: bool = True
    include_events: bool = True

    def fingerprint(self) -> str:
        return hashlib.sha1(json.dumps(asdict(self), sort_keys=True).encode()).hexdigest()[:10]


@dataclass
class Factor:
    key: str
    label: str
    points: float
    max_points: float
    detail: str
    enabled: bool = True


@dataclass
class SignalResult:
    score: int
    attention: Attention
    movement_type: str
    confidence: float
    confidence_level: str
    factors: list[Factor]
    headline: str
    context_label: str
    caveats: list[str]
    is_meaningful: bool
    relative_to_sector: float | None
    relative_to_market: float | None

    def factors_json(self) -> list[dict]:
        return [asdict(f) for f in self.factors]


# --------------------------------------------------------------------------- helpers
def ramp(x: float, lo: float, hi: float) -> float:
    if hi <= lo:
        return 1.0 if x >= hi else 0.0
    return max(0.0, min(1.0, (x - lo) / (hi - lo)))


def _fmt_pct(v: float | None) -> str:
    return "n/a" if v is None else f"{v:+.1f}%"


def _same_sign(a: float, b: float) -> bool:
    return (a > 0 and b > 0) or (a < 0 and b < 0)


def classify_movement(inp: SignalInputs) -> str:
    chg = inp.change_pct
    sigma = inp.daily_volatility_pct
    noise = max(0.5, 0.35 * sigma) if sigma else 0.6
    if abs(chg) < noise:
        return "QUIET"
    tol = max(0.75, 0.25 * abs(chg))
    mkt, sec = inp.market_change_pct, inp.sector_change_pct
    if mkt is not None and _same_sign(chg, mkt) and abs(chg - mkt) <= tol:
        return "MARKET_WIDE"
    if sec is not None and _same_sign(chg, sec) and abs(chg - sec) <= tol and (mkt is None or abs(sec - mkt) > 0.75):
        return "SECTOR_WIDE"
    return "STOCK_SPECIFIC"


# --------------------------------------------------------------------------- engine
def evaluate(inp: SignalInputs, prefs: Preferences | None = None, config: EngineConfig = DEFAULT_CONFIG) -> SignalResult:
    prefs = prefs or Preferences()
    w = dict(config.weights)
    enabled = {
        "price_movement": True,
        "relative_performance": prefs.include_market_context,
        "volume_anomaly": prefs.include_volume,
        "event_significance": prefs.include_events,
        "watchlist_priority": True,
    }
    # Disabled factors give their weight to the others so the score stays 0-100.
    total_enabled = sum(w[k] for k, on in enabled.items() if on)
    scale = 100 / total_enabled if total_enabled else 1.0
    maxes = {k: (w[k] * scale if enabled[k] else 0.0) for k in w}

    chg = inp.change_pct
    abs_chg = abs(chg)
    sigma = inp.daily_volatility_pct
    caveats: list[str] = []

    # 1. Price movement -----------------------------------------------------
    if sigma and sigma > 0:
        window_sigma = sigma * max(1.0, inp.window_trading_days) ** 0.5
        magnitude = abs_chg / window_sigma
        price_ratio = ramp(magnitude, config.price_sigma_floor, config.price_sigma_full)
        price_detail = f"{_fmt_pct(chg)} is {magnitude:.1f}x this stock's typical move ({window_sigma:.1f}%)"
    else:
        price_ratio = ramp(abs_chg, config.price_pct_floor, config.price_pct_full)
        price_detail = f"{_fmt_pct(chg)} since you last checked (no volatility history to compare)"
        caveats.append("No price history, so the move cannot be compared with this stock's typical volatility.")

    explained = 0.0
    mkt = inp.market_change_pct
    if prefs.include_market_context and mkt is not None and abs_chg > 0 and _same_sign(chg, mkt):
        explained = min(1.0, abs(mkt) / abs_chg)
    dampen = 1 - config.market_dampening * explained
    price_points = maxes["price_movement"] * price_ratio * dampen
    if explained >= 0.5:
        price_detail += f"; the market moved {_fmt_pct(mkt)}, which explains much of it"

    # 2. Relative performance ----------------------------------------------
    rel_sector = round(chg - inp.sector_change_pct, 3) if inp.sector_change_pct is not None else None
    rel_market = round(chg - mkt, 3) if mkt is not None else None
    rel_points = 0.0
    rel_detail = "Market context disabled in your preferences"
    if prefs.include_market_context:
        parts = []
        sector_score = ramp(abs(rel_sector), config.relative_floor, config.relative_full) if rel_sector is not None else 0.0
        market_score = (
            config.market_relative_weight * ramp(abs(rel_market), config.relative_floor, config.relative_full) if rel_market is not None else 0.0
        )
        rel_points = maxes["relative_performance"] * max(sector_score, market_score)
        if rel_sector is not None:
            parts.append(f"{rel_sector:+.1f} pts vs {inp.sector_name or 'sector'} ({_fmt_pct(inp.sector_change_pct)})")
        if rel_market is not None:
            parts.append(f"{rel_market:+.1f} pts vs market ({_fmt_pct(mkt)})")
        rel_detail = "; ".join(parts) if parts else "Sector and market context unavailable"
        if rel_sector is None:
            caveats.append("Sector context unavailable.")
        if rel_market is None:
            caveats.append("Market context unavailable.")

    # 3. Volume anomaly -----------------------------------------------------
    vol_points = 0.0
    if not prefs.include_volume:
        vol_detail = "Volume disabled in your preferences"
    elif inp.volume_ratio is None:
        vol_detail = "Volume unavailable"
        caveats.append("Volume unavailable from the data provider.")
    else:
        vol_ratio = ramp(inp.volume_ratio, config.volume_floor, config.volume_full)
        vol_points = maxes["volume_anomaly"] * vol_ratio
        gated = price_ratio < config.volume_gate_price_ratio and vol_points > 0
        if gated:
            vol_points *= 0.5
        label = (
            "very unusual" if inp.volume_ratio >= 3 else "unusual" if inp.volume_ratio >= 2.5
            else "elevated" if inp.volume_ratio >= 1.5 else "normal"
        )
        vol_detail = f"{inp.volume_ratio:.1f}x normal volume ({label})" + ("; halved because the price barely moved" if gated else "")

    # 4. Event significance -------------------------------------------------
    ev_points = 0.0
    top_event = None
    if prefs.include_events and inp.events:
        top_event = max(inp.events, key=lambda e: e.significance)
        ev_points = maxes["event_significance"] * top_event.significance
        ev_detail = f"{top_event.event_type.title()}: {top_event.headline}"
    elif not prefs.include_events:
        ev_detail = "Company events disabled in your preferences"
    else:
        ev_detail = "No company event in the data for this window"

    # 5. Watchlist priority -------------------------------------------------
    pr_points = maxes["watchlist_priority"] if inp.priority == "HIGH" else 0.0
    pr_detail = "Marked high priority in your watchlist" if inp.priority == "HIGH" else "Normal priority"

    factors = [
        Factor("price_movement", "Price movement", round(price_points, 1), round(maxes["price_movement"], 1), price_detail),
        Factor("relative_performance", "Relative performance", round(rel_points, 1), round(maxes["relative_performance"], 1), rel_detail, enabled["relative_performance"]),
        Factor("volume_anomaly", "Volume anomaly", round(vol_points, 1), round(maxes["volume_anomaly"], 1), vol_detail, enabled["volume_anomaly"]),
        Factor("event_significance", "Event significance", round(ev_points, 1), round(maxes["event_significance"], 1), ev_detail, enabled["event_significance"]),
        Factor("watchlist_priority", "Watchlist priority", round(pr_points, 1), round(maxes["watchlist_priority"], 1), pr_detail),
    ]
    score = int(round(min(100.0, sum(f.points for f in factors))))

    # Attention ---------------------------------------------------------------
    high_t, med_t = config.thresholds.get(prefs.sensitivity, config.thresholds["BALANCED"])
    attention: Attention = "HIGH" if score >= high_t else "MEDIUM" if score >= med_t else "LOW"
    if attention == "HIGH" and price_points + rel_points < config.high_requires_price_points:
        attention = "MEDIUM"
        caveats.append("Capped at MEDIUM: the price evidence alone is not strong enough for HIGH.")

    # Confidence --------------------------------------------------------------
    confidence = 1.0
    if inp.data_status == "STALE":
        confidence -= 0.45
        caveats.append("Price data is stale. This may not be the current market state.")
    elif inp.data_status == "DELAYED":
        confidence -= 0.15
    if inp.is_conflicted:
        confidence -= 0.35
        caveats.append(f"Data providers disagree on the price (spread {inp.conflict_spread_pct or 0:.1f}%).")
    if inp.volume_ratio is None:
        confidence -= 0.08
    if inp.sector_change_pct is None:
        confidence -= 0.08
    if inp.market_change_pct is None:
        confidence -= 0.08
    if not sigma:
        confidence -= 0.08
    if inp.sources_count >= 2 and not inp.is_conflicted:
        confidence += 0.05
    confidence = round(max(0.05, min(1.0, confidence)), 2)
    confidence_level = "HIGH" if confidence >= 0.75 else "MEDIUM" if confidence >= 0.5 else "LOW"
    if attention == "HIGH" and (inp.data_status == "STALE" or inp.is_conflicted):
        attention = "MEDIUM"
        caveats.append("Capped at MEDIUM until the data is fresh and consistent.")

    movement = classify_movement(inp)
    headline, context_label = _headline(inp, movement)
    return SignalResult(
        score=score,
        attention=attention,
        movement_type=movement,
        confidence=confidence,
        confidence_level=confidence_level,
        factors=factors,
        headline=headline,
        context_label=context_label,
        caveats=caveats,
        is_meaningful=attention in ("HIGH", "MEDIUM"),
        relative_to_sector=rel_sector,
        relative_to_market=rel_market,
    )


def _headline(inp: SignalInputs, movement: str) -> tuple[str, str]:
    name = inp.name
    chg = inp.change_pct
    up = chg > 0
    verb_rel = "outperforming" if up else "underperforming"
    sector_phrase = f"the {inp.sector_name} sector" if inp.sector_name else "its sector"
    vol = inp.volume_ratio
    vol_clause = f", with unusually high trading volume ({vol:.1f}x normal)" if vol and vol >= 2 else (
        " with elevated activity" if vol and vol >= 1.5 else ""
    )
    if movement == "QUIET":
        return "Movement is minor and broadly consistent with the market.", "Minor movement"
    if movement == "MARKET_WIDE":
        return (
            f"{name} moved {_fmt_pct(chg)}, broadly in line with the market ({_fmt_pct(inp.market_change_pct)}). "
            "This is mostly broad market movement.",
            "Broad market movement",
        )
    if movement == "SECTOR_WIDE":
        return (
            f"{name} moved {_fmt_pct(chg)} along with {sector_phrase} ({_fmt_pct(inp.sector_change_pct)}), "
            f"while the market moved {_fmt_pct(inp.market_change_pct)}.",
            f"{inp.sector_name or 'Sector'} sector movement",
        )
    sig = "significantly " if abs(chg) >= 3 else ""
    return (
        f"{name} is {sig}{verb_rel} {sector_phrase} and the broader market{vol_clause}.",
        "Stock-specific",
    )
