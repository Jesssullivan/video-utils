// Stops the in-process static server (the only thing global setup started; R-N11: own processes only) and writes
// <SITE_VERIFY_OUT_DIR>/browser-summary.json from the per-case files (SITE_VERIFY_S3.md section 4.2, metrics V1 to V7).
// A case or scan without a file did not execute and counts against its denominator.
import { existsSync, readdirSync, readFileSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { createRequire } from 'node:module';
import { browserCacheEntries } from './global-setup';
import { BUILD_INTENDED_EXTERNAL, ROUTES, VIEWPORTS, outDir } from './routes';
import { SKIP_ENV } from './support';

type Started = { close: () => Promise<void> };
type Json = Record<string, any>; // eslint-disable-line @typescript-eslint/no-explicit-any

const read = (directory: string): Json[] =>
	existsSync(directory)
		? readdirSync(directory)
				.filter((name) => name.endsWith('.json'))
				.sort()
				.map((name) => JSON.parse(readFileSync(join(directory, name), 'utf8')) as Json)
		: [];

const version = (name: string): string | null => {
	try {
		const require = createRequire(import.meta.url);
		return (require(`${name}/package.json`) as { version: string }).version;
	} catch {
		return null;
	}
};

export function summarize(out: string): Json {
	const run = existsSync(join(out, 'run.json')) ? (JSON.parse(readFileSync(join(out, 'run.json'), 'utf8')) as Json) : {};
	const R = ROUTES.length;
	const smoke = read(join(out, 'smoke'));
	const skip = read(join(out, 'skip-link'));
	const scans = read(join(out, 'a11y'));
	const executedScans = scans.filter((scan) => scan.executed === true);
	const external = [...new Set([...smoke, ...scans].flatMap((entry) => (entry.external_requests ?? []) as string[]))].sort();
	const warnings = smoke.flatMap((entry) => ((entry.warnings ?? []) as Json[]).map((warning) => ({ case: entry.case, ...warning })));
	const overflowCases = smoke.filter((entry) => entry.overflow_px > 0);
	const consoleErrors = smoke.reduce((sum, entry) => sum + (entry.console_errors?.length ?? 0), 0);
	const pageErrors = smoke.reduce((sum, entry) => sum + (entry.page_errors?.length ?? 0), 0);
	const allowance = smoke.reduce((sum, entry) => sum + (entry.expected_document_404?.length ?? 0), 0);
	const violations = executedScans.reduce((sum, scan) => sum + scan.violation_count, 0);
	const outside = executedScans.reduce((sum, scan) => sum + scan.violations_outside_baseline, 0);
	const smokeExpected = R * VIEWPORTS.length;
	const scansExpected = 4 * R + 2;
	const skipCode = process.env[SKIP_ENV] ?? null;
	const cacheAfter = browserCacheEntries();
	const cacheBefore = (run.browser_cache_entries_before ?? []) as string[];
	const newCacheEntries = cacheAfter.filter((name) => !cacheBefore.includes(name));
	const metric = (numerator: number, denominator: number, pass: boolean) => ({ numerator, denominator, pass });
	return {
		schema_version: 1,
		lane: 'site_verify',
		generated_at_utc: new Date().toISOString(),
		skip_code: skipCode,
		browser_ladder_step: run.browser_ladder_step ?? null,
		browser_source: run.browser_source ?? null,
		browser_engines: ['chromium'],
		browser_version: smoke[0]?.browser_version ?? null,
		browser_cache_entries_before: cacheBefore,
		browser_cache_entries_after: cacheAfter,
		browser_cache_new_entries: newCacheEntries,
		browser_download_bytes: newCacheEntries.length === 0 ? 0 : null,
		playwright_version: version('@playwright/test'),
		axe_core_playwright_version: version('@axe-core/playwright'),
		axe_version: executedScans[0]?.axe_version ?? null,
		server_kind: 'local_static_emulation',
		pages_equivalence: 'inferred',
		zoom_method: 'viewport_emulation',
		route_count: R,
		routes: ROUTES,
		viewports: VIEWPORTS,
		smoke: {
			cases_expected: smokeExpected,
			cases_executed: smoke.length,
			cases_passed: smoke.filter((entry) => entry.passed === true).length,
			failing_cases: smoke.filter((entry) => entry.passed !== true).map((entry) => ({ case: entry.case, failed: entry.failed })),
			console_errors: consoleErrors,
			page_errors: pageErrors,
			expected_document_404_allowance: allowance,
			warnings_count: warnings.length,
			warnings,
			overflow_cases: overflowCases.map((entry) => entry.case),
			max_overflow_px: smoke.reduce((max, entry) => Math.max(max, entry.overflow_px ?? 0), 0),
			start_module_200: smoke.filter((entry) => entry.start_module_status === 200).length,
			compact_header_after_scroll: {
				true: smoke.filter((entry) => entry.compact_header_after_scroll === true).length,
				false: smoke.filter((entry) => entry.compact_header_after_scroll === false).length,
				not_scrollable: smoke.filter((entry) => entry.compact_header_after_scroll === null).length
			},
			requests_total: smoke.reduce((sum, entry) => sum + (entry.requests_total ?? 0), 0)
		},
		external_requests_observed: external,
		build_intended_external: BUILD_INTENDED_EXTERNAL,
		external_fetched: 0,
		skip_link: { expected: R, executed: skip.length, passed: skip.filter((entry) => entry.passed === true).length },
		a11y: {
			scans_expected: scansExpected,
			scans_executed: executedScans.length,
			mode_assertion_held: scans.filter((scan) => scan.mode_assertion === true).length,
			violations_total: violations,
			violation_nodes: executedScans.reduce((sum, scan) => sum + scan.violation_nodes, 0),
			violations_outside_baseline: outside,
			violation_rules: [...new Set(executedScans.flatMap((scan) => (scan.violations as Json[]).map((row) => row.rule_id)))].sort(),
			incomplete_total: executedScans.reduce((sum, scan) => sum + scan.incomplete_count, 0),
			incomplete_nodes: executedScans.reduce((sum, scan) => sum + scan.incomplete_nodes, 0),
			incomplete_rules: [...new Set(executedScans.flatMap((scan) => (scan.incomplete as Json[]).map((row) => row.rule_id)))].sort(),
			rules_evaluated_per_scan_max: executedScans.reduce((max, scan) => Math.max(max, scan.rules_evaluated.length), 0),
			scans: scans.map((scan) => ({
				scan: scan.scan,
				route: scan.route,
				scheme: scan.scheme,
				width: scan.width,
				state: scan.state,
				mode_assertion: scan.mode_assertion,
				violations: scan.violation_count ?? null,
				incomplete: scan.incomplete_count ?? null,
				passes: scan.passes ?? null
			}))
		},
		metrics: {
			V1: metric(smoke.filter((entry) => entry.passed === true).length, smokeExpected, smoke.filter((entry) => entry.passed === true).length === smokeExpected),
			V2: { console_errors: consoleErrors, page_errors: pageErrors, expected_document_404_allowance: allowance, pass: smoke.length === smokeExpected && consoleErrors === 0 && pageErrors === 0 },
			V3: { overflow_cases: overflowCases.length, denominator: smokeExpected, max_overflow_px: smoke.reduce((max, entry) => Math.max(max, entry.overflow_px ?? 0), 0), pass: smoke.length === smokeExpected && overflowCases.length === 0 },
			V4: { observed: external, intended: BUILD_INTENDED_EXTERNAL, fetched: 0, pass: smoke.length === smokeExpected && external.length === 0 },
			V5: metric(skip.filter((entry) => entry.passed === true).length, R, skip.filter((entry) => entry.passed === true).length === R),
			V6: metric(executedScans.filter((scan) => scan.mode_assertion === true).length, scansExpected, executedScans.filter((scan) => scan.mode_assertion === true).length === scansExpected),
			V7: { violations: violations, outside_baseline: outside, incomplete: executedScans.reduce((sum, scan) => sum + scan.incomplete_count, 0), pass: executedScans.length === scansExpected && outside === 0 }
		},
		claim_class: 'automated_checks_only',
		wcag_conformance: 'not_claimed',
		screen_reader_check: 'not_performed',
		keyboard_walkthrough: 'not_performed',
		real_device_check: 'not_performed',
		non_default_themes_scanned: false,
		reduced_motion_verified: false,
		contrast_basis: 'axe_color_contrast_rule_only',
		response_headers_on_pages: 'unknown',
		deployed: false,
		served_check: 'not_performed'
	};
}

export default async function globalTeardown(): Promise<void> {
	const holder = globalThis as unknown as { __siteVerifyServer?: Started };
	const server = holder.__siteVerifyServer;
	holder.__siteVerifyServer = undefined;
	if (server) await server.close();
	const out = outDir();
	writeFileSync(join(out, 'browser-summary.json'), `${JSON.stringify(summarize(out), null, 2)}\n`);
}
