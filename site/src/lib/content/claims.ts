/**
 * The one registry of authored claims for the public landing. Pages render
 * from it; nothing here is derived from a real recording or from any run.
 *
 * Format contract (the lane test reads this file as text): one claim per
 * object literal, double-quoted strings, keys in the order id, claim_class,
 * unknown, pages, section, text. The only numerals allowed in authored copy
 * are the instrument context "32 Hz" and "nine-string" spelled out.
 */

export const CLAIM_CLASSES = [
	"implemented",
	"measured_synthetic",
	"inferred",
	"product_hypothesis",
	"unverified_listening",
	"not_done",
	"unknown"
] as const;

export type ClaimClass = (typeof CLAIM_CLASSES)[number];
export type PageId = "home" | "features" | "agents" | "status";
export type SectionId = "capabilities" | "restoration" | "review" | "agent_tools" | "registry" | "not_done";

export interface Claim {
	readonly id: string;
	readonly claim_class: ClaimClass;
	/** True when the element must carry data-unknown: a limit, a gap or an unaccepted outcome. */
	readonly unknown: boolean;
	readonly pages: readonly PageId[];
	readonly section: SectionId;
	readonly text: string;
}

/** What each class means on the page. Shown next to every claim. */
export const CLASS_LABELS: Record<ClaimClass, string> = {
	implemented: "Implemented: exists in the repository, says nothing about accuracy",
	measured_synthetic: "Measured on synthetic fixtures only",
	inferred: "Inferred: a hypothesis for human review",
	product_hypothesis: "Product hypothesis",
	unverified_listening: "Listening outcome not accepted",
	not_done: "Not done",
	unknown: "Unknown"
};

export const SITE = {
	working_title: "video-utils",
	public_product_name: null,
	tagline: "Practice-take restoration and rhythm review for technical guitar.",
	footer_note:
		"Experimental local software. This site is static, sets no cookies and loads nothing from other origins.",
	footer_line: "video-utils is a working title, not a product name."
} as const;

export interface Axiom {
	readonly id: string;
	readonly title: string;
	readonly text: string;
}

/** The three product axioms, in the repository's own sense. */
export const AXIOMS: readonly Axiom[] = [
	{
		id: "technical_playing",
		title: "Technical playing drives detection",
		text: "Riffs, irregular subdivisions, palm mutes, intentional rests, tapping, sweeps and legato are musical context, not noise. Phrase and timing review works without a predefined score, keeps ambiguity visible, and never treats a count of attacks as a count of notes."
	},
	{
		id: "agents_participate",
		title: "Agents take part in processing a take",
		text: "Every processing step has a typed tool and a written skill that state intent, supported settings, dependencies and the evidence produced. Comparisons, sparse coverage, uncertainty and failures are kept so an agent and a musician can both assess a proposed setting."
	},
	{
		id: "distortion_and_low_tuning",
		title: "Heavy distortion and low tuning shape the defaults",
		text: "The reference instrument is a nine-string guitar tuned low, with intentional fundamentals near 32 Hz. Low-string weight, saturated texture, pick attacks and sustain are protected, so there is no blanket high-pass filter, no fixed mains notch and no speech denoiser by default."
	}
];

export const CLAIMS: readonly Claim[] = [
	{
		id: "restore_pipeline",
		claim_class: "implemented",
		unknown: false,
		pages: ["home"],
		section: "capabilities",
		text: "A local command-line pipeline inspects a recording, applies conservative noise reduction, and exports a clip that keeps the original video stream and timeline. The source file is never overwritten."
	},
	{
		id: "low_end_protection",
		claim_class: "implemented",
		unknown: false,
		pages: ["home"],
		section: "capabilities",
		text: "Processing defaults leave the low register in place. The figure of roughly 32 Hz is instrument context supplied by the player, not a measurement of any recording."
	},
	{
		id: "review_markers",
		claim_class: "inferred",
		unknown: false,
		pages: ["home"],
		section: "capabilities",
		text: "Tempo candidates, onset offsets against a recorded click, repeated regions and phrase boundaries are proposed with source timestamps for a musician to review. They are hypotheses, not verdicts."
	},
	{
		id: "agent_tools",
		claim_class: "implemented",
		unknown: false,
		pages: ["home"],
		section: "capabilities",
		text: "Each processing step is exposed to agents as a typed tool over the Model Context Protocol, paired with a written skill. The agent tools page lists them and shows how many are still experimental."
	},
	{
		id: "synthetic_benchmarks",
		claim_class: "measured_synthetic",
		unknown: false,
		pages: ["home"],
		section: "capabilities",
		text: "Restoration, rhythm and phrase tools are exercised against generated fixtures with known components. Those results describe the fixtures only, and no figure from them is quoted on this site."
	},
	{
		id: "real_take_accuracy",
		claim_class: "unknown",
		unknown: true,
		pages: ["home", "status"],
		section: "capabilities",
		text: "Accuracy on real recordings is unknown. Nothing on this site is an accuracy figure, and no result from a real recording is shown."
	},
	{
		id: "note_correctness_verdicts",
		claim_class: "not_done",
		unknown: true,
		pages: ["home", "status"],
		section: "capabilities",
		text: "The software does not issue missed-note or wrong-note verdicts. A judgment of that kind needs an approved reference for what was meant to be played, and a count of attacks never identifies a missed note."
	},
	{
		id: "market_hypothesis",
		claim_class: "product_hypothesis",
		unknown: true,
		pages: ["home", "status"],
		section: "capabilities",
		text: "That a complete local, agent-guided practice workflow for heavily distorted low-tuned guitar is underserved is a hypothesis. Existing products already cover many of the individual features, and this project has not verified specialized accuracy on distorted low-register guitar for any product, including its own."
	},
	{
		id: "feat_restore_separation",
		claim_class: "implemented",
		unknown: false,
		pages: ["features"],
		section: "restoration",
		text: "Noise reduction is conservative by default and is kept separate from tone and dynamics processing. A noise profile is bound to the take it was measured on and is not carried over to another take."
	},
	{
		id: "feat_restore_provenance",
		claim_class: "implemented",
		unknown: false,
		pages: ["features"],
		section: "restoration",
		text: "A master keeps the source sample rate, channel layout and timeline. Settings and content fingerprints are recorded with each run so the processing can be reproduced and compared."
	},
	{
		id: "feat_restore_synthetic",
		claim_class: "measured_synthetic",
		unknown: false,
		pages: ["features"],
		section: "restoration",
		text: "Low-register preservation and noise reduction are measured on generated fixtures with known components. No figure from those fixtures is quoted here, and they do not describe any real recording."
	},
	{
		id: "listening_acceptance",
		claim_class: "unverified_listening",
		unknown: true,
		pages: ["features", "status"],
		section: "restoration",
		text: "Restoration and tone results are not listening-accepted claims. Whether a processed clip sounds better is a judgment for a listener at matched level, and no such judgment is asserted here."
	},
	{
		id: "stem_identity",
		claim_class: "inferred",
		unknown: true,
		pages: ["features"],
		section: "restoration",
		text: "Stems are an optional extension outside the default workflow. Any stem is an estimate computed from a mixture, never a recovered original track."
	},
	{
		id: "feat_review_tools",
		claim_class: "implemented",
		unknown: false,
		pages: ["features"],
		section: "review",
		text: "Tools estimate tempo candidates, mark onset offsets against a recorded click, find repeated regions and propose phrase boundaries, all without a predefined score."
	},
	{
		id: "feat_review_hypotheses",
		claim_class: "inferred",
		unknown: false,
		pages: ["features"],
		section: "review",
		text: "Every marker is a hypothesis carrying a source timestamp or span. Half-tempo and double-tempo ambiguity is kept, and an issue reported by a player stays labelled as theirs, apart from detector proposals."
	},
	{
		id: "feat_review_synthetic",
		claim_class: "measured_synthetic",
		unknown: false,
		pages: ["features"],
		section: "review",
		text: "Boundary, recurrence and timing hypotheses are scored against generated references, with abstentions retained. No figure is quoted here."
	},
	{
		id: "bpm_meter_phrase_nullable",
		claim_class: "unknown",
		unknown: true,
		pages: ["features"],
		section: "review",
		text: "BPM, meter, phrase boundaries and onset confidence may be unknown. When the evidence is insufficient the output says so and does not guess."
	},
	{
		id: "low_register_pitch_accuracy",
		claim_class: "unknown",
		unknown: true,
		pages: ["features", "status"],
		section: "review",
		text: "Pitch and note identification on distorted low-register guitar is unverified. Pitch output is a set of candidates, not a transcription, and a dominant spectral peak does not establish the note that was meant."
	},
	{
		id: "feat_agents_typed",
		claim_class: "implemented",
		unknown: false,
		pages: ["features"],
		section: "agent_tools",
		text: "Each tool has a typed input schema, a stated intent and a repository skill describing its settings, its dependencies and the evidence it produces."
	},
	{
		id: "feat_agents_evidence",
		claim_class: "implemented",
		unknown: false,
		pages: ["features"],
		section: "agent_tools",
		text: "Tools keep comparisons, sparse coverage, uncertainty and failures in their output so that a proposed setting can be assessed and not only applied."
	},
	{
		id: "agent_outcome_unknown",
		claim_class: "unknown",
		unknown: true,
		pages: ["features"],
		section: "agent_tools",
		text: "Whether settings chosen with an agent improve a take is not established. A tool that runs successfully has not thereby passed listening review or musical review."
	},
	{
		id: "agents_registry_scope",
		claim_class: "implemented",
		unknown: false,
		pages: ["agents"],
		section: "registry",
		text: "This list is generated at build time from the tool registry in the repository. A tool being listed means it exists. It says nothing about accuracy on any recording, and tools marked experimental may change or be withdrawn."
	},
	{
		id: "logic_au_host_acceptance",
		claim_class: "not_done",
		unknown: true,
		pages: ["status"],
		section: "not_done",
		text: "An Audio Unit plugin and acceptance in a Logic host are not done. A plugin is a later integration, and nothing described on this site runs inside a host today."
	},
	{
		id: "editor_import_proof",
		claim_class: "not_done",
		unknown: true,
		pages: ["status"],
		section: "not_done",
		text: "Marker import into Final Cut or Resolve is unverified. Marker files are a generic interchange pilot until an import is shown in the actual application."
	},
	{
		id: "hosted_availability",
		claim_class: "not_done",
		unknown: true,
		pages: ["status"],
		section: "not_done",
		text: "There is no public hosted service, sign-up or download. This site describes software that runs locally and is not distributed here."
	},
	{
		id: "site_accessibility_review",
		claim_class: "not_done",
		unknown: true,
		pages: ["status"],
		section: "not_done",
		text: "Colour contrast ratios for this site have not been measured, and a keyboard walkthrough in a browser has not been recorded. Structure and theme tokens are checked automatically; that is not an accessibility audit."
	}
];

export function claimsFor(page: PageId, section?: SectionId): readonly Claim[] {
	return CLAIMS.filter((claim) => claim.pages.includes(page) && (section === undefined || claim.section === section));
}
