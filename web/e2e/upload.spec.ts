// Upload refusal (WEB_TESTS_S3.md 5.2). The mock replays the control API's recorded `uploads_disabled` refusal
// and stores nothing; an unsupported type is refused in the page before any request is made.
import { expect, expectNoForbiddenText, fixture, open, record, test } from '../tests/e2e-support';

const UPLOADS_DISABLED_TEXT = 'Uploads are off. The operator enables them by starting the control API with --allow-uploads.';
const TYPE_REFUSED_TEXT = 'Only .mov, .mp4, .m4v, .mkv or .webm video files are accepted.';
// Synthetic bytes with a QuickTime signature; not media and never decoded.
const FAKE_MOV = Buffer.concat([Buffer.from([0, 0, 0, 20]), Buffer.from('ftypqt  ', 'ascii'), Buffer.alloc(1024, 7)]);

test('with uploads disabled, submitting shows the typed code uploads_disabled and its refusal text', async ({ page, mock, problems }) => {
	problems.expectConsoleError(/\[\/api\/uploads\]/, 'the browser logs the typed 403 refusal of POST /api/uploads');
	const recordedRefusal = fixture<{ code: string; error: string }>('upload_refused.json');
	expect(recordedRefusal.code).toBe('uploads_disabled');
	await open(page, '/upload');
	await expect(page.getByRole('heading', { level: 1, name: 'Add a take' })).toBeVisible();
	const submit = page.getByRole('button', { name: 'Upload and admit' });
	await expect(submit).toBeDisabled();
	await page.locator('[data-upload-form="true"] input[type="file"]').setInputFiles({ name: 'take.mov', mimeType: 'video/quicktime', buffer: FAKE_MOV });
	await expect(submit).toBeEnabled();
	await submit.click();

	const refusal = page.locator('[data-upstream-code="uploads_disabled"]');
	await expect(refusal).toBeVisible();
	await expect(refusal).toHaveAttribute('data-error-code', 'control_api_refused');
	await expect(refusal.locator('code').first()).toHaveText('uploads_disabled');
	await expect(refusal).toContainText(UPLOADS_DISABLED_TEXT);
	await expect(page.locator('[data-admitted]')).toHaveCount(0);
	// The upstream `error` sentence is never rendered; only the typed code and the app's own text are.
	await expect(page.locator('body')).not.toContainText(recordedRefusal.error);
	await expectNoForbiddenText(page);

	const log = await mock.log();
	const uploads = log.requests.filter((entry) => entry.path === '/api/v1/uploads');
	expect(uploads.length).toBe(1);
	expect(uploads[0]).toMatchObject({ method: 'POST', status: 403, file: 'upload_refused.json', body_bytes: FAKE_MOV.length, authorized: true });
	expect(log.stored_upload_bytes).toBe(0);
	record('upload', 'uploads_disabled', { upload_requests: uploads.length, received_bytes: uploads[0].body_bytes, stored_bytes: log.stored_upload_bytes });
});

test('an unsupported extension shows upload_type_refused and sends nothing', async ({ page, mock }) => {
	await open(page, '/upload');
	await page.locator('[data-upload-form="true"] input[type="file"]').setInputFiles({ name: 'notes.txt', mimeType: 'text/plain', buffer: Buffer.from('not a video') });
	await page.getByRole('button', { name: 'Upload and admit' }).click();
	const refusal = page.locator('[data-upstream-code="upload_type_refused"]');
	await expect(refusal).toBeVisible();
	await expect(refusal.locator('code').first()).toHaveText('upload_type_refused');
	await expect(refusal).toContainText(TYPE_REFUSED_TEXT);
	await expect(page.locator('[data-admitted]')).toHaveCount(0);
	const log = await mock.log();
	expect(log.requests.filter((entry) => entry.non_get)).toEqual([]);
	expect(log.stored_upload_bytes).toBe(0);
	record('upload', 'upload_type_refused', { upload_requests: 0, stored_bytes: log.stored_upload_bytes });
});

test('a file whose browser type is empty falls back to its extension; an extension outside the list is still refused', async ({ page, mock, problems }) => {
	problems.expectConsoleError(/\[\/api\/uploads\]/, 'the browser logs the typed 403 refusal of POST /api/uploads');
	await open(page, '/upload');
	const input = page.locator('[data-upload-form="true"] input[type="file"]');
	await input.setInputFiles({ name: 'take.exe', mimeType: '', buffer: FAKE_MOV });
	await page.getByRole('button', { name: 'Upload and admit' }).click();
	await expect(page.locator('[data-upstream-code="upload_type_refused"]')).toBeVisible();
	expect(await mock.nonGet()).toEqual([]);
	await input.setInputFiles({ name: 'take.MKV', mimeType: '', buffer: FAKE_MOV });
	await page.getByRole('button', { name: 'Upload and admit' }).click();
	await expect(page.locator('[data-upstream-code="uploads_disabled"]')).toBeVisible();
	expect((await mock.nonGet()).map((entry) => entry.path)).toEqual(['/api/v1/uploads']);
});
