// Shared Playwright fixtures for the e2e and a11y projects (WEB_TESTS_S3.md 5.2, 5.3).
// - typed skip when no browser is available (never reported as passed);
// - a fresh mock request log per test, read through the mock's own loopback port;
// - every test fails on an uncaught page error or console.error it did not declare as expected.
import { test as base, expect, type APIRequestContext, type Page } from '@playwright/test';
import { appendFileSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

export { expect };

const FIXTURES = fileURLToPath(new URL('../e2e/fixtures/control-api/', import.meta.url));
export const OUT = fileURLToPath(new URL('../../artifacts/s2/web_tests/', import.meta.url));
export const fixture = <T = unknown>(name: string): T => JSON.parse(readFileSync(`${FIXTURES}${name}`, 'utf8')) as T;

export const SKIP_CODE = process.env.E2E_SKIP_CODE ?? '';
export const MOCK_URL = process.env.E2E_MOCK_URL ?? '';
export const UNCONFIGURED_URL = process.env.E2E_UNCONFIGURED_URL ?? '';

type Ids = {
	source_reviewed: string; source_plain: string; run_main: string; run_other: string; baseline_reviewed: string; baseline_plain: string; review_reviewed: string;
	jobs: Record<'share_succeeded' | 'share_failed' | 'share_running' | 'share_queued' | 'denoise_succeeded' | 'capture_profile_succeeded' | 'apply_succeeded' | 'bad_unknown_key', string>;
};
export const ids = fixture<Ids>('ids.json');

/** The 16 routes of WEB_TESTS_S3.md 5.3, bound to the synthetic fixture ids. */
export const ROUTES: ReadonlyArray<{ name: string; route: string; path: string }> = [
	{ name: 'library', route: '/', path: '/' },
	{ name: 'upload', route: '/upload', path: '/upload' },
	{ name: 'source', route: '/sources/[id]', path: `/sources/${ids.source_reviewed}` },
	{ name: 'capture', route: '/sources/[id]/capture', path: `/sources/${ids.source_reviewed}/capture?run=${ids.baseline_reviewed}` },
	{ name: 'process', route: '/sources/[id]/process', path: `/sources/${ids.source_reviewed}/process` },
	{ name: 'runs', route: '/runs', path: '/runs' },
	{ name: 'run-graph', route: '/runs/[id]', path: `/runs/${ids.run_main}` },
	{ name: 'run-compare', route: '/runs/[id]/compare', path: `/runs/${ids.run_main}/compare` },
	{ name: 'run-review', route: '/runs/[id]/review', path: `/runs/${ids.run_main}/review` },
	{ name: 'run-deliver', route: '/runs/[id]/deliver', path: `/runs/${ids.run_main}/deliver` },
	{ name: 'jobs', route: '/jobs', path: '/jobs' },
	{ name: 'job', route: '/jobs/[id]', path: `/jobs/${ids.jobs.share_succeeded}` },
	{ name: 'tools', route: '/tools', path: '/tools' },
	{ name: 'pick-compare', route: '/compare', path: '/compare' },
	{ name: 'pick-review', route: '/review', path: '/review' },
	{ name: 'pick-download', route: '/download', path: '/download' }
];

export type MockRequest = { method: string; path: string; status: number; file: string | null; non_get: boolean; body_bytes: number; authorized: boolean; review_request?: { start_seconds: unknown; setup_interval_acknowledged: unknown; review_status: unknown } };
export type MockLog = { scenario: string; requests: MockRequest[]; stored_upload_bytes: number; review_records: number; job_submissions: number };

export class Mock {
	constructor(private readonly request: APIRequestContext) {}
	async log(): Promise<MockLog> {
		return (await (await this.request.get(`${MOCK_URL}/__mock/log`)).json()) as MockLog;
	}
	async reset(): Promise<void> {
		expect((await this.request.post(`${MOCK_URL}/__mock/reset`)).status()).toBe(200);
	}
	async scenario(name: 'default' | 'product_default_admission'): Promise<void> {
		expect((await this.request.post(`${MOCK_URL}/__mock/scenario`, { data: { name } })).status()).toBe(200);
	}
	async nonGet(): Promise<MockRequest[]> {
		return (await this.log()).requests.filter((entry) => entry.non_get);
	}
}

/** Appends one metric row for the receipts (artifacts/s2/web_tests/metrics.jsonl, gitignored). */
export function record(spec: string, metric: string, value: unknown): void {
	mkdirSync(OUT, { recursive: true });
	appendFileSync(`${OUT}metrics.jsonl`, `${JSON.stringify({ spec, metric, value })}\n`);
}

type Problems = { expectConsoleError: (pattern: RegExp, reason: string) => void; seen: () => string[] };

export const test = base.extend<{ mock: Mock; problems: Problems; skipWithoutBrowser: void }, { browserFacts: void }>({
	browserFacts: [
		async ({ browser }, use, workerInfo) => {
			// Recorded for the browser receipt: what actually ran, not what the ladder intended.
			mkdirSync(OUT, { recursive: true });
			writeFileSync(`${OUT}browser-${workerInfo.project.name}.json`, `${JSON.stringify({ browser_used: browser.browserType().name(), browser_version: browser.version(), headless: true }, null, 2)}\n`);
			await use();
		},
		{ scope: 'worker', auto: true }
	],
	skipWithoutBrowser: [
		async ({}, use, testInfo) => {
			// Typed skip: reported as skipped with the code, never as passed.
			testInfo.skip(SKIP_CODE !== '', SKIP_CODE);
			await use();
		},
		{ auto: true }
	],
	mock: async ({ request }, use) => {
		const mock = new Mock(request);
		await mock.reset();
		await use(mock);
	},
	problems: [
		async ({ page }, use, testInfo) => {
			const unexpected: string[] = [];
			// Nothing is tolerated by default: a favicon is served (WEB_FIXES_S3 F3), so a /favicon.ico 404 is unexpected again.
			const expected: Array<{ pattern: RegExp; reason: string; hits: number }> = [];
			const note = (text: string) => {
				const allowed = expected.find((item) => item.pattern.test(text));
				if (allowed) allowed.hits += 1;
				else unexpected.push(text);
			};
			page.on('pageerror', (error) => note(`pageerror: ${error.message}`));
			page.on('console', (message) => {
				if (message.type() === 'error') note(`console.error: ${message.text()} [${message.location().url.replace(/^https?:\/\/[^/]+/, '')}]`);
			});
			await use({ expectConsoleError: (pattern, reason) => void expected.push({ pattern, reason, hits: 0 }), seen: () => [...unexpected] });
			record(testInfo.titlePath.slice(1).join(' > '), 'page_errors', { unexpected: unexpected.length, declared_expected: expected.map((item) => ({ reason: item.reason, hits: item.hits })) });
			expect(unexpected, 'uncaught page errors or console.error during the scenario').toEqual([]);
		},
		{ auto: true }
	]
});

/** Navigates and waits until SvelteKit has hydrated (the layout sets no marker, so wait for network idle). */
export async function open(page: Page, path: string, base = ''): Promise<void> {
	const response = await page.goto(`${base}${path}`, { waitUntil: 'networkidle' });
	expect(response, `no response for ${path}`).not.toBeNull();
}

/** Text that must never reach a page: the mock token, the upstream `error` strings and the control API URL. */
export function forbiddenText(): string[] {
	const upstream = ['upload_refused.json', 'submit_refused.json', 'review_refused_setup.json', 'annotations_plain.json'].map((name) => fixture<{ error: string }>(name).error);
	return [`e2e-mock-token-${'e'.repeat(24)}`, MOCK_URL, 'UPSTREAM_TEXT_MARKER_e2e', 'upstream_unexpected_field_e2e', ...upstream].filter((text) => text.length > 0);
}

export async function expectNoForbiddenText(page: Page): Promise<void> {
	const html = await page.content();
	for (const text of forbiddenText()) expect(html, `page contains forbidden text: ${text.slice(0, 24)}…`).not.toContain(text);
}
