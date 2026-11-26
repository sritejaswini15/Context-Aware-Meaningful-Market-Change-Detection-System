from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import BigInteger, Boolean, Date, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BigId, Base, JSONType, Price, TimestampMixin, UTCDateTime, utcnow


class Stock(TimestampMixin, Base):
    """Instrument reference data plus a pointer to the current market state."""

    __tablename__ = "stocks"

    symbol: Mapped[str] = mapped_column(String(16), primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    exchange: Mapped[str | None] = mapped_column(String(32))
    market: Mapped[str] = mapped_column(String(8), default="US")
    currency: Mapped[str] = mapped_column(String(8), default="USD")
    kind: Mapped[str] = mapped_column(String(16), default="EQUITY")  # EQUITY | SECTOR_ETF | INDEX_ETF
    sector: Mapped[str | None] = mapped_column(String(64))
    industry: Mapped[str | None] = mapped_column(String(120))
    sector_benchmark: Mapped[str | None] = mapped_column(String(16))  # e.g. XLK
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    avg_volume_20d: Mapped[float | None] = mapped_column(Float)
    daily_volatility_pct: Mapped[float | None] = mapped_column(Float)
    stats_updated_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    latest_snapshot_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("market_snapshots.id", use_alter=True, name="fk_stocks_latest_snapshot", ondelete="SET NULL")
    )
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, onupdate=utcnow)


class DataSource(Base):
    __tablename__ = "data_sources"

    name: Mapped[str] = mapped_column(String(40), primary_key=True)
    kind: Mapped[str] = mapped_column(String(16), default="market")  # market | ai
    reliability: Mapped[float] = mapped_column(Float, default=0.9)
    priority: Mapped[int] = mapped_column(Integer, default=0)
    is_realtime: Mapped[bool] = mapped_column(Boolean, default=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    status: Mapped[str] = mapped_column(String(16), default="UNKNOWN")  # HEALTHY | DEGRADED | DOWN | UNKNOWN
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0)
    last_success_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    last_failure_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    last_error: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, onupdate=utcnow)


class MarketQuote(Base):
    """Raw, validated observation from one provider. Idempotent on dedupe_key."""

    __tablename__ = "market_quotes"
    __table_args__ = (Index("ix_market_quotes_symbol_ts", "symbol", "market_timestamp"),)

    id: Mapped[int] = mapped_column(BigId, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(ForeignKey("stocks.symbol", ondelete="CASCADE"))
    provider: Mapped[str] = mapped_column(ForeignKey("data_sources.name"))
    price: Mapped[float] = mapped_column(Price)
    prev_close: Mapped[float | None] = mapped_column(Price)
    open: Mapped[float | None] = mapped_column(Price)
    high: Mapped[float | None] = mapped_column(Price)
    low: Mapped[float | None] = mapped_column(Price)
    volume: Mapped[int | None] = mapped_column(BigInteger)
    currency: Mapped[str] = mapped_column(String(8), default="USD")
    market_timestamp: Mapped[datetime] = mapped_column(UTCDateTime())
    received_timestamp: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    dedupe_key: Mapped[str] = mapped_column(String(64), unique=True)


class MarketSnapshot(Base):
    """Resolved market state for a symbol after validation and conflict resolution."""

    __tablename__ = "market_snapshots"
    __table_args__ = (Index("ix_market_snapshots_symbol_ts", "symbol", "market_timestamp"),)

    id: Mapped[int] = mapped_column(BigId, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(ForeignKey("stocks.symbol", ondelete="CASCADE"))
    price: Mapped[float] = mapped_column(Price)
    prev_close: Mapped[float | None] = mapped_column(Price)
    day_change_pct: Mapped[float | None] = mapped_column(Float)
    volume: Mapped[int | None] = mapped_column(BigInteger)
    volume_ratio: Mapped[float | None] = mapped_column(Float)
    currency: Mapped[str] = mapped_column(String(8), default="USD")
    primary_provider: Mapped[str] = mapped_column(String(40))
    provider_realtime: Mapped[bool] = mapped_column(Boolean, default=True)
    sources_count: Mapped[int] = mapped_column(Integer, default=1)
    is_conflicted: Mapped[bool] = mapped_column(Boolean, default=False)
    conflict_spread_pct: Mapped[float | None] = mapped_column(Float)
    market_timestamp: Mapped[datetime] = mapped_column(UTCDateTime())
    first_seen_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    last_confirmed_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)


class MarketHistory(Base):
    __tablename__ = "market_history"
    __table_args__ = (UniqueConstraint("symbol", "date", name="uq_market_history_symbol_date"),)

    id: Mapped[int] = mapped_column(BigId, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(ForeignKey("stocks.symbol", ondelete="CASCADE"), index=True)
    date: Mapped[date] = mapped_column(Date)
    open: Mapped[float | None] = mapped_column(Price)
    high: Mapped[float | None] = mapped_column(Price)
    low: Mapped[float | None] = mapped_column(Price)
    close: Mapped[float] = mapped_column(Price)
    volume: Mapped[int | None] = mapped_column(BigInteger)
    provider: Mapped[str] = mapped_column(String(40))


class MarketEvent(TimestampMixin, Base):
    __tablename__ = "market_events"
    __table_args__ = (Index("ix_market_events_symbol_time", "symbol", "event_time"),)

    id: Mapped[int] = mapped_column(BigId, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(ForeignKey("stocks.symbol", ondelete="CASCADE"))
    event_type: Mapped[str] = mapped_column(String(24))  # EARNINGS | GUIDANCE | REGULATORY | ANALYST | NEWS | DIVIDEND
    headline: Mapped[str] = mapped_column(String(400))
    summary: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str | None] = mapped_column(String(120))
    url: Mapped[str | None] = mapped_column(String(1000))
    event_time: Mapped[datetime] = mapped_column(UTCDateTime())
    significance: Mapped[float] = mapped_column(Float, default=0.4)
    provider: Mapped[str] = mapped_column(String(40))
    dedupe_key: Mapped[str] = mapped_column(String(64), unique=True)


class DataConflict(Base):
    __tablename__ = "data_conflicts"
    __table_args__ = (Index("ix_data_conflicts_symbol_time", "symbol", "detected_at"),)

    id: Mapped[int] = mapped_column(BigId, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(ForeignKey("stocks.symbol", ondelete="CASCADE"))
    detected_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    observations: Mapped[list] = mapped_column(JSONType)
    chosen_provider: Mapped[str] = mapped_column(String(40))
    chosen_price: Mapped[float] = mapped_column(Price)
    spread_pct: Mapped[float] = mapped_column(Float)
    tolerance_pct: Mapped[float] = mapped_column(Float)
    resolution: Mapped[str] = mapped_column(Text)
    snapshot_id: Mapped[int | None] = mapped_column(ForeignKey("market_snapshots.id", ondelete="SET NULL"))
    dedupe_key: Mapped[str] = mapped_column(String(64), unique=True)
