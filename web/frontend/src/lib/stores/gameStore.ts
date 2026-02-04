/**
 * Game state store for Cuttle.
 */

import { writable, derived, get } from 'svelte/store';
import type { GameState, Move, MoveRecord } from '$lib/types';

// API base URL
const API_BASE = '/api';

// Game state
export const gameState = writable<GameState | null>(null);
export const legalMoves = writable<Move[]>([]);
export const isHumanTurn = writable<boolean>(false);
export const moveHistory = writable<MoveRecord[]>([]);
export const isLoading = writable<boolean>(false);
export const error = writable<string | null>(null);
export const selectedMoveIndex = writable<number | null>(null);
export const aiThinking = writable<{ player: number; strategy: string } | null>(null);

// Playback controls for observer mode
export const isPaused = writable<boolean>(true);
export const playbackSpeed = writable<number>(500);

// WebSocket connection
let ws: WebSocket | null = null;

// Derived stores
export const isGameOver = derived(gameState, ($state) => $state?.winner !== null && $state?.winner !== undefined);
export const currentPhase = derived(gameState, ($state) => $state?.phase || 'MAIN');
export const humanPlayer = derived(gameState, ($state) => {
	// In human vs AI, human is player 0
	return $state?.players[0] || null;
});
export const aiPlayer = derived(gameState, ($state) => {
	return $state?.players[1] || null;
});

/**
 * Fetch available strategies.
 */
export async function fetchStrategies(): Promise<{ name: string; description: string }[]> {
	const response = await fetch(`${API_BASE}/strategies`);
	if (!response.ok) {
		throw new Error('Failed to fetch strategies');
	}
	return response.json();
}

/**
 * Create a new game.
 */
export async function createGame(
	player0Type: 'human' | 'ai',
	player0Strategy: string | null,
	player1Type: 'human' | 'ai',
	player1Strategy: string | null,
	seed?: number,
	handLimit?: number | null,
	watchMode?: boolean
): Promise<string> {
	isLoading.set(true);
	error.set(null);

	try {
		const response = await fetch(`${API_BASE}/games`, {
			method: 'POST',
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify({
				player0: {
					player_type: player0Type,
					strategy: player0Strategy
				},
				player1: {
					player_type: player1Type,
					strategy: player1Strategy
				},
				seed,
				hand_limit: handLimit,
				watch_mode: watchMode ?? false
			})
		});

		if (!response.ok) {
			const data = await response.json();
			throw new Error(data.detail || 'Failed to create game');
		}

		const data = await response.json();
		gameState.set(data.state);
		legalMoves.set(data.legal_moves);
		isHumanTurn.set(data.is_human_turn);
		moveHistory.set(data.move_history || []);

		return data.game_id;
	} finally {
		isLoading.set(false);
	}
}

/**
 * Load an existing game.
 */
export async function loadGame(gameId: string, viewer: number = 0): Promise<void> {
	isLoading.set(true);
	error.set(null);

	try {
		const response = await fetch(`${API_BASE}/games/${gameId}?viewer=${viewer}`);
		if (!response.ok) {
			throw new Error('Game not found');
		}

		const data = await response.json();
		gameState.set(data.state);
		legalMoves.set(data.legal_moves);
		isHumanTurn.set(data.is_human_turn);
		moveHistory.set(data.move_history || []);
	} finally {
		isLoading.set(false);
	}
}

/**
 * Make a move via REST API.
 */
export async function makeMove(moveIndex: number, viewer: number = 0): Promise<void> {
	const state = get(gameState);
	if (!state) return;

	isLoading.set(true);
	error.set(null);
	selectedMoveIndex.set(null);

	try {
		const response = await fetch(`${API_BASE}/games/${state.game_id}/move?viewer=${viewer}`, {
			method: 'POST',
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify({ move_index: moveIndex })
		});

		if (!response.ok) {
			const data = await response.json();
			throw new Error(data.detail || 'Failed to make move');
		}

		const data = await response.json();
		gameState.set(data.state);
		legalMoves.set(data.legal_moves);
		isHumanTurn.set(data.is_human_turn);
		moveHistory.set(data.move_history || []);
	} catch (e) {
		error.set(e instanceof Error ? e.message : 'Unknown error');
	} finally {
		isLoading.set(false);
	}
}

/**
 * Connect to game WebSocket for real-time updates.
 */
export function connectWebSocket(gameId: string, viewer: number = 0, watch: boolean = false, initialSpeed?: number): void {
	if (ws) {
		ws.close();
	}

	const watchParam = watch ? '&watch=true' : '';
	const speedParam = initialSpeed ? `&speed=${initialSpeed}` : '';

	// In development, connect directly to backend; in production, use relative path
	const isDev = window.location.port === '5173';
	let wsUrl: string;

	if (isDev) {
		// Development: connect directly to backend on port 8000
		wsUrl = `ws://localhost:8000/api/ws/game/${gameId}?viewer=${viewer}${watchParam}${speedParam}`;
	} else {
		// Production: use same host
		const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
		wsUrl = `${protocol}//${window.location.host}/api/ws/game/${gameId}?viewer=${viewer}${watchParam}${speedParam}`;
	}

	console.log('Connecting WebSocket to:', wsUrl);
	ws = new WebSocket(wsUrl);

	ws.onopen = () => {
		console.log('WebSocket connected to:', wsUrl);
		// Clear any previous error
		error.set(null);
	};

	ws.onmessage = (event) => {
		try {
			const data = JSON.parse(event.data);
			console.debug('WS message:', data.type, data);

			switch (data.type) {
				case 'game_state':
					gameState.set(data.state);
					legalMoves.set(data.legal_moves || []);
					isHumanTurn.set(data.is_human_turn);
					aiThinking.set(null);
					isLoading.set(false);
					// Update playback state if present
					if (data.playback) {
						isPaused.set(data.playback.paused);
						playbackSpeed.set(data.playback.delay_ms);
					}
					break;

				case 'playback_state':
					isPaused.set(data.paused);
					playbackSpeed.set(data.delay_ms);
					break;

				case 'move_made':
					aiThinking.set(null);
					if (data.move) {
						moveHistory.update((history) => {
							// Avoid duplicates
							const exists = history.some(
								(m) => m.timestamp === data.move.timestamp && m.move === data.move.move
							);
							if (exists) return history;
							return [...history, data.move];
						});
					}
					break;

				case 'ai_thinking':
					aiThinking.set({ player: data.player, strategy: data.strategy });
					break;

				case 'legal_moves':
					legalMoves.set(data.moves || []);
					break;

				case 'error':
					error.set(data.message);
					aiThinking.set(null);
					console.error('WebSocket error:', data.message);
					break;

				default:
					console.log('Unknown WebSocket message type:', data.type);
			}
		} catch (e) {
			console.error('Failed to parse WebSocket message:', e);
		}
	};

	ws.onerror = (event) => {
		console.error('WebSocket connection failed to:', wsUrl);
		console.error('WebSocket error event:', event);
		error.set('WebSocket connection error - check if backend is running on port 8000');
	};

	ws.onclose = (event) => {
		console.log('WebSocket disconnected, code:', event.code, 'reason:', event.reason);
		ws = null;
	};
}

/**
 * Send move via WebSocket.
 */
export function sendMove(moveIndex: number): void {
	if (ws && ws.readyState === WebSocket.OPEN) {
		console.debug('Sending move:', moveIndex);
		isLoading.set(true);
		ws.send(JSON.stringify({ type: 'select_move', move_index: moveIndex }));
		selectedMoveIndex.set(null);
	} else {
		// Fallback to REST
		makeMove(moveIndex);
	}
}

/**
 * Disconnect WebSocket.
 */
export function disconnectWebSocket(): void {
	if (ws) {
		ws.close();
		ws = null;
	}
}

/**
 * Reset game state.
 */
export function resetGame(): void {
	gameState.set(null);
	legalMoves.set([]);
	isHumanTurn.set(false);
	moveHistory.set([]);
	error.set(null);
	selectedMoveIndex.set(null);
	aiThinking.set(null);
	isLoading.set(false);
	isPaused.set(true);
	playbackSpeed.set(500);
	disconnectWebSocket();
}

/**
 * Playback control functions for observer mode.
 */
export function sendPause(): void {
	if (ws && ws.readyState === WebSocket.OPEN) {
		console.log('Sending pause command');
		ws.send(JSON.stringify({ type: 'pause' }));
	} else {
		console.warn('Cannot send pause - WebSocket not connected, state:', ws?.readyState);
	}
}

export function sendResume(): void {
	if (ws && ws.readyState === WebSocket.OPEN) {
		console.log('Sending resume command');
		ws.send(JSON.stringify({ type: 'resume' }));
	} else {
		console.warn('Cannot send resume - WebSocket not connected, state:', ws?.readyState);
	}
}

export function sendStep(): void {
	if (ws && ws.readyState === WebSocket.OPEN) {
		console.log('Sending step command');
		ws.send(JSON.stringify({ type: 'step' }));
	} else {
		console.warn('Cannot send step - WebSocket not connected, state:', ws?.readyState);
	}
}

export function sendSetSpeed(delayMs: number): void {
	if (ws && ws.readyState === WebSocket.OPEN) {
		ws.send(JSON.stringify({ type: 'set_speed', delay_ms: delayMs }));
		playbackSpeed.set(delayMs);
	}
}
