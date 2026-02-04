<script lang="ts">
	import Card from '$lib/components/cards/Card.svelte';
	import type { Card as CardType, Move } from '$lib/types';

	export let card: CardType;
	export let moves: Move[] = [];
	export let onSelectMove: (move: Move) => void;
	export let onCancel: () => void;

	function getMoveIcon(move: Move): string {
		// Jack steal moves
		if (card.rank === 11 && move.target) {
			return '🎯';
		}
		// 3 one-off (revive) with target
		if (card.rank === 3 && move.type === 'PLAY_ONE_OFF' && move.target) {
			return '♻️';
		}
		// 2 one-off (destroy permanent) with target
		if (card.rank === 2 && move.type === 'PLAY_ONE_OFF' && move.target) {
			return '💥';
		}
		// 9 one-off (return to hand) with target
		if (card.rank === 9 && move.type === 'PLAY_ONE_OFF' && move.target) {
			return '↩️';
		}
		switch (move.type) {
			case 'PLAY_POINTS':
				return '💎';
			case 'SCUTTLE':
				return '⚔️';
			case 'PLAY_ONE_OFF':
				return '✨';
			case 'PLAY_PERMANENT':
				return '🏰';
			default:
				return '🎴';
		}
	}

	function getMoveLabel(move: Move): string {
		// Jack steal moves - show target
		if (card.rank === 11 && move.target) {
			return `Steal ${move.target.rank_symbol}${move.target.suit_symbol}`;
		}
		// Scuttle moves - show target
		if (move.type === 'SCUTTLE' && move.target) {
			return `Scuttle ${move.target.rank_symbol}${move.target.suit_symbol}`;
		}
		// 3 one-off (revive) - show target card being revived
		if (card.rank === 3 && move.type === 'PLAY_ONE_OFF' && move.target) {
			return `Revive ${move.target.rank_symbol}${move.target.suit_symbol}`;
		}
		// 2 one-off (destroy permanent) - show target
		if (card.rank === 2 && move.type === 'PLAY_ONE_OFF' && move.target) {
			return `Destroy ${move.target.rank_symbol}${move.target.suit_symbol}`;
		}
		// 9 one-off (return to hand) - show target
		if (card.rank === 9 && move.type === 'PLAY_ONE_OFF' && move.target) {
			return `Return ${move.target.rank_symbol}${move.target.suit_symbol}`;
		}
		switch (move.type) {
			case 'PLAY_POINTS':
				return 'Points';
			case 'SCUTTLE':
				return 'Scuttle';
			case 'PLAY_ONE_OFF':
				return 'One-Off';
			case 'PLAY_PERMANENT':
				return 'Permanent';
			default:
				return move.type;
		}
	}

	function getMoveDescription(move: Move): string {
		// Jack steal moves
		if (card.rank === 11 && move.target) {
			return `Steal opponent's ${move.target.rank_name} of ${move.target.suit_name} (${move.target.point_value} pts)`;
		}
		// 3 one-off (revive) - show target card details
		if (card.rank === 3 && move.type === 'PLAY_ONE_OFF' && move.target) {
			return `Revive ${move.target.rank_name} of ${move.target.suit_name} from scrap`;
		}
		// 2 one-off (destroy permanent) - show target
		if (card.rank === 2 && move.type === 'PLAY_ONE_OFF' && move.target) {
			return `Destroy opponent's ${move.target.rank_name} of ${move.target.suit_name}`;
		}
		// 9 one-off (return to hand) - show target
		if (card.rank === 9 && move.type === 'PLAY_ONE_OFF' && move.target) {
			return `Return ${move.target.rank_name} of ${move.target.suit_name} to opponent's hand`;
		}
		switch (move.type) {
			case 'PLAY_POINTS':
				return `Add ${card.point_value} points to your field`;
			case 'SCUTTLE':
				return move.target
					? `Destroy opponent's ${move.target.rank_symbol}${move.target.suit_symbol}`
					: 'Destroy opponent\'s lower point card';
			case 'PLAY_ONE_OFF':
				return getOneOffEffect(card.rank);
			case 'PLAY_PERMANENT':
				return getPermanentEffect(card.rank);
			default:
				return move.description;
		}
	}

	function getOneOffEffect(rank: number): string {
		switch (rank) {
			case 1:
				return 'Scrap all point cards on the field';
			case 2:
				return 'Destroy one of opponent\'s permanents';
			case 3:
				return 'Revive a card from the scrap pile';
			case 4:
				return 'Opponent discards two cards';
			case 5:
				return 'Draw two cards from the deck';
			case 6:
				return 'Scrap all permanents on the field';
			case 7:
				return 'Reveal top two cards, play one for free';
			case 9:
				return 'Return a card to opponent\'s hand';
			default:
				return 'Play as one-off effect';
		}
	}

	function getPermanentEffect(rank: number): string {
		switch (rank) {
			case 8:
				return 'See opponent\'s hand (Glasses)';
			case 11:
				return 'Steal opponent\'s point card';
			case 12:
				return 'Protect yourself from targeted effects';
			case 13:
				return 'Reduce your point threshold by 7';
			default:
				return 'Play as permanent';
		}
	}

	function handleKeydown(event: KeyboardEvent) {
		if (event.key === 'Escape') {
			onCancel();
		}
	}
</script>

<svelte:window on:keydown={handleKeydown} />

<!-- svelte-ignore a11y-click-events-have-key-events -->
<!-- svelte-ignore a11y-no-static-element-interactions -->
<div class="modal-backdrop" on:click={onCancel}>
	<div class="modal" on:click|stopPropagation>
		<div class="modal-header">
			<span class="title">Choose Action</span>
			<button class="close-btn" on:click={onCancel}>×</button>
		</div>

		<div class="modal-content">
			<div class="card-preview">
				<Card {card} />
				<span class="card-name">{card.rank_name} of {card.suit_name}</span>
			</div>

			<div class="actions">
				{#each moves as move}
					<button class="action-btn" on:click={() => onSelectMove(move)}>
						<span class="action-icon">{getMoveIcon(move)}</span>
						<div class="action-text">
							<span class="action-label">{getMoveLabel(move)}</span>
							<span class="action-desc">{getMoveDescription(move)}</span>
						</div>
					</button>
				{/each}
			</div>
		</div>

		<div class="modal-footer">
			<button class="cancel-btn" on:click={onCancel}>Cancel</button>
		</div>
	</div>
</div>

<style>
	.modal-backdrop {
		position: fixed;
		inset: 0;
		background: rgba(0, 0, 0, 0.7);
		display: flex;
		align-items: center;
		justify-content: center;
		z-index: 1000;
		backdrop-filter: blur(4px);
	}

	.modal {
		background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%);
		border: 1px solid #334155;
		border-radius: 12px;
		min-width: 320px;
		max-width: 400px;
		box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.5);
	}

	.modal-header {
		display: flex;
		align-items: center;
		justify-content: space-between;
		padding: 16px 20px;
		border-bottom: 1px solid #334155;
	}

	.title {
		font-size: 16px;
		font-weight: 600;
		color: #e2e8f0;
	}

	.close-btn {
		width: 28px;
		height: 28px;
		border: none;
		background: rgba(255, 255, 255, 0.05);
		color: #94a3b8;
		font-size: 20px;
		border-radius: 6px;
		cursor: pointer;
		display: flex;
		align-items: center;
		justify-content: center;
		transition: all 0.15s;
	}

	.close-btn:hover {
		background: rgba(255, 255, 255, 0.1);
		color: #e2e8f0;
	}

	.modal-content {
		padding: 20px;
	}

	.card-preview {
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: 8px;
		margin-bottom: 20px;
	}

	.card-name {
		font-size: 14px;
		font-weight: 600;
		color: #e2e8f0;
	}

	.actions {
		display: flex;
		flex-direction: column;
		gap: 8px;
	}

	.action-btn {
		display: flex;
		align-items: center;
		gap: 12px;
		padding: 12px 16px;
		background: rgba(255, 255, 255, 0.03);
		border: 1px solid #334155;
		border-radius: 8px;
		cursor: pointer;
		text-align: left;
		transition: all 0.15s;
	}

	.action-btn:hover {
		background: rgba(59, 130, 246, 0.15);
		border-color: #3b82f6;
	}

	.action-icon {
		font-size: 24px;
		flex-shrink: 0;
	}

	.action-text {
		display: flex;
		flex-direction: column;
		gap: 2px;
	}

	.action-label {
		font-size: 14px;
		font-weight: 600;
		color: #e2e8f0;
	}

	.action-desc {
		font-size: 12px;
		color: #94a3b8;
	}

	.modal-footer {
		padding: 12px 20px;
		border-top: 1px solid #334155;
		display: flex;
		justify-content: flex-end;
	}

	.cancel-btn {
		padding: 8px 16px;
		background: transparent;
		border: 1px solid #475569;
		border-radius: 6px;
		color: #94a3b8;
		font-size: 13px;
		cursor: pointer;
		transition: all 0.15s;
	}

	.cancel-btn:hover {
		background: rgba(255, 255, 255, 0.05);
		color: #e2e8f0;
	}
</style>
