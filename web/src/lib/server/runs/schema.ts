// Effect Schemas for the S3 routes_review read API (scripts/web_runs_api.py; ROUTES_REVIEW_S3.md sections 3-5).
// Server-only. Decoded closed (onExcessProperty: "error", errors: "all"). Nullable unknown fields stay nullable
// and keep their reasons. Copied producer documents (tone_ab, coverage, flags triage, phrase timing) are decoded
// as closed envelopes {status, reason, document}; the inner document stays Schema.Unknown so a producer field
// addition cannot break a page (the UI reads it defensively). tests/test_web_runs_s3.py parses the top-level
// key lists of RunSummary, RunList, RunGraph, RunLayers and Capabilities from this file: keep one key per line.
import { Schema } from 'effect';

const SHA256_PATTERN = /^[0-9a-f]{64}$/;
const ARTIFACT_ID_PATTERN = /^art_[0-9a-f]{32}$/;
const SOURCE_ID_PATTERN = /^src_[0-9a-f]{32}$/;
export const EVIDENCE_ID_PATTERN = /^evd_[0-9a-f]{32}$/;
const SIGNAL_PATTERN = /^sha256:[0-9a-f]{64}$/;
const RUN_ID_PATTERN = /^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/;
export const MEDIA_NAME_PATTERN = /^[A-Za-z0-9][A-Za-z0-9._-]{0,95}$/;

const pattern = (re: RegExp) => Schema.String.check(Schema.isPattern(re));
const Sha256 = pattern(SHA256_PATTERN);
const ArtifactId = pattern(ARTIFACT_ID_PATTERN);
const SourceId = pattern(SOURCE_ID_PATTERN);
const EvidenceId = pattern(EVIDENCE_ID_PATTERN);
const Signal = pattern(SIGNAL_PATTERN);
const RunId = pattern(RUN_ID_PATTERN);
const Text = (max: number) => Schema.String.check(Schema.isMaxLength(max));
const NullText = (max: number) => Schema.NullOr(Text(max));
const Count = Schema.Int.check(Schema.isGreaterThanOrEqualTo(0));
const NullInt = Schema.NullOr(Schema.Int);
const NullFinite = Schema.NullOr(Schema.Finite);
const NullBool = Schema.NullOr(Schema.Boolean);
const Bounded = <S extends Schema.Top>(item: S, max: number) => Schema.Array(item).check(Schema.isMaxLength(max));

// --------------------------------------------------------------------------- shared

/** {value, reason[, basis]}: value is any JSON (including null); the reason is always carried. */
export const UnknownEntry = Schema.Struct({
	value: Schema.Unknown,
	reason: NullText(4000),
	basis: Schema.optionalKey(Text(400))
});
export type UnknownEntry = typeof UnknownEntry.Type;

export const S2_UNKNOWN_KEYS = [
	'operator_preference',
	'listening_acceptance',
	'perceived_fullness',
	'nasal_quality',
	'fundamental_32hz_presence',
	'monitoring_device',
	'true_peak_dbtp',
	'fan_only_gain',
	'music_only_gain',
	'click_identity',
	'physical_capture_latency',
	'detector_delay',
	'meter',
	'downbeat_confirmed',
	'anchor_adopted',
	'breakdown1_execution',
	'real_take_phrase_correctness',
	'missed_or_extra_notes',
	'phrase_timing.real_take_status',
	'browser_level_match',
	'walkthrough_listening'
] as const;
export const S3_UNKNOWN_KEYS = [
	'clock_alignment',
	'bpm',
	'annotation_source',
	'editor_import',
	'share_low_register_preservation',
	'model_local_presence',
	'model_gate_state',
	'tool_area_basis',
	'physical_av_sync',
	'spectrogram_binding',
	'room_response_recovered',
	'stems'
] as const;

export const UnknownFields = Schema.Struct(
	Object.fromEntries([...S2_UNKNOWN_KEYS, ...S3_UNKNOWN_KEYS].map((key) => [key, UnknownEntry])) as Record<
		(typeof S2_UNKNOWN_KEYS)[number] | (typeof S3_UNKNOWN_KEYS)[number],
		typeof UnknownEntry
	>
);
export type UnknownFields = typeof UnknownFields.Type;

export const ClaimBoundary = Schema.Struct({
	listening_acceptance_scope: NullText(600),
	musical_verdict: Schema.Literal('not_established'),
	missed_or_extra_notes: Schema.Literal('not_assessed_no_approved_reference'),
	default_adopted: Schema.Literal(false),
	master_changed: Schema.Literal(false)
});

// --------------------------------------------------------------------------- runs list

export const RunSummary = Schema.Struct({
	run_id: RunId,
	run_status: NullText(120),
	source_id: Schema.NullOr(SourceId),
	source_sha256: Schema.NullOr(Sha256),
	manifest_sha256: Schema.NullOr(Sha256),
	manifest_readable: Schema.Boolean,
	stage_count: Schema.NullOr(Count),
	state_basis: Schema.Literal('listing does not re-hash')
});
export type RunSummary = typeof RunSummary.Type;

export const RunList = Schema.Struct({
	schema_id: Schema.Literal('video-utils.web-runs.list'),
	schema_version: Schema.Literal(1),
	runs: Bounded(RunSummary, 500),
	truncated: Schema.Boolean
});
export type RunList = typeof RunList.Type;

// --------------------------------------------------------------------------- run graph

export const STAGE_STATES = ['current', 'stale', 'missing', 'unbound'] as const;
export const EVIDENCE_KINDS = ['practice_bundle', 'lowreg_render', 'editor_marker_export', 'marked_compact'] as const;
export const EVIDENCE_STATES = ['current', 'invalidated', 'refused', 'unbound'] as const;
export const INVALIDATION_REASONS = [
	'bound_manifest_changed',
	'analyzed_input_not_current',
	'file_hash_mismatch',
	'source_mismatch'
] as const;

const Stage = Schema.Struct({
	stage: Text(300),
	file_role: Text(300),
	role_basis: Text(200),
	artifact_id: Schema.NullOr(ArtifactId),
	signal_version: Schema.NullOr(Signal),
	state: Schema.Literals(STAGE_STATES),
	size_bytes: Schema.NullOr(Count)
});
export type Stage = typeof Stage.Type;

const Edge = Schema.Struct({ from: Text(300), to: Text(300), edge_basis: Text(200) });

const AdmittedSource = Schema.Struct({
	source_artifact_id: ArtifactId,
	kind: Text(32),
	has_annotation_clock: NullBool
});

const Processing = Schema.Struct({
	profile_name: NullText(200),
	denoise: Schema.Struct({ filter: NullText(64), delay_samples: NullInt, status: NullText(120) }),
	tone: Schema.Struct({
		peaking_eq: Bounded(Schema.Struct({ frequency_hz: NullFinite, gain_db: NullFinite, q: NullFinite }), 16),
		compressor: Schema.NullOr(Schema.Record(Schema.String, NullFinite))
	}),
	loudness_targets: Schema.Record(Schema.String, Schema.Record(Schema.String, NullFinite)),
	high_pass_applied: NullBool,
	hum_notches_applied: NullBool,
	intentional_low_fundamental_hz: NullFinite,
	noise_capture: Schema.Struct({ selected_seconds: Schema.NullOr(Bounded(NullFinite, 2)), review: NullText(2000) }),
	dsp_latency_status: Schema.Record(Schema.String, NullText(120)),
	manifest_listening_accepted_field: NullBool
});
export type Processing = typeof Processing.Type;

const EvidenceFile = Schema.Struct({
	name: Text(200),
	role: Text(200),
	artifact_id: ArtifactId,
	sha256: Sha256,
	size_bytes: Schema.NullOr(Count),
	import_verified: NullBool
});
export type EvidenceFile = typeof EvidenceFile.Type;

const Evidence = Schema.Struct({
	evidence_id: EvidenceId,
	kind: Schema.Literals(EVIDENCE_KINDS),
	state: Schema.Literals(EVIDENCE_STATES),
	reason: NullText(200),
	bound_signal_version: Schema.NullOr(Signal),
	generated_utc: NullText(64),
	files: Bounded(EvidenceFile, 16)
});
export type Evidence = typeof Evidence.Type;

const Invalidation = Schema.Struct({
	evidence_id: EvidenceId,
	reason: Schema.Literals(INVALIDATION_REASONS),
	was_bound_to: Schema.NullOr(Signal),
	now: Schema.NullOr(Signal)
});

const ListeningAcceptance = Schema.Struct({
	value: Schema.Literals(['accepted', 'not_established']),
	reason: Text(600),
	scope: NullText(600),
	receipt_sha256: Schema.NullOr(Sha256),
	master_adopted: Schema.Literal(false),
	accepted_file_sha256: Bounded(Sha256, 8)
});
export type ListeningAcceptance = typeof ListeningAcceptance.Type;

export const RunGraph = Schema.Struct({
	schema_id: Schema.Literal('video-utils.web-runs.run'),
	schema_version: Schema.Literal(1),
	run_id: RunId,
	run_status: NullText(120),
	manifest_sha256: Sha256,
	source_sha256: Schema.NullOr(Sha256),
	source_id: Schema.NullOr(SourceId),
	admitted_sources: Bounded(AdmittedSource, 64),
	admitted_sources_lookup: Schema.Literals(['available', 'unavailable']),
	pcm: Schema.Struct({ sample_rate: NullInt, channels: NullInt, sample_count: NullInt, duration_seconds: NullFinite }),
	timeline: Schema.Struct({
		audio_start_seconds: NullFinite,
		format_start_seconds: NullFinite,
		no_time_stretch: NullBool,
		axis: Schema.Literal('decoded source audio seconds')
	}),
	stages: Bounded(Stage, 256),
	edges: Bounded(Edge, 64),
	processing: Processing,
	evidence: Bounded(Evidence, 512),
	invalidation: Bounded(Invalidation, 512),
	listening_acceptance: ListeningAcceptance,
	claim_boundary: ClaimBoundary,
	unknown_fields: UnknownFields,
	discovery_truncated: Schema.Boolean
});
export type RunGraph = typeof RunGraph.Type;

// --------------------------------------------------------------------------- layers

const LayerEnvelope = Schema.Struct({
	status: Schema.Literals(['available', 'unavailable']),
	reason: NullText(200),
	document: Schema.Unknown
});
export type LayerEnvelope = typeof LayerEnvelope.Type;

const SpectrogramEnvelope = Schema.Struct({
	status: Schema.Literals(['available', 'unbound', 'unavailable']),
	reason: NullText(200),
	document: Schema.Null
});

const Bpm = Schema.Struct({
	value: NullFinite,
	reason: Text(400),
	basis: NullText(200),
	grid: Schema.NullOr(
		Schema.Struct({ period_seconds: Schema.Finite, phase_seconds: Schema.Finite, window_seconds: NullFinite, basis: Text(300) })
	)
});
export type Bpm = typeof Bpm.Type;

const MediaRecord = Schema.Struct({
	evidence_id: EvidenceId,
	sha256: Sha256,
	frames: NullInt,
	sample_rate: NullInt,
	channels: NullInt,
	role: NullText(200)
});
export type MediaRecord = typeof MediaRecord.Type;

const Spectrogram = Schema.Struct({
	status: Schema.Literals(['available', 'unbound', 'unavailable']),
	reason: NullText(200),
	evidence_id: Schema.NullOr(EvidenceId),
	signal_version: Schema.NullOr(Signal),
	stage: NullText(300),
	shape: Schema.NullOr(Schema.Struct({ frames: NullInt, bands: NullInt })),
	band_centre_hz: Bounded(Schema.Finite, 4096),
	band_centre_hz_range: Schema.NullOr(Bounded(Schema.Finite, 2)),
	hop_seconds: NullFinite,
	window_seconds: NullFinite,
	first_frame_centre_seconds: NullFinite,
	axis_offset_seconds: NullFinite,
	matrices: Bounded(
		Schema.Struct({
			name: Schema.Literals(['log_power_db', 'pcen']),
			media_name: pattern(MEDIA_NAME_PATTERN),
			sha256: Sha256,
			dtype: NullText(64),
			layout: NullText(64),
			status: Text(80)
		}),
		2
	),
	reference_lines: Bounded(Schema.Struct({ label: Text(120), hz: Schema.Finite }), 16),
	claim: Schema.Literal('visualisation only; no pitch, note or stem claim'),
	pcen_status: NullText(80)
});
export type Spectrogram = typeof Spectrogram.Type;

export const RunLayers = Schema.Struct({
	schema_id: Schema.Literal('video-utils.web-runs.layers'),
	schema_version: Schema.Literal(1),
	run_id: RunId,
	manifest_sha256: Sha256,
	selected_evidence_id: Schema.NullOr(EvidenceId),
	selected_generated_utc: NullText(64),
	alternatives: Bounded(EvidenceId, 512),
	layers: Schema.Struct({
		tone_ab: LayerEnvelope,
		coverage: LayerEnvelope,
		flags_triage: LayerEnvelope,
		phrase_timing: LayerEnvelope,
		spectrogram: SpectrogramEnvelope,
		bpm: Bpm
	}),
	media: Schema.Record(Schema.String, MediaRecord),
	spectrogram: Spectrogram,
	clock: Schema.Struct({
		layer_axis: Schema.Literal('original source decoded-audio seconds'),
		annotation_axis: Text(300),
		alignment: Schema.Literal('unverified'),
		reason: Text(600)
	}),
	source_extent: Schema.Struct({ audio_start_seconds: NullFinite, duration_seconds: NullFinite }),
	unknown_fields: UnknownFields,
	claim_boundary: ClaimBoundary,
	discovery_truncated: Schema.Boolean
});
export type RunLayers = typeof RunLayers.Type;

// --------------------------------------------------------------------------- capabilities

const Capability = Schema.Struct({
	domain: NullText(64),
	stage: NullText(64),
	effects: Schema.Struct({
		reads: Bounded(Text(64), 32),
		writes: Bounded(Text(64), 32),
		renders_audio: NullBool,
		renders_video: NullBool,
		network: NullBool,
		model_acquisition: NullBool,
		overwrites_input: NullBool
	}),
	resources: Schema.Struct({
		resource_class: NullText(64),
		heavy_numeric: NullBool,
		timeout_seconds: Schema.Struct({ min: NullFinite, max: NullFinite, default: NullFinite })
	}),
	parameters: Schema.Record(Schema.String, Schema.Struct({ default_owner: NullText(32), default_policy: NullText(64) }))
});
export type Capability = typeof Capability.Type;

const Tool = Schema.Struct({
	name: Text(64),
	title: NullText(120),
	area: Text(64),
	area_basis: Text(200),
	implementation_status: NullText(64),
	evidence_kind: NullText(64),
	annotations: Schema.Struct({
		readOnlyHint: NullBool,
		destructiveHint: NullBool,
		idempotentHint: NullBool,
		openWorldHint: NullBool
	}),
	skill: NullText(300),
	limitations_count: Count,
	limitations: Bounded(NullText(2000), 64),
	dependencies: Schema.Struct({ recommended_prior_tools: Bounded(Text(64), 32), enforced: NullBool, note: NullText(600) }),
	input: Schema.Struct({ properties: Bounded(Text(64), 128), required: Bounded(Text(64), 128) }),
	capability: Schema.NullOr(Capability),
	capability_reason: NullText(200)
});
export type Tool = typeof Tool.Type;

const Model = Schema.Struct({
	model_id: Text(128),
	format: NullText(64),
	license: NullText(300),
	sha256: Schema.NullOr(Sha256),
	max_bytes: NullInt,
	source_commit: NullText(64),
	url_host: NullText(255),
	registration: Schema.Literals(['registered_hash_bound', 'registered_incomplete']),
	local_presence: Schema.Literal('not_checked'),
	lane: NullText(200),
	gate: NullText(200),
	status: NullText(200),
	gate_state: Schema.Struct({ value: NullText(200), reason: Text(200) })
});
export type Model = typeof Model.Type;

export const Capabilities = Schema.Struct({
	schema_id: Schema.Literal('video-utils.web-runs.capabilities'),
	schema_version: Schema.Literal(1),
	tool_count: Count,
	pilot_tool_count: Count,
	tools: Bounded(Tool, 256),
	areas: Bounded(Schema.Struct({ area: Text(64), tools: Bounded(Text(64), 256) }), 64),
	models: Bounded(Model, 256),
	model_note: Text(600),
	registry_sha256: Schema.Struct({ tools: Sha256, capabilities: Sha256, models: Sha256 }),
	unknown_fields: Schema.Struct({
		model_local_presence: UnknownEntry,
		model_gate_state: UnknownEntry,
		tool_area_basis: UnknownEntry
	})
});
export type Capabilities = typeof Capabilities.Type;

// --------------------------------------------------------------------------- helpers

const structs = [
	UnknownEntry,
	UnknownFields,
	ClaimBoundary,
	RunSummary,
	RunList,
	Stage,
	Edge,
	AdmittedSource,
	Processing,
	Processing.fields.denoise,
	Processing.fields.tone,
	Processing.fields.noise_capture,
	EvidenceFile,
	Evidence,
	Invalidation,
	ListeningAcceptance,
	RunGraph,
	RunGraph.fields.pcm,
	RunGraph.fields.timeline,
	LayerEnvelope,
	SpectrogramEnvelope,
	Bpm,
	MediaRecord,
	Spectrogram,
	RunLayers,
	RunLayers.fields.layers,
	RunLayers.fields.clock,
	RunLayers.fields.source_extent,
	Capability,
	Capability.fields.effects,
	Capability.fields.resources,
	Tool,
	Tool.fields.annotations,
	Tool.fields.dependencies,
	Tool.fields.input,
	Model,
	Model.fields.gate_state,
	Capabilities,
	Capabilities.fields.registry_sha256,
	Capabilities.fields.unknown_fields
];

/** Every field name the closed run schemas know; used to keep decode error paths free of upstream text. */
export const KNOWN_RUN_FIELD_NAMES: ReadonlySet<string> = new Set(structs.flatMap((s) => Object.keys(s.fields)));

export const isEvidenceId = (value: string): boolean => EVIDENCE_ID_PATTERN.test(value);
export const isMediaName = (value: string): boolean => MEDIA_NAME_PATTERN.test(value);
