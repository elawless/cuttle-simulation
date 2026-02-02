"""Run 10k games and save results for easy viewing."""

import json
import os
from collections import defaultdict
from pathlib import Path
from cuttle_engine.state import create_initial_state, GamePhase
from cuttle_engine.move_generator import generate_legal_moves
from cuttle_engine.executor import execute_move, IllegalMoveError
from cuttle_engine.moves import (
    PlayPoints, PlayPermanent, PlayOneOff, Scuttle, Draw,
    Counter, DeclineCounter, Discard, Pass, ResolveSeven
)
from strategies.random_strategy import RandomStrategy


OUTPUT_DIR = Path("analysis_output")


def get_move_category(move):
    """Categorize a move for analysis."""
    match move:
        case PlayPoints(card=card):
            return f"PlayPoints_{card.rank.name}"
        case PlayPermanent(card=card):
            return f"PlayPermanent_{card.rank.name}"
        case PlayOneOff(card=card):
            return f"PlayOneOff_{card.rank.name}"
        case Scuttle():
            return "Scuttle"
        case Draw():
            return "Draw"
        case Counter():
            return "Counter"
        case DeclineCounter():
            return "DeclineCounter"
        case Discard():
            return "Discard"
        case Pass():
            return "Pass"
        case ResolveSeven():
            return "ResolveSeven"
        case _:
            return "Unknown"


def run_game(seed):
    """Run a single game and return detailed log."""
    state = create_initial_state(seed=seed)
    strategy = RandomStrategy(seed=seed * 2)

    game_log = {
        "seed": seed,
        "moves": [],
        "winner": None,
        "final_score": None,
        "win_reason": None,
        "error": None
    }

    turn = 0
    while not state.is_game_over and turn < 500:
        # Determine acting player
        if state.phase == GamePhase.COUNTER:
            acting = state.counter_state.waiting_for_player
        elif state.phase == GamePhase.DISCARD_FOUR:
            acting = state.four_state.player
        elif state.phase == GamePhase.RESOLVE_SEVEN:
            acting = state.seven_state.player
        else:
            acting = state.current_player

        moves = generate_legal_moves(state)
        if not moves:
            break

        move = strategy.select_move(state, moves)
        category = get_move_category(move)

        move_record = {
            "turn": turn,
            "player": acting,
            "move": str(move),
            "category": category,
            "score_before": [state.players[0].point_total, state.players[1].point_total],
            "hands": [len(state.players[0].hand), len(state.players[1].hand)],
            "deck_size": len(state.deck)
        }

        try:
            state = execute_move(state, move)
            move_record["score_after"] = [state.players[0].point_total, state.players[1].point_total]
            game_log["moves"].append(move_record)
        except IllegalMoveError as e:
            move_record["error"] = str(e)
            game_log["moves"].append(move_record)
            game_log["error"] = str(e)
            return game_log

        turn += 1

    game_log["winner"] = state.winner
    game_log["final_score"] = [state.players[0].point_total, state.players[1].point_total]
    game_log["win_reason"] = state.win_reason.name if state.win_reason else None

    return game_log


def format_game_readable(game_log):
    """Format a game log as human-readable text."""
    lines = []
    lines.append(f"=" * 70)
    lines.append(f"GAME {game_log['seed']}")
    lines.append(f"=" * 70)

    for m in game_log["moves"]:
        score = f"{m['score_before'][0]}-{m['score_before'][1]}"
        lines.append(f"T{m['turn']:02d} P{m['player']}: {m['move'][:55]:<55} [{score}]")
        if "error" in m:
            lines.append(f"     ERROR: {m['error']}")

    lines.append("")
    if game_log["error"]:
        lines.append(f"GAME ERROR: {game_log['error']}")
    else:
        lines.append(f"WINNER: P{game_log['winner']}")
        lines.append(f"FINAL SCORE: {game_log['final_score'][0]} - {game_log['final_score'][1]}")
        lines.append(f"REASON: {game_log['win_reason']}")

    lines.append("")
    return "\n".join(lines)


def main():
    OUTPUT_DIR.mkdir(exist_ok=True)

    num_games = 10000
    print(f"Running {num_games} games...")

    # Storage for analysis
    all_games = []
    move_stats = defaultdict(lambda: {"made": 0, "won": 0})
    first_move_stats = defaultdict(lambda: {"made": 0, "won": 0})
    winner_counts = {0: 0, 1: 0, None: 0}
    errors = 0

    # Run games
    for seed in range(num_games):
        if seed % 1000 == 0:
            print(f"  Progress: {seed}/{num_games}")

        game_log = run_game(seed)
        all_games.append(game_log)

        if game_log["error"]:
            errors += 1
            continue

        winner = game_log["winner"]
        winner_counts[winner] += 1

        # Analyze moves
        for m in game_log["moves"]:
            player = m["player"]
            category = m["category"]
            player_won = (winner == player)

            move_stats[category]["made"] += 1
            if player_won:
                move_stats[category]["won"] += 1

        # First move analysis
        if game_log["moves"]:
            first = game_log["moves"][0]
            if first["player"] == 0:
                first_move_stats[first["category"]]["made"] += 1
                if winner == 0:
                    first_move_stats[first["category"]]["won"] += 1

    print(f"Completed: {num_games - errors} games, {errors} errors")

    # Save all game logs as JSON (for programmatic access)
    print("Saving game logs...")
    with open(OUTPUT_DIR / "all_games.json", "w") as f:
        json.dump(all_games, f)

    # Save readable game logs (first 100, random sample of 100, last 100)
    print("Saving readable samples...")

    with open(OUTPUT_DIR / "games_first_100.txt", "w") as f:
        for game in all_games[:100]:
            f.write(format_game_readable(game))

    with open(OUTPUT_DIR / "games_last_100.txt", "w") as f:
        for game in all_games[-100:]:
            f.write(format_game_readable(game))

    # Sample 100 random games
    import random
    random.seed(42)
    sample_indices = random.sample(range(len(all_games)), min(100, len(all_games)))
    with open(OUTPUT_DIR / "games_random_100.txt", "w") as f:
        for i in sorted(sample_indices):
            f.write(format_game_readable(all_games[i]))

    # Save analysis summary
    print("Generating analysis...")

    analysis_lines = []
    analysis_lines.append("=" * 70)
    analysis_lines.append(f"BRUTE FORCE ANALYSIS - {num_games} GAMES")
    analysis_lines.append("=" * 70)
    analysis_lines.append("")
    analysis_lines.append(f"Games completed: {num_games - errors}")
    analysis_lines.append(f"Errors: {errors}")
    analysis_lines.append(f"P0 wins: {winner_counts[0]} ({100*winner_counts[0]/(num_games-errors):.1f}%)")
    analysis_lines.append(f"P1 wins: {winner_counts[1]} ({100*winner_counts[1]/(num_games-errors):.1f}%)")
    analysis_lines.append(f"Draws: {winner_counts[None]}")

    analysis_lines.append("")
    analysis_lines.append("=" * 70)
    analysis_lines.append("MOVE WIN RATES")
    analysis_lines.append("=" * 70)
    analysis_lines.append(f"{'Move Category':<30} {'Times Made':>12} {'Win Rate':>10}")
    analysis_lines.append("-" * 55)

    sorted_moves = sorted(move_stats.items(), key=lambda x: x[1]["made"], reverse=True)
    for cat, stats in sorted_moves:
        if stats["made"] >= 100:
            rate = stats["won"] / stats["made"]
            analysis_lines.append(f"{cat:<30} {stats['made']:>12} {rate:>10.1%}")

    analysis_lines.append("")
    analysis_lines.append("=" * 70)
    analysis_lines.append("FIRST MOVE WIN RATES (P0)")
    analysis_lines.append("=" * 70)
    analysis_lines.append(f"{'First Move':<30} {'Times Made':>12} {'P0 Win Rate':>12}")
    analysis_lines.append("-" * 55)

    sorted_first = sorted(first_move_stats.items(), key=lambda x: x[1]["made"], reverse=True)
    for cat, stats in sorted_first:
        if stats["made"] >= 50:
            rate = stats["won"] / stats["made"]
            analysis_lines.append(f"{cat:<30} {stats['made']:>12} {rate:>12.1%}")

    # Best and worst moves
    significant = [(c, s) for c, s in move_stats.items() if s["made"] >= 500]
    if significant:
        best = max(significant, key=lambda x: x[1]["won"]/x[1]["made"])
        worst = min(significant, key=lambda x: x[1]["won"]/x[1]["made"])

        analysis_lines.append("")
        analysis_lines.append("=" * 70)
        analysis_lines.append("KEY INSIGHTS")
        analysis_lines.append("=" * 70)
        analysis_lines.append(f"Best move:  {best[0]} ({100*best[1]['won']/best[1]['made']:.1f}% win rate, n={best[1]['made']})")
        analysis_lines.append(f"Worst move: {worst[0]} ({100*worst[1]['won']/worst[1]['made']:.1f}% win rate, n={worst[1]['made']})")

    analysis_text = "\n".join(analysis_lines)
    print(analysis_text)

    with open(OUTPUT_DIR / "analysis_summary.txt", "w") as f:
        f.write(analysis_text)

    print(f"\nOutput saved to {OUTPUT_DIR}/")
    print(f"  - all_games.json          (all {num_games} games, JSON)")
    print(f"  - games_first_100.txt     (first 100 games, readable)")
    print(f"  - games_last_100.txt      (last 100 games, readable)")
    print(f"  - games_random_100.txt    (random sample, readable)")
    print(f"  - analysis_summary.txt    (statistics)")


if __name__ == "__main__":
    main()
