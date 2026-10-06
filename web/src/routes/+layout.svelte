<script lang="ts">
	import '../app.css';
	import type { Snippet } from 'svelte';
	let { children }: { children: Snippet } = $props();
</script>

<svelte:head>
	<title>video-utils web (prototype)</title>
</svelte:head>

<div class="mx-auto max-w-6xl space-y-6 px-4 py-8">
	<header class="space-y-3">
		<p class="vu-eyebrow">video-utils · local loopback fixture</p>
		<nav class="flex flex-wrap gap-2 text-sm" aria-label="Primary">
			<a class="btn btn-sm preset-tonal" href="/">Sources</a>
			<a class="btn btn-sm preset-outlined-surface-500" href="/upload">Upload (prototype)</a>
			<a class="btn btn-sm preset-outlined-surface-500" href="/compare">Compare (prototype)</a>
			<a class="btn btn-sm preset-outlined-surface-500" href="/review">Review (prototype)</a>
			<a class="btn btn-sm preset-outlined-surface-500" href="/download">Download (prototype)</a>
		</nav>
		<p class="vu-panel card p-3 text-sm" data-prototype-banner="true">
			Prototype — local loopback fixture; no processing is started from this page.
		</p>
	</header>
	<main>
		{@render children()}
	</main>
	<footer class="vu-muted text-xs">
		Values come from the local control API and are shown as reported. Unreported values read
		“Unknown”. No browser, accessibility, visual or listening acceptance is claimed by this build.
	</footer>
</div>
