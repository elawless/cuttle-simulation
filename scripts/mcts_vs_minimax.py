#!/usr/bin/env python
"""Run MCTS vs Minimax tournament with configurable depth and memory levels."""

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
    parser.add_argument(
        "--memory",
        type=str,
        choices=["perfect", "turn_limited", "probabilistic", "none"],
        default="perfect",
        help="Memory level for both strategies (default: perfect)"
    )
    parser.add_argument(
        "--memory-turns",
        type=int,
        default=3,
        help="For turn_limited memory, how many turns to remember (default: 3)"
    )
    parser.add_argument("--workers", type=int, default=1, help="MCTS parallel workers (default: 1)")
    args = parser.parse_args()

    from strategies.minimax import MinimaxStrategy
    from strategies.mcts import MCTSStrategy
    from strategies.knowledge import MemoryLevel

    # Map string to MemoryLevel enum
    memory_map = {
        "perfect": MemoryLevel.PERFECT,
        "turn_limited": MemoryLevel.TURN_LIMITED,
        "probabilistic": MemoryLevel.PROBABILISTIC,
        "none": MemoryLevel.NONE,
    }
    memory_level = memory_map[args.memory]

    print(f"MCTS({args.mcts_iter}) vs Minimax(depth={args.depth}) - {args.games} games")
    print(f"Memory level: {args.memory.upper()}")
    if args.memory == "turn_limited":
        print(f"Memory turns: {args.memory_turns}")
    if args.workers > 1:
        print(f"MCTS workers: {args.workers}")
    print("=" * 50)

    mcts = MCTSStrategy(
        iterations=args.mcts_iter,
        num_workers=args.workers,
        memory_level=memory_level,
        memory_turns=args.memory_turns,
    )
    minimax = MinimaxStrategy(
        depth=args.depth,
        memory_level=memory_level,
        memory_turns=args.memory_turns,
    )

    # Run games with progress logging
    from simulation.runner import GameRunner

    runner = GameRunner(mcts, minimax, log_moves=False)
    results = []
    mcts_wins = 0
    minimax_wins = 0
    log_interval = max(1, args.games // 10)  # Log ~10 times during run

    for i in range(args.games):
        result, _ = runner.run_game(seed=i)
        results.append(result)

        if result.winner == 0:
            mcts_wins += 1
        else:
            minimax_wins += 1

        game_num = i + 1
        if game_num % log_interval == 0 or game_num == args.games:
            print(f"Game {game_num}/{args.games} - MCTS: {mcts_wins}, Minimax: {minimax_wins}")

    print("=" * 50)

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
        "memory_level": args.memory,
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
