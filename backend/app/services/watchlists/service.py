"""Watchlists. Every query is scoped by user_id: a watchlist id alone never
grants access (ownership is checked on every read and write)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session, selectinload

from app.core.errors import Conflict, DomainError, NotFound
from app.core.logging import log_event
from app.models import ChangeEvent, CheckpointBaseline, Stock, User, Watchlist, WatchlistItem
from app.providers.market.universe import MARKET_BENCHMARK
from app.services.market_data.ingestion import IngestionService
from app.services.snapshots.checkpoints import CheckpointService, user_symbols
from app.workers.queue import enqueue_after_commit

MAX_WATCHLISTS = 20
MAX_ITEMS = 50


def list_watchlists(db: Session, user: User) -> list[Watchlist]:
    return list(
        db.scalars(
            select(Watchlist).where(Watchlist.user_id == user.id).options(selectinload(Watchlist.items)).order_by(Watchlist.position, Watchlist.created_at)
        )
    )


def get_owned(db: Session, user: User, watchlist_id: uuid.UUID) -> Watchlist:
    wl = db.scalar(
        select(Watchlist).where(Watchlist.id == watchlist_id, Watchlist.user_id == user.id).options(selectinload(Watchlist.items))
    )
    if wl is None:
        raise NotFound("Watchlist not found")  # same response whether it doesn't exist or isn't yours
    return wl


def create_watchlist(db: Session, user: User, name: str, symbols: list[str] | None = None) -> Watchlist:
    count = db.scalar(select(func.count(Watchlist.id)).where(Watchlist.user_id == user.id)) or 0
    if count >= MAX_WATCHLISTS:
        raise DomainError(f"You can have up to {MAX_WATCHLISTS} watchlists", "limit_reached")
    if db.scalar(select(Watchlist.id).where(Watchlist.user_id == user.id, func.lower(Watchlist.name) == name.lower())):
        raise Conflict("You already have a watchlist with that name")
    wl = Watchlist(user_id=user.id, name=name, position=count)
    db.add(wl)
    db.flush()
    for sym in symbols or []:
        add_stock(db, user, wl, sym)
    log_event("watchlist.created", user_id=str(user.id), watchlist_id=str(wl.id), symbols=len(symbols or []))
    return wl


def rename_watchlist(db: Session, user: User, wl: Watchlist, name: str) -> Watchlist:
    clash = db.scalar(
        select(Watchlist.id).where(Watchlist.user_id == user.id, func.lower(Watchlist.name) == name.lower(), Watchlist.id != wl.id)
    )
    if clash:
        raise Conflict("You already have a watchlist with that name")
    wl.name = name
    wl.updated_at = datetime.now(UTC)
    return wl


def delete_watchlist(db: Session, user: User, wl: Watchlist) -> None:
    symbols = [i.symbol for i in wl.items]
    db.delete(wl)
    db.flush()
    _retire_unwatched(db, user, symbols)


def prepare_symbol(db: Session, symbol: str) -> Stock:
    """Make sure we know the instrument and have a current price before baselining it."""
    svc = IngestionService(db)
    stock = svc.ensure_stock(symbol)
    if stock is None:
        raise NotFound(f"Unknown symbol {symbol}")
    if stock.stats_updated_at is None:
        svc.load_history(stock.symbol)
    needed = [stock.symbol, MARKET_BENCHMARK] + ([stock.sector_benchmark] if stock.sector_benchmark else [])
    missing = [s for s in needed if (st := db.get(Stock, s)) is None or st.latest_snapshot_id is None]
    if missing:
        svc.refresh(missing)
    enqueue_after_commit(db, "stock.bootstrap", {"symbol": stock.symbol}, job_id=f"bootstrap:{stock.symbol}:{datetime.now(UTC).date()}")
    return stock


def add_stock(db: Session, user: User, wl: Watchlist, symbol: str, priority: str = "NORMAL") -> WatchlistItem:
    symbol = symbol.upper()
    if any(i.symbol == symbol for i in wl.items):
        raise Conflict(f"{symbol} is already in this watchlist")
    if len(wl.items) >= MAX_ITEMS:
        raise DomainError(f"A watchlist can hold up to {MAX_ITEMS} stocks", "limit_reached")
    stock = prepare_symbol(db, symbol)
    if not stock.latest_snapshot_id:
        raise DomainError(f"No market data is available for {symbol} right now", "no_market_data")
    item = WatchlistItem(watchlist_id=wl.id, symbol=stock.symbol, priority=priority)
    wl.items.append(item)
    wl.updated_at = datetime.now(UTC)
    db.flush()
    # "Since you last checked" starts now for a newly watched stock.
    CheckpointService(db).ensure_baselines(user, [stock.symbol])
    user.last_evaluated_at = None
    log_event("watchlist.stock_added", user_id=str(user.id), symbol=stock.symbol)
    return item


def set_priority(db: Session, user: User, wl: Watchlist, symbol: str, priority: str) -> WatchlistItem:
    item = next((i for i in wl.items if i.symbol == symbol.upper()), None)
    if item is None:
        raise NotFound(f"{symbol} is not in this watchlist")
    item.priority = priority
    user.last_evaluated_at = None
    return item


def remove_stock(db: Session, user: User, wl: Watchlist, symbol: str) -> None:
    item = next((i for i in wl.items if i.symbol == symbol.upper()), None)
    if item is None:
        raise NotFound(f"{symbol} is not in this watchlist")
    wl.items.remove(item)
    wl.updated_at = datetime.now(UTC)
    db.flush()
    _retire_unwatched(db, user, [item.symbol])
    log_event("watchlist.stock_removed", user_id=str(user.id), symbol=item.symbol)


def _retire_unwatched(db: Session, user: User, symbols: list[str]) -> None:
    still = set(user_symbols(db, user.id))
    gone = [s for s in symbols if s not in still]
    if not gone:
        return
    ids = list(
        db.scalars(
            select(CheckpointBaseline.id).where(
                CheckpointBaseline.user_id == user.id, CheckpointBaseline.symbol.in_(gone), CheckpointBaseline.is_current.is_(True)
            )
        )
    )
    if ids:
        now = datetime.now(UTC)
        db.execute(update(CheckpointBaseline).where(CheckpointBaseline.id.in_(ids)).values(is_current=False, superseded_at=now))
        db.execute(
            update(ChangeEvent).where(ChangeEvent.baseline_id.in_(ids), ChangeEvent.status.in_(["ACTIVE", "RESOLVED"])).values(status="ARCHIVED", updated_at=now)
        )
    user.last_evaluated_at = None
