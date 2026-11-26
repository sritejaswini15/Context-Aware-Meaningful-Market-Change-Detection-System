"""Checkpoints: remember exactly what the user last saw.

A baseline per (user, symbol) records the price the user saw *and* the sector
and market benchmark prices at that moment, so "since you last checked" is
measured over the same window for stock, sector and market.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.logging import log_event
from app.models import ChangeEvent, CheckpointBaseline, MarketSnapshot, Stock, User, UserCheckpoint, Watchlist, WatchlistItem
from app.providers.market.universe import MARKET_BENCHMARK


def latest_snapshots(db: Session, symbols: Iterable[str]) -> dict[str, tuple[Stock, MarketSnapshot | None]]:
    symbols = list(set(symbols))
    if not symbols:
        return {}
    rows = db.execute(
        select(Stock, MarketSnapshot)
        .outerjoin(MarketSnapshot, MarketSnapshot.id == Stock.latest_snapshot_id)
        .where(Stock.symbol.in_(symbols))
    ).all()
    return {stock.symbol: (stock, snap) for stock, snap in rows}


def user_symbols(db: Session, user_id: uuid.UUID, watchlist_id: uuid.UUID | None = None) -> dict[str, str]:
    """symbol -> effective priority (HIGH wins across watchlists)."""
    q = select(WatchlistItem.symbol, WatchlistItem.priority).join(Watchlist).where(Watchlist.user_id == user_id)
    if watchlist_id is not None:
        q = q.where(Watchlist.id == watchlist_id)
    out: dict[str, str] = {}
    for sym, prio in db.execute(q):
        if out.get(sym) != "HIGH":
            out[sym] = prio
    return out


class CheckpointService:
    def __init__(self, db: Session, now: datetime | None = None):
        self.db = db
        self.now = now or datetime.now(UTC)

    def current_baselines(self, user_id: uuid.UUID, symbols: Iterable[str] | None = None) -> dict[str, CheckpointBaseline]:
        q = select(CheckpointBaseline).where(CheckpointBaseline.user_id == user_id, CheckpointBaseline.is_current.is_(True))
        if symbols is not None:
            q = q.where(CheckpointBaseline.symbol.in_(list(symbols)))
        return {b.symbol: b for b in self.db.scalars(q)}

    def create_baselines(self, user: User, symbols: Iterable[str], reason: str, checkpoint: UserCheckpoint | None = None) -> list[CheckpointBaseline]:
        symbols = sorted(set(symbols))
        if not symbols:
            return []
        state = latest_snapshots(self.db, symbols)
        bench_syms = {MARKET_BENCHMARK} | {st.sector_benchmark for st, _ in state.values() if st.sector_benchmark}
        bench = latest_snapshots(self.db, bench_syms)
        priceable = [s for s in symbols if s in state and state[s][1] is not None]
        if not priceable:
            return []

        old = self.current_baselines(user.id, priceable)
        if old:
            old_ids = [b.id for b in old.values()]
            self.db.execute(
                update(CheckpointBaseline)
                .where(CheckpointBaseline.id.in_(old_ids))
                .values(is_current=False, superseded_at=self.now)
            )
            # Changes measured against an old baseline are history now.
            self.db.execute(
                update(ChangeEvent)
                .where(ChangeEvent.baseline_id.in_(old_ids), ChangeEvent.status.in_(["ACTIVE", "RESOLVED"]))
                .values(status="ARCHIVED", updated_at=self.now)
            )
            self.db.flush()

        from app.services.market_data.quality import classify_freshness

        simulated = get_settings().uses_mock_market
        created = []
        for sym in priceable:
            stock, snap = state[sym]
            sector_snap = bench.get(stock.sector_benchmark or "", (None, None))[1]
            market_snap = bench.get(MARKET_BENCHMARK, (None, None))[1]
            fresh = classify_freshness(snap.market_timestamp, self.now, realtime=snap.provider_realtime, conflicted=snap.is_conflicted, simulated_session=simulated)
            b = CheckpointBaseline(
                user_id=user.id,
                checkpoint_id=checkpoint.id if checkpoint else None,
                symbol=sym,
                reason=reason,
                price=snap.price,
                volume=snap.volume,
                market_timestamp=snap.market_timestamp,
                snapshot_id=snap.id,
                sector_symbol=stock.sector_benchmark if sector_snap else None,
                sector_price=sector_snap.price if sector_snap else None,
                market_symbol=MARKET_BENCHMARK if market_snap and sym != MARKET_BENCHMARK else None,
                market_price=market_snap.price if market_snap and sym != MARKET_BENCHMARK else None,
                baseline_status=fresh.status,
                is_current=True,
                created_at=self.now,
            )
            self.db.add(b)
            created.append(b)
        self.db.flush()
        user.last_evaluated_at = None
        return created

    def ensure_baselines(self, user: User, symbols: Iterable[str]) -> list[CheckpointBaseline]:
        symbols = set(symbols)
        have = set(self.current_baselines(user.id, symbols))
        missing = symbols - have
        return self.create_baselines(user, missing, reason="ADDED") if missing else []

    def checkpoint(self, user: User, watchlist_id: uuid.UUID | None = None) -> UserCheckpoint:
        symbols = user_symbols(self.db, user.id, watchlist_id)
        cp = UserCheckpoint(
            user_id=user.id,
            watchlist_id=watchlist_id,
            scope="WATCHLIST" if watchlist_id else "ALL",
            symbols_count=len(symbols),
            created_at=self.now,
        )
        self.db.add(cp)
        self.db.flush()
        self.create_baselines(user, symbols, reason="CHECKPOINT", checkpoint=cp)
        log_event("checkpoint.created", user_id=str(user.id), scope=cp.scope, symbols=len(symbols))
        return cp

    def last_checked_at(self, user_id: uuid.UUID) -> datetime | None:
        cp = self.db.scalar(select(UserCheckpoint.created_at).where(UserCheckpoint.user_id == user_id).order_by(UserCheckpoint.created_at.desc()).limit(1))
        if cp:
            return cp
        return self.db.scalar(
            select(CheckpointBaseline.created_at)
            .where(CheckpointBaseline.user_id == user_id, CheckpointBaseline.is_current.is_(True))
            .order_by(CheckpointBaseline.created_at.asc())
            .limit(1)
        )
