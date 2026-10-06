<script lang="ts">
	import UnknownValue from './UnknownValue.svelte';
	import type { Unknowns } from '$lib/schema/control';
	interface Props {
		unknowns: Unknowns;
	}
	let { unknowns }: Props = $props();
	const rows = $derived([
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
	] as const);
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
