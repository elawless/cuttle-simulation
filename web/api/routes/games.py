"""Game API routes."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

from web.api.session_manager import (
    GameSession,
    PlayerConfig,
    PlayerType,
    StrategyFactory,
    session_manager,
)

router = APIRouter(tags=["games"])


# Request/Response models
class PlayerConfigRequest(BaseModel):
    """Player configuration for game creation."""

    player_type: str = Field(..., description="'human' or 'ai'")
    strategy: str | None = Field(None, description="Strategy name for AI players")
    strategy_params: dict[str, Any] = Field(
        default_factory=dict, description="Strategy parameters"
    )


class CreateGameRequest(BaseModel):
    """Request to create a new game."""

    player0: PlayerConfigRequest
    player1: PlayerConfigRequest
    seed: int | None = Field(None, description="Random seed for reproducibility")
    hand_limit: int | None = Field(None, description="Max hand size (None=unlimited, 8=standard variant)")
    watch_mode: bool = Field(False, description="If True, don't auto-run AI turns (for observer mode)")


class GameStateResponse(BaseModel):
    """Game state response."""

    game_id: str
    phase: str
    current_player: int
    turn_number: int
    deck_count: int
    winner: int | None
    win_reason: str | None
    acting_player: int
    players: list[dict]
    scrap: list[dict]
    counter_state: dict | None
    seven_state: dict | None
    four_state: dict | None


class LegalMovesResponse(BaseModel):
    """Response with legal moves."""

    moves: list[dict]


class MoveRequest(BaseModel):
    """Request to make a move."""

    move_index: int = Field(..., description="Index of the move in legal_moves list")


class StrategyInfo(BaseModel):
    """Information about an available strategy."""

    name: str
    description: str


# REST Endpoints


@router.get("/strategies", response_model=list[StrategyInfo])
async def list_strategies():
    """List available AI strategies."""
    factory = StrategyFactory()
    strategies = factory.list_strategies()
    return [StrategyInfo(name=name, description=desc) for name, desc in strategies.items()]


@router.post("/games", response_model=dict)
async def create_game(request: CreateGameRequest):
    """Create a new game session."""
    # Convert request to PlayerConfig
    def to_config(req: PlayerConfigRequest) -> PlayerConfig:
        return PlayerConfig(
            player_type=PlayerType(req.player_type),
            strategy_name=req.strategy,
            strategy_params=req.strategy_params,
        )

    try:
        session = session_manager.create_session(
            player0_config=to_config(request.player0),
            player1_config=to_config(request.player1),
            seed=request.seed,
            hand_limit=request.hand_limit,
        )

        # In watch mode, don't auto-run AI turns - let WebSocket control it
        # Otherwise, if AI goes first, run initial AI turns
        if not request.watch_mode and not session.is_human_turn:
            await session_manager.run_ai_turns_until_human(session)

        return {
            "game_id": session.id,
            "state": session.to_client_state(viewer=0),
            "legal_moves": session.moves_to_client(session.legal_moves),
            "is_human_turn": session.is_human_turn,
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/games", response_model=list[dict])
async def list_games():
    """List all active game sessions."""
    return session_manager.list_sessions()


@router.get("/games/{game_id}")
async def get_game(game_id: str, viewer: int = 0):
    """Get current state of a game."""
    session = session_manager.get_session(game_id)
    if not session:
        raise HTTPException(status_code=404, detail="Game not found")

    return {
        "state": session.to_client_state(viewer=viewer),
        "legal_moves": session.moves_to_client(session.legal_moves),
        "is_human_turn": session.is_human_turn,
        "move_history": session.move_history,
    }


@router.get("/games/{game_id}/moves")
async def get_legal_moves(game_id: str):
    """Get legal moves for current game state."""
    session = session_manager.get_session(game_id)
    if not session:
        raise HTTPException(status_code=404, detail="Game not found")

    return {"moves": session.moves_to_client(session.legal_moves)}


@router.post("/games/{game_id}/move")
async def make_move(game_id: str, request: MoveRequest, viewer: int = 0):
    """Make a move in a game."""
    session = session_manager.get_session(game_id)
    if not session:
        raise HTTPException(status_code=404, detail="Game not found")

    if session.state.is_game_over:
        raise HTTPException(status_code=400, detail="Game is already over")

    if not session.is_human_turn:
        raise HTTPException(status_code=400, detail="Not your turn")

    legal_moves = session.legal_moves
    if request.move_index < 0 or request.move_index >= len(legal_moves):
        raise HTTPException(status_code=400, detail="Invalid move index")

    move = legal_moves[request.move_index]

    try:
        session.execute_move(move)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Move execution failed: {e}")

    # Run AI turns after human move
    if not session.state.is_game_over and not session.is_human_turn:
        await session_manager.run_ai_turns_until_human(session)

    return {
        "state": session.to_client_state(viewer=viewer),
        "legal_moves": session.moves_to_client(session.legal_moves),
        "is_human_turn": session.is_human_turn,
        "move_history": session.move_history,
    }


@router.delete("/games/{game_id}")
async def delete_game(game_id: str):
    """Delete a game session."""
    if session_manager.delete_session(game_id):
        return {"deleted": True}
    raise HTTPException(status_code=404, detail="Game not found")


@router.get("/replays")
async def list_replays(limit: int = 50):
    """List saved game replays."""
    logs_dir = Path("logs/games")
    if not logs_dir.exists():
        return {"replays": []}

    replays = []
    for date_dir in sorted(logs_dir.iterdir(), reverse=True):
        if not date_dir.is_dir():
            continue
        for game_file in sorted(date_dir.glob("game_*.json"), reverse=True):
            if len(replays) >= limit:
                break
            try:
                with open(game_file) as f:
                    data = json.load(f)
                replays.append({
                    "game_id": data.get("game_id"),
                    "timestamp": data.get("timestamp"),
                    "player_strategies": data.get("player_strategies"),
                    "result": data.get("result"),
                    "path": str(game_file),
                })
            except Exception:
                pass

    return {"replays": replays}


@router.get("/replays/{game_id}")
async def get_replay(game_id: str):
    """Get a saved game replay."""
    logs_dir = Path("logs/games")
    if not logs_dir.exists():
        raise HTTPException(status_code=404, detail="Replay not found")

    # Search for the game file
    for date_dir in logs_dir.iterdir():
        if not date_dir.is_dir():
            continue
        game_file = date_dir / f"game_{game_id}.json"
        if game_file.exists():
            with open(game_file) as f:
                return json.load(f)

    raise HTTPException(status_code=404, detail="Replay not found")


# WebSocket endpoint for real-time game play


class ConnectionManager:
    """Manages WebSocket connections for games."""

    def __init__(self):
        self.connections: dict[str, list[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, game_id: str):
        """Connect a WebSocket to a game."""
        await websocket.accept()
        if game_id not in self.connections:
            self.connections[game_id] = []
        self.connections[game_id].append(websocket)

    def disconnect(self, websocket: WebSocket, game_id: str):
        """Disconnect a WebSocket from a game."""
        if game_id in self.connections:
            if websocket in self.connections[game_id]:
                self.connections[game_id].remove(websocket)
            if not self.connections[game_id]:
                del self.connections[game_id]

    async def broadcast(self, game_id: str, message: dict):
        """Broadcast a message to all connections for a game."""
        if game_id in self.connections:
            disconnected = []
            for ws in self.connections[game_id]:
                try:
                    await ws.send_json(message)
                except Exception:
                    disconnected.append(ws)
            for ws in disconnected:
                self.disconnect(ws, game_id)


ws_manager = ConnectionManager()


@router.websocket("/ws/game/{game_id}")
async def game_websocket(websocket: WebSocket, game_id: str):
    """WebSocket endpoint for real-time game updates.

    Protocol:
    Server -> Client messages:
        - game_state: Full game state update
        - legal_moves: Available moves for current player
        - move_made: A move was executed
        - playback_state: Pause/speed state for observer mode
        - error: Error message

    Client -> Server messages:
        - select_move: {move_index: int} - Select and execute a move
        - get_state: Request current state
        - get_moves: Request legal moves
        - pause: Pause AI execution (observer mode)
        - resume: Resume AI execution (observer mode)
        - step: Execute single AI turn (observer mode)
        - set_speed: {delay_ms: int} - Set delay between moves (observer mode)
    """
    # Parse query parameters manually (WebSocket doesn't auto-parse like HTTP)
    query_params = dict(websocket.query_params)
    viewer = int(query_params.get("viewer", "0"))
    watch = query_params.get("watch", "").lower() == "true"
    speed = int(query_params.get("speed", "500"))

    import logging
    logger = logging.getLogger(__name__)
    logger.info(f"WebSocket connection: game_id={game_id}, viewer={viewer}, watch={watch}, speed={speed}")

    session = session_manager.get_session(game_id)
    if not session:
        logger.warning(f"WebSocket: Game not found: {game_id}")
        await websocket.close(code=4004, reason="Game not found")
        return

    logger.info(f"WebSocket: Found session, connecting...")
    await ws_manager.connect(websocket, game_id)
    logger.info(f"WebSocket: Connected successfully")

    # Set up listener for state changes from other sources
    async def on_state_change(event: dict):
        try:
            await websocket.send_json(event)
        except Exception:
            pass

    # We'll use a queue for async event handling
    event_queue: asyncio.Queue = asyncio.Queue()

    def queue_event(event: dict):
        try:
            event_queue.put_nowait(event)
        except Exception:
            pass

    session.add_listener(queue_event)

    # In watch mode, start paused so observer can control playback
    if watch:
        session.is_paused = True
        # Apply initial speed from URL parameter
        session.move_delay_ms = max(50, min(5000, speed))

    try:
        # Send initial state with playback info
        await websocket.send_json({
            "type": "game_state",
            "state": session.to_client_state(viewer=viewer),
            "legal_moves": session.moves_to_client(session.legal_moves),
            "is_human_turn": session.is_human_turn,
            "playback": {
                "paused": session.is_paused,
                "delay_ms": session.move_delay_ms,
            } if watch else None,
        })

        # Start task to forward events from queue
        async def forward_events():
            while True:
                event = await event_queue.get()
                try:
                    await websocket.send_json(event)
                except Exception:
                    break

        event_task = asyncio.create_task(forward_events())

        try:
            while True:
                # Receive message from client
                data = await websocket.receive_json()
                msg_type = data.get("type", "")

                if msg_type == "select_move":
                    if session.state.is_game_over:
                        await websocket.send_json({
                            "type": "error",
                            "message": "Game is already over",
                        })
                        continue

                    if not session.is_human_turn:
                        await websocket.send_json({
                            "type": "error",
                            "message": "Not your turn",
                        })
                        continue

                    move_index = data.get("move_index")
                    legal_moves = session.legal_moves

                    if move_index is None or move_index < 0 or move_index >= len(legal_moves):
                        await websocket.send_json({
                            "type": "error",
                            "message": "Invalid move index",
                        })
                        continue

                    move = legal_moves[move_index]

                    try:
                        session.execute_move(move)

                        # Send updated state
                        await websocket.send_json({
                            "type": "game_state",
                            "state": session.to_client_state(viewer=viewer),
                            "legal_moves": session.moves_to_client(session.legal_moves),
                            "is_human_turn": session.is_human_turn,
                        })

                        # Broadcast to other connections
                        await ws_manager.broadcast(game_id, {
                            "type": "move_made",
                            "move": session.move_history[-1],
                        })

                        # Run AI turns
                        if not session.state.is_game_over and not session.is_human_turn:
                            await session_manager.run_ai_turns_until_human(session)

                            # Send updated state after AI moves
                            await websocket.send_json({
                                "type": "game_state",
                                "state": session.to_client_state(viewer=viewer),
                                "legal_moves": session.moves_to_client(session.legal_moves),
                                "is_human_turn": session.is_human_turn,
                            })

                    except Exception as e:
                        await websocket.send_json({
                            "type": "error",
                            "message": f"Move failed: {e}",
                        })

                elif msg_type == "get_state":
                    await websocket.send_json({
                        "type": "game_state",
                        "state": session.to_client_state(viewer=viewer),
                        "legal_moves": session.moves_to_client(session.legal_moves),
                        "is_human_turn": session.is_human_turn,
                    })

                elif msg_type == "get_moves":
                    await websocket.send_json({
                        "type": "legal_moves",
                        "moves": session.moves_to_client(session.legal_moves),
                    })

                elif msg_type == "pause":
                    session.is_paused = True
                    await websocket.send_json({
                        "type": "playback_state",
                        "paused": session.is_paused,
                        "delay_ms": session.move_delay_ms,
                    })

                elif msg_type == "resume":
                    session.is_paused = False
                    await websocket.send_json({
                        "type": "playback_state",
                        "paused": session.is_paused,
                        "delay_ms": session.move_delay_ms,
                    })
                    # Run AI turns with observer mode
                    if not session.state.is_game_over and not session.is_human_turn:
                        await session_manager.run_ai_turns_until_human(session, observer_mode=True)
                        await websocket.send_json({
                            "type": "game_state",
                            "state": session.to_client_state(viewer=viewer),
                            "legal_moves": session.moves_to_client(session.legal_moves),
                            "is_human_turn": session.is_human_turn,
                            "playback": {
                                "paused": session.is_paused,
                                "delay_ms": session.move_delay_ms,
                            },
                        })

                elif msg_type == "step":
                    # Execute a single AI turn
                    if session.state.is_game_over:
                        await websocket.send_json({
                            "type": "error",
                            "message": "Game is already over",
                        })
                        continue

                    move, thinking = await session_manager.run_single_ai_turn(session)
                    await websocket.send_json({
                        "type": "game_state",
                        "state": session.to_client_state(viewer=viewer),
                        "legal_moves": session.moves_to_client(session.legal_moves),
                        "is_human_turn": session.is_human_turn,
                        "playback": {
                            "paused": session.is_paused,
                            "delay_ms": session.move_delay_ms,
                        },
                    })

                elif msg_type == "set_speed":
                    delay_ms = data.get("delay_ms", 500)
                    # Clamp to reasonable range
                    session.move_delay_ms = max(50, min(5000, delay_ms))
                    await websocket.send_json({
                        "type": "playback_state",
                        "paused": session.is_paused,
                        "delay_ms": session.move_delay_ms,
                    })

                else:
                    await websocket.send_json({
                        "type": "error",
                        "message": f"Unknown message type: {msg_type}",
                    })

        finally:
            event_task.cancel()
            try:
                await event_task
            except asyncio.CancelledError:
                pass

    except WebSocketDisconnect:
        pass
    finally:
        session.remove_listener(queue_event)
        ws_manager.disconnect(websocket, game_id)
