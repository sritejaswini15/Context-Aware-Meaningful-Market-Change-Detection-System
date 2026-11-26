from __future__ import annotations

from functools import lru_cache

from app.core.config import get_settings
from app.providers.ai.base import AIError, AIProvider


class SimulatedOutageProvider(AIProvider):
    """Used by the AI_FAILURE demo scenario."""

    def __init__(self, inner: AIProvider | None):
        self.name = inner.name if inner else "none"
        self.model = inner.model if inner else "-"

    def explain(self, system_prompt: str, user_prompt: str) -> str:
        raise AIError("Simulated AI provider outage (demo scenario)")


@lru_cache
def _configured_provider() -> AIProvider | None:
    s = get_settings()
    if s.ai_provider == "anthropic" and s.ai_api_key:
        from app.providers.ai.anthropic_provider import AnthropicProvider

        return AnthropicProvider(s.ai_api_key, s.ai_model, s.ai_timeout_seconds)
    return None


def get_ai_provider() -> AIProvider | None:
    """None means "AI not configured": deterministic explanations are used."""
    provider = _configured_provider()
    s = get_settings()
    if s.demo_mode:
        from app.providers.market.scenarios import SCENARIOS
        from app.services.demo.state import current_scenario

        key, _ = current_scenario()
        if "AI_DOWN" in SCENARIOS[key].faults:
            return SimulatedOutageProvider(provider)
    return provider


def ai_configured() -> bool:
    return _configured_provider() is not None
