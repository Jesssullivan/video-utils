// Capture review never auto-confirms the first five seconds (WEB_TESTS_S3.md 5.2; metric W9).
// The setup-interval rule itself belongs to the control API: the mock replays its recorded 422
// `setup_interval_unacknowledged` whenever the forwarded body is not explicitly acknowledged. What is
// asserted here is the page: loads write nothing, nothing is prefilled or pre-checked, and the page
// forwards an acknowledgement only after the operator ticks the control.
import type { Page } from '@playwright/test';
import { expect, expectNoForbiddenText, ids, open, record, test } from '../tests/e2e-support';

const BASE = `/sources/${ids.source_plain}/capture`;
const WITH_RUN = `${BASE}?run=${ids.baseline_plain}`;

// The interval inputs are number inputs whose state stays text (WEB_FIXES_S3 F1): typing never throws and the setup
// warning follows the typed start at once. No console-error tolerance is declared for it anywhere in this file.
test('loading and reloading the page writes nothing and proposes no interval', async ({ page, mock }) => {
	let loads = 0;
	for (const path of [BASE, WITH_RUN]) {
		await open(page, path);
		loads += 1;
		await page.reload({ waitUntil: 'networkidle' });
		loads += 1;
		await expect(page.locator('[data-capture-page="true"]')).toBeVisible();
		const picker = page.locator('[data-interval-picker="true"]');
		await expect(picker).toHaveAttribute('data-interval-empty', 'true');
		await expect(picker.locator('[data-no-prefill="true"]')).toBeVisible();
		await expect(page.locator('input[name="start_seconds"]')).toHaveValue('');
		await expect(page.locator('input[name="end_seconds"]')).toHaveValue('');
		await expect(page.locator('input[name="setup_interval_acknowledged"]')).not.toBeChecked();
		await expect(page.locator('select[name="review_status"]')).toHaveValue('');
		await expect(page.locator('select[name="authorization_scope"]')).toHaveValue('');
		await expect(page.locator('textarea[name="note"]')).toHaveValue('');
		await expect(page.locator('[data-setup-warning="true"]')).toHaveCount(0);
		await expect(page.locator('[data-review-saved]')).toHaveCount(0);
	}
	const log = await mock.log();
	expect(log.requests.filter((entry) => entry.non_get)).toEqual([]);
	expect(log.review_records).toBe(0);
	expect(log.requests.length).toBeGreaterThan(0);
	// Without a chosen baseline run nothing can be measured or saved.
	await open(page, BASE);
	await expect(page.getByRole('button', { name: /Save review/ })).toBeDisabled();
	await expect(page.getByRole('button', { name: /Measure interval/ })).toBeDisabled();
	record('capture', 'W9_no_auto_confirm', { page_loads: loads, non_get_requests: 0, review_records: log.review_records });
});

test('typing an interval inside the first five seconds shows the setup warning at once, without a page error', async ({ page }) => {
	await open(page, WITH_RUN);
	await page.locator('input[name="start_seconds"]').fill('1');
	await page.locator('input[name="end_seconds"]').fill('2');
	await expect(page.locator('[data-setup-warning="true"]')).toBeVisible({ timeout: 3000 });
	await expect(page.locator('select[name="review_status"] option[value="reviewed_candidate"]')).toHaveJSProperty('disabled', true);
});

async function enterSetupInterval(page: Page): Promise<void> {
	await open(page, WITH_RUN);
	await expect(page.locator('[data-native-timeline="true"]')).toBeVisible();
	await page.locator('input[name="start_seconds"]').fill('1');
	await page.locator('input[name="end_seconds"]').fill('2');
	await page.locator('select[name="review_status"]').selectOption('reviewed_possible_contamination');
	await page.locator('select[name="authorization_scope"]').selectOption('profile_authoring');
	await page.locator('textarea[name="note"]').fill('e2e synthetic note');
}

test('an interval inside the first five seconds cannot be saved without the explicit acknowledgement', async ({ page, mock, problems }) => {
	problems.expectConsoleError(/\[\/sources\/art_[0-9a-f]{32}\/capture\?\/save&run=[A-Za-z0-9_.-]+\]/, 'the browser logs the typed 422 answer to the refused form post');
	await enterSetupInterval(page);
	const acknowledge = page.locator('input[name="setup_interval_acknowledged"]');
	await expect(acknowledge).not.toBeChecked();
	await page.getByRole('button', { name: /Save review/ }).click();

	const refusal = page.locator('[data-refusal-code="setup_interval_unacknowledged"]');
	await expect(refusal).toBeVisible();
	await expect(refusal).toContainText('Acknowledge it explicitly.');
	await expect(page.locator('[data-review-saved]')).toHaveCount(0);
	const log = await mock.log();
	const posts = log.requests.filter((entry) => entry.non_get);
	expect(posts.length).toBe(1);
	expect(posts[0]).toMatchObject({ method: 'POST', path: `/api/v1/sources/${ids.source_plain}/capture-reviews`, status: 422, file: 'review_refused_setup.json' });
	// The page forwarded exactly what the operator entered: no acknowledgement was added on their behalf.
	expect(posts[0].review_request).toEqual({ start_seconds: 1, setup_interval_acknowledged: false, review_status: 'reviewed_possible_contamination' });
	expect(log.review_records).toBe(0);
	await expectNoForbiddenText(page);

	// After the refusal the operator's values are echoed back as text: the warning renders, the clean status is not
	// selectable, and the control is still unticked.
	await expect(page.locator('input[name="start_seconds"]')).toHaveValue('1');
	await expect(page.locator('[data-setup-warning="true"]')).toBeVisible();
	await expect(page.locator('[data-setup-warning="true"]')).toContainText('never');
	await expect(page.locator('select[name="review_status"] option[value="reviewed_candidate"]')).toHaveJSProperty('disabled', true);
	await expect(acknowledge).not.toBeChecked();
	record('capture', 'setup_interval_refused', { refused_without_acknowledgement: 1, review_records: log.review_records, acknowledgements_added_by_page: 0 });
});

test('the same interval saves once the operator ticks the acknowledgement themselves', async ({ page, mock }) => {
	await enterSetupInterval(page);
	const acknowledge = page.locator('input[name="setup_interval_acknowledged"]');
	await expect(acknowledge).not.toBeChecked();
	await acknowledge.check();
	await page.getByRole('button', { name: /Save review/ }).click();
	const saved = page.locator('[data-review-saved]');
	await expect(saved).toBeVisible();
	await expect(saved).toContainText('Not verified noise-only.');
	await expect(saved).toContainText('reviewed_possible_contamination');
	const log = await mock.log();
	const posts = log.requests.filter((entry) => entry.non_get);
	expect(posts.length).toBe(1);
	expect(posts[0].review_request).toEqual({ start_seconds: 1, setup_interval_acknowledged: true, review_status: 'reviewed_possible_contamination' });
	expect(log.review_records).toBe(1);
	record('capture', 'setup_interval_saved', { saved_after_explicit_acknowledgement: 1, review_records: log.review_records });
});

// X5: every typed case, keyed in through the keyboard as an operator would. `expected` is null where the browser decides
// what a partial entry's value is; the warning must then agree with the value the input itself reports.
const TYPING_CASES: ReadonlyArray<{ name: string; field: 'start_seconds' | 'end_seconds'; keys: string; erase?: number; warning: boolean | null }> = [
	{ name: 'start 0', field: 'start_seconds', keys: '0', warning: true },
	{ name: 'start 1', field: 'start_seconds', keys: '1', warning: true },
	{ name: 'start 4.999', field: 'start_seconds', keys: '4.999', warning: true },
	{ name: 'start 5', field: 'start_seconds', keys: '5', warning: false },
	{ name: 'start 5.5', field: 'start_seconds', keys: '5.5', warning: false },
	{ name: 'start partial "-"', field: 'start_seconds', keys: '-', warning: null },
	{ name: 'start partial "1."', field: 'start_seconds', keys: '1.', warning: null },
	{ name: 'start typed then cleared', field: 'start_seconds', keys: '1', erase: 1, warning: false },
	{ name: 'end only', field: 'end_seconds', keys: '2', warning: false }
];

test('typing any interval value never throws; the setup warning follows the typed start at once', async ({ page, mock, problems }) => {
	const outcome = { cases: TYPING_CASES.length, without_page_error: 0, inside_cases: 0, inside_warned: 0, outside_cases: 0, outside_silent: 0, partial_cases: 0, partial_consistent: 0, observed: [] as Array<{ name: string; value: string; warning: boolean }> };
	for (const item of TYPING_CASES) {
		await open(page, WITH_RUN);
		const before = problems.seen().length;
		const input = page.locator(`input[name="${item.field}"]`);
		await input.click();
		await input.pressSequentially(item.keys);
		for (let index = 0; index < (item.erase ?? 0); index += 1) await input.press('Backspace');
		const warning = page.locator('[data-setup-warning="true"]');
		const clean = page.locator('select[name="review_status"] option[value="reviewed_candidate"]');
		if (item.warning === true) {
			await expect(warning, item.name).toBeVisible({ timeout: 3000 });
			await expect(clean, item.name).toHaveJSProperty('disabled', true);
			outcome.inside_cases += 1;
			outcome.inside_warned += 1;
		} else if (item.warning === false) {
			await expect(warning, item.name).toHaveCount(0);
			await expect(clean, item.name).toHaveJSProperty('disabled', false);
			outcome.outside_cases += 1;
			outcome.outside_silent += 1;
		}
		// The warning always agrees with the text the start input reports (a partial entry may report an empty value).
		const start = await page.locator('input[name="start_seconds"]').inputValue();
		const shown = (await warning.count()) === 1;
		expect(shown, `${item.name}: warning agrees with the reported start value "${start}"`).toBe(start.trim() !== '' && Number(start) < 5);
		expect(await clean.evaluate((option: HTMLOptionElement) => option.disabled), item.name).toBe(shown);
		if (item.warning === null) {
			outcome.partial_cases += 1;
			outcome.partial_consistent += 1;
		}
		await expect(page.locator('[data-interval-picker="true"]')).toHaveAttribute('data-interval-empty', (await input.inputValue()) === '' ? 'true' : 'false');
		// The acknowledgement is never ticked for the operator, whatever is typed.
		await expect(page.locator('input[name="setup_interval_acknowledged"]')).not.toBeChecked();
		expect(problems.seen().slice(before), item.name).toEqual([]);
		outcome.without_page_error += 1;
		outcome.observed.push({ name: item.name, value: start, warning: shown });
	}
	expect((await mock.log()).requests.filter((entry) => entry.non_get)).toEqual([]);
	record('capture', 'X5_typed_interval', outcome);
});

// X7 (WEB_FIXES_S3 F2): each form action keeps the chosen baseline run, so Measure and Save stay enabled and the typed
// interval is kept. The run is still chosen by the load from the eligible baseline list only.
async function expectRunKept(page: Page, runId: string): Promise<void> {
	await expect(page.locator('select[name="run"]')).toHaveValue(runId, { timeout: 3000 });
	await expect(page.locator('input[name="run_id"]')).toHaveValue(runId);
	await expect(page.locator('[data-native-timeline="true"]')).toBeVisible();
	await expect(page.getByRole('button', { name: /Save review/ })).toBeEnabled({ timeout: 3000 });
	await expect(page.getByRole('button', { name: /Measure interval/ })).toBeEnabled();
}

test('after a form action the chosen baseline run is still selected, so the operator can continue', async ({ page }) => {
	await open(page, WITH_RUN);
	await page.locator('input[name="start_seconds"]').fill('5.5');
	await page.locator('input[name="end_seconds"]').fill('6.4');
	await page.getByRole('button', { name: /Measure interval/ }).click();
	await expect(page.locator('[data-measurement="true"]')).toBeVisible();
	await expectRunKept(page, ids.baseline_plain);
	await expect(page.locator('input[name="start_seconds"]')).toHaveValue('5.5');
	await expect(page.locator('input[name="end_seconds"]')).toHaveValue('6.4');
	// The operator can go straight on to a second action without choosing the run again.
	await page.getByRole('button', { name: /Measure interval/ }).click();
	await expect(page.locator('[data-measurement="true"]')).toBeVisible();
	await expectRunKept(page, ids.baseline_plain);
	record('capture', 'X7_run_kept_after_measure', { kept: 1, of: 1 });
});

test('the run stays selected after a refused save and after an accepted save', async ({ page, mock, problems }) => {
	problems.expectConsoleError(/\[\/sources\/art_[0-9a-f]{32}\/capture\?\/save&run=[A-Za-z0-9_.-]+\]/, 'the browser logs the typed 422 answer to the refused form post');
	await enterSetupInterval(page);
	await page.getByRole('button', { name: /Save review/ }).click();
	await expect(page.locator('[data-refusal-code="setup_interval_unacknowledged"]')).toBeVisible();
	await expectRunKept(page, ids.baseline_plain);
	await expect(page.locator('input[name="start_seconds"]')).toHaveValue('1');
	await expect(page.locator('input[name="end_seconds"]')).toHaveValue('2');
	// Still not acknowledged by the page; the operator ticks it and saves from the same page.
	const acknowledge = page.locator('input[name="setup_interval_acknowledged"]');
	await expect(acknowledge).not.toBeChecked();
	await acknowledge.check();
	await page.getByRole('button', { name: /Save review/ }).click();
	await expect(page.locator('[data-review-saved]')).toBeVisible();
	await expectRunKept(page, ids.baseline_plain);
	const posts = (await mock.log()).requests.filter((entry) => entry.non_get);
	expect(posts.map((entry) => entry.status)).toEqual([422, 201]);
	expect(posts.map((entry) => entry.review_request?.setup_interval_acknowledged)).toEqual([false, true]);
	record('capture', 'X7_run_kept_after_save', { kept: 2, of: 2, actions: ['save refused 422', 'save accepted'] });
});

test('the run stays selected after the author action', async ({ page, mock, problems }) => {
	problems.expectConsoleError(/\[\/sources\/art_[0-9a-f]{32}\/capture\?\/author&run=[A-Za-z0-9_.-]+\]/, 'the browser logs the typed refusal the mock replays for every job submission');
	const runId = ids.baseline_reviewed;
	await open(page, `/sources/${ids.source_reviewed}/capture?run=${runId}`);
	const author = page.locator(`[data-review-row="${ids.review_reviewed}"]`).getByRole('button', { name: 'Author FULLER profile' });
	await expect(author).toBeEnabled();
	await author.click();
	await expect(page.locator('[data-saved-reviews="true"] [data-refusal-code]')).toBeVisible();
	await expectRunKept(page, runId);
	expect((await mock.log()).job_submissions).toBe(1);
	record('capture', 'X7_run_kept_after_author', { kept: 1, of: 1, author_answer: 'typed refusal replayed by the mock' });
});

test('a run id that is malformed, unlisted or bound to another source selects nothing, before or after an action', async ({ page, mock }) => {
	const forged = ['not-a-run', 'BASE-UNLISTED', ids.run_main, ids.baseline_reviewed, `${ids.baseline_plain}x`, '../' + ids.baseline_plain];
	for (const value of forged) {
		for (const query of [`?run=${encodeURIComponent(value)}`, `?/measure&run=${encodeURIComponent(value)}`]) {
			await open(page, `${BASE}${query}`);
			await expect(page.locator('select[name="run"]'), value).toHaveValue('');
			await expect(page.locator('input[name="run_id"]'), value).toHaveValue('');
			await expect(page.locator('[data-native-timeline="true"]'), value).toHaveCount(0);
			await expect(page.locator('audio[data-baseline-player="true"]'), value).toHaveCount(0);
			await expect(page.getByRole('button', { name: /Save review/ }), value).toBeDisabled();
			await expect(page.getByRole('button', { name: /Measure interval/ }), value).toBeDisabled();
		}
	}
	expect((await mock.log()).requests.filter((entry) => entry.non_get)).toEqual([]);
	record('capture', 'X8_forged_run_selects_nothing', { selected_nothing: forged.length, of: forged.length, urls_tried: forged.length * 2 });
});

test('an interval after the first five seconds shows no setup warning; measuring writes no review', async ({ page, mock }) => {
	await open(page, WITH_RUN);
	await page.locator('input[name="start_seconds"]').fill('5.5');
	await page.locator('input[name="end_seconds"]').fill('6.4');
	await page.getByRole('button', { name: /Measure interval/ }).click();
	const measurement = page.locator('[data-measurement="true"]');
	await expect(measurement).toBeVisible();
	await expect(measurement.locator('[data-measurement-unknowns="true"]')).toBeVisible();
	const log = await mock.log();
	expect(log.requests.filter((entry) => entry.non_get).map((entry) => entry.path)).toEqual([`/api/v1/sources/${ids.source_plain}/capture-measurements`]);
	expect(log.review_records).toBe(0);
	// Echoed back as text, an interval that starts at 5.5 s shows no setup warning and keeps the clean status selectable.
	await expect(page.locator('input[name="start_seconds"]')).toHaveValue('5.5');
	await expect(page.locator('[data-setup-warning="true"]')).toHaveCount(0);
	await expect(page.locator('select[name="review_status"] option[value="reviewed_candidate"]')).toHaveJSProperty('disabled', false);
	await expect(page.locator('input[name="setup_interval_acknowledged"]')).not.toBeChecked();
	await expect(page.locator('[data-review-saved]')).toHaveCount(0);
});

test('the baseline player does not start by itself', async ({ page }) => {
	await open(page, WITH_RUN);
	const player = page.locator('audio[data-baseline-player="true"]');
	await expect(player).toHaveCount(1);
	expect(await player.evaluate((element: HTMLAudioElement) => ({ paused: element.paused, autoplay: element.autoplay, preload: element.preload, time: element.currentTime }))).toEqual({ paused: true, autoplay: false, preload: 'none', time: 0 });
});
