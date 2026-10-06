<script lang="ts">
	// Renders null/undefined as the literal "Unknown" (never 0, blank or NaN).
	interface Props {
		value: string | number | null | undefined;
		suffix?: string;
		mono?: boolean;
	}
	let { value, suffix = '', mono = false }: Props = $props();
	const known = $derived(value !== null && value !== undefined && !(typeof value === 'number' && !Number.isFinite(value)));
</script>

{#if known}<span class:vu-time={mono}>{value}{suffix}</span>{:else}<span class="vu-unknown" data-unknown="true">Unknown</span>{/if}
