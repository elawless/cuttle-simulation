"""Tests for move generation."""

import pytest

from cuttle_engine.cards import Card, Rank, Suit
from cuttle_engine.move_generator import generate_legal_moves
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
    Scuttle,
)
from cuttle_engine.state import (
    CounterState,
    FourState,
    GamePhase,
    GameState,
    PlayerState,
    SevenState,
    create_initial_state,
)


class TestMainPhaseMoves:
    def test_can_draw_when_deck_not_empty(self):
        state = create_initial_state(seed=42)
        moves = generate_legal_moves(state)
        assert any(isinstance(m, Draw) for m in moves)

    def test_cannot_draw_when_deck_empty(self):
        player0 = PlayerState(
            hand=(Card(Rank.ACE, Suit.CLUBS),), points_field=(), permanents=()
        )
        player1 = PlayerState(hand=(), points_field=(), permanents=())
        state = GameState(
            players=(player0, player1),
            deck=(),  # Empty
            scrap=(),
            current_player=0,
        )
        moves = generate_legal_moves(state)
        assert not any(isinstance(m, Draw) for m in moves)

    def test_can_pass_when_deck_empty(self):
        player0 = PlayerState(
            hand=(Card(Rank.ACE, Suit.CLUBS),), points_field=(), permanents=()
        )
        player1 = PlayerState(hand=(), points_field=(), permanents=())
        state = GameState(
            players=(player0, player1),
            deck=(),
            scrap=(),
            current_player=0,
        )
        moves = generate_legal_moves(state)
        assert any(isinstance(m, Pass) for m in moves)

    def test_cannot_pass_when_deck_not_empty(self):
        state = create_initial_state(seed=42)
        moves = generate_legal_moves(state)
        assert not any(isinstance(m, Pass) for m in moves)

    def test_can_play_for_points(self):
        ace = Card(Rank.ACE, Suit.CLUBS)
        player0 = PlayerState(hand=(ace,), points_field=(), permanents=())
        player1 = PlayerState(hand=(), points_field=(), permanents=())
        state = GameState(
            players=(player0, player1),
            deck=(Card(Rank.TWO, Suit.HEARTS),),
            scrap=(),
            current_player=0,
        )
        moves = generate_legal_moves(state)
        point_moves = [m for m in moves if isinstance(m, PlayPoints)]
        assert len(point_moves) == 1
        assert point_moves[0].card == ace

    def test_can_scuttle_lower_card(self):
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
        moves = generate_legal_moves(state)
        scuttle_moves = [m for m in moves if isinstance(m, Scuttle)]
        assert len(scuttle_moves) == 1
        assert scuttle_moves[0].card == two
        assert scuttle_moves[0].target == ace

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
        moves = generate_legal_moves(state)
        scuttle_moves = [m for m in moves if isinstance(m, Scuttle)]
        assert len(scuttle_moves) == 0

    def test_queen_protects_from_scuttle(self):
        ten = Card(Rank.TEN, Suit.CLUBS)
        five = Card(Rank.FIVE, Suit.SPADES)
        queen = Card(Rank.QUEEN, Suit.HEARTS)

        player0 = PlayerState(hand=(ten,), points_field=(), permanents=())
        player1 = PlayerState(hand=(), points_field=(five,), permanents=(queen,))
        state = GameState(
            players=(player0, player1),
            deck=(Card(Rank.THREE, Suit.HEARTS),),
            scrap=(),
            current_player=0,
        )
        moves = generate_legal_moves(state)
        scuttle_moves = [m for m in moves if isinstance(m, Scuttle)]
        assert len(scuttle_moves) == 0  # Protected by Queen


class TestOneOffMoves:
    def test_ace_one_off_when_points_exist(self):
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
        moves = generate_legal_moves(state)
        one_off_moves = [
            m for m in moves if isinstance(m, PlayOneOff) and m.card == ace
        ]
        assert len(one_off_moves) == 1

    def test_two_destroy_permanent(self):
        two = Card(Rank.TWO, Suit.CLUBS)
        queen = Card(Rank.QUEEN, Suit.SPADES)

        player0 = PlayerState(hand=(two,), points_field=(), permanents=())
        player1 = PlayerState(hand=(), points_field=(), permanents=(queen,))
        state = GameState(
            players=(player0, player1),
            deck=(Card(Rank.THREE, Suit.HEARTS),),
            scrap=(),
            current_player=0,
        )
        moves = generate_legal_moves(state)
        two_moves = [m for m in moves if isinstance(m, PlayOneOff) and m.card == two]
        assert len(two_moves) == 1
        assert two_moves[0].target_card == queen

    def test_three_revive_from_scrap(self):
        three = Card(Rank.THREE, Suit.CLUBS)
        ace = Card(Rank.ACE, Suit.SPADES)

        player0 = PlayerState(hand=(three,), points_field=(), permanents=())
        player1 = PlayerState(hand=(), points_field=(), permanents=())
        state = GameState(
            players=(player0, player1),
            deck=(Card(Rank.FIVE, Suit.HEARTS),),
            scrap=(ace,),
            current_player=0,
        )
        moves = generate_legal_moves(state)
        three_moves = [
            m for m in moves if isinstance(m, PlayOneOff) and m.card == three
        ]
        assert len(three_moves) == 1
        assert three_moves[0].target_card == ace

    def test_four_force_discard(self):
        four = Card(Rank.FOUR, Suit.CLUBS)
        ace = Card(Rank.ACE, Suit.SPADES)

        player0 = PlayerState(hand=(four,), points_field=(), permanents=())
        player1 = PlayerState(hand=(ace,), points_field=(), permanents=())
        state = GameState(
            players=(player0, player1),
            deck=(Card(Rank.FIVE, Suit.HEARTS),),
            scrap=(),
            current_player=0,
        )
        moves = generate_legal_moves(state)
        four_moves = [m for m in moves if isinstance(m, PlayOneOff) and m.card == four]
        assert len(four_moves) == 1

    def test_five_draw_two(self):
        five = Card(Rank.FIVE, Suit.CLUBS)

        player0 = PlayerState(hand=(five,), points_field=(), permanents=())
        player1 = PlayerState(hand=(), points_field=(), permanents=())
        state = GameState(
            players=(player0, player1),
            deck=(Card(Rank.ACE, Suit.HEARTS), Card(Rank.TWO, Suit.SPADES)),
            scrap=(),
            current_player=0,
        )
        moves = generate_legal_moves(state)
        five_moves = [m for m in moves if isinstance(m, PlayOneOff) and m.card == five]
        assert len(five_moves) == 1


class TestPermanentMoves:
    def test_eight_glasses(self):
        eight = Card(Rank.EIGHT, Suit.CLUBS)

        player0 = PlayerState(hand=(eight,), points_field=(), permanents=())
        player1 = PlayerState(hand=(), points_field=(), permanents=())
        state = GameState(
            players=(player0, player1),
            deck=(Card(Rank.ACE, Suit.HEARTS),),
            scrap=(),
            current_player=0,
        )
        moves = generate_legal_moves(state)
        perm_moves = [
            m for m in moves if isinstance(m, PlayPermanent) and m.card == eight
        ]
        assert len(perm_moves) == 1

    def test_jack_steal_point_card(self):
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
        moves = generate_legal_moves(state)
        jack_moves = [
            m for m in moves if isinstance(m, PlayPermanent) and m.card == jack
        ]
        assert len(jack_moves) == 1
        assert jack_moves[0].target_card == five

    def test_queen_protection(self):
        queen = Card(Rank.QUEEN, Suit.CLUBS)

        player0 = PlayerState(hand=(queen,), points_field=(), permanents=())
        player1 = PlayerState(hand=(), points_field=(), permanents=())
        state = GameState(
            players=(player0, player1),
            deck=(Card(Rank.ACE, Suit.HEARTS),),
            scrap=(),
            current_player=0,
        )
        moves = generate_legal_moves(state)
        queen_moves = [
            m for m in moves if isinstance(m, PlayPermanent) and m.card == queen
        ]
        assert len(queen_moves) == 1

    def test_king_threshold(self):
        king = Card(Rank.KING, Suit.CLUBS)

        player0 = PlayerState(hand=(king,), points_field=(), permanents=())
        player1 = PlayerState(hand=(), points_field=(), permanents=())
        state = GameState(
            players=(player0, player1),
            deck=(Card(Rank.ACE, Suit.HEARTS),),
            scrap=(),
            current_player=0,
        )
        moves = generate_legal_moves(state)
        king_moves = [
            m for m in moves if isinstance(m, PlayPermanent) and m.card == king
        ]
        assert len(king_moves) == 1


class TestCounterPhaseMoves:
    def test_can_counter_with_two(self):
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
        moves = generate_legal_moves(state)
        counter_moves = [m for m in moves if isinstance(m, Counter)]
        assert len(counter_moves) == 1
        assert counter_moves[0].card == two

    def test_can_decline_counter(self):
        ace = Card(Rank.ACE, Suit.CLUBS)
        counter_state = CounterState(one_off_card=ace, one_off_player=0)

        player0 = PlayerState(hand=(), points_field=(), permanents=())
        player1 = PlayerState(hand=(), points_field=(), permanents=())
        state = GameState(
            players=(player0, player1),
            deck=(Card(Rank.THREE, Suit.HEARTS),),
            scrap=(),
            current_player=0,
            phase=GamePhase.COUNTER,
            counter_state=counter_state,
        )
        moves = generate_legal_moves(state)
        decline_moves = [m for m in moves if isinstance(m, DeclineCounter)]
        assert len(decline_moves) == 1


class TestDiscardPhaseMoves:
    def test_can_discard_any_card(self):
        ace = Card(Rank.ACE, Suit.CLUBS)
        two = Card(Rank.TWO, Suit.SPADES)

        four_state = FourState(player=1, cards_to_discard=2)

        player0 = PlayerState(hand=(), points_field=(), permanents=())
        player1 = PlayerState(hand=(ace, two), points_field=(), permanents=())
        state = GameState(
            players=(player0, player1),
            deck=(),
            scrap=(),
            current_player=0,
            phase=GamePhase.DISCARD_FOUR,
            four_state=four_state,
        )
        moves = generate_legal_moves(state)
        discard_moves = [m for m in moves if isinstance(m, Discard)]
        assert len(discard_moves) == 2


class TestGameOverMoves:
    def test_no_moves_when_game_over(self):
        player0 = PlayerState(hand=(), points_field=(), permanents=())
        player1 = PlayerState(hand=(), points_field=(), permanents=())
        state = GameState(
            players=(player0, player1),
            deck=(),
            scrap=(),
            current_player=0,
            phase=GamePhase.GAME_OVER,
            winner=0,
        )
        moves = generate_legal_moves(state)
        assert len(moves) == 0
