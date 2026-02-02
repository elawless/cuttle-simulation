"""Tests for move execution."""

import pytest

from cuttle_engine.cards import Card, Rank, Suit
from cuttle_engine.executor import IllegalMoveError, execute_move
from cuttle_engine.moves import (
    Counter,
    DeclineCounter,
    Discard,
    Draw,
    OneOffEffect,
    Pass,
    PlayOneOff,
    PlayPermanent,
    PlayPoints,
    Scuttle,
)
from cuttle_engine.state import (
    CounterState,
    FourState,
    GamePhase,
    GameState,
    PlayerState,
    WinReason,
    create_initial_state,
)


class TestDraw:
    def test_draw_adds_card_to_hand(self):
        state = create_initial_state(seed=42)
        initial_hand_size = len(state.current_player_state.hand)
        top_card = state.deck[0]

        new_state = execute_move(state, Draw())

        # Card moved from deck to hand
        assert len(new_state.deck) == len(state.deck) - 1
        assert top_card in new_state.players[0].hand
        # Turn ended
        assert new_state.current_player == 1

    def test_draw_from_empty_deck_fails(self):
        player0 = PlayerState(hand=(), points_field=(), permanents=())
        player1 = PlayerState(hand=(), points_field=(), permanents=())
        state = GameState(
            players=(player0, player1),
            deck=(),
            scrap=(),
            current_player=0,
        )

        with pytest.raises(IllegalMoveError):
            execute_move(state, Draw())


class TestPlayPoints:
    def test_play_for_points(self):
        ace = Card(Rank.ACE, Suit.CLUBS)
        player0 = PlayerState(hand=(ace,), points_field=(), permanents=())
        player1 = PlayerState(hand=(), points_field=(), permanents=())
        state = GameState(
            players=(player0, player1),
            deck=(Card(Rank.TWO, Suit.HEARTS),),
            scrap=(),
            current_player=0,
        )

        new_state = execute_move(state, PlayPoints(card=ace))

        assert ace not in new_state.players[0].hand
        assert ace in new_state.players[0].points_field
        assert new_state.current_player == 1

    def test_play_face_card_for_points_fails(self):
        jack = Card(Rank.JACK, Suit.CLUBS)
        player0 = PlayerState(hand=(jack,), points_field=(), permanents=())
        player1 = PlayerState(hand=(), points_field=(), permanents=())
        state = GameState(
            players=(player0, player1),
            deck=(Card(Rank.TWO, Suit.HEARTS),),
            scrap=(),
            current_player=0,
        )

        with pytest.raises(IllegalMoveError):
            execute_move(state, PlayPoints(card=jack))

    def test_win_by_reaching_21_points(self):
        ten1 = Card(Rank.TEN, Suit.CLUBS)
        ten2 = Card(Rank.TEN, Suit.SPADES)
        ace = Card(Rank.ACE, Suit.HEARTS)

        player0 = PlayerState(
            hand=(ace,), points_field=(ten1, ten2), permanents=()
        )  # Has 20 points
        player1 = PlayerState(hand=(), points_field=(), permanents=())
        state = GameState(
            players=(player0, player1),
            deck=(Card(Rank.TWO, Suit.HEARTS),),
            scrap=(),
            current_player=0,
        )

        new_state = execute_move(state, PlayPoints(card=ace))

        assert new_state.is_game_over
        assert new_state.winner == 0
        assert new_state.win_reason == WinReason.POINTS


class TestScuttle:
    def test_scuttle_destroys_both_cards(self):
        two = Card(Rank.TWO, Suit.CLUBS)
        ace = Card(Rank.ACE, Suit.SPADES)

        player0 = PlayerState(hand=(two,), points_field=(), permanents=())
        player1 = PlayerState(hand=(), points_field=(ace,), permanents=())
        state = GameState(
            players=(player0, player1),
            deck=(Card(Rank.THREE, Suit.HEARTS),),
            scrap=(),
            current_player=0,
        )

        new_state = execute_move(state, Scuttle(card=two, target=ace))

        assert two not in new_state.players[0].hand
        assert ace not in new_state.players[1].points_field
        assert two in new_state.scrap
        assert ace in new_state.scrap

    def test_cannot_scuttle_higher_card(self):
        ace = Card(Rank.ACE, Suit.CLUBS)
        two = Card(Rank.TWO, Suit.SPADES)

        player0 = PlayerState(hand=(ace,), points_field=(), permanents=())
        player1 = PlayerState(hand=(), points_field=(two,), permanents=())
        state = GameState(
            players=(player0, player1),
            deck=(Card(Rank.THREE, Suit.HEARTS),),
            scrap=(),
            current_player=0,
        )

        with pytest.raises(IllegalMoveError):
            execute_move(state, Scuttle(card=ace, target=two))


class TestOneOff:
    def test_one_off_enters_counter_phase(self):
        ace = Card(Rank.ACE, Suit.CLUBS)
        five = Card(Rank.FIVE, Suit.SPADES)

        player0 = PlayerState(hand=(ace,), points_field=(), permanents=())
        player1 = PlayerState(hand=(), points_field=(five,), permanents=())
        state = GameState(
            players=(player0, player1),
            deck=(Card(Rank.THREE, Suit.HEARTS),),
            scrap=(),
            current_player=0,
        )

        new_state = execute_move(
            state, PlayOneOff(card=ace, effect=OneOffEffect.ACE_SCRAP_ALL_POINTS)
        )

        assert new_state.phase == GamePhase.COUNTER
        assert new_state.counter_state is not None
        assert new_state.counter_state.one_off_card == ace
        assert ace not in new_state.players[0].hand


class TestCounter:
    def test_counter_adds_to_chain(self):
        ace = Card(Rank.ACE, Suit.CLUBS)
        two = Card(Rank.TWO, Suit.SPADES)

        counter_state = CounterState(one_off_card=ace, one_off_player=0)

        player0 = PlayerState(hand=(), points_field=(), permanents=())
        player1 = PlayerState(hand=(two,), points_field=(), permanents=())
        state = GameState(
            players=(player0, player1),
            deck=(Card(Rank.THREE, Suit.HEARTS),),
            scrap=(),
            current_player=0,
            phase=GamePhase.COUNTER,
            counter_state=counter_state,
        )

        new_state = execute_move(state, Counter(card=two))

        assert new_state.phase == GamePhase.COUNTER
        assert two in new_state.counter_state.counter_chain
        assert two not in new_state.players[1].hand

    def test_decline_counter_resolves_effect(self):
        ace = Card(Rank.ACE, Suit.CLUBS)
        five = Card(Rank.FIVE, Suit.SPADES)

        counter_state = CounterState(one_off_card=ace, one_off_player=0)

        player0 = PlayerState(hand=(), points_field=(), permanents=())
        player1 = PlayerState(hand=(), points_field=(five,), permanents=())
        state = GameState(
            players=(player0, player1),
            deck=(Card(Rank.THREE, Suit.HEARTS),),
            scrap=(),
            current_player=0,
            phase=GamePhase.COUNTER,
            counter_state=counter_state,
        )

        new_state = execute_move(state, DeclineCounter())

        # Ace effect resolved - all points scrapped
        assert len(new_state.players[1].points_field) == 0
        assert five in new_state.scrap
        assert ace in new_state.scrap
        assert new_state.phase == GamePhase.MAIN

    def test_counter_chain_cancels_effect(self):
        ace = Card(Rank.ACE, Suit.CLUBS)
        two = Card(Rank.TWO, Suit.SPADES)
        five = Card(Rank.FIVE, Suit.HEARTS)

        counter_state = CounterState(
            one_off_card=ace, one_off_player=0, counter_chain=(two,)
        )

        player0 = PlayerState(hand=(), points_field=(), permanents=())
        player1 = PlayerState(hand=(), points_field=(five,), permanents=())
        state = GameState(
            players=(player0, player1),
            deck=(Card(Rank.THREE, Suit.HEARTS),),
            scrap=(),
            current_player=0,
            phase=GamePhase.COUNTER,
            counter_state=counter_state,
        )

        new_state = execute_move(state, DeclineCounter())

        # Effect cancelled - points remain
        assert five in new_state.players[1].points_field
        assert ace in new_state.scrap
        assert two in new_state.scrap


class TestPermanents:
    def test_play_eight_glasses(self):
        eight = Card(Rank.EIGHT, Suit.CLUBS)

        player0 = PlayerState(hand=(eight,), points_field=(), permanents=())
        player1 = PlayerState(hand=(), points_field=(), permanents=())
        state = GameState(
            players=(player0, player1),
            deck=(Card(Rank.ACE, Suit.HEARTS),),
            scrap=(),
            current_player=0,
        )

        new_state = execute_move(state, PlayPermanent(card=eight))

        assert eight in new_state.players[0].permanents
        assert new_state.players[0].has_glasses

    def test_play_jack_steals_card(self):
        jack = Card(Rank.JACK, Suit.CLUBS)
        five = Card(Rank.FIVE, Suit.SPADES)

        player0 = PlayerState(hand=(jack,), points_field=(), permanents=())
        player1 = PlayerState(hand=(), points_field=(five,), permanents=())
        state = GameState(
            players=(player0, player1),
            deck=(Card(Rank.ACE, Suit.HEARTS),),
            scrap=(),
            current_player=0,
        )

        new_state = execute_move(state, PlayPermanent(card=jack, target_card=five))

        assert five not in new_state.players[1].points_field
        assert (jack, five) in new_state.players[0].jacks
        assert new_state.players[0].point_total == 5

    def test_play_queen_provides_protection(self):
        queen = Card(Rank.QUEEN, Suit.CLUBS)

        player0 = PlayerState(hand=(queen,), points_field=(), permanents=())
        player1 = PlayerState(hand=(), points_field=(), permanents=())
        state = GameState(
            players=(player0, player1),
            deck=(Card(Rank.ACE, Suit.HEARTS),),
            scrap=(),
            current_player=0,
        )

        new_state = execute_move(state, PlayPermanent(card=queen))

        assert queen in new_state.players[0].permanents
        assert new_state.players[0].queens_count == 1

    def test_play_king_reduces_threshold(self):
        king = Card(Rank.KING, Suit.CLUBS)

        player0 = PlayerState(hand=(king,), points_field=(), permanents=())
        player1 = PlayerState(hand=(), points_field=(), permanents=())
        state = GameState(
            players=(player0, player1),
            deck=(Card(Rank.ACE, Suit.HEARTS),),
            scrap=(),
            current_player=0,
        )

        new_state = execute_move(state, PlayPermanent(card=king))

        assert new_state.point_threshold(0) == 14  # 21 - 7


class TestFourEffect:
    def test_four_triggers_discard_phase(self):
        four = Card(Rank.FOUR, Suit.CLUBS)
        ace = Card(Rank.ACE, Suit.SPADES)
        two = Card(Rank.TWO, Suit.HEARTS)

        counter_state = CounterState(
            one_off_card=four, one_off_player=0, target_player=1
        )

        player0 = PlayerState(hand=(), points_field=(), permanents=())
        player1 = PlayerState(hand=(ace, two), points_field=(), permanents=())
        state = GameState(
            players=(player0, player1),
            deck=(Card(Rank.THREE, Suit.HEARTS),),
            scrap=(),
            current_player=0,
            phase=GamePhase.COUNTER,
            counter_state=counter_state,
        )

        new_state = execute_move(state, DeclineCounter())

        assert new_state.phase == GamePhase.DISCARD_FOUR
        assert new_state.four_state is not None
        assert new_state.four_state.player == 1
        assert new_state.four_state.cards_to_discard == 2

    def test_discard_removes_card(self):
        ace = Card(Rank.ACE, Suit.CLUBS)
        two = Card(Rank.TWO, Suit.SPADES)

        four_state = FourState(player=1, cards_to_discard=2)

        player0 = PlayerState(hand=(), points_field=(), permanents=())
        player1 = PlayerState(hand=(ace, two), points_field=(), permanents=())
        state = GameState(
            players=(player0, player1),
            deck=(Card(Rank.THREE, Suit.HEARTS),),
            scrap=(),
            current_player=0,
            phase=GamePhase.DISCARD_FOUR,
            four_state=four_state,
        )

        new_state = execute_move(state, Discard(card=ace))

        assert ace not in new_state.players[1].hand
        assert ace in new_state.scrap
        assert new_state.phase == GamePhase.DISCARD_FOUR
        assert new_state.four_state.cards_to_discard == 1


class TestPass:
    def test_pass_when_deck_empty(self):
        ace = Card(Rank.ACE, Suit.CLUBS)

        player0 = PlayerState(hand=(ace,), points_field=(), permanents=())
        player1 = PlayerState(hand=(), points_field=(), permanents=())
        state = GameState(
            players=(player0, player1),
            deck=(),
            scrap=(),
            current_player=0,
        )

        new_state = execute_move(state, Pass())

        assert new_state.consecutive_passes == 1
        assert new_state.current_player == 1

    def test_cannot_pass_when_deck_not_empty(self):
        state = create_initial_state(seed=42)

        with pytest.raises(IllegalMoveError):
            execute_move(state, Pass())


class TestFiveEffect:
    def test_five_draws_two_cards(self):
        five = Card(Rank.FIVE, Suit.CLUBS)
        card1 = Card(Rank.ACE, Suit.SPADES)
        card2 = Card(Rank.TWO, Suit.HEARTS)

        counter_state = CounterState(one_off_card=five, one_off_player=0)

        player0 = PlayerState(hand=(), points_field=(), permanents=())
        player1 = PlayerState(hand=(), points_field=(), permanents=())
        state = GameState(
            players=(player0, player1),
            deck=(card1, card2, Card(Rank.THREE, Suit.DIAMONDS)),
            scrap=(),
            current_player=0,
            phase=GamePhase.COUNTER,
            counter_state=counter_state,
        )

        new_state = execute_move(state, DeclineCounter())

        assert card1 in new_state.players[0].hand
        assert card2 in new_state.players[0].hand
        assert len(new_state.deck) == 1


class TestThreeEffect:
    def test_three_revives_from_scrap(self):
        three = Card(Rank.THREE, Suit.CLUBS)
        ace = Card(Rank.ACE, Suit.SPADES)

        counter_state = CounterState(
            one_off_card=three, one_off_player=0, target_card=ace
        )

        player0 = PlayerState(hand=(), points_field=(), permanents=())
        player1 = PlayerState(hand=(), points_field=(), permanents=())
        state = GameState(
            players=(player0, player1),
            deck=(Card(Rank.TWO, Suit.HEARTS),),
            scrap=(ace,),
            current_player=0,
            phase=GamePhase.COUNTER,
            counter_state=counter_state,
        )

        new_state = execute_move(state, DeclineCounter())

        assert ace in new_state.players[0].hand
        assert ace not in new_state.scrap


class TestSixEffect:
    def test_six_scraps_all_permanents(self):
        six = Card(Rank.SIX, Suit.CLUBS)
        queen = Card(Rank.QUEEN, Suit.SPADES)
        king = Card(Rank.KING, Suit.HEARTS)

        counter_state = CounterState(one_off_card=six, one_off_player=0)

        player0 = PlayerState(hand=(), points_field=(), permanents=(queen,))
        player1 = PlayerState(hand=(), points_field=(), permanents=(king,))
        state = GameState(
            players=(player0, player1),
            deck=(Card(Rank.TWO, Suit.HEARTS),),
            scrap=(),
            current_player=0,
            phase=GamePhase.COUNTER,
            counter_state=counter_state,
        )

        new_state = execute_move(state, DeclineCounter())

        assert len(new_state.players[0].permanents) == 0
        assert len(new_state.players[1].permanents) == 0
        assert queen in new_state.scrap
        assert king in new_state.scrap


class TestNineEffect:
    def test_nine_returns_permanent_to_hand(self):
        nine = Card(Rank.NINE, Suit.CLUBS)
        queen = Card(Rank.QUEEN, Suit.SPADES)

        counter_state = CounterState(
            one_off_card=nine, one_off_player=0, target_card=queen, target_player=1
        )

        player0 = PlayerState(hand=(), points_field=(), permanents=())
        player1 = PlayerState(hand=(), points_field=(), permanents=(queen,))
        state = GameState(
            players=(player0, player1),
            deck=(Card(Rank.TWO, Suit.HEARTS),),
            scrap=(),
            current_player=0,
            phase=GamePhase.COUNTER,
            counter_state=counter_state,
        )

        new_state = execute_move(state, DeclineCounter())

        assert queen not in new_state.players[1].permanents
        assert queen in new_state.players[1].hand
