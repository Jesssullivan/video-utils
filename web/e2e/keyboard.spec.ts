// Keyboard navigation (WEB_TESTS_S3.md 5.2; metric W13): skip link, primary navigation, the 12 review bindings and
// a focus-trap sweep over the 16 routes. Chromium only; no screen-reader or assistive-technology claim.
import type { Page } from '@playwright/test';
import { expect, ids, open, record, ROUTES, test } from '../tests/e2e-support';

const NAV = ['Clips', 'Upload', 'Runs', 'Jobs', 'Tools'];
const MAX_SAME_ELEMENT_PRESSES = 50;

type Focus = { tag: string; text: string; href: string | null; id: string; cls: string; outlineStyle: string; outlineWidth: string; boxShadow: string; inViewport: boolean };
const focused = (page: Page): Promise<Focus> =>
	page.evaluate(() => {
		const element = document.activeElement as HTMLElement;
		const style = getComputedStyle(element);
		const box = element.getBoundingClientRect();
		return {
			tag: element.tagName, text: (element.textContent ?? '').trim().slice(0, 40), href: element.getAttribute('href'), id: element.id, cls: element.className,
			outlineStyle: style.outlineStyle, outlineWidth: style.outlineWidth, boxShadow: style.boxShadow,
			inViewport: box.width > 0 && box.height > 0 && box.left >= 0 && box.top >= 0
		};
	});

test('the first Tab focuses the skip link and Enter moves focus to #main', async ({ page }) => {
	await open(page, '/');
	await page.keyboard.press('Tab');
	const skip = await focused(page);
	expect(skip).toMatchObject({ tag: 'A', text: 'Skip to content', href: '#main' });
	// Off-screen until focused; once focused it is inside the viewport.
	expect(skip.inViewport).toBe(true);
	await page.keyboard.press('Enter');
	await expect(page).toHaveURL(/#main$/);
	await expect.poll(() => page.evaluate(() => document.activeElement?.id)).toBe('main');
	record('keyboard', 'skip_link', { first_tab_focus: skip.text, enter_moves_focus_to: 'main' });
});

test('every primary-nav link is reachable by Tab in DOM order with a visible focus indicator', async ({ page }) => {
	await open(page, '/runs');
	const unfocused = await page.locator('nav[aria-label="Primary"] a').evaluateAll((links) =>
		links.map((link) => {
			const style = getComputedStyle(link);
			return { text: (link.textContent ?? '').trim(), outlineStyle: style.outlineStyle, outlineWidth: style.outlineWidth, boxShadow: style.boxShadow };
		})
	);
	expect(unfocused.map((link) => link.text)).toEqual(NAV);
	await page.keyboard.press('Tab'); // skip link
	const visible: string[] = [];
	for (const [index, name] of NAV.entries()) {
		await page.keyboard.press('Tab');
		const link = await focused(page);
		expect(link, `Tab ${index + 2}`).toMatchObject({ tag: 'A', text: name });
		const before = unfocused[index];
		const outlineChanged = link.outlineStyle !== 'none' && parseFloat(link.outlineWidth) > 0 && (link.outlineStyle !== before.outlineStyle || link.outlineWidth !== before.outlineWidth);
		const shadowChanged = link.boxShadow !== 'none' && link.boxShadow !== before.boxShadow;
		expect(outlineChanged || shadowChanged, `${name}: focused ${link.outlineStyle} ${link.outlineWidth} / ${link.boxShadow}; unfocused ${before.outlineStyle} ${before.outlineWidth} / ${before.boxShadow}`).toBe(true);
		visible.push(name);
	}
	// Enter on a focused nav link navigates.
	await page.keyboard.press('Enter');
	await expect(page).toHaveURL(/\/tools$/);
	record('keyboard', 'primary_nav', { links: NAV.length, reachable_in_dom_order: visible.length, visible_focus_indicator: visible.length });
});

test.describe('review workspace bindings', () => {
	const state = (page: Page) =>
		page.evaluate(() => ({
			time: document.querySelector('[data-source-time]')?.getAttribute('data-source-time') ?? '',
			transport: (document.querySelector('[data-transport="true"] p')?.textContent ?? '').replace(/\s+/g, ' ').trim(),
			loop: (document.querySelector('[data-transport="true"] input[type="checkbox"]') as HTMLInputElement | null)?.checked ?? null,
			queue: document.querySelector('[data-queue-count]')?.getAttribute('data-queue-count') ?? null
		}));

	async function openReview(page: Page): Promise<void> {
		await open(page, `/runs/${ids.run_main}/review`);
		await expect(page.locator('[data-transport="true"]')).toBeVisible();
		// Labelling session on, with the operator's own template words (quick marks need them).
		await page.locator('[data-labelling-session] > label input[type="checkbox"]').check();
		await page.locator('[data-quick-mark-bar="true"] input.input').fill('e2e template words');
	}

	test('all 12 bindings act from the transport toolbar', async ({ page, mock, problems }) => {
		// The player is kept empty here so the position is exactly what the keys set: the mock serves a 0.5 s WAV without
		// byte ranges, and a loaded element would clamp or reset the position on its own schedule. Media seeking against
		// real video is out of scope for this lane (WEB_TESTS_S3.md section 1).
		problems.expectConsoleError(/\[\/api\/sources\/art_[0-9a-f]{32}\/media\]/, 'the review player request is aborted by this test on purpose');
		await page.route('**/api/sources/*/media', (route) => route.abort());
		await openReview(page);
		const transport = page.locator('[data-transport="true"]');
		await transport.focus();
		const acted: string[] = [];
		const press = async (key: string, name: string, changed: (before: Awaited<ReturnType<typeof state>>, after: Awaited<ReturnType<typeof state>>) => boolean) => {
			const before = await state(page);
			await page.keyboard.press(key);
			await expect.poll(async () => changed(before, await state(page)), { message: `${name} (${key}) had no effect`, timeout: 5000 }).toBe(true);
			acted.push(name);
		};
		expect((await state(page)).transport).toContain('no span selected');
		await press('[', 'span_start', (_before, after) => after.transport.includes('span not ordered'));
		await press('ArrowRight', 'seek_forward', (before, after) => Number(before.time) === 0 && Number(after.time) === 1);
		await press(']', 'span_end', (_before, after) => after.transport.includes('Span: 0:00.000–0:01.000'));
		await press('ArrowLeft', 'seek_back', (before, after) => Number(before.time) === 1 && Number(after.time) === 0);
		await press('l', 'loop', (before, after) => before.loop === false && after.loop === true);
		await press('n', 'next_boundary', (_before, after) => after.transport.includes('At intent boundary 0:00.500 (projected; not detected).'));
		await press('p', 'prev_boundary', (_before, after) => after.transport.includes('No intent boundary in that direction.'));
		await press('Shift+N', 'next_flag', (_before, after) => after.transport.includes('No shown flag in that direction.'));
		await press('Shift+P', 'prev_flag', (_before, after) => after.transport.includes('At flag-1') && after.transport.includes('(detector hypothesis)'));
		await press('b', 'queue_phrase_point', (before, after) => Number(after.queue) === Number(before.queue) + 1);
		await press('i', 'queue_selected_kind', (before, after) => Number(after.queue) === Number(before.queue) + 1);
		await press('u', 'undo', (before, after) => Number(after.queue) === Number(before.queue) - 1);
		expect(new Set(acted).size).toBe(12);
		// Queued marks are local until saved, and no key started playback: nothing was written upstream.
		expect(await mock.nonGet()).toEqual([]);
		expect(await page.locator('video').evaluateAll((players) => players.every((player) => (player as HTMLVideoElement).paused))).toBe(true);
		record('keyboard', 'review_bindings_act_with_focus', { bindings: 12, acted: new Set(acted).size });
		// Leave no unsaved-queue prompt behind for the page close.
		await page.keyboard.press('u');
		await expect(page.locator('[data-queue-count]')).toHaveAttribute('data-queue-count', '0');
	});

	test('the 12 bindings are inert in a text field, in a field inside the toolbar, and when the workspace has no focus', async ({ page, mock }) => {
		await openReview(page);
		const keys = ['ArrowRight', 'ArrowLeft', '[', ']', 'l', 'b', 'i', 'n', 'p', 'Shift+N', 'Shift+P', 'u'];
		const places: Array<{ name: string; focus: () => Promise<void> }> = [
			{ name: 'text field outside the toolbars (Mark here note)', focus: () => page.locator('[data-mark-here="true"] input.input').last().focus() },
			{ name: 'text field inside the quick-mark toolbar', focus: () => page.locator('[data-quick-mark-bar="true"] input.input').focus() },
			{ name: 'select inside the quick-mark toolbar', focus: () => page.locator('[data-quick-mark-bar="true"] select').first().focus() },
			{ name: 'page heading (workspace not focused)', focus: () => page.locator('main#main').focus() }
		];
		let inert = 0;
		for (const place of places) {
			await place.focus();
			const before = await state(page);
			for (const key of keys) await page.keyboard.press(key);
			const after = await state(page);
			expect(after, place.name).toEqual(before);
			inert += keys.length;
		}
		// Typing the letters into a text field is ordinary text entry.
		const note = page.locator('[data-mark-here="true"] input.input').last();
		await note.fill('');
		await note.pressSequentially('blip nu');
		await expect(note).toHaveValue('blip nu');
		expect(await mock.nonGet()).toEqual([]);
		record('keyboard', 'review_bindings_inert_without_workspace_focus', { key_presses: inert, state_changes: 0, places: places.map((place) => place.name) });
	});
});

test('no keyboard trap: Tab leaves every widget within 50 presses on all 16 routes', async ({ page }) => {
	test.setTimeout(240_000);
	const rows: Array<{ route: string; presses: number; distinct_stops: number; longest_stay: number; wrapped: boolean }> = [];
	for (const route of ROUTES) {
		await open(page, route.path);
		const tabbable = await page.evaluate(() => document.querySelectorAll('a[href], button:not([disabled]), input:not([disabled]):not([type="hidden"]), select:not([disabled]), textarea:not([disabled]), summary, audio[controls], video[controls], [tabindex]:not([tabindex="-1"])').length);
		const limit = tabbable * 12 + MAX_SAME_ELEMENT_PRESSES + 20;
		let presses = 0;
		let longest = 0;
		let stay = 0;
		let previous = '';
		let skipSeen = 0;
		const stops = new Set<string>();
		while (presses < limit && skipSeen < 2) {
			await page.keyboard.press('Tab');
			presses += 1;
			const signature = await page.evaluate(() => {
				const element = document.activeElement;
				if (!element || element === document.body) return 'BODY';
				const all = Array.from(document.querySelectorAll('*'));
				return `${element.tagName}#${all.indexOf(element)}`;
			});
			stay = signature === previous ? stay + 1 : 1;
			longest = Math.max(longest, stay);
			previous = signature;
			stops.add(signature);
			expect(stay, `${route.route}: focus stayed on ${signature} for more than ${MAX_SAME_ELEMENT_PRESSES} Tab presses`).toBeLessThanOrEqual(MAX_SAME_ELEMENT_PRESSES);
			if (await page.evaluate(() => document.activeElement?.classList.contains('vu-skip') ?? false)) skipSeen += 1;
		}
		// Focus came back round to the skip link: every widget on the way was left again.
		expect(skipSeen, `${route.route}: focus never wrapped back to the skip link within ${limit} presses`).toBe(2);
		rows.push({ route: route.route, presses, distinct_stops: stops.size, longest_stay: longest, wrapped: skipSeen === 2 });
	}
	expect(rows.length).toBe(16);
	record('keyboard', 'no_keyboard_trap', { routes: rows.length, traps: 0, rows });
});
