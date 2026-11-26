"""Market ingestion: INGEST -> VALIDATE -> NORMALIZE -> RESOLVE -> STORE CURRENT STATE.

Idempotent by construction:
* raw quotes are keyed by provider + symbol + market timestamp + price;
* a snapshot row is only written when the resolved state actually changes;
* history and events are keyed by (symbol, date) / provider event id.
"""

from __future__ import annotations

import hashlib
import logging
import statistics
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import insert_ignore
from app.core.logging import log_event
from app.models import (
    AppState,
    DataConflict,
    DataSource,
    MarketEvent,
    MarketHistory,
    MarketQuote,
    MarketSnapshot,
    Stock,
)
from app.providers.market.base import (
    CapabilityUnavailable,
    MarketDataProvider,
    ProviderError,
    ProviderQuote,
    SymbolNotFound,
    with_retry,
)
from app.providers.market.registry import get_market_providers
from app.providers.market.universe import BENCHMARK_SYMBOLS, MARKET_BENCHMARK, UNIVERSE
from app.services.market_data.quality import InvalidObservation, resolve_quotes, validate_quote
from app.utils.market_hours import session_fraction

log = logging.getLogger(__name__)


def _key(*parts: object) -> str:
    return hashlib.sha256("|".join(str(p) for p in parts).encode()).hexdigest()[:48]


@dataclass
class IngestReport:
    requested: int = 0
    updated: list[str] = field(default_factory=list)
    unchanged: list[str] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)
    conflicts: list[str] = field(default_factory=list)
    rejected: list[str] = field(default_factory=list)
    provider_errors: dict[str, str] = field(default_factory=dict)


def record_source(db: Session, provider: MarketDataProvider, ok: bool, error: str | None = None, now: datetime | None = None) -> DataSource:
    now = now or datetime.now(UTC)
    src = db.get(DataSource, provider.name)
    if src is None:
        src = DataSource(name=provider.name, kind="market", reliability=provider.reliability, is_realtime=provider.is_realtime)
        db.add(src)
    src.reliability = provider.reliability
    if ok:
        src.status, src.consecutive_failures, src.last_success_at = "HEALTHY", 0, now
    else:
        src.consecutive_failures = (src.consecutive_failures or 0) + 1
        src.status = "DOWN" if src.consecutive_failures >= 2 else "DEGRADED"
        src.last_failure_at, src.last_error = now, (error or "")[:500]
    return src


class IngestionService:
    def __init__(self, db: Session, providers: Sequence[MarketDataProvider] | None = None, now: datetime | None = None):
        self.db = db
        self.providers = list(providers or get_market_providers())
        self.settings = get_settings()
        self._now = now

    @property
    def now(self) -> datetime:
        return self._now or datetime.now(UTC)

    # ------------------------------------------------------------------ stocks
    def ensure_stock(self, symbol: str, bootstrap: bool = True) -> Stock | None:
        symbol = symbol.upper().strip()
        stock = self.db.get(Stock, symbol)
        if stock is not None:
            return stock
        profile = None
        for p in self.providers:
            try:
                profile = with_retry(lambda p=p: p.get_profile(symbol), retries=1)
                break
            except SymbolNotFound:
                continue
            except ProviderError as exc:
                log_event("provider.profile_failed", logging.WARNING, provider=p.name, symbol=symbol, error=str(exc))
        if profile is None:
            return None
        stock = Stock(
            symbol=symbol,
            name=profile.name,
            exchange=profile.exchange,
            market=profile.market,
            currency=profile.currency,
            kind=profile.kind,
            sector=profile.sector,
            industry=profile.industry,
            sector_benchmark=profile.sector_benchmark,
        )
        self.db.add(stock)
        self.db.flush()
        if bootstrap:
            self.load_history(symbol)
        return stock

    def seed_universe(self) -> int:
        """Reference data for offline search + benchmarks. Safe to run repeatedly."""
        existing = set(self.db.scalars(select(Stock.symbol)))
        added = 0
        for inst in UNIVERSE.values():
            if inst.symbol in existing:
                continue
            self.db.add(
                Stock(
                    symbol=inst.symbol,
                    name=inst.name,
                    exchange=inst.exchange,
                    kind=inst.kind,
                    sector=inst.sector,
                    sector_benchmark=inst.benchmark,
                )
            )
            added += 1
        self.db.flush()
        return added

    # ------------------------------------------------------------------ history
    def load_history(self, symbol: str, days: int = 90) -> int:
        bars = []
        used = None
        for p in self.providers:
            try:
                bars = with_retry(lambda p=p: p.get_historical_prices(symbol, days), retries=1)
                used = p.name
                if bars:
                    break
            except (CapabilityUnavailable, SymbolNotFound):
                continue
            except ProviderError as exc:
                log_event("provider.history_failed", logging.WARNING, provider=p.name, symbol=symbol, error=str(exc))
        rows = [
            {"symbol": symbol, "date": b.date, "open": b.open, "high": b.high, "low": b.low, "close": b.close, "volume": b.volume, "provider": used}
            for b in bars
        ]
        inserted = insert_ignore(self.db, MarketHistory, rows, ["symbol", "date"])
        self.update_stats(symbol)
        return inserted

    def update_stats(self, symbol: str) -> None:
        stock = self.db.get(Stock, symbol)
        if stock is None:
            return
        bars = list(
            self.db.scalars(select(MarketHistory).where(MarketHistory.symbol == symbol).order_by(MarketHistory.date.desc()).limit(21))
        )[::-1]
        closes = [b.close for b in bars if b.close]
        rets = [closes[i] / closes[i - 1] - 1 for i in range(1, len(closes))]
        vols = [b.volume for b in bars[-20:] if b.volume]
        stock.daily_volatility_pct = round(statistics.stdev(rets) * 100, 4) if len(rets) >= 10 else None
        stock.avg_volume_20d = float(sum(vols) / len(vols)) if len(vols) >= 10 else None
        stock.stats_updated_at = self.now

    # ------------------------------------------------------------------ events
    def refresh_events(self, symbols: Sequence[str], lookback: timedelta = timedelta(days=14)) -> int:
        since = self.now - lookback
        rows = []
        for symbol in symbols:
            for p in self.providers:
                try:
                    events = with_retry(lambda p=p: p.get_events(symbol, since), retries=1)
                except (CapabilityUnavailable, SymbolNotFound):
                    continue
                except ProviderError as exc:
                    log_event("provider.events_failed", logging.WARNING, provider=p.name, symbol=symbol, error=str(exc))
                    continue
                for e in events:
                    rows.append(
                        {
                            "symbol": symbol,
                            "event_type": e.event_type,
                            "headline": e.headline,
                            "summary": e.summary,
                            "source": e.source,
                            "url": e.url,
                            "event_time": e.event_time,
                            "significance": e.significance,
                            "provider": p.name,
                            "dedupe_key": _key(p.name, e.external_id),
                            "created_at": self.now,
                        }
                    )
                break  # first provider that answers is authoritative for events
        return insert_ignore(self.db, MarketEvent, rows, ["dedupe_key"])

    # ------------------------------------------------------------------ quotes
    def tracked_symbols(self) -> list[str]:
        from app.models import WatchlistItem

        watched = set(self.db.scalars(select(WatchlistItem.symbol).distinct()))
        benchmarks = set(BENCHMARK_SYMBOLS)
        for stock in self.db.scalars(select(Stock).where(Stock.symbol.in_(watched))):
            if stock.sector_benchmark:
                benchmarks.add(stock.sector_benchmark)
        return sorted(watched | benchmarks)

    def refresh(self, symbols: Sequence[str] | None = None, replace_state: bool = False) -> IngestReport:
        symbols = [s.upper() for s in (symbols or self.tracked_symbols())]
        report = IngestReport(requested=len(symbols))
        now = self.now
        stocks = {s.symbol: s for s in self.db.scalars(select(Stock).where(Stock.symbol.in_(symbols)))}
        for sym in symbols:
            if sym not in stocks:
                st = self.ensure_stock(sym)
                if st is not None:
                    stocks[sym] = st
        symbols = [s for s in symbols if s in stocks]

        observations: dict[str, list[ProviderQuote]] = {s: [] for s in symbols}
        for p in self.providers:
            try:
                results = with_retry(lambda p=p: p.get_quotes(symbols), retries=self.settings.provider_max_retries)
            except ProviderError as exc:
                report.provider_errors[p.name] = str(exc)
                record_source(self.db, p, ok=False, error=str(exc), now=now)
                log_event("market.provider_failure", logging.WARNING, provider=p.name, error=str(exc))
                continue
            record_source(self.db, p, ok=True, now=now)
            for sym, res in results.items():
                if isinstance(res, ProviderError):
                    continue
                try:
                    observations[sym].append(validate_quote(res, now))
                except InvalidObservation as exc:
                    report.rejected.append(sym)
                    log_event("market.observation_rejected", logging.WARNING, provider=p.name, symbol=sym, reason=str(exc))

        self.db.flush()  # data_sources rows must exist before quotes reference them
        raw_rows = []
        for sym, quotes in observations.items():
            for q in quotes:
                raw_rows.append(
                    {
                        "symbol": sym,
                        "provider": q.provider,
                        "price": q.price,
                        "prev_close": q.prev_close,
                        "open": q.open,
                        "high": q.high,
                        "low": q.low,
                        "volume": q.volume,
                        "currency": q.currency,
                        "market_timestamp": q.market_timestamp,
                        "received_timestamp": now,
                        "dedupe_key": _key(q.provider, sym, q.market_timestamp.isoformat(), q.price),
                    }
                )
        insert_ignore(self.db, MarketQuote, raw_rows, ["dedupe_key"])

        reliability = {p.name: p.reliability for p in self.providers}
        for sym in symbols:
            quotes = observations[sym]
            if not quotes:
                report.failed.append(sym)
                continue
            res = resolve_quotes(quotes, reliability, self.settings.conflict_tolerance_pct, now)
            stock = stocks[sym]
            changed = self._store_snapshot(stock, res, now, replace_state)
            (report.updated if changed else report.unchanged).append(sym)
            if res.conflicted:
                report.conflicts.append(sym)

        self._set_state("market.last_ingest", {"at": now.isoformat(), "updated": len(report.updated), "failed": len(report.failed)})
        if report.updated:
            self._set_state("market.last_change", {"at": now.isoformat()})
        log_event(
            "market.ingested",
            requested=report.requested,
            updated=len(report.updated),
            unchanged=len(report.unchanged),
            failed=len(report.failed),
            conflicts=report.conflicts,
            provider_errors=report.provider_errors,
        )
        if report.failed and not report.updated and not report.unchanged:
            log_event("market.all_providers_failed", logging.ERROR, symbols=len(report.failed))
        return report

    def _store_snapshot(self, stock: Stock, res, now: datetime, replace_state: bool) -> bool:
        q = res.chosen
        current = self.db.get(MarketSnapshot, stock.latest_snapshot_id) if stock.latest_snapshot_id else None
        if current is not None and q.market_timestamp < current.market_timestamp and not replace_state:
            log_event("market.out_of_order_ignored", logging.INFO, symbol=stock.symbol, provider=q.provider)
            return False
        volume_ratio = None
        if res.volume is not None and stock.avg_volume_20d:
            expected = stock.avg_volume_20d * session_fraction(q.market_timestamp)
            volume_ratio = round(res.volume / expected, 3) if expected > 0 else None
        day_change = round((q.price / q.prev_close - 1) * 100, 4) if q.prev_close else None
        if (
            current is not None
            and abs(current.price - q.price) < 1e-9
            and current.is_conflicted == res.conflicted
            and current.primary_provider == q.provider
            and current.provider_realtime == q.is_realtime
            and (current.volume_ratio is None) == (volume_ratio is None)
            and abs((current.volume_ratio or 0) - (volume_ratio or 0)) < 0.05
        ):
            current.market_timestamp = q.market_timestamp if replace_state else max(current.market_timestamp, q.market_timestamp)
            current.last_confirmed_at = now
            current.volume = res.volume
            current.sources_count = res.sources
            return False
        snap = MarketSnapshot(
            symbol=stock.symbol,
            price=q.price,
            prev_close=q.prev_close,
            day_change_pct=day_change,
            volume=res.volume,
            volume_ratio=volume_ratio,
            currency=q.currency,
            primary_provider=q.provider,
            provider_realtime=q.is_realtime,
            sources_count=res.sources,
            is_conflicted=res.conflicted,
            conflict_spread_pct=res.spread_pct if res.conflicted else None,
            market_timestamp=q.market_timestamp,
            first_seen_at=now,
            last_confirmed_at=now,
        )
        self.db.add(snap)
        self.db.flush()
        stock.latest_snapshot_id = snap.id
        if res.conflicted:
            insert_ignore(
                self.db,
                DataConflict,
                [
                    {
                        "symbol": stock.symbol,
                        "detected_at": now,
                        "observations": res.observations,
                        "chosen_provider": q.provider,
                        "chosen_price": q.price,
                        "spread_pct": res.spread_pct,
                        "tolerance_pct": self.settings.conflict_tolerance_pct,
                        "resolution": res.reason,
                        "snapshot_id": snap.id,
                        "dedupe_key": _key("conflict", snap.id),
                    }
                ],
                ["dedupe_key"],
            )
            log_event("market.data_conflict", logging.WARNING, symbol=stock.symbol, spread_pct=res.spread_pct, chosen=q.provider)
        return True

    def _set_state(self, key: str, value: dict) -> None:
        row = self.db.get(AppState, key)
        if row is None:
            self.db.add(AppState(key=key, value=value))
        else:
            row.value = value


def bootstrap_reference_data(db: Session) -> None:
    """Seed reference instruments and load benchmark history/stats once."""
    svc = IngestionService(db)
    svc.seed_universe()
    for sym in BENCHMARK_SYMBOLS:
        stock = db.get(Stock, sym)
        if stock is not None and stock.stats_updated_at is None:
            svc.load_history(sym)
    db.flush()


__all__ = ["IngestionService", "IngestReport", "MARKET_BENCHMARK", "bootstrap_reference_data", "record_source"]
