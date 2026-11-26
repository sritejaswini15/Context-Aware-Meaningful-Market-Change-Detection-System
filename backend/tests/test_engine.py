"""Meaningful-change engine, freshness and conflict resolution (pure logic)."""

from datetime import UTC, datetime, timedelta

import pytest

from app.providers.market.base import ProviderQuote
from app.services.market_data.quality import classify_freshness, resolve_quotes
from app.services.signal_engine.engine import EventFact, Preferences, SignalInputs, evaluate


def inputs(chg, sec, mkt, vol=1.0, sigma=2.4, **kw):
    return SignalInputs(
        symbol="X", name="X Corp", change_pct=chg, day_change_pct=chg, window_trading_days=0.3, sector_name="Technology",
        sector_change_pct=sec, market_change_pct=mkt, volume_ratio=vol, daily_volatility_pct=sigma, **kw,
    )


def test_stock_specific_drop_is_high_attention():
    r = evaluate(inputs(-4.8, -0.7, -0.3, vol=2.8))
    assert r.attention == "HIGH"
    assert r.movement_type == "STOCK_SPECIFIC"
    assert 70 <= r.score <= 85
    assert sum(f.points for f in r.factors) == pytest.approx(r.score, abs=1)


def test_same_move_with_broad_market_is_deprioritised():
    specific = evaluate(inputs(-4.8, -0.7, -0.3, vol=1.6))
    broad = evaluate(inputs(-4.8, -4.2, -3.9, vol=1.6))
    assert broad.movement_type == "MARKET_WIDE"
    assert broad.attention == "LOW"
    assert broad.score < specific.score - 30


def test_sector_wide_move_is_labelled_and_medium():
    r = evaluate(inputs(-3.9, -3.6, -0.2, vol=1.7, sigma=1.6))
    assert r.movement_type == "SECTOR_WIDE"
    assert r.attention == "MEDIUM"


def test_volume_alone_never_makes_high_attention():
    r = evaluate(inputs(0.2, 0.1, 0.1, vol=5.0, sigma=1.3), Preferences(sensitivity="HIGH"))
    assert r.attention != "HIGH"
    vol = next(f for f in r.factors if f.key == "volume_anomaly")
    assert "halved" in vol.detail


def test_events_and_priority_add_points():
    base = evaluate(inputs(-3.0, -0.5, -0.2, vol=1.5))
    with_event = evaluate(inputs(-3.0, -0.5, -0.2, vol=1.5, events=[EventFact("EARNINGS", "Q3 results", 1.0, "t")], priority="HIGH"))
    assert with_event.score > base.score + 15


def test_preferences_change_ranking_and_keep_0_100_scale():
    full = evaluate(inputs(1.1, 0.2, 0.1, vol=3.4, sigma=1.3))
    no_volume = evaluate(inputs(1.1, 0.2, 0.1, vol=3.4, sigma=1.3), Preferences(include_volume=False))
    assert no_volume.score < full.score
    assert abs(sum(f.max_points for f in no_volume.factors) - 100) < 0.5
    sensitive = evaluate(inputs(1.1, 0.2, 0.1, vol=3.4, sigma=1.3), Preferences(sensitivity="HIGH"))
    assert full.attention == "LOW" and sensitive.attention == "MEDIUM"


def test_stale_and_conflicted_data_reduce_confidence_and_cap_attention():
    fresh = evaluate(inputs(-4.8, -0.7, -0.3, vol=2.8))
    stale = evaluate(inputs(-4.8, -0.7, -0.3, vol=2.8, data_status="STALE"))
    conflicted = evaluate(inputs(-4.8, -0.7, -0.3, vol=2.8, data_status="CONFLICTED", is_conflicted=True, conflict_spread_pct=3.9))
    assert fresh.attention == "HIGH"
    assert stale.attention == "MEDIUM" and stale.confidence < 0.7
    assert conflicted.attention == "MEDIUM" and conflicted.confidence < fresh.confidence
    assert any("stale" in c.lower() for c in stale.caveats)


def test_missing_volume_and_history_are_explicit_not_invented():
    r = evaluate(inputs(-4.8, -0.7, -0.3, vol=None, sigma=None))
    vol = next(f for f in r.factors if f.key == "volume_anomaly")
    assert vol.points == 0 and vol.detail == "Volume unavailable"
    assert r.confidence < 1.0


def test_freshness_states():
    now = datetime(2026, 11, 25, 16, 0, tzinfo=UTC)  # 11:00 New York, market open
    assert classify_freshness(now - timedelta(seconds=20), now).status == "LIVE"
    assert classify_freshness(now - timedelta(minutes=3), now).status == "FRESH"
    assert classify_freshness(now - timedelta(minutes=12), now).status == "DELAYED"
    assert classify_freshness(now - timedelta(minutes=45), now).status == "STALE"
    assert classify_freshness(now - timedelta(seconds=20), now, conflicted=True).status == "CONFLICTED"
    # Market closed: a quote from the close is fresh, not stale.
    saturday = datetime(2026, 11, 28, 15, 0, tzinfo=UTC)
    friday_close = datetime(2026, 11, 27, 21, 0, tzinfo=UTC)
    assert classify_freshness(friday_close, saturday).status == "FRESH"


def test_conflict_resolution_prefers_reliable_fresh_source_and_flags_disagreement():
    now = datetime.now(UTC)
    a = ProviderQuote(symbol="NVDA", provider="a", price=180.20, market_timestamp=now - timedelta(seconds=20))
    b = ProviderQuote(symbol="NVDA", provider="b", price=186.90, market_timestamp=now - timedelta(minutes=4))
    res = resolve_quotes([b, a], {"a": 0.95, "b": 0.8}, tolerance_pct=1.0, now=now)
    assert res.chosen.provider == "a"
    assert res.conflicted and res.spread_pct > 3.5
    agree = resolve_quotes([a, a.model_copy(update={"provider": "b", "price": 180.25})], {"a": 0.95, "b": 0.8}, 1.0, now)
    assert not agree.conflicted and agree.sources == 2
