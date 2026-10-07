<script lang="ts">
	import ClaimList from '$lib/components/ClaimList.svelte';
	import { SITE, claimsFor } from '$lib/content/claims';
	import type { PageProps } from './$types';

	let { data }: PageProps = $props();

	const withheld = $derived(data.tools.filter((tool) => tool.intent === null).length);
	const skillCount = $derived(new Set(data.tools.map((tool) => tool.skill_name)).size);
</script>

<svelte:head>
	<title>Agent tools | {SITE.working_title}</title>
	<meta
		name="description"
		content="Typed Model Context Protocol tools and their skills, generated from the repository tool registry. Names and intents only."
	/>
</svelte:head>

<h1>Agent tools</h1>
<p class="mt-6 text-lg">
	Every processing primitive has a typed tool that an agent can call over the Model Context Protocol, and a written
	skill that tells the agent how to use it. This page shows names and intents only.
</p>

<section class="mt-12" aria-labelledby="registry-heading">
	<h2 id="registry-heading">Registry summary</h2>
	<p class="mt-4" data-tool-count={data.tool_count} data-skill-count={skillCount} data-intents-withheld={withheld}>
		The registry lists {data.tool_count} tools backed by {skillCount} skills.
	</p>
	<ul class="mt-4 list-disc space-y-1 ps-6" aria-label="Tools by implementation status">
		{#each data.status_counts as entry (entry.status)}
			<li data-status={entry.status} data-status-count={entry.count}>
				{entry.count} of {data.tool_count} marked <span class="font-mono">{entry.status}</span>
			</li>
		{/each}
	</ul>
	{#if withheld > 0}
		<p class="mt-4">
			{withheld} of {data.tool_count} intents are withheld from this public page pending review of their wording.
		</p>
	{/if}
	<ClaimList claims={claimsFor('agents')} label="What this list does and does not say" />
</section>

<section class="mt-12" aria-labelledby="tools-heading">
	<h2 id="tools-heading">Tools</h2>
	<ul class="mt-6 grid list-none gap-3 p-0 lg:grid-cols-2" aria-label="Agent tools" data-prose-measure="none">
		{#each data.tools as tool (tool.name)}
			<li class="card bg-surface-100-900 space-y-2 p-4" data-tool={tool.name}>
				<h3 class="h4">{tool.title}</h3>
				<p class="text-surface-700-300 font-mono text-xs">
					tool <span data-tool-name>{tool.name}</span> · skill <span data-skill-name>{tool.skill_name}</span>
				</p>
				{#if tool.intent === null}
					<p data-intent-withheld={tool.name}><em>Intent withheld from the public page.</em></p>
				{:else}
					<p data-tool-intent>{tool.intent}</p>
				{/if}
			</li>
		{/each}
	</ul>
</section>
