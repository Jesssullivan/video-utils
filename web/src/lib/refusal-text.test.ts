// Plain-language text for typed refusal codes (WEB_TESTS_S3.md 5.1; metric W7).
// The table is read from the module source so a code added there is covered without editing this test.
import { mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';
import { HOST_PATH_MARKERS } from '../../tests/fixtures';
import { processingText } from './components/processing/processing-text';
import { refusalText } from './refusal-text';

const read = (relative: string) => readFileSync(fileURLToPath(new URL(relative, import.meta.url)), 'utf8');
const FALLBACK = refusalText('zz_code_that_is_not_in_the_table');
const LANE_FALLBACK = processingText('zz_code_that_is_not_in_the_table');

function tableCodes(source: string): string[] {
	const start = source.indexOf('const TEXT');
	const block = source.slice(start, source.indexOf('\n};', start));
	return [...block.matchAll(/^\t([a-z_]{1,64}):/gm)].map((match) => match[1]);
}

const CODES = tableCodes(read('./refusal-text.ts'));
const LANE_CODES = tableCodes(read('./components/processing/processing-text.ts'));

describe('refusalText', () => {
	it('maps every table code to its own non-empty text, never the fallback', () => {
		expect(CODES.length).toBeGreaterThanOrEqual(40);
		expect(new Set(CODES).size).toBe(CODES.length);
		for (const code of CODES) {
			const text = refusalText(code);
			expect(text.trim().length, code).toBeGreaterThan(10);
			expect(text, code).not.toBe(FALLBACK);
		}
	});

	it('maps an unknown code to the fallback, which names no code or upstream text', () => {
		expect(FALLBACK.length).toBeGreaterThan(10);
		for (const code of ['', 'unknown', 'UPLOADS_DISABLED', 'uploads_disabled ', 'x'.repeat(65), 'internal_error']) expect(refusalText(code)).toBe(FALLBACK);
	});

	// KNOWN SOURCE DEFECT, reported to root (web_tests-root-requests.json, code refusal_text_prototype_key):
	// both tables are plain objects read with `TEXT[code] ?? fallback`, so a code that names an Object.prototype
	// member and matches ^[a-z_]{1,64}$ ("constructor", "__proto__") returns that member instead of the fallback.
	// `it.fails` keeps the suite green while the defect exists and turns red as soon as the source is fixed.
	it.fails('known defect: refusalText returns the fallback string for Object.prototype member names', () => {
		for (const code of ['constructor', '__proto__']) expect(refusalText(code)).toBe(FALLBACK);
	});
	it.fails('known defect: processingText returns the fallback string for Object.prototype member names', () => {
		for (const code of ['constructor', '__proto__']) expect(processingText(code)).toBe(LANE_FALLBACK);
	});

	it('contains no upstream passthrough placeholder, host path, URL or environment variable name', () => {
		const envName = ['VIDEO', 'UTILS'].join('_');
		for (const code of [...CODES, 'zz_fallback']) {
			const text = refusalText(code);
			expect(text, code).not.toMatch(/\$\{|%s|%d|\{\{|\{error\}|\{message\}|undefined|\[object|NaN/);
			expect(text, code).not.toMatch(/https?:\/\//);
			expect(text, code).not.toContain(envName);
			for (const marker of HOST_PATH_MARKERS) expect(text, code).not.toContain(marker);
		}
	});

	it('states no note-correctness or listening verdict', () => {
		for (const code of CODES) expect(refusalText(code), code).not.toMatch(/missed note|wrong note|extra note|sounds (good|better|worse)/i);
	});
});

describe('codes referenced by the form builders, the option builder and the auth gate', () => {
	const literal = (source: string, pattern: RegExp) => [...new Set([...source.matchAll(pattern)].map((match) => match[1]))].sort();
	const formCodes = literal(read('./server/processing/forms.ts'), /code: '([a-z_]+)'/g);
	const optionCodes = literal(read('./server/processing/options.ts'), /'((?:capture_interval_required|tool_pending_admission|profile_source_mismatch|unreviewed_trial|shelf_not_exposed))'/g);
	const gateCodes = literal(read('./server/auth/gate.js'), /'(bff_[a-z_]+)'/g);

	it('finds the expected referenced codes', () => {
		expect(formCodes).toEqual(['interval_required', 'invalid_form_key', 'invalid_review_id', 'run_required']);
		expect(optionCodes).toEqual(['capture_interval_required', 'profile_source_mismatch', 'shelf_not_exposed', 'tool_pending_admission', 'unreviewed_trial']);
		expect(gateCodes).toEqual(['bff_auth_unconfigured', 'bff_host_refused', 'bff_identity_refused']);
	});

	it('every gate code has table text (the gate answers with the code and a fixed message only)', () => {
		for (const code of gateCodes) expect(refusalText(code), code).not.toBe(FALLBACK);
	});

	it('records which builder codes are mapped; unmapped ones always carry an inline message', () => {
		const rows = [...formCodes.map((code) => ({ code, origin: 'forms.ts' })), ...optionCodes.map((code) => ({ code, origin: 'options.ts' })), ...gateCodes.map((code) => ({ code, origin: 'auth/gate.js' }))].map((row) => ({
			...row,
			refusal_text: refusalText(row.code) !== FALLBACK ? 'mapped' : 'unmapped',
			processing_text: processingText(row.code) !== LANE_FALLBACK ? 'mapped' : 'unmapped',
			// forms.ts returns {code, message}; options.ts returns {refusal_code, reason}: both are rendered with the code.
			inline_message: row.origin !== 'auth/gate.js'
		}));
		for (const row of rows) {
			const shownWithMessage = row.refusal_text === 'mapped' || row.processing_text === 'mapped' || row.inline_message;
			expect(shownWithMessage, row.code).toBe(true);
		}
		const report = {
			claim_class: 'contract',
			table_codes: CODES.length,
			table_codes_non_fallback: CODES.filter((code) => refusalText(code) !== FALLBACK).length,
			processing_table_codes: LANE_CODES.length,
			referenced_codes: rows.length,
			referenced: rows,
			unmapped_in_both_tables: rows.filter((row) => row.refusal_text === 'unmapped' && row.processing_text === 'unmapped').map((row) => row.code)
		};
		const out = fileURLToPath(new URL('../../../artifacts/s2/web_tests/unit/', import.meta.url));
		mkdirSync(out, { recursive: true });
		writeFileSync(`${out}refusal-codes.json`, `${JSON.stringify(report, null, 2)}\n`);
		expect(report.table_codes_non_fallback).toBe(report.table_codes);
	});
});
