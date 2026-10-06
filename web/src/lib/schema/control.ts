// Effect Schemas for the merged S2 control API (scripts/web_api.py /api/v1, WEB_UI_S2.md section 4).
// control_api_contract_source: web_jobs_s2_merged. Structs are decoded closed
// (onExcessProperty: "error"); nullable/unknown fields stay nullable and keep their reasons.
// Only the six web_jobs states are decoded; the WEB_BACKEND states web_jobs collapses are not.
import { Schema } from 'effect';

export const JOB_ID_PATTERN = /^job_[0-9a-f]{32}$/;
export const ARTIFACT_ID_PATTERN = /^art_[0-9a-f]{32}$/;
const SOURCE_ID_PATTERN = /^src_[0-9a-f]{32}$/;
const SHA256_PATTERN = /^[0-9a-f]{64}$/;
const CODE_PATTERN = /^[a-z_]{1,64}$/;
const ISO_UTC_PATTERN = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d{1,9})?Z$/;
const ISO_OFFSET_PATTERN = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d{1,9})?(Z|[+-]00:00)$/;
const UUID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;

const pattern = (re: RegExp) => Schema.String.check(Schema.isPattern(re));
export const JobId = pattern(JOB_ID_PATTERN);
export const ArtifactId = pattern(ARTIFACT_ID_PATTERN);
const SourceId = pattern(SOURCE_ID_PATTERN);
const Sha256 = pattern(SHA256_PATTERN);
const Code = pattern(CODE_PATTERN);
const IsoUtc = pattern(ISO_UTC_PATTERN);
const Text = (max: number) => Schema.String.check(Schema.isMaxLength(max));
const BoundedText = (max: number) => Schema.String.check(Schema.isMinLength(1), Schema.isMaxLength(max));
const NonNegativeInt = Schema.Int.check(Schema.isGreaterThanOrEqualTo(0));
const NonNegativeFinite = Schema.Finite.check(Schema.isGreaterThanOrEqualTo(0));
const IntBetween = (minimum: number, maximum: number) => Schema.Int.check(Schema.isBetween({ minimum, maximum }));

// --------------------------------------------------------------------------- sources

export const SourceRecord = Schema.Struct({
	source_artifact_id: ArtifactId,
	source_id: Schema.NullOr(SourceId),
	source_id_reason: BoundedText(300),
	source_binding: Schema.Literals(['bound', 'unknown']),
	kind: Schema.Literal('video'),
	sha256: Sha256,
	size_bytes: NonNegativeInt,
	admitted_at: IsoUtc,
	origin: Schema.Literals(['upload', 'run_selector']),
	state: Schema.Literal('admitted'),
	rechecked: Schema.Literal(false),
	state_reason: BoundedText(300),
	duration_seconds: Schema.NullOr(NonNegativeFinite),
	duration_seconds_reason: BoundedText(300)
});
export type SourceRecord = typeof SourceRecord.Type;

export const SourceList = Schema.Struct({
	schema_version: Schema.Literal(1),
	sources: Schema.Array(SourceRecord).check(Schema.isMaxLength(500)),
	truncated: Schema.Boolean
});
export type SourceList = typeof SourceList.Type;

/** POST /api/v1/sources admission record (WEB_JOBS_S2 section 4.4). */
export const AdmissionRecord = Schema.Struct({
	source_artifact_id: ArtifactId,
	source_id: Schema.NullOr(SourceId),
	source_binding: Schema.Literals(['bound', 'unknown']),
	kind: Schema.Literal('video'),
	sha256: Sha256,
	size_bytes: NonNegativeInt,
	state: Schema.Literal('current')
});
export type AdmissionRecord = typeof AdmissionRecord.Type;

export const UploadResult = Schema.Struct({
	schema_version: Schema.Literal(1),
	upload: Schema.Struct({
		upload_id: pattern(/^upl_[0-9a-f]{16}$/),
		bytes: NonNegativeInt,
		sha256: Sha256,
		deduplicated: Schema.Boolean
	}),
	source: AdmissionRecord
});
export type UploadResult = typeof UploadResult.Type;

// --------------------------------------------------------------------------- jobs

export const JOB_STATES = ['queued', 'running', 'succeeded', 'failed', 'cancelled', 'interrupted'] as const;
export const JobState = Schema.Literals(JOB_STATES);
export type JobState = typeof JobState.Type;

export const JobParameters = Schema.Struct({
	height: IntBetween(240, 1080),
	crf: IntBetween(18, 32),
	audio_kbps: IntBetween(64, 192),
	codec: Schema.Literals(['h264', 'hevc', 'copy']),
	timeout_seconds: IntBetween(30, 900)
});
export type JobParameters = typeof JobParameters.Type;

export const JobProgress = Schema.Struct({
	completed: IntBetween(0, 6),
	denominator: Schema.Literal(6),
	unit: Schema.Literal('lifecycle_steps')
});

const CancelReceipt = Schema.Struct({
	reason: Schema.NullOr(Text(200)),
	requested_at: Schema.NullOr(IsoUtc),
	ack_at: Schema.NullOr(IsoUtc),
	signal_at: Schema.NullOr(IsoUtc),
	observed_stop_at: Schema.NullOr(IsoUtc),
	signal_target: Schema.NullOr(Code),
	signals_sent: Schema.NullOr(Schema.Array(Text(64)).check(Schema.isMaxLength(8))),
	group_empty_observed: Schema.NullOr(Schema.Boolean)
});

/** Path-free worker check projection (web_jobs._worker_checks); nested measurement blocks stay opaque. */
const WorkerChecks = Schema.Struct({
	status: Schema.optionalKey(Schema.NullOr(Text(64))),
	code: Schema.optionalKey(Schema.NullOr(Text(128))),
	returncode: Schema.optionalKey(Schema.Int),
	source_sha256: Schema.optionalKey(Schema.NullOr(Sha256)),
	source_bytes: Schema.optionalKey(Schema.NullOr(NonNegativeInt)),
	output_sha256: Schema.optionalKey(Schema.NullOr(Sha256)),
	output_bytes: Schema.optionalKey(Schema.NullOr(NonNegativeInt)),
	byte_reduction_fraction: Schema.optionalKey(Schema.NullOr(Schema.Finite)),
	settings: Schema.optionalKey(Schema.Unknown),
	codecs: Schema.optionalKey(Schema.Unknown),
	dimensions: Schema.optionalKey(Schema.Unknown),
	video_encode_count: Schema.optionalKey(Schema.NullOr(Schema.Int)),
	video_proof: Schema.optionalKey(Schema.NullOr(Schema.Record(Schema.String, Schema.Unknown))),
	audio_proof: Schema.optionalKey(Schema.NullOr(Schema.Record(Schema.String, Schema.Unknown))),
	loudness: Schema.optionalKey(Schema.Unknown),
	output_decode_errors_checked: Schema.optionalKey(Schema.Unknown),
	master_adopted: Schema.optionalKey(Schema.NullOr(Schema.Boolean)),
	listening_accepted: Schema.optionalKey(Schema.NullOr(Schema.Boolean))
});
export type WorkerChecks = typeof WorkerChecks.Type;

const Attempt = Schema.Struct({
	attempt: IntBetween(1, 1000),
	state: JobState,
	worker_kind: Schema.NullOr(Schema.Literals(['tool_api_share_export', 'test_stub'])),
	reason_code: Schema.NullOr(Code),
	started_at: Schema.NullOr(IsoUtc),
	ended_at: Schema.NullOr(IsoUtc),
	liveness: Schema.NullOr(Schema.Literals(['dead', 'alive_unowned', 'unknown'])),
	reconciled_publication: Schema.Boolean,
	cancel: Schema.NullOr(CancelReceipt),
	worker_checks: Schema.NullOr(WorkerChecks)
});
export type Attempt = typeof Attempt.Type;

const JobArtifact = Schema.Struct({
	artifact_id: ArtifactId,
	attempt: IntBetween(1, 1000),
	role: Schema.Literals(['share_mp4', 'share_receipt', 'publication']),
	sha256: Sha256,
	size_bytes: NonNegativeInt,
	content_type: BoundedText(100),
	downloadable: Schema.Boolean
});
export type JobArtifact = typeof JobArtifact.Type;

/** WEB_JOBS_S2 section 6 unknowns: every key and its *_reason. */
const Unknowns = Schema.Struct({
	listening_acceptance: Schema.Literal('not_established'),
	master_adopted: Schema.Literal(false),
	low_register_preservation: Schema.Null,
	low_register_preservation_reason: BoundedText(300),
	musical_review: Schema.Null,
	musical_review_reason: BoundedText(300),
	source_duration_seconds: Schema.NullOr(NonNegativeFinite),
	source_duration_seconds_reason: BoundedText(300),
	memory_bytes_peak: Schema.Null,
	memory_bytes_peak_reason: BoundedText(300),
	cpu_seconds: Schema.Null,
	cpu_seconds_reason: BoundedText(300),
	exactly_once: Schema.Literal('not_claimed'),
	slo: Schema.Literal('not_claimed'),
	worker_birth: Schema.NullOr(Schema.Literal('recorded')),
	worker_birth_reason: BoundedText(300)
});
export type Unknowns = typeof Unknowns.Type;

const ToolEnvelope = Schema.Struct({
	schema_version: Schema.Literal(1),
	tool: Schema.Literal('share_export'),
	evidence_kind: BoundedText(100),
	implementation_status: BoundedText(100),
	limitations: Schema.Array(Text(2000)).check(Schema.isMaxLength(32)),
	skill: BoundedText(300),
	instrument_context: Schema.Record(Schema.String, Schema.Unknown)
});

export const JobProjection = Schema.Struct({
	job_id: JobId,
	tool: Schema.Literal('share_export'),
	state: JobState,
	reason_code: Schema.NullOr(Code),
	source_artifact_id: ArtifactId,
	source_id: Schema.NullOr(SourceId),
	source_binding: Schema.Literals(['bound', 'unknown']),
	parameters: JobParameters,
	capability_revision: Sha256,
	idempotency_key: BoundedText(128),
	cancel_requested: Schema.Boolean,
	attempts: Schema.Array(Attempt).check(Schema.isMaxLength(64)),
	artifacts: Schema.Array(JobArtifact).check(Schema.isMaxLength(192)),
	claim_class: Schema.Literal('job_state_record'),
	unknowns: Unknowns,
	schema_version: Schema.Literal(1),
	phase: Schema.NullOr(Code),
	phase_reason: BoundedText(300),
	progress: Schema.NullOr(JobProgress),
	progress_reason: BoundedText(300),
	eta_seconds: Schema.Null,
	eta_seconds_reason: BoundedText(300),
	created_at: IsoUtc,
	updated_at: IsoUtc,
	tool_envelope: ToolEnvelope,
	replayed: Schema.optionalKey(Schema.Boolean),
	late_cancel: Schema.optionalKey(Schema.Boolean)
});
export type JobProjection = typeof JobProjection.Type;

export const JobSummary = Schema.Struct({
	job_id: JobId,
	state: JobState,
	reason_code: Schema.NullOr(Code),
	parameters: JobParameters,
	created_at: IsoUtc,
	updated_at: IsoUtc,
	attempt_count: IntBetween(1, 1000),
	artifact_count: NonNegativeInt
});
export type JobSummary = typeof JobSummary.Type;

export const JobList = Schema.Struct({
	schema_version: Schema.Literal(1),
	jobs: Schema.Array(JobSummary).check(Schema.isMaxLength(200)),
	truncated: Schema.Boolean
});
export type JobList = typeof JobList.Type;

// --------------------------------------------------------------------------- annotations (annotation_v2)

export const ANNOTATION_KINDS = [
	'rhythm_timing',
	'rhythm_pattern',
	'phrase_omission',
	'phrase_duration',
	'melodic_pitch',
	'articulation',
	'rest_execution',
	'meter_mismatch',
	'tone',
	'noise',
	'other'
] as const;

const SourceSpan = Schema.Struct({
	start_seconds: Schema.Finite,
	end_seconds: Schema.Finite,
	extent_known: Schema.Boolean
});
const Provenance = Schema.Struct({ manifest_sha256: Sha256, candidate_artifact_sha256: Schema.NullOr(Sha256) });

export const AnnotationRecord = Schema.Struct({
	id: pattern(UUID_PATTERN),
	candidate_id: Schema.NullOr(Sha256),
	reference_sha256: Schema.NullOr(Sha256),
	kind: Schema.Literals(ANNOTATION_KINDS),
	basis: Schema.Literals(['operator_assertion', 'operator_context', 'detector_hypothesis', 'reference_comparison']),
	status: Schema.Literals(['needs_review', 'accepted_observation', 'dismissed_candidate']),
	source_span: SourceSpan,
	reported_by: Schema.Struct({
		actor: Schema.Literals(['operator', 'agent', 'detector']),
		via: Schema.Literals(['browser', 'agent', 'cli'])
	}),
	operator_certainty: Schema.NullOr(Schema.Literals(['uncertain', 'confirmed'])),
	operator_quote: Schema.NullOr(Text(4000)),
	note: Text(4000),
	created_at: pattern(ISO_OFFSET_PATTERN),
	updated_at: pattern(ISO_OFFSET_PATTERN),
	created_with: Provenance,
	updated_with: Provenance,
	claim_label: Schema.Literals(['USER REPORTED', 'INTENT', 'REVIEW', 'REFERENCE REVIEW']),
	musical_verdict: Schema.Literal('not_established')
});
export type AnnotationRecord = typeof AnnotationRecord.Type;

export const AnnotationStorePublic = Schema.Struct({
	schema_version: Schema.Literal(2),
	source_sha256: Sha256,
	manifest_sha256: Sha256,
	revision: IntBetween(0, 512),
	annotations: Schema.Array(AnnotationRecord).check(Schema.isMaxLength(200)),
	listening_acceptance: Schema.Literal('not_established')
});
export type AnnotationStorePublic = typeof AnnotationStorePublic.Type;

export const AnnotationClock = Schema.Struct({
	source_start_seconds: Schema.Finite,
	source_end_seconds: Schema.Finite,
	duration_seconds: Schema.Finite,
	clock_basis: BoundedText(300),
	job_id: JobId,
	attempt: IntBetween(1, 1000),
	manifest_sha256: Sha256,
	player_clock_offset_verified: Schema.Literal(false),
	player_clock_offset_reason: BoundedText(400)
});
export type AnnotationClock = typeof AnnotationClock.Type;

export const AnnotationRead = Schema.Struct({
	schema_version: Schema.Literal(1),
	store: AnnotationStorePublic,
	clock: AnnotationClock
});
export type AnnotationRead = typeof AnnotationRead.Type;

export const AnnotationWrite = Schema.Struct({
	schema_version: Schema.Literal(1),
	store: AnnotationStorePublic,
	mutation: Schema.Struct({
		outcome: Schema.Literals(['saved', 'replayed']),
		annotation_id: pattern(UUID_PATTERN),
		committed_revision: IntBetween(1, 512)
	}),
	clock: AnnotationClock
});
export type AnnotationWrite = typeof AnnotationWrite.Type;

// --------------------------------------------------------------------------- helpers

const structs = [
	SourceRecord,
	SourceList,
	AdmissionRecord,
	UploadResult,
	UploadResult.fields.upload,
	JobParameters,
	JobProgress,
	CancelReceipt,
	WorkerChecks,
	Attempt,
	JobArtifact,
	Unknowns,
	ToolEnvelope,
	JobProjection,
	JobSummary,
	JobList,
	SourceSpan,
	Provenance,
	AnnotationRecord,
	AnnotationRecord.fields.reported_by,
	AnnotationStorePublic,
	AnnotationClock,
	AnnotationRead,
	AnnotationWrite,
	AnnotationWrite.fields.mutation
];

/** Every field name the closed schemas know; used to keep error paths free of upstream text. */
export const KNOWN_FIELD_NAMES: ReadonlySet<string> = new Set(structs.flatMap((s) => Object.keys(s.fields)));

export const isJobId = (value: string): boolean => JOB_ID_PATTERN.test(value);
export const isArtifactId = (value: string): boolean => ARTIFACT_ID_PATTERN.test(value);
