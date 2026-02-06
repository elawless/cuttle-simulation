"""LLM-based strategies for Cuttle.

Supports multiple providers:
- Anthropic (Claude models)
- OpenRouter (Qwen, Kimi, Llama, DeepSeek, etc.)
- Ollama (local models)
"""

from strategies.llm.base import LLMProvider, LLMResponse, ProviderConfig
from strategies.llm.anthropic_provider import AnthropicProvider
from strategies.llm.openrouter_provider import OpenRouterProvider
from strategies.llm.ollama_provider import OllamaProvider
from strategies.llm.unified_llm_strategy import (
    UnifiedLLMStrategy,
    LLMThinking,
    create_llm_strategy,
)

__all__ = [
    # Base classes
    "LLMProvider",
    "LLMResponse",
    "ProviderConfig",
    # Providers
    "AnthropicProvider",
    "OpenRouterProvider",
    "OllamaProvider",
    # Strategy
    "UnifiedLLMStrategy",
    "LLMThinking",
    "create_llm_strategy",
]
