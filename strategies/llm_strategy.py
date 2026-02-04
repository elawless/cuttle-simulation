"""LLM-based strategy for Cuttle using Claude models."""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from strategies.base import Strategy

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from cuttle_engine.moves import Move
    from cuttle_engine.state import GameState


@dataclass
class LLMThinking:
    """Captures the LLM's reasoning process."""
    prompt: str
    response: str
    model: str
    chosen_move_index: int
    chosen_move_description: str
    error: str | None = None


class LLMStrategy(Strategy):
    """Strategy that uses Claude LLM to select moves."""

    AVAILABLE_MODELS = {
        "haiku": "claude-3-5-haiku-latest",
        "sonnet": "claude-sonnet-4-20250514",
        "opus": "claude-opus-4-20250514",
    }

    def __init__(self, model: str = "haiku", temperature: float = 0.3):
        """Initialize the LLM strategy.

        Args:
            model: Model name ("haiku", "sonnet", "opus")
            temperature: Sampling temperature (0-1)
        """
        self._model_key = model.lower()
        self._model_id = self.AVAILABLE_MODELS.get(self._model_key, model)
        self._temperature = temperature
        self._client = None
        self._player_index: int | None = None
        self._last_thinking: LLMThinking | None = None

    def _get_client(self):
        """Lazy-load the Anthropic client."""
        if self._client is None:
            import os

            api_key = os.environ.get("ANTHROPIC_API_KEY")
            if not api_key:
                raise RuntimeError(
                    "ANTHROPIC_API_KEY environment variable not set. "
                    "Set it before starting the server: export ANTHROPIC_API_KEY=your-key"
                )

            try:
                import anthropic
                self._client = anthropic.Anthropic(api_key=api_key)
            except ImportError:
                raise RuntimeError("anthropic package not installed. Run: pip install anthropic")
        return self._client

    @property
    def name(self) -> str:
        return f"LLM-{self._model_key.capitalize()}"

    @property
    def last_thinking(self) -> LLMThinking | None:
        """Get the last thinking/reasoning from the LLM."""
        return self._last_thinking

    def on_game_start(self, state: GameState, player_index: int) -> None:
        """Remember which player we are."""
        self._player_index = player_index
        self._last_thinking = None

    def select_move(self, state: GameState, legal_moves: list[Move]) -> Move:
        """Select a move using the LLM."""
        if not legal_moves:
            raise ValueError("No legal moves available")

        # If only one move, just play it
        if len(legal_moves) == 1:
            self._last_thinking = LLMThinking(
                prompt="(Only one legal move)",
                response="Auto-selected",
                model=self._model_id,
                chosen_move_index=0,
                chosen_move_description=str(legal_moves[0]),
            )
            return legal_moves[0]

        # Build the prompt
        prompt = self._build_prompt(state, legal_moves)
        response_text = ""
        error_msg = None

        try:
            client = self._get_client()

            logger.info(f"LLM API call starting: model={self._model_id}")
            api_start = time.time()

            response = client.messages.create(
                model=self._model_id,
                max_tokens=1024,
                temperature=self._temperature,
                messages=[{"role": "user", "content": prompt}],
            )

            api_elapsed = time.time() - api_start
            logger.info(f"LLM API call completed in {api_elapsed:.2f}s")

            # Parse the response to get move index
            response_text = response.content[0].text.strip()
            move_index = self._parse_move_index(response_text, len(legal_moves))

            self._last_thinking = LLMThinking(
                prompt=prompt,
                response=response_text,
                model=self._model_id,
                chosen_move_index=move_index,
                chosen_move_description=str(legal_moves[move_index]),
            )

            return legal_moves[move_index]

        except Exception as e:
            error_msg = str(e)
            print(f"LLM error: {e}, falling back to first legal move")

            self._last_thinking = LLMThinking(
                prompt=prompt,
                response=response_text or "(no response)",
                model=self._model_id,
                chosen_move_index=0,
                chosen_move_description=str(legal_moves[0]),
                error=error_msg,
            )

            return legal_moves[0]

    def _build_prompt(self, state: GameState, legal_moves: list[Move]) -> str:
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
        import re

        # First, look for explicit "MOVE: X" pattern
        move_match = re.search(r'MOVE:\s*(\d+)', response, re.IGNORECASE)
        if move_match:
            index = int(move_match.group(1))
            if 0 <= index < max_index:
                return index

        # Look for "move X" or "choose X" or "select X" patterns
        choice_match = re.search(r'(?:move|choose|select|pick|play)\s*(?:number\s*)?(\d+)', response, re.IGNORECASE)
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
