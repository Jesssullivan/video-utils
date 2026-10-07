#!/usr/bin/env node
// Emits the colour block of theme/theme-xoxd.css from theme/palette.ts, so the
// CSS Skeleton paints with and the typed carrier the tests measure are one
// source (lifted from xoxd.ai scripts/build-theme-css.mjs at 4fd966f).
//
//   bazelisk run //:build_theme_css             rewrite the block in place
//   bazelisk run //:build_theme_css -- --check  exit 1 if the block is stale
//
// //test:theme_css_test imports render() and readPalette() and holds the
// committed block to them.
import { readFileSync, writeFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

export const BEGIN = '\t/* BEGIN generated from theme/palette.ts by scripts/build-theme-css.mjs */';
export const END = '\t/* END generated */';

/** Parses the palette table out of palette.ts's source text. */
export function readPalette(src) {
	const families = [];
	const palette = {};
	let family = null;
	for (const line of src.split('\n')) {
		const f = /^\t([a-z]+): \{$/u.exec(line);
		if (f) {
			family = f[1];
			families.push(family);
			palette[family] = [];
			continue;
		}
		const m = /^\t\t(\d+): \{ hex: '(#[0-9a-f]{6})', oklch: '([^']+)', text: '(light|dark)', ratio: ([\d.]+) \},?$/u.exec(line);
		if (m && family) palette[family].push({ shade: Number(m[1]), hex: m[2], oklch: m[3], text: m[4], ratio: Number(m[5]) });
	}
	if (families.length !== 7) throw new Error(`expected 7 families in palette.ts, found ${families.length}`);
	for (const f of families) {
		if (palette[f].length !== 11) throw new Error(`expected 11 shades for ${f}, found ${palette[f].length}`);
	}
	return { families, palette };
}

/** Renders the generated block, markers included. */
export function render({ families, palette }) {
	const lines = [BEGIN];
	for (const family of families) {
		lines.push(`\t/* ${family} */`);
		for (const { shade, oklch } of palette[family]) lines.push(`\t--color-${family}-${shade}: ${oklch};`);
		lines.push(`\t--color-${family}-contrast-dark: var(--color-${family}-950);`);
		lines.push(`\t--color-${family}-contrast-light: var(--color-${family}-50);`);
		for (const { shade, text } of palette[family]) {
			lines.push(`\t--color-${family}-contrast-${shade}: var(--color-${family}-contrast-${text});`);
		}
	}
	lines.push(END);
	return lines.join('\n');
}

/** The committed block of a theme-xoxd.css text, markers included. */
export function committedBlock(css) {
	const start = css.indexOf(BEGIN);
	const end = css.indexOf(END);
	if (start < 0 || end < 0 || end < start) throw new Error('build-theme-css: markers missing in theme-xoxd.css');
	return css.slice(start, end + END.length);
}

function main() {
	const root = process.env.BUILD_WORKSPACE_DIRECTORY ?? path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
	const palettePath = path.join(root, 'theme/palette.ts');
	const cssPath = path.join(root, 'theme/theme-xoxd.css');
	const css = readFileSync(cssPath, 'utf8');
	const current = committedBlock(css);
	const next = css.replace(current, render(readPalette(readFileSync(palettePath, 'utf8'))));
	if (next === css) {
		console.log('build-theme-css: theme/theme-xoxd.css matches theme/palette.ts');
		return 0;
	}
	if (process.argv.includes('--check')) {
		console.error('build-theme-css: theme/theme-xoxd.css is stale; run bazelisk run //:build_theme_css');
		return 1;
	}
	writeFileSync(cssPath, next);
	console.log('build-theme-css: wrote theme/theme-xoxd.css');
	return 0;
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
	process.exit(main());
}
