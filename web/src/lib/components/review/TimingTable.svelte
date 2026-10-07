<script lang="ts">
	// Per-phrase timing as measurements (phrase_timing schema 2): signed median, IQR and count. Real-take rows read
	// "direction withheld (uncalibrated)"; a direction class appears only on a synthetic known-offset fixture row.
	// An abstained row shows — and its reason, never 0. Offsets describe timing evidence only.
	import { arr, clockText, human, rec, shortSha, str, timingRows } from './review-logic';
	interface Props {
		layer: { readonly status: string; readonly reason: string | null; readonly document: unknown };
		onseek: (seconds: number) => void;
	}
	let { layer, onseek }: Props = $props();
	const files = $derived(arr(rec(layer.document).files).map(rec));
	const refused = $derived(arr(rec(layer.document).refused).map(rec));
</script>

<section class="space-y-2 text-sm" data-timing="true">
	<h3 class="h5">Per-phrase timing</h3>
	{#if layer.status !== 'available'}
		<p class="vu-muted" data-timing-unavailable={layer.reason ?? 'unavailable'}>Unavailable: {human(layer.reason ?? 'unknown')}.</p>
	{:else}
		<p class="vu-eyebrow">MEASUREMENT · unvalidated until operator spot check · click identity unverified · capture latency uncalibrated</p>
		<p class="vu-muted text-xs">Offsets are onset minus modelled click (negative = before the modelled click). They never grade the performance.</p>
		{#each files as file, index (index)}
			{@const doc = rec(file.document)}
			{@const rows = timingRows(doc)}
			<details open={index === 0} data-run-kind={str(file.run_kind) ?? 'unknown'}>
				<summary>{human(doc.phrase_basis ?? 'phrase basis unknown')} · measured {rows.filter((row) => row.measured).length} of {rows.length} · {shortSha(file.sha256)}</summary>
				<p class="vu-muted text-xs">run kind: {human(file.run_kind)} · real-take status: {human(doc.real_take_status)} · direction: {file.run_kind === 'synthetic_fixture' ? 'synthetic known-offset fixture only' : 'withheld until operator calibration'} · detector delay: {human(rec(doc.detector_delay).status ?? 'uncalibrated')}</p>
				<div class="table-wrap overflow-x-auto">
					<table class="table text-xs">
						<thead><tr><th>Phrase</th><th>Label basis</th><th>Span</th><th>Status</th><th>Median offset</th><th>IQR</th><th>Count</th><th>Direction</th></tr></thead>
						<tbody>
							{#each rows as row (row.id)}
								<tr data-timing-row={row.id} data-measured={row.measured}>
									<td>{#if row.start !== null}<button type="button" class="anchor" onclick={() => row.start !== null && onseek(row.start)}>{row.label}</button>{:else}{row.label}{/if}</td>
									<td>{row.labelBasis}</td>
									<td class="vu-time">{clockText(row.span[0])} → {clockText(row.span[1])}</td>
									<td>{row.status}</td>
									<td class="vu-time">{row.median}</td>
									<td class="vu-time">{row.iqr}</td>
									<td class="vu-time">n {row.count}</td>
									<td data-direction={row.direction}>{row.measured ? row.direction : `— abstained: ${row.abstain}`}</td>
								</tr>
							{/each}
						</tbody>
					</table>
				</div>
			</details>
		{/each}
	{/if}
	{#each refused as item, index (index)}
		<p class="vu-muted text-xs">Timing file {str(item.file) ?? 'unknown'} not shown: {human(item.reason)}.</p>
	{/each}
</section>
