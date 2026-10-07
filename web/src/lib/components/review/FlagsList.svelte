<script lang="ts">
	// Triaged flags (port of practice_s2.js s2RenderFlags): shown list in triage order; navigation proxies and
	// suppressed flags behind toggles that default to off. Numeric confidence is never shown or used for order.
	import BasisBadge from './BasisBadge.svelte';
	import { clockText, human, type FlagItem } from './review-logic';
	interface Props {
		available: boolean;
		reason: string | null;
		shown: FlagItem[];
		navigation: FlagItem[];
		suppressed: FlagItem[];
		denominators: Record<string, unknown>;
		windowKind: string;
		showNavigation: boolean;
		showSuppressed: boolean;
		onseek: (seconds: number, flag: FlagItem) => void;
	}
	let { available, reason, shown, navigation, suppressed, denominators, windowKind, showNavigation = $bindable(), showSuppressed = $bindable(), onseek }: Props = $props();
	const count = (key: string) => (typeof denominators[key] === 'number' ? String(denominators[key]) : 'unknown');
	const basisText = $derived(
		windowKind.startsWith('click_grid') ? 'click-grid navigation window — not bar, phrase or meter' : windowKind === 'phrase_spans' ? 'phrase spans' : human(windowKind)
	);
</script>

<section class="space-y-2 text-sm" data-flags="true">
	<h2 class="h5">Triaged flags</h2>
	{#if !available}
		<p class="vu-muted">Unavailable: {human(reason ?? 'unknown')}.</p>
	{:else}
		<p data-flag-denominators="true">shown {count('shown')} of {count('total_flags')} flags · navigation hidden {count('navigation_hidden')} · suppressed {count('suppressed_lower_priority')}</p>
		<p class="vu-muted text-xs">Window basis: {basisText} ({windowKind}). {windowKind === 'phrase_spans' ? 'At most one per phrase span.' : 'At most one per navigation window.'} Ordering is the triage file's own rule.</p>
		<ul class="space-y-1">
			{#each shown as flag (flag.id)}
				<li data-flag-id={flag.id}>
					<BasisBadge origin="detector" /> {flag.window} · {flag.kind} · {clockText(flag.start)} → {clockText(flag.end)} {flag.tier ? `· ${flag.tier}` : ''}
					{#if flag.start !== null}<button type="button" class="btn btn-sm preset-tonal" onclick={() => flag.start !== null && onseek(flag.start, flag)}>Seek</button>{/if}
				</li>
			{/each}
		</ul>
		<label class="flex items-center gap-2"><input type="checkbox" class="checkbox" bind:checked={showNavigation} /> Show navigation proxies ({navigation.length}) — navigation proxy; not a confirmed bar</label>
		{#if showNavigation}
			<ul class="space-y-1 pl-4">{#each navigation as flag (flag.id)}<li>{flag.kind} · {clockText(flag.start)} · {flag.note}</li>{/each}</ul>
		{/if}
		<label class="flex items-center gap-2"><input type="checkbox" class="checkbox" bind:checked={showSuppressed} /> Show suppressed ({suppressed.length})</label>
		{#if showSuppressed}
			<ul class="space-y-1 pl-4">{#each suppressed as flag (flag.id)}<li>{flag.kind} · {clockText(flag.start)} · {flag.note}</li>{/each}</ul>
		{/if}
	{/if}
</section>
