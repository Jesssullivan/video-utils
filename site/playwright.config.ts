// Playwright configuration for the site browser suites (SITE_VERIFY_S3.md section 4.2). Chromium only, one worker,
// zero retries, service workers blocked, video off, screenshots and traces kept only on failure. Every output goes
// under SITE_VERIFY_OUT_DIR, which must be set and must lie outside site/; nothing is written inside site/.
// The server under test is the local static emulation started by e2e/global-setup.ts. No browser is downloaded
// (tests/browser-ladder.ts), and no flag disables web security or the sandbox.
import { defineConfig } from '@playwright/test';
import { join } from 'node:path';
import { chooseBrowser } from './tests/browser-ladder';
import { outDir } from './e2e/routes';

const out = outDir(); // throws site_verify_out_dir_required when unset or inside site/
const browser = chooseBrowser();

export default defineConfig({
	testDir: './e2e',
	testMatch: /.*\.spec\.ts$/,
	globalSetup: './e2e/global-setup.ts',
	globalTeardown: './e2e/global-teardown.ts',
	outputDir: join(out, 'playwright-output'),
	fullyParallel: false,
	workers: 1,
	retries: 0,
	forbidOnly: true,
	timeout: 60_000,
	expect: { timeout: 10_000 },
	reporter: [['list'], ['json', { outputFile: join(out, 'report.json') }]],
	use: {
		browserName: 'chromium',
		headless: true,
		video: 'off',
		screenshot: 'only-on-failure',
		trace: 'retain-on-failure',
		serviceWorkers: 'block',
		launchOptions: browser.launch ?? {}
	}
});
