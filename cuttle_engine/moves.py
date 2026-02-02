"""Move types for Cuttle."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import IntEnum, auto
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from cuttle_engine.cards import Card


class MoveType(IntEnum):
    """Type of move."""

    DRAW = auto()
    PLAY_POINTS = auto()
    SCUTTLE = auto()
    PLAY_ONE_OFF = auto()
    PLAY_PERMANENT = auto()
    COUNTER = auto()  # Play a Two to counter
    DECLINE_COUNTER = auto()  # Pass on countering
    RESOLVE_SEVEN = auto()  # Choose card from Seven's reveal
    DISCARD = auto()  # Discard for Four's effect
    PASS = auto()  # Pass turn (when deck is empty)


class OneOffEffect(IntEnum):
    """Effects for one-off cards."""

    ACE_SCRAP_ALL_POINTS = auto()  # Ace: scrap all points on board
    TWO_COUNTER = auto()  # Two: counter a one-off
    TWO_DESTROY_PERMANENT = auto()  # Two: destroy target permanent (royals + 8)
    THREE_REVIVE = auto()  # Three: take a card from scrap to hand
    FOUR_DISCARD = auto()  # Four: opponent discards 2 cards
    FIVE_DRAW_TWO = auto()  # Five: draw 2 cards
    SIX_SCRAP_ALL_PERMANENTS = auto()  # Six: scrap all permanents (both sides)
    SEVEN_PLAY_FROM_DECK = auto()  # Seven: reveal and play from top of deck
    NINE_RETURN_PERMANENT = auto()  # Nine: return target permanent to hand


@dataclass(frozen=True, slots=True)
class Move(ABC):
    """Base class for all moves."""

    @property
    @abstractmethod
    def move_type(self) -> MoveType:
        """The type of this move."""
        ...

    @abstractmethod
    def __str__(self) -> str:
        """Human-readable move description."""
        ...


@dataclass(frozen=True, slots=True)
class Draw(Move):
    """Draw a card from the deck."""

    @property
    def move_type(self) -> MoveType:
        return MoveType.DRAW

    def __str__(self) -> str:
        return "Draw"


@dataclass(frozen=True, slots=True)
class PlayPoints(Move):
    """Play a card for points."""

    card: Card

    @property
    def move_type(self) -> MoveType:
        return MoveType.PLAY_POINTS

    def __str__(self) -> str:
        return f"Play {self.card} for points"


@dataclass(frozen=True, slots=True)
class Scuttle(Move):
    """Scuttle an opponent's point card."""

    card: Card  # Card being played
    target: Card  # Opponent's point card being destroyed

    @property
    def move_type(self) -> MoveType:
        return MoveType.SCUTTLE

    def __str__(self) -> str:
        return f"Scuttle {self.target} with {self.card}"


@dataclass(frozen=True, slots=True)
class PlayOneOff(Move):
    """Play a card as a one-off effect."""

    card: Card
    effect: OneOffEffect
    target_card: Card | None = None  # For targeted effects (Two, Three, Nine)
    target_player: int | None = None  # For player-targeted effects

    @property
    def move_type(self) -> MoveType:
        return MoveType.PLAY_ONE_OFF

    def __str__(self) -> str:
        effect_names = {
            OneOffEffect.ACE_SCRAP_ALL_POINTS: "scrap all points",
            OneOffEffect.TWO_COUNTER: "counter",
            OneOffEffect.TWO_DESTROY_PERMANENT: f"destroy {self.target_card}",
            OneOffEffect.THREE_REVIVE: f"revive {self.target_card}",
            OneOffEffect.FOUR_DISCARD: "force discard",
            OneOffEffect.FIVE_DRAW_TWO: "draw two",
            OneOffEffect.SIX_SCRAP_ALL_PERMANENTS: "scrap all permanents",
            OneOffEffect.SEVEN_PLAY_FROM_DECK: "play from deck",
            OneOffEffect.NINE_RETURN_PERMANENT: f"return {self.target_card}",
        }
        return f"Play {self.card} as one-off ({effect_names.get(self.effect, self.effect.name)})"


@dataclass(frozen=True, slots=True)
class PlayPermanent(Move):
    """Play a permanent card (8, Jack, Queen, King)."""

    card: Card
    target_card: Card | None = None  # For Jack: target opponent's point card

    @property
    def move_type(self) -> MoveType:
        return MoveType.PLAY_PERMANENT

    def __str__(self) -> str:
        from cuttle_engine.cards import Rank

        if self.card.rank == Rank.JACK and self.target_card:
            return f"Play {self.card} to steal {self.target_card}"
        elif self.card.rank == Rank.EIGHT:
            return f"Play {self.card} as Glasses (see opponent's hand)"
        elif self.card.rank == Rank.QUEEN:
            return f"Play {self.card} for protection"
        elif self.card.rank == Rank.KING:
            return f"Play {self.card} to reduce win threshold"
        return f"Play {self.card} as permanent"


@dataclass(frozen=True, slots=True)
class Counter(Move):
    """Counter a one-off with a Two."""

    card: Card  # The Two being played

    @property
    def move_type(self) -> MoveType:
        return MoveType.COUNTER

    def __str__(self) -> str:
        return f"Counter with {self.card}"


@dataclass(frozen=True, slots=True)
class DeclineCounter(Move):
    """Decline to counter (let the one-off resolve)."""

    @property
    def move_type(self) -> MoveType:
        return MoveType.DECLINE_COUNTER

    def __str__(self) -> str:
        return "Decline to counter"


@dataclass(frozen=True, slots=True)
class ResolveSeven(Move):
    """Choose which card to play from Seven's reveal."""

    card: Card  # The card to play from the revealed cards
    play_as: MoveType  # How to play it (PLAY_POINTS, SCUTTLE, PLAY_ONE_OFF, PLAY_PERMANENT)
    target_card: Card | None = None  # For scuttle or targeted effects

    @property
    def move_type(self) -> MoveType:
        return MoveType.RESOLVE_SEVEN

    def __str__(self) -> str:
        return f"Seven: play {self.card} as {self.play_as.name}"


@dataclass(frozen=True, slots=True)
class Discard(Move):
    """Discard a card (for Four's effect)."""

    card: Card

    @property
    def move_type(self) -> MoveType:
        return MoveType.DISCARD

    def __str__(self) -> str:
        return f"Discard {self.card}"


@dataclass(frozen=True, slots=True)
class Pass(Move):
    """Pass the turn (only allowed when deck is empty)."""

    @property
    def move_type(self) -> MoveType:
        return MoveType.PASS

    def __str__(self) -> str:
        return "Pass"
