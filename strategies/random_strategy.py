"""Random strategy for baseline testing."""

from __future__ import annotations

import random
from typing import TYPE_CHECKING

from strategies.base import Strategy

if TYPE_CHECKING:
    from cuttle_engine.moves import Move
    from cuttle_engine.state import GameState


class RandomStrategy(Strategy):
    """Strategy that selects moves uniformly at random.

    Useful as a baseline and for smoke testing.
    """

    def __init__(self, seed: int | None = None):
        """Initialize the random strategy.

        Args:
            seed: Optional random seed for reproducibility.
        """
        self._rng = random.Random(seed)
        self._seed = seed

    @property
    def name(self) -> str:
        return "Random"

    def select_move(self, state: GameState, legal_moves: list[Move]) -> Move:
        """Select a random legal move."""
        if not legal_moves:
            raise ValueError("No legal moves available")
        return self._rng.choice(legal_moves)

    def reset_seed(self, seed: int | None = None) -> None:
        """Reset the random number generator with a new seed."""
        self._seed = seed
        self._rng = random.Random(seed)
