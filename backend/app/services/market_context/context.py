"""Market and sector context: is this the stock, its sector, or the whole market?"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import AppState, CheckpointBaseline
from app.providers.market.universe import MARKET_BENCHMARK, SECTORS
from app.services.change_detection.detector import pct
from app.services.change_detection.views import snapshot_freshness
from app.services.snapshots.checkpoints import latest_snapshots
from app.utils.market_hours import session_state


def _bench(stock, snap, since: float | None = None) -> dict:
    return {
        "symbol": stock.symbol,
        "name": SECTORS.get(stock.symbol, "S&P 500" if stock.symbol == MARKET_BENCHMARK else stock.name),
        "price": snap.price if snap else None,
        "day_change_pct": snap.day_change_pct if snap else None,
        "since_check_pct": since,
        "freshness": snapshot_freshness(snap),
    }


def market_context(db: Session, baselines: dict[str, CheckpointBaseline] | None = None, meaningful: int = 0) -> dict:
    s = get_settings()
    now = datetime.now(UTC)
    state = latest_snapshots(db, [MARKET_BENCHMARK, *SECTORS])
    baselines = baselines or {}

    # Benchmark prices captured with the user's most recent baselines.
    market_ref = None
    sector_ref: dict[str, float] = {}
    for b in sorted(baselines.values(), key=lambda x: x.created_at):
        if b.market_price:
            market_ref = b.market_price
        if b.sector_symbol and b.sector_price:
            sector_ref[b.sector_symbol] = b.sector_price

    market = None
    m_since = None
    if MARKET_BENCHMARK in state:
        st, snap = state[MARKET_BENCHMARK]
        m_since = pct(snap.price, market_ref) if snap else None
        market = _bench(st, snap, m_since)
    sectors = []
    for etf in SECTORS:
        if etf in state:
            st, snap = state[etf]
            sectors.append(_bench(st, snap, pct(snap.price, sector_ref.get(etf)) if snap and etf in sector_ref else None))
    sectors.sort(key=lambda x: (x["since_check_pct"] is None, -(abs(x["since_check_pct"] or 0)), -(abs(x["day_change_pct"] or 0))))

    if m_since is not None and abs(m_since) >= 1.5:
        summary = (
            f"The market is {'down' if m_since < 0 else 'up'} {abs(m_since):.1f}% since you last checked. "
            "Moves that simply follow the market are ranked lower."
        )
    elif meaningful == 0:
        summary = "Most movement is broadly in line with the market."
    elif m_since is not None:
        summary = f"The market is roughly flat ({m_since:+.1f}%) since you last checked, so the changes above are specific to those stocks or sectors."
    else:
        summary = "Market context is building: benchmark data will appear after the next refresh."
    tracked = [x for x in sectors if x["since_check_pct"] is not None and abs(x["since_check_pct"]) >= 1.5]
    if tracked:
        top = tracked[0]
        summary += f" {top['name']} is {'down' if top['since_check_pct'] < 0 else 'up'} {abs(top['since_check_pct']):.1f}% over the same period."

    scenario = None
    if s.demo_mode and s.uses_mock_market:
        row = db.get(AppState, "demo.scenario")
        scenario = row.value.get("key") if row else "NORMAL_MOVEMENT"
    last = db.get(AppState, "market.last_ingest")
    return {
        "session": "SIMULATED" if s.uses_mock_market else session_state(now),
        "simulated": s.uses_mock_market,
        "scenario": scenario,
        "market": market,
        "sectors": sectors,
        "summary": summary,
        "last_update": datetime.fromisoformat(last.value["at"]) if last and last.value.get("at") else None,
    }
