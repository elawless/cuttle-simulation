<script lang="ts">
	import type { Card } from '$lib/types';
	import { isRedSuit } from '$lib/types';

	export let card: Card;
	export let faceDown: boolean = false;
	export let selected: boolean = false;
	export let selectable: boolean = false;
	export let small: boolean = false;
	export let onClick: (() => void) | undefined = undefined;

	$: isRed = card && !card.hidden && isRedSuit(card.suit_name);
	$: showBack = faceDown || card?.hidden;
</script>

<!-- svelte-ignore a11y-no-static-element-interactions -->
<!-- svelte-ignore a11y-click-events-have-key-events -->
<div
	class="card"
	class:face-down={showBack}
	class:selected
	class:selectable
	class:small
	on:click={selectable && onClick ? onClick : undefined}
>
	{#if showBack}
		<!-- Card back - Bicycle Metalluxe Red styling -->
		<svg viewBox="0 0 100 140" class="card-svg">
			<defs>
				<linearGradient id="metalluxeRed" x1="0%" y1="0%" x2="100%" y2="100%">
					<stop offset="0%" style="stop-color:#8B0000" />
					<stop offset="25%" style="stop-color:#B22222" />
					<stop offset="50%" style="stop-color:#DC143C" />
					<stop offset="75%" style="stop-color:#B22222" />
					<stop offset="100%" style="stop-color:#8B0000" />
				</linearGradient>
				<linearGradient id="sheen" x1="0%" y1="0%" x2="100%" y2="100%">
					<stop offset="0%" style="stop-color:rgba(255,255,255,0)" />
					<stop offset="45%" style="stop-color:rgba(255,255,255,0)" />
					<stop offset="50%" style="stop-color:rgba(255,255,255,0.3)" />
					<stop offset="55%" style="stop-color:rgba(255,255,255,0)" />
					<stop offset="100%" style="stop-color:rgba(255,255,255,0)" />
				</linearGradient>
				<pattern id="backPattern" width="10" height="10" patternUnits="userSpaceOnUse">
					<circle cx="5" cy="5" r="1.5" fill="rgba(255,255,255,0.15)" />
				</pattern>
			</defs>
			<rect x="2" y="2" width="96" height="136" rx="6" fill="url(#metalluxeRed)" />
			<rect x="8" y="8" width="84" height="124" rx="4" fill="none" stroke="rgba(255,255,255,0.2)" stroke-width="1" />
			<rect x="8" y="8" width="84" height="124" rx="4" fill="url(#backPattern)" />
			<g transform="translate(50, 70)">
				<rect x="-20" y="-30" width="40" height="60" rx="3" fill="none" stroke="rgba(255,255,255,0.25)" stroke-width="1.5" transform="rotate(45)" />
				<rect x="-12" y="-18" width="24" height="36" rx="2" fill="none" stroke="rgba(255,255,255,0.2)" stroke-width="1" transform="rotate(45)" />
			</g>
			<rect x="2" y="2" width="96" height="136" rx="6" fill="url(#sheen)" />
			<rect x="2" y="2" width="96" height="136" rx="6" fill="none" stroke="#4a0000" stroke-width="2" />
		</svg>
	{:else}
		<!-- Card face -->
		<svg viewBox="0 0 100 140" class="card-svg">
			<rect x="2" y="2" width="96" height="136" rx="6" fill="white" />
			<rect x="2" y="2" width="96" height="136" rx="6" fill="none" stroke="#ddd" stroke-width="2" />
			<text x="8" y="24" class="rank-text" class:red={isRed}>{card.rank_symbol}</text>
			<text x="8" y="42" class="suit-text" class:red={isRed}>{card.suit_symbol}</text>
			<g transform="rotate(180, 50, 70)">
				<text x="8" y="24" class="rank-text" class:red={isRed}>{card.rank_symbol}</text>
				<text x="8" y="42" class="suit-text" class:red={isRed}>{card.suit_symbol}</text>
			</g>
			<text x="50" y="85" class="center-suit" class:red={isRed}>{card.suit_symbol}</text>
		</svg>
	{/if}
</div>

<style>
	.card {
		width: 80px;
		height: 112px;
		border-radius: 8px;
		box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1), 0 4px 8px rgba(0, 0, 0, 0.1);
		transition: all 0.2s ease;
		cursor: default;
		user-select: none;
	}

	.card.small {
		width: 60px;
		height: 84px;
	}

	.card.selectable {
		cursor: pointer;
	}

	.card.selectable:hover {
		transform: translateY(-8px);
		box-shadow: 0 8px 16px rgba(0, 0, 0, 0.2), 0 12px 24px rgba(0, 0, 0, 0.15);
	}

	.card.selected {
		transform: translateY(-12px);
		box-shadow: 0 12px 24px rgba(59, 130, 246, 0.4), 0 16px 32px rgba(59, 130, 246, 0.3);
		outline: 3px solid #3b82f6;
	}

	.card-svg {
		width: 100%;
		height: 100%;
		display: block;
	}

	.rank-text {
		font-family: 'Georgia', serif;
		font-size: 18px;
		font-weight: bold;
		fill: #1a1a1a;
	}

	.rank-text.red { fill: #dc2626; }

	.suit-text {
		font-family: 'DejaVu Sans', sans-serif;
		font-size: 16px;
		fill: #1a1a1a;
	}

	.suit-text.red { fill: #dc2626; }

	.center-suit {
		font-family: 'DejaVu Sans', sans-serif;
		font-size: 48px;
		fill: #1a1a1a;
		text-anchor: middle;
	}

	.center-suit.red { fill: #dc2626; }
</style>
