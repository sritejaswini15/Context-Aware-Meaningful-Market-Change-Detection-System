from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UTCDateTime, new_uuid, utcnow


class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_uuid)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    display_name: Mapped[str | None] = mapped_column(String(120))
    auth_provider: Mapped[str] = mapped_column(String(20), default="local")  # local | cognito
    external_id: Mapped[str | None] = mapped_column(String(128), unique=True)  # Cognito `sub`
    password_hash: Mapped[str | None] = mapped_column(String(255))
    onboarded_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    last_seen_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    # Set to NULL whenever inputs to the user's signals change (checkpoint,
    # preferences, watchlist edits) so the next read re-evaluates.
    last_evaluated_at: Mapped[datetime | None] = mapped_column(UTCDateTime())

    preferences: Mapped["UserPreferences"] = relationship(back_populates="user", uselist=False, cascade="all, delete-orphan")


class UserPreferences(Base):
    __tablename__ = "user_preferences"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    sensitivity: Mapped[str] = mapped_column(String(16), default="BALANCED")  # LOW | BALANCED | HIGH
    include_volume: Mapped[bool] = mapped_column(Boolean, default=True)
    include_market_context: Mapped[bool] = mapped_column(Boolean, default=True)
    include_events: Mapped[bool] = mapped_column(Boolean, default=True)
    notify_min_attention: Mapped[str] = mapped_column(String(16), default="HIGH")  # HIGH | MEDIUM
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, onupdate=utcnow)

    user: Mapped[User] = relationship(back_populates="preferences")
