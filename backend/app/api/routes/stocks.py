from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.config import get_settings
from app.core.db import get_db
from app.core.errors import NotFound
from app.core.logging import log_event
from app.models import (
    ChangeEvent,
    DataConflict,
    MarketEvent,
    MarketHistory,
    MarketSnapshot,
    SignalScore,
    Stock,
    User,
    Watchlist,
    WatchlistItem,
)
from app.providers.market.base import ProviderError
from app.providers.market.registry import get_market_providers
from app.providers.market.universe import MARKET_BENCHMARK, SECTORS
from app.schemas.api import EventOut, SearchResultOut, StockDetailOut
from app.services.ai.explainer import explanation_for_event
from app.services.change_detection.detector import ChangeDetectionService, EvaluatedItem
from app.services.change_detection.views import change_cards, snapshot_freshness, stock_state
from app.services.market_data.quality import classify_freshness
from app.services.preferences.service import engine_preferences, get_preferences
from app.services.signal_engine.engine import EventFact, SignalInputs, evaluate
from app.services.snapshots.checkpoints import latest_snapshots
from app.services.watchlists.service import prepare_symbol

router = APIRouter(prefix="/stocks", tags=["stocks"])


def _in_watchlists(db: Session, user: User, symbol: str) -> list:
    return list(db.scalars(select(Watchlist.id).join(WatchlistItem).where(Watchlist.user_id == user.id, WatchlistItem.symbol == symbol)))


@router.get("/search", response_model=list[SearchResultOut])
def search(q: str = Query(min_length=1, max_length=40), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Search by ticker or company name: local reference data first, then the provider."""
    term = q.strip()
    like = f"%{term.lower()}%"
    local = list(
        db.scalars(
            select(Stock)
            .where(Stock.kind == "EQUITY", or_(func.lower(Stock.symbol).like(like), func.lower(Stock.name).like(like)))
            .order_by((func.lower(Stock.symbol) == term.lower()).desc(), Stock.symbol)
            .limit(10)
        )
    )
    results = {s.symbol: {"symbol": s.symbol, "name": s.name, "exchange": s.exchange, "sector": s.sector} for s in local}
    if len(results) < 5:
        for p in get_market_providers():
            try:
                for prof in p.search(term):
                    results.setdefault(prof.symbol, {"symbol": prof.symbol, "name": prof.name, "exchange": prof.exchange, "sector": prof.sector})
                break
            except ProviderError as exc:
                log_event("provider.search_failed", provider=p.name, error=str(exc))
    syms = list(results)[:10]
    state = latest_snapshots(db, syms)
    owned: dict[str, list] = {}
    for wid, sym in db.execute(select(Watchlist.id, WatchlistItem.symbol).join(WatchlistItem).where(Watchlist.user_id == user.id, WatchlistItem.symbol.in_(syms))):
        owned.setdefault(sym, []).append(wid)
    out = []
    for sym in syms:
        snap = state.get(sym, (None, None))[1]
        out.append({**results[sym], "price": snap.price if snap else None, "day_change_pct": snap.day_change_pct if snap else None, "in_watchlists": owned.get(sym, [])})
    return out


def _today_item(db: Session, user: User, stock: Stock, snap: MarketSnapshot) -> EvaluatedItem:
    """Signal for a stock the user doesn't watch: measured against the previous close."""
    bench = latest_snapshots(db, [MARKET_BENCHMARK] + ([stock.sector_benchmark] if stock.sector_benchmark else []))
    sector_snap = bench.get(stock.sector_benchmark or "", (None, None))[1]
    market_snap = bench.get(MARKET_BENCHMARK, (None, None))[1]
    now = datetime.now(UTC)
    fresh = classify_freshness(snap.market_timestamp, now, realtime=snap.provider_realtime, conflicted=snap.is_conflicted, simulated_session=get_settings().uses_mock_market)
    evs = db.scalars(select(MarketEvent).where(MarketEvent.symbol == stock.symbol, MarketEvent.event_time >= now - timedelta(hours=24)))
    inputs = SignalInputs(
        symbol=stock.symbol,
        name=stock.name,
        change_pct=snap.day_change_pct or 0.0,
        day_change_pct=snap.day_change_pct,
        window_trading_days=1.0,
        sector_name=stock.sector if stock.kind == "EQUITY" else None,
        sector_change_pct=sector_snap.day_change_pct if sector_snap else None,
        market_change_pct=market_snap.day_change_pct if market_snap and stock.symbol != MARKET_BENCHMARK else None,
        volume_ratio=snap.volume_ratio,
        daily_volatility_pct=stock.daily_volatility_pct,
        events=[EventFact(e.event_type, e.headline, e.significance, e.event_time.isoformat()) for e in evs],
        data_status=fresh.status,
        is_conflicted=snap.is_conflicted,
        conflict_spread_pct=snap.conflict_spread_pct,
        sources_count=snap.sources_count,
    )
    result = evaluate(inputs, engine_preferences(get_preferences(db, user)))
    return EvaluatedItem(symbol=stock.symbol, stock=stock, priority="NORMAL", snapshot=snap, freshness=fresh, inputs=inputs, result=result)


def _bench_out(stock: Stock | None, snap: MarketSnapshot | None, since: float | None) -> dict | None:
    if stock is None:
        return None
    return {
        "symbol": stock.symbol,
        "name": SECTORS.get(stock.symbol, "S&P 500" if stock.symbol == MARKET_BENCHMARK else stock.name),
        "price": snap.price if snap else None,
        "day_change_pct": snap.day_change_pct if snap else None,
        "since_check_pct": since,
        "freshness": snapshot_freshness(snap),
    }


@router.get("/{symbol}", response_model=StockDetailOut)
def stock_detail(symbol: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    symbol = symbol.upper()
    stock = db.get(Stock, symbol)
    if stock is None or stock.latest_snapshot_id is None:
        try:
            stock = prepare_symbol(db, symbol)
        except NotFound:
            raise
    watched = _in_watchlists(db, user, symbol)
    items = ChangeDetectionService(db).evaluate_user(user) if watched else {}
    db.commit()
    item = items.get(symbol)
    basis = "CHECKPOINT"
    if item is None or item.result is None:
        snap = db.get(MarketSnapshot, stock.latest_snapshot_id) if stock.latest_snapshot_id else None
        if snap is None:
            raise NotFound(f"No market data for {symbol}")
        item = _today_item(db, user, stock, snap)
        basis = "PREVIOUS_CLOSE"
    ev = item.event if item.event is not None and item.event.status == "ACTIVE" else None
    bench = latest_snapshots(db, [MARKET_BENCHMARK] + ([stock.sector_benchmark] if stock.sector_benchmark else []))
    events = list(db.scalars(select(MarketEvent).where(MarketEvent.symbol == symbol).order_by(MarketEvent.event_time.desc()).limit(10)))
    # Only surface a conflict that applies to the price being shown right now.
    conflict = (
        db.scalar(select(DataConflict).where(DataConflict.snapshot_id == stock.latest_snapshot_id).limit(1))
        if stock.latest_snapshot_id
        else None
    )
    s_stock, s_snap = bench.get(stock.sector_benchmark or "", (None, None))
    m_stock, m_snap = bench.get(MARKET_BENCHMARK, (None, None))
    return {
        "state": stock_state(item),
        "signal_basis": basis,
        "factors": item.result.factors_json() if item.result else [],
        "change": change_cards(db, [ev])[0] if ev else None,
        "explanation": explanation_for_event(db, ev) if ev else None,
        "sector": _bench_out(s_stock, s_snap, item.inputs.sector_change_pct if item.inputs else None),
        "market": _bench_out(m_stock, m_snap, item.inputs.market_change_pct if item.inputs else None),
        "events": [EventOut.model_validate(e, from_attributes=True).model_dump() for e in events],
        "conflict": (
            {
                "detected_at": conflict.detected_at,
                "observations": conflict.observations,
                "chosen_provider": conflict.chosen_provider,
                "chosen_price": conflict.chosen_price,
                "spread_pct": conflict.spread_pct,
                "tolerance_pct": conflict.tolerance_pct,
                "resolution": conflict.resolution,
            }
            if conflict
            else None
        ),
        "in_watchlists": watched,
        "stats": {
            "daily_volatility_pct": stock.daily_volatility_pct,
            "avg_volume_20d": stock.avg_volume_20d,
            "history_available": stock.daily_volatility_pct is not None,
        },
    }


@router.get("/{symbol}/history")
def history(symbol: str, days: int = Query(90, ge=5, le=365), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Chart data. Each series answers one question:
    price (how did it move?), relative (vs sector and market), volume (how unusual?),
    since_check (what happened since you last looked?)."""
    symbol = symbol.upper()
    stock = db.get(Stock, symbol)
    if stock is None:
        raise NotFound(f"Unknown symbol {symbol}")
    bench_syms = [MARKET_BENCHMARK] + ([stock.sector_benchmark] if stock.sector_benchmark else [])
    rows = list(
        db.scalars(
            select(MarketHistory).where(MarketHistory.symbol.in_([symbol, *bench_syms])).order_by(MarketHistory.date.desc()).limit(days * (1 + len(bench_syms)))
        )
    )
    by_sym: dict[str, dict] = {}
    for r in rows:
        by_sym.setdefault(r.symbol, {})[r.date] = r
    own = by_sym.get(symbol, {})
    dates = sorted(own)[-days:]
    price = [{"date": d.isoformat(), "close": own[d].close, "volume": own[d].volume} for d in dates]
    relative = []
    if dates:
        base = {s: by_sym.get(s, {}).get(dates[0]) for s in [symbol, *bench_syms]}
        for d in dates:
            point = {"date": d.isoformat()}
            for key, s in (("stock", symbol), ("sector", stock.sector_benchmark), ("market", MARKET_BENCHMARK)):
                r, b = by_sym.get(s or "", {}).get(d), base.get(s or "")
                point[key] = round((r.close / b.close - 1) * 100, 3) if r and b else None
            relative.append(point)
    vols = [p["volume"] for p in price[-20:] if p["volume"]]
    since = []
    watched = _in_watchlists(db, user, symbol)
    baseline_at = None
    if watched:
        from app.services.snapshots.checkpoints import CheckpointService

        b = CheckpointService(db).current_baselines(user.id, [symbol]).get(symbol)
        if b is not None:
            baseline_at = b.created_at
            refs = {symbol: b.price, stock.sector_benchmark: b.sector_price, MARKET_BENCHMARK: b.market_price}
            snaps = list(
                db.scalars(
                    select(MarketSnapshot)
                    .where(MarketSnapshot.symbol.in_([symbol, *bench_syms]), MarketSnapshot.first_seen_at >= b.created_at - timedelta(seconds=5))
                    .order_by(MarketSnapshot.first_seen_at)
                    .limit(2000)
                )
            )
            current = {"stock": 0.0, "sector": 0.0 if b.sector_price else None, "market": 0.0 if b.market_price else None}
            since.append({"at": b.created_at.isoformat(), **current})
            for sn in snaps:
                key = "stock" if sn.symbol == symbol else "sector" if sn.symbol == stock.sector_benchmark else "market"
                ref = refs.get(sn.symbol)
                if ref:
                    current[key] = round((sn.price / ref - 1) * 100, 3)
                    since.append({"at": sn.first_seen_at.isoformat(), **current})
            last = db.get(MarketSnapshot, stock.latest_snapshot_id) if stock.latest_snapshot_id else None
            if last is not None and since:
                since.append({"at": datetime.now(UTC).isoformat(), **current})
    return {
        "symbol": symbol,
        "sector_symbol": stock.sector_benchmark,
        "market_symbol": MARKET_BENCHMARK,
        "price": price,
        "relative": relative,
        "volume": {"bars": price, "avg_20d": (sum(vols) / len(vols)) if vols else None, "available": bool(vols)},
        "since_check": since,
        "baseline_at": baseline_at,
        "history_available": bool(price),
    }


@router.get("/{symbol}/signals")
def signals(symbol: str, limit: int = Query(30, ge=1, le=200), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Your evaluation history and change timeline for this stock."""
    symbol = symbol.upper()
    scores = list(
        db.scalars(select(SignalScore).where(SignalScore.user_id == user.id, SignalScore.symbol == symbol).order_by(SignalScore.created_at.desc()).limit(limit))
    )
    events = list(db.scalars(select(ChangeEvent).where(ChangeEvent.user_id == user.id, ChangeEvent.symbol == symbol).order_by(ChangeEvent.created_at.desc()).limit(20)))
    return {
        "signals": [
            {
                "id": s.id,
                "at": s.created_at,
                "score": s.score,
                "attention": s.attention,
                "movement_type": s.movement_type,
                "confidence": s.confidence,
                "change_pct": s.inputs.get("change_pct"),
                "data_status": s.inputs.get("data_status"),
                "headline": s.headline,
            }
            for s in scores
        ],
        "changes": change_cards(db, events),
    }
