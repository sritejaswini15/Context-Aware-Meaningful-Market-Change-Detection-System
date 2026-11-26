"""Data quality: validation, freshness classification and conflict resolution."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from app.providers.market.base import ProviderQuote
from app.utils.market_hours import last_close, session_state

LIVE_WITHIN = timedelta(seconds=90)
DELAYED_AFTER = timedelta(minutes=5)
STALE_AFTER = timedelta(minutes=30)


class InvalidObservation(ValueError):
    pass


def validate_quote(q: ProviderQuote, now: datetime) -> ProviderQuote:
    if not math.isfinite(q.price) or q.price <= 0:
        raise InvalidObservation("non-positive or non-finite price")
    if q.market_timestamp > now + timedelta(minutes=2):
        raise InvalidObservation("timestamp in the future")
    if q.market_timestamp < now - timedelta(days=10):
        raise InvalidObservation("observation older than 10 days")
    if q.prev_close and abs(q.price / q.prev_close - 1) > 0.8:
        raise InvalidObservation("implausible move vs previous close")
    if q.volume is not None and q.volume < 0:
        raise InvalidObservation("negative volume")
    return q


@dataclass
class Freshness:
    status: str  # LIVE | FRESH | DELAYED | STALE | CONFLICTED
    age_seconds: int
    label: str
    is_stale: bool
    is_conflicted: bool


def classify_freshness(
    market_ts: datetime,
    now: datetime,
    *,
    realtime: bool = True,
    conflicted: bool = False,
    simulated_session: bool = False,
    provider_down: bool = False,
) -> Freshness:
    """Freshness relative to what the market session allows.

    Outside regular hours the last close is the newest possible price, so a
    quote stamped at the close is FRESH, not stale.
    """
    age = now - market_ts
    reference_age = age
    label_suffix = ""
    if not simulated_session and session_state(now) != "OPEN":
        close = last_close(now)
        reference_age = max(timedelta(0), close - market_ts)
        label_suffix = " (market closed)"
    if reference_age > STALE_AFTER:
        status, label = "STALE", "Stale"
    elif reference_age > DELAYED_AFTER or not realtime or provider_down:
        status, label = "DELAYED", "Delayed" if not provider_down else "Last known"
    elif reference_age <= LIVE_WITHIN and realtime and label_suffix == "":
        status, label = "LIVE", "Live"
    else:
        status, label = "FRESH", "Fresh"
    is_stale = status == "STALE"
    if conflicted and not is_stale:
        status, label = "CONFLICTED", "Providers disagree"
    return Freshness(status, int(age.total_seconds()), label + label_suffix, is_stale, conflicted)


@dataclass
class Resolution:
    chosen: ProviderQuote
    sources: int
    conflicted: bool
    spread_pct: float
    observations: list[dict] = field(default_factory=list)
    reason: str = ""
    volume: int | None = None


def _freshness_weight(q: ProviderQuote, now: datetime) -> float:
    age = (now - q.market_timestamp).total_seconds()
    if age <= 120:
        return 1.0
    return max(0.3, 1 - (age - 120) / 3600)


def resolve_quotes(quotes: list[ProviderQuote], reliability: dict[str, float], tolerance_pct: float, now: datetime) -> Resolution:
    """Choose a preferred observation by reliability x freshness and detect disagreement."""
    if not quotes:
        raise ValueError("no observations")
    ranked = sorted(quotes, key=lambda q: reliability.get(q.provider, 0.5) * _freshness_weight(q, now), reverse=True)
    chosen = ranked[0]
    prices = [q.price for q in quotes]
    spread = (max(prices) - min(prices)) / chosen.price * 100 if len(quotes) > 1 else 0.0
    conflicted = len(quotes) > 1 and spread > tolerance_pct
    volume = chosen.volume if chosen.volume is not None else next((q.volume for q in ranked if q.volume is not None), None)
    obs = [
        {
            "provider": q.provider,
            "price": q.price,
            "market_timestamp": q.market_timestamp.isoformat(),
            "reliability": reliability.get(q.provider, 0.5),
        }
        for q in ranked
    ]
    if conflicted:
        reason = (
            f"Prices differ by {spread:.2f}% (tolerance {tolerance_pct:.2f}%). Preferred {chosen.provider}: "
            f"reliability {reliability.get(chosen.provider, 0.5):.2f}, age {int((now - chosen.market_timestamp).total_seconds())}s."
        )
    elif len(quotes) > 1:
        reason = f"{len(quotes)} providers agree within {tolerance_pct:.2f}%."
    else:
        reason = "Single provider; not cross-verified."
    return Resolution(chosen, len(quotes), conflicted, round(spread, 4), obs, reason, volume)
