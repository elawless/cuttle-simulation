"""Investigate why simulation rollouts differ from actual game results."""

from cuttle_engine.state import create_initial_state
from cuttle_engine.move_generator import generate_legal_moves
from cuttle_engine.executor import execute_move
from strategies.random_strategy import RandomStrategy


def compare_rollout_methods():
    """Compare two ways of running random games."""
    print("Comparing rollout methods from same initial state")

    # Method 1: Using GameRunner (what actual games use)
    from simulation.runner import GameRunner

    runner_results = {"p0": 0, "p1": 0, "draw": 0}
    for seed in range(100):
        strategy0 = RandomStrategy(seed=seed * 2)
        strategy1 = RandomStrategy(seed=seed * 2 + 1)
        runner = GameRunner(strategy0, strategy1, log_moves=False)
        result, _ = runner.run_game(seed=seed)
        if result.winner == 0:
            runner_results["p0"] += 1
        elif result.winner == 1:
            runner_results["p1"] += 1
        else:
            runner_results["draw"] += 1

    print(f"GameRunner results: {runner_results}")

    # Method 2: Manual rollout (what MCTS simulations use)
    from cuttle_engine.executor import IllegalMoveError

    manual_results = {"p0": 0, "p1": 0, "draw": 0, "aborted": 0}
    for seed in range(100):
        state = create_initial_state(seed=seed)
        sim_strategy = RandomStrategy(seed=seed * 2)
        aborted = False

        while not state.is_game_over:
            moves = generate_legal_moves(state)
            if not moves:
                break
            move = sim_strategy.select_move(state, moves)
            try:
                state = execute_move(state, move)
            except IllegalMoveError:
                aborted = True
                break

        if aborted:
            manual_results["aborted"] += 1
        elif state.winner == 0:
            manual_results["p0"] += 1
        elif state.winner == 1:
            manual_results["p1"] += 1
        else:
            manual_results["draw"] += 1

    print(f"Manual rollout results: {manual_results}")


def check_if_same_strategy_used():
    """Check if MCTS simulations use separate strategies for each player."""
    # In MCTS._simulate, it uses self._simulation_strategy for ALL moves
    # This is a single RandomStrategy instance

    # Let's see what happens when one strategy plays both sides
    print("\nSingle strategy playing both sides:")
    for seed in range(5):
        state = create_initial_state(seed=seed)
        sim_strategy = RandomStrategy(seed=seed)

        moves = []
        turn = 0
        while not state.is_game_over and turn < 50:
            legal_moves = generate_legal_moves(state)
            if not legal_moves:
                break

            # Check which player is acting
            from cuttle_engine.state import GamePhase
            if state.phase == GamePhase.COUNTER:
                acting = state.counter_state.waiting_for_player
            elif state.phase == GamePhase.DISCARD_FOUR:
                acting = state.four_state.player
            elif state.phase == GamePhase.RESOLVE_SEVEN:
                acting = state.seven_state.player
            else:
                acting = state.current_player

            move = sim_strategy.select_move(state, legal_moves)
            moves.append((turn, acting, str(move)[:30]))

            state = execute_move(state, move)
            turn += 1

        print(f"Seed {seed}: Winner={state.winner}, Turns={turn}")
        print(f"  First 5 moves: {moves[:5]}")


def analyze_state_difference():
    """Check if there's hidden state affecting random choices."""
    print("\nAnalyzing state in RandomStrategy:")

    # Create two random strategies with same seed
    r1 = RandomStrategy(seed=42)
    r2 = RandomStrategy(seed=42)

    state = create_initial_state(seed=0)
    moves = generate_legal_moves(state)

    # Both should pick the same move
    m1 = r1.select_move(state, moves)
    m2 = r2.select_move(state, moves)
    print(f"Same seed, same state: m1={m1}, m2={m2}, same={m1==m2}")

    # Now pick again - they should still match
    m1b = r1.select_move(state, moves)
    m2b = r2.select_move(state, moves)
    print(f"Second pick: m1b={m1b}, m2b={m2b}, same={m1b==m2b}")
    print(f"m1==m1b: {m1==m1b} (different because RNG advanced)")


if __name__ == "__main__":
    compare_rollout_methods()
    check_if_same_strategy_used()
    analyze_state_difference()
