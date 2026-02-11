"""Minimax strategy for Cuttle with glasses-aware evaluation."""

from __future__ import annotations

import random
from typing import TYPE_CHECKING

from cuttle_engine.executor import execute_move
from cuttle_engine.move_generator import generate_legal_moves
from strategies.base import Strategy
from strategies.knowledge import (
    KnowledgeTracker,
    MemoryLevel,
    analyze_known_hand,
    get_unknown_card_count,
)

if TYPE_CHECKING:
    from cuttle_engine.cards import Card
    from cuttle_engine.moves import Move
    from cuttle_engine.state import GameState


class MinimaxStrategy(Strategy):
    """Minimax AI with configurable depth and glasses-aware evaluation.

    When the player has Glasses (8 as permanent), or remembers seeing
    opponent's hand, the evaluation function uses this knowledge to make
    better decisions.

    Memory Levels:
    - PERFECT: Remember all seen cards until they leave opponent's hand
    - TURN_LIMITED: Remember cards for N turns after seeing them
    - PROBABILISTIC: Chance to forget cards each turn
    - NONE: No memory, only use current Glasses visibility
    """

    def __init__(
        self,
        depth: int = 2,
        seed: int | None = None,
        memory_level: MemoryLevel = MemoryLevel.PERFECT,
        memory_turns: int = 3,
        forget_probability: float = 0.3,
    ):
        """Initialize the Minimax strategy.

        Args:
            depth: Search depth (default 2, matching cuttle.cards)
            seed: Random seed for tie-breaking and probabilistic forgetting
            memory_level: How much to remember about opponent's hand
            memory_turns: For TURN_LIMITED, how many turns to remember
            forget_probability: For PROBABILISTIC, chance to forget per turn
        """
        self._depth = depth
        self._rng = random.Random(seed)
        self._seed = seed
        self._memory_level = memory_level
        self._memory_turns = memory_turns
        self._forget_probability = forget_probability
        # Knowledge tracker (initialized on game start)
        self._knowledge: KnowledgeTracker | None = None
        self._player_idx: int | None = None

    @property
    def name(self) -> str:
        mem_suffix = ""
        if self._memory_level != MemoryLevel.NONE:
            mem_suffix = f"-mem:{self._memory_level.name.lower()}"
        return f"minimax-d{self._depth}{mem_suffix}"

    def on_game_start(self, state: GameState, player_idx: int) -> None:
        """Initialize knowledge tracker for new game."""
        self._player_idx = player_idx
        self._knowledge = KnowledgeTracker.create(
            player_idx=player_idx,
            memory_level=self._memory_level,
            memory_turns=self._memory_turns,
            forget_probability=self._forget_probability,
            seed=self._seed,
        )

    def select_move(
        self, state: GameState, legal_moves: list[Move]
    ) -> Move | None:
        """Select the best move using minimax search."""
        if not legal_moves:
            return None

        player = state.current_player

        # Lazy initialize knowledge tracker if not done via on_game_start
        if self._knowledge is None or self._player_idx != player:
            self._player_idx = player
            self._knowledge = KnowledgeTracker.create(
                player_idx=player,
                memory_level=self._memory_level,
                memory_turns=self._memory_turns,
                forget_probability=self._forget_probability,
                seed=self._seed,
            )

        # Update knowledge from current state
        self._knowledge.update_from_state(state)

        # Get current knowledge for evaluation
        known_cards = self._knowledge.get_known_opponent_cards()

        best_score = float("-inf")
        best_moves: list[Move] = []

        for move in legal_moves:
            try:
                new_state = execute_move(state, move)
                score = self._minimax(
                    new_state, self._depth - 1, float("-inf"), float("inf"),
                    False, player, known_cards
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
        known_cards: frozenset[Card],
    ) -> float:
        """Minimax search with alpha-beta pruning.

        Args:
            state: Current game state
            depth: Remaining search depth
            alpha: Alpha value for pruning
            beta: Beta value for pruning
            maximizing: Whether this is a maximizing node
            player: The player we're optimizing for
            known_cards: Cards we know are in opponent's hand

        Returns:
            The minimax value of the state
        """
        # Terminal state check
        if state.winner is not None:
            return 1000.0 if state.winner == player else -1000.0

        # Depth limit reached
        if depth == 0:
            return self._evaluate(state, player, known_cards)

        moves = generate_legal_moves(state)
        if not moves:
            return self._evaluate(state, player, known_cards)

        # Update known cards - remove any cards that have left opponent's hand
        # (we can tell by checking if cards are still in opponent's hand)
        opp_hand = set(state.players[1 - player].hand)
        updated_known = frozenset(c for c in known_cards if c in opp_hand)

        if maximizing:
            value = float("-inf")
            for move in moves:
                try:
                    new_state = execute_move(state, move)
                    value = max(
                        value,
                        self._minimax(new_state, depth - 1, alpha, beta,
                                     False, player, updated_known),
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
                        self._minimax(new_state, depth - 1, alpha, beta,
                                     True, player, updated_known),
                    )
                    beta = min(beta, value)
                    if beta <= alpha:
                        break  # Alpha cutoff
                except Exception:
                    continue
            return value

    def _evaluate(
        self,
        state: GameState,
        player: int,
        known_cards: frozenset[Card] | None = None,
    ) -> float:
        """Evaluate the state from the perspective of the given player.

        When we have knowledge of opponent's hand, the evaluation includes
        bonuses for information advantage and threat awareness.
        """
        my_score = self._player_score(state, player)
        opp_score = self._player_score(state, 1 - player)
        # Small bonus for having the turn
        turn_bonus = 0.5 if state.current_player == player else -0.5

        # Knowledge-based evaluation bonus
        knowledge_bonus = 0.0
        if known_cards:
            knowledge_bonus = self._knowledge_bonus(state, player, known_cards)

        return my_score - opp_score + turn_bonus + knowledge_bonus

    def _knowledge_bonus(
        self,
        state: GameState,
        player: int,
        known_cards: frozenset[Card],
    ) -> float:
        """Calculate evaluation bonus from knowing opponent's hand.

        This method quantifies the strategic advantage of knowing what
        cards the opponent holds. Knowledge allows:
        - Safe one-off plays when opponent can't counter
        - Better protection decisions
        - Accurate threat assessment

        Args:
            state: Current game state
            player: Our player index
            known_cards: Cards we know opponent has

        Returns:
            Evaluation bonus (higher = better position due to knowledge)
        """
        from cuttle_engine.cards import Rank

        if not known_cards:
            return 0.0

        me = state.players[player]
        opp = state.players[1 - player]

        # Calculate certainty: 1.0 when we know all cards
        opp_hand_size = len(opp.hand)
        unknown_count = get_unknown_card_count(state, player, known_cards)
        certainty = 1.0 - (unknown_count / max(opp_hand_size, 1)) if opp_hand_size > 0 else 0.0

        # Analyze known cards
        analysis = analyze_known_hand(known_cards)
        bonus = 0.0

        # Bonus for knowing opponent has no counter
        if not analysis["has_counter"]:
            # Big bonus - we can safely play one-offs
            bonus += 2.0 * certainty

        # Bonus for knowing opponent's threats (allows planning)
        if analysis["has_jack"]:
            if me.point_total > 10:
                # We know to protect our high-value points
                bonus += 0.5 * certainty
        else:
            # No Jack threat - our points are safer
            if me.point_total > 0:
                bonus += 0.5 * certainty

        # Bonus for knowing opponent's max point play
        max_opp_points = analysis["max_point_play"]
        if max_opp_points <= 5:
            # Opponent has weak hand
            bonus += 1.0 * certainty
        elif max_opp_points >= 9:
            # We know they have strong cards - can plan around it
            bonus += 0.3 * certainty

        # Bonus for knowing opponent lacks key cards
        if not analysis["has_ace"]:
            if len(me.points_field) > 0 or len(me.jacks) > 0:
                # Our points are safe from mass scrap
                bonus += 0.8 * certainty

        if not analysis["has_king"]:
            # Opponent can't reduce their threshold quickly
            bonus += 0.3 * certainty

        # Bonus for knowing opponent's counter count
        if analysis["counter_count"] == 0 and certainty >= 0.8:
            # Confirmed no counters - very valuable
            bonus += 1.0
        elif analysis["counter_count"] >= 2:
            # Multiple counters - we know to be careful
            bonus += 0.2 * certainty

        # Partial knowledge is still valuable (scaled by certainty)
        base_info_bonus = 0.5 * len(known_cards) / max(opp_hand_size, 1)
        bonus += base_info_bonus * certainty

        return bonus

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
        if glasses >= 1:
            # ISMCTS-derived glasses value (Feb 2026):
            # Glasses is valuable when hand has 9/10/King for layering/timing,
            # but not when hand has Queen (protection makes info redundant)
            has_high_points = any(c.rank in (9, 10) for c in p.hand)
            has_king = any(c.rank == 13 for c in p.hand)
            has_queen = any(c.rank == 12 for c in p.hand)

            if (has_high_points or has_king) and not has_queen:
                # Layering/timing opportunity - glasses worth nearly as much as 8 points
                score += 10
            # else: glasses just gets base permanent value (2 from len(p.permanents) * 2)

        if glasses > 1:
            score -= (glasses - 1) * 2  # Extra glasses useless

        # Kings are valuable for threshold reduction
        kings = sum(1 for c in p.permanents if c.rank == 13)
        score += kings * 3  # Extra value for kings

        return score

    def get_identity_params(self) -> dict:
        """Return parameters that identify this strategy configuration."""
        return {
            "depth": self._depth,
            "memory_level": self._memory_level.name,
        }
