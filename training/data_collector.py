"""Data collection utilities for MCTS training."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from cuttle_engine.state import GameState


@dataclass
class MCTSMoveData:
    """Data collected for a single MCTS move decision.

    Captures the state, available moves, MCTS statistics, and eventual
    game outcome for training purposes.
    """

    turn: int
    player: int
    phase: str
    state_hash: str  # Hash of game state for deduplication
    legal_moves: list[str]  # String representations of legal moves
    visit_counts: dict[str, int]  # move_str -> visit count
    win_rates: dict[str, float]  # move_str -> win rate
    selected_move: str
    selected_visits: int
    selected_win_rate: float

    # Filled in after game ends
    game_result: float | None = None  # 1.0 win, 0.0 loss, 0.5 draw

    def to_policy_target(self) -> list[float]:
        """Convert visit counts to policy probability distribution.

        Returns probability distribution over legal_moves based on
        visit counts (standard MCTS policy target).
        """
        total_visits = sum(self.visit_counts.values())
        if total_visits == 0:
            # Uniform distribution
            n = len(self.legal_moves)
            return [1.0 / n] * n if n > 0 else []

        return [
            self.visit_counts.get(move, 0) / total_visits for move in self.legal_moves
        ]


@dataclass
class GameHistory:
    """Complete record of a game for training."""

    game_id: str
    timestamp: str
    seed: int | None
    mcts_player: int
    mcts_iterations: int
    opponent_strategy: str
    winner: int | None
    final_scores: tuple[int, int]
    moves: list[MCTSMoveData] = field(default_factory=list)

    @property
    def mcts_won(self) -> bool:
        """Whether the MCTS player won."""
        return self.winner == self.mcts_player

    @property
    def mcts_result(self) -> float:
        """Game result from MCTS player's perspective (1.0 win, 0.0 loss, 0.5 draw)."""
        if self.winner is None:
            return 0.5
        return 1.0 if self.winner == self.mcts_player else 0.0


class DataCollector:
    """Collect and store training data from MCTS games.

    Converts raw game data into structured training samples and
    persists to disk in JSON format.
    """

    def __init__(self, output_dir: Path | str):
        """Initialize the data collector.

        Args:
            output_dir: Directory to store training data files.
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def collect_from_game_data(self, game_data: dict) -> GameHistory:
        """Convert raw game data dict to GameHistory.

        Args:
            game_data: Dict from ParallelGameRunner.run_games_with_mcts_stats()

        Returns:
            Structured GameHistory object.
        """
        mcts_player = game_data["mcts_player"]
        winner = game_data["winner"]

        # Calculate result from MCTS perspective
        if winner is None:
            mcts_result = 0.5
        elif winner == mcts_player:
            mcts_result = 1.0
        else:
            mcts_result = 0.0

        moves = []
        for move_record in game_data["moves"]:
            # Only collect MCTS moves (those with statistics)
            if move_record.get("mcts_stats") is None:
                continue

            stats = move_record["mcts_stats"]
            move_data = MCTSMoveData(
                turn=move_record["turn"],
                player=move_record["player"],
                phase=move_record["phase"],
                state_hash=self._compute_state_hash(move_record),
                legal_moves=list(stats.keys()),
                visit_counts={m: s["visits"] for m, s in stats.items()},
                win_rates={m: s["win_rate"] for m, s in stats.items()},
                selected_move=move_record["move"],
                selected_visits=move_record.get("selected_visits", 0),
                selected_win_rate=move_record.get("selected_win_rate", 0.0),
                game_result=mcts_result,
            )
            moves.append(move_data)

        return GameHistory(
            game_id=game_data["game_id"],
            timestamp=datetime.now().isoformat(),
            seed=game_data.get("seed"),
            mcts_player=mcts_player,
            mcts_iterations=game_data["mcts_iterations"],
            opponent_strategy=game_data["opponent_strategy"],
            winner=winner,
            final_scores=tuple(game_data["final_scores"]),
            moves=moves,
        )

    def _compute_state_hash(self, move_record: dict) -> str:
        """Compute a hash for deduplication/lookup."""
        # Use turn, player, and move info as proxy for state
        key = f"{move_record['turn']}:{move_record['player']}:{move_record['phase']}"
        return hashlib.md5(key.encode()).hexdigest()[:12]

    def save_histories(
        self, histories: list[GameHistory], filename: str | None = None
    ) -> Path:
        """Save game histories to JSON file.

        Args:
            histories: List of GameHistory objects to save.
            filename: Output filename (default: auto-generated with timestamp).

        Returns:
            Path to saved file.
        """
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"training_data_{timestamp}.json"

        file_path = self.output_dir / filename

        # Convert to JSON-serializable format
        data = {
            "metadata": {
                "num_games": len(histories),
                "timestamp": datetime.now().isoformat(),
                "total_moves": sum(len(h.moves) for h in histories),
            },
            "games": [self._history_to_dict(h) for h in histories],
        }

        with open(file_path, "w") as f:
            json.dump(data, f, indent=2)

        return file_path

    def _history_to_dict(self, history: GameHistory) -> dict:
        """Convert GameHistory to JSON-serializable dict."""
        return {
            "game_id": history.game_id,
            "timestamp": history.timestamp,
            "seed": history.seed,
            "mcts_player": history.mcts_player,
            "mcts_iterations": history.mcts_iterations,
            "opponent_strategy": history.opponent_strategy,
            "winner": history.winner,
            "final_scores": list(history.final_scores),
            "mcts_won": history.mcts_won,
            "mcts_result": history.mcts_result,
            "moves": [asdict(m) for m in history.moves],
        }

    def load_histories(self, filename: str) -> list[GameHistory]:
        """Load game histories from JSON file.

        Args:
            filename: Filename to load (relative to output_dir).

        Returns:
            List of GameHistory objects.
        """
        file_path = self.output_dir / filename

        with open(file_path) as f:
            data = json.load(f)

        histories = []
        for game_dict in data["games"]:
            moves = [
                MCTSMoveData(
                    turn=m["turn"],
                    player=m["player"],
                    phase=m["phase"],
                    state_hash=m["state_hash"],
                    legal_moves=m["legal_moves"],
                    visit_counts=m["visit_counts"],
                    win_rates=m["win_rates"],
                    selected_move=m["selected_move"],
                    selected_visits=m["selected_visits"],
                    selected_win_rate=m["selected_win_rate"],
                    game_result=m.get("game_result"),
                )
                for m in game_dict["moves"]
            ]

            history = GameHistory(
                game_id=game_dict["game_id"],
                timestamp=game_dict["timestamp"],
                seed=game_dict.get("seed"),
                mcts_player=game_dict["mcts_player"],
                mcts_iterations=game_dict["mcts_iterations"],
                opponent_strategy=game_dict["opponent_strategy"],
                winner=game_dict.get("winner"),
                final_scores=tuple(game_dict["final_scores"]),
                moves=moves,
            )
            histories.append(history)

        return histories

    def export_policy_targets(self, histories: list[GameHistory]) -> list[dict]:
        """Export move data as policy training targets.

        Returns list of dicts suitable for training a policy network:
        - state_hash: For grouping/dedup
        - legal_moves: List of move strings
        - policy_target: Probability distribution from MCTS visits
        - value_target: Game outcome from this player's perspective

        Args:
            histories: Game histories to export.

        Returns:
            List of training sample dicts.
        """
        samples = []
        for history in histories:
            for move in history.moves:
                sample = {
                    "state_hash": move.state_hash,
                    "turn": move.turn,
                    "phase": move.phase,
                    "legal_moves": move.legal_moves,
                    "policy_target": move.to_policy_target(),
                    "value_target": move.game_result,
                    "selected_move": move.selected_move,
                }
                samples.append(sample)
        return samples

    def get_statistics(self, histories: list[GameHistory]) -> dict:
        """Compute summary statistics for a collection of games.

        Args:
            histories: Game histories to analyze.

        Returns:
            Dict with statistics about the games.
        """
        if not histories:
            return {"num_games": 0}

        wins = sum(1 for h in histories if h.mcts_won)
        total_moves = sum(len(h.moves) for h in histories)
        avg_moves = total_moves / len(histories) if histories else 0

        return {
            "num_games": len(histories),
            "mcts_wins": wins,
            "mcts_win_rate": wins / len(histories),
            "total_mcts_moves": total_moves,
            "avg_mcts_moves_per_game": avg_moves,
            "iterations_used": histories[0].mcts_iterations if histories else None,
            "opponent_strategy": histories[0].opponent_strategy if histories else None,
        }
