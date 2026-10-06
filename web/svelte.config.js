import adapter from '@sveltejs/adapter-node';
import { vitePreprocess } from '@sveltejs/vite-plugin-svelte';

/**
 * Stable SvelteKit 2 configuration only: adapter-node, no experimental flags.
 * The production start path is `node serve.js` (loopback-only); see WEB_STACK_S2.md.
 * @type {import('@sveltejs/kit').Config}
 */
const config = {
	preprocess: vitePreprocess(),
	kit: {
		adapter: adapter({ out: 'build', precompress: false })
	}
};

export default config;
