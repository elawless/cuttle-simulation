<script lang="ts">
	import { goto } from '$app/navigation';
	import { onMount } from 'svelte';
	import { createGame, fetchStrategies } from '$lib/stores/gameStore';

	let strategies: { name: string; description: string }[] = [];
	let selectedStrategy = 'heuristic';
	let player0Strategy = 'heuristic';  // For AI vs AI mode
	let player1Strategy = 'mcts';       // For AI vs AI mode
	let handLimit: number | null = 8;   // Default to 8-card limit
	let humanGoesFirst = true;          // true = human is player 0, false = human is player 1
	let gameSpeed = 500;                // Delay between AI moves in ms
	let isCreating = false;
	let error: string | null = null;

	onMount(async () => {
		try {
			strategies = await fetchStrategies();
		} catch (e) {
			error = 'Failed to load strategies. Is the server running?';
		}
	});

	async function startGame() {
		isCreating = true;
		error = null;

		try {
			let gameId: string;
			if (humanGoesFirst) {
				// Human is player 0 (goes first, 5 cards)
				gameId = await createGame('human', null, 'ai', selectedStrategy, undefined, handLimit);
				goto(`/game/${gameId}?viewer=0`);
			} else {
				// Human is player 1 (goes second, 6 cards)
				gameId = await createGame('ai', selectedStrategy, 'human', null, undefined, handLimit);
				goto(`/game/${gameId}?viewer=1`);
			}
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to create game';
			isCreating = false;
		}
	}

	async function watchAiGame() {
		isCreating = true;
		error = null;

		try {
			const gameId = await createGame('ai', player0Strategy, 'ai', player1Strategy, undefined, handLimit, true);
			goto(`/game/${gameId}?watch=true&speed=${gameSpeed}`);
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to create game';
			isCreating = false;
		}
	}
</script>

<svelte:head>
	<title>Cuttle - Card Game</title>
</svelte:head>

<div class="home">
	<div class="hero">
		<h1 class="title">Cuttle</h1>
		<p class="subtitle">The classic two-player card combat game</p>
	</div>

	<div class="game-setup">
		<div class="card">
			<h2>New Game</h2>

			{#if error}
				<div class="error">{error}</div>
			{/if}

			<div class="form-group">
				<label for="strategy">AI Opponent</label>
				<select id="strategy" bind:value={selectedStrategy} disabled={isCreating}>
					{#each strategies as strategy}
						<option value={strategy.name}>{strategy.name} - {strategy.description}</option>
					{/each}
				</select>
			</div>

			<div class="form-group">
				<label for="goFirst">Who Goes First</label>
				<select id="goFirst" bind:value={humanGoesFirst} disabled={isCreating}>
					<option value={true}>You (5 cards)</option>
					<option value={false}>AI (you get 6 cards)</option>
				</select>
			</div>

			<div class="form-group">
				<label for="handLimit">Hand Limit</label>
				<select id="handLimit" bind:value={handLimit} disabled={isCreating}>
					<option value={8}>8 cards (standard)</option>
					<option value={null}>Unlimited</option>
				</select>
			</div>

			<div class="actions">
				<button class="btn primary" on:click={startGame} disabled={isCreating}>
					{#if isCreating}
						Starting...
					{:else}
						Play vs AI
					{/if}
				</button>
			</div>

			<div class="divider"></div>

			<h3>AI vs AI Match</h3>

			<div class="ai-vs-ai-setup">
				<div class="form-group">
					<label for="player0Strategy">Player 1 (goes first)</label>
					<select id="player0Strategy" bind:value={player0Strategy} disabled={isCreating}>
						{#each strategies as strategy}
							<option value={strategy.name}>{strategy.name}</option>
						{/each}
					</select>
				</div>

				<span class="vs">vs</span>

				<div class="form-group">
					<label for="player1Strategy">Player 2</label>
					<select id="player1Strategy" bind:value={player1Strategy} disabled={isCreating}>
						{#each strategies as strategy}
							<option value={strategy.name}>{strategy.name}</option>
						{/each}
					</select>
				</div>
			</div>

			<div class="form-group">
				<label for="gameSpeed">Game Speed</label>
				<select id="gameSpeed" bind:value={gameSpeed} disabled={isCreating}>
					<option value={100}>Fast (0.1s per turn)</option>
					<option value={300}>Quick (0.3s per turn)</option>
					<option value={500}>Normal (0.5s per turn)</option>
					<option value={1000}>Slow (1s per turn)</option>
					<option value={2000}>Very Slow (2s per turn)</option>
				</select>
			</div>

			<div class="actions">
				<button class="btn secondary" on:click={watchAiGame} disabled={isCreating}>
					Watch AI vs AI
				</button>
			</div>
		</div>

		<div class="card rules">
			<h2>How to Play</h2>
			<div class="rules-content">
				<p><strong>Goal:</strong> Reach 21 points with cards on your field.</p>

				<h3>Card Types</h3>
				<ul>
					<li><strong>A-10:</strong> Play for points or use as one-off effects</li>
					<li><strong>Jack:</strong> Steal opponent's point card</li>
					<li><strong>Queen:</strong> Protects your cards from targeting</li>
					<li><strong>King:</strong> Reduces your win threshold by 7</li>
				</ul>

				<h3>One-Off Effects</h3>
				<ul>
					<li><strong>Ace:</strong> Scrap all point cards</li>
					<li><strong>Two:</strong> Destroy a permanent OR counter a one-off</li>
					<li><strong>Three:</strong> Revive a card from scrap</li>
					<li><strong>Four:</strong> Opponent discards 2 cards</li>
					<li><strong>Five:</strong> Draw 2 cards</li>
					<li><strong>Six:</strong> Scrap all permanents</li>
					<li><strong>Seven:</strong> Play from top of deck</li>
					<li><strong>Nine:</strong> Return a permanent to hand</li>
				</ul>

				<h3>Scuttling</h3>
				<p>Play a higher point card to destroy opponent's point card.</p>
			</div>
		</div>
	</div>
</div>

<style>
	.home {
		min-height: 100vh;
		padding: 32px;
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: 32px;
	}

	.hero {
		text-align: center;
		padding: 48px 0;
	}

	.title {
		font-size: 64px;
		font-weight: 800;
		margin: 0;
		background: linear-gradient(135deg, #dc2626 0%, #f59e0b 100%);
		-webkit-background-clip: text;
		-webkit-text-fill-color: transparent;
		background-clip: text;
	}

	.subtitle {
		font-size: 20px;
		color: #94a3b8;
		margin: 8px 0 0 0;
	}

	.game-setup {
		display: grid;
		grid-template-columns: 1fr 1fr;
		gap: 24px;
		max-width: 900px;
		width: 100%;
	}

	@media (max-width: 768px) {
		.game-setup {
			grid-template-columns: 1fr;
		}
	}

	.card {
		background: #1e293b;
		border-radius: 12px;
		padding: 24px;
	}

	.card h2 {
		margin: 0 0 20px 0;
		font-size: 20px;
		color: white;
	}

	.error {
		padding: 12px;
		background: rgba(239, 68, 68, 0.2);
		border: 1px solid #ef4444;
		border-radius: 6px;
		color: #fca5a5;
		margin-bottom: 16px;
		font-size: 14px;
	}

	.form-group {
		margin-bottom: 20px;
	}

	.form-group label {
		display: block;
		font-size: 14px;
		font-weight: 500;
		color: #94a3b8;
		margin-bottom: 8px;
	}

	.form-group select {
		width: 100%;
		padding: 10px 12px;
		font-size: 14px;
		background: #0f172a;
		border: 1px solid #334155;
		border-radius: 6px;
		color: white;
		cursor: pointer;
	}

	.form-group select:focus {
		outline: none;
		border-color: #3b82f6;
	}

	.actions {
		display: flex;
		flex-direction: column;
		gap: 12px;
	}

	.btn {
		padding: 12px 24px;
		font-size: 16px;
		font-weight: 600;
		border: none;
		border-radius: 8px;
		cursor: pointer;
		transition: all 0.2s ease;
	}

	.btn:disabled {
		opacity: 0.6;
		cursor: not-allowed;
	}

	.btn.primary {
		background: linear-gradient(135deg, #dc2626 0%, #b91c1c 100%);
		color: white;
	}

	.btn.primary:hover:not(:disabled) {
		transform: translateY(-2px);
		box-shadow: 0 4px 12px rgba(220, 38, 38, 0.4);
	}

	.btn.secondary {
		background: #334155;
		color: white;
	}

	.btn.secondary:hover:not(:disabled) {
		background: #475569;
	}

	.divider {
		height: 1px;
		background: #334155;
		margin: 20px 0;
	}

	.card h3 {
		margin: 0 0 12px 0;
		font-size: 16px;
		color: #94a3b8;
	}

	.ai-vs-ai-setup {
		display: flex;
		align-items: flex-end;
		gap: 12px;
		margin-bottom: 16px;
	}

	.ai-vs-ai-setup .form-group {
		flex: 1;
		margin-bottom: 0;
	}

	.vs {
		padding-bottom: 10px;
		color: #64748b;
		font-weight: 600;
		font-size: 14px;
	}

	.rules {
		font-size: 14px;
		color: #cbd5e1;
	}

	.rules h3 {
		font-size: 14px;
		color: #f59e0b;
		margin: 16px 0 8px 0;
	}

	.rules ul {
		margin: 0;
		padding-left: 20px;
	}

	.rules li {
		margin-bottom: 4px;
	}

	.rules p {
		margin: 0 0 8px 0;
	}

	.rules-content {
		max-height: 400px;
		overflow-y: auto;
	}
</style>
