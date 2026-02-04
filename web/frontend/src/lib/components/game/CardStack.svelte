<script lang="ts">
	import Card from '$lib/components/cards/Card.svelte';
	import type { Card as CardType } from '$lib/types';

	export let cards: CardType[] = [];
	export let faceDown: boolean = false;
	export let label: string = '';
	export let showCount: boolean = true;
	export let maxVisible: number = 3;
</script>

<div class="card-stack">
	{#if label}
		<div class="label">{label}</div>
	{/if}

	<div class="stack-container">
		{#if cards.length === 0}
			<div class="empty-stack">
				<span>Empty</span>
			</div>
		{:else}
			<div class="cards" style="--count: {Math.min(cards.length, maxVisible)}">
				{#each cards.slice(-maxVisible) as card, i}
					<div class="stacked-card" style="--index: {i}">
						<Card {card} {faceDown} small />
					</div>
				{/each}
			</div>
		{/if}

		{#if showCount && cards.length > 0}
			<div class="count">{cards.length}</div>
		{/if}
	</div>
</div>

<style>
	.card-stack {
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: 4px;
	}

	.label {
		font-size: 12px;
		font-weight: 600;
		color: #64748b;
		text-transform: uppercase;
		letter-spacing: 0.05em;
	}

	.stack-container {
		position: relative;
	}

	.empty-stack {
		width: 60px;
		height: 84px;
		border: 2px dashed #cbd5e1;
		border-radius: 6px;
		display: flex;
		align-items: center;
		justify-content: center;
		color: #94a3b8;
		font-size: 11px;
	}

	.cards {
		position: relative;
		width: 60px;
		height: calc(84px + (var(--count) - 1) * 4px);
	}

	.stacked-card {
		position: absolute;
		top: calc(var(--index) * 4px);
		left: calc(var(--index) * 2px);
	}

	.count {
		position: absolute;
		bottom: -8px;
		right: -8px;
		background: #1e293b;
		color: white;
		font-size: 11px;
		font-weight: 600;
		width: 22px;
		height: 22px;
		border-radius: 50%;
		display: flex;
		align-items: center;
		justify-content: center;
	}
</style>
