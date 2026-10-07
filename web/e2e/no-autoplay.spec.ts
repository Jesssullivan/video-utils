// No media starts by itself (WEB_TESTS_S3.md 5.2; metric W12). An init script counts every call of
// HTMLMediaElement.prototype.play before any page script runs; with no user gesture the count must stay 0 and every
// media element must be paused at 0 s. The browser is launched with its default media policy.
import { expect, open, record, ROUTES, test } from '../tests/e2e-support';

test('on each of the 16 routes nothing calls play() and every media element is paused at 0 s', async ({ page }) => {
	test.setTimeout(180_000);
	await page.addInitScript(() => {
		const counter = { calls: 0 };
		(window as unknown as { __playCalls: typeof counter }).__playCalls = counter;
		const original = HTMLMediaElement.prototype.play;
		HTMLMediaElement.prototype.play = function play(this: HTMLMediaElement) {
			counter.calls += 1;
			return original.call(this);
		};
	});
	const rows: Array<{ route: string; media_elements: number; play_calls: number; unpaused: number; marked_to_start: number; moved: number }> = [];
	for (const route of ROUTES) {
		await open(page, route.path);
		await page.waitForTimeout(1000);
		const result = await page.evaluate(() => {
			const media = Array.from(document.querySelectorAll<HTMLMediaElement>('audio, video'));
			return {
				media_elements: media.length,
				play_calls: (window as unknown as { __playCalls: { calls: number } }).__playCalls.calls,
				unpaused: media.filter((element) => !element.paused).length,
				marked_to_start: media.filter((element) => element.autoplay || element.hasAttribute('autoplay')).length,
				moved: media.filter((element) => element.currentTime !== 0).length
			};
		});
		rows.push({ route: route.route, ...result });
		expect(result, route.route).toMatchObject({ play_calls: 0, unpaused: 0, marked_to_start: 0, moved: 0 });
	}
	expect(rows.length).toBe(16);
	// The sweep is not vacuous: several routes do carry players.
	const withMedia = rows.filter((row) => row.media_elements > 0);
	expect(withMedia.length).toBeGreaterThanOrEqual(4);
	record('no-autoplay', 'W12_no_autoplay', { routes: rows.length, routes_with_media: withMedia.length, media_elements: rows.reduce((sum, row) => sum + row.media_elements, 0), play_calls: 0, unpaused: 0, rows });
});

test('the counter does see a play() call when the operator starts a player', async ({ page }) => {
	// Control for the sweep above: the same instrumentation registers an operator-initiated start.
	await page.addInitScript(() => {
		const counter = { calls: 0 };
		(window as unknown as { __playCalls: typeof counter }).__playCalls = counter;
		const original = HTMLMediaElement.prototype.play;
		HTMLMediaElement.prototype.play = function play(this: HTMLMediaElement) {
			counter.calls += 1;
			return original.call(this);
		};
	});
	await open(page, ROUTES.find((route) => route.name === 'run-compare')!.path);
	const player = page.locator('audio[data-ab-player="X"]');
	await expect(player).toHaveCount(1);
	await player.evaluate((element: HTMLAudioElement) => void element.play().catch(() => undefined));
	expect(await page.evaluate(() => (window as unknown as { __playCalls: { calls: number } }).__playCalls.calls)).toBe(1);
});
