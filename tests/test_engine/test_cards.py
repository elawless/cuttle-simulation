"""Tests for card models."""

import pytest

from cuttle_engine.cards import Card, CardType, Rank, Suit, create_deck, shuffle_deck


class TestSuit:
    def test_suit_ordering(self):
        """Suits should be ordered Clubs < Diamonds < Hearts < Spades."""
        assert Suit.CLUBS < Suit.DIAMONDS < Suit.HEARTS < Suit.SPADES

    def test_suit_symbols(self):
        assert Suit.CLUBS.symbol == "♣"
        assert Suit.DIAMONDS.symbol == "♦"
        assert Suit.HEARTS.symbol == "♥"
        assert Suit.SPADES.symbol == "♠"


class TestRank:
    def test_rank_values(self):
        assert Rank.ACE.value == 1
        assert Rank.TEN.value == 10
        assert Rank.JACK.value == 11
        assert Rank.QUEEN.value == 12
        assert Rank.KING.value == 13

    def test_rank_symbols(self):
        assert Rank.ACE.symbol == "A"
        assert Rank.TEN.symbol == "10"
        assert Rank.JACK.symbol == "J"
        assert Rank.QUEEN.symbol == "Q"
        assert Rank.KING.symbol == "K"


class TestCard:
    def test_card_creation(self):
        card = Card(Rank.ACE, Suit.SPADES)
        assert card.rank == Rank.ACE
        assert card.suit == Suit.SPADES

    def test_card_singleton(self):
        """Same rank/suit should return same instance."""
        card1 = Card(Rank.ACE, Suit.SPADES)
        card2 = Card(Rank.ACE, Suit.SPADES)
        assert card1 is card2

    def test_card_string(self):
        card = Card(Rank.ACE, Suit.SPADES)
        assert str(card) == "A♠"

    def test_card_repr(self):
        card = Card(Rank.ACE, Suit.SPADES)
        assert repr(card) == "Card(ACE, SPADES)"

    def test_point_values(self):
        assert Card(Rank.ACE, Suit.CLUBS).point_value == 1
        assert Card(Rank.TEN, Suit.CLUBS).point_value == 10
        assert Card(Rank.JACK, Suit.CLUBS).point_value == 0
        assert Card(Rank.KING, Suit.CLUBS).point_value == 0

    def test_can_play_for_points(self):
        assert Card(Rank.ACE, Suit.CLUBS).can_play_for_points
        assert Card(Rank.TEN, Suit.CLUBS).can_play_for_points
        assert not Card(Rank.JACK, Suit.CLUBS).can_play_for_points

    def test_can_play_as_one_off(self):
        assert Card(Rank.ACE, Suit.CLUBS).can_play_as_one_off
        assert Card(Rank.NINE, Suit.CLUBS).can_play_as_one_off
        assert not Card(Rank.TEN, Suit.CLUBS).can_play_as_one_off
        assert not Card(Rank.JACK, Suit.CLUBS).can_play_as_one_off

    def test_can_play_as_permanent(self):
        assert Card(Rank.EIGHT, Suit.CLUBS).can_play_as_permanent
        assert Card(Rank.JACK, Suit.CLUBS).can_play_as_permanent
        assert Card(Rank.QUEEN, Suit.CLUBS).can_play_as_permanent
        assert Card(Rank.KING, Suit.CLUBS).can_play_as_permanent
        assert not Card(Rank.NINE, Suit.CLUBS).can_play_as_permanent
        assert not Card(Rank.TEN, Suit.CLUBS).can_play_as_permanent

    def test_card_types(self):
        # Ace can be points or one-off
        ace = Card(Rank.ACE, Suit.CLUBS)
        assert CardType.POINTS in ace.card_types
        assert CardType.ONE_OFF in ace.card_types
        assert CardType.PERMANENT not in ace.card_types

        # Eight can be points, one-off, or permanent
        eight = Card(Rank.EIGHT, Suit.CLUBS)
        assert CardType.POINTS in eight.card_types
        assert CardType.ONE_OFF in eight.card_types
        assert CardType.PERMANENT in eight.card_types

        # Jack is permanent only
        jack = Card(Rank.JACK, Suit.CLUBS)
        assert CardType.POINTS not in jack.card_types
        assert CardType.ONE_OFF not in jack.card_types
        assert CardType.PERMANENT in jack.card_types

    def test_card_ordering(self):
        """Cards should be ordered by rank, then suit."""
        ace_clubs = Card(Rank.ACE, Suit.CLUBS)
        ace_spades = Card(Rank.ACE, Suit.SPADES)
        two_clubs = Card(Rank.TWO, Suit.CLUBS)

        assert ace_clubs < ace_spades  # Same rank, Spades > Clubs
        assert ace_clubs < two_clubs  # Lower rank
        assert ace_spades < two_clubs  # Rank takes precedence

    def test_card_equality(self):
        card1 = Card(Rank.ACE, Suit.SPADES)
        card2 = Card(Rank.ACE, Suit.SPADES)
        card3 = Card(Rank.ACE, Suit.CLUBS)

        assert card1 == card2
        assert card1 != card3

    def test_card_hash(self):
        """Cards should be hashable for use in sets/dicts."""
        card1 = Card(Rank.ACE, Suit.SPADES)
        card2 = Card(Rank.ACE, Suit.SPADES)
        card3 = Card(Rank.ACE, Suit.CLUBS)

        card_set = {card1, card2, card3}
        assert len(card_set) == 2  # card1 and card2 are same


class TestScuttling:
    def test_higher_rank_can_scuttle(self):
        two = Card(Rank.TWO, Suit.CLUBS)
        ace = Card(Rank.ACE, Suit.CLUBS)
        assert two.can_scuttle(ace)
        assert not ace.can_scuttle(two)

    def test_same_rank_higher_suit_can_scuttle(self):
        ace_spades = Card(Rank.ACE, Suit.SPADES)
        ace_clubs = Card(Rank.ACE, Suit.CLUBS)
        assert ace_spades.can_scuttle(ace_clubs)
        assert not ace_clubs.can_scuttle(ace_spades)

    def test_same_rank_same_suit_cannot_scuttle(self):
        ace = Card(Rank.ACE, Suit.SPADES)
        assert not ace.can_scuttle(ace)

    def test_face_cards_cannot_scuttle(self):
        jack = Card(Rank.JACK, Suit.SPADES)
        ace = Card(Rank.ACE, Suit.CLUBS)
        assert not jack.can_scuttle(ace)

    def test_cannot_scuttle_face_cards(self):
        ten = Card(Rank.TEN, Suit.SPADES)
        jack = Card(Rank.JACK, Suit.CLUBS)
        assert not ten.can_scuttle(jack)


class TestDeck:
    def test_create_deck(self):
        deck = create_deck()
        assert len(deck) == 52

    def test_deck_contains_all_cards(self):
        deck = create_deck()
        for suit in Suit:
            for rank in Rank:
                assert Card(rank, suit) in deck

    def test_shuffle_deck_deterministic(self):
        deck = create_deck()
        shuffled1 = shuffle_deck(deck, seed=42)
        shuffled2 = shuffle_deck(deck, seed=42)
        assert shuffled1 == shuffled2

    def test_shuffle_deck_different_seeds(self):
        deck = create_deck()
        shuffled1 = shuffle_deck(deck, seed=42)
        shuffled2 = shuffle_deck(deck, seed=43)
        assert shuffled1 != shuffled2

    def test_shuffle_preserves_cards(self):
        deck = create_deck()
        shuffled = shuffle_deck(deck, seed=42)
        assert set(deck) == set(shuffled)
