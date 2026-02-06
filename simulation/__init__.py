"""Simulation and tournament running."""

from simulation.runner import (
    GameResult,
    GameLog,
    GameRunner,
    MoveRecord,
    save_game_log,
    run_batch,
)
from simulation.tournament import (
    MatchResult,
    TournamentResult,
    MoveTypeDistribution,
    run_match,
    run_tournament,
    run_gauntlet,
    analyze_move_distribution,
    compare_strategies_detailed,
)
from simulation.llm_tournament import (
    LLMTournamentRunner,
    TournamentConfig,
    StrategySpec,
)

__all__ = [
    # runner
    "GameResult",
    "GameLog",
    "GameRunner",
    "MoveRecord",
    "save_game_log",
    "run_batch",
    # tournament
    "MatchResult",
    "TournamentResult",
    "MoveTypeDistribution",
    "run_match",
    "run_tournament",
    "run_gauntlet",
    "analyze_move_distribution",
    "compare_strategies_detailed",
    # llm_tournament
    "LLMTournamentRunner",
    "TournamentConfig",
    "StrategySpec",
]
