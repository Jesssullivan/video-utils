// Pure job-status polling policy (WEB_STACK_S2.md section 5.2). No timers, no I/O:
// callers ask for the next decision and own scheduling. Testable with plain `node`.

export const POLL_BASE_MS = 2000;
export const POLL_BACKOFF_CAP_MS = 30000;
export const POLL_MAX_CONSECUTIVE_ERRORS = 5;

/** States after which the job snapshot can no longer change without operator action. */
export const TERMINAL_STATES = Object.freeze([
	'succeeded',
	'failed',
	'cancelled',
	'needs_reconciliation',
	'interrupted'
]);

/**
 * @param {string | null | undefined} state
 * @returns {boolean}
 */
export function isTerminalState(state) {
	return typeof state === 'string' && TERMINAL_STATES.includes(state);
}

/**
 * @typedef {{ action: 'poll', delayMs: number, reason: 'base' | 'backoff' }
 *   | { action: 'stop', reason: 'terminal_state' }
 *   | { action: 'paused', reason: 'polling_paused' | 'hidden' }} PollDecision
 */

/**
 * Decide what to do after the latest poll outcome.
 * @param {{ lastState: string | null, consecutiveErrors: number, hidden?: boolean }} input
 * @returns {PollDecision}
 */
export function nextPollDecision({ lastState, consecutiveErrors, hidden = false }) {
	if (consecutiveErrors === 0 && isTerminalState(lastState)) {
		return { action: 'stop', reason: 'terminal_state' };
	}
	if (consecutiveErrors >= POLL_MAX_CONSECUTIVE_ERRORS) {
		return { action: 'paused', reason: 'polling_paused' };
	}
	if (hidden) {
		return { action: 'paused', reason: 'hidden' };
	}
	if (consecutiveErrors <= 0) {
		return { action: 'poll', delayMs: POLL_BASE_MS, reason: 'base' };
	}
	const delayMs = Math.min(POLL_BASE_MS * 2 ** consecutiveErrors, POLL_BACKOFF_CAP_MS);
	return { action: 'poll', delayMs, reason: 'backoff' };
}
