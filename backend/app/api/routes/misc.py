"""Market status, preferences, notifications, system health and demo controls."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import func, select, text, update
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.config import get_settings
from app.core.db import get_db
from app.core.errors import DomainError, NotFound
from app.core.logging import log_event
from app.models import NotificationEvent, User
from app.providers.market.scenarios import SCENARIOS
from app.schemas.api import MarketContextOut, NotificationListOut, NotificationOut, PreferencesOut, PreferencesPatch, ScenarioIn
from app.services.market_context.context import market_context
from app.services.preferences.service import get_preferences, update_preferences
from app.services.snapshots.checkpoints import CheckpointService
from app.services.system_health.service import health_report

market = APIRouter(prefix="/market", tags=["market"])


@market.get("/status", response_model=MarketContextOut)
def market_status(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    baselines = CheckpointService(db).current_baselines(user.id)
    return market_context(db, baselines)


prefs = APIRouter(prefix="/preferences", tags=["preferences"])


@prefs.get("", response_model=PreferencesOut)
def get_prefs(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    p = get_preferences(db, user)
    db.commit()
    return p


@prefs.patch("", response_model=PreferencesOut)
def patch_prefs(body: PreferencesPatch, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    p = update_preferences(db, user, body.model_dump(exclude_none=True))
    db.commit()
    log_event("preferences.updated", user_id=str(user.id), **body.model_dump(exclude_none=True))
    return p


notifications = APIRouter(prefix="/notifications", tags=["notifications"])


@notifications.get("", response_model=NotificationListOut)
def list_notifications(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    items = list(db.scalars(select(NotificationEvent).where(NotificationEvent.user_id == user.id).order_by(NotificationEvent.created_at.desc()).limit(50)))
    unread = db.scalar(select(func.count(NotificationEvent.id)).where(NotificationEvent.user_id == user.id, NotificationEvent.read_at.is_(None))) or 0
    return {"items": items, "unread": unread}


@notifications.post("/{notification_id}/read", response_model=NotificationOut)
def read_notification(notification_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    n = db.scalar(select(NotificationEvent).where(NotificationEvent.id == notification_id, NotificationEvent.user_id == user.id))
    if n is None:
        raise NotFound("Notification not found")
    n.read_at = n.read_at or datetime.now(UTC)
    db.commit()
    return n


@notifications.post("/read-all")
def read_all(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    count = db.execute(
        update(NotificationEvent).where(NotificationEvent.user_id == user.id, NotificationEvent.read_at.is_(None)).values(read_at=datetime.now(UTC))
    ).rowcount
    db.commit()
    return {"read": count}


system = APIRouter(tags=["system"])


@system.get("/system/health")
def system_health(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Component-level health for the System page."""
    return health_report(db)


@system.get("/health/live", include_in_schema=False)
def live():
    return {"status": "ok"}


@system.get("/health/ready", include_in_schema=False)
def ready(db: Session = Depends(get_db)):
    db.execute(text("SELECT 1"))
    return {"status": "ready"}


demo = APIRouter(prefix="/demo", tags=["demo"])


def _require_demo() -> None:
    s = get_settings()
    if not (s.demo_mode and s.uses_mock_market):
        raise NotFound("Demo mode is disabled")


@demo.get("/scenarios")
def scenarios(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    from app.services.demo.state import read_scenario

    s = get_settings()
    enabled = s.demo_mode and s.uses_mock_market
    active, activated = read_scenario(db) if enabled else (None, None)
    return {
        "enabled": enabled,
        "active": active,
        "activated_at": activated,
        "scenarios": [
            {"key": sc.key, "title": sc.title, "description": sc.description, "expectation": sc.expectation, "faults": sorted(sc.faults)}
            for sc in SCENARIOS.values()
        ],
    }


@demo.post("/scenario")
def set_scenario(body: ScenarioIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Switch the simulated market, ingest immediately, and re-evaluate."""
    _require_demo()
    if body.key not in SCENARIOS:
        raise DomainError("Unknown scenario", "unknown_scenario")
    from app.services.change_detection.detector import ChangeDetectionService
    from app.services.demo.state import set_scenario as store
    from app.services.market_data.ingestion import IngestionService
    from app.workers.jobs import schedule_evaluations

    store(db, body.key)
    db.commit()
    svc = IngestionService(db)
    report = svc.refresh(replace_state=True)
    svc.refresh_events([s for s in svc.tracked_symbols()], lookback=timedelta(days=14))
    schedule_evaluations(db, report.updated or svc.tracked_symbols())
    items = ChangeDetectionService(db).evaluate_user(user)
    db.commit()
    log_event("demo.scenario_set", scenario=body.key, user_id=str(user.id))
    meaningful = [s for s, it in items.items() if it.event is not None and it.event.status == "ACTIVE"]
    return {"active": body.key, "updated": len(report.updated), "provider_errors": report.provider_errors, "meaningful_symbols": meaningful}


@demo.post("/refresh")
def refresh_now(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Run one market ingestion cycle now (what the scheduler does every minute)."""
    _require_demo()
    from app.services.market_data.ingestion import IngestionService

    report = IngestionService(db).refresh()
    db.commit()
    return {"updated": len(report.updated), "unchanged": len(report.unchanged), "failed": len(report.failed), "provider_errors": report.provider_errors}
