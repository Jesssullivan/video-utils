<script lang="ts">
	// The typed tools grouped by area with capability metadata for the pilot tools, and the model registry with
	// gate states. Registry views only: nothing here runs a tool, checks a model cache or changes a default.
	import ControlApiError from '$lib/components/ControlApiError.svelte';
	import RunUnknowns from '$lib/components/review/RunUnknowns.svelte';
	import { human, shortSha } from '$lib/components/review/review-logic';
	import type { PageProps } from './$types';
	let { data }: PageProps = $props();
	const caps = $derived(data.capabilities);
	const byName = $derived(new Map((caps?.tools ?? []).map((tool) => [tool.name, tool])));
	const hints = (annotations: Record<string, boolean | null>) =>
		Object.entries(annotations).filter(([, value]) => value === true).map(([key]) => key.replace('Hint', '')).join(', ') || 'none';
</script>

<section class="space-y-4" data-tools-page="true">
	<div>
		<p class="vu-eyebrow">Tools</p>
		<h1 class="h2">Typed tools and models</h1>
	</div>
	{#if data.error}
		<ControlApiError error={data.error} />
	{:else if caps}
		<p class="text-sm" data-tool-count={caps.tool_count}>{caps.tool_count} tools in program/tools.json; {caps.pilot_tool_count} carry capability metadata (capability pilot). Area basis: {caps.unknown_fields.tool_area_basis.value}.</p>
		{#each caps.areas as group (group.area)}
			<section class="space-y-2" data-area={group.area}>
				<h2 class="h4">{human(group.area)} <span class="vu-muted text-sm">({group.tools.length})</span></h2>
				<div class="grid grid-cols-1 gap-3 lg:grid-cols-2">
					{#each group.tools as name (name)}
						{@const tool = byName.get(name)}
						{#if tool}
							<article class="vu-panel card space-y-1 p-3 text-sm" data-tool={tool.name}>
								<h3 class="h5"><code>{tool.name}</code> · {tool.title ?? 'untitled'}</h3>
								<p>Status {tool.implementation_status ?? 'unknown'} · evidence {tool.evidence_kind ?? 'unknown'} · hints: {hints(tool.annotations)}</p>
								<p class="vu-muted text-xs">Skill <code>{tool.skill ?? 'unknown'}</code> · area basis: {tool.area_basis}</p>
								<details><summary>Limitations ({tool.limitations_count})</summary><ul class="list-disc pl-5 text-xs">{#each tool.limitations as text, index (index)}<li>{text}</li>{/each}</ul></details>
								<p class="text-xs">Dependencies: {tool.dependencies.recommended_prior_tools.join(', ') || 'none recommended'} (enforced: {tool.dependencies.enforced ?? 'unknown'}). Inputs: {tool.input.properties.join(', ')}; required {tool.input.required.join(', ') || 'none'}.</p>
								{#if tool.capability}
									{@const cap = tool.capability}
									<div class="rounded border border-dashed p-2 text-xs" data-capability="true">
										<p>Capability: {cap.domain} · {cap.stage}</p>
										<p>Effects — reads {cap.effects.reads.join(', ') || 'none'}; writes {cap.effects.writes.join(', ') || 'none'}; renders audio {cap.effects.renders_audio}; renders video {cap.effects.renders_video}; network {cap.effects.network}; model acquisition {cap.effects.model_acquisition}</p>
										<p>Resources — {cap.resources.resource_class} · heavy numeric {cap.resources.heavy_numeric} · timeout {cap.resources.timeout_seconds.min ?? '?'}–{cap.resources.timeout_seconds.max ?? '?'} s (default {cap.resources.timeout_seconds.default ?? '?'})</p>
										<p>Default ownership — {Object.entries(cap.parameters).map(([param, spec]) => `${param}: ${spec.default_owner ?? '?'} / ${spec.default_policy ?? '?'}`).join('; ')}</p>
									</div>
								{:else}
									<p class="vu-muted text-xs">capability: null — {tool.capability_reason}</p>
								{/if}
							</article>
						{/if}
					{/each}
				</div>
			</section>
		{/each}

		<section class="space-y-2" data-models="true">
			<h2 class="h4" id="models-heading">Models</h2>
			<!-- Wide table: the scroll region is focusable so keyboard users can scroll it (axe scrollable-region-focusable). -->
			<!-- svelte-ignore a11y_no_noninteractive_tabindex -->
			<div class="table-wrap vu-panel card overflow-x-auto" role="region" aria-labelledby="models-heading" tabindex="0">
				<table class="table text-sm">
					<thead><tr><th>Model</th><th>Format</th><th>License</th><th>SHA-256</th><th>Max bytes</th><th>Host</th><th>Registration</th><th>Gate state</th><th>Local presence</th></tr></thead>
					<tbody>
						{#each caps.models as model (model.model_id)}
							<tr data-model={model.model_id}>
								<td><code>{model.model_id}</code>{model.lane ? ` · lane ${model.lane}` : ''}</td>
								<td>{model.format ?? 'unknown'}</td>
								<td class="text-xs">{model.license ?? 'unknown'}</td>
								<td class="vu-time" title={model.sha256 ?? ''}>{shortSha(model.sha256)}</td>
								<td class="vu-time">{model.max_bytes ?? 'unknown'}</td>
								<td>{model.url_host ?? 'unknown'}</td>
								<td>{human(model.registration)}</td>
								<td>{model.gate_state.value ?? 'Unknown'} <span class="vu-muted text-xs">— {model.gate_state.reason}</span></td>
								<td>{human(model.local_presence)}</td>
							</tr>
						{/each}
					</tbody>
				</table>
			</div>
			<p class="vu-muted text-xs" data-model-note="true">{caps.model_note}</p>
		</section>
		<RunUnknowns fields={caps.unknown_fields} title="Registry unknowns" />
	{/if}
</section>
