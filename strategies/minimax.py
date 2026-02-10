"""Minimax strategy for Cuttle."""

from __future__ import annotations

import random
from typing import TYPE_CHECKING

from cuttle_engine.executor import execute_move
from cuttle_engine.move_generator import generate_legal_moves
from strategies.base import Strategy

if TYPE_CHECKING:
    from cuttle_engine.moves import Move
    from cuttle_engine.state import GameState


class MinimaxStrategy(Strategy):
    """Minimax AI with configurable depth (default 2, like cuttle.cards)."""

    name = "minimax"

    def __init__(self, depth: int = 2, seed: int | None = None):
        """Initialize the Minimax strategy.

        Args:
            depth: Search depth (default 2, matching cuttle.cards)
            seed: Random seed for tie-breaking
        """
        self._depth = depth
        self._rng = random.Random(seed)

    def select_move(
        self, state: GameState, legal_moves: list[Move]
    ) -> Move | None:
        """Select the best move using minimax search."""
        if not legal_moves:
            return None

        player = state.current_player
        best_score = float("-inf")
        best_moves: list[Move] = []

        for move in legal_moves:
            try:
                new_state = execute_move(state, move)
                score = self._minimax(
                    new_state, self._depth - 1, float("-inf"), float("inf"), False, player
                )
            except Exception:
                continue  # Skip invalid moves

            if score > best_score:
                best_score = score
                best_moves = [move]
            elif score == best_score:
                best_moves.append(move)

        return self._rng.choice(best_moves) if best_moves else legal_moves[0]

    def _minimax(
        self,
        state: GameState,
        depth: int,
        alpha: float,
        beta: float,
        maximizing: bool,
        player: int,
    ) -> float:
        """Minimax search with alpha-beta pruning.

        Args:
            state: Current game state
            depth: Remaining search depth
            alpha: Alpha value for pruning
            beta: Beta value for pruning
            maximizing: Whether this is a maximizing node
            player: The player we're optimizing for

        Returns:
            The minimax value of the state
        """
        # Terminal state check
        if state.winner is not None:
            return 1000.0 if state.winner == player else -1000.0

        # Depth limit reached
        if depth == 0:
            return self._evaluate(state, player)

        moves = generate_legal_moves(state)
        if not moves:
            return self._evaluate(state, player)

        if maximizing:
            value = float("-inf")
            for move in moves:
                try:
                    new_state = execute_move(state, move)
                    value = max(
                        value,
                        self._minimax(new_state, depth - 1, alpha, beta, False, player),
                    )
                    alpha = max(alpha, value)
                    if beta <= alpha:
                        break  # Beta cutoff
                except Exception:
                    continue
            return value
        else:
            value = float("inf")
            for move in moves:
                try:
                    new_state = execute_move(state, move)
                    value = min(
                        value,
                        self._minimax(new_state, depth - 1, alpha, beta, True, player),
                    )
                    beta = min(beta, value)
                    if beta <= alpha:
                        break  # Alpha cutoff
                except Exception:
                    continue
            return value

    def _evaluate(self, state: GameState, player: int) -> float:
        """Evaluate the state from the perspective of the given player.

        Heuristic inspired by cuttle.cards bot.
        """
        my_score = self._player_score(state, player)
        opp_score = self._player_score(state, 1 - player)
        # Small bonus for having the turn
        turn_bonus = 0.5 if state.current_player == player else -0.5
        return my_score - opp_score + turn_bonus

    def _player_score(self, state: GameState, player: int) -> float:
        """Calculate a heuristic score for a player's position."""
        p = state.players[player]
        score = 0.0

        # Hand size matters for options
        score += len(p.hand)

        # Points are very valuable (doubled weight)
        score += sum(c.rank for c in p.points_field) * 2

        # Jacks count as points (the stolen card value)
        for _, stolen in p.jacks:
            score += stolen.rank * 2

        # Permanents have value
        score += len(p.permanents) * 2
        score += len(p.jacks) * 2

        # Penalties for redundant permanents
        queens = sum(1 for c in p.permanents if c.rank == 12)
        if queens > 2:
            score -= (queens - 2) * 2  # Extra queens less useful

        glasses = sum(1 for c in p.permanents if c.rank == 8)
        if glasses > 1:
            score -= (glasses - 1) * 2  # Extra glasses useless

        # Kings are valuable for threshold reduction
        kings = sum(1 for c in p.permanents if c.rank == 13)
        score += kings * 3  # Extra value for kings

        return score

    def get_identity_params(self) -> dict:
        """Return parameters that identify this strategy configuration."""
        return {"depth": self._depth}
