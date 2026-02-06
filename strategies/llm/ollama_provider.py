"""Ollama provider implementation for local models."""

from __future__ import annotations

import os
import time
from typing import Any

from strategies.llm.base import LLMProvider, LLMResponse, ProviderConfig


class OllamaProvider(LLMProvider):
    """LLM provider for local Ollama models.

    Ollama runs models locally, so there's no API cost.
    """

    DEFAULT_HOST = "http://localhost:11434"

    # Common Ollama models
    AVAILABLE_MODELS = {
        "llama3.3": "llama3.3",
        "llama3": "llama3",
        "qwen2.5": "qwen2.5",
        "mistral": "mistral",
        "gemma2": "gemma2",
        "phi3": "phi3",
        "codellama": "codellama",
    }

    def __init__(self, config: ProviderConfig | None = None):
        """Initialize the Ollama provider.

        Args:
            config: Optional provider configuration.
        """
        self._config = config or ProviderConfig()
        self._client = None

    def _get_client(self):
        """Lazy-load the HTTP client."""
        if self._client is None:
            try:
                import httpx
            except ImportError:
                raise RuntimeError(
                    "httpx package not installed. Run: pip install httpx"
                )

            host = (
                self._config.base_url
                or os.environ.get("OLLAMA_HOST")
                or self.DEFAULT_HOST
            )

            self._client = httpx.Client(
                base_url=host,
                timeout=self._config.timeout or 120.0,  # Local models can be slower
            )
        return self._client

    @property
    def name(self) -> str:
        return "ollama"

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
        """Send a completion request to Ollama.

        Args:
            prompt: The prompt to send.
            model: Model name.
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

        response = client.post(
            "/api/generate",
            json={
                "model": resolved_model,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": temperature,
                    "num_predict": max_tokens,
                },
            },
        )
        response.raise_for_status()
        data = response.json()

        latency_ms = (time.perf_counter() - start_time) * 1000

        # Extract content and estimate token usage
        content = data.get("response", "").strip()

        # Ollama provides token counts
        prompt_tokens = data.get("prompt_eval_count", 0)
        completion_tokens = data.get("eval_count", 0)

        return LLMResponse(
            content=content,
            input_tokens=prompt_tokens,
            output_tokens=completion_tokens,
            model=f"ollama/{resolved_model}",
            latency_ms=latency_ms,
            raw_response=data,
        )

    def estimate_cost(
        self,
        model: str,
        input_tokens: int,
        output_tokens: int,
    ) -> float:
        """Ollama is free (local models)."""
        return 0.0

    def is_available(self) -> bool:
        """Check if Ollama server is accessible."""
        try:
            client = self._get_client()
            # Try to list models
            response = client.get("/api/tags")
            return response.status_code == 200
        except Exception:
            return False

    def list_local_models(self) -> list[str]:
        """List models available on the local Ollama server."""
        try:
            client = self._get_client()
            response = client.get("/api/tags")
            response.raise_for_status()
            data = response.json()
            return [m["name"] for m in data.get("models", [])]
        except Exception:
            return []
