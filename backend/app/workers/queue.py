"""Job queue abstraction: SQS in production, in-process threads locally.

Jobs are enqueued *after* the surrounding DB transaction commits
(`enqueue_after_commit`) so a worker never sees a job for data that was
rolled back or isn't visible yet.
"""

from __future__ import annotations

import json
import logging
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from sqlalchemy import event
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.logging import log_event

log = logging.getLogger(__name__)


class JobQueue:
    backend = "base"

    def enqueue(self, job_type: str, payload: dict[str, Any] | None = None, job_id: str | None = None) -> str:
        raise NotImplementedError

    def depth(self) -> dict[str, Any]:
        return {}


class InlineQueue(JobQueue):
    """Runs jobs on a small background thread pool (local development)."""

    backend = "inline"

    def __init__(self, workers: int = 2):
        self._pool = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="knoww-job")
        self._pending = 0
        self._lock = threading.Lock()
        self.failed = 0

    def enqueue(self, job_type: str, payload: dict[str, Any] | None = None, job_id: str | None = None) -> str:
        job_id = job_id or str(uuid.uuid4())
        message = {"id": job_id, "type": job_type, "payload": payload or {}}
        with self._lock:
            self._pending += 1
        self._pool.submit(self._run, message)
        return job_id

    def _run(self, message: dict[str, Any]) -> None:
        from app.workers.jobs import handle_message

        try:
            for attempt in range(3):  # retry like SQS redelivery would
                try:
                    handle_message(message)
                    return
                except Exception as exc:  # noqa: BLE001
                    log_event("job.failed", logging.WARNING, job_type=message["type"], attempt=attempt + 1, error=str(exc))
            self.failed += 1
        finally:
            with self._lock:
                self._pending -= 1

    def depth(self) -> dict[str, Any]:
        return {"pending": self._pending, "failed": self.failed}


class SqsQueue(JobQueue):
    backend = "sqs"

    def __init__(self, queue_url: str, region: str, endpoint_url: str | None = None):
        import boto3

        self.queue_url = queue_url
        self.client = boto3.client("sqs", region_name=region, endpoint_url=endpoint_url)

    def enqueue(self, job_type: str, payload: dict[str, Any] | None = None, job_id: str | None = None) -> str:
        job_id = job_id or str(uuid.uuid4())
        body = json.dumps({"id": job_id, "type": job_type, "payload": payload or {}})
        self.client.send_message(QueueUrl=self.queue_url, MessageBody=body)
        return job_id

    def depth(self) -> dict[str, Any]:
        attrs = self.client.get_queue_attributes(
            QueueUrl=self.queue_url,
            AttributeNames=["ApproximateNumberOfMessages", "ApproximateNumberOfMessagesNotVisible"],
        )["Attributes"]
        return {"visible": int(attrs.get("ApproximateNumberOfMessages", 0)), "in_flight": int(attrs.get("ApproximateNumberOfMessagesNotVisible", 0))}


_queue: JobQueue | None = None


def get_queue() -> JobQueue:
    global _queue
    if _queue is None:
        s = get_settings()
        if s.queue_backend == "sqs" and s.sqs_queue_url:
            _queue = SqsQueue(s.sqs_queue_url, s.aws_region, s.aws_endpoint_url)
        else:
            _queue = InlineQueue()
    return _queue


def set_queue(queue: JobQueue | None) -> None:
    global _queue
    _queue = queue


def enqueue_after_commit(db: Session, job_type: str, payload: dict[str, Any] | None = None, job_id: str | None = None) -> None:
    db.info.setdefault("pending_jobs", []).append((job_type, payload or {}, job_id))


@event.listens_for(Session, "after_commit")
def _dispatch_pending(session: Session) -> None:
    jobs = session.info.pop("pending_jobs", [])
    if not jobs:
        return
    queue = get_queue()
    for job_type, payload, job_id in jobs:
        try:
            queue.enqueue(job_type, payload, job_id)
        except Exception as exc:  # queue outage must not fail the user request
            log_event("queue.enqueue_failed", logging.ERROR, job_type=job_type, error=str(exc))


@event.listens_for(Session, "after_rollback")
def _drop_pending(session: Session) -> None:
    session.info.pop("pending_jobs", None)
