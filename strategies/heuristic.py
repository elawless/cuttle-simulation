"""Heuristic strategy based on MCTS-learned optimal play patterns.

This heuristic was tuned based on analysis of 1000+ MCTS games that achieved
94.9% win rate against the previous heuristic. Key insights:

1. Cuttle is a RACING game - points > control
2. High cards (8-10) should almost always be played for points
3. Scuttling is usually wrong (1-for-1 trades don't advance win condition)
4. 8 as Glasses is a trap (8 points > information)
5. Queens are overrated (protection < offense)
6. Draw when no good point play available
7. Use Threes to revive valuable cards
8. Use Sevens for deck play one-off
9. Counter selectively (only Aces and Fives)
10. When behind, use Jacks to steal high-value points

VERSION HISTORY:
- v1: Initial MCTS-learned heuristic (Feb 2026)
- v2: Incorporates Minimax analysis learnings (Feb 2026):
  * One-off timing: early (T1-4) is okay, late (T5+) is bad
  * Six is best one-off (64% win rate), Nine is worst (0%)
  * Limit one-offs to 1-2 per game - over-destroying loses
  * Kings early > Kings late (threshold reduction compounds)
  * Racing beats destroying in most cases (75% points > 25% one-offs)
  * Destroy only when: behind AND have Six targeting King/Queen
"""

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
from strategies.knowledge import (
    KnowledgeTracker,
    MemoryLevel,
    analyze_known_hand,
    get_unknown_card_count,
)

if TYPE_CHECKING:
    from cuttle_engine.moves import Move
    from cuttle_engine.state import GameState


class HeuristicStrategy(Strategy):
    """Strategy using MCTS-learned heuristics for move selection.

    Priorities (learned from MCTS analysis):
    1. Win if possible (play points to reach threshold)
    2. Play high-value points (8, 9, 10) - never scuttle with these
    3. Play Kings to reduce threshold
    4. Draw if no good point card (better than weak plays)
    5. Use Jacks to steal high-value opponent points (especially when behind)
    6. Play mid-value points (5, 6, 7)
    7. Use one-offs situationally (Threes to revive, Sevens for deck play)
    8. Counter only Aces and Fives
    9. Scuttle rarely (only for lethal or huge value differential)
    10. Queens/8-as-Glasses are low priority

    Version History:
    - v1: Initial MCTS-learned heuristic (Feb 2026)
    - v2: Minimax-informed refinements (Feb 2026)
    - v3: Glasses knowledge tracking (Feb 2026)

    Memory Levels (for knowledge tracking):
    - PERFECT: Remember all seen cards until they leave opponent's hand
    - TURN_LIMITED: Remember cards for N turns after seeing them
    - PROBABILISTIC: Chance to forget cards each turn
    - NONE: No memory, only use current Glasses visibility
    """

    VERSION = "v1"

    def __init__(
        self,
        seed: int | None = None,
        version: str | None = None,
        memory_level: MemoryLevel = MemoryLevel.PERFECT,
        memory_turns: int = 3,
        forget_probability: float = 0.3,
    ):
        """Initialize the heuristic strategy.

        Args:
            seed: Random seed for tie-breaking and probabilistic forgetting
            version: Strategy version override
            memory_level: How much to remember about opponent's hand
            memory_turns: For TURN_LIMITED, how many turns to remember
            forget_probability: For PROBABILISTIC, chance to forget per turn
        """
        self._rng = random.Random(seed)
        self._seed = seed
        # Allow overriding version for testing different variants
        self._version = version or self.VERSION
        # Track one-off usage for v2 strategy
        self._oneoffs_used = 0
        # Knowledge tracking configuration
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
        return f"Heuristic-{self._version}{mem_suffix}"

    def on_game_start(self, state: GameState, player_idx: int) -> None:
        """Reset per-game tracking and initialize knowledge tracker."""
        self._oneoffs_used = 0
        self._player_idx = player_idx
        self._knowledge = KnowledgeTracker.create(
            player_idx=player_idx,
            memory_level=self._memory_level,
            memory_turns=self._memory_turns,
            forget_probability=self._forget_probability,
            seed=self._seed,
        )

    def select_move(self, state: GameState, legal_moves: list[Move]) -> Move:
        """Select a move based on heuristic evaluation."""
        if not legal_moves:
            raise ValueError("No legal moves available")

        player_idx = state.current_player

        # Lazy initialize knowledge tracker if not done via on_game_start
        if self._knowledge is None or self._player_idx != player_idx:
            self._player_idx = player_idx
            self._knowledge = KnowledgeTracker.create(
                player_idx=player_idx,
                memory_level=self._memory_level,
                memory_turns=self._memory_turns,
                forget_probability=self._forget_probability,
                seed=self._seed,
            )

        # Update knowledge from current state (observes hand if we have glasses)
        self._knowledge.update_from_state(state)

        # Get knowledge analysis (may be partial or complete)
        known_cards = self._knowledge.get_known_opponent_cards()
        knowledge_analysis = analyze_known_hand(known_cards) if known_cards else None
        unknown_count = get_unknown_card_count(state, player_idx, known_cards)

        my_points = state.players[player_idx].point_total
        opp_points = state.players[1 - player_idx].point_total
        point_diff = my_points - opp_points

        # Score each move with context and knowledge
        scored_moves = [
            (self._score_move(state, move, player_idx, point_diff, knowledge_analysis, unknown_count), move)
            for move in legal_moves
        ]

        # Get best score
        best_score = max(score for score, _ in scored_moves)

        # Pick randomly among tied best moves
        best_moves = [move for score, move in scored_moves if score == best_score]
        return self._rng.choice(best_moves)

    def _score_move(
        self,
        state: GameState,
        move: Move,
        player_idx: int,
        point_diff: int,
        knowledge: dict | None = None,
        unknown_count: int = 0,
    ) -> float:
        """Score a move (higher is better).

        Scoring is based on MCTS-learned patterns from 1000+ games.
        When knowledge about opponent's hand is available, adjustments are made.

        Args:
            state: Current game state
            move: Move to score
            player_idx: Our player index
            point_diff: Our points minus opponent's points
            knowledge: Analysis of known opponent cards (from analyze_known_hand)
            unknown_count: Number of cards in opponent's hand we don't know about
        """
        my_points = state.players[player_idx].point_total
        opp_points = state.players[1 - player_idx].point_total
        threshold = state.point_threshold(player_idx)
        is_behind = point_diff < -3
        is_behind_big = point_diff < -8

        # Calculate base score first
        base_score = self._base_score(
            state, move, player_idx, my_points, opp_points, threshold,
            is_behind, is_behind_big
        )

        # Apply knowledge-based adjustments if we have information
        if knowledge is not None:
            base_score += self._knowledge_adjustment(
                move, knowledge, unknown_count, state, player_idx
            )

        return base_score

    def _base_score(
        self,
        state: GameState,
        move: Move,
        player_idx: int,
        my_points: int,
        opp_points: int,
        threshold: int,
        is_behind: bool,
        is_behind_big: bool,
    ) -> float:
        """Calculate the base score for a move (without knowledge adjustments)."""
        # Calculate point_diff for cases that need it
        point_diff = my_points - opp_points

        match move:
            case PlayPoints(card=card):
                # Check if this wins the game
                if my_points + card.point_value >= threshold:
                    return 10000  # Winning move

                # High cards (8-10) are extremely valuable as points
                # MCTS plays 8 for points 93% of the time (vs 1% for Heuristic)
                if card.point_value >= 8:
                    return 800 + card.point_value * 10
                elif card.point_value >= 5:
                    return 400 + card.point_value * 10
                else:
                    # Low cards (2-4) - still play for points but lower priority
                    # MCTS plays 2s for points 52% vs destroy 42%
                    return 200 + card.point_value * 10

            case Scuttle(card=card, target=target):
                # MCTS scuttles only 1.6% of the time!
                # Only scuttle if it's clearly winning or huge value
                value_gained = target.point_value - card.point_value

                # Check if scuttling wins (prevents opponent from winning)
                opp_threshold = state.point_threshold(1 - player_idx)
                if opp_points >= opp_threshold - target.point_value:
                    return 5000  # Prevent opponent win

                # Otherwise, scuttling is usually bad
                # Only consider if we're losing big AND it's high value
                if is_behind_big and value_gained >= 5:
                    return 100 + value_gained * 10

                # Generally avoid scuttling - it's a 1-for-1 trade
                return 20 + value_gained

            case PlayPermanent(card=card, target_card=target):
                if card.rank == Rank.KING:
                    # Kings are valuable - reduce threshold
                    # MCTS plays Kings ~6% overall, higher when ahead
                    return 600

                elif card.rank == Rank.JACK and target:
                    # Jacks to steal high-value points
                    # MCTS: 79.5% win rate - one of the best plays!
                    base = 400 + target.point_value * 25  # Increased from 300 + 20
                    if is_behind_big:
                        return base + 200  # Bonus when behind
                    elif is_behind:
                        return base + 100
                    return base

                elif card.rank == Rank.QUEEN:
                    # Queens: 45% win rate - correlates with weaker positions
                    # MCTS plays Queen when it has weak options
                    return 100  # Reduced from 150

                elif card.rank == Rank.EIGHT:
                    # 8 as Glasses is almost never correct
                    # MCTS: 5.1% Glasses vs 93.4% points
                    # Only consider if we literally can't play it for points
                    return 50

            case PlayOneOff(card=card, effect=effect):
                from cuttle_engine.moves import OneOffEffect

                # Determine game phase for one-off decisions
                is_opening = state.turn_number <= 3
                is_midgame = 4 <= state.turn_number <= 8

                if effect == OneOffEffect.ACE_SCRAP_ALL_POINTS:
                    # MCTS uses Ace 94% when behind 8+, NEVER when even/ahead
                    # Ace is a COMEBACK mechanic, not control
                    if is_behind_big:
                        # 94% of Ace plays are when behind 8+
                        return 700 if is_opening else 500
                    elif is_behind:
                        # Only 5.7% when behind 3-7
                        return 150
                    # NEVER use Ace when even or ahead (0% in data)
                    return -100  # Actively avoid

                elif effect == OneOffEffect.TWO_DESTROY_PERMANENT:
                    # MCTS uses 2 for points 52%, destroy only when necessary
                    # Only destroy truly critical targets
                    return 120

                elif effect == OneOffEffect.THREE_REVIVE:
                    # MCTS revives 36% when behind 8+, 28% even
                    # Priority: Jack > 10 > King > 9 > 8 > 7
                    # NEVER revive: 2, 3, Queen (0% in 500 games)
                    best_revive_score = 0
                    for c in state.scrap:
                        if c.rank == Rank.JACK:
                            best_revive_score = max(best_revive_score, 600)  # 27.7% of revives
                        elif c.rank == Rank.TEN:
                            best_revive_score = max(best_revive_score, 550)  # 23.4% of revives
                        elif c.rank == Rank.KING:
                            best_revive_score = max(best_revive_score, 500)  # 17% of revives
                        elif c.point_value >= 8:  # 9, 8
                            best_revive_score = max(best_revive_score, 400 + c.point_value * 10)
                        elif c.point_value >= 7:
                            best_revive_score = max(best_revive_score, 300)
                        # Skip 2, 3, 4, 5, 6 for points and Queen - MCTS never revives these

                    if best_revive_score > 0:
                        if is_behind_big:
                            return best_revive_score + 100  # Bonus when behind
                        elif is_behind or point_diff == 0:
                            return best_revive_score
                        return best_revive_score - 100  # Lower priority when ahead
                    return 50  # No good targets in scrap

                elif effect == OneOffEffect.FOUR_DISCARD:
                    # MCTS uses Four for points 60% of time!
                    # 41% win rate suggests one-off is often weak
                    if is_opening:
                        return 350  # Reduced from 450
                    elif is_midgame:
                        return 150  # Reduced from 200
                    return 100  # Low priority lategame

                elif effect == OneOffEffect.FIVE_DRAW_TWO:
                    # MCTS prefers 5 for points 65.6% of time
                    if is_opening:
                        return 300  # Reduced from 400
                    elif is_midgame:
                        return 200  # Reduced from 300
                    return 150  # Play for points lategame

                elif effect == OneOffEffect.SIX_SCRAP_ALL_PERMANENTS:
                    # MCTS almost never uses Six (2 total in 300 games)
                    # 6 points > scrapping permanents
                    our_perms = len(state.players[player_idx].permanents)
                    opp_perms = len(state.players[1 - player_idx].permanents)
                    if opp_perms >= our_perms + 3:
                        return 200  # Only if huge advantage
                    return 30  # Almost always play for 6 points

                elif effect == OneOffEffect.SEVEN_PLAY_FROM_DECK:
                    # MCTS prefers 7 for points 68.8% of time
                    if is_opening:
                        return 350  # Reduced from 450
                    elif is_midgame:
                        return 250  # Reduced from 300
                    return 150  # Play for points lategame

                return 100

            case Counter(card=card):
                # MCTS only counters 19% of the time!
                # Only counter Aces (36%) and Fives (50%)
                if state.counter_state and state.counter_state.one_off_card:
                    threat_rank = state.counter_state.one_off_card.rank
                    if threat_rank == Rank.ACE:
                        # Counter Ace 36% - scrap all points is dangerous
                        return 400
                    elif threat_rank == Rank.FIVE:
                        # Counter Five 50% - don't let them draw two
                        return 350
                    elif threat_rank == Rank.FOUR:
                        # Counter Four only 15%
                        return 100
                    elif threat_rank == Rank.TWO:
                        # Counter Two only 14%
                        return 80
                    else:
                        # Don't counter Six, Three, Seven, Nine
                        return 50
                return 100

            case DeclineCounter():
                # Declining is often correct - save your counter cards
                if state.counter_state:
                    threat_rank = state.counter_state.one_off_card.rank
                    # Prefer declining for non-critical threats
                    if threat_rank in (Rank.SIX, Rank.THREE, Rank.SEVEN):
                        return 200  # Definitely decline
                    elif threat_rank in (Rank.TWO, Rank.FOUR):
                        return 150  # Probably decline
                    elif threat_rank == Rank.FIVE:
                        return 50  # Maybe decline
                    elif threat_rank == Rank.ACE:
                        return -50  # Don't want to decline vs Ace
                return 100

            case Draw():
                # MCTS: 58% win rate - below average
                # Draw is often a 'settle' option
                return 250  # Reduced from 300

            case Pass():
                return 0

            case Discard(card=card):
                # Prefer discarding low-value cards
                return 10 - card.point_value

            case ResolveSeven(card=card, play_as=play_as, target_card=target):
                # Seven resolution - prefer one-off effects
                if play_as == MoveType.PLAY_ONE_OFF:
                    # MCTS uses Seven one-off effects more
                    from cuttle_engine.moves import OneOffEffect
                    # Check what effect we're getting
                    if card.rank == Rank.FIVE:
                        return 400  # Draw two is great
                    elif card.rank == Rank.ACE:
                        if opp_points > my_points:
                            return 350
                        return 100
                    return 250
                elif play_as == MoveType.PLAY_POINTS:
                    if my_points + card.point_value >= threshold:
                        return 10000  # Win!
                    return 200 + card.point_value * 10
                elif play_as == MoveType.SCUTTLE:
                    # Scuttling via Seven is still usually bad
                    if target:
                        value = target.point_value - card.point_value
                        return 50 + value
                    return 50
                elif play_as == MoveType.PLAY_PERMANENT:
                    if card.rank == Rank.KING:
                        return 500
                    elif card.rank == Rank.JACK and target:
                        return 400 + target.point_value * 25  # Match Jack steal scoring
                    return 100  # Match Queen scoring
                return 100

        return 0

    def _knowledge_adjustment(
        self,
        move: Move,
        knowledge: dict,
        unknown_count: int,
        state: GameState,
        player_idx: int,
    ) -> float:
        """Calculate score adjustment based on knowledge of opponent's hand.

        This method applies strategic adjustments when we have information about
        what cards the opponent holds. The adjustments vary based on:
        - Whether we have complete knowledge (unknown_count == 0)
        - Specific threats we know about (Jacks, Aces, counters)
        - Opportunities created by knowing what opponent lacks

        Args:
            move: The move being scored
            knowledge: Analysis dict from analyze_known_hand()
            unknown_count: How many cards in opponent's hand we don't know
            state: Current game state
            player_idx: Our player index

        Returns:
            Score adjustment (positive = better, negative = worse)
        """
        adjustment = 0.0

        # Full knowledge is more valuable than partial
        # Certainty factor: 1.0 when we know all cards, decreasing with unknowns
        opp_hand_size = len(state.players[1 - player_idx].hand)
        certainty = 1.0 - (unknown_count / max(opp_hand_size, 1)) if opp_hand_size > 0 else 0.0

        match move:
            case PlayOneOff():
                # Key insight: one-offs are much better when opponent can't counter
                if not knowledge["has_counter"]:
                    if certainty >= 0.8:
                        # High certainty they have no counter - big boost
                        adjustment += 200
                    elif certainty >= 0.5:
                        # Moderate certainty
                        adjustment += 100
                    # If low certainty, unknown cards might have counter
                elif knowledge["counter_count"] == 1 and certainty >= 0.8:
                    # We know they have exactly one counter
                    # If we have multiple one-offs, first one draws it out
                    adjustment += 30

            case Scuttle(target=target):
                # If opponent has Jack, protect our high-value points proactively
                if knowledge["has_jack"] and target.point_value >= 8:
                    # Remove their high-value target before they steal ours
                    adjustment += 100 * certainty

                # If we know opponent can't scuttle back, less risky
                if not any(r.value > target.point_value for r in knowledge["scuttle_ranks"]):
                    if certainty >= 0.7:
                        adjustment += 30

            case PlayPoints(card=card):
                # Adjust based on known threats to this card

                # If opponent has Jack and this is high-value, be cautious
                if knowledge["has_jack"] and card.point_value >= 8:
                    # Penalty scales with certainty and number of Jacks
                    adjustment -= 40 * certainty * knowledge["jack_count"]

                # If opponent can scuttle this specific card
                can_scuttle = any(
                    r.value > card.rank.value or
                    (r.value == card.rank.value)  # Same rank, might have higher suit
                    for r in knowledge["scuttle_ranks"]
                )
                if can_scuttle:
                    adjustment -= 20 * certainty

                # Positive: if we KNOW opponent can't threaten this card
                if (not knowledge["has_jack"] and
                    not can_scuttle and
                    certainty >= 0.8):
                    # Safe to play - small boost
                    adjustment += 20

            case PlayPermanent(card=card):
                if card.rank == Rank.QUEEN:
                    # Queen is more valuable when opponent has Jacks
                    if knowledge["has_jack"]:
                        adjustment += 120 * certainty * knowledge["jack_count"]
                    # Queen less valuable when opponent has no threats
                    elif certainty >= 0.8 and not knowledge["has_jack"]:
                        adjustment -= 30  # Don't waste time on protection

                elif card.rank == Rank.KING:
                    # King slightly more valuable when opponent lacks Ace
                    # (can't mass-scrap our accumulated points)
                    if not knowledge["has_ace"] and certainty >= 0.7:
                        adjustment += 30

                elif card.rank == Rank.EIGHT:
                    # Playing 8 as Glasses when we already have knowledge
                    # is less valuable (we already know their hand)
                    if knowledge["known_count"] > 0:
                        adjustment -= 20  # Redundant information

                elif card.rank == Rank.JACK:
                    # Jack steal - if opponent has counter, risky
                    if knowledge["has_counter"]:
                        adjustment -= 50 * certainty
                    # If opponent has no counter, Jack is very safe
                    elif certainty >= 0.7:
                        adjustment += 50

            case Counter():
                # If we KNOW opponent has another counter, might want to hold ours
                if knowledge["counter_count"] >= 2 and certainty >= 0.5:
                    # They can counter our counter, so our counter is less valuable
                    adjustment -= 30

            case DeclineCounter():
                # If we know opponent has no more counters, we're safe to decline
                if not knowledge["has_counter"] and certainty >= 0.8:
                    adjustment += 50  # Safe to let it resolve if we have no counter

            case Draw():
                # Drawing is less valuable when we already have good information
                # But still useful if there are many unknowns
                if certainty >= 0.8:
                    adjustment -= 20  # We already know a lot, maybe act on it
                elif unknown_count > 2:
                    adjustment += 10  # Drawing might reveal threats

        return adjustment


class HeuristicStrategyV2(Strategy):
    """Enhanced heuristic incorporating Minimax vs MCTS analysis learnings.

    Key differences from v1:
    1. One-off timing: penalize late-game (T5+) one-offs heavily
    2. One-off budget: track and limit to 1-2 per game
    3. Six is the ONLY reliable one-off (64% win rate)
    4. Nine one-off is NEVER good (0% win rate)
    5. Kings are better early (threshold reduction compounds)
    6. Racing > Destroying in 75% of situations

    Decision Framework:
    - DESTROY if: Turn 1-4, have Six, opponent has King/Queen, used <2 one-offs
    - RACE otherwise: Points > Draw > One-offs

    Memory Levels (for knowledge tracking):
    - PERFECT: Remember all seen cards until they leave opponent's hand
    - TURN_LIMITED: Remember cards for N turns after seeing them
    - PROBABILISTIC: Chance to forget cards each turn
    - NONE: No memory, only use current Glasses visibility
    """

    VERSION = "v2"

    # One-off win rates from analysis
    ONEOFF_WIN_RATES = {
        Rank.SIX: 0.64,    # Best - clear Kings/Queens
        Rank.FIVE: 0.50,   # Okay - draw 2
        Rank.SEVEN: 0.46,  # Okay - tempo
        Rank.TWO: 0.43,    # Situational
        Rank.FOUR: 0.42,   # Situational
        Rank.THREE: 0.30,  # Usually play for points
        Rank.ACE: 0.28,    # Often a trap
        Rank.NINE: 0.00,   # NEVER use
    }

    def __init__(
        self,
        seed: int | None = None,
        memory_level: MemoryLevel = MemoryLevel.PERFECT,
        memory_turns: int = 3,
        forget_probability: float = 0.3,
    ):
        """Initialize the v2 heuristic strategy.

        Args:
            seed: Random seed for tie-breaking and probabilistic forgetting
            memory_level: How much to remember about opponent's hand
            memory_turns: For TURN_LIMITED, how many turns to remember
            forget_probability: For PROBABILISTIC, chance to forget per turn
        """
        self._rng = random.Random(seed)
        self._seed = seed
        self._oneoffs_used = 0
        self._memory_level = memory_level
        self._memory_turns = memory_turns
        self._forget_probability = forget_probability
        self._knowledge: KnowledgeTracker | None = None
        self._player_idx: int | None = None

    @property
    def name(self) -> str:
        mem_suffix = ""
        if self._memory_level != MemoryLevel.NONE:
            mem_suffix = f"-mem:{self._memory_level.name.lower()}"
        return f"Heuristic-v2{mem_suffix}"

    def on_game_start(self, state: GameState, player_idx: int) -> None:
        """Reset per-game tracking and initialize knowledge tracker."""
        self._oneoffs_used = 0
        self._player_idx = player_idx
        self._knowledge = KnowledgeTracker.create(
            player_idx=player_idx,
            memory_level=self._memory_level,
            memory_turns=self._memory_turns,
            forget_probability=self._forget_probability,
            seed=self._seed,
        )

    def select_move(self, state: GameState, legal_moves: list[Move]) -> Move:
        """Select a move based on v2 heuristic evaluation."""
        if not legal_moves:
            raise ValueError("No legal moves available")

        player_idx = state.current_player

        # Lazy initialize knowledge tracker if not done via on_game_start
        if self._knowledge is None or self._player_idx != player_idx:
            self._player_idx = player_idx
            self._knowledge = KnowledgeTracker.create(
                player_idx=player_idx,
                memory_level=self._memory_level,
                memory_turns=self._memory_turns,
                forget_probability=self._forget_probability,
                seed=self._seed,
            )

        # Update knowledge from current state
        self._knowledge.update_from_state(state)

        # Get knowledge analysis
        known_cards = self._knowledge.get_known_opponent_cards()
        knowledge_analysis = analyze_known_hand(known_cards) if known_cards else None
        unknown_count = get_unknown_card_count(state, player_idx, known_cards)

        my_points = state.players[player_idx].point_total
        opp_points = state.players[1 - player_idx].point_total
        point_diff = my_points - opp_points

        # Score each move with knowledge
        scored_moves = [
            (self._score_move(state, move, player_idx, point_diff, knowledge_analysis, unknown_count), move)
            for move in legal_moves
        ]

        best_score = max(score for score, _ in scored_moves)
        best_moves = [move for score, move in scored_moves if score == best_score]
        chosen = self._rng.choice(best_moves)

        # Track one-off usage
        if isinstance(chosen, PlayOneOff):
            self._oneoffs_used += 1

        return chosen

    def _score_move(
        self,
        state: GameState,
        move: Move,
        player_idx: int,
        point_diff: int,
        knowledge: dict | None = None,
        unknown_count: int = 0,
    ) -> float:
        """Score a move using v2 heuristic with knowledge adjustments."""
        my_points = state.players[player_idx].point_total
        opp_points = state.players[1 - player_idx].point_total
        threshold = state.point_threshold(player_idx)
        opp_threshold = state.point_threshold(1 - player_idx)

        is_early = state.turn_number <= 4
        is_late = state.turn_number >= 5
        is_behind = point_diff < -3
        is_behind_big = point_diff < -8
        is_ahead = point_diff > 3

        # Check opponent's permanents for Six targeting
        opp_kings = sum(
            1 for c in state.players[1 - player_idx].permanents if c.rank == Rank.KING
        )
        opp_queens = state.players[1 - player_idx].queens_count

        # Calculate base score
        base_score = self._base_score_v2(
            state, move, player_idx, my_points, opp_points, threshold, opp_threshold,
            is_early, is_late, is_behind, is_behind_big, is_ahead, opp_kings, opp_queens
        )

        # Apply knowledge-based adjustments (reuse v1's adjustment logic)
        if knowledge is not None:
            # Use same adjustment logic as v1
            base_score += self._knowledge_adjustment_v2(
                move, knowledge, unknown_count, state, player_idx
            )

        return base_score

    def _knowledge_adjustment_v2(
        self,
        move: Move,
        knowledge: dict,
        unknown_count: int,
        state: GameState,
        player_idx: int,
    ) -> float:
        """Calculate score adjustment based on knowledge (v2 version).

        Similar to v1's _knowledge_adjustment but tuned for v2's priorities.
        """
        adjustment = 0.0

        opp_hand_size = len(state.players[1 - player_idx].hand)
        certainty = 1.0 - (unknown_count / max(opp_hand_size, 1)) if opp_hand_size > 0 else 0.0

        match move:
            case PlayOneOff():
                # v2 cares more about one-off timing, so knowledge is very valuable
                if not knowledge["has_counter"]:
                    if certainty >= 0.8:
                        adjustment += 250  # Higher than v1 - one-offs need to succeed
                    elif certainty >= 0.5:
                        adjustment += 120

            case Scuttle(target=target):
                if knowledge["has_jack"] and target.point_value >= 8:
                    adjustment += 100 * certainty

            case PlayPoints(card=card):
                if knowledge["has_jack"] and card.point_value >= 8:
                    adjustment -= 40 * certainty * knowledge["jack_count"]

                can_scuttle = any(
                    r.value > card.rank.value or r.value == card.rank.value
                    for r in knowledge["scuttle_ranks"]
                )
                if can_scuttle:
                    adjustment -= 20 * certainty

                if not knowledge["has_jack"] and not can_scuttle and certainty >= 0.8:
                    adjustment += 30  # v2 values safe point plays more

            case PlayPermanent(card=card):
                if card.rank == Rank.QUEEN:
                    if knowledge["has_jack"]:
                        adjustment += 120 * certainty * knowledge["jack_count"]
                    elif certainty >= 0.8:
                        adjustment -= 40  # v2 dislikes defensive plays more

                elif card.rank == Rank.KING:
                    if not knowledge["has_ace"] and certainty >= 0.7:
                        adjustment += 40  # v2 values Kings more

                elif card.rank == Rank.EIGHT:
                    if knowledge["known_count"] > 0:
                        adjustment -= 30

                elif card.rank == Rank.JACK:
                    if knowledge["has_counter"]:
                        adjustment -= 60 * certainty  # v2 more cautious
                    elif certainty >= 0.7:
                        adjustment += 60

            case Counter():
                if knowledge["counter_count"] >= 2 and certainty >= 0.5:
                    adjustment -= 40  # v2 values counter cards more

            case DeclineCounter():
                if not knowledge["has_counter"] and certainty >= 0.8:
                    adjustment += 60

            case Draw():
                if certainty >= 0.8:
                    adjustment -= 30
                elif unknown_count > 2:
                    adjustment += 15

        return adjustment

    def _base_score_v2(
        self,
        state: GameState,
        move: Move,
        player_idx: int,
        my_points: int,
        opp_points: int,
        threshold: int,
        opp_threshold: int,
        is_early: bool,
        is_late: bool,
        is_behind: bool,
        is_behind_big: bool,
        is_ahead: bool,
        opp_kings: int,
        opp_queens: int,
    ) -> float:
        """Calculate base score for v2 heuristic."""
        match move:
            case PlayPoints(card=card):
                # Check for win
                if my_points + card.point_value >= threshold:
                    return 10000

                # High cards are extremely valuable
                if card.point_value >= 8:
                    return 900 + card.point_value * 10
                elif card.point_value >= 5:
                    return 500 + card.point_value * 10
                else:
                    return 300 + card.point_value * 10

            case Scuttle(card=card, target=target):
                # Prevent opponent win
                if opp_points >= opp_threshold - target.point_value:
                    return 5000

                value_gained = target.point_value - card.point_value

                # Only scuttle when behind big and good value
                if is_behind_big and value_gained >= 5:
                    return 150 + value_gained * 10

                return 30 + value_gained

            case PlayPermanent(card=card, target_card=target):
                if card.rank == Rank.KING:
                    # Kings are BETTER early (threshold reduction compounds)
                    # v2 change: boost early King plays
                    if is_early:
                        return 750  # Higher than v1
                    return 550

                elif card.rank == Rank.JACK and target:
                    base = 450 + target.point_value * 25
                    if is_behind_big:
                        return base + 200
                    elif is_behind:
                        return base + 100
                    return base

                elif card.rank == Rank.QUEEN:
                    return 100

                elif card.rank == Rank.EIGHT:
                    return 50

            case PlayOneOff(card=card, effect=effect):
                from cuttle_engine.moves import OneOffEffect

                # v2 KEY CHANGE: Heavily penalize late one-offs
                # Late one-offs appear 2x more often in LOSSES
                late_penalty = -200 if is_late else 0

                # v2 KEY CHANGE: Penalize if already used 2+ one-offs
                # Games with >2 one-offs have 30% win rate vs 70% with <=2
                overuse_penalty = -300 if self._oneoffs_used >= 2 else 0

                # Get base win rate for this one-off type
                base_win_rate = self.ONEOFF_WIN_RATES.get(card.rank, 0.3)

                if effect == OneOffEffect.SIX_SCRAP_ALL_PERMANENTS:
                    # SIX is the BEST one-off (64% win rate)
                    # v2: Only good if opponent has Kings or Queens
                    if opp_kings > 0 or opp_queens > 0:
                        value = 600 + opp_kings * 100 + opp_queens * 50
                        # Less penalty for Six since it's actually good
                        return value + late_penalty // 2 + overuse_penalty // 2
                    return 50  # No good targets, play for 6 points

                elif effect == OneOffEffect.NINE_RETURN_PERMANENT:
                    # NINE is NEVER good (0% win rate)
                    # v2: Actively avoid Nine one-off
                    return -100

                elif effect == OneOffEffect.ACE_SCRAP_ALL_POINTS:
                    # Ace: 28% win rate - only when behind big
                    if is_behind_big and is_early:
                        return 500 + late_penalty + overuse_penalty
                    elif is_behind_big:
                        return 200 + late_penalty + overuse_penalty
                    # v2: Never use when even/ahead
                    return -150

                elif effect == OneOffEffect.THREE_REVIVE:
                    # 30% win rate - usually play for points
                    best_revive = 0
                    for c in state.scrap:
                        if c.rank == Rank.JACK:
                            best_revive = max(best_revive, 500)
                        elif c.rank == Rank.TEN:
                            best_revive = max(best_revive, 450)
                        elif c.rank == Rank.KING:
                            best_revive = max(best_revive, 400)
                        elif c.point_value >= 8:
                            best_revive = max(best_revive, 350)

                    if best_revive > 0:
                        return best_revive + late_penalty + overuse_penalty
                    return 50  # Play for 3 points

                elif effect == OneOffEffect.FOUR_DISCARD:
                    # 42% win rate - only early
                    if is_early:
                        return 300 + late_penalty + overuse_penalty
                    return 100 + late_penalty + overuse_penalty

                elif effect == OneOffEffect.FIVE_DRAW_TWO:
                    # 50% win rate - okay
                    if is_early:
                        return 350 + late_penalty + overuse_penalty
                    return 150 + late_penalty + overuse_penalty

                elif effect == OneOffEffect.SEVEN_PLAY_FROM_DECK:
                    # 46% win rate - okay for tempo
                    if is_early:
                        return 300 + late_penalty + overuse_penalty
                    return 100 + late_penalty + overuse_penalty

                elif effect == OneOffEffect.TWO_DESTROY_PERMANENT:
                    # 43% win rate - only for critical targets
                    if opp_kings > 0:
                        return 250 + late_penalty + overuse_penalty
                    return 50 + late_penalty + overuse_penalty

                return 100 + late_penalty + overuse_penalty

            case Counter(card=card):
                if state.counter_state and state.counter_state.one_off_card:
                    threat_rank = state.counter_state.one_off_card.rank
                    if threat_rank == Rank.ACE:
                        return 400
                    elif threat_rank == Rank.FIVE:
                        return 350
                    elif threat_rank == Rank.SIX:
                        # v2: Counter Six more (it's actually dangerous)
                        return 300
                    elif threat_rank == Rank.FOUR:
                        return 100
                    else:
                        return 50
                return 100

            case DeclineCounter():
                if state.counter_state:
                    threat_rank = state.counter_state.one_off_card.rank
                    if threat_rank == Rank.NINE:
                        return 250  # Always decline Nine (it's weak)
                    elif threat_rank in (Rank.THREE, Rank.SEVEN):
                        return 200
                    elif threat_rank in (Rank.TWO, Rank.FOUR):
                        return 150
                    elif threat_rank == Rank.FIVE:
                        return 50
                    elif threat_rank == Rank.SIX:
                        return -50  # Don't decline Six
                    elif threat_rank == Rank.ACE:
                        return -100
                return 100

            case Draw():
                # v2: Draw is slightly better than one-offs late game
                if is_late:
                    return 280  # Higher than most late one-offs
                return 250

            case Pass():
                return 0

            case Discard(card=card):
                return 10 - card.point_value

            case ResolveSeven(card=card, play_as=play_as, target_card=target):
                if play_as == MoveType.PLAY_ONE_OFF:
                    # Track this as a one-off
                    if card.rank == Rank.FIVE:
                        return 400
                    elif card.rank == Rank.ACE and opp_points > my_points:
                        return 300
                    return 200
                elif play_as == MoveType.PLAY_POINTS:
                    if my_points + card.point_value >= threshold:
                        return 10000
                    return 300 + card.point_value * 10
                elif play_as == MoveType.SCUTTLE:
                    if target:
                        return 50 + target.point_value - card.point_value
                    return 50
                elif play_as == MoveType.PLAY_PERMANENT:
                    if card.rank == Rank.KING:
                        return 600 if is_early else 450
                    elif card.rank == Rank.JACK and target:
                        return 450 + target.point_value * 25
                    return 100
                return 100

        return 0

    def get_identity_params(self) -> dict:
        """Return parameters that identify this strategy configuration."""
        return {
            "version": self.VERSION,
            "memory_level": self._memory_level.name,
        }
