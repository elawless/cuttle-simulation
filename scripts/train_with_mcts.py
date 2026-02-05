#!/usr/bin/env python3
"""Run MCTS games to collect training data.

This script runs many games in parallel, collecting MCTS statistics
that can be used to train heuristics or policy networks.

Examples:
    # Run 100 games with MCTS vs Heuristic
    python scripts/train_with_mcts.py --games 100

    # Use 8 workers and 500 MCTS iterations
    python scripts/train_with_mcts.py --games 100 --workers 8 --iterations 500

    # Specify output directory
    python scripts/train_with_mcts.py --games 100 --output training_data
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run MCTS games to collect training data.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--games",
        type=int,
        default=100,
        help="Number of games to run (default: 100)",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=None,
        help="Number of parallel workers (default: CPU count)",
    )
    parser.add_argument(
        "--iterations",
        type=int,
        default=1000,
        help="MCTS iterations per move (default: 1000)",
    )
    parser.add_argument(
        "--opponent",
        type=str,
        default="heuristic",
        choices=["random", "heuristic"],
        help="Opponent strategy (default: heuristic)",
    )
    parser.add_argument(
        "--mcts-player",
        type=int,
        default=0,
        choices=[0, 1],
        help="Which player uses MCTS (default: 0)",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="training_data",
        help="Output directory for training data (default: training_data)",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=0,
        help="Starting random seed (default: 0)",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress progress output",
    )
    return parser.parse_args()


def print_progress(game_data: dict, progress) -> None:
    """Print progress update."""
    winner_str = "draw" if game_data["winner"] is None else f"P{game_data['winner']}"
    elapsed = progress.elapsed_seconds
    rate = progress.games_per_second

    p0_wins, p1_wins = progress.wins_by_player
    total = p0_wins + p1_wins
    p0_rate = p0_wins / total * 100 if total > 0 else 0

    print(
        f"\r[{progress.completed}/{progress.total}] "
        f"Winner: {winner_str} | "
        f"P0 wins: {p0_wins} ({p0_rate:.1f}%) | "
        f"Rate: {rate:.2f} games/s | "
        f"Elapsed: {elapsed:.1f}s",
        end="",
        flush=True,
    )


def main() -> int:
    args = parse_args()

    # Import here to avoid slow import on --help
    from training.data_collector import DataCollector
    from training.parallel_runner import ParallelGameRunner

    print(f"Starting MCTS training data collection")
    print(f"  Games: {args.games}")
    print(f"  Workers: {args.workers or 'auto'}")
    print(f"  MCTS iterations: {args.iterations}")
    print(f"  MCTS player: {args.mcts_player}")
    print(f"  Opponent: {args.opponent}")
    print(f"  Output: {args.output}/")
    print()

    runner = ParallelGameRunner(num_workers=args.workers)
    collector = DataCollector(Path(args.output))

    callback = None if args.quiet else print_progress

    start_time = time.perf_counter()

    # Run games with MCTS statistics collection
    game_data_list = runner.run_games_with_mcts_stats(
        mcts_player=args.mcts_player,
        opponent_strategy_name=args.opponent,
        num_games=args.games,
        mcts_iterations=args.iterations,
        callback=callback,
        start_seed=args.seed,
    )

    if not args.quiet:
        print()  # Newline after progress

    elapsed = time.perf_counter() - start_time
    print(f"\nCompleted {len(game_data_list)} games in {elapsed:.1f}s")

    # Convert to GameHistory objects
    histories = [collector.collect_from_game_data(gd) for gd in game_data_list]

    # Print statistics
    stats = collector.get_statistics(histories)
    print(f"\nResults:")
    print(f"  MCTS wins: {stats['mcts_wins']}/{stats['num_games']} ({stats['mcts_win_rate']*100:.1f}%)")
    print(f"  Total MCTS moves collected: {stats['total_mcts_moves']}")
    print(f"  Avg moves per game: {stats['avg_mcts_moves_per_game']:.1f}")

    # Save to file
    filename = f"mcts{args.iterations}_vs_{args.opponent}_{args.games}games.json"
    output_path = collector.save_histories(histories, filename)
    print(f"\nSaved training data to: {output_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
