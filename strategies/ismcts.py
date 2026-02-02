"""Information Set Monte Carlo Tree Search for Cuttle.

ISMCTS handles hidden information (opponent's hand) by sampling
possible opponent hands consistent with what we've observed.
"""

from __future__ import annotations

import math
import random
from collections import defaultdict
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from cuttle_engine.cards import Card, Rank, Suit, create_deck
from cuttle_engine.executor import execute_move
from cuttle_engine.move_generator import generate_legal_moves
from cuttle_engine.state import GamePhase, GameState, PlayerState
from strategies.base import Strategy
from strategies.random_strategy import RandomStrategy

if TYPE_CHECKING:
    from cuttle_engine.moves import Move


@dataclass
class ISMCTSNode:
    """A node in the ISMCTS tree.

    Unlike regular MCTS, ISMCTS nodes represent information sets -
    they aggregate statistics across multiple possible game states
    that are indistinguishable from the player's perspective.

    Attributes:
        move: The move that led to this node.
        parent: Parent node.
        children: Child nodes keyed by move.
        visits: Total visit count.
        wins: Total wins.
        availability_count: How many times this node was available for selection.
    """

    move: Move | None = None
    parent: ISMCTSNode | None = None
    children: dict[Move, ISMCTSNode] = field(default_factory=dict)
    visits: int = 0
    wins: float = 0.0
    availability_count: int = 0

    def ucb1_ismcts(self, exploration: float) -> float:
        """Calculate ISMCTS-style UCB1 score.

        Uses availability count instead of parent visits for proper
        handling of information sets.
        """
        if self.visits == 0:
            return float("inf")

        exploitation = self.wins / self.visits
        exploration_term = exploration * math.sqrt(
            math.log(self.availability_count) / self.visits
        )
        return exploitation + exploration_term

    def get_or_create_child(self, move: Move) -> ISMCTSNode:
        """Get existing child or create new one for the move."""
        if move not in self.children:
            self.children[move] = ISMCTSNode(move=move, parent=self)
        return self.children[move]

    def update(self, result: float) -> None:
        """Update node statistics."""
        self.visits += 1
        self.wins += result


class ISMCTSStrategy(Strategy):
    """Information Set Monte Carlo Tree Search strategy.

    Handles hidden information by:
    1. At each iteration, sample a determinization (possible opponent hand)
    2. Run MCTS selection/expansion/simulation on that determinization
    3. Aggregate statistics across all determinizations

    This gives us robust move selection even when we don't know
    the opponent's exact hand.
    """

    def __init__(
        self,
        iterations: int = 1000,
        exploration_constant: float = 0.7,  # Lower than standard MCTS
        simulation_strategy: Strategy | None = None,
        seed: int | None = None,
        max_simulation_depth: int = 200,
    ):
        """Initialize ISMCTS.

        Args:
            iterations: Number of MCTS iterations per move.
            exploration_constant: UCB1 exploration parameter.
            simulation_strategy: Strategy for rollouts.
            seed: Random seed.
            max_simulation_depth: Max moves per simulation.
        """
        self._iterations = iterations
        self._exploration = exploration_constant
        self._simulation_strategy = simulation_strategy or RandomStrategy(seed)
        self._rng = random.Random(seed)
        self._max_sim_depth = max_simulation_depth
        self._player_index: int | None = None
        self._known_cards: set[Card] = set()  # Cards we know locations of

    @property
    def name(self) -> str:
        return f"ISMCTS({self._iterations})"

    def on_game_start(self, state: GameState, player_index: int) -> None:
        """Track our player index and reset knowledge."""
        self._player_index = player_index
        self._known_cards = set()
        # We know our own starting hand
        self._known_cards.update(state.players[player_index].hand)

    def on_move_made(self, state: GameState, move: Move, player: int) -> None:
        """Update our knowledge based on observed moves."""
        # Track cards that become visible through play
        from cuttle_engine.moves import (
            PlayPoints, Scuttle, PlayOneOff, PlayPermanent,
            Counter, Discard, ResolveSeven
        )

        match move:
            case PlayPoints(card=card) | Scuttle(card=card) | PlayOneOff(card=card):
                self._known_cards.add(card)
            case PlayPermanent(card=card, target_card=target):
                self._known_cards.add(card)
                if target:
                    self._known_cards.add(target)
            case Counter(card=card) | Discard(card=card):
                self._known_cards.add(card)
            case ResolveSeven(card=card):
                self._known_cards.add(card)

        # Update our known hand
        if self._player_index is not None:
            self._known_cards.update(state.players[self._player_index].hand)

    def select_move(self, state: GameState, legal_moves: list[Move]) -> Move:
        """Select a move using ISMCTS.

        Args:
            state: Current game state (may have hidden info).
            legal_moves: Legal moves for current player.

        Returns:
            Selected move.
        """
        if not legal_moves:
            raise ValueError("No legal moves available")

        if len(legal_moves) == 1:
            return legal_moves[0]

        # Determine our perspective
        acting_player = self._get_acting_player(state)

        # Create root node
        root = ISMCTSNode()

        # Run ISMCTS iterations
        for _ in range(self._iterations):
            # Determinize: sample a possible state
            det_state = self._determinize(state, acting_player)

            # Run one MCTS iteration on this determinization
            self._run_iteration(root, det_state, acting_player)

        # Select move with highest visit count
        best_move = max(
            root.children.items(),
            key=lambda x: x[1].visits
        )[0]

        return best_move

    def _get_acting_player(self, state: GameState) -> int:
        """Get the player who needs to act."""
        if state.phase == GamePhase.COUNTER:
            return state.counter_state.waiting_for_player
        elif state.phase == GamePhase.DISCARD_FOUR:
            return state.four_state.player
        elif state.phase == GamePhase.RESOLVE_SEVEN:
            return state.seven_state.player
        return state.current_player

    def _determinize(self, state: GameState, perspective_player: int) -> GameState:
        """Create a determinized state by sampling unknown cards.

        We know:
        - Our own hand
        - Cards in play (points, permanents, jacks)
        - Cards in scrap
        - How many cards opponent has

        We don't know:
        - Exact cards in opponent's hand
        - Order of deck

        Args:
            state: Current game state.
            perspective_player: Which player we're playing as.

        Returns:
            A determinized game state with sampled hidden cards.
        """
        opponent = 1 - perspective_player

        # Collect all known card locations
        known_locations: set[Card] = set()

        # Our hand
        known_locations.update(state.players[perspective_player].hand)

        # All cards in play for both players
        for i in range(2):
            p = state.players[i]
            known_locations.update(p.points_field)
            known_locations.update(p.permanents)
            for jack, stolen in p.jacks:
                known_locations.add(jack)
                known_locations.add(stolen)

        # Cards in scrap
        known_locations.update(state.scrap)

        # Cards revealed by Seven (if in that phase)
        if state.seven_state:
            known_locations.update(state.seven_state.revealed_cards)

        # Cards we've tracked during the game
        known_locations.update(self._known_cards)

        # All unknown cards could be in opponent's hand or deck
        all_cards = set(create_deck())
        unknown_cards = list(all_cards - known_locations)
        self._rng.shuffle(unknown_cards)

        # Assign unknown cards
        opp_hand_size = len(state.players[opponent].hand)
        sampled_opp_hand = tuple(unknown_cards[:opp_hand_size])
        sampled_deck = tuple(unknown_cards[opp_hand_size:])

        # Create new player states
        opp_state = state.players[opponent]
        new_opp_state = PlayerState(
            hand=sampled_opp_hand,
            points_field=opp_state.points_field,
            permanents=opp_state.permanents,
            jacks=opp_state.jacks,
        )

        if opponent == 0:
            new_players = (new_opp_state, state.players[1])
        else:
            new_players = (state.players[0], new_opp_state)

        # Create determinized state
        return GameState(
            players=new_players,
            deck=sampled_deck,
            scrap=state.scrap,
            current_player=state.current_player,
            phase=state.phase,
            turn_number=state.turn_number,
            consecutive_passes=state.consecutive_passes,
            counter_state=state.counter_state,
            seven_state=state.seven_state,
            four_state=state.four_state,
            winner=state.winner,
            win_reason=state.win_reason,
        )

    def _run_iteration(
        self, root: ISMCTSNode, state: GameState, perspective_player: int
    ) -> None:
        """Run one ISMCTS iteration.

        Args:
            root: Root node of the tree.
            state: Determinized game state.
            perspective_player: Player from whose perspective we're searching.
        """
        node = root
        current_state = state
        path: list[tuple[ISMCTSNode, int | None]] = [(root, None)]

        # Selection & Expansion
        while not current_state.is_game_over:
            legal_moves = generate_legal_moves(current_state)
            if not legal_moves:
                break

            acting_player = self._get_acting_player(current_state)

            # Mark available children
            for move in legal_moves:
                child = node.get_or_create_child(move)
                child.availability_count += 1

            # Find unvisited moves
            unvisited = [m for m in legal_moves if node.children[m].visits == 0]

            if unvisited:
                # Expand: pick random unvisited move
                move = self._rng.choice(unvisited)
                child = node.children[move]
                current_state = execute_move(current_state, move)
                path.append((child, acting_player))
                node = child
                break
            else:
                # Select: UCB1 among available children
                available_children = [
                    (m, node.children[m]) for m in legal_moves
                ]
                move, child = max(
                    available_children,
                    key=lambda x: x[1].ucb1_ismcts(self._exploration)
                )
                current_state = execute_move(current_state, move)
                path.append((child, acting_player))
                node = child

        # Simulation
        result = self._simulate(current_state, perspective_player)

        # Backpropagation
        for node, player_just_moved in path:
            if player_just_moved is None:
                # Root node
                node.visits += 1
            else:
                # Result from perspective of perspective_player
                # If player_just_moved is perspective_player, use result directly
                # Otherwise, use 1 - result
                if player_just_moved == perspective_player:
                    node.update(result)
                else:
                    node.update(1.0 - result)

    def _simulate(self, state: GameState, perspective_player: int) -> float:
        """Run random simulation from state.

        Args:
            state: Starting state.
            perspective_player: Player to evaluate for.

        Returns:
            Win value (1.0 = win, 0.0 = loss, 0.5 = draw).
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
                # Move generator bug - abort with neutral result
                break
            depth += 1

        if not current_state.is_game_over:
            # Use point-based heuristic
            my_points = current_state.players[perspective_player].point_total
            opp_points = current_state.players[1 - perspective_player].point_total
            if my_points > opp_points:
                return 0.7
            elif opp_points > my_points:
                return 0.3
            return 0.5

        if current_state.winner == perspective_player:
            return 1.0
        elif current_state.winner is not None:
            return 0.0
        return 0.5

    def get_move_statistics(self, state: GameState) -> dict[Move, dict]:
        """Get detailed statistics for each move after ISMCTS search.

        Args:
            state: Current game state.

        Returns:
            Dict mapping moves to statistics.
        """
        legal_moves = generate_legal_moves(state)
        if not legal_moves:
            return {}

        acting_player = self._get_acting_player(state)
        root = ISMCTSNode()

        for _ in range(self._iterations):
            det_state = self._determinize(state, acting_player)
            self._run_iteration(root, det_state, acting_player)

        stats = {}
        for move, child in root.children.items():
            win_rate = child.wins / child.visits if child.visits > 0 else 0.0
            stats[move] = {
                "visits": child.visits,
                "wins": child.wins,
                "win_rate": win_rate,
                "availability": child.availability_count,
            }

        return stats
