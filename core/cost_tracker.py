"""Cost tracking with tournament budget enforcement."""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING

from core.pricing import get_cost
from db.database import Database, CostRepository, TournamentRepository

if TYPE_CHECKING:
    pass


class BudgetExceededError(Exception):
    """Raised when tournament budget is exceeded."""

    def __init__(self, budget: float, spent: float, attempted: float):
        self.budget = budget
        self.spent = spent
        self.attempted = attempted
        super().__init__(
            f"Budget exceeded: ${spent:.4f} spent of ${budget:.4f} budget, "
            f"attempted to add ${attempted:.4f}"
        )


class CostTracker:
    """Track API costs with tournament budget enforcement.

    Thread-safe cost tracking with real-time budget monitoring.
    Raises BudgetExceededError when tournament budget would be exceeded.
    """

    def __init__(
        self,
        db: Database,
        tournament_id: str | None = None,
        budget_usd: float | None = None,
        player_id: str | None = None,
    ):
        """Initialize the cost tracker.

        Args:
            db: Database instance for persistence.
            tournament_id: Optional tournament ID for budget tracking.
            budget_usd: Optional budget limit in USD.
            player_id: Optional default player ID for cost attribution.
        """
        self.db = db
        self.tournament_id = tournament_id
        self.budget_usd = budget_usd
        self.player_id = player_id

        self._cost_repo = CostRepository(db)
        self._tournament_repo = TournamentRepository(db)
        self._lock = threading.Lock()

        # Cache for current spent amount
        self._cached_spent: float | None = None

    def record_cost(
        self,
        provider: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        player_id: str | None = None,
        game_id: str | None = None,
    ) -> float:
        """Record an API cost and check budget.

        Args:
            provider: API provider (e.g., 'anthropic', 'openrouter').
            model: Model name.
            input_tokens: Number of input tokens.
            output_tokens: Number of output tokens.
            player_id: Optional player ID (uses default if not provided).
            game_id: Optional game ID for attribution.

        Returns:
            The cost in USD.

        Raises:
            BudgetExceededError: If adding this cost would exceed budget.
        """
        cost_usd = get_cost(model, input_tokens, output_tokens)
        player_id = player_id or self.player_id

        with self._lock:
            # Check budget before recording
            if self.budget_usd is not None and self.tournament_id:
                current_spent = self.get_tournament_spent()
                if current_spent + cost_usd > self.budget_usd:
                    raise BudgetExceededError(
                        self.budget_usd, current_spent, cost_usd
                    )

            # Record the cost
            self._cost_repo.add_cost(
                provider=provider,
                model=model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cost_usd=cost_usd,
                player_id=player_id,
                game_id=game_id,
                tournament_id=self.tournament_id,
            )

            # Update cached spent
            if self._cached_spent is not None:
                self._cached_spent += cost_usd

            # Update tournament spent if tracking
            if self.tournament_id:
                new_spent = self.get_tournament_spent()
                self._tournament_repo.update_spent(self.tournament_id, new_spent)

        return cost_usd

    def check_budget(self) -> bool:
        """Check if within budget.

        Returns:
            True if under budget or no budget set.
        """
        if self.budget_usd is None:
            return True
        return self.get_tournament_spent() < self.budget_usd

    def get_remaining_budget(self) -> float | None:
        """Get remaining budget in USD.

        Returns:
            Remaining budget, or None if no budget set.
        """
        if self.budget_usd is None:
            return None
        return self.budget_usd - self.get_tournament_spent()

    def get_tournament_spent(self) -> float:
        """Get total spent in current tournament.

        Returns:
            Total cost in USD for the tournament.
        """
        if self.tournament_id is None:
            return 0.0

        if self._cached_spent is None:
            self._cached_spent = self._cost_repo.get_tournament_spent(
                self.tournament_id
            )
        return self._cached_spent

    def get_player_total_cost(self, player_id: str | None = None) -> float:
        """Get total cost for a player across all games.

        Args:
            player_id: Player ID (uses default if not provided).

        Returns:
            Total cost in USD.
        """
        player_id = player_id or self.player_id
        if player_id is None:
            return 0.0
        return self._cost_repo.get_player_total_cost(player_id)

    def get_cost_summary(self) -> dict:
        """Get cost summary for the tournament.

        Returns:
            Dict with cost breakdown by model.
        """
        summary = self._cost_repo.get_cost_summary_by_model(self.tournament_id)
        total = sum(s["total_cost_usd"] for s in summary)

        return {
            "tournament_id": self.tournament_id,
            "budget_usd": self.budget_usd,
            "total_spent_usd": total,
            "remaining_usd": (self.budget_usd - total) if self.budget_usd else None,
            "by_model": summary,
        }

    def invalidate_cache(self) -> None:
        """Invalidate the cached spent amount."""
        with self._lock:
            self._cached_spent = None


def create_tracker_for_player(
    db: Database,
    player_id: str,
    tournament_id: str | None = None,
    budget_usd: float | None = None,
) -> CostTracker:
    """Create a cost tracker for a specific player.

    Args:
        db: Database instance.
        player_id: Player ID for cost attribution.
        tournament_id: Optional tournament ID.
        budget_usd: Optional budget limit.

    Returns:
        Configured CostTracker instance.
    """
    return CostTracker(
        db=db,
        tournament_id=tournament_id,
        budget_usd=budget_usd,
        player_id=player_id,
    )
