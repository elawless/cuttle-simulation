"""Trace through one MCTS iteration to debug perspective issues."""

from cuttle_engine.state import create_initial_state
from cuttle_engine.move_generator import generate_legal_moves
from cuttle_engine.executor import execute_move
from strategies.mcts import MCTSNode, MCTSStrategy


def trace_one_iteration():
    """Run one MCTS iteration with detailed tracing."""
    state = create_initial_state()
    print(f"Initial state: current_player={state.current_player}")
    print(f"Initial state game_over={state.is_game_over}")

    # Create root node
    root = MCTSNode(state=state)
    print(f"\nRoot node: player_just_moved={root.player_just_moved}")
    print(f"Root has {len(root.untried_moves)} untried moves")

    # Create an MCTS strategy for helper methods
    mcts = MCTSStrategy(iterations=1)

    # Expansion: pick first untried move
    move = root.untried_moves[0]
    print(f"\nExpanding move: {move}")

    new_state = execute_move(root.state, move)
    player_who_moved = mcts._get_acting_player(root.state)
    print(f"Player who made this move: {player_who_moved}")
    print(f"State after move: current_player={new_state.current_player}")

    child = root.add_child(move, new_state, player_who_moved)
    print(f"Child node: player_just_moved={child.player_just_moved}")

    # Simulation
    print(f"\n--- SIMULATION ---")
    print(f"Simulating from child's state, perspective_player={child.player_just_moved}")
    result = mcts._simulate(child.state, child.player_just_moved)
    print(f"Simulation result (from perspective of player {child.player_just_moved}): {result}")

    # Backpropagation trace
    print(f"\n--- BACKPROPAGATION ---")
    node = child
    while node is not None:
        print(f"Node: player_just_moved={node.player_just_moved}")
        if node.player_just_moved is not None:
            print(f"  Updating with result={result}")
            node.update(result if result is not None else 0.5)
            if result is not None:
                result = 1.0 - result
            print(f"  After flip, result for parent={result}")
        else:
            print(f"  Skipping (player_just_moved is None)")
        node = node.parent

    print(f"\n--- RESULT ---")
    print(f"Child visits={child.visits}, wins={child.wins}, win_rate={child.wins/child.visits if child.visits > 0 else 0}")


def trace_full_search():
    """Run a full MCTS search and show statistics."""
    state = create_initial_state()
    mcts = MCTSStrategy(iterations=100)

    legal_moves = generate_legal_moves(state)
    move, stats = mcts.select_move_with_stats(state, legal_moves)

    print(f"Current player: {state.current_player}")
    print(f"Selected move: {move}")
    print(f"\nMove statistics:")

    sorted_stats = sorted(stats.items(), key=lambda x: x[1]['visits'], reverse=True)[:10]
    for m, s in sorted_stats:
        print(f"  {m}: visits={s['visits']}, win_rate={s['win_rate']:.3f}")


if __name__ == "__main__":
    print("=" * 60)
    print("TRACE ONE ITERATION")
    print("=" * 60)
    trace_one_iteration()

    print("\n" + "=" * 60)
    print("FULL SEARCH STATISTICS")
    print("=" * 60)
    trace_full_search()
