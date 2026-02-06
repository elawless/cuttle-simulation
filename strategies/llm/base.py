"""Base classes for LLM provider abstraction."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass
class LLMResponse:
    """Response from an LLM provider."""
    content: str
    input_tokens: int
    output_tokens: int
    model: str
    latency_ms: float
    raw_response: Any = None  # Provider-specific response object


class LLMProvider(ABC):
    """Abstract base class for LLM providers."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Provider name (e.g., 'anthropic', 'openrouter')."""
        ...

    @abstractmethod
    def complete(
        self,
        prompt: str,
        model: str,
        temperature: float = 0.3,
        max_tokens: int = 1024,
        **kwargs: Any,
    ) -> LLMResponse:
        """Send a completion request to the provider.

        Args:
            prompt: The prompt to send.
            model: Model name.
            temperature: Sampling temperature.
            max_tokens: Maximum tokens in response.
            **kwargs: Additional provider-specific parameters.

        Returns:
            LLMResponse with content and token usage.
        """
        ...

    @abstractmethod
    def estimate_cost(
        self,
        model: str,
        input_tokens: int,
        output_tokens: int,
    ) -> float:
        """Estimate cost for a request.

        Args:
            model: Model name.
            input_tokens: Number of input tokens.
            output_tokens: Number of output tokens.

        Returns:
            Estimated cost in USD.
        """
        ...

    @property
    @abstractmethod
    def available_models(self) -> list[str]:
        """List of available models for this provider."""
        ...

    def is_available(self) -> bool:
        """Check if the provider is available (has API key, etc.)."""
        return True


@dataclass
class ProviderConfig:
    """Configuration for an LLM provider."""
    api_key: str | None = None
    base_url: str | None = None
    timeout: float = 60.0
    extra: dict[str, Any] | None = None
