"""Immutable game state models for Cuttle."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum, auto
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from cuttle_engine.cards import Card


class GamePhase(IntEnum):
    """Current phase of the game."""

    MAIN = auto()  # Normal turn: player can draw, play, or pass
    COUNTER = auto()  # Waiting for opponent to counter with a Two
    RESOLVE_SEVEN = auto()  # Player must play a card from Seven's reveal
    DISCARD_FOUR = auto()  # Opponent must discard two cards (Four's effect)
    GAME_OVER = auto()  # Game has ended


class WinReason(IntEnum):
    """How the game was won."""

    POINTS = auto()  # Winner reached point threshold
    EMPTY_DECK_POINTS = auto()  # Deck empty, winner has more points
    OPPONENT_EMPTY_HAND = auto()  # Opponent has no cards in hand (cannot play)


@dataclass(frozen=True, slots=True)
class PlayerState:
    """State of a single player.

    Attributes:
        hand: Cards in hand (hidden from opponent)
        points_field: Cards played for points
        permanents: Active permanent cards (8s, Jacks, Queens, Kings)
        jacks: Cards stolen by Jacks (maps Jack -> stolen card)
    """

    hand: tuple[Card, ...]
    points_field: tuple[Card, ...]
    permanents: tuple[Card, ...]
    jacks: tuple[tuple[Card, Card], ...] = ()  # (Jack, stolen_card) pairs

    @property
    def point_total(self) -> int:
        """Total points from point cards (including Jack-stolen cards)."""
        total = sum(card.point_value for card in self.points_field)
        # Add points from cards we stole with Jacks
        total += sum(stolen.point_value for _, stolen in self.jacks)
        return total

    @property
    def queens_count(self) -> int:
        """Number of Queens protecting this player."""
        from cuttle_engine.cards import Rank

        return sum(1 for card in self.permanents if card.rank == Rank.QUEEN)

    @property
    def kings_count(self) -> int:
        """Number of Kings reducing point threshold."""
        from cuttle_engine.cards import Rank

        return sum(1 for card in self.permanents if card.rank == Rank.KING)

    @property
    def has_glasses(self) -> bool:
        """Whether player has an Eight (sees opponent's hand)."""
        from cuttle_engine.cards import Rank

        return any(card.rank == Rank.EIGHT for card in self.permanents)

    def with_hand(self, hand: tuple[Card, ...]) -> PlayerState:
        """Return new state with updated hand."""
        return PlayerState(
            hand=hand,
            points_field=self.points_field,
            permanents=self.permanents,
            jacks=self.jacks,
        )

    def with_points_field(self, points_field: tuple[Card, ...]) -> PlayerState:
        """Return new state with updated points field."""
        return PlayerState(
            hand=self.hand,
            points_field=points_field,
            permanents=self.permanents,
            jacks=self.jacks,
        )

    def with_permanents(self, permanents: tuple[Card, ...]) -> PlayerState:
        """Return new state with updated permanents."""
        return PlayerState(
            hand=self.hand,
            points_field=self.points_field,
            permanents=permanents,
            jacks=self.jacks,
        )

    def with_jacks(self, jacks: tuple[tuple[Card, Card], ...]) -> PlayerState:
        """Return new state with updated jacks."""
        return PlayerState(
            hand=self.hand,
            points_field=self.points_field,
            permanents=self.permanents,
            jacks=jacks,
        )


@dataclass(frozen=True, slots=True)
class CounterState:
    """State of a pending one-off that can be countered.

    Attributes:
        one_off_card: The card that was played as a one-off
        one_off_player: 0 or 1, who played the one-off
        target_card: Optional target of the one-off (for targeted effects)
        target_player: Optional target player (0 or 1)
        counter_chain: Stack of Twos played as counters
    """

    one_off_card: Card
    one_off_player: int
    target_card: Card | None = None
    target_player: int | None = None
    counter_chain: tuple[Card, ...] = ()

    @property
    def counter_count(self) -> int:
        """Number of Twos in the counter chain."""
        return len(self.counter_chain)

    @property
    def resolves(self) -> bool:
        """Whether the one-off resolves (even number of counters)."""
        return self.counter_count % 2 == 0

    @property
    def waiting_for_player(self) -> int:
        """Which player can counter next (alternates)."""
        if self.counter_count % 2 == 0:
            return 1 - self.one_off_player  # Opponent of original caster
        return self.one_off_player  # Original caster


@dataclass(frozen=True, slots=True)
class SevenState:
    """State when resolving a Seven (must play from top of deck).

    Attributes:
        revealed_cards: The top 1-2 cards revealed from deck
        player: Which player is resolving
    """

    revealed_cards: tuple[Card, ...]
    player: int


@dataclass(frozen=True, slots=True)
class FourState:
    """State when opponent must discard due to Four.

    Attributes:
        player: Which player must discard
        cards_to_discard: How many cards they must discard (usually 2)
    """

    player: int
    cards_to_discard: int = 2


@dataclass(frozen=True, slots=True)
class GameState:
    """Complete immutable game state.

    Attributes:
        players: Tuple of two PlayerStates (index 0 and 1)
        deck: Remaining cards in draw pile
        scrap: Cards in the scrap pile (discard)
        current_player: 0 or 1, whose turn it is
        phase: Current game phase
        turn_number: Current turn (increments after each player's turn)
        consecutive_passes: Number of consecutive passes (for stalemate)
        counter_state: Present if in COUNTER phase
        seven_state: Present if in RESOLVE_SEVEN phase
        four_state: Present if in DISCARD_FOUR phase
        winner: 0, 1, or None if game ongoing
        win_reason: How the game was won
    """

    players: tuple[PlayerState, PlayerState]
    deck: tuple[Card, ...]
    scrap: tuple[Card, ...]
    current_player: int
    phase: GamePhase = GamePhase.MAIN
    turn_number: int = 1
    consecutive_passes: int = 0
    counter_state: CounterState | None = None
    seven_state: SevenState | None = None
    four_state: FourState | None = None
    winner: int | None = None
    win_reason: WinReason | None = None

    @property
    def opponent(self) -> int:
        """The other player (not current_player)."""
        return 1 - self.current_player

    @property
    def current_player_state(self) -> PlayerState:
        """State of the current player."""
        return self.players[self.current_player]

    @property
    def opponent_state(self) -> PlayerState:
        """State of the opponent."""
        return self.players[self.opponent]

    @property
    def is_game_over(self) -> bool:
        """Whether the game has ended."""
        return self.winner is not None

    def point_threshold(self, player: int) -> int:
        """Point threshold for a player to win (21 minus 7 per King)."""
        kings = self.players[player].kings_count
        return max(21 - (7 * kings), 7)  # Minimum 7 with 2+ Kings

    def check_winner(self) -> tuple[int | None, WinReason | None]:
        """Check if someone has won.

        Returns:
            Tuple of (winner, reason) or (None, None) if game continues.
        """
        # Check point threshold victory
        for i in range(2):
            if self.players[i].point_total >= self.point_threshold(i):
                return i, WinReason.POINTS

        # Check if deck is empty and current player can't draw
        if len(self.deck) == 0:
            p0_points = self.players[0].point_total
            p1_points = self.players[1].point_total
            if p0_points != p1_points:
                if p0_points > p1_points:
                    return 0, WinReason.EMPTY_DECK_POINTS
                return 1, WinReason.EMPTY_DECK_POINTS

        # Check if any player has no cards and can't draw
        if len(self.deck) == 0:
            for i in range(2):
                if len(self.players[i].hand) == 0:
                    # Player with cards remaining wins
                    return 1 - i, WinReason.OPPONENT_EMPTY_HAND

        return None, None

    def with_players(self, players: tuple[PlayerState, PlayerState]) -> GameState:
        """Return new state with updated players."""
        return GameState(
            players=players,
            deck=self.deck,
            scrap=self.scrap,
            current_player=self.current_player,
            phase=self.phase,
            turn_number=self.turn_number,
            consecutive_passes=self.consecutive_passes,
            counter_state=self.counter_state,
            seven_state=self.seven_state,
            four_state=self.four_state,
            winner=self.winner,
            win_reason=self.win_reason,
        )

    def with_deck(self, deck: tuple[Card, ...]) -> GameState:
        """Return new state with updated deck."""
        return GameState(
            players=self.players,
            deck=deck,
            scrap=self.scrap,
            current_player=self.current_player,
            phase=self.phase,
            turn_number=self.turn_number,
            consecutive_passes=self.consecutive_passes,
            counter_state=self.counter_state,
            seven_state=self.seven_state,
            four_state=self.four_state,
            winner=self.winner,
            win_reason=self.win_reason,
        )

    def with_scrap(self, scrap: tuple[Card, ...]) -> GameState:
        """Return new state with updated scrap pile."""
        return GameState(
            players=self.players,
            deck=self.deck,
            scrap=scrap,
            current_player=self.current_player,
            phase=self.phase,
            turn_number=self.turn_number,
            consecutive_passes=self.consecutive_passes,
            counter_state=self.counter_state,
            seven_state=self.seven_state,
            four_state=self.four_state,
            winner=self.winner,
            win_reason=self.win_reason,
        )

    def with_current_player(self, current_player: int) -> GameState:
        """Return new state with updated current player."""
        return GameState(
            players=self.players,
            deck=self.deck,
            scrap=self.scrap,
            current_player=current_player,
            phase=self.phase,
            turn_number=self.turn_number,
            consecutive_passes=self.consecutive_passes,
            counter_state=self.counter_state,
            seven_state=self.seven_state,
            four_state=self.four_state,
            winner=self.winner,
            win_reason=self.win_reason,
        )

    def with_phase(self, phase: GamePhase) -> GameState:
        """Return new state with updated phase."""
        return GameState(
            players=self.players,
            deck=self.deck,
            scrap=self.scrap,
            current_player=self.current_player,
            phase=phase,
            turn_number=self.turn_number,
            consecutive_passes=self.consecutive_passes,
            counter_state=self.counter_state,
            seven_state=self.seven_state,
            four_state=self.four_state,
            winner=self.winner,
            win_reason=self.win_reason,
        )

    def with_turn_number(self, turn_number: int) -> GameState:
        """Return new state with updated turn number."""
        return GameState(
            players=self.players,
            deck=self.deck,
            scrap=self.scrap,
            current_player=self.current_player,
            phase=self.phase,
            turn_number=turn_number,
            consecutive_passes=self.consecutive_passes,
            counter_state=self.counter_state,
            seven_state=self.seven_state,
            four_state=self.four_state,
            winner=self.winner,
            win_reason=self.win_reason,
        )

    def with_consecutive_passes(self, consecutive_passes: int) -> GameState:
        """Return new state with updated consecutive passes."""
        return GameState(
            players=self.players,
            deck=self.deck,
            scrap=self.scrap,
            current_player=self.current_player,
            phase=self.phase,
            turn_number=self.turn_number,
            consecutive_passes=consecutive_passes,
            counter_state=self.counter_state,
            seven_state=self.seven_state,
            four_state=self.four_state,
            winner=self.winner,
            win_reason=self.win_reason,
        )

    def with_counter_state(self, counter_state: CounterState | None) -> GameState:
        """Return new state with updated counter state."""
        return GameState(
            players=self.players,
            deck=self.deck,
            scrap=self.scrap,
            current_player=self.current_player,
            phase=self.phase,
            turn_number=self.turn_number,
            consecutive_passes=self.consecutive_passes,
            counter_state=counter_state,
            seven_state=self.seven_state,
            four_state=self.four_state,
            winner=self.winner,
            win_reason=self.win_reason,
        )

    def with_seven_state(self, seven_state: SevenState | None) -> GameState:
        """Return new state with updated seven state."""
        return GameState(
            players=self.players,
            deck=self.deck,
            scrap=self.scrap,
            current_player=self.current_player,
            phase=self.phase,
            turn_number=self.turn_number,
            consecutive_passes=self.consecutive_passes,
            counter_state=self.counter_state,
            seven_state=seven_state,
            four_state=self.four_state,
            winner=self.winner,
            win_reason=self.win_reason,
        )

    def with_four_state(self, four_state: FourState | None) -> GameState:
        """Return new state with updated four state."""
        return GameState(
            players=self.players,
            deck=self.deck,
            scrap=self.scrap,
            current_player=self.current_player,
            phase=self.phase,
            turn_number=self.turn_number,
            consecutive_passes=self.consecutive_passes,
            counter_state=self.counter_state,
            seven_state=self.seven_state,
            four_state=four_state,
            winner=self.winner,
            win_reason=self.win_reason,
        )

    def with_winner(self, winner: int | None, win_reason: WinReason | None) -> GameState:
        """Return new state with winner set."""
        return GameState(
            players=self.players,
            deck=self.deck,
            scrap=self.scrap,
            current_player=self.current_player,
            phase=GamePhase.GAME_OVER if winner is not None else self.phase,
            turn_number=self.turn_number,
            consecutive_passes=self.consecutive_passes,
            counter_state=self.counter_state,
            seven_state=self.seven_state,
            four_state=self.four_state,
            winner=winner,
            win_reason=win_reason,
        )


def create_initial_state(deck: list[Card] | None = None, seed: int | None = None) -> GameState:
    """Create the initial game state.

    Args:
        deck: Optional pre-ordered deck. If None, creates and shuffles a new deck.
        seed: Random seed for shuffling (only used if deck is None).

    Returns:
        Initial game state with cards dealt.
    """
    from cuttle_engine.cards import create_deck, shuffle_deck

    if deck is None:
        deck = shuffle_deck(create_deck(), seed)

    # Deal 6 cards to player 0 (goes second, gets extra card)
    # Deal 5 cards to player 1 (goes first)
    # Actually in Cuttle: player who goes first gets 5, second gets 6
    # First player is player 0 in our model
    hand0 = tuple(deck[:5])  # First player gets 5 cards
    hand1 = tuple(deck[5:11])  # Second player gets 6 cards
    remaining_deck = tuple(deck[11:])

    player0 = PlayerState(hand=hand0, points_field=(), permanents=())
    player1 = PlayerState(hand=hand1, points_field=(), permanents=())

    return GameState(
        players=(player0, player1),
        deck=remaining_deck,
        scrap=(),
        current_player=0,  # Player 0 goes first (with 5 cards)
        phase=GamePhase.MAIN,
    )
