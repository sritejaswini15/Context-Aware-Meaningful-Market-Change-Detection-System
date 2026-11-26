from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.routes.auth import user_out
from app.api.routes.watchlists import summary
from app.core.db import get_db
from app.models import ChangeEvent, NotificationEvent, User, UserCheckpoint
from app.providers.ai.registry import ai_configured, get_ai_provider
from app.schemas.api import CommandCenterOut
from app.services.change_detection.detector import ATT_RANK, ChangeDetectionService
from app.services.change_detection.views import change_cards, sort_by_importance, stock_state
from app.services.market_context.context import market_context
from app.services.snapshots.checkpoints import CheckpointService
from app.services.watchlists.service import list_watchlists

router = APIRouter(tags=["command center"])


@router.get("/command-center", response_model=CommandCenterOut)
def command_center(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Everything for the "Since you last checked" screen in one round trip."""
    items = ChangeDetectionService(db).evaluate_user(user)
    db.commit()

    events = [it.event for it in items.values() if it.event is not None and it.event.status == "ACTIVE"]
    cards = sort_by_importance(change_cards(db, events))
    open_cards = [c for c in cards if c["state"] != "ACKNOWLEDGED"]
    reviewed = [c for c in cards if c["state"] == "ACKNOWLEDGED"]
    eventful = {e.symbol for e in events}
    quiet_items = [it for s, it in items.items() if s not in eventful and it.result is not None]
    quiet_items.sort(key=lambda it: -abs(it.inputs.change_pct))
    pending = [it for it in items.values() if it.result is None]

    attention_by_symbol = {c["symbol"]: c["attention"] for c in cards}
    watchlists = [summary(db, wl, attention_by_symbol) for wl in list_watchlists(db, user)]

    baselines = {s: it.baseline for s, it in items.items() if it.baseline is not None}
    statuses = [it.freshness.status for it in items.values() if it.freshness]

    activity = []
    for ev in db.scalars(select(ChangeEvent).where(ChangeEvent.user_id == user.id).order_by(ChangeEvent.updated_at.desc()).limit(12)):
        if ev.acknowledged_at:
            activity.append({"kind": "ACKNOWLEDGED", "at": ev.acknowledged_at, "title": f"You reviewed {ev.symbol}", "symbol": ev.symbol, "attention": ev.attention, "change_id": ev.id})
        verb = "rose" if ev.direction == "UP" else "fell"
        activity.append(
            {"kind": "CHANGE", "at": ev.created_at, "title": f"{ev.symbol} {verb} {abs(ev.change_pct):.1f}% ({ev.attention.lower()} attention)", "symbol": ev.symbol, "attention": ev.attention, "change_id": ev.id}
        )
    for cp in db.scalars(select(UserCheckpoint).where(UserCheckpoint.user_id == user.id).order_by(UserCheckpoint.created_at.desc()).limit(5)):
        activity.append({"kind": "CHECKPOINT", "at": cp.created_at, "title": f"You marked {cp.symbols_count} stocks as reviewed"})
    activity.sort(key=lambda a: a["at"], reverse=True)

    unread = db.scalar(select(func.count(NotificationEvent.id)).where(NotificationEvent.user_id == user.id, NotificationEvent.read_at.is_(None))) or 0
    provider = get_ai_provider()
    meaningful = len(open_cards)
    return {
        "user": user_out(user),
        "last_checked_at": CheckpointService(db).last_checked_at(user.id),
        "counts": {
            "meaningful": meaningful,
            "high": sum(1 for c in open_cards if c["attention"] == "HIGH"),
            "medium": sum(1 for c in open_cards if c["attention"] == "MEDIUM"),
            "low": len(quiet_items),
            "reviewed": len(reviewed),
            "tracked": len(items),
            "pending": len(pending),
        },
        "needs_attention": open_cards,
        "reviewed": reviewed,
        "quiet": [stock_state(it) for it in quiet_items],
        "market_context": market_context(db, baselines, meaningful),
        "watchlists": watchlists,
        "recent_activity": activity[:10],
        "data_quality": {
            "stale": statuses.count("STALE"),
            "delayed": statuses.count("DELAYED"),
            "conflicted": sum(1 for it in items.values() if it.snapshot is not None and it.snapshot.is_conflicted),
            "volume_unavailable": sum(1 for it in items.values() if it.snapshot is not None and it.snapshot.volume_ratio is None),
            "missing_price": len(pending),
        },
        "ai": {
            "configured": ai_configured(),
            "available": provider is not None and provider.__class__.__name__ != "SimulatedOutageProvider",
        },
        "unread_notifications": unread,
    }


__all__ = ["ATT_RANK", "router"]
