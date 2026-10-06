<script lang="ts">
	// Renders null/undefined/non-finite as the literal "Unknown" (never 0, blank or NaN), with its reason.
	interface Props {
		value: string | number | null | undefined;
		suffix?: string;
		mono?: boolean;
		reason?: string | null;
	}
	let { value, suffix = '', mono = false, reason = null }: Props = $props();
	const known = $derived(value !== null && value !== undefined && !(typeof value === 'number' && !Number.isFinite(value)));
</script>

{#if known}<span class:vu-time={mono}>{value}{suffix}</span>{:else}<span class="vu-unknown" data-unknown="true" title={reason ?? undefined}>Unknown</span>{#if reason}<span class="vu-muted text-xs" data-unknown-reason="true"> — {reason}</span>{/if}{/if}
