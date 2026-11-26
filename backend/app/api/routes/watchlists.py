from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.db import get_db
from app.models import ChangeEvent, CheckpointBaseline, Stock, User, Watchlist
from app.schemas.api import (
    AddStockIn,
    ChangeListOut,
    CheckpointOut,
    ItemPatch,
    StockStateOut,
    WatchlistIn,
    WatchlistOut,
    WatchlistPatch,
    WatchlistSummary,
)
from app.services.change_detection.detector import ATT_RANK, ChangeDetectionService
from app.services.change_detection.views import change_cards, sort_by_importance, stock_state
from app.services.snapshots.checkpoints import CheckpointService
from app.services.watchlists import service as wls

router = APIRouter(prefix="/watchlists", tags=["watchlists"])


def summary(db: Session, wl: Watchlist, attention_by_symbol: dict[str, str] | None = None) -> dict:
    attention_by_symbol = attention_by_symbol or {}
    syms = [i.symbol for i in wl.items]
    return {
        "id": wl.id,
        "name": wl.name,
        "symbols_count": len(syms),
        "symbols": syms,
        "high_count": sum(1 for s in syms if attention_by_symbol.get(s) == "HIGH"),
        "medium_count": sum(1 for s in syms if attention_by_symbol.get(s) == "MEDIUM"),
        "created_at": wl.created_at,
        "updated_at": wl.updated_at,
    }


def detail(db: Session, wl: Watchlist) -> dict:
    names = {s.symbol: s.name for s in db.scalars(select(Stock).where(Stock.symbol.in_([i.symbol for i in wl.items])))} if wl.items else {}
    return {
        **summary(db, wl),
        "items": [{"symbol": i.symbol, "name": names.get(i.symbol, i.symbol), "priority": i.priority, "added_at": i.added_at} for i in wl.items],
    }


def active_attention(db: Session, user: User) -> dict[str, str]:
    rows = db.execute(
        select(ChangeEvent.symbol, ChangeEvent.attention)
        .join(CheckpointBaseline, CheckpointBaseline.id == ChangeEvent.baseline_id)
        .where(ChangeEvent.user_id == user.id, ChangeEvent.status == "ACTIVE", CheckpointBaseline.is_current.is_(True))
    )
    out: dict[str, str] = {}
    for sym, att in rows:
        if ATT_RANK[att] > ATT_RANK.get(out.get(sym, "LOW"), 0):
            out[sym] = att
    return out


@router.get("", response_model=list[WatchlistSummary])
def list_all(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    att = active_attention(db, user)
    out = [summary(db, wl, att) for wl in wls.list_watchlists(db, user)]
    db.commit()
    return out


@router.post("", response_model=WatchlistOut, status_code=201)
def create(body: WatchlistIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    wl = wls.create_watchlist(db, user, body.name, body.symbols)
    db.commit()
    return detail(db, wls.get_owned(db, user, wl.id))


@router.get("/{watchlist_id}", response_model=WatchlistOut)
def get_one(watchlist_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return detail(db, wls.get_owned(db, user, watchlist_id))


@router.patch("/{watchlist_id}", response_model=WatchlistOut)
def rename(watchlist_id: uuid.UUID, body: WatchlistPatch, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    wl = wls.rename_watchlist(db, user, wls.get_owned(db, user, watchlist_id), body.name)
    db.commit()
    return detail(db, wl)


@router.delete("/{watchlist_id}", status_code=204)
def delete(watchlist_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    wls.delete_watchlist(db, user, wls.get_owned(db, user, watchlist_id))
    db.commit()
    return Response(status_code=204)


@router.post("/{watchlist_id}/stocks", response_model=WatchlistOut, status_code=201)
def add_stock(watchlist_id: uuid.UUID, body: AddStockIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    wl = wls.get_owned(db, user, watchlist_id)
    wls.add_stock(db, user, wl, body.symbol, body.priority)
    db.commit()
    return detail(db, wls.get_owned(db, user, watchlist_id))


@router.patch("/{watchlist_id}/stocks/{symbol}", response_model=WatchlistOut)
def update_stock(watchlist_id: uuid.UUID, symbol: str, body: ItemPatch, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    wl = wls.get_owned(db, user, watchlist_id)
    wls.set_priority(db, user, wl, symbol, body.priority)
    db.commit()
    return detail(db, wl)


@router.delete("/{watchlist_id}/stocks/{symbol}", response_model=WatchlistOut)
def remove_stock(watchlist_id: uuid.UUID, symbol: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    wl = wls.get_owned(db, user, watchlist_id)
    wls.remove_stock(db, user, wl, symbol)
    db.commit()
    return detail(db, wls.get_owned(db, user, watchlist_id))


@router.get("/{watchlist_id}/snapshot", response_model=list[StockStateOut])
def snapshot(watchlist_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Current state of every stock, with change since the user's checkpoint and its signal."""
    wl = wls.get_owned(db, user, watchlist_id)
    items = ChangeDetectionService(db).evaluate_user(user)
    db.commit()
    rows = [stock_state(items[i.symbol]) for i in wl.items if i.symbol in items]
    rows.sort(key=lambda r: (-(ATT_RANK[r["signal"]["attention"]] if r["signal"] else -1), -(r["signal"]["score"] if r["signal"] else 0)))
    return rows


@router.get("/{watchlist_id}/changes", response_model=ChangeListOut)
def changes(watchlist_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    wl = wls.get_owned(db, user, watchlist_id)
    items = ChangeDetectionService(db).evaluate_user(user)
    db.commit()
    syms = {i.symbol for i in wl.items}
    events = [it.event for s, it in items.items() if s in syms and it.event is not None and it.event.status == "ACTIVE"]
    cards = sort_by_importance(change_cards(db, events))
    counts = {k: sum(1 for c in cards if c["attention"] == k) for k in ("HIGH", "MEDIUM", "LOW")}
    return {"items": cards, "total": len(cards), "counts": counts}


@router.post("/{watchlist_id}/checkpoint", response_model=CheckpointOut, status_code=201)
def checkpoint(watchlist_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """"I've reviewed this watchlist": future changes are measured from now."""
    wl = wls.get_owned(db, user, watchlist_id)
    cp = CheckpointService(db).checkpoint(user, wl.id)
    db.commit()
    return cp


checkpoints = APIRouter(tags=["watchlists"])


@checkpoints.post("/checkpoint", response_model=CheckpointOut, status_code=201)
def checkpoint_all(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """"I'm caught up" across all watchlists."""
    cp = CheckpointService(db).checkpoint(user, None)
    db.commit()
    return cp
