"""Request and response models (they also drive the OpenAPI docs)."""

from __future__ import annotations

import re
import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

Attention = Literal["LOW", "MEDIUM", "HIGH"]
SYMBOL_RE = re.compile(r"^[A-Z][A-Z0-9.\-]{0,9}$")


def _symbol(v: str) -> str:
    v = v.strip().upper()
    if not SYMBOL_RE.match(v):
        raise ValueError("Invalid ticker symbol")
    return v


class Model(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ----------------------------------------------------------------------------- auth
class SignupIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    display_name: str | None = Field(default=None, max_length=120)


class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class ConfirmIn(BaseModel):
    email: EmailStr
    code: str = Field(min_length=4, max_length=12)


class UserOut(Model):
    id: uuid.UUID
    email: str
    display_name: str | None
    onboarded: bool
    auth_provider: str
    created_at: datetime


class AuthOut(BaseModel):
    status: Literal["OK", "CONFIRMATION_REQUIRED"] = "OK"
    user: UserOut | None = None
    token: str | None = Field(default=None, description="Also set as an httpOnly cookie")


class ProfilePatch(BaseModel):
    display_name: str | None = Field(default=None, max_length=120)


class OnboardingIn(BaseModel):
    watchlist_name: str = Field(default="My Watchlist", min_length=1, max_length=80)
    symbols: list[str] = Field(min_length=1, max_length=30)
    sensitivity: Literal["LOW", "BALANCED", "HIGH"] = "BALANCED"

    @field_validator("symbols")
    @classmethod
    def _syms(cls, v: list[str]) -> list[str]:
        return list(dict.fromkeys(_symbol(s) for s in v))


# ----------------------------------------------------------------------------- preferences
class PreferencesOut(Model):
    sensitivity: Literal["LOW", "BALANCED", "HIGH"]
    include_volume: bool
    include_market_context: bool
    include_events: bool
    notify_min_attention: Literal["HIGH", "MEDIUM"]
    updated_at: datetime


class PreferencesPatch(BaseModel):
    sensitivity: Literal["LOW", "BALANCED", "HIGH"] | None = None
    include_volume: bool | None = None
    include_market_context: bool | None = None
    include_events: bool | None = None
    notify_min_attention: Literal["HIGH", "MEDIUM"] | None = None


# ----------------------------------------------------------------------------- watchlists
class WatchlistIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    symbols: list[str] = Field(default_factory=list, max_length=50)

    @field_validator("name")
    @classmethod
    def _name(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Name is required")
        return v

    @field_validator("symbols")
    @classmethod
    def _syms(cls, v: list[str]) -> list[str]:
        return list(dict.fromkeys(_symbol(s) for s in v))


class WatchlistPatch(BaseModel):
    name: str = Field(min_length=1, max_length=80)

    @field_validator("name")
    @classmethod
    def _name(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Name is required")
        return v


class AddStockIn(BaseModel):
    symbol: str
    priority: Literal["NORMAL", "HIGH"] = "NORMAL"

    @field_validator("symbol")
    @classmethod
    def _sym(cls, v: str) -> str:
        return _symbol(v)


class ItemPatch(BaseModel):
    priority: Literal["NORMAL", "HIGH"]


class WatchlistItemOut(BaseModel):
    symbol: str
    name: str
    priority: str
    added_at: datetime


class WatchlistSummary(BaseModel):
    id: uuid.UUID
    name: str
    symbols_count: int
    symbols: list[str]
    high_count: int = 0
    medium_count: int = 0
    created_at: datetime
    updated_at: datetime


class WatchlistOut(WatchlistSummary):
    items: list[WatchlistItemOut]


# ----------------------------------------------------------------------------- market state
class FreshnessOut(BaseModel):
    status: Literal["LIVE", "FRESH", "DELAYED", "STALE", "CONFLICTED"]
    label: str
    age_seconds: int
    is_stale: bool
    is_conflicted: bool
    market_timestamp: datetime
    provider: str
    sources_count: int
    simulated: bool


class BaselineOut(BaseModel):
    price: float
    checked_at: datetime
    reason: str
    status: str


class SignalOut(BaseModel):
    score: int
    attention: Attention
    movement_type: str
    context_label: str
    confidence: float
    confidence_level: Attention
    headline: str
    caveats: list[str]
    evaluated_at: datetime | None = None


class FactorOut(BaseModel):
    key: str
    label: str
    points: float
    max_points: float
    detail: str
    enabled: bool = True


class StockStateOut(BaseModel):
    symbol: str
    name: str
    sector: str | None
    sector_benchmark: str | None
    exchange: str | None
    currency: str
    kind: str
    priority: str | None = None
    price: float | None
    day_change_pct: float | None
    since_check_pct: float | None
    sector_since_check_pct: float | None = None
    market_since_check_pct: float | None = None
    volume: int | None
    volume_ratio: float | None
    freshness: FreshnessOut | None
    baseline: BaselineOut | None
    signal: SignalOut | None
    change_id: uuid.UUID | None = None
    change_state: str | None = None


class ExplanationOut(BaseModel):
    source: Literal["AI", "FALLBACK"]
    status: Literal["READY", "PENDING", "UPDATING"]
    summary: str
    why_it_matters: str
    key_factors: list[str]
    attention: str
    confidence: str
    model: str | None = None
    error: str | None = None
    is_latest: bool = True
    generated_at: datetime


class ChangeCardOut(BaseModel):
    id: uuid.UUID
    symbol: str
    name: str
    sector: str | None
    attention: Attention
    peak_attention: Attention
    score: int
    movement_type: str
    context_label: str
    direction: Literal["UP", "DOWN"]
    change_pct: float
    day_change_pct: float | None
    sector_change_pct: float | None
    market_change_pct: float | None
    volume_ratio: float | None
    price: float | None
    baseline_price: float | None
    checked_at: datetime | None
    confidence: float
    confidence_level: Attention
    data_status: str
    headline: str
    summary: str | None = None
    state: Literal["NEW", "SEEN", "ACKNOWLEDGED"]
    status: str
    generation: int
    created_at: datetime
    updated_at: datetime
    caveats: list[str] = []


class ChangeDetailOut(ChangeCardOut):
    factors: list[FactorOut]
    explanation: ExplanationOut
    freshness: FreshnessOut | None
    history: list[ChangeCardOut]


class ChangeListOut(BaseModel):
    items: list[ChangeCardOut]
    total: int
    counts: dict[str, int]


class CheckpointOut(BaseModel):
    id: uuid.UUID
    scope: str
    watchlist_id: uuid.UUID | None
    symbols_count: int
    created_at: datetime


class MarketBenchOut(BaseModel):
    symbol: str
    name: str
    price: float | None
    day_change_pct: float | None
    since_check_pct: float | None = None
    freshness: FreshnessOut | None


class MarketContextOut(BaseModel):
    session: str
    simulated: bool
    scenario: str | None
    market: MarketBenchOut | None
    sectors: list[MarketBenchOut]
    summary: str
    last_update: datetime | None


class ActivityOut(BaseModel):
    kind: str
    at: datetime
    title: str
    symbol: str | None = None
    attention: str | None = None
    change_id: uuid.UUID | None = None


class CommandCenterOut(BaseModel):
    user: UserOut
    last_checked_at: datetime | None
    counts: dict[str, int]
    needs_attention: list[ChangeCardOut]
    reviewed: list[ChangeCardOut]
    quiet: list[StockStateOut]
    market_context: MarketContextOut
    watchlists: list[WatchlistSummary]
    recent_activity: list[ActivityOut]
    data_quality: dict
    ai: dict
    unread_notifications: int


class SearchResultOut(BaseModel):
    symbol: str
    name: str
    exchange: str | None
    sector: str | None
    price: float | None
    day_change_pct: float | None
    in_watchlists: list[uuid.UUID]


class EventOut(BaseModel):
    id: int
    event_type: str
    headline: str
    summary: str | None
    source: str | None
    url: str | None
    event_time: datetime
    significance: float


class ConflictOut(BaseModel):
    detected_at: datetime
    observations: list[dict]
    chosen_provider: str
    chosen_price: float
    spread_pct: float
    tolerance_pct: float
    resolution: str


class StockDetailOut(BaseModel):
    state: StockStateOut
    signal_basis: Literal["CHECKPOINT", "PREVIOUS_CLOSE", "NONE"]
    factors: list[FactorOut]
    change: ChangeCardOut | None
    explanation: ExplanationOut | None
    sector: MarketBenchOut | None
    market: MarketBenchOut | None
    events: list[EventOut]
    conflict: ConflictOut | None
    in_watchlists: list[uuid.UUID]
    stats: dict


class NotificationOut(Model):
    id: uuid.UUID
    kind: str
    title: str
    body: str
    attention: str | None
    symbol: str | None
    change_event_id: uuid.UUID | None
    read_at: datetime | None
    created_at: datetime


class NotificationListOut(BaseModel):
    items: list[NotificationOut]
    unread: int


class ScenarioIn(BaseModel):
    key: str
