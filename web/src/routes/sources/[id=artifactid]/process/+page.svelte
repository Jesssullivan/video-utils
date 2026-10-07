<script lang="ts">
	import ControlApiError from '$lib/components/ControlApiError.svelte';
	import JobStateBadge from '$lib/components/JobStateBadge.svelte';
	import UnknownValue from '$lib/components/UnknownValue.svelte';
	import KnobField from '$lib/components/processing/KnobField.svelte';
	import LaneRefusal from '$lib/components/processing/LaneRefusal.svelte';
	import OriginNotice from '$lib/components/processing/OriginNotice.svelte';
	import { stepTarget } from '$lib/components/review/step-context';
	import SpanAudition from '$lib/components/processing/SpanAudition.svelte';
	import type { PageProps } from './$types';

	let { data, form }: PageProps = $props();
	const echoed = (name: string) => (form?.values?.[name] ?? '');
	const initialChoice = () => form?.values?.preset || form?.values?.profile || 'fuller';
	let choice = $state(initialChoice());
	const selected = $derived(data.options.find((option) => option.id === choice) ?? data.options[0]);
	const capture = $derived(data.catalogue?.capture ?? null);
	const knobs = $derived((capture?.knobs ?? {}) as Record<string, { type?: string; minimum?: number; maximum?: number; items?: { properties?: Record<string, { minimum?: number; maximum?: number; type?: string }> }; properties?: Record<string, { minimum?: number; maximum?: number; type?: string }> }>);
	const fuller = $derived(((capture?.presets as Record<string, { controls?: Record<string, unknown> }> | undefined)?.fuller?.controls ?? {}) as Record<string, unknown>);
	const scalar = (name: string) => (typeof fuller[name] === 'number' ? (fuller[name] as number) : null);
	const fullerBands = $derived((Array.isArray(fuller.peaking_eq) ? fuller.peaking_eq : []) as { frequency_hz: number; gain_db: number; q: number }[]);
	const fullerComp = $derived((fuller.compressor ?? null) as Record<string, number> | null);
	const usableReviews = $derived(data.reviews.filter((review) => selected?.reviewIds.includes(review.review_id)));
	const authored = $derived(data.processing.filter((job) => job.tool === 'capture_profile' && job.state === 'succeeded' && job.worker_status === 'authored_unrendered'));
	const candidates = $derived(data.processing.filter((job) => job.tool !== 'capture_profile' && job.state === 'succeeded' && job.run_id));
	const baseline = $derived(data.runs.find((run) => run.role === 'baseline') ?? null);
	const groupLabel: Record<string, string> = { cleanup: 'Cleanup (pure denoise)', tone: 'Tone (peaking EQ, ≥160 Hz)', dynamics: 'Dynamics (compressor, all-or-none)', delivery_loudness: 'Delivery loudness', supervision: 'Supervision' };
	// Review route of a run (routes_review); null for an absent or malformed run id, so no dead link renders.
	const reviewHref = (run: string | null | undefined) =>
		stepTarget({ current: 'process', source_artifact_id: data.sourceId, run_id: run ?? null, disabled_reasons: {} }, 'review').href;
	const media = (run: string, role: string) => `/sources/${data.sourceId}/runs/${run}/media/${role}`;
	const players = (job: (typeof candidates)[number]) => [
		...(baseline ? [{ label: `baseline ${baseline.run_id} · source`, src: media(baseline.run_id, 'source') }] : []),
		...(job.outputs ?? []).filter((output) => output.served_via_run_media && output.role !== 'source').map((output) => ({ label: `${job.run_id} · ${output.role}`, src: media(job.run_id ?? '', output.role) }))
	];
</script>

<section class="space-y-6" data-process-page="true">
	<div>
		<p class="vu-eyebrow">Source · process</p>
		<h1 class="h3"><a class="anchor" href={`/sources/${data.sourceId}`}><code>{data.sourceId}</code></a></h1>
		<p class="vu-muted text-sm">
			Full-take renders only (the admitted tools take no interval argument). FULLER is the default selection and needs a
			saved reviewed capture interval. There is no high-pass, low-cut or notch control here and none can be sent.
			Outputs are separate candidates: never adopted as a master, never listening-accepted by this page.
		</p>
	</div>

	<OriginNotice show={data.originMisconfigured} />
	{#if data.error}
		<ControlApiError error={data.error} />
	{:else if data.source}
		{#if data.typesError}<ControlApiError error={data.typesError} />{/if}
		<fieldset class="vu-panel card space-y-2 p-5" data-preset-choice="true">
			<legend class="vu-eyebrow">Preset</legend>
			{#each data.options as option (option.id)}
				<label class="flex flex-wrap items-center gap-2 text-sm" data-option={option.id} data-enabled={option.enabled ? 'true' : 'false'} data-refusal={option.refusal_code ?? ''}>
					<input class="radio" type="radio" name="choice" value={option.id} bind:group={choice} />
					<span>{option.label}</span>
					{#if option.default}<span class="vu-muted text-xs">(default selection)</span>{/if}
					{#if !option.enabled}<code class="text-xs">{option.refusal_code}</code><span class="vu-muted text-xs">— {option.reason}</span>{/if}
				</label>
			{/each}
		</fieldset>

		{#if selected && selected.jobPath[0] === 'capture_profile'}
			<form method="POST" action="?/author" class="vu-panel card space-y-4 p-5" novalidate data-author-form={selected.id}>
				<input type="hidden" name="preset" value={selected.id} />
				<input type="hidden" name="idempotency_key" value={data.keys.author} />
				<p class="vu-eyebrow">Step 1 · author settings from a reviewed interval (capture_profile)</p>
				{#if !selected.enabled}
					<LaneRefusal local={{ code: selected.refusal_code ?? 'capture_interval_required', message: selected.reason }} />
					<p class="text-sm"><a class="anchor" href={`/sources/${data.sourceId}/capture`}>Open the capture review page</a></p>
				{/if}
				<label class="label space-y-1">
					<span class="label-text">Saved review (renderable scope only)</span>
					<select class="select" name="capture_review_id">
						<option value="">— choose a saved review —</option>
						{#each usableReviews as review (review.review_id)}
							<option value={review.review_id} selected={echoed('capture_review_id') === review.review_id}>{review.review_id} · {review.interval.start_seconds.toFixed(3)}–{review.interval.end_seconds.toFixed(3)} s · {review.review_status}</option>
						{/each}
					</select>
				</label>
				{#each Object.entries(data.groups) as [group, names] (group)}
					{#if names.length > 0}
						<fieldset class="space-y-2" data-knob-group={group}>
							<legend class="text-sm font-semibold">{groupLabel[group] ?? group}</legend>
							<div class="grid grid-cols-1 gap-3 sm:grid-cols-3">
								{#each names as name (name)}
									{#if name === 'peaking_eq'}
										{#each [0, 1, 2] as index (index)}
											{#each ['frequency_hz', 'gain_db', 'q'] as field (field)}
												<KnobField name={`eq_${index}_${field}`} label={`band ${index + 1} ${field}`} spec={knobs.peaking_eq?.items?.properties?.[field]} value={echoed(`eq_${index}_${field}`)} presetValue={fullerBands[index]?.[field as 'frequency_hz' | 'gain_db' | 'q'] ?? null} disabled={selected.id === 'fuller'} />
											{/each}
										{/each}
									{:else if name === 'compressor'}
										<label class="flex items-center gap-2 text-sm sm:col-span-3"><input class="checkbox" type="checkbox" name="compressor_enabled" disabled={selected.id === 'fuller'} checked={echoed('compressor_enabled') === 'on'} /> Compressor on (every field required)</label>
										{#each ['threshold_db', 'ratio', 'attack_ms', 'release_ms', 'knee_db'] as field (field)}
											<KnobField name={`compressor_${field}`} label={field} spec={knobs.compressor?.properties?.[field]} value={echoed(`compressor_${field}`)} presetValue={fullerComp?.[field] ?? null} disabled={selected.id === 'fuller'} />
										{/each}
									{:else if name === 'timeout_seconds'}
										<KnobField {name} spec={knobs[name]} value={echoed(name)} />
									{:else}
										<KnobField {name} spec={knobs[name]} value={echoed(name)} presetValue={scalar(name)} disabled={selected.id === 'fuller'} />
									{/if}
								{/each}
							</div>
						</fieldset>
					{/if}
				{/each}
				{#if selected.id === 'fuller'}
					<p class="vu-muted text-xs">FULLER values are shown as preset values and sent verbatim from profiles/fuller.json; explicit controls are refused. Listening acceptance covers only the identical chain on source a522115f4e72 with samples [180810, 218295); for this take it is <strong>not performed</strong>.</p>
				{/if}
				<button class="btn preset-filled-primary-300-700" type="submit" disabled={!selected.enabled}>Author {selected.id === 'fuller' ? 'FULLER' : 'custom'} settings</button>
				{#if form?.action === 'author'}
					{#if form.job}<p class="text-sm" data-submitted-job={form.job.job_id}>{form.job.replayed ? 'Replayed' : 'Queued'} <code>{form.job.job_id}</code> <JobStateBadge state={form.job.state} /></p>{/if}
					<LaneRefusal error={form.error} local={form.local} />
				{/if}
			</form>

			<form method="POST" action="?/apply" class="vu-panel card space-y-3 p-5" novalidate data-apply-form="true">
				<input type="hidden" name="idempotency_key" value={data.keys.apply} />
				<p class="vu-eyebrow">Step 2 · render full take (apply_capture_profile)</p>
				<label class="label space-y-1">
					<span class="label-text">Authored profile (succeeded capture_profile job, authored_unrendered)</span>
					<select class="select" name="capture_profile_job_id">
						<option value="">— choose an authored profile —</option>
						{#each authored as job (job.job_id)}<option value={job.job_id}>{job.job_id} · run {job.run_id}</option>{/each}
					</select>
				</label>
				<KnobField name="timeout_seconds" spec={data.catalogue?.apply?.knobs?.timeout_seconds} value={echoed('timeout_seconds')} />
				<button class="btn preset-filled-primary-300-700" type="submit" disabled={!selected.enabled || authored.length === 0}>Render full take</button>
				{#if authored.length === 0}<p class="vu-muted text-xs" data-refusal="capture_interval_required">No authored profile yet: <code>capture_interval_required</code>.</p>{/if}
				{#if form?.action === 'apply'}
					{#if form.job}<p class="text-sm" data-submitted-job={form.job.job_id}>Queued <code>{form.job.job_id}</code> <JobStateBadge state={form.job.state} /></p>{/if}
					<LaneRefusal error={form.error} local={form.local} />
				{/if}
			</form>
		{:else if selected && selected.jobPath[0] === 'denoise'}
			<form method="POST" action="?/denoise" class="vu-panel card space-y-3 p-5" novalidate data-denoise-form={selected.id}>
				<input type="hidden" name="profile" value={selected.id} />
				<input type="hidden" name="idempotency_key" value={data.keys.denoise} />
				<p class="vu-eyebrow">Render full take (denoise, fixed profile <code>{selected.id}</code>)</p>
				{#if !selected.enabled}<LaneRefusal local={{ code: selected.refusal_code ?? 'refused', message: selected.reason }} />{/if}
				<KnobField name="timeout_seconds" spec={data.catalogue?.denoise?.knobs?.timeout_seconds} value={echoed('timeout_seconds')} />
				<button class="btn preset-filled-primary-300-700" type="submit" disabled={!selected.enabled}>Render full take</button>
				{#if form?.action === 'denoise'}
					{#if form.job}<p class="text-sm" data-submitted-job={form.job.job_id}>{form.job.replayed ? 'Replayed' : 'Queued'} <code>{form.job.job_id}</code> <JobStateBadge state={form.job.state} /></p>{/if}
					<LaneRefusal error={form.error} local={form.local} />
				{/if}
			</form>
		{:else if selected}
			<p class="vu-panel card p-4 text-sm" data-option-unavailable={selected.id}><code>{selected.refusal_code}</code> — {selected.reason}</p>
		{/if}

		<section class="space-y-3" data-candidates="true">
			<div><p class="vu-eyebrow">Processing jobs</p><h2 class="h4">Candidates and authoring for this source</h2></div>
			{#if data.jobsError}<ControlApiError error={data.jobsError} />{/if}
			{#if data.processing.length === 0}
				<p class="vu-muted text-sm">No processing job yet.</p>
			{/if}
			{#each data.processing as job (job.job_id)}
				<article class="vu-panel card space-y-2 p-4" data-processing-job={job.job_id}>
					<p class="flex flex-wrap items-center gap-3 text-sm">
						<code>{job.tool}</code> <JobStateBadge state={job.state} />
						<span class="vu-muted text-xs">phase <code>{job.phase ?? 'unknown'}</code>{#if job.reason_code} · reason <code>{job.reason_code}</code>{/if}</span>
						<span class="vu-muted text-xs">run <UnknownValue value={job.run_id ?? null} mono /> · status <UnknownValue value={job.worker_status ?? null} /></span>
						<a class="anchor text-xs" href={`/jobs/${job.job_id}`}>job page</a>
						{#if reviewHref(job.run_id)}<a class="anchor text-xs" href={reviewHref(job.run_id)} data-review-link="true">review this run</a>{/if}
					</p>
					<p class="vu-muted text-xs">master adopted: false · listening acceptance: <UnknownValue value={null} reason="operator listening not performed for this version" /> · ~32 Hz preservation: <UnknownValue value={null} reason="not measured by a job service" /></p>
				</article>
			{/each}
			{#each candidates as job (job.job_id)}
				<div class="vu-panel card space-y-2 p-4" data-audition={job.job_id}>
					<p class="text-sm">Audition <code>{job.run_id}</code> ({job.tool})</p>
					<SpanAudition players={players(job)} />
				</div>
			{/each}
		</section>
	{/if}
</section>
