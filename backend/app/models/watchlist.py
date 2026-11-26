from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, Boolean, ForeignKey, Index, Integer, String, UniqueConstraint, Uuid, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BigId, Base, Price, TimestampMixin, UTCDateTime, new_uuid, utcnow


class Watchlist(TimestampMixin, Base):
    __tablename__ = "watchlists"
    __table_args__ = (UniqueConstraint("user_id", "name", name="uq_watchlists_user_name"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_uuid)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(80))
    position: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, onupdate=utcnow)

    items: Mapped[list["WatchlistItem"]] = relationship(
        back_populates="watchlist", cascade="all, delete-orphan", order_by="WatchlistItem.added_at"
    )


class WatchlistItem(Base):
    __tablename__ = "watchlist_items"
    __table_args__ = (UniqueConstraint("watchlist_id", "symbol", name="uq_watchlist_items_symbol"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_uuid)
    watchlist_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("watchlists.id", ondelete="CASCADE"), index=True)
    symbol: Mapped[str] = mapped_column(ForeignKey("stocks.symbol"), index=True)
    priority: Mapped[str] = mapped_column(String(8), default="NORMAL")  # NORMAL | HIGH
    added_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)

    watchlist: Mapped[Watchlist] = relationship(back_populates="items")


class UserCheckpoint(TimestampMixin, Base):
    """A moment the user reviewed the market ("last checked")."""

    __tablename__ = "user_checkpoints"
    __table_args__ = (Index("ix_user_checkpoints_user_time", "user_id", "created_at"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_uuid)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    watchlist_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("watchlists.id", ondelete="SET NULL"))
    scope: Mapped[str] = mapped_column(String(16), default="ALL")  # ALL | WATCHLIST
    symbols_count: Mapped[int] = mapped_column(Integer, default=0)


class CheckpointBaseline(TimestampMixin, Base):
    """What the user last saw for one symbol, plus benchmark prices at that moment.

    Exactly one baseline per (user, symbol) is current. Benchmarks are stored
    so sector/market movement is measured over the *same* window as the stock.
    """

    __tablename__ = "checkpoint_baselines"
    __table_args__ = (
        Index(
            "uq_checkpoint_baselines_current",
            "user_id",
            "symbol",
            unique=True,
            postgresql_where=text("is_current"),
            sqlite_where=text("is_current = 1"),
        ),
    )

    id: Mapped[int] = mapped_column(BigId, primary_key=True, autoincrement=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    checkpoint_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("user_checkpoints.id", ondelete="SET NULL"))
    symbol: Mapped[str] = mapped_column(ForeignKey("stocks.symbol"))
    reason: Mapped[str] = mapped_column(String(16), default="CHECKPOINT")  # ADDED | CHECKPOINT
    price: Mapped[float] = mapped_column(Price)
    volume: Mapped[int | None] = mapped_column(BigInteger)
    market_timestamp: Mapped[datetime] = mapped_column(UTCDateTime())
    snapshot_id: Mapped[int | None] = mapped_column(ForeignKey("market_snapshots.id", ondelete="SET NULL"))
    sector_symbol: Mapped[str | None] = mapped_column(String(16))
    sector_price: Mapped[float | None] = mapped_column(Price)
    market_symbol: Mapped[str | None] = mapped_column(String(16))
    market_price: Mapped[float | None] = mapped_column(Price)
    baseline_status: Mapped[str] = mapped_column(String(16), default="FRESH")
    is_current: Mapped[bool] = mapped_column(Boolean, default=True)
    latest_signal_id: Mapped[int | None] = mapped_column(
        ForeignKey("signal_scores.id", use_alter=True, name="fk_baseline_latest_signal", ondelete="SET NULL")
    )
    superseded_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
