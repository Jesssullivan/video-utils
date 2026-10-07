<script lang="ts">
	// Low-register spectrogram view (lowreg-render-v1): the bound matrix is fetched through layer media and drawn
	// to a canvas with a fixed colour ramp and a text legend. Log-power dB is the default; PCEN is experimental.
	// Visualisation only: no pitch, note or stem claim; energy near 32.7 Hz is not C1 identification.
	import { decodeMatrix, fixed, rampColour } from './review-logic';
	import { layerMediaUrl } from './media';

	interface Matrix {
		readonly name: 'log_power_db' | 'pcen';
		readonly media_name: string;
		readonly status: string;
	}
	interface Meta {
		readonly status: string;
		readonly reason: string | null;
		readonly evidence_id: string | null;
		readonly stage: string | null;
		readonly shape: { readonly frames: number | null; readonly bands: number | null } | null;
		readonly band_centre_hz: readonly number[];
		readonly hop_seconds: number | null;
		readonly window_seconds: number | null;
		readonly first_frame_centre_seconds: number | null;
		readonly axis_offset_seconds: number | null;
		readonly matrices: readonly Matrix[];
		readonly reference_lines: readonly { readonly label: string; readonly hz: number }[];
		readonly claim: string;
		readonly pcen_status: string | null;
	}
	interface Props {
		runId: string;
		meta: Meta;
		matrix: 'log_power_db' | 'pcen';
	}
	let { runId, meta, matrix }: Props = $props();

	const RANGE = { log_power_db: { lo: -100, hi: 0, unit: 'dB (window-normalized power; uncalibrated digital scale)' }, pcen: { lo: 0, hi: 4, unit: 'PCEN units (experimental; fixed knobs, not tuned)' } };
	let canvas = $state<HTMLCanvasElement | null>(null);
	let status = $state('not loaded');
	const selected = $derived(meta.matrices.find((item) => item.name === matrix) ?? null);
	const frames = $derived(meta.shape?.frames ?? 0);
	const bands = $derived(meta.shape?.bands ?? 0);
	const centres = $derived(meta.band_centre_hz);
	const startSeconds = $derived((meta.axis_offset_seconds ?? 0) + (meta.first_frame_centre_seconds ?? 0));
	const endSeconds = $derived(startSeconds + Math.max(0, frames - 1) * (meta.hop_seconds ?? 0));
	const bandFor = (hz: number) => {
		let best = 0;
		for (let k = 1; k < centres.length; k += 1) if (Math.abs(centres[k] - hz) < Math.abs(centres[best] - hz)) best = k;
		return best;
	};
	const labels = $derived(
		[20, 50, 100, 200, 500, 1000, 2000]
			.filter((hz) => centres.length && hz >= centres[0] && hz <= centres[centres.length - 1])
			.map((hz) => ({ hz, band: bandFor(hz) }))
	);
	const lines = $derived(meta.reference_lines.map((line) => ({ ...line, band: bandFor(line.hz) })));
	const top = (band: number) => `${(1 - (band + 0.5) / Math.max(1, bands)) * 100}%`;

	$effect(() => {
		const target = canvas;
		const chosen = selected;
		const evidence = meta.evidence_id;
		if (!target || !chosen || !evidence || !(frames > 0 && bands > 0)) return;
		let cancelled = false;
		status = 'loading';
		(async () => {
			try {
				const response = await fetch(layerMediaUrl(runId, evidence, chosen.media_name));
				if (!response.ok) {
					status = `unavailable (HTTP ${response.status})`;
					return;
				}
				const values = decodeMatrix(await response.arrayBuffer(), frames, bands);
				if (cancelled) return;
				if (!values) {
					status = 'unavailable (matrix size does not match the recorded shape)';
					return;
				}
				const columns = Math.min(frames, 1600);
				target.width = columns;
				target.height = bands;
				const context = target.getContext('2d');
				if (!context) {
					status = 'unavailable (no canvas context)';
					return;
				}
				const image = context.createImageData(columns, bands);
				const range = RANGE[chosen.name];
				for (let column = 0; column < columns; column += 1) {
					const frame = Math.min(frames - 1, Math.floor((column * frames) / columns));
					for (let band = 0; band < bands; band += 1) {
						const [r, g, b] = rampColour(values[frame * bands + band], range.lo, range.hi);
						const offset = ((bands - 1 - band) * columns + column) * 4;
						image.data[offset] = r;
						image.data[offset + 1] = g;
						image.data[offset + 2] = b;
						image.data[offset + 3] = 255;
					}
				}
				context.putImageData(image, 0, 0);
				status = 'drawn';
			} catch {
				if (!cancelled) status = 'unavailable (fetch failed)';
			}
		})();
		return () => {
			cancelled = true;
		};
	});
</script>

<section class="space-y-1 text-sm" data-spectrogram={meta.status}>
	{#if meta.status !== 'available' || !selected}
		<p class="vu-muted">Low-register spectrogram {meta.status === 'unbound' ? 'unbound' : 'unavailable'}: {meta.reason ?? 'no bound render'}.</p>
	{:else}
		<p class="vu-muted text-xs">
			{matrix === 'pcen' ? 'PCEN (experimental; fixed knobs, not tuned)' : 'Log-power dB (baseline)'} of stage <code>{meta.stage ?? 'unknown'}</code> ·
			window {fixed(meta.window_seconds, 3)} s, hop {fixed(meta.hop_seconds, 3)} s · {frames} frames × {bands} bands · {status}
		</p>
		<div class="vu-spec">
			<canvas bind:this={canvas} class="vu-spec-canvas" aria-label={`Low-register spectrogram ${matrix}, ${fixed(startSeconds, 2)} to ${fixed(endSeconds, 2)} source seconds`}></canvas>
			{#each labels as label (label.hz)}<span class="vu-spec-label" style:top={top(label.band)}>{label.hz} Hz</span>{/each}
			{#each lines as line (line.label)}
				<span class="vu-spec-line" style:top={top(line.band)} data-reference-line={line.label}><span>{line.label} · {fixed(line.hz, 1)} Hz</span></span>
			{/each}
		</div>
		<p class="vu-muted text-xs" data-spectrogram-legend="true">
			Legend: fixed ramp dark → amber → pale over {RANGE[matrix].lo} … {RANGE[matrix].hi} {RANGE[matrix].unit}. Time axis
			{fixed(startSeconds, 2)}–{fixed(endSeconds, 2)} s (frame centres, decoded source audio). {meta.claim}. A band level near 32.7 Hz is
			mixture energy, not an identified C1.
		</p>
	{/if}
</section>

<style>
	.vu-spec {
		position: relative;
		max-width: 100%;
	}
	.vu-spec-canvas {
		display: block;
		width: 100%;
		height: 12rem;
		image-rendering: pixelated;
		border: 1px solid var(--vu-line);
	}
	.vu-spec-label {
		position: absolute;
		left: 0.2rem;
		transform: translateY(-50%);
		font-size: 0.6rem;
		color: var(--vu-text);
		background: rgba(22, 21, 18, 0.7);
		padding: 0 0.2rem;
	}
	.vu-spec-line {
		position: absolute;
		left: 0;
		right: 0;
		border-top: 1px dashed var(--vu-gold);
	}
	.vu-spec-line span {
		position: absolute;
		right: 0.2rem;
		top: -0.9rem;
		font-size: 0.6rem;
		background: rgba(22, 21, 18, 0.7);
		padding: 0 0.2rem;
	}
</style>
