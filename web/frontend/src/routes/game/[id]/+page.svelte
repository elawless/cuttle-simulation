<script lang="ts">
	import { page } from '$app/stores';
	import { goto } from '$app/navigation';
	import { onMount, onDestroy } from 'svelte';
	import GameBoard from '$lib/components/game/GameBoard.svelte';
	import {
		loadGame,
		connectWebSocket,
		disconnectWebSocket,
		resetGame,
		gameState,
		isLoading,
		error,
		moveHistory,
		playbackSpeed,
		sendSetSpeed
	} from '$lib/stores/gameStore';

	$: gameId = $page.params.id;
	$: isWatch = $page.url.searchParams.get('watch') === 'true';
	$: viewer = parseInt($page.url.searchParams.get('viewer') || '0', 10);
	$: initialSpeed = parseInt($page.url.searchParams.get('speed') || '500', 10);

	let mounted = false;
	let showingReplay = false;
	let replayIndex = 0;

	onMount(async () => {
		mounted = true;
		// Set initial speed from URL
		playbackSpeed.set(initialSpeed);
		await loadGame(gameId, viewer);
		connectWebSocket(gameId, viewer, isWatch, initialSpeed);
	});

	onDestroy(() => {
		disconnectWebSocket();
	});

	function handleNewGame() {
		resetGame();
		goto('/');
	}

	function handlePlayAgain() {
		// Create a new game with same settings
		resetGame();
		goto('/');
	}
</script>

<svelte:head>
	<title>Cuttle - Game {gameId.slice(0, 8)}</title>
</svelte:head>

<div class="game-page">
	<header class="header">
		<button class="back-btn" on:click={handleNewGame}>
			← New Game
		</button>
		<div class="game-id">
			Game: {gameId.slice(0, 8)}...
		</div>
		{#if isWatch}
			<div class="watch-badge">Spectating</div>
		{/if}
	</header>

	<main class="game-container">
		{#if $isLoading && !$gameState}
			<div class="loading">
				<div class="spinner"></div>
				<p>Loading game...</p>
			</div>
		{:else if $error && !$gameState}
			<div class="error-state">
				<h2>Error</h2>
				<p>{$error}</p>
				<button class="btn" on:click={handleNewGame}>Back to Home</button>
			</div>
		{:else}
			<GameBoard watchMode={isWatch} />

			{#if $gameState?.winner !== null && $gameState?.winner !== undefined && !showingReplay}
				<div class="game-over-overlay">
					<div class="game-over-modal">
						<h2>
							{#if isWatch}
								Player {$gameState.winner + 1} Wins!
							{:else}
								{$gameState.winner === viewer ? '🎉 You Won!' : '😔 AI Won'}
							{/if}
						</h2>
						<p class="win-reason">
							{#if $gameState.win_reason === 'POINTS'}
								Reached the point threshold!
							{:else if $gameState.win_reason === 'EMPTY_DECK_POINTS'}
								More points when deck emptied!
							{:else if $gameState.win_reason === 'OPPONENT_EMPTY_HAND'}
								{isWatch ? `Player ${2 - $gameState.winner}` : 'Opponent'} ran out of cards!
							{/if}
						</p>
						<div class="final-scores">
							<div class="score">
								<span class="label">{isWatch ? 'Player 1' : 'You'}</span>
								<span class="value">{$gameState.players[viewer].point_total} pts</span>
							</div>
							<div class="score">
								<span class="label">{isWatch ? 'Player 2' : 'AI'}</span>
								<span class="value">{$gameState.players[1 - viewer].point_total} pts</span>
							</div>
						</div>
						<div class="modal-actions">
							<button class="btn primary" on:click={handlePlayAgain}>
								{isWatch ? 'Watch Another' : 'Play Again'}
							</button>
							{#if isWatch && $moveHistory.length > 0}
								<button class="btn secondary" on:click={() => { showingReplay = true; replayIndex = 0; }}>
									Replay Game
								</button>
							{/if}
							<button class="btn secondary" on:click={handleNewGame}>
								New Game
							</button>
						</div>
					</div>
				</div>
			{/if}

			{#if showingReplay}
				<div class="replay-overlay">
					<div class="replay-panel">
						<h3>Game Replay</h3>
						<div class="replay-info">
							Move {replayIndex + 1} of {$moveHistory.length}
						</div>
						{#if $moveHistory[replayIndex]}
							<div class="replay-move">
								<span class="player-badge" class:p1={$moveHistory[replayIndex].player === 0} class:p2={$moveHistory[replayIndex].player === 1}>
									Player {$moveHistory[replayIndex].player + 1}
								</span>
								<span class="move-desc">{$moveHistory[replayIndex].move}</span>
							</div>
							{#if $moveHistory[replayIndex].points_after && $moveHistory[replayIndex].points_after.length >= 2}
								<div class="replay-scores">
									P1: {$moveHistory[replayIndex].points_after?.[0] ?? 0} pts | P2: {$moveHistory[replayIndex].points_after?.[1] ?? 0} pts
								</div>
							{/if}
						{/if}
						<div class="replay-controls">
							<button class="replay-btn" on:click={() => replayIndex = 0} disabled={replayIndex === 0}>
								⏮ Start
							</button>
							<button class="replay-btn" on:click={() => replayIndex = Math.max(0, replayIndex - 1)} disabled={replayIndex === 0}>
								◀ Prev
							</button>
							<button class="replay-btn" on:click={() => replayIndex = Math.min($moveHistory.length - 1, replayIndex + 1)} disabled={replayIndex >= $moveHistory.length - 1}>
								Next ▶
							</button>
							<button class="replay-btn" on:click={() => replayIndex = $moveHistory.length - 1} disabled={replayIndex >= $moveHistory.length - 1}>
								End ⏭
							</button>
						</div>
						<button class="btn secondary close-replay" on:click={() => showingReplay = false}>
							Close Replay
						</button>
					</div>
				</div>
			{/if}
		{/if}
	</main>
</div>

<style>
	.game-page {
		height: 100vh;
		display: flex;
		flex-direction: column;
		overflow: hidden;
	}

	.header {
		display: flex;
		align-items: center;
		gap: 16px;
		padding: 12px 16px;
		background: #1e293b;
		border-bottom: 1px solid #334155;
	}

	.back-btn {
		padding: 8px 16px;
		font-size: 14px;
		font-weight: 500;
		background: transparent;
		border: 1px solid #475569;
		border-radius: 6px;
		color: #94a3b8;
		cursor: pointer;
		transition: all 0.2s ease;
	}

	.back-btn:hover {
		background: #334155;
		color: white;
	}

	.game-id {
		font-size: 14px;
		color: #64748b;
		font-family: monospace;
	}

	.watch-badge {
		padding: 4px 8px;
		font-size: 12px;
		font-weight: 600;
		background: #7c3aed;
		color: white;
		border-radius: 4px;
	}

	.game-container {
		flex: 1;
		overflow: hidden;
		position: relative;
	}

	.loading {
		display: flex;
		flex-direction: column;
		align-items: center;
		justify-content: center;
		height: 100%;
		gap: 16px;
		color: #94a3b8;
	}

	.spinner {
		width: 40px;
		height: 40px;
		border: 3px solid #334155;
		border-top-color: #3b82f6;
		border-radius: 50%;
		animation: spin 1s linear infinite;
	}

	@keyframes spin {
		to {
			transform: rotate(360deg);
		}
	}

	.error-state {
		display: flex;
		flex-direction: column;
		align-items: center;
		justify-content: center;
		height: 100%;
		gap: 16px;
		color: #f87171;
	}

	.error-state h2 {
		margin: 0;
	}

	.error-state p {
		color: #94a3b8;
	}

	.game-over-overlay {
		position: absolute;
		inset: 0;
		background: rgba(0, 0, 0, 0.7);
		display: flex;
		align-items: center;
		justify-content: center;
		z-index: 100;
	}

	.game-over-modal {
		background: #1e293b;
		border-radius: 16px;
		padding: 32px;
		text-align: center;
		max-width: 400px;
		width: 90%;
	}

	.game-over-modal h2 {
		margin: 0 0 8px 0;
		font-size: 28px;
	}

	.win-reason {
		color: #94a3b8;
		margin: 0 0 24px 0;
	}

	.final-scores {
		display: flex;
		justify-content: center;
		gap: 32px;
		margin-bottom: 24px;
	}

	.score {
		display: flex;
		flex-direction: column;
		gap: 4px;
	}

	.score .label {
		font-size: 14px;
		color: #64748b;
	}

	.score .value {
		font-size: 24px;
		font-weight: 700;
		color: white;
	}

	.modal-actions {
		display: flex;
		gap: 12px;
		justify-content: center;
	}

	.btn {
		padding: 12px 24px;
		font-size: 14px;
		font-weight: 600;
		border: none;
		border-radius: 8px;
		cursor: pointer;
		transition: all 0.2s ease;
	}

	.btn.primary {
		background: linear-gradient(135deg, #dc2626 0%, #b91c1c 100%);
		color: white;
	}

	.btn.primary:hover {
		transform: translateY(-2px);
		box-shadow: 0 4px 12px rgba(220, 38, 38, 0.4);
	}

	.btn.secondary {
		background: #334155;
		color: white;
	}

	.btn.secondary:hover {
		background: #475569;
	}

	.replay-overlay {
		position: absolute;
		inset: 0;
		background: rgba(0, 0, 0, 0.85);
		display: flex;
		align-items: center;
		justify-content: center;
		z-index: 100;
	}

	.replay-panel {
		background: #1e293b;
		border-radius: 16px;
		padding: 24px 32px;
		text-align: center;
		max-width: 500px;
		width: 90%;
	}

	.replay-panel h3 {
		margin: 0 0 16px 0;
		font-size: 20px;
		color: #e2e8f0;
	}

	.replay-info {
		color: #64748b;
		font-size: 14px;
		margin-bottom: 16px;
	}

	.replay-move {
		display: flex;
		align-items: center;
		justify-content: center;
		gap: 12px;
		padding: 16px;
		background: rgba(0, 0, 0, 0.3);
		border-radius: 8px;
		margin-bottom: 12px;
	}

	.player-badge {
		padding: 4px 10px;
		border-radius: 4px;
		font-size: 12px;
		font-weight: 600;
	}

	.player-badge.p1 {
		background: #3b82f6;
		color: white;
	}

	.player-badge.p2 {
		background: #f59e0b;
		color: white;
	}

	.move-desc {
		color: #e2e8f0;
		font-size: 14px;
	}

	.replay-scores {
		color: #94a3b8;
		font-size: 13px;
		margin-bottom: 16px;
	}

	.replay-controls {
		display: flex;
		gap: 8px;
		justify-content: center;
		margin-bottom: 16px;
	}

	.replay-btn {
		padding: 8px 12px;
		background: #334155;
		border: none;
		border-radius: 6px;
		color: #e2e8f0;
		font-size: 13px;
		cursor: pointer;
		transition: all 0.15s;
	}

	.replay-btn:hover:not(:disabled) {
		background: #475569;
	}

	.replay-btn:disabled {
		opacity: 0.4;
		cursor: not-allowed;
	}

	.close-replay {
		width: 100%;
	}
</style>
