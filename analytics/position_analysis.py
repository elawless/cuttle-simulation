"""Position analysis tools for identifying critical decision points.

Provides functions to analyze game logs and identify positions where
move choice had the highest impact on game outcome.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from cuttle_engine.cards import Card, Rank, Suit
from cuttle_engine.state import (
    GamePhase,
    GameState,
    PlayerState,
    CounterState,
    SevenState,
    FourState,
)
from analytics.move_ev import analyze_position, PositionAnalysis

if TYPE_CHECKING:
    from cuttle_engine.moves import Move


@dataclass
class CriticalPosition:
    """A game position identified as a critical decision point.

    Attributes:
        game_id: ID of the game this position came from.
        turn: Turn number in the game.
        move_number: Move number within the game.
        state: The game state at this position.
        analysis: MCTS analysis of the position.
        actual_move: The move that was actually played.
        actual_move_rank: Rank of actual move among all moves.
        ev_loss: EV lost by playing actual move vs best move.
        was_winning: Whether the player who moved went on to win.
    """

    game_id: str
    turn: int
    move_number: int
    state: GameState
    analysis: PositionAnalysis
    actual_move: str  # String representation
    actual_move_rank: int
    ev_loss: float
    was_winning: bool

    def __str__(self) -> str:
        return (
            f"Critical Position (Game {self.game_id[:8]}, Turn {self.turn}):\n"
            f"  Best Move: {self.analysis.best_move} (EV: {self.analysis.position_value:.1%})\n"
            f"  Actual Move: {self.actual_move} (Rank #{self.actual_move_rank}, EV loss: {self.ev_loss:.1%})\n"
            f"  Player {'won' if self.was_winning else 'lost'} the game\n"
            f"  EV Spread: {self.analysis.ev_spread:.1%}"
        )


def reconstruct_state_from_dict(state_dict: dict) -> GameState | None:
    """Reconstruct a GameState from a logged state dictionary.

    Note: This is a best-effort reconstruction - some information may be lost.

    Args:
        state_dict: Dictionary from game log.

    Returns:
        Reconstructed GameState or None if reconstruction fails.
    """
    try:
        def parse_card(s: str) -> Card:
            """Parse card string like '5♠' into Card object."""
            rank_map = {
                'A': Rank.ACE, '2': Rank.TWO, '3': Rank.THREE, '4': Rank.FOUR,
                '5': Rank.FIVE, '6': Rank.SIX, '7': Rank.SEVEN, '8': Rank.EIGHT,
                '9': Rank.NINE, '10': Rank.TEN, 'J': Rank.JACK, 'Q': Rank.QUEEN,
                'K': Rank.KING,
            }
            suit_map = {
                '♣': Suit.CLUBS, '♦': Suit.DIAMONDS,
                '♥': Suit.HEARTS, '♠': Suit.SPADES,
            }

            # Handle 10 specially
            if s.startswith('10'):
                rank = Rank.TEN
                suit_char = s[2]
            else:
                rank = rank_map[s[0]]
                suit_char = s[1]

            suit = suit_map[suit_char]
            return Card(rank, suit)

        players = []
        for p_dict in state_dict["players"]:
            hand = tuple(parse_card(c) for c in p_dict["hand"])
            points = tuple(parse_card(c) for c in p_dict["points"])
            permanents = tuple(parse_card(c) for c in p_dict["permanents"])
            jacks = tuple(
                (parse_card(j), parse_card(s))
                for j, s in p_dict.get("jacks", [])
            )
            players.append(PlayerState(
                hand=hand,
                points_field=points,
                permanents=permanents,
                jacks=jacks,
            ))

        phase = GamePhase[state_dict["phase"]]

        return GameState(
            players=(players[0], players[1]),
            deck=(),  # Deck order unknown from logs
            scrap=(),  # Could reconstruct but not critical
            current_player=state_dict["current_player"],
            phase=phase,
            turn_number=state_dict["turn"],
        )

    except Exception:
        return None


def find_critical_positions(
    game_log_path: str | Path,
    mcts_iterations: int = 2000,
    min_ev_spread: float = 0.1,
    max_positions: int = 10,
    seed: int | None = None,
) -> list[CriticalPosition]:
    """Find critical decision points in a game log.

    Analyzes each position in the game and identifies those where:
    1. The EV spread between best and worst moves is high
    2. The actual move played was not optimal

    Args:
        game_log_path: Path to game log JSON file.
        mcts_iterations: MCTS iterations for analysis.
        min_ev_spread: Minimum EV spread to consider a position critical.
        max_positions: Maximum number of positions to return.
        seed: Random seed for MCTS.

    Returns:
        List of CriticalPosition objects, sorted by EV loss.
    """
    with open(game_log_path) as f:
        log = json.load(f)

    game_id = log["game_id"]
    winner = log["result"]["winner"] if log.get("result") else None

    critical_positions = []

    for i, move_record in enumerate(log["moves"]):
        # Get state BEFORE this move was made
        if i == 0:
            state_dict = log["initial_state"]
        else:
            state_dict = log["moves"][i - 1]["state_after"]

        state = reconstruct_state_from_dict(state_dict)
        if state is None:
            continue

        # Skip terminal states
        if state.is_game_over:
            continue

        # Analyze the position
        try:
            analysis = analyze_position(
                state,
                iterations=mcts_iterations,
                seed=seed,
            )
        except (ValueError, Exception):
            continue

        # Skip if not critical enough
        if analysis.ev_spread < min_ev_spread:
            continue

        # Find the actual move in our analysis
        actual_move_str = move_record["move"]
        actual_rank = None
        actual_ev = None

        for mev in analysis.move_evs:
            if str(mev.move) == actual_move_str:
                actual_rank = mev.rank
                actual_ev = mev.win_rate
                break

        if actual_rank is None:
            # Move not found in analysis (shouldn't happen)
            continue

        ev_loss = analysis.position_value - (actual_ev or 0.0)
        player = move_record["player"]
        was_winning = (winner == player)

        critical_positions.append(CriticalPosition(
            game_id=game_id,
            turn=move_record["turn"],
            move_number=i,
            state=state,
            analysis=analysis,
            actual_move=actual_move_str,
            actual_move_rank=actual_rank,
            ev_loss=ev_loss,
            was_winning=was_winning,
        ))

    # Sort by EV loss and return top positions
    critical_positions.sort(key=lambda x: x.ev_loss, reverse=True)
    return critical_positions[:max_positions]


def find_critical_positions_batch(
    log_dir: str | Path,
    mcts_iterations: int = 1000,
    min_ev_spread: float = 0.15,
    max_per_game: int = 3,
    max_total: int = 50,
    seed: int | None = None,
) -> list[CriticalPosition]:
    """Find critical positions across multiple game logs.

    Args:
        log_dir: Directory containing game log JSON files.
        mcts_iterations: MCTS iterations for analysis.
        min_ev_spread: Minimum EV spread threshold.
        max_per_game: Maximum positions to extract per game.
        max_total: Maximum total positions to return.
        seed: Random seed.

    Returns:
        List of CriticalPosition objects from all games.
    """
    log_dir = Path(log_dir)
    all_positions = []

    for log_file in log_dir.rglob("*.json"):
        try:
            positions = find_critical_positions(
                log_file,
                mcts_iterations=mcts_iterations,
                min_ev_spread=min_ev_spread,
                max_positions=max_per_game,
                seed=seed,
            )
            all_positions.extend(positions)
        except Exception:
            continue

    # Sort all by EV loss and return top
    all_positions.sort(key=lambda x: x.ev_loss, reverse=True)
    return all_positions[:max_total]


@dataclass
class MoveTypeStats:
    """Statistics for a type of move across analyzed positions."""

    move_type: str
    total_played: int
    times_optimal: int
    avg_rank_when_played: float
    avg_ev_loss: float


def analyze_move_patterns(
    critical_positions: list[CriticalPosition],
) -> dict[str, MoveTypeStats]:
    """Analyze patterns in move selection from critical positions.

    Identifies which move types are most often suboptimal.

    Args:
        critical_positions: List of analyzed critical positions.

    Returns:
        Dict mapping move type to statistics.
    """
    from collections import defaultdict

    type_data = defaultdict(lambda: {
        "total": 0,
        "optimal": 0,
        "ranks": [],
        "ev_losses": [],
    })

    for pos in critical_positions:
        # Categorize the actual move
        move_str = pos.actual_move

        if "Draw" in move_str:
            move_type = "Draw"
        elif "points" in move_str.lower():
            move_type = "PlayPoints"
        elif "Scuttle" in move_str:
            move_type = "Scuttle"
        elif "one-off" in move_str.lower():
            move_type = "OneOff"
        elif "permanent" in move_str.lower() or "steal" in move_str.lower():
            move_type = "Permanent"
        elif "Counter" in move_str:
            move_type = "Counter"
        elif "Decline" in move_str:
            move_type = "DeclineCounter"
        elif "Pass" in move_str:
            move_type = "Pass"
        elif "Discard" in move_str:
            move_type = "Discard"
        else:
            move_type = "Other"

        data = type_data[move_type]
        data["total"] += 1
        if pos.actual_move_rank == 1:
            data["optimal"] += 1
        data["ranks"].append(pos.actual_move_rank)
        data["ev_losses"].append(pos.ev_loss)

    # Convert to MoveTypeStats
    result = {}
    for move_type, data in type_data.items():
        result[move_type] = MoveTypeStats(
            move_type=move_type,
            total_played=data["total"],
            times_optimal=data["optimal"],
            avg_rank_when_played=sum(data["ranks"]) / len(data["ranks"]) if data["ranks"] else 0,
            avg_ev_loss=sum(data["ev_losses"]) / len(data["ev_losses"]) if data["ev_losses"] else 0,
        )

    return result
