#!/usr/bin/env node
/**
 * Leak scanner for the video-utils public landing. Node standard library only.
 * Modelled on the xoxd.ai scanner (scripts/lib/leak-scan.mjs, origin/main
 * cc570c3): walk a tree, scan text files against every rule in
 * leak-scan-rules.json, check every outbound host and mailbox against a
 * reviewed allowlist, print findings as `rule-id file:line`, and exit
 * non-zero on any finding.
 *
 * Usage:
 *   node scripts/leak-scan.mjs <directory> [--surface build|source|vendor]
 *                              [--report <path>] [--rules <path>]
 *
 * Surfaces:
 *   build   every rule; fixed text extension list; refuses source maps,
 *           documents, media and archives; fails closed on unknown extensions.
 *   source  the site directory minus generated and third-party trees; rules
 *           marked sourceScope "src" apply to files under src/ only.
 *   vendor  the unmodified third-party carriers; only rules marked
 *           vendorCarrier; no host or mailbox allowlist check.
 *
 * Exit status: 0 no findings, 1 findings, 2 usage or input error.
 * The report never contains an absolute path or matched text; the one exception
 * is the host name of an unreviewed outbound host, which a reviewer needs.
 */

import { readFileSync, readdirSync, statSync, writeFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const moduleDirectory = path.dirname(fileURLToPath(import.meta.url));
const DEFAULT_RULES_PATH = path.join(moduleDirectory, 'leak-scan-rules.json');

export const SURFACES = Object.freeze(['build', 'source', 'vendor']);

const dotted = (names) => new Set(names.map((name) => `.${name}`));

/** Build surface: extensions scanned as UTF-8 text. '' covers extensionless files. */
export const BUILD_TEXT_EXTENSIONS = new Set([...dotted(['html', 'js', 'mjs', 'css', 'json', 'svg', 'txt', 'md', 'xml']), '']);

/** Build surface: opaque files that are listed as unscannable, not refused. */
export const BUILD_OPAQUE_EXTENSIONS = dotted(['woff', 'woff2', 'ico']);

/** Build surface: file types that must never be published; each is a finding. */
export const BUILD_REFUSED_EXTENSIONS = dotted([
	'map', 'pdf',
	'mov', 'mp4', 'm4v', 'webm', 'mkv', 'avi',
	'wav', 'flac', 'aiff', 'aif', 'aac', 'mp3', 'ogg', 'opus', 'm4a',
	'png', 'jpg', 'jpeg', 'gif', 'webp', 'avif', 'bmp', 'tiff',
	'zip', 'tar', 'gz', 'tgz', 'br', 'bz2', 'xz', '7z'
]);

/** Source surface: directories and files that are generated or third-party. */
export const SOURCE_EXCLUDED_PREFIXES = Object.freeze(['node_modules/', '.svelte-kit/', 'build/', 'vendor/', 'static/fonts/']);
export const SOURCE_EXCLUDED_FILES = Object.freeze(['pnpm-lock.yaml']);

const VENDOR_RUNTIME_CHUNK_RE = /(?:^|\/)_app\/immutable\/chunks\//u;
const URL_RE = /\bhttps?:\/\/([a-z0-9.-]+)/giu;
const MAILBOX_RE = /\b[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}\b/giu;

/** The one forge host that exact reviewed URLs may name (assembled so this file stays clean). */
const FORGE_HOST = ['github', 'com'].join('.');
const FORGE_URL_RE = /https:\/\/github\.com\/[^\s"'`<>)\]]+/giu;
const FORGE_RULE_ID = 'internal-tracker-reference';

function isAllowedForgeMatch(text, matchIndex, allowedUrls) {
	for (const match of text.matchAll(FORGE_URL_RE)) {
		const start = match.index ?? 0;
		if (matchIndex < start || matchIndex >= start + match[0].length) continue;
		return allowedUrls.has(match[0].replace(/\/$/u, ''));
	}
	return false;
}

export function loadRules(rulesPath = DEFAULT_RULES_PATH) {
	const document = JSON.parse(readFileSync(rulesPath, 'utf8'));
	if (!Array.isArray(document.rules) || document.rules.length === 0) {
		throw new Error('leak-scan: rule file has no rules');
	}
	return {
		rules: document.rules.map((rule) => ({
			...rule,
			regexp: new RegExp(rule.pattern, rule.flags.includes('g') ? rule.flags : `${rule.flags}g`)
		})),
		allowedHosts: new Set((document.allowedHosts ?? []).map((host) => host.toLowerCase())),
		allowedForgeUrls: new Set((document.allowedPublicForgeUrls ?? []).map((url) => url.replace(/\/$/u, ''))),
		allowedMailboxes: new Set((document.allowedMailboxes ?? []).map((box) => box.toLowerCase()))
	};
}

/** Whether a rule applies to a file (posix relative path) on a surface. */
export function ruleApplies(rule, surface, relativePath) {
	if (surface === 'vendor') return rule.vendorCarrier === true;
	if (surface === 'source') return rule.sourceScope !== 'src' || relativePath.startsWith('src/');
	return !(rule.skipVendorRuntimeChunks === true && VENDOR_RUNTIME_CHUNK_RE.test(relativePath));
}

function lineOf(text, index) {
	let line = 1;
	for (let cursor = 0; cursor < index; cursor += 1) {
		if (text.charCodeAt(cursor) === 10) line += 1;
	}
	return line;
}

/**
 * Applies the rules and allowlists to one file's text.
 * @returns {{ruleId: string, file: string, line: number}[]}
 */
export function scanText(relativePath, text, ruleSet, surface = 'build') {
	const findings = [];
	for (const rule of ruleSet.rules) {
		if (!ruleApplies(rule, surface, relativePath)) continue;
		rule.regexp.lastIndex = 0;
		for (const match of text.matchAll(rule.regexp)) {
			if (
				rule.id === FORGE_RULE_ID &&
				match[0].toLowerCase() === FORGE_HOST &&
				isAllowedForgeMatch(text, match.index ?? 0, ruleSet.allowedForgeUrls)
			) {
				continue;
			}
			findings.push({ ruleId: rule.id, file: relativePath, line: lineOf(text, match.index ?? 0) });
		}
	}
	if (surface !== 'vendor') {
		for (const match of text.matchAll(URL_RE)) {
			const host = match[1].toLowerCase().replace(/\.$/u, '');
			if (ruleSet.allowedHosts.has(host)) continue;
			if (host === FORGE_HOST && isAllowedForgeMatch(text, match.index ?? 0, ruleSet.allowedForgeUrls)) continue;
			findings.push({ ruleId: 'unreviewed-outbound-host', file: relativePath, line: lineOf(text, match.index ?? 0), host });
		}
		for (const match of text.matchAll(MAILBOX_RE)) {
			if (ruleSet.allowedMailboxes.has(match[0].toLowerCase())) continue;
			findings.push({ ruleId: 'unreviewed-mailbox', file: relativePath, line: lineOf(text, match.index ?? 0) });
		}
	}
	return findings;
}

function walk(root) {
	const found = [];
	const visit = (directory) => {
		for (const entry of readdirSync(directory).sort()) {
			const absolute = path.join(directory, entry);
			if (statSync(absolute).isDirectory()) visit(absolute);
			else found.push(path.relative(root, absolute).split(path.sep).join('/'));
		}
	};
	visit(root);
	return found.sort();
}

function decodeText(bytes) {
	if (bytes.includes(0)) return null;
	try {
		return new TextDecoder('utf-8', { fatal: true }).decode(bytes);
	} catch {
		return null;
	}
}

/**
 * Scans a directory on a surface.
 * @returns {{files_scanned: string[], files_unscannable: string[], findings: object[], rules_applied: string[]}}
 */
export function scanDirectory(root, ruleSet, surface = 'build') {
	const scanned = [];
	const unscannable = [];
	const findings = [];
	for (const relativePath of walk(root)) {
		if (surface === 'source') {
			if (SOURCE_EXCLUDED_PREFIXES.some((prefix) => relativePath.startsWith(prefix))) continue;
			if (SOURCE_EXCLUDED_FILES.includes(relativePath)) continue;
		}
		const extension = path.extname(relativePath).toLowerCase();
		if (surface === 'build') {
			if (BUILD_REFUSED_EXTENSIONS.has(extension)) {
				findings.push({ ruleId: 'refused-file-type', file: relativePath, line: 0 });
				continue;
			}
			if (BUILD_OPAQUE_EXTENSIONS.has(extension)) {
				unscannable.push(relativePath);
				continue;
			}
			if (!BUILD_TEXT_EXTENSIONS.has(extension)) {
				findings.push({ ruleId: 'unclassified-file-type', file: relativePath, line: 0 });
				continue;
			}
		}
		const text = decodeText(readFileSync(path.join(root, relativePath)));
		if (text === null) {
			if (surface === 'build') findings.push({ ruleId: 'undecodable-text-file', file: relativePath, line: 0 });
			else unscannable.push(relativePath);
			continue;
		}
		scanned.push(relativePath);
		findings.push(...scanText(relativePath, text, ruleSet, surface));
	}
	findings.sort((left, right) => left.file.localeCompare(right.file) || left.line - right.line || left.ruleId.localeCompare(right.ruleId));
	const applied = ruleSet.rules.filter((rule) => surface !== 'vendor' || rule.vendorCarrier === true).map((rule) => rule.id);
	return { files_scanned: scanned, files_unscannable: unscannable, findings, rules_applied: applied };
}

export function formatFindings(findings) {
	return findings.map((finding) => `${finding.ruleId} ${finding.file}:${finding.line}`).join('\n');
}

function parseArguments(argv) {
	const options = { directory: null, surface: 'build', report: null, rules: DEFAULT_RULES_PATH };
	for (let index = 0; index < argv.length; index += 1) {
		const argument = argv[index];
		if (argument === '--surface' || argument === '--report' || argument === '--rules') {
			const value = argv[index + 1];
			if (value === undefined) throw new Error(`leak-scan: ${argument} needs a value`);
			options[argument.slice(2)] = value;
			index += 1;
		} else if (argument.startsWith('--')) {
			throw new Error(`leak-scan: unknown option ${argument}`);
		} else if (options.directory === null) {
			options.directory = argument;
		} else {
			throw new Error('leak-scan: exactly one directory is expected');
		}
	}
	if (options.directory === null) throw new Error('leak-scan: a directory is required');
	if (!SURFACES.includes(options.surface)) throw new Error(`leak-scan: surface must be one of ${SURFACES.join(', ')}`);
	return options;
}

function main(argv) {
	let options;
	let ruleSet;
	let result;
	try {
		options = parseArguments(argv);
		ruleSet = loadRules(options.rules);
		if (!statSync(options.directory).isDirectory()) throw new Error('leak-scan: not a directory');
		result = scanDirectory(options.directory, ruleSet, options.surface);
	} catch (error) {
		process.stderr.write(`${error instanceof Error ? error.message : String(error)}\n`);
		return 2;
	}
	const counts = {};
	for (const finding of result.findings) counts[finding.ruleId] = (counts[finding.ruleId] ?? 0) + 1;
	if (options.report !== null) {
		const report = {
			schema_version: 1,
			scanner: 'site/scripts/leak-scan.mjs',
			surface: options.surface,
			directory_name: path.basename(path.resolve(options.directory)),
			rules_total: ruleSet.rules.length,
			rules_applied: result.rules_applied,
			rules_applied_count: result.rules_applied.length,
			allowed_hosts: [...ruleSet.allowedHosts].sort(),
			allowed_mailboxes_count: ruleSet.allowedMailboxes.size,
			files_scanned_count: result.files_scanned.length,
			files_scanned: result.files_scanned,
			files_unscannable_count: result.files_unscannable.length,
			files_unscannable: result.files_unscannable,
			findings_count: result.findings.length,
			findings_by_rule: counts,
			findings: result.findings
		};
		writeFileSync(options.report, `${JSON.stringify(report, null, 2)}\n`);
	}
	if (result.findings.length > 0) process.stdout.write(`${formatFindings(result.findings)}\n`);
	process.stdout.write(
		`leak-scan: surface=${options.surface} rules=${result.rules_applied.length} files=${result.files_scanned.length} ` +
			`unscannable=${result.files_unscannable.length} findings=${result.findings.length}\n`
	);
	return result.findings.length > 0 ? 1 : 0;
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
	process.exitCode = main(process.argv.slice(2));
}
