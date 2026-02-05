"""Parallel game runner for training data collection."""

from __future__ import annotations

import os
import time
import uuid
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from simulation.runner import GameResult
    from strategies.base import Strategy


@dataclass
class BatchProgress:
    """Progress information for a batch run."""

    completed: int
    total: int
    elapsed_seconds: float
    wins_by_player: tuple[int, int]

    @property
    def completion_rate(self) -> float:
        return self.completed / self.total if self.total > 0 else 0.0

    @property
    def games_per_second(self) -> float:
        return self.completed / self.elapsed_seconds if self.elapsed_seconds > 0 else 0.0


class ParallelGameRunner:
    """Run many games in parallel across multiple processes.

    Uses ProcessPoolExecutor to distribute games across CPU cores.
    This is ideal for collecting large amounts of training data.
    """

    def __init__(self, num_workers: int | None = None):
        """Initialize the parallel game runner.

        Args:
            num_workers: Number of parallel worker processes.
                        Defaults to os.cpu_count().
        """
        self.num_workers = num_workers or os.cpu_count() or 4

    def run_games(
        self,
        strategy0_name: str,
        strategy1_name: str,
        num_games: int,
        strategy0_params: dict | None = None,
        strategy1_params: dict | None = None,
        callback: Callable[[GameResult, BatchProgress], None] | None = None,
        start_seed: int = 0,
    ) -> list[GameResult]:
        """Run multiple games in parallel.

        Args:
            strategy0_name: Name of strategy for player 0 (e.g., "mcts", "heuristic").
            strategy1_name: Name of strategy for player 1.
            num_games: Total number of games to run.
            strategy0_params: Parameters for strategy 0 (e.g., {"iterations": 1000}).
            strategy1_params: Parameters for strategy 1.
            callback: Optional callback called after each game completes.
                     Receives (GameResult, BatchProgress).
            start_seed: Starting seed (each game uses start_seed + game_index).

        Returns:
            List of GameResult objects.
        """
        strategy0_params = strategy0_params or {}
        strategy1_params = strategy1_params or {}

        start_time = time.perf_counter()
        results: list[GameResult] = []
        wins = [0, 0]

        with ProcessPoolExecutor(max_workers=self.num_workers) as pool:
            # Submit all games
            futures = {
                pool.submit(
                    _run_single_game,
                    strategy0_name,
                    strategy1_name,
                    strategy0_params,
                    strategy1_params,
                    start_seed + i,
                ): i
                for i in range(num_games)
            }

            # Collect results as they complete
            for future in as_completed(futures):
                try:
                    result = future.result()
                    results.append(result)

                    if result.winner is not None:
                        wins[result.winner] += 1

                    if callback:
                        progress = BatchProgress(
                            completed=len(results),
                            total=num_games,
                            elapsed_seconds=time.perf_counter() - start_time,
                            wins_by_player=(wins[0], wins[1]),
                        )
                        callback(result, progress)

                except Exception as e:
                    # Log error but continue with other games
                    print(f"Game failed: {e}")

        return results

    def run_games_with_mcts_stats(
        self,
        mcts_player: int,
        opponent_strategy_name: str,
        num_games: int,
        mcts_iterations: int = 1000,
        opponent_params: dict | None = None,
        callback: Callable[[dict, BatchProgress], None] | None = None,
        start_seed: int = 0,
    ) -> list[dict]:
        """Run games collecting detailed MCTS statistics.

        This variant collects per-move MCTS statistics (visit counts, win rates)
        for training heuristics or neural networks.

        Args:
            mcts_player: Which player uses MCTS (0 or 1).
            opponent_strategy_name: Strategy for the other player.
            num_games: Number of games to run.
            mcts_iterations: MCTS iterations per move.
            opponent_params: Parameters for opponent strategy.
            callback: Called after each game with (game_data, progress).
            start_seed: Starting random seed.

        Returns:
            List of game data dicts with MCTS statistics per move.
        """
        opponent_params = opponent_params or {}
        start_time = time.perf_counter()
        results: list[dict] = []
        wins = [0, 0]

        with ProcessPoolExecutor(max_workers=self.num_workers) as pool:
            futures = {
                pool.submit(
                    _run_game_with_mcts_stats,
                    mcts_player,
                    opponent_strategy_name,
                    opponent_params,
                    mcts_iterations,
                    start_seed + i,
                ): i
                for i in range(num_games)
            }

            for future in as_completed(futures):
                try:
                    game_data = future.result()
                    results.append(game_data)

                    winner = game_data.get("winner")
                    if winner is not None:
                        wins[winner] += 1

                    if callback:
                        progress = BatchProgress(
                            completed=len(results),
                            total=num_games,
                            elapsed_seconds=time.perf_counter() - start_time,
                            wins_by_player=(wins[0], wins[1]),
                        )
                        callback(game_data, progress)

                except Exception as e:
                    print(f"Game failed: {e}")

        return results


def _run_single_game(
    strategy0_name: str,
    strategy1_name: str,
    strategy0_params: dict,
    strategy1_params: dict,
    seed: int,
) -> GameResult:
    """Run a single game in a worker process.

    This is a standalone function for pickling compatibility.
    """
    from simulation.runner import GameRunner
    from web.api.session_manager import StrategyFactory

    factory = StrategyFactory()
    strategy0 = factory.create(strategy0_name, strategy0_params)
    strategy1 = factory.create(strategy1_name, strategy1_params)

    runner = GameRunner(strategy0, strategy1, log_moves=False)
    result, _ = runner.run_game(seed=seed)
    return result


def _run_game_with_mcts_stats(
    mcts_player: int,
    opponent_strategy_name: str,
    opponent_params: dict,
    mcts_iterations: int,
    seed: int,
) -> dict:
    """Run a game collecting MCTS statistics.

    Returns a dict with:
    - game_id: Unique game identifier
    - seed: Random seed used
    - winner: Winning player (0, 1, or None)
    - final_scores: (p0_points, p1_points)
    - moves: List of move records with MCTS stats
    """
    from cuttle_engine.executor import execute_move
    from cuttle_engine.move_generator import generate_legal_moves
    from cuttle_engine.state import GamePhase, create_initial_state
    from strategies.mcts import MCTSStrategy
    from web.api.session_manager import StrategyFactory

    factory = StrategyFactory()

    # Create strategies
    mcts = MCTSStrategy(iterations=mcts_iterations, seed=seed)
    opponent = factory.create(opponent_strategy_name, opponent_params)

    strategies = [opponent, opponent]
    strategies[mcts_player] = mcts

    # Initialize game
    state = create_initial_state(seed=seed)
    for i, strat in enumerate(strategies):
        strat.on_game_start(state, i)

    game_data = {
        "game_id": str(uuid.uuid4()),
        "seed": seed,
        "mcts_player": mcts_player,
        "mcts_iterations": mcts_iterations,
        "opponent_strategy": opponent_strategy_name,
        "moves": [],
        "winner": None,
        "final_scores": (0, 0),
    }

    max_turns = 500
    while not state.is_game_over and state.turn_number <= max_turns:
        # Determine acting player
        if state.phase == GamePhase.COUNTER:
            acting_player = state.counter_state.waiting_for_player
        elif state.phase == GamePhase.DISCARD_FOUR:
            acting_player = state.four_state.player
        elif state.phase == GamePhase.RESOLVE_SEVEN:
            acting_player = state.seven_state.player
        else:
            acting_player = state.current_player

        legal_moves = generate_legal_moves(state)
        if not legal_moves:
            break

        strategy = strategies[acting_player]

        # If MCTS player, collect statistics
        if acting_player == mcts_player:
            move, stats = mcts.select_move_with_stats(state, legal_moves)

            # Convert stats to serializable format
            move_stats = {}
            for m, s in stats.items():
                move_stats[str(m)] = {
                    "visits": s["visits"],
                    "wins": s["wins"],
                    "win_rate": s["win_rate"],
                }

            move_record = {
                "turn": state.turn_number,
                "player": acting_player,
                "phase": state.phase.name,
                "move": str(move),
                "legal_move_count": len(legal_moves),
                "mcts_stats": move_stats,
                "selected_visits": stats.get(move, {}).get("visits", 0),
                "selected_win_rate": stats.get(move, {}).get("win_rate", 0.0),
            }
        else:
            move = strategy.select_move(state, legal_moves)
            move_record = {
                "turn": state.turn_number,
                "player": acting_player,
                "phase": state.phase.name,
                "move": str(move),
                "legal_move_count": len(legal_moves),
                "mcts_stats": None,
            }

        game_data["moves"].append(move_record)

        # Execute move
        state = execute_move(state, move)

        # Notify strategies
        for strat in strategies:
            strat.on_move_made(state, move, acting_player)

    game_data["winner"] = state.winner
    game_data["final_scores"] = (
        state.players[0].point_total,
        state.players[1].point_total,
    )

    return game_data
