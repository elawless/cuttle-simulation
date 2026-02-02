"""Tests for move types."""

import pytest

from cuttle_engine.cards import Card, Rank, Suit
from cuttle_engine.moves import (
    Counter,
    DeclineCounter,
    Discard,
    Draw,
    MoveType,
    OneOffEffect,
    Pass,
    PlayOneOff,
    PlayPermanent,
    PlayPoints,
    ResolveSeven,
    Scuttle,
)


class TestDraw:
    def test_draw_move_type(self):
        move = Draw()
        assert move.move_type == MoveType.DRAW
        assert str(move) == "Draw"


class TestPlayPoints:
    def test_play_points(self):
        ace = Card(Rank.ACE, Suit.CLUBS)
        move = PlayPoints(card=ace)
        assert move.move_type == MoveType.PLAY_POINTS
        assert move.card == ace
        assert "A♣" in str(move)


class TestScuttle:
    def test_scuttle(self):
        two = Card(Rank.TWO, Suit.SPADES)
        ace = Card(Rank.ACE, Suit.CLUBS)
        move = Scuttle(card=two, target=ace)
        assert move.move_type == MoveType.SCUTTLE
        assert move.card == two
        assert move.target == ace
        assert "A♣" in str(move)
        assert "2♠" in str(move)


class TestPlayOneOff:
    def test_ace_one_off(self):
        ace = Card(Rank.ACE, Suit.CLUBS)
        move = PlayOneOff(card=ace, effect=OneOffEffect.ACE_SCRAP_ALL_POINTS)
        assert move.move_type == MoveType.PLAY_ONE_OFF
        assert "scrap all points" in str(move)

    def test_two_destroy_permanent(self):
        two = Card(Rank.TWO, Suit.CLUBS)
        queen = Card(Rank.QUEEN, Suit.SPADES)
        move = PlayOneOff(
            card=two,
            effect=OneOffEffect.TWO_DESTROY_PERMANENT,
            target_card=queen,
            target_player=1,
        )
        assert "Q♠" in str(move)

    def test_three_revive(self):
        three = Card(Rank.THREE, Suit.CLUBS)
        ace = Card(Rank.ACE, Suit.SPADES)
        move = PlayOneOff(
            card=three, effect=OneOffEffect.THREE_REVIVE, target_card=ace
        )
        assert "revive" in str(move)


class TestPlayPermanent:
    def test_eight_glasses(self):
        eight = Card(Rank.EIGHT, Suit.CLUBS)
        move = PlayPermanent(card=eight)
        assert move.move_type == MoveType.PLAY_PERMANENT
        assert "Glasses" in str(move)

    def test_jack_steal(self):
        jack = Card(Rank.JACK, Suit.CLUBS)
        ten = Card(Rank.TEN, Suit.SPADES)
        move = PlayPermanent(card=jack, target_card=ten)
        assert "steal" in str(move)
        assert "10♠" in str(move)

    def test_queen_protection(self):
        queen = Card(Rank.QUEEN, Suit.CLUBS)
        move = PlayPermanent(card=queen)
        assert "protection" in str(move)

    def test_king_threshold(self):
        king = Card(Rank.KING, Suit.CLUBS)
        move = PlayPermanent(card=king)
        assert "threshold" in str(move)


class TestCounter:
    def test_counter(self):
        two = Card(Rank.TWO, Suit.SPADES)
        move = Counter(card=two)
        assert move.move_type == MoveType.COUNTER
        assert "Counter" in str(move)
        assert "2♠" in str(move)


class TestDeclineCounter:
    def test_decline_counter(self):
        move = DeclineCounter()
        assert move.move_type == MoveType.DECLINE_COUNTER
        assert "Decline" in str(move)


class TestResolveSeven:
    def test_resolve_seven_points(self):
        ace = Card(Rank.ACE, Suit.CLUBS)
        move = ResolveSeven(card=ace, play_as=MoveType.PLAY_POINTS)
        assert move.move_type == MoveType.RESOLVE_SEVEN
        assert "Seven" in str(move)

    def test_resolve_seven_scuttle(self):
        two = Card(Rank.TWO, Suit.CLUBS)
        ace = Card(Rank.ACE, Suit.SPADES)
        move = ResolveSeven(card=two, play_as=MoveType.SCUTTLE, target_card=ace)
        assert move.target_card == ace


class TestDiscard:
    def test_discard(self):
        ace = Card(Rank.ACE, Suit.CLUBS)
        move = Discard(card=ace)
        assert move.move_type == MoveType.DISCARD
        assert "Discard" in str(move)


class TestPass:
    def test_pass(self):
        move = Pass()
        assert move.move_type == MoveType.PASS
        assert str(move) == "Pass"
