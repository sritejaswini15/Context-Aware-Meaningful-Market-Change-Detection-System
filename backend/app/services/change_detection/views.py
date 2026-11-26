"""Read models: turn evaluated state into API payloads without N+1 queries."""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import ChangeEvent, CheckpointBaseline, MarketSnapshot, SignalExplanation, SignalScore, Stock
from app.services.change_detection.detector import ATT_RANK, EvaluatedItem
from app.services.market_data.quality import Freshness, classify_freshness

CONTEXT_LABELS = {
    "STOCK_SPECIFIC": "Stock-specific",
    "MARKET_WIDE": "Broad market movement",
    "SECTOR_WIDE": "Sector movement",
    "QUIET": "In line with the market",
}


def context_label(movement_type: str, sector: str | None = None) -> str:
    if movement_type == "SECTOR_WIDE" and sector:
        return f"{sector} sector movement"
    return CONTEXT_LABELS.get(movement_type, movement_type.replace("_", " ").title())


def freshness_out(snap: MarketSnapshot | None, fresh: Freshness | None) -> dict | None:
    if snap is None or fresh is None:
        return None
    return {
        "status": fresh.status,
        "label": fresh.label,
        "age_seconds": fresh.age_seconds,
        "is_stale": fresh.is_stale,
        "is_conflicted": fresh.is_conflicted,
        "market_timestamp": snap.market_timestamp,
        "provider": snap.primary_provider,
        "sources_count": snap.sources_count,
        "simulated": snap.primary_provider.startswith("mock"),
    }


def snapshot_freshness(snap: MarketSnapshot | None, provider_down: bool = False) -> dict | None:
    if snap is None:
        return None
    fresh = classify_freshness(
        snap.market_timestamp,
        datetime.now(UTC),
        realtime=snap.provider_realtime,
        conflicted=snap.is_conflicted,
        simulated_session=get_settings().uses_mock_market,
        provider_down=provider_down,
    )
    return freshness_out(snap, fresh)


def stock_state(item: EvaluatedItem) -> dict:
    st, snap, b, r, i = item.stock, item.snapshot, item.baseline, item.result, item.inputs
    return {
        "symbol": st.symbol,
        "name": st.name,
        "sector": st.sector,
        "sector_benchmark": st.sector_benchmark,
        "exchange": st.exchange,
        "currency": st.currency,
        "kind": st.kind,
        "priority": item.priority,
        "price": snap.price if snap else None,
        "day_change_pct": snap.day_change_pct if snap else None,
        "since_check_pct": i.change_pct if i else None,
        "sector_since_check_pct": i.sector_change_pct if i else None,
        "market_since_check_pct": i.market_change_pct if i else None,
        "volume": snap.volume if snap else None,
        "volume_ratio": snap.volume_ratio if snap else None,
        "freshness": freshness_out(snap, item.freshness),
        "baseline": {"price": b.price, "checked_at": b.created_at, "reason": b.reason, "status": b.baseline_status} if b else None,
        "signal": (
            {
                "score": r.score,
                "attention": r.attention,
                "movement_type": r.movement_type,
                "context_label": context_label(r.movement_type, st.sector),
                "confidence": r.confidence,
                "confidence_level": r.confidence_level,
                "headline": r.headline,
                "caveats": r.caveats,
                "evaluated_at": item.signal.created_at if item.signal else None,
            }
            if r
            else None
        ),
        "change_id": item.event.id if item.event is not None and item.event.status == "ACTIVE" else None,
        "change_state": item.event.state if item.event is not None and item.event.status == "ACTIVE" else None,
    }


def change_cards(db: Session, events: Iterable[ChangeEvent]) -> list[dict]:
    events = list(events)
    if not events:
        return []
    stocks = {s.symbol: s for s in db.scalars(select(Stock).where(Stock.symbol.in_({e.symbol for e in events})))}
    baselines = {b.id: b for b in db.scalars(select(CheckpointBaseline).where(CheckpointBaseline.id.in_({e.baseline_id for e in events})))}
    signals = {s.id: s for s in db.scalars(select(SignalScore).where(SignalScore.id.in_({e.latest_signal_id for e in events})))}
    snap_ids = {s.snapshot_id for s in signals.values()}
    snaps = {s.id: s for s in db.scalars(select(MarketSnapshot).where(MarketSnapshot.id.in_(snap_ids)))} if snap_ids else {}
    summaries: dict[uuid.UUID, str] = {}
    for exp in db.scalars(
        select(SignalExplanation).where(SignalExplanation.change_event_id.in_([e.id for e in events])).order_by(SignalExplanation.created_at)
    ):
        summaries[exp.change_event_id] = exp.summary
    out = []
    for e in events:
        st = stocks.get(e.symbol)
        sig = signals.get(e.latest_signal_id)
        snap = snaps.get(sig.snapshot_id) if sig else None
        b = baselines.get(e.baseline_id)
        out.append(
            {
                "id": e.id,
                "symbol": e.symbol,
                "name": st.name if st else e.symbol,
                "sector": st.sector if st else None,
                "attention": e.attention,
                "peak_attention": e.peak_attention,
                "score": e.score,
                "movement_type": e.movement_type,
                "context_label": context_label(e.movement_type, st.sector if st else None),
                "direction": e.direction,
                "change_pct": e.change_pct,
                "day_change_pct": e.day_change_pct,
                "sector_change_pct": e.sector_change_pct,
                "market_change_pct": e.market_change_pct,
                "volume_ratio": e.volume_ratio,
                "price": snap.price if snap else None,
                "baseline_price": b.price if b else None,
                "checked_at": b.created_at if b else None,
                "confidence": e.confidence,
                "confidence_level": "HIGH" if e.confidence >= 0.75 else "MEDIUM" if e.confidence >= 0.5 else "LOW",
                "data_status": e.data_status,
                "headline": e.headline,
                "summary": summaries.get(e.id),
                "state": e.state,
                "status": e.status,
                "generation": e.generation,
                "created_at": e.created_at,
                "updated_at": e.updated_at,
                "caveats": list(sig.caveats or []) if sig else [],
            }
        )
    return out


def sort_by_importance(cards: list[dict]) -> list[dict]:
    return sorted(cards, key=lambda c: (c["state"] == "ACKNOWLEDGED", -ATT_RANK[c["attention"]], -c["score"], c["symbol"]))
