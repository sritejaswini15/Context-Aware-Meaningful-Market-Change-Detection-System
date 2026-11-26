from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Float, ForeignKey, Index, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BigId, Base, JSONType, TimestampMixin, UTCDateTime, new_uuid, utcnow


class SignalScore(TimestampMixin, Base):
    """One deterministic evaluation of a symbol for a user. Fully auditable:
    `inputs` holds every fact used, `factors` every point awarded."""

    __tablename__ = "signal_scores"
    __table_args__ = (Index("ix_signal_scores_user_symbol_time", "user_id", "symbol", "created_at"),)

    id: Mapped[int] = mapped_column(BigId, primary_key=True, autoincrement=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    symbol: Mapped[str] = mapped_column(ForeignKey("stocks.symbol"))
    baseline_id: Mapped[int] = mapped_column(ForeignKey("checkpoint_baselines.id", ondelete="CASCADE"), index=True)
    snapshot_id: Mapped[int] = mapped_column(ForeignKey("market_snapshots.id", ondelete="CASCADE"))
    score: Mapped[int] = mapped_column(Integer)
    attention: Mapped[str] = mapped_column(String(8))  # LOW | MEDIUM | HIGH
    movement_type: Mapped[str] = mapped_column(String(20))  # STOCK_SPECIFIC | SECTOR_WIDE | MARKET_WIDE | QUIET
    confidence: Mapped[float] = mapped_column(Float)
    confidence_level: Mapped[str] = mapped_column(String(8))
    headline: Mapped[str] = mapped_column(String(400))
    factors: Mapped[list] = mapped_column(JSONType)
    inputs: Mapped[dict] = mapped_column(JSONType)
    caveats: Mapped[list] = mapped_column(JSONType, default=list)
    engine_version: Mapped[str] = mapped_column(String(16))
    dedupe_key: Mapped[str] = mapped_column(String(64), unique=True)


class ChangeEvent(Base):
    """A meaningful change surfaced to a user.

    Lifecycle: state NEW -> SEEN -> ACKNOWLEDGED. status ACTIVE while it is still
    meaningful against the user's current baseline, RESOLVED if it faded, and
    ARCHIVED once the user checkpoints past it.
    """

    __tablename__ = "change_events"
    __table_args__ = (
        Index("ix_change_events_user_state", "user_id", "status", "state"),
        Index("ix_change_events_user_time", "user_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_uuid)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    symbol: Mapped[str] = mapped_column(ForeignKey("stocks.symbol"))
    baseline_id: Mapped[int] = mapped_column(ForeignKey("checkpoint_baselines.id", ondelete="CASCADE"))
    first_signal_id: Mapped[int] = mapped_column(ForeignKey("signal_scores.id", ondelete="CASCADE"))
    latest_signal_id: Mapped[int] = mapped_column(ForeignKey("signal_scores.id", ondelete="CASCADE"))
    previous_event_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("change_events.id", ondelete="SET NULL"))
    direction: Mapped[str] = mapped_column(String(4))  # UP | DOWN
    generation: Mapped[int] = mapped_column(Integer, default=1)
    attention: Mapped[str] = mapped_column(String(8))
    peak_attention: Mapped[str] = mapped_column(String(8))
    score: Mapped[int] = mapped_column(Integer)
    movement_type: Mapped[str] = mapped_column(String(20))
    change_pct: Mapped[float] = mapped_column(Float)
    day_change_pct: Mapped[float | None] = mapped_column(Float)
    sector_change_pct: Mapped[float | None] = mapped_column(Float)
    market_change_pct: Mapped[float | None] = mapped_column(Float)
    volume_ratio: Mapped[float | None] = mapped_column(Float)
    confidence: Mapped[float] = mapped_column(Float)
    data_status: Mapped[str] = mapped_column(String(16))
    headline: Mapped[str] = mapped_column(String(400))
    state: Mapped[str] = mapped_column(String(16), default="NEW")
    status: Mapped[str] = mapped_column(String(16), default="ACTIVE")
    seen_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    acknowledged_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    ack_change_pct: Mapped[float | None] = mapped_column(Float)
    dedupe_key: Mapped[str] = mapped_column(String(160), unique=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, onupdate=utcnow)


class SignalExplanation(TimestampMixin, Base):
    __tablename__ = "signal_explanations"

    id: Mapped[int] = mapped_column(BigId, primary_key=True, autoincrement=True)
    signal_score_id: Mapped[int] = mapped_column(ForeignKey("signal_scores.id", ondelete="CASCADE"), unique=True)
    change_event_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("change_events.id", ondelete="CASCADE"), index=True)
    source: Mapped[str] = mapped_column(String(16))  # AI | FALLBACK
    provider: Mapped[str | None] = mapped_column(String(40))
    model: Mapped[str | None] = mapped_column(String(80))
    summary: Mapped[str] = mapped_column(Text)
    why_it_matters: Mapped[str] = mapped_column(Text)
    key_factors: Mapped[list] = mapped_column(JSONType)
    attention: Mapped[str] = mapped_column(String(8))
    confidence: Mapped[str] = mapped_column(String(8))
    attempts: Mapped[int] = mapped_column(Integer, default=1)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    error: Mapped[str | None] = mapped_column(Text)
    prompt_version: Mapped[str] = mapped_column(String(16))


class NotificationEvent(TimestampMixin, Base):
    __tablename__ = "notification_events"
    __table_args__ = (Index("ix_notification_events_user_time", "user_id", "created_at"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_uuid)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    change_event_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("change_events.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(String(24))  # MEANINGFUL_CHANGE | ESCALATION | DATA_QUALITY
    channel: Mapped[str] = mapped_column(String(16), default="IN_APP")
    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text)
    attention: Mapped[str | None] = mapped_column(String(8))
    symbol: Mapped[str | None] = mapped_column(String(16))
    read_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    dedupe_key: Mapped[str] = mapped_column(String(160), unique=True)
