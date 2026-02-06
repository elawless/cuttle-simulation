"""SQLite database layer for Cuttle tournament infrastructure."""

from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator


@dataclass
class PlayerRecord:
    """A player/model record from the database."""
    id: str
    provider: str
    model_name: str
    params_json: str
    display_name: str | None
    created_at: datetime


@dataclass
class EloRecord:
    """An ELO rating record from the database."""
    id: int
    player_id: str
    rating: float
    rating_pool: str
    games_played: int
    timestamp: datetime


@dataclass
class GameRecord:
    """A game record from the database."""
    id: str
    player0_id: str
    player1_id: str
    winner: int | None
    win_reason: str | None
    score_p0: int
    score_p1: int
    turns: int
    move_count: int
    duration_ms: float
    seed: int | None
    tournament_id: str | None
    created_at: datetime


@dataclass
class MoveRecord:
    """A move record from the database."""
    id: int
    game_id: str
    move_number: int
    turn: int
    player: int
    phase: str
    move_description: str
    state_json: str | None
    mcts_stats_json: str | None
    llm_thinking_json: str | None


@dataclass
class CostRecord:
    """An API cost record from the database."""
    id: int
    player_id: str | None
    game_id: str | None
    tournament_id: str | None
    provider: str
    model: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    timestamp: datetime


@dataclass
class TournamentRecord:
    """A tournament record from the database."""
    id: str
    name: str | None
    config_json: str
    status: str
    budget_usd: float | None
    spent_usd: float
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime


class Database:
    """SQLite database connection manager with thread safety."""

    def __init__(self, db_path: str | Path = "cuttle_tournament.db"):
        """Initialize the database.

        Args:
            db_path: Path to the SQLite database file.
        """
        self.db_path = Path(db_path)
        self._local = threading.local()
        self._init_schema()

    def _get_connection(self) -> sqlite3.Connection:
        """Get thread-local database connection."""
        if not hasattr(self._local, "connection"):
            conn = sqlite3.connect(
                str(self.db_path),
                detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES,
                timeout=30.0,  # Wait up to 30s for locks
            )
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys = ON")
            # Enable WAL mode for better concurrency (allows concurrent reads + one write)
            conn.execute("PRAGMA journal_mode = WAL")
            # Set busy timeout to retry on lock contention
            conn.execute("PRAGMA busy_timeout = 30000")
            self._local.connection = conn
        return self._local.connection

    def _init_schema(self) -> None:
        """Initialize database schema if not exists."""
        schema_path = Path(__file__).parent / "schema.sql"
        with open(schema_path, "r") as f:
            schema_sql = f.read()

        conn = self._get_connection()
        conn.executescript(schema_sql)
        conn.commit()

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        """Context manager for database transactions."""
        conn = self._get_connection()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    def execute(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        """Execute a SQL statement."""
        conn = self._get_connection()
        return conn.execute(sql, params)

    def executemany(self, sql: str, params_list: list[tuple]) -> sqlite3.Cursor:
        """Execute a SQL statement with multiple parameter sets."""
        conn = self._get_connection()
        return conn.executemany(sql, params_list)

    def commit(self) -> None:
        """Commit the current transaction."""
        self._get_connection().commit()

    def close(self) -> None:
        """Close the database connection for the current thread."""
        if hasattr(self._local, "connection"):
            self._local.connection.close()
            del self._local.connection


class PlayerRepository:
    """Repository for player/model records."""

    def __init__(self, db: Database):
        self.db = db

    def create(
        self,
        player_id: str,
        provider: str,
        model_name: str,
        params: dict[str, Any] | None = None,
        display_name: str | None = None,
    ) -> PlayerRecord:
        """Create a new player record."""
        params_json = json.dumps(params or {})
        self.db.execute(
            """
            INSERT INTO players (id, provider, model_name, params_json, display_name)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                display_name = COALESCE(excluded.display_name, players.display_name)
            """,
            (player_id, provider, model_name, params_json, display_name),
        )
        self.db.commit()
        return self.get(player_id)

    def get(self, player_id: str) -> PlayerRecord | None:
        """Get a player by ID."""
        row = self.db.execute(
            "SELECT * FROM players WHERE id = ?", (player_id,)
        ).fetchone()
        if row is None:
            return None
        return PlayerRecord(
            id=row["id"],
            provider=row["provider"],
            model_name=row["model_name"],
            params_json=row["params_json"],
            display_name=row["display_name"],
            created_at=_parse_datetime(row["created_at"]),
        )

    def get_or_create(
        self,
        player_id: str,
        provider: str,
        model_name: str,
        params: dict[str, Any] | None = None,
        display_name: str | None = None,
    ) -> PlayerRecord:
        """Get an existing player or create a new one."""
        existing = self.get(player_id)
        if existing:
            return existing
        return self.create(player_id, provider, model_name, params, display_name)

    def list_all(self) -> list[PlayerRecord]:
        """List all players."""
        rows = self.db.execute("SELECT * FROM players ORDER BY created_at DESC").fetchall()
        return [
            PlayerRecord(
                id=row["id"],
                provider=row["provider"],
                model_name=row["model_name"],
                params_json=row["params_json"],
                display_name=row["display_name"],
                created_at=_parse_datetime(row["created_at"]),
            )
            for row in rows
        ]


class GameRepository:
    """Repository for game and move records."""

    def __init__(self, db: Database):
        self.db = db

    def create_game(
        self,
        game_id: str,
        player0_id: str,
        player1_id: str,
        winner: int | None,
        win_reason: str | None,
        score_p0: int,
        score_p1: int,
        turns: int,
        move_count: int,
        duration_ms: float,
        seed: int | None = None,
        tournament_id: str | None = None,
    ) -> GameRecord:
        """Create a new game record."""
        self.db.execute(
            """
            INSERT INTO games (
                id, player0_id, player1_id, winner, win_reason,
                score_p0, score_p1, turns, move_count, duration_ms,
                seed, tournament_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                game_id, player0_id, player1_id, winner, win_reason,
                score_p0, score_p1, turns, move_count, duration_ms,
                seed, tournament_id,
            ),
        )
        self.db.commit()
        return self.get_game(game_id)

    def get_game(self, game_id: str) -> GameRecord | None:
        """Get a game by ID."""
        row = self.db.execute(
            "SELECT * FROM games WHERE id = ?", (game_id,)
        ).fetchone()
        if row is None:
            return None
        return _row_to_game_record(row)

    def update_game(
        self,
        game_id: str,
        winner: int | None,
        win_reason: str | None,
        score_p0: int,
        score_p1: int,
        turns: int,
        move_count: int,
        duration_ms: float,
    ) -> GameRecord | None:
        """Update an existing game record with final results."""
        self.db.execute(
            """
            UPDATE games SET
                winner = ?,
                win_reason = ?,
                score_p0 = ?,
                score_p1 = ?,
                turns = ?,
                move_count = ?,
                duration_ms = ?
            WHERE id = ?
            """,
            (
                winner, win_reason, score_p0, score_p1,
                turns, move_count, duration_ms, game_id,
            ),
        )
        self.db.commit()
        return self.get_game(game_id)

    def list_games(
        self,
        player_id: str | None = None,
        tournament_id: str | None = None,
        limit: int = 100,
    ) -> list[GameRecord]:
        """List games with optional filters."""
        conditions = []
        params = []

        if player_id:
            conditions.append("(player0_id = ? OR player1_id = ?)")
            params.extend([player_id, player_id])
        if tournament_id:
            conditions.append("tournament_id = ?")
            params.append(tournament_id)

        where_clause = " AND ".join(conditions) if conditions else "1=1"
        params.append(limit)

        rows = self.db.execute(
            f"""
            SELECT * FROM games
            WHERE {where_clause}
            ORDER BY created_at DESC
            LIMIT ?
            """,
            tuple(params),
        ).fetchall()

        return [_row_to_game_record(row) for row in rows]

    def add_move(
        self,
        game_id: str,
        move_number: int,
        turn: int,
        player: int,
        phase: str,
        move_description: str,
        state_json: str | None = None,
        mcts_stats_json: str | None = None,
        llm_thinking_json: str | None = None,
    ) -> None:
        """Add a move record to a game."""
        self.db.execute(
            """
            INSERT INTO game_moves (
                game_id, move_number, turn, player, phase,
                move_description, state_json, mcts_stats_json, llm_thinking_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                game_id, move_number, turn, player, phase,
                move_description, state_json, mcts_stats_json, llm_thinking_json,
            ),
        )
        self.db.commit()

    def get_moves(self, game_id: str) -> list[MoveRecord]:
        """Get all moves for a game."""
        rows = self.db.execute(
            "SELECT * FROM game_moves WHERE game_id = ? ORDER BY move_number",
            (game_id,),
        ).fetchall()
        return [
            MoveRecord(
                id=row["id"],
                game_id=row["game_id"],
                move_number=row["move_number"],
                turn=row["turn"],
                player=row["player"],
                phase=row["phase"],
                move_description=row["move_description"],
                state_json=row["state_json"],
                mcts_stats_json=row["mcts_stats_json"],
                llm_thinking_json=row["llm_thinking_json"],
            )
            for row in rows
        ]

    def count_games(
        self,
        player_id: str | None = None,
        tournament_id: str | None = None,
    ) -> int:
        """Count games with optional filters."""
        conditions = []
        params = []

        if player_id:
            conditions.append("(player0_id = ? OR player1_id = ?)")
            params.extend([player_id, player_id])
        if tournament_id:
            conditions.append("tournament_id = ?")
            params.append(tournament_id)

        where_clause = " AND ".join(conditions) if conditions else "1=1"

        row = self.db.execute(
            f"SELECT COUNT(*) as cnt FROM games WHERE {where_clause}",
            tuple(params),
        ).fetchone()
        return row["cnt"]


class EloRepository:
    """Repository for ELO rating records."""

    def __init__(self, db: Database):
        self.db = db

    def get_latest_rating(
        self,
        player_id: str,
        rating_pool: str = "all",
    ) -> EloRecord | None:
        """Get the latest ELO rating for a player."""
        row = self.db.execute(
            """
            SELECT * FROM elo_ratings
            WHERE player_id = ? AND rating_pool = ?
            ORDER BY timestamp DESC, id DESC
            LIMIT 1
            """,
            (player_id, rating_pool),
        ).fetchone()
        if row is None:
            return None
        return _row_to_elo_record(row)

    def get_or_create_rating(
        self,
        player_id: str,
        rating_pool: str = "all",
        initial_rating: float = 1500.0,
    ) -> EloRecord:
        """Get existing rating or create initial rating."""
        existing = self.get_latest_rating(player_id, rating_pool)
        if existing:
            return existing
        return self.add_rating(player_id, initial_rating, rating_pool, 0)

    def add_rating(
        self,
        player_id: str,
        rating: float,
        rating_pool: str = "all",
        games_played: int = 0,
    ) -> EloRecord:
        """Add a new rating record."""
        cursor = self.db.execute(
            """
            INSERT INTO elo_ratings (player_id, rating, rating_pool, games_played)
            VALUES (?, ?, ?, ?)
            """,
            (player_id, rating, rating_pool, games_played),
        )
        self.db.commit()
        return self.get_latest_rating(player_id, rating_pool)

    def get_rating_history(
        self,
        player_id: str,
        rating_pool: str = "all",
        limit: int = 100,
    ) -> list[EloRecord]:
        """Get rating history for a player."""
        rows = self.db.execute(
            """
            SELECT * FROM elo_ratings
            WHERE player_id = ? AND rating_pool = ?
            ORDER BY timestamp DESC, id DESC
            LIMIT ?
            """,
            (player_id, rating_pool, limit),
        ).fetchall()
        return [_row_to_elo_record(row) for row in rows]

    def get_leaderboard(
        self,
        rating_pool: str = "all",
        limit: int = 20,
    ) -> list[EloRecord]:
        """Get leaderboard of top players by rating."""
        rows = self.db.execute(
            """
            SELECT e1.* FROM elo_ratings e1
            INNER JOIN (
                SELECT player_id, MAX(id) as max_id
                FROM elo_ratings
                WHERE rating_pool = ?
                GROUP BY player_id
            ) e2 ON e1.id = e2.max_id
            WHERE e1.rating_pool = ?
            ORDER BY e1.rating DESC
            LIMIT ?
            """,
            (rating_pool, rating_pool, limit),
        ).fetchall()
        return [_row_to_elo_record(row) for row in rows]


class CostRepository:
    """Repository for API cost records."""

    def __init__(self, db: Database):
        self.db = db

    def add_cost(
        self,
        provider: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        cost_usd: float,
        player_id: str | None = None,
        game_id: str | None = None,
        tournament_id: str | None = None,
    ) -> CostRecord:
        """Add an API cost record."""
        cursor = self.db.execute(
            """
            INSERT INTO api_costs (
                player_id, game_id, tournament_id, provider, model,
                input_tokens, output_tokens, cost_usd
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                player_id, game_id, tournament_id, provider, model,
                input_tokens, output_tokens, cost_usd,
            ),
        )
        self.db.commit()
        return CostRecord(
            id=cursor.lastrowid,
            player_id=player_id,
            game_id=game_id,
            tournament_id=tournament_id,
            provider=provider,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost_usd,
            timestamp=datetime.now(),
        )

    def get_tournament_spent(self, tournament_id: str) -> float:
        """Get total spent in a tournament."""
        row = self.db.execute(
            "SELECT COALESCE(SUM(cost_usd), 0) as total FROM api_costs WHERE tournament_id = ?",
            (tournament_id,),
        ).fetchone()
        return row["total"]

    def get_player_total_cost(self, player_id: str) -> float:
        """Get total cost for a player across all games."""
        row = self.db.execute(
            "SELECT COALESCE(SUM(cost_usd), 0) as total FROM api_costs WHERE player_id = ?",
            (player_id,),
        ).fetchone()
        return row["total"]

    def get_costs_by_tournament(self, tournament_id: str) -> list[CostRecord]:
        """Get all costs for a tournament."""
        rows = self.db.execute(
            "SELECT * FROM api_costs WHERE tournament_id = ? ORDER BY timestamp",
            (tournament_id,),
        ).fetchall()
        return [_row_to_cost_record(row) for row in rows]

    def get_cost_summary_by_model(
        self,
        tournament_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Get cost summary grouped by model."""
        if tournament_id:
            rows = self.db.execute(
                """
                SELECT provider, model,
                       SUM(input_tokens) as total_input,
                       SUM(output_tokens) as total_output,
                       SUM(cost_usd) as total_cost,
                       COUNT(*) as call_count
                FROM api_costs
                WHERE tournament_id = ?
                GROUP BY provider, model
                ORDER BY total_cost DESC
                """,
                (tournament_id,),
            ).fetchall()
        else:
            rows = self.db.execute(
                """
                SELECT provider, model,
                       SUM(input_tokens) as total_input,
                       SUM(output_tokens) as total_output,
                       SUM(cost_usd) as total_cost,
                       COUNT(*) as call_count
                FROM api_costs
                GROUP BY provider, model
                ORDER BY total_cost DESC
                """,
            ).fetchall()

        return [
            {
                "provider": row["provider"],
                "model": row["model"],
                "total_input_tokens": row["total_input"],
                "total_output_tokens": row["total_output"],
                "total_cost_usd": row["total_cost"],
                "call_count": row["call_count"],
            }
            for row in rows
        ]


class TournamentRepository:
    """Repository for tournament records."""

    def __init__(self, db: Database):
        self.db = db

    def create(
        self,
        tournament_id: str,
        name: str | None = None,
        config: dict[str, Any] | None = None,
        budget_usd: float | None = None,
    ) -> TournamentRecord:
        """Create a new tournament."""
        config_json = json.dumps(config or {})
        self.db.execute(
            """
            INSERT INTO tournaments (id, name, config_json, budget_usd, status)
            VALUES (?, ?, ?, ?, 'pending')
            """,
            (tournament_id, name, config_json, budget_usd),
        )
        self.db.commit()
        return self.get(tournament_id)

    def get(self, tournament_id: str) -> TournamentRecord | None:
        """Get a tournament by ID."""
        row = self.db.execute(
            "SELECT * FROM tournaments WHERE id = ?", (tournament_id,)
        ).fetchone()
        if row is None:
            return None
        return _row_to_tournament_record(row)

    def update_status(
        self,
        tournament_id: str,
        status: str,
        spent_usd: float | None = None,
    ) -> None:
        """Update tournament status."""
        if spent_usd is not None:
            self.db.execute(
                """
                UPDATE tournaments
                SET status = ?, spent_usd = ?,
                    started_at = CASE WHEN status = 'pending' AND ? = 'running' THEN CURRENT_TIMESTAMP ELSE started_at END,
                    completed_at = CASE WHEN ? IN ('completed', 'cancelled') THEN CURRENT_TIMESTAMP ELSE completed_at END
                WHERE id = ?
                """,
                (status, spent_usd, status, status, tournament_id),
            )
        else:
            self.db.execute(
                """
                UPDATE tournaments
                SET status = ?,
                    started_at = CASE WHEN status = 'pending' AND ? = 'running' THEN CURRENT_TIMESTAMP ELSE started_at END,
                    completed_at = CASE WHEN ? IN ('completed', 'cancelled') THEN CURRENT_TIMESTAMP ELSE completed_at END
                WHERE id = ?
                """,
                (status, status, status, tournament_id),
            )
        self.db.commit()

    def update_spent(self, tournament_id: str, spent_usd: float) -> None:
        """Update tournament spent amount."""
        self.db.execute(
            "UPDATE tournaments SET spent_usd = ? WHERE id = ?",
            (spent_usd, tournament_id),
        )
        self.db.commit()

    def list_tournaments(
        self,
        status: str | None = None,
        limit: int = 50,
    ) -> list[TournamentRecord]:
        """List tournaments with optional status filter."""
        if status:
            rows = self.db.execute(
                """
                SELECT * FROM tournaments
                WHERE status = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (status, limit),
            ).fetchall()
        else:
            rows = self.db.execute(
                "SELECT * FROM tournaments ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()

        return [_row_to_tournament_record(row) for row in rows]


def _parse_datetime(value: str | datetime | None) -> datetime | None:
    """Parse a datetime value from the database."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return datetime.now()


def _row_to_game_record(row: sqlite3.Row) -> GameRecord:
    """Convert a database row to a GameRecord."""
    return GameRecord(
        id=row["id"],
        player0_id=row["player0_id"],
        player1_id=row["player1_id"],
        winner=row["winner"],
        win_reason=row["win_reason"],
        score_p0=row["score_p0"],
        score_p1=row["score_p1"],
        turns=row["turns"],
        move_count=row["move_count"],
        duration_ms=row["duration_ms"],
        seed=row["seed"],
        tournament_id=row["tournament_id"],
        created_at=_parse_datetime(row["created_at"]),
    )


def _row_to_elo_record(row: sqlite3.Row) -> EloRecord:
    """Convert a database row to an EloRecord."""
    return EloRecord(
        id=row["id"],
        player_id=row["player_id"],
        rating=row["rating"],
        rating_pool=row["rating_pool"],
        games_played=row["games_played"],
        timestamp=_parse_datetime(row["timestamp"]),
    )


def _row_to_cost_record(row: sqlite3.Row) -> CostRecord:
    """Convert a database row to a CostRecord."""
    return CostRecord(
        id=row["id"],
        player_id=row["player_id"],
        game_id=row["game_id"],
        tournament_id=row["tournament_id"],
        provider=row["provider"],
        model=row["model"],
        input_tokens=row["input_tokens"],
        output_tokens=row["output_tokens"],
        cost_usd=row["cost_usd"],
        timestamp=_parse_datetime(row["timestamp"]),
    )


def _row_to_tournament_record(row: sqlite3.Row) -> TournamentRecord:
    """Convert a database row to a TournamentRecord."""
    return TournamentRecord(
        id=row["id"],
        name=row["name"],
        config_json=row["config_json"],
        status=row["status"],
        budget_usd=row["budget_usd"],
        spent_usd=row["spent_usd"],
        started_at=_parse_datetime(row["started_at"]),
        completed_at=_parse_datetime(row["completed_at"]),
        created_at=_parse_datetime(row["created_at"]),
    )
