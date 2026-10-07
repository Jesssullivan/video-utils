// The pre-paint script agrees with the theme it applies, defaults to dark
// (DK1), and the manifest carries MODULE.bazel's version.
import assert from 'node:assert/strict';
import { describe, it } from 'node:test';

import { COLOR_MODE_KEY, DEFAULT_MODE, FOUC_SCRIPT, THEME_ID } from '../theme/fouc.mjs';
import { read } from './lib.mjs';

describe('the pre-paint script', () => {
	it('applies the theme id theme-xoxd.css keys on', () => {
		assert.equal(THEME_ID, 'xoxd');
		assert.ok(read('theme/theme-xoxd.css').includes(`[data-theme='${THEME_ID}'] {`));
		assert.ok(FOUC_SCRIPT.includes(`setAttribute('data-theme', '${THEME_ID}')`));
	});

	it('defaults to dark and reads the stored mode from color-mode', () => {
		assert.equal(DEFAULT_MODE, 'dark');
		assert.equal(COLOR_MODE_KEY, 'color-mode');
		assert.ok(FOUC_SCRIPT.includes("var mode = 'dark';"));
		assert.ok(FOUC_SCRIPT.includes("localStorage.getItem('color-mode')"));
	});

	it('is syntactically valid script and resolves each stored mode', () => {
		const run = (stored, prefersDark) => {
			const attrs = {};
			const style = {};
			const fn = new Function('localStorage', 'window', 'document', FOUC_SCRIPT);
			fn(
				{ getItem: () => stored },
				{ matchMedia: () => ({ matches: prefersDark }) },
				{ documentElement: { setAttribute: (k, v) => (attrs[k] = v), style } },
			);
			return [attrs['data-mode'], attrs['data-theme'], style.colorScheme];
		};
		assert.deepEqual(run(null, false), ['dark', 'xoxd', 'dark']);
		assert.deepEqual(run('light', true), ['light', 'xoxd', 'light']);
		assert.deepEqual(run('system', false), ['light', 'xoxd', 'light']);
		assert.deepEqual(run('system', true), ['dark', 'xoxd', 'dark']);
		assert.deepEqual(run('bogus', false), ['dark', 'xoxd', 'dark']);
	});
});

describe('the version', () => {
	it('xoxd-theme.json carries the module name and MODULE.bazel version', () => {
		const manifest = JSON.parse(read('xoxd-theme.json'));
		const module = /module\(\s*name = "([^"]+)",\s*version = "([^"]+)"/.exec(read('MODULE.bazel'));
		assert.equal(manifest.module, module[1]);
		assert.equal(manifest.version, module[2]);
	});
});
