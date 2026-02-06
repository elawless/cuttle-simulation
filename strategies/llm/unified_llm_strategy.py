"""Unified LLM strategy that works with any provider."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from strategies.base import Strategy
from strategies.llm.base import LLMProvider, LLMResponse

if TYPE_CHECKING:
    from cuttle_engine.moves import Move
    from cuttle_engine.state import GameState
    from core.cost_tracker import CostTracker

logger = logging.getLogger(__name__)


@dataclass
class LLMThinking:
    """Captures the LLM's reasoning process."""
    prompt: str
    response: str
    model: str
    provider: str
    chosen_move_index: int
    chosen_move_description: str
    input_tokens: int
    output_tokens: int
    latency_ms: float
    cost_usd: float
    error: str | None = None


class UnifiedLLMStrategy(Strategy):
    """Strategy that uses any LLM provider to select moves.

    Supports Anthropic, OpenRouter, and Ollama providers through
    a unified interface.
    """

    def __init__(
        self,
        provider: LLMProvider,
        model: str,
        temperature: float = 0.3,
        max_tokens: int = 1024,
        cost_tracker: "CostTracker | None" = None,
    ):
        """Initialize the unified LLM strategy.

        Args:
            provider: LLM provider instance.
            model: Model name or alias.
            temperature: Sampling temperature (0-1).
            max_tokens: Maximum tokens in response.
            cost_tracker: Optional cost tracker for budget enforcement.
        """
        self._provider = provider
        self._provider_name = provider.name
        self._model = model
        self._temperature = temperature
        self._max_tokens = max_tokens
        self._cost_tracker = cost_tracker
        self._player_index: int | None = None
        self._last_thinking: LLMThinking | None = None

    @property
    def name(self) -> str:
        return f"LLM-{self._provider_name}-{self._model}"

    @property
    def last_thinking(self) -> LLMThinking | None:
        """Get the last thinking/reasoning from the LLM."""
        return self._last_thinking

    def on_game_start(self, state: "GameState", player_index: int) -> None:
        """Remember which player we are."""
        self._player_index = player_index
        self._last_thinking = None

    def select_move(
        self,
        state: "GameState",
        legal_moves: list["Move"],
    ) -> "Move":
        """Select a move using the LLM provider."""
        if not legal_moves:
            raise ValueError("No legal moves available")

        # If only one move, just play it
        if len(legal_moves) == 1:
            self._last_thinking = LLMThinking(
                prompt="(Only one legal move)",
                response="Auto-selected",
                model=self._model,
                provider=self._provider_name,
                chosen_move_index=0,
                chosen_move_description=str(legal_moves[0]),
                input_tokens=0,
                output_tokens=0,
                latency_ms=0,
                cost_usd=0,
            )
            return legal_moves[0]

        # Build the prompt
        prompt = self._build_prompt(state, legal_moves)
        response_text = ""
        error_msg = None
        response: LLMResponse | None = None

        try:
            logger.info(f"LLM API call: provider={self._provider_name}, model={self._model}")

            response = self._provider.complete(
                prompt=prompt,
                model=self._model,
                temperature=self._temperature,
                max_tokens=self._max_tokens,
            )

            response_text = response.content
            logger.info(f"LLM response received in {response.latency_ms:.0f}ms")

            # Track cost if tracker provided
            if self._cost_tracker:
                self._cost_tracker.record_cost(
                    provider=self._provider_name,
                    model=response.model,
                    input_tokens=response.input_tokens,
                    output_tokens=response.output_tokens,
                )

            # Parse the response to get move index
            move_index = self._parse_move_index(response_text, len(legal_moves))

            # Calculate cost
            cost_usd = self._provider.estimate_cost(
                self._model, response.input_tokens, response.output_tokens
            )

            self._last_thinking = LLMThinking(
                prompt=prompt,
                response=response_text,
                model=response.model,
                provider=self._provider_name,
                chosen_move_index=move_index,
                chosen_move_description=str(legal_moves[move_index]),
                input_tokens=response.input_tokens,
                output_tokens=response.output_tokens,
                latency_ms=response.latency_ms,
                cost_usd=cost_usd,
            )

            return legal_moves[move_index]

        except Exception as e:
            error_msg = str(e)
            logger.error(f"LLM error: {e}, falling back to first legal move")

            # Get token counts from response if available
            input_tokens = response.input_tokens if response else 0
            output_tokens = response.output_tokens if response else 0
            latency_ms = response.latency_ms if response else 0

            self._last_thinking = LLMThinking(
                prompt=prompt,
                response=response_text or "(no response)",
                model=self._model,
                provider=self._provider_name,
                chosen_move_index=0,
                chosen_move_description=str(legal_moves[0]),
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                latency_ms=latency_ms,
                cost_usd=0,
                error=error_msg,
            )

            return legal_moves[0]

    def _build_prompt(
        self,
        state: "GameState",
        legal_moves: list["Move"],
    ) -> str:
        """Build the prompt for the LLM."""
        player = self._player_index or state.current_player
        opponent = 1 - player
        my_state = state.players[player]
        opp_state = state.players[opponent]

        lines = [
            "Cuttle game. You need to reach your point threshold to win.",
            "",
            f"YOU: {my_state.point_total}/{state.point_threshold(player)} pts | Hand: {', '.join(str(c) for c in my_state.hand) or 'empty'}",
            f"  Field: {', '.join(str(c) for c in my_state.points_field) or 'none'} | Perms: {', '.join(str(c) for c in my_state.permanents) or 'none'}",
            "",
            f"OPP: {opp_state.point_total}/{state.point_threshold(opponent)} pts | {len(opp_state.hand)} cards in hand",
            f"  Field: {', '.join(str(c) for c in opp_state.points_field) or 'none'} | Perms: {', '.join(str(c) for c in opp_state.permanents) or 'none'}",
            "",
            f"Deck: {len(state.deck)} | Turn {state.turn_number} | {state.phase.name}",
            "",
            "Moves:",
        ]

        for i, move in enumerate(legal_moves):
            lines.append(f"  {i}: {move}")

        lines.extend([
            "",
            "Analyze briefly, then end with MOVE: <number>",
            "You MUST include 'MOVE: X' where X is the move number.",
        ])

        return "\n".join(lines)

    def _parse_move_index(self, response: str, max_index: int) -> int:
        """Parse the move index from the LLM response."""
        # First, look for explicit "MOVE: X" pattern
        move_match = re.search(r'MOVE:\s*(\d+)', response, re.IGNORECASE)
        if move_match:
            index = int(move_match.group(1))
            if 0 <= index < max_index:
                return index

        # Look for "move X" or "choose X" or "select X" patterns
        choice_match = re.search(
            r'(?:move|choose|select|pick|play)\s*(?:number\s*)?(\d+)',
            response,
            re.IGNORECASE,
        )
        if choice_match:
            index = int(choice_match.group(1))
            if 0 <= index < max_index:
                return index

        # Look for "X:" at start of line (move number reference)
        line_match = re.search(r'^\s*(\d+):', response, re.MULTILINE)
        if line_match:
            index = int(line_match.group(1))
            if 0 <= index < max_index:
                return index

        # Last resort: find the last number mentioned that's a valid move index
        numbers = re.findall(r'\b(\d+)\b', response)
        for num_str in reversed(numbers):
            index = int(num_str)
            if 0 <= index < max_index:
                return index

        # Default to 0 if parsing fails
        return 0


def create_llm_strategy(
    provider: str,
    model: str,
    temperature: float = 0.3,
    cost_tracker: "CostTracker | None" = None,
    **provider_kwargs: Any,
) -> UnifiedLLMStrategy:
    """Factory function to create an LLM strategy.

    Args:
        provider: Provider name ('anthropic', 'openrouter', 'ollama').
        model: Model name or alias.
        temperature: Sampling temperature.
        cost_tracker: Optional cost tracker.
        **provider_kwargs: Additional provider configuration.

    Returns:
        Configured UnifiedLLMStrategy.
    """
    from strategies.llm.base import ProviderConfig

    config = ProviderConfig(**provider_kwargs) if provider_kwargs else None

    if provider == "anthropic":
        from strategies.llm.anthropic_provider import AnthropicProvider
        llm_provider = AnthropicProvider(config)
    elif provider == "openrouter":
        from strategies.llm.openrouter_provider import OpenRouterProvider
        llm_provider = OpenRouterProvider(config)
    elif provider == "ollama":
        from strategies.llm.ollama_provider import OllamaProvider
        llm_provider = OllamaProvider(config)
    else:
        raise ValueError(f"Unknown provider: {provider}")

    return UnifiedLLMStrategy(
        provider=llm_provider,
        model=model,
        temperature=temperature,
        cost_tracker=cost_tracker,
    )
