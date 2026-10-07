// The carrier directory a consumer takes carries no beacon or telemetry string
// (BC1 on the portal; the design's dist scan). Bare cdn-cgi is allowed: the
// portal's Access sign-out uses /cdn-cgi/access/logout.
import assert from 'node:assert/strict';
import { readdirSync, readFileSync, statSync } from 'node:fs';
import path from 'node:path';
import { describe, it } from 'node:test';

const REFUSED = ['faro', 'cloudflareinsights', 'data-cf-beacon', 'cdn-cgi/trace'];
const dir = path.resolve(process.argv[2] ?? '');

function walk(d) {
	return readdirSync(d).flatMap((name) => {
		const p = path.join(d, name);
		return statSync(p).isDirectory() ? walk(p) : [p];
	});
}

describe('the carrier', () => {
	const files = walk(dir);

	it('holds the theme, the sources, the fonts, the manifest and the notice', () => {
		const rel = files.map((f) => path.relative(dir, f)).sort();
		for (const want of [
			'NOTICE',
			'fonts/FiraCodeNerdFontMono-Bold.woff2',
			'fonts/FiraCodeNerdFontMono-Regular.woff2',
			'fonts/OFL.txt',
			'theme/base.css',
			'theme/fonts.css',
			'theme/fouc.mjs',
			'theme/palette.ts',
			'theme/tailwind.css',
			'theme/theme-xoxd.css',
			'xoxd-theme.json',
		]) {
			assert.ok(rel.includes(want), want);
		}
	});

	it('carries none of the refused beacon strings', () => {
		for (const file of files.filter((f) => !f.endsWith('.woff2'))) {
			const text = readFileSync(file, 'utf8').toLowerCase();
			for (const word of REFUSED) assert.ok(!text.includes(word), `${path.relative(dir, file)} contains ${word}`);
		}
	});
});
