"""Opponent hand knowledge tracking for glasses-aware strategies.

When a player has Glasses (8 as permanent), they can see the opponent's hand.
This module tracks that knowledge and provides utilities for strategies to use it.

Key concepts:
- Knowledge persists after Glasses is destroyed (until cards leave opponent's hand)
- Memory levels control how much knowledge is retained (for balancing vs humans)
- Strategies can query known cards to make better decisions
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import TYPE_CHECKING
import random

if TYPE_CHECKING:
    from cuttle_engine.cards import Card
    from cuttle_engine.state import GameState


class MemoryLevel(Enum):
    """How much the AI remembers about opponent's hand after seeing it.

    PERFECT: Remember all seen cards until they leave opponent's hand.
             This is the strongest setting - AI never forgets.

    TURN_LIMITED: Remember cards for N turns after last seeing them.
                  Simulates human short-term memory.

    PROBABILISTIC: Each turn, have a chance to forget each card.
                   More realistic human-like forgetting.

    NONE: No memory - only use current Glasses visibility.
          Most fair for human opponents.
    """
    PERFECT = auto()
    TURN_LIMITED = auto()
    PROBABILISTIC = auto()
    NONE = auto()


@dataclass
class KnownCard:
    """A card we know is in opponent's hand."""
    card: Card
    turn_seen: int  # Turn number when we first saw this card
    last_confirmed: int  # Turn number when we last confirmed it's still there


@dataclass
class OpponentKnowledge:
    """Tracks what we know about an opponent's hand.

    This class maintains knowledge about cards we've seen in the opponent's
    hand and provides methods to query and update that knowledge.
    """

    # Cards we know are in opponent's hand
    known_cards: dict[Card, KnownCard] = field(default_factory=dict)

    # Memory configuration
    memory_level: MemoryLevel = MemoryLevel.PERFECT
    memory_turns: int = 3  # For TURN_LIMITED: how many turns to remember
    forget_probability: float = 0.3  # For PROBABILISTIC: chance to forget per turn

    # Random state for probabilistic forgetting
    _rng: random.Random = field(default_factory=random.Random)

    def observe_hand(self, hand: tuple[Card, ...], current_turn: int) -> None:
        """Record observation of opponent's full hand (when we have Glasses).

        Args:
            hand: The opponent's current hand
            current_turn: Current turn number
        """
        # Update known cards - add new ones, confirm existing ones
        current_hand_set = set(hand)

        # Add/update cards we see
        for card in hand:
            if card in self.known_cards:
                # Update last confirmed time
                self.known_cards[card] = KnownCard(
                    card=card,
                    turn_seen=self.known_cards[card].turn_seen,
                    last_confirmed=current_turn,
                )
            else:
                # New card we're seeing
                self.known_cards[card] = KnownCard(
                    card=card,
                    turn_seen=current_turn,
                    last_confirmed=current_turn,
                )

        # Remove cards no longer in hand (opponent played/discarded them)
        cards_to_remove = [c for c in self.known_cards if c not in current_hand_set]
        for card in cards_to_remove:
            del self.known_cards[card]

    def card_left_hand(self, card: Card) -> None:
        """Record that a card has left opponent's hand (played, discarded, stolen).

        Args:
            card: The card that left opponent's hand
        """
        if card in self.known_cards:
            del self.known_cards[card]

    def on_turn_end(self, current_turn: int) -> None:
        """Called at end of each turn to apply memory decay.

        Args:
            current_turn: The turn that just ended
        """
        if self.memory_level == MemoryLevel.NONE:
            # Forget everything immediately when we don't have glasses
            # (handled separately - this is for between-turn decay)
            pass

        elif self.memory_level == MemoryLevel.TURN_LIMITED:
            # Forget cards we haven't confirmed recently
            cards_to_forget = [
                card for card, known in self.known_cards.items()
                if current_turn - known.last_confirmed > self.memory_turns
            ]
            for card in cards_to_forget:
                del self.known_cards[card]

        elif self.memory_level == MemoryLevel.PROBABILISTIC:
            # Randomly forget cards (except ones just seen this turn)
            cards_to_forget = [
                card for card, known in self.known_cards.items()
                if known.last_confirmed < current_turn and self._rng.random() < self.forget_probability
            ]
            for card in cards_to_forget:
                del self.known_cards[card]

        # PERFECT: never forget anything

    def clear_if_no_glasses(self, has_glasses: bool) -> None:
        """For NONE memory level, clear knowledge when glasses are lost.

        Args:
            has_glasses: Whether we currently have Glasses
        """
        if self.memory_level == MemoryLevel.NONE and not has_glasses:
            self.known_cards.clear()

    def get_known_cards(self) -> frozenset[Card]:
        """Get the set of cards we know are in opponent's hand.

        Returns:
            Frozen set of known cards
        """
        return frozenset(self.known_cards.keys())

    def knows_card(self, card: Card) -> bool:
        """Check if we know a specific card is in opponent's hand.

        Args:
            card: The card to check

        Returns:
            True if we know this card is in opponent's hand
        """
        return card in self.known_cards

    def get_known_count(self) -> int:
        """Get the number of cards we know about.

        Returns:
            Count of known cards
        """
        return len(self.known_cards)

    def copy(self) -> OpponentKnowledge:
        """Create a copy of this knowledge state.

        Returns:
            A new OpponentKnowledge with the same data
        """
        new_knowledge = OpponentKnowledge(
            known_cards=dict(self.known_cards),
            memory_level=self.memory_level,
            memory_turns=self.memory_turns,
            forget_probability=self.forget_probability,
        )
        new_knowledge._rng = random.Random()
        new_knowledge._rng.setstate(self._rng.getstate())
        return new_knowledge

    def reset(self) -> None:
        """Clear all knowledge (for new game)."""
        self.known_cards.clear()


@dataclass
class KnowledgeTracker:
    """Tracks opponent knowledge for a player across a game.

    This class is meant to be held by a strategy and updated as the game
    progresses. It handles:
    - Observing opponent's hand when Glasses is active
    - Tracking when cards leave opponent's hand
    - Applying memory decay between turns
    """

    player_idx: int  # Which player we are (0 or 1)
    knowledge: OpponentKnowledge = field(default_factory=OpponentKnowledge)
    last_observed_turn: int = -1  # Last turn we observed opponent's hand

    def __post_init__(self):
        if not isinstance(self.knowledge, OpponentKnowledge):
            self.knowledge = OpponentKnowledge()

    @classmethod
    def create(
        cls,
        player_idx: int,
        memory_level: MemoryLevel = MemoryLevel.PERFECT,
        memory_turns: int = 3,
        forget_probability: float = 0.3,
        seed: int | None = None,
    ) -> KnowledgeTracker:
        """Create a new knowledge tracker with specified memory settings.

        Args:
            player_idx: Which player we are (0 or 1)
            memory_level: How much to remember
            memory_turns: For TURN_LIMITED, how many turns to remember
            forget_probability: For PROBABILISTIC, chance to forget per turn
            seed: Random seed for probabilistic forgetting

        Returns:
            Configured KnowledgeTracker
        """
        knowledge = OpponentKnowledge(
            memory_level=memory_level,
            memory_turns=memory_turns,
            forget_probability=forget_probability,
        )
        if seed is not None:
            knowledge._rng = random.Random(seed)

        return cls(player_idx=player_idx, knowledge=knowledge)

    def update_from_state(self, state: GameState) -> None:
        """Update knowledge based on current game state.

        Call this at the start of your turn to update what you know.

        Args:
            state: Current game state
        """
        me = state.players[self.player_idx]
        opponent = state.players[1 - self.player_idx]
        current_turn = state.turn_number

        # If we have glasses, observe opponent's full hand
        if me.has_glasses:
            self.knowledge.observe_hand(opponent.hand, current_turn)
            self.last_observed_turn = current_turn
        else:
            # No glasses - apply NONE memory level clearing if needed
            self.knowledge.clear_if_no_glasses(has_glasses=False)

        # Apply turn-based memory decay
        if current_turn > self.last_observed_turn:
            self.knowledge.on_turn_end(current_turn)

    def on_opponent_plays_card(self, card: Card) -> None:
        """Record that opponent played a card from their hand.

        Args:
            card: The card that was played
        """
        self.knowledge.card_left_hand(card)

    def on_opponent_discards_card(self, card: Card) -> None:
        """Record that opponent discarded a card from their hand.

        Args:
            card: The card that was discarded
        """
        self.knowledge.card_left_hand(card)

    def on_card_stolen_from_opponent(self, card: Card) -> None:
        """Record that a card was stolen from opponent's hand/field.

        Args:
            card: The card that was stolen
        """
        self.knowledge.card_left_hand(card)

    def get_known_opponent_cards(self) -> frozenset[Card]:
        """Get cards we know are in opponent's hand.

        Returns:
            Set of known cards
        """
        return self.knowledge.get_known_cards()

    def opponent_has_card(self, card: Card) -> bool:
        """Check if we know opponent has a specific card.

        Args:
            card: The card to check

        Returns:
            True if we know opponent has this card
        """
        return self.knowledge.knows_card(card)

    def reset(self) -> None:
        """Reset knowledge for a new game."""
        self.knowledge.reset()
        self.last_observed_turn = -1


def analyze_known_hand(known_cards: frozenset[Card]) -> dict:
    """Analyze a set of known cards to extract strategic information.

    This is similar to _analyze_opponent_hand but works on any set of
    known cards, not just when we currently have Glasses.

    Args:
        known_cards: Set of cards we know opponent has

    Returns:
        Dict with strategic analysis:
        - has_counter: bool - opponent has a Two
        - counter_count: int - number of Twos
        - has_jack: bool - opponent can steal our points
        - jack_count: int - number of Jacks
        - max_point_play: int - highest point card they can play
        - scuttle_ranks: list[int] - ranks they can scuttle with (1-10)
        - has_king: bool - opponent has a King
        - has_ace: bool - opponent has an Ace
        - known_count: int - how many cards we know about
    """
    from cuttle_engine.cards import Rank

    cards = list(known_cards)

    return {
        "has_counter": any(c.rank == Rank.TWO for c in cards),
        "counter_count": sum(1 for c in cards if c.rank == Rank.TWO),
        "has_jack": any(c.rank == Rank.JACK for c in cards),
        "jack_count": sum(1 for c in cards if c.rank == Rank.JACK),
        "max_point_play": max((c.point_value for c in cards if c.point_value > 0), default=0),
        "scuttle_ranks": [c.rank for c in cards if c.rank.value <= 10],
        "has_king": any(c.rank == Rank.KING for c in cards),
        "has_ace": any(c.rank == Rank.ACE for c in cards),
        "has_queen": any(c.rank == Rank.QUEEN for c in cards),
        "known_count": len(cards),
    }


def get_unknown_card_count(state: GameState, player_idx: int, known_cards: frozenset[Card]) -> int:
    """Calculate how many cards in opponent's hand we don't know about.

    Args:
        state: Current game state
        player_idx: Our player index
        known_cards: Cards we know opponent has

    Returns:
        Number of unknown cards in opponent's hand
    """
    opponent_hand_size = len(state.players[1 - player_idx].hand)
    return max(0, opponent_hand_size - len(known_cards))
