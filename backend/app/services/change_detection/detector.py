"""COMPARE WITH CHECKPOINT -> DETECT -> SCORE -> CONTEXT -> PERSONALIZE -> PRIORITIZE.

`ChangeDetectionService.evaluate_user` is deterministic and idempotent:
evaluating the same inputs twice writes nothing new. It is called by the
worker after every market ingestion and by read endpoints, so a user always
sees results that are consistent with the stored market state.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
import uuid
from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.cache import get_cache
from app.core.config import get_settings
from app.core.db import insert_ignore
from app.core.logging import log_event
from app.models import (
    ChangeEvent,
    CheckpointBaseline,
    DataSource,
    MarketEvent,
    MarketSnapshot,
    SignalScore,
    Stock,
    User,
    UserPreferences,
)
from app.providers.market.universe import MARKET_BENCHMARK
from app.services.market_data.quality import Freshness, classify_freshness
from app.services.preferences.service import engine_preferences, get_preferences
from app.services.signal_engine.engine import ENGINE_VERSION, EventFact, SignalInputs, SignalResult, evaluate
from app.services.snapshots.checkpoints import CheckpointService, latest_snapshots, user_symbols
from app.utils.market_hours import trading_days_between
from app.workers.queue import enqueue_after_commit

ATT_RANK = {"LOW": 0, "MEDIUM": 1, "HIGH": 2}
EVENT_LOOKBACK = timedelta(hours=12)


def pct(now_price: float | None, then_price: float | None) -> float | None:
    if not now_price or not then_price:
        return None
    return round((now_price / then_price - 1) * 100, 4)


@dataclass
class EvaluatedItem:
    symbol: str
    stock: Stock
    priority: str
    snapshot: MarketSnapshot | None = None
    baseline: CheckpointBaseline | None = None
    freshness: Freshness | None = None
    inputs: SignalInputs | None = None
    result: SignalResult | None = None
    signal: SignalScore | None = None
    event: ChangeEvent | None = None


class ChangeDetectionService:
    def __init__(self, db: Session, now: datetime | None = None):
        self.db = db
        self.now = now or datetime.now(UTC)
        self.simulated = get_settings().uses_mock_market

    # ------------------------------------------------------------------
    def evaluate_user(self, user: User) -> dict[str, EvaluatedItem]:
        cache = get_cache()
        deadline = time.monotonic() + 3
        while True:
            with cache.lock(f"evaluate:{user.id}", ttl=30) as acquired:
                if acquired or time.monotonic() > deadline:
                    return self._evaluate(user)
            time.sleep(0.05)

    def _evaluate(self, user: User) -> dict[str, EvaluatedItem]:
        db, now = self.db, self.now
        prefs_row = get_preferences(db, user)
        prefs = engine_preferences(prefs_row)
        sym_prio = user_symbols(db, user.id)
        if not sym_prio:
            user.last_evaluated_at = now
            return {}

        cps = CheckpointService(db, now)
        cps.ensure_baselines(user, sym_prio.keys())
        baselines = cps.current_baselines(user.id, sym_prio.keys())
        state = latest_snapshots(db, sym_prio.keys())
        bench_syms = {MARKET_BENCHMARK} | {b.sector_symbol for b in baselines.values() if b.sector_symbol}
        bench = latest_snapshots(db, bench_syms)
        sources = {s.name: s for s in db.scalars(select(DataSource))}

        events_by_sym: dict[str, list[MarketEvent]] = defaultdict(list)
        if baselines:
            since = min(b.created_at for b in baselines.values()) - EVENT_LOOKBACK
            for ev in db.scalars(
                select(MarketEvent).where(MarketEvent.symbol.in_(list(baselines)), MarketEvent.event_time >= since, MarketEvent.event_time <= now + timedelta(minutes=1))
            ):
                events_by_sym[ev.symbol].append(ev)

        latest_event: dict[int, ChangeEvent] = {}
        if baselines:
            for ev in db.scalars(
                select(ChangeEvent).where(ChangeEvent.user_id == user.id, ChangeEvent.baseline_id.in_([b.id for b in baselines.values()])).order_by(ChangeEvent.generation)
            ):
                latest_event[ev.baseline_id] = ev

        items: dict[str, EvaluatedItem] = {}
        pending: list[tuple[EvaluatedItem, str, dict]] = []
        for sym, prio in sym_prio.items():
            stock, snap = state.get(sym, (None, None))
            if stock is None:
                continue
            item = EvaluatedItem(symbol=sym, stock=stock, priority=prio, snapshot=snap, baseline=baselines.get(sym))
            items[sym] = item
            if snap is None or item.baseline is None:
                continue
            b = item.baseline
            src = sources.get(snap.primary_provider)
            item.freshness = classify_freshness(
                snap.market_timestamp,
                now,
                realtime=snap.provider_realtime,
                conflicted=snap.is_conflicted,
                simulated_session=self.simulated,
                provider_down=bool(src and src.status == "DOWN"),
            )
            sector_snap = bench.get(b.sector_symbol or "", (None, None))[1]
            market_snap = bench.get(MARKET_BENCHMARK, (None, None))[1]
            evs = [e for e in events_by_sym.get(sym, []) if e.event_time >= b.created_at - EVENT_LOOKBACK]
            item.inputs = SignalInputs(
                symbol=sym,
                name=stock.name,
                change_pct=pct(snap.price, b.price) or 0.0,
                day_change_pct=snap.day_change_pct,
                window_trading_days=round(trading_days_between(b.created_at, now), 3),
                sector_name=stock.sector if stock.kind == "EQUITY" else None,
                sector_change_pct=pct(sector_snap.price, b.sector_price) if sector_snap else None,
                market_change_pct=pct(market_snap.price, b.market_price) if market_snap and b.market_price else None,
                volume_ratio=snap.volume_ratio,
                daily_volatility_pct=stock.daily_volatility_pct,
                events=[EventFact(e.event_type, e.headline, e.significance, e.event_time.isoformat()) for e in evs],
                priority=prio,
                data_status=item.freshness.status,
                is_conflicted=snap.is_conflicted,
                conflict_spread_pct=snap.conflict_spread_pct,
                sources_count=snap.sources_count,
            )
            item.result = evaluate(item.inputs, prefs)
            inputs_json = asdict(item.inputs)
            # Hash only what can change the outcome, so re-reading doesn't create rows:
            # windows under a trading day score identically and LIVE == FRESH for scoring.
            basis = dict(inputs_json)
            basis["window_trading_days"] = max(1.0, round(item.inputs.window_trading_days, 1))
            basis["data_status"] = "FRESH" if basis["data_status"] == "LIVE" else basis["data_status"]
            key = hashlib.sha256(
                "|".join([str(user.id), str(b.id), str(snap.id), json.dumps(basis, sort_keys=True, default=str), prefs.fingerprint(), ENGINE_VERSION]).encode()
            ).hexdigest()[:48]
            pending.append((item, key, inputs_json))

        self._persist_scores(user, pending)
        for item, _, _ in pending:
            item.event = self._upsert_event(user, item, latest_event.get(item.baseline.id), prefs_row)

        user.last_evaluated_at = now
        db.flush()
        return items

    # ------------------------------------------------------------------
    def _persist_scores(self, user: User, pending: list[tuple[EvaluatedItem, str, dict]]) -> None:
        if not pending:
            return
        rows = []
        for item, key, inputs_json in pending:
            r = item.result
            rows.append(
                {
                    "user_id": user.id,
                    "symbol": item.symbol,
                    "baseline_id": item.baseline.id,
                    "snapshot_id": item.snapshot.id,
                    "score": r.score,
                    "attention": r.attention,
                    "movement_type": r.movement_type,
                    "confidence": r.confidence,
                    "confidence_level": r.confidence_level,
                    "headline": r.headline[:400],
                    "factors": r.factors_json(),
                    "inputs": inputs_json,
                    "caveats": r.caveats,
                    "engine_version": ENGINE_VERSION,
                    "dedupe_key": key,
                    "created_at": self.now,
                }
            )
        inserted = insert_ignore(self.db, SignalScore, rows, ["dedupe_key"])
        keys = [k for _, k, _ in pending]
        by_key = {s.dedupe_key: s for s in self.db.scalars(select(SignalScore).where(SignalScore.dedupe_key.in_(keys)))}
        for item, key, _ in pending:
            item.signal = by_key.get(key)
            if item.signal is not None:
                item.baseline.latest_signal_id = item.signal.id
        if inserted:
            log_event("signal.generated", user_id=str(user.id), count=inserted)

    def _refresh(self, ev: ChangeEvent, item: EvaluatedItem) -> None:
        r, i = item.result, item.inputs
        ev.attention = r.attention
        ev.score = r.score
        ev.movement_type = r.movement_type
        ev.change_pct = i.change_pct
        ev.day_change_pct = i.day_change_pct
        ev.sector_change_pct = i.sector_change_pct
        ev.market_change_pct = i.market_change_pct
        ev.volume_ratio = i.volume_ratio
        ev.confidence = r.confidence
        ev.data_status = i.data_status
        ev.headline = r.headline[:400]
        if item.signal is not None:
            ev.latest_signal_id = item.signal.id
        ev.updated_at = self.now

    def _new_event(self, user: User, item: EvaluatedItem, generation: int, previous: ChangeEvent | None, prefs: UserPreferences) -> ChangeEvent | None:
        if item.signal is None:
            return previous
        r, i = item.result, item.inputs
        direction = "UP" if i.change_pct >= 0 else "DOWN"
        ev = ChangeEvent(
            id=uuid.uuid4(),
            user_id=user.id,
            symbol=item.symbol,
            baseline_id=item.baseline.id,
            first_signal_id=item.signal.id,
            latest_signal_id=item.signal.id,
            previous_event_id=previous.id if previous else None,
            direction=direction,
            generation=generation,
            attention=r.attention,
            peak_attention=r.attention,
            score=r.score,
            movement_type=r.movement_type,
            change_pct=i.change_pct,
            day_change_pct=i.day_change_pct,
            sector_change_pct=i.sector_change_pct,
            market_change_pct=i.market_change_pct,
            volume_ratio=i.volume_ratio,
            confidence=r.confidence,
            data_status=i.data_status,
            headline=r.headline[:400],
            state="NEW",
            status="ACTIVE",
            dedupe_key=f"{user.id}:{item.symbol}:{item.baseline.id}:{direction}:{generation}",
            created_at=self.now,
            updated_at=self.now,
        )
        try:
            with self.db.begin_nested():
                self.db.add(ev)
                self.db.flush()
        except IntegrityError:  # concurrent evaluation already created it
            return self.db.scalar(select(ChangeEvent).where(ChangeEvent.dedupe_key == ev.dedupe_key))
        log_event("change.detected", user_id=str(user.id), symbol=item.symbol, attention=r.attention, score=r.score, generation=generation)
        self._after_change(user, ev, item, "MEANINGFUL_CHANGE", prefs)
        return ev

    def _after_change(self, user: User, ev: ChangeEvent, item: EvaluatedItem, kind: str, prefs: UserPreferences) -> None:
        from app.services.notifications.service import notify_change

        notify_change(self.db, user, ev, kind, prefs)
        if item.signal is not None:
            enqueue_after_commit(
                self.db,
                "ai.explain",
                {"signal_score_id": item.signal.id, "change_event_id": str(ev.id)},
                job_id=f"ai.explain:{item.signal.id}",
            )

    def _upsert_event(self, user: User, item: EvaluatedItem, ev: ChangeEvent | None, prefs: UserPreferences) -> ChangeEvent | None:
        r, i = item.result, item.inputs
        direction = "UP" if i.change_pct >= 0 else "DOWN"
        if not r.is_meaningful:
            if ev is not None and ev.status == "ACTIVE":
                self._refresh(ev, item)
                ev.status = "RESOLVED"
                log_event("change.resolved", user_id=str(user.id), symbol=item.symbol)
            return ev

        if ev is not None and ev.direction == direction and ev.status in ("ACTIVE", "RESOLVED"):
            escalated = ATT_RANK[r.attention] > ATT_RANK[ev.peak_attention]
            if ev.state == "ACKNOWLEDGED":
                sigma = i.daily_volatility_pct or 1.5
                moved_further = abs(i.change_pct - (ev.ack_change_pct if ev.ack_change_pct is not None else ev.change_pct)) >= max(1.5, sigma)
                if moved_further or escalated:
                    ev.status = "SUPERSEDED"
                    return self._new_event(user, item, ev.generation + 1, ev, prefs)
                self._refresh(ev, item)
                ev.status = "ACTIVE"
                return ev
            prev_score, prev_att = ev.score, ev.attention
            self._refresh(ev, item)
            ev.status = "ACTIVE"
            if escalated:
                ev.peak_attention = r.attention
                ev.state = "NEW"
                self._after_change(user, ev, item, "ESCALATION", prefs)
            elif (abs(prev_score - r.score) >= 10 or prev_att != r.attention) and item.signal is not None:
                enqueue_after_commit(
                    self.db, "ai.explain", {"signal_score_id": item.signal.id, "change_event_id": str(ev.id)}, job_id=f"ai.explain:{item.signal.id}"
                )
            return ev

        if ev is not None and ev.status == "ACTIVE":
            ev.status = "RESOLVED"
        return self._new_event(user, item, (ev.generation + 1) if ev else 1, ev, prefs)


def acknowledge(db: Session, user: User, event_id: uuid.UUID) -> ChangeEvent | None:
    ev = db.scalar(select(ChangeEvent).where(ChangeEvent.id == event_id, ChangeEvent.user_id == user.id))
    if ev is None:
        return None
    if ev.state != "ACKNOWLEDGED":
        now = datetime.now(UTC)
        ev.state = "ACKNOWLEDGED"
        ev.acknowledged_at = now
        ev.seen_at = ev.seen_at or now
        ev.ack_change_pct = ev.change_pct
        log_event("change.acknowledged", user_id=str(user.id), symbol=ev.symbol, event_id=str(ev.id))
    return ev


def mark_seen(db: Session, user: User, event_id: uuid.UUID) -> ChangeEvent | None:
    ev = db.scalar(select(ChangeEvent).where(ChangeEvent.id == event_id, ChangeEvent.user_id == user.id))
    if ev is None:
        return None
    if ev.state == "NEW":
        ev.state = "SEEN"
        ev.seen_at = datetime.now(UTC)
    return ev


__all__ = ["ATT_RANK", "ChangeDetectionService", "EvaluatedItem", "acknowledge", "mark_seen", "pct"]
logging.getLogger(__name__)
