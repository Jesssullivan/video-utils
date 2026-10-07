import { readFileSync } from 'node:fs';
import path from 'node:path';
import type { PageServerLoad } from './$types';

/**
 * Build-time overview of the typed agent tools. Runs only during prerender:
 * it reads the repository tool registry and emits, per tool, exactly four
 * fields (name, title, intent, skill_name) plus two aggregates. Schemas,
 * limitations, dependencies, workflows, paths and instrument context are
 * never emitted. No generated copy of the registry is committed.
 *
 * A registry string that would trip a public leak rule is not rewritten: the
 * intent is withheld (null) and the page shows a visible marker.
 */

export interface PublicTool {
	readonly name: string;
	readonly title: string;
	readonly intent: string | null;
	readonly skill_name: string;
}

interface LeakRule {
	readonly id: string;
	readonly pattern: string;
	readonly flags: string;
}

const NAME_RE = /^[a-z][a-z0-9_]{0,63}$/u;
const SKILL_PATH_RE = /^\.agents\/skills\/([a-z0-9][a-z0-9-]{0,63})\/SKILL\.md$/u;
const URL_OR_MAILBOX_RE = /\bhttps?:\/\/|\b[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}\b/iu;

function readJson(file: string, label: string): unknown {
	let text: string;
	try {
		text = readFileSync(file, 'utf8');
	} catch {
		throw new Error(`agents page: cannot read the ${label}`);
	}
	try {
		return JSON.parse(text);
	} catch {
		throw new Error(`agents page: the ${label} is not valid JSON`);
	}
}

function requireString(value: unknown, field: string, index: number): string {
	if (typeof value !== 'string' || value.trim() === '') {
		throw new Error(`agents page: tool ${index} has no usable ${field}`);
	}
	return value;
}

export const load: PageServerLoad = () => {
	// `pnpm run build` runs with the site directory as the working directory.
	const siteRoot = process.cwd();
	const registry = readJson(path.resolve(siteRoot, '..', 'program', 'tools.json'), 'tool registry');
	const ruleFile = readJson(path.resolve(siteRoot, 'scripts', 'leak-scan-rules.json'), 'leak rule file');

	const rawTools = (registry as { tools?: unknown }).tools;
	if (!Array.isArray(rawTools) || rawTools.length === 0) {
		throw new Error('agents page: the tool registry lists no tools');
	}
	const rawRules = (ruleFile as { rules?: unknown }).rules;
	if (!Array.isArray(rawRules) || rawRules.length === 0) {
		throw new Error('agents page: the leak rule file lists no rules');
	}
	const rules = (rawRules as LeakRule[]).map((rule) => new RegExp(rule.pattern, rule.flags));
	const trips = (text: string) => URL_OR_MAILBOX_RE.test(text) || rules.some((rule) => rule.test(text));

	const byStatus: Record<string, number> = {};
	const seen = new Set<string>();
	const tools: PublicTool[] = rawTools.map((entry, index) => {
		const tool = entry as Record<string, unknown>;
		const name = requireString(tool.name, 'name', index);
		if (!NAME_RE.test(name) || seen.has(name)) {
			throw new Error(`agents page: tool ${index} has an unexpected or repeated name`);
		}
		seen.add(name);
		const skillMatch = SKILL_PATH_RE.exec(requireString(tool.skill, 'skill', index));
		if (skillMatch === null) {
			throw new Error(`agents page: tool ${index} has an unexpected skill path`);
		}
		const title = requireString(tool.title, 'title', index);
		const intent = requireString(tool.intent, 'intent', index);
		const status = requireString(tool.implementation_status, 'implementation_status', index);
		if (!NAME_RE.test(status)) {
			throw new Error(`agents page: tool ${index} has an unexpected implementation status`);
		}
		byStatus[status] = (byStatus[status] ?? 0) + 1;
		if (trips(name) || trips(skillMatch[1])) {
			throw new Error(`agents page: tool ${index} has a name that a public leak rule refuses`);
		}
		const withheld = trips(title) || trips(intent);
		return { name, title: trips(title) ? name : title, intent: withheld ? null : intent, skill_name: skillMatch[1] };
	});

	return {
		tools,
		tool_count: tools.length,
		status_counts: Object.entries(byStatus)
			.map(([status, count]) => ({ status, count }))
			.sort((left, right) => right.count - left.count || left.status.localeCompare(right.status))
	};
};
