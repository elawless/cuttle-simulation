#!/usr/bin/env python3
"""Pure simulation test: 8 as Glasses vs 8 as Points.

This test uses ISMCTS (Information Set MCTS) for both branches, which:
- Properly handles hidden information (samples opponent hands)
- When glasses is active, uses KNOWN opponent hand (no sampling)
- Has NO hard-coded heuristics about what to do with the information

The question: Does having perfect information about opponent's hand
actually lead to more wins, when both players play optimally?
"""

from __future__ import annotations

import argparse
import pickle
import random
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from cuttle_engine.cards import Rank
from cuttle_engine.executor import execute_move, IllegalMoveError
from cuttle_engine.move_generator import generate_legal_moves
from cuttle_engine.moves import PlayPermanent, PlayPoints
from cuttle_engine.state import GamePhase, GameState, create_initial_state
from strategies.ismcts import ISMCTSStrategy


def get_acting_player(state: GameState) -> int:
    if state.phase == GamePhase.COUNTER:
        return state.counter_state.waiting_for_player
    elif state.phase == GamePhase.DISCARD_FOUR:
        return state.four_state.player
    elif state.phase == GamePhase.RESOLVE_SEVEN:
        return state.seven_state.player
    return state.current_player


def find_eight_decision(state, moves):
    """Find 8-as-Points and 8-as-Glasses moves if both available."""
    points_move = glasses_move = None
    for m in moves:
        if isinstance(m, PlayPoints) and m.card.rank == Rank.EIGHT:
            points_move = m
        elif isinstance(m, PlayPermanent) and m.card.rank == Rank.EIGHT:
            glasses_move = m
    if points_move and glasses_move:
        return points_move, glasses_move
    return None


def play_game_with_ismcts(state: GameState, player: int, iterations: int, seed: int) -> tuple[bool, int]:
    """Play game to completion using ISMCTS for both players.

    Returns (player_won, moves_played).
    """
    # Create separate ISMCTS instances for each player
    strategies = [
        ISMCTSStrategy(iterations=iterations, seed=seed),
        ISMCTSStrategy(iterations=iterations, seed=seed + 1000),
    ]
    strategies[0].on_game_start(state, 0)
    strategies[1].on_game_start(state, 1)

    moves_played = 0
    max_moves = 300

    while not state.is_game_over and moves_played < max_moves:
        legal_moves = generate_legal_moves(state)
        if not legal_moves:
            break

        acting = get_acting_player(state)
        strategy = strategies[acting]

        try:
            move = strategy.select_move(state, legal_moves)
            state = execute_move(state, move)

            # Notify both strategies of the move
            for s in strategies:
                s.on_move_made(state, move, acting)

            moves_played += 1
        except (IllegalMoveError, Exception):
            break

    return state.winner == player, moves_played


def test_decision_point(state_pickle: bytes, player: int, iterations: int, seed: int) -> dict:
    """Test both branches from a decision point using pure ISMCTS."""
    state = pickle.loads(state_pickle)
    moves = generate_legal_moves(state)

    decision = find_eight_decision(state, moves)
    if not decision:
        return {"error": "Not at decision point"}

    points_move, glasses_move = decision
    opponent = 1 - player

    # Get context
    my_points = state.players[player].point_total
    opp_points = state.players[opponent].point_total
    opp_has_ace = any(c.rank == Rank.ACE for c in state.players[opponent].hand)

    try:
        # Branch A: Play 8 as Points
        state_points = execute_move(state, points_move)
        points_won, points_moves = play_game_with_ismcts(state_points, player, iterations, seed)

        # Branch B: Play 8 as Glasses
        state_glasses = execute_move(state, glasses_move)
        glasses_won, glasses_moves = play_game_with_ismcts(state_glasses, player, iterations, seed)

        return {
            "turn": state.turn_number,
            "player": player,
            "my_points": my_points,
            "opp_points": opp_points,
            "opp_has_ace": opp_has_ace,
            "points_won": points_won,
            "glasses_won": glasses_won,
        }
    except Exception as e:
        return {"error": str(e)}


def find_decision_points(num_needed: int, seed_start: int) -> list[tuple[bytes, int, int]]:
    """Find decision points by playing random games.

    Returns list of (pickled_state, player, seed).
    """
    decisions = []
    seed = seed_start

    while len(decisions) < num_needed:
        state = create_initial_state(seed=seed)
        rng = random.Random(seed)

        for _ in range(10):  # Max turns to search
            if state.is_game_over:
                break

            moves = generate_legal_moves(state)
            if not moves:
                break

            decision = find_eight_decision(state, moves)
            if decision:
                player = get_acting_player(state)
                decisions.append((pickle.dumps(state), player, seed))
                break

            # Random move to continue
            state = execute_move(state, rng.choice(moves))

        seed += 1

        if len(decisions) % 50 == 0 and len(decisions) > 0:
            print(f"  Found {len(decisions)} decision points...")

    return decisions[:num_needed]


def main():
    parser = argparse.ArgumentParser(
        description="Pure ISMCTS simulation: 8 as Glasses vs Points"
    )
    parser.add_argument("--decisions", type=int, default=100,
                        help="Number of decision points to test")
    parser.add_argument("--iterations", type=int, default=200,
                        help="ISMCTS iterations per move (higher = stronger play)")
    parser.add_argument("--workers", type=int, default=4,
                        help="Parallel workers")
    parser.add_argument("--seed", type=int, default=42,
                        help="Starting seed")

    args = parser.parse_args()

    print(f"Pure ISMCTS Simulation: 8 as Glasses vs Points")
    print(f"  Decision points: {args.decisions}")
    print(f"  ISMCTS iterations: {args.iterations}")
    print(f"  Workers: {args.workers}")
    print()

    # Find decision points
    print("Finding decision points...")
    decision_points = find_decision_points(args.decisions, args.seed)
    print(f"Found {len(decision_points)} decision points\n")

    # Test each decision point
    print("Running simulations...")
    results = []

    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        futures = [
            pool.submit(test_decision_point, state_pickle, player, args.iterations, seed)
            for state_pickle, player, seed in decision_points
        ]

        for i, future in enumerate(as_completed(futures)):
            try:
                result = future.result()
                results.append(result)
                if (i + 1) % 10 == 0:
                    print(f"  Completed {i + 1}/{len(decision_points)}")
            except Exception as e:
                print(f"  Error: {e}")

    # Analyze results
    valid = [r for r in results if "error" not in r]

    if not valid:
        print("No valid results!")
        return

    n = len(valid)
    points_wins = sum(1 for r in valid if r["points_won"])
    glasses_wins = sum(1 for r in valid if r["glasses_won"])

    glasses_better = sum(1 for r in valid if r["glasses_won"] and not r["points_won"])
    points_better = sum(1 for r in valid if r["points_won"] and not r["glasses_won"])
    same = n - glasses_better - points_better

    print(f"\n{'='*60}")
    print(f"PURE ISMCTS RESULTS (no heuristic biases)")
    print(f"{'='*60}")
    print(f"\nDecision points tested: {n}")
    print(f"\nWin rates:")
    print(f"  Points branch: {points_wins}/{n} ({100*points_wins/n:.1f}%)")
    print(f"  Glasses branch: {glasses_wins}/{n} ({100*glasses_wins/n:.1f}%)")

    print(f"\nContested outcomes:")
    print(f"  Glasses better: {glasses_better} ({100*glasses_better/n:.1f}%)")
    print(f"  Points better:  {points_better} ({100*points_better/n:.1f}%)")
    print(f"  Same outcome:   {same} ({100*same/n:.1f}%)")

    if glasses_better + points_better > 0:
        contested = glasses_better + points_better
        winner = "GLASSES" if glasses_better > points_better else "POINTS"
        margin = abs(glasses_better - points_better)
        print(f"\n  -> {winner} wins {margin} more contested ({100*margin/contested:.1f}% advantage)")

    # Breakdown by Ace presence
    with_ace = [r for r in valid if r["opp_has_ace"]]
    without_ace = [r for r in valid if not r["opp_has_ace"]]

    print(f"\n{'-'*60}")
    print(f"When opponent HAS Ace (n={len(with_ace)}):")
    if with_ace:
        p_w = sum(1 for r in with_ace if r["points_won"])
        g_w = sum(1 for r in with_ace if r["glasses_won"])
        g_b = sum(1 for r in with_ace if r["glasses_won"] and not r["points_won"])
        p_b = sum(1 for r in with_ace if r["points_won"] and not r["glasses_won"])
        print(f"  Points: {100*p_w/len(with_ace):.1f}%, Glasses: {100*g_w/len(with_ace):.1f}%")
        print(f"  Contested: Glasses +{g_b}, Points +{p_b}")

    print(f"\nWhen opponent has NO Ace (n={len(without_ace)}):")
    if without_ace:
        p_w = sum(1 for r in without_ace if r["points_won"])
        g_w = sum(1 for r in without_ace if r["glasses_won"])
        g_b = sum(1 for r in without_ace if r["glasses_won"] and not r["points_won"])
        p_b = sum(1 for r in without_ace if r["points_won"] and not r["glasses_won"])
        print(f"  Points: {100*p_w/len(without_ace):.1f}%, Glasses: {100*g_w/len(without_ace):.1f}%")
        print(f"  Contested: Glasses +{g_b}, Points +{p_b}")


if __name__ == "__main__":
    main()
