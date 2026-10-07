// Source overview `/sources/[id]` (WEB_TESTS_S3.md 5.2): probe summary, runs and jobs from fixtures; unknowns visible.
import { expect, expectNoForbiddenText, fixture, ids, open, record, test } from '../tests/e2e-support';

type RunRow = { run_id: string; role: string; pcm: { sample_rate?: number; channels?: number; duration_seconds?: number } };
type JobRow = { job_id: string; state: string; tool?: string };

for (const alias of ['reviewed', 'plain'] as const) {
	test(`${alias} source: probe summary, bound runs, reviews and jobs render from the fixtures`, async ({ page, mock }) => {
		const sourceId = ids[`source_${alias}`];
		const runs = fixture<{ runs: RunRow[] }>(`source_runs_${alias}.json`).runs;
		const jobs = fixture<{ jobs: JobRow[] }>(`jobs_${alias}.json`).jobs;
		const reviews = fixture<{ reviews: Array<{ review_id: string }> }>(`reviews_${alias}.json`).reviews;
		await open(page, `/sources/${sourceId}`);
		await expect(page.getByRole('heading', { level: 1 })).toHaveText(sourceId);
		await expect(page.locator('main#main')).toBeVisible();

		// Probe summary: values of the first listed baseline run, as the page states.
		const baseline = runs.find((run) => run.role === 'baseline');
		expect(baseline, 'fixture has a baseline run').toBeDefined();
		const probe = page.locator('[data-probe-summary="true"] dd');
		await expect(probe.nth(0)).toHaveText((baseline!.pcm.duration_seconds as number).toFixed(3));
		await expect(probe.nth(1)).toHaveText(String(baseline!.pcm.sample_rate));
		await expect(probe.nth(2)).toHaveText(String(baseline!.pcm.channels));

		await expect(page.locator('[data-bound-runs="true"] tr[data-run]')).toHaveCount(runs.length);
		for (const run of runs) await expect(page.locator(`[data-bound-runs="true"] tr[data-run="${run.run_id}"]`)).toHaveCount(1);

		await expect(page.locator('[data-capture-reviews="true"] li[data-review]')).toHaveCount(reviews.length);
		if (reviews.length === 0) await expect(page.locator('[data-capture-reviews="true"]')).toContainText('Nothing is created automatically.');

		const rows = page.locator('[data-iterate="true"] [data-job-row]');
		await expect(rows).toHaveCount(jobs.length);
		for (const job of jobs) {
			const row = page.locator(`[data-job-row="${job.job_id}"]`);
			await expect(row).toHaveAttribute('data-job-tool', job.tool ?? 'share_export');
			await expect(row.locator('[data-job-state]').first()).toHaveAttribute('data-job-state', job.state);
		}
		if (jobs.length === 0) await expect(page.locator('[data-jobs-empty="true"]')).toBeVisible();
		await expectNoForbiddenText(page);
		expect(await mock.nonGet()).toEqual([]);
		record('source', `${alias}_sections`, { runs: runs.length, jobs: jobs.length, reviews: reviews.length });
	});
}

test('unknown fields are visible as Unknown with their reasons on the plain source', async ({ page }) => {
	const source = fixture<{ sources: Array<{ source_artifact_id: string; source_id: string | null; source_id_reason: string; duration_seconds: number | null; duration_seconds_reason: string }> }>('sources.json').sources.find((item) => item.source_artifact_id === ids.source_plain)!;
	expect(source.source_id).toBeNull();
	expect(source.duration_seconds).toBeNull();
	await open(page, `/sources/${ids.source_plain}`);
	const facts = page.locator('[data-source-facts="true"]');
	const sourceIdCell = facts.locator('dd').nth(3);
	await expect(sourceIdCell.locator('[data-unknown="true"]')).toHaveText('Unknown');
	await expect(sourceIdCell.locator('[data-unknown-reason="true"]')).toContainText(source.source_id_reason);
	const extentCell = facts.locator('dd').nth(4);
	await expect(extentCell.locator('[data-unknown="true"]')).toHaveText('Unknown');
	await expect(extentCell.locator('[data-unknown-reason="true"]')).toContainText(source.duration_seconds_reason);
	// No annotation clock exists for a source without a succeeded share preview: a typed state and no note form.
	const annotate = page.locator('[data-annotate="true"]');
	await expect(annotate.locator('[data-annotation-state="unavailable"] [data-upstream-code="annotation_source_clock_unknown"]')).toBeVisible();
	await expect(annotate.locator('[data-annotation-form="true"]')).toHaveCount(0);
	await expect(annotate).toContainText('Source clock unknown');
});

test('processing jobs on the reviewed source state that nothing is adopted or listening-accepted', async ({ page }) => {
	await open(page, `/sources/${ids.source_reviewed}`);
	for (const name of ['denoise_succeeded', 'capture_profile_succeeded', 'apply_succeeded'] as const) {
		const row = page.locator(`[data-job-row="${ids.jobs[name]}"]`);
		await expect(row).toContainText('master adopted: false');
		await expect(row).toContainText('listening acceptance: not performed');
	}
	// The operator note saved in the fixture is labelled as the operator's, apart from detector hypotheses.
	const operator = page.locator('[data-track="operator"] li[data-claim-label]');
	await expect(operator).toHaveCount(1);
	await expect(operator).toHaveAttribute('data-claim-label', 'USER REPORTED');
	await expect(page.locator('[data-track="detector"] [data-detector-empty="true"]')).toContainText('This is not an empty pass.');
	await expect(page.locator('[data-player-clock-verified="false"]')).toHaveText('no');
});

test('typing into the share-preview knob inputs and submitting never throws (X6)', async ({ page, mock, problems }) => {
	problems.expectConsoleError(/\[\/api\/jobs\]/, 'the browser logs the typed refusal the mock replays for every job submission');
	await open(page, `/sources/${ids.source_reviewed}`);
	const form = page.locator('[data-process-form="share_export"]');
	const knobs = form.locator('input[type="number"]');
	const count = await knobs.count();
	expect(count).toBeGreaterThan(0);
	for (let index = 0; index < count; index += 1) {
		await knobs.nth(index).click();
		await knobs.nth(index).pressSequentially('60');
		await expect(knobs.nth(index)).toHaveValue('60');
	}
	// Submitting reads every typed knob; the mock answers with its recorded typed refusal, which the form shows.
	await form.getByRole('button', { name: 'Submit share preview job' }).click();
	await expect(form.locator('[data-upstream-code]')).toBeVisible();
	const log = await mock.log();
	expect(log.job_submissions).toBe(1);
	expect(problems.seen()).toEqual([]);
	record('source', 'X6_process_form_number_inputs', { typed_without_page_error: 1, of: 1, knob_fields_typed: count, inputs: ['ProcessForm'] });
});

test('typing a span length and adding a note never throws (X6)', async ({ page, mock, problems }) => {
	problems.expectConsoleError(/\[\/api\/sources\/art_[0-9a-f]{32}\/annotations\]/, 'the mock replays no annotation write, so the BFF answers with a typed error the browser logs');
	await open(page, `/sources/${ids.source_reviewed}`);
	const form = page.locator('[data-annotation-form="true"]');
	await expect(form).toBeVisible();
	const length = form.locator('input[type="number"]');
	await expect(length).toHaveCount(1);
	await length.click();
	await length.pressSequentially('0.5');
	await expect(length).toHaveValue('0.5');
	await form.locator('textarea').fill('e2e synthetic note');
	await form.getByRole('button', { name: 'Add note at current time' }).click();
	// The save handler read the typed length and reached the BFF: one write attempt arrived upstream.
	await expect.poll(async () => (await mock.nonGet()).length).toBe(1);
	expect((await mock.nonGet())[0].path).toBe(`/api/v1/sources/${ids.source_reviewed}/annotations`);
	expect(problems.seen()).toEqual([]);
	record('source', 'X6_annotation_number_input', { typed_without_page_error: 1, of: 1, inputs: ['AnnotationPanel'] });
});
