#!/usr/bin/env python3
"""Debug script for analyzing MCTS game play.

Prints move-by-move game state with MCTS statistics to identify
issues with move selection and win rate.

Usage:
    python scripts/debug_mcts.py --games 5 --iterations 500 --verbose
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from cuttle_engine.executor import execute_move
from cuttle_engine.move_generator import generate_legal_moves
from cuttle_engine.state import GamePhase, create_initial_state
from strategies.mcts import MCTSStrategy, MCTSNode
from strategies.random_strategy import RandomStrategy


def get_acting_player(state):
    """Determine which player needs to act in the given state."""
    if state.phase == GamePhase.COUNTER:
        return state.counter_state.waiting_for_player
    elif state.phase == GamePhase.DISCARD_FOUR:
        return state.four_state.player
    elif state.phase == GamePhase.RESOLVE_SEVEN:
        return state.seven_state.player
    return state.current_player


def format_hand(hand):
    """Format a hand for display."""
    return ", ".join(str(c) for c in hand) if hand else "(empty)"


def format_field(field):
    """Format a point/permanent field for display."""
    return ", ".join(str(c) for c in field) if field else "(none)"


def test_simulation_perspective():
    """Test that simulations return results from the correct perspective."""
    print("\n=== Simulation Perspective Test ===\n")

    # Create a state where we know who should win
    state = create_initial_state(seed=42)

    # Run multiple simulations and track results
    mcts = MCTSStrategy(iterations=100, seed=42)

    # Run 100 simulations from the same state
    p0_wins = 0
    p1_wins = 0
    draws = 0

    for i in range(100):
        result = mcts._simulate(state, perspective_player=0)
        if result is None:
            draws += 1
        elif result > 0.6:
            p0_wins += 1
        elif result < 0.4:
            p1_wins += 1
        else:
            draws += 1

    print(f"From P0's perspective (100 simulations):")
    print(f"  P0 wins: {p0_wins}, P1 wins: {p1_wins}, Draws/neutral: {draws}")

    # Now test from P1's perspective - should be opposite
    p0_wins_p1_perspective = 0
    p1_wins_p1_perspective = 0
    draws_p1 = 0

    mcts2 = MCTSStrategy(iterations=100, seed=42)  # Same seed for comparison
    for i in range(100):
        result = mcts2._simulate(state, perspective_player=1)
        if result is None:
            draws_p1 += 1
        elif result > 0.6:
            p1_wins_p1_perspective += 1  # P1 won from P1's perspective
        elif result < 0.4:
            p0_wins_p1_perspective += 1  # P0 won (P1 lost)
        else:
            draws_p1 += 1

    print(f"\nFrom P1's perspective (100 simulations, same seed):")
    print(f"  P1 wins: {p1_wins_p1_perspective}, P0 wins: {p0_wins_p1_perspective}, Draws/neutral: {draws_p1}")

    print("\nExpected: Results should be mirror images (P0's wins ≈ P1's losses)")
    print(f"  P0 win rate (from P0): {p0_wins}%")
    print(f"  P0 win rate (from P1): {p0_wins_p1_perspective}%")
    print(f"  These should be approximately equal.")


def run_debug_game(
    mcts_iterations: int = 500,
    seed: int | None = None,
    verbose: bool = True,
    mcts_player: int = 0,
):
    """Run a single game with detailed MCTS debugging output.

    Args:
        mcts_iterations: Number of MCTS iterations per move.
        seed: Random seed for game initialization.
        verbose: If True, print detailed state each move.
        mcts_player: Which player uses MCTS (0 or 1).

    Returns:
        Tuple of (winner, total_moves, mcts_move_stats).
    """
    # Create strategies
    mcts = MCTSStrategy(iterations=mcts_iterations, seed=seed)
    random_strat = RandomStrategy(seed=seed)

    strategies = (
        (mcts, random_strat) if mcts_player == 0
        else (random_strat, mcts)
    )

    # Initialize game
    state = create_initial_state(seed=seed)

    print(f"\n{'='*60}")
    print(f"Game Start (seed={seed})")
    print(f"MCTS({mcts_iterations}) is Player {mcts_player}")
    print(f"{'='*60}")

    if verbose:
        print(f"\nInitial hands:")
        print(f"  P0: {format_hand(state.players[0].hand)}")
        print(f"  P1: {format_hand(state.players[1].hand)}")

    move_count = 0
    mcts_move_stats = []
    max_turns = 200

    while not state.is_game_over and state.turn_number <= max_turns:
        acting_player = get_acting_player(state)
        legal_moves = generate_legal_moves(state)

        if not legal_moves:
            print(f"\nNo legal moves - ending game")
            break

        # Get move and stats
        is_mcts_turn = acting_player == mcts_player

        if is_mcts_turn and state.phase == GamePhase.MAIN:
            # Run MCTS once and capture statistics from the same search
            move, move_stats = mcts.select_move_with_stats(state, legal_moves)

            # Sort moves by visit count
            sorted_stats = sorted(
                move_stats.items(),
                key=lambda x: x[1]["visits"],
                reverse=True
            )
            top_3 = sorted_stats[:3]

            mcts_move_stats.append({
                "turn": state.turn_number,
                "top_moves": top_3,
                "selected": move,
                "total_visits": sum(s["visits"] for _, s in move_stats.items()),
            })
        else:
            move_stats = None
            move = strategies[acting_player].select_move(state, legal_moves)

        # Print move info
        print(f"\n--- Turn {state.turn_number}, Player {acting_player} ({state.phase.name}) ---")
        print(f"Points: P0={state.players[0].point_total}, P1={state.players[1].point_total}")
        print(f"Thresholds: P0 needs {state.point_threshold(0)}, P1 needs {state.point_threshold(1)}")

        if verbose:
            print(f"Hand: {format_hand(state.players[acting_player].hand)}")
            print(f"Points field: {format_field(state.players[acting_player].points_field)}")
            print(f"Permanents: {format_field(state.players[acting_player].permanents)}")
            print(f"Legal moves: {len(legal_moves)}")

        print(f"Move: {move}")

        if is_mcts_turn and move_stats:
            print(f"\nMCTS Stats (top 3 by visits):")
            for m, stats in top_3:
                selected_marker = " <-- SELECTED" if m == move else ""
                print(f"  {m}")
                print(f"    visits={stats['visits']}, wins={stats['wins']:.1f}, "
                      f"win_rate={stats['win_rate']:.1%}{selected_marker}")

        # Execute move
        try:
            state = execute_move(state, move)
            move_count += 1
        except Exception as e:
            print(f"\nERROR executing move: {e}")
            break

    # Game ended
    print(f"\n{'='*60}")
    print(f"Game Over!")
    print(f"Winner: Player {state.winner} ({state.win_reason.name if state.win_reason else 'unknown'})")
    print(f"Final scores: P0={state.players[0].point_total}, P1={state.players[1].point_total}")
    print(f"Total moves: {move_count}")
    print(f"{'='*60}")

    return state.winner, move_count, mcts_move_stats


def analyze_mcts_stats(all_stats: list[list[dict]]):
    """Analyze MCTS move selection patterns across games."""
    print(f"\n{'='*60}")
    print("MCTS Move Selection Analysis")
    print(f"{'='*60}")

    # Check if selected move was highest-visit
    selected_top = 0
    total_decisions = 0
    avg_top_winrate = []

    for game_stats in all_stats:
        for move_info in game_stats:
            total_decisions += 1
            top_moves = move_info["top_moves"]
            if top_moves:
                top_move, top_stats = top_moves[0]
                if top_move == move_info["selected"]:
                    selected_top += 1
                avg_top_winrate.append(top_stats["win_rate"])

    if total_decisions > 0:
        print(f"MCTS selected highest-visit move: {selected_top}/{total_decisions} "
              f"({100*selected_top/total_decisions:.1f}%)")

    if avg_top_winrate:
        print(f"Average top move win rate: {sum(avg_top_winrate)/len(avg_top_winrate):.1%}")
        print(f"  (Should be >50% if MCTS is working correctly)")

    # Check for concerning patterns
    low_winrate_selections = [
        wr for wr in avg_top_winrate if wr < 0.4
    ]
    if low_winrate_selections:
        print(f"\nWARNING: {len(low_winrate_selections)} moves had top win rate <40%")
        print("  This may indicate backpropagation issues or insufficient iterations")


def run_tournament(
    num_games: int = 10,
    mcts_iterations: int = 500,
    verbose: bool = False,
):
    """Run a tournament and analyze results."""
    print(f"\n{'#'*60}")
    print(f"MCTS Debugging Tournament")
    print(f"Games: {num_games}, MCTS iterations: {mcts_iterations}")
    print(f"{'#'*60}")

    mcts_wins = 0
    random_wins = 0
    all_stats = []

    for i in range(num_games):
        # Alternate who plays first
        mcts_player = i % 2

        winner, moves, stats = run_debug_game(
            mcts_iterations=mcts_iterations,
            seed=i,
            verbose=verbose,
            mcts_player=mcts_player,
        )

        if winner == mcts_player:
            mcts_wins += 1
        elif winner is not None:
            random_wins += 1

        all_stats.append(stats)

    # Summary
    print(f"\n{'#'*60}")
    print(f"Tournament Results")
    print(f"{'#'*60}")
    print(f"MCTS wins: {mcts_wins}/{num_games} ({100*mcts_wins/num_games:.1f}%)")
    print(f"Random wins: {random_wins}/{num_games} ({100*random_wins/num_games:.1f}%)")

    expected = "EXPECTED: MCTS should win >70% against Random"
    if mcts_wins / num_games < 0.7:
        print(f"\n*** BELOW EXPECTED ***")
        print(expected)
        print("Possible issues:")
        print("  1. Backpropagation perspective bug (wins credited wrong way)")
        print("  2. player_just_moved tracking incorrect")
        print("  3. Insufficient iterations")
        print("  4. Simulation quality issues")
    else:
        print(f"\n{expected} - PASS")

    # Analyze stats
    analyze_mcts_stats(all_stats)


def main():
    parser = argparse.ArgumentParser(description="Debug MCTS game play")
    parser.add_argument(
        "--games", type=int, default=5,
        help="Number of games to run (default: 5)"
    )
    parser.add_argument(
        "--iterations", type=int, default=500,
        help="MCTS iterations per move (default: 500)"
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true",
        help="Print detailed state each move"
    )
    parser.add_argument(
        "--single", type=int, default=None,
        help="Run a single game with given seed"
    )

    args = parser.parse_args()

    if args.single is not None:
        if args.single == -1:
            # Special case: run perspective test
            test_simulation_perspective()
        else:
            run_debug_game(
                mcts_iterations=args.iterations,
                seed=args.single,
                verbose=True,
                mcts_player=0,
            )
    else:
        run_tournament(
            num_games=args.games,
            mcts_iterations=args.iterations,
            verbose=args.verbose,
        )


if __name__ == "__main__":
    main()
