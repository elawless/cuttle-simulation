"""Anthropic provider implementation."""

from __future__ import annotations

import os
import time
from typing import Any

from strategies.llm.base import LLMProvider, LLMResponse, ProviderConfig
from core.pricing import get_cost


class AnthropicProvider(LLMProvider):
    """LLM provider for Anthropic's Claude models."""

    AVAILABLE_MODELS = {
        "haiku": "claude-3-5-haiku-latest",
        "sonnet": "claude-sonnet-4-20250514",
        "opus": "claude-opus-4-20250514",
    }

    def __init__(self, config: ProviderConfig | None = None):
        """Initialize the Anthropic provider.

        Args:
            config: Optional provider configuration.
        """
        self._config = config or ProviderConfig()
        self._client = None

    def _get_client(self):
        """Lazy-load the Anthropic client."""
        if self._client is None:
            api_key = self._config.api_key or os.environ.get("ANTHROPIC_API_KEY")
            if not api_key:
                raise RuntimeError(
                    "ANTHROPIC_API_KEY environment variable not set. "
                    "Set it in your environment or pass it in ProviderConfig."
                )

            try:
                import anthropic
                self._client = anthropic.Anthropic(api_key=api_key)
            except ImportError:
                raise RuntimeError(
                    "anthropic package not installed. Run: pip install anthropic"
                )
        return self._client

    @property
    def name(self) -> str:
        return "anthropic"

    @property
    def available_models(self) -> list[str]:
        return list(self.AVAILABLE_MODELS.values())

    def complete(
        self,
        prompt: str,
        model: str,
        temperature: float = 0.3,
        max_tokens: int = 1024,
        **kwargs: Any,
    ) -> LLMResponse:
        """Send a completion request to Anthropic.

        Args:
            prompt: The prompt to send.
            model: Model name or alias (haiku, sonnet, opus).
            temperature: Sampling temperature.
            max_tokens: Maximum tokens in response.
            **kwargs: Additional parameters.

        Returns:
            LLMResponse with content and token usage.
        """
        # Resolve model alias
        resolved_model = self.AVAILABLE_MODELS.get(model.lower(), model)

        client = self._get_client()

        start_time = time.perf_counter()

        response = client.messages.create(
            model=resolved_model,
            max_tokens=max_tokens,
            temperature=temperature,
            messages=[{"role": "user", "content": prompt}],
        )

        latency_ms = (time.perf_counter() - start_time) * 1000

        return LLMResponse(
            content=response.content[0].text.strip(),
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            model=resolved_model,
            latency_ms=latency_ms,
            raw_response=response,
        )

    def estimate_cost(
        self,
        model: str,
        input_tokens: int,
        output_tokens: int,
    ) -> float:
        """Estimate cost for a request."""
        resolved_model = self.AVAILABLE_MODELS.get(model.lower(), model)
        return get_cost(resolved_model, input_tokens, output_tokens)

    def is_available(self) -> bool:
        """Check if Anthropic API key is available."""
        api_key = self._config.api_key or os.environ.get("ANTHROPIC_API_KEY")
        return api_key is not None
