// Capture review never auto-confirms the first five seconds (WEB_TESTS_S3.md 5.2; metric W9).
// The setup-interval rule itself belongs to the control API: the mock replays its recorded 422
// `setup_interval_unacknowledged` whenever the forwarded body is not explicitly acknowledged. What is
// asserted here is the page: loads write nothing, nothing is prefilled or pre-checked, and the page
// forwards an acknowledgement only after the operator ticks the control.
import type { Page } from '@playwright/test';
import { expect, expectNoForbiddenText, ids, open, record, test } from '../tests/e2e-support';

const BASE = `/sources/${ids.source_plain}/capture`;
const WITH_RUN = `${BASE}?run=${ids.baseline_plain}`;

// KNOWN SOURCE DEFECT, reported to root (code capture_interval_number_binding). IntervalPicker.svelte and the capture
// page bind `<input type="number">` to state they then call `.trim()` on; Svelte gives a number for that binding, so
// typing an interval in a real browser throws "trim is not a function" and the live setup warning never renders.
// The Python walkthroughs post the form without a browser and cannot see it. The form itself still posts natively,
// and the warning does render once the server echoes the values back as text.
const NUMBER_BINDING_DEFECT = /trim is not a function/;
const DEFECT_REASON = 'known source defect capture_interval_number_binding (typing in the interval inputs throws)';

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
	// Expected to fail while capture_interval_number_binding exists; Playwright reports an unexpected pass once it is fixed.
	test.fail(true, DEFECT_REASON);
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
	problems.expectConsoleError(NUMBER_BINDING_DEFECT, DEFECT_REASON);
	problems.expectConsoleError(/\[\/sources\/art_[0-9a-f]{32}\/capture\?\/save\]/, 'the browser logs the typed 422 answer to the refused form post');
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

test('the same interval saves once the operator ticks the acknowledgement themselves', async ({ page, mock, problems }) => {
	problems.expectConsoleError(NUMBER_BINDING_DEFECT, DEFECT_REASON);
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

test('after a form action the chosen baseline run is still selected, so the operator can continue', async ({ page, problems }) => {
	// KNOWN SOURCE DEFECT, reported to root (code capture_action_drops_run_selection): the measure/save form actions post
	// to `?/measure` and `?/save`, which replaces the `?run=` query. The page then loads with no baseline run, Save and
	// Measure are disabled, and re-choosing the run discards the typed interval. Expected to fail until that is fixed.
	test.fail(true, 'known source defect capture_action_drops_run_selection (a form action drops ?run=)');
	problems.expectConsoleError(NUMBER_BINDING_DEFECT, DEFECT_REASON);
	await open(page, WITH_RUN);
	await page.locator('input[name="start_seconds"]').fill('5.5');
	await page.locator('input[name="end_seconds"]').fill('6.4');
	await page.getByRole('button', { name: /Measure interval/ }).click();
	await expect(page.locator('[data-measurement="true"]')).toBeVisible();
	await expect(page.locator('select[name="run"]')).toHaveValue(ids.baseline_plain, { timeout: 3000 });
	await expect(page.getByRole('button', { name: /Save review/ })).toBeEnabled({ timeout: 3000 });
});

test('an interval after the first five seconds shows no setup warning; measuring writes no review', async ({ page, mock, problems }) => {
	problems.expectConsoleError(NUMBER_BINDING_DEFECT, DEFECT_REASON);
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
