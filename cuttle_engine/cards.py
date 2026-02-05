"""Card, Suit, and Rank models for Cuttle."""

from __future__ import annotations

from enum import IntEnum, auto
from functools import total_ordering
from typing import ClassVar


class Suit(IntEnum):
    """Card suits ordered by Cuttle precedence (for scuttling tiebreaks)."""

    CLUBS = 0
    DIAMONDS = 1
    HEARTS = 2
    SPADES = 3

    def __str__(self) -> str:
        return self.symbol

    @property
    def symbol(self) -> str:
        return {
            Suit.CLUBS: "♣",
            Suit.DIAMONDS: "♦",
            Suit.HEARTS: "♥",
            Suit.SPADES: "♠",
        }[self]

    @property
    def letter(self) -> str:
        return self.name[0]


class Rank(IntEnum):
    """Card ranks (Ace=1 through King=13)."""

    ACE = 1
    TWO = 2
    THREE = 3
    FOUR = 4
    FIVE = 5
    SIX = 6
    SEVEN = 7
    EIGHT = 8
    NINE = 9
    TEN = 10
    JACK = 11
    QUEEN = 12
    KING = 13

    def __str__(self) -> str:
        return self.symbol

    @property
    def symbol(self) -> str:
        if self.value == 1:
            return "A"
        elif self.value <= 10:
            return str(self.value)
        else:
            return self.name[0]


class CardType(IntEnum):
    """How a card can be played in Cuttle."""

    POINTS = auto()  # Played face-up for point value
    ONE_OFF = auto()  # One-time effect, goes to scrap
    PERMANENT = auto()  # Stays on board (8, J, Q, K)


@total_ordering
class Card:
    """A playing card with Cuttle-specific properties.

    Cards are immutable and comparable. Comparison is first by rank,
    then by suit (for scuttling tiebreaks).
    """

    __slots__ = ("_rank", "_suit")

    # Pre-computed card instances for the standard 52-card deck
    _instances: ClassVar[dict[tuple[Rank, Suit], Card]] = {}

    def __new__(cls, rank: Rank, suit: Suit) -> Card:
        key = (rank, suit)
        if key not in cls._instances:
            instance = object.__new__(cls)
            instance._rank = rank
            instance._suit = suit
            cls._instances[key] = instance
        return cls._instances[key]

    @property
    def rank(self) -> Rank:
        return self._rank

    @property
    def suit(self) -> Suit:
        return self._suit

    @property
    def point_value(self) -> int:
        """Points this card is worth when played for points (A-10 only)."""
        if self._rank.value <= 10:
            return self._rank.value
        return 0

    @property
    def can_play_for_points(self) -> bool:
        """Whether this card can be played face-up for points."""
        return self._rank.value <= 10

    @property
    def can_play_as_one_off(self) -> bool:
        """Whether this card can be played as a one-off effect."""
        # A-9 can be one-offs, 10 and face cards cannot (except J on opponent's point card)
        return self._rank.value <= 9

    @property
    def can_play_as_permanent(self) -> bool:
        """Whether this card can be played as a permanent (8, J, Q, K)."""
        return self._rank.value >= 8 and self._rank != Rank.NINE and self._rank != Rank.TEN

    @property
    def is_royal(self) -> bool:
        """Whether this is a face card (J, Q, K)."""
        return self._rank.value >= 11

    @property
    def card_types(self) -> list[CardType]:
        """All ways this card can be played."""
        types = []
        if self.can_play_for_points:
            types.append(CardType.POINTS)
        if self.can_play_as_one_off:
            types.append(CardType.ONE_OFF)
        if self.can_play_as_permanent:
            types.append(CardType.PERMANENT)
        return types

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Card):
            return NotImplemented
        return self._rank == other._rank and self._suit == other._suit

    def __lt__(self, other: object) -> bool:
        if not isinstance(other, Card):
            return NotImplemented
        if self._rank != other._rank:
            return self._rank < other._rank
        return self._suit < other._suit

    def __hash__(self) -> int:
        return hash((self._rank, self._suit))

    def __reduce__(self) -> tuple:
        """Support pickling for multiprocessing."""
        return (Card, (self._rank, self._suit))

    def __repr__(self) -> str:
        return f"Card({self._rank.name}, {self._suit.name})"

    def __str__(self) -> str:
        return f"{self._rank.symbol}{self._suit.symbol}"

    def can_scuttle(self, target: Card) -> bool:
        """Whether this card can scuttle the target card.

        A card can scuttle another if:
        - It has a higher rank, OR
        - Same rank and higher suit (Spades > Hearts > Diamonds > Clubs)
        """
        if not self.can_play_for_points or not target.can_play_for_points:
            return False
        if self._rank > target._rank:
            return True
        if self._rank == target._rank and self._suit > target._suit:
            return True
        return False


def create_deck() -> list[Card]:
    """Create a standard 52-card deck."""
    return [Card(rank, suit) for suit in Suit for rank in Rank]


def shuffle_deck(deck: list[Card], seed: int | None = None) -> list[Card]:
    """Return a shuffled copy of the deck."""
    import random

    rng = random.Random(seed)
    shuffled = deck.copy()
    rng.shuffle(shuffled)
    return shuffled
