#!/usr/bin/env python3
"""Counterfactual test: 8 as Glasses vs 8 as Points.

This script finds decision points where a player has an 8 in hand and could
play it either as Glasses (permanent) or Points, then plays out both branches
to completion to see which choice wins more often.

This isolates the Glasses vs Points decision while keeping all other factors
constant (same game state, same continuation strategy).
"""

from __future__ import annotations

import argparse
import pickle
import random
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from cuttle_engine.cards import Rank
from cuttle_engine.executor import IllegalMoveError, execute_move
from cuttle_engine.move_generator import generate_legal_moves
from cuttle_engine.moves import PlayPermanent, PlayPoints
from cuttle_engine.state import GamePhase, GameState, create_initial_state
from strategies.base import Strategy
from strategies.heuristic import HeuristicStrategy
from strategies.ismcts import ISMCTSStrategy
from strategies.mcts import MCTSStrategy
from strategies.random_strategy import RandomStrategy

if TYPE_CHECKING:
    from cuttle_engine.moves import Move


@dataclass
class DecisionPoint:
    """A state where player can play 8 as Glasses or Points."""

    state: GameState
    seed: int
    turn: int
    player: int
    player_points: int
    opponent_points: int
    opponent_hand: tuple  # What info Glasses would reveal

    def to_pickle_data(self) -> dict:
        """Serialize for worker process."""
        return {
            "state_pickle": pickle.dumps(self.state),
            "seed": self.seed,
            "turn": self.turn,
            "player": self.player,
            "player_points": self.player_points,
            "opponent_points": self.opponent_points,
        }

    @classmethod
    def from_pickle_data(cls, data: dict) -> "DecisionPoint":
        """Deserialize from worker data."""
        state = pickle.loads(data["state_pickle"])
        opponent = 1 - data["player"]
        return cls(
            state=state,
            seed=data["seed"],
            turn=data["turn"],
            player=data["player"],
            player_points=data["player_points"],
            opponent_points=data["opponent_points"],
            opponent_hand=state.players[opponent].hand,
        )


@dataclass
class BranchResult:
    """Result of playing out one branch."""

    won: bool
    final_state: GameState
    moves_to_completion: int


@dataclass
class CounterfactualResult:
    """Result of testing both branches from a decision point."""

    decision: DecisionPoint
    points_result: BranchResult
    glasses_result: BranchResult

    @property
    def points_won(self) -> bool:
        return self.points_result.won

    @property
    def glasses_won(self) -> bool:
        return self.glasses_result.won

    @property
    def glasses_better(self) -> bool:
        """Glasses won when Points lost."""
        return self.glasses_won and not self.points_won

    @property
    def points_better(self) -> bool:
        """Points won when Glasses lost."""
        return self.points_won and not self.glasses_won

    @property
    def same_outcome(self) -> bool:
        """Both branches had same outcome."""
        return self.points_won == self.glasses_won


def get_acting_player(state: GameState) -> int:
    """Determine which player is acting in the given state."""
    if state.phase == GamePhase.COUNTER:
        return state.counter_state.waiting_for_player
    elif state.phase == GamePhase.DISCARD_FOUR:
        return state.four_state.player
    elif state.phase == GamePhase.RESOLVE_SEVEN:
        return state.seven_state.player
    return state.current_player


def play_to_completion(
    state: GameState,
    strategy: Strategy,
    perspective_player: int,
    max_moves: int = 500,
) -> BranchResult:
    """Play a game to completion from a given state.

    Args:
        state: Starting state.
        strategy: Strategy to use for both players.
        perspective_player: Which player we're tracking win/loss for.
        max_moves: Maximum moves before giving up.

    Returns:
        BranchResult with win/loss and final state.
    """
    current_state = state
    moves = 0

    while not current_state.is_game_over and moves < max_moves:
        legal_moves = generate_legal_moves(current_state)
        if not legal_moves:
            break

        move = strategy.select_move(current_state, legal_moves)
        try:
            current_state = execute_move(current_state, move)
        except IllegalMoveError:
            # Move generator bug - abort
            break
        moves += 1

    won = current_state.winner == perspective_player

    return BranchResult(
        won=won,
        final_state=current_state,
        moves_to_completion=moves,
    )


def find_eight_decision(
    state: GameState,
    moves: list[Move],
) -> tuple[PlayPoints, PlayPermanent] | None:
    """Find if current state has both 8-as-Points and 8-as-Glasses options.

    Returns:
        Tuple of (points_move, glasses_move) or None if not a decision point.
    """
    points_move = None
    glasses_move = None

    for m in moves:
        if isinstance(m, PlayPoints) and m.card.rank == Rank.EIGHT:
            points_move = m
        elif isinstance(m, PlayPermanent) and m.card.rank == Rank.EIGHT:
            glasses_move = m

    if points_move and glasses_move:
        return points_move, glasses_move
    return None


def find_decision_points(
    num_games: int,
    seed_start: int,
    exploration_strategy: Strategy,
    max_per_game: int = 5,
) -> list[DecisionPoint]:
    """Play games and collect decision points where 8 choice is available.

    Args:
        num_games: Number of games to play through.
        seed_start: Starting seed.
        exploration_strategy: Strategy to drive game exploration.
        max_per_game: Max decision points to collect per game.

    Returns:
        List of decision points found.
    """
    decision_points = []

    for seed in range(seed_start, seed_start + num_games):
        state = create_initial_state(seed=seed)
        # Initialize strategy for this game
        exploration_strategy.on_game_start(state, 0)
        game_decisions = 0

        while not state.is_game_over and game_decisions < max_per_game:
            moves = generate_legal_moves(state)
            if not moves:
                break

            # Check for 8 decision point
            eight_decision = find_eight_decision(state, moves)
            if eight_decision:
                player = get_acting_player(state)
                opponent = 1 - player

                decision_points.append(
                    DecisionPoint(
                        state=state,
                        seed=seed,
                        turn=state.turn_number,
                        player=player,
                        player_points=state.players[player].point_total,
                        opponent_points=state.players[opponent].point_total,
                        opponent_hand=state.players[opponent].hand,
                    )
                )
                game_decisions += 1

            # Play a move to continue
            move = exploration_strategy.select_move(state, moves)
            try:
                state = execute_move(state, move)
            except IllegalMoveError:
                break

    return decision_points


def test_counterfactual(
    decision: DecisionPoint,
    continuation_strategy: Strategy,
) -> CounterfactualResult:
    """Test both branches from a decision point.

    Args:
        decision: The decision point to test.
        continuation_strategy: Strategy to continue the game after the 8 move.

    Returns:
        Results for both branches.
    """
    state = decision.state
    player = decision.player
    moves = generate_legal_moves(state)

    # Find the 8 moves
    eight_decision = find_eight_decision(state, moves)
    if not eight_decision:
        raise ValueError("Decision point no longer has 8 options")

    points_move, glasses_move = eight_decision

    # Initialize strategy for continuations
    continuation_strategy.on_game_start(state, player)

    # Branch A: Play 8 as Points
    state_a = execute_move(state, points_move)
    points_result = play_to_completion(state_a, continuation_strategy, player)

    # Branch B: Play 8 as Glasses
    state_b = execute_move(state, glasses_move)
    glasses_result = play_to_completion(state_b, continuation_strategy, player)

    return CounterfactualResult(
        decision=decision,
        points_result=points_result,
        glasses_result=glasses_result,
    )


def create_strategy(strategy_name: str, mcts_iterations: int, seed: int | None) -> Strategy:
    """Create a fresh strategy instance."""
    if strategy_name == "mcts":
        return MCTSStrategy(iterations=mcts_iterations, seed=seed)
    elif strategy_name == "ismcts":
        return ISMCTSStrategy(iterations=mcts_iterations, seed=seed)
    elif strategy_name == "heuristic":
        return HeuristicStrategy(seed=seed)
    else:
        return RandomStrategy(seed=seed)


def test_counterfactual_worker(
    decision_data: dict,
    strategy_name: str,
    mcts_iterations: int,
    seed: int | None,
) -> dict:
    """Worker function for parallel counterfactual testing.

    Args:
        decision_data: Serialized decision point data (with pickled state).
        strategy_name: Which strategy to use for continuation.
        mcts_iterations: Iterations for MCTS (if used).
        seed: Random seed.

    Returns:
        Dict with results.
    """
    # Deserialize the decision point
    decision = DecisionPoint.from_pickle_data(decision_data)
    state = decision.state
    player = decision.player

    # Verify we're at a decision point
    moves = generate_legal_moves(state)
    eight_decision = find_eight_decision(state, moves)

    if not eight_decision:
        return {"error": "State is not at an 8 decision point"}

    points_move, glasses_move = eight_decision

    # IMPORTANT: Create SEPARATE strategy instances for each branch
    # to avoid state pollution between branches
    points_strategy = create_strategy(strategy_name, mcts_iterations, seed)
    glasses_strategy = create_strategy(strategy_name, mcts_iterations, seed)

    # Test Points branch
    state_points = execute_move(state, points_move)
    points_strategy.on_game_start(state_points, player)
    points_result = play_to_completion(state_points, points_strategy, player)

    # Test Glasses branch
    state_glasses = execute_move(state, glasses_move)
    glasses_strategy.on_game_start(state_glasses, player)
    glasses_result = play_to_completion(state_glasses, glasses_strategy, player)

    return {
        "seed": decision.seed,
        "turn": decision.turn,
        "player": player,
        "player_points": decision.player_points,
        "opponent_points": decision.opponent_points,
        "points_won": points_result.won,
        "glasses_won": glasses_result.won,
        "points_moves": points_result.moves_to_completion,
        "glasses_moves": glasses_result.moves_to_completion,
    }


def run_parallel_test(
    decisions: int,
    workers: int,
    strategy: str,
    mcts_iterations: int,
    seed_start: int,
) -> list[dict]:
    """Run counterfactual tests in parallel.

    Args:
        decisions: Number of decision points to test.
        workers: Number of parallel workers.
        strategy: Continuation strategy name.
        mcts_iterations: MCTS iterations (if applicable).
        seed_start: Starting seed.

    Returns:
        List of result dicts.
    """
    print(f"Finding {decisions} decision points...")

    # First, find decision points by playing games
    exploration = RandomStrategy(seed=seed_start)
    decision_points = []
    games_played = 0

    while len(decision_points) < decisions:
        batch_points = find_decision_points(
            num_games=100,
            seed_start=seed_start + games_played,
            exploration_strategy=exploration,
            max_per_game=3,
        )
        decision_points.extend(batch_points)
        games_played += 100
        print(f"  Found {len(decision_points)} decision points from {games_played} games...")

    decision_points = decision_points[:decisions]
    print(f"Testing {len(decision_points)} decision points with {strategy} continuation...")

    # Serialize decision data for workers (includes pickled state)
    decision_data = [d.to_pickle_data() for d in decision_points]

    results = []

    with ProcessPoolExecutor(max_workers=workers) as pool:
        futures = [
            pool.submit(
                test_counterfactual_worker,
                data,
                strategy,
                mcts_iterations,
                seed_start + i,
            )
            for i, data in enumerate(decision_data)
        ]

        for i, future in enumerate(as_completed(futures)):
            try:
                result = future.result()
                results.append(result)
                if (i + 1) % 10 == 0:
                    print(f"  Completed {i + 1}/{len(decision_data)} tests...")
            except Exception as e:
                print(f"  Error in worker: {e}")

    return results


def binomial_test_pvalue(successes: int, trials: int, null_prob: float = 0.5) -> float:
    """Calculate two-tailed p-value for binomial test.

    Args:
        successes: Number of successes observed.
        trials: Total number of trials.
        null_prob: Probability under null hypothesis (default 0.5).

    Returns:
        Two-tailed p-value.
    """
    from math import comb

    if trials == 0:
        return 1.0

    # Calculate probability of observing this many or more extreme results
    observed_prob = comb(trials, successes) * (null_prob ** successes) * ((1 - null_prob) ** (trials - successes))

    # Two-tailed: sum probabilities of results as extreme or more extreme
    p_value = 0.0
    for k in range(trials + 1):
        prob = comb(trials, k) * (null_prob ** k) * ((1 - null_prob) ** (trials - k))
        if prob <= observed_prob:
            p_value += prob

    return min(p_value, 1.0)


def analyze_results(results: list[dict]) -> None:
    """Analyze and print results of counterfactual testing."""
    valid = [r for r in results if "error" not in r]

    if not valid:
        print("No valid results to analyze!")
        return

    points_wins = sum(1 for r in valid if r["points_won"])
    glasses_wins = sum(1 for r in valid if r["glasses_won"])
    both_won = sum(1 for r in valid if r["points_won"] and r["glasses_won"])
    both_lost = sum(1 for r in valid if not r["points_won"] and not r["glasses_won"])
    glasses_better = sum(1 for r in valid if r["glasses_won"] and not r["points_won"])
    points_better = sum(1 for r in valid if r["points_won"] and not r["glasses_won"])

    n = len(valid)

    print("\n" + "=" * 60)
    print("COUNTERFACTUAL RESULTS: 8 as Glasses vs 8 as Points")
    print("=" * 60)
    print(f"\nDecision points tested: {n}")
    print(f"\nOverall Outcomes:")
    print(f"  Points branch wins: {points_wins}/{n} ({100*points_wins/n:.1f}%)")
    print(f"  Glasses branch wins: {glasses_wins}/{n} ({100*glasses_wins/n:.1f}%)")
    print(f"\nDifferential Analysis:")
    print(f"  Glasses better (Glasses won, Points lost): {glasses_better}/{n} ({100*glasses_better/n:.1f}%)")
    print(f"  Points better (Points won, Glasses lost): {points_better}/{n} ({100*points_better/n:.1f}%)")
    print(f"  Same outcome (both won or both lost): {both_won + both_lost}/{n} ({100*(both_won + both_lost)/n:.1f}%)")

    if glasses_better + points_better > 0:
        net_advantage = glasses_better - points_better
        advantage_pct = 100 * net_advantage / (glasses_better + points_better)
        winner = "Glasses" if net_advantage > 0 else "Points"
        print(f"\n  NET ADVANTAGE: {winner} by {abs(net_advantage)} decision points ({abs(advantage_pct):.1f}% of contested)")

        # Statistical significance using binomial test
        contested = glasses_better + points_better
        p_value = binomial_test_pvalue(points_better, contested, 0.5)
        significance = ""
        if p_value < 0.001:
            significance = "***"
        elif p_value < 0.01:
            significance = "**"
        elif p_value < 0.05:
            significance = "*"
        print(f"  P-value (binomial test): {p_value:.4f} {significance}")
        if significance:
            print(f"    ({significance} = statistically significant at {'p<0.001' if significance == '***' else 'p<0.01' if significance == '**' else 'p<0.05'})")

    # Breakdown by game context
    print("\n" + "-" * 60)
    print("Breakdown by Turn (Early/Mid/Late):")

    early = [r for r in valid if r["turn"] <= 4]
    mid = [r for r in valid if 5 <= r["turn"] <= 8]
    late = [r for r in valid if r["turn"] >= 9]

    for label, subset in [("Early (T1-4)", early), ("Mid (T5-8)", mid), ("Late (T9+)", late)]:
        if subset:
            p_wins = sum(1 for r in subset if r["points_won"])
            g_wins = sum(1 for r in subset if r["glasses_won"])
            g_better = sum(1 for r in subset if r["glasses_won"] and not r["points_won"])
            p_better = sum(1 for r in subset if r["points_won"] and not r["glasses_won"])
            sn = len(subset)
            print(f"  {label}: n={sn}")
            print(f"    Points: {100*p_wins/sn:.1f}%, Glasses: {100*g_wins/sn:.1f}%")
            if g_better + p_better > 0:
                net = g_better - p_better
                winner = "Glasses" if net > 0 else "Points"
                print(f"    Contested: Glasses +{g_better}, Points +{p_better} -> {winner} wins")

    # Breakdown by point differential
    print("\n" + "-" * 60)
    print("Breakdown by Point Differential:")

    behind = [r for r in valid if r["player_points"] < r["opponent_points"] - 3]
    even = [r for r in valid if abs(r["player_points"] - r["opponent_points"]) <= 3]
    ahead = [r for r in valid if r["player_points"] > r["opponent_points"] + 3]

    for label, subset in [("Behind (>3 pts)", behind), ("Even (±3 pts)", even), ("Ahead (>3 pts)", ahead)]:
        if subset:
            p_wins = sum(1 for r in subset if r["points_won"])
            g_wins = sum(1 for r in subset if r["glasses_won"])
            g_better = sum(1 for r in subset if r["glasses_won"] and not r["points_won"])
            p_better = sum(1 for r in subset if r["points_won"] and not r["glasses_won"])
            sn = len(subset)
            print(f"  {label}: n={sn}")
            print(f"    Points: {100*p_wins/sn:.1f}%, Glasses: {100*g_wins/sn:.1f}%")
            if g_better + p_better > 0:
                net = g_better - p_better
                winner = "Glasses" if net > 0 else "Points"
                print(f"    Contested: Glasses +{g_better}, Points +{p_better} -> {winner} wins")


def main():
    parser = argparse.ArgumentParser(
        description="Counterfactual test: 8 as Glasses vs 8 as Points"
    )
    parser.add_argument(
        "--decisions",
        type=int,
        default=100,
        help="Number of decision points to test (default: 100)",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=4,
        help="Number of parallel workers (default: 4)",
    )
    parser.add_argument(
        "--strategy",
        choices=["mcts", "ismcts", "heuristic", "random"],
        default="heuristic",
        help="Continuation strategy after 8 is played (default: heuristic). Use 'ismcts' for proper glasses testing.",
    )
    parser.add_argument(
        "--iterations",
        type=int,
        default=500,
        help="MCTS iterations if strategy=mcts (default: 500)",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Starting random seed (default: 42)",
    )

    args = parser.parse_args()

    print(f"Counterfactual Test: 8 as Glasses vs 8 as Points")
    print(f"  Decision points: {args.decisions}")
    print(f"  Continuation strategy: {args.strategy}")
    if args.strategy in ("mcts", "ismcts"):
        print(f"  Iterations: {args.iterations}")
    print(f"  Workers: {args.workers}")
    print(f"  Seed: {args.seed}")
    print()

    results = run_parallel_test(
        decisions=args.decisions,
        workers=args.workers,
        strategy=args.strategy,
        mcts_iterations=args.iterations,
        seed_start=args.seed,
    )

    analyze_results(results)


if __name__ == "__main__":
    main()
