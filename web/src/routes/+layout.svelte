<script lang="ts">
	import '../app.css';
	import type { Snippet } from 'svelte';
	import { page } from '$app/state';
	import StepBar from '$lib/components/review/StepBar.svelte';
	import { isStepContext } from '$lib/components/review/step-context';
	let { children }: { children: Snippet } = $props();

	// Primary navigation (ROUTES_REVIEW_S3.md 6.1). Capture and Process live under /sources/[id] (routes_processing)
	// and are reached from the step bar, which appears whenever a page provides `stepContext`.
	const NAV = [
		{ href: '/', label: 'Clips' },
		{ href: '/upload', label: 'Upload' },
		{ href: '/runs', label: 'Runs' },
		{ href: '/jobs', label: 'Jobs' },
		{ href: '/tools', label: 'Tools' }
	] as const;
	const stepContext = $derived(isStepContext(page.data?.stepContext) ? page.data.stepContext : null);
	const active = (href: string) => (href === '/' ? page.url.pathname === '/' : page.url.pathname.startsWith(href));
</script>

<svelte:head>
	<title>video-utils web (local pilot)</title>
</svelte:head>

<a class="vu-skip" href="#main">Skip to content</a>
<div class="mx-auto max-w-6xl space-y-6 px-4 py-8">
	<header class="space-y-3">
		<p class="vu-eyebrow">video-utils · local loopback pilot</p>
		<nav class="flex flex-wrap gap-2 text-sm" aria-label="Primary">
			{#each NAV as item (item.href)}
				<a class="btn btn-sm {active(item.href) ? 'preset-filled-primary-500' : 'preset-tonal'}" href={item.href}
					aria-current={active(item.href) ? 'page' : undefined}>{item.label}</a>
			{/each}
		</nav>
		{#if stepContext}<StepBar context={stepContext} />{/if}
		<p class="vu-panel card p-3 text-sm" data-pilot-banner="true">Local loopback pilot — private; not a hosted service.</p>
	</header>
	<main id="main" tabindex="-1">
		{@render children()}
	</main>
	<footer class="vu-muted text-xs">
		Values come from the local control API and are shown as reported. Unreported values read “Unknown” with their
		reason. No browser playback, hydration, accessibility, visual, level-matching or listening acceptance is claimed by
		this build, and no note-correctness, missed-note or phrase verdict is made.
	</footer>
</div>

<style>
	.vu-skip {
		position: absolute;
		left: -9999px;
		top: 0.5rem;
		padding: 0.5rem 0.75rem;
		background: var(--vu-panel);
		border: 1px solid var(--vu-gold);
		z-index: 50;
	}
	.vu-skip:focus {
		left: 0.5rem;
	}
	:global(a:focus-visible),
	:global(button:focus-visible),
	:global(select:focus-visible),
	:global(input:focus-visible),
	:global(textarea:focus-visible),
	:global(summary:focus-visible),
	:global([tabindex]:focus-visible) {
		outline: 2px solid var(--vu-gold);
		outline-offset: 2px;
	}
	:global(.vu-steps .vu-step) {
		display: inline-flex;
		align-items: baseline;
		gap: 0.25rem;
		padding: 0.15rem 0.5rem;
		border: 1px solid var(--vu-line);
		border-radius: 999px;
	}
	:global(.vu-steps .vu-step[data-step-current='true']) {
		border-color: var(--vu-gold);
	}
	:global(.vu-state) {
		font-size: 0.8rem;
		white-space: nowrap;
	}
	:global(.vu-basis) {
		display: inline-flex;
		align-items: baseline;
		gap: 0.25rem;
		padding: 0.05rem 0.45rem;
		font-size: 0.72rem;
		letter-spacing: 0.04em;
		border: 1px solid var(--vu-line);
		border-radius: 999px;
	}
	:global(.vu-basis-text) {
		letter-spacing: 0;
		color: var(--vu-muted);
	}
	:global(.vu-shape-solid) {
		background: #5b4a2c;
		border-style: solid;
	}
	:global(.vu-shape-bracket) {
		border-radius: 2px;
		border-style: solid;
	}
	:global(.vu-shape-hollow) {
		border-style: dashed;
	}
	:global(.vu-shape-dotted) {
		border-style: dotted;
	}
	:global(.vu-shape-double) {
		border-style: double;
		border-width: 3px;
	}
</style>
