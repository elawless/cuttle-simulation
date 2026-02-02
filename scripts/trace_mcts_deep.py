"""Deep trace to debug MCTS perspective issues."""

from cuttle_engine.state import create_initial_state
from cuttle_engine.move_generator import generate_legal_moves
from cuttle_engine.executor import execute_move
from strategies.mcts import MCTSNode, MCTSStrategy
import random


def test_simulation_consistency():
    """Test if simulation results are consistent with perspective."""
    state = create_initial_state(seed=42)
    mcts = MCTSStrategy(iterations=1, seed=42)

    # Run multiple simulations from the same state
    # and check if they're consistent
    print("Testing simulation consistency from initial state")
    print(f"Current player (who needs to move): {state.current_player}")

    wins_p0 = 0
    wins_p1 = 0
    draws = 0
    total = 100

    for i in range(total):
        # Simulate from perspective of player 0
        result_p0 = mcts._simulate(state, 0)
        # Simulate from perspective of player 1
        result_p1 = mcts._simulate(state, 1)

        # These should be mirror images!
        if result_p0 is not None and result_p1 is not None:
            if abs(result_p0 + result_p1 - 1.0) > 0.01:
                print(f"MISMATCH! result_p0={result_p0}, result_p1={result_p1}, sum={result_p0+result_p1}")

        if result_p0 == 1.0:
            wins_p0 += 1
        elif result_p0 == 0.0:
            wins_p1 += 1
        else:
            draws += 1

    print(f"From 100 simulations (perspective=player0):")
    print(f"  Player 0 wins: {wins_p0}")
    print(f"  Player 1 wins: {wins_p1}")
    print(f"  Draws/unclear: {draws}")


def test_backprop_two_levels():
    """Test backpropagation through two levels."""
    state = create_initial_state(seed=42)
    mcts = MCTSStrategy(iterations=1, seed=42)

    print("\n" + "=" * 60)
    print("Testing 2-level backpropagation")
    print("=" * 60)

    # Create root (player 0 to move)
    root = MCTSNode(state=state)
    print(f"Root: current_player={state.current_player}, player_just_moved={root.player_just_moved}")

    # Expand first move (player 0 moves)
    move1 = root.untried_moves[0]
    state1 = execute_move(root.state, move1)
    child1 = root.add_child(move1, state1, 0)  # player 0 just moved
    print(f"Level 1: Player 0 moved, now current_player={state1.current_player}")

    # Expand second move (player 1 moves)
    move2 = child1.untried_moves[0]
    state2 = execute_move(child1.state, move2)
    child2 = child1.add_child(move2, state2, 1)  # player 1 just moved
    print(f"Level 2: Player 1 moved, now current_player={state2.current_player}")

    # Simulate from child2's state
    # The perspective should be player_just_moved = player 1
    print(f"\nSimulating from level 2, perspective_player={child2.player_just_moved}")

    # Let's do it manually to understand
    # Say player 0 wins the simulation
    print("\n--- Scenario: Player 0 wins the simulation ---")
    result = 0.0  # From player 1's perspective, this is a loss

    print(f"Simulation result (player 1 perspective): {result}")

    # Backprop
    node = child2
    while node is not None:
        if node.player_just_moved is not None:
            old_wins = node.wins
            node.update(result)
            print(f"Node (player_just_moved={node.player_just_moved}): updated wins {old_wins} -> {node.wins}")
            result = 1.0 - result
            print(f"  Flipped result for parent: {result}")
        node = node.parent

    print(f"\nFinal statistics:")
    print(f"  child2 (player 1's move): visits={child2.visits}, wins={child2.wins}, win_rate={child2.wins/child2.visits:.3f}")
    print(f"  child1 (player 0's move): visits={child1.visits}, wins={child1.wins}, win_rate={child1.wins/child1.visits:.3f}")

    # INTERPRETATION:
    # Player 0 won.
    # child2 = player 1's move. Player 1 lost, so child2 should have LOW win rate (0.0) - CORRECT
    # child1 = player 0's move. Player 0 won, so child1 should have HIGH win rate (1.0) - CORRECT


def test_selection_perspective():
    """Test if selection chooses moves that help the current player."""
    state = create_initial_state(seed=42)

    print("\n" + "=" * 60)
    print("Testing if MCTS selects good moves for current player")
    print("=" * 60)

    # Run MCTS with more iterations
    mcts = MCTSStrategy(iterations=500, seed=42)

    legal_moves = generate_legal_moves(state)
    move, stats = mcts.select_move_with_stats(state, legal_moves)

    print(f"Current player: {state.current_player}")
    print(f"Selected move: {move}")

    # Check: does MCTS prefer moves with HIGH win rates?
    # The win rate in the stats should be from the current player's perspective
    sorted_stats = sorted(stats.items(), key=lambda x: x[1]['visits'], reverse=True)

    print("\nTop 10 moves by visit count:")
    for m, s in sorted_stats[:10]:
        print(f"  {m}: visits={s['visits']}, win_rate={s['win_rate']:.3f}")

    # The selected move should have reasonable win rate
    if move in stats:
        selected_win_rate = stats[move]['win_rate']
        print(f"\nSelected move win_rate: {selected_win_rate:.3f}")

        # Check if this is from the RIGHT perspective
        # The child node stores wins from player_just_moved's perspective
        # Root's children have player_just_moved = current_player (player 0)
        # So the win_rate should be FROM player 0's perspective
        print(f"This win_rate is from player {state.current_player}'s perspective")

        if selected_win_rate > 0.5:
            print("✓ MCTS is selecting moves that favor the current player")
        else:
            print("✗ MCTS might be selecting moves that favor the OPPONENT!")


def test_ucb1_perspective():
    """Test if UCB1 is selecting from the right perspective."""
    state = create_initial_state(seed=42)

    print("\n" + "=" * 60)
    print("Testing UCB1 perspective")
    print("=" * 60)

    # Create a simple tree and manually set wins to test UCB1
    root = MCTSNode(state=state)
    root.visits = 100

    # Add two children with different win rates
    move1 = root.untried_moves[0]
    state1 = execute_move(root.state, move1)
    child1 = root.add_child(move1, state1, 0)

    move2 = root.untried_moves[0]  # Next untried move
    state2 = execute_move(root.state, move2)
    child2 = root.add_child(move2, state2, 0)

    # Set child1 to have HIGH win rate (good for player 0)
    child1.visits = 40
    child1.wins = 36  # 90% win rate

    # Set child2 to have LOW win rate (bad for player 0)
    child2.visits = 40
    child2.wins = 4  # 10% win rate

    print(f"child1: visits={child1.visits}, wins={child1.wins}, win_rate={child1.wins/child1.visits:.3f}")
    print(f"child2: visits={child2.visits}, wins={child2.wins}, win_rate={child2.wins/child2.visits:.3f}")

    ucb1_1 = child1.ucb1(1.414)
    ucb1_2 = child2.ucb1(1.414)
    print(f"child1 UCB1: {ucb1_1:.3f}")
    print(f"child2 UCB1: {ucb1_2:.3f}")

    best = root.best_child(1.414)
    print(f"\nbest_child selects: child1" if best is child1 else "\nbest_child selects: child2")

    if best is child1:
        print("✓ UCB1 correctly prefers the move with higher win rate")
    else:
        print("✗ UCB1 is selecting the LOSING move!")


if __name__ == "__main__":
    test_simulation_consistency()
    test_backprop_two_levels()
    test_selection_perspective()
    test_ucb1_perspective()
