// Shared readers for the tests: files are read from the tree the test runs in
// (Bazel copies every data file beside the test's own package).
import { readFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

export const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
export const read = (file) => readFileSync(path.join(ROOT, file), 'utf8');

/** A `export const NAME = [ ... ] as const;` string list out of palette.ts. */
export function constList(src, name) {
	const m = new RegExp(`export const ${name} = \\[([\\s\\S]*?)\\] as const;`).exec(src);
	if (!m) throw new Error(`palette.ts has no ${name}`);
	return [...m[1].matchAll(/'([^']+)'/g)].map((x) => x[1]);
}

/** The pinnedTokens object out of palette.ts, as a Map. */
export function pinnedTokens(src) {
	const m = /export const pinnedTokens = \{([\s\S]*?)\} as const;/.exec(src);
	if (!m) throw new Error('palette.ts has no pinnedTokens');
	return new Map([...m[1].matchAll(/'(--[^']+)': '([^']+)'/g)].map((x) => [x[1], x[2]]));
}

/** The declarations of one `[data-theme='<id>']` block, whitespace collapsed. */
export function themeTokens(id, css) {
	const start = css.indexOf(`[data-theme='${id}']`);
	if (start < 0) throw new Error(`no [data-theme='${id}'] block`);
	const open = css.indexOf('{', start);
	let depth = 0;
	let end = open;
	for (let i = open; i < css.length; i += 1) {
		if (css[i] === '{') depth += 1;
		if (css[i] === '}') {
			depth -= 1;
			if (depth === 0) {
				end = i;
				break;
			}
		}
	}
	const body = css.slice(open + 1, end).replace(/\/\*[\s\S]*?\*\//g, '');
	const tokens = new Map();
	for (const declaration of body.split(';')) {
		const colon = declaration.indexOf(':');
		if (colon < 0) continue;
		const name = declaration.slice(0, colon).trim();
		if (!name.startsWith('--')) continue;
		tokens.set(name, declaration.slice(colon + 1).replace(/\s+/g, ' ').trim());
	}
	return tokens;
}
