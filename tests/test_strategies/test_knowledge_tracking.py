"""Tests for opponent hand knowledge tracking system.

These tests verify the knowledge tracking module and its integration with
strategies when Glasses (8 as permanent) is in play.
"""

import pytest

from cuttle_engine.cards import Card, Rank, Suit
from cuttle_engine.state import GameState, PlayerState
from cuttle_engine.move_generator import generate_legal_moves
from strategies.knowledge import (
    MemoryLevel,
    OpponentKnowledge,
    KnowledgeTracker,
    analyze_known_hand,
    get_unknown_card_count,
)
from strategies.heuristic import HeuristicStrategy
from strategies.minimax import MinimaxStrategy


class TestOpponentKnowledge:
    """Tests for the OpponentKnowledge class."""

    def test_observe_hand_adds_cards(self):
        """Observing a hand should add cards to known set."""
        knowledge = OpponentKnowledge()
        hand = (
            Card(Rank.TWO, Suit.SPADES),
            Card(Rank.TEN, Suit.HEARTS),
        )

        knowledge.observe_hand(hand, current_turn=1)

        assert len(knowledge.known_cards) == 2
        assert knowledge.knows_card(Card(Rank.TWO, Suit.SPADES))
        assert knowledge.knows_card(Card(Rank.TEN, Suit.HEARTS))

    def test_observe_hand_removes_played_cards(self):
        """Re-observing should remove cards no longer in hand."""
        knowledge = OpponentKnowledge()

        # First observation
        hand1 = (
            Card(Rank.TWO, Suit.SPADES),
            Card(Rank.TEN, Suit.HEARTS),
        )
        knowledge.observe_hand(hand1, current_turn=1)

        # Second observation - Two was played
        hand2 = (Card(Rank.TEN, Suit.HEARTS),)
        knowledge.observe_hand(hand2, current_turn=2)

        assert len(knowledge.known_cards) == 1
        assert not knowledge.knows_card(Card(Rank.TWO, Suit.SPADES))
        assert knowledge.knows_card(Card(Rank.TEN, Suit.HEARTS))

    def test_card_left_hand_removes_card(self):
        """Explicitly marking a card as left should remove it."""
        knowledge = OpponentKnowledge()
        card = Card(Rank.TWO, Suit.SPADES)
        knowledge.observe_hand((card,), current_turn=1)

        knowledge.card_left_hand(card)

        assert not knowledge.knows_card(card)
        assert len(knowledge.known_cards) == 0

    def test_perfect_memory_never_forgets(self):
        """PERFECT memory level should never forget cards."""
        knowledge = OpponentKnowledge(memory_level=MemoryLevel.PERFECT)
        card = Card(Rank.TWO, Suit.SPADES)
        knowledge.observe_hand((card,), current_turn=1)

        # Many turns pass
        for turn in range(2, 100):
            knowledge.on_turn_end(turn)

        assert knowledge.knows_card(card)

    def test_turn_limited_memory_forgets_after_turns(self):
        """TURN_LIMITED should forget cards after N turns."""
        knowledge = OpponentKnowledge(
            memory_level=MemoryLevel.TURN_LIMITED,
            memory_turns=3,
        )
        card = Card(Rank.TWO, Suit.SPADES)
        knowledge.observe_hand((card,), current_turn=1)

        # Turns 2, 3, 4 - should still remember (within 3 turns)
        knowledge.on_turn_end(2)
        assert knowledge.knows_card(card)
        knowledge.on_turn_end(3)
        assert knowledge.knows_card(card)
        knowledge.on_turn_end(4)
        assert knowledge.knows_card(card)

        # Turn 5 - should forget (more than 3 turns since last confirmed)
        knowledge.on_turn_end(5)
        assert not knowledge.knows_card(card)

    def test_turn_limited_refresh_on_reobserve(self):
        """Re-observing a card should refresh the timer."""
        knowledge = OpponentKnowledge(
            memory_level=MemoryLevel.TURN_LIMITED,
            memory_turns=2,
        )
        card = Card(Rank.TWO, Suit.SPADES)
        knowledge.observe_hand((card,), current_turn=1)

        # Turn 2 - re-observe
        knowledge.observe_hand((card,), current_turn=2)

        # Turn 3, 4 - should still remember (refreshed at turn 2)
        knowledge.on_turn_end(3)
        assert knowledge.knows_card(card)
        knowledge.on_turn_end(4)
        assert knowledge.knows_card(card)

        # Turn 5 - now forgets
        knowledge.on_turn_end(5)
        assert not knowledge.knows_card(card)

    def test_none_memory_clears_without_glasses(self):
        """NONE memory level should clear when glasses are lost."""
        knowledge = OpponentKnowledge(memory_level=MemoryLevel.NONE)
        card = Card(Rank.TWO, Suit.SPADES)
        knowledge.observe_hand((card,), current_turn=1)

        # Still have glasses - knowledge retained
        knowledge.clear_if_no_glasses(has_glasses=True)
        assert knowledge.knows_card(card)

        # Lost glasses - knowledge cleared
        knowledge.clear_if_no_glasses(has_glasses=False)
        assert not knowledge.knows_card(card)

    def test_copy_creates_independent_copy(self):
        """Copy should create an independent knowledge state."""
        knowledge = OpponentKnowledge()
        card = Card(Rank.TWO, Suit.SPADES)
        knowledge.observe_hand((card,), current_turn=1)

        copy = knowledge.copy()

        # Modify original
        knowledge.card_left_hand(card)

        # Copy should be unaffected
        assert copy.knows_card(card)
        assert not knowledge.knows_card(card)


class TestKnowledgeTracker:
    """Tests for the KnowledgeTracker class."""

    def test_update_from_state_with_glasses(self):
        """Should observe opponent's hand when we have glasses."""
        glasses = Card(Rank.EIGHT, Suit.DIAMONDS)
        opp_card = Card(Rank.TEN, Suit.HEARTS)

        player0 = PlayerState(
            hand=(),
            points_field=(),
            permanents=(glasses,),
        )
        player1 = PlayerState(
            hand=(opp_card,),
            points_field=(),
            permanents=(),
        )
        state = GameState(
            players=(player0, player1),
            deck=(),
            scrap=(),
            current_player=0,
        )

        tracker = KnowledgeTracker.create(player_idx=0)
        tracker.update_from_state(state)

        assert tracker.opponent_has_card(opp_card)

    def test_update_from_state_without_glasses(self):
        """Should not observe hand without glasses."""
        opp_card = Card(Rank.TEN, Suit.HEARTS)

        player0 = PlayerState(
            hand=(),
            points_field=(),
            permanents=(),  # No glasses
        )
        player1 = PlayerState(
            hand=(opp_card,),
            points_field=(),
            permanents=(),
        )
        state = GameState(
            players=(player0, player1),
            deck=(),
            scrap=(),
            current_player=0,
        )

        tracker = KnowledgeTracker.create(player_idx=0)
        tracker.update_from_state(state)

        assert not tracker.opponent_has_card(opp_card)

    def test_knowledge_persists_after_glasses_destroyed_perfect(self):
        """With PERFECT memory, knowledge persists after glasses destroyed."""
        glasses = Card(Rank.EIGHT, Suit.DIAMONDS)
        opp_card = Card(Rank.TEN, Suit.HEARTS)

        # State with glasses
        player0_with = PlayerState(
            hand=(),
            points_field=(),
            permanents=(glasses,),
        )
        player1 = PlayerState(
            hand=(opp_card,),
            points_field=(),
            permanents=(),
        )
        state_with = GameState(
            players=(player0_with, player1),
            deck=(),
            scrap=(),
            current_player=0,
            turn_number=1,
        )

        tracker = KnowledgeTracker.create(
            player_idx=0,
            memory_level=MemoryLevel.PERFECT,
        )
        tracker.update_from_state(state_with)

        # Now glasses destroyed
        player0_without = PlayerState(
            hand=(),
            points_field=(),
            permanents=(),  # Glasses gone
        )
        state_without = GameState(
            players=(player0_without, player1),
            deck=(),
            scrap=(glasses,),
            current_player=0,
            turn_number=2,
        )

        tracker.update_from_state(state_without)

        # Should still know about opponent's card
        assert tracker.opponent_has_card(opp_card)

    def test_knowledge_clears_after_glasses_destroyed_none(self):
        """With NONE memory, knowledge clears when glasses destroyed."""
        glasses = Card(Rank.EIGHT, Suit.DIAMONDS)
        opp_card = Card(Rank.TEN, Suit.HEARTS)

        # State with glasses
        player0_with = PlayerState(
            hand=(),
            points_field=(),
            permanents=(glasses,),
        )
        player1 = PlayerState(
            hand=(opp_card,),
            points_field=(),
            permanents=(),
        )
        state_with = GameState(
            players=(player0_with, player1),
            deck=(),
            scrap=(),
            current_player=0,
        )

        tracker = KnowledgeTracker.create(
            player_idx=0,
            memory_level=MemoryLevel.NONE,
        )
        tracker.update_from_state(state_with)
        assert tracker.opponent_has_card(opp_card)

        # Now glasses destroyed
        player0_without = PlayerState(
            hand=(),
            points_field=(),
            permanents=(),
        )
        state_without = GameState(
            players=(player0_without, player1),
            deck=(),
            scrap=(glasses,),
            current_player=0,
        )

        tracker.update_from_state(state_without)

        # Should NOT know about opponent's card anymore
        assert not tracker.opponent_has_card(opp_card)


class TestAnalyzeKnownHand:
    """Tests for the analyze_known_hand function."""

    def test_empty_known_cards(self):
        """Should handle empty known cards."""
        analysis = analyze_known_hand(frozenset())

        assert analysis["has_counter"] is False
        assert analysis["counter_count"] == 0
        assert analysis["has_jack"] is False
        assert analysis["max_point_play"] == 0
        assert analysis["known_count"] == 0

    def test_detects_counter(self):
        """Should detect Two (counter) cards."""
        known = frozenset([
            Card(Rank.TWO, Suit.SPADES),
            Card(Rank.TWO, Suit.HEARTS),
            Card(Rank.TEN, Suit.CLUBS),
        ])

        analysis = analyze_known_hand(known)

        assert analysis["has_counter"] is True
        assert analysis["counter_count"] == 2

    def test_detects_jack(self):
        """Should detect Jack cards."""
        known = frozenset([
            Card(Rank.JACK, Suit.SPADES),
            Card(Rank.FIVE, Suit.HEARTS),
        ])

        analysis = analyze_known_hand(known)

        assert analysis["has_jack"] is True
        assert analysis["jack_count"] == 1

    def test_calculates_max_points(self):
        """Should calculate max point play correctly."""
        known = frozenset([
            Card(Rank.THREE, Suit.SPADES),
            Card(Rank.SEVEN, Suit.HEARTS),
            Card(Rank.KING, Suit.CLUBS),  # Not a point card
        ])

        analysis = analyze_known_hand(known)

        assert analysis["max_point_play"] == 7

    def test_detects_all_threats(self):
        """Should detect all threat types."""
        known = frozenset([
            Card(Rank.ACE, Suit.SPADES),
            Card(Rank.KING, Suit.HEARTS),
            Card(Rank.QUEEN, Suit.CLUBS),
        ])

        analysis = analyze_known_hand(known)

        assert analysis["has_ace"] is True
        assert analysis["has_king"] is True
        assert analysis["has_queen"] is True


class TestGetUnknownCardCount:
    """Tests for the get_unknown_card_count function."""

    def test_full_knowledge(self):
        """Should return 0 when all cards known."""
        opp_cards = (
            Card(Rank.TEN, Suit.HEARTS),
            Card(Rank.FIVE, Suit.SPADES),
        )
        player0 = PlayerState(hand=(), points_field=(), permanents=())
        player1 = PlayerState(hand=opp_cards, points_field=(), permanents=())
        state = GameState(
            players=(player0, player1),
            deck=(),
            scrap=(),
            current_player=0,
        )

        known = frozenset(opp_cards)
        unknown = get_unknown_card_count(state, 0, known)

        assert unknown == 0

    def test_partial_knowledge(self):
        """Should return correct count for partial knowledge."""
        opp_cards = (
            Card(Rank.TEN, Suit.HEARTS),
            Card(Rank.FIVE, Suit.SPADES),
            Card(Rank.TWO, Suit.CLUBS),
        )
        player0 = PlayerState(hand=(), points_field=(), permanents=())
        player1 = PlayerState(hand=opp_cards, points_field=(), permanents=())
        state = GameState(
            players=(player0, player1),
            deck=(),
            scrap=(),
            current_player=0,
        )

        # Only know about one card
        known = frozenset([Card(Rank.TEN, Suit.HEARTS)])
        unknown = get_unknown_card_count(state, 0, known)

        assert unknown == 2

    def test_no_knowledge(self):
        """Should return full hand size when no knowledge."""
        opp_cards = (
            Card(Rank.TEN, Suit.HEARTS),
            Card(Rank.FIVE, Suit.SPADES),
        )
        player0 = PlayerState(hand=(), points_field=(), permanents=())
        player1 = PlayerState(hand=opp_cards, points_field=(), permanents=())
        state = GameState(
            players=(player0, player1),
            deck=(),
            scrap=(),
            current_player=0,
        )

        unknown = get_unknown_card_count(state, 0, frozenset())

        assert unknown == 2


class TestHeuristicWithKnowledge:
    """Integration tests for HeuristicStrategy with knowledge tracking."""

    def test_initializes_knowledge_tracker(self):
        """Should initialize knowledge tracker on game start."""
        strategy = HeuristicStrategy(
            seed=42,
            memory_level=MemoryLevel.PERFECT,
        )

        player0 = PlayerState(hand=(), points_field=(), permanents=())
        player1 = PlayerState(hand=(), points_field=(), permanents=())
        state = GameState(
            players=(player0, player1),
            deck=(),
            scrap=(),
            current_player=0,
        )

        strategy.on_game_start(state, player_idx=0)

        assert strategy._knowledge is not None
        assert strategy._player_idx == 0

    def test_uses_knowledge_in_scoring(self):
        """Strategy should use knowledge to adjust scores."""
        glasses = Card(Rank.EIGHT, Suit.DIAMONDS)
        ace = Card(Rank.ACE, Suit.HEARTS)

        # Player 0 has glasses and ace, opponent has no Two
        player0 = PlayerState(
            hand=(ace,),
            points_field=(),
            permanents=(glasses,),
        )
        player1 = PlayerState(
            hand=(Card(Rank.FIVE, Suit.SPADES),),  # No counter!
            points_field=(Card(Rank.TEN, Suit.CLUBS),),  # 10 points
            permanents=(),
        )
        state = GameState(
            players=(player0, player1),
            deck=(Card(Rank.THREE, Suit.CLUBS),),
            scrap=(),
            current_player=0,
        )

        strategy = HeuristicStrategy(
            seed=42,
            memory_level=MemoryLevel.PERFECT,
        )
        strategy.on_game_start(state, player_idx=0)

        legal_moves = generate_legal_moves(state)
        move = strategy.select_move(state, legal_moves)

        # Strategy should make a valid move
        assert move in legal_moves

    def test_different_memory_levels(self):
        """Different memory levels should work."""
        for level in MemoryLevel:
            strategy = HeuristicStrategy(
                seed=42,
                memory_level=level,
            )

            player0 = PlayerState(
                hand=(Card(Rank.TEN, Suit.HEARTS),),
                points_field=(),
                permanents=(),
            )
            player1 = PlayerState(
                hand=(Card(Rank.FIVE, Suit.SPADES),),
                points_field=(),
                permanents=(),
            )
            state = GameState(
                players=(player0, player1),
                deck=(Card(Rank.THREE, Suit.CLUBS),),
                scrap=(),
                current_player=0,
            )

            strategy.on_game_start(state, player_idx=0)
            legal_moves = generate_legal_moves(state)
            move = strategy.select_move(state, legal_moves)

            assert move in legal_moves


class TestMinimaxWithKnowledge:
    """Integration tests for MinimaxStrategy with knowledge tracking."""

    def test_initializes_knowledge_tracker(self):
        """Should initialize knowledge tracker on game start."""
        strategy = MinimaxStrategy(
            depth=2,
            seed=42,
            memory_level=MemoryLevel.PERFECT,
        )

        player0 = PlayerState(hand=(), points_field=(), permanents=())
        player1 = PlayerState(hand=(), points_field=(), permanents=())
        state = GameState(
            players=(player0, player1),
            deck=(),
            scrap=(),
            current_player=0,
        )

        strategy.on_game_start(state, player_idx=0)

        assert strategy._knowledge is not None
        assert strategy._player_idx == 0

    def test_knowledge_bonus_in_evaluation(self):
        """Knowledge should affect state evaluation."""
        glasses = Card(Rank.EIGHT, Suit.DIAMONDS)

        player0 = PlayerState(
            hand=(),
            points_field=(Card(Rank.TEN, Suit.HEARTS),),
            permanents=(glasses,),
        )
        player1 = PlayerState(
            hand=(Card(Rank.FIVE, Suit.SPADES),),  # Known: no counter, no jack
            points_field=(),
            permanents=(),
        )
        state = GameState(
            players=(player0, player1),
            deck=(Card(Rank.THREE, Suit.CLUBS),),
            scrap=(),
            current_player=0,
        )

        strategy = MinimaxStrategy(depth=2, seed=42)
        strategy.on_game_start(state, player_idx=0)
        strategy._knowledge.update_from_state(state)

        known_cards = strategy._knowledge.get_known_opponent_cards()

        eval_with_knowledge = strategy._evaluate(state, player=0, known_cards=known_cards)
        eval_without_knowledge = strategy._evaluate(state, player=0, known_cards=None)

        # Evaluation with knowledge should be higher (information advantage)
        assert eval_with_knowledge > eval_without_knowledge

    def test_different_memory_levels(self):
        """Different memory levels should work."""
        for level in MemoryLevel:
            strategy = MinimaxStrategy(
                depth=2,
                seed=42,
                memory_level=level,
            )

            player0 = PlayerState(
                hand=(Card(Rank.TEN, Suit.HEARTS),),
                points_field=(),
                permanents=(),
            )
            player1 = PlayerState(
                hand=(Card(Rank.FIVE, Suit.SPADES),),
                points_field=(),
                permanents=(),
            )
            state = GameState(
                players=(player0, player1),
                deck=(Card(Rank.THREE, Suit.CLUBS),),
                scrap=(),
                current_player=0,
            )

            strategy.on_game_start(state, player_idx=0)
            legal_moves = generate_legal_moves(state)
            move = strategy.select_move(state, legal_moves)

            assert move in legal_moves


class TestMemoryLevelNames:
    """Tests for strategy naming with memory levels."""

    def test_heuristic_name_with_memory(self):
        """HeuristicStrategy name should include memory level."""
        strategy_perfect = HeuristicStrategy(memory_level=MemoryLevel.PERFECT)
        strategy_none = HeuristicStrategy(memory_level=MemoryLevel.NONE)

        assert "mem:perfect" in strategy_perfect.name.lower()
        # NONE doesn't add suffix (default no-memory behavior)
        assert "mem:" not in strategy_none.name.lower()

    def test_minimax_name_with_memory(self):
        """MinimaxStrategy name should include memory level."""
        strategy_perfect = MinimaxStrategy(depth=2, memory_level=MemoryLevel.PERFECT)
        strategy_none = MinimaxStrategy(depth=2, memory_level=MemoryLevel.NONE)

        assert "mem:perfect" in strategy_perfect.name.lower()
        assert "mem:" not in strategy_none.name.lower()
