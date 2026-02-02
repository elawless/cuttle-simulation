"""Base strategy interface for Cuttle players."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from cuttle_engine.moves import Move
    from cuttle_engine.state import GameState


class Strategy(ABC):
    """Abstract base class for player strategies."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable name for this strategy."""
        ...

    @abstractmethod
    def select_move(self, state: GameState, legal_moves: list[Move]) -> Move:
        """Select a move from the list of legal moves.

        Args:
            state: Current game state.
            legal_moves: List of all legal moves for the current situation.

        Returns:
            The selected move.
        """
        ...

    def on_game_start(self, state: GameState, player_index: int) -> None:
        """Called when a game starts.

        Override to initialize per-game state.

        Args:
            state: Initial game state.
            player_index: Which player this strategy controls (0 or 1).
        """
        pass

    def on_game_end(self, state: GameState, winner: int | None) -> None:
        """Called when a game ends.

        Override to handle end-of-game cleanup or learning.

        Args:
            state: Final game state.
            winner: 0, 1, or None for draw.
        """
        pass

    def on_move_made(self, state: GameState, move: Move, player: int) -> None:
        """Called after any move is made (by either player).

        Override to track game history.

        Args:
            state: State after the move.
            move: The move that was made.
            player: Which player made the move.
        """
        pass
