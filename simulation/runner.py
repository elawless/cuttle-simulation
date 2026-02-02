"""Game runner for Cuttle simulations."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from cuttle_engine.executor import execute_move
from cuttle_engine.move_generator import generate_legal_moves
from cuttle_engine.state import GamePhase, create_initial_state

if TYPE_CHECKING:
    from cuttle_engine.moves import Move
    from cuttle_engine.state import GameState
    from strategies.base import Strategy


@dataclass
class GameResult:
    """Result of a completed game."""

    game_id: str
    winner: int | None  # 0, 1, or None for draw
    win_reason: str | None
    turns: int
    final_scores: tuple[int, int]
    player_strategies: tuple[str, str]
    seed: int | None
    duration_ms: float
    move_count: int


@dataclass
class MoveRecord:
    """Record of a single move."""

    turn: int
    player: int
    move: str
    state_after: dict


@dataclass
class GameLog:
    """Complete log of a game."""

    game_id: str
    timestamp: str
    seed: int | None
    player_strategies: tuple[str, str]
    initial_state: dict
    moves: list[MoveRecord] = field(default_factory=list)
    result: GameResult | None = None


class GameRunner:
    """Runs Cuttle games between two strategies."""

    def __init__(
        self,
        strategy0: Strategy,
        strategy1: Strategy,
        max_turns: int = 500,
        log_moves: bool = True,
    ):
        """Initialize the game runner.

        Args:
            strategy0: Strategy for player 0.
            strategy1: Strategy for player 1.
            max_turns: Maximum turns before declaring a draw.
            log_moves: Whether to log individual moves.
        """
        self.strategies = (strategy0, strategy1)
        self.max_turns = max_turns
        self.log_moves = log_moves

    def run_game(self, seed: int | None = None) -> tuple[GameResult, GameLog | None]:
        """Run a single game.

        Args:
            seed: Random seed for reproducibility.

        Returns:
            Tuple of (result, log). Log is None if log_moves is False.
        """
        import time

        start_time = time.perf_counter()
        game_id = str(uuid.uuid4())

        # Initialize game
        state = create_initial_state(seed=seed)

        # Notify strategies
        for i, strategy in enumerate(self.strategies):
            strategy.on_game_start(state, i)

        # Create log if needed
        game_log = None
        if self.log_moves:
            game_log = GameLog(
                game_id=game_id,
                timestamp=datetime.now().isoformat(),
                seed=seed,
                player_strategies=(self.strategies[0].name, self.strategies[1].name),
                initial_state=self._state_to_dict(state),
            )

        move_count = 0

        # Game loop
        while not state.is_game_over and state.turn_number <= self.max_turns:
            # Determine who needs to act
            if state.phase == GamePhase.COUNTER:
                acting_player = state.counter_state.waiting_for_player
            elif state.phase == GamePhase.DISCARD_FOUR:
                acting_player = state.four_state.player
            elif state.phase == GamePhase.RESOLVE_SEVEN:
                acting_player = state.seven_state.player
            else:
                acting_player = state.current_player

            # Get legal moves
            legal_moves = generate_legal_moves(state)

            if not legal_moves:
                # Shouldn't happen in a valid game
                break

            # Select move
            strategy = self.strategies[acting_player]
            move = strategy.select_move(state, legal_moves)

            # Execute move
            new_state = execute_move(state, move)
            move_count += 1

            # Log move
            if game_log:
                game_log.moves.append(
                    MoveRecord(
                        turn=state.turn_number,
                        player=acting_player,
                        move=str(move),
                        state_after=self._state_to_dict(new_state),
                    )
                )

            # Notify strategies
            for strategy in self.strategies:
                strategy.on_move_made(new_state, move, acting_player)

            state = new_state

        # Game ended
        duration_ms = (time.perf_counter() - start_time) * 1000

        result = GameResult(
            game_id=game_id,
            winner=state.winner,
            win_reason=state.win_reason.name if state.win_reason else None,
            turns=state.turn_number,
            final_scores=(
                state.players[0].point_total,
                state.players[1].point_total,
            ),
            player_strategies=(self.strategies[0].name, self.strategies[1].name),
            seed=seed,
            duration_ms=duration_ms,
            move_count=move_count,
        )

        if game_log:
            game_log.result = result

        # Notify strategies
        for strategy in self.strategies:
            strategy.on_game_end(state, state.winner)

        return result, game_log

    def _state_to_dict(self, state: GameState) -> dict:
        """Convert game state to a dictionary for logging."""
        return {
            "turn": state.turn_number,
            "current_player": state.current_player,
            "phase": state.phase.name,
            "deck_size": len(state.deck),
            "scrap_size": len(state.scrap),
            "players": [
                {
                    "hand": [str(c) for c in p.hand],
                    "points": [str(c) for c in p.points_field],
                    "permanents": [str(c) for c in p.permanents],
                    "jacks": [(str(j), str(s)) for j, s in p.jacks],
                    "point_total": p.point_total,
                }
                for p in state.players
            ],
        }


def save_game_log(log: GameLog, base_dir: str = "logs/games") -> Path:
    """Save a game log to disk.

    Args:
        log: Game log to save.
        base_dir: Base directory for logs.

    Returns:
        Path to the saved file.
    """
    # Create directory structure
    date_str = log.timestamp[:10]  # YYYY-MM-DD
    dir_path = Path(base_dir) / date_str
    dir_path.mkdir(parents=True, exist_ok=True)

    # Save as JSON
    file_path = dir_path / f"game_{log.game_id}.json"

    data = {
        "game_id": log.game_id,
        "timestamp": log.timestamp,
        "seed": log.seed,
        "player_strategies": log.player_strategies,
        "initial_state": log.initial_state,
        "moves": [
            {
                "turn": m.turn,
                "player": m.player,
                "move": m.move,
                "state_after": m.state_after,
            }
            for m in log.moves
        ],
        "result": {
            "winner": log.result.winner,
            "win_reason": log.result.win_reason,
            "turns": log.result.turns,
            "final_scores": log.result.final_scores,
            "duration_ms": log.result.duration_ms,
            "move_count": log.result.move_count,
        }
        if log.result
        else None,
    }

    with open(file_path, "w") as f:
        json.dump(data, f, indent=2)

    return file_path


def run_batch(
    strategy0: Strategy,
    strategy1: Strategy,
    num_games: int,
    start_seed: int = 0,
    log_moves: bool = False,
) -> list[GameResult]:
    """Run multiple games.

    Args:
        strategy0: Strategy for player 0.
        strategy1: Strategy for player 1.
        num_games: Number of games to run.
        start_seed: Starting seed (incremented for each game).
        log_moves: Whether to log moves (slower).

    Returns:
        List of game results.
    """
    runner = GameRunner(strategy0, strategy1, log_moves=log_moves)
    results = []

    for i in range(num_games):
        result, _ = runner.run_game(seed=start_seed + i)
        results.append(result)

    return results
