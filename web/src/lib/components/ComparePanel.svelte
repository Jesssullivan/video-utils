<script lang="ts">
	// Source vs processed share derivative. No gain, EQ or normalization is applied in the browser.
	import PrototypeNotice from './PrototypeNotice.svelte';
	import type { JobProjection } from '$lib/schema/control';
	interface Props {
		job: JobProjection;
	}
	let { job }: Props = $props();
	const COMPARE_NOTE =
		"Levels are not matched by this page. Loudness values shown are the worker's measurements of the share derivative; listening comparison not established. Lossy AAC derivative: ~32 Hz low-string preservation not measured.";
	const share = $derived(
		job.state === 'succeeded' ? [...job.artifacts].reverse().find((a) => a.role === 'share_mp4' && a.downloadable) ?? null : null
	);
	const checks = $derived(share ? (job.attempts.find((a) => a.attempt === share.attempt)?.worker_checks ?? null) : null);
</script>

{#if share}
	<section
		class="vu-panel card space-y-3 p-5"
		data-compare="bound"
		data-level-matched="false"
		data-listening-comparison="not_established"
		data-low-register-preservation="null"
	>
		<p class="vu-eyebrow">Compare</p>
		<p class="text-sm" data-compare-note="true">{COMPARE_NOTE}</p>
		<div class="grid grid-cols-1 gap-4 lg:grid-cols-2">
			<figure class="space-y-1">
				<figcaption class="vu-muted text-xs">Source (admitted bytes, re-hashed on each request)</figcaption>
				<!-- svelte-ignore a11y_media_has_caption -->
				<video class="w-full" controls preload="metadata" src={`/api/sources/${job.source_artifact_id}/media`} data-player="source"></video>
			</figure>
			<figure class="space-y-1">
				<figcaption class="vu-muted text-xs">Processed <code>share_mp4</code> (attempt {share.attempt})</figcaption>
				<!-- svelte-ignore a11y_media_has_caption -->
				<video class="w-full" controls preload="metadata" src={`/api/artifacts/${share.artifact_id}`} data-player="processed"></video>
			</figure>
		</div>
		<div class="text-sm">
			<p class="vu-muted">Worker loudness measurement of the share derivative (verbatim; a measurement, not a listening verdict):</p>
			{#if checks && checks.loudness !== undefined && checks.loudness !== null}
				<pre class="vu-time overflow-x-auto text-xs" data-loudness="measured">{JSON.stringify(checks.loudness, null, 2)}</pre>
			{:else}
				<span class="vu-unknown" data-unknown="true">Unknown</span> <span class="vu-muted text-xs">— the worker reported no loudness block</span>
			{/if}
		</div>
		<p class="vu-muted text-xs">Browser playback, hydration and level matching are not verified by this build (Range requests are not supported in S2).</p>
	</section>
{:else}
	<div data-compare="absent">
		<PrototypeNotice inline step="Compare" purpose="Comparison data absent: no succeeded share_mp4 artifact for this job yet." />
	</div>
{/if}
