<script lang="ts">
	// Matched-level A/B from the tone_ab layer (port of practice_s2.js s2RenderAB). The excerpt files are
	// pre-gained by tone_ab; this page applies no gain. One active player at a time; preload none; playback starts only from the operator.
	import { arr, fixed, human, num, rec, signed, str } from './review-logic';
	import { layerMediaUrl, pauseOthers } from './media';

	interface MediaEntry {
		readonly evidence_id: string;
		readonly sha256: string;
	}
	interface Props {
		runId: string;
		layer: { readonly status: string; readonly reason: string | null; readonly document: unknown };
		media: Readonly<Record<string, MediaEntry>>;
		browserLevelMatch: { readonly value: unknown; readonly reason: string | null } | null;
	}
	let { runId, layer, media, browserLevelMatch }: Props = $props();

	const doc = $derived(rec(layer.document));
	const match = $derived(rec(doc.loudness_match));
	const region = $derived(rec(doc.region));
	const arms = $derived(Object.entries(rec(match.per_arm)).map(([name, value]) => ({ name, f: rec(value) })));
	const pairs = $derived(arr(rec(doc.excerpts).pairs).map(rec));
	const blindKey = $derived(arr(rec(doc.excerpts).blind_key).map(rec));
	const pairMedia = $derived(arr(doc.pair_media).map(rec));
	const trial = $derived(rec(doc.trial));
	const experiment = $derived(rec(doc.experiment));
	const claims = $derived(rec(doc.claims));
	const bandDeltas = $derived(Object.entries(rec(experiment.band_deltas_vs_delivery_master)).map(([band, value]) => ({ band, f: rec(value) })));
	const attackDeltas = $derived(Object.entries(rec(experiment.attack_deltas_vs_delivery_master)).map(([name, value]) => ({ name, f: rec(value) })));
	const excluded = $derived(arr(region.excluded_setup_interval_seconds));

	let pairIndex = $state(0);
	let revealed = $state<Record<number, boolean>>({}); // local display toggle; never saved
	const pair = $derived(pairs[Math.min(pairIndex, Math.max(0, pairs.length - 1))] ?? null);
	const names = $derived(pairMedia.find((item) => item.pair === pair?.pair) ?? {});
	const keyRow = $derived(blindKey.find((item) => item.pair === pair?.pair) ?? null);
	const trialPair = $derived(arr(trial.pairs).map(rec).find((item) => item.pair === pair?.pair) ?? null);
	const armName = (arm: unknown) => (arm === 'delivery_master' ? 'FULLER delivery master' : arm === 'source' ? 'source' : human(arm));
	const url = (name: unknown) => {
		const text = str(name);
		const entry = text ? media[text] : undefined;
		return text && entry ? layerMediaUrl(runId, entry.evidence_id, text) : null;
	};
</script>

{#if layer.status !== 'available'}
	<div class="vu-panel card space-y-1 p-4 text-sm" data-ab-unavailable={layer.reason ?? 'unavailable'}>
		<p>Matched-level A/B is unavailable: <code>{layer.reason ?? 'unavailable'}</code>.</p>
		<p>Open the <a class="anchor" href={`/runs/${runId}`}>run graph</a> for bound evidence and invalidation.</p>
	</div>
{:else}
	<section class="space-y-4" data-ab="true">
		<div class="vu-panel card space-y-1 p-4 text-sm">
			<p data-match-status={str(match.match_status) ?? 'unknown'}>
				Region match: <strong>{human(match.match_status)}</strong>, ±{fixed(match.match_lu_delta, 3)} LU (tolerance {fixed(match.tolerance_lu, 2)} LU),
				target {fixed(match.target_lufs, 2)} LUFS over {fixed(region.start_seconds, 2)}–{fixed(region.end_seconds, 2)} s (measured).
			</p>
			{#if excluded.length === 2}<p>Excluded setup interval: {fixed(excluded[0], 2)}–{fixed(excluded[1], 2)} s (not part of the matched region).</p>{/if}
			<p class="vu-muted text-xs">Meter (verbatim): {str(match.meter) ?? 'unknown'}{match.policy ? ` · policy: ${str(match.policy)}` : ''}</p>
			<p data-operator-preference="not recorded">operator_preference: <strong>not recorded</strong> (no control on this page)</p>
			<p>Browser level match (verbatim): {browserLevelMatch ? `${human(browserLevelMatch.value)} — ${browserLevelMatch.reason ?? ''}` : 'unknown'}</p>
		</div>

		<div class="table-wrap vu-panel card overflow-x-auto">
			<table class="table text-sm" data-arms="true">
				<caption class="vu-muted text-xs">Per-arm static gain to the matched target (measurements; denominators: {arms.length} arms)</caption>
				<thead><tr><th>Arm</th><th>LUFS before</th><th>Gain dB</th><th>LUFS after</th><th>|Δ| LU</th></tr></thead>
				<tbody>
					{#each arms as arm (arm.name)}
						<tr data-arm={arm.name}>
							<td>{human(arm.name)}{arm.name.startsWith('trial') ? ' · unreviewed trial; not adopted' : ''}</td>
							<td class="vu-time">{fixed(arm.f.lufs_before, 2)}</td>
							<td class="vu-time">{signed(arm.f.gain_db, 2)}</td>
							<td class="vu-time">{fixed(arm.f.lufs_after, 2)}</td>
							<td class="vu-time">{fixed(arm.f.abs_delta_lu, 3)}</td>
						</tr>
					{/each}
				</tbody>
			</table>
		</div>

		<div class="vu-panel card space-y-3 p-4" data-pairs="true">
			<div class="flex flex-wrap gap-2" role="group" aria-label="Excerpt pair">
				{#each pairs as item, index (index)}
					<button type="button" class="btn btn-sm {index === pairIndex ? 'preset-filled-primary-300-700' : 'preset-tonal'}" aria-pressed={index === pairIndex} onclick={() => (pairIndex = index)}>Pair {String(item.pair)}</button>
				{/each}
			</div>
			{#if pair}
				<p class="vu-muted text-xs">Pair {String(pair.pair)} · native samples {String(pair.start_sample)}–{String(pair.end_sample_exclusive)} ({fixed(pair.start_seconds, 3)} s start, source audio clock)</p>
				<div class="grid grid-cols-1 gap-3 md:grid-cols-2">
					{#each ['X', 'Y'] as side (side)}
						<figure class="space-y-1">
							<figcaption class="text-sm">{side}</figcaption>
							{#if url(names[side])}
								<audio controls preload="none" src={url(names[side])} data-ab-player={side} aria-label={`Excerpt pair ${String(pair.pair)} player ${side}`} onplay={(event) => pauseOthers(event.currentTarget)}></audio>
							{:else}
								<p class="vu-muted text-sm">Media not served for this side.</p>
							{/if}
						</figure>
					{/each}
				</div>
				<button type="button" class="btn btn-sm preset-tonal" aria-pressed={!!revealed[pairIndex]} onclick={() => (revealed = { ...revealed, [pairIndex]: !revealed[pairIndex] })}>
					{revealed[pairIndex] ? 'Hide mapping' : 'Reveal which is FULLER'}
				</button>
				<p class="text-sm" data-mapping={revealed[pairIndex] ? 'revealed' : 'hidden'}>
					{#if revealed[pairIndex] && keyRow}X = {armName(keyRow.X)} · Y = {armName(keyRow.Y)} (display only; not saved, not a preference){:else}Mapping hidden. Revealing is a local display toggle; it is never saved.{/if}
				</p>
				<details class="text-sm">
					<summary>Per-file level measurements (measured; gains can hint at the mapping)</summary>
					{#each ['X', 'Y'] as side (side)}
						{@const file = rec(rec(pair.files)[side])}
						<p>{side}: static gain {signed(file.static_gain_db, 2)} dB · excerpt LUFS {fixed(file.excerpt_lufs_informational, 2)} (informational) · sample peak {fixed(file.sample_peak_dbfs, 2)} dBFS · true peak {num(file.true_peak_dbtp) === null ? 'not measured' : `${fixed(file.true_peak_dbtp, 2)} dBTP`}</p>
					{/each}
				</details>
				<div class="space-y-1 rounded border border-dashed p-3" data-trial={str(trial.status) ?? 'unknown'}>
					<p class="text-sm"><strong>TRIAL</strong> · {human(rec(trial.controls).type ?? 'trial')} {fixed(rec(trial.controls).frequency_hz, 0)} Hz {signed(rec(trial.controls).gain_db, 1)} dB · unreviewed trial; not adopted</p>
					{#if trial.status === 'available' && trialPair && url(trialPair.media)}
						<audio controls preload="none" src={url(trialPair.media)} data-ab-player="trial" aria-label="Trial excerpt (unblinded)" onplay={(event) => pauseOthers(event.currentTarget)}></audio>
						<p class="vu-muted text-xs">Unblinded. Same native samples as the pair; static gain {signed(trial.gain_db, 2)} dB from the tone_ab region match.</p>
					{:else}
						<p class="vu-muted text-sm">Trial excerpt unavailable: {human(trial.reason ?? 'not served')}.</p>
					{/if}
				</div>
			{:else}
				<p class="vu-muted text-sm">No excerpt pairs in tone-ab.json.</p>
			{/if}
		</div>

		{#if bandDeltas.length || attackDeltas.length}
			<div class="vu-panel card space-y-2 p-4 text-sm" data-band-measurements="true">
				<h2 class="h5">Trial vs delivery master: band and attack measurements</h2>
				{#if bandDeltas.length}
					<div class="table-wrap overflow-x-auto">
						<table class="table text-sm">
							<caption class="vu-muted text-xs">Mixture-energy band deltas (dB); {bandDeltas.length} bands. Not fan/music separated.</caption>
							<thead><tr><th>Band (Hz)</th><th>Raw dB</th><th>Matched dB</th><th>Share dB</th></tr></thead>
							<tbody>
								{#each bandDeltas as row (row.band)}
									<tr><td>{row.band}</td><td class="vu-time">{signed(row.f.raw_db, 2)}</td><td class="vu-time">{signed(row.f.matched_db, 2)}</td><td class="vu-time">{signed(row.f.share_db, 2)}</td></tr>
								{/each}
							</tbody>
						</table>
					</div>
				{/if}
				{#each attackDeltas as row (row.name)}
					<p>Attacks ({human(row.name)}): energy {signed(row.f.energy_db_matched, 3)} dB matched over n = {String(row.f.pairs ?? 'unknown')} pairs; centroid {signed(row.f.centroid_hz, 1)} Hz over n = {String(row.f.centroid_pairs ?? 'unknown')} pairs.</p>
				{/each}
			</div>
		{/if}

		<details class="vu-panel card p-4 text-sm">
			<summary>tone_ab claims and limitations (verbatim)</summary>
			{#each ['measurements', 'inferences', 'listening'] as group (group)}
				<p class="mt-2 vu-eyebrow">{group}</p>
				{#if arr(claims[group]).length === 0}<p class="vu-muted">none recorded</p>{/if}
				<ul class="list-disc pl-5">{#each arr(claims[group]) as text, index (index)}<li>{String(text)}</li>{/each}</ul>
			{/each}
			<p class="mt-2 vu-eyebrow">limitations</p>
			<ul class="list-disc pl-5">{#each arr(doc.limitations) as text, index (index)}<li>{String(text)}</li>{/each}</ul>
		</details>
	</section>
{/if}
