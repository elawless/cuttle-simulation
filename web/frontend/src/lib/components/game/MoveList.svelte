<script lang="ts">
	import type { Move } from '$lib/types';

	export let moves: Move[] = [];
	export let selectedIndex: number | null = null;
	export let onSelectMove: ((move: Move) => void) | undefined = undefined;
	export let disabled: boolean = false;

	function getMoveIcon(moveType: string): string {
		switch (moveType) {
			case 'DRAW':
				return '📤';
			case 'PLAY_POINTS':
				return '💎';
			case 'SCUTTLE':
				return '⚔️';
			case 'PLAY_ONE_OFF':
				return '✨';
			case 'PLAY_PERMANENT':
				return '🏰';
			case 'COUNTER':
				return '🛡️';
			case 'DECLINE_COUNTER':
				return '❌';
			case 'RESOLVE_SEVEN':
				return '7️⃣';
			case 'DISCARD':
				return '🗑️';
			case 'PASS':
				return '⏭️';
			default:
				return '🎴';
		}
	}

	function getShortDescription(move: Move): string {
		// Shorten descriptions for compact display
		let desc = move.description;
		desc = desc.replace('Play ', '');
		desc = desc.replace(' for points', ' pts');
		desc = desc.replace(' as one-off', '');
		desc = desc.replace(' as permanent', '');
		desc = desc.replace('Scuttle ', '⚔️ ');
		desc = desc.replace(' with ', '→');
		return desc;
	}
</script>

<div class="move-list">
	<div class="header">
		<span class="title">Moves</span>
		<span class="count">{moves.length}</span>
	</div>

	{#if moves.length === 0}
		<div class="empty">No moves available</div>
	{:else}
		<div class="moves">
			{#each moves as move}
				<button
					class="move-chip"
					class:selected={selectedIndex === move.index}
					{disabled}
					on:click={() => onSelectMove?.(move)}
					title={move.description}
				>
					<span class="icon">{getMoveIcon(move.type)}</span>
					<span class="desc">{getShortDescription(move)}</span>
				</button>
			{/each}
		</div>
	{/if}
</div>

<style>
	.move-list {
		background: rgba(255, 255, 255, 0.03);
		border-radius: 8px;
		padding: 12px;
	}

	.header {
		display: flex;
		align-items: center;
		gap: 8px;
		margin-bottom: 10px;
	}

	.title {
		font-size: 12px;
		font-weight: 600;
		color: #64748b;
		text-transform: uppercase;
		letter-spacing: 0.05em;
	}

	.count {
		font-size: 11px;
		background: #334155;
		color: #94a3b8;
		padding: 2px 6px;
		border-radius: 10px;
	}

	.empty {
		color: #475569;
		font-size: 13px;
		text-align: center;
		padding: 8px;
	}

	.moves {
		display: flex;
		flex-wrap: wrap;
		gap: 6px;
	}

	.move-chip {
		display: inline-flex;
		align-items: center;
		gap: 6px;
		padding: 6px 10px;
		background: #1e293b;
		border: 1px solid #334155;
		border-radius: 6px;
		color: #e2e8f0;
		font-size: 12px;
		cursor: pointer;
		transition: all 0.15s ease;
		white-space: nowrap;
	}

	.move-chip:hover:not(:disabled) {
		background: #334155;
		border-color: #475569;
	}

	.move-chip.selected {
		background: #3b82f6;
		border-color: #3b82f6;
		color: white;
	}

	.move-chip:disabled {
		opacity: 0.5;
		cursor: not-allowed;
	}

	.icon {
		font-size: 14px;
	}

	.desc {
		max-width: 200px;
		overflow: hidden;
		text-overflow: ellipsis;
	}
</style>
