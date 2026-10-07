<script lang="ts">
	// Span audition: loop the same source-time span on the baseline and on a completed candidate's
	// stems. Not level-matched (matched A/B belongs to /runs/[id]/compare); no listening verdict.
	interface Player {
		label: string;
		src: string;
	}
	interface Props {
		players: ReadonlyArray<Player>;
	}
	let { players }: Props = $props();
	// Always strings: the number inputs are read through their `value` text, never bound as numbers.
	let start = $state('');
	let end = $state('');
	const elements: (HTMLAudioElement | null)[] = $state([]);

	function onTime(index: number) {
		const element = elements[index];
		const s = Number(start);
		const e = Number(end);
		if (!element || start.trim() === '' || end.trim() === '' || !Number.isFinite(s) || !Number.isFinite(e) || e <= s) return;
		if (element.currentTime >= e || element.currentTime < s - 0.25) element.currentTime = s;
	}
</script>

<section class="space-y-3" data-span-audition="true" data-level-matched="false">
	<p class="vu-muted text-xs">
		Span audition — <strong>not level-matched</strong>; loudness differs between stages. Listening acceptance is not
		performed or recorded here.
	</p>
	<div class="grid grid-cols-2 gap-3 sm:max-w-md">
		<label class="label"><span class="label-text">Span start (s)</span><input class="input vu-time" type="number" step="0.001" value={start} oninput={(event) => (start = event.currentTarget.value)} /></label>
		<label class="label"><span class="label-text">Span end (s)</span><input class="input vu-time" type="number" step="0.001" value={end} oninput={(event) => (end = event.currentTarget.value)} /></label>
	</div>
	{#each players as player, index (player.src)}
		<div class="space-y-1">
			<p class="text-sm"><code>{player.label}</code></p>
			<audio bind:this={elements[index]} controls preload="none" src={player.src} ontimeupdate={() => onTime(index)} class="w-full"></audio>
		</div>
	{/each}
</section>
