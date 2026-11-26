"""LLM provider contract. AI explains facts computed by the backend; it never
decides attention, and it never supplies numbers."""

from __future__ import annotations

import abc
from typing import Literal

from pydantic import BaseModel, Field


class AIError(Exception):
    pass


class FactorFact(BaseModel):
    label: str
    points: float
    max_points: float
    detail: str


class EventFactModel(BaseModel):
    event_type: str
    headline: str
    event_time: str


class ExplanationFacts(BaseModel):
    """Everything the AI is allowed to talk about."""

    symbol: str
    company: str
    attention_level: Literal["LOW", "MEDIUM", "HIGH"]
    signal_score: int
    movement_type: str
    context_label: str
    change_since_checkpoint_pct: float
    checkpoint_time: str
    price_now: float
    price_at_checkpoint: float
    currency: str
    day_change_pct: float | None
    sector_name: str | None
    sector_change_pct: float | None
    market_change_pct: float | None
    relative_to_sector_pct_points: float | None
    relative_to_market_pct_points: float | None
    volume_ratio: float | None
    events: list[EventFactModel]
    factors: list[FactorFact]
    confidence_level: Literal["LOW", "MEDIUM", "HIGH"]
    data_status: str
    caveats: list[str]


class ExplanationDraft(BaseModel):
    summary: str = Field(min_length=10, max_length=320)
    why_it_matters: str = Field(min_length=10, max_length=700)
    key_factors: list[str] = Field(min_length=1, max_length=5)
    attention_level: Literal["LOW", "MEDIUM", "HIGH"]
    confidence: Literal["LOW", "MEDIUM", "HIGH"]


EXPLANATION_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string", "description": "One or two sentences: what changed, using only provided numbers."},
        "why_it_matters": {"type": "string", "description": "Why this deserves (or does not deserve) attention, in context of sector and market."},
        "key_factors": {"type": "array", "items": {"type": "string"}, "description": "2-4 short factor statements drawn from the facts."},
        "attention_level": {"type": "string", "enum": ["LOW", "MEDIUM", "HIGH"]},
        "confidence": {"type": "string", "enum": ["LOW", "MEDIUM", "HIGH"]},
    },
    "required": ["summary", "why_it_matters", "key_factors", "attention_level", "confidence"],
    "additionalProperties": False,
}


class AIProvider(abc.ABC):
    name: str
    model: str

    @abc.abstractmethod
    def explain(self, system_prompt: str, user_prompt: str) -> str:
        """Return raw JSON text matching EXPLANATION_JSON_SCHEMA."""
