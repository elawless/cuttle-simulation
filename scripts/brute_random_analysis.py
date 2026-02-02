"""Brute random analysis - run many games and find patterns."""

from collections import defaultdict
from cuttle_engine.state import create_initial_state, GamePhase
from cuttle_engine.move_generator import generate_legal_moves
from cuttle_engine.executor import execute_move, IllegalMoveError
from cuttle_engine.moves import (
    PlayPoints, PlayPermanent, PlayOneOff, Scuttle, Draw,
    Counter, DeclineCounter, Discard, Pass, ResolveSeven
)
from cuttle_engine.cards import Rank
from strategies.random_strategy import RandomStrategy


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


def run_game_with_tracking(seed, verbose=False):
    """Run a single game and track all moves."""
    state = create_initial_state(seed=seed)
    strategy = RandomStrategy(seed=seed * 2)

    moves_by_player = {0: [], 1: []}
    move_log = []
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

        # Log the move
        category = get_move_category(move)
        moves_by_player[acting].append(category)

        if verbose:
            p0_pts = state.players[0].point_total
            p1_pts = state.players[1].point_total
            move_log.append(f"T{turn:02d} P{acting}: {str(move)[:50]} (score: {p0_pts}-{p1_pts})")

        try:
            state = execute_move(state, move)
        except IllegalMoveError as e:
            if verbose:
                move_log.append(f"  ERROR: {e}")
            return None, None, move_log

        turn += 1

    if verbose:
        p0_pts = state.players[0].point_total
        p1_pts = state.players[1].point_total
        move_log.append(f"GAME OVER: Winner=P{state.winner}, Final score: {p0_pts}-{p1_pts}, Reason={state.win_reason}")

    return state.winner, moves_by_player, move_log


def print_sample_games(num_games=3):
    """Print a few complete games for verification."""
    print("=" * 70)
    print("SAMPLE GAMES (for verification)")
    print("=" * 70)

    for seed in range(num_games):
        print(f"\n--- Game {seed + 1} (seed={seed}) ---")
        winner, moves, log = run_game_with_tracking(seed, verbose=True)

        for line in log:
            print(f"  {line}")

        print()


def analyze_patterns(num_games=500):
    """Run many games and analyze move patterns."""
    print("=" * 70)
    print(f"PATTERN ANALYSIS ({num_games} games)")
    print("=" * 70)

    # Track: for each move category, how often does the player who made it win?
    move_wins = defaultdict(lambda: {"made": 0, "won": 0})

    # Track: first move correlations
    first_move_wins = defaultdict(lambda: {"made": 0, "won": 0})

    # Track: move frequency by winner
    winner_moves = {0: defaultdict(int), 1: defaultdict(int), None: defaultdict(int)}

    games_completed = 0
    games_errored = 0

    for seed in range(num_games):
        winner, moves_by_player, _ = run_game_with_tracking(seed, verbose=False)

        if winner is None and moves_by_player is None:
            games_errored += 1
            continue

        games_completed += 1

        # Analyze each player's moves
        for player in [0, 1]:
            player_won = (winner == player)

            for move_cat in moves_by_player[player]:
                move_wins[move_cat]["made"] += 1
                if player_won:
                    move_wins[move_cat]["won"] += 1

            # First move analysis (for player 0 only, since they go first)
            if player == 0 and moves_by_player[player]:
                first_move = moves_by_player[player][0]
                first_move_wins[first_move]["made"] += 1
                if player_won:
                    first_move_wins[first_move]["won"] += 1

        # Track moves by winner
        for player in [0, 1]:
            for move_cat in moves_by_player[player]:
                winner_moves[winner][move_cat] += 1

    print(f"\nGames completed: {games_completed}, Errors: {games_errored}")

    # Print move win rates
    print(f"\n{'Move Category':<30} {'Times Made':>12} {'Win Rate':>10}")
    print("-" * 55)

    sorted_moves = sorted(move_wins.items(), key=lambda x: x[1]["made"], reverse=True)
    for move_cat, stats in sorted_moves:
        if stats["made"] >= 10:  # Only show moves made at least 10 times
            win_rate = stats["won"] / stats["made"] if stats["made"] > 0 else 0
            print(f"{move_cat:<30} {stats['made']:>12} {win_rate:>10.1%}")

    # Print first move analysis
    print(f"\n\nFIRST MOVE ANALYSIS (P0's opening move)")
    print(f"{'First Move':<30} {'Times Made':>12} {'P0 Win Rate':>12}")
    print("-" * 55)

    sorted_first = sorted(first_move_wins.items(), key=lambda x: x[1]["made"], reverse=True)
    for move_cat, stats in sorted_first:
        if stats["made"] >= 5:
            win_rate = stats["won"] / stats["made"] if stats["made"] > 0 else 0
            print(f"{move_cat:<30} {stats['made']:>12} {win_rate:>12.1%}")

    # Baseline P0 win rate
    p0_baseline = sum(1 for seed in range(games_completed)
                      if run_game_with_tracking(seed, verbose=False)[0] == 0)
    # Actually let's compute from what we tracked

    print(f"\n\nKEY INSIGHTS:")

    # Find moves with highest/lowest win rates (with sufficient sample)
    significant_moves = [(cat, stats) for cat, stats in move_wins.items() if stats["made"] >= 50]

    if significant_moves:
        best_move = max(significant_moves, key=lambda x: x[1]["won"]/x[1]["made"])
        worst_move = min(significant_moves, key=lambda x: x[1]["won"]/x[1]["made"])

        best_rate = best_move[1]["won"] / best_move[1]["made"]
        worst_rate = worst_move[1]["won"] / worst_move[1]["made"]

        print(f"  Best move category: {best_move[0]} ({best_rate:.1%} win rate)")
        print(f"  Worst move category: {worst_move[0]} ({worst_rate:.1%} win rate)")


def analyze_winning_vs_losing_patterns(num_games=500):
    """Compare move patterns between winners and losers."""
    print("\n" + "=" * 70)
    print("WINNER vs LOSER MOVE PATTERNS")
    print("=" * 70)

    winner_moves = defaultdict(int)
    loser_moves = defaultdict(int)
    winner_total = 0
    loser_total = 0

    for seed in range(num_games):
        winner, moves_by_player, _ = run_game_with_tracking(seed, verbose=False)

        if winner is None or moves_by_player is None:
            continue

        loser = 1 - winner

        for move_cat in moves_by_player[winner]:
            winner_moves[move_cat] += 1
            winner_total += 1

        for move_cat in moves_by_player[loser]:
            loser_moves[move_cat] += 1
            loser_total += 1

    print(f"\n{'Move Category':<30} {'Winner %':>10} {'Loser %':>10} {'Diff':>10}")
    print("-" * 65)

    all_moves = set(winner_moves.keys()) | set(loser_moves.keys())

    diffs = []
    for move_cat in all_moves:
        w_pct = winner_moves[move_cat] / winner_total if winner_total > 0 else 0
        l_pct = loser_moves[move_cat] / loser_total if loser_total > 0 else 0
        diff = w_pct - l_pct
        diffs.append((move_cat, w_pct, l_pct, diff))

    # Sort by difference
    diffs.sort(key=lambda x: x[3], reverse=True)

    for move_cat, w_pct, l_pct, diff in diffs:
        if winner_moves[move_cat] + loser_moves[move_cat] >= 20:  # Minimum sample
            print(f"{move_cat:<30} {w_pct:>10.1%} {l_pct:>10.1%} {diff:>+10.1%}")


if __name__ == "__main__":
    # First, print sample games for verification
    print_sample_games(5)

    # Then run pattern analysis
    analyze_patterns(500)

    # Compare winner vs loser patterns
    analyze_winning_vs_losing_patterns(500)
