"""Tournament runner for LLM-based strategies with cost tracking and ELO ratings."""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from cuttle_engine.executor import execute_move
from cuttle_engine.move_generator import generate_legal_moves
from cuttle_engine.state import GamePhase, create_initial_state
from core.cost_tracker import BudgetExceededError, CostTracker
from core.elo_manager import EloManager
from core.game_logger import PersistentGameLogger
from core.player_identity import PlayerIdentity
from db.database import Database, TournamentRepository

if TYPE_CHECKING:
    from cuttle_engine.moves import Move
    from cuttle_engine.state import GameState
    from strategies.base import Strategy

logger = logging.getLogger(__name__)


@dataclass
class StrategySpec:
    """Specification for a strategy in a tournament."""
    name: str
    factory: str  # Factory function path or strategy type
    params: dict[str, Any] = field(default_factory=dict)


@dataclass
class TournamentConfig:
    """Configuration for an LLM tournament."""
    strategies: list[StrategySpec]
    games_per_match: int = 10
    parallel_games: int = 4
    budget_usd: float | None = None
    rate_limit_rpm: int = 60  # Requests per minute
    max_turns_per_game: int = 500
    alternate_start: bool = True
    log_moves: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "strategies": [
                {"name": s.name, "factory": s.factory, "params": s.params}
                for s in self.strategies
            ],
            "games_per_match": self.games_per_match,
            "parallel_games": self.parallel_games,
            "budget_usd": self.budget_usd,
            "rate_limit_rpm": self.rate_limit_rpm,
            "max_turns_per_game": self.max_turns_per_game,
            "alternate_start": self.alternate_start,
            "log_moves": self.log_moves,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TournamentConfig":
        strategies = [
            StrategySpec(
                name=s["name"],
                factory=s["factory"],
                params=s.get("params", {}),
            )
            for s in data["strategies"]
        ]
        return cls(
            strategies=strategies,
            games_per_match=data.get("games_per_match", 10),
            parallel_games=data.get("parallel_games", 4),
            budget_usd=data.get("budget_usd"),
            rate_limit_rpm=data.get("rate_limit_rpm", 60),
            max_turns_per_game=data.get("max_turns_per_game", 500),
            alternate_start=data.get("alternate_start", True),
            log_moves=data.get("log_moves", True),
        )


@dataclass
class MatchResult:
    """Result of a match between two strategies."""
    strategy_a: str
    strategy_b: str
    wins_a: int
    wins_b: int
    draws: int
    total_games: int
    avg_turns: float
    cost_usd: float


@dataclass
class TournamentResult:
    """Complete tournament results."""
    tournament_id: str
    config: TournamentConfig
    matches: list[MatchResult]
    elo_ratings: dict[str, float]
    total_games: int
    total_cost_usd: float
    duration_seconds: float
    completed: bool
    cancelled_reason: str | None = None


class RateLimiter:
    """Simple rate limiter for API calls."""

    def __init__(self, requests_per_minute: int):
        self._rpm = requests_per_minute
        self._interval = 60.0 / requests_per_minute
        self._last_request = 0.0
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        async with self._lock:
            now = time.time()
            elapsed = now - self._last_request
            if elapsed < self._interval:
                await asyncio.sleep(self._interval - elapsed)
            self._last_request = time.time()


class LLMTournamentRunner:
    """Runs tournaments between LLM and other strategies.

    Features:
    - Round-robin matchups between all strategies
    - Cost tracking with budget enforcement
    - ELO rating updates after each game
    - Persistent game logging
    - Checkpoint/resume support
    - Rate limiting for API calls
    """

    def __init__(
        self,
        config: TournamentConfig,
        db: Database,
        tournament_id: str | None = None,
    ):
        """Initialize the tournament runner.

        Args:
            config: Tournament configuration.
            db: Database for persistence.
            tournament_id: Optional specific tournament ID.
        """
        self.config = config
        self.db = db
        self.tournament_id = tournament_id or str(uuid.uuid4())

        # Initialize repositories and managers
        self._tournament_repo = TournamentRepository(db)
        self._elo_manager = EloManager(db)
        self._game_logger = PersistentGameLogger(db)
        self._cost_tracker = CostTracker(
            db,
            tournament_id=self.tournament_id,
            budget_usd=config.budget_usd,
        )
        self._rate_limiter = RateLimiter(config.rate_limit_rpm)

        # State
        self._strategies: dict[str, Strategy] = {}
        self._identities: dict[str, PlayerIdentity] = {}
        self._matches: list[MatchResult] = []
        self._cancelled = False
        self._completed_games: set[tuple[str, str, int]] = set()  # (a, b, game_num)

    def _create_strategy(self, spec: StrategySpec) -> Strategy:
        """Create a strategy instance from a specification."""
        factory = spec.factory.lower()

        if factory == "random":
            from strategies.random_strategy import RandomStrategy
            return RandomStrategy(seed=spec.params.get("seed"))

        elif factory == "heuristic":
            from strategies.heuristic import HeuristicStrategy
            return HeuristicStrategy(seed=spec.params.get("seed"))

        elif factory == "mcts":
            from strategies.mcts import MCTSStrategy
            return MCTSStrategy(
                iterations=spec.params.get("iterations", 1000),
                exploration_constant=spec.params.get("exploration", 1.414),
                num_workers=spec.params.get("num_workers", 1),
            )

        elif factory == "ismcts":
            from strategies.ismcts import ISMCTSStrategy
            return ISMCTSStrategy(
                iterations=spec.params.get("iterations", 1000),
                exploration_constant=spec.params.get("exploration", 0.7),
            )

        elif factory.startswith("llm-anthropic"):
            from strategies.llm import create_llm_strategy
            return create_llm_strategy(
                provider="anthropic",
                model=spec.params.get("model", "haiku"),
                temperature=spec.params.get("temperature", 0.3),
                cost_tracker=self._cost_tracker,
            )

        elif factory.startswith("llm-openrouter"):
            from strategies.llm import create_llm_strategy
            return create_llm_strategy(
                provider="openrouter",
                model=spec.params.get("model", "qwen3-235b"),
                temperature=spec.params.get("temperature", 0.3),
                cost_tracker=self._cost_tracker,
            )

        elif factory.startswith("llm-ollama"):
            from strategies.llm import create_llm_strategy
            return create_llm_strategy(
                provider="ollama",
                model=spec.params.get("model", "llama3.3"),
                temperature=spec.params.get("temperature", 0.3),
            )

        else:
            raise ValueError(f"Unknown strategy factory: {factory}")

    async def run(self) -> TournamentResult:
        """Run the tournament.

        Returns:
            TournamentResult with all statistics.
        """
        start_time = time.perf_counter()

        # Create or update tournament record
        tournament = self._tournament_repo.get(self.tournament_id)
        if tournament is None:
            self._tournament_repo.create(
                tournament_id=self.tournament_id,
                name=f"Tournament {datetime.now().strftime('%Y-%m-%d %H:%M')}",
                config=self.config.to_dict(),
                budget_usd=self.config.budget_usd,
            )
        self._tournament_repo.update_status(self.tournament_id, "running")

        # Initialize strategies
        logger.info(f"Initializing {len(self.config.strategies)} strategies...")
        for spec in self.config.strategies:
            strategy = self._create_strategy(spec)
            identity = PlayerIdentity.from_strategy(strategy)
            self._strategies[spec.name] = strategy
            self._identities[spec.name] = identity
            logger.info(f"  {spec.name}: {identity.display_name}")

        # Run round-robin matches
        strategy_names = list(self._strategies.keys())
        total_matches = len(strategy_names) * (len(strategy_names) - 1) // 2

        logger.info(f"Running {total_matches} matches, {self.config.games_per_match} games each...")

        try:
            for i, name_a in enumerate(strategy_names):
                for name_b in strategy_names[i + 1:]:
                    if self._cancelled:
                        break

                    match_result = await self._run_match(name_a, name_b)
                    self._matches.append(match_result)

                    logger.info(
                        f"Match complete: {name_a} vs {name_b} - "
                        f"{match_result.wins_a}-{match_result.wins_b} "
                        f"(${match_result.cost_usd:.4f})"
                    )

                    # Save checkpoint
                    self._save_checkpoint()

        except BudgetExceededError as e:
            logger.warning(f"Budget exceeded: {e}")
            self._cancelled = True

        except Exception as e:
            logger.error(f"Tournament error: {e}")
            self._cancelled = True

        # Calculate final ELO ratings
        elo_ratings = {}
        for name in strategy_names:
            identity = self._identities[name]
            elo_ratings[name] = self._elo_manager.get_rating(identity.id)

        # Update tournament status
        duration = time.perf_counter() - start_time
        total_cost = self._cost_tracker.get_tournament_spent()
        total_games = sum(m.total_games for m in self._matches)

        status = "completed" if not self._cancelled else "cancelled"
        self._tournament_repo.update_status(
            self.tournament_id, status, spent_usd=total_cost
        )

        return TournamentResult(
            tournament_id=self.tournament_id,
            config=self.config,
            matches=self._matches,
            elo_ratings=elo_ratings,
            total_games=total_games,
            total_cost_usd=total_cost,
            duration_seconds=duration,
            completed=not self._cancelled,
            cancelled_reason="Budget exceeded" if self._cancelled else None,
        )

    async def _run_match(self, name_a: str, name_b: str) -> MatchResult:
        """Run a match between two strategies."""
        strategy_a = self._strategies[name_a]
        strategy_b = self._strategies[name_b]
        identity_a = self._identities[name_a]
        identity_b = self._identities[name_b]

        wins_a = 0
        wins_b = 0
        draws = 0
        total_turns = 0
        match_cost = 0.0

        # Run games (could be parallelized in future)
        for game_num in range(self.config.games_per_match):
            # Check if already completed (for resume)
            game_key = (name_a, name_b, game_num)
            if game_key in self._completed_games:
                continue

            # Alternate starting player
            if self.config.alternate_start and game_num % 2 == 1:
                p0_strategy, p1_strategy = strategy_b, strategy_a
                p0_identity, p1_identity = identity_b, identity_a
                swap_perspective = True
            else:
                p0_strategy, p1_strategy = strategy_a, strategy_b
                p0_identity, p1_identity = identity_a, identity_b
                swap_perspective = False

            # Apply rate limiting before game
            await self._rate_limiter.acquire()

            # Run the game
            seed = hash((self.tournament_id, name_a, name_b, game_num)) % (2**31)
            result = await self._run_single_game(
                p0_strategy, p1_strategy,
                p0_identity, p1_identity,
                seed=seed,
            )

            # Record result
            winner = result["winner"]
            if swap_perspective:
                if winner == 0:
                    wins_b += 1
                elif winner == 1:
                    wins_a += 1
                else:
                    draws += 1
            else:
                if winner == 0:
                    wins_a += 1
                elif winner == 1:
                    wins_b += 1
                else:
                    draws += 1

            total_turns += result["turns"]
            match_cost += result.get("cost_usd", 0)

            # Update ELO
            game_winner = winner
            if swap_perspective and winner is not None:
                game_winner = 1 - winner

            pools = self._elo_manager.determine_rating_pools(
                identity_a.provider, identity_b.provider
            )
            self._elo_manager.update_ratings_from_game(
                identity_a.id, identity_b.id, game_winner, pools
            )

            self._completed_games.add(game_key)

        total_games = wins_a + wins_b + draws

        return MatchResult(
            strategy_a=name_a,
            strategy_b=name_b,
            wins_a=wins_a,
            wins_b=wins_b,
            draws=draws,
            total_games=total_games,
            avg_turns=total_turns / total_games if total_games > 0 else 0,
            cost_usd=match_cost,
        )

    async def _run_single_game(
        self,
        strategy0: Strategy,
        strategy1: Strategy,
        identity0: PlayerIdentity,
        identity1: PlayerIdentity,
        seed: int | None = None,
    ) -> dict[str, Any]:
        """Run a single game."""
        game_id = str(uuid.uuid4())
        game_cost = 0.0

        # Start logging
        if self.config.log_moves:
            self._game_logger.start_game(
                identity0, identity1,
                seed=seed,
                tournament_id=self.tournament_id,
                game_id=game_id,
            )

        # Initialize game
        state = create_initial_state(seed=seed)

        # Notify strategies
        strategy0.on_game_start(state, 0)
        strategy1.on_game_start(state, 1)

        strategies = (strategy0, strategy1)
        move_count = 0

        # Game loop
        while not state.is_game_over and state.turn_number <= self.config.max_turns_per_game:
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
                break

            # Select move
            strategy = strategies[acting_player]

            # Run in executor if it's an LLM strategy (to not block)
            loop = asyncio.get_event_loop()
            move = await loop.run_in_executor(
                None, strategy.select_move, state, legal_moves
            )

            # Get MCTS stats or LLM thinking
            mcts_stats = None
            llm_thinking = None

            if hasattr(strategy, 'last_thinking') and strategy.last_thinking:
                thinking = strategy.last_thinking
                llm_thinking = {
                    "response": thinking.response[:500],  # Truncate for storage
                    "model": thinking.model,
                    "input_tokens": thinking.input_tokens,
                    "output_tokens": thinking.output_tokens,
                    "cost_usd": thinking.cost_usd,
                }
                game_cost += thinking.cost_usd

            # Execute move
            try:
                new_state = execute_move(state, move)
                move_count += 1
            except Exception as e:
                logger.error(f"Move execution error: {e}")
                break

            # Log move
            if self.config.log_moves:
                self._game_logger.log_move(
                    game_id=game_id,
                    turn=state.turn_number,
                    player=acting_player,
                    phase=state.phase.name,
                    move=move,
                    state=new_state,
                    mcts_stats=mcts_stats,
                    llm_thinking=llm_thinking,
                )

            # Notify strategies
            for s in strategies:
                s.on_move_made(new_state, move, acting_player)

            state = new_state

        # End game
        if self.config.log_moves:
            self._game_logger.end_game(
                game_id=game_id,
                winner=state.winner,
                win_reason=state.win_reason.name if state.win_reason else None,
                score_p0=state.players[0].point_total,
                score_p1=state.players[1].point_total,
                turns=state.turn_number,
            )

        # Notify strategies
        for s in strategies:
            s.on_game_end(state, state.winner)

        return {
            "game_id": game_id,
            "winner": state.winner,
            "win_reason": state.win_reason.name if state.win_reason else None,
            "turns": state.turn_number,
            "move_count": move_count,
            "score_p0": state.players[0].point_total,
            "score_p1": state.players[1].point_total,
            "cost_usd": game_cost,
        }

    def _save_checkpoint(self) -> None:
        """Save tournament checkpoint for resume."""
        checkpoint = {
            "tournament_id": self.tournament_id,
            "completed_games": list(self._completed_games),
            "matches": [
                {
                    "strategy_a": m.strategy_a,
                    "strategy_b": m.strategy_b,
                    "wins_a": m.wins_a,
                    "wins_b": m.wins_b,
                    "draws": m.draws,
                    "total_games": m.total_games,
                    "avg_turns": m.avg_turns,
                    "cost_usd": m.cost_usd,
                }
                for m in self._matches
            ],
        }

        checkpoint_path = Path(f"checkpoints/{self.tournament_id}.json")
        checkpoint_path.parent.mkdir(parents=True, exist_ok=True)

        with open(checkpoint_path, "w") as f:
            json.dump(checkpoint, f, indent=2)

    @classmethod
    def resume(
        cls,
        tournament_id: str,
        db: Database,
    ) -> "LLMTournamentRunner":
        """Resume a tournament from checkpoint.

        Args:
            tournament_id: Tournament ID to resume.
            db: Database instance.

        Returns:
            Configured runner ready to continue.
        """
        tournament_repo = TournamentRepository(db)
        tournament = tournament_repo.get(tournament_id)

        if tournament is None:
            raise ValueError(f"Tournament not found: {tournament_id}")

        config = TournamentConfig.from_dict(json.loads(tournament.config_json))

        runner = cls(config, db, tournament_id)

        # Load checkpoint
        checkpoint_path = Path(f"checkpoints/{tournament_id}.json")
        if checkpoint_path.exists():
            with open(checkpoint_path, "r") as f:
                checkpoint = json.load(f)

            runner._completed_games = set(
                tuple(g) for g in checkpoint.get("completed_games", [])
            )
            runner._matches = [
                MatchResult(**m) for m in checkpoint.get("matches", [])
            ]

        return runner

    def cancel(self) -> None:
        """Cancel the tournament."""
        self._cancelled = True
