"""ELO rating management for Cuttle tournaments."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

from db.database import Database, EloRepository, PlayerRepository

if TYPE_CHECKING:
    from core.player_identity import PlayerIdentity


@dataclass
class RatingUpdate:
    """Result of an ELO rating update."""
    player_id: str
    old_rating: float
    new_rating: float
    change: float
    games_played: int


@dataclass
class LeaderboardEntry:
    """An entry in the ELO leaderboard."""
    rank: int
    player_id: str
    display_name: str
    provider: str
    model_name: str
    rating: float
    games_played: int


class EloManager:
    """Manages ELO ratings for players in Cuttle tournaments.

    Supports multiple rating pools (e.g., 'all', 'llm-only', 'mcts-only')
    for fair comparisons between similar strategy types.
    """

    DEFAULT_RATING = 1500.0
    K_FACTOR = 32.0  # Standard K-factor for ELO calculations

    def __init__(self, db: Database, k_factor: float | None = None):
        """Initialize the ELO manager.

        Args:
            db: Database instance for persistence.
            k_factor: Optional custom K-factor (default: 32.0).
        """
        self.db = db
        self._elo_repo = EloRepository(db)
        self._player_repo = PlayerRepository(db)
        self._k_factor = k_factor or self.K_FACTOR

    def get_rating(
        self,
        player_id: str,
        pool: str = "all",
    ) -> float:
        """Get the current ELO rating for a player.

        Args:
            player_id: The player's unique ID.
            pool: Rating pool to query.

        Returns:
            Current ELO rating (default 1500.0 if never rated).
        """
        record = self._elo_repo.get_latest_rating(player_id, pool)
        return record.rating if record else self.DEFAULT_RATING

    def get_games_played(
        self,
        player_id: str,
        pool: str = "all",
    ) -> int:
        """Get the number of games played by a player in a pool.

        Args:
            player_id: The player's unique ID.
            pool: Rating pool to query.

        Returns:
            Number of games played.
        """
        record = self._elo_repo.get_latest_rating(player_id, pool)
        return record.games_played if record else 0

    def update_ratings(
        self,
        p0_id: str,
        p1_id: str,
        result: float,
        pool: str = "all",
    ) -> tuple[RatingUpdate, RatingUpdate]:
        """Update ELO ratings after a game.

        Args:
            p0_id: Player 0's unique ID.
            p1_id: Player 1's unique ID.
            result: Game result from player 0's perspective:
                    1.0 = p0 win, 0.0 = p1 win, 0.5 = draw.
            pool: Rating pool to update.

        Returns:
            Tuple of (p0_update, p1_update) with rating changes.
        """
        # Get current ratings
        p0_record = self._elo_repo.get_or_create_rating(
            p0_id, pool, self.DEFAULT_RATING
        )
        p1_record = self._elo_repo.get_or_create_rating(
            p1_id, pool, self.DEFAULT_RATING
        )

        r0 = p0_record.rating
        r1 = p1_record.rating

        # Calculate expected scores
        e0 = 1.0 / (1.0 + 10 ** ((r1 - r0) / 400.0))
        e1 = 1.0 - e0

        # Calculate new ratings
        new_r0 = r0 + self._k_factor * (result - e0)
        new_r1 = r1 + self._k_factor * ((1.0 - result) - e1)

        # Update database
        self._elo_repo.add_rating(
            p0_id, new_r0, pool, p0_record.games_played + 1
        )
        self._elo_repo.add_rating(
            p1_id, new_r1, pool, p1_record.games_played + 1
        )

        return (
            RatingUpdate(
                player_id=p0_id,
                old_rating=r0,
                new_rating=new_r0,
                change=new_r0 - r0,
                games_played=p0_record.games_played + 1,
            ),
            RatingUpdate(
                player_id=p1_id,
                old_rating=r1,
                new_rating=new_r1,
                change=new_r1 - r1,
                games_played=p1_record.games_played + 1,
            ),
        )

    def update_ratings_from_game(
        self,
        p0_id: str,
        p1_id: str,
        winner: int | None,
        pools: list[str] | None = None,
    ) -> dict[str, tuple[RatingUpdate, RatingUpdate]]:
        """Update ELO ratings from a game result.

        Args:
            p0_id: Player 0's unique ID.
            p1_id: Player 1's unique ID.
            winner: Winner (0, 1, or None for draw).
            pools: Optional list of pools to update (default: ['all']).

        Returns:
            Dict mapping pool name to (p0_update, p1_update) tuples.
        """
        # Convert winner to result value
        if winner == 0:
            result = 1.0
        elif winner == 1:
            result = 0.0
        else:
            result = 0.5

        pools = pools or ["all"]
        updates = {}

        for pool in pools:
            updates[pool] = self.update_ratings(p0_id, p1_id, result, pool)

        return updates

    def get_leaderboard(
        self,
        pool: str = "all",
        limit: int = 20,
    ) -> list[LeaderboardEntry]:
        """Get the ELO leaderboard.

        Args:
            pool: Rating pool to query.
            limit: Maximum number of entries to return.

        Returns:
            List of LeaderboardEntry sorted by rating descending.
        """
        elo_records = self._elo_repo.get_leaderboard(pool, limit)

        entries = []
        for rank, record in enumerate(elo_records, 1):
            # Get player details
            player = self._player_repo.get(record.player_id)
            if player:
                entries.append(
                    LeaderboardEntry(
                        rank=rank,
                        player_id=record.player_id,
                        display_name=player.display_name or player.model_name,
                        provider=player.provider,
                        model_name=player.model_name,
                        rating=record.rating,
                        games_played=record.games_played,
                    )
                )

        return entries

    def get_rating_history(
        self,
        player_id: str,
        pool: str = "all",
        limit: int = 100,
    ) -> list[tuple[datetime, float, int]]:
        """Get rating history for a player.

        Args:
            player_id: The player's unique ID.
            pool: Rating pool to query.
            limit: Maximum number of entries to return.

        Returns:
            List of (timestamp, rating, games_played) tuples, newest first.
        """
        records = self._elo_repo.get_rating_history(player_id, pool, limit)
        return [
            (record.timestamp, record.rating, record.games_played)
            for record in records
        ]

    def get_matchup_probabilities(
        self,
        p0_id: str,
        p1_id: str,
        pool: str = "all",
    ) -> tuple[float, float]:
        """Get expected win probabilities for a matchup.

        Args:
            p0_id: Player 0's unique ID.
            p1_id: Player 1's unique ID.
            pool: Rating pool to use.

        Returns:
            Tuple of (p0_expected, p1_expected) probabilities.
        """
        r0 = self.get_rating(p0_id, pool)
        r1 = self.get_rating(p1_id, pool)

        e0 = 1.0 / (1.0 + 10 ** ((r1 - r0) / 400.0))
        e1 = 1.0 - e0

        return (e0, e1)

    def determine_rating_pools(
        self,
        p0_provider: str,
        p1_provider: str,
    ) -> list[str]:
        """Determine which rating pools a game should update.

        Args:
            p0_provider: Provider for player 0.
            p1_provider: Provider for player 1.

        Returns:
            List of pool names to update.
        """
        pools = ["all"]

        # LLM-only pool
        llm_providers = {"anthropic", "openrouter", "openai", "ollama"}
        if p0_provider in llm_providers and p1_provider in llm_providers:
            pools.append("llm-only")

        # MCTS-only pool
        mcts_providers = {"mcts", "ismcts"}
        if p0_provider in mcts_providers and p1_provider in mcts_providers:
            pools.append("mcts-only")

        return pools
