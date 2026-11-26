"""In-app notifications for meaningful changes only.

Records are channel-agnostic (`channel` column), so email/push can be added
as additional delivery workers without changing detection logic.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.core.db import insert_ignore
from app.core.logging import log_event
from app.models import ChangeEvent, NotificationEvent, User, UserPreferences

_RANK = {"LOW": 0, "MEDIUM": 1, "HIGH": 2}


def notify_change(db: Session, user: User, ev: ChangeEvent, kind: str, prefs: UserPreferences) -> bool:
    if _RANK[ev.attention] < _RANK.get(prefs.notify_min_attention, 2):
        return False
    verb = "rose" if ev.direction == "UP" else "fell"
    title = f"{ev.symbol} {verb} {abs(ev.change_pct):.1f}% since you last checked"
    if kind == "ESCALATION":
        title = f"{ev.symbol} escalated to {ev.attention} attention"
    inserted = insert_ignore(
        db,
        NotificationEvent,
        [
            {
                "id": uuid.uuid4(),
                "user_id": user.id,
                "change_event_id": ev.id,
                "kind": kind,
                "channel": "IN_APP",
                "title": title[:200],
                "body": ev.headline,
                "attention": ev.attention,
                "symbol": ev.symbol,
                "dedupe_key": f"{ev.id}:{kind}:{ev.attention}",
                "created_at": datetime.now(UTC),
            }
        ],
        ["dedupe_key"],
    )
    if inserted:
        log_event("notification.generated", user_id=str(user.id), symbol=ev.symbol, kind=kind, attention=ev.attention)
    return bool(inserted)
