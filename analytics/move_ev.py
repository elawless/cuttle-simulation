"""Move Expected Value analysis tools for Cuttle.

Provides functions to analyze positions using MCTS and extract
win probabilities for each legal move.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING

from cuttle_engine.move_generator import generate_legal_moves
from strategies.mcts import MCTSStrategy
from strategies.ismcts import ISMCTSStrategy

if TYPE_CHECKING:
    from cuttle_engine.moves import Move
    from cuttle_engine.state import GameState


@dataclass
class MoveEV:
    """Expected value analysis for a single move.

    Attributes:
        move: The move being analyzed.
        win_rate: Estimated probability of winning after this move.
        visit_count: Number of MCTS visits (higher = more confident).
        confidence_interval: 95% confidence interval for win_rate.
        rank: Rank among all moves (1 = best).
    """

    move: Move
    win_rate: float
    visit_count: int
    confidence_interval: tuple[float, float]
    rank: int

    @property
    def ev_label(self) -> str:
        """Human-readable EV label."""
        return f"{self.win_rate:.1%} ({self.visit_count} visits)"

    def __str__(self) -> str:
        low, high = self.confidence_interval
        return (
            f"#{self.rank}: {self.move} - "
            f"EV: {self.win_rate:.1%} [{low:.1%}, {high:.1%}] "
            f"({self.visit_count} visits)"
        )


@dataclass
class PositionAnalysis:
    """Complete analysis of a game position.

    Attributes:
        state: The analyzed game state.
        move_evs: List of MoveEV for each legal move, sorted by win_rate.
        best_move: The recommended move.
        position_value: Estimated win probability for the acting player.
        ev_spread: Difference between best and worst move EVs.
        is_critical: Whether this is a critical decision point.
    """

    state: GameState
    move_evs: list[MoveEV]
    best_move: Move
    position_value: float
    ev_spread: float
    is_critical: bool

    def __str__(self) -> str:
        lines = [
            f"Position Value: {self.position_value:.1%}",
            f"EV Spread: {self.ev_spread:.1%}",
            f"Critical: {'Yes' if self.is_critical else 'No'}",
            f"Best Move: {self.best_move}",
            "",
            "All Moves:",
        ]
        for mev in self.move_evs[:10]:  # Top 10
            lines.append(f"  {mev}")
        if len(self.move_evs) > 10:
            lines.append(f"  ... and {len(self.move_evs) - 10} more")
        return "\n".join(lines)


def wilson_score_interval(
    wins: float, total: int, confidence: float = 0.95
) -> tuple[float, float]:
    """Calculate Wilson score confidence interval for a proportion.

    Better than normal approximation for small samples or extreme proportions.

    Args:
        wins: Number of wins (can be fractional).
        total: Total trials.
        confidence: Confidence level (default 95%).

    Returns:
        (lower, upper) bounds of confidence interval.
    """
    if total == 0:
        return (0.0, 1.0)

    # Z-score for confidence level
    z = 1.96 if confidence == 0.95 else 1.645 if confidence == 0.90 else 2.576

    p_hat = wins / total
    denominator = 1 + z * z / total

    center = (p_hat + z * z / (2 * total)) / denominator
    margin = z * math.sqrt(p_hat * (1 - p_hat) / total + z * z / (4 * total * total)) / denominator

    return (max(0.0, center - margin), min(1.0, center + margin))


def analyze_position(
    state: GameState,
    iterations: int = 10000,
    use_ismcts: bool = False,
    exploration_constant: float = 1.414,
    critical_threshold: float = 0.1,
    seed: int | None = None,
) -> PositionAnalysis:
    """Analyze a position using MCTS and return EV for each legal move.

    Args:
        state: Game state to analyze.
        iterations: Number of MCTS iterations.
        use_ismcts: Whether to use ISMCTS for hidden information.
        exploration_constant: UCB1 exploration parameter.
        critical_threshold: EV spread threshold for "critical" positions.
        seed: Random seed for reproducibility.

    Returns:
        PositionAnalysis with detailed move EVs.
    """
    legal_moves = generate_legal_moves(state)
    if not legal_moves:
        raise ValueError("No legal moves in this position")

    # Create appropriate strategy
    if use_ismcts:
        strategy = ISMCTSStrategy(
            iterations=iterations,
            exploration_constant=exploration_constant,
            seed=seed,
        )
    else:
        strategy = MCTSStrategy(
            iterations=iterations,
            exploration_constant=exploration_constant,
            seed=seed,
        )

    # Get statistics
    stats = strategy.get_move_statistics(state)

    # Convert to MoveEV objects
    move_evs = []
    for move, stat in stats.items():
        win_rate = stat["win_rate"]
        visits = stat["visits"]
        ci = wilson_score_interval(stat["wins"], visits)

        move_evs.append(MoveEV(
            move=move,
            win_rate=win_rate,
            visit_count=visits,
            confidence_interval=ci,
            rank=0,  # Will be set after sorting
        ))

    # Sort by win rate (descending)
    move_evs.sort(key=lambda x: x.win_rate, reverse=True)

    # Assign ranks
    for i, mev in enumerate(move_evs):
        object.__setattr__(mev, 'rank', i + 1)

    # Calculate position metrics
    if move_evs:
        best_move = move_evs[0].move
        position_value = move_evs[0].win_rate
        ev_spread = move_evs[0].win_rate - move_evs[-1].win_rate
    else:
        best_move = legal_moves[0]
        position_value = 0.5
        ev_spread = 0.0

    # A position is "critical" if move choice significantly impacts EV
    is_critical = ev_spread >= critical_threshold

    return PositionAnalysis(
        state=state,
        move_evs=move_evs,
        best_move=best_move,
        position_value=position_value,
        ev_spread=ev_spread,
        is_critical=is_critical,
    )


def compare_moves(
    state: GameState,
    moves: list[Move],
    iterations: int = 5000,
    seed: int | None = None,
) -> dict[Move, MoveEV]:
    """Compare specific moves in a position.

    Useful when you want to compare a subset of moves rather than all legal moves.

    Args:
        state: Game state.
        moves: Specific moves to compare.
        iterations: MCTS iterations.
        seed: Random seed.

    Returns:
        Dict mapping each move to its MoveEV.
    """
    analysis = analyze_position(state, iterations=iterations, seed=seed)

    result = {}
    for mev in analysis.move_evs:
        if mev.move in moves:
            result[mev.move] = mev

    return result


def estimate_position_value(
    state: GameState,
    player: int,
    iterations: int = 2000,
    seed: int | None = None,
) -> tuple[float, tuple[float, float]]:
    """Estimate the win probability for a player in a position.

    Uses MCTS to estimate how likely the player is to win from this state,
    assuming optimal play.

    Args:
        state: Game state to evaluate.
        player: Player index (0 or 1) to evaluate for.
        iterations: MCTS iterations.
        seed: Random seed.

    Returns:
        (win_probability, confidence_interval)
    """
    if state.is_game_over:
        if state.winner == player:
            return (1.0, (1.0, 1.0))
        elif state.winner is not None:
            return (0.0, (0.0, 0.0))
        return (0.5, (0.5, 0.5))  # Draw

    analysis = analyze_position(state, iterations=iterations, seed=seed)

    # Position value is from acting player's perspective
    # Adjust if we're evaluating for the other player
    from cuttle_engine.state import GamePhase

    if state.phase == GamePhase.COUNTER:
        acting = state.counter_state.waiting_for_player
    elif state.phase == GamePhase.DISCARD_FOUR:
        acting = state.four_state.player
    elif state.phase == GamePhase.RESOLVE_SEVEN:
        acting = state.seven_state.player
    else:
        acting = state.current_player

    if acting == player:
        value = analysis.position_value
    else:
        value = 1.0 - analysis.position_value

    # Calculate aggregate confidence interval
    if analysis.move_evs:
        best = analysis.move_evs[0]
        ci = best.confidence_interval
        if acting != player:
            ci = (1.0 - ci[1], 1.0 - ci[0])
    else:
        ci = (0.0, 1.0)

    return (value, ci)
