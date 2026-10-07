// Stops only what global setup started: the two app process groups (SIGTERM, then SIGKILL after 5 s) and the
// in-process mock (R-N11: own recorded processes only). Nothing outlives the run.
import type { ChildProcess } from 'node:child_process';

type Started = { mock: { close: () => Promise<void> }; children: ChildProcess[] };
const KILL_AFTER_MS = 5000;

function signal(child: ChildProcess, name: NodeJS.Signals): void {
	if (child.pid === undefined || child.exitCode !== null || child.signalCode !== null) return;
	try {
		process.kill(-child.pid, name);
	} catch {
		// the group is already gone
	}
}

export default async function globalTeardown(): Promise<void> {
	const holder = globalThis as unknown as { __webTestsE2E?: Started };
	const started = holder.__webTestsE2E;
	if (!started) return;
	holder.__webTestsE2E = undefined;
	await Promise.all(
		started.children.map(
			(child) =>
				new Promise<void>((resolve) => {
					if (child.exitCode !== null || child.signalCode !== null) return resolve();
					const timer = setTimeout(() => signal(child, 'SIGKILL'), KILL_AFTER_MS);
					child.once('exit', () => {
						clearTimeout(timer);
						resolve();
					});
					signal(child, 'SIGTERM');
				})
		)
	);
	await started.mock.close();
}
