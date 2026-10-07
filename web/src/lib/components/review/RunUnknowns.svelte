<script lang="ts">
	// Every unknown key with its value and reason (33 run keys or the capabilities subset). Unknown stays unknown.
	import { human } from './review-logic';
	interface Entry {
		readonly value: unknown;
		readonly reason: string | null;
		readonly basis?: string;
	}
	interface Props {
		fields: Readonly<Record<string, Entry>>;
		title?: string;
	}
	let { fields, title = 'Unknown and not-established fields' }: Props = $props();
	const rows = $derived(Object.entries(fields));
	const show = (value: unknown): string =>
		value === null || value === undefined ? 'Unknown' : typeof value === 'object' ? JSON.stringify(value) : human(value);
</script>

<details class="vu-panel card p-3 text-sm" data-unknowns-block="true" data-unknown-count={rows.length}>
	<summary>{title} ({rows.length})</summary>
	<dl class="mt-2 grid grid-cols-1 gap-x-4 gap-y-1 sm:grid-cols-[16rem_1fr]">
		{#each rows as [key, entry] (key)}
			<dt class="vu-muted" data-unknown-key={key}>{human(key)}</dt>
			<dd>
				<span class:vu-unknown={entry.value === null || entry.value === undefined}>{show(entry.value)}</span>
				<span class="vu-muted text-xs" data-unknown-reason="true"> — {entry.reason ?? 'reason not recorded'}</span>
				{#if entry.basis}<span class="vu-muted text-xs"> ({entry.basis})</span>{/if}
			</dd>
		{/each}
	</dl>
</details>
