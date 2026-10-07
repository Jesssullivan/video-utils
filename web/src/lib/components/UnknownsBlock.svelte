<script lang="ts">
	import UnknownValue from './UnknownValue.svelte';
	import type { JobProjection } from '$lib/schema/control';
	interface Props {
		unknowns: JobProjection['unknowns'];
	}
	let { unknowns }: Props = $props();
	type Row = readonly [string, string | number | null, string | null];
	// S3 processing jobs (ROUTES_PROCESSING_S3 section 9) report a different closed set: every value is null with a
	// `<key>_reason`. They are listed by their reported key, never mapped onto the share_export labels.
	const PROCESSING_LABELS: Record<string, string> = {
		master_adopted: 'Master adopted',
		listening_acceptance: 'Listening acceptance',
		low_register_preservation: '~32 Hz low-register preservation',
		capture_noise_only: 'Capture interval is noise only',
		music_or_click_presence: 'Music or click presence in the interval',
		fuller_listening_transfer: 'FULLER listening acceptance transfer',
		musical_review: 'Musical review',
		level_matched: 'Level-matched audition',
		memory_bytes_peak: 'Peak memory (bytes)',
		cpu_seconds: 'CPU seconds',
		exactly_once: 'Exactly-once execution',
		slo: 'SLO',
		worker_birth: 'Worker birth evidence'
	};
	const scalar = (value: unknown): string | number | null =>
		typeof value === 'string' || (typeof value === 'number' && Number.isFinite(value)) ? value : value === null || value === undefined ? null : String(value);
	const rows = $derived.by((): ReadonlyArray<Row> => {
		if ('source_duration_seconds' in unknowns) {
			return [
				['Listening acceptance', unknowns.listening_acceptance, null],
				['Master adopted', String(unknowns.master_adopted), null],
				['~32 Hz low-register preservation', unknowns.low_register_preservation, unknowns.low_register_preservation_reason],
				['Musical review', unknowns.musical_review, unknowns.musical_review_reason],
				['Source duration (s)', unknowns.source_duration_seconds, unknowns.source_duration_seconds_reason],
				['Peak memory (bytes)', unknowns.memory_bytes_peak, unknowns.memory_bytes_peak_reason],
				['CPU seconds', unknowns.cpu_seconds, unknowns.cpu_seconds_reason],
				['Exactly-once execution', unknowns.exactly_once, null],
				['SLO', unknowns.slo, null],
				['Worker birth evidence', unknowns.worker_birth, unknowns.worker_birth_reason]
			];
		}
		const record = unknowns as Readonly<Record<string, unknown>>;
		return Object.keys(PROCESSING_LABELS)
			.filter((key) => key in record)
			.map((key): Row => {
				const reason = record[`${key}_reason`];
				return [PROCESSING_LABELS[key], scalar(record[key]), typeof reason === 'string' ? reason : null];
			});
	});
</script>

<dl class="grid grid-cols-1 gap-x-6 gap-y-1 text-sm sm:grid-cols-[16rem_1fr]" data-unknowns-block="true">
	{#each rows as [label, value, reason] (label)}
		<dt class="vu-muted">{label}</dt>
		<dd>
			<UnknownValue {value} />
			{#if reason}<span class="vu-muted text-xs" data-unknown-reason="true">{` — ${reason}`}</span>{/if}
		</dd>
	{/each}
</dl>
