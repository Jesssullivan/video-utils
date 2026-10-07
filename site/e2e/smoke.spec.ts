// Browser smoke over every built route at five viewport configurations (SITE_VERIFY_S3.md section 5; metrics V1 to V5).
// Each case runs in a fresh context in the site's default mode (no stored preference, so dark). A case passes only if
// all six checks of section 5.2 hold. The only console allowance is the declared expected_document_404 on the
// not-found probe (section 5.3). The build-intended external request list is frozen as empty (section 5.4).
import { expect, test } from '@playwright/test';
import { BUILD_INTENDED_EXTERNAL, FALLBACK_HEADING, ROUTES, VIEWPORTS, viewport, writeJson } from './routes';
import { openContext, origin, skipWhenNoBrowser, visit } from './support';

const SETTLE_MS = 400; // longer than the chrome's 180 ms header transition

test.beforeEach(skipWhenNoBrowser);

for (const route of ROUTES) {
	for (const view of VIEWPORTS) {
		const id = `${route.id}-${view.id}`;
		test(`smoke ${route.path} [${view.id}]`, async ({ browser }) => {
			const { context, page, traffic } = await openContext(browser, view);
			const consoleErrors: Array<{ text: string; url: string }> = [];
			const allowance: Array<{ text: string; url: string }> = [];
			const warnings: Array<{ text: string; url: string }> = [];
			const pageErrors: string[] = [];
			const probeUrl = `${origin()}${route.path}`;
			page.on('console', (message) => {
				const entry = { text: message.text().slice(0, 300), url: message.location().url ?? '' };
				if (message.type() === 'error') {
					// Section 5.3: the browser's own report of the fallback's 404 document status, on the probe only.
					if (route.kind === 'not_found_probe' && entry.url === probeUrl && /\b404\b/.test(entry.text)) allowance.push(entry);
					else consoleErrors.push(entry);
				} else if (message.type() === 'warning') {
					warnings.push(entry);
				}
			});
			page.on('pageerror', (error) => pageErrors.push(String(error.message).slice(0, 300)));
			try {
				const status = await visit(page, route.path);
				const measure = () =>
					page.evaluate(() => ({ scroll: document.documentElement.scrollWidth, client: document.documentElement.clientWidth }));
				const atLoad = await measure();
				const renders = await page.evaluate((fallbackHeading) => {
					const visible = (element: Element | null) => {
						if (!element) return false;
						const box = (element as HTMLElement).getBoundingClientRect();
						const style = getComputedStyle(element);
						return box.width > 0 && box.height > 0 && style.visibility !== 'hidden' && style.display !== 'none';
					};
					const main = document.querySelector('main#content');
					const h1s = Array.from(document.querySelectorAll('h1')).filter(visible);
					const namedNav = Array.from(document.querySelectorAll('nav')).some((nav) => {
						const label = (nav.getAttribute('aria-label') ?? '').trim();
						const ids = (nav.getAttribute('aria-labelledby') ?? '').trim().split(/\s+/).filter(Boolean);
						return label !== '' || ids.some((id) => (document.getElementById(id)?.textContent ?? '').trim() !== '');
					});
					return {
						main_visible_with_text: visible(main) && (main?.textContent ?? '').trim().length > 0,
						visible_h1_count: h1s.length,
						h1_text: h1s.map((h) => (h.textContent ?? '').trim()),
						title: document.title.trim(),
						header_visible: visible(document.querySelector('[data-testid="public-navigation"]')),
						footer_attached: document.querySelector('footer') !== null,
						named_nav_attached: namedNav,
						fallback_heading_shown: h1s.some((h) => (h.textContent ?? '').trim() === fallbackHeading),
						scroll_height: document.documentElement.scrollHeight,
						viewport_height: window.innerHeight
					};
				}, FALLBACK_HEADING);
				await page.evaluate(() => window.scrollTo(0, document.documentElement.scrollHeight));
				await page.waitForTimeout(SETTLE_MS);
				const atBottom = await measure();
				// Supplementary hydration evidence: the chrome's scroll listener is attached only after hydration.
				const compactAfterScroll =
					renders.scroll_height - renders.viewport_height > 32
						? await page.evaluate(() => document.querySelector('[data-testid="public-navigation"]')?.classList.contains('site-chrome--compact') ?? false)
						: null;
				const overflow = Math.max(0, atLoad.scroll - atLoad.client, atBottom.scroll - atBottom.client);
				const unexpectedExternal = traffic.external.filter((url) => !BUILD_INTENDED_EXTERNAL.includes(url));
				const checks = {
					navigation_status: status === route.expected_status,
					renders:
						renders.main_visible_with_text &&
						renders.visible_h1_count === 1 &&
						renders.title !== '' &&
						renders.header_visible &&
						renders.footer_attached &&
						renders.named_nav_attached &&
						(route.kind !== 'not_found_probe' || renders.fallback_heading_shown),
					hydration: traffic.startModuleStatus === 200 && pageErrors.length === 0,
					console: consoleErrors.length === 0 && pageErrors.length === 0,
					horizontal_scroll: overflow === 0,
					requests: unexpectedExternal.length === 0
				};
				const failed = Object.entries(checks).filter(([, ok]) => !ok).map(([name]) => name);
				writeJson('smoke', id, {
					case: id,
					route: route.path,
					route_file: route.file,
					route_kind: route.kind,
					viewport: view,
					zoom_method: view.id === 'z200' ? 'viewport_emulation' : null,
					browser_version: browser.version(),
					navigation_status: status,
					expected_status: route.expected_status,
					renders,
					start_module_status: traffic.startModuleStatus,
					compact_header_after_scroll: compactAfterScroll,
					overflow_px: overflow,
					scroll_width: { at_load: atLoad, at_bottom: atBottom },
					console_errors: consoleErrors,
					expected_document_404: allowance,
					page_errors: pageErrors,
					warnings,
					requests_total: traffic.requests.length,
					requests_local: traffic.requests.filter((url) => url.startsWith(origin())).length,
					external_requests: traffic.external,
					external_fetched: 0,
					checks,
					failed,
					passed: failed.length === 0
				});
				expect(failed, `${id}: ${JSON.stringify({ status, renders, overflow, consoleErrors, pageErrors, external: traffic.external })}`).toEqual([]);
			} finally {
				await context.close();
			}
		});
	}
}

// Section 5.2, one extra check per route at w1280: the first Tab press focuses the skip link and its target exists.
// A partial keyboard check, not a keyboard walkthrough.
for (const route of ROUTES) {
	test(`skip link ${route.path} [w1280]`, async ({ browser }) => {
		const { context, page } = await openContext(browser, viewport('w1280'));
		try {
			await visit(page, route.path);
			await page.keyboard.press('Tab');
			const focus = await page.evaluate(() => {
				const active = document.activeElement as HTMLAnchorElement | null;
				const href = active?.getAttribute('href') ?? '';
				return {
					tag: active?.tagName.toLowerCase() ?? null,
					href,
					text: (active?.textContent ?? '').trim(),
					target_exists: href.startsWith('#') && document.getElementById(href.slice(1)) !== null
				};
			});
			const passed = focus.tag === 'a' && focus.href === '#content' && focus.target_exists;
			writeJson('skip-link', route.id, { route: route.path, viewport: 'w1280', focus, passed });
			expect(passed, JSON.stringify(focus)).toBe(true);
		} finally {
			await context.close();
		}
	});
}
