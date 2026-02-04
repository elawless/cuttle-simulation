<script lang="ts">
	import Card from '$lib/components/cards/Card.svelte';
	import type { Player, Move, JackPair } from '$lib/types';

	export let player: Player;
	export let isCurrentPlayer: boolean = false;
	export let label: string = '';
	export let selectableMoves: Move[] = [];
	export let onSelectMove: ((move: Move) => void) | undefined = undefined;

	function getMoveForCard(card: any): Move | undefined {
		if (!selectableMoves.length) return undefined;

		// Check for moves that target this card (scuttle, jack steal, etc.)
		return selectableMoves.find((move) => {
			if (move.target) {
				return move.target.rank === card.rank && move.target.suit === card.suit;
			}
			return false;
		});
	}

	function isCardTargetable(card: any): boolean {
		return getMoveForCard(card) !== undefined;
	}
</script>

<div class="player-field" class:current={isCurrentPlayer}>
	<div class="header">
		<span class="label">{label}</span>
		<span class="points">
			{player.point_total} / {player.point_threshold} pts
		</span>
		{#if player.queens_count > 0}
			<span class="badge queen">
				{player.queens_count} Queen{player.queens_count > 1 ? 's' : ''}
			</span>
		{/if}
		{#if player.kings_count > 0}
			<span class="badge king">
				{player.kings_count} King{player.kings_count > 1 ? 's' : ''}
			</span>
		{/if}
	</div>

	<div class="sections">
		<!-- Points Field -->
		<div class="section">
			<div class="section-label">Points</div>
			<div class="cards">
				{#if player.points_field.length === 0 && player.jacks.length === 0}
					<div class="empty">No points</div>
				{:else}
					{#each player.points_field as card}
						{@const move = getMoveForCard(card)}
						<Card
							{card}
							selectable={isCardTargetable(card)}
							onClick={move && onSelectMove ? () => onSelectMove(move) : undefined}
						/>
					{/each}
					{#each player.jacks as jackPair}
						<div class="jack-stolen">
							<Card card={jackPair.stolen} small />
							<div class="jack-indicator">
								<Card card={jackPair.jack} small />
							</div>
						</div>
					{/each}
				{/if}
			</div>
		</div>

		<!-- Permanents -->
		<div class="section">
			<div class="section-label">Permanents</div>
			<div class="cards">
				{#if player.permanents.length === 0}
					<div class="empty">No permanents</div>
				{:else}
					{#each player.permanents as card}
						{@const move = getMoveForCard(card)}
						<Card
							{card}
							selectable={isCardTargetable(card)}
							onClick={move && onSelectMove ? () => onSelectMove(move) : undefined}
						/>
					{/each}
				{/if}
			</div>
		</div>
	</div>
</div>

<style>
	.player-field {
		background: linear-gradient(135deg, #f8fafc 0%, #f1f5f9 100%);
		border: 2px solid #e2e8f0;
		border-radius: 12px;
		padding: 16px;
	}

	.player-field.current {
		border-color: #3b82f6;
		box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.2);
	}

	.header {
		display: flex;
		align-items: center;
		gap: 12px;
		margin-bottom: 12px;
	}

	.label {
		font-size: 16px;
		font-weight: 700;
		color: #1e293b;
	}

	.points {
		font-size: 14px;
		font-weight: 600;
		color: #3b82f6;
		background: #eff6ff;
		padding: 4px 8px;
		border-radius: 6px;
	}

	.badge {
		font-size: 11px;
		font-weight: 600;
		padding: 3px 6px;
		border-radius: 4px;
	}

	.badge.queen {
		background: #fce7f3;
		color: #be185d;
	}

	.badge.king {
		background: #fef3c7;
		color: #92400e;
	}

	.sections {
		display: flex;
		flex-direction: column;
		gap: 16px;
	}

	.section {
		display: flex;
		flex-direction: column;
		gap: 8px;
	}

	.section-label {
		font-size: 11px;
		font-weight: 600;
		color: #64748b;
		text-transform: uppercase;
		letter-spacing: 0.05em;
	}

	.cards {
		display: flex;
		flex-wrap: wrap;
		gap: 8px;
		min-height: 60px;
		align-items: flex-start;
	}

	.empty {
		color: #94a3b8;
		font-size: 13px;
		font-style: italic;
	}

	.jack-stolen {
		position: relative;
	}

	.jack-indicator {
		position: absolute;
		bottom: -8px;
		right: -8px;
		transform: scale(0.6);
		transform-origin: bottom right;
		opacity: 0.9;
	}
</style>
