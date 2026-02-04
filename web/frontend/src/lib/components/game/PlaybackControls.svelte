<script lang="ts">
	import { isPaused, playbackSpeed, sendPause, sendResume, sendStep, sendSetSpeed } from '$lib/stores/gameStore';

	$: paused = $isPaused;
	$: speed = $playbackSpeed;

	function togglePause() {
		if (paused) {
			sendResume();
		} else {
			sendPause();
		}
	}

	function step() {
		sendStep();
	}

	function handleSpeedChange(event: Event) {
		const target = event.target as HTMLSelectElement;
		const newSpeed = parseInt(target.value, 10);
		sendSetSpeed(newSpeed);
	}
</script>

<div class="playback-controls">
	<button class="control-btn" class:playing={!paused} on:click={togglePause}>
		{#if paused}
			<span class="icon">&#9654;</span>
			<span class="label">Play</span>
		{:else}
			<span class="icon">&#10074;&#10074;</span>
			<span class="label">Pause</span>
		{/if}
	</button>

	<button class="control-btn" on:click={step} disabled={!paused}>
		<span class="icon">&#9654;&#10074;</span>
		<span class="label">Step</span>
	</button>

	<div class="speed-control">
		<label for="speed">Speed:</label>
		<select id="speed" value={speed} on:change={handleSpeedChange}>
			<option value={100}>Fast (0.1s)</option>
			<option value={300}>Quick (0.3s)</option>
			<option value={500}>Normal (0.5s)</option>
			<option value={1000}>Slow (1s)</option>
			<option value={2000}>Very Slow (2s)</option>
		</select>
	</div>
</div>

<style>
	.playback-controls {
		display: flex;
		align-items: center;
		gap: 12px;
		padding: 10px 16px;
		background: rgba(0, 0, 0, 0.4);
		border-radius: 8px;
		border: 1px solid rgba(255, 255, 255, 0.1);
	}

	.control-btn {
		display: flex;
		align-items: center;
		gap: 6px;
		padding: 8px 14px;
		background: rgba(255, 255, 255, 0.1);
		border: 1px solid rgba(255, 255, 255, 0.2);
		border-radius: 6px;
		color: #e2e8f0;
		font-size: 13px;
		cursor: pointer;
		transition: all 0.15s;
	}

	.control-btn:hover:not(:disabled) {
		background: rgba(255, 255, 255, 0.15);
		border-color: rgba(255, 255, 255, 0.3);
	}

	.control-btn:disabled {
		opacity: 0.4;
		cursor: not-allowed;
	}

	.control-btn.playing {
		background: rgba(34, 197, 94, 0.2);
		border-color: rgba(34, 197, 94, 0.4);
	}

	.icon {
		font-size: 12px;
	}

	.label {
		font-weight: 500;
	}

	.speed-control {
		display: flex;
		align-items: center;
		gap: 8px;
		margin-left: 8px;
	}

	.speed-control label {
		font-size: 12px;
		color: #94a3b8;
	}

	.speed-control select {
		padding: 6px 10px;
		background: rgba(0, 0, 0, 0.3);
		border: 1px solid rgba(255, 255, 255, 0.2);
		border-radius: 4px;
		color: #e2e8f0;
		font-size: 12px;
		cursor: pointer;
	}

	.speed-control select:focus {
		outline: none;
		border-color: #3b82f6;
	}
</style>
