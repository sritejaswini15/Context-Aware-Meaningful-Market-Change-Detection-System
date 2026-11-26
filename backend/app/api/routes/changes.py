from __future__ import annotations

import uuid
from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.db import get_db
from app.core.errors import NotFound
from app.models import ChangeEvent, CheckpointBaseline, MarketSnapshot, SignalScore, User
from app.schemas.api import ChangeCardOut, ChangeDetailOut, ChangeListOut
from app.services.ai.explainer import explanation_for_event
from app.services.change_detection.detector import ATT_RANK, ChangeDetectionService, acknowledge, mark_seen
from app.services.change_detection.views import change_cards, snapshot_freshness, sort_by_importance

router = APIRouter(prefix="/changes", tags=["changes"])


@router.get("", response_model=ChangeListOut)
def list_changes(
    attention: Literal["HIGH", "MEDIUM", "LOW"] | None = None,
    state: Literal["NEW", "SEEN", "ACKNOWLEDGED", "UNACKNOWLEDGED"] | None = None,
    scope: Literal["current", "history"] = "current",
    sort: Literal["importance", "recent"] = "importance",
    symbol: str | None = None,
    limit: int = Query(50, ge=1, le=200),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Meaningful changes. `current` = since your last check; `history` = everything."""
    ChangeDetectionService(db).evaluate_user(user)
    db.commit()
    q = select(ChangeEvent).where(ChangeEvent.user_id == user.id)
    if scope == "current":
        q = q.join(CheckpointBaseline, CheckpointBaseline.id == ChangeEvent.baseline_id).where(
            ChangeEvent.status == "ACTIVE", CheckpointBaseline.is_current.is_(True)
        )
    if symbol:
        q = q.where(ChangeEvent.symbol == symbol.upper())
    all_events = list(db.scalars(q.order_by(ChangeEvent.created_at.desc()).limit(500)))
    counts = {k: sum(1 for e in all_events if e.attention == k) for k in ("HIGH", "MEDIUM", "LOW")}
    counts["NEW"] = sum(1 for e in all_events if e.state == "NEW")
    counts["ACKNOWLEDGED"] = sum(1 for e in all_events if e.state == "ACKNOWLEDGED")
    counts["ALL"] = len(all_events)
    events = all_events
    if attention:
        events = [e for e in events if e.attention == attention]
    if state == "UNACKNOWLEDGED":
        events = [e for e in events if e.state != "ACKNOWLEDGED"]
    elif state:
        events = [e for e in events if e.state == state]
    cards = change_cards(db, events)
    cards = sort_by_importance(cards) if sort == "importance" else sorted(cards, key=lambda c: c["updated_at"], reverse=True)
    return {"items": cards[:limit], "total": len(cards), "counts": counts}


def _owned(db: Session, user: User, change_id: uuid.UUID) -> ChangeEvent:
    ev = db.scalar(select(ChangeEvent).where(ChangeEvent.id == change_id, ChangeEvent.user_id == user.id))
    if ev is None:
        raise NotFound("Change not found")
    return ev


@router.get("/{change_id}", response_model=ChangeDetailOut)
def get_change(change_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ev = _owned(db, user, change_id)
    card = change_cards(db, [ev])[0]
    signal = db.get(SignalScore, ev.latest_signal_id)
    snap = db.get(MarketSnapshot, signal.snapshot_id) if signal else None
    related = list(
        db.scalars(
            select(ChangeEvent).where(ChangeEvent.user_id == user.id, ChangeEvent.symbol == ev.symbol, ChangeEvent.id != ev.id).order_by(ChangeEvent.created_at.desc()).limit(10)
        )
    )
    return {
        **card,
        "factors": signal.factors if signal else [],
        "explanation": explanation_for_event(db, ev),
        "freshness": snapshot_freshness(snap),
        "history": change_cards(db, related),
    }


@router.post("/{change_id}/seen", response_model=ChangeCardOut)
def seen(change_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ev = mark_seen(db, user, change_id)
    if ev is None:
        raise NotFound("Change not found")
    db.commit()
    return change_cards(db, [ev])[0]


@router.post("/{change_id}/acknowledge", response_model=ChangeCardOut)
def ack(change_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """The user has reviewed this change: it stops being treated as new. A materially
    larger move later creates a new change event."""
    ev = acknowledge(db, user, change_id)
    if ev is None:
        raise NotFound("Change not found")
    db.commit()
    return change_cards(db, [ev])[0]


@router.post("/acknowledge-all")
def ack_all(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ids = list(
        db.scalars(
            select(ChangeEvent.id).where(ChangeEvent.user_id == user.id, ChangeEvent.status == "ACTIVE", ChangeEvent.state != "ACKNOWLEDGED")
        )
    )
    for cid in ids:
        acknowledge(db, user, cid)
    db.commit()
    return {"acknowledged": len(ids)}


def unacknowledged_count(db: Session, user: User) -> int:
    return db.scalar(
        select(func.count(ChangeEvent.id)).where(ChangeEvent.user_id == user.id, ChangeEvent.status == "ACTIVE", ChangeEvent.state != "ACKNOWLEDGED")
    ) or 0


__all__ = ["ATT_RANK", "router", "unacknowledged_count"]
