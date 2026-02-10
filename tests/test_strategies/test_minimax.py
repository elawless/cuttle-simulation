"""Tests for MinimaxStrategy."""

import pytest

from cuttle_engine.cards import Card, Rank, Suit
from cuttle_engine.state import GameState, PlayerState, create_initial_state
from cuttle_engine.move_generator import generate_legal_moves
from strategies.minimax import MinimaxStrategy


class TestMinimaxBasics:
    def test_selects_move_from_legal_moves(self):
        state = create_initial_state(seed=42)
        legal_moves = generate_legal_moves(state)
        strategy = MinimaxStrategy(depth=2, seed=123)

        move = strategy.select_move(state, legal_moves)

        assert move in legal_moves

    def test_returns_none_for_empty_moves(self):
        state = create_initial_state(seed=42)
        strategy = MinimaxStrategy(depth=2)

        move = strategy.select_move(state, [])

        assert move is None

    def test_deterministic_with_seed(self):
        state = create_initial_state(seed=42)
        legal_moves = generate_legal_moves(state)

        strategy1 = MinimaxStrategy(depth=2, seed=123)
        strategy2 = MinimaxStrategy(depth=2, seed=123)

        move1 = strategy1.select_move(state, legal_moves)
        move2 = strategy2.select_move(state, legal_moves)

        assert move1 == move2

    def test_different_seeds_may_differ(self):
        state = create_initial_state(seed=42)
        legal_moves = generate_legal_moves(state)

        strategy1 = MinimaxStrategy(depth=2, seed=1)
        strategy2 = MinimaxStrategy(depth=2, seed=999)

        # Run multiple times - with different seeds, at least some should differ
        # (unless all moves have same score)
        move1 = strategy1.select_move(state, legal_moves)
        move2 = strategy2.select_move(state, legal_moves)
        # Just verify both are valid moves
        assert move1 in legal_moves
        assert move2 in legal_moves


class TestMinimaxEvaluation:
    def test_prefers_winning_state(self):
        # Set up a state where player 0 can win by playing a card
        ten1 = Card(Rank.TEN, Suit.CLUBS)
        ten2 = Card(Rank.TEN, Suit.SPADES)
        ace = Card(Rank.ACE, Suit.HEARTS)

        player0 = PlayerState(
            hand=(ace,), points_field=(ten1, ten2), permanents=()
        )  # Has 20 points, ace wins
        player1 = PlayerState(hand=(), points_field=(), permanents=())
        state = GameState(
            players=(player0, player1),
            deck=(Card(Rank.TWO, Suit.HEARTS),),
            scrap=(),
            current_player=0,
        )

        strategy = MinimaxStrategy(depth=2, seed=42)
        legal_moves = generate_legal_moves(state)
        move = strategy.select_move(state, legal_moves)

        # Should play the ace for points to win
        from cuttle_engine.moves import PlayPoints
        assert isinstance(move, PlayPoints)
        assert move.card == ace

    def test_avoids_losing_move(self):
        # Player 0 has 20 points, player 1 has an ace in hand
        # If player 0 passes/draws, player 1 wins next turn
        ten1 = Card(Rank.TEN, Suit.CLUBS)
        ten2 = Card(Rank.TEN, Suit.SPADES)
        ace_opp = Card(Rank.ACE, Suit.HEARTS)
        ace_mine = Card(Rank.ACE, Suit.DIAMONDS)

        player0 = PlayerState(
            hand=(ace_mine,), points_field=(ten1, ten2), permanents=()
        )
        player1 = PlayerState(hand=(ace_opp,), points_field=(), permanents=())
        state = GameState(
            players=(player0, player1),
            deck=(Card(Rank.TWO, Suit.HEARTS),),
            scrap=(),
            current_player=0,
        )

        strategy = MinimaxStrategy(depth=2, seed=42)
        legal_moves = generate_legal_moves(state)
        move = strategy.select_move(state, legal_moves)

        # Should play ace to win rather than draw
        from cuttle_engine.moves import PlayPoints
        assert isinstance(move, PlayPoints)


class TestMinimaxDepth:
    def test_depth_1_works(self):
        state = create_initial_state(seed=42)
        legal_moves = generate_legal_moves(state)
        strategy = MinimaxStrategy(depth=1, seed=42)

        move = strategy.select_move(state, legal_moves)
        assert move in legal_moves

    def test_depth_3_works(self):
        state = create_initial_state(seed=42)
        legal_moves = generate_legal_moves(state)
        strategy = MinimaxStrategy(depth=3, seed=42)

        move = strategy.select_move(state, legal_moves)
        assert move in legal_moves


class TestMinimaxPerformance:
    def test_completes_in_reasonable_time(self):
        """Minimax depth 2 should complete quickly."""
        import time
        state = create_initial_state(seed=42)
        legal_moves = generate_legal_moves(state)
        strategy = MinimaxStrategy(depth=2, seed=42)

        start = time.time()
        move = strategy.select_move(state, legal_moves)
        elapsed = time.time() - start

        assert move in legal_moves
        assert elapsed < 5.0  # Should be well under 5 seconds


class TestMinimaxIdentity:
    def test_get_identity_params(self):
        strategy = MinimaxStrategy(depth=3)
        params = strategy.get_identity_params()
        assert params == {"depth": 3}
