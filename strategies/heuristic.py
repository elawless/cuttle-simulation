"""Heuristic strategy based on point maximization and threat assessment."""

from __future__ import annotations

import random
from typing import TYPE_CHECKING

from cuttle_engine.cards import Rank
from cuttle_engine.moves import (
    Counter,
    DeclineCounter,
    Discard,
    Draw,
    MoveType,
    Pass,
    PlayOneOff,
    PlayPermanent,
    PlayPoints,
    ResolveSeven,
    Scuttle,
)
from strategies.base import Strategy

if TYPE_CHECKING:
    from cuttle_engine.moves import Move
    from cuttle_engine.state import GameState


class HeuristicStrategy(Strategy):
    """Strategy using simple heuristics for move selection.

    Priorities:
    1. Win if possible (play points to reach threshold)
    2. Counter dangerous one-offs
    3. Scuttle high-value opponent cards
    4. Play permanents (especially Queen, King)
    5. Play points
    6. Draw
    """

    def __init__(self, seed: int | None = None):
        self._rng = random.Random(seed)

    @property
    def name(self) -> str:
        return "Heuristic"

    def select_move(self, state: GameState, legal_moves: list[Move]) -> Move:
        """Select a move based on heuristic evaluation."""
        if not legal_moves:
            raise ValueError("No legal moves available")

        # Score each move
        scored_moves = [(self._score_move(state, move), move) for move in legal_moves]

        # Get best score
        best_score = max(score for score, _ in scored_moves)

        # Pick randomly among tied best moves
        best_moves = [move for score, move in scored_moves if score == best_score]
        return self._rng.choice(best_moves)

    def _score_move(self, state: GameState, move: Move) -> float:
        """Score a move (higher is better)."""
        player_idx = state.current_player

        match move:
            case PlayPoints(card=card):
                # Check if this wins the game
                current_points = state.players[player_idx].point_total
                threshold = state.point_threshold(player_idx)
                if current_points + card.point_value >= threshold:
                    return 10000  # Winning move

                # Otherwise score by point value
                return 100 + card.point_value

            case Scuttle(card=card, target=target):
                # Score by value destroyed minus value lost
                return 200 + target.point_value - card.point_value

            case PlayPermanent(card=card, target_card=target):
                if card.rank == Rank.KING:
                    # Kings are very valuable
                    return 500
                elif card.rank == Rank.QUEEN:
                    # Queens provide protection
                    return 400
                elif card.rank == Rank.JACK and target:
                    # Jacks steal points
                    return 300 + target.point_value
                elif card.rank == Rank.EIGHT:
                    return 150

            case PlayOneOff(card=card, effect=effect):
                # Score based on impact
                from cuttle_engine.moves import OneOffEffect

                if effect == OneOffEffect.ACE_SCRAP_ALL_POINTS:
                    # Good if opponent has more points
                    our_points = state.players[player_idx].point_total
                    opp_points = state.players[1 - player_idx].point_total
                    if opp_points > our_points:
                        return 250
                    return 50  # Risky if we have more

                elif effect == OneOffEffect.TWO_DESTROY_PERMANENT:
                    # Very good to destroy Queen/King
                    return 200

                elif effect == OneOffEffect.FOUR_DISCARD:
                    return 150

                elif effect == OneOffEffect.FIVE_DRAW_TWO:
                    return 100

                elif effect == OneOffEffect.SIX_SCRAP_ALL_PERMANENTS:
                    # Good if opponent has more permanents
                    our_perms = len(state.players[player_idx].permanents)
                    opp_perms = len(state.players[1 - player_idx].permanents)
                    if opp_perms > our_perms:
                        return 200
                    return 30

                return 80

            case Counter(card=card):
                # Usually good to counter
                return 300

            case DeclineCounter():
                # Depends on what's being countered
                if state.counter_state:
                    # If we're about to get hit, decline is bad
                    if state.counter_state.resolves:
                        return -100  # Effect will happen
                    return 50  # Effect will be countered
                return 0

            case Draw():
                return 50

            case Pass():
                return 0

            case Discard(card=card):
                # Prefer discarding low-value cards
                return 10 - card.point_value

            case ResolveSeven(card=card, play_as=play_as):
                # Similar to regular plays
                if play_as == MoveType.PLAY_POINTS:
                    return 100 + card.point_value
                elif play_as == MoveType.PLAY_PERMANENT:
                    return 150
                return 80

        return 0
