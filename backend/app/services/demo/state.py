"""Active demo scenario, stored in the database so API and workers agree."""

from __future__ import annotations

import threading
import time
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.core.db import SessionLocal
from app.models import AppState
from app.providers.market.scenarios import DEFAULT_SCENARIO, SCENARIOS

KEY = "demo.scenario"
_cache: tuple[float, tuple[str, datetime]] | None = None
_lock = threading.Lock()


def read_scenario(db: Session) -> tuple[str, datetime]:
    row = db.get(AppState, KEY)
    if row is None or row.value.get("key") not in SCENARIOS:
        return DEFAULT_SCENARIO, datetime(2026, 1, 1, tzinfo=UTC)
    return row.value["key"], datetime.fromisoformat(row.value["activated_at"])


def current_scenario() -> tuple[str, datetime]:
    """Cached for 1s: providers call this once per symbol."""
    global _cache
    with _lock:
        if _cache and time.monotonic() - _cache[0] < 1.0:
            return _cache[1]
    try:
        db = SessionLocal()
        try:
            value = read_scenario(db)
        finally:
            db.close()
    except Exception:
        value = (DEFAULT_SCENARIO, datetime(2026, 1, 1, tzinfo=UTC))
    with _lock:
        _cache = (time.monotonic(), value)
    return value


def set_scenario(db: Session, key: str) -> tuple[str, datetime]:
    global _cache
    if key not in SCENARIOS:
        raise ValueError(f"Unknown scenario {key}")
    now = datetime.now(UTC).replace(microsecond=0)
    row = db.get(AppState, KEY)
    value = {"key": key, "activated_at": now.isoformat()}
    if row is None:
        db.add(AppState(key=KEY, value=value))
    else:
        row.value = value
    db.flush()
    with _lock:
        _cache = (time.monotonic(), (key, now))
    return key, now


def reset_cache() -> None:
    global _cache
    with _lock:
        _cache = None
