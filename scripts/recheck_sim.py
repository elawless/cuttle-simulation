"""Recheck simulation outcomes."""

from cuttle_engine.state import create_initial_state
from cuttle_engine.move_generator import generate_legal_moves
from cuttle_engine.executor import execute_move, IllegalMoveError
from strategies.mcts import MCTSStrategy


def recheck_simulations():
    """Recheck simulation behavior exactly as MCTS does it."""
    mcts = MCTSStrategy(iterations=1, seed=42, max_simulation_depth=200)

    p0_wins = 0
    p1_wins = 0
    other = 0

    for i in range(100):
        state = create_initial_state(seed=i)

        # Run simulation exactly as MCTS does
        result = mcts._simulate(state, perspective_player=0)

        if result == 1.0:
            p0_wins += 1
        elif result == 0.0:
            p1_wins += 1
        else:
            other += 1

    print(f"MCTS._simulate from fresh initial state, perspective=0:")
    print(f"  P0 wins (result=1.0): {p0_wins}")
    print(f"  P1 wins (result=0.0): {p1_wins}")
    print(f"  Other: {other}")


def check_perspective_0_vs_1():
    """Check if perspective matters in simulation."""
    mcts = MCTSStrategy(iterations=1, seed=42, max_simulation_depth=200)

    same_winner = 0
    diff_winner = 0

    for i in range(100):
        state = create_initial_state(seed=i)

        # Run simulation with perspective=0
        result_p0 = mcts._simulate(state, perspective_player=0)

        # Run DIFFERENT simulation (different random choices) with perspective=1
        # These won't match because they're independent simulations
        result_p1 = mcts._simulate(state, perspective_player=1)

        # Both results are from different games, but should show similar distributions
        print(f"Seed {i}: result_p0={result_p0}, result_p1={result_p1}")


def check_mcts_rng_state():
    """Check if MCTS simulation RNG state persists."""
    mcts = MCTSStrategy(iterations=1, seed=42)

    state = create_initial_state(seed=0)

    # Run several simulations
    results = []
    for i in range(10):
        r = mcts._simulate(state, perspective_player=0)
        results.append(r)

    print(f"10 simulations from same state: {results}")
    print(f"All same? {len(set(results)) == 1}")


if __name__ == "__main__":
    recheck_simulations()
    print()
    check_mcts_rng_state()
