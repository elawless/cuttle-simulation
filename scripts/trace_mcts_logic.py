"""Trace MCTS logic to find the bug."""

from cuttle_engine.state import create_initial_state
from cuttle_engine.move_generator import generate_legal_moves
from cuttle_engine.executor import execute_move, IllegalMoveError
from strategies.mcts import MCTSNode, MCTSStrategy
import random


def trace_full_iteration(verbose=True):
    """Trace a complete MCTS search with detailed output."""
    state = create_initial_state(seed=42)
    print(f"Initial state: P{state.current_player} to move")

    # Create MCTS with controlled seed
    mcts = MCTSStrategy(iterations=50, seed=123)

    # Run search with tracing
    root = MCTSNode(state=state)

    for iteration in range(50):
        node = root

        # Selection
        selection_path = []
        while not node.is_terminal and node.is_fully_expanded and node.children:
            node = node.best_child(mcts._exploration)
            selection_path.append(node.player_just_moved)

        # Expansion
        expanded = False
        if not node.is_terminal and node.untried_moves:
            move = mcts._rng.choice(node.untried_moves)
            try:
                new_state = execute_move(node.state, move)
                player_just_moved = mcts._get_acting_player(node.state)
                node = node.add_child(move, new_state, player_just_moved)
                expanded = True
            except Exception:
                node.untried_moves.remove(move)

        # Simulation
        sim_perspective = node.player_just_moved
        result = mcts._simulate(node.state, sim_perspective)

        if verbose and iteration < 10:
            print(f"\nIteration {iteration}:")
            print(f"  Selection path (player_just_moved): {selection_path}")
            print(f"  Expanded: {expanded}")
            print(f"  Simulation perspective: P{sim_perspective}")
            print(f"  Simulation result: {result}")

        # Backpropagation
        backprop_node = node
        backprop_result = result
        while backprop_node is not None:
            if backprop_node.player_just_moved is not None:
                backprop_node.update(backprop_result if backprop_result is not None else 0.5)
                if backprop_result is not None:
                    backprop_result = 1.0 - backprop_result
            backprop_node = backprop_node.parent

    # Print final statistics
    print("\n" + "=" * 60)
    print("Final statistics after 50 iterations:")
    print("=" * 60)

    sorted_children = sorted(root.children.items(), key=lambda x: x[1].visits, reverse=True)
    for move, child in sorted_children[:5]:
        win_rate = child.wins / child.visits if child.visits > 0 else 0
        print(f"  {str(move)[:40]}: visits={child.visits}, wins={child.wins:.1f}, win_rate={win_rate:.3f}")

    print(f"\nRoot was visited {root.visits} times")

    # KEY CHECK: Is the win rate from root's perspective (the current player)?
    # Child nodes have player_just_moved = current_player (P0)
    # So child.wins counts wins FOR player 0
    # So child.wins/child.visits = P0's win rate from that move
    # MCTS should select moves with HIGH win rate for P0

    # Let's verify by checking what percentage of SIMULATIONS from this state P0 wins
    print("\n" + "=" * 60)
    print("Verifying simulation baseline:")
    print("=" * 60)

    baseline_wins = 0
    for _ in range(100):
        r = mcts._simulate(state, perspective_player=0)
        if r == 1.0:
            baseline_wins += 1

    print(f"P0 wins {baseline_wins}% of random simulations from initial state")
    print(f"Best move win rate: {sorted_children[0][1].wins / sorted_children[0][1].visits:.3f}")

    if sorted_children[0][1].wins / sorted_children[0][1].visits > baseline_wins / 100:
        print("✓ MCTS found a move that beats baseline!")
    else:
        print("✗ MCTS best move doesn't beat baseline...")


def check_exploration_vs_exploitation():
    """Check if UCB1 exploration constant is appropriate."""
    print("\n" + "=" * 60)
    print("Checking exploration constant effect:")
    print("=" * 60)

    state = create_initial_state(seed=42)

    for exploration in [0.5, 1.414, 2.0, 4.0]:
        mcts = MCTSStrategy(iterations=200, exploration_constant=exploration, seed=123)
        legal_moves = generate_legal_moves(state)
        _, stats = mcts.select_move_with_stats(state, legal_moves)

        visits = [s['visits'] for s in stats.values()]
        max_visits = max(visits) if visits else 0
        total_visits = sum(visits)

        print(f"C={exploration:.3f}: max_visits={max_visits}, total={total_visits}, concentration={max_visits/total_visits:.2f}")


def test_move_quality():
    """Test if MCTS can distinguish good from bad moves."""
    print("\n" + "=" * 60)
    print("Testing move quality discrimination:")
    print("=" * 60)

    # Find a state where there's an obviously good move (winning move)
    state = create_initial_state(seed=42)

    # Play a few moves to get to a more interesting state
    moves_played = 0
    while moves_played < 10 and not state.is_game_over:
        moves = generate_legal_moves(state)
        move = random.choice(moves)
        try:
            state = execute_move(state, move)
            moves_played += 1
        except IllegalMoveError:
            pass

    if state.is_game_over:
        print("Game ended during setup")
        return

    print(f"State after {moves_played} moves: P{state.current_player} to move")
    print(f"P0 points: {state.players[0].point_total}, P1 points: {state.players[1].point_total}")

    # Check if there's a winning move
    moves = generate_legal_moves(state)
    from cuttle_engine.moves import PlayPoints

    winning_moves = []
    for m in moves:
        if isinstance(m, PlayPoints):
            threshold = state.point_threshold(state.current_player)
            if state.players[state.current_player].point_total + m.card.point_value >= threshold:
                winning_moves.append(m)

    if winning_moves:
        print(f"Winning moves available: {winning_moves}")

    # Run MCTS and see if it finds the winning move
    mcts = MCTSStrategy(iterations=500, seed=42)
    selected, stats = mcts.select_move_with_stats(state, moves)

    print(f"MCTS selected: {selected}")

    if winning_moves:
        if selected in winning_moves:
            print("✓ MCTS found the winning move!")
        else:
            print("✗ MCTS missed the winning move")
            for wm in winning_moves:
                if wm in stats:
                    print(f"  Winning move stats: {stats[wm]}")


if __name__ == "__main__":
    trace_full_iteration(verbose=True)
    check_exploration_vs_exploitation()
    test_move_quality()
