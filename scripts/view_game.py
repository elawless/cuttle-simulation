#!/usr/bin/env python3
"""View a specific game by seed number.

Usage:
    python scripts/view_game.py 42        # View game with seed 42
    python scripts/view_game.py 100-105   # View games 100 through 105
    python scripts/view_game.py random    # View a random game
"""

import sys
import random
from cuttle_engine.state import create_initial_state, GamePhase
from cuttle_engine.move_generator import generate_legal_moves
from cuttle_engine.executor import execute_move, IllegalMoveError
from strategies.random_strategy import RandomStrategy


def view_game(seed, detailed=True):
    """Run and display a single game."""
    state = create_initial_state(seed=seed)
    strategy = RandomStrategy(seed=seed * 2)

    print("=" * 70)
    print(f"GAME SEED: {seed}")
    print("=" * 70)

    if detailed:
        print(f"\nInitial hands:")
        print(f"  P0: {', '.join(str(c) for c in state.players[0].hand)}")
        print(f"  P1: {', '.join(str(c) for c in state.players[1].hand)}")
        print(f"  Deck: {len(state.deck)} cards")
        print()

    turn = 0
    while not state.is_game_over and turn < 500:
        # Determine acting player
        if state.phase == GamePhase.COUNTER:
            acting = state.counter_state.waiting_for_player
            phase_info = " [COUNTER]"
        elif state.phase == GamePhase.DISCARD_FOUR:
            acting = state.four_state.player
            phase_info = " [DISCARD]"
        elif state.phase == GamePhase.RESOLVE_SEVEN:
            acting = state.seven_state.player
            phase_info = " [SEVEN]"
        else:
            acting = state.current_player
            phase_info = ""

        moves = generate_legal_moves(state)
        if not moves:
            print("NO LEGAL MOVES - game stuck")
            break

        move = strategy.select_move(state, moves)

        # Score before move
        p0_pts = state.players[0].point_total
        p1_pts = state.players[1].point_total

        # Display move
        print(f"T{turn:02d} P{acting}{phase_info}: {str(move):<55} [{p0_pts:2d}-{p1_pts:2d}]")

        if detailed:
            # Show hand before move
            hand = state.players[acting].hand
            print(f"     Hand: {', '.join(str(c) for c in hand)}")

            # Show legal move count
            print(f"     ({len(moves)} legal moves available)")

        try:
            state = execute_move(state, move)
        except IllegalMoveError as e:
            print(f"     ERROR: {e}")
            print("\nGAME ABORTED DUE TO ERROR")
            return

        turn += 1

    # Game over
    print()
    print("=" * 70)
    print("GAME OVER")
    print("=" * 70)
    print(f"Winner: P{state.winner}")
    print(f"Final score: {state.players[0].point_total} - {state.players[1].point_total}")
    print(f"Reason: {state.win_reason}")
    print(f"Turns: {turn}")

    if detailed:
        print(f"\nFinal board state:")
        for i in range(2):
            p = state.players[i]
            print(f"  P{i}:")
            print(f"    Hand: {', '.join(str(c) for c in p.hand) or '(empty)'}")
            print(f"    Points: {', '.join(str(c) for c in p.points_field) or '(none)'} = {p.point_total}")
            print(f"    Permanents: {', '.join(str(c) for c in p.permanents) or '(none)'}")

    print()


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    arg = sys.argv[1]

    # Check for detailed flag
    detailed = "--detailed" in sys.argv or "-d" in sys.argv

    if arg == "random":
        seed = random.randint(0, 100000)
        view_game(seed, detailed=True)
    elif "-" in arg and arg[0].isdigit():
        # Range: e.g., "100-105"
        start, end = map(int, arg.split("-"))
        for seed in range(start, end + 1):
            view_game(seed, detailed=False)
    else:
        # Single seed
        seed = int(arg)
        view_game(seed, detailed=True)


if __name__ == "__main__":
    main()
