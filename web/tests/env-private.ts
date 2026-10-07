// Stand-in for SvelteKit's `$env/dynamic/private` under vitest (see vitest.config.ts). Empty by default:
// the modules under test take their configuration as arguments, so nothing here reaches a real server.
export const env: Record<string, string | undefined> = {};
