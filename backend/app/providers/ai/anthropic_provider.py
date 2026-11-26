from __future__ import annotations

import anthropic

from app.providers.ai.base import EXPLANATION_JSON_SCHEMA, AIError, AIProvider

DEFAULT_MODEL = "claude-opus-5-5"


class AnthropicProvider(AIProvider):
    name = "anthropic"

    def __init__(self, api_key: str, model: str | None = None, timeout: float = 15.0):
        self.model = model or DEFAULT_MODEL
        self._client = anthropic.Anthropic(api_key=api_key, timeout=timeout, max_retries=1)

    def explain(self, system_prompt: str, user_prompt: str) -> str:
        try:
            response = self._client.beta.messages.create(
                model=self.model,
                max_tokens=4000,
                system=system_prompt,
                messages=[{"role": "user", "content": user_prompt}],
                # Short, bounded writing task: low effort keeps latency down.
                output_config={"effort": "low", "format": {"type": "json_schema", "schema": EXPLANATION_JSON_SCHEMA}},
                # If the model declines, the API retries on a fallback model in the same call.
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",
            )
        except anthropic.RateLimitError as exc:
            raise AIError("AI rate limited") from exc
        except anthropic.APIStatusError as exc:
            raise AIError(f"AI provider error {exc.status_code}") from exc
        except anthropic.APIConnectionError as exc:
            raise AIError("AI provider unreachable") from exc
        if response.stop_reason == "refusal":
            raise AIError("AI declined to answer")
        if response.stop_reason == "max_tokens":
            raise AIError("AI response truncated")
        text = next((b.text for b in response.content if b.type == "text"), None)
        if not text:
            raise AIError("AI returned no text")
        return text
