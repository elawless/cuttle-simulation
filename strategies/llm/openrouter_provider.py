"""OpenRouter provider implementation for access to open source models."""

from __future__ import annotations

import os
import time
from typing import Any

from strategies.llm.base import LLMProvider, LLMResponse, ProviderConfig
from core.pricing import get_cost


class OpenRouterProvider(LLMProvider):
    """LLM provider for OpenRouter API.

    OpenRouter provides access to various open source and proprietary models
    through a unified API.
    """

    BASE_URL = "https://openrouter.ai/api/v1"
    DEFAULT_TIMEOUT = 120.0  # 2 minutes for standard models

    # Models that need extra time (reasoning/thinking models)
    SLOW_MODELS = {
        "qwen/qwen3-235b-a22b",
        "deepseek/deepseek-r1",
        "deepseek/deepseek-r1-0528",
    }
    SLOW_MODEL_TIMEOUT = 300.0  # 5 minutes for reasoning models

    # Priority models for Cuttle
    AVAILABLE_MODELS = {
        # Open source models - Fast options
        "qwen2.5-72b": "qwen/qwen-2.5-72b-instruct",  # Fast, good quality
        "llama-4-maverick": "meta-llama/llama-4-maverick",  # Very fast
        "llama3": "meta-llama/llama-3.3-70b-instruct",  # Alias for llama3
        "llama-3.3-70b": "meta-llama/llama-3.3-70b-instruct",
        "gemini-flash": "google/gemini-2.0-flash-001",  # Very fast
        # Open source models - Slower, higher quality
        "qwen3": "qwen/qwen3-235b-a22b",  # SLOW: 235B with reasoning (~60s/move)
        "qwen3-235b": "qwen/qwen3-235b-a22b",  # SLOW: 235B with reasoning
        "kimi": "moonshotai/kimi-k2.5",  # Alias for kimi
        "kimi-k2.5": "moonshotai/kimi-k2.5",
        "deepseek": "deepseek/deepseek-chat-v3-0324",  # Alias for deepseek
        "deepseek-v3": "deepseek/deepseek-chat-v3-0324",
        "deepseek-r1": "deepseek/deepseek-r1",  # SLOW: reasoning model
        "mistral-large": "mistralai/mistral-large-2411",
        "gemini-pro": "google/gemini-2.5-pro-preview-06-05",
        # Anthropic via OpenRouter
        "claude-haiku": "anthropic/claude-3.5-haiku",
        "claude-sonnet": "anthropic/claude-3.5-sonnet",
        "claude-opus": "anthropic/claude-3-opus",
    }

    def __init__(self, config: ProviderConfig | None = None):
        """Initialize the OpenRouter provider.

        Args:
            config: Optional provider configuration.
        """
        self._config = config or ProviderConfig()
        self._client = None

    def _get_client(self):
        """Lazy-load the HTTP client."""
        if self._client is None:
            api_key = self._config.api_key or os.environ.get("OPENROUTER_API_KEY")
            if not api_key:
                raise RuntimeError(
                    "OPENROUTER_API_KEY environment variable not set. "
                    "Set it in your environment or pass it in ProviderConfig."
                )

            try:
                import httpx
            except ImportError:
                raise RuntimeError(
                    "httpx package not installed. Run: pip install httpx"
                )

            # Use longer default timeout for OpenRouter
            timeout = self._config.timeout
            if timeout == 60.0:  # Default from ProviderConfig
                timeout = self.DEFAULT_TIMEOUT

            self._client = httpx.Client(
                base_url=self._config.base_url or self.BASE_URL,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "HTTP-Referer": "https://github.com/cuttle-simulation",
                    "X-Title": "Cuttle Simulation",
                },
                timeout=timeout,
            )
        return self._client

    @property
    def name(self) -> str:
        return "openrouter"

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
        """Send a completion request to OpenRouter.

        Args:
            prompt: The prompt to send.
            model: Model name or alias.
            temperature: Sampling temperature.
            max_tokens: Maximum tokens in response.
            **kwargs: Additional parameters.

        Returns:
            LLMResponse with content and token usage.
        """
        # Resolve model alias
        resolved_model = self.AVAILABLE_MODELS.get(model.lower(), model)

        client = self._get_client()

        # Use extended timeout for slow reasoning models
        request_timeout = None
        if resolved_model in self.SLOW_MODELS:
            request_timeout = self.SLOW_MODEL_TIMEOUT

        start_time = time.perf_counter()

        response = client.post(
            "/chat/completions",
            json={
                "model": resolved_model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": temperature,
                "max_tokens": max_tokens,
            },
            timeout=request_timeout,  # Override timeout for slow models
        )
        response.raise_for_status()
        data = response.json()

        latency_ms = (time.perf_counter() - start_time) * 1000

        # Extract content and usage
        content = data["choices"][0]["message"]["content"].strip()
        usage = data.get("usage", {})

        return LLMResponse(
            content=content,
            input_tokens=usage.get("prompt_tokens", 0),
            output_tokens=usage.get("completion_tokens", 0),
            model=resolved_model,
            latency_ms=latency_ms,
            raw_response=data,
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
        """Check if OpenRouter API key is available."""
        api_key = self._config.api_key or os.environ.get("OPENROUTER_API_KEY")
        return api_key is not None


# Convenience aliases for common models
# Fast models (recommended for interactive play)
QWEN2_72B = "qwen/qwen-2.5-72b-instruct"
LLAMA4_MAVERICK = "meta-llama/llama-4-maverick"
GEMINI_FLASH = "google/gemini-2.0-flash-001"
LLAMA_70B = "meta-llama/llama-3.3-70b-instruct"

# Slow models (high quality but 30-60s per move)
QWEN3 = "qwen/qwen3-235b-a22b"
DEEPSEEK_R1 = "deepseek/deepseek-r1"
KIMI_K2 = "moonshotai/kimi-k2.5"
DEEPSEEK_V3 = "deepseek/deepseek-chat-v3-0324"
