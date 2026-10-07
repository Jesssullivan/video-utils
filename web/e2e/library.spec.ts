// Clip library `/` (WEB_TESTS_S3.md 5.2). Synthetic fixtures; no fact about a recording.
import { expect, expectNoForbiddenText, fixture, ids, open, record, test } from '../tests/e2e-support';

type Source = { source_artifact_id: string; duration_seconds: number | null; duration_seconds_reason: string; source_id: string | null };
const sources = fixture<{ sources: Source[] }>('sources.json').sources;

test('lists every fixture source and links to its page', async ({ page, mock }) => {
	await open(page, '/');
	await expect(page.getByRole('heading', { level: 1, name: 'Admitted sources' })).toBeVisible();
	const rows = page.locator('tr[data-source-artifact-id]');
	await expect(rows).toHaveCount(sources.length);
	for (const source of sources) await expect(page.locator(`tr[data-source-artifact-id="${source.source_artifact_id}"]`)).toHaveCount(1);
	await expectNoForbiddenText(page);
	record('library', 'sources_listed', { listed: await rows.count(), fixture: sources.length });

	await page.locator(`tr[data-source-artifact-id="${ids.source_reviewed}"] a`).click();
	await expect(page).toHaveURL(new RegExp(`/sources/${ids.source_reviewed}$`));
	await expect(page.locator('[data-source-facts="true"]')).toBeVisible();
	expect(await mock.nonGet()).toEqual([]);
});

test('a source with a null duration shows an explicit Unknown with its reason, not 0 or blank', async ({ page }) => {
	const unknown = sources.filter((source) => source.duration_seconds === null);
	expect(unknown.length).toBeGreaterThan(0);
	await open(page, '/');
	for (const source of unknown) {
		const cell = page.locator(`tr[data-source-artifact-id="${source.source_artifact_id}"] td`).nth(5);
		await expect(cell.locator('[data-unknown="true"]')).toHaveText('Unknown');
		await expect(cell.locator('[data-unknown-reason="true"]')).toContainText(source.duration_seconds_reason);
		const text = (await cell.innerText()).trim();
		expect(text).not.toMatch(/^0(\.0+)?$/);
		expect(text.length).toBeGreaterThan(0);
		// The original source id is unknown for the same row and says so too.
		await expect(page.locator(`tr[data-source-artifact-id="${source.source_artifact_id}"] td`).nth(2).locator('[data-unknown="true"]')).toHaveText('Unknown');
	}
	const known = sources.filter((source) => source.duration_seconds !== null);
	for (const source of known) {
		await expect(page.locator(`tr[data-source-artifact-id="${source.source_artifact_id}"] td`).nth(5)).toHaveText((source.duration_seconds as number).toFixed(3));
	}
});
