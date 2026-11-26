"""SQS worker: `python -m app.workers.main`.

Long-polls the queue, runs the handler, deletes the message on success.
Failures are left on the queue (visibility timeout -> redelivery); after
maxReceiveCount the redrive policy moves them to the dead-letter queue.
"""

from __future__ import annotations

import json
import logging
import signal
import time

from app.core.config import get_settings
from app.core.logging import configure_logging, log_event
from app.workers.jobs import handle_message, heartbeat

_running = True


def _stop(*_: object) -> None:
    global _running
    _running = False


def run() -> None:
    s = get_settings()
    configure_logging(s.log_level, s.log_json)
    if s.queue_backend != "sqs" or not s.sqs_queue_url:
        raise SystemExit("Worker requires QUEUE_BACKEND=sqs and SQS_QUEUE_URL (local mode runs jobs inside the API).")
    import boto3

    from app.workers.scheduler import start_local_scheduler

    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    client = boto3.client("sqs", region_name=s.aws_region, endpoint_url=s.aws_endpoint_url)
    start_local_scheduler(mode="worker")  # no-op unless SCHEDULER_MODE=local
    log_event("worker.started", queue=s.sqs_queue_url)
    last_beat = 0.0
    while _running:
        if time.monotonic() - last_beat > 30:
            try:
                heartbeat("sqs-worker")
            except Exception as exc:  # noqa: BLE001
                log_event("worker.heartbeat_failed", logging.WARNING, error=str(exc))
            last_beat = time.monotonic()
        resp = client.receive_message(QueueUrl=s.sqs_queue_url, MaxNumberOfMessages=10, WaitTimeSeconds=20, VisibilityTimeout=120)
        for msg in resp.get("Messages", []):
            try:
                body = json.loads(msg["Body"])
                body.setdefault("id", msg["MessageId"])
                handle_message(body)
                client.delete_message(QueueUrl=s.sqs_queue_url, ReceiptHandle=msg["ReceiptHandle"])
            except Exception as exc:  # noqa: BLE001
                log_event("worker.job_failed", logging.ERROR, message_id=msg.get("MessageId"), error=str(exc))
    log_event("worker.stopped")


if __name__ == "__main__":
    run()
