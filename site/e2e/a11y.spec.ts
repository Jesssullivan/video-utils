// axe scans of the built site (SITE_VERIFY_S3.md section 6; metrics V6 and V7). Protocol sealed in the contract:
// tags wcag2a, wcag2aa, wcag21a, wcag21aa, wcag22aa and best-practice; no rule disabled; nothing excluded; colour
// modes light and dark set through the site's stored preference plus the matching media emulation, each asserted on
// html[data-mode] before analysis; widths w1280 and w375; plus the mobile navigation dialog open at w375 per mode.
// Total 4R + 2 scans. A violation fails unless e2e/a11y-baseline.json lists it with a reason. Automated-check results
// only: not a WCAG conformance claim, and nothing about screen readers. `incomplete` results are counted, never passed.
import AxeBuilder from '@axe-core/playwright';
import { expect, test, type Page } from '@playwright/test';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { ROUTES, viewport, writeJson, type Route } from './routes';
import { openContext, skipWhenNoBrowser, visit } from './support';

export const TAGS = ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa', 'best-practice'];
const MODES = ['light', 'dark'] as const;
const WIDTHS = ['w1280', 'w375'] as const;
type Mode = (typeof MODES)[number];

type BaselineEntry = { rule_id: string; route: string; scheme: string; width: string; node_count: number; reason: string };
const baseline = (JSON.parse(readFileSync(fileURLToPath(new URL('./a11y-baseline.json', import.meta.url)), 'utf8')) as { violations: BaselineEntry[] })
	.violations;

type Scan = { id: string; route: Route; width: string; state: string | null; prepare?: (page: Page) => Promise<void> };
const home = ROUTES.find((route) => route.path === '/') ?? ROUTES[0];
const SCANS: Scan[] = [
	...ROUTES.flatMap((route) => WIDTHS.map((width): Scan => ({ id: `${route.id}-${width}`, route, width, state: null }))),
	{
		id: 'state-mobile-nav-open-w375',
		route: home,
		width: 'w375',
		state: 'mobile_navigation_dialog_open',
		prepare: async (page) => {
			await page.locator('button[aria-label="Open navigation"]:visible').first().click();
			await expect(page.getByRole('dialog')).toBeVisible();
			await page.waitForTimeout(400); // let the dialog's open transition settle before contrast is evaluated
		}
	}
];

const nodes = (group: Array<{ nodes: unknown[] }>) => group.reduce((sum, rule) => sum + rule.nodes.length, 0);

test.beforeEach(skipWhenNoBrowser);

for (const scan of SCANS) {
	for (const mode of MODES) {
		test(`axe ${scan.route.path} ${scan.state ?? 'route'} [${scan.width}, ${mode}]`, async ({ browser }) => {
			const view = viewport(scan.width);
			const { context, page, traffic } = await openContext(browser, view, { colorScheme: mode, storedMode: mode as Mode });
			try {
				await visit(page, scan.route.path);
				const observedMode = await page.evaluate(() => document.documentElement.getAttribute('data-mode'));
				const modeAssertion = observedMode === mode;
				const record: Record<string, unknown> = {
					scan: `${scan.id}-${mode}`,
					route: scan.route.path,
					scheme: mode,
					width: scan.width,
					state: scan.state,
					mode_assertion: modeAssertion,
					observed_mode: observedMode,
					theme: await page.evaluate(() => document.documentElement.getAttribute('data-theme')),
					external_requests: traffic.external
				};
				if (!modeAssertion) {
					writeJson('a11y', `${scan.id}-${mode}`, { ...record, executed: false });
					expect(observedMode, 'mode assertion failed: a scan of the wrong mode is a failed scan').toBe(mode);
				}
				if (scan.prepare) await scan.prepare(page);
				const results = await new AxeBuilder({ page }).withTags(TAGS).analyze();
				const violations = results.violations.map((violation) => ({
					rule_id: violation.id,
					impact: violation.impact ?? null,
					tags: violation.tags,
					node_count: violation.nodes.length,
					targets: violation.nodes.map((node) => node.target.join(' ')).slice(0, 12),
					summaries: violation.nodes.map((node) => (node.failureSummary ?? '').slice(0, 300)).slice(0, 4)
				}));
				const outside = violations.filter((row) => {
					const allowed = baseline.find(
						(entry) => entry.rule_id === row.rule_id && entry.route === scan.route.path && entry.scheme === mode && entry.width === scan.width
					);
					return !allowed || row.node_count > allowed.node_count || !allowed.reason;
				});
				writeJson('a11y', `${scan.id}-${mode}`, {
					...record,
					executed: true,
					axe_version: results.testEngine.version,
					tags: TAGS,
					rules_evaluated: [results.violations, results.incomplete, results.passes, results.inapplicable].flatMap((group) => group.map((rule) => rule.id)).sort(),
					violations,
					violation_count: results.violations.length,
					violation_nodes: nodes(results.violations),
					violations_outside_baseline: outside.length,
					incomplete: results.incomplete.map((rule) => ({ rule_id: rule.id, node_count: rule.nodes.length, targets: rule.nodes.map((node) => node.target.join(' ')).slice(0, 12) })),
					incomplete_count: results.incomplete.length,
					incomplete_nodes: nodes(results.incomplete),
					passes: results.passes.length,
					inapplicable: results.inapplicable.length
				});
				expect(
					outside.map((row) => `${row.rule_id} (${row.impact}) x${row.node_count}: ${row.targets.slice(0, 3).join(' ; ')}`),
					`violations outside e2e/a11y-baseline.json on ${scan.route.path} [${scan.width}, ${mode}]`
				).toEqual([]);
			} finally {
				await context.close();
			}
		});
	}
}
