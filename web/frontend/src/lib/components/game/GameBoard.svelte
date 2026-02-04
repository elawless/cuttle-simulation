<script lang="ts">
	import Card from '$lib/components/cards/Card.svelte';
	import MoveLog from '$lib/components/game/MoveLog.svelte';
	import StatusBar from '$lib/components/game/StatusBar.svelte';
	import CardActionModal from '$lib/components/game/CardActionModal.svelte';
	import PlaybackControls from '$lib/components/game/PlaybackControls.svelte';
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
		aiThinking,
		isPaused
	} from '$lib/stores/gameStore';
	import { page } from '$app/stores';

	export let watchMode: boolean = false;

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

	// Get strategy names for display in watch mode
	$: myStrategyName = state?.strategy_names?.[viewer] || `Player ${viewer + 1}`;
	$: oppStrategyName = state?.strategy_names?.[opponent] || `Player ${opponent + 1}`;

	// Labels that change based on watch mode
	$: myLabel = watchMode ? myStrategyName : 'You';
	$: oppLabel = watchMode ? oppStrategyName : 'Opponent';

	// Modal state for card action selection
	let modalCard: CardType | null = null;
	let modalMoves: Move[] = [];

	function handleSelectMove(move: Move) {
		if (!humanTurn || loading) return;
		selectedMoveIndex.set(move.index);
		sendMove(move.index);
		closeModal();
	}

	function handleCardClick(card: CardType, cardMoves: Move[]) {
		if (!humanTurn || loading) return;
		if (cardMoves.length === 0) return;

		if (cardMoves.length === 1) {
			// Single move - execute directly
			handleSelectMove(cardMoves[0]);
		} else {
			// Multiple moves - show modal
			modalCard = card;
			modalMoves = cardMoves;
		}
	}

	function closeModal() {
		modalCard = null;
		modalMoves = [];
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

	// Get all moves for a card in hand (including targeted moves like Jack steals)
	function getHandCardMoves(card: CardType): Move[] {
		return moves.filter(m => m.card?.rank === card.rank && m.card?.suit === card.suit);
	}

	// Get move that targets a specific card on the field
	function getTargetMove(card: CardType): Move | undefined {
		return moves.find(m => m.target?.rank === card.rank && m.target?.suit === card.suit);
	}

	// Get draw move
	$: drawMove = moves.find(m => m.type === 'DRAW');

	// Get counter/decline moves
	$: counterMove = moves.find(m => m.type === 'COUNTER');
	$: declineMove = moves.find(m => m.type === 'DECLINE_COUNTER');
	$: passMove = moves.find(m => m.type === 'PASS');

	// Placeholder card for face-down display
	const faceDownCard: CardType = {
		rank: 0,
		rank_symbol: '',
		rank_name: '',
		suit: 0,
		suit_symbol: '',
		suit_name: '',
		display: '',
		point_value: 0,
		hidden: true
	};
</script>

{#if state && myState && oppState}
	<div class="game-board">
		<!-- Opponent Hand Strip (Top) -->
		<div class="hand-strip opponent-hand">
			<div class="hand-label">
				<span class="name">{oppLabel}</span>
				<span class="count">{oppState.hand_count} cards</span>
			</div>
			<div class="hand-cards">
				{#each oppState.hand as card}
					<Card {card} faceDown={card.hidden} small />
				{/each}
				{#if oppState.hand.length === 0}
					<span class="empty">Empty</span>
				{/if}
			</div>
		</div>

		<!-- Left Sidebar: Deck & Scrap -->
		<div class="left-sidebar">
			<div class="stack">
				<div class="stack-label">Deck</div>
				<!-- svelte-ignore a11y-click-events-have-key-events -->
				<!-- svelte-ignore a11y-no-static-element-interactions -->
				<div class="stack-cards" class:clickable={humanTurn && drawMove} on:click={() => drawMove && handleSelectMove(drawMove)}>
					{#if state.deck_count > 0}
						<div class="deck-card">
							<Card card={faceDownCard} faceDown small />
						</div>
						<span class="count-badge">{state.deck_count}</span>
					{:else}
						<div class="empty-stack">Empty</div>
					{/if}
				</div>
			</div>

			<div class="stack">
				<div class="stack-label">Scrap</div>
				<div class="stack-cards">
					{#if state.scrap.length > 0}
						<Card card={state.scrap[state.scrap.length - 1]} small />
						<span class="count-badge">{state.scrap.length}</span>
					{:else}
						<div class="empty-stack">Empty</div>
					{/if}
				</div>
			</div>

			<!-- Turn/Phase Info -->
			<div class="game-info">
				<div class="turn-badge">Turn {state.turn_number}</div>
				<div class="phase-badge" class:your-turn={humanTurn && !watchMode} class:ai-turn={!humanTurn && state.winner === null && !watchMode} class:paused={watchMode && $isPaused}>
					{#if state.winner !== null}
						{state.winner === viewer ? 'P1 Won!' : 'P2 Won!'}
					{:else if watchMode}
						{#if $isPaused}
							Paused
						{:else if $aiThinking}
							{$aiThinking.strategy}...
						{:else}
							Playing
						{/if}
					{:else if humanTurn}
						Your Turn
					{:else if $aiThinking}
						{$aiThinking.strategy}...
					{:else}
						AI Turn
					{/if}
				</div>
			</div>
		</div>

		<!-- Main Play Area -->
		<div class="play-area">
			<!-- Playback Controls for Watch Mode -->
			{#if watchMode}
				<div class="playback-container">
					<PlaybackControls />
				</div>
			{/if}

			<!-- Opponent Status -->
			<StatusBar
				points={oppState.point_total}
				goal={oppState.point_threshold}
				isYou={false}
				yourTurn={false}
				queensCount={oppState.queens_count}
				kingsCount={oppState.kings_count}
				playerLabel={watchMode ? oppLabel.toUpperCase() : ''}
			/>

			<!-- Opponent Field -->
			<div class="field-row opponent-field">
				<div class="field-section">
					<div class="field-label">Points</div>
					<div class="field-cards">
						{#each oppState.points_field as card}
							{@const targetMove = getTargetMove(card)}
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
				<div class="field-section">
					<div class="field-label">Permanents</div>
					<div class="field-cards">
						{#each oppState.permanents as card}
							{@const targetMove = getTargetMove(card)}
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

			<!-- Divider Line -->
			<div class="field-divider"></div>

			<!-- Your Field -->
			<div class="field-row your-field">
				<div class="field-section">
					<div class="field-label">Points</div>
					<div class="field-cards">
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
				<div class="field-section">
					<div class="field-label">Permanents</div>
					<div class="field-cards">
						{#each myState.permanents as card}
							<Card {card} small />
						{/each}
						{#if myState.permanents.length === 0}
							<span class="empty">None</span>
						{/if}
					</div>
				</div>
			</div>

			<!-- Your Status -->
			<StatusBar
				points={myState.point_total}
				goal={myState.point_threshold}
				isYou={true}
				yourTurn={humanTurn && !watchMode}
				queensCount={myState.queens_count}
				kingsCount={myState.kings_count}
				playerLabel={watchMode ? myLabel.toUpperCase() : ''}
			/>

			<!-- Special States -->
			{#if state.counter_state}
				<div class="special-state">
					<span class="special-label">One-off being played:</span>
					<Card card={state.counter_state.one_off_card} small />
					{#if state.counter_state.target_card}
						<span class="arrow">→</span>
						<Card card={state.counter_state.target_card} small />
					{/if}
					{#if humanTurn}
						<div class="counter-actions">
							{#if counterMove}
								<button class="counter-btn" on:click={() => handleSelectMove(counterMove)}>
									Counter
								</button>
							{/if}
							{#if declineMove}
								<button class="decline-btn" on:click={() => handleSelectMove(declineMove)}>
									Let it resolve
								</button>
							{/if}
						</div>
					{/if}
				</div>
			{/if}

			{#if state.seven_state}
				<div class="special-state">
					<span class="special-label">Choose a card to play:</span>
					{#each state.seven_state.revealed_cards as card}
						{@const cardMoves = getHandCardMoves(card)}
						<Card
							{card}
							small
							selectable={humanTurn && cardMoves.length > 0}
							onClick={cardMoves.length > 0 ? () => handleCardClick(card, cardMoves) : undefined}
						/>
					{/each}
				</div>
			{/if}

			{#if state.four_state && humanTurn}
				<div class="special-state">
					<span class="special-label">Discard {state.four_state.cards_to_discard} card(s)</span>
				</div>
			{/if}

			{#if $error}
				<div class="error-message">{$error}</div>
			{/if}
		</div>

		<!-- Right Sidebar: Game Log -->
		<div class="right-sidebar">
			<MoveLog moves={$moveHistory} {viewer} />
		</div>

		<!-- Player Hand Strip (Bottom) -->
		<div class="hand-strip player-hand" class:your-turn={humanTurn && !watchMode}>
			<div class="hand-label">
				<span class="name">{myLabel}</span>
				<span class="count">{myState.hand.length} cards</span>
				{#if humanTurn && state.phase === 'MAIN' && !watchMode}
					{#if passMove}
						<button class="pass-btn" on:click={() => handleSelectMove(passMove)}>Pass</button>
					{/if}
				{/if}
			</div>
			<div class="hand-cards">
				{#each myState.hand as card}
					{@const cardMoves = getHandCardMoves(card)}
					<Card
						{card}
						selectable={humanTurn && cardMoves.length > 0}
						onClick={cardMoves.length > 0 ? () => handleCardClick(card, cardMoves) : undefined}
					/>
				{/each}
				{#if myState.hand.length === 0}
					<span class="empty">Empty</span>
				{/if}
			</div>
		</div>
	</div>

	<!-- Card Action Modal -->
	{#if modalCard}
		<CardActionModal
			card={modalCard}
			moves={modalMoves}
			onSelectMove={handleSelectMove}
			onCancel={closeModal}
		/>
	{/if}
{:else}
	<div class="no-game">No game loaded</div>
{/if}

<style>
	.game-board {
		display: grid;
		grid-template-areas:
			"opponent-hand opponent-hand opponent-hand"
			"left-sidebar  play-area     right-sidebar"
			"player-hand   player-hand   player-hand";
		grid-template-columns: 100px 1fr 280px;
		grid-template-rows: auto 1fr auto;
		height: 100%;
		gap: 0;

		/* Blue felt background */
		background-color: #1e3a5f;
		background-image:
			radial-gradient(ellipse at center, transparent 0%, rgba(0,0,0,0.3) 100%),
			repeating-linear-gradient(
				45deg,
				transparent,
				transparent 2px,
				rgba(255,255,255,0.02) 2px,
				rgba(255,255,255,0.02) 4px
			),
			linear-gradient(135deg, #1e4a6f 0%, #152842 50%, #1e3a5f 100%);
	}

	/* Hand Strips */
	.hand-strip {
		display: flex;
		align-items: center;
		gap: 16px;
		padding: 12px 20px;
		background: rgba(0, 0, 0, 0.3);
	}

	.hand-strip.opponent-hand {
		grid-area: opponent-hand;
		border-bottom: 1px solid rgba(255, 255, 255, 0.1);
	}

	.hand-strip.player-hand {
		grid-area: player-hand;
		border-top: 1px solid rgba(255, 255, 255, 0.1);
	}

	.hand-strip.player-hand.your-turn {
		border-top: 3px solid #22c55e;
		background: rgba(34, 197, 94, 0.1);
		box-shadow: 0 -4px 20px rgba(34, 197, 94, 0.2);
	}

	.hand-label {
		display: flex;
		flex-direction: column;
		gap: 2px;
		min-width: 80px;
	}

	.hand-label .name {
		font-weight: 600;
		color: #e2e8f0;
		font-size: 14px;
	}

	.hand-label .count {
		font-size: 11px;
		color: #64748b;
	}

	.hand-cards {
		display: flex;
		gap: 8px;
		flex-wrap: wrap;
		align-items: center;
	}

	.pass-btn {
		margin-top: 4px;
		padding: 4px 8px;
		font-size: 10px;
		background: rgba(255, 255, 255, 0.1);
		border: 1px solid rgba(255, 255, 255, 0.2);
		border-radius: 4px;
		color: #94a3b8;
		cursor: pointer;
		transition: all 0.15s;
	}

	.pass-btn:hover {
		background: rgba(255, 255, 255, 0.15);
		color: #e2e8f0;
	}

	/* Left Sidebar */
	.left-sidebar {
		grid-area: left-sidebar;
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: 16px;
		padding: 16px 8px;
		background: rgba(0, 0, 0, 0.2);
		border-right: 1px solid rgba(255, 255, 255, 0.1);
	}

	.stack {
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: 4px;
	}

	.stack-label {
		font-size: 10px;
		font-weight: 600;
		color: #64748b;
		text-transform: uppercase;
		letter-spacing: 0.05em;
	}

	.stack-cards {
		position: relative;
	}

	.stack-cards.clickable {
		cursor: pointer;
	}

	.stack-cards.clickable:hover {
		transform: scale(1.05);
	}

	.deck-card {
		position: relative;
	}

	.count-badge {
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

	.game-info {
		margin-top: auto;
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: 6px;
	}

	.turn-badge {
		font-size: 11px;
		color: #64748b;
	}

	.phase-badge {
		padding: 6px 10px;
		border-radius: 6px;
		font-size: 11px;
		font-weight: 600;
		text-align: center;
		background: rgba(0, 0, 0, 0.3);
		color: #94a3b8;
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

	.phase-badge.paused {
		background: #6366f1;
		color: white;
	}

	@keyframes pulse {
		0%, 100% { opacity: 1; }
		50% { opacity: 0.7; }
	}

	.playback-container {
		margin-bottom: 12px;
	}

	/* Main Play Area */
	.play-area {
		grid-area: play-area;
		display: flex;
		flex-direction: column;
		gap: 12px;
		padding: 16px;
		overflow-y: auto;
	}

	.field-row {
		display: flex;
		gap: 24px;
	}

	.field-section {
		flex: 1;
		display: flex;
		flex-direction: column;
		gap: 6px;
	}

	.field-label {
		font-size: 11px;
		font-weight: 600;
		color: #64748b;
		text-transform: uppercase;
		letter-spacing: 0.05em;
	}

	.field-cards {
		display: flex;
		flex-wrap: wrap;
		gap: 6px;
		min-height: 50px;
		align-items: center;
	}

	.field-divider {
		height: 1px;
		background: linear-gradient(90deg, transparent, rgba(255,255,255,0.2), transparent);
		margin: 8px 0;
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

	.empty {
		color: #475569;
		font-size: 12px;
		font-style: italic;
	}

	/* Special States */
	.special-state {
		display: flex;
		align-items: center;
		gap: 12px;
		padding: 12px 16px;
		background: rgba(245, 158, 11, 0.15);
		border: 1px solid rgba(245, 158, 11, 0.3);
		border-radius: 8px;
		flex-wrap: wrap;
	}

	.special-label {
		font-size: 13px;
		font-weight: 600;
		color: #f59e0b;
	}

	.arrow {
		color: #f59e0b;
		font-size: 16px;
	}

	.counter-actions {
		display: flex;
		gap: 8px;
		margin-left: auto;
	}

	.counter-btn {
		padding: 8px 16px;
		background: #22c55e;
		border: none;
		border-radius: 6px;
		color: white;
		font-size: 13px;
		font-weight: 600;
		cursor: pointer;
		transition: all 0.15s;
	}

	.counter-btn:hover {
		background: #16a34a;
	}

	.decline-btn {
		padding: 8px 16px;
		background: transparent;
		border: 1px solid #475569;
		border-radius: 6px;
		color: #94a3b8;
		font-size: 13px;
		cursor: pointer;
		transition: all 0.15s;
	}

	.decline-btn:hover {
		background: rgba(255, 255, 255, 0.05);
		color: #e2e8f0;
	}

	.error-message {
		padding: 10px 14px;
		background: rgba(239, 68, 68, 0.2);
		border: 1px solid rgba(239, 68, 68, 0.3);
		border-radius: 6px;
		color: #fca5a5;
		font-size: 13px;
	}

	/* Right Sidebar */
	.right-sidebar {
		grid-area: right-sidebar;
		background: rgba(0, 0, 0, 0.2);
		border-left: 1px solid rgba(255, 255, 255, 0.1);
		display: flex;
		flex-direction: column;
		overflow: hidden;
	}

	.no-game {
		display: flex;
		align-items: center;
		justify-content: center;
		height: 100%;
		color: #64748b;
		font-size: 16px;
	}

	/* Responsive adjustments */
	@media (max-width: 1000px) {
		.game-board {
			grid-template-areas:
				"opponent-hand opponent-hand"
				"left-sidebar  play-area"
				"player-hand   player-hand"
				"right-sidebar right-sidebar";
			grid-template-columns: 100px 1fr;
			grid-template-rows: auto 1fr auto auto;
		}

		.right-sidebar {
			max-height: 200px;
			border-left: none;
			border-top: 1px solid rgba(255, 255, 255, 0.1);
		}
	}

	@media (max-width: 700px) {
		.game-board {
			grid-template-areas:
				"opponent-hand"
				"play-area"
				"player-hand"
				"right-sidebar";
			grid-template-columns: 1fr;
			grid-template-rows: auto 1fr auto auto;
		}

		.left-sidebar {
			display: none;
		}

		.field-row {
			flex-direction: column;
			gap: 12px;
		}
	}
</style>
