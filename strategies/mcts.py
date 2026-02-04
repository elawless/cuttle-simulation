"""Monte Carlo Tree Search strategy for Cuttle."""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from cuttle_engine.executor import execute_move
from cuttle_engine.move_generator import generate_legal_moves
from cuttle_engine.state import GamePhase
from strategies.base import Strategy
from strategies.heuristic import HeuristicStrategy
from strategies.random_strategy import RandomStrategy

if TYPE_CHECKING:
    from cuttle_engine.moves import Move
    from cuttle_engine.state import GameState


class EpsilonGreedyStrategy(Strategy):
    """Hybrid strategy: mostly heuristic with some random exploration.

    This strategy uses heuristic-guided moves most of the time (1 - epsilon),
    but occasionally makes random moves (epsilon) to add diversity.
    This provides better signal than pure random rollouts while avoiding
    overfitting to heuristic blind spots.
    """

    def __init__(self, epsilon: float = 0.2, seed: int | None = None):
        """Initialize epsilon-greedy strategy.

        Args:
            epsilon: Probability of making a random move (0.2 = 20% random).
            seed: Random seed for reproducibility.
        """
        self._epsilon = epsilon
        self._rng = random.Random(seed)
        self._heuristic = HeuristicStrategy(seed)
        self._random = RandomStrategy(seed)

    @property
    def name(self) -> str:
        return f"EpsilonGreedy({self._epsilon})"

    def select_move(self, state: GameState, legal_moves: list[Move]) -> Move:
        """Select a move using epsilon-greedy strategy."""
        if self._rng.random() < self._epsilon:
            return self._random.select_move(state, legal_moves)
        return self._heuristic.select_move(state, legal_moves)


@dataclass
class MCTSNode:
    """A node in the MCTS search tree.

    Attributes:
        state: Game state at this node.
        parent: Parent node (None for root).
        move: Move that led to this node from parent.
        children: Child nodes (move -> child mapping).
        visits: Number of times this node was visited.
        wins: Number of wins for the player who made the move leading here.
        untried_moves: Moves that haven't been expanded yet.
        player_just_moved: Which player made the move to reach this state.
    """

    state: GameState
    parent: MCTSNode | None = None
    move: Move | None = None
    children: dict[Move, MCTSNode] = field(default_factory=dict)
    visits: int = 0
    wins: float = 0.0
    untried_moves: list[Move] | None = None
    player_just_moved: int | None = None

    def __post_init__(self):
        if self.untried_moves is None:
            moves = generate_legal_moves(self.state)
            # Order moves by heuristic score (best first) for better expansion order
            heuristic = HeuristicStrategy()
            # Use negative index as tiebreaker to maintain stable sort
            scored = [(heuristic._score_move(self.state, m), -i, m) for i, m in enumerate(moves)]
            scored.sort(reverse=True)  # Highest score first
            self.untried_moves = [m for _, _, m in scored]

    @property
    def is_fully_expanded(self) -> bool:
        """Whether all moves have been tried."""
        return len(self.untried_moves) == 0

    @property
    def is_terminal(self) -> bool:
        """Whether this is a terminal state."""
        return self.state.is_game_over

    def ucb1(self, exploration: float) -> float:
        """Calculate UCB1 score for this node.

        Args:
            exploration: Exploration constant (typically sqrt(2)).

        Returns:
            UCB1 score (higher = more promising to explore).
        """
        if self.visits == 0:
            return float("inf")

        if self.parent is None or self.parent.visits == 0:
            return float("inf")

        exploitation = self.wins / self.visits
        exploration_term = exploration * math.sqrt(
            math.log(self.parent.visits) / self.visits
        )
        return exploitation + exploration_term

    def best_child(self, exploration: float) -> MCTSNode:
        """Select the best child according to UCB1.

        Args:
            exploration: Exploration constant.

        Returns:
            The child node with highest UCB1 score.
        """
        return max(self.children.values(), key=lambda c: c.ucb1(exploration))

    def add_child(self, move: Move, state: GameState, player_just_moved: int) -> MCTSNode:
        """Add a child node for the given move.

        Args:
            move: The move taken.
            state: The resulting state.
            player_just_moved: Which player made the move.

        Returns:
            The new child node.
        """
        child = MCTSNode(
            state=state,
            parent=self,
            move=move,
            player_just_moved=player_just_moved,
        )
        self.untried_moves.remove(move)
        self.children[move] = child
        return child

    def update(self, result: float) -> None:
        """Update this node's statistics.

        Args:
            result: Win value (1.0 for win, 0.0 for loss, 0.5 for draw).
        """
        self.visits += 1
        self.wins += result


class MCTSStrategy(Strategy):
    """Monte Carlo Tree Search strategy.

    Uses UCB1 for selection and epsilon-greedy rollouts for evaluation.
    Rollouts use 80% heuristic moves and 20% random moves by default,
    providing better signal than pure random while maintaining diversity.

    This is an "open information" version - it assumes perfect information
    about the game state. For hidden information (opponent's hand),
    use ISMCTSStrategy instead.
    """

    def __init__(
        self,
        iterations: int = 1000,
        exploration_constant: float = 1.414,  # sqrt(2)
        simulation_strategy: Strategy | None = None,
        seed: int | None = None,
        max_simulation_depth: int = 200,
    ):
        """Initialize the MCTS strategy.

        Args:
            iterations: Number of MCTS iterations per move.
            exploration_constant: UCB1 exploration parameter (sqrt(2) is standard).
            simulation_strategy: Strategy for rollouts (EpsilonGreedyStrategy if None).
            seed: Random seed for reproducibility.
            max_simulation_depth: Maximum moves in a simulation before giving up.
        """
        self._iterations = iterations
        self._exploration = exploration_constant
        self._simulation_strategy = simulation_strategy or EpsilonGreedyStrategy(
            epsilon=0.2, seed=seed
        )
        self._rng = random.Random(seed)
        self._max_sim_depth = max_simulation_depth

    @property
    def name(self) -> str:
        return f"MCTS({self._iterations})"

    def select_move(self, state: GameState, legal_moves: list[Move]) -> Move:
        """Select a move using MCTS.

        Args:
            state: Current game state.
            legal_moves: List of legal moves.

        Returns:
            The selected move (highest visit count).
        """
        if not legal_moves:
            raise ValueError("No legal moves available")

        if len(legal_moves) == 1:
            return legal_moves[0]

        # Create root node
        root = MCTSNode(state=state)

        # Run MCTS iterations
        for _ in range(self._iterations):
            node = root

            # Selection: traverse tree using UCB1
            while not node.is_terminal and node.is_fully_expanded and node.children:
                node = node.best_child(self._exploration)

            # Expansion: add a new child for an untried move (best heuristic score first)
            expanded = False
            while not node.is_terminal and node.untried_moves and not expanded:
                move = node.untried_moves[0]  # Already sorted by heuristic score
                try:
                    new_state = execute_move(node.state, move)
                    player_just_moved = self._get_acting_player(node.state)
                    node = node.add_child(move, new_state, player_just_moved)
                    expanded = True
                except Exception:
                    # Move execution failed - remove from untried and try another
                    node.untried_moves.remove(move)

            # Simulation: random playout to terminal state
            result = self._simulate(node.state, node.player_just_moved)

            # Backpropagation: update statistics up the tree
            while node is not None:
                # Result is from perspective of player_just_moved
                # We need to flip it for the parent's perspective
                if node.player_just_moved is not None:
                    node.update(result if result is not None else 0.5)
                    # Flip result for next level (opponent's perspective)
                    if result is not None:
                        result = 1.0 - result
                node = node.parent

        # Select move with highest visit count (most robust)
        if not root.children:
            # No children expanded - fall back to random
            return self._rng.choice(legal_moves)

        best_move = max(
            root.children.items(),
            key=lambda x: x[1].visits
        )[0]

        return best_move

    def _get_acting_player(self, state: GameState) -> int:
        """Determine which player is acting in the given state."""
        if state.phase == GamePhase.COUNTER:
            return state.counter_state.waiting_for_player
        elif state.phase == GamePhase.DISCARD_FOUR:
            return state.four_state.player
        elif state.phase == GamePhase.RESOLVE_SEVEN:
            return state.seven_state.player
        return state.current_player

    def _simulate(self, state: GameState, perspective_player: int | None) -> float | None:
        """Run a random simulation from the given state.

        Args:
            state: Starting state for simulation.
            perspective_player: Player from whose perspective to evaluate.

        Returns:
            1.0 if perspective_player wins, 0.0 if loses, 0.5 for draw, None if max depth reached.
        """
        from cuttle_engine.executor import IllegalMoveError

        current_state = state
        depth = 0

        while not current_state.is_game_over and depth < self._max_sim_depth:
            moves = generate_legal_moves(current_state)
            if not moves:
                break

            move = self._simulation_strategy.select_move(current_state, moves)
            try:
                current_state = execute_move(current_state, move)
            except IllegalMoveError:
                # Move generator bug - abort simulation with neutral result
                break
            depth += 1

        if not current_state.is_game_over:
            # Reached max depth - use heuristic (point difference)
            if perspective_player is None:
                return 0.5
            my_points = current_state.players[perspective_player].point_total
            opp_points = current_state.players[1 - perspective_player].point_total
            if my_points > opp_points:
                return 0.7  # Slight advantage
            elif opp_points > my_points:
                return 0.3  # Slight disadvantage
            return 0.5

        # Game ended
        if perspective_player is None:
            return 0.5

        if current_state.winner == perspective_player:
            return 1.0
        elif current_state.winner is not None:
            return 0.0
        return 0.5  # Draw

    def select_move_with_stats(
        self, state: GameState, legal_moves: list[Move]
    ) -> tuple[Move, dict[Move, dict]]:
        """Select a move and return statistics from the same MCTS search.

        This is useful for debugging - unlike calling select_move and
        get_move_statistics separately, this returns stats from the exact
        same search that produced the move selection.

        Args:
            state: Current game state.
            legal_moves: List of legal moves.

        Returns:
            Tuple of (selected_move, statistics_dict).
        """
        if not legal_moves:
            raise ValueError("No legal moves available")

        if len(legal_moves) == 1:
            return legal_moves[0], {legal_moves[0]: {"visits": 1, "wins": 0.5, "win_rate": 0.5, "ucb1": float("inf")}}

        # Create root node
        root = MCTSNode(state=state)

        # Run MCTS iterations
        for _ in range(self._iterations):
            node = root

            # Selection: traverse tree using UCB1
            while not node.is_terminal and node.is_fully_expanded and node.children:
                node = node.best_child(self._exploration)

            # Expansion: add a new child for an untried move (best heuristic score first)
            expanded = False
            while not node.is_terminal and node.untried_moves and not expanded:
                move = node.untried_moves[0]  # Already sorted by heuristic score
                try:
                    new_state = execute_move(node.state, move)
                    player_just_moved = self._get_acting_player(node.state)
                    node = node.add_child(move, new_state, player_just_moved)
                    expanded = True
                except Exception:
                    node.untried_moves.remove(move)

            # Simulation: random playout to terminal state
            result = self._simulate(node.state, node.player_just_moved)

            # Backpropagation: update statistics up the tree
            while node is not None:
                if node.player_just_moved is not None:
                    node.update(result if result is not None else 0.5)
                    if result is not None:
                        result = 1.0 - result
                node = node.parent

        # Collect statistics
        stats = {}
        for move, child in root.children.items():
            win_rate = child.wins / child.visits if child.visits > 0 else 0.0
            stats[move] = {
                "visits": child.visits,
                "wins": child.wins,
                "win_rate": win_rate,
                "ucb1": child.ucb1(self._exploration) if child.visits > 0 else float("inf"),
            }

        # Select move with highest visit count (most robust)
        if not root.children:
            return self._rng.choice(legal_moves), {}

        best_move = max(
            root.children.items(),
            key=lambda x: x[1].visits
        )[0]

        return best_move, stats

    def get_move_statistics(self, state: GameState) -> dict[Move, dict]:
        """Get detailed statistics for each move after MCTS search.

        Useful for analysis - runs a full MCTS search and returns stats.
        Note: This runs a separate search from select_move, so stats may differ.

        Args:
            state: Current game state.

        Returns:
            Dict mapping moves to {visits, wins, win_rate, ucb1}.
        """
        legal_moves = generate_legal_moves(state)
        if not legal_moves:
            return {}

        _, stats = self.select_move_with_stats(state, legal_moves)
        return stats
