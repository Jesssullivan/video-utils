<script lang="ts">
	import ControlApiError from '$lib/components/ControlApiError.svelte';
	import JobStateBadge from '$lib/components/JobStateBadge.svelte';
	import IntervalPicker from '$lib/components/processing/IntervalPicker.svelte';
	import LaneRefusal from '$lib/components/processing/LaneRefusal.svelte';
	import OriginNotice from '$lib/components/processing/OriginNotice.svelte';
	import MeasurementPanel from '$lib/components/processing/MeasurementPanel.svelte';
	import { overlapsSetup } from '$lib/components/processing/setup';
	import { shortHash } from '$lib/format';
	import type { PageProps } from './$types';

	let { data, form }: PageProps = $props();
	const STATUSES = ['reviewed_candidate', 'reviewed_possible_contamination', 'rejected_contaminated'];
	const SCOPES = ['experimental_capture_render', 'profile_authoring'];
	const CONTENT = ['unknown', 'suspected', 'reviewed_no_obvious_content', 'reviewed_present'];
	const AMBIENT = ['not_reported', 'suspected', 'reviewed_absent', 'reviewed_present'];

	// Only the operator's own just-submitted values are echoed back; nothing is proposed.
	const echoed = (name: string, fallback: string) => (form?.values?.[name] ?? fallback);
	let start = $state(echoed('start_seconds', ''));
	let end = $state(echoed('end_seconds', ''));
	let reviewStatus = $state(echoed('review_status', ''));
	const overlap = $derived(start.trim() !== '' && overlapsSetup(Number(start)));
	const run = $derived(data.selectedRun);
	const duration = $derived(typeof run?.pcm?.duration_seconds === 'number' ? (run.pcm.duration_seconds as number) : null);
	// A form action replaces the query string, so each action URL carries the chosen run. The load still selects it
	// only from the eligible baseline list (isRunId + eligible.find); an absent or ineligible id selects nothing.
	const actionUrl = (name: 'measure' | 'save' | 'author') => (run ? `?/${name}&run=${encodeURIComponent(run.run_id)}` : `?/${name}`);
	const mediaUrl = $derived(run ? `/sources/${data.sourceId}/runs/${run.run_id}/media/source` : null);
</script>

<section class="space-y-6" data-capture-page="true">
	<div>
		<p class="vu-eyebrow">Source · capture review</p>
		<h1 class="h3"><a class="anchor" href={`/sources/${data.sourceId}`}><code>{data.sourceId}</code></a></h1>
		<p class="vu-muted text-sm">
			Choose and review a fan-noise capture interval on a baseline run bound to this source's sha256. The first five
			seconds include setup guitar/amp sounds and possible windup and are never auto-confirmed as noise. Review and
			authorization identities are operator assertions over loopback, not authentication.
		</p>
	</div>

	<OriginNotice show={data.originMisconfigured} />
	{#if data.error}
		<ControlApiError error={data.error} />
	{:else if data.source}
		<form method="GET" class="vu-panel card space-y-2 p-4" data-run-selector="true">
			<label class="label space-y-1">
				<span class="label-text">Baseline run (manifest source sha256 = <code class="vu-time">{shortHash(data.source.sha256)}</code>)</span>
				<select class="select" name="run">
					<option value="" selected={!run}>— choose a baseline run —</option>
					{#each data.runs as candidate (candidate.run_id)}
						<option value={candidate.run_id} selected={run?.run_id === candidate.run_id} disabled={!candidate.baseline_eligible}>
							{candidate.run_id} · {candidate.profile_name ?? 'profile unknown'}{candidate.baseline_eligible ? '' : ' (not eligible)'}
						</option>
					{/each}
				</select>
			</label>
			<button class="btn btn-sm preset-tonal" type="submit">Use this run</button>
			{#if data.runsError}<ControlApiError error={data.runsError} />{/if}
			{#if data.runs.length === 0}<p class="vu-muted text-xs">No baseline run is bound. Render one with an explicit denoise profile (for example <code>bypass</code>) on the process page.</p>{/if}
			{#if run}
				<p class="vu-muted text-xs" data-native-timeline="true">
					Native timeline: {String(run.pcm.sample_rate ?? 'unknown')} Hz, {String(run.pcm.channels ?? 'unknown')} channel(s),
					{String(run.pcm.sample_count ?? 'unknown')} samples ({duration !== null ? duration.toFixed(3) : 'unknown'} s); axis
					<code>decoded_source_audio_samples</code>. {run.baseline_eligibility_reason}
				</p>
			{/if}
		</form>

		<form method="POST" class="vu-panel card space-y-4 p-5" novalidate data-capture-form="true">
			<input type="hidden" name="run_id" value={run?.run_id ?? ''} />
			<input type="hidden" name="expected_source_sha256" value={data.source.sha256} />
			<input type="hidden" name="idempotency_key" value={data.keys.save} />
			<IntervalPicker {mediaUrl} durationSeconds={duration} bind:start bind:end />
			<div class="flex flex-wrap gap-3">
				<button class="btn preset-tonal" type="submit" formaction={actionUrl('measure')} disabled={!run}>Measure interval (writes nothing)</button>
			</div>
			{#if form?.action === 'measure' && form.measurement}<MeasurementPanel measurement={form.measurement} />{/if}
			{#if form?.action === 'measure'}<LaneRefusal error={form.error} local={form.local} />{/if}

			<fieldset class="grid grid-cols-1 gap-4 sm:grid-cols-2" data-review-fields="true">
				<label class="label space-y-1">
					<span class="label-text">Review status</span>
					<select class="select" name="review_status" bind:value={reviewStatus}>
						<option value="">— choose —</option>
						{#each STATUSES as status (status)}
							<option value={status} disabled={status === 'reviewed_candidate' && overlap}>{status}{status === 'reviewed_candidate' && overlap ? ' (refused within the first 5 s)' : ''}</option>
						{/each}
					</select>
				</label>
				<label class="label space-y-1">
					<span class="label-text">Authorization scope</span>
					<select class="select" name="authorization_scope">
						<option value="">— choose —</option>
						{#each SCOPES as scope (scope)}<option value={scope} selected={echoed('authorization_scope', '') === scope}>{scope}</option>{/each}
					</select>
					<span class="vu-muted text-xs">Only <code>experimental_capture_render</code> reviews can author a renderable profile.</span>
				</label>
				<label class="label space-y-1">
					<span class="label-text">Music in the interval</span>
					<select class="select" name="music_status">{#each CONTENT as value (value)}<option {value} selected={echoed('music_status', 'unknown') === value}>{value}</option>{/each}</select>
				</label>
				<label class="label space-y-1">
					<span class="label-text">Clicks in the interval</span>
					<select class="select" name="click_status">{#each CONTENT as value (value)}<option {value} selected={echoed('click_status', 'unknown') === value}>{value}</option>{/each}</select>
				</label>
				<label class="label space-y-1">
					<span class="label-text">Ambient music</span>
					<select class="select" name="ambient_music_status">{#each AMBIENT as value (value)}<option {value} selected={echoed('ambient_music_status', 'not_reported') === value}>{value}</option>{/each}</select>
				</label>
				<label class="label space-y-1 sm:col-span-2">
					<span class="label-text">Review note (required; what you heard and why this span)</span>
					<textarea class="textarea" name="note" rows="3" maxlength="2000">{echoed('note', '')}</textarea>
				</label>
				<label class="flex items-center gap-2 text-sm sm:col-span-2">
					<input class="checkbox" type="checkbox" name="setup_interval_acknowledged" checked={echoed('setup_interval_acknowledged', '') === 'on'} />
					I acknowledge this span overlaps the first five seconds (setup sounds / possible windup), when it does.
				</label>
			</fieldset>
			<div class="flex flex-wrap items-center gap-3">
				<button class="btn preset-filled-primary-300-700" type="submit" formaction={actionUrl('save')} disabled={!run}>Save review (immutable record)</button>
				<span class="vu-muted text-xs">Form key <code class="vu-time">{data.keys.save.slice(0, 11)}…</code> — a double submit replays the same record.</span>
			</div>
			{#if form?.action === 'save'}
				{#if form.review}
					<p class="vu-panel card p-3 text-sm" data-review-saved={form.review.review_id}>
						{form.review.replayed ? 'Replayed' : 'Saved'} <code>{form.review.review_id}</code>: {form.review.interval.start_seconds.toFixed(3)}–{form.review.interval.end_seconds.toFixed(3)} s,
						{form.review.review_status}, {form.review.authorization_scope}. Not verified noise-only.
					</p>
				{/if}
				<LaneRefusal error={form.error} local={form.local} />
			{/if}
		</form>

		<section class="space-y-3" data-saved-reviews="true">
			<div><p class="vu-eyebrow">Saved reviews</p><h2 class="h4">Author a FULLER profile from a review</h2></div>
			{#if data.reviewsError}<ControlApiError error={data.reviewsError} />{/if}
			{#if data.captureAdmission && data.captureAdmission !== 'admitted'}
				<p class="vu-muted text-sm" data-admission="pending">capture_profile web adapter: <code>{data.captureAdmission}</code>. Submissions are refused <code>tool_pending_admission</code> until root admits it.</p>
			{/if}
			{#if data.reviews.length === 0}
				<p class="vu-muted text-sm">No saved review for this source.</p>
			{:else}
				{#each data.reviews as review (review.review_id)}
					<form method="POST" action={actionUrl('author')} class="vu-panel card flex flex-wrap items-center gap-3 p-3 text-sm" data-review-row={review.review_id}>
						<input type="hidden" name="capture_review_id" value={review.review_id} />
						<input type="hidden" name="idempotency_key" value={data.keys.author} />
						<code>{review.review_id}</code>
						<span class="vu-time">{review.interval.start_seconds.toFixed(3)}–{review.interval.end_seconds.toFixed(3)} s</span>
						<span>{review.review_status} · {review.authorization_scope}</span>
						<button class="btn btn-sm preset-tonal" type="submit" disabled={!review.renderable}>Author FULLER profile</button>
						{#if !review.renderable}<span class="vu-muted text-xs">not renderable (scope or status)</span>{/if}
					</form>
				{/each}
			{/if}
			{#if form?.action === 'author'}
				{#if form.job}
					<p class="vu-panel card p-3 text-sm" data-author-job={form.job.job_id}>
						Authoring job <code>{form.job.job_id}</code> <JobStateBadge state={form.job.state} /> — follow it on
						<a class="anchor" href={`/sources/${data.sourceId}/process`}>the process page</a>.
					</p>
				{/if}
				<LaneRefusal error={form.error} local={form.local} />
			{/if}
		</section>
	{/if}
</section>
