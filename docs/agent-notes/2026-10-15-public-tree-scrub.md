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
| After, raw (no exceptions) | 456 | 148 |
| After, with the test's exceptions | 0 | 0 |

Before, by rule: developer-filesystem-path 1,374, private-network-address 213, nix-store-path 210,
real-take-filename 43, private-estate-hostname 42, internal-hostname 6.

The raw after-count includes this receipt and breaks down as follows:

- 38 hits are in the 2 frozen receipts (decision 3): 32 personal paths and 6 pinned store paths.
- 210 are loopback `127.0.0.1`.
- 143 are the pinned FFmpeg store path (134) and Nix store detector literals (9).
- 30 are host-path-shaped fixtures (one a store path), sentinels and three relative `root/` directories.
- 35 are Access team fixtures (14), the gateway contract (17) and the repository's own Service name (4).

0 real take names remain anywhere in the tree, and 0 non-loopback private addresses.

A first version of this receipt (PR head `17c0aa8`) kept 15 receipts frozen and reported 550 raw hits in
156 files; that count missed this receipt's own two loopback quotes (552 in 157). Review found that only two
of the 15 are pinned by code that still runs, so the other 13 were scrubbed (decision 3).

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
3. **Frozen receipts.** Two receipts stay byte-identical, because code that still runs pins them by
   sha256:
   - `2026-10-05-captured-restoration-comparison.json` is pinned by the low-register gate
     (`scripts/low_register_actual_diagnostic.py`). The gate's own hash is the released worker hash, so
     re-pinning it would also void that release.
   - `2026-10-06-capture-application-resource-qualification-result.json` is pinned by
     `docs/agent-notes/2026-10-06-nr8-nr10-comparison.py`, and `tests/test_nr8_nr10_comparison.py` loads
     that worker and checks the pin.

   Together they keep 38 hits: 32 personal paths and 6 pinned store paths, and no take name.
   `FROZEN_EVIDENCE` in the test exempts each one only while its sha256 is unchanged. Scrubbing them needs
   an operator decision to re-pin the gates.

   The method was a `git grep` of each candidate's file name and sha256 over `tests/`, `scripts/`, `src/`,
   `just/`, `bazel/` and the experiment scripts that tests load. The other 13 receipts and experiment
   scripts the first version froze are pinned only by archived one-shot experiment scripts and receipts
   under `docs/agent-notes/`, which nothing executes. They were scrubbed like the 154 others and added to
   the rebind list. They held all 12 remaining take names and 90 developer-path hits.
   `2026-10-06-root-low-register-diagnostic-release.json` is not hash-pinned by live code. The gate reads
   its `audit_path`, which now names the audit repo-relative instead of under the operator's home. The
   gate therefore resolves the audit from a checkout root, and the audit's sha256 is unchanged.
4. **Hash-recorded receipts.** 202 of the 419 hit files had their sha256 recorded elsewhere in the tree,
   mostly by later receipts. Apart from the frozen ones, they were scrubbed. A recorded hash now refers to
   the pre-scrub bytes, which stay in Git history. `2026-10-15-public-tree-scrub-rebind.json` lists the 166
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
manifest, and the pinned FFmpeg store path. There are 2 frozen-evidence entries, each checked by sha256,
and 28 path-and-rule exceptions:

- 3 relative directories named `root`
- leak detectors and their sentinels
- host-path-shaped fixtures that the code must refuse or redact
- synthetic Access team domains
- the guitar_noul gateway host contract, which `scripts/guitar_noul_client.py` enforces. The
  `guitar-noul` skill and `MODEL_LANES_S3.md` name the literal accepted host again, because the agent
  contract must say which host the client accepts. The domain is already public through the client, its
  tests and the site rules. The skill is back to its pre-scrub bytes and left the rebind list.

A stale exception fails the test. A planted file proves that each of the twelve rules fires.

## Not done / findings

- History rewrite: not done (operator decision in TIN-6515). The pre-scrub bytes remain in history.
- The guitar_noul client hard-codes the estate gateway host. Moving it to configuration would remove one
  exception.
- The S4 sprint goal of a scan with 0 hits holds only with the exceptions. The 2 frozen receipts still
  carry the operator user name in paths until their gates are re-pinned.
- The site check `test_m13` used to read the take name from README and PROJECT.md. It now reads it from
  local run manifests when runs exist (`tests/test_public_site_s3.py`, an out-of-lane edit made because the
  scrub removed its source). Without local runs, as in hosted CI, the exact-name check is a no-op, and the
  real-take-filename shape rule is the only take-name guard there.
- `deploy/cloudflare/video-utils-app-origin-routes.json`, `docs/research/2026-10-07-estate-auth-hosting.md`
  and `docs/spec/sprints/AUTH_HOSTING_S3.md` cite an external routes file as
  `<cluster>-ingress-mothership-xoxd-ai-routes.json`. `mothership` there is the routed application's
  hostname label, as in `mothership-xoxd-ai`, not a machine name. This is an inference from the file
  name and is not verified against the external repository; the operator can confirm it on TIN-6515. With the cluster as a placeholder, the cited path no longer
  resolves verbatim at the pinned commit. The pinned commit and its `infra/cloudflare/` directory still
  locate it.
- Hosted CI exercises `tests/test_public_tree.py` through the offline job. It is registered in
  `tests/BUILD.bazel` and `bazel/test_classification_s3_full.json` as a host tool (it runs `git`), and the
  hosted Bazel job excludes host-tool modules, the same as `test_condense_public_surface`.
- `program/linear.json` and Linear readback copies now differ from the live Linear text where Linear
  itself names a host (one project name). The tracker text is the operator's to change.
- Project and organisation names (tinyland, xoruby, legalab, blahaj) and git author identity are not
  host or path identifiers and were left as they are.
- `scripts/report_bundle.py` no longer lists the operator's Documents and Desktop by absolute path. It
  protects the running user's own Documents and Desktop, and it refuses any macOS user's Documents or
  Desktop by pattern, whatever HOME is. `tests/test_report_bundle.py` covers the pattern with a fixture
  user.

## Gates

Listed in the PR checks and in the TIN-6515 comment.
