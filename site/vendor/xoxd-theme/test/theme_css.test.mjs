// The CSS carriers: the generated block is current, one page shell, the type
// tokens and faces present (the xoxd.ai layout-tokens and type-tokens tests
// at 4fd966f, narrowed to what this module carries).
import assert from 'node:assert/strict';
import { describe, it } from 'node:test';

import { committedBlock, readPalette, render } from '../scripts/build-theme-css.mjs';
import { read, themeTokens } from './lib.mjs';

const theme = read('theme/theme-xoxd.css');
const fonts = read('theme/fonts.css');
const tailwind = read('theme/tailwind.css');
const base = read('theme/base.css');
const all = [theme, fonts, tailwind, base];

const MONO_STACK =
	"'FiraCode Nerd Font Mono', 'FiraCode Nerd Font Mono Fallback', ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace";
const SANS_STACK = "'Inter', 'Inter Fallback', system-ui, -apple-system, sans-serif";

describe('the generated colour block', () => {
	it('equals what scripts/build-theme-css.mjs renders from palette.ts', () => {
		assert.equal(committedBlock(theme), render(readPalette(read('theme/palette.ts'))));
	});
});

describe('the page shell (SH1)', () => {
	it('declares --page-shell exactly once across the module', () => {
		const count = all.reduce((n, css) => n + [...css.matchAll(/--page-shell\s*:/g)].length, 0);
		assert.equal(count, 1);
		assert.match(theme, /--page-shell: min\(100% - 2rem, 72rem\);/);
		assert.match(theme, /--prose-measure: 66ch;/);
		assert.match(theme, /--section-rhythm: clamp\(3rem, 6vw, 4rem\);/);
	});

	it('gives the four shell selectors the shell width', () => {
		for (const selector of ['.site-header__inner', '.page-shell', '.site-footer__inner', '.hero__inner']) {
			assert.ok(base.includes(selector), selector);
		}
		assert.match(base, /width: var\(--page-shell\);/);
	});

	it('declares no [data-theme] block outside theme-xoxd.css', () => {
		for (const css of [fonts, tailwind, base]) assert.doesNotMatch(css, /\[data-theme=/);
	});
});

describe('the type tokens (TY1)', () => {
	const tokens = themeTokens('xoxd', theme);

	it('heads on the mono and sets the body in Inter, fallbacks second', () => {
		assert.equal(tokens.get('--typo-heading--font-family'), MONO_STACK);
		assert.equal(tokens.get('--typo-base--font-family'), SANS_STACK);
	});

	it('gives Tailwind the same two stacks', () => {
		const flat = tailwind.replace(/\s+/g, ' ');
		assert.ok(flat.includes(`--font-mono: ${MONO_STACK};`));
		assert.ok(flat.includes(`--font-sans: ${SANS_STACK};`));
	});

	it('declares both mono weights with font-display: swap and both fallback faces', () => {
		const faces = [...fonts.matchAll(/@font-face \{([\s\S]*?)\}/g)].map((m) => m[1]);
		const mono = faces.filter((f) => f.includes("'FiraCode Nerd Font Mono';"));
		assert.equal(mono.length, 2);
		for (const face of mono) assert.match(face, /font-display: swap;/);
		assert.ok(fonts.includes("url('/fonts/FiraCodeNerdFontMono-Regular.woff2')"));
		assert.ok(fonts.includes("url('/fonts/FiraCodeNerdFontMono-Bold.woff2')"));
		assert.ok(fonts.includes("font-family: 'Inter Fallback';"));
		assert.ok(fonts.includes("font-family: 'FiraCode Nerd Font Mono Fallback';"));
	});

	it('keys the dark variant and the colour scheme on data-mode', () => {
		assert.ok(tailwind.includes("@custom-variant dark (&:where([data-mode='dark'], [data-mode='dark'] *));"));
		assert.match(base, /\[data-mode='dark'\] \{\s*color-scheme: dark;/);
		assert.match(base, /:focus-visible \{\s*outline: 2px solid var\(--color-primary-500\);/);
	});
});
