"""Player identity system for uniquely identifying strategy configurations."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from strategies.base import Strategy


@dataclass(frozen=True)
class PlayerIdentity:
    """Immutable identity for a player/strategy configuration.

    Generates a unique ID from the hash of provider:model:params.
    """

    provider: str
    model_name: str
    params: frozenset[tuple[str, Any]]

    @property
    def id(self) -> str:
        """Generate unique SHA256 hash ID from identity components."""
        # Sort params for deterministic ordering
        sorted_params = sorted(self.params)
        identity_str = f"{self.provider}:{self.model_name}:{json.dumps(sorted_params)}"
        return hashlib.sha256(identity_str.encode()).hexdigest()[:16]

    @property
    def display_name(self) -> str:
        """Human-readable display name."""
        if self.provider == "human":
            return self.model_name  # model_name stores the username for humans
        if self.provider == "heuristic":
            # model_name contains version info like "heuristic-v1"
            base = self.model_name if "-" in self.model_name else "heuristic-v1"
            if self.params:
                param_str = ", ".join(f"{k}={v}" for k, v in sorted(self.params))
                return f"{base}({param_str})"
            return base
        if self.provider in ("mcts", "random"):
            if self.params:
                param_str = ", ".join(f"{k}={v}" for k, v in sorted(self.params))
                return f"{self.provider}({param_str})"
            return self.provider
        return f"{self.provider}/{self.model_name}"

    @property
    def params_dict(self) -> dict[str, Any]:
        """Convert params frozenset back to dict."""
        return dict(self.params)

    @classmethod
    def from_human(cls, username: str) -> "PlayerIdentity":
        """Create identity for a human player.

        Args:
            username: The human player's username.

        Returns:
            PlayerIdentity for the human player.
        """
        return cls(
            provider="human",
            model_name=username.strip().lower(),
            params=frozenset(),
        )

    @classmethod
    def from_strategy(cls, strategy: "Strategy") -> "PlayerIdentity":
        """Extract identity from a strategy instance.

        Args:
            strategy: The strategy instance to extract identity from.

        Returns:
            PlayerIdentity for the strategy.
        """
        strategy_name = strategy.name.lower()

        # Handle MCTS strategies
        if "mcts" in strategy_name:
            provider = "mcts"
            model_name = "mcts"
            params = {}

            # Extract MCTS-specific parameters
            if hasattr(strategy, "_iterations"):
                params["iterations"] = strategy._iterations
            if hasattr(strategy, "_exploration"):
                params["exploration"] = round(strategy._exploration, 4)
            if hasattr(strategy, "_num_workers"):
                params["num_workers"] = strategy._num_workers

            return cls(
                provider=provider,
                model_name=model_name,
                params=frozenset(params.items()),
            )

        # Handle ISMCTS
        if "ismcts" in strategy_name:
            provider = "ismcts"
            model_name = "ismcts"
            params = {}

            if hasattr(strategy, "_iterations"):
                params["iterations"] = strategy._iterations
            if hasattr(strategy, "_exploration_constant"):
                params["exploration"] = round(strategy._exploration_constant, 4)

            return cls(
                provider=provider,
                model_name=model_name,
                params=frozenset(params.items()),
            )

        # Handle Heuristic
        if "heuristic" in strategy_name:
            params = {}
            if hasattr(strategy, "_seed") and strategy._seed is not None:
                params["seed"] = strategy._seed
            # Include version in model_name for tracking
            version = getattr(strategy, "_version", "v1")
            model_name = f"heuristic-{version}"

            return cls(
                provider="heuristic",
                model_name=model_name,
                params=frozenset(params.items()),
            )

        # Handle Random
        if "random" in strategy_name:
            params = {}
            if hasattr(strategy, "_seed") and strategy._seed is not None:
                params["seed"] = strategy._seed

            return cls(
                provider="random",
                model_name="random",
                params=frozenset(params.items()),
            )

        # Handle LLM strategies (Anthropic)
        if "llm" in strategy_name:
            provider = "anthropic"
            model_name = getattr(strategy, "_model_id", "unknown")
            params = {}

            if hasattr(strategy, "_temperature"):
                params["temperature"] = strategy._temperature

            return cls(
                provider=provider,
                model_name=model_name,
                params=frozenset(params.items()),
            )

        # Handle UnifiedLLMStrategy
        if hasattr(strategy, "_provider_name"):
            provider = strategy._provider_name
            model_name = getattr(strategy, "_model", "unknown")
            params = {}

            if hasattr(strategy, "_temperature"):
                params["temperature"] = strategy._temperature

            return cls(
                provider=provider,
                model_name=model_name,
                params=frozenset(params.items()),
            )

        # Fallback for unknown strategies
        return cls(
            provider="unknown",
            model_name=strategy_name,
            params=frozenset(),
        )

    @classmethod
    def from_config(
        cls,
        provider: str,
        model_name: str,
        params: dict[str, Any] | None = None,
    ) -> "PlayerIdentity":
        """Create identity from configuration values.

        Args:
            provider: Provider name (e.g., 'anthropic', 'openrouter', 'mcts').
            model_name: Model name.
            params: Optional parameters dict.

        Returns:
            PlayerIdentity instance.
        """
        return cls(
            provider=provider,
            model_name=model_name,
            params=frozenset((params or {}).items()),
        )

    def __str__(self) -> str:
        return self.display_name

    def __repr__(self) -> str:
        return f"PlayerIdentity(id={self.id}, name={self.display_name})"
