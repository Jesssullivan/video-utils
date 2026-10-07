// axe accessibility scans (WEB_TESTS_S3.md 5.3; metrics W14-W16). Protocol sealed in section 9 of the contract:
// tags wcag2a, wcag2aa, wcag21a, wcag21aa, wcag22aa and best-practice; no rule disabled; nothing excluded; light and
// dark colour schemes; 16 routes + 3 states = 19 scans x 2 = 38. Every violation is recorded; the suite fails only on a
// violation that is not in e2e/a11y-baseline.json (rule + scan + scheme, node count not above the baseline).
// Automated axe results are a measurement of the rules axe can evaluate on synthetic fixtures. They are not a WCAG
// conformance claim and say nothing about screen-reader behaviour. `incomplete` results are counted, never passed.
import AxeBuilder from '@axe-core/playwright';
import type { Page } from '@playwright/test';
import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { expect, ids, open, OUT, ROUTES, test, UNCONFIGURED_URL } from '../tests/e2e-support';

const TAGS = ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa', 'best-practice'];
const SCHEMES = ['light', 'dark'] as const;
const A11Y_OUT = `${OUT}a11y/`;
const BASELINE_FILE = fileURLToPath(new URL('./a11y-baseline.json', import.meta.url));

type BaselineEntry = { route: string; scheme: string; rule_id: string; impact: string | null; wcag_tags: string[]; node_count: number; selectors: string[] };
type Row = BaselineEntry & { scan: string };
const baseline = (JSON.parse(readFileSync(BASELINE_FILE, 'utf8')) as { violations: BaselineEntry[] }).violations;

type Scan = { name: string; route: string; kind: 'route' | 'state'; prepare: (page: Page) => Promise<void> };
const SCANS: Scan[] = [
	...ROUTES.map((route): Scan => ({ name: route.name, route: route.route, kind: 'route', prepare: (page) => open(page, route.path) })),
	{
		name: 'state-upload-refused', route: '/upload (after a typed refusal)', kind: 'state',
		prepare: async (page) => {
			await open(page, '/upload');
			await page.locator('[data-upload-form="true"] input[type="file"]').setInputFiles({ name: 'notes.txt', mimeType: 'text/plain', buffer: Buffer.from('not a video') });
			await page.getByRole('button', { name: 'Upload and admit' }).click();
			await expect(page.locator('[data-upstream-code="upload_type_refused"]')).toBeVisible();
		}
	},
	{
		name: 'state-process-fuller-refused', route: '/sources/[id]/process (FULLER refusal visible)', kind: 'state',
		prepare: async (page) => {
			await open(page, `/sources/${ids.source_plain}/process`);
			await expect(page.locator('[data-author-form="fuller"] [data-refusal-code="capture_interval_required"]')).toBeVisible();
		}
	},
	{
		name: 'state-library-unconfigured', route: '/ (control API unconfigured)', kind: 'state',
		prepare: async (page) => {
			await open(page, '/', UNCONFIGURED_URL);
			await expect(page.locator('[data-error-code="control_api_unconfigured"]')).toBeVisible();
		}
	}
];

type Executed = { scan: string; route: string; scheme: string; violations: number; violation_nodes: number; incomplete: number; incomplete_nodes: number; passes: number; inapplicable: number };
type ScanFile = { axe_version: string; rules: string[]; executed: Executed; rows: Row[] };
const scanFile = (scan: string, scheme: string) => `${A11Y_OUT}${scan}-${scheme}.json`;

for (const scan of SCANS) {
	for (const scheme of SCHEMES) {
		test(`axe ${scan.name} [${scheme}]`, async ({ page }) => {
			await page.emulateMedia({ colorScheme: scheme });
			await scan.prepare(page);
			const results = await new AxeBuilder({ page }).withTags(TAGS).analyze();
			const found: Row[] = results.violations.map((violation) => ({
				scan: scan.name, route: scan.route, scheme, rule_id: violation.id, impact: violation.impact ?? null,
				wcag_tags: violation.tags.filter((tag) => /^wcag|^best-practice$/.test(tag)), node_count: violation.nodes.length,
				selectors: violation.nodes.map((node) => node.target.join(' ')).slice(0, 12)
			}));
			const nodes = (group: Array<{ nodes: unknown[] }>) => group.reduce((sum, rule) => sum + rule.nodes.length, 0);
			const executed: Executed = {
				scan: scan.name, route: scan.route, scheme, violations: results.violations.length, violation_nodes: nodes(results.violations),
				incomplete: results.incomplete.length, incomplete_nodes: nodes(results.incomplete), passes: results.passes.length, inapplicable: results.inapplicable.length
			};
			const rules = [results.violations, results.incomplete, results.passes, results.inapplicable].flatMap((group) => group.map((rule) => rule.id));
			// Results go to disk per scan (a failed scan restarts the worker, so nothing is kept in memory).
			mkdirSync(A11Y_OUT, { recursive: true });
			const file: ScanFile & { tags: string[]; violations: unknown; incomplete: unknown } = { axe_version: results.testEngine.version, tags: TAGS, rules, executed, rows: found, violations: results.violations, incomplete: results.incomplete };
			writeFileSync(scanFile(scan.name, scheme), `${JSON.stringify(file, null, 2)}\n`);
			const outside = found.filter((row) => {
				const allowed = baseline.find((entry) => entry.route === row.route && entry.scheme === row.scheme && entry.rule_id === row.rule_id);
				return !allowed || row.node_count > allowed.node_count;
			});
			expect(outside.map((row) => `${row.rule_id} (${row.impact}) x${row.node_count}: ${row.selectors.slice(0, 3).join(' ; ')}`), `violations outside e2e/a11y-baseline.json on ${scan.route} [${scheme}]`).toEqual([]);
		});
	}
}

test.afterAll(() => {
	// Rebuilt from the per-scan files after every worker; the last write covers every scan of this run
	// (global setup clears the directory before an a11y run, so a missing file means that scan did not execute).
	const files: ScanFile[] = [];
	for (const scan of SCANS) {
		for (const scheme of SCHEMES) {
			if (existsSync(scanFile(scan.name, scheme))) files.push(JSON.parse(readFileSync(scanFile(scan.name, scheme), 'utf8')) as ScanFile);
		}
	}
	if (files.length === 0) return;
	const rows = files.flatMap((file) => file.rows);
	const executed = files.map((file) => file.executed);
	const byImpact: Record<string, number> = {};
	for (const row of rows) byImpact[row.impact ?? 'unknown'] = (byImpact[row.impact ?? 'unknown'] ?? 0) + 1;
	const violations = rows.map(({ scan: _scan, ...entry }) => entry);
	const summary = {
		claim_class: 'measurement',
		protocol: { tags: TAGS, schemes: SCHEMES, disabled_rules: [], excluded_selectors: [], scans_planned: SCANS.length * SCHEMES.length },
		axe_version: files[0].axe_version,
		axe_rules_evaluated_count: new Set(files.flatMap((file) => file.rules)).size,
		scans_executed: executed.length,
		scans_with_violations: executed.filter((row) => row.violations > 0).length,
		violations_total: rows.length,
		violation_nodes_total: rows.reduce((sum, row) => sum + row.node_count, 0),
		violations_by_impact: byImpact,
		violations_outside_baseline: rows.filter((row) => {
			const allowed = baseline.find((entry) => entry.route === row.route && entry.scheme === row.scheme && entry.rule_id === row.rule_id);
			return !allowed || row.node_count > allowed.node_count;
		}).length,
		axe_incomplete_count: executed.reduce((sum, row) => sum + row.incomplete, 0),
		axe_incomplete_nodes: executed.reduce((sum, row) => sum + row.incomplete_nodes, 0),
		baseline_entries: baseline.length,
		wcag_conformance: null,
		screen_reader_acceptance: null,
		executed,
		violations
	};
	writeFileSync(`${A11Y_OUT}summary.json`, `${JSON.stringify(summary, null, 2)}\n`);
	// A candidate baseline is always written next to the summary; committing it is a separate, recorded step.
	writeFileSync(`${A11Y_OUT}baseline-candidate.json`, `${JSON.stringify({ schema_version: 1, violations }, null, 2)}\n`);
});
