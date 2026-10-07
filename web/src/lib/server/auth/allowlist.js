// Operator allowlist (AUTH_HOSTING_S3.md section 4.2). Pure; no env reads, no I/O.
// The allowlist is an inner layer behind the Cloudflare Access perimeter: an identity is
// admitted only when its *verified* Access JWT email is listed here exactly (lowercased).

export const ALLOWLIST_ENV = 'VIDEO_UTILS_OPERATOR_ALLOWLIST';
export const MAX_ALLOWLIST_ENTRIES = 32;
const MAX_EMAIL_LENGTH = 254;

// Exact addresses only: no wildcard, no bare domain, no display name, no whitespace.
// Local part: RFC 5322 atext plus dots; domain: dotted LDH labels with at least one dot.
const EMAIL_PATTERN =
	/^[a-z0-9.!#$%&'+/=?^_`{|}~-]+@[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)+$/;

/**
 * @typedef {{ ok: true, emails: ReadonlySet<string> } | { ok: false, reason: string }} AllowlistResult
 */

/**
 * Parse a comma-separated allowlist: trim, lowercase, de-duplicate; 1..32 entries.
 * Any malformed entry rejects the whole list (fail closed, never a partial allowlist).
 * Reasons name the rule only and never echo a configured value.
 * @param {string | undefined | null} raw
 * @returns {AllowlistResult}
 */
export function parseAllowlist(raw) {
	if (typeof raw !== 'string' || raw.trim() === '') return { ok: false, reason: 'allowlist_missing' };
	/** @type {Set<string>} */
	const emails = new Set();
	for (const part of raw.split(',')) {
		const email = part.trim().toLowerCase();
		if (email === '') return { ok: false, reason: 'allowlist_empty_entry' };
		if (email.includes('*')) return { ok: false, reason: 'allowlist_wildcard' };
		if (email.length > MAX_EMAIL_LENGTH || !EMAIL_PATTERN.test(email)) {
			return { ok: false, reason: 'allowlist_invalid_entry' };
		}
		emails.add(email);
	}
	if (emails.size > MAX_ALLOWLIST_ENTRIES) return { ok: false, reason: 'allowlist_too_many' };
	return { ok: true, emails };
}

/**
 * Exact, case-insensitive membership of an already-verified email.
 * @param {ReadonlySet<string>} emails
 * @param {string | null | undefined} verifiedEmail
 * @returns {boolean}
 */
export function isAllowlisted(emails, verifiedEmail) {
	if (typeof verifiedEmail !== 'string' || verifiedEmail === '') return false;
	return emails.has(verifiedEmail.toLowerCase());
}
