"""Job handlers. Every handler is idempotent and safe to retry."""

from __future__ import annotations

import logging
import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError

from app.core.cache import get_cache
from app.core.config import get_settings
from app.core.db import session_scope
from app.core.logging import log_event
from app.models import AppState, MarketQuote, NotificationEvent, ProcessedJob, Stock, User, Watchlist, WatchlistItem
from app.workers.queue import enqueue_after_commit

Handler = Callable[[dict[str, Any]], None]
HANDLERS: dict[str, Handler] = {}
# Jobs whose effects must happen exactly once per message id.
ONCE_ONLY = {"ai.explain", "signals.evaluate", "stock.bootstrap"}


def job(name: str):
    def deco(fn: Handler) -> Handler:
        HANDLERS[name] = fn
        return fn

    return deco


def handle_message(message: dict[str, Any]) -> None:
    job_type = message.get("type")
    job_id = str(message.get("id") or uuid.uuid4())
    handler = HANDLERS.get(job_type or "")
    if handler is None:
        log_event("job.unknown", logging.WARNING, job_type=job_type)
        return
    if job_type in ONCE_ONLY:
        with session_scope() as db:
            if db.get(ProcessedJob, job_id) is not None:
                log_event("job.duplicate_skipped", job_type=job_type, job_id=job_id)
                return
    handler(message.get("payload") or {})
    if job_type in ONCE_ONLY:
        try:
            with session_scope() as db:
                db.add(ProcessedJob(job_id=job_id, job_type=job_type))
        except IntegrityError:
            pass


def heartbeat(mode: str) -> None:
    with session_scope() as db:
        row = db.get(AppState, "worker.heartbeat")
        value = {"at": datetime.now(UTC).isoformat(), "mode": mode}
        if row is None:
            db.add(AppState(key="worker.heartbeat", value=value))
        else:
            row.value = value


# --------------------------------------------------------------------------- market
@job("market.refresh")
def market_refresh(payload: dict[str, Any]) -> None:
    from app.services.market_data.ingestion import IngestionService

    with get_cache().lock("market.refresh", ttl=120) as acquired:
        if not acquired:
            log_event("market.refresh_skipped_locked")
            return
        with session_scope() as db:
            report = IngestionService(db).refresh(payload.get("symbols"), replace_state=bool(payload.get("replace_state")))
            if report.updated or payload.get("force_evaluate"):
                schedule_evaluations(db, report.updated)


def schedule_evaluations(db, changed_symbols: list[str]) -> int:
    """Fan out signal evaluation to active users affected by the changed symbols."""
    from app.providers.market.universe import BENCHMARK_SYMBOLS

    settings = get_settings()
    active_since = datetime.now(UTC) - timedelta(days=settings.active_user_days)
    q = select(Watchlist.user_id).join(WatchlistItem).join(User, User.id == Watchlist.user_id).where(
        (User.last_seen_at.is_(None)) | (User.last_seen_at >= active_since)
    )
    if not set(changed_symbols) & set(BENCHMARK_SYMBOLS):
        # Benchmark moves affect everyone's context; otherwise only holders of the symbol.
        q = q.where(WatchlistItem.symbol.in_(changed_symbols))
    user_ids = sorted({str(u) for u in db.scalars(q.distinct())})
    stamp = datetime.now(UTC).strftime("%Y%m%d%H%M%S%f")
    for i in range(0, len(user_ids), 50):
        chunk = user_ids[i : i + 50]
        enqueue_after_commit(db, "signals.evaluate", {"user_ids": chunk}, job_id=f"signals:{stamp}:{i}")
    return len(user_ids)


@job("signals.evaluate")
def signals_evaluate(payload: dict[str, Any]) -> None:
    from app.services.change_detection.detector import ChangeDetectionService

    for uid in payload.get("user_ids", []):
        try:
            with session_scope() as db:
                user = db.get(User, uuid.UUID(uid))
                if user is not None:
                    ChangeDetectionService(db).evaluate_user(user)
        except Exception as exc:  # one user's failure must not block others
            log_event("signals.evaluate_failed", logging.ERROR, user_id=uid, error=str(exc))


@job("ai.explain")
def ai_explain(payload: dict[str, Any]) -> None:
    from app.services.ai.explainer import explain_signal

    with session_scope() as db:
        explain_signal(db, int(payload["signal_score_id"]), payload.get("change_event_id"))


@job("stock.bootstrap")
def stock_bootstrap(payload: dict[str, Any]) -> None:
    from app.services.market_data.ingestion import IngestionService

    with session_scope() as db:
        svc = IngestionService(db)
        sym = payload["symbol"]
        stock = db.get(Stock, sym)
        if stock is None:
            return
        if stock.stats_updated_at is None:
            svc.load_history(sym)
        svc.refresh_events([sym])


@job("events.refresh")
def events_refresh(payload: dict[str, Any]) -> None:
    from app.services.market_data.ingestion import IngestionService

    with session_scope() as db:
        svc = IngestionService(db)
        symbols = [s for s in svc.tracked_symbols() if (db.get(Stock, s) or Stock(kind="X")).kind == "EQUITY"]
        svc.refresh_events(symbols, lookback=timedelta(days=3))


@job("market.daily")
def market_daily(payload: dict[str, Any]) -> None:
    from app.services.market_data.ingestion import IngestionService

    with session_scope() as db:
        svc = IngestionService(db)
        for sym in svc.tracked_symbols():
            svc.load_history(sym, days=30)


@job("system.health_check")
def system_health_check(payload: dict[str, Any]) -> None:
    from app.services.system_health.service import health_report, record_component

    with session_scope() as db:
        report = health_report(db)
        for c in report["components"]:
            if c["key"] != "ai":
                record_component(db, c["key"], c["status"], c["detail"])
        log_event("system.health", status=report["status"])


@job("maintenance.cleanup")
def maintenance_cleanup(payload: dict[str, Any]) -> None:
    now = datetime.now(UTC)
    with session_scope() as db:
        q = db.execute(delete(MarketQuote).where(MarketQuote.received_timestamp < now - timedelta(days=3))).rowcount
        n = db.execute(delete(NotificationEvent).where(NotificationEvent.read_at.is_not(None), NotificationEvent.created_at < now - timedelta(days=90))).rowcount
        j = db.execute(delete(ProcessedJob).where(ProcessedJob.processed_at < now - timedelta(days=7))).rowcount
        log_event("maintenance.cleanup", quotes=q, notifications=n, jobs=j)
