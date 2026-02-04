"""Game session management for the web API."""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Any, Callable

from cuttle_engine.executor import execute_move
from cuttle_engine.move_generator import generate_legal_moves
from cuttle_engine.state import GamePhase, create_initial_state

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from cuttle_engine.moves import Move
    from cuttle_engine.state import GameState
    from strategies.base import Strategy


class PlayerType(str, Enum):
    """Type of player."""
    HUMAN = "human"
    AI = "ai"


@dataclass
class PlayerConfig:
    """Configuration for a player in a game session."""
    player_type: PlayerType
    strategy_name: str | None = None  # None for human players
    strategy_params: dict[str, Any] = field(default_factory=dict)


@dataclass
class GameSession:
    """An active game session."""

    id: str
    player_configs: tuple[PlayerConfig, PlayerConfig]
    state: GameState
    strategies: tuple[Strategy | None, Strategy | None]
    created_at: datetime
    move_history: list[dict] = field(default_factory=list)
    is_paused: bool = False
    hand_limit: int | None = None  # None = no limit, 8 = standard variant

    # Callbacks for WebSocket notifications
    _state_listeners: list[Callable[[dict], None]] = field(default_factory=list)

    @property
    def current_player_config(self) -> PlayerConfig:
        """Get the config for the player who needs to act."""
        acting_player = self._get_acting_player()
        return self.player_configs[acting_player]

    @property
    def is_human_turn(self) -> bool:
        """Whether a human player needs to act."""
        return self.current_player_config.player_type == PlayerType.HUMAN

    @property
    def legal_moves(self) -> list[Move]:
        """Get legal moves for current state."""
        from cuttle_engine.moves import Draw

        moves = generate_legal_moves(self.state)

        # Apply hand limit if set
        if self.hand_limit is not None:
            acting_player = self._get_acting_player()
            hand_size = len(self.state.players[acting_player].hand)
            if hand_size >= self.hand_limit:
                # Filter out Draw moves
                moves = [m for m in moves if not isinstance(m, Draw)]

        return moves

    def _get_acting_player(self) -> int:
        """Determine which player needs to act based on game phase."""
        if self.state.phase == GamePhase.COUNTER:
            return self.state.counter_state.waiting_for_player
        elif self.state.phase == GamePhase.DISCARD_FOUR:
            return self.state.four_state.player
        elif self.state.phase == GamePhase.RESOLVE_SEVEN:
            return self.state.seven_state.player
        return self.state.current_player

    def add_listener(self, callback: Callable[[dict], None]) -> None:
        """Add a state change listener."""
        self._state_listeners.append(callback)

    def remove_listener(self, callback: Callable[[dict], None]) -> None:
        """Remove a state change listener."""
        if callback in self._state_listeners:
            self._state_listeners.remove(callback)

    def _notify_listeners(self, event: dict) -> None:
        """Notify all listeners of a state change."""
        for listener in self._state_listeners:
            try:
                listener(event)
            except Exception:
                pass  # Don't let one listener break others

    def execute_move(self, move: Move, llm_thinking: dict | None = None) -> GameState:
        """Execute a move and update state."""
        acting_player = self._get_acting_player()
        old_state = self.state
        self.state = execute_move(self.state, move)

        # Record move with hand snapshots for debugging
        move_record = {
            "turn": old_state.turn_number,
            "player": acting_player,
            "move": str(move),
            "move_type": move.move_type.name,
            "timestamp": datetime.now().isoformat(),
            # Snapshot hands before and after for debugging
            "hands_before": [
                [str(c) for c in old_state.players[i].hand] for i in range(2)
            ],
            "hands_after": [
                [str(c) for c in self.state.players[i].hand] for i in range(2)
            ],
            "points_after": [
                self.state.players[i].point_total for i in range(2)
            ],
        }

        # Include LLM thinking if available
        if llm_thinking:
            move_record["llm_thinking"] = llm_thinking

        self.move_history.append(move_record)

        # Notify listeners
        self._notify_listeners({
            "type": "move_made",
            "move": move_record,
            "state": self.to_client_state(acting_player),
        })

        return self.state

    def to_client_state(self, viewer: int = 0) -> dict:
        """Convert game state to client-friendly format.

        Args:
            viewer: Which player is viewing (affects hidden information)
        """
        state = self.state
        opponent = 1 - viewer

        # Check if viewer can see opponent's hand (has Glasses/Eight)
        can_see_opponent = state.players[viewer].has_glasses

        return {
            "game_id": self.id,
            "phase": state.phase.name,
            "current_player": state.current_player,
            "turn_number": state.turn_number,
            "deck_count": len(state.deck),
            "scrap": [_card_to_dict(c) for c in state.scrap],
            "winner": state.winner,
            "win_reason": state.win_reason.name if state.win_reason else None,
            "acting_player": self._get_acting_player(),
            "players": [
                {
                    "index": i,
                    "hand": (
                        [_card_to_dict(c) for c in state.players[i].hand]
                        if i == viewer or can_see_opponent
                        else [{"hidden": True} for _ in state.players[i].hand]
                    ),
                    "hand_count": len(state.players[i].hand),
                    "points_field": [_card_to_dict(c) for c in state.players[i].points_field],
                    "permanents": [_card_to_dict(c) for c in state.players[i].permanents],
                    "jacks": [
                        {"jack": _card_to_dict(j), "stolen": _card_to_dict(s)}
                        for j, s in state.players[i].jacks
                    ],
                    "point_total": state.players[i].point_total,
                    "point_threshold": state.point_threshold(i),
                    "queens_count": state.players[i].queens_count,
                    "kings_count": state.players[i].kings_count,
                }
                for i in range(2)
            ],
            "counter_state": (
                {
                    "one_off_card": _card_to_dict(state.counter_state.one_off_card),
                    "one_off_player": state.counter_state.one_off_player,
                    "target_card": (
                        _card_to_dict(state.counter_state.target_card)
                        if state.counter_state.target_card
                        else None
                    ),
                    "counter_chain": [
                        _card_to_dict(c) for c in state.counter_state.counter_chain
                    ],
                    "waiting_for_player": state.counter_state.waiting_for_player,
                    "resolves": state.counter_state.resolves,
                }
                if state.counter_state
                else None
            ),
            "seven_state": (
                {
                    "revealed_cards": [
                        _card_to_dict(c) for c in state.seven_state.revealed_cards
                    ],
                    "player": state.seven_state.player,
                }
                if state.seven_state
                else None
            ),
            "four_state": (
                {
                    "player": state.four_state.player,
                    "cards_to_discard": state.four_state.cards_to_discard,
                }
                if state.four_state
                else None
            ),
        }

    def moves_to_client(self, moves: list[Move]) -> list[dict]:
        """Convert moves to client-friendly format."""
        return [_move_to_dict(i, m) for i, m in enumerate(moves)]


def _card_to_dict(card) -> dict:
    """Convert a Card to a dictionary."""
    return {
        "rank": card.rank.value,
        "rank_symbol": card.rank.symbol,
        "rank_name": card.rank.name,
        "suit": card.suit.value,
        "suit_symbol": card.suit.symbol,
        "suit_name": card.suit.name,
        "display": str(card),
        "point_value": card.point_value,
    }


def _move_to_dict(index: int, move: Move) -> dict:
    """Convert a Move to a dictionary."""
    from cuttle_engine.moves import (
        Counter,
        DeclineCounter,
        Discard,
        Draw,
        Pass,
        PlayOneOff,
        PlayPermanent,
        PlayPoints,
        ResolveSeven,
        Scuttle,
    )

    base = {
        "index": index,
        "type": move.move_type.name,
        "description": str(move),
    }

    match move:
        case Draw():
            pass
        case Pass():
            pass
        case DeclineCounter():
            pass
        case PlayPoints(card=card):
            base["card"] = _card_to_dict(card)
        case Scuttle(card=card, target=target):
            base["card"] = _card_to_dict(card)
            base["target"] = _card_to_dict(target)
        case PlayOneOff(card=card, effect=effect, target_card=target, target_player=tp):
            base["card"] = _card_to_dict(card)
            base["effect"] = effect.name
            if target:
                base["target"] = _card_to_dict(target)
            if tp is not None:
                base["target_player"] = tp
        case PlayPermanent(card=card, target_card=target):
            base["card"] = _card_to_dict(card)
            if target:
                base["target"] = _card_to_dict(target)
        case Counter(card=card):
            base["card"] = _card_to_dict(card)
        case Discard(card=card):
            base["card"] = _card_to_dict(card)
        case ResolveSeven(card=card, play_as=play_as, target_card=target):
            base["card"] = _card_to_dict(card)
            base["play_as"] = play_as.name
            if target:
                base["target"] = _card_to_dict(target)

    return base


class GameSessionManager:
    """Manages all active game sessions."""

    def __init__(self):
        self._sessions: dict[str, GameSession] = {}
        self._strategy_factory = StrategyFactory()

    def create_session(
        self,
        player0_config: PlayerConfig,
        player1_config: PlayerConfig,
        seed: int | None = None,
        hand_limit: int | None = None,
    ) -> GameSession:
        """Create a new game session."""
        session_id = str(uuid.uuid4())

        # Create strategies for AI players
        strategy0 = None
        strategy1 = None

        if player0_config.player_type == PlayerType.AI:
            strategy0 = self._strategy_factory.create(
                player0_config.strategy_name,
                player0_config.strategy_params,
            )

        if player1_config.player_type == PlayerType.AI:
            strategy1 = self._strategy_factory.create(
                player1_config.strategy_name,
                player1_config.strategy_params,
            )

        # Create initial game state
        state = create_initial_state(seed=seed)

        session = GameSession(
            id=session_id,
            player_configs=(player0_config, player1_config),
            state=state,
            strategies=(strategy0, strategy1),
            created_at=datetime.now(),
            hand_limit=hand_limit,
        )

        # Notify strategies of game start
        if strategy0:
            strategy0.on_game_start(state, 0)
        if strategy1:
            strategy1.on_game_start(state, 1)

        self._sessions[session_id] = session
        return session

    def get_session(self, session_id: str) -> GameSession | None:
        """Get a session by ID."""
        return self._sessions.get(session_id)

    def delete_session(self, session_id: str) -> bool:
        """Delete a session."""
        if session_id in self._sessions:
            del self._sessions[session_id]
            return True
        return False

    def list_sessions(self) -> list[dict]:
        """List all active sessions."""
        return [
            {
                "id": s.id,
                "created_at": s.created_at.isoformat(),
                "turn_number": s.state.turn_number,
                "is_game_over": s.state.is_game_over,
                "winner": s.state.winner,
                "players": [
                    {
                        "type": s.player_configs[i].player_type.value,
                        "strategy": s.player_configs[i].strategy_name,
                    }
                    for i in range(2)
                ],
            }
            for s in self._sessions.values()
        ]

    async def run_ai_turn(self, session: GameSession) -> tuple[Move | None, dict | None]:
        """Run an AI turn if it's an AI player's turn.

        Returns tuple of (move made, llm_thinking dict) or (None, None) if not AI's turn.
        """
        if session.state.is_game_over:
            return None, None

        if session.is_human_turn:
            return None, None

        acting_player = session._get_acting_player()
        strategy = session.strategies[acting_player]

        if strategy is None:
            return None, None

        legal_moves = session.legal_moves
        if not legal_moves:
            return None, None

        llm_thinking = None
        move = None
        strategy_name = getattr(strategy, 'name', 'unknown')

        # Notify that AI is thinking
        session._notify_listeners({
            "type": "ai_thinking",
            "player": acting_player,
            "strategy": strategy_name,
        })

        logger.info(f"AI turn: player={acting_player}, strategy={strategy_name}, moves={len(legal_moves)}")
        start_time = time.time()

        try:
            # Run strategy in executor to not block
            loop = asyncio.get_event_loop()
            move = await loop.run_in_executor(
                None,
                strategy.select_move,
                session.state,
                legal_moves,
            )

            elapsed = time.time() - start_time
            logger.info(f"AI selected move in {elapsed:.2f}s: {move}")

            # Capture LLM thinking if available
            if hasattr(strategy, 'last_thinking') and strategy.last_thinking:
                thinking = strategy.last_thinking
                llm_thinking = {
                    "prompt": thinking.prompt,
                    "response": thinking.response,
                    "model": thinking.model,
                    "chosen_move_index": thinking.chosen_move_index,
                    "chosen_move_description": thinking.chosen_move_description,
                    "error": thinking.error,
                    "elapsed_ms": int(elapsed * 1000),
                }

        except Exception as e:
            elapsed = time.time() - start_time
            logger.error(f"Strategy error after {elapsed:.2f}s: {e}")
            move = legal_moves[0]
            llm_thinking = {
                "prompt": "(Strategy failed)",
                "response": "(No response)",
                "model": getattr(strategy, '_model_id', 'unknown'),
                "chosen_move_index": 0,
                "chosen_move_description": str(move),
                "error": str(e),
                "elapsed_ms": int(elapsed * 1000),
            }

        # Execute the move
        try:
            session.execute_move(move, llm_thinking=llm_thinking)
            return move, llm_thinking
        except Exception as e:
            logger.error(f"Move execution error: {e}")
            return None, None

    async def run_ai_turns_until_human(self, session: GameSession) -> list[tuple[Move, dict | None]]:
        """Run AI turns until it's a human's turn or game ends.

        Returns list of (move, llm_thinking) tuples.
        """
        results = []
        while not session.state.is_game_over and not session.is_human_turn:
            move, thinking = await self.run_ai_turn(session)
            if move:
                results.append((move, thinking))
            else:
                break
            # Minimal delay - just yield to event loop
            await asyncio.sleep(0.05)
        return results


class StrategyFactory:
    """Factory for creating strategy instances."""

    AVAILABLE_STRATEGIES = {
        "random": "Random player (baseline)",
        "heuristic": "Rule-based heuristic player",
        "mcts": "Monte Carlo Tree Search",
        "ismcts": "Information Set MCTS (handles hidden info)",
        "llm-haiku": "Claude Haiku (fast, lightweight)",
        "llm-sonnet": "Claude Sonnet (balanced)",
        "llm-opus": "Claude Opus (most capable)",
    }

    def create(self, name: str, params: dict[str, Any] | None = None) -> Strategy:
        """Create a strategy instance."""
        params = params or {}
        name_lower = name.lower()

        match name_lower:
            case "random":
                from strategies.random_strategy import RandomStrategy
                return RandomStrategy(seed=params.get("seed"))

            case "heuristic":
                from strategies.heuristic import HeuristicStrategy
                return HeuristicStrategy(seed=params.get("seed"))

            case "mcts":
                from strategies.mcts import MCTSStrategy
                return MCTSStrategy(
                    iterations=params.get("iterations", 500),
                    exploration=params.get("exploration", 1.414),
                )

            case "ismcts":
                from strategies.ismcts import ISMCTSStrategy
                return ISMCTSStrategy(
                    iterations=params.get("iterations", 500),
                    exploration=params.get("exploration", 0.7),
                )

            case s if s.startswith("llm-"):
                from strategies.llm_strategy import LLMStrategy
                model = s.replace("llm-", "")
                return LLMStrategy(
                    model=model,
                    temperature=params.get("temperature", 0.3),
                )

            case _:
                raise ValueError(f"Unknown strategy: {name}")

    def list_strategies(self) -> dict[str, str]:
        """List available strategies with descriptions."""
        return self.AVAILABLE_STRATEGIES.copy()


# Global session manager instance
session_manager = GameSessionManager()
