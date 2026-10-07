<script lang="ts">
	// Section 7.4 statistics: measurements of the mixture with their denominators. Nothing here
	// selects, ranks or confirms an interval; noise-only, fan band and ~32 Hz content stay unknown.
	import UnknownValue from '$lib/components/UnknownValue.svelte';

	type Channel = {
		sample_peak_dbfs: number;
		rms_dbfs: number;
		frame_rms_dbfs: { min: number | null; median: number | null; max: number | null; spread_db: number | null };
		frame_count: number;
		frame_samples: number;
		unframed_tail_samples: number;
		transient_frames: number;
		transient_frames_label: string;
		clipped_samples: number;
		sample_count: number;
	};
	interface Props {
		measurement: {
			interval: { start_seconds: number; end_seconds: number; start_sample: number; end_sample: number; sample_rate: number; duration_seconds: number; codec: string };
			channels: ReadonlyArray<Channel>;
			overlaps_setup_interval: boolean;
			pcm_sha256: string;
			unknowns: Record<string, unknown>;
		};
	}
	let { measurement }: Props = $props();
	const fixed = (value: number | null, digits = 2) => (value === null ? null : value.toFixed(digits));
	const unknownKeys = ['noise_only', 'fan_band_energy', 'music_or_click_presence', 'low_register_content_hz_32'];
</script>

<section class="vu-panel card space-y-3 p-4" data-measurement="true">
	<p class="vu-eyebrow">Measured (mixture) — not a selection</p>
	<p class="text-sm">
		Samples <span class="vu-time">[{measurement.interval.start_sample}, {measurement.interval.end_sample})</span> at
		<span class="vu-time">{measurement.interval.sample_rate}</span> Hz ({measurement.interval.codec}), duration
		<span class="vu-time">{measurement.interval.duration_seconds.toFixed(3)}</span> s; PCM re-hashed
		<code class="vu-time">{measurement.pcm_sha256.slice(0, 12)}…</code>.
		{#if measurement.overlaps_setup_interval}<strong>Overlaps the first five seconds.</strong>{/if}
	</p>
	<div class="overflow-x-auto">
		<table class="table text-sm">
			<thead>
				<tr><th>Ch</th><th>Sample peak dBFS</th><th>RMS dBFS</th><th>100 ms frame RMS min / median / max (spread) dBFS</th><th>Possible attack/windup frames</th><th>Clipped samples</th></tr>
			</thead>
			<tbody>
				{#each measurement.channels as channel, index (index)}
					<tr>
						<td>{index + 1}</td>
						<td class="vu-time">{channel.sample_peak_dbfs.toFixed(2)} <span class="vu-muted text-xs">(not true peak)</span></td>
						<td class="vu-time">{channel.rms_dbfs.toFixed(2)}</td>
						<td class="vu-time">
							<UnknownValue value={fixed(channel.frame_rms_dbfs.min)} /> / <UnknownValue value={fixed(channel.frame_rms_dbfs.median)} /> /
							<UnknownValue value={fixed(channel.frame_rms_dbfs.max)} /> (<UnknownValue value={fixed(channel.frame_rms_dbfs.spread_db)} />)
						</td>
						<td class="vu-time">{channel.transient_frames} / {channel.frame_count} frames</td>
						<td class="vu-time">{channel.clipped_samples} / {channel.sample_count}</td>
					</tr>
				{/each}
			</tbody>
		</table>
	</div>
	<p class="vu-muted text-xs">
		Frames are {measurement.channels[0]?.frame_samples ?? 'unknown'} samples (100 ms); an unframed tail of
		{measurement.channels[0]?.unframed_tail_samples ?? 0} samples is excluded from frame statistics. “Possible
		attack/windup frames” is an inference: frames more than 6 dB above the interval median.
	</p>
	<ul class="vu-muted text-xs" data-measurement-unknowns="true">
		{#each unknownKeys as key (key)}
			<li><code>{key}</code>: <UnknownValue value={null} reason={String(measurement.unknowns[`${key}_reason`] ?? 'not measured')} /></li>
		{/each}
	</ul>
</section>
