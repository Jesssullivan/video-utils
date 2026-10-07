<script lang="ts">
	import ClaimList from '$lib/components/ClaimList.svelte';
	import { AXIOMS, SITE, claimsFor } from '$lib/content/claims';

	const capabilities = claimsFor('home');
</script>

<svelte:head>
	<title>{SITE.working_title}: practice-take restoration and rhythm review for technical guitar</title>
	<meta
		name="description"
		content="Local-first restoration and rhythm review of technical-guitar practice takes. Experimental software; accuracy on real recordings is unknown."
	/>
</svelte:head>

<h1>Practice takes, restored and reviewed</h1>
<p class="mt-6 text-lg">
	{SITE.working_title} is local-first software for restoring and reviewing guitar practice takes recorded on a phone
	or a laptop camera. A take becomes a shareable restored clip, with musical review data timed against the source
	and a reproducible record of how it was processed. It is built for woodshedding technical guitar and for clear
	communication among working bands.
</p>
<p class="mt-4">
	It is experimental and runs on your own machine. There is no hosted service.
	<a class="anchor" href="/status">See what is not done</a>.
</p>

<section class="mt-12" aria-labelledby="axioms-heading">
	<h2 id="axioms-heading">Three product axioms</h2>
	<div class="mt-6 grid gap-4 lg:grid-cols-3" data-prose-measure="none">
		{#each AXIOMS as axiom (axiom.id)}
			<article class="card bg-surface-100-900 space-y-3 p-5" data-axiom={axiom.id}>
				<h3>{axiom.title}</h3>
				<p>{axiom.text}</p>
			</article>
		{/each}
	</div>
</section>

<section class="mt-12" aria-labelledby="capabilities-heading">
	<h2 id="capabilities-heading">What it does, and what is not known</h2>
	<p class="mt-4">
		Each statement below carries a label saying what kind of claim it is. The unknowns sit in the same list as the
		capabilities on purpose.
	</p>
	<ClaimList claims={capabilities} label="Capabilities and unknowns" />
</section>

<section class="mt-12" aria-labelledby="more-heading">
	<h2 id="more-heading">Read further</h2>
	<ul class="mt-4 list-disc space-y-2 ps-6">
		<li><a class="anchor" href="/features">Features</a>: restoration, phrase and timing review, and agent tools.</li>
		<li><a class="anchor" href="/agents">Agent tools</a>: the typed tools and skills, generated from the registry.</li>
		<li><a class="anchor" href="/status">Status</a>: what is not done and what is unverified.</li>
	</ul>
</section>
