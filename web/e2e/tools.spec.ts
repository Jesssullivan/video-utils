// The tools page lists every typed tool (WEB_TESTS_S3.md 5.2; metric W11). The number has one source:
// program/tools.json, projected by the real control API into capabilities.json at generation time;
// tests/test_web_house_stack_s3.py asserts the registry holds 42 tools and that the fixture names match it.
import { expect, expectNoForbiddenText, fixture, open, record, test } from '../tests/e2e-support';

type Capabilities = { tool_count: number; pilot_tool_count: number; tools: Array<{ name: string; capability: unknown }>; areas: Array<{ area: string; tools: string[] }>; models: Array<{ model_id: string }> };
const capabilities = fixture<Capabilities>('capabilities.json');

test('lists 42 tools: rendered cards = data-tool-count = fixture tool_count = 42', async ({ page, mock }) => {
	await open(page, '/tools');
	await expect(page.locator('main#main [data-tools-page="true"]')).toBeVisible();
	await expect(page.getByRole('heading', { level: 1, name: 'Typed tools and models' })).toBeVisible();
	const count = page.locator('[data-tool-count]');
	await expect(count).toHaveAttribute('data-tool-count', '42');
	const cards = page.locator('[data-tool]');
	await expect(cards).toHaveCount(42);
	expect(capabilities.tool_count).toBe(42);
	expect(capabilities.tools.length).toBe(42);
	const rendered = await cards.evaluateAll((elements) => elements.map((element) => element.getAttribute('data-tool') ?? ''));
	expect([...rendered].sort()).toEqual(capabilities.tools.map((tool) => tool.name).sort());
	expect(new Set(rendered).size).toBe(42);
	await expect(page.locator('section[data-area]')).toHaveCount(capabilities.areas.length);
	expect(await mock.nonGet()).toEqual([]);
	await expectNoForbiddenText(page);
	record('tools', 'W11_tools_listed', { rendered: rendered.length, data_tool_count: 42, fixture_tool_count: capabilities.tool_count });
});

test('capability metadata and model rows are registry views: unknown stays unknown, nothing runs', async ({ page }) => {
	await open(page, '/tools');
	const withCapability = capabilities.tools.filter((tool) => tool.capability !== null).length;
	expect(withCapability).toBe(capabilities.pilot_tool_count);
	await expect(page.locator('[data-tool] [data-capability="true"]')).toHaveCount(withCapability);
	await expect(page.locator('tr[data-model]')).toHaveCount(capabilities.models.length);
	// Local model presence is never checked by this page.
	const presence = await page.locator('tr[data-model] td:last-child').allInnerTexts();
	for (const text of presence) expect(text.trim()).toBe('not checked');
	await expect(page.locator('[data-unknowns-block="true"]')).toHaveAttribute('data-unknown-count', '3');
	await expect(page.locator('main form, main button')).toHaveCount(0);
});
