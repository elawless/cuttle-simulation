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
		error
	} from '$lib/stores/gameStore';

	$: gameId = $page.params.id;
	$: isWatch = $page.url.searchParams.get('watch') === 'true';
	$: viewer = parseInt($page.url.searchParams.get('viewer') || '0', 10);

	let mounted = false;

	onMount(async () => {
		mounted = true;
		await loadGame(gameId, viewer);
		connectWebSocket(gameId, viewer);
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
			<GameBoard />

			{#if $gameState?.winner !== null && $gameState?.winner !== undefined}
				<div class="game-over-overlay">
					<div class="game-over-modal">
						<h2>
							{$gameState.winner === viewer ? '🎉 You Won!' : '😔 AI Won'}
						</h2>
						<p class="win-reason">
							{#if $gameState.win_reason === 'POINTS'}
								Reached the point threshold!
							{:else if $gameState.win_reason === 'EMPTY_DECK_POINTS'}
								More points when deck emptied!
							{:else if $gameState.win_reason === 'OPPONENT_EMPTY_HAND'}
								Opponent ran out of cards!
							{/if}
						</p>
						<div class="final-scores">
							<div class="score">
								<span class="label">You</span>
								<span class="value">{$gameState.players[viewer].point_total} pts</span>
							</div>
							<div class="score">
								<span class="label">AI</span>
								<span class="value">{$gameState.players[1 - viewer].point_total} pts</span>
							</div>
						</div>
						<div class="modal-actions">
							<button class="btn primary" on:click={handlePlayAgain}>
								Play Again
							</button>
							<button class="btn secondary" on:click={handleNewGame}>
								New Game
							</button>
						</div>
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
</style>
