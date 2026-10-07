// Run graph, compare, review and deliver pages plus the three run pickers (WEB_TESTS_S3.md 5.2).
// Everything rendered here comes from synthetic fixtures; no listening, tone or musical claim follows from it.
import { expect, expectNoForbiddenText, fixture, ids, open, record, test } from '../tests/e2e-support';

type RunSummary = { run_id: string; run_status: string | null };
const runs = fixture<{ runs: RunSummary[] }>('runs_list.json').runs;
const graph = fixture<{ listening_acceptance: { value: string; scope: string | null }; stages: Array<{ stage: string }>; evidence: Array<{ evidence_id: string; kind: string; state: string; files: Array<{ name: string; import_verified: boolean | null }> }>; unknown_fields: Record<string, { value: unknown; reason: string | null }> }>('run_run_s3.json');
const run = `/runs/${ids.run_main}`;

test('/runs lists every fixture run with its four links', async ({ page, mock }) => {
	await open(page, '/runs');
	await expect(page.getByRole('heading', { level: 1, name: 'Processed runs' })).toBeVisible();
	await expect(page.locator('main#main')).toBeVisible();
	await expect(page.locator('tr[data-run-id]')).toHaveCount(runs.length);
	const row = page.locator(`tr[data-run-id="${ids.run_main}"]`);
	for (const name of ['Graph', 'Review', 'Compare', 'Deliver']) await expect(row.getByRole('link', { name, exact: true })).toHaveCount(1);
	expect(await mock.nonGet()).toEqual([]);
});

test('/runs/[id] renders the graph, the recorded processing flags and all 33 unknown fields', async ({ page }) => {
	await open(page, run);
	await expect(page.locator('main#main [data-run-graph="true"]')).toBeVisible();
	await expect(page.getByRole('heading', { level: 1 })).toHaveText(ids.run_main);
	await expect(page.locator('tr[data-stage]')).toHaveCount(graph.stages.length);
	await expect(page.locator('[data-evidence="true"] li[data-evidence-id]')).toHaveCount(graph.evidence.length);
	// The synthetic manifest records no high-pass and no hum notch, and keeps the ~32 Hz fundamental.
	const processing = page.locator('[data-processing="true"]');
	await expect(processing.locator('[data-high-pass="false"]')).toHaveText('No high-pass (manifest: high_pass_applied false)');
	await expect(processing.locator('[data-hum-notch="false"]')).toHaveText('No hum notch (manifest: hum_notches_applied false)');
	await expect(processing).toContainText('Intentional low fundamental: 32 Hz');
	const unknowns = page.locator('[data-unknowns-block="true"]');
	await expect(unknowns).toHaveAttribute('data-unknown-count', '33');
	await unknowns.locator('summary').click();
	await expect(unknowns.locator('dt[data-unknown-key]')).toHaveCount(Object.keys(graph.unknown_fields).length);
	for (const key of ['bpm', 'missed_or_extra_notes', 'listening_acceptance', 'fundamental_32hz_presence', 'editor_import']) {
		await expect(unknowns.locator(`dt[data-unknown-key="${key}"]`)).toHaveCount(1);
	}
	// The acceptance state shown is the fixture's own record (a synthetic receipt), with its scope verbatim.
	await expect(page.locator('[data-listening-acceptance]')).toHaveAttribute('data-listening-acceptance', graph.listening_acceptance.value);
	if (graph.listening_acceptance.scope) await expect(page.locator('[data-run-graph="true"] [data-acceptance-scope="true"]')).toContainText(graph.listening_acceptance.scope);
	await expect(page.locator('[data-run-graph="true"]')).toContainText('note-level comparison not assessed no approved reference');
	await expectNoForbiddenText(page);
});

test('/runs/[id]/compare shows operator_preference as not recorded and offers no way to record one', async ({ page, mock }) => {
	await open(page, `${run}/compare`);
	await expect(page.locator('main#main [data-compare-page="true"]')).toBeVisible();
	await expect(page.getByRole('heading', { level: 1 })).toContainText(ids.run_main);
	const preference = page.locator('[data-operator-preference="not recorded"]');
	await expect(preference).toBeVisible();
	await expect(preference).toContainText('operator_preference: not recorded');
	await expect(page.locator('[data-ab="true"] [data-arms="true"] tr[data-arm]')).toHaveCount(2);
	await expect(page.locator('[data-mapping="hidden"]')).toBeVisible();
	const controls = await page.locator('main').locator('button, input, select, textarea').evaluateAll((elements) => elements.map((element) => `${element.getAttribute('name') ?? ''} ${element.getAttribute('aria-label') ?? ''} ${element.textContent ?? ''}`));
	for (const control of controls) expect(control).not.toMatch(/prefer|choose (x|y)|i like|better/i);
	// Revealing the blind mapping is a local display toggle: it sends nothing.
	await page.getByRole('button', { name: 'Reveal which is FULLER' }).click();
	await expect(page.locator('[data-mapping="revealed"]')).toContainText('not saved, not a preference');
	expect(await mock.nonGet()).toEqual([]);
});

test('/runs/[id]/review shows user-reported and detector items with distinct labels and shapes', async ({ page, mock }) => {
	await open(page, `${run}/review`);
	await expect(page.locator('main#main [data-review-page="true"]')).toBeVisible();
	await expect(page.getByRole('heading', { level: 1 })).toContainText(ids.run_main);
	await expect(page.locator('[data-review-workspace="true"]')).toBeVisible();
	await expect(page.locator('[data-clock-alignment="unverified"]')).toContainText('alignment unverified');
	// BPM is unknown in the fixture and is shown as unknown, not as a number.
	await expect(page.locator('[data-overlay="bpm"]')).toHaveText('BPM unknown');

	// Markers tab (default): the detector flag, labelled as a hypothesis.
	const detector = page.locator('[data-flags="true"] li[data-flag-id="flag-1"] [data-basis="detector"]');
	await expect(detector).toBeVisible();
	await expect(detector).toContainText('DETECTOR HYPOTHESIS');
	const timing = page.locator('[data-timing="true"]');
	await expect(timing.locator('tr[data-timing-row="span-0"] td[data-direction]')).toHaveText('direction withheld (uncalibrated)');
	await expect(timing.locator('tr[data-timing-row="span-1"]')).toHaveAttribute('data-measured', 'false');
	await expect(timing.locator('tr[data-timing-row="span-1"] td[data-direction]')).toContainText('— abstained:');
	const detectorShape = await detector.getAttribute('data-shape');

	// Notes tab: the operator's saved note, labelled as theirs.
	await page.getByRole('tab', { name: 'Notes' }).click();
	const note = page.locator('[data-saved-notes="true"] li[data-claim-label="USER REPORTED"]');
	await expect(note).toHaveCount(1);
	const user = note.locator('[data-basis="operator_assertion"]');
	await expect(user).toContainText('USER REPORTED');
	const userShape = await user.getAttribute('data-shape');
	expect(userShape).toBe('solid');
	expect(detectorShape).toBe('dotted');
	expect(userShape).not.toBe(detectorShape);
	await expect(page.locator('[data-tab="notes"]')).toContainText('musical verdict not established');
	// The two kinds never share a label anywhere on the page.
	await expect(page.locator('[data-basis="detector"]', { hasText: 'USER REPORTED' })).toHaveCount(0);
	await expect(page.locator('[data-basis="operator_assertion"]', { hasText: 'DETECTOR' })).toHaveCount(0);
	await expect(page.locator('[data-review-page="true"]')).toContainText('None of them is a note-correctness or phrase verdict.');
	expect(await mock.nonGet()).toEqual([]);
	await expectNoForbiddenText(page);
	record('runs', 'review_labels', { user_reported_items: 1, detector_items: 1, shapes: { user: userShape, detector: detectorShape } });
});

test('/runs/[id]/deliver shows editor-import files as import unverified', async ({ page }) => {
	const markers = graph.evidence.filter((item) => item.kind === 'editor_marker_export' && item.state === 'current').flatMap((item) => item.files);
	const unverified = markers.filter((file) => file.import_verified === false);
	expect(unverified.length).toBeGreaterThan(0);
	await open(page, `${run}/deliver`);
	await expect(page.locator('main#main [data-deliver-page="true"]')).toBeVisible();
	await expect(page.getByRole('heading', { level: 1 })).toContainText(ids.run_main);
	await expect(page.locator('tr[data-deliverable="marker-file"]')).toHaveCount(markers.length);
	const rows = page.locator('tr[data-deliverable="marker-file"][data-import-verified="false"]');
	await expect(rows).toHaveCount(unverified.length);
	await expect(rows.first().locator('[data-import-unverified="true"]')).toHaveText('import unverified (no editor application proof)');
	await expect(page.locator('tr[data-deliverable="marker-file"][data-import-verified="true"]')).toHaveCount(0);
	await expect(page.locator('tr[data-deliverable="share-mp4"]')).toContainText('low-register preservation not claimed');
	await expect(page.locator('[data-deliver-page="true"]')).toContainText('Nothing here adopts a master.');
	record('runs', 'deliver_import_unverified', { marker_files: markers.length, import_unverified: unverified.length });
});

test('a run with no bound evidence still renders review, compare and deliver without a crash', async ({ page }) => {
	const other = `/runs/${ids.run_other}`;
	await open(page, `${other}/review`);
	await expect(page.locator('[data-review-workspace="true"]')).toBeVisible();
	await expect(page.locator('[data-player="none"]')).toBeVisible();
	await expect(page.locator('[data-mark-disabled]').first()).toBeVisible();
	await open(page, `${other}/compare`);
	await expect(page.locator('[data-ab-unavailable]')).toBeVisible();
	await open(page, `${other}/deliver`);
	await expect(page.locator('[data-markers-none="true"]')).toBeVisible();
});

for (const [path, picker] of [['/compare', 'compare'], ['/review', 'review'], ['/download', 'deliver']] as const) {
	test(`the ${path} run picker renders a run list instead of redirecting`, async ({ page }) => {
		expect(runs.length).toBeGreaterThanOrEqual(2);
		await open(page, path);
		await expect(page).toHaveURL(new RegExp(`${path}$`));
		const section = page.locator(`[data-run-picker="${picker}"]`);
		await expect(section.getByRole('heading', { level: 1, name: 'Choose a run' })).toBeVisible();
		await expect(section.locator('li a')).toHaveCount(runs.length);
		await expect(section.locator(`a[href="/runs/${ids.run_main}/${picker}"]`)).toHaveCount(1);
		await expect(page.locator('main form, main input')).toHaveCount(0);
	});
}
