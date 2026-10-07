---
name: guitar-noul
description: DRAFT (S3 model_lanes, not admitted). Request per-window guitar_noul detector hypotheses from the tailnet-only models.xoxd.ai gateway under the TIN-5619 closed contract; refuses when the gateway is not configured, and sends real-take windows only with the explicit V6 operator switch.
---

# Request guitar_noul window hypotheses (TIN-5619, experimental)

**Status:** draft client. The gateway is not deployed: serving waits on
TIN-5590 parity, around 2026-10-10. The wire schema `tin-5619-v0` is
provisional and unratified (`gateway_wire_schema_ratified: false`).

Root still has to admit:
- the descriptor `guitar_noul_decide`;
- the MCP hook;
- the recipe.

## Intent

guitar_noul is an external read-only detector (the Rune model family served by
the xoxd inference lane). It returns one opaque decision label, or an abstain,
per source-timed window.

Agents use it as one more hypothesis next to project detectors. Its labels are
never annotations, flags, review badges, user labels or note verdicts.

## Input (closed)

```json
{"run_dir": "artifacts/runs/<run>", "windows": [{"source_start_s": 12.0, "source_end_s": 16.0}], "timeout_seconds": 60}
```

Rules:
- `run_dir` must be beneath `artifacts/runs/` or
  `artifacts/s2/model_lanes/fixtures/`.
- 1–64 non-overlapping windows. Each lasts 0.25–30 s and lies inside the
  manifest duration.
- `timeout_seconds` is an integer from 1 to 120.
- Extra keys refuse with `input_schema_invalid`.

## Configuration (environment only)

- `VIDEO_UTILS_GUITAR_NOUL_GATEWAY`:
  - must be `https` on `models.xoxd.ai` or a `*.ts.net` host, port 443, with no
    userinfo;
  - unset refuses with `gateway_not_configured`;
  - anything else refuses with `gateway_url_rejected`.
- `VIDEO_UTILS_GUITAR_NOUL_ALLOW_REAL_TAKE=v6-private-operator-lab-host`:
  - the only value that lets windows from a real take leave video-utils (V6
    ruling, 2026-10-07);
  - a run counts as synthetic only when its manifest declares
    `source.kind: "generated_fixture"` with a generator and a seed;
  - every other run is a real take and refuses with `real_take_not_permitted`
    without contacting the gateway.

The client holds no credentials. Identity is assumed to come from the tailnet
and tsidp, and the client does not verify it.

## Use

```sh
VIDEO_UTILS_GUITAR_NOUL_GATEWAY=https://models.xoxd.ai/<endpoint> \
  python3 scripts/guitar_noul_client.py --request request.json --out artifacts/s2/model_lanes/noul/<name>.json
```

- The client posts one JSON request. Each window carries a 16 kHz mono PCM16
  WAV excerpt of the manifest-verified `denoised.wav`, base64-encoded, up to
  8 MiB per request.
- Connection errors are retried once (`gateway_unreachable` after two attempts).
- HTTP 401/403 returns `gateway_auth_refused`.
- Output is never written inside `run_dir`.

## Reading `guitar_noul_decisions.json`

Each window carries:
- `decision.label` (an opaque string) or `abstain: true` with `abstain_reason`;
- `confidence_label`, which is gateway-reported and uncalibrated;
- `model_identity{gguf_sha256, catalog_name}`, validated against
  `xoxd/rune-26b-a4b-v3-xoruby-<recipe>-<date>`.

Abstain reasons:
- `gateway:<reason>`: the gateway's own abstain;
- `gateway_response_invalid`: the response failed validation, and the raw
  response sha256 is kept;
- `timeout`;
- `missing_from_response`.

Every window also carries these fixed fields:
- `claim_class: detector_hypothesis`
- `authorship: detector:guitar_noul`
- `is_label: false`, `user_reported: false`
- `note_correctness: null`, `performance_issue: null`
- `label_vocabulary_ratified: false`

Real-take results carry `privacy: V6_private_real_take_derived`.

## Iteration and evidence

- Compare the gateway's hypotheses with the project's phrase, onset and rhythm
  evidence for the same source spans, and listen to the disagreements.
- Keep `model_identity` and `input_identity.signal_version` with any
  comparison. Invalidate the comparison when either changes.
- Do not map labels to issue badges or count them as errors. Ratifying the label
  vocabulary and the wire schema is an open root/peer item on TIN-5619.
