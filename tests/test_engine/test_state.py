"""Tests for game state models."""

import pytest

from cuttle_engine.cards import Card, Rank, Suit, create_deck
from cuttle_engine.state import (
    CounterState,
    FourState,
    GamePhase,
    GameState,
    PlayerState,
    SevenState,
    WinReason,
    create_initial_state,
)


class TestPlayerState:
    def test_empty_player(self):
        player = PlayerState(hand=(), points_field=(), permanents=())
        assert len(player.hand) == 0
        assert player.point_total == 0
        assert player.queens_count == 0
        assert player.kings_count == 0
        assert not player.has_glasses

    def test_point_total(self):
        ace = Card(Rank.ACE, Suit.CLUBS)
        ten = Card(Rank.TEN, Suit.CLUBS)
        player = PlayerState(hand=(), points_field=(ace, ten), permanents=())
        assert player.point_total == 11

    def test_point_total_with_jacks(self):
        ace = Card(Rank.ACE, Suit.CLUBS)
        jack = Card(Rank.JACK, Suit.SPADES)
        ten = Card(Rank.TEN, Suit.HEARTS)  # Stolen by jack

        player = PlayerState(
            hand=(), points_field=(ace,), permanents=(), jacks=((jack, ten),)
        )
        assert player.point_total == 11  # 1 + 10

    def test_queens_count(self):
        queen1 = Card(Rank.QUEEN, Suit.CLUBS)
        queen2 = Card(Rank.QUEEN, Suit.SPADES)
        king = Card(Rank.KING, Suit.HEARTS)

        player = PlayerState(hand=(), points_field=(), permanents=(queen1, queen2, king))
        assert player.queens_count == 2

    def test_kings_count(self):
        king1 = Card(Rank.KING, Suit.CLUBS)
        king2 = Card(Rank.KING, Suit.SPADES)
        queen = Card(Rank.QUEEN, Suit.HEARTS)

        player = PlayerState(hand=(), points_field=(), permanents=(king1, king2, queen))
        assert player.kings_count == 2

    def test_has_glasses(self):
        eight = Card(Rank.EIGHT, Suit.CLUBS)
        player = PlayerState(hand=(), points_field=(), permanents=(eight,))
        assert player.has_glasses

        player_no_eight = PlayerState(hand=(), points_field=(), permanents=())
        assert not player_no_eight.has_glasses

    def test_with_hand(self):
        ace = Card(Rank.ACE, Suit.CLUBS)
        player = PlayerState(hand=(), points_field=(), permanents=())
        new_player = player.with_hand((ace,))
        assert ace in new_player.hand
        assert len(player.hand) == 0  # Original unchanged


class TestGameState:
    def test_initial_state(self):
        state = create_initial_state(seed=42)
        assert len(state.players) == 2
        assert len(state.players[0].hand) == 5  # First player
        assert len(state.players[1].hand) == 6  # Second player
        assert len(state.deck) == 41  # 52 - 11 dealt
        assert state.current_player == 0
        assert state.phase == GamePhase.MAIN
        assert state.turn_number == 1
        assert not state.is_game_over

    def test_initial_state_deterministic(self):
        state1 = create_initial_state(seed=42)
        state2 = create_initial_state(seed=42)
        assert state1.players[0].hand == state2.players[0].hand
        assert state1.deck == state2.deck

    def test_opponent(self):
        state = create_initial_state(seed=42)
        assert state.opponent == 1
        state2 = state.with_current_player(1)
        assert state2.opponent == 0

    def test_point_threshold_no_kings(self):
        state = create_initial_state(seed=42)
        assert state.point_threshold(0) == 21
        assert state.point_threshold(1) == 21

    def test_point_threshold_with_kings(self):
        king1 = Card(Rank.KING, Suit.CLUBS)
        king2 = Card(Rank.KING, Suit.SPADES)

        player = PlayerState(hand=(), points_field=(), permanents=(king1,))
        state = create_initial_state(seed=42)
        state = state.with_players((player, state.players[1]))

        assert state.point_threshold(0) == 14  # 21 - 7

        # Two kings
        player2 = PlayerState(hand=(), points_field=(), permanents=(king1, king2))
        state2 = state.with_players((player2, state.players[1]))
        assert state2.point_threshold(0) == 7  # Minimum

    def test_check_winner_by_points(self):
        # Give player 0 exactly 21 points
        ten1 = Card(Rank.TEN, Suit.CLUBS)
        ten2 = Card(Rank.TEN, Suit.SPADES)
        ace = Card(Rank.ACE, Suit.HEARTS)

        player0 = PlayerState(hand=(), points_field=(ten1, ten2, ace), permanents=())
        player1 = PlayerState(hand=(), points_field=(), permanents=())

        state = GameState(
            players=(player0, player1),
            deck=(),
            scrap=(),
            current_player=0,
        )

        winner, reason = state.check_winner()
        assert winner == 0
        assert reason == WinReason.POINTS

    def test_check_winner_empty_deck_more_points(self):
        ten = Card(Rank.TEN, Suit.CLUBS)
        ace = Card(Rank.ACE, Suit.HEARTS)

        player0 = PlayerState(hand=(), points_field=(ten,), permanents=())
        player1 = PlayerState(hand=(), points_field=(ace,), permanents=())

        state = GameState(
            players=(player0, player1),
            deck=(),  # Empty deck
            scrap=(),
            current_player=0,
        )

        winner, reason = state.check_winner()
        assert winner == 0
        assert reason == WinReason.EMPTY_DECK_POINTS


class TestCounterState:
    def test_counter_chain(self):
        ace = Card(Rank.ACE, Suit.CLUBS)
        two1 = Card(Rank.TWO, Suit.SPADES)
        two2 = Card(Rank.TWO, Suit.HEARTS)

        # One-off played, no counters yet
        cs = CounterState(one_off_card=ace, one_off_player=0)
        assert cs.counter_count == 0
        assert cs.resolves  # Even counters = resolves
        assert cs.waiting_for_player == 1  # Opponent responds first

        # One counter
        cs2 = CounterState(
            one_off_card=ace, one_off_player=0, counter_chain=(two1,)
        )
        assert cs2.counter_count == 1
        assert not cs2.resolves  # Odd counters = cancelled
        assert cs2.waiting_for_player == 0  # Original caster responds

        # Two counters
        cs3 = CounterState(
            one_off_card=ace, one_off_player=0, counter_chain=(two1, two2)
        )
        assert cs3.counter_count == 2
        assert cs3.resolves  # Even counters = resolves
        assert cs3.waiting_for_player == 1


class TestSevenState:
    def test_seven_state(self):
        ace = Card(Rank.ACE, Suit.CLUBS)
        ss = SevenState(revealed_cards=(ace,), player=0)
        assert ace in ss.revealed_cards
        assert ss.player == 0


class TestFourState:
    def test_four_state(self):
        fs = FourState(player=1, cards_to_discard=2)
        assert fs.player == 1
        assert fs.cards_to_discard == 2
