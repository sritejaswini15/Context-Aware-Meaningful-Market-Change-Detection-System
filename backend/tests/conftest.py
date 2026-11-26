import os

os.environ.update(
    {
        "APP_ENV": "test",
        "DATABASE_URL": "sqlite://",
        "MARKET_PROVIDERS": "mock,mock-reference",
        "DEMO_MODE": "true",
        "SCHEDULER_MODE": "off",
        "AI_PROVIDER": "none",
        "LOG_JSON": "false",
        "LOG_LEVEL": "WARNING",
    }
)

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from app.core import db as dbmod  # noqa: E402
from app.models import Base  # noqa: E402
from app.workers.queue import JobQueue, set_queue  # noqa: E402


class RecordingQueue(JobQueue):
    backend = "test"

    def __init__(self):
        self.jobs = []

    def enqueue(self, job_type, payload=None, job_id=None):
        self.jobs.append((job_type, payload, job_id))
        return job_id or "x"


@pytest.fixture()
def engine():
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)

    from sqlalchemy import event

    @event.listens_for(eng, "connect")
    def _fk(conn, _):
        conn.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(eng)
    dbmod.set_engine(eng)
    from app.services.demo import state

    state.reset_cache()
    yield eng
    eng.dispose()


@pytest.fixture()
def queue():
    q = RecordingQueue()
    set_queue(q)
    yield q
    set_queue(None)


@pytest.fixture()
def db(engine, queue):
    s = dbmod.SessionLocal()
    from app.services.market_data.ingestion import bootstrap_reference_data

    bootstrap_reference_data(s)
    s.commit()
    yield s
    s.close()


@pytest.fixture()
def client(db):
    from app.main import app

    with TestClient(app) as c:
        yield c


def signup(client, email="a@example.com"):
    r = client.post("/api/auth/signup", json={"email": email, "password": "password123"})
    assert r.status_code == 200, r.text
    return r
