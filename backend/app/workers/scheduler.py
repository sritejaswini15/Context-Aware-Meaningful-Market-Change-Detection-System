"""Local scheduler. In AWS, EventBridge Scheduler sends the same messages to SQS
(see infra/terraform/modules/queue), and SCHEDULER_MODE=eventbridge disables this."""

from __future__ import annotations

import logging
import threading
import time

from app.core.config import get_settings
from app.core.logging import log_event
from app.workers.queue import get_queue

SCHEDULES = [
    # (job type, interval seconds or None for market_refresh_seconds, payload)
    ("market.refresh", None, {}),
    ("system.health_check", 120, {}),
    ("events.refresh", 1800, {}),
    ("market.daily", 6 * 3600, {}),
    ("maintenance.cleanup", 24 * 3600, {}),
]

_started = False


def _loop(mode: str) -> None:
    from app.workers.jobs import heartbeat

    s = get_settings()
    last: dict[str, float] = {}
    while True:
        now = time.monotonic()
        for job_type, interval, payload in SCHEDULES:
            every = interval or s.market_refresh_seconds
            if now - last.get(job_type, -1e9) >= every:
                last[job_type] = now
                try:
                    get_queue().enqueue(job_type, payload)
                except Exception as exc:  # noqa: BLE001
                    log_event("scheduler.enqueue_failed", logging.ERROR, job_type=job_type, error=str(exc))
        try:
            heartbeat(mode)
        except Exception as exc:  # noqa: BLE001
            log_event("scheduler.heartbeat_failed", logging.WARNING, error=str(exc))
        time.sleep(5)


def start_local_scheduler(mode: str = "api-inline") -> None:
    global _started
    if _started or get_settings().scheduler_mode != "local":
        return
    _started = True
    threading.Thread(target=_loop, args=(mode,), name="knoww-scheduler", daemon=True).start()
    log_event("scheduler.started", mode=mode)
