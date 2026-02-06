"""Persistent game logger for recording games to the database."""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from db.database import Database, GameRepository, PlayerRepository

if TYPE_CHECKING:
    from cuttle_engine.moves import Move
    from cuttle_engine.state import GameState
    from core.player_identity import PlayerIdentity


@dataclass
class GameLogContext:
    """Context for an active game being logged."""
    game_id: str
    player0_id: str
    player1_id: str
    tournament_id: str | None
    seed: int | None
    start_time: float
    move_count: int = 0


class PersistentGameLogger:
    """Logs games and moves to persistent database storage.

    Provides methods to start a game, log each move, and end the game
    with final results. Supports MCTS statistics and LLM thinking capture.
    """

    def __init__(self, db: Database):
        """Initialize the game logger.

        Args:
            db: Database instance for persistence.
        """
        self.db = db
        self._player_repo = PlayerRepository(db)
        self._game_repo = GameRepository(db)
        self._active_games: dict[str, GameLogContext] = {}

    def start_game(
        self,
        player0_identity: "PlayerIdentity",
        player1_identity: "PlayerIdentity",
        seed: int | None = None,
        tournament_id: str | None = None,
        game_id: str | None = None,
    ) -> str:
        """Start logging a new game.

        Args:
            player0_identity: Identity for player 0.
            player1_identity: Identity for player 1.
            seed: Random seed for the game.
            tournament_id: Optional tournament this game belongs to.
            game_id: Optional specific game ID (generated if not provided).

        Returns:
            The game ID.
        """
        game_id = game_id or str(uuid.uuid4())

        # Ensure players exist in database
        self._player_repo.get_or_create(
            player_id=player0_identity.id,
            provider=player0_identity.provider,
            model_name=player0_identity.model_name,
            params=player0_identity.params_dict,
            display_name=player0_identity.display_name,
        )
        self._player_repo.get_or_create(
            player_id=player1_identity.id,
            provider=player1_identity.provider,
            model_name=player1_identity.model_name,
            params=player1_identity.params_dict,
            display_name=player1_identity.display_name,
        )

        # Create game context
        context = GameLogContext(
            game_id=game_id,
            player0_id=player0_identity.id,
            player1_id=player1_identity.id,
            tournament_id=tournament_id,
            seed=seed,
            start_time=time.perf_counter(),
        )
        self._active_games[game_id] = context

        # Create game record upfront with placeholder values
        # This ensures the game exists before moves reference it (foreign key constraint)
        self._game_repo.create_game(
            game_id=game_id,
            player0_id=player0_identity.id,
            player1_id=player1_identity.id,
            winner=None,
            win_reason=None,
            score_p0=0,
            score_p1=0,
            turns=0,
            move_count=0,
            duration_ms=0,
            seed=seed,
            tournament_id=tournament_id,
        )

        return game_id

    def log_move(
        self,
        game_id: str,
        turn: int,
        player: int,
        phase: str,
        move: "Move",
        state: "GameState | None" = None,
        mcts_stats: dict[str, Any] | None = None,
        llm_thinking: dict[str, Any] | None = None,
    ) -> None:
        """Log a move to the database.

        Args:
            game_id: The game ID.
            turn: Current turn number.
            player: Player who made the move (0 or 1).
            phase: Game phase when move was made.
            move: The move that was made.
            state: Optional game state after the move.
            mcts_stats: Optional MCTS statistics (visit counts, win rates).
            llm_thinking: Optional LLM reasoning (prompt, response).
        """
        context = self._active_games.get(game_id)
        if context is None:
            return

        context.move_count += 1

        # Compress state to JSON if provided
        state_json = None
        if state is not None:
            state_json = json.dumps(_compress_state(state))

        # Convert stats to JSON
        mcts_stats_json = json.dumps(mcts_stats) if mcts_stats else None
        llm_thinking_json = json.dumps(llm_thinking) if llm_thinking else None

        self._game_repo.add_move(
            game_id=game_id,
            move_number=context.move_count,
            turn=turn,
            player=player,
            phase=phase,
            move_description=str(move),
            state_json=state_json,
            mcts_stats_json=mcts_stats_json,
            llm_thinking_json=llm_thinking_json,
        )

    def end_game(
        self,
        game_id: str,
        winner: int | None,
        win_reason: str | None,
        score_p0: int,
        score_p1: int,
        turns: int,
    ) -> None:
        """End a game and record final results.

        Args:
            game_id: The game ID.
            winner: Winning player (0, 1, or None for draw).
            win_reason: Reason for win (e.g., 'POINTS_THRESHOLD').
            score_p0: Final score for player 0.
            score_p1: Final score for player 1.
            turns: Total turns played.
        """
        context = self._active_games.pop(game_id, None)
        if context is None:
            return

        duration_ms = (time.perf_counter() - context.start_time) * 1000

        # Update the game record that was created at start_game
        self._game_repo.update_game(
            game_id=game_id,
            winner=winner,
            win_reason=win_reason,
            score_p0=score_p0,
            score_p1=score_p1,
            turns=turns,
            move_count=context.move_count,
            duration_ms=duration_ms,
        )

    def abort_game(self, game_id: str) -> None:
        """Abort logging for a game without recording results.

        Args:
            game_id: The game ID to abort.
        """
        self._active_games.pop(game_id, None)

    def get_active_games(self) -> list[str]:
        """Get list of active game IDs being logged."""
        return list(self._active_games.keys())


def _compress_state(state: "GameState") -> dict[str, Any]:
    """Compress game state to a minimal JSON-serializable dict.

    Args:
        state: The game state to compress.

    Returns:
        Compressed state dictionary.
    """
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
                "point_total": p.point_total,
                "kings": p.kings_count,
                "queens": p.queens_count,
            }
            for p in state.players
        ],
    }
