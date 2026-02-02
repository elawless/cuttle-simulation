"""Command-line interface for Cuttle."""

from __future__ import annotations

import argparse
import sys
from typing import TYPE_CHECKING

from cuttle_engine.cards import Card
from cuttle_engine.executor import execute_move
from cuttle_engine.move_generator import generate_legal_moves
from cuttle_engine.state import GamePhase, create_initial_state

if TYPE_CHECKING:
    from cuttle_engine.moves import Move
    from cuttle_engine.state import GameState


def format_state(state: GameState, show_opponent_hand: bool = False) -> str:
    """Format game state for display."""
    lines = []

    lines.append("=" * 60)
    lines.append(f"Turn {state.turn_number} | Phase: {state.phase.name}")
    lines.append("=" * 60)

    for i, player in enumerate(state.players):
        prefix = "→ " if i == state.current_player else "  "
        threshold = state.point_threshold(i)

        lines.append(f"\n{prefix}Player {i} ({player.point_total}/{threshold} points)")
        lines.append("-" * 40)

        # Hand (hide opponent's unless glasses or show_opponent_hand)
        if i == state.current_player or show_opponent_hand:
            hand_str = ", ".join(str(c) for c in player.hand) or "(empty)"
            lines.append(f"  Hand: {hand_str}")
        else:
            opponent_has_glasses = state.players[state.current_player].has_glasses
            if opponent_has_glasses:
                hand_str = ", ".join(str(c) for c in player.hand) or "(empty)"
                lines.append(f"  Hand: {hand_str} (visible - Glasses)")
            else:
                lines.append(f"  Hand: [{len(player.hand)} cards]")

        # Points field
        points_str = ", ".join(str(c) for c in player.points_field) or "(none)"
        lines.append(f"  Points: {points_str}")

        # Permanents
        if player.permanents:
            perm_str = ", ".join(str(c) for c in player.permanents)
            lines.append(f"  Permanents: {perm_str}")

        # Jacks
        if player.jacks:
            jack_str = ", ".join(f"{j}→{s}" for j, s in player.jacks)
            lines.append(f"  Jacks: {jack_str}")

    # Deck and scrap
    lines.append(f"\nDeck: {len(state.deck)} cards | Scrap: {len(state.scrap)} cards")

    if state.is_game_over:
        lines.append("\n" + "=" * 60)
        lines.append(f"GAME OVER - Player {state.winner} wins! ({state.win_reason.name})")
        lines.append("=" * 60)

    return "\n".join(lines)


def format_moves(moves: list[Move]) -> str:
    """Format available moves for display."""
    lines = ["Available moves:"]
    for i, move in enumerate(moves):
        lines.append(f"  {i + 1}. {move}")
    return "\n".join(lines)


def play_interactive(seed: int | None = None) -> None:
    """Play an interactive game against random AI."""
    from strategies.random_strategy import RandomStrategy

    ai = RandomStrategy(seed=seed)
    state = create_initial_state(seed=seed)

    print("\nWelcome to Cuttle!")
    print("You are Player 0. Type the number of a move to play.")
    print("Type 'q' to quit.\n")

    while not state.is_game_over:
        print(format_state(state))

        # Determine who acts
        if state.phase == GamePhase.COUNTER:
            acting_player = state.counter_state.waiting_for_player
        elif state.phase == GamePhase.DISCARD_FOUR:
            acting_player = state.four_state.player
        elif state.phase == GamePhase.RESOLVE_SEVEN:
            acting_player = state.seven_state.player
        else:
            acting_player = state.current_player

        legal_moves = generate_legal_moves(state)

        if acting_player == 0:
            # Human's turn
            print(f"\n{format_moves(legal_moves)}")

            while True:
                try:
                    choice = input("\nYour move: ").strip()
                    if choice.lower() == "q":
                        print("Goodbye!")
                        return

                    move_idx = int(choice) - 1
                    if 0 <= move_idx < len(legal_moves):
                        move = legal_moves[move_idx]
                        break
                    else:
                        print(f"Please enter a number 1-{len(legal_moves)}")
                except ValueError:
                    print("Please enter a valid number or 'q' to quit")
        else:
            # AI's turn
            move = ai.select_move(state, legal_moves)
            print(f"\nAI plays: {move}")

        state = execute_move(state, move)
        print()

    print(format_state(state))


def watch_game(seed: int | None = None, delay: float = 0.5) -> None:
    """Watch two AIs play against each other."""
    import time

    from strategies.heuristic import HeuristicStrategy
    from strategies.random_strategy import RandomStrategy

    strategy0 = HeuristicStrategy(seed=seed)
    strategy1 = RandomStrategy(seed=seed)
    state = create_initial_state(seed=seed)

    print("\nWatching: Heuristic vs Random")
    print("Press Ctrl+C to stop.\n")

    try:
        while not state.is_game_over:
            print(format_state(state, show_opponent_hand=True))

            # Determine who acts
            if state.phase == GamePhase.COUNTER:
                acting_player = state.counter_state.waiting_for_player
            elif state.phase == GamePhase.DISCARD_FOUR:
                acting_player = state.four_state.player
            elif state.phase == GamePhase.RESOLVE_SEVEN:
                acting_player = state.seven_state.player
            else:
                acting_player = state.current_player

            legal_moves = generate_legal_moves(state)
            strategy = strategy0 if acting_player == 0 else strategy1
            move = strategy.select_move(state, legal_moves)

            print(f"\nPlayer {acting_player} ({strategy.name}) plays: {move}")
            state = execute_move(state, move)

            time.sleep(delay)
            print("\n" + "-" * 60 + "\n")

    except KeyboardInterrupt:
        print("\nStopped.")

    print(format_state(state, show_opponent_hand=True))


def run_tournament(num_games: int = 100, seed: int = 42) -> None:
    """Run a tournament between strategies."""
    from simulation.runner import run_batch
    from strategies.heuristic import HeuristicStrategy
    from strategies.random_strategy import RandomStrategy

    print(f"\nRunning {num_games} games: Random vs Random")

    strategy0 = RandomStrategy(seed=seed)
    strategy1 = RandomStrategy(seed=seed + 1000)

    results = run_batch(strategy0, strategy1, num_games, start_seed=seed, log_moves=False)

    p0_wins = sum(1 for r in results if r.winner == 0)
    p1_wins = sum(1 for r in results if r.winner == 1)
    draws = sum(1 for r in results if r.winner is None)
    avg_turns = sum(r.turns for r in results) / len(results)
    avg_duration = sum(r.duration_ms for r in results) / len(results)

    print(f"\nResults (Random vs Random):")
    print(f"  Player 0 wins: {p0_wins} ({100*p0_wins/num_games:.1f}%)")
    print(f"  Player 1 wins: {p1_wins} ({100*p1_wins/num_games:.1f}%)")
    print(f"  Draws: {draws} ({100*draws/num_games:.1f}%)")
    print(f"  Average turns: {avg_turns:.1f}")
    print(f"  Average duration: {avg_duration:.2f}ms")

    print(f"\nRunning {num_games} games: Heuristic vs Random")

    strategy0 = HeuristicStrategy(seed=seed)
    strategy1 = RandomStrategy(seed=seed + 1000)

    results = run_batch(strategy0, strategy1, num_games, start_seed=seed, log_moves=False)

    p0_wins = sum(1 for r in results if r.winner == 0)
    p1_wins = sum(1 for r in results if r.winner == 1)
    draws = sum(1 for r in results if r.winner is None)
    avg_turns = sum(r.turns for r in results) / len(results)

    print(f"\nResults (Heuristic vs Random):")
    print(f"  Heuristic wins: {p0_wins} ({100*p0_wins/num_games:.1f}%)")
    print(f"  Random wins: {p1_wins} ({100*p1_wins/num_games:.1f}%)")
    print(f"  Draws: {draws} ({100*draws/num_games:.1f}%)")
    print(f"  Average turns: {avg_turns:.1f}")


def main() -> None:
    """Main entry point for the CLI."""
    parser = argparse.ArgumentParser(description="Cuttle card game simulator")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Play command
    play_parser = subparsers.add_parser("play", help="Play against AI")
    play_parser.add_argument("--seed", type=int, help="Random seed")

    # Watch command
    watch_parser = subparsers.add_parser("watch", help="Watch AI vs AI")
    watch_parser.add_argument("--seed", type=int, help="Random seed")
    watch_parser.add_argument(
        "--delay", type=float, default=0.5, help="Delay between moves (seconds)"
    )

    # Tournament command
    tournament_parser = subparsers.add_parser("tournament", help="Run tournament")
    tournament_parser.add_argument(
        "--games", type=int, default=100, help="Number of games"
    )
    tournament_parser.add_argument("--seed", type=int, default=42, help="Random seed")

    args = parser.parse_args()

    if args.command == "play":
        play_interactive(seed=args.seed)
    elif args.command == "watch":
        watch_game(seed=args.seed, delay=args.delay)
    elif args.command == "tournament":
        run_tournament(num_games=args.games, seed=args.seed)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
