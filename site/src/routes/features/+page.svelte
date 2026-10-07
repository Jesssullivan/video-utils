<script lang="ts">
	import ClaimList from '$lib/components/ClaimList.svelte';
	import { SITE, claimsFor, type SectionId } from '$lib/content/claims';

	interface FeatureSection {
		readonly id: SectionId;
		readonly anchor: string;
		readonly title: string;
		readonly intro: string;
	}

	const sections: readonly FeatureSection[] = [
		{
			id: 'restoration',
			anchor: 'restoration',
			title: 'Restoration',
			intro:
				'Room recordings of a loud, distorted, low-tuned guitar carry background noise that overlaps the music. Cleanup is conservative: low-frequency energy is not assumed to be noise, and equalization is not described as recreating a fundamental the microphone did not capture or the sound of the amplifier in the room.'
		},
		{
			id: 'review',
			anchor: 'phrase-and-timing-review',
			title: 'Phrase and timing review',
			intro:
				'Review data is timed against the source recording so that a marker points at the same moment in the original clip. The aim is to help a player find the passages worth another listen, not to grade a performance.'
		},
		{
			id: 'agent_tools',
			anchor: 'agent-tools',
			title: 'Agent tools',
			intro:
				'Agent participation is part of the product. An agent can inspect a capture, look up options, run a bounded comparison and keep the result with its provenance, through the same typed tools a person can run by hand.'
		}
	];
</script>

<svelte:head>
	<title>Features | {SITE.working_title}</title>
	<meta
		name="description"
		content="Restoration, phrase and timing review, and agent tools, each with a note on what is measured and what is unknown."
	/>
</svelte:head>

<h1>Features</h1>
<p class="mt-6 text-lg">
	Three areas, each with a note that separates what exists or is measured on synthetic fixtures from what is unknown.
</p>

{#each sections as section (section.id)}
	<section class="mt-12" aria-labelledby={`${section.anchor}-heading`} data-feature-section={section.id}>
		<h2 id={`${section.anchor}-heading`}>{section.title}</h2>
		<p class="mt-4">{section.intro}</p>
		<div class="mt-6" data-measured-vs-unknown={section.id}>
			<h3>Measured vs unknown</h3>
			<ClaimList claims={claimsFor('features', section.id)} label={`${section.title}: measured vs unknown`} />
		</div>
		{#if section.id === 'agent_tools'}
			<p class="mt-4"><a class="anchor" href="/agents">See the generated list of agent tools</a>.</p>
		{/if}
	</section>
{/each}
