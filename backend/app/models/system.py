from __future__ import annotations

from datetime import datetime

from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, JSONType, UTCDateTime, utcnow


class SystemHealth(Base):
    __tablename__ = "system_health"

    component: Mapped[str] = mapped_column(String(40), primary_key=True)
    status: Mapped[str] = mapped_column(String(16))  # HEALTHY | DEGRADED | DOWN | NOT_CONFIGURED
    detail: Mapped[str | None] = mapped_column(Text)
    meta: Mapped[dict] = mapped_column(JSONType, default=dict)
    last_success_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    checked_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, onupdate=utcnow)


class AppState(Base):
    """Small cross-process key/value state (demo scenario, heartbeats)."""

    __tablename__ = "app_state"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[dict] = mapped_column(JSONType, default=dict)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, onupdate=utcnow)


class ProcessedJob(Base):
    """Idempotency ledger for at-least-once queue delivery."""

    __tablename__ = "processed_jobs"

    job_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    job_type: Mapped[str] = mapped_column(String(48))
    processed_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
