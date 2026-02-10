#!/usr/bin/env python
"""Run MCTS vs Minimax tournament with configurable depth."""

import argparse
import json
from datetime import datetime
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description="Run MCTS vs Minimax tournament")
    parser.add_argument("--depth", type=int, default=2, help="Minimax depth (default: 2)")
    parser.add_argument("--games", type=int, default=50, help="Number of games (default: 50)")
    parser.add_argument("--mcts-iter", type=int, default=500, help="MCTS iterations (default: 500)")
    parser.add_argument("--output-dir", type=str, default="training_data", help="Output directory")
    args = parser.parse_args()

    from strategies.minimax import MinimaxStrategy
    from strategies.mcts import MCTSStrategy
    from simulation.runner import run_batch

    print(f"MCTS({args.mcts_iter}) vs Minimax(depth={args.depth}) - {args.games} games")
    print("=" * 50)

    results = run_batch(
        MCTSStrategy(iterations=args.mcts_iter),
        MinimaxStrategy(depth=args.depth),
        num_games=args.games,
    )

    mcts_wins = sum(1 for r in results if r.winner == 0)
    minimax_wins = sum(1 for r in results if r.winner == 1)

    print(f"MCTS wins: {mcts_wins} ({mcts_wins * 100 / args.games:.0f}%)")
    print(f"Minimax wins: {minimax_wins} ({minimax_wins * 100 / args.games:.0f}%)")

    # Save for later analysis
    output_dir = Path(args.output_dir)
    output_dir.mkdir(exist_ok=True)

    filename = f"mcts_vs_minimax_d{args.depth}_{datetime.now():%Y%m%d_%H%M}.json"
    filepath = output_dir / filename

    data = {
        "mcts_iterations": args.mcts_iter,
        "minimax_depth": args.depth,
        "games": args.games,
        "mcts_wins": mcts_wins,
        "minimax_wins": minimax_wins,
        "results": [
            {
                "winner": r.winner,
                "turns": r.turns,
                "win_reason": r.win_reason,
            }
            for r in results
        ],
    }

    with open(filepath, "w") as f:
        json.dump(data, f, indent=2)

    print(f"Saved to {filepath}")


if __name__ == "__main__":
    main()
