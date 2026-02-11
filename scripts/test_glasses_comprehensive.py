#!/usr/bin/env python3
"""Comprehensive glasses test: Measure value across ALL threat types.

Instead of just checking Ace, we measure how glasses performs when
opponent has various combinations of threats.
"""

import json
import sys
import pickle
import random
from datetime import datetime
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor, as_completed

sys.path.insert(0, str(Path(__file__).parent.parent))

from cuttle_engine.cards import Rank
from cuttle_engine.executor import execute_move, IllegalMoveError
from cuttle_engine.move_generator import generate_legal_moves
from cuttle_engine.moves import PlayPermanent, PlayPoints
from cuttle_engine.state import GamePhase, create_initial_state
from strategies.ismcts import ISMCTSStrategy


def get_acting_player(state):
    if state.phase == GamePhase.COUNTER:
        return state.counter_state.waiting_for_player
    elif state.phase == GamePhase.DISCARD_FOUR:
        return state.four_state.player
    elif state.phase == GamePhase.RESOLVE_SEVEN:
        return state.seven_state.player
    return state.current_player


def card_to_dict(card):
    """Convert card to serializable dict."""
    return {'rank': card.rank.value, 'suit': card.suit.value, 'str': str(card)}


def analyze_hand(hand):
    """Analyze a hand for threats and assets."""
    return {
        'cards': [card_to_dict(c) for c in hand],
        'ace': any(c.rank == Rank.ACE for c in hand),
        'two': any(c.rank == Rank.TWO for c in hand),
        'three': any(c.rank == Rank.THREE for c in hand),
        'four': any(c.rank == Rank.FOUR for c in hand),
        'five': any(c.rank == Rank.FIVE for c in hand),
        'six': any(c.rank == Rank.SIX for c in hand),
        'seven': any(c.rank == Rank.SEVEN for c in hand),
        'eight': any(c.rank == Rank.EIGHT for c in hand),
        'nine': any(c.rank == Rank.NINE for c in hand),
        'ten': any(c.rank == Rank.TEN for c in hand),
        'jack': any(c.rank == Rank.JACK for c in hand),
        'queen': any(c.rank == Rank.QUEEN for c in hand),
        'king': any(c.rank == Rank.KING for c in hand),
        'threat_count': sum(1 for c in hand if c.rank in (Rank.ACE, Rank.TWO, Rank.SIX, Rank.JACK, Rank.NINE, Rank.KING)),
    }


def analyze_threats(hand):
    """Analyze what threats are in a hand (legacy format for compatibility)."""
    return {
        'ace': any(c.rank == Rank.ACE for c in hand),
        'two': any(c.rank == Rank.TWO for c in hand),
        'six': any(c.rank == Rank.SIX for c in hand),
        'jack': any(c.rank == Rank.JACK for c in hand),
        'nine': any(c.rank == Rank.NINE for c in hand),
        'king': any(c.rank == Rank.KING for c in hand),
        'count': sum(1 for c in hand if c.rank in (Rank.ACE, Rank.TWO, Rank.SIX, Rank.JACK, Rank.NINE, Rank.KING)),
    }


def play_game_ismcts(state, player, iterations, seed):
    """Play game with ISMCTS, return winner == player."""
    strategies = [
        ISMCTSStrategy(iterations=iterations, seed=seed),
        ISMCTSStrategy(iterations=iterations, seed=seed + 1000),
    ]
    strategies[0].on_game_start(state, 0)
    strategies[1].on_game_start(state, 1)

    for _ in range(300):
        if state.is_game_over:
            break
        moves = generate_legal_moves(state)
        if not moves:
            break
        acting = get_acting_player(state)
        try:
            move = strategies[acting].select_move(state, moves)
            state = execute_move(state, move)
            for s in strategies:
                s.on_move_made(state, move, acting)
        except:
            break

    return state.winner == player


def test_point(data):
    """Test one decision point."""
    state = pickle.loads(data['state'])
    player = data['player']
    seed = data['seed']
    iterations = data['iterations']
    threats = data['threats']
    extra = data.get('extra', {})

    moves = generate_legal_moves(state)
    points_move = glasses_move = None
    for m in moves:
        if isinstance(m, PlayPoints) and m.card.rank == Rank.EIGHT:
            points_move = m
        elif isinstance(m, PlayPermanent) and m.card.rank == Rank.EIGHT:
            glasses_move = m

    if not points_move or not glasses_move:
        return None

    try:
        state_p = execute_move(state, points_move)
        points_won = play_game_ismcts(state_p, player, iterations, seed)

        state_g = execute_move(state, glasses_move)
        glasses_won = play_game_ismcts(state_g, player, iterations, seed)

        return {
            'seed': seed,
            'turn': state.turn_number,
            'player': player,
            'my_points': extra.get('my_points', 0),
            'opp_points': extra.get('opp_points', 0),
            'my_hand': extra.get('my_hand', {}),
            'opp_hand': extra.get('opp_hand', {}),
            'threats': threats,
            'points_won': points_won,
            'glasses_won': glasses_won,
        }
    except Exception as e:
        return None


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--decisions", type=int, default=200)
    parser.add_argument("--iterations", type=int, default=150)
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--output", type=str, default=None,
                        help="Output JSON file for training data (default: training_data/glasses_comprehensive_<timestamp>.json)")
    args = parser.parse_args()

    print(f"Comprehensive Glasses Test")
    print(f"  Decisions: {args.decisions}, ISMCTS iterations: {args.iterations}")
    print()

    # Find decision points
    print("Finding decision points...")
    decision_data = []
    seed = args.seed

    while len(decision_data) < args.decisions:
        state = create_initial_state(seed=seed)
        rng = random.Random(seed)

        for _ in range(10):
            if state.is_game_over:
                break
            moves = generate_legal_moves(state)
            if not moves:
                break

            has_8 = False
            for m in moves:
                if isinstance(m, PlayPoints) and m.card.rank == Rank.EIGHT:
                    for m2 in moves:
                        if isinstance(m2, PlayPermanent) and m2.card.rank == Rank.EIGHT:
                            has_8 = True
                            break
                if has_8:
                    break

            if has_8:
                player = get_acting_player(state)
                opponent = 1 - player
                threats = analyze_threats(state.players[opponent].hand)

                # Capture detailed state for analysis
                my_hand = analyze_hand(state.players[player].hand)
                opp_hand = analyze_hand(state.players[opponent].hand)

                decision_data.append({
                    'state': pickle.dumps(state),
                    'player': player,
                    'seed': seed,
                    'iterations': args.iterations,
                    'threats': threats,
                    'extra': {
                        'my_points': state.players[player].point_total,
                        'opp_points': state.players[opponent].point_total,
                        'my_hand': my_hand,
                        'opp_hand': opp_hand,
                    }
                })
                break

            state = execute_move(state, rng.choice(moves))

        seed += 1
        if len(decision_data) % 50 == 0 and decision_data:
            print(f"  Found {len(decision_data)}...")

    print(f"Found {len(decision_data)} decision points\n")

    # Run tests
    print("Running simulations...")
    results = []

    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        futures = [pool.submit(test_point, d) for d in decision_data]
        for i, f in enumerate(as_completed(futures)):
            r = f.result()
            if r:
                results.append(r)
            if (i + 1) % 20 == 0:
                print(f"  Completed {i+1}/{len(decision_data)}")

    # Analyze
    print(f"\n{'='*70}")
    print("COMPREHENSIVE RESULTS")
    print(f"{'='*70}")

    n = len(results)
    p_wins = sum(1 for r in results if r['points_won'])
    g_wins = sum(1 for r in results if r['glasses_won'])
    g_better = sum(1 for r in results if r['glasses_won'] and not r['points_won'])
    p_better = sum(1 for r in results if r['points_won'] and not r['glasses_won'])

    print(f"\nOverall (n={n}):")
    print(f"  Points: {100*p_wins/n:.1f}%, Glasses: {100*g_wins/n:.1f}%")
    print(f"  Contested: Points +{p_better}, Glasses +{g_better}")

    # By threat count
    print(f"\n{'-'*70}")
    print("By THREAT COUNT (Ace, Two, Six, Jack, Nine, King):")

    for count in [0, 1, 2, 3, 4]:
        if count == 4:
            subset = [r for r in results if r['threats']['count'] >= 4]
            label = "4+"
        else:
            subset = [r for r in results if r['threats']['count'] == count]
            label = str(count)

        if len(subset) >= 5:
            sn = len(subset)
            sp = sum(1 for r in subset if r['points_won'])
            sg = sum(1 for r in subset if r['glasses_won'])
            sgb = sum(1 for r in subset if r['glasses_won'] and not r['points_won'])
            spb = sum(1 for r in subset if r['points_won'] and not r['glasses_won'])

            winner = "GLASSES" if sgb > spb else "POINTS" if spb > sgb else "TIE"
            margin = abs(sgb - spb)

            print(f"  {label} threats (n={sn:3d}): Points {100*sp/sn:5.1f}%, Glasses {100*sg/sn:5.1f}% | Contested: {winner} +{margin}")

    # By specific threat type
    print(f"\n{'-'*70}")
    print("By SPECIFIC THREAT:")

    for threat_name, threat_key in [
        ("Ace (wipe)", "ace"),
        ("Two (counter)", "two"),
        ("Jack (steal)", "jack"),
        ("Six (destroy)", "six"),
        ("King (threshold)", "king"),
    ]:
        has_threat = [r for r in results if r['threats'][threat_key]]
        no_threat = [r for r in results if not r['threats'][threat_key]]

        if len(has_threat) >= 10:
            sn = len(has_threat)
            sp = sum(1 for r in has_threat if r['points_won'])
            sg = sum(1 for r in has_threat if r['glasses_won'])
            sgb = sum(1 for r in has_threat if r['glasses_won'] and not r['points_won'])
            spb = sum(1 for r in has_threat if r['points_won'] and not r['glasses_won'])

            winner = "G" if sgb > spb else "P" if spb > sgb else "="

            print(f"  Has {threat_name:15s} (n={sn:3d}): P {100*sp/sn:5.1f}%, G {100*sg/sn:5.1f}% | {winner} +{abs(sgb-spb)}")

    # Save to training file
    output_dir = Path(__file__).parent.parent / "training_data"
    output_dir.mkdir(exist_ok=True)

    if args.output:
        output_path = Path(args.output)
    else:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = output_dir / f"glasses_comprehensive_{args.iterations}iter_{timestamp}.json"

    # Prepare summary statistics
    summary = {
        'metadata': {
            'timestamp': datetime.now().isoformat(),
            'decisions': args.decisions,
            'iterations': args.iterations,
            'seed': args.seed,
            'valid_results': n,
        },
        'overall': {
            'points_wins': p_wins,
            'glasses_wins': g_wins,
            'points_win_rate': p_wins / n if n > 0 else 0,
            'glasses_win_rate': g_wins / n if n > 0 else 0,
            'points_better_contested': p_better,
            'glasses_better_contested': g_better,
        },
        'by_threat_count': {},
        'by_specific_threat': {},
        'raw_results': results,
    }

    # Add threat count breakdown
    for count in [0, 1, 2, 3, 4]:
        if count == 4:
            subset = [r for r in results if r['threats']['count'] >= 4]
            label = "4+"
        else:
            subset = [r for r in results if r['threats']['count'] == count]
            label = str(count)

        if len(subset) >= 1:
            sn = len(subset)
            sp = sum(1 for r in subset if r['points_won'])
            sg = sum(1 for r in subset if r['glasses_won'])
            sgb = sum(1 for r in subset if r['glasses_won'] and not r['points_won'])
            spb = sum(1 for r in subset if r['points_won'] and not r['glasses_won'])

            summary['by_threat_count'][label] = {
                'n': sn,
                'points_wins': sp,
                'glasses_wins': sg,
                'points_better': spb,
                'glasses_better': sgb,
            }

    # Add specific threat breakdown
    for threat_name, threat_key in [
        ("ace", "ace"), ("two", "two"), ("jack", "jack"),
        ("six", "six"), ("nine", "nine"), ("king", "king"),
    ]:
        has_threat = [r for r in results if r['threats'][threat_key]]
        if len(has_threat) >= 1:
            sn = len(has_threat)
            sp = sum(1 for r in has_threat if r['points_won'])
            sg = sum(1 for r in has_threat if r['glasses_won'])
            sgb = sum(1 for r in has_threat if r['glasses_won'] and not r['points_won'])
            spb = sum(1 for r in has_threat if r['points_won'] and not r['glasses_won'])

            summary['by_specific_threat'][threat_name] = {
                'n': sn,
                'points_wins': sp,
                'glasses_wins': sg,
                'points_better': spb,
                'glasses_better': sgb,
            }

    with open(output_path, 'w') as f:
        json.dump(summary, f, indent=2)

    print(f"\n{'='*70}")
    print(f"Results saved to: {output_path}")


if __name__ == "__main__":
    main()
