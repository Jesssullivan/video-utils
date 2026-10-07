// Jobs index and job detail (WEB_TESTS_S3.md 5.2).
import { expect, expectNoForbiddenText, fixture, ids, open, record, test } from '../tests/e2e-support';

type JobRow = { job_id: string; state: string; tool?: string };
type Job = { job_id: string; state: string; tool: string; progress: { completed: number; denominator: number } | null; artifacts: unknown[]; eta_seconds_reason: string };
const jobs = fixture<{ jobs: JobRow[] }>('jobs_all.json').jobs;

test('/jobs lists every fixture job with its state badge and tool', async ({ page, mock }) => {
	await open(page, '/jobs');
	await expect(page.locator('main#main [data-jobs-page="true"]')).toBeVisible();
	await expect(page.getByRole('heading', { level: 1, name: 'All jobs' })).toBeVisible();
	await expect(page.locator('tr[data-job-id]')).toHaveCount(jobs.length);
	const states = new Set<string>();
	for (const job of jobs) {
		const row = page.locator(`tr[data-job-id="${job.job_id}"]`);
		await expect(row.locator('[data-job-state]')).toHaveAttribute('data-job-state', job.state);
		await expect(row.locator('[data-job-state]')).toHaveText(job.state);
		await expect(row.locator('td').nth(2)).toHaveText(job.tool ?? 'share_export');
		states.add(job.state);
	}
	expect([...states].sort()).toEqual(['failed', 'queued', 'running', 'succeeded']);
	expect(await mock.nonGet()).toEqual([]);
	record('jobs', 'index', { listed: jobs.length, states: [...states].sort() });
});

for (const name of ['share_queued', 'share_running', 'share_succeeded', 'share_failed'] as const) {
	test(`/jobs/[id] renders the ${name.replace('share_', '')} fixture`, async ({ page, mock }) => {
		const job = fixture<Job>(`job_${name}.json`);
		expect(job.job_id).toBe(ids.jobs[name]);
		await open(page, `/jobs/${job.job_id}`);
		await expect(page.getByRole('heading', { level: 1 })).toHaveText(job.job_id);
		const facts = page.locator('[data-job-facts="true"]');
		await expect(facts.locator('[data-job-state]')).toHaveAttribute('data-job-state', job.state);
		// ETA is never estimated: Unknown with the control API's reason.
		await expect(facts.locator('[data-eta="unknown"]')).toHaveText('Unknown');
		await expect(facts).toContainText(job.eta_seconds_reason);
		if (job.progress) await expect(facts.locator('[data-progress="reported"]')).toHaveText(`${job.progress.completed} / ${job.progress.denominator} lifecycle steps`);
		else await expect(facts.locator('[data-progress="unknown"]')).toHaveText('Unknown');
		const actions = page.locator('[data-job-actions="true"]');
		await expect(actions.getByRole('button', { name: 'Cancel job' })).toHaveCount(job.state === 'queued' || job.state === 'running' ? 1 : 0);
		await expect(actions.getByRole('button', { name: /Retry/ })).toHaveCount(job.state === 'failed' ? 1 : 0);
		await expect(page.locator('[data-download="true"] tr[data-artifact-id]')).toHaveCount(job.artifacts.length);
		if (job.artifacts.length === 0) await expect(page.locator('[data-artifacts="none"]')).toBeVisible();
		await expectNoForbiddenText(page);
		// Viewing a job never cancels, retries or submits anything.
		expect(await mock.nonGet()).toEqual([]);
	});
}

test('/jobs/[id] renders a processing job with its run and the process-page link', async ({ page }) => {
	const job = fixture<Job & { run_id?: string | null }>('job_denoise_succeeded.json');
	await open(page, `/jobs/${job.job_id}`);
	const facts = page.locator('[data-job-facts="true"]');
	await expect(facts.locator('[data-job-state]')).toHaveAttribute('data-job-state', 'succeeded');
	await expect(facts).toContainText('denoise');
	if (job.run_id) await expect(facts).toContainText(job.run_id);
	await expect(page.locator('[data-job-actions="true"] [data-process-link="true"]')).toHaveAttribute('href', `/sources/${ids.source_reviewed}/process`);
});

test('a closed-schema-violating job renders the typed decode error and no partial data', async ({ page, mock, problems }) => {
	problems.expectConsoleError(/\[\/api\/jobs\/job_f{31}1\]/, 'the job page polls the BFF, which answers the same typed 502 decode error');
	const bad = fixture<Record<string, unknown>>('job_bad_unknown_key.json');
	expect(bad.job_id).toBe(ids.jobs.bad_unknown_key);
	expect(Object.keys(bad)).toContain('upstream_unexpected_field_e2e');
	await open(page, `/jobs/${ids.jobs.bad_unknown_key}`);
	const error = page.locator('[data-error-code="control_api_decode_error"]').first();
	await expect(error).toBeVisible();
	await expect(error.locator('code').first()).toHaveText('control_api_decode_error');
	// The error names only a sanitized path: the unknown key and its value are never echoed.
	await expect(error).toContainText('<unexpected_key>');
	await expect(page.locator('[data-job-facts="true"]')).toHaveCount(0);
	await expect(page.locator('[data-job-state]')).toHaveCount(0);
	await expect(page.locator('[data-attempts="true"]')).toHaveCount(0);
	await expectNoForbiddenText(page);
	expect(await mock.nonGet()).toEqual([]);
	record('jobs', 'closed_schema_violation', { rendered: 'control_api_decode_error', partial_data_rendered: false });
});

test('an id that is not a job id is a 404 before any control API request', async ({ page, mock, problems }) => {
	problems.expectConsoleError(/\[\/jobs\/not-a-job\]/, 'the browser logs the 404 document');
	const response = await page.goto('/jobs/not-a-job');
	expect(response?.status()).toBe(404);
	expect((await mock.log()).requests).toEqual([]);
});
