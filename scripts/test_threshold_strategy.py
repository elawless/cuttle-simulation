"""Test the 'play X+ for points, otherwise draw' strategy threshold."""

from collections import defaultdict
from cuttle_engine.state import create_initial_state, GamePhase
from cuttle_engine.move_generator import generate_legal_moves
from cuttle_engine.executor import execute_move, IllegalMoveError
from cuttle_engine.cards import Rank
from cuttle_engine.moves import PlayPoints, Draw
from strategies.random_strategy import RandomStrategy


def analyze_threshold_from_data():
    """Analyze what the optimal point threshold is from 100k data."""
    import json

    with open('analysis_output/deep_analysis_100k.json') as f:
        data = json.load(f)

    print("=" * 60)
    print("POINT CARD WIN RATES vs DRAW")
    print("=" * 60)
    print(f"{'Card':<15} {'Win Rate':>10} {'vs Draw':>12} {'Count':>10}")
    print("-" * 50)

    draw_rate = data['move_stats']['Draw']['wins'] / data['move_stats']['Draw']['count']
    print(f"{'Draw':<15} {draw_rate:>10.1%} {'baseline':>12} {data['move_stats']['Draw']['count']:>10}")
    print()

    ranks = ['TEN', 'NINE', 'EIGHT', 'SEVEN', 'SIX', 'FIVE', 'FOUR', 'THREE', 'TWO', 'ACE']
    point_values = {'TEN': 10, 'NINE': 9, 'EIGHT': 8, 'SEVEN': 7, 'SIX': 6,
                    'FIVE': 5, 'FOUR': 4, 'THREE': 3, 'TWO': 2, 'ACE': 1}

    for rank in ranks:
        key = f'PlayPoints_{rank}'
        if key in data['move_stats']:
            stats = data['move_stats'][key]
            rate = stats['wins'] / stats['count']
            diff = rate - draw_rate
            marker = "✓ PLAY" if rate > draw_rate else "✗ DRAW"
            print(f"{rank:<15} {rate:>10.1%} {diff:>+11.1%} {stats['count']:>10}  {marker}")

    print()
    print("=" * 60)
    print("OPTIMAL STRATEGY THRESHOLDS")
    print("=" * 60)

    # Find the threshold
    for rank in ranks:
        key = f'PlayPoints_{rank}'
        if key in data['move_stats']:
            stats = data['move_stats'][key]
            rate = stats['wins'] / stats['count']
            if rate <= draw_rate:
                print(f"\nThreshold: Play {point_values[ranks[ranks.index(rank)-1]]}+ for points")
                print(f"           {rank} and below -> better to draw")
                break

    # Now let's look at what ELSE you might do
    print()
    print("=" * 60)
    print("OTHER MOVES vs DRAW")
    print("=" * 60)

    other_moves = [
        ('PlayPermanent_JACK', 'Jack (steal points)'),
        ('PlayPermanent_KING', 'King (reduce threshold)'),
        ('PlayOneOff_SEVEN', 'Seven one-off (play from deck)'),
        ('PlayOneOff_FIVE', 'Five one-off (draw 2)'),
        ('Counter', 'Counter'),
        ('Scuttle', 'Scuttle'),
        ('PlayPermanent_QUEEN', 'Queen (protection)'),
        ('PlayPermanent_EIGHT', 'Eight (glasses)'),
    ]

    print(f"{'Move':<30} {'Win Rate':>10} {'vs Draw':>10}")
    print("-" * 55)

    for key, name in other_moves:
        if key in data['move_stats']:
            stats = data['move_stats'][key]
            rate = stats['wins'] / stats['count']
            diff = rate - draw_rate
            marker = "✓" if rate > draw_rate else "✗"
            print(f"{name:<30} {rate:>10.1%} {diff:>+10.1%} {marker}")


def simulate_threshold_strategies(num_games=5000):
    """Simulate what happens when players follow threshold strategies."""
    print()
    print("=" * 60)
    print(f"SIMULATING THRESHOLD STRATEGIES ({num_games} games each)")
    print("=" * 60)

    # We'll track: for each decision point, what was the outcome?
    # Decision: had a choice between playing N points or drawing

    thresholds_to_test = [4, 5, 6, 7, 8]

    for threshold in thresholds_to_test:
        # Track decisions at this threshold
        played_at_threshold = {"count": 0, "won": 0}  # Played a card at exactly threshold
        drew_with_threshold = {"count": 0, "won": 0}  # Drew when had threshold card

        for seed in range(num_games):
            state = create_initial_state(seed=seed)
            strategy = RandomStrategy(seed=seed * 2)

            decisions = []  # Track threshold decisions this game

            turn = 0
            while not state.is_game_over and turn < 500:
                if state.phase == GamePhase.COUNTER:
                    acting = state.counter_state.waiting_for_player
                elif state.phase == GamePhase.DISCARD_FOUR:
                    acting = state.four_state.player
                elif state.phase == GamePhase.RESOLVE_SEVEN:
                    acting = state.seven_state.player
                else:
                    acting = state.current_player

                legal_moves = generate_legal_moves(state)
                if not legal_moves:
                    break

                move = strategy.select_move(state, legal_moves)

                # Check if this was a threshold decision
                can_draw = any(isinstance(m, Draw) for m in legal_moves)
                point_moves = [m for m in legal_moves if isinstance(m, PlayPoints)]
                has_threshold_card = any(m.card.point_value == threshold for m in point_moves)

                if can_draw and has_threshold_card:
                    if isinstance(move, PlayPoints) and move.card.point_value == threshold:
                        decisions.append(("played", acting))
                    elif isinstance(move, Draw):
                        decisions.append(("drew", acting))

                try:
                    state = execute_move(state, move)
                except IllegalMoveError:
                    break

                turn += 1

            winner = state.winner
            for decision, player in decisions:
                won = (winner == player)
                if decision == "played":
                    played_at_threshold["count"] += 1
                    if won:
                        played_at_threshold["won"] += 1
                else:
                    drew_with_threshold["count"] += 1
                    if won:
                        drew_with_threshold["won"] += 1

        # Report
        if played_at_threshold["count"] > 0 and drew_with_threshold["count"] > 0:
            play_rate = played_at_threshold["won"] / played_at_threshold["count"]
            draw_rate = drew_with_threshold["won"] / drew_with_threshold["count"]
            print(f"\nThreshold = {threshold}:")
            print(f"  Played {threshold}-point card: {played_at_threshold['count']:>6} times, {play_rate:.1%} win rate")
            print(f"  Drew (had {threshold}):        {drew_with_threshold['count']:>6} times, {draw_rate:.1%} win rate")
            print(f"  Better to: {'PLAY' if play_rate > draw_rate else 'DRAW'} ({abs(play_rate-draw_rate):.1%} difference)")


if __name__ == "__main__":
    analyze_threshold_from_data()
    simulate_threshold_strategies(10000)
