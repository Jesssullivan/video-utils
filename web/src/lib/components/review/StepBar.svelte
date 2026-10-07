<script lang="ts">
	// Step indicator Clip / Capture / Process / Review / Download. A step without a target renders as text
	// with its disabled reason, never as a dead link. Review carries Compare and Graph sub-tabs on run routes.
	import { STEP_ORDER, stepTarget, type StepContext } from './step-context';
	interface Props {
		context: StepContext;
	}
	let { context }: Props = $props();
	const steps = $derived(STEP_ORDER.map((step) => ({ ...step, ...stepTarget(context, step.key) })));
	const run = $derived(context.run_id);
</script>

<nav class="vu-steps" aria-label="Workflow steps" data-step-bar="true">
	<ol class="flex flex-wrap items-center gap-1 text-sm">
		{#each steps as step, index (step.key)}
			<li class="vu-step" data-step={step.key} data-step-current={step.key === context.current}>
				<span class="vu-muted text-xs" aria-hidden="true">{index + 1}</span>
				{#if step.href}
					<a class="anchor" href={step.href} aria-current={step.key === context.current ? 'step' : undefined}>{step.label}</a>
				{:else}
					<span data-step-disabled="true" title={step.reason ?? undefined}>{step.label}</span>
					<span class="vu-muted text-xs" data-step-reason={step.reason}>({step.reason})</span>
				{/if}
				{#if step.key === context.current}<span class="vu-step-mark" aria-hidden="true">◆</span>{/if}
			</li>
		{/each}
	</ol>
	{#if run && context.current === 'review'}
		<ul class="mt-1 flex flex-wrap gap-2 text-xs" aria-label="Review sub-tabs" data-review-tabs="true">
			<li><a class="anchor" href={`/runs/${run}/review`} aria-current={context.review_tab === 'review' ? 'page' : undefined}>Review</a></li>
			<li><a class="anchor" href={`/runs/${run}/compare`} aria-current={context.review_tab === 'compare' ? 'page' : undefined}>Compare</a></li>
			<li><a class="anchor" href={`/runs/${run}`} aria-current={context.review_tab === 'graph' ? 'page' : undefined}>Graph</a></li>
		</ul>
	{/if}
</nav>
