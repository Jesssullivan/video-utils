// Browser ladder for the Playwright suites (WEB_TESTS_S3.md section 4.6). First match wins; nothing is downloaded.
// (a) PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH; (b) the Chromium revision the pinned Playwright expects, if it is already in
// the Playwright cache; (c) an installed Google Chrome; (e) typed skip e2e_browser_unavailable. Step (d), a one-time
// `pnpm exec playwright install chromium`, is an operator action that must be recorded; this module never runs it.
import { chromium } from '@playwright/test';
import { existsSync } from 'node:fs';

export const BROWSER_SKIP_CODE = 'e2e_browser_unavailable';

export type BrowserChoice =
	| { step: 'a_env_executable'; source: string; launch: { executablePath: string } }
	| { step: 'b_cached_expected_revision'; source: string; launch: { channel: 'chromium' } }
	| { step: 'c_installed_chrome'; source: string; launch: { channel: 'chrome' } }
	| { step: 'e_skip'; source: string; launch: null; skip_code: typeof BROWSER_SKIP_CODE };

const CHROME_LOCATIONS = [
	'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
	'/usr/bin/google-chrome',
	'/usr/bin/google-chrome-stable',
	'/opt/google/chrome/chrome'
];

export function chooseBrowser(env: Record<string, string | undefined> = process.env): BrowserChoice {
	const explicit = env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH;
	if (explicit && existsSync(explicit)) {
		return { step: 'a_env_executable', source: 'PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH', launch: { executablePath: explicit } };
	}
	let expected = '';
	try {
		// The full Chromium build of the pinned Playwright; `channel: 'chromium'` runs it in the new headless mode,
		// so the separate headless-shell download is not needed.
		expected = chromium.executablePath();
	} catch {
		expected = '';
	}
	if (expected && existsSync(expected)) {
		return { step: 'b_cached_expected_revision', source: 'playwright cache (expected revision already present)', launch: { channel: 'chromium' } };
	}
	if (CHROME_LOCATIONS.some((location) => existsSync(location))) {
		return { step: 'c_installed_chrome', source: 'installed Google Chrome (channel chrome)', launch: { channel: 'chrome' } };
	}
	return { step: 'e_skip', source: 'no Chromium found; nothing was downloaded', launch: null, skip_code: BROWSER_SKIP_CODE };
}
