"""AI explanation layer.

Flow: facts (from the stored, deterministic signal) -> LLM with a JSON schema
-> Pydantic validation -> "no invented numbers" guard -> retry once with the
rejection reason -> deterministic fallback. Knoww keeps working with no AI.
"""

from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass
from datetime import UTC, datetime

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import insert_ignore
from app.core.logging import log_event
from app.models import ChangeEvent, CheckpointBaseline, MarketSnapshot, SignalExplanation, SignalScore, Stock
from app.providers.ai.base import AIError, AIProvider, EventFactModel, ExplanationDraft, ExplanationFacts, FactorFact
from app.providers.ai.registry import get_ai_provider

PROMPT_VERSION = "2026-11.1"

SYSTEM_PROMPT = """You write short, neutral explanations for Knoww, a market-awareness app.
Knoww's deterministic engine has already measured what changed and how much attention it deserves.
Your job is only to explain those facts clearly to an investor who has a few seconds.

Rules:
- Use only the facts in the JSON. Do not introduce any number, price, percentage, volume figure,
  date, event, earnings result or cause that is not in the facts.
- If no event is listed, say that no company event was found in the available data. Do not guess why the stock moved.
- Never give buy, sell or hold advice, price targets or predictions.
- attention_level and confidence must equal the values in the facts.
- If data_status or caveats mention stale, delayed, conflicting or unavailable data, say so plainly.
- Plain English, calm tone, no hype, no emojis. summary <= 2 sentences, why_it_matters <= 3 sentences,
  2-4 key_factors of a few words each."""

_NUM_RE = re.compile(r"(?<![A-Za-z])[-+]?\$?\d[\d,]*(?:\.\d+)?")


def _numbers(text: str) -> list[float]:
    out = []
    for m in _NUM_RE.findall(text):
        try:
            out.append(abs(float(m.replace("$", "").replace(",", "").replace("+", ""))))
        except ValueError:
            continue
    return out


def _allowed_numbers(facts: ExplanationFacts) -> set[float]:
    allowed: set[float] = set(range(0, 13))  # small counts ("two factors", "3 providers")
    for n in _numbers(facts.model_dump_json()):
        for d in (0, 1, 2):
            allowed.add(round(n, d))
    return allowed


def check_grounded(draft: ExplanationDraft, facts: ExplanationFacts) -> str | None:
    if draft.attention_level != facts.attention_level:
        return f"attention_level must be {facts.attention_level}"
    if draft.confidence != facts.confidence_level:
        return f"confidence must be {facts.confidence_level}"
    allowed = _allowed_numbers(facts)
    text = " ".join([draft.summary, draft.why_it_matters, *draft.key_factors])
    for n in _numbers(text):
        if not any(abs(n - round(n, d)) < 1e-9 and round(n, d) in allowed for d in (0, 1, 2)):
            return f"the number {n:g} does not appear in the facts"
    lowered = text.lower()
    for banned in ("buy", "sell", "strong buy", "price target"):
        if re.search(rf"\b{banned}\b", lowered):
            return f"advice language ('{banned}') is not allowed"
    return None


def build_facts(db: Session, signal: SignalScore) -> ExplanationFacts:
    stock = db.get(Stock, signal.symbol)
    baseline = db.get(CheckpointBaseline, signal.baseline_id)
    snap = db.get(MarketSnapshot, signal.snapshot_id)
    i = signal.inputs
    rel_s = round(i["change_pct"] - i["sector_change_pct"], 2) if i.get("sector_change_pct") is not None else None
    rel_m = round(i["change_pct"] - i["market_change_pct"], 2) if i.get("market_change_pct") is not None else None
    context_label = {
        "STOCK_SPECIFIC": "Stock-specific",
        "MARKET_WIDE": "Broad market movement",
        "SECTOR_WIDE": "Sector movement",
        "QUIET": "Minor movement",
    }.get(signal.movement_type, signal.movement_type)
    return ExplanationFacts(
        symbol=signal.symbol,
        company=stock.name if stock else signal.symbol,
        attention_level=signal.attention,
        signal_score=signal.score,
        movement_type=signal.movement_type,
        context_label=context_label,
        change_since_checkpoint_pct=round(i["change_pct"], 2),
        checkpoint_time=baseline.created_at.strftime("%H:%M UTC on %b %d") if baseline else "unknown",
        price_now=round(snap.price, 2) if snap else 0.0,
        price_at_checkpoint=round(baseline.price, 2) if baseline else 0.0,
        currency=stock.currency if stock else "USD",
        day_change_pct=round(i["day_change_pct"], 2) if i.get("day_change_pct") is not None else None,
        sector_name=i.get("sector_name"),
        sector_change_pct=round(i["sector_change_pct"], 2) if i.get("sector_change_pct") is not None else None,
        market_change_pct=round(i["market_change_pct"], 2) if i.get("market_change_pct") is not None else None,
        relative_to_sector_pct_points=rel_s,
        relative_to_market_pct_points=rel_m,
        volume_ratio=round(i["volume_ratio"], 1) if i.get("volume_ratio") is not None else None,
        events=[EventFactModel(event_type=e["event_type"], headline=e["headline"], event_time=e["event_time"]) for e in i.get("events", [])],
        factors=[FactorFact(label=f["label"], points=f["points"], max_points=f["max_points"], detail=f["detail"]) for f in signal.factors if f.get("enabled", True)],
        confidence_level=signal.confidence_level,
        data_status=i.get("data_status", "FRESH"),
        caveats=list(signal.caveats or []),
    )


def _pct(v: float | None) -> str:
    return "unavailable" if v is None else f"{v:+.1f}%"


def deterministic_explanation(facts: ExplanationFacts) -> ExplanationDraft:
    f = facts
    direction = "up" if f.change_since_checkpoint_pct >= 0 else "down"
    summary = (
        f"{f.company} is {direction} {abs(f.change_since_checkpoint_pct):.1f}% since you last checked "
        f"(sector {_pct(f.sector_change_pct)}, market {_pct(f.market_change_pct)})."
    )
    parts: list[str] = []
    if f.movement_type == "STOCK_SPECIFIC":
        rel = []
        if f.relative_to_sector_pct_points is not None:
            rel.append(f"{f.relative_to_sector_pct_points:+.1f} points versus its sector")
        if f.relative_to_market_pct_points is not None:
            rel.append(f"{f.relative_to_market_pct_points:+.1f} versus the market")
        parts.append(f"The move is {' and '.join(rel) or 'not matched by its benchmarks'}, so broad movement does not explain it.")
    elif f.movement_type == "MARKET_WIDE":
        parts.append(f"The market moved {_pct(f.market_change_pct)} over the same window, so this is mostly broad market movement.")
    elif f.movement_type == "SECTOR_WIDE":
        parts.append(f"The {f.sector_name or 'sector'} moved {_pct(f.sector_change_pct)}, so the move looks sector-driven, not company-specific.")
    else:
        parts.append("The change is within this stock's normal range and broadly consistent with the market.")
    if f.volume_ratio is not None and f.volume_ratio >= 1.5:
        parts.append(f"Trading volume is {f.volume_ratio:.1f}x normal, which strengthens the signal.")
    if f.events:
        parts.append(f"Related event: {f.events[0].headline}.")
    elif f.movement_type == "STOCK_SPECIFIC":
        parts.append("No company event was found in the available data.")
    if f.data_status in ("STALE", "DELAYED") or f.caveats:
        parts.append(f.caveats[0] if f.caveats else f"Data is {f.data_status.lower()}.")
    top = sorted((x for x in f.factors if x.points > 0), key=lambda x: x.points, reverse=True)[:4]
    key_factors = [f"{x.label}: {x.detail}" for x in top] or ["No factor contributed meaningfully"]
    return ExplanationDraft(
        summary=summary[:320],
        why_it_matters=" ".join(parts)[:700],
        key_factors=[k[:160] for k in key_factors],
        attention_level=f.attention_level,
        confidence=f.confidence_level,
    )


@dataclass
class ExplanationOutcome:
    draft: ExplanationDraft
    source: str  # AI | FALLBACK
    provider: str | None
    model: str | None
    attempts: int
    error: str | None
    latency_ms: int | None


def generate(facts: ExplanationFacts, provider: AIProvider | None) -> ExplanationOutcome:
    if provider is None:
        return ExplanationOutcome(deterministic_explanation(facts), "FALLBACK", None, None, 0, "AI not configured", None)
    user_prompt = "Facts (JSON):\n" + facts.model_dump_json(indent=1) + "\n\nWrite the explanation."
    error: str | None = None
    started = time.monotonic()
    for attempt in (1, 2):
        prompt = user_prompt if attempt == 1 else user_prompt + f"\n\nYour previous answer was rejected because {error}. Fix that."
        try:
            raw = provider.explain(SYSTEM_PROMPT, prompt)
            draft = ExplanationDraft.model_validate(json.loads(raw))
            problem = check_grounded(draft, facts)
            if problem is None:
                return ExplanationOutcome(draft, "AI", provider.name, provider.model, attempt, None, int((time.monotonic() - started) * 1000))
            error = problem
            log_event("ai.invalid_output", logging.WARNING, symbol=facts.symbol, attempt=attempt, reason=problem)
        except AIError as exc:
            error = str(exc)
            log_event("ai.failure", logging.WARNING, symbol=facts.symbol, attempt=attempt, error=error)
            if attempt == 2 or "outage" in error:
                break
        except (ValidationError, json.JSONDecodeError) as exc:
            error = f"output did not match the schema ({type(exc).__name__})"
            log_event("ai.invalid_output", logging.WARNING, symbol=facts.symbol, attempt=attempt, reason=error)
    return ExplanationOutcome(
        deterministic_explanation(facts), "FALLBACK", provider.name, provider.model, 2, error, int((time.monotonic() - started) * 1000)
    )


def explain_signal(db: Session, signal_score_id: int, change_event_id: str | None) -> SignalExplanation | None:
    """Idempotent: one explanation per signal score."""
    existing = db.scalar(select(SignalExplanation).where(SignalExplanation.signal_score_id == signal_score_id))
    if existing is not None:
        return existing
    signal = db.get(SignalScore, signal_score_id)
    if signal is None:
        return None
    facts = build_facts(db, signal)
    outcome = generate(facts, get_ai_provider())
    insert_ignore(
        db,
        SignalExplanation,
        [
            {
                "signal_score_id": signal.id,
                "change_event_id": change_event_id,
                "source": outcome.source,
                "provider": outcome.provider,
                "model": outcome.model,
                "summary": outcome.draft.summary,
                "why_it_matters": outcome.draft.why_it_matters,
                "key_factors": outcome.draft.key_factors,
                "attention": outcome.draft.attention_level,
                "confidence": outcome.draft.confidence,
                "attempts": outcome.attempts,
                "latency_ms": outcome.latency_ms,
                "error": outcome.error,
                "prompt_version": PROMPT_VERSION,
                "created_at": datetime.now(UTC),
            }
        ],
        ["signal_score_id"],
    )
    _record_ai_health(db, outcome)
    log_event("ai.generated" if outcome.source == "AI" else "ai.fallback_used", symbol=signal.symbol, source=outcome.source, error=outcome.error)
    return db.scalar(select(SignalExplanation).where(SignalExplanation.signal_score_id == signal_score_id))


def _record_ai_health(db: Session, outcome: ExplanationOutcome) -> None:
    from app.services.system_health.service import record_component

    if outcome.provider is None:
        return
    if outcome.source == "AI":
        record_component(db, "ai", "HEALTHY", f"{outcome.provider} responding ({outcome.latency_ms} ms)", success=True)
    else:
        record_component(db, "ai", "DEGRADED", f"Using deterministic fallback: {outcome.error}")


def explanation_for_event(db: Session, ev: ChangeEvent) -> dict:
    """Latest stored explanation, or an immediate deterministic one while AI runs."""
    ai_on = get_ai_provider() is not None
    row = db.scalar(
        select(SignalExplanation).where(SignalExplanation.change_event_id == ev.id).order_by(SignalExplanation.created_at.desc()).limit(1)
    )
    if row is not None:
        is_latest = row.signal_score_id == ev.latest_signal_id
        return {
            "source": row.source,
            "status": "READY" if is_latest or not ai_on else "UPDATING",
            "summary": row.summary,
            "why_it_matters": row.why_it_matters,
            "key_factors": row.key_factors,
            "attention": row.attention,
            "confidence": row.confidence,
            "model": row.model,
            "error": row.error,
            "is_latest": is_latest,
            "generated_at": row.created_at,
        }
    signal = db.get(SignalScore, ev.latest_signal_id)
    draft = deterministic_explanation(build_facts(db, signal))
    return {
        "source": "FALLBACK",
        "status": "PENDING" if ai_on else "READY",
        "summary": draft.summary,
        "why_it_matters": draft.why_it_matters,
        "key_factors": draft.key_factors,
        "attention": draft.attention_level,
        "confidence": draft.confidence,
        "model": None,
        "error": None if ai_on else "AI not configured",
        "is_latest": True,
        "generated_at": datetime.now(UTC),
    }
