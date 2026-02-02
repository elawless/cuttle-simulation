"""Tournament system for comparing Cuttle strategies.

Provides tools for running multi-strategy tournaments with statistical
analysis including win rates, confidence intervals, and ELO ratings.
"""

from __future__ import annotations

import math
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from simulation.runner import GameRunner, GameResult

if TYPE_CHECKING:
    from strategies.base import Strategy


@dataclass
class MatchResult:
    """Result of a match (series of games) between two strategies.

    Attributes:
        strategy_a: Name of first strategy.
        strategy_b: Name of second strategy.
        wins_a: Wins by strategy A.
        wins_b: Wins by strategy B.
        draws: Number of draws.
        total_games: Total games played.
        avg_game_length: Average number of moves per game.
        avg_turns: Average turns per game.
    """

    strategy_a: str
    strategy_b: str
    wins_a: int
    wins_b: int
    draws: int
    total_games: int
    avg_game_length: float
    avg_turns: float

    @property
    def win_rate_a(self) -> float:
        """Win rate for strategy A."""
        if self.total_games == 0:
            return 0.0
        return self.wins_a / self.total_games

    @property
    def win_rate_b(self) -> float:
        """Win rate for strategy B."""
        if self.total_games == 0:
            return 0.0
        return self.wins_b / self.total_games

    def confidence_interval(self, confidence: float = 0.95) -> tuple[float, float]:
        """Wilson score confidence interval for strategy A's win rate."""
        if self.total_games == 0:
            return (0.0, 1.0)

        z = 1.96 if confidence == 0.95 else 1.645 if confidence == 0.90 else 2.576
        p_hat = self.win_rate_a
        n = self.total_games

        denominator = 1 + z * z / n
        center = (p_hat + z * z / (2 * n)) / denominator
        margin = z * math.sqrt(p_hat * (1 - p_hat) / n + z * z / (4 * n * n)) / denominator

        return (max(0.0, center - margin), min(1.0, center + margin))

    def __str__(self) -> str:
        ci = self.confidence_interval()
        return (
            f"{self.strategy_a} vs {self.strategy_b}: "
            f"{self.wins_a}-{self.wins_b} ({self.draws} draws) "
            f"[{self.win_rate_a:.1%} win rate, 95% CI: {ci[0]:.1%}-{ci[1]:.1%}]"
        )


@dataclass
class TournamentResult:
    """Results of a complete tournament.

    Attributes:
        strategies: List of strategy names.
        matches: All match results.
        elo_ratings: ELO ratings for each strategy.
        win_matrix: Win counts (win_matrix[a][b] = wins for a vs b).
        total_games: Total games played.
        duration_seconds: Total tournament duration.
    """

    strategies: list[str]
    matches: list[MatchResult]
    elo_ratings: dict[str, float]
    win_matrix: dict[str, dict[str, int]]
    total_games: int
    duration_seconds: float

    def get_match(self, strategy_a: str, strategy_b: str) -> MatchResult | None:
        """Get the match result between two strategies."""
        for match in self.matches:
            if (match.strategy_a == strategy_a and match.strategy_b == strategy_b) or \
               (match.strategy_a == strategy_b and match.strategy_b == strategy_a):
                return match
        return None

    def standings(self) -> list[tuple[str, float, int, int]]:
        """Get tournament standings.

        Returns:
            List of (strategy, elo, wins, losses) sorted by ELO.
        """
        standings = []
        for strategy in self.strategies:
            wins = sum(self.win_matrix[strategy].values())
            losses = sum(
                self.win_matrix[other][strategy]
                for other in self.strategies
                if other != strategy
            )
            standings.append((strategy, self.elo_ratings[strategy], wins, losses))

        return sorted(standings, key=lambda x: x[1], reverse=True)

    def __str__(self) -> str:
        lines = [
            "Tournament Results",
            "=" * 50,
            "",
            "Standings:",
        ]

        for rank, (strategy, elo, wins, losses) in enumerate(self.standings(), 1):
            lines.append(f"  {rank}. {strategy}: ELO {elo:.0f} ({wins}W-{losses}L)")

        lines.extend(["", "Match Results:"])
        for match in self.matches:
            lines.append(f"  {match}")

        lines.append(f"\nTotal: {self.total_games} games in {self.duration_seconds:.1f}s")
        return "\n".join(lines)


@dataclass
class MoveTypeDistribution:
    """Distribution of move types for a strategy."""

    strategy: str
    total_moves: int
    distribution: dict[str, int] = field(default_factory=dict)

    def percentage(self, move_type: str) -> float:
        """Get percentage of moves that were this type."""
        if self.total_moves == 0:
            return 0.0
        return self.distribution.get(move_type, 0) / self.total_moves


def run_match(
    strategy_a: Strategy,
    strategy_b: Strategy,
    num_games: int,
    start_seed: int = 0,
    alternate_start: bool = True,
) -> MatchResult:
    """Run a match (series of games) between two strategies.

    Args:
        strategy_a: First strategy.
        strategy_b: Second strategy.
        num_games: Number of games to play.
        start_seed: Starting random seed.
        alternate_start: Whether to alternate who starts each game.

    Returns:
        MatchResult with statistics.
    """
    wins_a = 0
    wins_b = 0
    draws = 0
    total_moves = 0
    total_turns = 0

    for i in range(num_games):
        seed = start_seed + i

        # Alternate starting player
        if alternate_start and i % 2 == 1:
            runner = GameRunner(strategy_b, strategy_a, log_moves=False)
            result, _ = runner.run_game(seed=seed)
            # Flip winner perspective
            if result.winner == 0:
                wins_b += 1
            elif result.winner == 1:
                wins_a += 1
            else:
                draws += 1
        else:
            runner = GameRunner(strategy_a, strategy_b, log_moves=False)
            result, _ = runner.run_game(seed=seed)
            if result.winner == 0:
                wins_a += 1
            elif result.winner == 1:
                wins_b += 1
            else:
                draws += 1

        total_moves += result.move_count
        total_turns += result.turns

    return MatchResult(
        strategy_a=strategy_a.name,
        strategy_b=strategy_b.name,
        wins_a=wins_a,
        wins_b=wins_b,
        draws=draws,
        total_games=num_games,
        avg_game_length=total_moves / num_games if num_games > 0 else 0,
        avg_turns=total_turns / num_games if num_games > 0 else 0,
    )


def calculate_elo_ratings(
    matches: list[MatchResult],
    initial_elo: float = 1500.0,
    k_factor: float = 32.0,
) -> dict[str, float]:
    """Calculate ELO ratings from match results.

    Uses iterative ELO calculation to converge on stable ratings.

    Args:
        matches: List of match results.
        initial_elo: Starting ELO for all players.
        k_factor: ELO K-factor (higher = more volatile).

    Returns:
        Dict mapping strategy name to ELO rating.
    """
    # Collect all strategies
    strategies = set()
    for match in matches:
        strategies.add(match.strategy_a)
        strategies.add(match.strategy_b)

    # Initialize ratings
    ratings = {s: initial_elo for s in strategies}

    # Iterate to convergence (or max iterations)
    for _ in range(100):
        old_ratings = ratings.copy()

        for match in matches:
            a, b = match.strategy_a, match.strategy_b
            ra, rb = ratings[a], ratings[b]

            # Expected scores
            ea = 1 / (1 + 10 ** ((rb - ra) / 400))
            eb = 1 - ea

            # Actual scores (normalized)
            total = match.total_games
            if total == 0:
                continue
            sa = (match.wins_a + 0.5 * match.draws) / total
            sb = (match.wins_b + 0.5 * match.draws) / total

            # Update ratings
            ratings[a] += k_factor * total * (sa - ea) / len(matches)
            ratings[b] += k_factor * total * (sb - eb) / len(matches)

        # Check convergence
        max_change = max(abs(ratings[s] - old_ratings[s]) for s in strategies)
        if max_change < 0.1:
            break

    return ratings


def run_tournament(
    strategies: list[Strategy],
    games_per_match: int = 100,
    start_seed: int = 0,
) -> TournamentResult:
    """Run a round-robin tournament between strategies.

    Each pair of strategies plays games_per_match games.

    Args:
        strategies: List of strategies to compete.
        games_per_match: Number of games per matchup.
        start_seed: Starting random seed.

    Returns:
        TournamentResult with all statistics.
    """
    start_time = time.perf_counter()

    matches = []
    win_matrix = defaultdict(lambda: defaultdict(int))
    seed_offset = 0

    # Round robin
    for i, strat_a in enumerate(strategies):
        for strat_b in strategies[i + 1:]:
            match = run_match(
                strat_a, strat_b,
                num_games=games_per_match,
                start_seed=start_seed + seed_offset,
            )
            matches.append(match)
            win_matrix[match.strategy_a][match.strategy_b] = match.wins_a
            win_matrix[match.strategy_b][match.strategy_a] = match.wins_b
            seed_offset += games_per_match

    # Calculate ELO ratings
    elo_ratings = calculate_elo_ratings(matches)

    duration = time.perf_counter() - start_time
    total_games = sum(m.total_games for m in matches)

    return TournamentResult(
        strategies=[s.name for s in strategies],
        matches=matches,
        elo_ratings=elo_ratings,
        win_matrix=dict(win_matrix),
        total_games=total_games,
        duration_seconds=duration,
    )


def run_gauntlet(
    challenger: Strategy,
    opponents: list[Strategy],
    games_per_opponent: int = 100,
    start_seed: int = 0,
) -> list[MatchResult]:
    """Run a gauntlet where one strategy plays against multiple opponents.

    Useful for testing a new strategy against established baselines.

    Args:
        challenger: Strategy to test.
        opponents: List of opponent strategies.
        games_per_opponent: Games per matchup.
        start_seed: Starting seed.

    Returns:
        List of MatchResult for each opponent.
    """
    results = []
    seed_offset = 0

    for opponent in opponents:
        match = run_match(
            challenger, opponent,
            num_games=games_per_opponent,
            start_seed=start_seed + seed_offset,
        )
        results.append(match)
        seed_offset += games_per_opponent

    return results


def analyze_move_distribution(
    strategy: Strategy,
    opponent: Strategy,
    num_games: int = 100,
    start_seed: int = 0,
) -> MoveTypeDistribution:
    """Analyze the distribution of move types made by a strategy.

    Args:
        strategy: Strategy to analyze.
        opponent: Opponent to play against.
        num_games: Number of games to sample.
        start_seed: Starting seed.

    Returns:
        MoveTypeDistribution with move type counts.
    """
    from cuttle_engine.moves import MoveType

    distribution = defaultdict(int)
    total_moves = 0

    for i in range(num_games):
        runner = GameRunner(strategy, opponent, log_moves=True)
        result, log = runner.run_game(seed=start_seed + i)

        if log:
            for move_record in log.moves:
                if move_record.player == 0:  # Strategy is player 0
                    # Categorize move
                    move_str = move_record.move
                    if "Draw" in move_str:
                        move_type = "Draw"
                    elif "points" in move_str.lower() and "Play" in move_str:
                        move_type = "PlayPoints"
                    elif "Scuttle" in move_str:
                        move_type = "Scuttle"
                    elif "one-off" in move_str.lower():
                        move_type = "OneOff"
                    elif "steal" in move_str.lower() or "permanent" in move_str.lower():
                        move_type = "Permanent"
                    elif "Counter" in move_str:
                        move_type = "Counter"
                    elif "Decline" in move_str:
                        move_type = "DeclineCounter"
                    elif "Pass" in move_str:
                        move_type = "Pass"
                    elif "Discard" in move_str:
                        move_type = "Discard"
                    elif "Seven:" in move_str:
                        move_type = "ResolveSeven"
                    else:
                        move_type = "Other"

                    distribution[move_type] += 1
                    total_moves += 1

    return MoveTypeDistribution(
        strategy=strategy.name,
        total_moves=total_moves,
        distribution=dict(distribution),
    )


def compare_strategies_detailed(
    strategies: list[Strategy],
    games_per_match: int = 100,
    start_seed: int = 0,
) -> dict:
    """Run detailed comparison between strategies.

    Returns tournament results plus move distributions.

    Args:
        strategies: Strategies to compare.
        games_per_match: Games per matchup.
        start_seed: Starting seed.

    Returns:
        Dict with 'tournament' and 'distributions' keys.
    """
    # Run tournament
    tournament = run_tournament(strategies, games_per_match, start_seed)

    # Analyze move distributions (each strategy vs first strategy as baseline)
    baseline = strategies[0]
    distributions = {}

    for strategy in strategies:
        if strategy != baseline:
            dist = analyze_move_distribution(
                strategy, baseline,
                num_games=min(50, games_per_match),
                start_seed=start_seed,
            )
            distributions[strategy.name] = dist

    # Also analyze baseline vs second strategy (if exists)
    if len(strategies) > 1:
        dist = analyze_move_distribution(
            baseline, strategies[1],
            num_games=min(50, games_per_match),
            start_seed=start_seed,
        )
        distributions[baseline.name] = dist

    return {
        "tournament": tournament,
        "distributions": distributions,
    }
