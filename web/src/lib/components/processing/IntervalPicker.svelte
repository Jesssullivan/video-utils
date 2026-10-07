<script lang="ts">
	// Operator-chosen capture interval on the baseline run's native timeline. The selection starts
	// empty and is never prefilled or proposed; "Set from playhead" copies the operator's own
	// playhead. Span loop is a listening aid only (not level-matched, no listening claim).
	import { overlapsSetup } from './setup';

	// `start` and `end` are always strings. A number input bound with bind:value would be assigned a number (or
	// null), so the inputs are read through their own `value` text instead and the state never changes type.
	const text = (event: Event) => (event.currentTarget as HTMLInputElement).value;

	interface Props {
		mediaUrl: string | null;
		durationSeconds: number | null;
		start?: string;
		end?: string;
	}
	let { mediaUrl, durationSeconds, start = $bindable(''), end = $bindable('') }: Props = $props();
	let player = $state<HTMLAudioElement | null>(null);
	let loop = $state(true);
	const startValue = $derived(Number(start));
	const endValue = $derived(Number(end));
	const empty = $derived(start.trim() === '' && end.trim() === '');
	const overlap = $derived(start.trim() !== '' && overlapsSetup(startValue));
	const playhead = () => (player ? player.currentTime.toFixed(3) : '');

	function onTime() {
		if (!player || !loop || !Number.isFinite(startValue) || !Number.isFinite(endValue) || endValue <= startValue) return;
		if (player.currentTime >= endValue || player.currentTime < startValue - 0.25) player.currentTime = startValue;
	}
</script>

<div class="space-y-3" data-interval-picker="true" data-interval-empty={empty ? 'true' : 'false'}>
	{#if mediaUrl}
		<audio bind:this={player} controls preload="none" src={mediaUrl} ontimeupdate={onTime} class="w-full" data-baseline-player="true"></audio>
		<p class="vu-muted text-xs">
			Baseline <code>source.wav</code> (native decoded audio, re-hashed by the control API before streaming). Player
			seconds are assumed to equal decoded-source seconds; that mapping is not verified by this page.
		</p>
	{:else}
		<p class="vu-muted text-sm">Choose a baseline run to load its native audio.</p>
	{/if}
	<div class="grid grid-cols-1 gap-3 sm:grid-cols-3">
		<label class="label space-y-1">
			<span class="label-text">Start (s, decoded-source axis)</span>
			<input class="input vu-time" type="number" name="start_seconds" step="0.001" inputmode="decimal" value={start} oninput={(event) => (start = text(event))} />
			<button type="button" class="btn btn-sm preset-tonal" onclick={() => (start = playhead())} disabled={!player}>Set start from playhead</button>
		</label>
		<label class="label space-y-1">
			<span class="label-text">End (s)</span>
			<input class="input vu-time" type="number" name="end_seconds" step="0.001" inputmode="decimal" value={end} oninput={(event) => (end = text(event))} />
			<button type="button" class="btn btn-sm preset-tonal" onclick={() => (end = playhead())} disabled={!player}>Set end from playhead</button>
		</label>
		<div class="space-y-1 text-sm">
			<label class="flex items-center gap-2"><input class="checkbox" type="checkbox" bind:checked={loop} /> Loop the span</label>
			<p class="vu-muted text-xs">Duration must be 0.1–10 s{durationSeconds !== null ? `; native extent ${durationSeconds.toFixed(3)} s` : ''}. Bounds are checked by the control API, never clamped here.</p>
		</div>
	</div>
	{#if empty}
		<p class="vu-muted text-xs" data-no-prefill="true">No interval is selected. Nothing proposes, ranks or prefills a capture interval.</p>
	{/if}
	{#if overlap}
		<p class="vu-panel vu-error card p-3 text-sm" data-setup-warning="true">
			This span overlaps the first five seconds (setup guitar/amp sounds, possible mechanical windup). It is never
			auto-confirmed as noise: it needs an explicit acknowledgement and can only be saved as
			<code>reviewed_possible_contamination</code> or <code>rejected_contaminated</code>.
		</p>
	{/if}
</div>
