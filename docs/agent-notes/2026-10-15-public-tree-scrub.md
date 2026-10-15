# Public-tree scrub (2026-10-15)

Authority: S4 lane L9-scrub, Linear TIN-6515; operator decision: forward scrub only, no history rewrite,
no visibility change (docs/spec/sprints/20261015-S4.md, "The forward scrub needs no go"); R-N13.

Scope: every tracked text file, scanned with the twelve site leak-scan rules that
`tests/test_condense_public_surface.py` applies to `condense/` (`site/scripts/leak-scan-rules.json`).
Binary and non-UTF-8 files are skipped. The new `tests/test_public_tree.py` makes the scan permanent.

## Counts

Measured with the same twelve rules over `git ls-files`.

| State | Hits | Files |
| --- | --- | --- |
| Before (main at the lane base) | 1,888 | 419 |
| After, raw (no exceptions) | 550 | 156 |
| After, with the test's exceptions | 0 | 0 |

Before, by rule: developer-filesystem-path 1,374, private-network-address 213, nix-store-path 210,
real-take-filename 43, private-estate-hostname 42, internal-hostname 6.

The raw after-count breaks down as follows:

- 145 hits are in 15 frozen receipts (decision 3): 122 personal paths, 12 take names and 11 pinned
  store paths.
- 208 are loopback `127.0.0.1`.
- 139 are Nix store paths outside the frozen receipts: the pinned FFmpeg store path and detector
  literals.
- 28 are host-path-shaped fixtures, sentinels and three relative `root/` directories.
- 30 are Access team fixtures, the gateway contract and the repository's own Service name.

Outside the frozen receipts, 0 real take names and 0 non-loopback private addresses remain.

## Classification and treatment

| Class | Treatment |
| --- | --- |
| Checkout path under the operator's home | `<repo>` |
| Other operator-home paths | `<operator-home>`; temporary folders `<tmpdir>`; an external volume `<external-volume>`; work and scratch roots `<work-root>`, `<scratch-root>` |
| Agent-tree actor ids (a leading slash, then `root/<lane>`) | `root/<lane>`; the leading slash made them read as the superuser home |
| Nix store paths | the pinned FFmpeg output stays (see below); other store paths keep hash and name under `<nix-store>/`, so no store hash changed |
| The real take's file name | `<demo-take>`; its source sha256 is unchanged |
| Real LAN address | `<peer-host-address>` |
| Fixture private addresses | RFC 5737 documentation addresses (`192.0.2.1`, `192.0.2.10`) |
| Estate hosts in prose | roles: the model gateway host, `<operator-team>`/`<test-team>`/`<other-team>` Access team names, `<estate-staging-service>`, `<estate-remote-execution-service>`, `<cluster>-ingress`, `openebs-<node>-zfs` |
| Bare host names (not covered by a rule) | roles: operator host, peer host, compute host, build host, builder; the peer note was renamed to `2026-10-06-s2-peer-host.md` |
| Code fixtures | real user name replaced by `fixture`; real take name replaced by a synthetic `Take on 1-2-03 at 4.56 PM`; real-run paths became checkout-relative |

## Decisions

1. **Nix store paths.** The store hash of the qualified FFmpeg output
   (`mv3x2v2p…-ffmpeg-headless-8.1.2-bin`) is code: tests and scripts resolve FFmpeg through it, and
   receipts bind it. `cache.nixos.org` serves its narinfo (checked 2026-10-15, HTTP 200), so it is a
   public build output, not a private identifier. It is exempt as that whole store path only. Of 41
   distinct store paths, 30 were on the public cache and 11 (local shell derivations and one estate
   guard) were not. Outside the frozen receipts, every store path other than the pinned one now reads
   `<nix-store>/<hash>-<name>`.
2. **Loopback.** `127.0.0.1` is exempt by value: the web stack's loopback-only bind is a tested
   security property, and the address names no host.
3. **Frozen receipts.** Fifteen receipts and experiment scripts stay byte-identical:
   - Thirteen are pinned by sha256 in executable code. The nr8/nr10 comparison worker and its
     source-freezes, the capture-application and nr10 artifact audits, and the desktop export scripts pin
     them; `tests/test_nr8_nr10_comparison.py` checks some of those pins.
   - `2026-10-05-captured-restoration-comparison.json` is pinned by the live low-register gate
     (`scripts/low_register_actual_diagnostic.py`, whose own hash still equals the released harness hash).
   - The gate opens its audit through the absolute `audit_path` in
     `2026-10-06-root-low-register-diagnostic-release.json`.

   Together they keep 145 hits: the operator user name in paths, the take name and the pinned store
   path. `FROZEN_EVIDENCE` in the test exempts each one only while its sha256 is unchanged. Scrubbing
   them needs an operator decision to re-pin the gates.
4. **Hash-recorded receipts.** 202 of the 419 hit files had their sha256 recorded elsewhere in the tree,
   mostly by later receipts. Apart from the frozen ones, they were scrubbed. A recorded hash now refers to
   the pre-scrub bytes, which stay in Git history. `2026-10-15-public-tree-scrub-rebind.json` lists the 154
   scrubbed files whose old sha256 the tree records, with the new sha256 and the pre-scrub commit. No hash
   value recorded in a receipt was edited.

   Every code path that rereads a receipt by hash was checked. Pins in executable code, including the
   experiment scripts under `docs/agent-notes/`, led to decision 3. Two other paths stay as they are:
   - The phrase-localization and phrase-riff release gates are already closed, because their scripts
     changed after release.
   - `scripts/phrase_riff_s2.py` compares its preregistration to `metadata()`, so its recorded
     interpreter label and the preregistration receipt changed together.
5. **Skill pin.** One host word in `.agents/skills/stems-estimate/SKILL.md` changed, so
   `tests/test_s3g_tool_admission.py` re-pins its sha256 and keeps the superseded value in a comment, as
   S2 follow-up 8 did.
6. **Bare host words are not in the tracked test.** Listing them would leak them. The test reads an
   optional untracked word file from `VIDEO_UTILS_PRIVATE_TERMS`. Run with the estate words, it found 0
   hits after the scrub.

## Exceptions in `tests/test_public_tree.py`

There are 3 value exceptions: loopback, the repository's own `video-utils-web` Service name in its deploy
manifest, and the pinned FFmpeg store path. There are 15 frozen-evidence entries, each checked by sha256,
and 26 path-and-rule exceptions:

- 3 relative directories named `root`
- leak detectors and their sentinels
- host-path-shaped fixtures that the code must refuse or redact
- synthetic Access team domains
- the guitar_noul gateway host contract, which `scripts/guitar_noul_client.py` enforces

A stale exception fails the test. A planted file proves that each of the twelve rules fires.

## Not done / findings

- History rewrite: not done (operator decision in TIN-6515). The pre-scrub bytes remain in history.
- The guitar_noul client hard-codes the estate gateway host. Moving it to configuration would remove one
  exception.
- The S4 sprint goal of a scan with 0 hits holds only with the exceptions. The 15 frozen receipts still
  carry the operator user name and the take name until their gates are re-pinned.
- The site check `test_m13` used to read the take name from README and PROJECT.md. It now reads it from
  local run manifests when runs exist, and the shape rule covers it otherwise
  (`tests/test_public_site_s3.py`, edited because the scrub removed its source).
- `program/linear.json` and Linear readback copies now differ from the live Linear text where Linear
  itself names a host (one project name). The tracker text is the operator's to change.
- Project and organisation names (tinyland, xoruby, legalab, blahaj) and git author identity are not
  host or path identifiers and were left as they are.
- `scripts/report_bundle.py` no longer lists the operator's Documents and Desktop by absolute path. It
  protects the running user's own Documents and Desktop, which are the same directories on the operator
  host.

## Gates

Listed in the PR checks and in the TIN-6515 comment.
