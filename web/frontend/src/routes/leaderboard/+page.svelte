<script lang="ts">
	import { onMount } from 'svelte';
	import type { LeaderboardEntry } from '$lib/types';

	// API base URL - use environment variable in production
	const API_BASE = import.meta.env.VITE_API_URL || '/api';

	let entries: LeaderboardEntry[] = [];
	let pool = 'all';  // Default to 'all' to show CLI tournament data too
	let isLoading = true;
	let error: string | null = null;

	async function fetchLeaderboard() {
		isLoading = true;
		error = null;

		try {
			// Use API_BASE consistently; in local dev without VITE_API_URL, use localhost:8000
			const apiBase = import.meta.env.VITE_API_URL;
			const isDevLocal = window.location.port === '5173' && !apiBase;
			const baseUrl = isDevLocal ? 'http://localhost:8000/api' : API_BASE;

			const response = await fetch(`${baseUrl}/leaderboard?pool=${pool}&limit=50`);
			if (!response.ok) {
				throw new Error('Failed to fetch leaderboard');
			}
			const data = await response.json();
			entries = data.entries || [];
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to load leaderboard';
			entries = [];
		} finally {
			isLoading = false;
		}
	}

	onMount(() => {
		fetchLeaderboard();
	});

	function handlePoolChange() {
		fetchLeaderboard();
	}

	function formatRating(rating: number): string {
		return Math.round(rating).toString();
	}
</script>

<svelte:head>
	<title>Cuttle - Leaderboard</title>
</svelte:head>

<div class="leaderboard-page">
	<header class="header">
		<a href="/" class="back-btn">← Home</a>
		<h1>Leaderboard</h1>
	</header>

	<main class="content">
		<div class="controls">
			<label for="pool">Rating Pool:</label>
			<select id="pool" bind:value={pool} on:change={handlePoolChange}>
				<option value="all">All Games (Web + CLI)</option>
				<option value="web">Web Games Only</option>
				<option value="llm-only">LLM Players Only</option>
				<option value="mcts-only">MCTS Players Only</option>
			</select>
		</div>

		{#if error}
			<div class="error">{error}</div>
		{/if}

		{#if isLoading}
			<div class="loading">
				<div class="spinner"></div>
				<p>Loading leaderboard...</p>
			</div>
		{:else if entries.length === 0}
			<div class="empty">
				<p>No players found in this pool yet.</p>
				<p class="hint">Play some games to appear on the leaderboard!</p>
			</div>
		{:else}
			<div class="table-container">
				<table class="leaderboard-table">
					<thead>
						<tr>
							<th class="rank-col">Rank</th>
							<th class="player-col">Player</th>
							<th class="rating-col">Rating</th>
							<th class="games-col">Games</th>
						</tr>
					</thead>
					<tbody>
						{#each entries as entry}
							<tr class:top-three={entry.rank <= 3}>
								<td class="rank-col">
									{#if entry.rank === 1}
										<span class="medal gold">1</span>
									{:else if entry.rank === 2}
										<span class="medal silver">2</span>
									{:else if entry.rank === 3}
										<span class="medal bronze">3</span>
									{:else}
										{entry.rank}
									{/if}
								</td>
								<td class="player-col">
									<span class="player-name">{entry.display_name}</span>
									{#if entry.is_human}
										<span class="badge human">Human</span>
									{:else}
										<span class="badge ai">{entry.provider}</span>
									{/if}
								</td>
								<td class="rating-col">
									<span class="rating">{formatRating(entry.rating)}</span>
								</td>
								<td class="games-col">{entry.games_played}</td>
							</tr>
						{/each}
					</tbody>
				</table>
			</div>
		{/if}
	</main>
</div>

<style>
	.leaderboard-page {
		min-height: 100vh;
		display: flex;
		flex-direction: column;
	}

	.header {
		display: flex;
		align-items: center;
		gap: 16px;
		padding: 16px 24px;
		background: #1e293b;
		border-bottom: 1px solid #334155;
	}

	.header h1 {
		margin: 0;
		font-size: 24px;
		color: white;
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
		text-decoration: none;
		transition: all 0.2s ease;
	}

	.back-btn:hover {
		background: #334155;
		color: white;
	}

	.content {
		flex: 1;
		padding: 24px;
		max-width: 800px;
		margin: 0 auto;
		width: 100%;
	}

	.controls {
		display: flex;
		align-items: center;
		gap: 12px;
		margin-bottom: 24px;
	}

	.controls label {
		font-size: 14px;
		color: #94a3b8;
	}

	.controls select {
		padding: 8px 12px;
		font-size: 14px;
		background: #1e293b;
		border: 1px solid #334155;
		border-radius: 6px;
		color: white;
		cursor: pointer;
	}

	.controls select:focus {
		outline: none;
		border-color: #3b82f6;
	}

	.error {
		padding: 16px;
		background: rgba(239, 68, 68, 0.2);
		border: 1px solid #ef4444;
		border-radius: 8px;
		color: #fca5a5;
		margin-bottom: 24px;
	}

	.loading {
		display: flex;
		flex-direction: column;
		align-items: center;
		justify-content: center;
		padding: 64px;
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

	.empty {
		text-align: center;
		padding: 64px;
		color: #94a3b8;
	}

	.empty .hint {
		font-size: 14px;
		color: #64748b;
	}

	.table-container {
		background: #1e293b;
		border-radius: 12px;
		overflow: hidden;
	}

	.leaderboard-table {
		width: 100%;
		border-collapse: collapse;
	}

	.leaderboard-table th {
		text-align: left;
		padding: 16px;
		font-size: 12px;
		font-weight: 600;
		color: #64748b;
		text-transform: uppercase;
		letter-spacing: 0.05em;
		background: rgba(0, 0, 0, 0.2);
		border-bottom: 1px solid #334155;
	}

	.leaderboard-table td {
		padding: 16px;
		font-size: 14px;
		color: #e2e8f0;
		border-bottom: 1px solid rgba(255, 255, 255, 0.05);
	}

	.leaderboard-table tr:hover {
		background: rgba(255, 255, 255, 0.03);
	}

	.leaderboard-table tr.top-three {
		background: rgba(251, 191, 36, 0.05);
	}

	.rank-col {
		width: 60px;
		text-align: center !important;
	}

	.rating-col,
	.games-col {
		width: 100px;
		text-align: right !important;
	}

	.medal {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		width: 28px;
		height: 28px;
		border-radius: 50%;
		font-size: 12px;
		font-weight: 700;
	}

	.medal.gold {
		background: linear-gradient(135deg, #fbbf24 0%, #d97706 100%);
		color: #1a1a1a;
	}

	.medal.silver {
		background: linear-gradient(135deg, #9ca3af 0%, #6b7280 100%);
		color: white;
	}

	.medal.bronze {
		background: linear-gradient(135deg, #d97706 0%, #92400e 100%);
		color: white;
	}

	.player-col {
		display: flex;
		align-items: center;
		gap: 8px;
	}

	.player-name {
		font-weight: 500;
	}

	.badge {
		display: inline-block;
		padding: 2px 6px;
		font-size: 10px;
		font-weight: 600;
		border-radius: 4px;
		text-transform: uppercase;
	}

	.badge.human {
		background: #22c55e;
		color: white;
	}

	.badge.ai {
		background: #6366f1;
		color: white;
	}

	.rating {
		font-weight: 600;
		font-family: monospace;
	}

	@media (max-width: 600px) {
		.content {
			padding: 16px;
		}

		.leaderboard-table th,
		.leaderboard-table td {
			padding: 12px 8px;
		}

		.games-col {
			display: none;
		}
	}
</style>
