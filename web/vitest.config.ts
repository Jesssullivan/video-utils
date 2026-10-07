// Standalone vitest config for the pure web modules (WEB_TESTS_S3.md section 4.4). It does not load
// vite.config.ts: no SvelteKit or Tailwind plugin runs, so only modules without `$app/*` are testable here.
import { fileURLToPath } from 'node:url';
import { defineConfig } from 'vitest/config';

const here = (path: string) => fileURLToPath(new URL(path, import.meta.url));

export default defineConfig({
	resolve: {
		alias: [
			{ find: /^\$lib\//, replacement: `${here('./src/lib')}/` },
			// Server modules read the private env through SvelteKit; tests get an empty, mutable stand-in.
			{ find: '$env/dynamic/private', replacement: here('./tests/env-private.ts') }
		]
	},
	test: {
		environment: 'node',
		include: ['src/**/*.test.ts'],
		passWithNoTests: false,
		setupFiles: [here('./tests/setup.ts')],
		reporters: ['default', 'json'],
		outputFile: { json: here('../artifacts/s2/web_tests/unit/vitest-report.json') }
	}
});
