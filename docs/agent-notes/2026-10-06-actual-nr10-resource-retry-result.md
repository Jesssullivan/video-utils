# Actual NR10 resource retry: rendered candidate

Root's new exact single-retry release
`2026-10-06-root-actual-nr10-resource-retry-release.json` (SHA256
`24ba4717093779c7afbb7d8ade6cba493353ed6d93a0b447f48f3336023392f9`)
authorized the existing NR10 source-bound profile through application `790ac58f…`.
Media `91443154…`, author `7d282087…`, source `a522115f…`, capture and DSP controls
were unchanged. The resource-only repair had 51 passing fixtures, the new exact
8-second native trial and independent artifact audit before this release.

Actor `/root/media_latency` launched controller execution session 33666 once.
The exact CLI child PID/session/group 78105, arguments and ownership checks were
saved before observation. It used 600 seconds internally, 610 seconds for the
outer stage, two threads, bounded 4 MiB file-backed output and qualified shared
five-second cleanup. Controller `46ca7e3f…` is a minimal successor of the earlier
paired controller. It preserves full CLI error output and publication recovery
on failure; there was no automatic retry or further approval stage.

The retry completed after 512.843 seconds, exit zero, and published only the
fresh `rendered_unreviewed` candidate
`artifacts/runs/20261006T034521Z-a0def0c43eac`. Manifest SHA256:
`a6c371ab36e1f50b850f167a42b010ffa7b923b32aca14f4bfd70fb24036077c`;
application receipt SHA256:
`71a3a33e221f02d1b5141cdaaaf023d498decf2a615ed0763de5bfd70a5abfc7`.
The controller receipt under
`artifacts/experiments/actual-nr10-resource-retry-20261006T0345/receipt.json`
has SHA256 `12761e959b55bd192e7e48c4e37c9bdd1dd6fdaf54fb2dc111c62c0ccfc29963`.
The sibling dated JSON binds all selectors and native/timing/protected evidence.

Native extent stayed 6657385 mono sample frames at 44100 Hz (150.961111 seconds),
source origin zero, with no time stretch. Capture remained `[180810,218295)`
samples, audio-relative 4.10–4.95 seconds, with music/click uncertainty and
noise-only status unverified. Measured afftdn delay was 1102 samples and its
recorded remaining bulk delay zero. Two causal peaking EQ bands and the fixed
25-percent wet RMS compressor retained native extent; their phase/envelope
effects are distinct from physical waveform synchronization.

Exporter proof records 3621 decoded picture frames and 3631 packets, ordered
payload hashes preserved, zero PTS/DTS/duration deltas and zero clock translation.
Decoded AAC measured −18.01 LUFS and −1.75 dBTP, meeting the recorded −1.75 dBTP
ceiling on its first encode, with no additional feed attenuation. Container
duration diagnostics remain separate from decoded picture and native PCM extent.
This is measured delivery evidence, not a listening or physical-sync claim.

All protected identities, including original/current/master/latest, prior and
new profiles and completed NR8, were verified unchanged. The prior NR10 failure
receipt `72e88ebd…` was rehashed unchanged and retained. No NR8 rerender, latest
promotion, master adoption or new marker burn occurred. The successful runtime
recorded no inspection retry; recovered-timeout behavior remains established by
the injected resource fixtures, not an invented timeout in this actual run.

Independent closure: release_review's saved-artifact audit passed native extent,
capture, delay, residue, existing picture/AAC receipts and all protected hashes.
Its durable `2026-10-06-actual-nr10-resource-independent-artifact-audit.json`
has SHA256 `9ad57bc926339676dec3f663d5295217dc681b1f0eb07e78d93215ae2d4994ba`.
The earlier result JSON retains its pre-audit status. A separately authorized
fresh extended analysis subsequently passed all 15 stages; its dated
`2026-10-06-nr10-extended-analysis-result.md` records that next proof class.

Status: NR10 candidate rendered and independent saved-artifact audit passed.
NR8 and NR10 are matched unreviewed restoration candidates. Listening acceptance,
musical quality and any master choice remain separate.
