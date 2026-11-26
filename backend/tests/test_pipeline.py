"""Ingestion idempotency, provider failure, AI fallback, and the end-to-end API flow."""

import json
from datetime import UTC, datetime

from sqlalchemy import func, select

from app.models import ChangeEvent, DataSource, MarketQuote, MarketSnapshot, Stock
from app.providers.ai.base import AIError, AIProvider
from app.providers.market.base import ProviderUnavailable
from app.providers.market.mock import MockProvider
from app.services.ai.explainer import generate
from app.services.market_data.ingestion import IngestionService
from tests.conftest import signup

FIXED = datetime(2026, 11, 25, 16, 0, tzinfo=UTC)


class DownProvider(MockProvider):
    def get_quote(self, symbol):
        raise ProviderUnavailable("down")


def count(db, model):
    return db.scalar(select(func.count()).select_from(model))


def test_ingestion_is_idempotent(db):
    p = MockProvider(clock=lambda: FIXED)
    svc = IngestionService(db, providers=[p], now=FIXED)
    svc.refresh(["NVDA", "SPY"])
    db.commit()
    snaps, quotes = count(db, MarketSnapshot), count(db, MarketQuote)
    report = svc.refresh(["NVDA", "SPY"])
    db.commit()
    assert report.updated == [] and set(report.unchanged) == {"NVDA", "SPY"}
    assert count(db, MarketSnapshot) == snaps and count(db, MarketQuote) == quotes


def test_provider_failure_falls_back_then_keeps_last_known(db):
    primary = DownProvider("primary", clock=lambda: FIXED)
    reference = MockProvider("reference", clock=lambda: FIXED)
    svc = IngestionService(db, providers=[primary, reference], now=FIXED)
    report = svc.refresh(["NVDA"])
    db.commit()
    assert report.updated == ["NVDA"]
    snap = db.get(MarketSnapshot, db.get(Stock, "NVDA").latest_snapshot_id)
    assert snap.primary_provider == "mock-reference"
    assert db.get(DataSource, "mock-primary").status in ("DEGRADED", "DOWN")

    all_down = IngestionService(db, providers=[primary, DownProvider("reference", clock=lambda: FIXED)], now=FIXED)
    report = all_down.refresh(["NVDA"])
    db.commit()
    assert report.failed == ["NVDA"]
    assert db.get(Stock, "NVDA").latest_snapshot_id == snap.id  # last-known state is kept, not invented


class StubAI(AIProvider):
    name, model = "stub", "stub-1"

    def __init__(self, outputs):
        self.outputs = list(outputs)
        self.calls = 0

    def explain(self, system_prompt, user_prompt):
        self.calls += 1
        out = self.outputs.pop(0)
        if isinstance(out, Exception):
            raise out
        return json.dumps(out)


def _facts(db):
    from app.providers.ai.base import ExplanationFacts

    return ExplanationFacts(
        symbol="NVDA", company="NVIDIA", attention_level="HIGH", signal_score=77, movement_type="STOCK_SPECIFIC", context_label="Stock-specific",
        change_since_checkpoint_pct=-4.8, checkpoint_time="10:32 UTC on Nov 25", price_now=171.55, price_at_checkpoint=180.2, currency="USD",
        day_change_pct=-4.11, sector_name="Technology", sector_change_pct=-0.7, market_change_pct=-0.3, relative_to_sector_pct_points=-4.1,
        relative_to_market_pct_points=-4.5, volume_ratio=2.8, events=[], factors=[], confidence_level="HIGH", data_status="LIVE", caveats=[],
    )


GOOD = {
    "summary": "NVIDIA is down 4.8% since you last checked while Technology fell 0.7%.",
    "why_it_matters": "The drop is far larger than its sector and the market, on 2.8x normal volume.",
    "key_factors": ["Underperforming sector by 4.1 points", "Volume 2.8x normal"],
    "attention_level": "HIGH",
    "confidence": "HIGH",
}


def test_ai_valid_output_is_used(db):
    out = generate(_facts(db), StubAI([GOOD]))
    assert out.source == "AI" and out.attempts == 1


def test_ai_invented_number_is_rejected_then_retried(db):
    bad = {**GOOD, "summary": "NVIDIA fell 9.7% after an earnings miss."}
    ai = StubAI([bad, GOOD])
    out = generate(_facts(db), ai)
    assert ai.calls == 2 and out.source == "AI" and out.attempts == 2


def test_ai_failure_uses_deterministic_fallback(db):
    out = generate(_facts(db), StubAI([AIError("timeout"), AIError("timeout")]))
    assert out.source == "FALLBACK"
    assert "4.8%" in out.draft.summary and out.draft.attention_level == "HIGH"
    assert generate(_facts(db), None).source == "FALLBACK"


def test_end_to_end_flow_idempotency_and_authorization(client, db):
    signup(client, "owner@example.com")
    assert client.post("/api/demo/scenario", json={"key": "NORMAL_MOVEMENT"}).status_code == 200
    r = client.post("/api/onboarding", json={"symbols": ["NVDA", "AAPL", "MSFT"], "sensitivity": "BALANCED"})
    assert r.status_code == 200, r.text

    cc = client.get("/api/command-center").json()
    assert cc["counts"]["meaningful"] == 0 and cc["counts"]["tracked"] == 3

    assert client.post("/api/demo/scenario", json={"key": "STOCK_SPECIFIC_DROP"}).status_code == 200
    cc = client.get("/api/command-center").json()
    assert [c["symbol"] for c in cc["needs_attention"]] == ["NVDA"]
    card = cc["needs_attention"][0]
    assert card["attention"] == "HIGH" and round(card["change_pct"], 1) == -4.8
    assert round(card["day_change_pct"], 1) == -4.1  # since-checkpoint differs from today's change

    # Re-reading and re-evaluating does not duplicate the change.
    for _ in range(3):
        client.get("/api/command-center")
    assert db.scalar(select(func.count()).select_from(ChangeEvent)) == 1

    detail = client.get(f"/api/changes/{card['id']}").json()
    assert detail["explanation"]["source"] == "FALLBACK" and detail["factors"]
    assert client.post(f"/api/changes/{card['id']}/acknowledge").json()["state"] == "ACKNOWLEDGED"
    cc = client.get("/api/command-center").json()
    assert cc["needs_attention"] == [] and cc["reviewed"][0]["symbol"] == "NVDA"

    wl_id = cc["watchlists"][0]["id"]
    owner_cookies = dict(client.cookies)

    # Another user can't see or touch the owner's data.
    client.cookies.clear()
    signup(client, "intruder@example.com")
    assert client.get(f"/api/watchlists/{wl_id}").status_code == 404
    assert client.get(f"/api/watchlists/{wl_id}/snapshot").status_code == 404
    assert client.delete(f"/api/watchlists/{wl_id}").status_code == 404
    assert client.post(f"/api/watchlists/{wl_id}/stocks", json={"symbol": "AMD"}).status_code == 404
    assert client.get(f"/api/changes/{card['id']}").status_code == 404
    assert client.post(f"/api/changes/{card['id']}/acknowledge").status_code == 404

    client.cookies.clear()
    assert client.get("/api/command-center").status_code == 401
    client.cookies.update(owner_cookies)

    # Checkpoint: the change becomes history; nothing is new any more.
    assert client.post("/api/checkpoint").status_code == 201
    cc = client.get("/api/command-center").json()
    assert cc["counts"]["meaningful"] == 0 and cc["reviewed"] == []
