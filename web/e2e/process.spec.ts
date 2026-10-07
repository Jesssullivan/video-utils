// The process form: FULLER requires a reviewed capture interval (WEB_TESTS_S3.md 5.2; metric W10).
// Fixtures: the plain source has no saved review; the reviewed source has one with scope
// experimental_capture_render. The catalogue replayed by default was recorded under the test admission seam;
// the product-default catalogue recorded at the lane baseline is replayed in the third state.
import type { Page } from '@playwright/test';
import { expect, expectNoForbiddenText, fixture, ids, open, record, test } from '../tests/e2e-support';

const plain = `/sources/${ids.source_plain}/process`;
const reviewed = `/sources/${ids.source_reviewed}/process`;
const fullerOption = (page: Page) => page.locator('[data-preset-choice="true"] [data-option="fuller"]');

test('state 1: no current review -> FULLER is rendered disabled with capture_interval_required and nothing can be submitted', async ({ page, mock }) => {
	await open(page, plain);
	await expect(page.locator('[data-process-page="true"]')).toBeVisible();
	const option = fullerOption(page);
	await expect(option).toHaveAttribute('data-enabled', 'false');
	await expect(option).toHaveAttribute('data-refusal', 'capture_interval_required');
	await expect(option.locator('code')).toHaveText('capture_interval_required');
	// FULLER stays the default selection while disabled; it is never silently replaced by another preset.
	await expect(option.locator('input[type="radio"]')).toBeChecked();
	const form = page.locator('[data-author-form="fuller"]');
	await expect(form.locator('[data-refusal-code="capture_interval_required"]')).toBeVisible();
	const author = form.getByRole('button', { name: 'Author FULLER settings' });
	const render = page.locator('[data-apply-form="true"]').getByRole('button', { name: 'Render full take' });
	await expect(author).toBeDisabled();
	await expect(render).toBeDisabled();
	await expect(page.locator('[data-apply-form="true"] [data-refusal="capture_interval_required"]')).toBeVisible();

	// Pointer activation of the disabled controls.
	await author.click({ force: true });
	await render.click({ force: true });
	await author.dispatchEvent('click');
	// Keyboard activation: Space/Enter on the selected preset, and implicit submission from enabled fields of both forms.
	await option.locator('input[type="radio"]').focus();
	await page.keyboard.press('Space');
	await page.keyboard.press('Enter');
	await form.locator('select[name="capture_review_id"]').focus();
	await page.keyboard.press('Enter');
	const timeouts = page.locator('input[name="timeout_seconds"]');
	for (let index = 0; index < (await timeouts.count()); index += 1) {
		if (await timeouts.nth(index).isEnabled()) {
			await timeouts.nth(index).fill('30');
			await timeouts.nth(index).press('Enter');
		}
	}
	await page.waitForLoadState('networkidle');
	await expect(page).toHaveURL(new RegExp(`${plain}$`));
	await expect(page.locator('[data-submitted-job]')).toHaveCount(0);
	const log = await mock.log();
	expect(log.job_submissions).toBe(0);
	expect(log.requests.filter((entry) => entry.non_get)).toEqual([]);
	await expectNoForbiddenText(page);
	record('process', 'W10_state_refused', { fuller_enabled: false, refusal_code: 'capture_interval_required', job_submissions: log.job_submissions, activation_attempts: 'pointer x3, keyboard Space/Enter, implicit submission' });
});

test('state 2: a saved experimental_capture_render review -> FULLER is enabled', async ({ page, mock }) => {
	await open(page, reviewed);
	const option = fullerOption(page);
	await expect(option).toHaveAttribute('data-enabled', 'true');
	await expect(option).toHaveAttribute('data-refusal', '');
	await expect(option.locator('input[type="radio"]')).toBeChecked();
	const form = page.locator('[data-author-form="fuller"]');
	await expect(form.getByRole('button', { name: 'Author FULLER settings' })).toBeEnabled();
	await expect(form.locator('[data-refusal-code]')).toHaveCount(0);
	await expect(form.locator(`select[name="capture_review_id"] option[value="${ids.review_reviewed}"]`)).toHaveCount(1);
	// FULLER controls are shown as preset values and are not editable.
	const knobs = form.locator('[data-knob] input:not([name="timeout_seconds"])');
	expect(await knobs.count()).toBeGreaterThan(0);
	for (let index = 0; index < (await knobs.count()); index += 1) await expect(knobs.nth(index)).toBeDisabled();
	const log = await mock.log();
	expect(log.job_submissions).toBe(0);
	record('process', 'W10_state_enabled', { fuller_enabled: true, job_submissions: log.job_submissions, admission_basis: 'test seam catalogue (job_types.json)' });
});

test('state 3: with the product-default catalogue the page shows what that catalogue admits', async ({ page, mock }) => {
	const types = fixture<{ job_types: Array<{ tool: string; admission_state: string }> }>('job_types_product_default.json').job_types;
	const pending = types.filter((entry) => entry.admission_state !== 'admitted').map((entry) => entry.tool);
	const fullerPending = pending.includes('capture_profile') || pending.includes('apply_capture_profile');
	await mock.scenario('product_default_admission');
	await open(page, reviewed);
	const option = fullerOption(page);
	await expect(option).toHaveAttribute('data-enabled', fullerPending ? 'false' : 'true');
	await expect(option).toHaveAttribute('data-refusal', fullerPending ? 'tool_pending_admission' : '');
	if (fullerPending) await expect(page.locator('[data-author-form="fuller"]').getByRole('button', { name: 'Author FULLER settings' })).toBeDisabled();
	expect((await mock.log()).job_submissions).toBe(0);
	record('process', 'product_default_admission', { pending_tools: pending, fuller_enabled: !fullerPending });
});

test('no control is labelled high-pass, low-cut or notch, on any preset', async ({ page }) => {
	const FORBIDDEN = /high[\s_-]?pass|low[\s_-]?cut|notch|\bhpf\b/i;
	let controls = 0;
	for (const path of [plain, reviewed]) {
		await open(page, path);
		const presets = await page.locator('[data-preset-choice="true"] input[type="radio"]').count();
		expect(presets).toBeGreaterThanOrEqual(6);
		for (let index = 0; index < presets; index += 1) {
			await page.locator('[data-preset-choice="true"] input[type="radio"]').nth(index).check();
			const labels = await page.locator('main').evaluate((main) => {
				const out: string[] = [];
				for (const element of main.querySelectorAll('input, select, textarea, button, option, label, legend')) {
					const field = element as HTMLInputElement;
					out.push([element.tagName, field.name ?? '', field.id ?? '', element.getAttribute('aria-label') ?? '', field.placeholder ?? '', ['LABEL', 'LEGEND', 'BUTTON', 'OPTION'].includes(element.tagName) ? (element.textContent ?? '') : ''].join(' | '));
				}
				return out;
			});
			controls += labels.length;
			for (const label of labels) expect(label, label).not.toMatch(FORBIDDEN);
		}
	}
	// The page says so in prose as well.
	await expect(page.locator('[data-process-page="true"]')).toContainText('There is no high-pass, low-cut or notch control here and none can be sent.');
	record('process', 'no_high_pass_low_cut_notch_control', { controls_checked: controls, matches: 0 });
});

test('the low shelf is listed as unavailable and offers no form', async ({ page }) => {
	await open(page, reviewed);
	const shelf = page.locator('[data-option="fuller-shelf"]');
	await expect(shelf).toHaveAttribute('data-enabled', 'false');
	await shelf.locator('input[type="radio"]').check();
	await expect(page.locator('[data-option-unavailable="fuller-shelf"]')).toBeVisible();
	await expect(page.locator('main form[method="POST"]')).toHaveCount(0);
});

test('typing into the span audition and knob number inputs never throws (X6)', async ({ page, mock, problems }) => {
	await open(page, reviewed);
	const audition = page.locator('[data-span-audition="true"]').first();
	await expect(audition).toBeVisible();
	const span = audition.locator('input[type="number"]');
	await expect(span).toHaveCount(2);
	await span.nth(0).click();
	await span.nth(0).pressSequentially('1');
	await span.nth(1).click();
	await span.nth(1).pressSequentially('2.5');
	// The loop handler reads both values on every timeupdate of a player; nothing is played by this test.
	const player = audition.locator('audio').first();
	await player.dispatchEvent('timeupdate');
	expect(await player.evaluate((element: HTMLAudioElement) => element.paused)).toBe(true);
	await expect(span.nth(0)).toHaveValue('1');
	await expect(span.nth(1)).toHaveValue('2.5');
	// A partial entry and a cleared entry are read the same way.
	await span.nth(1).press('Backspace');
	await span.nth(1).press('Backspace');
	await span.nth(1).press('Backspace');
	await span.nth(0).pressSequentially('.');
	await player.dispatchEvent('timeupdate');

	const knob = page.locator('[data-knob] input[type="number"]:enabled').first();
	await expect(knob).toBeVisible();
	await knob.click();
	await knob.pressSequentially('30');
	await expect(knob).toHaveValue('30');
	expect(problems.seen()).toEqual([]);
	expect((await mock.log()).requests.filter((entry) => entry.non_get)).toEqual([]);
	record('process', 'X6_number_inputs', { typed_without_page_error: 3, of: 3, inputs: ['SpanAudition start', 'SpanAudition end', 'KnobField'] });
});
