<script lang="ts">
	import Card from '$lib/components/cards/Card.svelte';
	import type { Card as CardType, Move } from '$lib/types';

	export let cards: CardType[] = [];
	export let faceDown: boolean = false;
	export let label: string = '';
	export let selectableMoves: Move[] = [];
	export let onSelectMove: ((move: Move) => void) | undefined = undefined;

	function getMoveForCard(card: CardType): Move | undefined {
		if (!selectableMoves.length) return undefined;

		return selectableMoves.find((move) => {
			if (move.card) {
				return (
					move.card.rank === card.rank &&
					move.card.suit === card.suit &&
					!move.target // Only show moves where this card is the source, not target
				);
			}
			return false;
		});
	}

	function isCardSelectable(card: CardType): boolean {
		return getMoveForCard(card) !== undefined;
	}
</script>

<div class="card-row">
	{#if label}
		<div class="label">{label}</div>
	{/if}

	<div class="cards">
		{#if cards.length === 0}
			<div class="empty">No cards</div>
		{:else}
			{#each cards as card}
				{@const move = getMoveForCard(card)}
				<Card
					{card}
					{faceDown}
					selectable={isCardSelectable(card)}
					onClick={move && onSelectMove ? () => onSelectMove(move) : undefined}
				/>
			{/each}
		{/if}
	</div>
</div>

<style>
	.card-row {
		display: flex;
		flex-direction: column;
		gap: 8px;
	}

	.label {
		font-size: 12px;
		font-weight: 600;
		color: #64748b;
		text-transform: uppercase;
		letter-spacing: 0.05em;
	}

	.cards {
		display: flex;
		flex-wrap: wrap;
		gap: 8px;
		min-height: 112px;
		align-items: flex-start;
	}

	.empty {
		color: #94a3b8;
		font-size: 14px;
		display: flex;
		align-items: center;
		height: 112px;
	}
</style>
