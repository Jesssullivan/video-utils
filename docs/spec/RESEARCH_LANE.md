# FOSS audio research lane

Plan recorded October 5, 2026 before the research pass. Owned outputs are this
plan and `docs/research/FOSS_AUDIO_MATRIX.md`; shared source, existing receipts,
README, PROJECT, media latency work, and other lanes remain outside this lane.

## Objective and instrument constraints

Produce a bounded primary-source decision matrix of 15–25 candidates and 6–10
practical decisions for the existing 35-hour week baseline plus optional 35-hour
extension. Recommendations must respect operator-stated nine-string pitch
classes C F Bb Eb Bb Eb Ab C F, inferred C1–F4 octaves, theoretical C1=32.703 Hz,
approximately 178 BPM context, changing/unknown meter, sweeps, tapping, legato,
and intentional distortion. Discovery and internal consistency review work
without an intended score; definite note/performance correctness needs reference
and calibration evidence.

## Research work and acceptance

1. Inspect primary upstream documentation, papers, source, releases, and licenses
   for restoration, music MIR/separation, tone ML, native/plugin interfaces, and
   AU diagnostics. Prefer exact package/API/version applicability to summaries.
2. For every candidate, record supported purpose/interface, source evidence,
   code-versus-weight licensing, this instrument's limiting case, and a bounded
   adopt/compare/defer decision. Unknown licensing or artifact provenance stays
   unknown; no model download follows from a research recommendation.
3. Separate public upstream capabilities from this repo's installed, tested,
   rendered, listened-to, and host-validated states. Treat the media latency
   lane's calibration as its evidence; do not independently change that worker.
4. Synthesize 6–10 adapter choices and evaluation gates within existing weekly
   budgets. Include source-time/delay/confidence boundaries and diagnostics that
   gather evidence without installing, deleting, rescanning, or repairing plugins.
5. Deliver a citation-linked matrix and concise priorities. Check local links,
   attribution, candidate count, and that every recommendation addresses the
   32.703 Hz/variable-meter/legato case. No heavy build, checkpoint download,
   recording upload, external publication, or host mutation is part of this lane.

## Decision receipt

Completed the [FOSS audio matrix](../research/FOSS_AUDIO_MATRIX.md): 23 candidate
rows, eight focused decisions, 74 source/file links, and priorities within the
existing 35+35 hours. A local structural check verified consecutive candidate
IDs, eight decision items, and existing local link targets. Primary-source
research was split between named read-only MIR and plugin/tone lanes; root's
clip-baseline lane assembled restoration evidence and the synthesis.

Key decisions retain the FFmpeg/native Swift-Rust direction, prioritize the
locked librosa 0.11.0/SuperFlux/recurrence plus FMP algorithms, qualify low-range
pYIN, and reserve a bounded Basic Pitch/Beat This comparison. Basic Pitch's
27.5 Hz lower range includes C1; accuracy on this guitar remains unverified.
RNNoise/DeepFilterNet stay out of the guitar default. Demucs checkpoint terms,
Essentia's conflicting model-license pages, and third-party RoFormer weights
remain explicit admission gaps rather than inferred code-license grants.

Version/license applicability includes FFmpeg 8.1.2 source, current Demucs 4.1.0
successor, JUCE 9.0.3, NIH-plug's actual VST3 binding terms/no native AU export,
and DPF's existing AU target. Architecture/format availability is distinct from
runtime, musical quality, AU validation, and Logic host acceptance.

No package/model download, build, recording upload, host/plugin mutation,
listening acceptance, or new media render occurred in this lane. Its only written
files are this plan/receipt and the new matrix. Existing shared docs, media
latency source, private artifacts, remote/tracker state, and root receipts were
preserved. Canonical RNNoise GitLab fetches were unavailable; the inspected
convenience-mirror API is identified as such, not promoted to latest canonical
evidence. Other unresolved artifact terms remain recorded for exact qualification.
