"""Trace simulation outcomes to understand rollout behavior."""

from cuttle_engine.state import create_initial_state
from cuttle_engine.move_generator import generate_legal_moves
from cuttle_engine.executor import execute_move
from strategies.mcts import MCTSStrategy


def analyze_simulations():
    """Analyze what happens during simulations."""
    state = create_initial_state(seed=42)
    mcts = MCTSStrategy(iterations=1, seed=42, max_simulation_depth=200)

    print("Analyzing 100 simulations from initial state")

    outcomes = {"p0_win": 0, "p1_win": 0, "draw": 0, "depth_limit": 0, "aborted": 0}
    depths = []

    for i in range(100):
        # Manually run simulation and track depth
        current_state = state
        depth = 0

        while not current_state.is_game_over and depth < 200:
            moves = generate_legal_moves(current_state)
            if not moves:
                break

            move = mcts._simulation_strategy.select_move(current_state, moves)
            try:
                current_state = execute_move(current_state, move)
            except Exception:
                outcomes["aborted"] += 1
                break
            depth += 1

        depths.append(depth)

        if current_state.is_game_over:
            if current_state.winner == 0:
                outcomes["p0_win"] += 1
            elif current_state.winner == 1:
                outcomes["p1_win"] += 1
            else:
                outcomes["draw"] += 1
        elif depth >= 200:
            outcomes["depth_limit"] += 1

    print(f"Outcomes: {outcomes}")
    print(f"Average depth: {sum(depths)/len(depths):.1f}")
    print(f"Min depth: {min(depths)}, Max depth: {max(depths)}")


def test_random_vs_random():
    """Run games between two random players to establish baseline."""
    from simulation.runner import run_batch
    from strategies.random_strategy import RandomStrategy

    print("\nRandom vs Random (to establish variance baseline):")
    results = run_batch(RandomStrategy(), RandomStrategy(), 100)
    p0_wins = sum(1 for r in results if r.winner == 0)
    print(f"Player 0 (goes first) wins: {p0_wins}/100")


def test_first_player_advantage():
    """Check if there's a first-player advantage affecting results."""
    from simulation.runner import run_batch
    from strategies.mcts import MCTSStrategy
    from strategies.random_strategy import RandomStrategy

    print("\nChecking for first-player bias:")

    # MCTS as player 0 vs Random as player 1
    results_p0 = run_batch(MCTSStrategy(200), RandomStrategy(), 30)
    mcts_wins_as_p0 = sum(1 for r in results_p0 if r.winner == 0)
    print(f"MCTS(200) as P0 vs Random as P1: MCTS wins {mcts_wins_as_p0}/30")

    # Random as player 0 vs MCTS as player 1
    results_p1 = run_batch(RandomStrategy(), MCTSStrategy(200), 30)
    mcts_wins_as_p1 = sum(1 for r in results_p1 if r.winner == 1)
    print(f"Random as P0 vs MCTS(200) as P1: MCTS wins {mcts_wins_as_p1}/30")


if __name__ == "__main__":
    analyze_simulations()
    test_random_vs_random()
    test_first_player_advantage()
