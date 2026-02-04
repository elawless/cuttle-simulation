<script lang="ts">
	export let points: number;
	export let goal: number;
	export let isYou: boolean = false;
	export let yourTurn: boolean = false;
	export let queensCount: number = 0;
	export let kingsCount: number = 0;
	export let playerLabel: string = '';
</script>

<div class="status-bar" class:your-turn={yourTurn && isYou}>
	<span class="label">{playerLabel || (isYou ? 'YOU' : 'OPPONENT')}</span>
	<span class="divider">|</span>
	<span class="stat">POINTS: <strong>{points}</strong></span>
	<span class="stat">GOAL: <strong>{goal}</strong></span>
	{#if queensCount > 0}
		<span class="badge queen">Q×{queensCount}</span>
	{/if}
	{#if kingsCount > 0}
		<span class="badge king">K×{kingsCount}</span>
	{/if}
	{#if yourTurn && isYou}
		<span class="turn-indicator">YOUR TURN</span>
	{/if}
</div>

<style>
	.status-bar {
		display: flex;
		align-items: center;
		gap: 12px;
		padding: 8px 16px;
		background: rgba(0, 0, 0, 0.4);
		border-radius: 6px;
		font-size: 12px;
		color: #94a3b8;
	}

	.status-bar.your-turn {
		background: rgba(34, 197, 94, 0.15);
		border: 1px solid rgba(34, 197, 94, 0.3);
	}

	.label {
		font-weight: 700;
		color: #e2e8f0;
		letter-spacing: 0.05em;
	}

	.divider {
		color: #475569;
	}

	.stat {
		color: #94a3b8;
	}

	.stat strong {
		color: #3b82f6;
		font-weight: 700;
	}

	.badge {
		font-size: 10px;
		font-weight: 600;
		padding: 2px 6px;
		border-radius: 4px;
	}

	.badge.queen {
		background: rgba(236, 72, 153, 0.2);
		color: #f472b6;
	}

	.badge.king {
		background: rgba(251, 191, 36, 0.2);
		color: #fbbf24;
	}

	.turn-indicator {
		margin-left: auto;
		font-weight: 700;
		color: #22c55e;
		animation: pulse 1.5s infinite;
	}

	@keyframes pulse {
		0%, 100% { opacity: 1; }
		50% { opacity: 0.6; }
	}
</style>
