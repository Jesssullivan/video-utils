// Playwright configuration (WEB_TESTS_S3.md section 4.5). Chromium only, loopback only, one worker, zero retries.
// The app under test is the adapter-node build started by e2e/global-setup.ts through `node serve.js` on an
// ephemeral loopback port, with a replay mock of the control API. Reports and traces go outside web/.
import { defineConfig } from '@playwright/test';
import { fileURLToPath } from 'node:url';
import { chooseBrowser } from './tests/browser-ladder';

const browser = chooseBrowser();
const selected = process.argv.find((argument) => argument.startsWith('--project='))?.slice('--project='.length) ?? 'all';
const out = (relative: string) => fileURLToPath(new URL(`../artifacts/s2/web_tests/${relative}`, import.meta.url));

export default defineConfig({
	testDir: './e2e',
	globalSetup: './e2e/global-setup.ts',
	globalTeardown: './e2e/global-teardown.ts',
	outputDir: out('playwright-output'),
	fullyParallel: false,
	workers: 1,
	retries: 0,
	forbidOnly: !!process.env.CI,
	timeout: 60_000,
	expect: { timeout: 10_000 },
	reporter: [['list'], ['json', { outputFile: out(`${selected}/report.json`) }]],
	use: {
		// Set by global setup; always http://127.0.0.1:<ephemeral port>.
		baseURL: process.env.E2E_BASE_URL,
		browserName: 'chromium',
		headless: true,
		video: 'off',
		screenshot: 'only-on-failure',
		trace: 'retain-on-failure',
		serviceWorkers: 'block',
		// No flag that disables web security or the sandbox: the BFF same-origin checks are part of what is tested.
		launchOptions: browser.launch ?? {}
	},
	projects: [
		{ name: 'e2e', testMatch: /.*\.spec\.ts$/, testIgnore: /a11y-.*\.spec\.ts$/ },
		{ name: 'a11y', testMatch: /a11y-.*\.spec\.ts$/ }
	]
});
