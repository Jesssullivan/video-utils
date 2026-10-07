// The palette carrier, re-derived (ported from xoxd.ai src/lib/theme/palette.test.ts
// at 4fd966f). Every number is recomputed through scripts/lib/color-contrast.mjs;
// nothing in palette.ts is trusted.
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { describe, it } from 'node:test';

import { readPalette } from '../scripts/build-theme-css.mjs';
import { contrastRatio, formatRgb, parseCssColor, roundRatio } from '../scripts/lib/color-contrast.mjs';
import { constList, pinnedTokens, read } from './lib.mjs';

const src = read('theme/palette.ts');
const css = read('theme/theme-xoxd.css');
const { families, palette: rows } = readPalette(src);
const palette = Object.fromEntries(families.map((f) => [f, Object.fromEntries(rows[f].map((r) => [r.shade, r]))]));
const FAMILIES = constList(src, 'FAMILIES');
const SHADES = [50, 100, 200, 300, 400, 500, 600, 700, 800, 900, 950];
const allTokenNames = FAMILIES.flatMap((family) => SHADES.map((shade) => `${family}-${shade}`));

// The palette block of xoxd.ai src/lib/theme/palette.ts at 4fd966f, the carrier
// this module lifted (from `export const palette` to its closing brace).
const XOXD_AI_PALETTE_BLOCK_SHA256 = '15eaa6bb64447e61e2e023ae2183d8b1096544703ee264a8d756dd58a0097bce';

describe('the carrier', () => {
	it('is byte for byte the xoxd.ai palette block it was lifted from', () => {
		const start = src.indexOf('export const palette');
		const end = src.indexOf('\n};\n', start) + 4;
		assert.equal(createHash('sha256').update(src.slice(start, end)).digest('hex'), XOXD_AI_PALETTE_BLOCK_SHA256);
	});

	it('carries seven families of eleven shades, 77 tokens', () => {
		assert.deepEqual(families, FAMILIES);
		assert.equal(allTokenNames.length, 77);
		for (const family of FAMILIES) assert.deepEqual(Object.keys(palette[family]).map(Number), SHADES);
	});

	it('ships explicit public licensing and attribution', () => {
		assert.match(read('LICENSE'), /MIT License/);
		assert.match(read('NOTICE'), /Jess Sullivan/);
		assert.doesNotMatch(src, /private/);
	});
});

describe('theme-xoxd.css and palette.ts agree', () => {
	const cssColorTokens = new Map([...css.matchAll(/--color-([a-z]+)-(\d+):\s*(oklch\([^)]+\));/g)].map((m) => [`${m[1]}-${m[2]}`, m[3]]));
	const cssContrastRefs = new Map(
		[...css.matchAll(/--color-([a-z]+)-contrast-(\d+):\s*var\(--color-\1-contrast-(light|dark)\);/g)].map((m) => [`${m[1]}-${m[2]}`, m[3]]),
	);

	it('carries exactly the 77 colour tokens', () => {
		assert.deepEqual([...cssColorTokens.keys()].sort(), [...allTokenNames].sort());
	});

	it('every oklch value and contrast pointer matches palette.ts literally', () => {
		for (const family of FAMILIES) {
			for (const shade of SHADES) {
				assert.equal(cssColorTokens.get(`${family}-${shade}`), palette[family][shade].oklch, `${family}-${shade}`);
				assert.equal(cssContrastRefs.get(`${family}-${shade}`), palette[family][shade].text, `${family}-${shade}`);
			}
		}
	});

	it('pins the heading, anchor, root background and brand roles', () => {
		for (const [token, value] of pinnedTokens(src)) assert.ok(css.includes(`${token}: ${value};`), token);
	});
});

describe('colour math', () => {
	it('round-trips all 77 oklch values to their documented hex', () => {
		for (const family of FAMILIES) {
			for (const shade of SHADES) {
				assert.equal(formatRgb(parseCssColor(palette[family][shade].oklch)), palette[family][shade].hex, `${family}-${shade}`);
			}
		}
	});

	it('keeps lightness strictly monotone down every family', () => {
		for (const family of FAMILIES) {
			const lightness = SHADES.map((shade) => Number(/oklch\(([\d.]+)%/.exec(palette[family][shade].oklch)[1]));
			for (let i = 1; i < lightness.length; i += 1) assert.ok(lightness[i] < lightness[i - 1], `${family}-${SHADES[i]}`);
		}
	});
});

describe('WCAG claims (recomputed, not trusted)', () => {
	const best = (family, shade) =>
		Math.max(contrastRatio(palette[family][shade].hex, palette[family][50].hex), contrastRatio(palette[family][shade].hex, palette[family][950].hex));

	it('every recorded ratio matches a fresh computation within 0.01', () => {
		for (const family of FAMILIES) {
			for (const shade of SHADES) {
				const token = palette[family][shade];
				const pole = token.text === 'light' ? palette[family][50].hex : palette[family][950].hex;
				assert.ok(Math.abs(contrastRatio(token.hex, pole) - token.ratio) < 0.01, `${family}-${shade}`);
			}
		}
	});

	it('the pairs a page paints measure what the v2 spec records (PAL2a)', () => {
		const pairs = [
			['heading light', palette.primary[800].hex, palette.surface[50].hex, 11.87],
			['heading dark', palette.primary[300].hex, palette.surface[950].hex, 8.08],
			['link rest light', palette.primary[500].hex, palette.surface[50].hex, 5.28],
			['link rest dark', palette.primary[400].hex, palette.surface[950].hex, 5.08],
			['link hover light', palette.primary[600].hex, palette.surface[50].hex, 6.91],
			['link hover dark', palette.primary[300].hex, palette.surface[950].hex, 8.08],
			['brand light text', palette.primary[50].hex, palette.primary[500].hex, 5.26],
			['field edge on paper', palette.surface[500].hex, palette.surface[50].hex, 4.45],
			['field edge on ink', palette.surface[500].hex, palette.surface[950].hex, 4.27],
		];
		for (const [name, fg, bg, expected] of pairs) assert.equal(roundRatio(contrastRatio(fg, bg)), expected, name);
	});

	it('body ink is 19.02:1 in both schemes (SK1c)', () => {
		assert.equal(roundRatio(contrastRatio(palette.surface[950].hex, palette.surface[50].hex)), 19.02);
		assert.equal(roundRatio(contrastRatio(palette.surface[50].hex, palette.surface[950].hex)), 19.02);
	});

	it('the disclosed sub-AA set is exhaustive and exact', () => {
		const computed = allTokenNames.filter((name) => {
			const [family, shade] = name.split('-');
			return best(family, Number(shade)) < 4.5;
		});
		assert.deepEqual(computed.sort(), constList(src, 'disclosedSubAaShades').sort());
	});

	it('exactly the disclosed families fail the 3:1 fill check on paper and on ink', () => {
		const accents = FAMILIES.filter((family) => family !== 'surface');
		const onPaper = accents.filter((f) => contrastRatio(palette[f][500].hex, palette.surface[50].hex) < 3);
		const onInk = accents.filter((f) => contrastRatio(palette[f][500].hex, palette.surface[950].hex) < 3);
		assert.deepEqual(onPaper.sort(), constList(src, 'fillContrastExceptions').sort());
		assert.deepEqual(onInk.sort(), constList(src, 'fillContrastExceptionsOnInk').sort());
	});
});
