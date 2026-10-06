import { sveltekit } from '@sveltejs/kit/vite';
import tailwindcss from '@tailwindcss/vite';
import { defineConfig } from 'vite';

// Loopback only. Dev and preview never bind a non-loopback interface.
export default defineConfig({
	plugins: [tailwindcss(), sveltekit()],
	server: { host: '127.0.0.1', strictPort: true },
	preview: { host: '127.0.0.1', strictPort: true }
});
