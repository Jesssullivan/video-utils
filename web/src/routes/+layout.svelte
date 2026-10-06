<script lang="ts">
	import '../app.css';
	import type { Snippet } from 'svelte';
	let { children }: { children: Snippet } = $props();
</script>

<svelte:head>
	<title>video-utils web (local pilot)</title>
</svelte:head>

<div class="mx-auto max-w-6xl space-y-6 px-4 py-8">
	<header class="space-y-3">
		<p class="vu-eyebrow">video-utils · local loopback pilot</p>
		<nav class="flex flex-wrap gap-2 text-sm" aria-label="Primary">
			<a class="btn btn-sm preset-tonal" href="/">Sources</a>
			<a class="btn btn-sm preset-tonal" href="/upload">Upload / admit</a>
			<a class="btn btn-sm preset-outlined-surface-500" href="/compare">Compare</a>
			<a class="btn btn-sm preset-outlined-surface-500" href="/review">Review</a>
			<a class="btn btn-sm preset-outlined-surface-500" href="/download">Download</a>
		</nav>
		<p class="vu-panel card p-3 text-sm" data-pilot-banner="true">Local loopback pilot — private; not a hosted service.</p>
	</header>
	<main>
		{@render children()}
	</main>
	<footer class="vu-muted text-xs">
		Values come from the local control API and are shown as reported. Unreported values read “Unknown” with their
		reason. No browser playback, hydration, accessibility, visual, level-matching or listening acceptance is claimed by
		this build, and no note-correctness, missed-note or phrase verdict is made.
	</footer>
</div>
