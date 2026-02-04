<script lang="ts">
	import type { MoveRecord } from '$lib/types';

	export let moves: MoveRecord[] = [];
	export let expanded: boolean = true;

	let selectedMove: MoveRecord | null = null;
	let logContentEl: HTMLDivElement;

	function getPlayerLabel(player: number): string {
		return player === 0 ? 'You' : 'AI';
	}

	function getMoveIcon(moveType: string): string {
		switch (moveType) {
			case 'DRAW': return '📤';
			case 'PLAY_POINTS': return '💎';
			case 'SCUTTLE': return '⚔️';
			case 'PLAY_ONE_OFF': return '✨';
			case 'PLAY_PERMANENT': return '🏰';
			case 'COUNTER': return '🛡️';
			case 'DECLINE_COUNTER': return '❌';
			case 'RESOLVE_SEVEN': return '7️⃣';
			case 'DISCARD': return '🗑️';
			case 'PASS': return '⏭️';
			default: return '🎴';
		}
	}

	function toggleMove(move: MoveRecord) {
		if (selectedMove === move) {
			selectedMove = null;
		} else {
			selectedMove = move;
		}
	}

	$: recentMoves = moves.slice(-30).reverse();

	// Auto-scroll to top when new moves come in
	$: if (moves.length && logContentEl) {
		logContentEl.scrollTop = 0;
	}
</script>

<div class="move-log" class:expanded>
	<button class="header" on:click={() => expanded = !expanded}>
		<span class="title">Game Log</span>
		<span class="count">{moves.length}</span>
		<span class="toggle">{expanded ? '▼' : '▲'}</span>
	</button>

	{#if expanded}
		<div class="log-content" bind:this={logContentEl}>
			{#if recentMoves.length === 0}
				<div class="empty">No moves yet</div>
			{:else}
				{#each recentMoves as move, i}
					<button
						class="log-entry"
						class:selected={selectedMove === move}
						class:ai={move.player === 1}
						class:has-details={move.llm_thinking || move.hands_after}
						on:click={() => toggleMove(move)}
					>
						<span class="turn">T{move.turn}</span>
						<span class="player">{getPlayerLabel(move.player)}</span>
						<span class="icon">{getMoveIcon(move.move_type)}</span>
						<span class="move-text">{move.move}</span>
						{#if move.points_after}
							<span class="points-badge">{move.points_after[0]}v{move.points_after[1]}</span>
						{/if}
						{#if move.llm_thinking}
							<span class="thinking-indicator">🧠</span>
						{/if}
					</button>

					{#if selectedMove === move}
						<div class="details-panel">
							{#if move.hands_before || move.hands_after}
								<div class="hands-section">
									<div class="hands-row">
										<span class="hand-label">Your hand:</span>
										<span class="hand-cards">{move.hands_after?.[0]?.join(', ') || 'empty'}</span>
									</div>
									<div class="hands-row">
										<span class="hand-label">AI hand:</span>
										<span class="hand-cards">{move.hands_after?.[1]?.length || 0} cards</span>
									</div>
								</div>
							{/if}

							{#if move.llm_thinking}
								<div class="thinking-section">
									<div class="thinking-header">
										<span class="model">{move.llm_thinking.model}</span>
										{#if move.llm_thinking.error}
											<span class="error">Error: {move.llm_thinking.error}</span>
										{/if}
									</div>

									<details class="collapsible">
										<summary>Prompt</summary>
										<pre class="prompt-text">{move.llm_thinking.prompt}</pre>
									</details>

									<details class="collapsible" open>
										<summary>Response</summary>
										<pre class="response-text">{move.llm_thinking.response}</pre>
									</details>

									<div class="chosen">
										→ {move.llm_thinking.chosen_move_description}
									</div>
								</div>
							{/if}
						</div>
					{/if}
				{/each}
			{/if}
		</div>
	{/if}
</div>

<style>
	.move-log {
		background: rgba(0, 0, 0, 0.3);
		border-radius: 8px;
		display: flex;
		flex-direction: column;
		height: 100%;
		overflow: hidden;
	}

	.header {
		display: flex;
		align-items: center;
		gap: 8px;
		padding: 8px 12px;
		background: rgba(255, 255, 255, 0.05);
		border: none;
		cursor: pointer;
		color: white;
		text-align: left;
		width: 100%;
		flex-shrink: 0;
	}

	.header:hover {
		background: rgba(255, 255, 255, 0.08);
	}

	.title {
		font-size: 12px;
		font-weight: 600;
		color: #94a3b8;
		text-transform: uppercase;
		letter-spacing: 0.05em;
	}

	.count {
		font-size: 10px;
		background: #334155;
		color: #94a3b8;
		padding: 2px 6px;
		border-radius: 10px;
	}

	.toggle {
		margin-left: auto;
		font-size: 10px;
		color: #64748b;
	}

	.log-content {
		flex: 1;
		overflow-y: auto;
		overflow-x: hidden;
		padding: 4px;
	}

	.empty {
		padding: 16px;
		text-align: center;
		color: #475569;
		font-size: 12px;
	}

	.log-entry {
		display: flex;
		align-items: center;
		gap: 6px;
		padding: 6px 8px;
		background: transparent;
		border: none;
		border-radius: 4px;
		cursor: pointer;
		width: 100%;
		text-align: left;
		font-size: 11px;
		color: #cbd5e1;
		transition: background 0.1s;
	}

	.log-entry:hover {
		background: rgba(255, 255, 255, 0.05);
	}

	.log-entry.selected {
		background: rgba(59, 130, 246, 0.2);
	}

	.log-entry.ai {
		color: #fbbf24;
	}

	.turn {
		color: #64748b;
		font-size: 10px;
		min-width: 24px;
	}

	.player {
		font-weight: 600;
		min-width: 24px;
	}

	.icon {
		font-size: 12px;
	}

	.move-text {
		flex: 1;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}

	.points-badge {
		font-size: 9px;
		background: #1e40af;
		color: #93c5fd;
		padding: 1px 4px;
		border-radius: 3px;
	}

	.thinking-indicator {
		font-size: 10px;
	}

	.details-panel {
		margin: 4px 0 8px 0;
		padding: 8px;
		background: rgba(0, 0, 0, 0.4);
		border-radius: 6px;
		border-left: 3px solid #3b82f6;
	}

	.hands-section {
		margin-bottom: 8px;
		padding-bottom: 8px;
		border-bottom: 1px solid rgba(255, 255, 255, 0.1);
	}

	.hands-row {
		display: flex;
		gap: 8px;
		font-size: 10px;
		margin-bottom: 2px;
	}

	.hand-label {
		color: #64748b;
		min-width: 60px;
	}

	.hand-cards {
		color: #94a3b8;
	}

	.thinking-section {
		font-size: 10px;
	}

	.thinking-header {
		display: flex;
		gap: 12px;
		margin-bottom: 8px;
	}

	.model {
		color: #94a3b8;
	}

	.error {
		color: #f87171;
	}

	.collapsible {
		margin-bottom: 8px;
	}

	.collapsible summary {
		font-size: 11px;
		font-weight: 600;
		color: #94a3b8;
		cursor: pointer;
		padding: 4px 0;
	}

	.collapsible summary:hover {
		color: #cbd5e1;
	}

	.prompt-text,
	.response-text {
		margin: 4px 0 0 0;
		padding: 8px;
		background: rgba(0, 0, 0, 0.3);
		border-radius: 4px;
		font-size: 10px;
		white-space: pre-wrap;
		word-break: break-word;
		max-height: 250px;
		overflow-y: auto;
		font-family: monospace;
	}

	.prompt-text {
		color: #94a3b8;
	}

	.response-text {
		color: #4ade80;
	}

	.chosen {
		font-size: 11px;
		color: #3b82f6;
		font-weight: 600;
		padding-top: 4px;
	}
</style>
