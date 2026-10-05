# video-utils repository contract

## Mission and authority

Local-first restoration and rhythm analysis of guitar recordings in phone and
Photo Booth videos. The operator-approved October 5, 2026 plan is recorded in
`docs/spec/PROJECT.md`. Rust owns the CLI and reusable DSP; FFmpeg owns media
decoding/export; bounded Python owns offline analysis; R/Quarto owns research
reports. Swift AUv3 is a later integration, never an implicit runtime claim.

User instructions and the nearest repository overlay take precedence. Global
authority is R-HOOK-CONVERGENCE-20261004 (TIN-3692 comment
98cf680c-7299-4949-bfb2-60079053ad43): R-N11 requires target ownership/live-session
checks before signalling; R-N12 makes hooks advisory; R-N13 requires traceable
receipts, durable notes here, and factual tracker evidence. Do not edit sibling
repositories, terminate other sessions, or change host/plugin configuration as
part of this project.

## Work and interfaces

- `just` is the operator entrypoint. Root `justfile` routes `just/*.just`.
- Commit toolchain/dependency locks; model downloads are explicit and hash-bound.
- Original recordings, rendered media, model checkpoints, and caches stay out
  of Git. The repository is private; privacy still applies to CI/log artifacts.
- Preserve source rate/channels and timeline in masters. Analysis resampling is
  separate and recorded. Never overwrite the input.
- Keep workers bounded; use existing approved builders for heavy compilation,
  and cluster placement for GPU work after checking capacity. No new host daemon.
- Contributors own named files; root integrates and publishes. Parallel research
  and implementation lanes are authorized by the operator for this project.
- Verify behavior with meaningful synthetic fixtures and the actual demo.

## Evidence and acceptance

Measurements, inferences, and unverified listening claims must be distinct.
Never describe a mono-mixture estimate as a recovered original stem. Do not
label missed/extra notes without an approved expected-rhythm reference. BPM,
meter, phrase boundaries and onset confidence may be unknown.

Save research with primary-source links and limitations in `docs/research/`;
specifications in `docs/spec/`; dated run/implementation receipts in
`docs/agent-notes/`. Keep `program/linear.json` synchronized with published
project/issue IDs. Source checks, rendered demo, listening acceptance, AU
validation and actual Logic host acceptance are separate states.

AU render code must not allocate, block, invoke subprocesses, perform I/O,
download models, or unwind across a native ABI. Plugin installation and repairs
are outside this release's scope.

## Instrument and agent processing graph

The instrument is always a nine-string down-tuned guitar used for deathcore,
technical and virtuoso playing, with intentional fundamentals near 32 Hz.
Protect that low end; no blanket 80 Hz high-pass, mains notch or speech-denoiser
default. Palm mutes, rests, tuplets, tapping and sweeps are musical context.

The operator means musical phrase mistakes. Analyze a hash-bound graph: denoise
then click/BPM, pitch/tonic/mode evidence (nullable), phrase recurrence, and
review flags carrying source timestamps or spans. Every tool has a typed MCP
hook and a repository skill under `.agents/skills/`; agents inspect, research,
compare supported knobs and record evidence. Intended notes require tuning and
a reference; note correctness cannot follow from a dominant spectral peak.
Generic markers are an interchange pilot; Final Cut/Resolve import requires
actual application proof in a future milestone.
