// Client-safe form keys (WEB_TESTS_S3.md 5.1). One key per rendered form; a double submit replays.
import { afterEach, describe, expect, it, vi } from 'vitest';
import { UI_KEY_PATTERN, newFormKey } from './idempotency';

afterEach(() => vi.restoreAllMocks());

describe('newFormKey', () => {
	it('returns ui- followed by 32 lowercase hex characters', () => {
		for (let index = 0; index < 50; index += 1) expect(UI_KEY_PATTERN.test(newFormKey())).toBe(true);
		expect(UI_KEY_PATTERN.test(newFormKey('ui'))).toBe(true);
	});

	it('uses the ui-ann prefix for annotation keys, which is not a job form key', () => {
		const key = newFormKey('ui-ann');
		expect(key).toMatch(/^ui-ann-[0-9a-f]{32}$/);
		expect(UI_KEY_PATTERN.test(key)).toBe(false);
	});

	it('1,000 generated keys are distinct', () => {
		const keys = new Set(Array.from({ length: 1000 }, () => newFormKey()));
		expect(keys.size).toBe(1000);
	});

	it('takes its 16 bytes from crypto.getRandomValues and encodes them verbatim', () => {
		const spy = vi.spyOn(globalThis.crypto, 'getRandomValues').mockImplementation((array) => {
			const bytes = array as unknown as Uint8Array;
			for (let index = 0; index < bytes.length; index += 1) bytes[index] = index;
			return array;
		});
		expect(newFormKey()).toBe('ui-000102030405060708090a0b0c0d0e0f');
		expect(spy).toHaveBeenCalledTimes(1);
		expect((spy.mock.calls[0][0] as unknown as Uint8Array).length).toBe(16);
	});

	it('does not fall back to Math.random', () => {
		const random = vi.spyOn(Math, 'random');
		newFormKey();
		newFormKey('ui-ann');
		expect(random).not.toHaveBeenCalled();
	});
});

describe('UI_KEY_PATTERN', () => {
	it('refuses anything but the exact shape', () => {
		for (const bad of ['', 'ui-', `ui-${'0'.repeat(31)}`, `ui-${'0'.repeat(33)}`, `ui-${'A'.repeat(32)}`, ` ui-${'0'.repeat(32)}`, `ui-${'0'.repeat(32)}\n`]) {
			expect(UI_KEY_PATTERN.test(bad), JSON.stringify(bad)).toBe(false);
		}
	});
});
