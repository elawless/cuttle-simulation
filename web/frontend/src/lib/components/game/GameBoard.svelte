<script lang="ts">
	import Card from '$lib/components/cards/Card.svelte';
	import MoveList from '$lib/components/game/MoveList.svelte';
	import MoveLog from '$lib/components/game/MoveLog.svelte';
	import type { GameState, Move, Card as CardType } from '$lib/types';
	import {
		gameState,
		legalMoves,
		isHumanTurn,
		selectedMoveIndex,
		sendMove,
		isLoading,
		error,
		moveHistory,
		aiThinking
	} from '$lib/stores/gameStore';
	import { page } from '$app/stores';

	// Get viewer from URL (0 or 1)
	$: viewer = parseInt($page.url.searchParams.get('viewer') || '0', 10);
	$: opponent = 1 - viewer;

	$: state = $gameState;
	$: moves = $legalMoves;
	$: humanTurn = $isHumanTurn;
	$: loading = $isLoading;

	// Player states based on viewer perspective
	$: myState = state?.players[viewer];
	$: oppState = state?.players[opponent];

	function handleSelectMove(move: Move) {
		if (!humanTurn || loading) return;
		selectedMoveIndex.set(move.index);
		sendMove(move.index);
	}

	function getPhaseDescription(phase: string): string {
		switch (phase) {
			case 'MAIN':
				return 'Main Phase';
			case 'COUNTER':
				return 'Counter!';
			case 'RESOLVE_SEVEN':
				return 'Play from Seven';
			case 'DISCARD_FOUR':
				return 'Discard';
			case 'GAME_OVER':
				return 'Game Over';
			default:
				return phase;
		}
	}
</script>

{#if state}
	<div class="game-board">
		<!-- Left: Opponent Area -->
		<div class="player-column opponent">
			<div class="player-header">
				<span class="player-name">Opponent</span>
				<span class="points">{oppState.point_total} / {oppState.point_threshold}</span>
				{#if oppState.queens_count > 0}
					<span class="badge">👑×{oppState.queens_count}</span>
				{/if}
			</div>

			<!-- Opponent Hand -->
			<div class="section">
				<div class="section-label">Hand ({oppState.hand_count})</div>
				<div class="card-row">
					{#each oppState.hand as card}
						<Card {card} faceDown={card.hidden} small />
					{/each}
					{#if oppState.hand.length === 0}
						<span class="empty">Empty</span>
					{/if}
				</div>
			</div>

			<!-- Opponent Field -->
			<div class="section">
				<div class="section-label">Points</div>
				<div class="card-row">
					{#each oppState.points_field as card}
						{@const targetMove = moves.find(m => m.target?.rank === card.rank && m.target?.suit === card.suit)}
						<Card
							{card}
							small
							selectable={humanTurn && !!targetMove}
							onClick={targetMove ? () => handleSelectMove(targetMove) : undefined}
						/>
					{/each}
					{#each oppState.jacks as jp}
						<div class="jack-pair">
							<Card card={jp.stolen} small />
							<span class="jack-icon">J</span>
						</div>
					{/each}
					{#if oppState.points_field.length === 0 && oppState.jacks.length === 0}
						<span class="empty">None</span>
					{/if}
				</div>
			</div>

			<div class="section">
				<div class="section-label">Permanents</div>
				<div class="card-row">
					{#each oppState.permanents as card}
						{@const targetMove = moves.find(m => m.target?.rank === card.rank && m.target?.suit === card.suit)}
						<Card
							{card}
							small
							selectable={humanTurn && !!targetMove}
							onClick={targetMove ? () => handleSelectMove(targetMove) : undefined}
						/>
					{/each}
					{#if oppState.permanents.length === 0}
						<span class="empty">None</span>
					{/if}
				</div>
			</div>
		</div>

		<!-- Center: Deck, Scrap, Status -->
		<div class="center-column">
			<div class="status-area">
				<div class="phase-badge" class:your-turn={humanTurn} class:ai-turn={!humanTurn && state.winner === null}>
					{#if state.winner !== null}
						{state.winner === viewer ? '🎉 You Won!' : 'Opponent Wins'}
					{:else if humanTurn}
						Your Turn
					{:else if $aiThinking}
						🧠 {$aiThinking.strategy}...
					{:else}
						AI Turn
					{/if}
				</div>
				<div class="turn-info">
					Turn {state.turn_number} · {getPhaseDescription(state.phase)}
				</div>
			</div>

			<div class="table-center">
				<!-- Deck -->
				<div class="stack">
					<div class="stack-label">Deck</div>
					<div class="stack-cards">
						{#if state.deck_count > 0}
							<Card card={{ hidden: true }} faceDown small />
							<span class="count">{state.deck_count}</span>
						{:else}
							<div class="empty-stack">Empty</div>
						{/if}
					</div>
				</div>

				<!-- Scrap -->
				<div class="stack">
					<div class="stack-label">Scrap</div>
					<div class="stack-cards">
						{#if state.scrap.length > 0}
							<Card card={state.scrap[state.scrap.length - 1]} small />
							<span class="count">{state.scrap.length}</span>
						{:else}
							<div class="empty-stack">Empty</div>
						{/if}
					</div>
				</div>
			</div>

			<!-- Special States -->
			{#if state.counter_state}
				<div class="special-state">
					<span class="special-label">One-off:</span>
					<Card card={state.counter_state.one_off_card} small />
					{#if state.counter_state.target_card}
						<span>→</span>
						<Card card={state.counter_state.target_card} small />
					{/if}
				</div>
			{/if}

			{#if state.seven_state}
				<div class="special-state">
					<span class="special-label">Choose:</span>
					{#each state.seven_state.revealed_cards as card}
						<Card {card} small />
					{/each}
				</div>
			{/if}

			{#if $error}
				<div class="error">{$error}</div>
			{/if}
		</div>

		<!-- Right: Your Area -->
		<div class="player-column you">
			<div class="player-header">
				<span class="player-name">You</span>
				<span class="points">{myState.point_total} / {myState.point_threshold}</span>
				{#if myState.queens_count > 0}
					<span class="badge">👑×{myState.queens_count}</span>
				{/if}
			</div>

			<!-- Your Field -->
			<div class="section">
				<div class="section-label">Points</div>
				<div class="card-row">
					{#each myState.points_field as card}
						<Card {card} small />
					{/each}
					{#each myState.jacks as jp}
						<div class="jack-pair">
							<Card card={jp.stolen} small />
							<span class="jack-icon">J</span>
						</div>
					{/each}
					{#if myState.points_field.length === 0 && myState.jacks.length === 0}
						<span class="empty">None</span>
					{/if}
				</div>
			</div>

			<div class="section">
				<div class="section-label">Permanents</div>
				<div class="card-row">
					{#each myState.permanents as card}
						<Card {card} small />
					{/each}
					{#if myState.permanents.length === 0}
						<span class="empty">None</span>
					{/if}
				</div>
			</div>

			<!-- Your Hand -->
			<div class="section hand-section">
				<div class="section-label">Your Hand</div>
				<div class="card-row hand">
					{#each myState.hand as card}
						{@const cardMoves = moves.filter(m => m.card?.rank === card.rank && m.card?.suit === card.suit && !m.target)}
						<Card
							{card}
							selectable={humanTurn && cardMoves.length > 0}
							onClick={cardMoves.length === 1 ? () => handleSelectMove(cardMoves[0]) : undefined}
						/>
					{/each}
					{#if myState.hand.length === 0}
						<span class="empty">Empty</span>
					{/if}
				</div>
			</div>
		</div>

		<!-- Bottom: Move List + Game Log -->
		<div class="bottom-panel">
			<div class="moves-panel">
				<MoveList
					{moves}
					selectedIndex={$selectedMoveIndex}
					onSelectMove={handleSelectMove}
					disabled={!humanTurn || loading}
				/>
			</div>
			<div class="log-panel">
				<MoveLog moves={$moveHistory} />
			</div>
		</div>
	</div>
{:else}
	<div class="no-game">No game loaded</div>
{/if}

<style>
	.game-board {
		display: grid;
		grid-template-columns: 1fr auto 1fr;
		grid-template-rows: 1fr auto;
		gap: 16px;
		height: 100%;
		padding: 16px;
		background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%);
		overflow: hidden;
	}

	.player-column {
		display: flex;
		flex-direction: column;
		gap: 12px;
		min-width: 200px;
		max-width: 320px;
	}

	.player-header {
		display: flex;
		align-items: center;
		gap: 8px;
		padding: 8px 12px;
		background: rgba(255,255,255,0.05);
		border-radius: 8px;
	}

	.player-name {
		font-weight: 600;
		color: white;
		font-size: 14px;
	}

	.points {
		font-size: 13px;
		font-weight: 600;
		color: #3b82f6;
		background: rgba(59, 130, 246, 0.15);
		padding: 2px 8px;
		border-radius: 4px;
	}

	.badge {
		font-size: 12px;
	}

	.section {
		display: flex;
		flex-direction: column;
		gap: 6px;
	}

	.section-label {
		font-size: 11px;
		font-weight: 600;
		color: #64748b;
		text-transform: uppercase;
		letter-spacing: 0.05em;
	}

	.card-row {
		display: flex;
		flex-wrap: wrap;
		gap: 4px;
		align-items: center;
		min-height: 44px;
	}

	.card-row.hand {
		gap: 6px;
	}

	.hand-section {
		margin-top: auto;
		padding-top: 12px;
		border-top: 1px solid rgba(255,255,255,0.1);
	}

	.empty {
		color: #475569;
		font-size: 12px;
		font-style: italic;
	}

	.jack-pair {
		position: relative;
	}

	.jack-icon {
		position: absolute;
		bottom: -4px;
		right: -4px;
		width: 16px;
		height: 16px;
		background: #7c3aed;
		color: white;
		font-size: 10px;
		font-weight: bold;
		border-radius: 50%;
		display: flex;
		align-items: center;
		justify-content: center;
	}

	.center-column {
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: 16px;
		padding: 0 24px;
		min-width: 180px;
	}

	.status-area {
		text-align: center;
	}

	.phase-badge {
		padding: 6px 16px;
		border-radius: 20px;
		font-size: 14px;
		font-weight: 600;
		margin-bottom: 4px;
	}

	.phase-badge.your-turn {
		background: #22c55e;
		color: white;
	}

	.phase-badge.ai-turn {
		background: #f59e0b;
		color: white;
		animation: pulse 1.5s infinite;
	}

	@keyframes pulse {
		0%, 100% { opacity: 1; }
		50% { opacity: 0.7; }
	}

	.turn-info {
		font-size: 12px;
		color: #64748b;
	}

	.table-center {
		display: flex;
		gap: 24px;
	}

	.stack {
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: 4px;
	}

	.stack-label {
		font-size: 11px;
		font-weight: 600;
		color: #64748b;
		text-transform: uppercase;
	}

	.stack-cards {
		position: relative;
	}

	.count {
		position: absolute;
		bottom: -6px;
		right: -6px;
		background: #1e293b;
		color: white;
		font-size: 10px;
		font-weight: 600;
		width: 20px;
		height: 20px;
		border-radius: 50%;
		display: flex;
		align-items: center;
		justify-content: center;
		border: 2px solid #0f172a;
	}

	.empty-stack {
		width: 60px;
		height: 84px;
		border: 2px dashed #334155;
		border-radius: 6px;
		display: flex;
		align-items: center;
		justify-content: center;
		color: #475569;
		font-size: 10px;
	}

	.special-state {
		display: flex;
		align-items: center;
		gap: 8px;
		padding: 8px 12px;
		background: rgba(245, 158, 11, 0.15);
		border: 1px solid rgba(245, 158, 11, 0.3);
		border-radius: 8px;
	}

	.special-label {
		font-size: 12px;
		font-weight: 600;
		color: #f59e0b;
	}

	.error {
		padding: 8px 12px;
		background: rgba(239, 68, 68, 0.2);
		border: 1px solid rgba(239, 68, 68, 0.3);
		border-radius: 6px;
		color: #fca5a5;
		font-size: 12px;
	}

	.bottom-panel {
		grid-column: 1 / -1;
		display: grid;
		grid-template-columns: 1fr 1fr;
		gap: 16px;
		max-height: 200px;
	}

	.moves-panel {
		overflow: hidden;
	}

	.log-panel {
		overflow: hidden;
	}

	.no-game {
		display: flex;
		align-items: center;
		justify-content: center;
		height: 100%;
		color: #64748b;
	}

	/* Responsive adjustments */
	@media (max-width: 900px) {
		.game-board {
			grid-template-columns: 1fr 1fr;
		}
		.center-column {
			grid-column: 1 / -1;
			grid-row: 1;
			flex-direction: row;
			justify-content: center;
			padding: 8px 0;
		}
	}
</style>
