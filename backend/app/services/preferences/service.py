from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import User, UserPreferences
from app.services.signal_engine.engine import Preferences


def get_preferences(db: Session, user: User) -> UserPreferences:
    prefs = db.get(UserPreferences, user.id)
    if prefs is None:
        prefs = UserPreferences(user_id=user.id)
        db.add(prefs)
        db.flush()
    return prefs


def engine_preferences(prefs: UserPreferences) -> Preferences:
    return Preferences(
        sensitivity=prefs.sensitivity,
        include_volume=prefs.include_volume,
        include_market_context=prefs.include_market_context,
        include_events=prefs.include_events,
    )


def update_preferences(db: Session, user: User, changes: dict) -> UserPreferences:
    prefs = get_preferences(db, user)
    for key, value in changes.items():
        if value is not None and hasattr(prefs, key):
            setattr(prefs, key, value)
    user.last_evaluated_at = None  # preferences change ranking -> re-evaluate
    db.flush()
    return prefs
