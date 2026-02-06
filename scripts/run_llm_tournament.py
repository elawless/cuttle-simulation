#!/usr/bin/env python3
"""CLI for running LLM tournaments.

Usage:
    # Run tournament
    python scripts/run_llm_tournament.py \
        --strategies "llm-haiku,openrouter-qwen3,openrouter-kimi,mcts-1000" \
        --games-per-match 20 \
        --budget 10.00 \
        --parallel 4

    # Resume failed tournament
    python scripts/run_llm_tournament.py --resume <tournament_id>

    # View leaderboard
    python scripts/run_llm_tournament.py --leaderboard --pool llm-only

    # Estimate costs
    python scripts/run_llm_tournament.py --estimate-cost \
        --strategies "llm-haiku,openrouter-qwen3" \
        --games-per-match 20
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from db.database import Database
from simulation.llm_tournament import (
    LLMTournamentRunner,
    TournamentConfig,
    StrategySpec,
)
from core.elo_manager import EloManager
from core.pricing import estimate_tournament_cost


def parse_strategy(spec_str: str) -> StrategySpec:
    """Parse a strategy specification string.

    Formats:
        - "random" -> RandomStrategy
        - "heuristic" -> HeuristicStrategy
        - "mcts-1000" -> MCTSStrategy(iterations=1000)
        - "ismcts-500" -> ISMCTSStrategy(iterations=500)
        - "llm-haiku" -> AnthropicProvider with haiku
        - "llm-sonnet" -> AnthropicProvider with sonnet
        - "openrouter-qwen3" -> OpenRouterProvider with qwen3
        - "openrouter-kimi" -> OpenRouterProvider with kimi
        - "ollama-llama3" -> OllamaProvider with llama3
    """
    spec_str = spec_str.strip()

    if spec_str == "random":
        return StrategySpec(name="Random", factory="random")

    if spec_str == "heuristic":
        return StrategySpec(name="Heuristic", factory="heuristic")

    if spec_str.startswith("mcts-"):
        iterations = int(spec_str.split("-")[1])
        return StrategySpec(
            name=f"MCTS-{iterations}",
            factory="mcts",
            params={"iterations": iterations},
        )

    if spec_str.startswith("ismcts-"):
        iterations = int(spec_str.split("-")[1])
        return StrategySpec(
            name=f"ISMCTS-{iterations}",
            factory="ismcts",
            params={"iterations": iterations},
        )

    if spec_str.startswith("llm-"):
        model = spec_str.replace("llm-", "")
        return StrategySpec(
            name=f"Claude-{model.capitalize()}",
            factory="llm-anthropic",
            params={"model": model},
        )

    if spec_str.startswith("openrouter-"):
        model = spec_str.replace("openrouter-", "")
        return StrategySpec(
            name=f"OR-{model}",
            factory="llm-openrouter",
            params={"model": model},
        )

    if spec_str.startswith("ollama-"):
        model = spec_str.replace("ollama-", "")
        return StrategySpec(
            name=f"Ollama-{model}",
            factory="llm-ollama",
            params={"model": model},
        )

    raise ValueError(f"Unknown strategy specification: {spec_str}")


async def run_tournament(args: argparse.Namespace) -> None:
    """Run a tournament."""
    # Parse strategies
    strategy_specs = [parse_strategy(s) for s in args.strategies.split(",")]

    print(f"\nTournament Configuration:")
    print(f"  Strategies: {len(strategy_specs)}")
    for spec in strategy_specs:
        print(f"    - {spec.name} ({spec.factory})")
    print(f"  Games per match: {args.games_per_match}")
    print(f"  Budget: ${args.budget:.2f}" if args.budget else "  Budget: Unlimited")
    print()

    # Create config
    config = TournamentConfig(
        strategies=strategy_specs,
        games_per_match=args.games_per_match,
        parallel_games=args.parallel,
        budget_usd=args.budget,
        rate_limit_rpm=args.rate_limit,
        log_moves=not args.no_log_moves,
    )

    # Initialize database
    db_path = args.db or "cuttle_tournament.db"
    db = Database(db_path)

    # Create and run tournament
    runner = LLMTournamentRunner(config, db)

    print(f"Tournament ID: {runner.tournament_id}")
    print("Starting tournament...\n")

    try:
        result = await runner.run()
    except KeyboardInterrupt:
        print("\nTournament cancelled by user.")
        runner.cancel()
        return

    # Print results
    print("\n" + "=" * 60)
    print("TOURNAMENT RESULTS")
    print("=" * 60)

    print(f"\nTournament ID: {result.tournament_id}")
    print(f"Total Games: {result.total_games}")
    print(f"Total Cost: ${result.total_cost_usd:.4f}")
    print(f"Duration: {result.duration_seconds:.1f}s")
    print(f"Status: {'Completed' if result.completed else 'Cancelled'}")

    if result.cancelled_reason:
        print(f"Reason: {result.cancelled_reason}")

    print("\n--- ELO Ratings ---")
    sorted_elo = sorted(result.elo_ratings.items(), key=lambda x: x[1], reverse=True)
    for rank, (name, rating) in enumerate(sorted_elo, 1):
        print(f"  {rank}. {name}: {rating:.0f}")

    print("\n--- Match Results ---")
    for match in result.matches:
        total = match.total_games
        a_pct = match.wins_a / total * 100 if total > 0 else 0
        print(
            f"  {match.strategy_a} vs {match.strategy_b}: "
            f"{match.wins_a}-{match.wins_b} ({match.draws} draws) "
            f"[{a_pct:.0f}% win rate, ${match.cost_usd:.4f}]"
        )

    db.close()


async def resume_tournament(args: argparse.Namespace) -> None:
    """Resume an existing tournament."""
    db_path = args.db or "cuttle_tournament.db"
    db = Database(db_path)

    print(f"Resuming tournament: {args.resume}")

    runner = LLMTournamentRunner.resume(args.resume, db)

    print(f"Found {len(runner._completed_games)} completed games")
    print("Continuing tournament...\n")

    try:
        result = await runner.run()
    except KeyboardInterrupt:
        print("\nTournament cancelled by user.")
        runner.cancel()
        return

    # Print results (same as above)
    print("\n" + "=" * 60)
    print("TOURNAMENT RESULTS")
    print("=" * 60)
    print(f"Total Games: {result.total_games}")
    print(f"Total Cost: ${result.total_cost_usd:.4f}")

    db.close()


def show_leaderboard(args: argparse.Namespace) -> None:
    """Display the ELO leaderboard."""
    db_path = args.db or "cuttle_tournament.db"
    db = Database(db_path)

    elo_manager = EloManager(db)
    entries = elo_manager.get_leaderboard(pool=args.pool, limit=args.limit)

    print(f"\n{'='*60}")
    print(f"ELO LEADERBOARD - Pool: {args.pool}")
    print(f"{'='*60}\n")

    if not entries:
        print("No players found.")
    else:
        print(f"{'Rank':<6} {'Player':<30} {'Rating':<10} {'Games':<8}")
        print("-" * 60)
        for entry in entries:
            print(
                f"{entry.rank:<6} {entry.display_name:<30} "
                f"{entry.rating:<10.0f} {entry.games_played:<8}"
            )

    db.close()


def estimate_costs(args: argparse.Namespace) -> None:
    """Estimate tournament costs."""
    strategy_specs = [parse_strategy(s) for s in args.strategies.split(",")]

    # Extract models for cost estimation
    models = []
    for spec in strategy_specs:
        if spec.factory.startswith("llm-"):
            model = spec.params.get("model", "haiku")
            if "anthropic" in spec.factory:
                models.append(model)
            elif "openrouter" in spec.factory:
                models.append(f"{model}")

    if not models:
        print("No LLM strategies specified.")
        return

    # Estimate costs
    estimates = estimate_tournament_cost(
        models,
        games_per_match=args.games_per_match,
        avg_turns_per_game=20,  # Typical game length
    )

    print(f"\n{'='*60}")
    print("COST ESTIMATE")
    print(f"{'='*60}\n")

    print(f"Strategies: {len(strategy_specs)}")
    print(f"Games per match: {args.games_per_match}")
    print(f"Total matches: {len(strategy_specs) * (len(strategy_specs) - 1) // 2}")
    print(f"Total games: {estimates['total_games']}")
    print()

    print("Per-model estimated costs:")
    for model, cost in estimates["per_model"].items():
        print(f"  {model}: ${cost:.4f}")

    print()
    print(f"TOTAL ESTIMATED COST: ${estimates['total']:.4f}")


def main() -> None:
    # Configure logging to show progress
    import logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(message)s",
        datefmt="%H:%M:%S",
    )

    parser = argparse.ArgumentParser(
        description="Run LLM tournaments for Cuttle",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    # Mode selection
    parser.add_argument(
        "--resume",
        metavar="TOURNAMENT_ID",
        help="Resume a previously started tournament",
    )
    parser.add_argument(
        "--leaderboard",
        action="store_true",
        help="Show the ELO leaderboard",
    )
    parser.add_argument(
        "--estimate-cost",
        action="store_true",
        help="Estimate tournament costs without running",
    )

    # Tournament configuration
    parser.add_argument(
        "--strategies",
        default="random,heuristic,mcts-500",
        help="Comma-separated strategy specs (default: random,heuristic,mcts-500)",
    )
    parser.add_argument(
        "--games-per-match",
        type=int,
        default=10,
        help="Games per pairwise matchup (default: 10)",
    )
    parser.add_argument(
        "--budget",
        type=float,
        help="Maximum budget in USD",
    )
    parser.add_argument(
        "--parallel",
        type=int,
        default=4,
        help="Parallel games (default: 4)",
    )
    parser.add_argument(
        "--rate-limit",
        type=int,
        default=60,
        help="API requests per minute (default: 60)",
    )
    parser.add_argument(
        "--no-log-moves",
        action="store_true",
        help="Disable move logging for faster execution",
    )

    # Leaderboard options
    parser.add_argument(
        "--pool",
        default="all",
        help="Rating pool to query (default: all)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Number of entries to show (default: 20)",
    )

    # Database
    parser.add_argument(
        "--db",
        help="Database path (default: cuttle_tournament.db)",
    )

    args = parser.parse_args()

    # Load environment variables
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass

    # Execute appropriate mode
    if args.leaderboard:
        show_leaderboard(args)
    elif args.estimate_cost:
        estimate_costs(args)
    elif args.resume:
        asyncio.run(resume_tournament(args))
    else:
        asyncio.run(run_tournament(args))


if __name__ == "__main__":
    main()
