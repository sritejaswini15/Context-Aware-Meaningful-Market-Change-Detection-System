"""Component health: what is working, what is degraded, and what Knoww does about it."""

from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.core.cache import get_cache
from app.core.config import get_settings
from app.models import AppState, ChangeEvent, DataConflict, DataSource, SignalScore, SystemHealth
from app.providers.ai.registry import ai_configured, get_ai_provider
from app.workers.queue import get_queue


def record_component(db: Session, component: str, status: str, detail: str, success: bool = False, meta: dict | None = None) -> None:
    now = datetime.now(UTC)
    row = db.get(SystemHealth, component)
    if row is None:
        row = SystemHealth(component=component, status=status, detail=detail, meta=meta or {}, checked_at=now)
        db.add(row)
    row.status, row.detail, row.checked_at = status, detail, now
    if meta is not None:
        row.meta = meta
    if success or status == "HEALTHY":
        row.last_success_at = now


def _state(db: Session, key: str) -> dict:
    row = db.get(AppState, key)
    return row.value if row else {}


def health_report(db: Session) -> dict:
    s = get_settings()
    now = datetime.now(UTC)
    components: list[dict] = []

    # Database ------------------------------------------------------------
    t0 = time.monotonic()
    db.execute(text("SELECT 1"))
    components.append({"key": "database", "name": "Database", "status": "HEALTHY", "detail": f"PostgreSQL responding in {int((time.monotonic() - t0) * 1000)} ms"})

    # Market data ----------------------------------------------------------
    sources = list(db.scalars(select(DataSource).where(DataSource.kind == "market").order_by(DataSource.name)))
    last_ingest = _state(db, "market.last_ingest")
    last_at = datetime.fromisoformat(last_ingest["at"]) if last_ingest.get("at") else None
    down = [x.name for x in sources if x.status == "DOWN"]
    healthy = [x.name for x in sources if x.status == "HEALTHY"]
    if not sources or last_at is None:
        md_status, md_detail = "DEGRADED", "No market data ingested yet"
    elif not healthy:
        md_status, md_detail = "DOWN", "All providers failing; showing last-known prices"
    elif down:
        md_status, md_detail = "DEGRADED", f"{', '.join(down)} unavailable; serving from fallback ({', '.join(healthy)})"
    elif last_at < now - timedelta(seconds=s.market_refresh_seconds * 5):
        md_status, md_detail = "DEGRADED", "Market refresh is behind schedule"
    else:
        md_status, md_detail = "HEALTHY", f"{len(healthy)} provider(s) healthy"
    components.append({"key": "market_data", "name": "Market Data", "status": md_status, "detail": md_detail})

    # Signal engine --------------------------------------------------------
    last_signal = db.scalar(select(func.max(SignalScore.created_at)))
    components.append(
        {
            "key": "signal_engine",
            "name": "Signal Engine",
            "status": "HEALTHY",
            "detail": f"Deterministic engine ready; last signal {last_signal.isoformat() if last_signal else 'not yet generated'}",
        }
    )

    # AI ------------------------------------------------------------------
    ai_row = db.get(SystemHealth, "ai")
    provider = get_ai_provider()
    if not ai_configured():
        ai = {"status": "NOT_CONFIGURED", "detail": "No AI provider configured; using deterministic explanations"}
    elif provider is not None and provider.__class__.__name__ == "SimulatedOutageProvider":
        ai = {"status": "DOWN", "detail": "Simulated outage; deterministic explanations in use"}
    elif ai_row is not None:
        ai = {"status": ai_row.status, "detail": ai_row.detail}
    else:
        ai = {"status": "HEALTHY", "detail": f"{provider.name} configured ({provider.model})"}
    components.append({"key": "ai", "name": "AI Explanations", **ai})

    # Redis ---------------------------------------------------------------
    ok, detail = get_cache().ping()
    components.append({"key": "redis", "name": "Redis Cache", "status": "HEALTHY" if ok else ("NOT_CONFIGURED" if not s.redis_url else "DEGRADED"), "detail": detail})

    # Queue ---------------------------------------------------------------
    q = get_queue()
    try:
        depth = q.depth()
        q_status = "HEALTHY"
        q_detail = ("Amazon SQS" if q.backend == "sqs" else "In-process queue (local mode)") + (f": {depth}" if depth else "")
        if depth.get("failed"):
            q_status = "DEGRADED"
    except Exception as exc:  # noqa: BLE001
        q_status, q_detail = "DOWN", f"Queue unreachable: {type(exc).__name__}"
    components.append({"key": "queue", "name": "Job Queue", "status": q_status, "detail": q_detail})

    # Worker / scheduler heartbeat ------------------------------------------
    hb = _state(db, "worker.heartbeat")
    hb_at = datetime.fromisoformat(hb["at"]) if hb.get("at") else None
    if hb_at and hb_at > now - timedelta(minutes=3):
        w_status, w_detail = "HEALTHY", f"Last heartbeat {int((now - hb_at).total_seconds())}s ago ({hb.get('mode', 'worker')})"
    else:
        w_status, w_detail = "DEGRADED", "No recent worker heartbeat"
    components.append({"key": "worker", "name": "Background Worker", "status": w_status, "detail": w_detail})

    # Product metrics. Attention precision needs labelled outcomes; until users can rate
    # signals, "reviewed" share and time-to-first-look are the measurable proxies.
    week = now - timedelta(days=7)
    events = list(db.execute(select(ChangeEvent.peak_attention, ChangeEvent.state, ChangeEvent.created_at, ChangeEvent.seen_at).where(ChangeEvent.created_at >= week)))
    high = [e for e in events if e.peak_attention == "HIGH"]
    seen_secs = sorted((e.seen_at - e.created_at).total_seconds() for e in events if e.seen_at)
    product = {
        "meaningful_changes_7d": len(events),
        "high_attention_7d": len(high),
        "high_reviewed_pct": round(100 * sum(1 for e in high if e.state == "ACKNOWLEDGED") / len(high), 1) if high else None,
        "median_seconds_to_first_look": int(seen_secs[len(seen_secs) // 2]) if seen_secs else None,
        "signals_evaluated_7d": db.scalar(select(func.count(SignalScore.id)).where(SignalScore.created_at >= week)) or 0,
    }

    conflicts_24h = db.scalar(select(func.count(DataConflict.id)).where(DataConflict.detected_at >= now - timedelta(hours=24))) or 0
    order = {"DOWN": 3, "DEGRADED": 2, "NOT_CONFIGURED": 1, "HEALTHY": 0}
    worst = max((c for c in components if c["key"] in ("database", "market_data", "signal_engine")), key=lambda c: order[c["status"]])
    return {
        "status": "HEALTHY" if order[worst["status"]] == 0 else worst["status"],
        "checked_at": now,
        "components": components,
        "providers": [
            {
                "name": x.name,
                "status": x.status,
                "reliability": x.reliability,
                "realtime": x.is_realtime,
                "last_success_at": x.last_success_at,
                "last_failure_at": x.last_failure_at,
                "consecutive_failures": x.consecutive_failures,
                "last_error": x.last_error,
                "simulated": x.name.startswith("mock"),
            }
            for x in sources
        ],
        "last_market_update": last_at,
        "conflicts_24h": conflicts_24h,
        "product_metrics": product,
        "environment": s.app_env,
        "version": s.app_version,
        "demo_mode": s.demo_mode,
    }
