<script lang="ts">
	import ClaimList from '$lib/components/ClaimList.svelte';
	import { SITE, claimsFor } from '$lib/content/claims';

	const all = claimsFor('status');
	const notDone = all.filter((claim) => claim.claim_class === 'not_done');
	const unverified = all.filter((claim) => claim.claim_class !== 'not_done');
</script>

<svelte:head>
	<title>Status | {SITE.working_title}</title>
	<meta name="description" content="What is not done, what is unverified and what this site stores in your browser." />
</svelte:head>

<h1>Status</h1>
<p class="mt-6 text-lg">
	This page lists what has not been done and what has no supporting evidence. It is the plain version; the same
	limits appear beside the capabilities on the other pages.
</p>

<section class="mt-12" aria-labelledby="not-done-heading">
	<h2 id="not-done-heading">Not done</h2>
	<ClaimList claims={notDone} label="Work that has not been performed" />
</section>

<section class="mt-12" aria-labelledby="unverified-heading">
	<h2 id="unverified-heading">Unknown or unverified</h2>
	<ClaimList claims={unverified} label="Quantities and outcomes without supporting evidence" />
</section>

<section class="mt-12" aria-labelledby="site-heading">
	<h2 id="site-heading">About this site</h2>
	<p class="mt-4">
		This is a static site. It has no analytics, no sign-up, no upload and no contact transport. It sets no cookies and
		loads no script, stylesheet, font or image from another origin. The only thing it keeps in your browser is the
		theme and colour mode you choose with the theme control, held in local storage.
	</p>
	<p class="mt-4">
		No audio, video, still image or measurement from a real recording is published here. {SITE.working_title} is a
		working title; a public product name has not been chosen.
	</p>
</section>
