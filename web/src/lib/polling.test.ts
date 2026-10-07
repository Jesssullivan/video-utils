// Pure job-status polling policy (WEB_TESTS_S3.md 5.1).
import fc from 'fast-check';
import { describe, expect, it } from 'vitest';
import { POLL_BACKOFF_CAP_MS, POLL_BASE_MS, POLL_MAX_CONSECUTIVE_ERRORS, TERMINAL_STATES, isTerminalState, nextPollDecision } from './polling.js';

describe('isTerminalState', () => {
	it('is true only for the five terminal states', () => {
		expect([...TERMINAL_STATES].sort()).toEqual(['cancelled', 'failed', 'interrupted', 'needs_reconciliation', 'succeeded']);
		for (const state of TERMINAL_STATES) expect(isTerminalState(state)).toBe(true);
		for (const state of ['queued', 'running', '', 'SUCCEEDED', null, undefined]) expect(isTerminalState(state)).toBe(false);
	});
});

describe('nextPollDecision', () => {
	it('stops on a terminal state after a clean poll', () => {
		for (const state of TERMINAL_STATES) {
			expect(nextPollDecision({ lastState: state, consecutiveErrors: 0 })).toEqual({ action: 'stop', reason: 'terminal_state' });
		}
	});

	it('polls at the base delay while queued or running, and for an unknown first state', () => {
		for (const lastState of ['queued', 'running', null]) {
			expect(nextPollDecision({ lastState, consecutiveErrors: 0 })).toEqual({ action: 'poll', delayMs: POLL_BASE_MS, reason: 'base' });
		}
	});

	it('backs off exponentially and never beyond the cap', () => {
		expect(nextPollDecision({ lastState: 'running', consecutiveErrors: 1 })).toEqual({ action: 'poll', delayMs: 4000, reason: 'backoff' });
		expect(nextPollDecision({ lastState: 'running', consecutiveErrors: 2 })).toEqual({ action: 'poll', delayMs: 8000, reason: 'backoff' });
		expect(nextPollDecision({ lastState: 'running', consecutiveErrors: 4 })).toEqual({ action: 'poll', delayMs: POLL_BACKOFF_CAP_MS, reason: 'backoff' });
		expect(POLL_BACKOFF_CAP_MS).toBe(30000);
	});

	it(`pauses after ${POLL_MAX_CONSECUTIVE_ERRORS} consecutive errors, even when the last known state was terminal`, () => {
		expect(nextPollDecision({ lastState: 'running', consecutiveErrors: POLL_MAX_CONSECUTIVE_ERRORS })).toEqual({ action: 'paused', reason: 'polling_paused' });
		expect(nextPollDecision({ lastState: 'succeeded', consecutiveErrors: POLL_MAX_CONSECUTIVE_ERRORS + 3 })).toEqual({ action: 'paused', reason: 'polling_paused' });
	});

	it('pauses while the page is hidden, but a terminal state still stops', () => {
		expect(nextPollDecision({ lastState: 'running', consecutiveErrors: 0, hidden: true })).toEqual({ action: 'paused', reason: 'hidden' });
		expect(nextPollDecision({ lastState: 'failed', consecutiveErrors: 0, hidden: true })).toEqual({ action: 'stop', reason: 'terminal_state' });
	});

	it('never returns a delay outside [base, cap] and never polls past the error bound (property)', () => {
		const state = fc.oneof(fc.constantFrom('queued', 'running', ...TERMINAL_STATES), fc.constant(null), fc.string({ maxLength: 12 }));
		fc.assert(
			fc.property(state, fc.integer({ min: 0, max: 64 }), fc.boolean(), (lastState, consecutiveErrors, hidden) => {
				const decision = nextPollDecision({ lastState, consecutiveErrors, hidden });
				if (decision.action === 'poll') {
					expect(decision.delayMs).toBeGreaterThanOrEqual(POLL_BASE_MS);
					expect(decision.delayMs).toBeLessThanOrEqual(POLL_BACKOFF_CAP_MS);
					expect(consecutiveErrors).toBeLessThan(POLL_MAX_CONSECUTIVE_ERRORS);
					expect(hidden).toBe(false);
				}
				if (decision.action === 'stop') expect(consecutiveErrors).toBe(0);
			})
		);
	});
});
